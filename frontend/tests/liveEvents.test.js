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
