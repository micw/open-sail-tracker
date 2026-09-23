# Open Sail Tracker backend

The backend provides an unauthenticated CoAP-over-UDP ingest and a separate HTTP race API for the transport proof of concept. The ingest decodes and logs position and status packets and can persist every decoded value to VictoriaMetrics. It must not be treated as a production service yet.

## Resources

| Method | CoAP type | Resource | Payload |
|---|---|---|---|
| `POST` | `NON` | `/v1/position` | 26-byte version 1 position packet |
| `POST` | `CON` | `/v1/status` | 58-byte version 1 status packet |

Both resources use CoAP Content-Format `application/octet-stream` (`42`). A valid confirmable status request receives a piggybacked `2.04 Changed` response. The non-confirmable position resource does not generate a response.

All accepted packets and rejected requests are written as one-line JSON records to standard output. The accepted-packet log contains decoded values only: position flags become named booleans, fixed-point coordinates become decimal degrees, enum values become names, and sentinel values become JSON `null`. Raw wire-format fields such as numeric flags and `latitude_e7` are not included.

## VictoriaMetrics storage

Set `VICTORIA_METRICS_URL` to enable persistence:

```bash
export VICTORIA_METRICS_URL=http://open-sail-tracker-vm:8428/api/v1/import/prometheus
export STORAGE_QUEUE_SIZE=10000
open-sail-tracker-backend --port 39001
```

The backend uses the VictoriaMetrics Prometheus text import API instead of Prometheus remote write. Remote write requires protobuf encoding and Snappy compression; the import API accepts the same metric model over a dependency-free HTTP request and is directly supported by VictoriaMetrics.

The UDP event loop never waits for HTTP. Decoded packets enter a bounded in-memory queue and a worker thread sends batches of up to 100 packets. Failed requests are retried with exponential backoff. The default queue can hold approximately 14 hours of five-second position packets from one tracker.

Metrics use the prefix `open_sail_tracker_`. The labels common to a packet are:

- `device_id`
- `boot_id`
- `packet_type`
- `coap_path`
- `coap_type`
- `source_ip`

Available numeric and boolean fields become individual time series. State fields such as cellular state, health, and reset reason become labels on `_info` metrics. JSON `null` values are omitted. Server receipt time is used as the sample timestamp because protocol version 1 has no device timestamp.

Examples:

```text
open_sail_tracker_latitude{device_id="4c939764",...} 51.335525 1789763000000
open_sail_tracker_longitude{device_id="4c939764",...} 12.2393267 1789763000000
open_sail_tracker_battery_mv{device_id="4c939764",...} 3778 1789763000000
open_sail_tracker_cell_state_info{device_id="4c939764",cell_state="data",...} 1 1789763000000
```

The queue is not a durable local write-ahead log. A backend restart while VictoriaMetrics is unavailable can lose queued data. Durable offline buffering belongs in a later backend and tracker milestone.

## HTTP event API

Run the HTTP component separately from the CoAP ingest:

```bash
export VICTORIA_METRICS_QUERY_URL=http://open-sail-tracker-vm:8428/api/v1/export
open-sail-tracker-api --port 8080
```

The initial API has three unauthenticated resources:

| Method | Resource | Description |
|---|---|---|
| `GET` | `/api/v1/events` | Available public event summaries and slugs |
| `GET` | `/api/v1/events/{slug}` | Event geometry, entries, boats, and public tracker numbers |
| `GET` | `/api/v1/events/{slug}/tracks?from={timestamp}&to={timestamp}` | Position and motion samples for assigned entries |
| `GET` | `/api/v1/live` | Public live-view metadata and geographic boundary |
| `GET` | `/api/v1/live/tracks` | Geofenced tracks from the most recent four hours |

`EventRepository` abstracts event metadata; its current implementation is a static list of proof-of-concept events. `TelemetryRepository` abstracts raw track data; the online implementation reads VictoriaMetrics. Internal telemetry device IDs remain in the event repository and are not exposed by the API.

The static proof-of-concept repository currently also defines three Pilsensee test events for 25–27 September 2026, each from 08:00 to 18:00 Europe/Berlin. Tracker `4c939764` is assigned internally to public tracker number `01`. The publication rectangle is limited to the provided Pilsensee bounds. These are deliberately three technical events until the multi-session event model in the backlog is implemented.

Both query timestamps must be ISO 8601 values with a time zone. The service intersects every query with the event interval and the tracker-assignment interval before calling the telemetry repository. The guest visibility policy then removes coordinates outside the event's publication bounds and splits the track so hidden excursions cannot be connected by a rendered line. A query wholly outside the event interval returns an empty track list. Positions for which the tracker reported `fix_current=false` are omitted rather than presenting stale coordinates as movement.

The live resources are deliberately unauthenticated at this stage. They use the same public geographic boundary and never return coordinates outside it. A future authenticated admin live resource may use a different visibility policy.

## Run locally

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e backend
open-sail-tracker-backend --port 39001
# In a second terminal:
open-sail-tracker-api --port 8080
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

The image also contains the `open-sail-tracker-api` command used by the separate API deployment. Both processes require no writable container filesystem. The ingest retry queue exists only in memory.

## Security limitation

This stage deliberately has no encryption and no sender authentication. Anyone who can reach the UDP port can read, replay, or forge telemetry. Do not send names, SIM identifiers, credentials, or operationally sensitive positions. Authenticated encryption remains the first project backlog item.
