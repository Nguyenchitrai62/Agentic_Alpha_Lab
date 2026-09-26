"""v134: shorts only in a confirmed daily downtrend, on the v133 configuration (registry parallel-20260906-r2 / v134).

DIAGNOSTIC-MOTIVATED (OOS-BIASED): a per-side breakdown of the v115 books over the 2021-2026 OOS years showed that
long sides earn every year while the short sides of the v94 and v103 books lose in bull years (2022-2023). This test
therefore uses already-seen years; a positive result is only a hypothesis for the prospective log, not evidence.

Change vs v133: in the v94 LS and v103 LS weight formulas the short leg is allowed only where the asset's daily ribbon
== -1 (close < SMA50 < SMA200) instead of != +1; long legs, v92 LO, vol-forecast sizing, tranching, portfolio (15%
target) unchanged. Reports three scenarios (full-path DD) and the hidden year with the strict 1m rule. Reference v133:
2.44/2.222/1.95, full-path DD 15.18/16.64/18.42, hidden +29.0% DD 10.06%. Fixed before running.

  python research/parallel/rounds/parallel-20260906-r2/v134/v134_bear_only_shorts.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
spec = importlib.util.spec_from_file_location("v133", HERE.parent / "v133" / "v133_deploy_v2.py")
v133 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v133)
v125 = v133.v125
PD, SYMS = 6, 5


def raw_ls_bear_shorts(df):
    W = {}
    for s, g in df.groupby("sym"):
        g = g.set_index("t").sort_index()
        long_ = (g["pred"].clip(lower=0) / 0.5).clip(upper=1.0).where(g["rib"] != -1, 0.0)
        short = ((-g["pred"]).clip(lower=0) / 0.5).clip(upper=1.0).where(g["rib"] == -1, 0.0)
        W[s] = (long_ - short) / (g["vol42"] * np.sqrt(PD * 365))
    W = pd.DataFrame(W).sort_index().fillna(0.0)
    gross, active = W.abs().sum(axis=1), W.ne(0).sum(axis=1)
    return W.div(gross.where(gross > 0, 1.0), axis=0).mul((active / SYMS).clip(upper=1.0), axis=0)


def main():
    v125.raw_ls = raw_ls_bear_shorts  # v133.main calls v125.raw_ls for the v94 and v103 books
    v133.HERE = HERE
    v133.main()
    p = HERE / "v133_result.json"
    res = json.loads(p.read_text())
    res["version"] = "v134"
    res["reference_v133"] = {"normal": 2.44, "fee_stress": 2.222, "execution_stress": 1.95, "hidden_net_pct": 29.0, "hidden_dd": 10.06}
    raw = json.dumps(res, indent=1, default=str)
    (HERE / "v134_result.json").write_text(raw)
    p.unlink()
    print("v134 sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
