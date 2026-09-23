"""Unauthenticated HTTP API for public events and bounded tracker replay data."""

from __future__ import annotations

import argparse
import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Protocol

LOGGER = logging.getLogger("open_sail_tracker_backend.web_api")
KNOTS_PER_MPS = 1.9438444924406
LIVE_WINDOW_MS = 4 * 60 * 60 * 1000


@dataclass(frozen=True)
class Boat:
    id: str
    sail_number: str
    name: str


@dataclass(frozen=True)
class TrackerAssignment:
    tracker_number: str
    telemetry_device_id: str
    valid_from: str | None = None
    valid_to: str | None = None


@dataclass(frozen=True)
class EventEntry:
    id: str
    boat: Boat
    color: str
    tracker_assignments: tuple[TrackerAssignment, ...]


@dataclass(frozen=True)
class Event:
    slug: str
    name: str
    start_time: str
    end_time: str
    initial_bounds: list[list[float]]
    publication_bounds: list[list[float]]
    entries: tuple[EventEntry, ...]
    public: bool = True

    @property
    def start_ms(self) -> int:
        return parse_datetime(self.start_time)

    @property
    def end_ms(self) -> int:
        return parse_datetime(self.end_time)

    def summary_dict(self) -> dict[str, Any]:
        return {
            "slug": self.slug,
            "name": self.name,
            "startTime": self.start_time,
            "endTime": self.end_time,
        }

    def public_dict(self) -> dict[str, Any]:
        return {
            "event": {
                **self.summary_dict(),
                "initialBounds": self.initial_bounds,
                "publicationBounds": self.publication_bounds,
                "course": {"type": "FeatureCollection", "features": []},
            },
            "entries": [
                {
                    "id": entry.id,
                    "trackerNumbers": [
                        assignment.tracker_number
                        for assignment in entry.tracker_assignments
                    ],
                    "color": entry.color,
                    "boat": {
                        "id": entry.boat.id,
                        "sailNumber": entry.boat.sail_number,
                        "name": entry.boat.name,
                    },
                }
                for entry in self.entries
            ],
        }


class EventRepository(Protocol):
    """Source of event metadata and time-bounded tracker assignments."""

    def list_public_events(self) -> list[Event]: ...

    def get_public_event(self, slug: str) -> Event | None: ...


class TelemetryRepository(Protocol):
    """Source of raw tracks for trackers assigned to an event."""

    def get_tracks(self, event: Event, start_ms: int, end_ms: int) -> list[dict[str, Any]]: ...


class TrackVisibilityPolicy(Protocol):
    """Remove telemetry that the current audience must not receive."""

    def publish_tracks(self, event: Event, tracks: list[dict[str, Any]]) -> list[dict[str, Any]]: ...


class StaticEventRepository:
    def __init__(self, events: tuple[Event, ...]) -> None:
        self.events = events
        self.by_slug = {event.slug: event for event in events}
        if len(self.by_slug) != len(events):
            raise ValueError("event slugs must be unique")

    def list_public_events(self) -> list[Event]:
        return [event for event in self.events if event.public]

    def get_public_event(self, slug: str) -> Event | None:
        event = self.by_slug.get(slug)
        return event if event is not None and event.public else None


TEST_EVENT = Event(
    slug="training-2026-09-19",
    name="Training vom 19. September",
    start_time="2026-09-19T10:50:00+02:00",
    end_time="2026-09-19T12:45:00+02:00",
    initial_bounds=[[12.2367, 51.3047], [12.2514, 51.3168]],
    publication_bounds=[
        [12.236718465054931, 51.296003387362596],
        [12.258043783104087, 51.31842232597056],
    ],
    entries=(
        EventEntry(
            id="test-entry",
            boat=Boat(id="test-boat", sail_number="TEST", name="Testskiff"),
            color="#ef476f",
            tracker_assignments=(
                TrackerAssignment(
                    tracker_number="01",
                    telemetry_device_id="4c939764",
                ),
            ),
        ),
    ),
)

PILSENSEE_BOUNDS = [
    [11.172458803865464, 48.0127936438613],
    [11.203311981805054, 48.0376395211887],
]


