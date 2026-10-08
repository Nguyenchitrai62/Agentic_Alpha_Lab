# OpenCode task oc_presampleg2 - can the FULL deployed G2 (book + dip sleeve) be replayed on the unseen pre-sample years 2018-2020?
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. Write ONLY `research/tournament/oc_presampleg2/` and `tests/test_oc_presampleg2.py`.
Print progress every 10 minutes. Write PLAN.md (frozen) before any outcome. Heavy work via heavy_slot (RAM tight). CPU training only.

## Why
The dip sleeve alone has been replayed on 2017-2020 under frozen rules (research/tournament/oc_presample, oc_presample2: positive in most
years) and the pre-sample member predictions exist for some families (research/tournament/oc_presamplebook, oc_presampleflow: IC ~0 at 7 days,
TV-only member). The deployed G2 = book (members A/Aq/B/Bq/D/Dq blended, research_books_d2 / forward_v205) + dip sleeve + caps. A full
pre-sample replay would be the cleanest evidence the program can produce for the system that is actually deployed.
## Part A - feasibility (report before running anything heavy)
For each G2 book member list the inputs it needs (features, order-level flow, premium, funding ...) and whether they exist for 2018-01 ..
2020-09 for the majors (Binance spot / USD-M availability per coin; SOL and some perps start late). Decide per member: buildable with the
frozen builder and walk-forward training (per-anchor, data before A - embargo only), or not available.
## Part B - if at least the TV / price members are buildable
Build a pre-sample book from the buildable members only (disclose which are missing; blend weights frozen as in research_books_d2 with
missing members dropped and renormalised - pre-registered), run the 4-phase engine with the frozen G2 dip sleeve and caps on the yearly
pre-sample windows of oc_presample2, and report per year %/month, DD, book vs dip P&L, and the same for the dip sleeve alone (should match
oc_presample2). Vietnamese 3-line verdict: does the deployed design make money in years nobody looked at?
