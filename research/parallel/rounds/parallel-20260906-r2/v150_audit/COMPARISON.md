# v150 blind audit — COMPARISON.md (Part B)

Scope: `research/parallel/rounds/parallel-20260906-r2/v150_audit/` +
`tests/test_v150_audit.py` only. Base: v144 replication
(v142 books + v141 sequential governor + 10bps 1m execution, audited in
`v141_v142_audit` A2 / `v148_v149_audit`). No leader files edited.

Blind protocol: `replication.json` (`replicate_v150.py`,
`tests/test_v150_audit.py` passing 4/4) was saved BEFORE opening `v150/`.
Pre-save reads were limited to the allowed base (`AGENTS.md`,
`OPENCODE_VF_COMMON.md`, `OPENCODE_V150_AUDIT.md`, skill,
`v144/v144_deploy_v3.py` + `v144_result.json`, `v142/v142_cross_sectional_features.py`,
`v114/v114_bitstamp_history.py`, `v103/v103_flow_short_horizon.py`,
`v92/v94` bases, `v148_v149_audit/replicate_v148_v149.py` +
`replication.json` + `COMPARISON.md`, `v129_v131_audit` pvol rows, raw
4h/1d/funding/spot/Coinbase/Bitstamp panels, carry, 1m intraday, Deribit
options parquet + `research/mj/fetch_deribit_options_4h.py`; directory
listing showed `v150/` filenames only, no file contents). `v150/`
(`v150_options_flow.py`, `v150_result.json`, manifest, logs) was first
opened after the Part A save. Part A imports no
v150/v144/v142/v141/v135/v129/v125/v115/v114/v110/v103/v92/v94 leader
module (all formulas inline from the assignment text + audited
replication code + raw data + carry + 1m intraday).

Key maps: blind `rows.{reference_t15_ungoverned,t20_governed,primary_t25_governed}`
<-> leader `v150_result.json` same keys. Thresholds per assignment:
return diff > 1pp, DD diff > 0.5pp.

## A. Number comparison (blind vs leader)

| row | blind monthly / fullDD | leader monthly / fullDD | Δ monthly | Δ DD |
|---|---|---|---|---|
| reference_t15_ungoverned | 2.351 / 16.54 | 2.446 / 15.53 | +0.095 | -1.01pp |
| t20_governed | 2.967 / 17.84 | 3.039 / 17.44 | +0.072 | -0.40pp |
| primary_t25_governed | 3.338 / 18.31 | 3.465 / 19.15 | +0.127 | +0.84pp |

Monthly diffs are small (< 0.13pp) but DD thresholds (> 0.5pp) are
exceeded on t15 (-1.01pp) and t25 (+0.84pp). Yearly nets exceed the 1pp
threshold in every year of every row:

| row | 2021 Δnet/ΔDD | 2022 Δnet/ΔDD | 2023 Δnet/ΔDD | 2024 Δnet/ΔDD | 2025 Δnet/ΔDD |
|---|---|---|---|---|---|
| t15 | -6.25/-0.06 | +14.27/-3.99 | +5.08/+2.63 | -2.90/+0.43 | -2.61/-0.37 |
| t20 | -5.38/+0.58 | +21.83/-4.27 | -4.95/+3.09 | -2.65/-0.17 | -4.10/-0.48 |
| t25 | -3.65/+1.13 | +25.06/-4.75 | -6.49/+2.65 | -1.28/-1.14 | -4.61/+0.97 |

(Δ = leader − blind, nets in pp, DDs in pp. Fills match within 16:
2021 t15 2033 vs 2017, t20 2032 vs 2027; all other years exact or ±1.)
Large offsetting yearly diffs with a small monthly diff is the signature
of materially different direction books, not of cost/engine drift.

## B. Why they differ — pre-open spec misinterpretation (logged, not patched)

