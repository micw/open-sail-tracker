from __future__ import annotations

import unittest
from typing import Any

from open_sail_tracker_backend.web_api import (
    RACE_REPOSITORY,
    TEST_RACE,
    Race,
    RaceService,
    StaticRaceRepository,
    VictoriaMetricsTelemetryRepository,
    bounded_query_range,
)


class QueryBoundaryTests(unittest.TestCase):
    def test_clamps_query_to_race_boundaries(self) -> None:
        interval = bounded_query_range(
            {"from": ["2026-09-19T07:00:00Z"], "to": ["2026-09-19T12:00:00Z"]},
            TEST_RACE,
        )
        self.assertEqual(interval, (TEST_RACE.start_ms, TEST_RACE.end_ms))

    def test_returns_no_interval_outside_race(self) -> None:
        interval = bounded_query_range(
            {"from": ["2026-09-19T13:00:00Z"], "to": ["2026-09-19T14:00:00Z"]},
            TEST_RACE,
        )
        self.assertIsNone(interval)

    def test_rejects_missing_or_unzoned_timestamps(self) -> None:
        with self.assertRaisesRegex(ValueError, "supplied once"):
            bounded_query_range({"from": [TEST_RACE.start_time]}, TEST_RACE)
        with self.assertRaisesRegex(ValueError, "time zone"):
            bounded_query_range(
                {"from": ["2026-09-19T10:50:00"], "to": [TEST_RACE.end_time]},
                TEST_RACE,
            )


class StaticRaceRepositoryTests(unittest.TestCase):
    def test_lists_and_resolves_races_by_slug(self) -> None:
        self.assertEqual(RACE_REPOSITORY.list_races(), [TEST_RACE])
        self.assertIs(RACE_REPOSITORY.get_race(TEST_RACE.slug), TEST_RACE)
        self.assertIsNone(RACE_REPOSITORY.get_race("missing"))

    def test_rejects_duplicate_slugs(self) -> None:
        with self.assertRaisesRegex(ValueError, "unique"):
            StaticRaceRepository((TEST_RACE, TEST_RACE))


class FakeVictoriaMetricsRepository(VictoriaMetricsTelemetryRepository):
    def __init__(self, metrics: dict[tuple[str, str], dict[int, float]]) -> None:
        self.metrics = metrics

    def _metric(
        self,
        name: str,
        packet_type: str,
        device_id: str,
        start_ms: int,
        end_ms: int,
    ) -> dict[int, float]:
        return self.metrics.get((name, packet_type), {})


class TrackAssemblyTests(unittest.TestCase):
    def test_joins_samples_and_omits_stale_positions(self) -> None:
        first = TEST_RACE.start_ms + 1_000
        stale = TEST_RACE.start_ms + 2_000
        status = TEST_RACE.start_ms + 10_000
        repository = FakeVictoriaMetricsRepository(
            {
                ("latitude", "position"): {first: 51.1, stale: 51.2},
                ("longitude", "position"): {first: 12.1, stale: 12.2},
                ("fix_current", "position"): {first: 1, stale: 0},
                ("speed_mps", "status"): {status: 2.0},
                ("course_deg", "status"): {status: 123.4},
            }
        )

        result = repository.get_tracks(TEST_RACE, TEST_RACE.start_ms, TEST_RACE.end_ms)

        self.assertEqual(result[0]["entryId"], "test-entry")
        self.assertEqual(result[0]["positions"], [[1_000, 12.1, 51.1]])
        self.assertEqual(result[0]["motion"][0][0], 10_000)
        self.assertAlmostEqual(result[0]["motion"][0][1], 3.8876889848812)
        self.assertEqual(result[0]["motion"][0][2], 123.4)


class FakeTelemetryRepository:
    def __init__(self) -> None:
        self.calls: list[tuple[Race, int, int]] = []

    def get_tracks(self, race: Race, start_ms: int, end_ms: int) -> list[dict[str, Any]]:
        self.calls.append((race, start_ms, end_ms))
        return [{"entryId": "test-entry", "positions": [], "motion": []}]


class RaceServiceTests(unittest.TestCase):
    def test_lists_races_and_returns_public_details(self) -> None:
        service = RaceService(RACE_REPOSITORY, FakeTelemetryRepository())
        listed = service.list_races()
        details = service.race_details(TEST_RACE.slug)

        self.assertEqual(listed["races"][0]["slug"], TEST_RACE.slug)
        self.assertEqual(details["entries"][0]["trackerNumber"], "01")  # type: ignore[index]
        self.assertNotIn("telemetryDeviceId", str(details))

    def test_bounds_track_query_before_calling_telemetry(self) -> None:
        telemetry = FakeTelemetryRepository()
        service = RaceService(RACE_REPOSITORY, telemetry)
        result = service.tracks(
            TEST_RACE.slug,
            {"from": ["2026-09-19T07:00:00Z"], "to": ["2026-09-19T12:00:00Z"]},
        )

        self.assertEqual(result["raceSlug"], TEST_RACE.slug)  # type: ignore[index]
        self.assertEqual(telemetry.calls[0][1:], (TEST_RACE.start_ms, TEST_RACE.end_ms))

    def test_does_not_query_telemetry_outside_race(self) -> None:
        telemetry = FakeTelemetryRepository()
        service = RaceService(RACE_REPOSITORY, telemetry)
        result = service.tracks(
            TEST_RACE.slug,
            {"from": ["2026-09-20T07:00:00Z"], "to": ["2026-09-20T08:00:00Z"]},
        )

        self.assertEqual(result, {"raceSlug": TEST_RACE.slug, "tracks": []})
        self.assertEqual(telemetry.calls, [])


if __name__ == "__main__":
    unittest.main()
