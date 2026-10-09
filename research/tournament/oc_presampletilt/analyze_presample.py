"""oc_presampletilt: assemble results.json (CPU-only, no outcome computation).

Reads tmp/tilt_presample.json (pre-sample outcomes) and the FROZEN 2021-2026
copies (verbatim from oc_voltilt/tmp/placebo_vol.json and
oc_chronos/tmp/placebo_c2.json; not recomputed), writes results.json.
"""
from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
TMP = HERE / "tmp"

# 2021-2026 COPIES (verbatim from placebo_vol.json / placebo_c2.json; labelled copied).
Y5 = ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")
COPIED_2126 = {
    "V_RV6": {
        "per_year": [
            {"year": "2021-09-24", "n_fills": 4171, "base": 0.911273,
             "tilt": 0.667497, "realised_mean": 0.982378, "norm": 0.67947,
             "gain": -0.231803},
            {"year": "2022-09-24", "n_fills": 4059, "base": 0.832599,
             "tilt": 0.636543, "realised_mean": 0.947278, "norm": 0.671971,
             "gain": -0.160628},
            {"year": "2023-09-24", "n_fills": 5352, "base": 2.099814,
             "tilt": 1.99955, "realised_mean": 0.996357, "norm": 2.006862,
             "gain": -0.092952},
            {"year": "2024-09-24", "n_fills": 3958, "base": 3.19739,
             "tilt": 3.252162, "realised_mean": 0.997726, "norm": 3.259574,
             "gain": 0.062184},
            {"year": "2025-09-24", "n_fills": 4772, "base": 0.677229,
             "tilt": 0.802518, "realised_mean": 1.002515, "norm": 0.800505,
             "gain": 0.123276},
        ],
        "timing_pct": [2.4, 14.49, 97.1, 100.0, 100.0],
        "block_pct": [1.4, 16.78, 96.0, 100.0, 100.0],
    },
    "V_GARCH": {
        "per_year": [
            {"year": "2021-09-24", "n_fills": 4171, "base": 0.911273,
             "tilt": 0.726871, "realised_mean": 0.987953, "norm": 0.735735,
             "gain": -0.175538},
            {"year": "2022-09-24", "n_fills": 4059, "base": 0.832599,
             "tilt": 0.675262, "realised_mean": 1.028702, "norm": 0.656421,
             "gain": -0.176178},
            {"year": "2023-09-24", "n_fills": 5352, "base": 2.099814,
             "tilt": 2.131201, "realised_mean": 0.997711, "norm": 2.13609,
             "gain": 0.036276},
            {"year": "2024-09-24", "n_fills": 3958, "base": 3.19739,
             "tilt": 3.178083, "realised_mean": 0.987873, "norm": 3.217098,
             "gain": 0.019708},
            {"year": "2025-09-24", "n_fills": 4772, "base": 0.677229,
             "tilt": 0.85406, "realised_mean": 1.018389, "norm": 0.838639,
             "gain": 0.16141},
        ],
        "timing_pct": [12.39, 7.29, 99.9, 100.0, 100.0],
        "block_pct": [8.39, 19.18, 100.0, 100.0, 100.0],
    },
    "C2": {
        "per_year": [
            {"year": "2021-09-24", "n_fills": 4171, "base": 0.911273,
             "tilt": 0.928375, "realised_mean": 1.039079, "norm": 0.893459,
             "gain": -0.017814},
            {"year": "2022-09-24", "n_fills": 4059, "base": 0.832599,
             "tilt": 0.785261, "realised_mean": 0.917898, "norm": 0.855498,
             "gain": 0.022899},
            {"year": "2023-09-24", "n_fills": 5352, "base": 2.099814,
             "tilt": 2.189835, "realised_mean": 0.981736, "norm": 2.230574,
             "gain": 0.13076},
            {"year": "2024-09-24", "n_fills": 3958, "base": 3.19739,
             "tilt": 3.24732, "realised_mean": 1.002463, "norm": 3.23934,
             "gain": 0.04195},
            {"year": "2025-09-24", "n_fills": 4772, "base": 0.677229,
             "tilt": 0.732798, "realised_mean": 1.01645, "norm": 0.720938,
             "gain": 0.043709},
        ],
        "timing_pct": [90.11, 88.31, 100.0, 100.0, 99.2],
        "block_pct": [85.61, 89.01, 100.0, 100.0, 98.9],
    },
}


