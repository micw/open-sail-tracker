"""Small RFC 7252 codec for the telemetry ingest resources.

This module intentionally implements only the CoAP subset required by the tracker.
It has no network side effects and is kept independently testable.
"""

from __future__ import annotations

from dataclasses import dataclass

COAP_VERSION = 1
TYPE_CON = 0
TYPE_NON = 1
TYPE_ACK = 2
TYPE_RST = 3
CODE_EMPTY = 0
CODE_POST = 2
CODE_CHANGED = 68  # 2.04
CODE_BAD_REQUEST = 128  # 4.00
CODE_NOT_FOUND = 132  # 4.04
CODE_METHOD_NOT_ALLOWED = 133  # 4.05
CODE_UNSUPPORTED_CONTENT_FORMAT = 143  # 4.15
OPTION_URI_PATH = 11
OPTION_CONTENT_FORMAT = 12
CONTENT_FORMAT_OCTET_STREAM = 42
MAX_DATAGRAM_SIZE = 1024


class CoapError(ValueError):
    """Raised when an incoming CoAP datagram is malformed."""


@dataclass(frozen=True)
class CoapMessage:
    message_type: int
    code: int
    message_id: int
    token: bytes
    options: tuple[tuple[int, bytes], ...]
    payload: bytes

    @property
    def uri_path(self) -> str:
        segments = [value.decode("utf-8") for number, value in self.options if number == OPTION_URI_PATH]
        return "/" + "/".join(segments)

    @property
    def content_format(self) -> int | None:
        values = [value for number, value in self.options if number == OPTION_CONTENT_FORMAT]
        if not values:
            return None
        if len(values) != 1 or len(values[0]) > 2:
            raise CoapError("invalid Content-Format option")
        return int.from_bytes(values[0], "big")


def _read_extended(nibble: int, data: bytes, offset: int) -> tuple[int, int]:
    if nibble < 13:
        return nibble, offset
    if nibble == 13:
        if offset >= len(data):
            raise CoapError("truncated extended option")
        return 13 + data[offset], offset + 1
    if nibble == 14:
        if offset + 2 > len(data):
            raise CoapError("truncated extended option")
        return 269 + int.from_bytes(data[offset : offset + 2], "big"), offset + 2
    raise CoapError("reserved option encoding")


def decode_message(data: bytes) -> CoapMessage:
    if len(data) < 4:
        raise CoapError("datagram shorter than CoAP header")
    if len(data) > MAX_DATAGRAM_SIZE:
        raise CoapError("datagram exceeds size limit")

    version = data[0] >> 6
    message_type = (data[0] >> 4) & 0x03
    token_length = data[0] & 0x0F
    if version != COAP_VERSION:
        raise CoapError("unsupported CoAP version")
    if token_length > 8:
        raise CoapError("invalid token length")
    if len(data) < 4 + token_length:
        raise CoapError("truncated token")

    code = data[1]
    message_id = int.from_bytes(data[2:4], "big")
    token = data[4 : 4 + token_length]
    offset = 4 + token_length
    option_number = 0
    options: list[tuple[int, bytes]] = []
    payload = b""

    while offset < len(data):
        if data[offset] == 0xFF:
            offset += 1
            if offset == len(data):
                raise CoapError("empty payload after marker")
            payload = data[offset:]
            break

        option_header = data[offset]
        offset += 1
        delta, offset = _read_extended(option_header >> 4, data, offset)
        length, offset = _read_extended(option_header & 0x0F, data, offset)
        option_number += delta
        if offset + length > len(data):
            raise CoapError("truncated option value")
        options.append((option_number, data[offset : offset + length]))
        offset += length

    return CoapMessage(message_type, code, message_id, token, tuple(options), payload)


def encode_response(request: CoapMessage, code: int) -> bytes:
    """Create a piggybacked ACK response for a confirmable request."""
    if request.message_type != TYPE_CON:
        raise CoapError("ACK response requires a confirmable request")
    first = (COAP_VERSION << 6) | (TYPE_ACK << 4) | len(request.token)
    return bytes((first, code)) + request.message_id.to_bytes(2, "big") + request.token