def pilsensee_event(day: str, weekday: str) -> Event:
    return Event(
        slug=f"pilsensee-2026-09-{day}",
        name=f"Regatta am Pilsensee – {weekday}",
        start_time=f"2026-09-{day}T08:00:00+02:00",
        end_time=f"2026-09-{day}T18:00:00+02:00",
        initial_bounds=PILSENSEE_BOUNDS,
        publication_bounds=PILSENSEE_BOUNDS,
        entries=(
            EventEntry(
                id=f"pilsensee-{day}-tracker-01",
                boat=Boat(id="pilsensee-testboot", sail_number="01", name="Testboot"),
                color="#ef476f",
                tracker_assignments=(
                    TrackerAssignment(
                        tracker_number="01",
                        telemetry_device_id="4c939764",
                    ),
                ),
            ),
        ),
    )


PILSENSEE_EVENTS = (
    pilsensee_event("25", "Freitag"),
    pilsensee_event("26", "Samstag"),
    pilsensee_event("27", "Sonntag"),
)
EVENT_REPOSITORY = StaticEventRepository((*PILSENSEE_EVENTS, TEST_EVENT))


def parse_datetime(value: str) -> int:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("timestamp must be ISO 8601") from error
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include a time zone")
    return int(parsed.timestamp() * 1000)


def bounded_query_range(parameters: dict[str, list[str]], event: Event) -> tuple[int, int] | None:
    """Validate and clamp a requested interval to the event's hard boundaries."""
    if len(parameters.get("from", [])) != 1 or len(parameters.get("to", [])) != 1:
        raise ValueError("from and to must each be supplied once")
    requested_start = parse_datetime(parameters["from"][0])
    requested_end = parse_datetime(parameters["to"][0])
    if requested_start > requested_end:
        raise ValueError("from must not be later than to")
    start_ms = max(requested_start, event.start_ms)
    end_ms = min(requested_end, event.end_ms)
    return None if start_ms > end_ms else (start_ms, end_ms)


def assignment_range(
    assignment: TrackerAssignment,
    start_ms: int,
    end_ms: int,
) -> tuple[int, int] | None:
    assigned_start = parse_datetime(assignment.valid_from) if assignment.valid_from else start_ms
    assigned_end = parse_datetime(assignment.valid_to) if assignment.valid_to else end_ms
    effective_start = max(start_ms, assigned_start)
    effective_end = min(end_ms, assigned_end)
    return None if effective_start > effective_end else (effective_start, effective_end)


