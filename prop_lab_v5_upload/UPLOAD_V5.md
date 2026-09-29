# Parlay Lab V5 — upload notes

Upload/replace the files in this repo while preserving their paths.

Changed files:
- `docs/index.html` — new main GitHub Pages homepage (Parlay Lab V5)
- `docs/ledger.html` — existing public Eevee ledger, now generated here instead of `index.html`
- `docs/internal.html` — regenerated H1–H4 lab
- `report.py` — writes `ledger.html` + `internal.html`; no longer overwrites the homepage
- `common.py` — version bumped to `2026-09-29-parlay-v5`
- `run.py` — comment updated for the new page layout
- `README.md` — documents the new page routes

Do not delete or replace the `data/` directory. No changes are required to `.github/workflows/lab.yml`, `snapshot.py`, `close.py`, or `slips.py`.

After upload:
1. Open the GitHub Pages root and confirm Parlay Lab V5 loads.
2. Open `/ledger.html` and `/internal.html`.
3. Run the GitHub Action manually once (or run `python3 report.py`).
4. Confirm the root `index.html` is still Parlay Lab V5 after the run.
5. Confirm `ledger.html` and `internal.html` show code version `2026-09-29-parlay-v5`.

Important: V5 is currently a historical research cockpit. Its V1/V2 model metrics are embedded prototype values. Live parlay model generation and actual cross-book ticket-quote capture are the next phase.
