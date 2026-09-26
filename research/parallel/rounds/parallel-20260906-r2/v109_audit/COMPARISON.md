# v109 blind audit — COMPARISON.md (Part B)

Blind replication was saved BEFORE opening `v109/` (see `replication.json`,
`gates.csv`, `gates_tau_lo.csv`, `gates_tau_b94.csv`, `gates_tau_b103.csv`,
`equity_primary_gated/ungated_*.csv`, `equity_secondary_v92_gated/ungated_*.csv`,
`replicate_v109.py` in this folder). Audit scope: `v109/v109_ic_gate.py`,
`v109/v109_result.json`, `v109/result_manifest.json`, `v109/run.log`
(plus audited `v92`/`v94`/`v103`/`v104` paths as base). No leader files edited.
All writes under `v109_audit/` + `tests/test_v109_audit.py`.

## A. Number comparison (blind audit vs leader)

Gate means per anchor year [m_lo, m94, m103], blind (4dp) vs leader (3dp):

| anchor | blind | leader `gate_mean_by_year` | max diff |
|---|---|---|---|
| 2021-09-24 | 0.7197/0.7667/0.6452 | 0.72/0.767/0.645 | 0.0003 |
| 2022-09-24 | 0.3513/0.3593/0.3323 | 0.351/0.359/0.332 | 0.0003 |
| 2023-09-24 | 0.3564/0.3571/0.3349 | 0.356/0.357/0.335 | 0.0004 |
| 2024-09-24 | 0.6686/0.5795/0.3181 | 0.669/0.579/0.318 | 0.0005 |
| 2025-09-24 | 0.7416/0.77/0.5355 | 0.742/0.77/0.535 | 0.0005 |

No gate-mean diff exceeds 0.02 (largest 0.0005; pure 4dp-vs-3dp rounding).

Primary gated yearly normal, blind vs leader `primary_v104_gated.normal.yearly`
(net % / DD % / fills b/l): 3.78/3.78, 17.41/17.41, 1480/1480;
21.47/21.47, 4.38/4.38, 1477/1477; 14.17/14.17, 4.43/4.43, 1149/1149;
15.81/15.81, 4.51/4.51, 1694/1694; 6.86/6.86, 9.86/9.86, 1780/1780.
Fee-stress: 2.39/2.39, 20.49/20.49, 13.63/13.63, 14.26/14.26, 4.97/4.97 exact;
DDs 17.79/17.79, 4.47/4.47, 4.44/4.44, 4.71/4.71, 10.02/10.02 exact.
Execution-stress: 0.67/0.67, 19.27/19.27, 12.96/12.96, 12.37/12.37, 2.65/2.65
exact; DDs exact. No return diff exceeds 1pp (all 0.00pp).

Reference ungated (blind `primary_ungated_yearly` vs leader
`reference_v104_ungated`) is bit-exact in all three scenarios and equals the
audited v104 result (normal 14.07/15.80/64.90/46.93/32.70; fee 11.96/12.93/
60.61/42.59/29.09; execution 9.37/9.43/55.40/37.35/24.73; DDs/fills exact).

Secondary v92-gated (blind vs leader `secondary_v92_gated`), normal:
18.41/18.41, 35.91/35.91, 11.24/11.24, 48.03/48.03, -6.19/-6.19;
DDs 22.04/22.04, 7.47/7.47, 8.21/8.21, 8.60/8.60, 22.39/22.39;
fills 686/686, 573/573, 394/394, 1145/1145, 945/945 exact.
Fee/execution stresses likewise exact (incl. 2025 negatives -8.71/-11.77).
No threshold exceeded anywhere.

## B. Why blind matched

- Books: blind reuses audited OOS CSVs (`v92_audit/predictions_5asset.csv`,
  `v93_v94_audit/predictions_v94.csv`, `v103_v105_audit/predictions_v103.csv`;
  identical 10950-bar grid, opens equal) with inline audited `weights_ls`
  (shorts False/True/True) and `vol_target_scale` (20% cap 2, `W.shift(2)`
  realised, trailing 360/min-120, NaN->1). Leader retrains the same audited
  `v92`/`v94`/`v103` paths inside `v109_ic_gate.py:69-78` (deterministic HGB);
  both give the same books, confirmed by the exact ungated v104 match.
