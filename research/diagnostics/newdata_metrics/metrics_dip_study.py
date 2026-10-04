"""Dev-only study: Binance USD-M 5m metrics (top-trader / account long-short ratios, taker long/short volume ratio, open interest) vs the outcome
of the simulated dip-limit fills (research/diagnostics/phase_agents/fills_U.parquet, majors only, t_exit < 2025-09-14).
Features (fixed before looking): a metrics row stamped c is used only from c + 5 min (snapshot lag); as-of strictly before the fill minute.
  tt_ls_z   top-trader position long/short ratio, z vs trailing 7 days (2016 rows)
  acc_ls_z  account long/short ratio, z vs trailing 7 days
  taker_1h  mean taker long/short volume ratio over the last 12 rows (1 h)
  oi_1h     log change of open interest value over the last 1 h;  oi_4h over 4 h;  oi_24h over 24 h
  btc_*     the same for BTCUSDT (market-wide) for every coin
IC = Spearman with y1.0 per calendar year; partial IC = Spearman with the residual of an OLS of y1.0 on x0..x6 (same rows)."""
import json
from pathlib import Path
import numpy as np, pandas as pd
ROOT = Path(__file__).resolve().parents[3]
SY = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]

def feats(s):
    m = pd.read_parquet(ROOT / f"data/raw/um_metrics_20260926/{s}_metrics.parquet")
    m["t"] = pd.to_datetime(m["create_time"], utc=True) + pd.Timedelta(minutes=5)
    m = m.drop_duplicates("t").set_index("t").sort_index()
    f = pd.DataFrame(index=m.index)
    z = lambda x: (x - x.rolling(2016, min_periods=500).mean()) / x.rolling(2016, min_periods=500).std()
    f["tt_ls_z"] = z(m["sum_toptrader_long_short_ratio"])
    f["acc_ls_z"] = z(m["count_long_short_ratio"])
    f["taker_1h"] = m["sum_taker_long_short_vol_ratio"].rolling(12, min_periods=6).mean()
    oi = np.log(m["sum_open_interest_value"])
    for h, k in (("1h", 12), ("4h", 48), ("24h", 288)):
        f[f"oi_{h}"] = oi - oi.shift(k)
    return f

F = {s: feats(s) for s in SY}
fl = pd.read_parquet(ROOT / "research/diagnostics/phase_agents/fills_U.parquet")
fl = fl[fl.sym.isin(SY) & (fl.t_exit < pd.Timestamp("2025-09-14", tz="UTC"))].sort_values("t_fill").reset_index(drop=True)
rows = []
for s in SY:
    g = fl[fl.sym == s]
    a = pd.merge_asof(g[["t_fill"]].reset_index(), F[s].reset_index().rename(columns={"t": "ta"}), left_on="t_fill", right_on="ta",
                      direction="backward", allow_exact_matches=False)
    b = pd.merge_asof(g[["t_fill"]].reset_index(), F["BTCUSDT"].add_prefix("btc_").reset_index().rename(columns={"t": "ta"}),
                      left_on="t_fill", right_on="ta", direction="backward", allow_exact_matches=False)
    assert (a["ta"].dropna() < a.loc[a["ta"].notna(), "t_fill"]).all()
    rows.append(pd.concat([a.set_index("index").drop(columns=["t_fill", "ta"]), b.set_index("index").drop(columns=["t_fill", "ta"])], axis=1))
X = pd.concat(rows).sort_index()
d = pd.concat([fl, X], axis=1)
cols = [c for c in X.columns]
xs = [f"x{i}" for i in range(7)]
d["year"] = d.t_fill.dt.year
out = {}
for c in cols:
    ok = d[[c, "y1.0"] + xs].dropna()
    if len(ok) < 500:
        continue
    A = np.column_stack([np.ones(len(ok))] + [ok[x].to_numpy(float) for x in xs])
    res = ok["y1.0"].to_numpy() - A @ np.linalg.lstsq(A, ok["y1.0"].to_numpy(), rcond=None)[0]
    pic = pd.Series(ok[c].to_numpy()).corr(pd.Series(res), method="spearman")
    yr = {int(y): round(float(g[c].corr(g["y1.0"], method="spearman")), 4) for y, g in ok.join(d["year"]).groupby("year") if len(g) > 200}
    out[c] = dict(n=len(ok), ic_years=yr, partial_ic=round(float(pic), 4), t_partial=round(float(pic * np.sqrt(len(ok))), 2),
                  same_sign=bool(len(set(np.sign(list(yr.values())))) == 1))
    print(c, out[c], flush=True)
(Path(__file__).parent / "metrics_dip_study.json").write_text(json.dumps(out, indent=1))