def main() -> None:
    pre = json.loads((TMP / "tilt_presample.json").read_text())
    meta = json.loads((TMP / "ledger_presample_meta.json").read_text())
    out = {
        "config": {
            "rule": "frozen anchor-2021 fits (V_RV6/V_GARCH/C2 dir +1, hi/lo "
                    "1.25/0.75, missing->1); labelled fit from later data, rule frozen",
            "ledger": "D0+B1 replica same as oc_k2placebo (no budget/cap; kept iff "
                      "y09/y10/y11 finite), spot store 2017-08..2020-09-30",
            "costs": {"maker": 0.0002, "taker": 0.00055, "fund_long_8h": 0.0001,
                      "note": "inside replica outcomes; limits strict trade-through, "
                              "live 16..238, stop-first"},
            "placebo": "1000 within-year timing perms (seed 20261007+y) + 42-bar "
                       "block perms (seed 20261008+y); pct=100*(1+#{perm<=actual})/1001, "
                       "significant iff >=95",
            "y2021_2026": "COPIED from oc_voltilt/tmp/placebo_vol.json and "
                          "oc_chronos/tmp/placebo_c2.json, not recomputed",
            "model": {"name": "amazon/chronos-bolt-small",
                      "requested_revision": "772f3d25d38aec6d914c8949dab4462e2d46f5d8",
                      "resolved_revision": "772f3d25d38aec6d914c8949dab4462e2d46f5d8",
                      "chronos_forecasting": "2.3.2", "transformers": "5.19.0",
                      "torch": "2.12.1+cu126", "seed": 20261007},
        },
        "ledger": meta,
        "features": {
            "bars": "bars_4h_presample.parquet: 101345 rows (4 sym x 4 shifts), "
                    "2017-08-17..2020-09-30",
            "vol": "vol_features_presample.parquet: 59247 rows (sigma 360 burn-in)",
            "chronos": "chronos_features_presample.parquet: 44375 rows "
                       "(512 ctx + sigma burn-in; first usable 2017-12-01)",
            "join_missing_fills": {"V_RV6": 4254, "V_GARCH": 4254, "C2": 5547,
                                   "note": "early-bar fills before burn-in/context "
                                           "get mult 1 (of 9731 ledger fills)"},
        },
        "presample": {v: pre[v] for v in ("V_RV6", "V_GARCH", "C2")},
        "y2021_2026_copied": COPIED_2126,
    }
    # counts: helps = gain>0; timing_sig = timing>=95
    for v in ("V_RV6", "V_GARCH", "C2"):
        pre_years = pre[v]["per_year"]
        pre_tim = pre[v]["timing_placebo"]
        cpy = COPIED_2126[v]
        helps_pre = sum(1 for r in pre_years if r["gain"] > 0)
        helps_cpy = sum(1 for r in cpy["per_year"] if r["gain"] > 0)
        sig_pre = sum(1 for r in pre_tim if r["percentile"] >= 95)
        sig_cpy = sum(1 for p in cpy["timing_pct"] if p >= 95)
        out.setdefault("counts", {})[v] = {
            "helps_gain_gt0": {"presample": helps_pre, "y2021_2026": helps_cpy,
                               "all9": helps_pre + helps_cpy},
            "timing_sig_ge95": {"presample": sig_pre, "y2021_2026": sig_cpy,
                                "all9": sig_pre + sig_cpy},
        }
    (HERE / "results.json").write_text(json.dumps(out, indent=1))
    print("wrote results.json", flush=True)


if __name__ == "__main__":
    main()
