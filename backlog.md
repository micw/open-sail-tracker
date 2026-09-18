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
