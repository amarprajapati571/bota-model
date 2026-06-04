from __future__ import annotations

import unittest

from src.api.schemas import CardObservation, Side, Winner
from src.engine.baccarat_rules import hand_total, score_hands, validate_round_cards


def card(side: Side, slot: str, rank: str) -> CardObservation:
    return CardObservation(side, slot, rank, "hearts", 0.99)


class BaccaratRulesTests(unittest.TestCase):
    def test_hand_total_uses_modulo_ten(self) -> None:
        cards = (card(Side.PLAYER, "P1", "9"), card(Side.PLAYER, "P2", "8"))
        self.assertEqual(hand_total(cards), 7)

    def test_winner_calculation(self) -> None:
        player = (card(Side.PLAYER, "P1", "5"), card(Side.PLAYER, "P2", "9"))
        banker = (card(Side.BANKER, "B1", "7"), card(Side.BANKER, "B2", "7"))
        outcome = score_hands(player, banker)
        self.assertEqual(outcome.winner, Winner.TIE)

    def test_natural_stands(self) -> None:
        player = (card(Side.PLAYER, "P1", "8"), card(Side.PLAYER, "P2", "K"))
        banker = (card(Side.BANKER, "B1", "7"), card(Side.BANKER, "B2", "Q"))
        result = validate_round_cards(player, banker)
        self.assertTrue(result.baccarat_rules_valid)

    def test_flags_invalid_third_card_after_natural(self) -> None:
        player = (
            card(Side.PLAYER, "P1", "8"),
            card(Side.PLAYER, "P2", "K"),
            card(Side.PLAYER, "P3", "2"),
        )
        banker = (card(Side.BANKER, "B1", "7"), card(Side.BANKER, "B2", "Q"))
        result = validate_round_cards(player, banker)
        self.assertFalse(result.baccarat_rules_valid)
        self.assertTrue(result.needs_review)

    def test_banker_draw_rule_after_player_third_card(self) -> None:
        player = (
            card(Side.PLAYER, "P1", "2"),
            card(Side.PLAYER, "P2", "3"),
            card(Side.PLAYER, "P3", "6"),
        )
        banker = (
            card(Side.BANKER, "B1", "3"),
            card(Side.BANKER, "B2", "2"),
            card(Side.BANKER, "B3", "A"),
        )
        self.assertTrue(validate_round_cards(player, banker).baccarat_rules_valid)


if __name__ == "__main__":
    unittest.main()
