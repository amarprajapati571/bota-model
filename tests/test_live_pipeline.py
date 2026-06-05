from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
import unittest

from PIL import Image, ImageDraw

from src.live.config import LiveConfig
from src.live.events import EventSequencer
from src.live.pipeline import LiveInferencePipeline
from src.live.roi_calibration import normalized_roi_to_pixels


def _config() -> LiveConfig:
    return LiveConfig(
        table_id="MD3212",
        stream_id="stream_MD3212_live",
        camera_id="cam-01",
        source_type="browser_page",
        source_url="https://example.test",
        viewport_width=1000,
        viewport_height=500,
        raw_frame_width=1000,
        raw_frame_height=500,
        wait_after_load_ms=0,
        capture_fps=5,
        evidence_dir=Path("/tmp/bota-model-test-evidence"),
        save_latest_frame=False,
        save_roi_crops=False,
        playback={},
        ws_url="",
        rois={
            "clock": {"x1": 0.02, "y1": 0.02, "x2": 0.20, "y2": 0.12},
            "player": {"x1": 0.25, "y1": 0.25, "x2": 0.50, "y2": 0.55},
            "banker": {"x1": 0.52, "y1": 0.25, "x2": 0.75, "y2": 0.55},
        },
        clock_ocr_enabled=False,
        card_recognition_enabled=False,
        card_detector_backend="heuristic",
        yolo_card_detector={},
        debug_sample_every=0,
        card_hold_frames=2,
        card_confirm_frames=2,
        card_min_confidence=0.45,
        visual_stable_frames=3,
        empty_reset_frames=3,
        clock_ocr_interval_frames=5,
        timer_visibility_threshold=0.55,
        timer_hidden_confirm_frames=2,
        timer_visible_confirm_frames=2,
        round_reset_delay_ms=1500,
    )


def _frame(with_cards: bool, timer_visible: bool = False) -> bytes:
    image = Image.new("RGB", (1000, 500), (0, 90, 50))
    draw = ImageDraw.Draw(image)
    if timer_visible:
        draw.rectangle((30, 20, 180, 55), fill=(5, 20, 30))
        draw.text((55, 25), "18:43", fill=(70, 210, 240))
    if with_cards:
        draw.rectangle((320, 165, 370, 235), fill=(245, 245, 240))
        draw.rectangle((390, 165, 440, 235), fill=(245, 245, 240))
        draw.rectangle((560, 165, 610, 235), fill=(245, 245, 240))
        draw.rectangle((630, 165, 680, 235), fill=(245, 245, 240))
    buffer = BytesIO()
    image.save(buffer, format="JPEG")
    return buffer.getvalue()


def _frame_one_side(side: str) -> bytes:
    image = Image.new("RGB", (1000, 500), (0, 90, 50))
    draw = ImageDraw.Draw(image)
    if side == "PLAYER":
        draw.rectangle((320, 165, 370, 235), fill=(245, 245, 240))
        draw.rectangle((390, 165, 440, 235), fill=(245, 245, 240))
    else:
        draw.rectangle((560, 165, 610, 235), fill=(245, 245, 240))
        draw.rectangle((630, 165, 680, 235), fill=(245, 245, 240))
    buffer = BytesIO()
    image.save(buffer, format="JPEG")
    return buffer.getvalue()


