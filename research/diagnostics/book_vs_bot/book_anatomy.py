"""Dev-only diagnostic (dev years 2021-2024 only; not a selection input by itself): anatomy of the MANUAL (book-only) G2 trades -
contribution by coin, side, exit kind, holding time, entry signal strength. Informs which genes the next MANUAL search gets.
  python research/diagnostics/book_vs_bot/book_anatomy.py
"""
import importlib.util, json
from pathlib import Path
import numpy as np, pandas as pd
RD = Path("research/parallel/rounds/parallel-20260906-r2")
s = importlib.util.spec_from_file_location("v307r", RD / "v307/v307_manual_book_evolution.py"); m = importlib.util.module_from_spec(s); s.loader.exec_module(m)
m.init_worker(); W = m.W; eu = W["eu"]
d = m.decode(m.encode({}))
books = pd.DataFrame(sum(d[n] * W["grp"][n] for n in m.MEM) / sum(d[n] for n in m.MEM), index=W["idx"], columns=W["cols"])
trade = dict(W["v216"].GRID, policy=m.v306._policy(0.03, 0.40, 6))
ev = []
r = eu.simulate(books, W["opens"], W["prep"], trade=trade, win_start=5, events=ev, sleeve=False, **{k: v for k, v in W["KW"].items() if k != "sleeve"})
end = W["anchors"][4]
pos, rows = {}, []
for e in ev:
    k, sym = e["kind"], e.get("symbol")
    if k == "book_fill":
        q = abs(e["weight"]) / e["price"]
        pos[sym] = dict(t=e["t"], side=1 if e["side"] == "buy" else -1, qty=q, cost=q * e["price"], proceeds=0.0, fees=q * e["price"] * eu.MAKER, w0=abs(e["weight"]), adds=0)
        continue
    o = pos.get(sym)
    if o is None:
        continue
    if k == "book_add":
        q = abs(e["weight"]) / e["price"]; o["qty"] += q; o["cost"] += q * e["price"]; o["fees"] += q * e["price"] * eu.MAKER; o["adds"] += 1
    elif k in ("book_reduce", "book_partial"):
        q = min(abs(e["weight"]) / e["price"], o["qty"]); o["qty"] -= q; o["proceeds"] += q * e["price"]; o["fees"] += q * e["price"] * eu.MAKER
    elif k in ("book_stop", "book_tp", "book_close"):
        o["proceeds"] += o["qty"] * e["price"]; o["fees"] += o["qty"] * e["price"] * (eu.TAKER if k == "book_stop" else eu.MAKER)
        net = (o["side"] * (o["proceeds"] - o["cost"]) - o["fees"]) / o["cost"]
        rows.append(dict(t=o["t"], sym=sym, side=o["side"], exit=k, net=net, pnl_w=net * o["w0"], hours=(e["t"] - o["t"]).total_seconds() / 3600, adds=o["adds"], w0=o["w0"]))
        pos.pop(sym)
df = pd.DataFrame(rows)
df = df[df.t < end]
df["year"] = [str(next(a.year for a in reversed(W["anchors"]) if t >= a)) for t in df.t]
def tab(g):
    x = df.groupby(g).agg(n=("net", "size"), win=("net", lambda v: (v > 0).mean()), avg_net_pct=("net", lambda v: 100 * v.mean()),
                          sum_pnl_w=("pnl_w", "sum"), med_h=("hours", "median"))
    return x.round(4)
out = {}
for g in (["side"], ["sym"], ["exit"], ["year", "side"], ["sym", "side"]):
    t = tab(g); out["/".join(g)] = t.reset_index().to_dict("records"); print(t, "\n", flush=True)
df["hbin"] = pd.cut(df.hours, [0, 12, 24, 48, 96, 1e5])
t = tab(["hbin"]); print(t, flush=True)
Path("research/diagnostics/book_vs_bot/book_anatomy.json").write_text(json.dumps(out, indent=1, default=str))
