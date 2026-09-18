# Open Sail Tracker backend

The backend currently provides a minimal, unauthenticated CoAP-over-UDP ingest for the transport proof of concept. It decodes and logs position and status packets. It does not store data and must not be treated as a production service.

## Resources

| Method | CoAP type | Resource | Payload |
|---|---|---|---|
| `POST` | `NON` | `/v1/position` | 26-byte version 1 position packet |
| `POST` | `CON` | `/v1/status` | 58-byte version 1 status packet |

Both resources use CoAP Content-Format `application/octet-stream` (`42`). A valid confirmable status request receives a piggybacked `2.04 Changed` response. The non-confirmable position resource does not generate a response.

All accepted packets and rejected requests are written as one-line JSON records to standard output.

## Run locally

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e backend
open-sail-tracker-backend --port 39001
```

Run tests from the repository root:

```bash
PYTHONPATH=backend/src python -m unittest discover -s backend/tests -v
```

## Container

```bash
docker build -t open-sail-tracker-backend:local backend
docker run --rm -p 39001:39001/udp open-sail-tracker-backend:local
```

The process is stateless and requires no writable container filesystem.

## Security limitation

This stage deliberately has no encryption and no sender authentication. Anyone who can reach the UDP port can read, replay, or forge telemetry. Do not send names, SIM identifiers, credentials, or operationally sensitive positions. Authenticated encryption remains the first project backlog item.
