# S3 True Correlation Research Checkpoint

This folder is intended to be committed under:

`research/s3_true_correlation/`

It preserves the 2026-09-30 S3 research checkpoint without activating the model.

## Reproduce the historical correlation study

1. Download nflverse weekly stats:
   `python3 download_nflverse.py`

2. Run the S3 research engine using 2021–2024 train and 2025 validation.

3. Recompute the residual-based position/archetype priors with:
   `python3 recompute_s3_priors.py`

The large nflverse source CSVs are intentionally excluded from GitHub.

## Tests
From this folder:
`python3 -m pytest -q`

Expected checkpoint result: `4 passed`.

## Important
This checkpoint is **not wired into `run.py`, `parlay_lab.py`, the main dashboard, or Telegram**.
See `FORWARD_TEST_PLAN.md` for the next integration phase.
