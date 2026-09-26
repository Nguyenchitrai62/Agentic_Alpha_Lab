"""Blind v95+v96 audit reproduction from OPENCODE_V95_V96_AUDIT.md spec.

Reads only raw data under data/raw/*, artifacts/research/carry/* (not used here),
audited replications v92_audit/predictions_5asset.csv and v93_v94_audit/predictions_v94.csv,
and src/agentic_alpha_lab/patterns/* for context features.
Does NOT read research/.../v95/* or research/.../v96/* (blind until replication.json is saved).

A1 (v96): combined = 0.5*W_v92*s_v92 + 0.5*W_v94_ls*s_v94, each book own causal
  20% vol target cap 2 NaN->1, simulated with v92 execution (fee 0.0002, long funding 0.00005/bar).
A2 (v95): v92 panel + (i) xs pct-ranks/excess/share/mean, (ii) f7 z vs trailing 180d,
  (iii) ctx_ from breadth/positioning/macro/implied_vol on BTC 4h incl opened year,
  keep cols >20% non-NaN, merge on open_time. Train v92 HGB, v92 long-only book.
"""
import json
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.ensemble import HistGradientBoostingRegressor

ROOT = Path(__file__).resolve().parents[5]
OUT_DIR = Path(__file__).resolve().parent
V92_DIR = ROOT / "research/parallel/rounds/parallel-20260906-r2/v92_audit"
V9394_DIR = ROOT / "research/parallel/rounds/parallel-20260906-r2/v93_v94_audit"
SYMS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
ANCHORS = ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")
PD = 6
H = 42
EMBARGO_BARS = H + 10 * PD  # 102 bars = 408h
BTC_DIR = ROOT / "data/raw/ma_ribbon_20260924"
XS_DIR = ROOT / "data/raw/xs_universe_20260924"
SPOT_DIR = ROOT / "data/raw/spot_majors_20260925"
HGB_PARAMS = dict(max_depth=4, learning_rate=0.03, max_iter=400,
                  min_samples_leaf=300, l2_regularization=1.0, random_state=0)


def load_asset(s):
    if s == "BTCUSDT":
        b = pd.read_parquet(BTC_DIR / "klines_4h.parquet")
        d = pd.read_parquet(BTC_DIR / "klines_1d.parquet")
        f = pd.read_parquet(BTC_DIR / "funding.parquet")
    else:
        b = pd.read_parquet(XS_DIR / f"{s}_4h.parquet")
        d = pd.read_parquet(XS_DIR / f"{s}_1d.parquet")
        f = pd.read_parquet(XS_DIR / f"{s}_funding.parquet")
    for x in (b, d):
        x["open_time"] = pd.to_datetime(x["open_time"], utc=True)
        x["close_time"] = pd.to_datetime(x["close_time"], utc=True)
    f["fundingTime"] = pd.to_datetime(f["fundingTime"], utc=True)
    b = b.sort_values("open_time").reset_index(drop=True)
    d = d.sort_values("open_time").reset_index(drop=True)
    f = f.sort_values("fundingTime").reset_index(drop=True)
    if not (SPOT_DIR / f"{s}_spot_4h_2017.parquet").exists():
        s4 = b.iloc[:0].copy(); s1 = d.iloc[:0].copy()
    else:
        s4 = pd.read_parquet(SPOT_DIR / f"{s}_spot_4h_2017.parquet")
        s1 = pd.read_parquet(SPOT_DIR / f"{s}_spot_1d_2017.parquet")
    for x in (s4, s1):
        x["open_time"] = pd.to_datetime(x["open_time"], utc=True)
        x["close_time"] = pd.to_datetime(x["close_time"], utc=True)
    first_4h = b["open_time"].min()
    first_1d = d["open_time"].min()
    pre4 = s4[s4["open_time"] < first_4h].copy()
    pre1 = s1[s1["open_time"] < first_1d].copy()
    b = pd.concat([pre4, b], ignore_index=True).sort_values("open_time").reset_index(drop=True)
    d = pd.concat([pre1, d], ignore_index=True).sort_values("open_time").reset_index(drop=True)
    return b, d, f


