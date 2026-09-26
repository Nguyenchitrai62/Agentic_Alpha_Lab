"""v149: cross-sectional features in the v129 volatility forecast, on the v144 configuration (registry v149, track B).

The two vol models (v114 panel with v92 features; v103 panel with v103 features) additionally get xs_c / xr_c (deviation
from the majors' mean at t and percentile rank at t) for c in vol42, vol180, vol_ratio, volz (both panels) and rng6, ntr_z
(v103 panel). Return models, books, tranching and the v144 engine (10 bps 1m execution, governor) unchanged. Rows 0.15
ungoverned / 0.20 / 0.25 governed (primary). Reference v144: 2.361/16.89, 2.955/18.28, 3.374/19.63. Fixed before running.

  python research/parallel/rounds/parallel-20260906-r2/v149/v149_xs_vol_forecast.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).parent
spec = importlib.util.spec_from_file_location("v144", HERE.parent / "v144" / "v144_deploy_v3.py")
v144 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v144)
VOL92 = ("vol42", "vol180", "vol_ratio", "volz")
VOL103 = VOL92 + ("rng6", "ntr_z")


def main():
    v129, v142 = v144.v129, v144.v142
    orig = v129.vol_predict

    def vol_predict_xs(panel, feats, anchors, embargo_bars):
        cols = VOL103 if "rng6" in panel.columns else VOL92
        p = v142.add_xs(panel, cols)
        extra = [f"xs_{c}" for c in cols] + [f"xr_{c}" for c in cols]
        return orig(p, list(feats) + extra, anchors, embargo_bars)

    v129.vol_predict = vol_predict_xs
    p103, books = v144.books_v142()
    out = {"version": "v149", **v144.simulate(p103, books)}
    out["reference_v144"] = {"t15": (2.361, 16.89), "t20": (2.955, 18.28), "t25": (3.374, 19.63)}
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v149_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
