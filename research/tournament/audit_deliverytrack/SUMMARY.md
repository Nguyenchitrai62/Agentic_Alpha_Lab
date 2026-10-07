# audit_deliverytrack SUMMARY — verdict PASS (11 lines)

Blind replication (33/33 deliveries) saved to replication.json BEFORE opening
oc_deliverytrack/*. Same-venue exact-def recheck matches bit-for-bit: TWAP,
slices6, 08:00 open, typical-VWAP, 08:15 open all mean 0.00000 bp, worst 0.00000
bp (tolerance 1 bp mean / 3 bp worst). No spot 1m exists locally (spot 4h/1h
only); evaluated perp-proxy venue is honestly documented, and a true-spot REST
check shows only a ~2.6 bp level gap with te-mean gap 0.006 bp — conclusion
stands: 6 slices (07:34/39/44/49/54/59 closes) cut exit noise 29→6 bp std,
worst 92→20 bp, worst return damage 0.051→0.007 pp (frozen hedged formula).
Bot (bot/carry.py: one market-IOC slice per 5-min bucket from delivery-30min,
first cycle in bucket) executes at bucket STARTS vs evaluated bucket ENDS —
not tick-for-tick, but statistically equivalent (std 7.2 vs 6.2 bp, dret gap
worst 0.015 pp). A 25 s cycle delay moves the result ~0.0–0.1 bp mean (worst
3.9 bp) — negligible. Unmodeled: spot market spread on slices.
Verdict: PASS.
