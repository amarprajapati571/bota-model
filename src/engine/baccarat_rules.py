from __future__ import annotations

from dataclasses import dataclass

from src.api.schemas import CardObservation, ValidationResult, Winner


RANK_POINTS = {
    "A": 1,
    "2": 2,
    "3": 3,
    "4": 4,
    "5": 5,
    "6": 6,
    "7": 7,
    "8": 8,
    "9": 9,
    "10": 0,
    "J": 0,
    "Q": 0,
    "K": 0,
}


@dataclass(frozen=True)
class HandOutcome:
    player_total: int
    banker_total: int
    winner: Winner


def card_value(card: CardObservation | str) -> int:
    rank = card.rank if isinstance(card, CardObservation) else card
    if rank is None:
        raise ValueError("Cannot score a card without a rank.")
    normalized = rank.upper()
    if normalized not in RANK_POINTS:
        raise ValueError(f"Unknown baccarat rank: {rank}")
    return RANK_POINTS[normalized]


def hand_total(cards: list[CardObservation] | tuple[CardObservation, ...]) -> int:
    return sum(card_value(card) for card in cards) % 10


def score_hands(
    player_cards: tuple[CardObservation, ...], banker_cards: tuple[CardObservation, ...]
) -> HandOutcome:
    player_total = hand_total(player_cards)
    banker_total = hand_total(banker_cards)
    if player_total > banker_total:
        winner = Winner.PLAYER
    elif banker_total > player_total:
        winner = Winner.BANKER
    else:
        winner = Winner.TIE
    return HandOutcome(player_total, banker_total, winner)


def validate_round_cards(
    player_cards: tuple[CardObservation, ...],
    banker_cards: tuple[CardObservation, ...],
    clock_boundary_valid: bool = True,
) -> ValidationResult:
    warnings: list[str] = []
    card_count_valid = 2 <= len(player_cards) <= 3 and 2 <= len(banker_cards) <= 3
    if not card_count_valid:
        warnings.append("invalid_card_count")

    ranks_known = all(card.rank for card in player_cards + banker_cards)
    if not ranks_known:
        warnings.append("missing_rank")

    rules_valid = False
    if card_count_valid and ranks_known:
        rules_valid = _drawing_rules_valid(player_cards, banker_cards)
        if not rules_valid:
            warnings.append("baccarat_drawing_rules_failed")

    if not clock_boundary_valid:
        warnings.append("clock_boundary_unconfirmed")

    return ValidationResult(
        baccarat_rules_valid=rules_valid,
        card_count_valid=card_count_valid,
        clock_boundary_valid=clock_boundary_valid,
        needs_review=bool(warnings),
        warnings=tuple(warnings),
    )


def _drawing_rules_valid(
    player_cards: tuple[CardObservation, ...], banker_cards: tuple[CardObservation, ...]
) -> bool:
    player_initial = hand_total(player_cards[:2])
    banker_initial = hand_total(banker_cards[:2])
    player_count = len(player_cards)
    banker_count = len(banker_cards)

    if player_initial in (8, 9) or banker_initial in (8, 9):
        return player_count == 2 and banker_count == 2

    player_should_draw = player_initial <= 5
    if player_should_draw and player_count != 3:
        return False
    if not player_should_draw and player_count != 2:
        return False

    if not player_should_draw:
        banker_should_draw = banker_initial <= 5
    else:
        player_third = card_value(player_cards[2])
        banker_should_draw = _banker_draws_after_player_third(banker_initial, player_third)

    expected_banker_count = 3 if banker_should_draw else 2
    return banker_count == expected_banker_count


def _banker_draws_after_player_third(banker_initial: int, player_third_value: int) -> bool:
    if banker_initial in (0, 1, 2):
        return True
    if banker_initial == 3:
        return player_third_value != 8
    if banker_initial == 4:
        return 2 <= player_third_value <= 7
    if banker_initial == 5:
        return 4 <= player_third_value <= 7
    if banker_initial == 6:
        return 6 <= player_third_value <= 7
    return False
