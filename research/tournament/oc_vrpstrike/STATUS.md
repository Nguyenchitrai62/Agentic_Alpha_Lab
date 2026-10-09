# oc_vrpstrike STATUS (run on what is complete 2026-10-07 ~11:00 UTC)

## Complete months USED (strictly manifest-listed)

- BTC forward (`deribit_strike_20261007/BTC`, 28): 2021-01..2022-12,
  2023-01, 2023-02, 2023-03, 2025-06.
- BTC backward (`deribit_strike_20261007_b/BTC`, 9): 2026-01..2026-09.
- ETH forward (`deribit_strike_20261007/ETH`, manifest lists 3 as complete):
  2021-06, 2023-03, 2025-06. NOTE: 27 parquet files exist on disk but only
  these 3 are manifest-complete; the other 24 were NOT used (fetchers still
  running; unlisted files may be partial downloads).
- ETH backward (`deribit_strike_20261007_b/ETH`, 12): 2025-10..2026-09.
- Overlap months present complete in BOTH folders: NONE for either coin, so
  no dedupe decision was needed (code path asserted + logged; zero identical
  overlap rows encountered).

## Coverage consequence (all anchor years PARTIAL, pre-registered rule)

- 2021-09-24: 51 coin-weeks traded (all BTC; ETH entry months missing).
- 2022-09-24: 22 coin-weeks (20 BTC incl. new 2023-01/02/03 + 2 ETH Mar-2023).
- 2023-09-24: 0 coin-weeks (no complete months in range).
- 2024-09-24: 4 coin-weeks (June-2025 only, 2 BTC + 2 ETH).
- 2025-09-24 (recent, scored once): 57 coin-weeks (24 BTC + 33 ETH).
- Skips over 520 Friday coin-weeks: data-gap 344, low-volume 38
  (entry window < 0.1 coin/leg), no-pair 3, no-vol/no-price 0. 1m lookups:
  0 inexact. Full inventory: `tmp/inventory.json`.

## Repro

`.venv/Scripts/python.exe scripts/heavy_slot.py run --tag <t> --min-free-gb 2.0 -- .venv/Scripts/python.exe research/tournament/oc_vrpstrike/run_strike.py {inventory|dev|final}`
G2 f=0 reproduces `v421_result.json` (R2B1D17BFG2 yearly R/DD, 5y R/W/DD,
full_path_dd) to the digit (asserted in-script). Leader: re-dispatch `dev`
+ `final` when the fetch finishes to extend coverage; rule frozen, no refit.
