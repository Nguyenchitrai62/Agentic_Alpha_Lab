# OpenCode task docs_report20261008 - update the owner reports with the 2026-10-07/08 findings
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. EXCEPTION (docs task): you may edit `docs/FINAL_REPORT_VI.md` (add a dated section at
the top, do not delete older content) and create `docs/SUMMARY_FOR_OWNER_20261008_VI.md`. Copy every number from the cited source
(docs/CLOSED_DIRECTIONS.md sections 11+, docs/FRONTIER_MAP_VI.md, the REPORT.md / COMPARISON.md files named there). No new numbers.

## Content (Vietnamese, plain language, <= 80 lines for the summary)
1. Deployed: unchanged G2 + carry f 0.25; honest expectation now INCLUDING the Bybit-price gap (oc_bybitgap / oc_amihudrobust S5: G2 5y 4.883,
   full-path DD 18.09 on Bybit prices vs 5.410 / 16.82 on Binance) - state plainly what that means for the 5 %/month goal.
2. What was confirmed: book return is timing not beta (oc_bookattrib), skill at 4h-3d horizons (oc_bookichorizon), design layers earn their
   keep (oc_ablation), models do not decay (oc_staleness), feeds redundant (oc_memberdrop), dip sleeve generalises to 2017-2020 (oc_presample,
   oc_presample2).
3. The one new lead: Kronos K2 (oc_kronoshidden, oc_k2placebo, oc_k2bybit, audit_k2) - what it is, numbers on Binance and Bybit, why not
   deployed yet, and that a paper runner (paper_d17bfg2k2) collects the evidence.
4. Bugs fixed (exit cancel, dust, paper carry mark) and ops (keepalive script; evidence horizon 26 weeks).
5. Everything closed in these two days, one line each (options family, GEX, IV term, option flow, HL funding, ETF, stablecoin, USDT depeg,
   literature gates, Amihud, MVRV, governor variants, alt dips, native clocks, MANUAL variants).
6. Owner actions in order.
