# Datasets

Large videos, frames, crops, labels, model runs, and reports are intentionally not committed.

Create immutable dataset versions under this directory, for example:

```text
datasets/baccarat_v1/
```

Each release should include `dataset.yaml`, annotation files, manifests, train/validation/test splits, and an annotation QA report.

Use session/day/table-level splits. Do not split adjacent frames from the same round across train, validation, and test.