class VictoriaMetricsTelemetryRepository:
    """Read exact telemetry samples through the VictoriaMetrics export API."""

    def __init__(self, url: str, *, timeout_s: float = 10.0) -> None:
        self.url = url
        self.timeout_s = timeout_s

    def _metric(
        self,
        name: str,
        packet_type: str,
        device_id: str,
        start_ms: int,
        end_ms: int,
    ) -> dict[int, float]:
        selector = (
            f'open_sail_tracker_{name}{{device_id="{device_id}",'
            f'packet_type="{packet_type}"}}'
        )
        parameters = urllib.parse.urlencode(
            {
                "match[]": selector,
                "start": datetime.fromtimestamp(start_ms / 1000, timezone.utc).isoformat(),
                "end": datetime.fromtimestamp(end_ms / 1000, timezone.utc).isoformat(),
            }
        )
        request = urllib.request.Request(f"{self.url}?{parameters}", method="GET")
        samples: dict[int, float] = {}
        with urllib.request.urlopen(request, timeout=self.timeout_s) as response:
            if not 200 <= response.status < 300:
                raise RuntimeError(f"VictoriaMetrics returned HTTP {response.status}")
            for raw_line in response:
                if not raw_line.strip():
                    continue
                row = json.loads(raw_line)
                if not isinstance(row, dict):
                    raise RuntimeError("VictoriaMetrics returned an invalid export row")
                timestamps = row.get("timestamps")
                values = row.get("values")
                if (
                    not isinstance(timestamps, list)
                    or not isinstance(values, list)
                    or len(timestamps) != len(values)
                ):
                    raise RuntimeError("VictoriaMetrics returned an invalid export row")
                for timestamp, value in zip(timestamps, values):
                    timestamp_ms = int(timestamp)
                    if start_ms <= timestamp_ms <= end_ms:
                        samples[timestamp_ms] = float(value)
        return samples

    def _assignment_track(
        self,
        assignment: TrackerAssignment,
        event_start_ms: int,
        start_ms: int,
        end_ms: int,
    ) -> tuple[list[list[float | int]], list[list[float | int]]]:
        device_id = assignment.telemetry_device_id
        latitude = self._metric("latitude", "position", device_id, start_ms, end_ms)
        longitude = self._metric("longitude", "position", device_id, start_ms, end_ms)
        current_fix = self._metric("fix_current", "position", device_id, start_ms, end_ms)
        speed = self._metric("speed_mps", "status", device_id, start_ms, end_ms)
        course = self._metric("course_deg", "status", device_id, start_ms, end_ms)
        status_latitude = self._metric("latitude", "status", device_id, start_ms, end_ms)
        status_longitude = self._metric("longitude", "status", device_id, start_ms, end_ms)
        status_fix = self._metric("fix_current", "status", device_id, start_ms, end_ms)

        positions = [
            [timestamp - event_start_ms, longitude[timestamp], latitude[timestamp]]
            for timestamp in sorted(latitude.keys() & longitude.keys() & current_fix.keys())
            if current_fix[timestamp] == 1
        ]
        motion = [
            [
                timestamp - event_start_ms,
                speed[timestamp] * KNOTS_PER_MPS,
                course[timestamp],
                status_longitude[timestamp],
                status_latitude[timestamp],
            ]
            for timestamp in sorted(
                speed.keys()
                & course.keys()
                & status_latitude.keys()
                & status_longitude.keys()
                & status_fix.keys()
            )
            if status_fix[timestamp] == 1
        ]
        return positions, motion

    def get_tracks(self, event: Event, start_ms: int, end_ms: int) -> list[dict[str, Any]]:
        tracks: list[dict[str, Any]] = []
        for entry in event.entries:
            positions: list[list[float | int]] = []
            motion: list[list[float | int]] = []
            for assignment in entry.tracker_assignments:
                interval = assignment_range(assignment, start_ms, end_ms)
                if interval is None:
                    continue
                assignment_positions, assignment_motion = self._assignment_track(
                    assignment,
                    event.start_ms,
                    *interval,
                )
                positions.extend(assignment_positions)
                motion.extend(assignment_motion)
            positions.sort(key=lambda sample: sample[0])
            motion.sort(key=lambda sample: sample[0])
            tracks.append({"entryId": entry.id, "positions": positions, "motion": motion})
        return tracks


