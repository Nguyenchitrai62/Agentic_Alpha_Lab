"""Dev-only: anatomy of CB's drawdowns (2021-09-24 .. 2025-09-24 only). For every drawdown deeper than 8% on the 4h close path:
peak / trough dates, depth, days to trough, share of the loss from the book vs the dip sleeve, the worst 1-day and 3-day losses inside it,
and the BTC move over the episode."""
import importlib.util, json
from pathlib import Path
import numpy as np, pandas as pd
RD = Path("research/parallel/rounds/parallel-20260906-r2")
def L(n, p):
    s = importlib.util.spec_from_file_location(n, p); m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
v221 = L("v221", RD / "v221/v221_grid_hysteresis.py"); eu, v216 = v221.eu, v221.v216
books154, opens = eu.er.v154_books(); cols, idx, C = list(books154.columns), books154.index, eu.er.CACHE
m = {k: pd.read_parquet(C / f).reindex(idx).fillna(0.0)[cols] for k, f in (("A", "member_A_O1_orders.parquet"), ("Aq", "member_Aq_O1_orders.parquet"), ("B", "member_B_tv.parquet"), ("Bq", "member_Bq_tv.parquet"))}
D = pd.read_parquet(C / "members_v154.parquet").xs("D", axis=1, level=0).reindex(idx).fillna(0.0)[cols]
Dq = pd.read_parquet(C / "members_quarterly_D.parquet").reindex(idx).fillna(0.0)[cols]
cb = 0.8 * (0.5 * (m["A"] + m["B"]) / 2 + 0.5 * (m["Aq"] + m["Bq"]) / 2) + 0.2 * (D + Dq) / 2
att, path = [], {}
eu.simulate(cb, opens, eu.prepare(books154, opens), trade=dict(v216.GRID, policy=v216.grid_policy(v221.B_ABS, v221.B_REL)), win_start=5,
            attrib=att, path_out=path, **dict(v221.KW, sleeve_stop_mode="close5", sleeve_backstop=8.0, m_sleeve_sl=4.0, sleeve_risk_budget=0.18))
t = pd.DatetimeIndex(path["t"]); eq = pd.Series(path["eq"], t)
a = pd.DataFrame({"book": [float(np.sum(x[1])) for x in att], "sleeve": [float(x[2]) for x in att]}, index=pd.DatetimeIndex([x[0] for x in att]))
lo, hi = pd.Timestamp("2021-09-24", tz="UTC"), pd.Timestamp("2025-09-24", tz="UTC")
eq = eq[(eq.index >= lo) & (eq.index < hi)]; eq = eq / eq.iloc[0]
a = a.reindex(eq.index).fillna(0.0)
btc = opens["BTCUSDT"].reindex(eq.index)
peak = eq.cummax(); dd = 1 - eq / peak
eps, i = [], 0
vals = dd.to_numpy()
while i < len(vals):
    if vals[i] > 0.08:
        j = i
        while j < len(vals) and vals[j] > 0: j += 1
        seg = slice(i, j); tr_i = i + int(np.argmax(vals[seg]))
        pk = eq.index[max(i - 1, 0)]; pk = peak.index[peak.iloc[:i].to_numpy().argmax()] if i > 0 else eq.index[0]
        win = (eq.index >= pk) & (eq.index <= eq.index[tr_i])
        eb, es = a["book"][win], a["sleeve"][win]
        daily = eq[win].resample("1D").last().pct_change()
        eps.append(dict(peak=str(pk.date()), trough=str(eq.index[tr_i].date()), depth=round(100 * vals[tr_i], 1),
                        days=(eq.index[tr_i] - pk).days, book_sum=round(100 * eb.sum(), 1), sleeve_sum=round(100 * es.sum(), 1),
                        worst_day=round(100 * daily.min(), 1), worst_3d=round(100 * (eq[win].resample("1D").last().pct_change(3).min()), 1),
                        btc_move=round(100 * (btc[eq.index[tr_i]] / btc[pk] - 1), 1)))
        i = j
    else:
        i += 1
for e in eps: print(e)
Path("research/diagnostics/cb_dd/cb_dd_dev.json").write_text(json.dumps(eps, indent=1))
