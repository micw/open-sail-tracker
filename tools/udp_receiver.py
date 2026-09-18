#!/usr/bin/env python3
"""Legacy raw-UDP receiver for the Open Sail Tracker transport PoC."""

from __future__ import annotations

import argparse
import datetime
import socket
import struct

POSITION_PACKET = struct.Struct(">HBBIIIHii")
MAGIC = 0x4F53
UNKNOWN_COORDINATE = -(2**31)


def decode(data: bytes) -> str:
    if len(data) != POSITION_PACKET.size:
        return f"raw hex={data.hex()}"

    magic, version, packet_type, device_id, boot_id, seq, flags, lat_e7, lon_e7 = (
        POSITION_PACKET.unpack(data)
    )
    if magic != MAGIC:
        return f"raw hex={data.hex()}"

    known = bool(flags & 0x0001)
    current = bool(flags & 0x0002)
    gnss_on = bool(flags & 0x0004)
    gnss_error = bool(flags & 0x0008)
    if known:
        position = f"{lat_e7 / 1e7:.7f},{lon_e7 / 1e7:.7f}"
    elif lat_e7 == UNKNOWN_COORDINATE and lon_e7 == UNKNOWN_COORDINATE:
        position = "unknown"
    else:
        position = "invalid-sentinel"

    return (
        f"OST v={version} type={packet_type} device={device_id:08x} "
        f"boot={boot_id:08x} seq={seq} flags=0x{flags:04x} "
        f"known={known} current={current} gnss_on={gnss_on} "
        f"gnss_error={gnss_error} position={position}"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=39001)
    parser.add_argument("--log")
    args = parser.parse_args()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((args.host, args.port))
    log = open(args.log, "a", buffering=1) if args.log else None
    print(f"listening on {args.host}:{args.port}/udp", flush=True)

    try:
        while True:
            data, address = sock.recvfrom(4096)
            now = datetime.datetime.now(datetime.timezone.utc).isoformat()
            line = (
                f"{now} src={address[0]}:{address[1]} len={len(data)} "
                f"{decode(data)}"
            )
            print(line, flush=True)
            if log:
                log.write(line + "\n")
    finally:
        if log:
            log.close()
        sock.close()


if __name__ == "__main__":
    main()
