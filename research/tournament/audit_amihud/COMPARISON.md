# audit_amihud COMPARISON (blind replication of the Amihud A1 book tilt on G2)

Blind protocol followed: replication built ONLY from `docs/opencode/IDEAS4_20261007.md`
§C item H4 (variant A1), `docs/opencode/OPENCODE_W_TEMPLATE_BOOKGATE_20261007.md` and
`research/tournament/oc_lit_xs/PLAN.md` (spec only). `replication.json` (part A) was
written BEFORE opening `oc_lit_xs` code / REPORT.md / results.json / engine_results.json /
engine_runs.pkl / tmp/, nor `research/tournament/oc_amihudrobust/`.
G2 baseline reproduced to the digit first from cache (5.41 / W 2.588 / DD 16.91 /
full-path DD 16.82) AND re-ran bit-exact through the harness before any comparison.
Deviations disclosed: (a) `oc_lit_xs/PLAN.md`'s post-hoc log (§Post-hoc log) already states
the A1 dev4 summary (5.844/W 2.798/DD 16.81, Y4 4.75) — read as part of the allowed spec,
so part A was blind to code but not to those headline numbers; the independent
implementation still reproduces them from scratch. (b) `tests/test_oc_lit_xs.py` was opened
before the engine run (revealed helper names `tilt_frames/xs_z/clip_mult`); the audit
module uses its own independent API and no code was copied. (c) a directory listing of
`oc_lit_xs/` (filenames only) was taken pre-unblinding; no file contents were opened.
No computation on the most recent year except the labelled Y4/byproduct rows; Y4 was never
a selection input here (this audit selects nothing).

## Part A (mine) vs theirs

A1 per-year 4-phase reset R (%/mo geometric) / yearly DD (%), plus aggregates:

| year | mine (replication.json) | theirs (REPORT.md / results.json / engine_results.json) | delta |
|---|---|---|---|
| 2021-09-24 | 2.798 / 12.21 | 2.798 / 12.21 | R 0.000 ok, DD 0.00 ok |
| 2022-09-24 | 3.395 / 16.81 | 3.395 / 16.81 | R 0.000 ok, DD 0.00 ok |
| 2023-09-24 | 6.390 / 15.77 | 6.390 / 15.77 | R 0.000 ok, DD 0.00 ok |
| 2024-09-24 | 10.987 / 8.42 | 10.987 / 8.42 | R 0.000 ok, DD 0.00 ok |
| dev4 mean / worst / maxDD | 5.844 / 2.798 / 16.81 | 5.844 / 2.798 / 16.81 | 0.000 / 0.000 / 0.00 ok |
| 2025-09-24 Y4 (labelled once) | 4.750 / 11.14 | 4.750 / 11.14 | R 0.000 ok, DD 0.00 ok |
| 5y R / W / maxDD | 5.624 / 2.798 / 16.81 | 5.624 / 2.798 / 16.81 | exact |
| full-path DD | 16.66 | 16.66 | exact |
| G2 engine re-run | 5.41 / 16.91 / 16.82 | 5.41 / 16.91 / 16.82 | exact |

Thresholds (R > 0.10 pp, DD > 0.5 pp): no breach on any row. Sampled signal cross-check:
my `tilt_frames` vs their `tilt_frames` A1 on 2022-03-01 (9 bars) max abs diff 0.0;
on the 2021-09-23..25 boundary diff 0.0 on every engine row (the only diff is the
pre-cutoff convention placement, see cause 1 — economically void since the book index
starts 2021-09-24 00:00).

## Causes (spec ambiguity vs bug)

1. Pre-cutoff placement (convention, no economic effect). I force 1.0 inside
   `tilt_frames` for T < 2021-09-24 (`amihud_signal.py::tilt_frames`); they return raw
   tilted values from `tilt_frames` and zero them later in
   `compute_xs_engine.py:70-71` (`frames[v].loc[T < CUTOFF] = 1.0`). On the real book
   index (starts 2021-09-24 00:00) both paths are identical (verified 0.0 diff).
