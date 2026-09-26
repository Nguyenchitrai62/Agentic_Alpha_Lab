# v135 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Write only under `research/parallel/rounds/parallel-20260906-r2/v135_audit/` and `tests/test_v135_audit.py`.
Base: your audited v132_v133 replication (v133 weights Wt = 0.8*s*books, carry, v104 cost path). Do NOT open v135/ until
part A is saved (`replication.json`).
A: 1m klines per major: BTC data/raw/btc_intraday_20260924/klines_1m_20*.parquet, others
data/raw/majors_intraday_20260924/{SYM}_1m_20*.parquet (dedup open_time). For each 4h execution bar T (floor 4h):
p0 = 1m open at minute 0; lo/hi = min low / max high over 1m bars with minute offset 2..14; p15 = 1m open at minute 15.
Orders dW = Wt.diff() (first row = Wt) decided at t execute at T = t + 4h. For offset d in (0, 5, 10, 20) bps: buy limit
p0*(1-d), sell limit p0*(1+d); maker (fee 0.0002, price = limit, rel = -d for buys / +d for sells) if lo < limit (buy) or
hi > limit (sell) and p0 exists; else taker fee 0.0005 with rel = p15/p0 - 1 (p15 := p0 if missing) +0.0002 for buys /
-0.0002 for sells; missing p0 -> taker with rel = +/-0.0002. cost = |dW|*fee + dW*rel summed over assets. net = sum(Wt *
(open[t+2]/open[t+1]-1)) - cost - 0.00005*long gross + 0.6*s*carry - |diff(0.6*s)|*2*0.0004/1.2 (first diff 0). Yearly stats
per anchor, maker rate over live orders (t >= 2021-09-24), full-path DD over [2021-09-24, +1825 days). Choose the d with the
highest mean net over the first four anchor years; report its hidden year.
Save `replication.json`, compare with v135/v135_result.json (explain return diff > 1pp, DD diff > 0.5pp, maker-rate diff >
0.01), audit v135_limit_offset.py for look-ahead (the fill window and fallback price must not use information before the
execution bar's decision), write COMPARISON.md. Do not edit leader files.