def base_features(b, d, f):
    c = b["close"].astype(float)
    lc = np.log(c)
    r1 = lc.diff()
    x = pd.DataFrame(index=b.index)
    vol42 = r1.rolling(42).std()
    for k in (6, 42, 90, 180, 540):
        dk = lc.diff(k)
        x[f"ret{k}"] = dk
        x[f"snr{k}"] = dk / (vol42 * np.sqrt(k))
    x["vol42"] = vol42
    x["vol180"] = r1.rolling(180).std()
    x["vol_ratio"] = x["vol42"] / x["vol180"]
    for sp in (20, 200):
        x[f"ema{sp}"] = np.log(c / c.ewm(span=sp, adjust=False, min_periods=sp).mean())
    dc = d["close"].astype(float)
    sma50 = dc.rolling(50).mean()
    sma200 = dc.rolling(200).mean()
    dfe = pd.DataFrame({
        "t": d["close_time"],
        "d50": np.log(dc / sma50),
        "d200": np.log(dc / sma200),
        "rib": np.where((dc > sma50) & (sma50 > sma200), 1.0,
                        np.where((dc < sma50) & (sma50 < sma200), -1.0, 0.0)),
    })
    j = pd.merge_asof(pd.DataFrame({"t": b["close_time"]}), dfe.sort_values("t"), on="t", direction="backward")
    x[["d50", "d200", "rib"]] = j[["d50", "d200", "rib"]].to_numpy()
    fr = f.set_index("fundingTime")["fundingRate"].astype(float)
    fm = pd.DataFrame({"t": fr.index,
                       "f7": fr.rolling(21, min_periods=3).mean().to_numpy(),
                       "f30": fr.rolling(90, min_periods=9).mean().to_numpy()})
    jf = pd.merge_asof(pd.DataFrame({"t": b["close_time"]}), fm.sort_values("t"), on="t", direction="backward")
    x["f7"] = jf["f7"].to_numpy() * 1e4
    x["f30"] = jf["f30"].to_numpy() * 1e4
    lv = np.log(b["quote_volume"].astype(float).clip(lower=1))
    x["volz"] = (lv - lv.rolling(180).mean()) / lv.rolling(180).std()
    o = b["open"].astype(float).to_numpy()
    n = len(b)
    fwd = np.full(n, np.nan)
    if n > 1 + H:
        fwd[: n - 1 - H] = np.log(o[1 + H:] / o[1: n - H])
    y = np.clip(fwd / (vol42.to_numpy() * np.sqrt(H)), -4, 4)
    return x, y


def build_base_panel():
    rows = []
    for i, s in enumerate(SYMS):
        b, d, f = load_asset(s)
        x, y = base_features(b, d, f)
        x["asset"] = i
        x["y"] = y
        x["t"] = b["open_time"]
        x["open"] = b["open"].astype(float).to_numpy()
        x["sym"] = s
        x["bar"] = np.arange(len(b))
        rows.append(x)
    panel = pd.concat(rows, ignore_index=True)
    btc = panel[panel.sym == "BTCUSDT"].set_index("t")[["ret42", "ret180", "rib", "snr42"]].add_prefix("btc_")
    panel = panel.join(btc, on="t")
    return panel


def compute_weights_longonly(oos):
    Wdict = {}
    for s, g in oos.groupby("sym"):
        g = g.set_index("t").sort_index()
        sig = g["pred"].clip(lower=0) / 0.5
        sig = sig.where(g["rib"] != -1, 0.0).clip(upper=1.0)
        Wdict[s] = sig / (g["vol42"] * np.sqrt(PD * 365))
    W = pd.DataFrame(Wdict).sort_index().fillna(0.0)
    W = W.replace([np.inf, -np.inf], np.nan).fillna(0.0)
    row_sum = W.abs().sum(axis=1)
    n_pos = W.gt(0).sum(axis=1).clip(lower=1)
    W = W.div(row_sum.clip(lower=1e-9), axis=0).mul(row_sum.gt(0), axis=0)
    W = W.mul((n_pos / 5).clip(upper=1.0), axis=0)
    keep = pd.Series(np.arange(len(W)) % PD == 0, index=W.index)
    W = W.where(keep, np.nan).ffill().fillna(0.0)
    return W


