# oc_carryparity REPORT — prospective parity of the frozen cash-and-carry rule

Frozen rule: `scripts/carry_paper.py` (`rule_sha256=63fa9be8…`, BTC+ETH, next
quarterly when front ≤7d else front at first availability, ENTER iff
`ln(F/S)*365/DTE ≥ 4%/yr`, quarterly delivery filter = last Friday of
Mar/Jun/Sep/Dec). Ledgers (read-only): `artifacts/bot/paper_carry/actions.jsonl`
(ledger since 2026-10-06 06:05 UTC, 1 BTC entry + 5 ETH skips + 4 BTC holds) and
`artifacts/bot/paper_d17bfg2c/actions.jsonl` (bot carry since 07:19 UTC: BTC
entry 07:19, ~134 ETH skips, ETH entry 08:17 at 4.02%/yr, BTC+ETH retry entries
09:14). Independent recomputation: public Bybit V5 hourly klines (spot +
`*-25DEC26` linear futures, 2026-10-06 UTC, no keys), causal mapping = last
CLOSED hourly bar (`open+1h ≤ T`); DTE from `delivery_ms=1798185600000`
(2026-12-25 08:00 UTC, confirmed via instruments-info). Repro:
`research/tournament/oc_carryparity/check_parity.py` → `results.json`.
Test: `tests/test_oc_carryparity.py`.

## Contract chosen

144/144 decisions name the correct front quarterly: `BTCUSDT-25DEC26` /
`ETHUSDT-25DEC26` (linear, delivery 2026-12-25, the only quarterly with
delivery > 2026-10-06 and ≤ next; weeklies `09/16/23/30OCT26` + `27NOV26`
correctly excluded by the quarterly filter). Same contract: YES everywhere.

## Basis within 0.2 pp/yr (ledger ticker-mid vs kline last-close)

56/144 within tolerance. All 88 breaches are classified `mid-vs-last`: the
quarterlies barely trade (hourly kline volume 0 in most hours 01:00–09:00,
futures close frozen at 86660.2 / 2721.04) while ticker mids move. Examples:
paper BTC 06:05 ledger 5.42% vs kline 6.04% (+0.62pp); paper ETH 08:07 ledger
3.99% vs kline 2.24% (−1.75pp); bot BTC 07:19 ledger 5.31% vs kline 7.13%
(+1.82pp). Kline `last` is stale; the ledger `mid` is the rule-correct input
(frozen rule prices from tickers). Not a rule bug.

## Enter/skip agreement

- Ledger vs kline decision: 141/144 agree. The 3 kline-side flips are the stale
  hours above (bot ETH entry 08:17 ledger-enter 4.02% vs kline-skip 2.24%; BTC
  retry 09:14 ledger-enter 5.34% vs kline-skip 3.35%; ETH retry, see below).
- Ledger vs frozen rule on its OWN mids: 143/144 agree. The single genuine
  violation is the known deviation: bot ETH retry entry 09:14:42
  (`S=2714.995, F=2737.67`, recomputed basis **3.80%/yr < 4%/yr**) entered with
  `attempt=2, retry=true`, no `ann_basis/dte` in the log line, and bot state
  keeps the stale first-entry `ann_basis=0.040184`. BTC retry at the same stamp
  recomputes to 5.34%/yr (enter, correct decision; same schema gap: no
  `ann_basis` logged). Fixed after the fact in `bot/carry.py` (retry re-checks
  the threshold, logs `carry_abandon … basis_below_threshold_on_retry`).

## Verdict

PARITY HOLDS with one known bug: same quarterly contract 144/144; first-decision
threshold logic (BTC enter, ETH skip) agrees on live mids in both the ledger
and the bot; hourly-kline exact-basis replication fails as expected on the
illiquid quarterlies (mid-vs-last, not a trading bug); the 09:14 ETH retry
entered at ~3.8%/yr below the frozen 4%/yr gate (known deviation, now gated in
code). No other enter/skip disagreement.
