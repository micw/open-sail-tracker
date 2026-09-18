"""Asynchronous VictoriaMetrics persistence for decoded telemetry."""

from __future__ import annotations

import json
import logging
import queue
import re
import threading
import time
import urllib.error
import urllib.request
from typing import Any

LOGGER = logging.getLogger("open_sail_tracker_backend")
METRIC_PREFIX = "open_sail_tracker_"
METRIC_NAME = re.compile(r"[^a-zA-Z0-9_:]")
LABEL_FIELDS = {"device_id", "boot_id", "packet_type"}
STATE_FIELDS = {"cell_state", "health", "reset_reason"}


def _escape_label(value: object) -> str:
    return str(value).replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


def _labels(values: dict[str, object]) -> str:
    rendered = ",".join(f'{key}="{_escape_label(value)}"' for key, value in sorted(values.items()))
    return "{" + rendered + "}"


def _metric_name(field: str) -> str:
    return METRIC_PREFIX + METRIC_NAME.sub("_", field)


def encode_telemetry(
    packet: dict[str, Any],
    *,
    coap_message_id: int,
    coap_path: str,
    coap_type: str,
    datagram_size: int,
    source_ip: str,
    source_port: int,
    received_at_ms: int,
) -> str:
    """Encode every decoded telemetry value as VictoriaMetrics import lines."""
    base_labels = {field: packet[field] for field in LABEL_FIELDS}
    base_labels["coap_path"] = coap_path
    base_labels["coap_type"] = coap_type
    base_labels["source_ip"] = source_ip
    labels = _labels(base_labels)
    lines = [
        f"{METRIC_PREFIX}packet_received{labels} 1 {received_at_ms}",
        f"{METRIC_PREFIX}coap_message_id{labels} {coap_message_id} {received_at_ms}",
        f"{METRIC_PREFIX}datagram_size_bytes{labels} {datagram_size} {received_at_ms}",
        f"{METRIC_PREFIX}source_port{labels} {source_port} {received_at_ms}",
    ]

    for field, value in packet.items():
        if field in LABEL_FIELDS or value is None:
            continue
        if field in STATE_FIELDS:
            state_labels = dict(base_labels)
            state_labels[field] = value
            lines.append(f"{_metric_name(field)}_info{_labels(state_labels)} 1 {received_at_ms}")
            continue
        if isinstance(value, bool):
            numeric_value: int | float = int(value)
        elif isinstance(value, (int, float)):
            numeric_value = value
        else:
            continue
        lines.append(f"{_metric_name(field)}{labels} {numeric_value} {received_at_ms}")
    return "\n".join(lines) + "\n"


class VictoriaMetricsWriter:
    """Queue telemetry and write it without blocking the UDP event loop."""

    def __init__(
        self,
        url: str,
        *,
        queue_size: int = 10_000,
        batch_size: int = 100,
        flush_interval_s: float = 1.0,
        request_timeout_s: float = 5.0,
    ) -> None:
        self.url = url
        self.batch_size = batch_size
        self.flush_interval_s = flush_interval_s
        self.request_timeout_s = request_timeout_s
        self.queue: queue.Queue[str] = queue.Queue(maxsize=queue_size)
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self._run, name="victoria-metrics-writer", daemon=True)
        self.thread.start()
        LOGGER.info(json.dumps({"event": "storage_started", "url": self.url}))

    def submit(self, payload: str) -> None:
        try:
            self.queue.put_nowait(payload)
        except queue.Full:
            LOGGER.error(json.dumps({"event": "storage_queue_full", "queued": self.queue.qsize()}))

    def close(self, timeout_s: float = 10.0) -> None:
        self.stop_event.set()
        self.thread.join(timeout_s)
        if self.thread.is_alive():
            LOGGER.error(json.dumps({"event": "storage_shutdown_timeout", "queued": self.queue.qsize()}))

    def _post(self, batch: list[str]) -> None:
        body = "".join(batch).encode("utf-8")
        request = urllib.request.Request(
            self.url,
            data=body,
            headers={"Content-Type": "text/plain; charset=utf-8"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.request_timeout_s) as response:
            if not 200 <= response.status < 300:
                raise RuntimeError(f"VictoriaMetrics returned HTTP {response.status}")

    def _run(self) -> None:
        pending: list[str] = []
        retry_delay_s = 1.0
        while not self.stop_event.is_set() or not self.queue.empty() or pending:
            if not pending:
                try:
                    pending.append(self.queue.get(timeout=self.flush_interval_s))
                except queue.Empty:
                    continue
                deadline = time.monotonic() + self.flush_interval_s
                while len(pending) < self.batch_size:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        break
                    try:
                        pending.append(self.queue.get(timeout=remaining))
                    except queue.Empty:
                        break
            try:
                self._post(pending)
            except (OSError, RuntimeError, urllib.error.URLError) as error:
                LOGGER.warning(
                    json.dumps(
                        {
                            "event": "storage_write_failed",
                            "batch_size": len(pending),
                            "reason": str(error),
                            "retry_in_s": retry_delay_s,
                        },
                        separators=(",", ":"),
                    )
                )
                time.sleep(retry_delay_s)
                retry_delay_s = min(retry_delay_s * 2, 30.0)
                continue

            LOGGER.debug(json.dumps({"event": "storage_write_succeeded", "batch_size": len(pending)}))
            for _ in pending:
                self.queue.task_done()
            pending.clear()
            retry_delay_s = 1.0
