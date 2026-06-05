from __future__ import annotations

import unittest

from PIL import Image, ImageDraw

from src.live.card_detection import detect_card_boxes
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

    def test_baseline_card_box_detector_finds_bright_cards_in_rois(self) -> None:
        image = Image.new("RGB", (1000, 500), (0, 90, 50))
        draw = ImageDraw.Draw(image)
        draw.rectangle((320, 165, 370, 235), fill=(245, 245, 240))
        draw.rectangle((390, 165, 440, 235), fill=(245, 245, 240))
        draw.rectangle((560, 165, 610, 235), fill=(245, 245, 240))
        draw.rectangle((630, 165, 680, 235), fill=(245, 245, 240))
        import io

        buffer = io.BytesIO()
        image.save(buffer, format="JPEG")

        payload = detect_card_boxes(
            buffer.getvalue(),
            {
                "player": {"x1": 0.25, "y1": 0.25, "x2": 0.50, "y2": 0.55},
                "banker": {"x1": 0.52, "y1": 0.25, "x2": 0.75, "y2": 0.55},
            },
        )

        self.assertGreaterEqual(len(payload["player_cards"]), 2)
        self.assertGreaterEqual(len(payload["banker_cards"]), 2)
        self.assertEqual(payload["player_cards"][0]["rank"], None)


if __name__ == "__main__":
    unittest.main()
