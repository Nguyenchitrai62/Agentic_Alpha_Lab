1. Blind replication saved first (`replication.json`); leader files opened only after.
2. Signals reproduce exactly: all holdout trade lists/dates/prices match, counts match.
3. Net gaps are accounting, not signals: H4 dev −119.8pp, buy_hold dev −267.2pp, H2 holdout −12.8pp.
4. Root cause is mine: daily-rebalanced equity vs protocol "1x at entry" fixed qty.
5. Short drag proves it: 100→50→100 gives fixed-qty 0% but rebalanced −100%.
6. Minor gaps: funding on open- vs close-notional, slippage-as-fee, DD peak set.
7. Leader engine audited correct; replication numbers left as-is per instructions.
8. Shadow log (`shadow_log.py`) appends daily H4 + 4h EMA20/200-ribbon-long, append-only.
9. Causality unit test passes (`tests/test_opencode_r82_shadow.py`): prefix targets stable.
10. No cloud, no training, no orders, no Kronos/registry edits; hashes verified.
