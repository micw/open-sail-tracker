"""Binary telemetry packet decoders for the unencrypted CoAP proof of concept."""

from __future__ import annotations

import struct
from dataclasses import dataclass

MAGIC = 0x4F53
PROTOCOL_VERSION = 1
PACKET_TYPE_POSITION = 1
PACKET_TYPE_STATUS = 2
UNKNOWN_I8 = -(2**7)
UNKNOWN_I16 = -(2**15)
UNKNOWN_I32 = -(2**31)
UNKNOWN_U16 = 2**16 - 1
KNOWN_POSITION_FLAGS = 0x000F

PACKET_TYPE_NAMES = {
    PACKET_TYPE_POSITION: "position",
    PACKET_TYPE_STATUS: "status",
}
CELL_STATE_NAMES = {
    0: "off",
    1: "searching",
    2: "registered",
    3: "data",
    4: "error",
}
RESET_REASON_NAMES = {
    0: "unknown",
    1: "power_on",
    2: "external",
    3: "software",
    4: "panic",
    5: "interrupt_watchdog",
    6: "task_watchdog",
    7: "watchdog",
    8: "deep_sleep",
    9: "brownout",
    10: "sdio",
}

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

    def as_log_dict(self) -> dict[str, object]:
        return {
            "protocol_version": self.version,
            "packet_type": PACKET_TYPE_NAMES[self.packet_type],
            "device_id": f"{self.device_id:08x}",
            "boot_id": f"{self.boot_id:08x}",
            "sequence": self.sequence,
        }


def _position_log_fields(flags: int, latitude_e7: int, longitude_e7: int) -> dict[str, object]:
    position_known = bool(flags & 0x0001)
    return {
        "position_known": position_known,
        "fix_current": bool(flags & 0x0002),
        "gnss_on": bool(flags & 0x0004),
        "gnss_error": bool(flags & 0x0008),
        "latitude": latitude_e7 / 10_000_000 if position_known else None,
        "longitude": longitude_e7 / 10_000_000 if position_known else None,
    }


def _optional_unsigned(value: int) -> int | None:
    return None if value == UNKNOWN_U16 else value


def _optional_signed(value: int, sentinel: int) -> int | None:
    return None if value == sentinel else value


@dataclass(frozen=True)
class PositionPacket:
    header: Header
    flags: int
    latitude_e7: int
    longitude_e7: int

    def as_log_dict(self) -> dict[str, object]:
        return {
            **self.header.as_log_dict(),
            **_position_log_fields(self.flags, self.latitude_e7, self.longitude_e7),
        }


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
        speed_cms = _optional_unsigned(self.speed_cms)
        course_cdeg = _optional_unsigned(self.course_cdeg)
        hdop_x100 = _optional_unsigned(self.hdop_x100)
        rsrq_x10 = _optional_signed(self.rsrq_x10, UNKNOWN_I16)
        sinr_x10 = _optional_signed(self.sinr_x10, UNKNOWN_I16)
        return {
            **self.header.as_log_dict(),
            **_position_log_fields(self.flags, self.latitude_e7, self.longitude_e7),
            "uptime_s": self.uptime_s,
            "battery_mv": _optional_unsigned(self.battery_mv),
            "battery_min_mv": _optional_unsigned(self.battery_min_mv),
            "fix_age_ms": _optional_unsigned(self.fix_age_ms),
            "speed_mps": speed_cms / 100 if speed_cms is not None else None,
            "course_deg": course_cdeg / 100 if course_cdeg is not None else None,
            "satellites": None if self.satellites == 0xFF else self.satellites,
            "hdop": hdop_x100 / 100 if hdop_x100 is not None else None,
            "cell_state": CELL_STATE_NAMES.get(self.cell_state, "unknown"),
            "rssi_dbm": _optional_signed(self.rssi_dbm, UNKNOWN_I8),
            "rsrp_dbm": _optional_signed(self.rsrp_dbm, UNKNOWN_I16),
            "rsrq_db": rsrq_x10 / 10 if rsrq_x10 is not None else None,
            "sinr_db": sinr_x10 / 10 if sinr_x10 is not None else None,
            "health": "ok" if self.health_flags == 0 else f"flags_0x{self.health_flags:08x}",
            "pending_records": self.pending_records,
            "reset_reason": RESET_REASON_NAMES.get(self.reset_reason, "unknown"),
        }


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