class GuestTrackVisibilityPolicy:
    """Publish only positions inside an event's public geographic boundary."""

    @staticmethod
    def _inside(bounds: list[list[float]], longitude: float, latitude: float) -> bool:
        (west, south), (east, north) = bounds
        return west <= longitude <= east and south <= latitude <= north

    def publish_tracks(self, event: Event, tracks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        published: list[dict[str, Any]] = []
        for track in tracks:
            segments: list[dict[str, Any]] = []
            current: list[list[float | int]] = []
            for sample in track["positions"]:
                if self._inside(event.publication_bounds, float(sample[1]), float(sample[2])):
                    current.append(sample)
                elif current:
                    segments.append({"positions": current})
                    current = []
            if current:
                segments.append({"positions": current})
            motion = [
                sample[:3]
                for sample in track["motion"]
                if self._inside(event.publication_bounds, float(sample[3]), float(sample[4]))
            ]
            published.append(
                {
                    "entryId": track["entryId"],
                    "segments": segments,
                    "motion": motion,
                }
            )
        return published


class EventService:
    def __init__(
        self,
        events: EventRepository,
        telemetry: TelemetryRepository,
        visibility: TrackVisibilityPolicy,
        live_template: Event,
    ) -> None:
        self.events = events
        self.telemetry = telemetry
        self.visibility = visibility
        self.live_template = live_template

    def _live_event(self, now_ms: int) -> Event:
        start_ms = now_ms - LIVE_WINDOW_MS
        isoformat = lambda value: datetime.fromtimestamp(value / 1000, timezone.utc).isoformat()
        return Event(
            slug="live",
            name="Live",
            start_time=isoformat(start_ms),
            end_time=isoformat(now_ms),
            initial_bounds=self.live_template.initial_bounds,
            publication_bounds=self.live_template.publication_bounds,
            entries=self.live_template.entries,
        )

    def list_events(self) -> dict[str, Any]:
        return {"events": [event.summary_dict() for event in self.events.list_public_events()]}

    def event_details(self, slug: str) -> dict[str, Any] | None:
        event = self.events.get_public_event(slug)
        return None if event is None else event.public_dict()

    def tracks(self, slug: str, parameters: dict[str, list[str]]) -> dict[str, Any] | None:
        event = self.events.get_public_event(slug)
        if event is None:
            return None
        interval = bounded_query_range(parameters, event)
        if interval is None:
            return {"eventSlug": event.slug, "tracks": []}
        raw_tracks = self.telemetry.get_tracks(event, *interval)
        return {
            "eventSlug": event.slug,
            "tracks": self.visibility.publish_tracks(event, raw_tracks),
        }

    def live_details(self, now_ms: int | None = None) -> dict[str, Any]:
        return self._live_event(now_ms or time.time_ns() // 1_000_000).public_dict()

    def live_tracks(self, now_ms: int | None = None) -> dict[str, Any]:
        event = self._live_event(now_ms or time.time_ns() // 1_000_000)
        raw_tracks = self.telemetry.get_tracks(event, event.start_ms, event.end_ms)
        return {
            "eventSlug": event.slug,
            "tracks": self.visibility.publish_tracks(event, raw_tracks),
        }


class ApiHandler(BaseHTTPRequestHandler):
    service: EventService

    def do_GET(self) -> None:  # noqa: N802 - method name is defined by BaseHTTPRequestHandler
        parsed = urllib.parse.urlsplit(self.path)
        if parsed.path == "/api/v1/events":
            self._json(200, self.service.list_events())
            return
        if parsed.path == "/api/v1/live":
            self._json(200, self.service.live_details())
            return
        if parsed.path == "/api/v1/live/tracks":
            try:
                self._json(200, self.service.live_tracks())
            except (OSError, RuntimeError, json.JSONDecodeError, urllib.error.URLError) as error:
                LOGGER.exception("Live telemetry query failed")
                self._json(502, {"error": "telemetry_unavailable", "message": str(error)})
            return

        parts = parsed.path.strip("/").split("/")
        if len(parts) not in (4, 5) or parts[:3] != ["api", "v1", "events"]:
            self._json(404, {"error": "not_found"})
            return
        slug = urllib.parse.unquote(parts[3])
        if len(parts) == 4:
            details = self.service.event_details(slug)
            if details is None:
                self._json(404, {"error": "not_found"})
            else:
                self._json(200, details)
            return
        if parts[4] != "tracks":
            self._json(404, {"error": "not_found"})
            return

        try:
            result = self.service.tracks(slug, urllib.parse.parse_qs(parsed.query))
        except ValueError as error:
            self._json(400, {"error": "invalid_query", "message": str(error)})
            return
        except (OSError, RuntimeError, json.JSONDecodeError, urllib.error.URLError) as error:
            LOGGER.exception("Telemetry query failed")
            self._json(502, {"error": "telemetry_unavailable", "message": str(error)})
            return
        if result is None:
            self._json(404, {"error": "not_found"})
        else:
            self._json(200, result)

    def _json(self, status: int, value: object) -> None:
        body = json.dumps(value, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        LOGGER.info(format, *args)


def serve(host: str, port: int, victoria_metrics_url: str) -> None:
    telemetry = VictoriaMetricsTelemetryRepository(victoria_metrics_url)
    service = EventService(
        EVENT_REPOSITORY,
        telemetry,
        GuestTrackVisibilityPolicy(),
        PILSENSEE_EVENTS[0],
    )
    handler = type("ConfiguredApiHandler", (ApiHandler,), {"service": service})
    server = ThreadingHTTPServer((host, port), handler)
    LOGGER.info(json.dumps({"event": "web_api_started", "host": host, "port": port}))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Open Sail Tracker HTTP API")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", default=8080, type=int)
    parser.add_argument("--log-level", default="INFO")
    parser.add_argument(
        "--victoria-metrics-url",
        default=os.getenv("VICTORIA_METRICS_QUERY_URL", "http://localhost:8428/api/v1/export"),
    )
    args = parser.parse_args()
    logging.basicConfig(level=args.log_level.upper(), format="%(message)s")
    serve(args.host, args.port, args.victoria_metrics_url)


if __name__ == "__main__":
    main()