Blind read "(no xs versions)" as "no xs/xr features at all":
return feats v114 26+5=31, v103 36+5=41.
Leader (`v150_options_flow.py:9-10,60-63,72`) joins opt feats to the base
panels BEFORE the v142 xs step and then still runs it: return feats are
base + opt + xs/xr (v114 26+5+18=49, v103 36+5+24=65); only the opt
columns themselves have no xs versions ("they are market-wide" — correct,
since a market-wide column broadcast to all syms at t would have
xs ≡ 0). The docstring is explicit; the assignment text is ambiguous and
blind chose the wrong branch. `replication.json` is frozen pre-open with
the no-xs choice; the diffs above are the measured cost of that choice.

Everything else matches line-for-line:

- Options math: blind `net/tot/opt_net6 (rolling6 sum, min 6, 0→NaN)`,
  `pcr=log(max(put,1)/max(call,1))`, `skew=iv_put−iv_call`,
  `z=(s−roll180mean(min90))/roll180std(min90,ddof1)`,
  `opt_skew6=roll6mean(min3)`, `opt_act_z=z(log(max(n,1)))` ≡ leader
  `:42-49` (`rolling(6).sum()` default min 6, `.clip(lower=1)`,
  `.replace(0,nan)`, same z lambda, `min_periods=3`). Reindex to the
  complete 4h grid with flows→0 / IVs NaN ≡ leader `:38-41`.
- Join: blind left-merge on t broadcast to all 5 syms ≡ leader
  `build92/build103 .merge(feats,on="t",how="left")` (`:59-63`).
- Vol: blind trains pvol on original 26/36 sets ≡ leader's wrapper
  `:66-67` dropping OPT from the feat lists (pvol anchors reproduce the
  audited v129 rows bit-exact on train_rows; spearmans 0.5275/0.5283/
  0.6272/0.6935/0.6604 v114, 0.5068/0.5031/0.6141/0.7032/0.665 v103).
- Engine: blind sequential governor (j=i−2, 540-bar peak,
  clip((0.20−DD)/0.10)), per-target s cap 2, 10 bps 1m rule
  (T=t+4h, strict through minutes 2..14, maker 0.0002 rel ∓0.0010 else
  taker 0.0005) ≡ audited `books_v142()` + `simulate()`.
- Leader `reference_v144` 2.361/16.89, 2.955/18.28, 3.374/19.63 matches
  the audited v144 values.
- Leader coverage (v103 rows with all 5 opt feats:
  BNB 0.859, BTC 0.845, ETH 0.841, SOL 1.0, XRP 0.913) is consistent with
  blind (opt grid 16944 bars 2019-01-01→2026-09-24 20:00, only 5/89/2/89/89
  NaNs on the grid; panel rows before 2019 + 180-bar z warmup explain the
  ~0.84-1.0 coverage; SOL lists later so its panel starts inside the opt
  history → 1.0).

Net assessment: v150 ≈ v144 + small options lift on the monthly
(t15 +0.085, t20 +0.084, t25 +0.091 vs reference) with mixed DD
(t15 −1.36pp, t20 −0.84pp, t25 −0.48pp vs reference). Blind no-xs+opt
vs v144 is near-neutral monthly (t15 −0.010, t20 +0.012, t25 −0.036) —
the xs direction features, not the opt features, drive the yearly gaps
in §A (notably 2022, where leader beats blind by 14-25pp across rows).

## C. Look-ahead audit

### `v150/v150_options_flow.py` — no look-ahead found

- Features (`:34-49`): reindex + fill is a present/past-only reshape;
  `net/tot/pcr/skew` use the current bar only; `opt_net6`,
  `opt_skew6`, all three z-scores use trailing rolling windows
  (current + past, min_periods 6/3/90). No `shift(-)`, no future bar.
  Pass.
- Timing (`:3-4,60-63`): options bar = trades in `[T,T+4h)`, known at bar
  close; joining bar T to panel row open T is the same timing as the
  row's own OHLCV (close T+4h−1ms). Decisions execute with the audited
  2-bar lag (`books.shift(2)` inside `books_v142`/`simulate`), so no
  signal fills on its own bar. Pass — the docstring claim "known at the
  bar close" is correct (see §D).
