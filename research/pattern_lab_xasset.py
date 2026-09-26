"""Frozen candidate (r4 R0 = r3 B) run unchanged on other USD-M perps."""
import json, sys
import numpy as np, pandas as pd
sys.path.insert(0, "scripts")
from pattern_lab_meta import idx_first, idx_last
from agentic_alpha_lab.backtest.ma_ribbon import NORMAL, STRESS, backtest, funding_per_bar, summarize
from agentic_alpha_lab.signals.trend_advisor import candidate_target, SIZE
from agentic_alpha_lab.backtest.ma_ribbon import ribbon_target
D = "data/raw/xasset_20260924"
rows = []
for sym in ["ETHUSDT","BNBUSDT","SOLUSDT","XRPUSDT","ADAUSDT","DOGEUSDT","LINKUSDT","LTCUSDT","BCHUSDT","TRXUSDT"]:
    b4 = pd.read_parquet(f"{D}/{sym}_4h.parquet"); d1 = pd.read_parquet(f"{D}/{sym}_1d.parquet"); f = pd.read_parquet(f"{D}/{sym}_funding.parquet")
    fr, fc = funding_per_bar(b4, f)
    tgt = candidate_target(b4, d1)
    prim = ribbon_target(b4["close"], 20, 200, "ribbon", "long", "EMA")
    for win, (a, z) in {"dev_2021_2025": ("2021-01-01", "2025-09-13"), "last_year": ("2025-09-24", "2026-09-22")}.items():
        rg = (idx_first(b4, a), idx_last(b4, z))
        for name, t, size in (("B_1x", tgt, None), ("B_0.65x", tgt, np.full(len(b4), SIZE)), ("A_unfiltered", prim, None), ("buy_hold", np.ones(len(b4), int), None)):
            for cn, c in (("normal", NORMAL), ("stress", STRESS)):
                if name == "buy_hold" and cn == "stress": continue
                s = summarize(backtest(b4, t, rg[0], rg[1], c, fr, fc, size))
                rows.append(dict(sym=sym, window=win, rule=name, costs=cn, net=s["net_pct"], dd=s["dd_intrabar_pct"], sharpe=s["sharpe"], trades=s["trades"], monthly=s["monthly_geo_pct"]))
df = pd.DataFrame(rows).round(2)
df.to_csv("artifacts/research/pattern_lab/xasset/results.csv", index=False)
for win in ("dev_2021_2025", "last_year"):
    print("==", win)
    p = df[df.window == win].pivot_table(index="sym", columns=["rule", "costs"], values="net")
    print(p.to_string())
    for r in ("B_0.65x", "B_1x", "A_unfiltered"):
        x = df[(df.window == win) & (df.rule == r)]
        print(r, "positive normal:", (x[x.costs=="normal"].net > 0).sum(), "/10; positive stress:", (x[x.costs=="stress"].net > 0).sum(), "/10; median sharpe", x[x.costs=="normal"].sharpe.median(), "median dd", x[x.costs=="normal"].dd.median())
    bh = df[(df.window == win) & (df.rule == "buy_hold")]; print("buy_hold positive", (bh.net > 0).sum(), "/10 median sharpe", bh.sharpe.median(), "median dd", bh.dd.median())
