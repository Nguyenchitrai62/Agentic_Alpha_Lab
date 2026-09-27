# v110 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Write only under `research/parallel/rounds/parallel-20260906-r2/v110_audit/` and `tests/test_v110_audit.py`.
Base: your audited v104 replication (books = 0.25 b_lo + 0.25 b94 + 0.5 b103, carry, v104 portfolio vol estimate).
Do NOT open v110/ until part A is saved (`replication.json`).

A: realized_t = 0.8*sum(books_{t-2}*(open_t/open_{t-1}-1)) + 0.6*carry_{t-1}; vol = rolling-360 (min 120) std * sqrt(2190);
s = min(target/vol, 2), NaN->1, target 0.25 (primary), 0.30 (secondary), 0.25 and 0.15 ungoverned references.
Sequential loop over the 4h index; live bars are [2021-09-24, 2026-09-23) (= start + 1825 days); outside, weights and
carry exposure are 0. Governor at bar i >= 2: j = i-2, peak = max(E over bars j-539..j), DD = 1 - E_j/peak,
g_i = clip((0.20 - DD)/0.10, 0, 1) (g = 1 when ungoverned or i < 2). w_i = 0.8*s_i*books_i*g_i, c_i = 0.6*s_i*g_i.
net_i = sum(w_i * (open_{i+2}/open_{i+1} - 1)) - sum|w_i - w_{i-1}|*(fee+slip) - 0.00005*sum(max(w_i,0))
+ c_i*carry_i - |c_i - c_{i-1}|*2*0.0004/1.2; E_i = E_{i-1}*(1+net_i), E before start = 1. Scenarios as v92.
Report yearly net/DD, mean g per anchor year, and full-path max DD over the live span for all four rows and scenarios.

Save `replication.json`, compare with v110/v110_result.json (explain return diff > 1pp or DD diff > 0.5pp), audit
v110_dd_governor.py for look-ahead (governor timing), write COMPARISON.md. Do not edit leader files.
