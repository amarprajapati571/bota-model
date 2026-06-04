# Training Pipeline

This project should be trained as several specialized models plus deterministic round logic:

- Clock OCR for the visible timer.
- Card detector for Player and Banker card boxes.
- Rank/suit classifier for card identity.
- Optional table-state classifier for boundary support.
- Temporal voting, baccarat validation, and confidence policy for round output.

The production gate is round-level correctness on unseen replay videos, not isolated component accuracy.

## Dataset Workflow

1. Collect only authorized videos or streams.
2. Freeze a versioned dataset folder such as `datasets/baccarat_v1`.
3. Split by session, day, dealer, or table, not by adjacent frames.
4. Label round boundaries, clock text, card boxes, card identity, quality, and occlusion.
5. Run annotation QA before training.
6. Train components independently.
7. Tune state-machine thresholds on validation videos only.
8. Run one final locked test replay.
9. Export, package, register, and shadow-deploy.

## Dataset Layout

```text
datasets/
  baccarat_v1/
    README.md
    dataset.yaml
    raw_videos/
    frames/
    crops/
      clock/
      player_cards/
      banker_cards/
      card_corners/
    annotations/
      rounds.jsonl
      clock_labels.csv
      card_identity.csv
      table_state.csv
      card_detections_yolo/
        images/train/
        images/val/
        images/test/
        labels/train/
        labels/val/
        labels/test/
    splits/
      train.txt
      val.txt
      test.txt
    manifests/
      frames_manifest.jsonl
      clips_manifest.jsonl
      annotation_quality_report.json
```

## QA Command

```bash
python3 -m src.data.validate_annotations \
  --dataset datasets/baccarat_v1 \
  --output reports/annotation_quality_v1.json
```

The validator checks required files, required columns, JSONL shape, card ranks/suits, split leakage by round, duplicate IDs, and common label-quality mistakes.

## Round Evaluation Command

```bash
python3 -m src.evaluation.eval_rounds \
  --truth datasets/baccarat_v1/annotations/rounds.jsonl \
  --predictions reports/e2e_replay_v1.jsonl \
  --output reports/e2e_metrics_v1.json
```

Predictions should be `round.closed` event JSON lines from the replay pipeline.

## Promotion Gates

Initial production gates:

- Round recall `>= 99.0%`.
- Round precision `>= 99.0%`.
- Winner accuracy `>= 99.5%`.
- Player card-set accuracy `>= 99.0%`.
- Banker card-set accuracy `>= 99.0%`.
- False finalization rate `<= 0.2%`.
- Human review rate `<= 2.0%` after tuning.
- P95 end-to-end inference latency `<= 500ms` per processed frame.

If the gates fail, mine errors, label the failure buckets, retrain, and replay again.
