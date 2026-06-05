from __future__ import annotations

import unittest

from src.live.roi_calibration import PixelBox
from src.live.yolo_card_detector import _assign_side_by_center, _is_card_class, build_yolo_detector


class YoloCardDetectorTests(unittest.TestCase):
    def test_empty_model_config_disables_yolo_detector(self) -> None:
        self.assertIsNone(build_yolo_detector({}))

    def test_assigns_detection_to_player_or_banker_by_center(self) -> None:
        rois = {
            "PLAYER": PixelBox(100, 100, 300, 250),
            "BANKER": PixelBox(400, 100, 650, 250),
        }

        self.assertEqual(_assign_side_by_center((150, 140, 220, 210), rois), "PLAYER")
        self.assertEqual(_assign_side_by_center((450, 140, 520, 210), rois), "BANKER")
        self.assertIsNone(_assign_side_by_center((700, 140, 760, 210), rois))

    def test_filters_non_card_classes(self) -> None:
        self.assertTrue(_is_card_class("card", ("card", "playing_card")))
        self.assertFalse(_is_card_class("chip", ("card", "playing_card")))


if __name__ == "__main__":
    unittest.main()
