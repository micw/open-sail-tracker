# Open Sail Tracker protocol

Status: authoritative proof-of-concept specification  
Last updated: 2026-09-18

This document defines the current unencrypted CoAP transport and the intended security upgrade. All multi-byte integers use network byte order (big endian). Encoders and decoders must process individual fields and must not transmit native C/C++ structs.

## Protocol stages

### Packet version 1: plain CoAP proof of concept

The currently deployed proof of concept wraps fixed version 1 binary packets in CoAP over UDP. It provides no confidentiality or sender authentication. It exists only to verify the modem, LTE network, CoAP framing, packet cadence, backend decoder, and operational deployment.

The earlier raw-UDP transport used the same 26-byte position payload without a CoAP envelope. It is obsolete after the successful CoAP test.

### Packet version 2: authenticated encryption

The next protocol version will encrypt payload fields and authenticate the visible header with AES-256-GCM. Each tracker receives one independent 256-bit key. The nonce consists of a direction value, a persistent boot counter, and a per-boot sequence number. Version 2 remains the first project backlog item and is required before production use.

## UDP endpoint

The proof-of-concept backend listens on UDP port `39001`. The Kubernetes test deployment is `sailtracker.wyraz.de:39001`. The tracker resolves the hostname after establishing its packet-data service, caches the returned IPv4 address, and resolves it again after socket or send failures.

## CoAP resources

| Method | Type | Resource | Content-Format | Success response |
|---|---|---|---:|---|
| `POST` | `NON` | `/v1/position` | `42` (`application/octet-stream`) | none |
| `POST` | `CON` | `/v1/status` | `42` (`application/octet-stream`) | piggybacked `2.04 Changed` |

The tracker sends a position every five seconds and a status packet every 60 seconds. Position loss does not delay later positions. Position and status packets share one packet sequence space.

The firmware currently does not retransmit an unacknowledged confirmable status packet. Full CoAP retransmission behavior is deferred until after the transport proof of concept.

## Common packet header

Every binary payload starts with this 16-byte header:

| Offset | Size | Type | Field | Value or meaning |
|---:|---:|---|---|---|
| 0 | 2 | `u16` | `magic` | `0x4f53`, ASCII `OS` |
| 2 | 1 | `u8` | `version` | `1` |
| 3 | 1 | `u8` | `packet_type` | `1` for position, `2` for status |
| 4 | 4 | `u32` | `device_id` | tracker identifier |
| 8 | 4 | `u32` | `boot_id` | random value generated at boot |
| 12 | 4 | `u32` | `sequence` | incremented for every packet |

`device_id` is not authentication. IMEI, IMSI, ICCID, names, and credentials must not be transmitted in telemetry.

## Position flags

| Bit | Name | Meaning |
|---:|---|---|
| 0 | `POSITION_KNOWN` | coordinates contain a previously valid fix |
| 1 | `FIX_CURRENT` | fix age does not exceed ten seconds |
| 2 | `GNSS_ON` | GNSS is enabled |
| 3 | `GNSS_ERROR` | GNSS or its data path reports an error |
| 4–15 | reserved | sender sets these bits to zero |

`FIX_CURRENT` without `POSITION_KNOWN` is invalid. If no position is known, both coordinates are `INT32_MIN`. Zero is a valid coordinate and is not a sentinel.

## Position packet

Packet type: `1`  
Binary payload size: 26 bytes  
Cadence: five seconds

| Offset | Size | Type | Field |
|---:|---:|---|---|
| 0 | 16 | header | common header |
| 16 | 2 | `u16` | position flags |
| 18 | 4 | `i32` | latitude × 10⁷ or `INT32_MIN` |
| 22 | 4 | `i32` | longitude × 10⁷ or `INT32_MIN` |

## Status packet

Packet type: `2`  
Binary payload size: 58 bytes  
Cadence: 60 seconds, with an additional packet immediately after boot

| Offset | Size | Type | Field | Unit or sentinel |
|---:|---:|---|---|---|
| 0 | 16 | header | common header | — |
| 16 | 2 | `u16` | position flags | — |
| 18 | 4 | `i32` | latitude | × 10⁷ or `INT32_MIN` |
| 22 | 4 | `i32` | longitude | × 10⁷ or `INT32_MIN` |
| 26 | 4 | `u32` | uptime | seconds |
| 30 | 2 | `u16` | battery voltage | mV or `UINT16_MAX` |
| 32 | 2 | `u16` | minimum battery voltage | mV or `UINT16_MAX` |
| 34 | 2 | `u16` | fix age | ms or `UINT16_MAX` |
| 36 | 2 | `u16` | speed over ground | cm/s or `UINT16_MAX` |
| 38 | 2 | `u16` | course over ground | 0.01° or `UINT16_MAX` |
| 40 | 1 | `u8` | satellites used | count or `UINT8_MAX` |
| 41 | 2 | `u16` | HDOP | × 100 or `UINT16_MAX` |
| 43 | 1 | `u8` | cellular state | enum below |
| 44 | 1 | `i8` | RSSI | dBm or `INT8_MIN` |
| 45 | 2 | `i16` | RSRP | dBm or `INT16_MIN` |
| 47 | 2 | `i16` | RSRQ | 0.1 dB or `INT16_MIN` |
| 49 | 2 | `i16` | SINR | 0.1 dB or `INT16_MIN` |
| 51 | 4 | `u32` | health flags | bit field |
| 55 | 2 | `u16` | pending records | count |
| 57 | 1 | `u8` | reset reason | ESP32 reset reason |

Cellular state values are `0` off, `1` searching, `2` registered, `3` data service available, and `4` error.

The current firmware populates position, uptime, battery voltage, minimum sampled battery voltage, cellular state, pending-record count, and reset reason. Battery voltage comes primarily from the averaged ESP32 GPIO8 ADC measurement; SIM7670G `AT+CBC` is used only as a fallback. Measurements that are not implemented yet use their defined sentinels.

## Backend validation

The backend accepts at most 1024 bytes per UDP datagram and validates:

1. CoAP version, token length, and option encoding.
2. request type, `POST` method, URI path, and Content-Format.
3. exact binary payload length.
4. magic, packet version, and resource-specific packet type.
5. reserved flag bits and flag combinations.
6. coordinate and course ranges.
7. required sentinels for unknown positions.

Accepted packets and rejected requests are logged as structured one-line JSON. The proof-of-concept backend does not store data or deduplicate packets.

## Security boundary

Plain CoAP exposes the complete packet and permits spoofing, modification, and replay. The public test listener must never receive personal data, SIM identifiers, credentials, or operationally sensitive positions. Packet validation prevents malformed data from being interpreted as valid telemetry, but it does not identify the sender.

Before production use, version 2 must add:

- one unique 32-byte AES key per tracker;
- AES-256-GCM encryption and authentication;
- a persistent boot counter;
- direction-separated nonces;
- backend authentication before payload processing;
- duplicate suppression using `(device_id, boot_counter, sequence)`;
- fixed interoperability and negative test vectors.
