from __future__ import annotations

from statistics import mean

from src.api.schemas import CardObservation, FrameQuality, ValidationResult


def score_round_confidence(
    clock_confidence: float,
    player_cards: tuple[CardObservation, ...],
    banker_cards: tuple[CardObservation, ...],
    validation: ValidationResult,
    frame_quality: FrameQuality,
    layout_confidence: float = 1.0,
    temporal_stability_confidence: float = 1.0,
) -> float:
    card_confidences = [card.confidence for card in player_cards + banker_cards]
    card_score = mean(card_confidences) if card_confidences else 0.0
    rules_score = 1.0 if validation.baccarat_rules_valid else 0.55
    quality_score = 1.0 if frame_quality.is_usable else 0.35
    weighted = (
        0.20 * clock_confidence
        + 0.30 * card_score
        + 0.20 * temporal_stability_confidence
        + 0.15 * rules_score
        + 0.10 * quality_score
        + 0.05 * layout_confidence
    )
    return round(max(0.0, min(weighted, 1.0)), 4)
