"""Report (not a selection input): the deployed G2 pipeline split into the two user-facing products (user 2026-10-02).
  MANUAL = book orders only (sleeve off; same CB books, grid trade mode, minute-5 rule, SL market / TP limit, adverse funding), target 0.25
           (+ a labelled risk-up row at target 0.31, the v306 gene maximum)
  BOT    = G2 bar-open form (book + learned dip ladder, budget 0.26) = v306 seed G2
Both on engine_user; the most recent year of G2 is already spent (deployed), the manual rows are reported on it as well (labelled).
  python research/diagnostics/book_vs_bot/book_vs_bot.py
"""
import importlib.util, json, sys
from pathlib import Path
import numpy as np, pandas as pd
RD = Path("research/parallel/rounds/parallel-20260906-r2")
s = importlib.util.spec_from_file_location("v306r", RD / "v306/v306_walkforward_evolution.py"); m = importlib.util.module_from_spec(s); s.loader.exec_module(m)
m.init_worker(); W = m.W
d = m.decode(m.encode({}))
idx, cols, eu = W["idx"], W["cols"], W["eu"]
wsum = sum(d[n] for n in W["grp"])
books = pd.DataFrame(sum(d[n] * W["grp"][n] for n in W["grp"]) / wsum, index=idx, columns=cols)
size, tp = m._tables(d)
rungs = tuple(k for k in m.U if d[f"r{int(k * 10)}"]); kmap = [m.U.index(k) for k in rungs]
trade = dict(W["v216"].GRID, policy=m._policy(d["b_abs"], d["b_rel"], d["cool"]))
base = dict(W["KW"], m_sl=d["m_sl"], align=d["align"], sleeve_risk_budget=d["budget"], size_mult=d["size_mult"], sleeve_stop_mode="close5",
            m_sleeve_sl=d["sleeve_sl"], sleeve_backstop=d["backstop"])
rows = {"MANUAL_book_only_t25": dict(sleeve=False, target=0.25), "MANUAL_book_only_t31": dict(sleeve=False, target=0.31),
        "BOT_G2_book_plus_dip": dict(target=0.25, sleeve_fill_size=lambda i, a, r, f: float(size[i, a, kmap[r]]),
                                     sleeve_tp=lambda i, a, r, f: float(tp[i, a, kmap[r]]), rungs=rungs)}
out = {}
for k, extra in rows.items():
    ev = []
    r = eu.simulate(books, W["opens"], W["prep"], trade=trade, win_start=5, events=ev, **dict(base, **extra))
    tr = m._trade_rows(ev)
    yrs = []
    for y in range(5):
        a0 = W["anchors"][y]; a1 = a0 + pd.Timedelta(days=365)
        bk = [x[2] for x in tr if x[0] == "book" and a0 <= x[1] < a1]; rg = [x[2] for x in tr if x[0] == "rung" and a0 <= x[1] < a1]
        yy = r["yearly"][y]
        yrs.append(dict(year=str(a0.date()), net=yy["net_pct"], monthly=yy["monthly_pct"], dd=yy["dd_1m_pct"], n_book=len(bk),
                        win_book=round(float(np.mean([v > 0 for v in bk])), 3) if bk else None, n_dip=len(rg),
                        win_dip=round(float(np.mean([v > 0 for v in rg])), 3) if rg else None,
                        win_all=round(float(np.mean([v > 0 for v in bk + rg])), 3) if bk + rg else None,
                        avg_book_pct=round(100 * float(np.mean(bk)), 3) if bk else None, avg_dip_pct=round(100 * float(np.mean(rg)), 3) if rg else None))
    out[k] = dict(monthly_dev4=r["monthly_dev4"], monthly_5y=r["monthly_5y"], monthly_last_year=r["monthly_last_year"], gate_dd=r["gate_dd"],
                  dev_dd=max(y["dd"] for y in yrs[:4]), worst_dev_month=min(y["monthly"] for y in yrs[:4]), losing_years=r["losing_years"], years=yrs)
    print(k, json.dumps({kk: v for kk, v in out[k].items() if kk != "years"}), flush=True)
    for y in yrs:
        print("   ", y, flush=True)
Path("research/diagnostics/book_vs_bot/book_vs_bot.json").write_text(json.dumps(out, indent=1))
