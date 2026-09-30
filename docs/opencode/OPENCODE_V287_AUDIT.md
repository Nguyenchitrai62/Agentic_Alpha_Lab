# v287 blind audit (read AGENTS.md, .agents/skills/alpha-lab-leader/SKILL.md, OPENCODE_VF_COMMON.md)
v287 trains the O1 flow member A (4h TradingView + order-level whale flow, v240 builder) on a PATH (first-touch / triple-barrier) label
instead of the vol-normalised forward return, and tests it on CB (v285 D2): P1 = 0.8 CB + 0.2 (PA + PAq)/2, P2 = PA/PAq replace A/Aq.
Write only under `research/parallel/rounds/parallel-20260906-r2/v287_audit/`, `research/diagnostics/p1_robustness/` and `tests/test_v287_audit.py`. Use relative paths without
quoting. Do NOT open v287/v287_result.json, v287/run.log or `artifacts/research/engine_real/member_PA*_path.parquet` until part A is
saved (`replication.json`).
A (audit): read `v287/v287_path_label_member.py`, `v240`, `v144`, `v202`, `v92`, `v94`, `v103`, `v113`, `v129`. Write your OWN path-label
function from this spec and compare it row by row with v287.path_label on at least one symbol: entry = open of bar t+1, B = vol42_t *
sqrt(h); scan bars t+1..t+h: -1 if low <= entry*exp(-B) (checked first, stop-first), +1 if high >= entry*exp(+B), else
clip(log(open_{t+1+h}/entry)/B, -1, 1); NaN if any bar in the path is missing (non-4h gap) or B invalid. LEAKAGE checks (explicit):
the label window must end at open_{t+1+h} (no data after it), the training filter `t + 4h (h + 1) < cutoff` and the embargo must still
exclude every label that is not realised before each anchor's cutoff (annual and v202 quarterly schedules), the path label must replace
the target in all three components (v92 y, v94 y18/y42/y84, v103 y6/y18) and nowhere feed the features or the vol models, feature timing
unchanged, fill timing (minute-5 rule, trade-through). Rebuild PA and PAq independently, replicate CB_ref (dev4 5.864), P1, P2 with the
C4 engine arguments; selection = v286.dev_select (DD filter on 2021-2024 only) among P1/P2, `replaces_cb` = dev_select over {CB_ref,
selected}; most recent year only for the selected row. B: compare with the result JSON (return > 1pp or DD > 0.5pp = mismatch);
COMPARISON.md with a "## Verdict" PASS/FAIL covering feature timing, label windows, fit windows and fill timing. Do not edit leader files.
C (robustness, after B): copy `research/diagnostics/d2c_robustness/d2c_robustness.py` into `research/diagnostics/p1_robustness/` and run
every row for CB (v285 D2) and P1 (books = 0.8 CB + 0.2 (PA + PAq)/2, same engine arguments): cost stress, latency 15 / 30 / 60,
band / cool / sleeve / offset shifts, outage (backstop only), close_1m, bootstrap (P(>=5%/month), P(loss year), P(DD>20)), 2000-USDT
placeability. Write its json and a SUMMARY.md (<= 25 lines) with a plain verdict: is P1 at least as robust as CB?
