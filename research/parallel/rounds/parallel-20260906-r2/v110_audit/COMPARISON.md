# v110 blind audit — COMPARISON.md (Part B)

Blind replication was saved BEFORE opening `v110/` (`replication.json`,
`scales.csv`, `books_carry.csv`, `equity_*_*.csv`, `replicate_v110.py` in this
folder). Audit scope: `v110/v110_dd_governor.py`, `v110/v110_result.json`,
`v110/result_manifest.json` (plus audited v92/v94/v103/v104 paths as base).
No leader files edited. All writes under `v110_audit/` + `tests/test_v110_audit.py`.

## A. Number comparison (blind vs leader)

Row key map: blind `primary_gated_0.25` = leader `primary_t25_governed`;
`secondary_gated_0.30` = `secondary_t30_governed`; `ref_ungov_0.25` =
`reference_t25_ungoverned`; `ref_ungov_0.15` = `reference_t15_ungoverned_v104`.

- Yearly net %: max abs diff 0.00pp over all 4 rows x 3 scenarios x 5 years
  (60 cells). DD %: max abs diff 0.00pp (60 yearly cells + 12 full-path DDs).
  Fills: exact in all 60 cells. No 1pp return / 0.5pp DD threshold exceeded.
- Mean g per anchor year: max abs diff 0.0008 (blind 4dp vs leader 3dp
  rounding; e.g. secondary exec-stress 2025: blind 0.8772 vs leader 0.878).
  Ungoverned rows mean_g = 1.0 exactly both sides.
- Full-path live DDs match exactly, e.g. normal: primary 19.71 / secondary
  20.97 / ref_t25 23.90 / ref_t15 15.79; exec-stress: 24.86 / 25.85 / 25.35 /
  17.30. Primary normal yearly (blind = leader): 9.59 / 20.27 / 109.75 /
  69.74 / 47.94; DDs 18.77 / 17.06 / 8.49 / 15.19 / 19.25; fills
  1805 / 2185 / 2183 / 2165 / 2126.
- ref_t15 reproduces the manifest note: 2025 normal 34.11 vs audited v104
  32.70 (+1.41pp) from zero weights on 2026-09-23 (live ends 2026-09-23
  00:00, yearly slice runs to 2026-09-24).

## B. Why blind matched

- Books: blind reuses audited OOS CSVs with inline audited `weights_ls`
  (LO shorts=False, 94/103 shorts=True, daily ffill) and 20%-cap-2
  `vol_target_scale` (W.shift(2) realised, trailing 360/min-120, NaN->1);
  leader retrains the same v92/v94/v103 paths in `v104.books_v104()`
  (`v110_dd_governor.py:89`). Bit-exact ungov match confirms identical books.
- Wrapper: blind realized/vol/s, forward return `o[i+2]/o[i+1]-1` (last two
  -> 0), turnover/funding/carry-cost, and `E*=1+net` match leader `run()`
  (`:41-72`) line for line (0.8 books + 0.6 carry, cap 2, fee/slip per v92
  SCEN, 0.00005 long funding, `2*0.0004/1.2` carry cost, exit costs on the
  first outside-live bar both sides).
- Governor: blind `j=i-2`, 540-bar peak incl. pre-start 1, `clip((0.20-DD)/
  0.10,0,1)` matches leader `:62-65`. Scenario-specific sequential equity
  feedback reproduced exactly (governed full-path DD 23.9->19.71 at t25).
- Minor reporting difference (no numeric effect): blind mean-g averages live
  bars only (2025 n=2184); leader averages all 2190 slice bars with g still
  evolving on the 6 zero-weight bars. Max effect 0.0008, pure rounding/denom.

## C. Look-ahead audit (`v110_dd_governor.py`, governor timing focus)

- Governor lag (`:62-65`): `j=i-2`, `peak=max(eq[j-539..j])`, `DD=1-eq[j]/
  peak`. `eq[j]` embeds `net[j]`, whose forward leg is `o[j+2]/o[j+1]-1 =
  o[i]/o[i-1]-1` — known at open of bar i, i.e. before the close-i decision
  that sets `w_i` (which earns `o[i+2]/o[i+1]-1`). Same 2-bar lag as the vol
  targets. Peak uses only `eq[..j]`. Pass — causal, no future peek.
- `eq` init-ones trap checked: `eq=np.ones(n)` but the peak slice
  `[max(0,j-win+1):j+1]` ends at `j+1` exclusive, so only already-computed
  `eq[..j]` enter; early peaks include pre-start 1s (= E_before=1). Pass.
- Vol/s (`:45-47`): `books.shift(2)`, `carry.shift(1)`, trailing
  `rolling(360,min 120)` — same audited v99/v104 causal estimator. Pass.
- Books/carry (`:43-44`, via `v104.books_v104`): audited v92/v94/v103 paths
  with per-anchor embargoes and causal weights/vol (see v92/v93_v94/v103_v105
  audits); carry reindexed ffill-0. No new training leakage. Pass.
- Application (`:66-69`): `w=B[i]*g[i]`, `c=cexp[i]*g[i]` contemporaneous;
  costs/funding/carry use current+previous only; `live` mask is calendar-only.
  Hidden-year (2025-09-24..) governor adaptation uses only realized own-equity
  — causal adaptation, not locked-test tuning. Pass.

## D. Post-hoc corrections log

- First saved Part A (before opening v110) had two bugs found via the
  ref_t15-vs-v104 mismatch after opening: (1) numpy column-order misalignment
  (books alphabetical vs opens SYMS order in `run_row` gross); (2) `i>=2`
  wrongly forced `w=c=0` on bars 0-1 instead of only forcing `g=1`.
  Fixed (`books=books[o.columns]`; `if live_mask[i]` + inner `governed and
  i>=2`), re-ran, re-saved `replication.json` + equity CSVs. Final numbers
  above are post-fix and bit-exact. No spec reinterpretation after opening.

## E. Manifest notes / verdict

- `v110/result_manifest.json`: track A, `rejected`, `live_approved:false`,
  audit pending. Primary `primary_t25_governed` monthly 3.282%, worst-year DD
  19.25%, full-path DD 19.71% (normal); stress full-path DDs 21.89/24.86.
  Note on t15-vs-v104 one-day gap confirmed by replication.
- Blind replication is bit-exact on yearly nets, DDs, fills, and full-path
  DDs (mean-g to 3dp rounding). No look-ahead in governor timing, vol scale,
  books, or carry. Audit complete; leader files untouched.
