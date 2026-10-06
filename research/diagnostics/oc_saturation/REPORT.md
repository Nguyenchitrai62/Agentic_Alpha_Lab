# oc_saturation REPORT — why dip-size return saturates near 5.9 %/mo (2026-10-06)

DIAGNOSTIC (no selection, no PROMISING flag). Question: rows R2B1D20B11 (5.894 / DD 21.21),
G2K20 (5.874 / 17.79), R2B1D17BFV2 (5.711 / 24.08) — more dip multiplier does not add return.
For each row (D13BF/D17BF/G2/D20/G2K20) and year: rung P&L by depth, constraint cut/skip shares,
realised vs nominal size, P&L per unit notional, book's share. All five walk-forward years are
research data (anchors 2021-09-24..2025-09-24); findings need prospective validation.

## Setup

Rows (configs read off the version workers; engine = engine_user trade mode, win_start=5):

| row | version | kd | risk budget 0.26·kd | gross cap G | bear books | book_mult |
|---|---|---|---|---|---|---|
| D13BF | oc_d13robust (kd1.3 bear) | 1.3 | 0.338 | none | yes | 1.0 |
| D17BF | v411 R2B1D17BF | 1.7 | 0.442 | none | yes | 1.0 |
| G2 | v421 R2B1D17BFG2 | 1.7 | 0.442 | 2.0 | yes | 1.0 |
| D20 | v407 R2B1D20 | 2.0 | 0.520 | none | no | 1.0 |
| G2K20 | v422 G2K20 | 2.0 | 0.520 | 2.0 | yes | 1.0 |

All: B1 inv-rule 1/(1+n) at F=2.5, ladder 2.5/3/3.5/4/5σ, R2 size/TP agents, close5+8σ stops.
Rung evidence: D17BF pooled 4 shifts (oc_kpi events, 21389 rungs) + s=0 n/fill_min/attrib
(oc_ddanat17); G2K20 pooled 4 shifts (ONE allowed rerun, run_g2k20.py via heavy_slot,
equity bit-matches v422_runs.pkl to rel diff 0.0 on all 10944 bars x4 shifts, 21163 rungs).
D13BF/D20/G2 have no stored rung events (counts/wins only) — their depth splits are INFERRED
via the measured kd-invariance below, labelled as such. No 1m data loaded here; analysis RAM MBs.

## 1. The saturation ladder (stored rows: 5y geometric %/mo R / max yearly DD)

| row | R | W | DD | full-path DD | years (R per anchor 21..25) |
|---|---|---|---|---|---|
| D13BF | 4.971 | — | 14.98 | 14.86 | 2.485 / 3.286 / 4.975 / 9.526 / 4.723 |
| D17BF | 5.425 | 2.831 | 18.33 | 16.90 | 2.831 / 3.505 / 4.669 / 11.270 / 5.060 |
| G2 | 5.410 | 2.588 | 16.91 | 16.82 | 2.588 / 3.282 / 6.045 / 10.677 / 4.648 |
| D20 | 5.779 | 2.515 | 20.95 | 18.89 | 2.515 / 3.924 / 4.997 / 12.534 / 5.203 |
| G2K20 | 5.874 | 2.832 | 17.79 | 17.69 | 2.832 / 3.272 / 7.149 / 11.644 / 4.716 |

Marginals (same-bear/cap pairs are clean): D17BF->D18BF +0.139 R / +0.89 DD per 0.1 kd;
G2->G2K20 +0.155 R / +0.29 DD per 0.1 kd; D17BF->G2 (cap at kd1.7) -0.015 R / -1.42 DD;
D20->D20B11 (book x1.1) +0.115 R / +0.26 DD; D17BF->D17BFV2 (dvol tilt) +0.286 R / +5.75 DD.
Uncapped size buys return at ~1 DD per 0.15 R; capped size at ~1 DD per 0.5 R; the tilt route
explodes DD for less return than D20B11. The ceiling is the DD wall, not a return wall:
D20B11's extra return (+0.02 over G2K20) costs DD 21.21, over the gate.

## 2. Rung P&L by depth and year (measured: exit anchor year, pooled 4 shifts)

D17BF pnl / gross / per-unit (weight·ret sums):

