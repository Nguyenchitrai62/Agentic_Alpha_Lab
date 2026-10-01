# Study B: a second, independent dip stream with a learned filter (dev years only; read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Why: the largest gains of this project came from NEW return streams. v289 showed a 12h dip stream (bid 3-4 sigma_12h below the 12h open) is positive
without stops in every dev year, but the mandatory stops (3 sigma touch) made it negative in 2022-23 and wide stops left only ~+8%/year per 1% risk.
Since then a learned filter on POOLED multi-coin experience (v293-v301) turned the 4h dip rungs into the best layer (size / take-profit agents trained on
~38k rungs of 35 coins). Test whether the same recipe makes a 12h (and 1d) dip stream strong enough to be worth adding.
Write only under `research/diagnostics/second_sleeve/` (script, json, SUMMARY.md <= 30 lines). Do not edit leader files, engine files, registries.
LOOK ONLY AT 2021-09-24 .. 2025-09-24; training rows of a year Y use only fills that EXITED before Y - 7 days; the 2020-08..2021-09 data are
training-only. Never compute a statistic for dates >= 2025-09-24.

Data: Binance USD-M 1m klines. Majors: `data/raw/majors_intraday_20260924/<SYM>_1m_<year>.parquet` and `data/raw/btc_intraday_20260924/klines_1m_<year>.parquet`;
alts: `data/raw/alts_intraday_20260926/` and `data/raw/alts2020_intraday_20260930/` (the 35-coin universe of research/parallel/rounds/parallel-20260906-r2/v294:
`v294.universe()`; alts are training-only, trade the five majors only). Reuse `research/diagnostics/daily_dip/account2.py` (12h dip account simulator with
touch / close5 stops) and `research/parallel/rounds/parallel-20260906-r2/v293/v293_pooled_exit_agent.py` (`Asset`, `fills_of` standalone dip replica, the seven
state features at minute f-1) as templates; adapt the periods to 720 and 1440 minutes (sigma_P = std of the last 30 CLOSED periods' close-to-close log returns,
shifted so only closed periods count; periods aligned at 00:00 / 12:00 UTC).

Structure (executable under the user's rules): resting limit bids at O x exp(-k sigma_P), k in (2.5, 3, 3.5, 4), placed at minute 5, valid until minute P-16,
fills only on a 1m trade-through, maker 0.0002; stop = the bot closes the position when a clock 5-minute block closes below L x exp(-4 sigma_P) (market,
taker 0.00055, at the next minute open) plus a native touch stop at L x exp(-8 sigma_P); take-profit limit at L x exp(+1 sigma_P) (maker); otherwise exit at
the next period open (taker); funding 0.0001 per 00 / 08 / 16 UTC settlement held; stop-first when a minute touches both.

Experiments (fix before running):
 E1 for P in (720, 1440): pooled rung table (all 35 coins): features = the seven v293 state features computed with the period's own windows + hour,
    label = net return of the rung under the structure above; walk-forward HGB (depth 3, lr 0.05, 200 iter, min leaf 200), cross-fitted even / odd periods.
 E2 policy per P: size x1.5 if both halves predict > 2 mu, x0.5 if both < 0, x0 if both < -mu (skip), else x1; report on the FIVE MAJORS only per dev
    year: rung count, win rate, mean net per notional, net / DD of a sub-account risking 1% of equity per rung at the 4 sigma stop (notional = 0.01 E / (4 sigma)),
    both for the unfiltered baseline and the policy; the account's 1m-low-marked DD.
 E3 daily-PnL correlation of the policy sub-account with the 4h G2 pipeline: reproduce G2 as in `docs/opencode/OPENCODE_STUDY_G2_DD.md` (v301 `build_hooks`,
    budget 0.26) and report the correlation of daily PnL and the dev4 / DD of the blend (1 - x) G2 + x sub-account for x in (0.15, 0.25, 0.35) with monthly
    rebalancing (indicative only).

Output: JSON + SUMMARY.md with a plain verdict: is the filtered 12h / 1d stream positive in every dev year with a DD small enough to matter, and does the
blend beat G2 alone on dev4 at the same or lower dev DD? State the number of stopped rungs, the skipped share and any look-ahead check you made.