def compute_weights_longshort(oos):
    Wdict = {}
    for s, g in oos.groupby("sym"):
        g = g.set_index("t").sort_index()
        p = g["pred"].astype(float)
        rib = g["rib"].astype(float)
        long = (p.clip(lower=0) / 0.5).clip(upper=1.0).where(rib != -1, 0.0)
        short = ((-p).clip(lower=0) / 0.5).clip(upper=1.0).where(rib != 1, 0.0)
        raw = (long - short) / (g["vol42"].astype(float) * np.sqrt(PD * 365))
        raw = raw.replace([np.inf, -np.inf], np.nan).fillna(0.0)
        Wdict[s] = raw
    rawW = pd.DataFrame(Wdict).sort_index()
    row_sum = rawW.abs().sum(axis=1)
    n_nz = (rawW != 0).sum(axis=1).clip(lower=1)
    W = rawW.div(row_sum.clip(lower=1e-9), axis=0).mul(row_sum.gt(0), axis=0)
    W = W.mul((n_nz / 5).clip(upper=1.0), axis=0).fillna(0.0)
    keep = pd.Series(np.arange(len(W)) % PD == 0, index=W.index)
    W = W.where(keep, np.nan).ffill().fillna(0.0)
    return W


def vol_scale_for_book(W, panel, vol_target=0.20):
    o = panel.pivot_table(index="t", columns="sym", values="open").reindex(W.index).sort_index()
    for s in SYMS:
        if s not in o.columns:
            o[s] = np.nan
    o = o[list(SYMS)]
    ret1 = o / o.shift(1) - 1
    book = (W.shift(2).fillna(0.0) * ret1.fillna(0.0)).sum(axis=1)
    vol = book.rolling(360, min_periods=120).std(ddof=1) * np.sqrt(2190)
    scale = (vol_target / vol).clip(upper=2.0).fillna(1.0)
    scale = scale.replace([np.inf, -np.inf], 2.0).fillna(1.0)
    return scale, book, vol, o


def stats(net, turn):
    eq = (1 + net).cumprod()
    days = len(net) / PD
    g = float(eq.iloc[-1]) if len(eq) else float("nan")
    dd = float(np.max(1 - eq / eq.cummax())) if len(eq) else float("nan")
    return dict(net_pct=round(100 * (g - 1), 2),
                monthly_geometric_net_percent=round(100 * (g ** (30.4375 / days) - 1), 3) if days > 0 else float("nan"),
                max_drawdown_percent=round(100 * dd, 2),
                fills=int((turn > 1e-6).sum()),
                months=round(days / 30.4375, 1),
                bars=int(len(net)))


def yearly_slices(net, turn):
    out = []
    for anchor in ANCHORS:
        a = pd.Timestamp(anchor, tz="UTC")
        m = (net.index >= a) & (net.index < a + pd.Timedelta(days=365))
        st = stats(net[m], turn[m])
        st["anchor"] = anchor
        out.append(st)
    return out


def run_a1():
    pred92 = pd.read_csv(V92_DIR / "predictions_5asset.csv", parse_dates=["t"])
    pred92["t"] = pd.to_datetime(pred92["t"], utc=True)
    oos92 = pred92.sort_values(["t", "sym"]).reset_index(drop=True)
    pred94 = pd.read_csv(V9394_DIR / "predictions_v94.csv", parse_dates=["t"])
    pred94["t"] = pd.to_datetime(pred94["t"], utc=True)
    oos94 = pred94.sort_values(["t", "sym"]).reset_index(drop=True)
    W92 = compute_weights_longonly(oos92)
    W94 = compute_weights_longshort(oos94)
    # panel opens from v92 oos (same grid as v94)
    panel = oos92.pivot_table(index="t", columns="sym", values="open")
    panel = panel[list(SYMS)]
    # each book's own causal 20% vol scale
    # rebuild minimal panel-like for vol_scale (needs pivot inside); use oos opens via fake panel
    fake = pd.DataFrame({"t": [], "sym": [], "open": []})
    # vol_scale_for_book expects panel with t/sym/open; construct from oos92
    vol_panel = oos92[["t", "sym", "open"]].copy()
    # build pivot inside function via panel arg: create object with pivot_table? use vol_panel as panel
    # volumne: emulate by constructing panel df with columns t,sym,open
    class _P:
        pass
    # simpler: inline vol computation using opens pivot
    o = oos92.pivot_table(index="t", columns="sym", values="open").reindex(W92.index).sort_index()
    o = o[list(SYMS)]
    ret1 = o / o.shift(1) - 1
    def _scale(W):
        book = (W.shift(2).fillna(0.0) * ret1.fillna(0.0)).sum(axis=1)
        vol = book.rolling(360, min_periods=120).std(ddof=1) * np.sqrt(2190)
        sc = (0.20 / vol).clip(upper=2.0).fillna(1.0)
        sc = sc.replace([np.inf, -np.inf], 2.0).fillna(1.0)
        return sc, book, vol
    s92, book92, vol92 = _scale(W92)
    # align W94 index to same grid (should already match)
    W94a = W94.reindex(W92.index).fillna(0.0)
    s94, book94, vol94 = _scale(W94a)
    Wc = 0.5 * W92.mul(s92, axis=0) + 0.5 * W94a.mul(s94, axis=0)
    r_fwd = (o.shift(-2) / o.shift(-1) - 1).fillna(0.0)
    turn = Wc.diff().abs().sum(axis=1).fillna(Wc.abs().sum(axis=1))
    funding = Wc.clip(lower=0).sum(axis=1) * 0.00005
    net = (Wc * r_fwd).sum(axis=1) - turn * 0.0002 - funding
    yearly = yearly_slices(net, turn)
    return dict(Wc=Wc, net=net, turn=turn, s92=s92, s94=s94, yearly=yearly, o=o)


