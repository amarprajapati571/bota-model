# Baccarat Video Extractor

Production-oriented starter service for detecting baccarat rounds from authorized live video streams.

This repository implements the rules, state, schemas, and orchestration seams described in the attached system design. The computer-vision pieces are intentionally interfaces/stubs so real OCR, detection, and classification models can be integrated without changing the round engine.

## What Is Included

- Clock parsing and minute-boundary smoothing.
- Baccarat point totals, winner calculation, and drawing-rule validation.
- Temporal card-slot voting with lock/contradiction handling.
- Round state machine that emits `round.started`, `round.closed`, and review events.
- Typed event dataclasses that serialize to JSON-friendly dictionaries.
- Standard-library test suite.
- Example production and staging configuration.
- A small replay CLI for JSONL frame observations.

## Quick Start

```bash
python3 -m unittest discover -s tests
python3 -m src.cli.replay --input examples/sample_observations.jsonl
npm test --prefix frontend
```

The replay command reads frame observations from JSON Lines and prints emitted events.

Start the static operator dashboard:

```bash
python3 -m http.server 4173 -d frontend
```

Then open `http://localhost:4173`.

## Training Workflow

Training guidance lives in [docs/training.md](/Users/amarprajapat/Documents/bota-model/docs/training.md:1). The repo now includes config templates for clock OCR, card detection, card classification, and state-machine threshold tuning under `configs/training/`.

Validate a frozen dataset release before training:

```bash
python3 -m src.data.validate_annotations \
  --dataset datasets/baccarat_v1 \
  --output reports/annotation_quality_v1.json
```

Evaluate end-to-end `round.closed` replay output against round labels:

```bash
python3 -m src.evaluation.eval_rounds \
  --truth datasets/baccarat_v1/annotations/rounds.jsonl \
  --predictions reports/e2e_replay_v1.jsonl \
  --output reports/e2e_metrics_v1.json
```

Large raw videos, extracted frames, crops, runs, and reports are ignored by git; keep only versioned metadata, configs, code, and lightweight templates in source control.

## Frontend Dashboard

Frontend streaming guidance lives in [docs/frontend.md](/Users/amarprajapat/Documents/bota-model/docs/frontend.md:1). The static dashboard in `frontend/` shows a live table surface, normalized ROI/card overlays, stream health, clock OCR, Player/Banker cards, winner, confidence, recent rounds, and review alerts using mock WebSocket-style events.

Production integration points:

- Replace mock session data with `GET /api/v1/tables/{table_id}/live-session`.
- Feed WebSocket events into `applyLiveEvent`.
- Use signed WebRTC/HLS playback URLs only.

## Repository Layout

```text
configs/
  prod/md3212.yaml
  staging/md3212.yaml
docs/
  architecture.md
frontend/
  index.html
  src/
examples/
  sample_observations.jsonl
src/
  api/
  cli/
  engine/
  ingest/
  layout/
  models/
  monitoring/
  publishing/
  storage/
tests/
```

## Event Contract

Frame observations are ingested as dictionaries with the core fields below:

```json
{
  "table_id": "MD3212",
  "camera_id": "cam-01",
  "frame_id": "MD3212-000001",
  "server_ts_utc": "2026-01-01T18:43:00.100Z",
  "stream_pts_ms": 100,
  "clock": {"text_raw": "18:43:00", "confidence": 0.98, "status": "valid"},
  "cards": [],
  "frame_quality": {"quality_status": "good"}
}
```

Final round events include locked cards, totals, winner, validation warnings, confidence, and review status.

## Important Limits

- Use only video streams you are authorized to process.
- This repo does not ship trained OCR or card-recognition models.
- Baccarat rules validate consistency; they do not overwrite visual evidence.
- Low-confidence or inconsistent rounds should go to human review.
