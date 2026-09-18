from __future__ import annotations

import struct
import unittest

from open_sail_tracker_backend.protocol import (
    HEADER,
    STATUS_BODY,
    UNKNOWN_I16,
    UNKNOWN_I32,
    UNKNOWN_I8,
    UNKNOWN_U16,
    PacketError,
    decode_position,
    decode_status,
)


def header(packet_type: int, sequence: int = 7) -> bytes:
    return HEADER.pack(0x4F53, 1, packet_type, 0x4C939764, 0x12345678, sequence)


class PositionDecoderTests(unittest.TestCase):
    def test_decodes_known_position(self) -> None:
        packet = decode_position(header(1) + struct.pack(">Hii", 0x0007, 53_550_0000, 10_000_0000))
        self.assertEqual(packet.header.sequence, 7)
        self.assertEqual(packet.latitude_e7, 53_550_0000)
        self.assertEqual(packet.as_log_dict()["longitude"], 10.0)

    def test_accepts_unknown_position_sentinels(self) -> None:
        packet = decode_position(header(1) + struct.pack(">Hii", 0x0004, UNKNOWN_I32, UNKNOWN_I32))
        self.assertIsNone(packet.as_log_dict()["latitude"])

    def test_rejects_current_without_known_position(self) -> None:
        with self.assertRaises(PacketError):
            decode_position(header(1) + struct.pack(">Hii", 0x0002, UNKNOWN_I32, UNKNOWN_I32))

    def test_rejects_packet_type_mismatch(self) -> None:
        with self.assertRaises(PacketError):
            decode_position(header(2) + struct.pack(">Hii", 0, UNKNOWN_I32, UNKNOWN_I32))


class StatusDecoderTests(unittest.TestCase):
    def test_decodes_status_packet(self) -> None:
        body = STATUS_BODY.pack(
            0x0004,
            UNKNOWN_I32,
            UNKNOWN_I32,
            123,
            UNKNOWN_U16,
            UNKNOWN_U16,
            UNKNOWN_U16,
            UNKNOWN_U16,
            UNKNOWN_U16,
            0,
            UNKNOWN_U16,
            3,
            UNKNOWN_I8,
            UNKNOWN_I16,
            UNKNOWN_I16,
            UNKNOWN_I16,
            0,
            0,
            1,
        )
        packet = decode_status(header(2, 12) + body)
        self.assertEqual(packet.header.sequence, 12)
        self.assertEqual(packet.uptime_s, 123)
        self.assertEqual(packet.cell_state, 3)


if __name__ == "__main__":
    unittest.main()