| depth | n | pnl | gross | pu | pu by year 21/22/23/24/25 |
|---|---|---|---|---|---|
| 2.5 | 8649 | 2.23 | 1154.4 | 0.0019 | .0020/.0009/.0020/.0036/.0006 |
| 3.0 | 5437 | 1.93 | 625.1 | 0.0031 | .0023/.0025/.0022/.0058/.0019 |
| 3.5 | 3592 | 1.38 | 349.9 | 0.0040 | .0031/.0024/.0022/.0081/.0031 |
| 4.0 | 2454 | 1.00 | 212.6 | 0.0047 | .0062/.0009/.0024/.0098/.0045 |
| 5.0 | 1257 | 0.53 | 90.6 | 0.0058 | .0069/.0045/.0036/.0114/.0047 |

G2K20 pnl / gross / per-unit:

| depth | n | pnl | gross | pu | pu by year 21/22/23/24/25 |
|---|---|---|---|---|---|
| 2.5 | 8843 | 2.81 | 1392.0 | 0.0020 | — (year table below) |
| 3.0 | 5468 | 2.25 | 727.9 | 0.0031 | |
| 3.5 | 3469 | 1.50 | 379.2 | 0.0040 | |
| 4.0 | 2277 | 0.92 | 209.9 | 0.0044 | |
| 5.0 | 1106 | 0.40 | 79.9 | 0.0051 | |

Yearly per-unit (all depths): D17BF .0027/.0017/.0022/.0055/.0017 vs
G2K20 .0024/.0015/.0029/.0052/.0013 — same shape every year (2024 fat, 2022/2025 thin).
Pooled per-unit: 0.0029 (D17BF) vs 0.0028 (G2K20). **Per-unit edge is invariant to kd:
scaling size multiplies notional, it does not move the edge.** Shallow 2.5σ rungs hold 51%
of gross at 0.19-0.20 %/unit (timeout-heavy: 53% timeout at 2.5σ vs 19% at 5σ; TP share
44% -> 75%); deep rungs earn 2-3x per unit but only 12% of gross. Exit mix pooled:
D17BF TP/timeout/SL ≈ 50/46/4 %, G2K20 ≈ 50/46/4 % — unchanged by kd.
Cascade (s=0, fill_min terciles): early pu 0.0053/0.0052, mid 0.0038/0.0034,
late 0.0020/0.0019 (D17BF/G2K20) — late/cascade fills earn ~40% of early fills at both sizes.
Per-unit by B1 n (s=0): flat 0.0033-0.0053, no trend — B1 cuts size, not edge.

## 3. Which constraint binds (measured + code refs engine_user.py)

- B1 1/(1+n): binds on 55% of fills (n>=1; n dist s=0: 0:45%, 1:18%, 2:14%, 3:12%, 4:11%),
  removes 34.8% (D17BF) / 34.5% (G2K20) of dip notional at flat per-unit edge — a proportional
  return-for-concentration trade, kd-invariant by construction (n, mult use no kd).
- Risk budget 0.26·k·kd (simulate lines 688-698): BOTH budget and nominal rung size scale with
  kd (rn = s·g·size_mult·0.25/4/1.657 · kd·B1·base), so concurrent-rung capacity is kd-INVARIANT
  by algebra — raising kd cannot buy more concurrency, only bigger rungs. Realised avg
  concurrent dip notional is ~1% of equity (oc_kpi) vs budgets 0.44-0.52: binds only in flush
  clusters (max 25 concurrent rungs). Combined cap+budget skips ≈ 226 fills (~1% G2K20 vs D17BF).
- Gross cap G=2.0 (lines 699-703): truncates the concurrent tail 6.29 -> 2.00 max; only
  1.2% of G2K20 fills arrive near the cap (C+w > 1.8) vs 2.1% over it uncapped — a 1-2%
  mass trim buying -1.42 DD for -0.015 R (D17BF->G2).
- Realised size scales exactly with kd: w/kd mean 0.0708 vs 0.0702, median 0.0530 vs 0.0517 —
  no hidden compression; the engine delivers the ordered size until a cap/budget clips it.
- Min notional: gates BOOK entries only (line 537); 0 in-path skips at 10k (oc_capscale);
  rungs have no minimum check. Cross-margin "95% budget": no such cut on the rung path —
  only the MMR-1% liquidation counter (0 liqs all shifts); the governor g (lines 497-513)
  is the stealth cap, multiplying book AND dip sizes down as trailing DD rises (feedback
  that eats kd gains at high DD — qualitative, mean_g not in stored rows).

