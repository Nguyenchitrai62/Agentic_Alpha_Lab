# OpenCode task docs_report20261009b - update the owner report with the afternoon results of 2026-10-08
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. EXCEPTION (docs task): edit `docs/SUMMARY_FOR_OWNER_20261009_VI.md` (add a section
"Cập nhật chiều 2026-10-08" at the TOP, keep the rest) - copy every number from docs/CLOSED_DIRECTIONS.md rows dated 2026-10-08 that are NOT
yet in the summary and their REPORT.md files. No new numbers. Vietnamese, plain language, <= 50 new lines.

## Must cover
1. The Bybit + carry decision table (oc_levfrontier) and what the owner can choose: G2 (deployed), G2+C2, G2K20+C2 (robust pick), G2+B7xC2;
   none reaches 5 %/month in the most recent year.
2. B7 truth: ~70 % exposure (oc_cboostctrl), broad plateau (oc_b7thresh), B7xC2 pre-sample (oc_b7c2pre), all IDEAS7 variants lose to flat B7.
3. The pre-sample finding (oc_presampleg2): the dip sleeve is the robust edge; the book's skill looks 2021+ (without the A members).
4. Everything closed in the afternoon in one line each (IDEAS8 book batch, IDEAS9 MANUAL batch, IDEAS10, IDEAS11, booktrim, bookband,
   dipdaily, spotlongs / spotlongs2, carryhurdle, Kronos-base, confirmgate lesson).
5. Ops: 11 paper runners on bot fix 83a466a (ops_newrunners PASS), live ramp plan docs/LIVE_RAMP_VI.md, weekly scripts/fm_paper_eval.py --all.
6. Owner actions (unchanged order + the live ramp).
