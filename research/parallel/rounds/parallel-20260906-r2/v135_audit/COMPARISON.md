# v135 blind audit — COMPARISON.md

Scope: `research/parallel/rounds/parallel-20260906-r2/v135_audit/` +
`tests/test_v135_audit.py` only. Base: audited v132_v133 replication
(v133 weights Wt = 0.8*s*books, carry, v104 cost path). No leader files edited.

Blind protocol: `replication.json` (`replicate_v135.py`,
`tests/test_v135_audit.py` passing 3/3) was saved BEFORE opening `v135/`.
Pre-save reads were limited to the allowed base (`v132_v133_audit/`
replication + COMPARISON, `v129_v131_audit/` pvol rows, `v113_v114_audit/` +
`v103_v105_audit/` OOS CSVs, raw 4h/1d/funding/spot/Coinbase/Bitstamp panels,
carry, 1m intraday). `v135/` (`v135_limit_offset.py`, `v135_result.json`,
manifest, logs) was first opened after the Part A save. Part A imports no
v135/v134/v133/v132/v129/v125/v115/v114/v110/v104/v103/v92/v94 leader module
(all formulas inline from the assignment text + audited OOS CSVs + raw data
+ carry + audited panel code).

## A. Number comparison (blind vs leader)

Key maps: blind `offsets.{0,5,10,20}.yearly/maker_fill_rate/mean_net_first4/
full_path_dd` <-> leader `by_offset.{0,5,10,20}bps.yearly/maker_rate/
mean_net_2021_2024/full_path_dd`; blind `chosen_d_bps` <-> leader
`chosen_offset`; blind `chosen.hidden_year` <-> leader `chosen_hidden_year`.

| offset | repl yearly nets | v135 yearly nets | return diff | DD diff | maker diff |
|---|---|---|---|---|---|
| 0bps | 18.58/12.91/44.29/40.78/29.00 | 18.58/12.91/44.29/40.78/29.00 | 0 | 0 | 0.860 vs 0.860 = 0 |
| 5bps | 20.10/13.82/45.96/42.60/30.14 | 20.10/13.82/45.96/42.60/30.14 | 0 | 0 | 0.760 vs 0.760 = 0 |
| 10bps | 21.04/14.06/46.54/43.13/30.51 | 21.04/14.06/46.54/43.13/30.51 | 0 | 0 | 0.639 vs 0.639 = 0 |
| 20bps | 21.76/13.82/46.06/42.98/30.25 | 21.76/13.82/46.06/42.98/30.25 | 0 | 0 | 0.427 vs 0.427 = 0 |

- Full-path DD blind = leader: 16.67 / 16.22 / 16.25 / 16.49 (diff 0.00pp).
- Mean net 2021-2024 blind = leader: 29.14 / 30.62 / 31.19 / 31.16 (diff 0).
- Chosen blind = leader: 10bps; hidden year blind = leader: net 30.51,
  monthly 2.245, DD 9.69, sharpe 1.63, fills 2161 (diff 0).
- Yearly monthly_geo/sharpe/fills match exactly (max abs diff 0).
- Return diff > 1pp or DD diff > 0.5pp or maker-rate diff > 0.01: none —
  no explanation required.
- Extra blind fields (no leader counterpart): per-offset `monthly_pct`
  (2.114/2.206/2.241/2.236), `orders_live`/`fills_live`, hidden maker
  0.597 / orders 9206 / fills 2161 for the chosen 10bps (leader stores no
  hidden maker/orders; live maker 0.639 matches). d=0 hidden 29.00/10.06/
  0.849/9206 reproduces the audited v133 hidden strict baseline bit-exact.

## B. Why blind matched

- Wt base rebuilt exactly as v133: v114 extended panel (Bitstamp>=2013-01-01
  + Coinbase BTC, Coinbase ETH, spot_2017 prefix) + v103 base panel
  (spot prefix + USD-M + flow), 26/36 feats, pvol by v129 method
  (fv = log rolling-42 std of diff(log open) shift -43, HGB v92 params,
  cutoff anchor-102*4h, t+44*4h<cutoff, pvol=exp(pred)) — train rows and
  spearmans match v129_v131_audit bit-exact (v114 46120/57070/68020/79000/
  89950 rho 0.5275/0.5283/0.6272/0.6935/0.6604; v103 33293/44243/55193/
  66173/77123 rho 0.5068/0.5031/0.6141/0.7032/0.6650) — left-join replace
  vol42, LO/LS weights (N=5, rib != -1 long gate, rib != 1 short gate),
  tranche mean /6, own 0.20-cap-2 scales, books 0.25/0.25/0.5, s 0.15
  sequential, carry 0.6*s path. d=0 reproduces v133 hidden, confirming the
  base.
