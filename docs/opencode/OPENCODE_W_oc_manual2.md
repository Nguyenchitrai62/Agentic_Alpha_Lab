# OpenCode task oc_manual2: human-placeable correlation control for the MANUAL product
Read AGENTS.md, docs/opencode/OPENCODE_VF_COMMON.md. Write ONLY under research/diagnostics/oc_manual2/ (+ tests/test_oc_manual2.py); no
commits; no edits of leader files; data up to 2026-09-24 00:00 UTC; ONE heavy process (Pool(1)), RAM < 2.5 GB.
Context: the BOT met the base gate by shrinking each dip rung at its FILL minute by 1/(1+n) (n = other majors flushing at minute f-1), which a
human cannot do (orders are placed at the bar open). A human CAN limit correlated stacking structurally: place the dip bracket limits on at most
2 coins per bar. Base harness: research/diagnostics/oc_manualbf/oc_manualbf.py (MANUAL M5 on the four phases over 5 years, human schedule:
15-minute reaction, night bar skipped, agents on, bear-book filter 'BF'). PLAN.md first, rows fixed:
  M5_humanBF (reference, reproduce oc_manualbf's number exactly first),
  M5_humanBF_top2: dip limits only on the 2 coins with the highest deployed R2-agent size at that bar (the same size table lookup the
    harness uses, at the bar open; ties -> order BTC, ETH, SOL, BNB, XRP); the other 3 coins get no dip limit that bar (sleeve_filter 0);
    dip rung size x1.5 for the chosen coins (sleeve_filter 1.5),
  M5_humanBF_btceth: dip limits only on BTC and ETH, size x1.5.
Report per row: per-year %/month (mean over phases), 5y geometric mean, mean / worst-phase max yearly DD, book win and all-trade win;
verdict vs the base gate (>= 5 %/month, DD < 20, win > 55 %). REPORT.md + results.json.
