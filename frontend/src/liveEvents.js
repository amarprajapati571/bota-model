import { cardCodeToViewModel, mapDetectedCard } from "./cards.js";

export const initialState = {
  tableId: "MD3212",
  streamId: "stream_MD3212_live",
  streamStatus: "connecting",
  videoLatencyMs: null,
  mlLatencyMs: null,
  roundId: null,
  roundState: "WAITING_FOR_ROUND",
  clockText: null,
  clockConfidence: null,
  playerCards: [],
  bankerCards: [],
  playerTotal: null,
  bankerTotal: null,
  winner: null,
  overallConfidence: null,
  needsReview: false,
  reviewReason: null,
  lastSequenceNumber: 0,
  lastEventAtMs: Date.now(),
  recentRounds: [],
  eventLog: [],
  seenEventIds: new Set(),
};

const FINAL_STATES = new Set(["ROUND_FINALIZED", "ERROR_REVIEW"]);

export function applyLiveEvent(state, event) {
  if (event.event_id && state.seenEventIds.has(event.event_id)) {
    return state;
  }
  if (
    typeof event.sequence_number === "number" &&
    event.sequence_number <= state.lastSequenceNumber
  ) {
    return state;
  }

  const base = withEventBookkeeping(state, event);
  switch (event.event_type) {
    case "stream.health":
      return {
        ...base,
        streamStatus: event.payload.status,
        videoLatencyMs: event.payload.video_latency_ms,
        mlLatencyMs: event.payload.ml_latency_ms,
      };

    case "clock.tick":
      return {
        ...base,
        clockText: event.payload.clock_text,
        clockConfidence: event.payload.confidence,
      };

    case "round.state":
      if (FINAL_STATES.has(state.roundState) && event.round_id === state.roundId) {
        return base;
      }
      return {
        ...base,
        roundId: event.round_id ?? state.roundId,
        roundState: event.payload.state,
        overallConfidence: event.payload.state_confidence,
      };

    case "cards.detected":
      return {
        ...base,
        roundId: event.round_id ?? state.roundId,
        playerCards: (event.payload.player_cards ?? []).map((card) =>
          mapDetectedCard("PLAYER", card),
        ),
        bankerCards: (event.payload.banker_cards ?? []).map((card) =>
          mapDetectedCard("BANKER", card),
        ),
        overallConfidence: event.payload.overall_confidence,
      };

    case "round.final": {
      const finalRound = {
        roundId: event.round_id,
        time: compactTime(event.payload.end_time ?? event.created_at),
        playerCards: event.payload.player_cards ?? [],
        bankerCards: event.payload.banker_cards ?? [],
        playerTotal: event.payload.player_total,
        bankerTotal: event.payload.banker_total,
        winner: event.payload.winner,
        confidence: event.payload.overall_confidence,
        needsReview: Boolean(event.payload.needs_review),
      };
      return {
        ...base,
        roundId: event.round_id ?? state.roundId,
        roundState: "ROUND_FINALIZED",
        playerCards: finalRound.playerCards.map((code, index) =>
          cardCodeToViewModel("PLAYER", index + 1, code),
        ),
        bankerCards: finalRound.bankerCards.map((code, index) =>
          cardCodeToViewModel("BANKER", index + 1, code),
        ),
        playerTotal: finalRound.playerTotal,
        bankerTotal: finalRound.bankerTotal,
        winner: finalRound.winner,
        overallConfidence: finalRound.confidence,
        needsReview: finalRound.needsReview,
        reviewReason: finalRound.needsReview ? "Final round requires review" : null,
        recentRounds: [finalRound, ...state.recentRounds].slice(0, 12),
      };
    }

    case "review.required":
      return {
        ...base,
        roundId: event.round_id ?? state.roundId,
        needsReview: true,
        reviewReason: event.payload.message,
        roundState: "ERROR_REVIEW",
      };

    default:
      return base;
  }
}

function withEventBookkeeping(state, event) {
  const seenEventIds = new Set(state.seenEventIds);
  if (event.event_id) seenEventIds.add(event.event_id);
  return {
    ...state,
    seenEventIds,
    lastSequenceNumber: event.sequence_number ?? state.lastSequenceNumber,
    lastEventAtMs: event.wall_time_ms ?? Date.now(),
    eventLog: [`${event.sequence_number ?? "-"} ${event.event_type}`, ...state.eventLog].slice(0, 18),
  };
}

function compactTime(value) {
  if (!value) return "--:--";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value).slice(11, 16);
  return date.toISOString().slice(11, 16);
}
