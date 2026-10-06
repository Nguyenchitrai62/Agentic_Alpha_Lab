# oc_outage REPORT (2026-10-06; PLAN pre-registered before any outcome)

## Setup

Dip-sleeve outage overlay on the validated 4-phase D0+B1 ledger
(`oc_usdtdip/panel.parquet`: 22,312 fills, phases 0..3, majors x R2 depths
2.5/3/3.5/4/5, B1 sizes w=1/(1+n), D0 exits; phase-0 raw sums reproduce the
oc_dipexit/oc_b1deeper refs to 6 decimals: 2.388/0.183/3.810/2.579/0.712).
While the bot is offline: no NEW rung bids (a bar whose T+16 falls in an
outage is missed; resting bids otherwise fill exactly as base), native TP
limit + native 8-sigma backstop keep working, close5 4-sigma software stop
and time exit fire late at the first online minute's open (native
TP/backstop touches before the comeback win instead). Maker 0.0002 /
taker 0.00055; funding 0.0001 on settling bars held past the bar end.
Scenarios per anchor year (seeds 101/102/103; adversarial deterministic):
(a) weekly-2h (52x120m), (b) monthly-6h (12x360m), (c) quarterly-24h
(4x1440m), (d) adversarial-10h (10 lowest mean-majors 1h returns of the
year). Units below are size-weighted w*y sums (B1 sizes); 4-phase means per
year; 5y = sum of yearly 4-phase-means (base 5y = 7.718; pooled full-path
base sum/DD = 30.873/3.127). Loss = base - scenario (positive = outage
cost). All 5 years are research data: diagnostic, needs prospective
confirmation (disclosed vs RULES.md hidden-year rule).

## Per-scenario vs base (5y 4-phase-mean sums, pooled DD, loss split)

| scenario | downtime/5y | scen sum | loss (vs 7.718) | pooled DD | missed | late | share miss/late |
|---|---|---|---|---|---|---|---|
| (a) weekly 2h | 520h | 7.530 | +0.188 (2.4%) | 3.127 (same) | +0.265 | -0.077 | 141% / -41% |
| (b) monthly 6h | 360h | 7.584 | +0.134 (1.7%) | 3.138 (+0.01) | +0.080 | +0.054 | 59% / 41% |
| (c) quarterly 24h | 480h | 7.647 | +0.072 (0.9%) | 3.138 (+0.01) | +0.098 | -0.027 | 137% / -37% |
| (d) adversarial 10h | 50h | 8.086 | -0.367 (GAIN 4.8%) | 3.554 (+0.43) | -1.492 | +1.125 | 406% / -306% |

## Per-year 4-phase-mean dS vs base (loss positive) and DD

| year | base S/DD | (a) dS/DD | (b) dS/DD | (c) dS/DD | (d) dS/DD |
|---|---|---|---|---|---|
| 2021 | 0.911/0.856 | -0.134/0.881 | 0.000/0.856 | -0.019/0.856 | -0.383/1.114 |
| 2022 | 0.833/0.951 | -0.001/0.951 | -0.014/0.952 | -0.006/0.952 | +0.627/0.692 |
| 2023 | 2.100/0.800 | -0.030/0.810 | -0.090/0.800 | -0.114/0.800 | +0.243/0.604 |
| 2024 | 3.197/0.355 | -0.003/0.355 | -0.002/0.355 | +0.014/0.355 | -0.222/0.322 |
| 2025 | 0.677/0.607 | -0.021/0.617 | -0.029/0.607 | +0.053/0.607 | +0.103/0.553 |

Notes: (b) 2021 is exactly 0 -- the 12 seeded 6h windows (seed 102) all fell
in quiet hours with zero placements and zero exits (verified in coordinates;
fills/exits cluster in flushes, so a clean sweep is ordinary seed luck, not
a bug). (d) gains in 3/5 years (dodged flush fills) but 2021 loses -0.383
with DD 0.856 -> 1.114 and worst day -0.740 -> -0.945.

## Worst single outage episode per scenario

| scenario | interval (UTC) | loss | missed / late | fills missed / delayed |
|---|---|---|---|---|
| (a) weekly 2h | 2021-12-05 12:41 +2h | +0.201 | +0.201 / 0.000 | 14 / 2 |
| (b) monthly 6h | 2024-03-18 22:28 +6h | +0.145 | +0.146 / -0.001 | 41 / 7 |
| (c) quarterly 24h | 2023-11-12 20:58 +24h | +0.293 | +0.293 / 0.000 | 25 / 0 |
| (d) adversarial | 2021-12-04 05:00 +1h (flash crash) | +0.684 | -0.605 / +1.288 | 25 / 70 |

