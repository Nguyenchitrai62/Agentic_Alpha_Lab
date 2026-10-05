# Kronos zero-shot worker report (saved by the leader from the worker's hand-back, 2026-10-05)
Kronos-small (Tokenizer-base, HF weights, zero-shot, context 400 x 4h bars, 6-bar horizon, 64 paths, T 1.0, top_p 0.9), every 4h bar of the
5 majors 2020-08..2025-09-23 (55,735 forecasts, 33 min on the GTX1650; fast sampler checked vs the reference code). Kronos-base on every 2nd
bar: no better.
BOOK: no directional value (7-day IC of er1 / er6 negative in 3-4 of 4 years; next-bar er1 IC +0.037/+0.032/+0.027/+0.013 < naive 1-bar
reversal ~0.043). Vol forecasting real (rng1 IC 0.19-0.28 vs 360-bar sigma 0.05-0.12) but only +0.01..+0.06 over a 42-bar trailing std.
DIP (harness.score): V1 size_dep x1.5 / x0.5 on Kronos low1 quintiles +0.111 / +0.924 / +1.453 / +0.034 = +2.52 (graduates, better worst day);
V2 HGB bar-open + Kronos +0.30 (no); V3 control bar-open only +0.09 (no). Post-hoc controls (disclosed): vol ratio +1.27, 24h range +0.61,
Kronos low1 residual after vol ratio / last return +1.49 (all years > 0).
CAVEAT: Kronos was pretrained (released 2025-08) on 12B candles from 45 exchanges -> the dev years are almost surely in its pretraining data;
every Kronos edge shrinks toward 2024. Leader decision: not engine-tested; Kronos dip tilt only as a prospective (post-2025-09) check.
