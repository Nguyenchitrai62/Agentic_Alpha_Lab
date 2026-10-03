"""Dev-only event study (fills 2021-09-24 .. 2025-09-17): does order-level taker flow just BEFORE a dip fill predict the rung outcome? (BOT idea)
Fills: R2 rules on the 5 majors (v293 replica: rungs 2.5 / 3 / 3.5 / 4 / 5 sigma_4h from minute 16, TP 1 sigma, close5 4 sigma + 8-sigma backstop,
exit next 4h open; y = y1.0). Flow from the kept 1m order-level store (data/raw/aggflow_20260929_orders_1m, minutes strictly before the fill minute):
  imb15      (buy - sell) / (buy + sell) notional over the 15 minutes before the fill
  big_imb15  same for orders >= 100k USDT
  exhaust    sell notional of the last 5 minutes / mean 5-minute sell notional of the 10 minutes before them (selling accelerating > 1)
  big_share  share of >= 100k orders in the 15-minute sell notional
Reports per dev year: Spearman(feature, y) and the mean y of the top / bottom feature tercile.
  python research/diagnostics/dip_flow/dip_flow_dev.py
"""
import glob, importlib.util, json
from pathlib import Path
import numpy as np, pandas as pd
RD = Path("research/parallel/rounds/parallel-20260906-r2")
def L(n, p):
    s = importlib.util.spec_from_file_location(n, p); m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
v293 = L("v293_df", RD / "v293/v293_pooled_exit_agent.py")
eu = L("eu_df", RD / "engine_user/engine_user.py")
v293.RUNGS = (2.5, 3.0, 3.5, 4.0, 5.0)
ANCH = [pd.Timestamp(a, tz="UTC") for a in ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24")]
STOP = pd.Timestamp("2025-09-17", tz="UTC")
BIG = ["100k_300k", "300k_1m", "1m_3m"]
btc = v293.Asset("BTCUSDT")
rows = []
for s in v293.MAJORS:
    A = btc if s == "BTCUSDT" else v293.Asset(s)
    d = v293.fills_of(A, eu.MAKER, eu.TAKER, eu.FUND_LONG, btc)
    d["t_fill"] = pd.to_datetime(d["t_fill"], utc=True)
    d = d[(d.t_fill >= ANCH[0]) & (d.t_fill < STOP)]
    fl = pd.concat([(lambda x: x if "t" in x.columns else x.reset_index().rename(columns={x.index.name or "index": "t"}))(pd.read_parquet(f))
                    for f in sorted(glob.glob(f"data/raw/aggflow_20260929_orders_1m/{s}/*.parquet"))])
    fl["t"] = pd.to_datetime(fl["t"], utc=True)
    fl = fl.drop_duplicates("t").set_index("t").sort_index()
    bc = [c for c in fl.columns if c.startswith("buy_")]; sc = [c for c in fl.columns if c.startswith("sell_")]
    buy, sell = fl[bc].sum(1), fl[sc].sum(1)
    bbig = fl[[f"buy_{b}" for b in BIG if f"buy_{b}" in fl]].sum(1); sbig = fl[[f"sell_{b}" for b in BIG if f"sell_{b}" in fl]].sum(1)
    for t, y in zip(d.t_fill, d["y1.0"]):
        w = slice(t - pd.Timedelta(minutes=15), t - pd.Timedelta(minutes=1))
        b, se, bb, sb = buy.loc[w], sell.loc[w], bbig.loc[w], sbig.loc[w]
        if len(b) < 10 or (b.sum() + se.sum()) <= 0:
            continue
        last5, prev10 = se.iloc[-5:].sum(), se.iloc[:-5].sum() / 2
        rows.append(dict(sym=s, y=y, yr=max(q for q, a in enumerate(ANCH) if t >= a),
                         imb15=(b.sum() - se.sum()) / (b.sum() + se.sum()),
                         big_imb15=(bb.sum() - sb.sum()) / max(bb.sum() + sb.sum(), 1e-9) if (bb.sum() + sb.sum()) > 0 else 0.0,
                         exhaust=last5 / prev10 if prev10 > 0 else np.nan, big_share=sb.sum() / se.sum() if se.sum() > 0 else np.nan))
    print(s, len(d), flush=True)
    if s != "BTCUSDT":
        del A
r = pd.DataFrame(rows)
out = {}
for f in ("imb15", "big_imb15", "exhaust", "big_share"):
    res = []
    for yr, g in r.groupby("yr"):
        g = g.dropna(subset=[f])
        q = g[f].rank(pct=True)
        res.append(dict(yr=int(yr), n=len(g), spearman=round(float(g[[f, "y"]].corr("spearman").iloc[0, 1]), 3),
                        top=round(100 * float(g.y[q > 2 / 3].mean()), 3), bottom=round(100 * float(g.y[q <= 1 / 3].mean()), 3)))
    out[f] = res
    print(f, res, flush=True)
Path("research/diagnostics/dip_flow/dip_flow_dev.json").write_text(json.dumps(out, indent=1))
