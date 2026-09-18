from __future__ import annotations

import struct
import unittest

from open_sail_tracker_backend.coap import (
    CODE_BAD_REQUEST,
    CODE_CHANGED,
    CONTENT_FORMAT_OCTET_STREAM,
    CoapError,
    decode_message,
    encode_response,
)
from open_sail_tracker_backend.protocol import HEADER, UNKNOWN_I32
from open_sail_tracker_backend.server import evaluate_request


def position_request(*, confirmable: bool = False, message_id: int = 0x1234) -> bytes:
    message_type = 0 if confirmable else 1
    first = (1 << 6) | (message_type << 4)
    payload = HEADER.pack(0x4F53, 1, 1, 0x4C939764, 0x12345678, 3)
    payload += struct.pack(">Hii", 0x0004, UNKNOWN_I32, UNKNOWN_I32)
    options = bytes((0xB2,)) + b"v1" + bytes((0x08,)) + b"position"
    options += bytes((0x11, CONTENT_FORMAT_OCTET_STREAM))
    return bytes((first, 2)) + message_id.to_bytes(2, "big") + options + b"\xff" + payload


class CoapCodecTests(unittest.TestCase):
    def test_decodes_position_request(self) -> None:
        message = decode_message(position_request())
        self.assertEqual(message.uri_path, "/v1/position")
        self.assertEqual(message.content_format, CONTENT_FORMAT_OCTET_STREAM)
        code, packet = evaluate_request(message)
        self.assertEqual(code, CODE_CHANGED)
        self.assertIsNotNone(packet)

    def test_encodes_piggybacked_ack(self) -> None:
        message = decode_message(position_request(confirmable=True))
        self.assertEqual(encode_response(message, CODE_CHANGED), b"\x60\x44\x124")

    def test_rejects_truncated_option(self) -> None:
        with self.assertRaises(CoapError):
            decode_message(b"\x50\x02\x00\x01\xbd")

    def test_rejects_invalid_payload(self) -> None:
        raw = position_request()[:-1]
        code, packet = evaluate_request(decode_message(raw))
        self.assertEqual(code, CODE_BAD_REQUEST)
        self.assertIsNone(packet)


if __name__ == "__main__":
    unittest.main()
