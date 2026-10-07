# Shared engine protocol for the 2026-10-07 literature book-gate tests (read with your own assignment)

- Specs come from docs/opencode/IDEAS4_20261007.md section C (read your items H# there fully; use EXACTLY the variants listed, no others).
- Engine: copy the per-(T, sym) book-multiplier mechanism of research/parallel/rounds/parallel-20260906-r2/v426/v426_book_brake.py (multiplier
  on STANDARD book rows after the bear filter, before the shifted-clock forward fill) on top of G2 (v421 RUNS: rule inv, k 1.0, kd 1.7,
  bear True, G 2.0). Reproduce G2 (5.41 / W 2.588 / DD 16.91 / full 16.82, yearly rows) to the digit first, else stop. 4-phase engine runs via
  `scripts/heavy_slot.py run --tag <your tag> --min-free-gb 2.0 -- ...`; one phase per process is fine; keep RAM < 2.5 GB.
- Every variant gets an EXPOSURE-MATCHED CONTROL: a constant per-year multiplier equal to that variant's realised mean multiplier on the
  affected side (longs / shorts) - the variant must beat its control to claim timing value (methodology lesson 3, docs/CLOSED_DIRECTIONS.md).
- Selection ONLY on dev4 (2021-09-24 .. 2025-09-23) with the robust criterion vs G2: candidate iff dev4 mean > G2's 5.601 AND dev4 worst year >
  G2's 2.588 AND max yearly DD <= 16.91 + 0.5 AND beats its control on dev4 mean. Score the most recent year ONCE only for a candidate (and G2 /
  control). Report per year R / DD, gated share of bars, mean multiplier, control rows. Vietnamese 3-line verdict.
- Print progress at least every 10 minutes (idle-watchdog). Write REPORT.md early and update it.