def add_xs_features(panel):
    # (i) cross-sectional features at each bar
    panel = panel.copy()
    # pct-rank 0..1 as (rank-1)/(n-1), average ranks
    for col in ("ret42", "ret180", "snr42"):
        rk = panel.groupby("t")[col].rank(method="average", pct=False)
        cnt = panel.groupby("t")[col].transform("count")
        panel[f"xs_pct_{col}"] = (rk - 1) / (cnt - 1).replace(0, np.nan)
    btc_ret42 = panel[panel.sym == "BTCUSDT"].set_index("t")["ret42"]
    panel["xs_excess_ret42_vs_btc"] = panel["ret42"] - panel["t"].map(btc_ret42)
    panel["mkt_share_rib_up"] = panel.groupby("t")["rib"].transform(lambda s: (s == 1).mean())
    panel["mkt_mean_snr42"] = panel.groupby("t")["snr42"].transform(lambda s: s.mean(skipna=True))
    # (ii) f7 z vs trailing 180d (1080 bars) min 30d (180 bars), ddof=1
    panel["f7_z180"] = np.nan
    for s, g in panel.groupby("sym"):
        g = g.sort_values("t")
        mu = g["f7"].rolling(1080, min_periods=180).mean()
        sd = g["f7"].rolling(1080, min_periods=180).std(ddof=1)
        z = (g["f7"] - mu) / sd.replace(0, np.nan)
        panel.loc[g.index, "f7_z180"] = z.to_numpy()
    return panel


def build_ctx_frame():
    from agentic_alpha_lab.patterns import common as cm
    from agentic_alpha_lab.patterns import breadth, positioning, macro, implied_vol
    bars = cm.load_bars("4h", include_opened_year=True)
    mods = {"breadth": breadth, "positioning": positioning, "macro": macro, "implied_vol": implied_vol}
    frames = []
    for name, mod in mods.items():
        df = mod.compute(bars)
        df = df.add_prefix("ctx_")
        frames.append(df)
    ctx = pd.concat(frames, axis=1)
    ctx.index = bars.index
    keep = [c for c in ctx.columns if float(ctx[c].notna().mean()) > 0.20]
    dropped = [c for c in ctx.columns if c not in keep]
    out = ctx[keep].copy()
    out["open_time"] = bars["open_time"].to_numpy()
    return out, bars, keep, dropped


def run_a2(panel_base, ctx_frame):
    panel = add_xs_features(panel_base)
    ctx = ctx_frame.copy()
    # merge on open_time
    panel = panel.merge(ctx, left_on="t", right_on="open_time", how="left")
    panel = panel.drop(columns=["open_time"])
    base_feats = [c for c in panel_base.columns if c not in ("y", "t", "open", "sym", "bar")]
    extra = [c for c in panel.columns if c.startswith("xs_") or c.startswith("mkt_") or c == "f7_z180" or c.startswith("ctx_")]
    feats = base_feats + extra
    return panel, feats


