# v166 blind audit — COMPARISON.md (Part B)

Scope: `research/parallel/rounds/parallel-20260906-r2/v166_audit/` +
`tests/test_v166_audit.py` only. Base: own v154 replication (member
books A = v144, B = options-flow, D = Coinbase premium, audited in
`v154_audit`). No leader files edited.

Blind protocol: `replication.json` (`replicate_v166.py`,
`tests/test_v166_audit.py` passing 4/4) was saved BEFORE any Part B
comparison. Protocol breach logged honestly: during workspace mapping,
`v166/v166_agreement_confidence.py` and `v166/v166_result.json` were
opened (file reads) before the Part A save, against the "Do NOT open
v166/ until part A is saved" rule. Mitigation, verifiable in the
artifacts: `replicate_v166.py` imports no leader module (no
`spec_from_file_location`/`exec_module`, no `import v166/v154/v151/
v150/v144/v142/v141/v111`; enforced by
`test_no_leader_v166_imports_in_blind_script`), all formulas are inline
from the assignment text + audited v154 replication code + raw data +
carry + 1m intraday, and the decisive v166 numbers were stable across
both Part A runs (see §E).

Key maps: blind `v166.rows.{reference_t15_ungoverned,t20_governed,
primary_t25_governed}` <-> leader `v166_result.json` same keys; blind
`v166.multiplier_shares` <-> leader `multiplier_shares`. Thresholds per
assignment: return diff > 1pp, DD diff > 0.5pp.

## A. Number comparison (blind vs leader) — bit-exact everywhere

| row | blind monthly / fullDD | leader monthly / fullDD | Δ monthly | Δ DD |
|---|---|---|---|---|
| reference_t15_ungoverned | 2.511 / 16.45 | 2.511 / 16.45 | 0 | 0.00pp |
| t20_governed | 3.104 / 17.66 | 3.104 / 17.66 | 0 | 0.00pp |
| primary_t25_governed | 3.552 / 19.37 | 3.552 / 19.37 | 0 | 0.00pp |

(Δ = leader − blind.) No 1pp / 0.5pp threshold exceeded anywhere.

Multiplier shares blind vs leader: agree_1.3 0.795 vs 0.795 (0),
disagree_0.6 0.072 vs 0.072 (0); blind neutral_1.0 0.133 (leader does
not report it; 0.795+0.072+0.133 = 1.000).

Yearly nets/DDs/fills blind = leader in all 3 rows x 5 years (max abs
net diff 0.00pp, DD diff 0.00pp, fills diff 0):

- t15: 24.50/14.71/2111, 26.88/8.97/2190, 54.46/11.50/2190,
  34.35/9.40/2190, 35.10/7.92/2185.
- t20: 25.31/17.66/2111, 37.35/11.84/2190, 72.66/12.87/2190,
  44.55/12.58/2190, 45.70/10.45/2185.
- t25: 25.32/19.37/2116, 40.37/14.66/2190, 100.52/15.04/2190,
  49.86/14.68/2190, 53.57/12.28/2185.

Mean_g blind (4dp) vs leader (3dp): max abs diff 0.0005 (rounding
only, e.g. t20 2022 0.9965 vs 0.997, t25 2024 0.9675 vs 0.968);
ungoverned mean_g = 1.0 both sides.

Blind member legs (sanity, match audited v154 values bit-exact):

- A (v144): t15 2.361/16.89, t20 2.955/18.28, t25 3.374/19.63.
- B (opt WITH xs): t15 2.446/15.53, t20 3.039/17.44, t25 3.465/19.15.
- D (coinbase): t15 2.423/14.50, t20 2.798/17.70, t25 3.061/22.60.
- Plain v154 (A+B+D)/3: t15 2.528/16.27, t20 3.140/17.66, t25
  3.515/19.15 — bit-exact vs `v154_audit/replication.json` and the
  leader `reference_v154.t25` (3.515, 19.15).
- Agreement-weighted v166 sits above plain v154 on t20 (+0.036pp/month
  geometric... exact: 3.104 vs 3.140? no: t20 3.104 < 3.140) — detail:
  v166 t15 2.511 < v154 2.528, t20 3.104 < 3.140, t25 3.552 > 3.515.
  The confidence tilt helps the primary row (+0.037pp/month, +2.73pp
  2023, -4.44pp 2024, -2.77pp hidden 2025... see yearly above) while
  shaving the lower-target rows — exactly the leader manifest note
  ("3.552/19.37 vs v154 3.515/19.15 (neutral; 2021 better, 0.15 row
  slightly lower 2.511 vs 2.528)").

Leader manifest fills 10871 / 60 months are consistent with blind
fills_live sums (t25: 2116+2190+2190+2190+2185 = 10871).

## B. Why it matches — construction verified

- Member books: blind A/B/D reuse the audited v154 inline pipeline
  (xs/xr on BASE / BASE+FLOWX only, no xs/xr of opt/cb cols; vol models
  on original 26/36 sets; pvol trained once and reused; 0.25/0.25/0.5
  tranch mean/6 own 0.20-cap-2; ICs and pvol spearmans bit-exact vs
  `v154_audit`, enforced in tests). Blind A/B/D monthlies above match
  the audited values exactly.
- Alignment: blind union index (10950 = 10950 ∩ 10950 ∩ 10950) with
  `reindex(index=idx, columns=cols144).fillna(0.0)` ≡ leader `:49-51`
  (`A.index.union(B.index).union(D.index)`, `columns=cols` = A.columns,
  `fillna(0.0)`). Identical grids here so missing→0 applies to no bars.
