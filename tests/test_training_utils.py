from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from src.data.validate_annotations import validate_dataset
from src.evaluation.eval_rounds import evaluate_rounds


class TrainingUtilityTests(unittest.TestCase):
    def test_validate_dataset_accepts_minimal_valid_annotations(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dataset = Path(tmp) / "baccarat_v1"
            _write_valid_dataset(dataset)

            report = validate_dataset(dataset)

            self.assertTrue(report.ok, report.errors)
            self.assertEqual(report.counts["rounds"], 1)
            self.assertEqual(report.counts["clock_labels"], 1)
            self.assertEqual(report.counts["card_identity"], 4)

    def test_validate_dataset_flags_bad_card_identity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dataset = Path(tmp) / "baccarat_v1"
            _write_valid_dataset(dataset)
            card_identity = dataset / "annotations" / "card_identity.csv"
            card_identity.write_text(
                "crop_id,frame_id,zone,slot,card_crop_path,rank,suit,visible,quality,label_status,split\n"
                "c1,f1,PLAYER,1,crops/card.jpg,1,stars,true,good,verified,train\n",
                encoding="utf-8",
            )

            report = validate_dataset(dataset)

            self.assertFalse(report.ok)
            self.assertTrue(any("invalid_rank" in error for error in report.errors))
            self.assertTrue(any("invalid_suit" in error for error in report.errors))

    def test_evaluate_rounds_scores_closed_events(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            truth = Path(tmp) / "truth.jsonl"
            predictions = Path(tmp) / "predictions.jsonl"
            truth.write_text(
                json.dumps(
                    {
                        "round_id": "MD3212_20260604_1844",
                        "player_cards": ["5H", "9S"],
                        "banker_cards": ["7H", "7D"],
                        "winner": "TIE",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            predictions.write_text(
                json.dumps(
                    {
                        "event_type": "round.closed",
                        "round_id": "MD3212_20260604_1844",
                        "player_cards": [
                            {"rank": "5", "suit": "hearts"},
                            {"rank": "9", "suit": "spades"},
                        ],
                        "banker_cards": [
                            {"rank": "7", "suit": "hearts"},
                            {"rank": "7", "suit": "diamonds"},
                        ],
                        "winner": "TIE",
                        "validation": {"needs_review": False},
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            metrics = evaluate_rounds(truth, predictions)

            self.assertEqual(metrics["round_recall"], 1.0)
            self.assertEqual(metrics["exact_round_accuracy"], 1.0)
            self.assertEqual(metrics["human_review_rate"], 0.0)


def _write_valid_dataset(dataset: Path) -> None:
    annotations = dataset / "annotations"
    manifests = dataset / "manifests"
    splits = dataset / "splits"
    annotations.mkdir(parents=True)
    manifests.mkdir()
    splits.mkdir()

    (annotations / "rounds.jsonl").write_text(
        json.dumps(
            {
                "round_id": "MD3212_20260604_1844",
                "table_id": "MD3212",
                "video_id": "2026-06-04_session_01",
                "start_frame_id": "f1",
                "end_frame_id": "f2",
                "start_time_visible_clock": "18:44:00",
                "end_time_visible_clock": "18:44:59",
                "boundary_confidence_label": "clear",
                "player_cards": ["5H", "9S"],
                "banker_cards": ["7H", "7D"],
                "winner": "TIE",
                "split": "train",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (annotations / "clock_labels.csv").write_text(
        "frame_id,clock_crop_path,clock_text,clock_format,visible,quality,label_status,split\n"
        "f1,crops/clock/000001.jpg,18:44:01,HH:MM:SS,true,good,verified,train\n",
        encoding="utf-8",
    )
    (annotations / "card_identity.csv").write_text(
        "crop_id,frame_id,zone,slot,card_crop_path,corner_crop_path,rank,suit,visible,occlusion,quality,label_status,split\n"
        "c1,f1,PLAYER,1,crops/p1.jpg,crops/p1c.jpg,5,hearts,true,none,good,verified,train\n"
        "c2,f1,PLAYER,2,crops/p2.jpg,crops/p2c.jpg,9,spades,true,none,good,verified,train\n"
        "c3,f1,BANKER,1,crops/b1.jpg,crops/b1c.jpg,7,hearts,true,none,good,verified,train\n"
        "c4,f1,BANKER,2,crops/b2.jpg,crops/b2c.jpg,7,diamonds,true,none,good,verified,train\n",
        encoding="utf-8",
    )
    (manifests / "frames_manifest.jsonl").write_text(
        json.dumps(
            {
                "frame_id": "f1",
                "table_id": "MD3212",
                "camera_id": "cam-01",
                "video_id": "2026-06-04_session_01",
                "frame_path": "frames/table_MD3212/000001.jpg",
                "width": 1450,
                "height": 685,
                "split": "train",
                "round_id": "MD3212_20260604_1844",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    for split in ("train", "val", "test"):
        (splits / f"{split}.txt").write_text("", encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
