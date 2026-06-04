from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
import sys
from typing import Any


@dataclass(frozen=True)
class RoundLabel:
    round_id: str
    player_cards: tuple[str, ...]
    banker_cards: tuple[str, ...]
    winner: str | None


@dataclass(frozen=True)
class RoundPrediction:
    round_id: str
    player_cards: tuple[str, ...]
    banker_cards: tuple[str, ...]
    winner: str | None
    needs_review: bool


def evaluate_rounds(truth_path: Path, predictions_path: Path) -> dict[str, Any]:
    truth = {label.round_id: label for label in _read_truth(truth_path)}
    predictions = {prediction.round_id: prediction for prediction in _read_predictions(predictions_path)}

    matched_ids = sorted(set(truth) & set(predictions))
    false_positives = sorted(set(predictions) - set(truth))
    misses = sorted(set(truth) - set(predictions))

    player_card_correct = 0
    banker_card_correct = 0
    winner_correct = 0
    exact_round_correct = 0
    needs_review = 0

    for round_id in matched_ids:
        label = truth[round_id]
        prediction = predictions[round_id]
        player_ok = set(label.player_cards) == set(prediction.player_cards)
        banker_ok = set(label.banker_cards) == set(prediction.banker_cards)
        winner_ok = label.winner == prediction.winner
        player_card_correct += int(player_ok)
        banker_card_correct += int(banker_ok)
        winner_correct += int(winner_ok)
        exact_round_correct += int(player_ok and banker_ok and winner_ok)
        needs_review += int(prediction.needs_review)

    total_truth = len(truth)
    total_predictions = len(predictions)
    total_matched = len(matched_ids)

    return {
        "truth_rounds": total_truth,
        "predicted_rounds": total_predictions,
        "matched_rounds": total_matched,
        "missed_rounds": len(misses),
        "false_positive_rounds": len(false_positives),
        "round_recall": _ratio(total_matched, total_truth),
        "round_precision": _ratio(total_matched, total_predictions),
        "exact_round_accuracy": _ratio(exact_round_correct, total_matched),
        "player_card_set_accuracy": _ratio(player_card_correct, total_matched),
        "banker_card_set_accuracy": _ratio(banker_card_correct, total_matched),
        "winner_accuracy": _ratio(winner_correct, total_matched),
        "human_review_rate": _ratio(needs_review, total_predictions),
        "missed_round_ids": misses[:100],
        "false_positive_round_ids": false_positives[:100],
    }


def _read_truth(path: Path) -> list[RoundLabel]:
    rows = _read_jsonl(path)
    labels: list[RoundLabel] = []
    for row in rows:
        labels.append(
            RoundLabel(
                round_id=str(row["round_id"]),
                player_cards=_normalize_card_list(row.get("player_cards", [])),
                banker_cards=_normalize_card_list(row.get("banker_cards", [])),
                winner=_normalize_winner(row.get("winner")),
            )
        )
    return labels


def _read_predictions(path: Path) -> list[RoundPrediction]:
    rows = _read_jsonl(path)
    predictions: list[RoundPrediction] = []
    for row in rows:
        if row.get("event_type") and row.get("event_type") != "round.closed":
            continue
        validation = row.get("validation", {})
        predictions.append(
            RoundPrediction(
                round_id=str(row["round_id"]),
                player_cards=_normalize_event_cards(row.get("player_cards", [])),
                banker_cards=_normalize_event_cards(row.get("banker_cards", [])),
                winner=_normalize_winner(row.get("winner")),
                needs_review=bool(validation.get("needs_review", False)),
            )
        )
    return predictions


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def _normalize_event_cards(cards: list[Any]) -> tuple[str, ...]:
    normalized: list[str] = []
    for card in cards:
        if isinstance(card, dict):
            rank = str(card.get("rank", "")).upper()
            suit = _suit_code(str(card.get("suit", "")).lower())
            if rank and suit:
                normalized.append(f"{rank}{suit}")
        elif isinstance(card, str):
            normalized.append(card.upper())
    return tuple(sorted(normalized))


def _normalize_card_list(cards: list[Any]) -> tuple[str, ...]:
    normalized: list[str] = []
    for card in cards:
        if isinstance(card, str):
            normalized.append(card.upper())
        elif isinstance(card, dict):
            normalized.extend(_normalize_event_cards([card]))
    return tuple(sorted(normalized))


def _suit_code(suit: str) -> str:
    return {
        "clubs": "C",
        "diamonds": "D",
        "hearts": "H",
        "spades": "S",
        "c": "C",
        "d": "D",
        "h": "H",
        "s": "S",
    }.get(suit, "")


def _normalize_winner(winner: Any) -> str | None:
    return str(winner).upper() if winner else None


def _ratio(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return round(numerator / denominator, 6)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate round.closed predictions against labels.")
    parser.add_argument("--truth", required=True, help="Ground-truth rounds.jsonl.")
    parser.add_argument("--predictions", required=True, help="Predicted round events JSONL.")
    parser.add_argument("--output", help="Optional JSON report path.")
    args = parser.parse_args(argv)

    metrics = evaluate_rounds(Path(args.truth), Path(args.predictions))
    text = json.dumps(metrics, indent=2, sort_keys=True)
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
