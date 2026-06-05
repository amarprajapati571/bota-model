from __future__ import annotations

from io import BytesIO
import unittest

from PIL import Image, ImageDraw

from src.live.timer_visibility import detect_timer_visibility


ROIS = {"timer_primary": {"x1": 0.0, "y1": 0.0, "x2": 1.0, "y2": 1.0}}


def _timer_crop(visible: bool) -> bytes:
    image = Image.new("RGB", (240, 80), (2, 8, 12))
    if visible:
        draw = ImageDraw.Draw(image)
        draw.rectangle((20, 12, 220, 68), fill=(5, 20, 30))
        draw.text((62, 22), "18:43", fill=(75, 210, 240))
    buffer = BytesIO()
    image.save(buffer, format="JPEG")
    return buffer.getvalue()


class TimerVisibilityTests(unittest.TestCase):
    def test_detects_visible_timer_without_ocr(self) -> None:
        timer = detect_timer_visibility(_timer_crop(True), ROIS, visibility_threshold=0.25)

        self.assertTrue(timer.visible)
        self.assertGreater(timer.confidence, 0)
        self.assertIn(timer.reason, {"cyan_digits", "bright_digits"})

    def test_detects_hidden_timer(self) -> None:
        timer = detect_timer_visibility(_timer_crop(False), ROIS, visibility_threshold=0.25)

        self.assertFalse(timer.visible)
        self.assertEqual(timer.reason, "hidden")


if __name__ == "__main__":
    unittest.main()