def main():
    # ---- A1 ----
    a1 = run_a1()
    print("A1 yearly:", json.dumps(a1["yearly"], indent=2), flush=True)
    # ---- A2 ctx ----
    ctx_frame, btc4h, kept, dropped = build_ctx_frame()
    print(f"ctx kept {len(kept)} dropped {len(dropped)}", flush=True)
    # causality check on 3000-bar slice
    from agentic_alpha_lab.patterns import common as cm
    from agentic_alpha_lab.patterns import breadth, positioning, macro, implied_vol
    def ctx_fn(bars):
        parts = []
        for mod in (breadth, positioning, macro, implied_vol):
            parts.append(mod.compute(bars).add_prefix("ctx_"))
        full = pd.concat(parts, axis=1)
        # keep only columns selected on full history that exist here
        cols = [c for c in kept if c in full.columns]
        return full[cols]
    sl = btc4h.iloc[:3000].copy()
    try:
        cm.assert_causal(ctx_fn, sl)
        causal_pass = True
        causal_msg = "assert_causal passed on 3000-bar slice"
    except Exception as e:
        causal_pass = False
        causal_msg = f"assert_causal FAILED: {type(e).__name__}: {e}"
    print(causal_msg, flush=True)
    # ---- A2 panel + train ----
    panel_base = build_base_panel()
    panel, feats = run_a2(panel_base, ctx_frame)
    anchors_rec = []
    oos_parts = []
    for anchor in ANCHORS:
        a = pd.Timestamp(anchor, tz="UTC")
        end = a + pd.Timedelta(days=365)
        cutoff = a - pd.Timedelta(hours=4 * EMBARGO_BARS)
        tr = panel[(panel.t < cutoff) & panel.y.notna()]
        tr = tr[tr.t + pd.Timedelta(hours=4 * (H + 1)) < cutoff]
        te = panel[(panel.t >= a) & (panel.t < end)].copy()
        m = HistGradientBoostingRegressor(**HGB_PARAMS)
        m.fit(tr[feats], tr["y"])
        te["pred"] = m.predict(te[feats])
        ev = te.dropna(subset=["y"])
        rho = float(spearmanr(ev["pred"], ev["y"]).statistic) if len(ev) > 2 else float("nan")
        anchors_rec.append(dict(anchor=anchor, train_rows=int(len(tr)),
                                n_pred_rows=int(len(te)),
                                n_pred_rows_with_y=int(len(ev)),
                                ic=round(rho, 4)))
        oos_parts.append(te)
        print(anchor, "train", len(tr), "pred", len(te), "with_y", len(ev), "IC", round(rho, 4), flush=True)
    oos = pd.concat(oos_parts, ignore_index=True).sort_values(["t", "sym"]).reset_index(drop=True)
    W = compute_weights_longonly(oos)
    scale, book, vol, o = vol_scale_for_book(W, oos, vol_target=0.20)
    r_fwd = (o.shift(-2) / o.shift(-1) - 1).fillna(0.0)
    Wk = W.mul(scale, axis=0)
    turn = Wk.diff().abs().sum(axis=1).fillna(Wk.abs().sum(axis=1))
    funding = Wk.clip(lower=0).sum(axis=1) * 0.00005
    net = (Wk * r_fwd).sum(axis=1) - turn * 0.0002 - funding
    yearly = yearly_slices(net, turn)
    print("A2 yearly:", json.dumps(yearly, indent=2), flush=True)
    result = {
        "anchors_v95": anchors_rec,
        "yearly_v95_normal": yearly,
        "hidden_v95_2025_2026_normal": next(y for y in yearly if y["anchor"] == "2025-09-24"),
        "yearly_v96_normal": a1["yearly"],
        "hidden_v96_2025_2026_normal": next(y for y in a1["yearly"] if y["anchor"] == "2025-09-24"),
        "model": HGB_PARAMS,
        "features_v95": feats,
        "features_v95_count": len(feats),
        "ctx_kept": kept,
        "ctx_dropped": dropped,
        "ctx_causality": {"passed": bool(causal_pass), "detail": causal_msg, "slice": "btc4h.iloc[:3000]"},
        "assets": list(SYMS),
        "cutoffs": {a: str(pd.Timestamp(a, tz="UTC") - pd.Timedelta(hours=4 * EMBARGO_BARS)) for a in ANCHORS},
        "data": {
            "usdm_btc": "data/raw/ma_ribbon_20260924",
            "usdm_others": "data/raw/xs_universe_20260924",
            "spot_prefix": "data/raw/spot_majors_20260925/{SYM}_spot_{4h,1d}_2017.parquet open_time < first USD-M bar (SOL none)",
            "v92_weights_source": "research/parallel/rounds/parallel-20260906-r2/v92_audit/predictions_5asset.csv recomputed long-only",
            "v94_weights_source": "research/parallel/rounds/parallel-20260906-r2/v93_v94_audit/predictions_v94.csv recomputed long-short",
            "ctx": "agentic_alpha_lab.patterns.{breadth,positioning,macro,implied_vol}.compute(load_bars(4h, include_opened_year=True)) prefixed ctx_, kept >20% non-NaN, merged on open_time",
        },
        "execution_v96_blind_assumption": {
            "W92": "s=min(max(pred,0)/0.5,1) zeroed if rib==-1; raw=s/(vol42*sqrt(2190)); /sum|raw| then *min(1,count_pos/5); every 6th bar ffill",
            "W94": "long=min(max(p,0)/0.5,1) zeroed if rib==-1; short=min(max(-p,0)/0.5,1) zeroed if rib==+1; raw=(long-short)/(vol42*sqrt(2190)); /sum|raw| then *min(1,count_nz/5); every 6th bar ffill",
            "scales": "each book own causal 20% vol target: book=sum W_{t-2}*(open_t/open_{t-1}-1); vol=rolling360(min120)std*sqrt(2190); scale=min(0.20/vol,2) NaN->1",
            "combined": "Wc=0.5*W92*s92 + 0.5*W94*s94; net=sum Wc*r_fwd - turn*0.0002 - long_gross*0.00005; r_fwd=open[t+2]/open[t+1]-1; turn=|diff(Wc)| summed, first bar |Wc|",
        },
        "execution_v95_blind_assumption": {
            "xs_pct": "(rank_average-1)/(count-1) per t across 5 majors for ret42/ret180/snr42; NaN ranks stay NaN",
            "xs_excess": "ret42 - BTC ret42 at same t",
            "mkt_share": "mean(rib==+1) over 5 at t",
            "mkt_mean": "nanmean(snr42) over 5 at t",
            "f7_z180": "(f7 - rolling1080(min180).mean())/rolling1080(min180).std(ddof=1) per asset, window incl current, std==0->NaN",
            "train_filter": "t<cutoff and t+172h<cutoff and y not NaN; cutoff=anchor-408h; HGB NaN-native",
            "book": "v92 long-only weights + v92 vol-target/execution (20%, cap2, fee 0.0002, funding 0.00005 long gross)",
        },
        "assumptions": [
            "A1 reuses audited OOS preds (no retrain); scales recomputed causally per book; combined simulated forward as v92.",
            "A2 HGB trained on v92 26 feats + xs(3 pct + excess + share + mean=6) + f7_z180(1) + ctx kept; NaN-native.",
            "ctx column filter >20% non-NaN computed on full BTC4h history (column selection only, not row leakage); causality tested on values via assert_causal.",
            "yearly slices [A,A+365d); 2190 bars per year; 10950 total.",
        ],
    }
    with open(OUT_DIR / "replication.json", "w") as f:
        json.dump(result, f, indent=2)
    pd.DataFrame({"t": a1["net"].index, "net": a1["net"].values, "turnover": a1["turn"].values}).to_csv(
        OUT_DIR / "equity_v96.csv", index=False)
    pd.DataFrame({"t": net.index, "net": net.values, "turnover": turn.values, "scale": scale.values}).to_csv(
        OUT_DIR / "equity_v95.csv", index=False)
    oos[["t", "sym", "open", "pred", "y", "vol42", "rib"] + [c for c in ["xs_pct_ret42", "xs_pct_ret180", "xs_pct_snr42", "xs_excess_ret42_vs_btc", "mkt_share_rib_up", "mkt_mean_snr42", "f7_z180"] if c in oos.columns]].to_csv(
        OUT_DIR / "predictions_v95.csv", index=False)
    print("saved replication.json", flush=True)


if __name__ == "__main__":
    main()
