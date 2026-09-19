"""Unauthenticated HTTP API for races and bounded tracker replay data."""

from __future__ import annotations

import argparse
import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Protocol

LOGGER = logging.getLogger("open_sail_tracker_backend.web_api")
KNOTS_PER_MPS = 1.9438444924406


@dataclass(frozen=True)
class Boat:
    id: str
    sail_number: str
    name: str


@dataclass(frozen=True)
class RaceEntry:
    id: str
    boat: Boat
    color: str
    tracker_number: str
    telemetry_device_id: str


@dataclass(frozen=True)
class Race:
    slug: str
    name: str
    start_time: str
    end_time: str
    initial_bounds: list[list[float]]
    entries: tuple[RaceEntry, ...]

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
            "race": {
                **self.summary_dict(),
                "initialBounds": self.initial_bounds,
                "course": {"type": "FeatureCollection", "features": []},
            },
            "entries": [
                {
                    "id": entry.id,
                    "trackerNumber": entry.tracker_number,
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


class RaceRepository(Protocol):
    """Source of race metadata and tracker-to-entry assignments."""

    def list_races(self) -> list[Race]: ...

    def get_race(self, slug: str) -> Race | None: ...


class TelemetryRepository(Protocol):
    """Source of tracks for entries assigned to a race."""

    def get_tracks(self, race: Race, start_ms: int, end_ms: int) -> list[dict[str, Any]]: ...


class StaticRaceRepository:
    def __init__(self, races: tuple[Race, ...]) -> None:
        self.races = races
        self.by_slug = {race.slug: race for race in races}
        if len(self.by_slug) != len(races):
            raise ValueError("race slugs must be unique")

    def list_races(self) -> list[Race]:
        return list(self.races)

    def get_race(self, slug: str) -> Race | None:
        return self.by_slug.get(slug)


TEST_RACE = Race(
    slug="training-2026-09-19",
    name="Training vom 19. September",
    start_time="2026-09-19T10:50:00+02:00",
    end_time="2026-09-19T12:45:00+02:00",
    initial_bounds=[[12.2367, 51.3047], [12.2514, 51.3168]],
    entries=(
        RaceEntry(
            id="test-entry",
            boat=Boat(id="test-boat", sail_number="TEST", name="Testskiff"),
            color="#ef476f",
            tracker_number="01",
            telemetry_device_id="4c939764",
        ),
    ),
)
RACE_REPOSITORY = StaticRaceRepository((TEST_RACE,))


def parse_datetime(value: str) -> int:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("timestamp must be ISO 8601") from error
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include a time zone")
    return int(parsed.timestamp() * 1000)


def bounded_query_range(parameters: dict[str, list[str]], race: Race) -> tuple[int, int] | None:
    """Validate and clamp a requested interval to the race's hard boundaries."""
    if len(parameters.get("from", [])) != 1 or len(parameters.get("to", [])) != 1:
        raise ValueError("from and to must each be supplied once")
    requested_start = parse_datetime(parameters["from"][0])
    requested_end = parse_datetime(parameters["to"][0])
    if requested_start > requested_end:
        raise ValueError("from must not be later than to")
    start_ms = max(requested_start, race.start_ms)
    end_ms = min(requested_end, race.end_ms)
    return None if start_ms > end_ms else (start_ms, end_ms)


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

    def _entry_track(
        self,
        entry: RaceEntry,
        race_start_ms: int,
        start_ms: int,
        end_ms: int,
    ) -> dict[str, Any]:
        device_id = entry.telemetry_device_id
        latitude = self._metric("latitude", "position", device_id, start_ms, end_ms)
        longitude = self._metric("longitude", "position", device_id, start_ms, end_ms)
        current_fix = self._metric("fix_current", "position", device_id, start_ms, end_ms)
        speed = self._metric("speed_mps", "status", device_id, start_ms, end_ms)
        course = self._metric("course_deg", "status", device_id, start_ms, end_ms)

        positions: list[list[float | int]] = []
        for timestamp in sorted(latitude.keys() & longitude.keys() & current_fix.keys()):
            if current_fix[timestamp] == 1:
                positions.append(
                    [timestamp - race_start_ms, longitude[timestamp], latitude[timestamp]]
                )

        motion: list[list[float | int]] = []
        for timestamp in sorted(speed.keys() & course.keys()):
            motion.append(
                [timestamp - race_start_ms, speed[timestamp] * KNOTS_PER_MPS, course[timestamp]]
            )
        return {"entryId": entry.id, "positions": positions, "motion": motion}

    def get_tracks(self, race: Race, start_ms: int, end_ms: int) -> list[dict[str, Any]]:
        return [
            self._entry_track(entry, race.start_ms, start_ms, end_ms)
            for entry in race.entries
        ]


class RaceService:
    def __init__(self, races: RaceRepository, telemetry: TelemetryRepository) -> None:
        self.races = races
        self.telemetry = telemetry

    def list_races(self) -> dict[str, Any]:
        return {"races": [race.summary_dict() for race in self.races.list_races()]}

    def race_details(self, slug: str) -> dict[str, Any] | None:
        race = self.races.get_race(slug)
        return None if race is None else race.public_dict()

    def tracks(self, slug: str, parameters: dict[str, list[str]]) -> dict[str, Any] | None:
        race = self.races.get_race(slug)
        if race is None:
            return None
        interval = bounded_query_range(parameters, race)
        if interval is None:
            return {"raceSlug": race.slug, "tracks": []}
        return {
            "raceSlug": race.slug,
            "tracks": self.telemetry.get_tracks(race, *interval),
        }


class ApiHandler(BaseHTTPRequestHandler):
    service: RaceService

    def do_GET(self) -> None:  # noqa: N802 - method name is defined by BaseHTTPRequestHandler
        parsed = urllib.parse.urlsplit(self.path)
        if parsed.path == "/api/v1/races":
            self._json(200, self.service.list_races())
            return

        parts = parsed.path.strip("/").split("/")
        if len(parts) not in (4, 5) or parts[:3] != ["api", "v1", "races"]:
            self._json(404, {"error": "not_found"})
            return
        slug = urllib.parse.unquote(parts[3])
        if len(parts) == 4:
            details = self.service.race_details(slug)
            self._json(200, details) if details is not None else self._json(404, {"error": "not_found"})
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
        self._json(200, result) if result is not None else self._json(404, {"error": "not_found"})

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
    service = RaceService(RACE_REPOSITORY, telemetry)
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