2. Daily aggregation phrasing (examined, immaterial). They `groupby(day).last` +
   reindex to a full consecutive daily index (`xs_signal.py:58-63`); I
   `drop_duplicates(keep=last)` without reindex. No duplicate `open_time` and no
   1-day gaps exist for any of the 5 coins over the span (checked: 0 dups, 0 gaps),
   so both frames coincide; a missing day would give NaN->mult 1 on theirs vs
   stale-prior-day on mine — never triggered.
3. Searchsorted side (examined, identical). They `searchsorted(..., side="left")` +
   exact-match guard (`xs_signal.py:96-106`); I `searchsorted(D*, side="right")-1`.
   With consecutive daily midnights both resolve to exactly D*(T); verified equal
   multipliers on samples and bit-exact engine outputs.
4. No other difference: r/amihud/30d-min20 (`xs_signal.py:66-72` vs mine),
   `d_last = floor(D)-1day` (`xs_signal.py:79-82` vs mine `normalize()-1day`, same on
   4h grid), per-row ddof=1 z with <2/std0->0 and NaN->NaN (`xs_signal.py:110-126` vs
   mine), `clip_mult` [0.5,1.5] NaN->1 (`xs_signal.py:164-170` vs mine), A1
   `1+0.25z` on every non-zero weight (`compute_xs_engine.py:81-83` vs mine
   `sb.where(sb==0, sb*mult)`), bear filter (1200-bar mean, longs x0.5), ffill order,
   `win_start=5` trade-through + stop-first harness, reset metric + `v388.mix`
   full-path DD — all identical by construction and confirmed by the exact numbers.

## Look-ahead and accounting checks (each with a test in tests/test_audit_amihud.py)

- Daily data timing PASS: both map T -> D*(T)=date(T)-1day (day usable iff
  D+1 00:00 <= T; `xs_signal.py:79-82`, mine `d_last`). Tests: ±1s boundary exposes
  exactly the prior day; truncated recompute of Amihud30 from closes/quote_volumes
  <= D0 matches to 1e-12; sampled-T truncation leaves multipliers unchanged.
- Cross-sectional z same-T only PASS: both compute mean/std(ddof=1) across the 5 raws
  at the same T only (`xs_signal.py:110-126`); no trailing fit, no full-sample rank.
  Test asserts truncated-index multipliers equal full-index prefix.
- Volume source PASS: both use `quote_volume` (USD) — `xs_signal.py:55,68,73`
  (`amihud_d = r.abs()/qv`, `Size30` unused for A1); no `volume`/`taker` leg in A1.
  Test hand-checks |r|/quote_volume and asserts it differs from a `volume`-based
  variant (so the test pins the source).
- Side mask / clip PASS: A1 scales every non-zero bear-filtered weight
  (`compute_xs_engine.py:81-83`); clip [0.5,1.5], NaN->1 on both sides. Tests pin
  clip edges and A1 maths on z=[-2,-1,0,1,2] -> [0.5,0.75,1.0,1.25,1.5].
- Cutoff rows PASS: rows before 2021-09-24 untilted on both sides (different code
  placement, same engine effect). Test asserts pre-cutoff frame is all 1.0.
- Engine constants PASS: `win_start=5`, G2 config (rule inv, k 1.0, kd 1.7, bear,
  G 2.0), v426 order (bear -> tilt -> ffill) asserted in the test by source grep on
  `compute_a1_engine.py`; engine G2 re-ran bit-exact to the cached triple.
- No accounting hole: book-tilt is a weight multiplier inside the standard engine
  (same fills/fees/funding/MtM DD as G2); full-path DD 16.66 < G2 16.82 on both sides.

## Final line

PASS (A1 reproduces exactly: all R deltas 0.000 pp, all DD deltas 0.00 pp;
no look-ahead, no volume-source or z-timing deviation; noted convention differences
are economically void).

Tiếng Việt:
- Tái lập độc lập khớp tuyệt đối với A1 của oc_lit_xs (mọi R lệch 0.000, mọi DD lệch 0.00; full-path DD 16.66 khớp từng chữ số).
- Không phát hiện look-ahead: ngày D*(T), z cùng thời điểm, nguồn quote_volume, clip/mặt nạ và hằng số engine đều khớp.
- Kết luận PASS; các khác biệt quy ước (vị trí cutoff, cách gộp ngày, hướng searchsorted) không ảnh hưởng kinh tế.
