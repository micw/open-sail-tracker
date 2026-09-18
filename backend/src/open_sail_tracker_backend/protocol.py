"""Binary telemetry packet decoders for the unencrypted CoAP proof of concept."""

from __future__ import annotations

import struct
from dataclasses import asdict, dataclass

MAGIC = 0x4F53
PROTOCOL_VERSION = 1
PACKET_TYPE_POSITION = 1
PACKET_TYPE_STATUS = 2
UNKNOWN_I8 = -(2**7)
UNKNOWN_I16 = -(2**15)
UNKNOWN_I32 = -(2**31)
UNKNOWN_U16 = 2**16 - 1
KNOWN_POSITION_FLAGS = 0x000F

HEADER = struct.Struct(">HBBIII")
POSITION_BODY = struct.Struct(">Hii")
STATUS_BODY = struct.Struct(">HiiIHHHHHBHBbhhhIHB")


class PacketError(ValueError):
    """Raised when a telemetry payload fails structural or semantic validation."""


@dataclass(frozen=True)
class Header:
    version: int
    packet_type: int
    device_id: int
    boot_id: int
    sequence: int


@dataclass(frozen=True)
class PositionPacket:
    header: Header
    flags: int
    latitude_e7: int
    longitude_e7: int

    def as_log_dict(self) -> dict[str, object]:
        value = asdict(self)
        value["latitude"] = None if self.latitude_e7 == UNKNOWN_I32 else self.latitude_e7 / 10_000_000
        value["longitude"] = None if self.longitude_e7 == UNKNOWN_I32 else self.longitude_e7 / 10_000_000
        return value


@dataclass(frozen=True)
class StatusPacket:
    header: Header
    flags: int
    latitude_e7: int
    longitude_e7: int
    uptime_s: int
    battery_mv: int
    battery_min_mv: int
    fix_age_ms: int
    speed_cms: int
    course_cdeg: int
    satellites: int
    hdop_x100: int
    cell_state: int
    rssi_dbm: int
    rsrp_dbm: int
    rsrq_x10: int
    sinr_x10: int
    health_flags: int
    pending_records: int
    reset_reason: int

    def as_log_dict(self) -> dict[str, object]:
        value = asdict(self)
        value["latitude"] = None if self.latitude_e7 == UNKNOWN_I32 else self.latitude_e7 / 10_000_000
        value["longitude"] = None if self.longitude_e7 == UNKNOWN_I32 else self.longitude_e7 / 10_000_000
        return value


def _decode_header(payload: bytes, expected_type: int, expected_size: int) -> Header:
    if len(payload) != expected_size:
        raise PacketError(f"packet has {len(payload)} bytes, expected {expected_size}")
    magic, version, packet_type, device_id, boot_id, sequence = HEADER.unpack_from(payload)
    if magic != MAGIC:
        raise PacketError("invalid packet magic")
    if version != PROTOCOL_VERSION:
        raise PacketError("unsupported packet version")
    if packet_type != expected_type:
        raise PacketError("packet type does not match resource")
    return Header(version, packet_type, device_id, boot_id, sequence)


def _validate_position(flags: int, latitude_e7: int, longitude_e7: int) -> None:
    if flags & ~KNOWN_POSITION_FLAGS:
        raise PacketError("reserved position flag is set")
    position_known = bool(flags & 0x0001)
    fix_current = bool(flags & 0x0002)
    if fix_current and not position_known:
        raise PacketError("current fix without known position")
    if position_known:
        if not -900_000_000 <= latitude_e7 <= 900_000_000:
            raise PacketError("latitude outside valid range")
        if not -1_800_000_000 <= longitude_e7 <= 1_800_000_000:
            raise PacketError("longitude outside valid range")
    elif latitude_e7 != UNKNOWN_I32 or longitude_e7 != UNKNOWN_I32:
        raise PacketError("unknown position does not use sentinel coordinates")


def decode_position(payload: bytes) -> PositionPacket:
    header = _decode_header(payload, PACKET_TYPE_POSITION, HEADER.size + POSITION_BODY.size)
    flags, latitude_e7, longitude_e7 = POSITION_BODY.unpack_from(payload, HEADER.size)
    _validate_position(flags, latitude_e7, longitude_e7)
    return PositionPacket(header, flags, latitude_e7, longitude_e7)


def decode_status(payload: bytes) -> StatusPacket:
    header = _decode_header(payload, PACKET_TYPE_STATUS, HEADER.size + STATUS_BODY.size)
    fields = STATUS_BODY.unpack_from(payload, HEADER.size)
    _validate_position(fields[0], fields[1], fields[2])
    if fields[8] != UNKNOWN_U16 and fields[8] > 35_999:
        raise PacketError("course outside valid range")
    return StatusPacket(header, *fields)