- Execution rebuilt literally from the assignment: 1m
  `klines_1m_20*.parquet` / `{SYM}_1m_20*.parquet` dedup open_time,
  T = t+4h, p0 minute-0, lo/hi min/max over offsets 2..14, p15 minute-15,
  buy p0*(1-d) / sell p0*(1+d), maker iff lo<limit / hi>limit with p0
  present (fee 0.0002, rel -d/+d) else taker (fee 0.0005,
  rel p15/p0-1 +/-0.0002, p15:=p0, missing p0 -> +/-0.0002),
  cost=|dW|*fee+dW*rel, net=sum(Wt*(open[t+2]/open[t+1]-1))-cost
  -0.00005*long+0.6*s*carry-|diff|*2*0.0004/1.2. Bit-exact yearlies confirm
  identical 1m grouping, limit, fee/rel, and cost accounting.

## C. Look-ahead audit of v135_limit_offset.py

- `bar_stats` (:43-53): T = floor 4h of each 1m open_time; off = minute
  offset; p0 off==0, w off 2..14 grouped by T for lo/hi, p15 off==15.
  Uses only 1m bars with off >= 0 (at/after T). Decision at t = T-4h, so
  the fill window [T+2m,T+14m] and fallback T+15m are strictly post-decision
  and post-execution-bar-open; they affect only fill cost at t, not the
  signal. No bar with off < 0 is touched. Pass.
- Missing handling (:105-107): `filled = (lo<lim / hi>lim) & p0.notna()`;
  `p15.fillna(p0)`; `taker_rel = where(p0.notna(), p15/p0-1, 0) +/-0.0002`.
  Missing T -> taker +/-0.0002; missing p15 -> p15:=p0. Matches spec. Pass.
- Mapping (:95, :98-114): `stats[sym].reindex(idx+4h).set_axis(idx)` puts
  execution-bar T data onto decision t; dW = Wt.diff().fillna(Wt);
  buy/sell, lim, filled, rel (-d/+d maker, taker as above),
  fee 0.0002/0.0005, c = |x|*fee + x*rel. Matches spec d in
  (0, 0.0005, 0.0010, 0.0020); d=0 reproduces v104 strict (docstring says
  so; blind d=0 == v133 hidden confirms). Pass.
- Net (:114): `(Wt*r_next).sum - cost - clip(lower=0).sum*0.00005 +
  carry_exp*carry - diff.abs*2*0.0004/1.2`, r_next = o.shift(-2)/o.shift(-1)-1,
  carry_exp = W_CARRY*CARRY_LEV*s = 0.6*s. Matches spec. Pass.
- Selection (:123-131): maker over live (idx>=ANCHORS[0]), full DD over
  live & idx<END, best = max mean_net_2021_2024, hidden = yearly[4].
  Rule text ("choose d with highest mean yearly net over 2021-2024")
  was fixed before running per docstring. Pass on causality.
- Wt path (:57-91): reuses audited v129/v125/v115/v103/v110/v104 chain
  (ext panels, train_predict per anchor, vol_predict + swap before weights,
  phased, vol_target_scale, books 0.25/0.25/0.5, s 0.15, carry). No embargo /
  feat / fitting change vs the audited v133 replication. No new forward data.
- Verdict: NO look-ahead in the fill window, fallback price, or cost path.
  The fill window and fallback price use only information at/after the
  execution bar T, which is after the decision t.

## D. Post-hoc corrections / protocol log

- Pre-open fix (logged, before Part A save): first blind run failed in
  `precompute_exec_frames` (Series.reindex index-misalignment: 142350 vs
  10950) — rewrote with numpy-aligned reindex arrays; then fixed boolean-mask
  handling (`np.asarray` for live/full/mk masks, `.to_numpy()[mk]` for hidden
  orders). No spec reinterpretation; pvol rows already matched v129 before
  the fix. Saved `replication.json` is the fixed run; tests pass 3/3.
- No spec reinterpretation after opening `v135/`. Comparison is programmatic
  bit-exact (all yearly/monthly/sharpe/DD/fills/maker diffs 0).

## E. Manifest notes / verdict

- `v135/result_manifest.json`: track B, `rejected`, `live_approved:false`,
  audit pending. Chosen 10bps (mean 31.19, maker 0.639, fullDD 16.25,
  hidden 30.51/9.69/2161) matches blind bit-exact; note "10 bps better than
  bar open (chosen on 2021-2024) ... hidden +30.51% vs +29.0% at d=0" matches
  the numbers.
- Caveat (own docstring + rule 5): the offset value (10bps) is selected on
  seen OOS years 2021-2024 (means 29.14/30.62/31.19/31.16); only the hidden
  year (+30.51 vs +29.0 at d=0, DD 9.69 vs 10.06) is prospective. Do not
  present the 10bps uplift as validated without locked-test confirmation;
  maker-rate / queue-position claims beyond OHLC+1m-through remain
  unvalidated per AGENTS.md (no queue position from OHLC alone; here 1m
  through-check only).
- Blind replication is bit-exact on all offsets/yearlies/makers/DDs and the
  chosen hidden year. No look-ahead in the limit-offset path. Audit complete;
  leader files untouched.

## Files

- `replication.json` (Part A, blind), `replicate_v135.py`,
  `tests/test_v135_audit.py` pass 3/3.
