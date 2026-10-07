# oc_rlb1plan — PLAN (DESIGN ONLY; no outcomes, no verdict)

Hypothesis: the deployed BOT R2B1D17BF (v411) runs R2 dip agents trained in the
pre-B1, pre-bear environment; retraining the same agents walk-forward INSIDE the
B1 + bear-book environment lifts net monthly return at the same DD (4-phase
reset-metric harness, 5 walk-forward years). Null expectation stated upfront:
B1 scales rung SIZE, not per-unit rung return, so a naive per-rung retrain
learns ~identical tables; a gain requires the environment to enter training via
an added state feature and/or sample weighting (variants below).

## (a) Which scripts produce the tables; inputs; state/action/reward; where B1 + bear enter

Table chain (read-only; do NOT edit):
- `research/diagnostics/phase_agents/build_tables.py` — dev tables
  `tables/r2_table_s{s}.parquet` (s = 0..3). Same construction as
  `v306_gene_tables.py` (fit "U") + `r2_cache.py`.
- `research/parallel/rounds/parallel-20260906-r2/v376/v376_final_hidden.py::build_tables`
  — extends dev tables with anchor-2025 rows into
  `v376/tables_hidden/r2_table_s{s}.parquet`. Check: s=0 equals deployed
  `artifacts/research/engine_real/v321_r2_table_m0.parquet` on the overlap.
- `v376/v376_multiphase_bot.py::worker` + `v376_final_hidden.replay` consume the
  tables via `backend/history_tm.py::R2_TABLE` +
  `research/diagnostics/phase_offset_full/phase_offset_full.py::pipe_setup("v321")`
  (lookup dicts keyed by (T, sym, rung) -> size/tp; `sleeve_fill_size`,
  `sleeve_tp`).
- Model code: `v293/v293_pooled_exit_agent.py` (fills replica, TP agent),
  `v294/v294_wide_pool_exit_agent.py` (wide U2020 universe = 30 alts + 5 majors,
  training only), `v296/v296_joint_dip_agent.py::hgb(seed)`
  (HistGradientBoostingRegressor max_depth=3, lr=0.05, max_iter=200,
  min_samples_leaf=200, l2=1.0). R2 genome choice/seeds: `v321/v321_bot_walkforward_seed_choice.py`
  (R2 = G2 + 5-sigma rung, agents fit on all 7 rung depths U=2.0..5.0; traded rungs 2.5..5.0).
  Memory notes: CONTINUOUS_RESEARCH.md (v292-v295 data effect; v296 J1 size+TP;
  v301 G2; v306 R2 best seed; v321 deploy; v375/v376 phases; v399 B1; v410/v411 bear filter).

Inputs per anchor jj (anchors 2021-09-24 .. 2025-09-24):
- Fills: `v293.fills_of` standalone replica on 1m data (majors
  `data/raw/{btc,majors}_intraday_20260924`, alts `data/raw/alts*_20260926/30`);
  shared causal mirror: `research/tournament/ext/fills_U_ext.parquet`
  (72,130 rows, t_fill 2020-08-21 .. 2026-09-23, cols j,r,f,t_fill,t_exit,
  y0.5/y1.0/y1.5, x0..x6, sym; verified 2026-10-05).
