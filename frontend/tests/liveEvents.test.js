import test from "node:test";
import assert from "node:assert/strict";

import { applyLiveEvent, initialState } from "../src/liveEvents.js";
import { buildMockEvents } from "../src/mockSession.js";

test("applies cards.detected to live state", () => {
  const event = buildMockEvents(1000).find((item) => item.event_type === "cards.detected");
  const state = applyLiveEvent({ ...initialState, seenEventIds: new Set() }, event);
  assert.equal(state.playerCards.length, 2);
  assert.equal(state.bankerCards[1].cardCode, "7D");
  assert.equal(state.overallConfidence, 0.95);
});

test("round.final updates recent rounds and totals", () => {
  const event = buildMockEvents(1000).find((item) => item.event_type === "round.final");
  const state = applyLiveEvent({ ...initialState, seenEventIds: new Set() }, event);
  assert.equal(state.roundState, "ROUND_FINALIZED");
  assert.equal(state.playerTotal, 4);
  assert.equal(state.bankerTotal, 4);
  assert.equal(state.recentRounds.length, 1);
});

test("deduplicates event ids and ignores older sequence numbers", () => {
  const event = buildMockEvents(1000)[0];
  const first = applyLiveEvent({ ...initialState, seenEventIds: new Set() }, event);
  const duplicate = applyLiveEvent(first, event);
  assert.equal(duplicate, first);

  const older = applyLiveEvent(first, { ...event, event_id: "newer-id", sequence_number: 0 });
  assert.equal(older, first);
});

test("review.required marks review state", () => {
  const event = buildMockEvents(1000).find((item) => item.event_type === "review.required");
  const state = applyLiveEvent({ ...initialState, seenEventIds: new Set() }, event);
  assert.equal(state.needsReview, true);
  assert.equal(state.roundState, "ERROR_REVIEW");
});

test("holds card slots through a transient empty detection frame", () => {
  const event = buildMockEvents(1000).find((item) => item.event_type === "cards.detected");
  const first = applyLiveEvent({ ...initialState, seenEventIds: new Set() }, event);
  const empty = applyLiveEvent(first, {
    ...event,
    event_id: "empty-cards",
    sequence_number: event.sequence_number + 1,
    wall_time_ms: event.wall_time_ms + 500,
    payload: {
      player_cards: [],
      banker_cards: [],
      overall_confidence: 0,
    },
  });

  assert.equal(empty.playerCards.length, 2);
  assert.equal(empty.bankerCards.length, 2);
  assert.equal(empty.playerCards[0].stable, false);
});

test("round reset clears stale cards totals and winner", () => {
  const finalEvent = buildMockEvents(1000).find((item) => item.event_type === "round.final");
  const finalized = applyLiveEvent({ ...initialState, seenEventIds: new Set() }, finalEvent);
  const reset = applyLiveEvent(finalized, {
    event_id: "reset-state",
    event_type: "round.state",
    sequence_number: finalEvent.sequence_number + 1,
    wall_time_ms: finalEvent.wall_time_ms + 1000,
    round_id: null,
    payload: {
      state: "RESET",
      state_confidence: 0.9,
    },
  });

  assert.equal(reset.roundState, "RESET");
  assert.equal(reset.playerCards.length, 0);
  assert.equal(reset.bankerTotal, null);
  assert.equal(reset.winner, null);
});
