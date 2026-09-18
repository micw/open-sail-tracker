# Plain CoAP proof of concept

Status: implemented and verified on 2026-09-18

The H802 tracker sends the version 1 binary position and status payloads through CoAP over UDP. The authoritative field definitions are in [PROTOCOL.md](../PROTOCOL.md).

## Verified path

```text
H802 firmware
  -> SIM7670G UDP socket
  -> Telefónica Germany LTE
  -> public UDP/39001
  -> Python CoAP listener on vpsprod2.wyraz.de
  -> structured journal log
```

The observed mobile source address during the verification was carrier-managed and must not be used as device identity.

## Cadence

- `NON POST /v1/position` every five seconds
- `CON POST /v1/status` immediately after startup and every 60 seconds

The backend returned a piggybacked `2.04 Changed` ACK for the confirmable status request. The test showed repeated positions at five-second intervals and two status messages exactly 60 seconds apart.

GNSS was enabled but had no indoor fix. Both packet types correctly used `POSITION_KNOWN=0`, `GNSS_ON=1`, and `INT32_MIN` coordinate sentinels.

## Security limitation

This stage has no encryption, authentication, replay protection, or access control at the application layer. It must not carry personal data, SIM identifiers, credentials, or sensitive operational positions. Authenticated encryption is the next protocol milestone.
