"""Async UDP server for the Open Sail Tracker CoAP ingest."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import signal
import time
from datetime import datetime, timezone
from typing import Any

from .coap import (
    CODE_BAD_REQUEST,
    CODE_CHANGED,
    CODE_METHOD_NOT_ALLOWED,
    CODE_NOT_FOUND,
    CODE_POST,
    CODE_UNSUPPORTED_CONTENT_FORMAT,
    CONTENT_FORMAT_OCTET_STREAM,
    TYPE_CON,
    TYPE_NON,
    CoapError,
    CoapMessage,
    decode_message,
    encode_response,
)
from .protocol import PacketError, decode_position, decode_status
from .storage import VictoriaMetricsWriter, encode_telemetry

LOGGER = logging.getLogger("open_sail_tracker_backend")
ROUTES = {
    "/v1/position": decode_position,
    "/v1/status": decode_status,
}


def log_event(
    event: str,
    address: tuple[str, int],
    *,
    received_at: datetime | None = None,
    **fields: Any,
) -> None:
    record = {
        "timestamp": (received_at or datetime.now(timezone.utc)).isoformat(),
        "event": event,
        "source_ip": address[0],
        "source_port": address[1],
        **fields,
    }
    LOGGER.info(json.dumps(record, separators=(",", ":"), sort_keys=True))


def evaluate_request(message: CoapMessage) -> tuple[int, dict[str, Any] | None]:
    if message.message_type not in (TYPE_CON, TYPE_NON):
        return CODE_BAD_REQUEST, None
    if message.code != CODE_POST:
        return CODE_METHOD_NOT_ALLOWED, None

    try:
        path = message.uri_path
        content_format = message.content_format
    except (CoapError, UnicodeError):
        return CODE_BAD_REQUEST, None

    decoder = ROUTES.get(path)
    if decoder is None:
        return CODE_NOT_FOUND, None
    if content_format != CONTENT_FORMAT_OCTET_STREAM:
        return CODE_UNSUPPORTED_CONTENT_FORMAT, None

    try:
        packet = decoder(message.payload)
    except PacketError:
        return CODE_BAD_REQUEST, None
    return CODE_CHANGED, packet.as_log_dict()


class CoapIngestProtocol(asyncio.DatagramProtocol):
    def __init__(self, storage: VictoriaMetricsWriter | None = None) -> None:
        self.storage = storage

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        self.transport = transport
        LOGGER.info('{"event":"listener_started"}')

    def datagram_received(self, data: bytes, address: tuple[str, int]) -> None:
        received_at = datetime.now(timezone.utc)
        received_at_ms = time.time_ns() // 1_000_000
        try:
            message = decode_message(data)
        except CoapError as error:
            log_event(
                "invalid_coap",
                address,
                received_at=received_at,
                datagram_size=len(data),
                reason=str(error),
            )
            return

        code, decoded = evaluate_request(message)
        try:
            path = message.uri_path
        except (UnicodeError, ValueError):
            path = None

        if decoded is not None:
            log_event(
                "telemetry_received",
                address,
                received_at=received_at,
                coap_message_id=message.message_id,
                coap_path=path,
                packet=decoded,
            )
            if self.storage is not None:
                self.storage.submit(
                    encode_telemetry(
                        decoded,
                        coap_message_id=message.message_id,
                        coap_path=path or "unknown",
                        coap_type="confirmable" if message.message_type == TYPE_CON else "non_confirmable",
                        datagram_size=len(data),
                        source_ip=address[0],
                        source_port=address[1],
                        received_at_ms=received_at_ms,
                    )
                )
        else:
            log_event(
                "request_rejected",
                address,
                received_at=received_at,
                coap_code=code,
                coap_message_id=message.message_id,
                coap_path=path,
                datagram_size=len(data),
            )

        if message.message_type == TYPE_CON:
            response = encode_response(message, code)
            self.transport.sendto(response, address)  # type: ignore[attr-defined]

    def error_received(self, error: Exception) -> None:
        LOGGER.warning(json.dumps({"event": "udp_error", "reason": str(error)}))


async def serve(host: str, port: int, victoria_metrics_url: str | None, storage_queue_size: int) -> None:
    loop = asyncio.get_running_loop()
    storage = (
        VictoriaMetricsWriter(victoria_metrics_url, queue_size=storage_queue_size)
        if victoria_metrics_url
        else None
    )
    transport, _ = await loop.create_datagram_endpoint(
        lambda: CoapIngestProtocol(storage),
        local_addr=(host, port),
    )
    LOGGER.info(json.dumps({"event": "bound", "host": host, "port": port, "transport": "udp"}))

    stop = asyncio.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)
    try:
        await stop.wait()
    finally:
        transport.close()
        if storage is not None:
            storage.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Open Sail Tracker CoAP ingest")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", default=39001, type=int)
    parser.add_argument("--log-level", default="INFO")
    parser.add_argument("--victoria-metrics-url", default=os.getenv("VICTORIA_METRICS_URL"))
    parser.add_argument(
        "--storage-queue-size",
        default=int(os.getenv("STORAGE_QUEUE_SIZE", "10000")),
        type=int,
    )
    args = parser.parse_args()

    logging.basicConfig(level=args.log_level.upper(), format="%(message)s")
    asyncio.run(serve(args.host, args.port, args.victoria_metrics_url, args.storage_queue_size))


if __name__ == "__main__":
    main()
