# Consolidated SGP Shadow Runner Upload

This is the complete current non-data patch for prop-lab as of 2026-09-30.

## Upload
Unzip this package. Upload/replace its contents at the repository root, preserving folders.

This bundle includes all current code and dashboard changes required for:
- cross-game V1-V8 forward research,
- SGP shadow S0/S1/S2/S3-A:E,
- verified-team S3 correlation research,
- actual PropLine /sgp shadow quotes,
- frozen pre-kickoff SGP decisions,
- rejection audit and paper settlement,
- historical SGP development replay,
- horizontal V1-V8 selector and collapsible SGP Model > Development/Forward > Week > Date > Game > Slip history.

## Intentionally excluded
Do NOT replace your live `data/` directory. This ZIP contains no live CSV state.
The GitHub workflow is unchanged and is not included.
Raw nflverse 2021-2025 source CSVs are intentionally excluded; the small reproducible S3 research outputs are included.

## After upload
1. Commit all uploaded files to `main`.
2. Verify `common.py` contains `LAB_VERSION = "2026-09-30-sgp-shadow-v3-history"`.
3. Run Actions > eevee-tick > Run workflow once.
4. Confirm the main dashboard loads and the legacy ledger/internal pages still load.
5. On an eligible game day, the SGP shadow runner will create/update its own `data/sgp_shadow_*.csv` files automatically.

## Safety / separation
The SGP family is shadow/paper research only. It does not place bets and does not alter V1-V8, H1-H4, or legacy slips records.
