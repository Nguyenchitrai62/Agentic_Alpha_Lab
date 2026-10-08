# OpenCode task oc_bybitfill - recover part of G2's Bybit-price gap with tiny venue-aware price offsets on dip TPs / rungs
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. Write ONLY `research/tournament/oc_bybitfill/` and `tests/test_oc_bybitfill.py`.
Print progress every 10 minutes. Write PLAN.md (frozen) before any outcome. Engine via heavy_slot (RAM tight: one engine job at a time).

## Why
research/tournament/oc_bybitgap: G2 loses ~0.5 %/month on Bybit prices (5y 5.410 -> 4.883) and the gap rides the dip ladder: fewer rung fills
(-25 / -57) and fewer take-profit fills (-34 / -59) because Bybit 1m wicks are shallower; the engine only fills a limit on a strict trade-through.
The owner trades on Bybit. A TP placed a few bps lower fills more often for a tiny price give-up; a rung a few bps shallower fills more often.

## Variants (exactly two; all on Bybit prices = the S5 friction of research/parallel/rounds/parallel-20260906-r2 v421_audit / oc_c2bybit)
TPm3: every dip take-profit limit 3 bps below the G2 TP price (still a maker limit). RUNp3: every dip rung limit 3 bps ABOVE the G2 rung
price (shallower) plus TPm3. Everything else exactly G2. Reproduce REF_S5 (5y 4.883 / full DD 18.09, per-year table of oc_c2bybit) to the
digit first.
## Report
Dev4 on Bybit prices (2021 is a short window from 2021-11-15, labelled), robust pick among REF_S5 / TPm3 / RUNp3 on dev4 ONLY, post-release
year scored ONCE (labelled), 5y, full-path DD, fill / TP counts vs REF_S5; also the same two variants on Binance prices as a side row (labelled,
not for selection). Vietnamese 3-line verdict: how much of the Bybit gap does each recover?
