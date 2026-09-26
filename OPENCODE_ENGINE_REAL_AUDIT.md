# engine_real blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Write only under `research/parallel/rounds/parallel-20260906-r2/engine_real_audit/` and `tests/test_engine_real_audit.py`.
Do NOT open `engine_real/` until part A is saved (`replication.json`). This engine becomes the evaluation standard, so
re-implement it independently (you may import only `v144/v144_deploy_v3.py` for `v99` constants W_BOOKS=0.8,
W_CARRY=0.2, CARRY_LEV=3, CAP=2, `v110.START/END/summarize`, `v135.bar_stats`, and `scripts/carry_lab.py` for
`load`, `position`, `GRID`, `SYMS`, `ANCHORS`, `EMBARGO_DAYS`).
Inputs: books = `artifacts/research/engine_real/books_v154.parquet` (index t = 4h bar close decision time, columns =
symbols, already audited v154 books), opens = `artifacts/research/engine_real/opens_v154.parquet` (4h opens per symbol).
A: sequential loop over bars i (4h, PD = 6 per day), target 0.25, governor on:
- o = opens reindexed to the books index; r_next[i] = o[i+2]/o[i+1] - 1 per symbol (0 if NaN).
- realized[i] = 0.8 * sum_j books[i-2, j] * (o[i,j]/o[i-1,j] - 1) + 0.6 * carry[i-1]; vol = rolling std over 360 bars
  (min 120) * sqrt(6*365); s = min(0.25/vol, 2) (1 if NaN).
- g[i] = clip((0.20 - (1 - eq[i-2]/max(eq over the 540 bars ending at i-2)))/0.10, 0, 1) for i >= 2, else 1.
- live = START <= t < END; w = 0.8 * s * books[i] * g (0 if not live); c = 0.6 * s * g (0 if not live).
- Carry sleeve (real): per symbol, rp/rs = next-bar perp/spot open-to-open returns (shift -2 over shift -1), fund =
  carry_lab funding bucket (`d["rate"]`, 4h-floored sums) shifted by -2; ret(pos) = (pos*(fund + rs - rp) -
  |diff(pos)| * (0.001 + 0.0005)) / 1.2; parameters per anchor = argmax over GRID of mean/std of ret on
  [first bar + 30 d, anchor - EMBARGO_DAYS]; take that config's ret and pos on [anchor, anchor + 365 d). carry[i] =
  mean over the 5 symbols of ret, expo[i] = mean of pos (missing -> 0).
- Budget: if c*expo + sum|w|/5 > 0.95: c = min(c, max(0, (0.95 - sum|w|/5)/max(expo, 1e-9))); if sum|w|/5 > 0.95
  scale w to sum|w| = 0.95*5.
- Min notional at 10,000 USDT * eq[i-1]: for each symbol with w != 0 and |w - prev_w| * equity < (BTCUSDT 100,
  ETHUSDT 20, others 5) keep prev_w.
- Execution (v135): per symbol, st = bar_stats(sym) reindexed to t + 4h; p0, lo, hi, p15 (p15 NaN -> p0);
  buy maker if lo < p0*(1-0.001): fee 0.0002, rel -0.001; else fee 0.0005, rel p15/p0 - 1 + 0.0002; sell maker if
  hi > p0*(1+0.001): fee 0.0002, rel +0.001; else fee 0.0005, rel p15/p0 - 1 - 0.0002 (no p0 -> taker with rel 0 +/- 0.0002).
  exec = sum(|dw| * fee + dw * rel).
- Funding: per symbol, `data/raw/xs_universe_20260924/<SYM>_funding.parquet` fundingRate summed by fundingTime
  floored to 4h, reindexed to the books index, shifted -2; funding = -sum(w * f).
- carry_cost = |c - prev_c| / 1.2 * expo * 0.0015. net = sum(w*r_next) - exec + funding + c*carry - carry_cost.
- Intrabar bound: eq_lo[i] = eq[i-1] * (1 + sum_j (w>0 ? w*(low/o[i+1]-1) : w*(high/o[i+1]-1)) - exec + min(funding, 0))
  with low/high of the 4h kline of bar i+1 (`<SYM>_4h.parquet`); report max over the live span of 1 - eq_lo/running
  max of eq (both normalised to the first live bar).
Also the same loop with ALL realism off (funding = -0.00005 * sum(max(w,0)); carry = artifacts/research/carry/
carry_oos_fee0.0004.parquet with expo = 1 and carry_cost = |c - prev_c| * 2 * 0.0004 / 1.2; no budget, no min
notional): it must equal v154 (3.515 %/month, full-path DD 19.15). Save `replication.json` (monthly, yearly,
full-path DD, intrabar bound, component sums).
B: compare with `engine_real/engine_real_v154_result.json` (return > 1pp, DD > 0.5pp must be explained), review
`engine_real/engine_real.py` for timing errors (funding settlement vs holding, look-ahead), and independently check
funding timing against Binance docs semantics (a position open at the settlement timestamp pays/receives). Write
COMPARISON.md with a verdict. Do not edit leader files.
