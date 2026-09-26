"""v147: add a 12h (3-bar) horizon to the v103 short-horizon ensemble inside v144 (registry v147, track A).

v103 targets become y3, y6, y18 (same definition clip(log(open[t+1+h]/open[t+1])/(vol42*sqrt(h)), +-4)); the v103
prediction = mean of the three HGBs; embargo unchanged (78 bars = max(18) + 60). Everything else exactly v144 (v142
cross-sectional books, vol-forecast sizing on the original feature sets, tranching, realistic 10 bps 1m execution,
governor). Rows 0.15 ungoverned / 0.20 / 0.25 governed (primary). Reference v144: 2.361/16.89, 2.955/18.28, 3.374/19.63.
Fixed before running.

  python research/parallel/rounds/parallel-20260906-r2/v147/v147_v103_12h_horizon.py
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


def main():
    v144.v103.HS = (3, 6, 18)
    assert v144.v103.EMBARGO == 78
    p103, books = v144.books_v142()
    out = {"version": "v147", "v103_horizons": v144.v103.HS, **v144.simulate(p103, books)}
    out["reference_v144"] = {"t15": (2.361, 16.89), "t20": (2.955, 18.28), "t25": (3.374, 19.63)}
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v147_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
