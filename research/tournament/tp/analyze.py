"""Post-score diagnostics (no selection): gains vs deployed and vs constant 1.5, day-block bootstrap, switch matrix, per-rung gains."""
import json, sys
from pathlib import Path
import numpy as np, pandas as pd
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import harness as H
d = H.load()
Y = {0.5: d["y0.5"].to_numpy(), 1.0: d["y1.0"].to_numpy(), 1.5: d["y1.5"].to_numpy()}
def yof(tp, rows):
    return np.select([tp == 0.5, tp == 1.5], [Y[0.5][rows], Y[1.5][rows]], Y[1.0][rows])
out = {}
rng = np.random.default_rng(0)
for v in ("v1_cls", "v2_diff", "v3_mlp", "v4_bot_only"):
    p = pd.read_parquet(HERE / f"tp_{v}.parquet")
    rows = p.row.to_numpy(); s = d.size_dep.to_numpy()[rows]
    g_dep = s * (yof(p.tp_new.to_numpy(), rows) - d.y_dep.to_numpy()[rows])
    g_15 = s * (yof(p.tp_new.to_numpy(), rows) - Y[1.5][rows])
    day = pd.to_datetime(p["T"]).dt.floor("D").to_numpy()
    yr = np.searchsorted(np.array([a.to_datetime64() for a in H.ANCHORS]), pd.to_datetime(p["T"]).dt.tz_convert(None).to_numpy(), side="right") - 1
    res = {}
    for nm, g in (("vs_dep", g_dep), ("vs_const15", g_15)):
        per = [round(float(g[yr == k].sum()), 4) for k in range(4)]
        dd = pd.Series(g).groupby(day).sum()
        bs = np.array([dd.sample(len(dd), replace=True, random_state=int(rng.integers(1e9))).sum() for _ in range(2000)])
        res[nm] = dict(per_year=per, total=round(float(g.sum()), 4), boot_p_le0=round(float((bs <= 0).mean()), 4),
                       boot_ci90=[round(float(np.quantile(bs, q)), 3) for q in (0.05, 0.95)])
    res["switch"] = pd.crosstab(p.tp_dep, p.tp_new).to_dict()
    res["gain_vs_dep_by_rung"] = {str(k): round(float(g_dep[p.k.to_numpy() == k].sum()), 4) for k in H.R2}
    res["gain_vs_dep_by_sym"] = {s_: round(float(g_dep[p.sym.to_numpy() == s_].sum()), 4) for s_ in H.MAJORS}
    out[v] = res
    print(v, json.dumps(res))
(HERE / "diagnostics.json").write_text(json.dumps(out, indent=1, default=str))
