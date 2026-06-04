const SUIT_SYMBOLS = {
  H: "♥",
  D: "♦",
  C: "♣",
  S: "♠",
  hearts: "♥",
  diamonds: "♦",
  clubs: "♣",
  spades: "♠",
};

const SUIT_CODES = {
  hearts: "H",
  diamonds: "D",
  clubs: "C",
  spades: "S",
};

export function cardCodeToViewModel(zone, slot, cardCode) {
  const code = String(cardCode || "").toUpperCase();
  const suit = code.slice(-1);
  const rank = code.slice(0, -1);
  return {
    zone,
    slot,
    rank: rank || null,
    suit: suit || null,
    cardCode: code || null,
    bboxNorm: null,
    confidence: 1,
    stable: true,
  };
}

export function mapDetectedCard(zone, card) {
  const confidence = Math.min(
    card.det_confidence ?? 0,
    card.rank_confidence ?? 0,
    card.suit_confidence ?? 0,
  );
  return {
    zone,
    slot: Number(card.slot),
    rank: card.rank ?? null,
    suit: card.suit ?? null,
    cardCode: card.card_code ?? buildCardCode(card.rank, card.suit),
    bboxNorm: card.bbox_norm ?? null,
    confidence,
    stable: Boolean(card.stable),
  };
}

export function buildCardCode(rank, suit) {
  if (!rank || !suit) return null;
  const code = SUIT_CODES[String(suit).toLowerCase()] ?? String(suit).toUpperCase().slice(0, 1);
  return `${String(rank).toUpperCase()}${code}`;
}

export function formatCard(code) {
  if (!code) return "?";
  const normalized = String(code).toUpperCase();
  const suit = normalized.slice(-1);
  const rank = normalized.slice(0, -1);
  return `${rank}${SUIT_SYMBOLS[suit] ?? suit}`;
}
