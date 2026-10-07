# oc_carrymargin REPORT — one-Bybit-UTA margin usage: G2 + carry f=0.25

Question: does G2 (book + dip ladder, `--dip-gross-cap 2.0`) + the frozen
quarterly carry sleeve (long spot + short quarterly, f=0.25 per coin BTC/ETH)
fit in ONE Bybit UTA without borrow? Repro:
`research/tournament/oc_carrymargin/compute_carrymargin.py` (one process,
hourly, 43,824 hours 2021-09-24 00:00 .. 2026-09-23 23:00 UTC, no 1m, no
engine reruns, no network) + `tests/test_oc_carrymargin.py`. All five years
are research data. Definitions fixed before results; post-hoc changes: none.

## Method (frozen inputs, nothing refit)

- G2 legs rebuilt HOURLY from stored `oc_kpi_g2` events/barsum s=0..3 with
  the exact `oc_margin` q-units math (book flats zeroed, dip FIFO,
  Hedge-Mode gross = |book_net| + |dip_net| per coin), `hourly_ext` 1h
  marks (causal: last bar strictly before H), equity ffill. Recon vs barsum
  `gross_book`: median 0.00120/0.00151/0.00207/0.00207, max
  0.5137/0.3230/0.4731/0.7058 per phase — rebuild OK (same to the digit as
  `oc_utamargin`). `v421`/`v422_runs.pkl` G2 equity verified bit-identical
  to barsum (both True).
- Carry: 33 frozen `oc_cashcarry` pairs verbatim; legs = f x total mix
  equity at entry hour (`oc_carrycombo` convention), held to delivery;
  spot via `hourly_ext` proxy, shorts via `qbasis_20261003` um_ 1h (causal).
- UTA math: IM_perp = G2 gross / 5 (bot account leverage 5x/coin,
  `BOT_RUNBOOK_VI.md` s1; `oc_margin`: minimum never-blocking at cap 2.0)
  + IM_carry = short / 10 BASE (`BOT_RUNBOOK_VI.md` s1: carry short 10x,
  spot-hedged); side row short / 5 (conservative, `oc_utamargin`
  convention). Spot needs no IM (collateral). Balance = Eq_tot −
  haircut x spot_val. BASE haircut 5% BTC/ETH (Bybit UTA help-center
  BTC/ETH 95% base tier via `oc_carrycombo` REPORT s3 + `oc_utamargin`
  haircut_src; < 10k stays base). STRESS 10% (assignment-ordered).
  Denominator "equity" = Eq_tot = Eq_mix + carry MtM (one UTA).
  Blocked convention IM > 95%, tight > 80% (`oc_margin`/`oc_utamargin`).

## Results (43,824 hours; max / p99 / share > 80% / share > 95%)

| row | max | p99 | > 80% | > 95% |
|---|---|---|---|---|
| G2 alone (IM/Eq) | 0.5698 | 0.2601 | 0 (0.0%) | 0 (0.0%) |
| G2+carry f=0.25 IM/Eq_tot (base) | 0.6405 | 0.2983 | 0 (0.0%) | 0 (0.0%) |
| G2+carry f=0.25 IM/bal 5% (base) | 0.6733 | 0.3082 | 0 (0.0%) | 0 (0.0%) |
| G2+carry f=0.25 IM/bal 10% (stress) | 0.7097 | 0.3198 | 0 (0.0%) | 0 (0.0%) |
| G2+carry f=0.25 IM/bal 5%, carry/5x (conservative) | 0.7751 | 0.3678 | 0 (0.0%) | 0 (0.0%) |

- Worst 5 hours by IM/bal base: 2025-09-25 18:00 (0.6733; Eq 0.6405;
  G 2.8492 + short 0.9681, spot 0.9758), 2025-09-25 19:00 (0.6137),
  2025-09-22 06:00 (0.5623), 2025-07-24 07:00 (0.5223),
  2025-07-23 14:00 (0.5072). Full rows in results.json.
- Borrow check (spot cash): max spot cost / Eq_tot 0.9582, min headroom
  +0.0418, ZERO hours with spot cost > equity — no structural USDT borrow
  at f=0.25 (same 95.82% as `oc_utamargin`).
- Cross-check: the conservative row (carry/5x, haircut 5%) reproduces
  `oc_utamargin` f=0.25 EXACTLY (max 0.7751, same worst hour, same gross
  2.8492, same spot 95.82%) on an independent grid — the rebuild is sound.

## Verdict (tiếng Việt, 3 dòng)

G2 + carry f=0.25 vừa một Bybit UTA, không cần vay: dùng margin cao nhất
~67% vốn (stress haircut 10% ~71%), 0/43.824 giờ vượt 80% hay 95%, tiền mặt
mua spot không giờ nào vượt vốn (tối đa 95,8%).
Giờ căng nhất 2025-09-25 18:00 (vùng đáy G2) vẫn còn ~33% đệm; hàng bảo thủ
(short/5x) khớp y hệt oc_utamargin (77,51%).
Giữ cấu hình runbook (perps 5x, carry short 10x, cross/hedge, f=0.25);
không nâng f chung UTA — f=0.50 đã chạm trần ở nghiên cứu trước.