- Broadcast (`:4,60-63`): one opt row per t merged to every asset at t —
  market-wide by construction; no cross-asset future (all inputs are bar-t
  closes, simultaneous). Correctly no xs/xr built on opt (xs ≡ 0). Pass.
- xs/xr on BASE/FLOWX (`books_v142` → `v142.add_xs`): groupby-t mean +
  `rank(pct=True)` over majors present at the same bar t — contemporaneous
  only, as audited in `v141_v142_audit` §C. Pass.
- Vol wrapper (`:66-67`): drops exactly the 5 OPT cols from the feat
  lists passed to the audited `v129.vol_predict`; embargoes
  (cutoff−102·4h, t+44·4h<cutoff), causal fv target, and left-join
  `pvol.fillna(vol42)` on (t,sym) unchanged. Test year never fit. Pass.
- Training (`books_v142`): HGB v92 h42 cutoff−408h + t+43h<cutoff, v94
  h18/42/84 cutoff−576h + t+(h+1)h<cutoff mean, v103 h6/18 cutoff−312h
  mean — audited cutoffs; extra opt/xs cols are features, labels unchanged
  and realised before cutoffs. No normalisation/threshold fit. Pass.
- Books/engine (`:72,75`): audited tranched books (0.25/0.25/0.5), 2-bar-lag
  returns, trailing vol, per-target s cap 2, governor j=i−2, 10 bps 1m
  fills, carry/funding per AGENTS.md. Pass.
- Costs/funding per AGENTS.md; target choice ex post (0.25 primary) is the
  disclosed v144 frontier, unchanged by v150.

## D. Aggregation alignment (`research/mj/fetch_deribit_options_4h.py`)

- `d["bar"] = d["ts"].dt.floor("4h")` (`:59`) + per-bar fetch windows
  `[w0, w0+4h−1ms]` (`:91`) + `groupby("bar")` (`:64-74`): each trade is
  counted exactly once, in bar T ⟺ trade time ∈ [T,T+4h). Matches the
  assignment's "[T,T+4h) only" and the leader docstring's "per UTC 4h bar
  [T,T+4h)". Pass.

## E. Post-hoc corrections / protocol log

- No change to `replication.json`, `replicate_v150.py`, or
  `tests/test_v150_audit.py` after opening `v150/`. Tests pass 4/4 pre-
  and post-open.
- One pre-open spec gamble logged here (not a code bug): `opt_net6`
  `min_periods=6` for both rolling sums — the spec gives no min; leader
  uses the pandas default (also 6). Match confirmed post-open.
- The §B xs misinterpretation was discovered post-open by reading
  `v150_options_flow.py:9-10,60-63,72`; blind did NOT rerun with xs (the
  frozen numbers above are the honest blind output). A confirmatory
  xs-rerun is left to the leader; the code path to reproduce is
  `books_v142()` with the opt-merged panels, i.e. exactly the leader
  script.
- Blind extras with no leader counterpart: direction ICs
  (v92 0.0983/0.008/0.1233/0.1295/0.137; v94-vs-h42
  0.1381/0.0154/0.116/0.1259/0.1327; v103_y6
  0.0735/0.0452/0.0516/0.0516/0.0545), pvol spearmans, `feats*o` lists,
  maker rate, orders/fills, full `meta`.

## F. Manifest notes / verdict

- `v150/result_manifest.json`: track A, `rejected`, `live_approved:false`,
  audit pending ("awaiting OpenCode blind audit"). Single realistic 1m
  scenario repeated in 3 slots (3.465/19.15, fills 10779, 60 months).
- Blind reproduces the options math, join timing, vol exclusion, and
  engine exactly; the only divergence is the documented xs-scope error,
  which fully explains the >1pp yearly and >0.5pp DD gaps. No look-ahead
  in feature timing, the t-broadcast, the vol wrapper, xs timing,
  embargoes, tranching, scales, governor timing, or 1m fill/cost paths.
  Audit complete; leader files untouched.

## Files

- `replication.json` (Part A, blind, frozen), `replicate_v150.py`,
  `tests/test_v150_audit.py` pass 4/4.
