from __future__ import annotations

import unittest
from typing import Any

from open_sail_tracker_backend.web_api import (
    EVENT_REPOSITORY,
    TEST_EVENT,
    Event,
    EventService,
    GuestTrackVisibilityPolicy,
    StaticEventRepository,
    VictoriaMetricsTelemetryRepository,
    assignment_range,
    bounded_query_range,
)


class QueryBoundaryTests(unittest.TestCase):
    def test_clamps_query_to_event_boundaries(self) -> None:
        interval = bounded_query_range(
            {"from": ["2026-09-19T07:00:00Z"], "to": ["2026-09-19T12:00:00Z"]},
            TEST_EVENT,
        )
        self.assertEqual(interval, (TEST_EVENT.start_ms, TEST_EVENT.end_ms))

    def test_returns_no_interval_outside_event(self) -> None:
        interval = bounded_query_range(
            {"from": ["2026-09-19T13:00:00Z"], "to": ["2026-09-19T14:00:00Z"]},
            TEST_EVENT,
        )
        self.assertIsNone(interval)

    def test_rejects_missing_or_unzoned_timestamps(self) -> None:
        with self.assertRaisesRegex(ValueError, "supplied once"):
            bounded_query_range({"from": [TEST_EVENT.start_time]}, TEST_EVENT)
        with self.assertRaisesRegex(ValueError, "time zone"):
            bounded_query_range(
                {"from": ["2026-09-19T10:50:00"], "to": [TEST_EVENT.end_time]},
                TEST_EVENT,
            )

    def test_intersects_tracker_assignment(self) -> None:
        assignment = TEST_EVENT.entries[0].tracker_assignments[0]
        self.assertEqual(
            assignment_range(assignment, TEST_EVENT.start_ms, TEST_EVENT.end_ms),
            (TEST_EVENT.start_ms, TEST_EVENT.end_ms),
        )


class StaticEventRepositoryTests(unittest.TestCase):
    def test_lists_and_resolves_public_events_by_slug(self) -> None:
        self.assertEqual(EVENT_REPOSITORY.list_public_events(), [TEST_EVENT])
        self.assertIs(EVENT_REPOSITORY.get_public_event(TEST_EVENT.slug), TEST_EVENT)
        self.assertIsNone(EVENT_REPOSITORY.get_public_event("missing"))

    def test_rejects_duplicate_slugs(self) -> None:
        with self.assertRaisesRegex(ValueError, "unique"):
            StaticEventRepository((TEST_EVENT, TEST_EVENT))


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
        first = TEST_EVENT.start_ms + 1_000
        stale = TEST_EVENT.start_ms + 2_000
        status = TEST_EVENT.start_ms + 10_000
        repository = FakeVictoriaMetricsRepository(
            {
                ("latitude", "position"): {first: 51.31, stale: 51.31},
                ("longitude", "position"): {first: 12.24, stale: 12.24},
                ("fix_current", "position"): {first: 1, stale: 0},
                ("speed_mps", "status"): {status: 2.0},
                ("course_deg", "status"): {status: 123.4},
                ("latitude", "status"): {status: 51.31},
                ("longitude", "status"): {status: 12.24},
                ("fix_current", "status"): {status: 1},
            }
        )

        result = repository.get_tracks(TEST_EVENT, TEST_EVENT.start_ms, TEST_EVENT.end_ms)

        self.assertEqual(result[0]["entryId"], "test-entry")
        self.assertEqual(result[0]["positions"], [[1_000, 12.24, 51.31]])
        self.assertAlmostEqual(result[0]["motion"][0][1], 3.8876889848812)