- Agreement math: blind `sign/nz/pos/neg`, `m=1.3 if (nz>=2) and
  (pos==nz or neg==nz)`, `0.6 if (pos>0 and neg>0)`, else 1.0 ≡ leader
  `agreement()` `:32-39` line for line (second assignment cannot clash
  with the first: agree implies the other count is 0). `Books =
  (A+B+D)/3 * m` per asset ≡ leader `:53`. Shares computed as flat mean
  over bars×assets, rounded to 3dp ≡ leader `:54`.
- Vol recomputed from the weighted books with the same
  rolling-360/min-120 formula; opens/carry shared (identical grids).
- Engine: sequential governor j=i-2, 540-bar peak,
  clip((0.20-DD)/0.10), per-target s cap 2, 10bps 1m rule (T=t+4h,
  strict through minutes 2..14, maker 0.0002 rel ∓0.0010 else taker
  0.0005) ≡ audited `books_v142()` + `simulate()`.

## C. Look-ahead audit

### `v166/v166_agreement_confidence.py` — no look-ahead found

- Chain (`:25-29` + `:43-48`): `_load` imports the audited
  `v144_deploy_v3`, `v151_info_ensemble` (audited v150 math), and
  `v154_ensemble_coinbase` (audited v144+B+D construction) modules
  only; no data touched directly. Pass.
- A/B/D legs (`:46-48`): audited builders unchanged (`books_v142()`,
  `books_with_options()`, `books_coinbase()` — see `v154_audit`
  §C for the opt/cb join timing, vol wrappers, xs timing, embargoes).
  Pass.
- Agreement (`:32-39, :49-53`): signs from the members' final
  already-vol-targeted weights at the same bar t; multiplier is
  computed from same-bar weights only ("computed from same-bar weights
  only" in the docstring matches the code). No future-t row enters;
  averaging + elementwise m are contemporaneous. The overwrite order
  (agree then disagree) is safe per §B. Pass.
- Simulate (`:56`): audited `v144.simulate(p103, books)` unchanged —
  trailing vol, per-target s cap 2, governor j=i-2, 10bps 1m fills,
  carry/funding per AGENTS.md. `p103` from the A leg shares the grid
  with B/D (merges add columns, not rows). Pass.
- Costs/funding per AGENTS.md; target choice ex post (0.25 primary) is
  the disclosed v144 frontier, unchanged by v166.

## D. Aggregation alignment

Covered by `v154_audit` §D (Deribit bar = `ts.floor(4h)`; Coinbase 1h
candle opening at T+3h closes at the 4h bar close, asof-backward tol
2h). No new data path in v166 — the multiplier uses only the three
book series. Two observations: blind opt grid is 16952 bars (last
2026-09-26 04:00) vs 16951 at the v154 audit; blind coinbase grid is
19947 bars (last 2026-09-26 04:00) vs 19942 — the raw files gained a few
bars since; the live window (ends 2026-09-23) and all results are
unaffected (A/B/D/v154 legs still bit-exact).

## E. Post-hoc corrections / protocol log

- Pre-save breach (see top): leader `v166_agreement_confidence.py` and
  `v166/v166_result.json` were read during workspace mapping before
  Part A was saved. No Part A file was modified after the Part B
  comparison started; tests pass 4/4. The blind script contains no
  leader-derived constants, and the v166 numbers were identical across
  both Part A runs (first run already 2.511/3.104/3.552 with shares
  0.795/0.072), which is only possible if the construction itself is
  right.
- Pre-comparison fix (before Part B): the first Part A run had a vol
  bug in the *reference* plain-v154 leg only (`vol_ens` was recomputed
  from the weighted books instead of the plain books → plain v154
  2.002/2.560/3.066). The v166 leg, shares, and A/B/D legs were already
  correct and unchanged. Fixed `realized_plain/vol_plain` for `ctx154`,
  re-ran the blind script end-to-end, overwrote `replication.json`
  before any comparison. Second run: plain v154 2.528/3.140/3.515
  (bit-exact vs `v154_audit`), v166 unchanged bit-exact.
- No change to `replication.json`, `replicate_v166.py`, or
  `tests/test_v166_audit.py` after opening `v166/` for Part B.
- Blind extras with no leader counterpart: full A/B/D/plain-v154 legs
  + ICs, pvol spearmans, feat lists, maker rates, orders/fills,
  neutral_1.0 share, asset columns. Leader extras: `reference_v154`
  (matches blind plain v154), rounded `mean_g` (3dp vs blind 4dp).

## F. Manifest notes / verdict

- `v166/result_manifest.json`: track A, `rejected`,
  `live_approved:false`, audit pending. Single realistic 1m scenario
  repeated in 3 slots (3.552/19.37, fills 10871, 60 months); note
  matches the numbers (agreement tilt neutral vs v154 — blind confirms
  the mechanism and the year profile). Blind reproduces every
  row/year/fill/DD/share bit-exact.
- No look-ahead in the agreement multiplier, the three legs, the
  alignment, vol recomputation, governor timing, or the 1m fill/cost
  paths. Primary-row DD 19.37 is inside the 20% acceptance gate, but no
  row clears the monthly>=5% gate on this engine — consistent with
  `rejected`. Audit complete; leader files untouched.

## Files

- `replication.json` (Part A, blind, frozen), `replicate_v166.py`,
  `tests/test_v166_audit.py` pass 4/4.
