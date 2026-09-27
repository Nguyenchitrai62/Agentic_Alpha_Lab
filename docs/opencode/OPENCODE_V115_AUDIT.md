# v115 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
Write only under `research/parallel/rounds/parallel-20260906-r2/v115_audit/` and `tests/test_v115_audit.py`.
Base: your audited v113_v114 replication (extended v114 panel: Bitstamp 2013 + Coinbase + Binance BTC, Coinbase +
Binance ETH), v103_v105 (v103 book, v104 strict fill rule) and v110 (sequential governor engine). If the v113_v114
audit is not finished, build the v114 panel from its spec in OPENCODE_V113_V114_AUDIT.md. Do NOT open v115/ until part A
is saved (`replication.json`).

A: b_lo = v92 LO weights (v92 model trained on the v114 panel) * v92 vol scale (computed on the v114 panel); b94 = v94 LS
ensemble weights (trained on the v114 panel) * v94 vol scale (v114 panel); b103 = v103 LS weights * own vol scale (v103
panel). Union index restricted to t >= first v103 panel t. books = 0.25 b_lo + 0.25 b94 + 0.5 b103. Run the v110
sequential engine (panel opens from the v103 panel) with target 0.15 ungoverned (primary) and 0.25 governed (secondary)
in the three v92 scenarios; report yearly net/DD and full-path DD. Hidden year (v104 fill rule, v104 cost path, target
0.15, vectorised over the whole index as in v104): net/DD/maker rate.

Save `replication.json`, compare with v115/v115_result.json (explain return diff > 1pp or DD diff > 0.5pp), audit
v115_candidate.py for look-ahead, write COMPARISON.md. Do not edit leader files.
