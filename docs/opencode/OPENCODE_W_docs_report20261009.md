# OpenCode task docs_report20261009 - owner report for the 2026-10-08 research day (Vietnamese, plain language)
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. EXCEPTION (docs task): create `docs/SUMMARY_FOR_OWNER_20261009_VI.md` and add a dated
section at the TOP of `docs/FINAL_REPORT_VI.md` (do not delete older content). Copy every number from docs/CLOSED_DIRECTIONS.md (all rows dated
2026-10-08) and the REPORT.md files they name. No new numbers, no new analysis. Do not start before the rows of oc_cboostctrl, oc_cboostbybit,
audit_cboost and oc_cboostmanual exist in CLOSED_DIRECTIONS.md; if they are still missing after 3 hours of waiting (check every 15 minutes),
write the report with those items marked "đang chạy".

## Content (<= 90 lines for the summary)
1. Deployed: unchanged (G2 + quarterly carry, paper only); honest Bybit expectation (oc_c2carry: G2+carry 5.111 / full DD 17.93).
2. Foundation-model / volatility dip tilts (K2, C2, Toto, TimesFM, RV6, GARCH, presampletilt, beargate, tiltgate, crashgate): what they are,
   that they are mostly volatility timing that fails in crash legs, C2 the most consistent (7/9 years, Bybit 5y 5.115 vs 4.883), live C2 feed +
   paper runner d17bfg2ch, what would make us switch.
3. The cascade boost B7: numbers, the contamination label, the verification results (controls, unseen 2017-2020 years, frictions, audit,
   MANUAL), and what is still needed (prospective paper).
4. Everything closed today, one line each (IDEAS5 and IDEAS6 batches, dip1h, shortmember, horizonfix, kronosfeat, fmbookic, D1 + caveat, ...).
5. Ops: bot exit-resend livelock fixed (bot_exitstuck), paper vs engine reconciliation (oc_paperrecon), backend outage 2026-10-07 and the
   keepalive recommendation, OpenCode DB growth and snapshot=false.
6. Owner actions in order (register keepalive, review the bot fix restart, prospective evaluation schedule with scripts/fm_paper_eval.py).