## 4. Book's share (attrib fractions of bar-start equity, summed per year)

D17BF s=0 dip share: 84/40/70/55/35% (5y flow: book 1.76, dip 2.47, dip 58%).
G2K20 pooled dip share: 83/44/66/62/28% (book 1.47, sleeve 1.97, dip 57%).
The dip carries ~3/5 of flow P&L; the book carries crash years (2022/2025 dip thin:
pu 0.0015-0.0017). D13BF/D20/G2 book shares unmeasured (no stored attrib) — books are
identical across kd rows except bear-halving (all but D20) and bm (D20B11 x1.1), and the
+10% book bump bought +0.115 R for +0.26 DD: the book leg is DD-cheap return.

## Verdict

Saturation is MECHANICAL, not economic — the per-unit dip edge does not fall with size
(pooled 0.0029 -> 0.0028; identical depth/year/cascade shapes at kd 1.7 vs 2.0). What falls
is DD-efficiency: return is mean-based (scales ~linearly with kd) while drawdown is
max/concentration-based (scales super-linearly), and three mechanical trims cap the kd
gain: B1 (-35% notional, proportional R cost), the G cap (tail truncation, nearly free),
and governor feedback (eats size exactly when DD is high). The extra size does NOT land in
the worst minutes (fill timing is kd-invariant; late fills are thin at every size) — it
lands proportionally everywhere, and the concentrated tail is what the DD gate rejects.
Under DD <= 20 the frontier bends at ~5.9 %/mo; uncapped size past kd 2.0 converts into DD,
not R (V2: +0.29 R for +5.75 DD).

## Ket luan (tieng Viet)

Viec tang dip multiplier (kd) KHONG lam giam edge tren moi don vi notional — edge giu
nguyen o moi do sau, moi nam va moi cum cascade khi kd tang tu 1.7 len 2.0. Su bao hoa
loi nhuan la van de CO HOC: loi nhuan tang tuyen tinh theo kd trong khi drawdown (thong ke
max/tap trung) tang nhanh hon, cong voi ba rao can cap: B1 cat ~35% notional, gross cap
cat duoi tap trung (re, hieu qua), va governor tu giam size khi DD cao. Vi vay, de tang
return ma khong tang DD, dung tang kd dong deu — cac huong dang thu (can kiem chung
walk-forward): (a) giu gross cap (da chung minh -1.4 DD voi gia -0.015 R); (b) chuyen
notional tu rung nong (2.5σ, edge 0.19%/don vi, timeout 53%) sang rung sau (5σ, edge
0.51-0.58%/don vi, TP 75%) — neu co the ma khong doi tan suat fill; (c) bo fill muon
trong cascade (edge chi ~40% so voi fill som); (d) cai thien exit timeout (44-46% so
exit, chiu taker + funding tra) thay vi tang size; (e) tang book (book x1.1 cho +0.115 R
chi voi +0.26 DD — re DD nhat). Tat ca deu la quan sat hoi cuu, bat buoc phai kiem chung
walk-forward truoc khi dung.

## Caveats / post-hoc log

1. No post-hoc change to definitions: rung pairing (FIFO/symbol), year = exit anchor year,
   cap sweep (exits-first ties), B1 cut formula were fixed in oc_saturation.py before numbers.
2. Depth/year rung splits are MEASURED for D17BF + G2K20 only (the one allowed rerun);
   D13BF/D20/G2 depth rows are inferred from kd-invariance, not measured — the one-row rule
   (assignment) forbids completing them with new runs.
3. Attrib yearly sums are flow attribution (fractions of bar-start equity), not geometric R;
   only shares are interpreted. D17BF attrib is shift 0; G2K20 is the shift mean.
4. Concurrent-notional sweep uses realised (post-cut) weights, so G2K20's in-engine cut-to-room
   amounts are unobserved; reported incidence (fills near cap) bounds, not exact cut mass.
5. All five years are research data; the D13BF baseline (oc_d13robust) and G2 years (v421)
   are reused caches, not new runs. Repro: research/diagnostics/oc_saturation/{run_g2k20.py,
   oc_saturation.py, results.json}; test tests/test_oc_saturation.py.

(End of report)