- Gates: blind `iloc[::6]` taus (1825) == leader `index[arange%6==0]`
  (`v109_ic_gate.py:46`); window `t>=tau-60d` + `t+(h+1)*4h<=tau` (`:49`) ==
  spec; clip `IC/0.10` to `[0,1.5]`, min-rows 200 -> 1, ffill + `fillna(1.0)`
  (`:55`) == spec. Blind Spearman via `scipy.stats.spearmanr`, leader via
  `rank().corr()` (Pearson on average ranks); both give the same ICs to the
  reported precision (gate means differ only by 3dp rounding).
- Wrapper: blind uses v99 constants (0.8 books + 0.2*3 carry, 15% target cap 2)
  with `s` from UNGATED books, `Wt=0.8*s*gated`, `carry_exp=0.6*s` (ungated s),
  leader carry convention `carry_exp[t]*carry[t]`, first carry diff 0
  (`:94-105`); realised/vol/scale/costs identical, so gated/ungated yearly agree
  exactly in all scenarios.
- Secondary: blind `simulate` (2-bar delay, fee+slip on scaled turnover,
  0.00005/bar long funding) with `scale=s_lo*m_lo` == leader
  `v92.simulate(p92, W_lo, vol_scale*m_lo, ...)` (`:111`).

## C. Look-ahead audit (`v109_ic_gate.py`, label timing focus)

- Gate window (`:43-55`): `real = t + 4*(h+1)h`; `sel = t>=tau-60d & real<=tau`.
  Label `y_h=log(open[t+1+h]/open[t+1])/(vol42*sqrt(h))` needs opens through
  bar `t+1+h`, whose open is known at `t+(h+1)*4h = real`; requiring `real<=tau`
  means the label is fully realized by tau. Correct; the `<=` boundary matches
  the spec and both sides. `h` is right per book: `v92.H=42` for `y` (`:83`),
  42 for `y42`, 6 for `y6`. Pass.
- OOS preds feeding the gate are from audited causal paths (`:69-77`):
  v92 embargo 102 (`H+10*PD`), v94 `max(18,42,84)+60=144`, v103 `18+60=78`,
  each with per-horizon `t+(h+1)*4h<cutoff`; features/weights/vol as audited in
  v92/v93_v94/v103_v105 audits. No new training leakage. Pass.
- Gate application is causal: `m` defined only at `taus<=t` then ffilled
  (`:55`); books multiplied contemporaneously (`:91`); portfolio scale `s`
  from UNGATED books only (`:94-96`) so vol targeting cannot undo/peek at the
  gate; model leg earns `o[t+2]/o[t+1]-1` with `shift(2)` timing, carry leg keeps
  the labelled `exposure[t]*carry[t]` convention from v99/v104. Pass (carry
  timing is the known labelled assumption, not leakage).
- Hidden-year adaptation (trailing 60d IC inside 2025-09-24..2026-09-23) uses
  only labels realized by each tau — causal adaptation, not locked-test tuning
  with future data. Pass.

## D. Manifest notes

- `v109/result_manifest.json`: track A, `rejected`, `live_approved:false`,
  audit pending ("awaiting OpenCode blind audit"). Primary key
  `primary_v104_gated`: normal monthly 0.967%, worst DD 17.41%, fills 7580/60mo;
  secondary `secondary_v92_gated` monthly 1.529%, worst DD 22.39%.
- `run.log` gate means/monthly/worst-DD match `v109_result.json`; sha256
  `f1379c2e...` (result file).

## E. Verdict

- Blind replication is bit-exact on gate means (to 3dp rounding, max diff
  0.0005 < 0.02), yearly gated/ungated normal/fee/execution nets, DDs, and
  fills, and secondary v92-gated legs. No 0.02 gate or 1pp return threshold
  exceeded.
- No look-ahead found in the IC gate (label-realization timing correct),
  book retraining/embargoes, weights/vol scales, ungated-`s` wrapper, or
  secondary scaling. Audit complete; leader files untouched.
