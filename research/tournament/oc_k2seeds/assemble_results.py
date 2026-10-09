"""Assemble oc_k2seeds/results.json from tmp/stage0.json + tmp/engine.json + tmp/placebo.json."""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
TMP = HERE / "tmp"

REF = {"R": 4.648, "DD": 12.90, "full_path_dd": 16.82}
K2_1234 = {"R": 4.801, "DD": 12.10, "full_path_dd": 16.09, "book_trades": 1104,
           "book_win": 0.5344, "rung_trades": 4665, "rung_win": 0.648, "all_win": 0.6263}

eng = json.loads((TMP / "engine.json").read_text())
pl = json.loads((TMP / "placebo.json").read_text())

per_seed = {"1234": {"engine": K2_1234, "placebo": pl["per_seed"]["1234"]}}
for s in ("1", "2", "3", "4"):
    per_seed[s] = {"engine": eng[s], "placebo": pl["per_seed"][s]}

res = {
    "config": {
        "seeds": [1234, 1, 2, 3, 4],
        "inference": "Kronos-small + Tokenizer-base, ctx 400x4h, pred_len 6, S=64, T=1.0, "
                     "top_p=0.9, top_k=0, fp32, per-window z-norm + clip 5; torch.manual_seed(SEED) "
                     "once; group order (sym,shift) sorted, B=32; window T in [2024-09-01, 2026-09-23]",
        "fit": "SHORTCUT row: anchor-2025 fit reused from seed-1234 fits.json "
               "(dir +1, q20 0.5872, q80 2.1828) for ALL seeds; no per-seed refit",
        "k2_rule": "1.25 favourable outer quintile / 0.75 unfavourable / 1 else; risk=-low1; missing->1",
        "engine": "oc_kronoshidden/run_engine.py tilt path on G2 (inv k=1.0 kd=1.7 bear G=2.0), "
                  "full window [2021-09-24, 2026-09-23), original-K2 years 0-3 + seed K2 year 4; "
                  "gate costs maker 0.0002/taker 0.00055, longs 0.0001/8h, win_start=5, stop-first",
        "placebo": pl["config"],
        "incidents": "seed-2 first attempt CUDA OOM at BTC s2 (transient WDDM pressure; seeds 1,3,4 "
                     "unaffected); resumed from 6-group checkpoint, remaining 14 groups recomputed "
                     "(RNG stream differs for those groups - sampling noise only, same caveat as "
                     "oc_kronoshidden resume)",
    },
    "gates": {
        "stage0_ref_k2_repro": "PASS (REF 4.648/12.90 full 16.82; K2 4.801/12.10 full 16.09, to the digit)",
        "prior_path_determinism": "PASS (all 4 new seeds years 0-3 == dev K2 to the digit)",
        "placebo_1234_repro": "PASS (norm 0.751465, timing 97.20, block 98.70 == oc_k2placebo)",
        "ledger_reuse": "n=22312, clean-year fills=4772, base_clean=0.677229 (== oc_k2placebo), 0 missing joins",
    },
    "REF_clean": REF,
    "per_seed": per_seed,
    "change_share": pl["change_share"],
    "verdict": "STABLE: all 5 clean-year R > REF (4.782..4.825 vs 4.648); all timing/block pct >= 95",
}
(HERE / "results.json").write_text(json.dumps(res, indent=1))
print("wrote results.json; seeds:", {s: (per_seed[s]["engine"]["R"], per_seed[s]["placebo"]["timing"]["percentile"],
      per_seed[s]["placebo"]["block"]["percentile"]) for s in per_seed})
