# NEWRUNNERS 2026-10-08: PASS (first ~4h live, fix 83a466a)
1. Tilt exact. ch L32 k2_mult XRP/s1/01:00 0.75 prospective = feed row 14; 5 rungs L44/64/84/104/122 qty 43.7/44.1/44.5/44.9/45.8 = b7 L32/52/72/92/110 (58.2/58.8/59.3/59.9/61.1) x0.75 within 0.1 lot; other 167/172 identical. Detail: research/diagnostics/ops_newrunners/tilt_check.csv.
2. B7: no window (feeds all 1.0, 30 rows). b7==b7c2 172/172; missing rows -> 1.0 k2_mode missing (b7 L4-6), phase0 late (L3); no k2_missing file errors. Dip gross open 0 <= 2.0 cap on all runners (resting bids ~2.87x are unfilled entries, same on twin).
3. Exits clean since restart: ch L13, b7 L1, b7c2 L1, twin L6959 protection_check open []; 0 market_exit/fill/exit_wait/dust/protection ops post-04:50Z. Twin Oct7: 423 market_exit + 1119 dust_skip (pre-fix livelock); signature gone.
4. Data: chronos 55/55 prospective lag 0.2-9.7min; cascade 25/30 prospective +5 late; ch stale_plan x10 L3-12 (23:11-23:14Z, pre-restart plan 14:02Z) then zero; cycles 259-316ms, lock_wait 0.
Caveat: twin-vs-tilted sizes differ ~1 lot on 25/79 shared rungs from equity drift (twin 5030 vs fresh 5000); use ch-vs-b7 for tilt proof. Watch: B7 untested under active x1.5 window (none yet).
Repro: python -c "compare place qty by orderLinkId ch vs b7; check k2_mult vs parquet (sym,shift,T)".
Tom tat: Tilt C2 chay dung 0.75 tren 5 rung XRP, B7 dung 1.0 khi chua co cascade.
Khong con loi exit/dust/protection sau restart; du lieu feed tuoi, prospective day du.
De nghi PASS tiep tuc theo doi, kiem lai khi co cua so cascade x1.5.
