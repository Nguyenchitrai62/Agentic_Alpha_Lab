"""oc_stablegate Leg 2: stablecoin-impulse dip-budget dial (dip replica, no engine).

Replica core is the verbatim copy `compute_placebo_dip_copy.py` (oc_placebo_dip exact).
Step 1 reproduces base 5y 4-phase-mean sum 7.718; else stops.
Rules (PLAN-fixed, z at the BAR OPEN, NaN -> x1):
  D1: w x(0.32/0.26) when z > +1.0, x(0.20/0.26) when z < -1.0, else x1.
  D2: w x(0.32/0.26) when z > +1.0, else x1.
Same fills, same y1.0/d10 legs; only weights change.
Gate (assignment): PROMISING_5y = sum>=base in >=4/5 AND DD<=base+0.01 in >=4/5
AND 5y sum delta >= +0.273 (pooled placebo p95; calibrated on all five years - LABELLED),
plus a dev4-only view (years 0-3).

HEAVY (4-phase 1m replica): run through heavy_slot.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import compute_placebo_dip_copy as P
from stablegate_signal import asof_z, dip_mult, load_daily

EXP_BASE_SUM5Y = 7.718304
GATE_DSUM = 0.273
DD_TOL = 0.01


def score_with_weights(ph, yr, wv, yv, dv):
    return P.score_assignment(ph, yr, wv, yv, dv)


def decide_full(rule_sc, base_sc):
    ps = sum(1 for y in range(5)
             if rule_sc["per_year"][y]["S"] >= base_sc["per_year"][y]["S"])
    pd_ = sum(1 for y in range(5)
              if rule_sc["per_year"][y]["DD"] <= base_sc["per_year"][y]["DD"] + DD_TOL)
    return {"years_sum_ge": int(ps), "years_dd_ok": int(pd_),
            "pass_sum": bool(ps >= 4), "pass_dd": bool(pd_ >= 4),
            "dSum5y": float(rule_sc["sum5y"] - base_sc["sum5y"]),
            "promising_5y": bool(ps >= 4 and pd_ >= 4
                                 and (rule_sc["sum5y"] - base_sc["sum5y"]) >= GATE_DSUM)}


def decide_dev4(rule_sc, base_sc):
    ps = sum(1 for y in range(4)
             if rule_sc["per_year"][y]["S"] >= base_sc["per_year"][y]["S"])
    pd_ = sum(1 for y in range(4)
              if rule_sc["per_year"][y]["DD"] <= base_sc["per_year"][y]["DD"] + DD_TOL)
    dsum4 = float(sum(rule_sc["per_year"][y]["S"] for y in range(4))
                  - sum(base_sc["per_year"][y]["S"] for y in range(4)))
    return {"dev4_sum_ge": int(ps), "dev4_dd_ok": int(pd_), "dev4_dSum": dsum4}


def main() -> None:
    led = P.build_base()
    n = len(led["w"])
    print(f"ledger fills={n}", flush=True)
    base_sc = P.score_assignment(led["phase"], led["year"], led["w"],
                                 led["y10"], led["d10"])
    print("base 4-phase-mean sums:", [round(r["S"], 6) for r in base_sc["per_year"]],
          flush=True)
    print("base_sum5y:", round(base_sc["sum5y"], 6), flush=True)
    assert abs(base_sc["sum5y"] - EXP_BASE_SUM5Y) < 5e-4, (base_sc["sum5y"], EXP_BASE_SUM5Y)
    print("base reproduction OK (7.718)", flush=True)

    daily = load_daily()
    bt_ord = np.asarray(led["bar_time"], dtype=np.int64)
    bt = P.START + pd.to_timedelta(bt_ord, unit="m")
    bt = pd.to_datetime(bt, utc=True)
    zfill = asof_z(daily, bt)
    print(f"z at fills: finite={np.isfinite(zfill).mean():.4f} "
          f"up={np.mean(zfill > 1.0):.4f} down={np.mean(zfill < -1.0):.4f}", flush=True)

    out_rules = {}
    for mode in ("D1", "D2"):
        mult = dip_mult(zfill, mode)
        wv = led["w"] * mult
        sc = P.score_assignment(led["phase"], led["year"], wv, led["y10"], led["d10"])
        dec5 = decide_full(sc, base_sc)
        dec4 = decide_dev4(sc, base_sc)
        out_rules[mode] = {
            "mult_up": 0.32 / 0.26, "mult_down": 0.20 / 0.26 if mode == "D1" else 1.0,
            "share_up": round(float((mult > 1.0).mean()), 6),
            "share_down": round(float((mult < 1.0).mean()), 6),
            "per_year": [{"S": r["S"], "DD": r["DD"], "n": r["n"], "win": r["win"]}
                         for r in sc["per_year"]],
            "sum5y": sc["sum5y"], "ddmean": sc["ddmean"], "full_sum": sc["full_sum"],
            "full_dd": sc["full_dd"],
            "dec5y": dec5, "dev4": dec4,
        }
        print(mode, dec5, dec4, flush=True)

    res = {
        "meta": {
            "replica": "oc_placebo_dip exact (copy in this folder); D0 y1.0 + B1 sizes; "
                       "4 phases; majors x R2 rungs; live 16..238 strict; "
                       "maker 0.0002/taker 0.00055; v293 settle funding",
            "signal": "stablecoin USDT+USDC impulse z (30d log change, trailing-730d norm ddof=1); "
                      "day D usable from D+1 04:00 UTC; z taken at the BAR OPEN; NaN->x1",
            "rules": {"D1": "x(0.32/0.26) if z>1, x(0.20/0.26) if z<-1 else x1",
                      "D2": "x(0.32/0.26) if z>1 else x1"},
            "gate_5y": "PROMISING_5y = sum>=base >=4/5 AND DD<=base+0.01 >=4/5 AND dSum5y>=+0.273 "
                       "(pooled placebo p95; CALIBRATED ON ALL FIVE YEARS - labelled) + dev4 view",
        },
        "n_fills": int(n),
        "ledger_checksum": hashlib.sha256(
            np.round(np.stack([led["w"], led["y10"]]), 9).tobytes()).hexdigest()[:16],
        "base": {
            "sum5y": base_sc["sum5y"],
            "per_year": [{"S": r["S"], "DD": r["DD"], "n": r["n"], "win": r["win"]}
                         for r in base_sc["per_year"]],
        },
        "rules": out_rules,
    }
    (HERE / "dip_results.json").write_text(json.dumps(res, indent=1))
    print(json.dumps({m: {"dec5y": r["dec5y"], "dev4": r["dev4"]}
                      for m, r in out_rules.items()}, indent=1))


if __name__ == "__main__":
    main()
