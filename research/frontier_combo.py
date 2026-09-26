"""Combine out-of-sample daily return streams (equal-risk weights, not optimised) and find the risk needed for 5%/month."""
import sys, numpy as np, pandas as pd
sys.path.insert(0, "scripts")
import agentic_alpha_lab.research_vf as V
from frontier import oos_returns, metrics, TARGET
import importlib.util
ctx = V.load_context_extended("4h")
rs, _ = oos_returns(ctx, "regime_scaled")
# majors TSMOM (portfolio DD-scaled K, as in research/mj_portfolio_risk.py) OOS daily returns
spec = importlib.util.spec_from_file_location("mjp", "research/mj_portfolio_risk.py")
src = open("research/mj_portfolio_risk.py").read().split("for anchor in V.ANCHORS:")[0]
ns = {}; sys.argv = ["x", "BTCUSDT,ETHUSDT,SOLUSDT,BNBUSDT,XRPUSDT", "tsmom"]; exec(src, ns)
parts = []
for anchor in V.ANCHORS:
    sel_curves, fwd = {}, {}
    for s, c in ns["ctxs"].items():
        w = V.windows(c, anchor, None); best, score = None, -np.inf
        for p in ns["grid"]:
            st = ns["summarize_curve"](ns["position_backtest"](c.bars, ns["fn"](c, p, fit_end=w["sel"][1]), *w["sel"], ns["NORMAL"], c.fr, c.fc))
            if st["changes"] >= 10 and st["sharpe"] > score: best, score = p, st["sharpe"]
        sel_curves[s] = ns["curve"](c, ns["fn"](c, best, fit_end=w["sel"][1]), w["sel"], ns["NORMAL"])
        fwd[s] = ns["curve"](c, ns["fn"](c, best, fit_end=w["fwd"][0]), w["fwd"], ns["NORMAL"])
    def port(curves):
        idx = sorted(set().union(*[c.index for c in curves.values()]))
        return pd.DataFrame({s: c.reindex(idx).ffill().pct_change().fillna(0.0) for s, c in curves.items()}).mean(axis=1)
    e = (1 + port(sel_curves)).cumprod(); dd1 = float(np.max(1 - e / e.cummax()))
    K = np.floor(min(2.0, 0.20 / max(dd1, 1e-6)) * 20) / 20
    parts.append(port(fwd) * K)
ts = pd.concat(parts); ts = ts.groupby(ts.index.floor("D")).apply(lambda x: float(np.prod(1 + x) - 1))
carry = pd.read_parquet("artifacts/research/carry/carry_oos_fee0.0004.parquet")["carry"]; carry = carry.groupby(carry.index.floor("D")).apply(lambda x: float(np.prod(1 + x) - 1))
df = pd.DataFrame({"regime_scaled_btc": rs, "tsmom_majors": ts, "carry_majors": carry}).fillna(0.0)
df = df[df.index >= pd.Timestamp("2021-09-24", tz="UTC")]
print("correlations:\n", df.corr().round(2))
vol = df.std()
w = (1 / vol) / (1 / vol).sum()
print("equal-risk weights:", w.round(3).to_dict())
for name, r in list(df.items()) + [("COMBINED", (df * w).sum(axis=1))]:
    c, d, y = metrics(r)
    lo, hi = 0.0, 30.0
    for _ in range(60):
        lam = (lo + hi) / 2; ct, dt, _ = metrics(r * lam); lo, hi = (lam, hi) if ct < TARGET else (lo, lam)
    ct, dt, yt = metrics(r * lam)
    print(f"{name:18s} OOS CAGR {100*c:6.1f}% maxDD {100*d:5.1f}% Calmar {c/d if d>0 else float('nan'):5.2f} | for 5%/mo need x{lam:.2f} -> DD {100*dt:.1f}%, yearly {[round(100*v,1) for v in yt]}")

print("\n== Realistic allocations: capital split across books, per-book leverage caps (trend <= 2x, carry <= 3x)")
def full(r):
    c, d, y = metrics(r)
    hid = r[r.index >= pd.Timestamp("2025-09-24", tz="UTC")]
    return c, d, float(np.prod(1 + hid) - 1)
rows = []
for a_rs, a_ts, a_ca in [(1, 0, 0), (0, 1, 0), (0.5, 0.5, 0), (0.5, 0, 0.5), (0.4, 0.3, 0.3), (0.34, 0.33, 0.33)]:
    for l_tr in (1.0, 1.5, 2.0):
        for l_ca in (1.0, 3.0):
            if a_ca == 0 and l_ca > 1: continue
            r = a_rs * df["regime_scaled_btc"] * l_tr + a_ts * df["tsmom_majors"] * l_tr + a_ca * df["carry_majors"] * l_ca
            c, d, h = full(r)
            rows.append(dict(split=f"RS {a_rs} / TS {a_ts} / carry {a_ca}", trend_lev=l_tr, carry_lev=l_ca, cagr=round(100*c,1), monthly=round(100*((1+c)**(1/12)-1),2), maxdd=round(100*d,1), hidden_year=round(100*h,1)))
out = pd.DataFrame(rows).sort_values("monthly", ascending=False)
print(out.to_string(index=False))
print("\nBest monthly with max DD <= 20%:"); print(out[out.maxdd <= 20].head(3).to_string(index=False))
