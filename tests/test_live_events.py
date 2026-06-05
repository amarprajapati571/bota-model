from __future__ import annotations

import unittest

from src.live.events import EventSequencer, make_event, stream_health_event


class LiveEventsTests(unittest.TestCase):
    def test_event_sequencer_increments(self) -> None:
        sequencer = EventSequencer()
        self.assertEqual(sequencer.next(), 1)
        self.assertEqual(sequencer.next(), 2)

    def test_make_event_includes_frontend_envelope_fields(self) -> None:
        event = make_event(
            "frame.captured",
            "MD3212",
            "stream_MD3212_live",
            7,
            {"frame_id": "f1"},
            frame_id="f1",
        )

        self.assertEqual(event["event_type"], "frame.captured")
        self.assertEqual(event["schema_version"], "1.0")
        self.assertEqual(event["table_id"], "MD3212")
        self.assertEqual(event["stream_id"], "stream_MD3212_live")
        self.assertEqual(event["sequence_number"], 7)
        self.assertTrue(event["event_id"].startswith("evt_"))

    def test_stream_health_payload_matches_frontend_contract(self) -> None:
        event = stream_health_event(
            "MD3212",
            "stream_MD3212_live",
            3,
            status="healthy",
            source_connected=True,
            last_frame_age_ms=10,
            capture_fps=1,
        )

        self.assertEqual(event["event_type"], "stream.health")
        self.assertEqual(event["payload"]["status"], "healthy")
        self.assertTrue(event["payload"]["source_connected"])
        self.assertEqual(event["payload"]["fps_processed"], 1)


if __name__ == "__main__":
    unittest.main()
