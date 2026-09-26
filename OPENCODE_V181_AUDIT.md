# v181 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Write only under `research/parallel/rounds/parallel-20260906-r2/v181_audit/` and `tests/test_v181_audit.py`.
Do NOT open v181/ until part A is saved (`replication.json`). Independent implementation.
Data: 1m klines `data/raw/alts_intraday_20260926/<SYM>_1m_<YYYY>.parquet` (check manifest.json and duplicates), 4h
opens and funding `data/raw/xs_universe_20260924/<SYM>_4h.parquet` / `<SYM>_funding.parquet` for DOGE, ADA, LINK, LTC,
AVAX, TRX USDT. Grid t = 4h bars 2020-02-01 .. 2026-09-23 20:00; T = t + 4h; sigma = std of 360 4h open-to-open pct
changes ending at t (min 120). For k in (2.5, 3, 3.5, 4): bid L = open(T) (1 - k sigma); filled if any 1m low in minute
offsets 16..238 of T is < L (missing minutes never fill); r = open(T+4h) (1 - s_out) / L - 1 - maker - taker - funding
settled at T+4h (fundingRate summed by fundingTime floored to 4h), s_out = max(0.0002, 0.25 (high-low)/open of minute 0
of T+4h) + extra. Normal: maker 0.0002, taker 0.0005, extra 0; stress: 0.0004, 0.0007, 0.0005. Per anchor year
(2021-09-24 .. 2025-09-24, 365 d each): fills, mean bps, per-asset mean bps, equal-rung sleeve (0.25/4 per rung per
asset) net % and DD; pooled mean over all anchor years; criterion = mean > 0 in >= 4/5 years (normal) and pooled > 0
(stress). Save `replication.json`.
B: compare with `v181/v181_result.json`; adversarial: 1m/4h alignment for these symbols, duplicated/bad rows, the
10 largest rung returns with timestamps (real moves?), and whether any parameter could have been tuned on these assets.
Write COMPARISON.md. Do not edit leader files.
