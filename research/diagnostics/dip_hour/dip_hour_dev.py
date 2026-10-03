"""Dev-only (anchors 2021-2024, no most-recent-year number is read): M3 dip-limit and book outcomes by the UTC hour of the holding bar.
Uses the deployed M3 configuration (kpack inputs); reports per dev year and bar hour: fills, win rate, mean net return per fill, and book trades.
  KPACK=artifacts/kaggle/kpack/pack347 python research/diagnostics/dip_hour/dip_hour_dev.py
"""
import importlib.util, json
from pathlib import Path
import numpy as np, pandas as pd
s = importlib.util.spec_from_file_location("v347", "research/parallel/rounds/parallel-20260906-r2/v347/v347_member_weight_evolution.py")
m = importlib.util.module_from_spec(s); s.loader.exec_module(m)
m.init_worker()
eu = m.W["v310"].W["eu"]; sim0 = eu.simulate; EV = []
def sim(*a, **kw):
    out = sim0(*a, **kw); EV.extend(kw["events"]); return out
eu.simulate = sim
m.run_genome(m.encode(m.SEEDS["CB"]))
eu.simulate = sim0
rows = m.W["v306"]._trade_rows(EV)
anch = m.W["v310"].W["anchors"]
out = {}
for kind in ("rung", "book"):
    d = pd.DataFrame([(t, r) for k, t, r in rows if k == kind], columns=["t", "ret"])
    d["t"] = pd.to_datetime(d["t"], utc=True)
    d["y"] = np.searchsorted(np.array(anch[:5]), d["t"].to_numpy(), side="right") - 1
    d = d[(d.y >= 0) & (d.y <= 3)]
    d["h"] = d["t"].dt.floor("4h").dt.hour
    g = d.groupby(["h", "y"]).ret.agg(n="size", win=lambda x: float((x > 0).mean()), mean=lambda x: float(100 * x.mean())).round(3)
    out[kind] = g.reset_index().to_dict("records")
    print(kind); print(g.unstack("y").to_string())
Path("research/diagnostics/dip_hour/dip_hour_dev.json").write_text(json.dumps(out, indent=1))
