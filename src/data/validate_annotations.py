from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass, field
from pathlib import Path
import sys
from typing import Any


VALID_RANKS = {"A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"}
VALID_SUITS = {"clubs", "diamonds", "hearts", "spades"}
VALID_SPLITS = {"train", "val", "test"}
VALID_BOUNDARY_LABELS = {
    "clear",
    "uncertain_start",
    "uncertain_end",
    "stream_drop",
    "camera_blocked",
    "invalid_round",
}
VALID_CLOCK_QUALITIES = {"good", "blurred", "partial", "glare", "offscreen", "unreadable"}


@dataclass
class ValidationReport:
    dataset: str
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.errors

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset": self.dataset,
            "ok": self.ok,
            "errors": self.errors,
            "warnings": self.warnings,
            "counts": self.counts,
        }


def validate_dataset(dataset: Path) -> ValidationReport:
    report = ValidationReport(str(dataset))
    annotations = dataset / "annotations"
    manifests = dataset / "manifests"

    _require_dir(dataset, report)
    _require_dir(annotations, report)

    rounds = _read_jsonl(annotations / "rounds.jsonl", report, "rounds")
    clock_rows = _read_csv(annotations / "clock_labels.csv", report, "clock_labels")
    card_rows = _read_csv(annotations / "card_identity.csv", report, "card_identity")

    if (manifests / "frames_manifest.jsonl").exists():
        frames = _read_jsonl(manifests / "frames_manifest.jsonl", report, "frames_manifest")
        _validate_frame_manifest(frames, report)

    _validate_rounds(rounds, report)
    _validate_clock_labels(clock_rows, report)
    _validate_card_identity(card_rows, report)
    _validate_split_files(dataset, report)
    return report


def _require_dir(path: Path, report: ValidationReport) -> None:
    if not path.exists():
        report.errors.append(f"missing_directory:{path}")
    elif not path.is_dir():
        report.errors.append(f"not_a_directory:{path}")


def _read_jsonl(path: Path, report: ValidationReport, name: str) -> list[dict[str, Any]]:
    if not path.exists():
        report.errors.append(f"missing_file:{path}")
        return []

    rows: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                report.errors.append(f"{name}:line_{line_number}:invalid_json:{exc.msg}")
                continue
            if not isinstance(row, dict):
                report.errors.append(f"{name}:line_{line_number}:expected_object")
                continue
            row_id = row.get("round_id") or row.get("frame_id") or row.get("video_id")
            if row_id:
                if row_id in seen_ids:
                    report.errors.append(f"{name}:line_{line_number}:duplicate_id:{row_id}")
                seen_ids.add(row_id)
            rows.append(row)

    report.counts[name] = len(rows)
    return rows


def _read_csv(path: Path, report: ValidationReport, name: str) -> list[dict[str, str]]:
    if not path.exists():
        report.errors.append(f"missing_file:{path}")
        return []

    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        if not reader.fieldnames:
            report.errors.append(f"{name}:missing_header")
        report.counts[name] = len(rows)
        return rows


def _validate_rounds(rows: list[dict[str, Any]], report: ValidationReport) -> None:
    required = {
        "round_id",
        "table_id",
        "video_id",
        "start_frame_id",
        "end_frame_id",
        "start_time_visible_clock",
        "end_time_visible_clock",
        "boundary_confidence_label",
    }
    split_by_round: dict[str, set[str]] = {}

    for index, row in enumerate(rows, start=1):
        _require_fields(row, required, report, f"rounds:line_{index}")
        label = row.get("boundary_confidence_label")
        if label and label not in VALID_BOUNDARY_LABELS:
            report.errors.append(f"rounds:line_{index}:invalid_boundary_label:{label}")
        split = row.get("split")
        if split:
            split_by_round.setdefault(str(row.get("round_id")), set()).add(str(split))

    for round_id, splits in split_by_round.items():
        if len(splits) > 1:
            report.errors.append(f"rounds:split_leakage:{round_id}:{sorted(splits)}")


