# Project Backlog

Items are listed in priority order.

## 1. Implement encrypted and authenticated backend communication

Replace the current unauthenticated plain-CoAP telemetry path with the version 2 CoAP and AES-256-GCM protocol outlined in [PROTOCOL.md](PROTOCOL.md).

### Scope

- Provision one unique 256-bit key per tracker.
- Implement the persistent boot counter and per-boot sequence number.
- Encode the 16-byte authenticated header and 14-byte live-position payload.
- Encrypt and authenticate messages with AES-256-GCM using mbedTLS.
- Send live positions as CoAP `NON POST` requests.
- Implement backend decryption, authentication, validation, deduplication, and rate limiting.
- Add fixed interoperability test vectors and negative tests for modified headers, ciphertexts, tags, device IDs, and duplicate packets.
- Ensure secrets are never committed to the repository or written to normal application logs.

### Acceptance criteria

- A provisioned tracker can send an encrypted position through LTE to the backend.
- The backend accepts the packet only with the correct device key and GCM tag.
- Position, timestamp, and status flags are not readable on the wire.
- Any change to the authenticated header, ciphertext, or tag causes rejection.
- Duplicate packets do not create duplicate records or refresh the live position.
- Restarting the tracker does not reuse an AES-GCM nonce.
- An unknown or unprovisioned device is rejected.
- Firmware and backend pass the same published binary test vectors.

## 2. Model multi-session events

Replace the current one-time-range-per-event model with an event that contains multiple sessions. A session represents one day or race block with its own time interval and location.

### Scope

- Keep one stable public event slug for a multi-day regatta.
- Add ordered sessions with a date, start time, end time, initial map bounds, publication bounds, and optional course geometry.
- Allow tracker assignments to cover the whole event or selected sessions.
- Refresh track data only while the current session is active.
- Show one combined event in the selector while preserving per-session replay and navigation.
- Prevent overnight, transport, and off-site telemetry from being published between sessions.

### Acceptance criteria

- A Friday-to-Sunday regatta appears as one event with three day sessions.
- Each session can use a different time interval and geographic publication boundary.
- The active session updates without a page reload.
- An inactive or completed session produces no polling traffic beyond explicit user navigation.
- Replay can select each session without exposing telemetry from another session or outside its bounds.
