"""Diagnostic (first four walk-forward years only, not registered): do bids placed k * sigma_24h below the 24h high pay like the 4h dip ladder?

The 4h ladder rests 2.5-4 sigma_4h below the bar open, so a slow multi-bar slide never reaches it. Here, per holding bar and coin, a limit
bid at ref * (1 - k sigma_24h), ref = highest 4h open of the last 24h incl. the holding-bar open, sigma_24h = sigma_4h * sqrt(6) (all known
at the bar open); only bids below the holding-bar open. Fill on a 1m trade-through from minute 16 (as the sleeve), then the sleeve's exit
rules: TP limit 1 sigma_4h above, SL 5 sigma_4h below (market), else market at the next 4h open. 'incremental' = bids ABOVE the first 4h rung
(fills the 4h ladder would not have).
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

RD = Path("research/parallel/rounds/parallel-20260906-r2")
spec = importlib.util.spec_from_file_location("eu", RD / "engine_user/engine_user.py")
eu = importlib.util.module_from_spec(spec)
spec.loader.exec_module(eu)
books154, opens = eu.er.v154_books()
cols, idx = list(books154.columns), books154.index
p = eu.prepare(books154, opens)
O, H, L = p["O"], p["H"], p["L"]
o = opens.reindex(idx)[cols].to_numpy(float)
o1, o2, sig4 = p["o1"], p["o2"], p["sig4"]
anchors = [pd.Timestamp(a, tz="UTC") for a in eu.ANCHORS]
t_hold = idx + pd.Timedelta(hours=4)
MK, TK = eu.MAKER, eu.TAKER
rows = []
for i in range(6, len(idx) - 2):
    if not (anchors[0] <= t_hold[i] < anchors[4]):
        continue
    for a in range(len(cols)):
        s = sig4[i, a]
        if not np.isfinite(s) or not np.isfinite(o1[i, a]) or not np.isfinite(o2[i, a]):
            continue
        ref = max(np.nanmax(o[i - 4:i + 1, a]), o1[i, a])
        r1 = o1[i, a] * (1 - 2.5 * s)
        for k in (1.5, 2.0, 2.5, 3.0):
            lv = ref * (1 - k * s * np.sqrt(6))
            if lv >= o1[i, a]:
                continue
            hit = L[i, 16:239, a].astype(float) < lv
            if not hit.any():
                continue
            f = 16 + int(np.argmax(hit))
            tp, sl = lv * (1 + s), lv * (1 - 5 * s)
            hs, ht = L[i, f + 1:240, a] <= sl, H[i, f + 1:240, a] > tp
            hh = hs | ht
            if hh.any():
                x = f + 1 + int(np.argmax(hh))
                ret = (min(sl, O[i, x, a]) / lv - 1 - MK - TK) if hs[x - f - 1] else (tp / lv - 1 - 2 * MK)
                kind = "sl" if hs[x - f - 1] else "tp"
            else:
                ret, kind = o2[i, a] / lv - 1 - MK - TK, "timeout"
            rows.append(dict(t=t_hold[i], sym=cols[a], k=k, ret=ret, kind=kind, inc=bool(lv > r1),
                             year=max(j for j, a0 in enumerate(anchors) if t_hold[i] >= a0)))
d = pd.DataFrame(rows)
out = {}
for (k, inc), g in d.groupby(["k", "inc"]):
    out[f"k{k}_{'incremental' if inc else 'overlap'}"] = dict(
        n=len(g), mean_pct=round(100 * g.ret.mean(), 3), stop_share=round(float((g.kind == "sl").mean()), 3),
        by_year_mean_pct=[round(100 * g[g.year == y].ret.mean(), 3) if (g.year == y).any() else None for y in range(4)],
        by_year_n=[int((g.year == y).sum()) for y in range(4)])
for k, v in out.items():
    print(k, v)
Path("research/diagnostics/slide_ladder/slide_ladder_dev.json").write_text(json.dumps(out, indent=1))
