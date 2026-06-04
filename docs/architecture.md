# Architecture

The service is deliberately split into small stages:

1. Stream ingestion decodes authorized video and emits timestamped frames.
2. Frame quality gates reject frozen, black, blurred, or stale frames.
3. Layout calibration crops the clock, Player area, Banker area, and optional slot priors.
4. Clock OCR parses a visible clock and smooths observations across frames.
5. Card detection and rank/suit classification produce frame-level card observations.
6. Temporal tracking votes across recent frames and locks stable card slots.
7. The round state machine combines clock boundaries, visual state, and timeouts.
8. Baccarat validation checks whether the locked card count and drawing behavior are plausible.
9. Event publishing and storage persist structured output and evidence references.

## Production Rules

- Never trust a single frame.
- Never trust OCR without temporal validation.
- Never emit duplicate final events for one round.
- Never silently overwrite model output with baccarat rules.
- Always include evidence and model/layout versions in final events.
- Route uncertainty to review instead of guessing.

## Model Integration

The interfaces in `src/models/` are intentionally narrow:

- `ClockOCR.predict(crop)` returns a `ClockObservation`.
- `CardDetector.detect(crop)` returns card boxes.
- `CardClassifier.predict(crop)` returns rank, suit, confidence, and visibility.

Production implementations can call ONNX Runtime, TensorRT, Triton, PyTorch, or a remote model server behind these interfaces.
