"""Dev-only diagnostic (not a selection input): book-only (manual product) return / DD / win frontier of the G2 books and rules over the risk
level (vol target) and the book take-profit. The most recent year is NOT computed into the report (yearly[:4] only).
  python research/diagnostics/book_vs_bot/book_frontier.py
"""
import importlib.util, json
from pathlib import Path
import numpy as np, pandas as pd
RD = Path("research/parallel/rounds/parallel-20260906-r2")
s = importlib.util.spec_from_file_location("v306r", RD / "v306/v306_walkforward_evolution.py"); m = importlib.util.module_from_spec(s); s.loader.exec_module(m)
m.init_worker(); W = m.W
d = m.decode(m.encode({})); idx, cols, eu = W["idx"], W["cols"], W["eu"]
books = pd.DataFrame(sum(d[n] * W["grp"][n] for n in W["grp"]) / sum(d[n] for n in W["grp"]), index=idx, columns=cols)
trade = dict(W["v216"].GRID, policy=m._policy(d["b_abs"], d["b_rel"], d["cool"]))
base = dict(W["KW"], m_sl=d["m_sl"], sleeve=False)
out = {}
import sys
rows = [(f"t{t}_cap{c}", dict(target=t, cap=c)) for t, c in ((0.25, 2.0), (0.25, 3.0), (0.25, 4.0), (0.37, 4.0), (0.50, 4.0), (0.70, 4.0))] if "--cap4" in sys.argv else [(f"t{t}", dict(target=t)) for t in (0.25, 0.31, 0.37, 0.44, 0.50)] + [(f"t0.25_cap3", dict(target=0.25, cap=3.0))]
for k, extra in rows:
    ev = []
    r = eu.simulate(books, W["opens"], W["prep"], trade=trade, win_start=5, events=ev, **dict(base, **extra))
    tr = [x for x in m._trade_rows(ev) if x[1] < W["anchors"][4]]
    ys = r["yearly"][:4]
    geo = 100 * (np.prod([1 + y["net_pct"] / 100 for y in ys]) ** (1 / 48) - 1)
    out[k] = dict(dev4=round(geo, 3), worst=min(y["monthly_pct"] for y in ys), dev_dd=max(y["dd_1m_pct"] for y in ys),
                  years=[(y["anchor"][:4], y["net_pct"], y["dd_1m_pct"]) for y in ys], win=round(float(np.mean([x[2] > 0 for x in tr])), 3), n=len(tr))
    print(k, out[k], flush=True)
Path("research/diagnostics/book_vs_bot/book_frontier" + ("_cap4" if "--cap4" in sys.argv else "") + ".json").write_text(json.dumps(out, indent=1))
