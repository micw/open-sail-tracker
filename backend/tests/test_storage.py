from __future__ import annotations

import queue
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from open_sail_tracker_backend.storage import VictoriaMetricsWriter, encode_telemetry


class TelemetryEncodingTests(unittest.TestCase):
    def test_encodes_all_available_position_values(self) -> None:
        packet = {
            "protocol_version": 1,
            "packet_type": "position",
            "device_id": "4c939764",
            "boot_id": "12345678",
            "sequence": 7,
            "position_known": True,
            "fix_current": True,
            "gnss_on": True,
            "gnss_error": False,
            "latitude": 51.335525,
            "longitude": 12.2393267,
        }
        encoded = encode_telemetry(
            packet,
            coap_message_id=42,
            coap_path="/v1/position",
            coap_type="non_confirmable",
            datagram_size=45,
            source_ip="192.0.2.1",
            source_port=39000,
            received_at_ms=1_700_000_000_123,
        )

        self.assertIn('device_id="4c939764"', encoded)
        self.assertIn('open_sail_tracker_latitude{', encoded)
        self.assertIn(" 51.335525 1700000000123", encoded)
        self.assertIn('open_sail_tracker_fix_current{', encoded)
        self.assertIn(" 1 1700000000123", encoded)
        self.assertIn('open_sail_tracker_source_port{', encoded)
        self.assertIn('coap_path="/v1/position"', encoded)
        self.assertIn('coap_type="non_confirmable"', encoded)
        self.assertIn('open_sail_tracker_datagram_size_bytes{', encoded)
        self.assertNotIn("latitude_e7", encoded)

    def test_omits_unavailable_values_and_encodes_states_as_labels(self) -> None:
        packet = {
            "protocol_version": 1,
            "packet_type": "status",
            "device_id": 'device"one',
            "boot_id": "12345678",
            "sequence": 8,
            "latitude": None,
            "battery_mv": 3778,
            "cell_state": "data",
            "health": "ok",
            "reset_reason": "power_on",
        }
        encoded = encode_telemetry(
            packet,
            coap_message_id=43,
            coap_path="/v1/status",
            coap_type="confirmable",
            datagram_size=75,
            source_ip="192.0.2.1",
            source_port=39000,
            received_at_ms=1_700_000_000_124,
        )

        self.assertNotIn("latitude", encoded)
        self.assertIn('device_id="device\\"one"', encoded)
        self.assertIn('cell_state="data"', encoded)
        self.assertIn('health="ok"', encoded)
        self.assertIn('reset_reason="power_on"', encoded)
        self.assertIn("open_sail_tracker_battery_mv", encoded)


class VictoriaMetricsWriterTests(unittest.TestCase):
    def test_posts_queued_metrics(self) -> None:
        received: queue.Queue[tuple[str, str, bytes]] = queue.Queue()

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802 - method name is defined by BaseHTTPRequestHandler
                length = int(self.headers["Content-Length"])
                received.put((self.path, self.headers["Content-Type"], self.rfile.read(length)))
                self.send_response(204)
                self.end_headers()

            def log_message(self, format: str, *args: object) -> None:
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()
        writer = VictoriaMetricsWriter(
            f"http://127.0.0.1:{server.server_port}/api/v1/import/prometheus",
            flush_interval_s=0.01,
            request_timeout_s=1,
        )
        try:
            writer.submit("open_sail_tracker_test 1 1700000000123\n")
            path, content_type, body = received.get(timeout=2)
        finally:
            writer.close()
            server.shutdown()
            server.server_close()
            server_thread.join(2)

        self.assertEqual(path, "/api/v1/import/prometheus")
        self.assertEqual(content_type, "text/plain; charset=utf-8")
        self.assertEqual(body, b"open_sail_tracker_test 1 1700000000123\n")


if __name__ == "__main__":
    unittest.main()