- Per-fill state x0..x6 (7 floats): sp30, rung k, volreg, trend, btc sp30,
  dd24 = log(C/hmax24)/sig, hour. Fills use minute f-1 (`kk = j*240+f-1`);
  TABLES use bar-open form (minute 0 close, `kk = j*240`; sigma/volreg/trend
  from the shifted grid's own 4h opens, sigma shifted one bar; hour = T.hour).
- Reward/labels: exact net returns y0.5/y1.0/y1.5 from `v293.outcomes`
  (engine_user close5 + backstop exit; maker/taker/funding as engine), clipped
  to [-0.10, 0.08] for fitting. Size models regress y1.0; TP models regress each
  action; mu = train mean of y1.0.
- Actions: size S1 rule (1.5 if pa,pb > 2*mu; 0.5 if both < 0; else 1.0) and TP
  X4 rule (0.5/1.5 sigma iff both halves agree on the same non-base action with
  gain > 0.001, else 1.0) — `phase_agents/build_tables.py::rules`.
- Fits: per anchor, `keep = t_exit < anchor - 7d` (`v293.EMBARGO`), cross-fit on
  j%2 halves; seeds `10*jj+h` (size) and `+3*c` (TP per action c); model for bar
  T = anchor jj with `jj = max(q: T >= anchor_q)`.

Deployed BOT env (model-blind to it):
- Book: `scripts/forward_v205.py::research_books_d2` (v285 D2 = 0.8*O1 + 0.2*D).
- B1 (v399 `corr_size`, rule "inv"): at fill minute f of coin a in bar i,
  n = #{other majors b: C[i,f-1,b] <= O[i,0,b]*(1-2.5*sig4[i,b])};
  executed size = table size x kd / (1+n) (R2B1D17BF: kd=1.7, budget 0.26*1.7).
  Bot-executable (amend resting bids each minute; uses data up to minute f-1).
- Bear-book filter (v410/v411): bear = BTC 4h open < rolling-1200-bar mean
  (min_periods 600, causal on standard-book rows); book LONG targets x0.5 in
  bear bars, shorts unchanged; transform applied BEFORE the shifted-clock
  forward-fill.
- R2B1D17BF (v411): dips kd=1.7 x B1 + bear-book; tables still the pre-B1,
  pre-bear R2 tables.

How B1 + bear enter retraining (the ONLY causal channels; per-unit y is
invariant to both, hence variants):
- V0 (null control): refit identical code inside B1+bear replay years — tables
  expected ~identical (documents the invariance; no gain expected).
- V1 (B1-aware): add 8th state feature n (computed at minute f-1 exactly as
  v399) to X AND sample-weight each fill by w = 1/(1+n) in both size and TP
  fits (same seeds/halves/embargo); tables store resulting size/tp; replay
  multiplies by 1/(1+n) as deployed.
- V2 (B1+bear-aware): V1 + bear flag b(T) in {0,1} (v410 definition, causal) as
  9th state feature; fits unchanged otherwise; replay with bear-book filter on.
- Max 3 variants (V0/V1/V2); V0 is a control, V1 vs V2 is the comparison. No
 TP-margin or seed changes.

## (b) Walk-forward folds and embargo

- Anchors A in {2021-09-24, 2022-09-24, 2023-09-24, 2024-09-24, 2025-09-24};
  test year Y(A) = [A, A+365d). All five years are research data (assignment
  window to 2026-09-24 00:00 UTC); prospective logs validate any winner later.
- Agent for Y(A) learns ONLY from fills with `t_exit < A - 7 days` (v293.EMBARGO;
  >= horizon). Normalisation internals (sig/volreg/trend/hmax24/sig1 rolling
  windows), mu, HGB fits, rule thresholds (2*mu, 0, 0.001 margin) all fitted on
  the same kept rows. Per-bar model jj = latest anchor <= T.
- 4 phases s=0..3h: state from each shifted grid's own bars; same per-anchor
  models (identical data/order/seeds -> identical models; only state differs).
- Scoring (later work, not this task): v399/v410 harness — per-year reset
  metric (`research/diagnostics/r2_decompose5/reset_metric.py`), per-year reset
  R/W/DD, 5y geometric mean, max DD over full path (max of 4h-close and
  1m-marked), win rates; selection by the robust criterion (DD<=20, no losing
  year; prefer mean>=5 then max worst-year; ties -> higher mean) AND the
  assignment default (PROMISING only if same sign in >=4/5 years AND
  leave-one-year-out holds in >=4/5).

## (c) Runtime estimate (ONE small timing sample, <10 min CPU, RAM < 1 GB, no 1m touched)

Measured 2026-10-05 (this box, single process):
- `fills_U_ext.parquet` projection (t_fill,t_exit,sym,r,y1.0; 72,130 rows):
  0.06 s. `v376/tables_hidden/r2_table_s0.parquet` (273,850 rows): 0.07 s.
- Micro HGB (same hyperparams, 2,000 fills fit + 500-row predict): 1.02 s,
  pred mean 0.00358 (sklearn 1.5.2).
Scale-up: 5 anchors x (2 size + 6 TP) = 40 HGB fits on ~10-50k rows each ->
  order of tens of minutes CPU single-process for fits alone (200-iteration
  HGB scales ~linearly; ~1 s/2k rows => ~5-25 s/fit => ~5-15 min total), plus
  state featurization per (anchor, phase). The dominant cost is rebuilding
  fills/state from 1m (35 coins x 6y minute bars; multi-GB I/O, hours) — that
  step does NOT fit this LIGHT slot and needs Kaggle CPU (kpack pattern as
  v306) or reuse of cached `fills_U.parquet` + `fills_U_ext.parquet`.
  Replay/eval (4 phases x 5 years, engine_user) is also a heavy multi-process
  job (v376/v399-v411 use Pool(2-4)). Verdict: design + micro-fits fit local
  CPU/GTX1650; FULL retrain + replay needs Kaggle; local box only for
  inference, table-lookup replay checks, and audits.

## (d) Minimal code-diff sketch (NEW code only in this folder; nothing applied)

New file `research/tournament/oc_rlb1plan/retrain_env.py` (sketch; not run here):
```python
# inputs: fills_U_ext.parquet (x0..x6, y*, t_exit, sym, f, j), hourly_ext.parquet, bar_open_ext.parquet
EMBARGO = pd.Timedelta(days=7)
def bear_flag(btc_opens):  # causal: BTC 4h open < rolling-1200 mean (min_periods 600)
    return (btc_opens < btc_opens.rolling(1200, min_periods=600).mean()).astype("int8")
def corr_n(hourly, bar_open, T, sym):  # v399 rule at minute f-1; hourly is too coarse -> needs 1m; else NaN
    ...
def fit_anchor(df, keep, seed_jj, W=None):  # v296.hgb hyperparams, j%2 halves, clip y to [-0.10,0.08]
    ...
# V0: W=None, X=x0..x6            # expected ~= deployed tables
# V1: X=x0..x6+n, W=1/(1+n)       # B1-aware
# V2: X=x0..x6+n+bear, W=1/(1+n)  # B1+bear-aware
# rules(): verbatim copy of phase_agents/build_tables.py::rules (R2 genome)
# replay hook: pipe_setup("v321") + v399 corr_size wrapper + v410 books_bear
```
No existing file is modified; `build_tables.py`, `v376_*.py`, `history_tm.py`,
`forward_v205.py` are imported or copied FROM, never edited.

## (e) Leakage risks (explicit checklist for the later build/audit)

1. Fill-time features: n uses minute f-1 strictly (C[m], O0, sig4 at decision
   bar); never f or later; bar-open tables never see intrabar data.
2. Fit window: `t_exit` (not t_fill) < A - 7d; fills exiting inside the embargo
   or test year excluded from every fit, mu, and threshold.
3. Thresholds (2*mu, 0, 0.001) and mu are per-anchor train statistics; no pooling
   across anchors, no test-year calibration.
4. Phase shift: sigma/volreg/trend/hmax/sp30 recomputed on each shifted grid
   (shifted-one-bar sigma as v293); never reuse standard-grid values off-phase.
5. Bear flag causal (rolling mean of opens up to decision row); transform before
   forward-fill; no centered/future mean.
6. B1 n is fill-minute information: allowed ONLY as training feature/weight and
   live sizing (bot_only); never as a bar-open signal.
7. No test-year (incl. 2025-09-24..2026-09-23) statistic feeds any choice; seed
   choice stays v321's; tables_hidden anchor-2025 rows are an output, not an input.
8. Cost/execution realism kept: maker 0.0002 entries/TP, taker 0.00055 stops,
   adverse long funding 0.0001/8h, stop-first intrabar, win_start=5.

Status: DESIGN ONLY. No scripts run beyond the two read-only timing/metadata
probes above; no outcomes computed; no verdict rendered.
