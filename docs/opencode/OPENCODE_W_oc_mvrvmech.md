# OpenCode task oc_mvrvmech - WHY does halving book longs during the 2023-24 rallies (MVRV z > 2) raise G2's return? mechanism check
Read docs/opencode/OPENCODE_W_COMMON_20261007.md first. Write ONLY `research/tournament/oc_mvrvmech/` and `tests/test_oc_mvrvmech.py`.
Print progress every 10 minutes. Engine runs via heavy_slot.

## Puzzle
research/tournament/oc_mvrvrobust (read REPORT.md, events.json, code): M1 halves all book LONG weights while BTC MVRV-z > 2; its dev4 gain
(+0.59 pp/month) comes from episodes E2 (2023-11-02..2024-01-13, BTC +22.6 %) and E4 (2024-11-12..12-01, BTC +10.6 %) - halving longs during
strong rallies INCREASED total P&L. Possible mechanisms: (a) the book's longs actually lost in those windows (trade-mode SL / TP whipsaw),
(b) smaller book longs freed margin / budget for the dip sleeve or changed the bear-book / gross-cap interaction, (c) an engine artefact.

## Tasks (frozen M1 and G2; no new variants)
1. Book-only engine runs (dip sleeve OFF, as research/tournament/oc_bookattrib/run_bookonly.py) for G2 and M1, 4 phases: book P&L per
   episode window and per year. Dip-only runs (book OFF) for both: is the dip sleeve identical (it should be if there is no coupling)?
2. Inside E2 / E3 / E4: per coin, the book's long trades in G2 vs M1 (entries, exits, SL / TP hits, P&L per trade, fees) - which trades
   differ and why. Show the capital-budget / margin-budget utilisation (the engine's cross-margin cap: spot cash + perp gross / leverage <=
   95 % of equity) in G2 vs M1 during the windows - does M1 let more dip rungs fill?
3. Conclusion in bold: (a), (b) or (c), with numbers. If (c), give a minimal reproduction. Vietnamese 3-line verdict on whether the M1 gain is
   an economically sensible effect.