def _validate_clock_labels(rows: list[dict[str, str]], report: ValidationReport) -> None:
    required = {"frame_id", "clock_crop_path", "clock_text", "visible", "quality", "label_status"}
    for index, row in enumerate(rows, start=2):
        _require_fields(row, required, report, f"clock_labels:line_{index}")
        quality = row.get("quality")
        if quality and quality not in VALID_CLOCK_QUALITIES:
            report.errors.append(f"clock_labels:line_{index}:invalid_quality:{quality}")
        visible = row.get("visible", "").lower()
        if visible not in {"true", "false"}:
            report.errors.append(f"clock_labels:line_{index}:invalid_visible:{visible}")
        if visible == "true" and not row.get("clock_text"):
            report.warnings.append(f"clock_labels:line_{index}:visible_without_clock_text")


def _validate_card_identity(rows: list[dict[str, str]], report: ValidationReport) -> None:
    required = {
        "crop_id",
        "frame_id",
        "zone",
        "slot",
        "card_crop_path",
        "rank",
        "suit",
        "visible",
        "quality",
        "label_status",
    }
    full_card_counts: dict[str, int] = {}
    for index, row in enumerate(rows, start=2):
        _require_fields(row, required, report, f"card_identity:line_{index}")
        rank = row.get("rank", "").upper()
        suit = row.get("suit", "").lower()
        zone = row.get("zone", "").upper()
        if rank and rank not in VALID_RANKS:
            report.errors.append(f"card_identity:line_{index}:invalid_rank:{rank}")
        if suit and suit not in VALID_SUITS:
            report.errors.append(f"card_identity:line_{index}:invalid_suit:{suit}")
        if zone and zone not in {"PLAYER", "BANKER"}:
            report.errors.append(f"card_identity:line_{index}:invalid_zone:{zone}")
        split = row.get("split")
        if split and split not in VALID_SPLITS:
            report.errors.append(f"card_identity:line_{index}:invalid_split:{split}")
        if rank and suit:
            key = f"{rank}-{suit}"
            full_card_counts[key] = full_card_counts.get(key, 0) + 1

    if full_card_counts:
        report.counts["card_identity_classes"] = len(full_card_counts)
        low_classes = sorted(card for card, count in full_card_counts.items() if count < 2)
        if low_classes:
            report.warnings.append(f"card_identity:low_class_counts:{','.join(low_classes[:20])}")


def _validate_frame_manifest(rows: list[dict[str, Any]], report: ValidationReport) -> None:
    required = {"frame_id", "table_id", "camera_id", "video_id", "frame_path", "width", "height", "split"}
    round_split: dict[str, set[str]] = {}
    for index, row in enumerate(rows, start=1):
        _require_fields(row, required, report, f"frames_manifest:line_{index}")
        split = row.get("split")
        if split and split not in VALID_SPLITS:
            report.errors.append(f"frames_manifest:line_{index}:invalid_split:{split}")
        round_id = row.get("round_id")
        if round_id and split:
            round_split.setdefault(str(round_id), set()).add(str(split))
    for round_id, splits in round_split.items():
        if len(splits) > 1:
            report.errors.append(f"frames_manifest:round_split_leakage:{round_id}:{sorted(splits)}")


def _validate_split_files(dataset: Path, report: ValidationReport) -> None:
    splits_dir = dataset / "splits"
    if not splits_dir.exists():
        report.warnings.append(f"missing_directory:{splits_dir}")
        return
    for split in ("train", "val", "test"):
        path = splits_dir / f"{split}.txt"
        if not path.exists():
            report.warnings.append(f"missing_file:{path}")


def _require_fields(
    row: dict[str, Any], required: set[str], report: ValidationReport, prefix: str
) -> None:
    for field_name in sorted(required):
        if field_name not in row or row[field_name] in (None, ""):
            report.errors.append(f"{prefix}:missing_field:{field_name}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate baccarat dataset annotations.")
    parser.add_argument("--dataset", required=True, help="Dataset version directory.")
    parser.add_argument("--output", help="Optional JSON report path.")
    args = parser.parse_args(argv)

    report = validate_dataset(Path(args.dataset))
    payload = report.to_dict()
    text = json.dumps(payload, indent=2, sort_keys=True)
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
