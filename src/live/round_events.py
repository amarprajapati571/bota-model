from __future__ import annotations

from typing import Any

from src.api.schemas import CardObservation, RoundEvent
from src.live.events import make_event


ENGINE_TO_FRONTEND_STATE = {
    "round.started": "BETTING_OPEN",
    "round.closed": "RESULT_CONFIRMED",
    "round.review": "ERROR_REVIEW",
}


def round_state_event(
    table_id: str,
    stream_id: str,
    sequence_number: int,
    *,
    round_id: str | None,
    state: str,
    confidence: float,
    reason: str,
    timer_visibility: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "state": state,
        "state_confidence": confidence,
        "reason": reason,
    }
    if timer_visibility is not None:
        payload["timer_visibility"] = timer_visibility
    return make_event(
        "round.state",
        table_id,
        stream_id,
        sequence_number,
        payload,
        round_id=round_id,
    )


def clock_tick_event(
    table_id: str,
    stream_id: str,
    sequence_number: int,
    payload: dict[str, Any],
    *,
    frame_id: str | None = None,
) -> dict[str, Any]:
    return make_event("clock.tick", table_id, stream_id, sequence_number, payload, frame_id=frame_id)


def cards_detected_event(
    table_id: str,
    stream_id: str,
    sequence_number: int,
    payload: dict[str, Any],
    *,
    frame_id: str | None = None,
    round_id: str | None = None,
) -> dict[str, Any]:
    return make_event(
        "cards.detected",
        table_id,
        stream_id,
        sequence_number,
        payload,
        frame_id=frame_id,
        round_id=round_id,
    )


def frontend_event_from_round_event(
    event: RoundEvent,
    table_id: str,
    stream_id: str,
    sequence_number: int,
) -> dict[str, Any]:
    if event.event_type == "round.closed":
        return make_event(
            "round.final",
            table_id,
            stream_id,
            sequence_number,
            {
                "start_time": event.started_at_utc.isoformat().replace("+00:00", "Z"),
                "end_time": event.ended_at_utc.isoformat().replace("+00:00", "Z")
                if event.ended_at_utc
                else None,
                "player_cards": [_card_code(card) for card in event.player_cards],
                "banker_cards": [_card_code(card) for card in event.banker_cards],
                "player_total": event.player_total,
                "banker_total": event.banker_total,
                "winner": event.winner.value if event.winner else None,
                "overall_confidence": event.round_confidence,
                "needs_review": event.validation.needs_review,
                "validation": event.validation.to_dict(),
            },
            round_id=event.round_id,
        )

    state = ENGINE_TO_FRONTEND_STATE.get(event.event_type, "WAITING_FOR_ROUND")
    return round_state_event(
        table_id,
        stream_id,
        sequence_number,
        round_id=event.round_id,
        state=state,
        confidence=event.round_confidence,
        reason=event.event_type,
    )


def _card_code(card: CardObservation) -> str:
    suit = {
        "clubs": "C",
        "diamonds": "D",
        "hearts": "H",
        "spades": "S",
    }.get(str(card.suit).lower(), str(card.suit or "").upper()[:1])
    return f"{str(card.rank).upper()}{suit}"