class LivePipelineTests(unittest.TestCase):
    def test_roi_scaling_uses_source_pixels(self) -> None:
        box = normalized_roi_to_pixels({"x1": 0.25, "y1": 0.2, "x2": 0.5, "y2": 0.6}, 1000, 500)

        self.assertEqual(box.to_dict(), {"x1": 250, "y1": 100, "x2": 500, "y2": 300})

    def test_pipeline_confirms_cards_after_stable_frames(self) -> None:
        pipeline = LiveInferencePipeline(_config(), EventSequencer())
        now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)

        pipeline.process_frame(_frame(False, timer_visible=True), now, "b1", 1)
        pipeline.process_frame(_frame(False, timer_visible=True), now, "b2", 2)
        pipeline.process_frame(_frame(False, timer_visible=False), now, "s1", 3)
        pipeline.process_frame(_frame(False, timer_visible=False), now, "s2", 4)
        first = pipeline.process_frame(_frame(True), now, "f1", 5)
        second = pipeline.process_frame(_frame(True), now, "f2", 6)

        self.assertEqual(first.card_payload["player_cards"], [])
        self.assertGreaterEqual(len(second.card_payload["player_cards"]), 2)
        self.assertGreaterEqual(len(second.card_payload["banker_cards"]), 2)
        self.assertIn("round.state", [event["event_type"] for event in second.events])

    def test_pipeline_holds_cards_through_short_miss(self) -> None:
        pipeline = LiveInferencePipeline(_config(), EventSequencer())
        now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)

        pipeline.process_frame(_frame(False, timer_visible=True), now, "b1", 1)
        pipeline.process_frame(_frame(False, timer_visible=True), now, "b2", 2)
        pipeline.process_frame(_frame(False, timer_visible=False), now, "s1", 3)
        pipeline.process_frame(_frame(False, timer_visible=False), now, "s2", 4)
        pipeline.process_frame(_frame(True), now, "f1", 5)
        pipeline.process_frame(_frame(True), now, "f2", 6)
        miss = pipeline.process_frame(_frame(False), now, "f3", 7)

        self.assertGreaterEqual(len(miss.card_payload["player_cards"]), 2)

    def test_player_and_banker_zones_do_not_mix(self) -> None:
        pipeline = LiveInferencePipeline(_config(), EventSequencer())
        now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)

        pipeline.process_frame(_frame(False, timer_visible=True), now, "b1", 1)
        pipeline.process_frame(_frame(False, timer_visible=True), now, "b2", 2)
        pipeline.process_frame(_frame(False, timer_visible=False), now, "s1", 3)
        pipeline.process_frame(_frame(False, timer_visible=False), now, "s2", 4)
        pipeline.process_frame(_frame_one_side("PLAYER"), now, "p1", 5)
        player = pipeline.process_frame(_frame_one_side("PLAYER"), now, "p2", 6)

        self.assertGreaterEqual(len(player.card_payload["player_cards"]), 2)
        self.assertEqual(player.card_payload["banker_cards"], [])

    def test_cards_are_ignored_while_timer_is_visible_for_betting(self) -> None:
        pipeline = LiveInferencePipeline(_config(), EventSequencer())
        now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)

        pipeline.process_frame(_frame(True, timer_visible=True), now, "b1", 1)
        result = pipeline.process_frame(_frame(True, timer_visible=True), now, "b2", 2)

        self.assertEqual(result.round_state, "BETTING_COUNTDOWN_VISIBLE")
        self.assertEqual(result.card_payload, {"player_cards": [], "banker_cards": []})
        self.assertGreater(result.debug_payload["ignored_raw_card_count"], 0)

    def test_low_confidence_cards_are_rejected_before_state_update(self) -> None:
        config = _config()
        pipeline = LiveInferencePipeline(config, EventSequencer())
        payload = {
            "player_cards": [
                {
                    "slot": 1,
                    "bbox_norm": {"x1": 0.3, "y1": 0.3, "x2": 0.35, "y2": 0.4},
                    "det_confidence": 0.1,
                }
            ],
            "banker_cards": [],
        }

        self.assertEqual(pipeline._filter_card_payload(payload), {"player_cards": [], "banker_cards": []})

    def test_review_required_is_not_spammed_after_round_complete(self) -> None:
        pipeline = LiveInferencePipeline(_config(), EventSequencer())
        now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
        review_counts = []

        frames = [
            _frame(False, timer_visible=True),
            _frame(False, timer_visible=True),
            _frame(False, timer_visible=False),
            _frame(False, timer_visible=False),
            _frame(True, timer_visible=False),
            _frame(True, timer_visible=False),
            _frame(True, timer_visible=False),
            _frame(True, timer_visible=False),
            _frame(True, timer_visible=False),
        ]
        for index, frame_bytes in enumerate(frames, start=1):
            result = pipeline.process_frame(frame_bytes, now, f"f{index}", index)
            review_counts.append(
                sum(event["event_type"] == "review.required" for event in result.events)
            )

        self.assertEqual(sum(review_counts), 1)

    def test_debug_payload_redacts_source_url_and_records_latency(self) -> None:
        pipeline = LiveInferencePipeline(_config(), EventSequencer())
        now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)

        result = pipeline.process_frame(_frame(False), now, "f1", 1)

        self.assertNotIn("source_url", result.debug_payload)
        self.assertEqual(result.debug_payload["source"]["host"], "example.test")
        self.assertIn("processing_ms", result.debug_payload)

    def test_timer_visible_then_hidden_starts_match(self) -> None:
        pipeline = LiveInferencePipeline(_config(), EventSequencer())
        now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)

        pipeline.process_frame(_frame(False, timer_visible=True), now, "t1", 1)
        visible = pipeline.process_frame(_frame(False, timer_visible=True), now, "t2", 2)
        pipeline.process_frame(_frame(False, timer_visible=False), now, "t3", 3)
        hidden = pipeline.process_frame(_frame(False, timer_visible=False), now, "t4", 4)

        self.assertEqual(visible.round_state, "BETTING_COUNTDOWN_VISIBLE")
        self.assertEqual(hidden.round_state, "MATCH_STARTED_TIMER_HIDDEN")

    def test_timer_reappears_after_round_complete_resets_next_bets(self) -> None:
        pipeline = LiveInferencePipeline(_config(), EventSequencer())
        now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
        frames = [
            _frame(False, timer_visible=True),
            _frame(False, timer_visible=True),
            _frame(False, timer_visible=False),
            _frame(False, timer_visible=False),
            _frame(True, timer_visible=False),
            _frame(True, timer_visible=False),
            _frame(True, timer_visible=False),
            _frame(True, timer_visible=False),
            _frame(True, timer_visible=True),
            _frame(True, timer_visible=True),
        ]

        result = None
        for index, frame_bytes in enumerate(frames, start=1):
            result = pipeline.process_frame(frame_bytes, now, f"r{index}", index)

        self.assertIsNotNone(result)
        self.assertIn(result.round_state, {"RESET_WAITING_NEXT_BETS", "BETTING_COUNTDOWN_VISIBLE"})


if __name__ == "__main__":
    unittest.main()
