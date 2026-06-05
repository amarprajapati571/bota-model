import test from "node:test";
import assert from "node:assert/strict";

import { buildCardCode, cardCodeToViewModel, formatCard, mapDetectedCard } from "../src/cards.js";

test("formats card codes with suit symbols", () => {
  assert.equal(formatCard("5H"), "5♥");
  assert.equal(formatCard("10S"), "10♠");
});

test("builds card code from rank and suit", () => {
  assert.equal(buildCardCode("Q", "diamonds"), "QD");
});

test("maps detected card confidence as the weakest component", () => {
  const card = mapDetectedCard("BANKER", {
    slot: 2,
    rank: "7",
    suit: "diamonds",
    det_confidence: 0.96,
    rank_confidence: 0.94,
    suit_confidence: 0.61,
    stable: false,
  });
  assert.equal(card.cardCode, "7D");
  assert.equal(card.confidence, 0.61);
  assert.equal(card.stable, false);
});

test("maps box-only detected card confidence from detector confidence", () => {
  const card = mapDetectedCard("PLAYER", {
    slot: 1,
    bbox_norm: { x1: 0.1, y1: 0.1, x2: 0.2, y2: 0.2 },
    det_confidence: 0.82,
    rank_confidence: 0,
    suit_confidence: 0,
    stable: false,
  });
  assert.equal(card.cardCode, null);
  assert.equal(card.confidence, 0.82);
});

test("cardCodeToViewModel creates locked final cards", () => {
  const card = cardCodeToViewModel("PLAYER", 1, "AH");
  assert.equal(card.rank, "A");
  assert.equal(card.suit, "H");
  assert.equal(card.stable, true);
});