The adversarial worst hour is the whole story in miniature: offline through
the 2021-12-04 flash crash dodged 25 fills that would have lost (-0.605,
i.e. missing them HELPED) but 70 already-open rungs lost their 4-sigma
software stop and bled an extra +1.288 before the comeback market exit
(the 8-sigma native backstop stayed, the 4-sigma close5 did not). Net for
that one hour: +0.684 of loss (~9% of the 5y base sum) and the year's DD
+0.26 and worst day -0.21.

## Reading the split

- Random outages (a/b/c) cost 1-2.5% of the 5y dip sum; the cost is
  dominated by MISSED bids (59-141% of the loss): fills that would have won
  never happen. Late exits average ~0 (sometimes slightly negative = late
  stops accidentally dodge whipsaws).
- Adversarial timing flips both signs: missing flush fills DODGES losers
  (-1.492) while late stops on already-open rungs BLEED (+1.125). Net is a
  small gain (+0.367) at a large tail cost (pooled DD +0.43, worst day
  -0.21 in 2021). Never read the +0.367 as "outages are good": it is the
  artifact of dodging entries while paying 4-sigma of extra slip on every
  open rung, and it comes with the worst drawdown of any scenario.
- Frequency matters more than duration: 52x2h/year (a) costs 2.6x the
  4x24h/year (c) for similar total downtime (520h vs 480h), because 52
  draws/year almost always clip an active episode while 4 draws usually land
  in calm water.

## Huong dan van hanh (plain Vietnamese)

- Mat bot 2h/tuan, 6h/thang hay 24h/quy trong gio yen binh: TON THAT NHO
  (1-2.5% lai dip 5 nam, DD gan nhu khong doi). Ke hoach bao tri dinh ky
  cu lam binh thuong, khong can hoan.
- Mat bot DUNG LUC XA MANH (flash crash, vi du 2021-12-04): MOI VI TRI DANG
  MO bi tre stop 4-sigma, mat them ~4-sigma truot gia moi rung; 1 gio xau
  nhat lich su ton +0.68 (gan 9% lai dip 5 nam) va day DD nam len +0.26.
  Day la rui ro chinh, khong phai chuyen mat lenh moi.
- Runbook NEN THEM 1 quy tac cho bao tri CO KE HOACH: HUY cac bid dip dang
  cho truoc khi bao tri (cancel resting bids), xong dat lai khi bot len.
  Ly do: bid nam yen thi khong sao, nhung bid khop dung vao luc xa ma khong
  co software stop se chay mau; con thiet hai mat lenh luc yen (moi gio
  ~0.4 fill) la khong dang ke. Native TP + backstop 8-sigma tren san cu de
  yen (tu chay, khong can bot).
- Sau su co bat ngo: bot tu dong exit o phut mo dau tien khi tro lai; nguoi
  truc chi can xac nhan khong con vi the "mo ma khong stop" (unprotected) va
  khong dat them lenh tay trong gio dau tien.

## Verdict

VERDICT (diagnostic, no selection): routine outages are cheap (1-2.5% of dip
P&L, DD ~unchanged) and need no runbook change beyond cancelling resting dip
bids before PLANNED maintenance; the real risk is an outage through a flush
(single worst hour +0.68 loss, DD +0.26/+0.43), so unplanned-downtime response
should prioritize confirming every open rung still has its native backstop
and letting the comeback exits print before touching anything.

## Caveats / limits

- Dip sleeve only (book positions are not modelled; book stops are also
  native conditional-market stops per BOT_EXECUTION.md, so the same logic
  applies qualitatively, not quantitatively).
- Seeded blocks tile [anchor, anchor+365d); the leap day 2024-09-23..24 in
  Y2 carries no seeded (a/b/c) outage (0.3% of one year, conservative).
- Costs are exactly the gate costs (no extra slippage on comeback exits).
- Repro: research/tournament/oc_outage/{PLAN.md,outage_core.py,
  compute_outage.py,results.json,REPORT.md} + tests/test_oc_outage.py
  (17 tests pass); one process, peak < 0.4 GB (no heavy_slot by design).