class GuestVisibilityTests(unittest.TestCase):
    def test_removes_outside_coordinates_and_splits_track(self) -> None:
        raw = [
            {
                "entryId": "test-entry",
                "positions": [
                    [1_000, 12.24, 51.31],
                    [2_000, 12.25, 51.31],
                    [3_000, 12.27, 51.31],
                    [4_000, 12.25, 51.30],
                ],
                "motion": [
                    [1_000, 2.0, 90.0, 12.24, 51.31],
                    [2_000, 3.0, 180.0, 12.27, 51.31],
                ],
            }
        ]

        result = GuestTrackVisibilityPolicy().publish_tracks(TEST_EVENT, raw)

        self.assertEqual(
            result[0]["segments"],
            [
                {"positions": [[1_000, 12.24, 51.31], [2_000, 12.25, 51.31]]},
                {"positions": [[4_000, 12.25, 51.30]]},
            ],
        )
        self.assertEqual(result[0]["motion"], [[1_000, 2.0, 90.0]])
        self.assertNotIn("12.27", str(result))

    def test_includes_points_on_publication_boundary(self) -> None:
        west_south, east_north = TEST_EVENT.publication_bounds
        self.assertTrue(GuestTrackVisibilityPolicy._inside(TEST_EVENT.publication_bounds, *west_south))
        self.assertTrue(GuestTrackVisibilityPolicy._inside(TEST_EVENT.publication_bounds, *east_north))


class FakeTelemetryRepository:
    def __init__(self) -> None:
        self.calls: list[tuple[Event, int, int]] = []

    def get_tracks(self, event: Event, start_ms: int, end_ms: int) -> list[dict[str, Any]]:
        self.calls.append((event, start_ms, end_ms))
        return [{"entryId": "test-entry", "positions": [], "motion": []}]


class EventServiceTests(unittest.TestCase):
    def create_service(self, telemetry: FakeTelemetryRepository) -> EventService:
        return EventService(
            EVENT_REPOSITORY,
            telemetry,
            GuestTrackVisibilityPolicy(),
            TEST_EVENT,
        )

    def test_lists_events_and_returns_public_details(self) -> None:
        service = self.create_service(FakeTelemetryRepository())
        listed = service.list_events()
        details = service.event_details(TEST_EVENT.slug)

        self.assertEqual(listed["events"][0]["slug"], TEST_EVENT.slug)
        self.assertEqual(details["entries"][0]["trackerNumbers"], ["01"])  # type: ignore[index]
        self.assertNotIn("telemetryDeviceId", str(details))

    def test_bounds_track_query_before_calling_telemetry(self) -> None:
        telemetry = FakeTelemetryRepository()
        service = self.create_service(telemetry)
        result = service.tracks(
            TEST_EVENT.slug,
            {"from": ["2026-09-19T07:00:00Z"], "to": ["2026-09-19T12:00:00Z"]},
        )

        self.assertEqual(result["eventSlug"], TEST_EVENT.slug)  # type: ignore[index]
        self.assertEqual(telemetry.calls[0][1:], (TEST_EVENT.start_ms, TEST_EVENT.end_ms))

    def test_does_not_query_telemetry_outside_event(self) -> None:
        telemetry = FakeTelemetryRepository()
        service = self.create_service(telemetry)
        result = service.tracks(
            TEST_EVENT.slug,
            {"from": ["2026-09-20T07:00:00Z"], "to": ["2026-09-20T08:00:00Z"]},
        )

        self.assertEqual(result, {"eventSlug": TEST_EVENT.slug, "tracks": []})
        self.assertEqual(telemetry.calls, [])

    def test_live_view_queries_recent_telemetry_with_public_bounds(self) -> None:
        telemetry = FakeTelemetryRepository()
        service = self.create_service(telemetry)
        now_ms = 1_800_000_000_000

        details = service.live_details(now_ms)
        result = service.live_tracks(now_ms)

        self.assertEqual(details["event"]["slug"], "live")
        self.assertEqual(details["event"]["publicationBounds"], TEST_EVENT.publication_bounds)
        self.assertEqual(result["eventSlug"], "live")
        self.assertEqual(telemetry.calls[0][2], now_ms)
        self.assertEqual(telemetry.calls[0][2] - telemetry.calls[0][1], 4 * 60 * 60 * 1000)


if __name__ == "__main__":
    unittest.main()
