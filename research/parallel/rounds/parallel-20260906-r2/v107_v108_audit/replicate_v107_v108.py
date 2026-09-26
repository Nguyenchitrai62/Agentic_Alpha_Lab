"""Blind v107+v108 audit reproduction from OPENCODE_V107_V108_AUDIT.md spec.

Reads only raw data under data/raw/*, audited replications
v92_audit/predictions_5asset.csv + v93_v94_audit/predictions_v94.csv.
Does NOT read research/.../v107/* or v108/* (blind until replication.json saved).

Base = audited v103_v105 replication (v103 panel, flow features, y6/y18 targets,
HGB, v94 weights_ls, vol target).
A1 (v107): 1h series per major = spot 1h prefix + USD-M 1h, dedup/sorted;
  r1/sd168/tbr + six ih_* feats; 4h bar at T takes 1h bar at T+3h (left join);
  features = v103 (36) + six; everything else as v103. Report per-anchor IC
  (y6,y18), LS yearly normal/fee/execution net/DD + 0.5*v96 + 0.5*(v107 LS scaled) blend (scale 1).
A2 (v108): v103 predictions unchanged; LS book = v94 weights_ls rule keeping
  every k-th row (k=1 primary, 3 secondary; v103 is k=6), ffill; own 20% vol
  target; v92 costs. Report yearly net/DD for k=1,3,6 in three scenarios.
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
EMBARGO_V103 = 78
HS_V103 = (6, 18)
BTC_DIR = ROOT / "data/raw/ma_ribbon_20260924"
XS_DIR = ROOT / "data/raw/xs_universe_20260924"
SPOT_DIR = ROOT / "data/raw/spot_majors_20260925"
MAJORS_1H_DIR = ROOT / "data/raw/majors_intraday_20260924"
HGB_PARAMS = dict(max_depth=4, learning_rate=0.03, max_iter=400,
                  min_samples_leaf=300, l2_regularization=1.0, random_state=0)
FLOW_FEATS = ["tbr_1", "tbr_6", "tbr_42", "flow_6", "flow_42", "tbr_z",
              "tsize_z", "ntr_z", "rng6", "clv6"]
IH_FEATS = ["ih_last", "ih_jump", "ih_rv", "ih_ac", "ih_tbr", "ih_up"]
SCEN = {"normal": (0.0002, 0.0), "fee_stress": (0.0006, 0.0), "execution_stress": (0.0006, 0.0005)}


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


def features_flow(b, d, f):
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
    qv = b["quote_volume"].astype(float).clip(lower=1)
    tbqv = b["taker_buy_quote_volume"].astype(float)
    tbr1 = (tbqv / qv).clip(lower=0, upper=1)
    x["tbr_1"] = tbr1.rolling(1).mean() - 0.5
    x["tbr_6"] = tbr1.rolling(6).mean() - 0.5
    x["tbr_42"] = tbr1.rolling(42).mean() - 0.5
    signed = (2 * tbr1 - 1) * qv
    x["flow_6"] = signed.rolling(6).sum() / qv.rolling(6).sum()
    x["flow_42"] = signed.rolling(42).sum() / qv.rolling(42).sum()
    x["tbr_z"] = (tbr1.rolling(6).mean() - tbr1.rolling(180).mean()) / tbr1.rolling(180).std()
    ntr_raw = b["num_trades"].astype(float).clip(lower=1)
    tsize_raw = np.log(qv / ntr_raw)
    ntr_log = np.log(ntr_raw)
    x["tsize_z"] = (tsize_raw - tsize_raw.rolling(180).mean()) / tsize_raw.rolling(180).std()
    x["ntr_z"] = (ntr_log - ntr_log.rolling(180).mean()) / ntr_log.rolling(180).std()
    hl = np.log(b["high"].astype(float) / b["low"].astype(float))
    x["rng6"] = hl.rolling(6).mean() / vol42
    rng = (b["high"].astype(float) - b["low"].astype(float))
    clv = (b["close"].astype(float) - b["low"].astype(float)) / rng
    clv = clv.where(rng != 0, np.nan)
    x["clv6"] = clv.rolling(6).mean() - 0.5
    o = b["open"].astype(float).to_numpy()
    n = len(b)
    v42 = vol42.to_numpy()
    for h in (6, 18, 42):
        fwd = np.full(n, np.nan)
        if n > 1 + h:
            fwd[: n - 1 - h] = np.log(o[1 + h:] / o[1: n - h])
        x[f"y{h}"] = np.clip(fwd / (v42 * np.sqrt(h)), -4, 4)
    return x


def build_panel():
    rows = []
    for i, s in enumerate(SYMS):
        b, d, f = load_asset(s)
        x = features_flow(b, d, f)
        x["asset"] = i
        x["t"] = b["open_time"]
        x["open"] = b["open"].astype(float).to_numpy()
        x["sym"] = s
        x["bar"] = np.arange(len(b))
        rows.append(x)
    panel = pd.concat(rows, ignore_index=True)
    btc = panel[panel.sym == "BTCUSDT"].set_index("t")[["ret42", "ret180", "rib", "snr42"]].add_prefix("btc_")
    panel = panel.join(btc, on="t")
    return panel


def load_1h_series(sym):
    """Spot 1h prefix (open_time < first USD-M 1h) + USD-M 1h, deduped, sorted."""
    if sym == "BTCUSDT":
        usdm = pd.read_parquet(BTC_DIR / "klines_1h.parquet")
    else:
        usdm = pd.read_parquet(MAJORS_1H_DIR / f"{sym}_1h.parquet")
    usdm["open_time"] = pd.to_datetime(usdm["open_time"], utc=True)
    usdm["close_time"] = pd.to_datetime(usdm["close_time"], utc=True)
    usdm = usdm.sort_values("open_time").reset_index(drop=True)
    first = usdm["open_time"].min()
    spot = pd.read_parquet(SPOT_DIR / f"{sym}_spot_1h_2017.parquet")
    spot["open_time"] = pd.to_datetime(spot["open_time"], utc=True)
    spot["close_time"] = pd.to_datetime(spot["close_time"], utc=True)
    pre = spot[spot["open_time"] < first].copy()
    full = pd.concat([pre[usdm.columns.intersection(pre.columns)], usdm], ignore_index=True)
    full = full.drop_duplicates(subset="open_time", keep="last").sort_values("open_time").reset_index(drop=True)
    return full


def ih_features(h1):
    """Six causal 1h features indexed like h1 (same row order)."""
    c = h1["close"].astype(float)
    lc = np.log(c)
    r1 = lc.diff()
    sd168 = r1.rolling(168, min_periods=84).std()
    qv = h1["quote_volume"].astype(float).clip(lower=1)
    tbqv = h1["taker_buy_quote_volume"].astype(float)
    tbr = (tbqv / qv).clip(lower=0, upper=1)
    out = pd.DataFrame(index=h1.index)
    out["ih_last"] = r1 / sd168
    out["ih_jump"] = r1.abs().rolling(4).max() / sd168
    out["ih_rv"] = r1.rolling(24).std() / sd168
    out["ih_ac"] = r1.rolling(72).corr(r1.shift(1))
    out["ih_tbr"] = tbr - tbr.rolling(24).mean()
    up = pd.Series(np.where(r1.isna(), np.nan, (r1 > 0).astype(float)), index=h1.index)
    out["ih_up"] = up.rolling(24).mean() - 0.5
    out = out.replace([np.inf, -np.inf], np.nan)
    return out


def attach_ih(panel):
    """Left-join 1h features at T+3h onto 4h bars opening at T, per sym."""
    parts = []
    for sym in SYMS:
        h1 = load_1h_series(sym)
        feats = ih_features(h1)
        lut = pd.DataFrame({"t1": h1["open_time"]})
        for col in IH_FEATS:
            lut[col] = feats[col].to_numpy()
        sub = panel[panel.sym == sym].copy()
        sub["t1"] = sub["t"] + pd.Timedelta(hours=3)
        m = pd.merge(sub[["t1"]], lut.sort_values("t1"), on="t1", how="left")
        for col in IH_FEATS:
            sub[col] = m[col].to_numpy()
        parts.append(sub)
    out = pd.concat(parts, ignore_index=True)
    # restore original row order (panel order is asset blocks; keep that)
    return out


def train_predict(panel, anchor, feats):
    a = pd.Timestamp(anchor, tz="UTC")
    end = a + pd.Timedelta(days=365)
    cutoff = a - pd.Timedelta(hours=4 * EMBARGO_V103)
    te = panel[(panel.t >= a) & (panel.t < end)].copy()
    preds = np.zeros((len(te), len(HS_V103)))
    ntrs = []
    for j, h in enumerate(HS_V103):
        yh = f"y{h}"
        tr = panel[(panel.t < cutoff) & panel[yh].notna()]
        tr = tr[tr.t + pd.Timedelta(hours=4 * (h + 1)) < cutoff]
        ntrs.append(int(len(tr)))
        m = HistGradientBoostingRegressor(**HGB_PARAMS)
        m.fit(tr[feats], tr[yh])
        preds[:, j] = m.predict(te[feats])
    te["pred"] = preds.mean(axis=1)
    for j, h in enumerate(HS_V103):
        te[f"pred_h{h}"] = preds[:, j]
    return te, ntrs


def weights_ls(oos, shorts, k=6):
    Wdict = {}
    for s, g in oos.groupby("sym"):
        g = g.set_index("t").sort_index()
        p = g["pred"].astype(float)
        rib = g["rib"].astype(float)
        long_ = (p.clip(lower=0) / 0.5).clip(upper=1.0).where(rib != -1, 0.0)
        short = (((-p).clip(lower=0) / 0.5).clip(upper=1.0).where(rib != 1, 0.0)) if shorts else 0.0 * long_
        raw = (long_ - short) / (g["vol42"].astype(float) * np.sqrt(PD * 365))
        raw = raw.replace([np.inf, -np.inf], np.nan).fillna(0.0)
        Wdict[s] = raw
    rawW = pd.DataFrame(Wdict).sort_index()
    row_sum = rawW.abs().sum(axis=1)
    n_nz = (rawW != 0).sum(axis=1).clip(lower=1)
    W = rawW.div(row_sum.clip(lower=1e-9), axis=0).mul(row_sum.gt(0), axis=0)
    W = W.mul((n_nz / 5).clip(upper=1.0), axis=0).fillna(0.0)
    keep = pd.Series(np.arange(len(W)) % k == 0, index=W.index)
    W = W.where(keep, np.nan).ffill().fillna(0.0)
    return W


def vol_target_scale(o, W, target=0.20, cap=2.0):
    ret1 = o / o.shift(1) - 1
    realized = (W.shift(2) * ret1).sum(axis=1)
    vol = realized.rolling(60 * PD, min_periods=20 * PD).std(ddof=1) * np.sqrt(PD * 365)
    sc = (target / vol).clip(upper=cap).fillna(1.0)
    sc = sc.replace([np.inf, -np.inf], 2.0).fillna(1.0)
    return sc


def simulate(o, W, scale, fee, slip=0.0):
    r = (o.shift(-2) / o.shift(-1) - 1).fillna(0.0)
    Wk = W.mul(scale, axis=0) if isinstance(scale, pd.Series) else W * scale
    turn = Wk.diff().abs().sum(axis=1).fillna(Wk.abs().sum(axis=1))
    funding = Wk.clip(lower=0).sum(axis=1) * 0.00005
    net = (Wk * r).sum(axis=1) - turn * (fee + slip) - funding
    return net, turn


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


def spearman(a, b):
    m = pd.DataFrame({"a": a, "b": b}).dropna()
    if len(m) < 3:
        return float("nan")
    return float(spearmanr(m["a"], m["b"]).statistic)


def build_v96_books():
    pred92 = pd.read_csv(V92_DIR / "predictions_5asset.csv", parse_dates=["t"])
    pred92["t"] = pd.to_datetime(pred92["t"], utc=True)
    oos92 = pred92.sort_values(["t", "sym"]).reset_index(drop=True)
    pred94 = pd.read_csv(V9394_DIR / "predictions_v94.csv", parse_dates=["t"])
    pred94["t"] = pd.to_datetime(pred94["t"], utc=True)
    oos94 = pred94.sort_values(["t", "sym"]).reset_index(drop=True)
    W92 = weights_ls(oos92.assign(pred=oos92["pred"]), False)
    W94 = weights_ls(oos94, True)
    o = oos92.pivot_table(index="t", columns="sym", values="open").reindex(W92.index).sort_index()
    o = o[list(SYMS)]
    s92 = vol_target_scale(o, W92.reindex(o.index).fillna(0.0), 0.20, 2.0)
    s94 = vol_target_scale(o, W94.reindex(o.index).fillna(0.0), 0.20, 2.0)
    idx = W92.index.union(W94.index).union(o.index)
    W92a = W92.reindex(idx).fillna(0.0)
    W94a = W94.reindex(idx).fillna(0.0)
    s92a = s92.reindex(idx).fillna(1.0)
    s94a = s94.reindex(idx).fillna(1.0)
    books = 0.5 * W92a.mul(s92a, axis=0) + 0.5 * W94a.mul(s94a, axis=0)
    o = o.reindex(idx).sort_index()
    return dict(books=books, o=o)


def main():
    panel = build_panel()
    feats_v92 = [c for c in panel.columns if c not in ("t", "open", "sym", "bar", "y6", "y18", "y42",
                                                       "pred", "pred_h6", "pred_h18")]
    # feats_v92 should be 26 (v92) since panel currently has v92+flow (36)
    feats_flow_only = [c for c in FLOW_FEATS if c in panel.columns]
    feats_v103 = [c for c in panel.columns if c not in ("t", "open", "sym", "bar", "y6", "y18", "y42",
                                                        "pred", "pred_h6", "pred_h18")]
    assert len(feats_v103) == 36, len(feats_v103)
    # --- base v103 (k=6) replication ---
    v103_anchors, oos103_parts = [], []
    for anchor in ANCHORS:
        te, ntrs = train_predict(panel, anchor, feats_v103)
        ic6 = spearman(te["pred"], te["y6"])
        ic18 = spearman(te["pred"], te["y18"])
        oos103_parts.append(te)
        v103_anchors.append(dict(anchor=anchor, train_rows_h6=ntrs[0], train_rows_h18=ntrs[1],
                                 n_pred_rows=int(len(te)),
                                 ic_vs_y6=round(ic6, 4), ic_vs_y18=round(ic18, 4)))
        print("v103", anchor, ntrs, round(ic6, 4), round(ic18, 4), flush=True)
    oos103 = pd.concat(oos103_parts, ignore_index=True).sort_values(["t", "sym"]).reset_index(drop=True)
    o103 = oos103.pivot_table(index="t", columns="sym", values="open")[list(SYMS)]
    # --- A1 v107: attach 1h features, retrain ---
    panel107 = attach_ih(panel)
    feats_v107 = feats_v103 + IH_FEATS
    assert all(c in panel107.columns for c in IH_FEATS)
    v107_anchors, oos107_parts = [], []
    for anchor in ANCHORS:
        te, ntrs = train_predict(panel107, anchor, feats_v107)
        ic6 = spearman(te["pred"], te["y6"])
        ic18 = spearman(te["pred"], te["y18"])
        oos107_parts.append(te)
        v107_anchors.append(dict(anchor=anchor, train_rows_h6=ntrs[0], train_rows_h18=ntrs[1],
                                 n_pred_rows=int(len(te)),
                                 ic_vs_y6=round(ic6, 4), ic_vs_y18=round(ic18, 4)))
        print("v107", anchor, ntrs, round(ic6, 4), round(ic18, 4), flush=True)
    oos107 = pd.concat(oos107_parts, ignore_index=True).sort_values(["t", "sym"]).reset_index(drop=True)
    o107 = oos107.pivot_table(index="t", columns="sym", values="open")[list(SYMS)]
    W107 = weights_ls(oos107, True, k=6)
    s107 = vol_target_scale(o107, W107, 0.20, 2.0)
    scen107 = {}
    for sc, (fee, slip) in SCEN.items():
        net, turn = simulate(o107, W107, s107, fee, slip)
        scen107[sc] = yearly_slices(net, turn)
    # keep normal net/turn for blend + files
    net107_n, turn107_n = simulate(o107, W107, s107, *SCEN["normal"])
    net107_f, turn107_f = simulate(o107, W107, s107, *SCEN["fee_stress"])
    net107_e, turn107_e = simulate(o107, W107, s107, *SCEN["execution_stress"])
    # blend 0.5*v96 + 0.5*(v107 scaled), scale 1.0
    v96 = build_v96_books()
    idx = v96["books"].index.union(W107.index).union(o107.index)
    books96 = v96["books"].reindex(idx).fillna(0.0)
    o_all = v96["o"].reindex(idx).ffill()
    o107a = o107.reindex(idx)
    o_blend = o_all.combine_first(o107a).sort_index()
    W107a = W107.reindex(idx).fillna(0.0)
    s107a = s107.reindex(idx).fillna(1.0)
    v107_scaled = W107a.mul(s107a, axis=0)
    blend_books = 0.5 * books96 + 0.5 * v107_scaled
    blend_scen = {}
    blend_nets = {}
    for sc, (fee, slip) in SCEN.items():
        net, turn = simulate(o_blend, blend_books, 1.0, fee, slip)
        blend_scen[sc] = yearly_slices(net, turn)
        blend_nets[sc] = (net, turn)
    # --- A2 v108: same v103 preds, k variants ---
    v108 = {}
    v108_nets = {}
    for k in (1, 3, 6):
        Wk = weights_ls(oos103, True, k=k)
        sk = vol_target_scale(o103, Wk, 0.20, 2.0)
        v108[str(k)] = {}
        v108_nets[str(k)] = {}
        for sc, (fee, slip) in SCEN.items():
            net, turn = simulate(o103, Wk, sk, fee, slip)
            v108[str(k)][sc] = yearly_slices(net, turn)
            v108_nets[str(k)][sc] = (net, turn)
        print(f"v108 k={k}", [(y["anchor"], y["net_pct"], y["max_drawdown_percent"]) for y in v108[str(k)]["normal"]], flush=True)
    result = {
        "anchors": list(ANCHORS),
        "cutoff_rule": "cutoff = anchor - 78*4h = anchor - 312h; per-horizon train t<cutoff and t+(h+1)*4h<cutoff and y_h not NaN",
        "model": HGB_PARAMS,
        "assets": list(SYMS),
        "features_v103": feats_v103,
        "features_ih": IH_FEATS,
        "features_v107": feats_v107,
        "v103_base": {"anchors": v103_anchors},
        "v107": {"anchors": v107_anchors,
                 "yearly_LS": scen107,
                 "yearly_blend_v96": blend_scen},
        "v108": {f"k={k}": v108[str(k)] for k in (1, 3, 6)},
        "data": {"usdm_btc_4h": "data/raw/ma_ribbon_20260924",
                 "usdm_others_4h": "data/raw/xs_universe_20260924",
                 "spot_prefix_4h": "data/raw/spot_majors_20260925/{SYM}_spot_{4h,1d}_2017.parquet open_time < first USD-M bar",
                 "usdm_btc_1h": "data/raw/ma_ribbon_20260924/klines_1h.parquet",
                 "usdm_others_1h": "data/raw/majors_intraday_20260924/{SYM}_1h.parquet",
                 "spot_prefix_1h": "data/raw/spot_majors_20260925/{SYM}_spot_1h_2017.parquet open_time < first USD-M 1h bar",
                 "v96_books_source": "v92_audit/predictions_5asset.csv + v93_v94_audit/predictions_v94.csv, leader vol_target_scale (no fillna, NaN->1)"},
        "execution": {"fee_per_unit_turnover": 0.0002, "long_funding_per_4h_bar": 5e-05,
                      "weight": "v94.weights_ls; long=min(max(p,0)/0.5,1) rib!=-1; short=min(max(-p,0)/0.5,1) rib!=+1; raw=(l-s)/(vol42*sqrt(2190)); /sum|raw| *min(1,count/5); every k-th bar ffill (v103 k=6; v108 k=1 primary, k=3 secondary)",
                      "vol": "v94.vol_target_scale target 0.20 cap 2 (realized=W.shift(2)*ret1 no fillna, rolling360 min120, NaN->1)",
                      "v107_ih": "per major: r1=diff(log close 1h); sd168=rolling168 std r1 min84; tbr=clip(taker_buy_quote/quote,0,1); ih_last=r1/sd168; ih_jump=roll4 max|r1|/sd168; ih_rv=roll24 std/sd168; ih_ac=roll72 corr(r1,r1.shift1); ih_tbr=tbr-roll24 mean tbr; ih_up=roll24 mean(r1>0, NaN where r1 NaN)-0.5; 4h T takes 1h T+3h left join",
                      "v107_blend": "blend_books=0.5*v96books+0.5*(W107LS*s107); simulate with scale 1.0",
                      "v108_costs": "v92.SCEN normal(0.0002,0.0) fee_stress(0.0006,0.0) execution_stress(0.0006,0.0005)"},
        "assumptions": ["flow+ih features causal rolling on prefixed bars; HGB NaN-native; inf->NaN in ih only",
                        "v103/v107 ICs spearman(mean pred, y_h) on OOS rows with y_h not NaN",
                        "v96 books recomputed from audited CSVs (no retrain) with leader scales",
                        "fills = turnover-bar count; funding 0.00005/bar on scaled longs"],
    }
    with open(OUT_DIR / "replication.json", "w") as f:
        json.dump(result, f, indent=2)
    oos103[["t", "sym", "open", "pred", "pred_h6", "pred_h18", "y6", "y18", "vol42", "rib"]].to_csv(
        OUT_DIR / "predictions_v103.csv", index=False)
    oos107[["t", "sym", "open", "pred", "pred_h6", "pred_h18", "y6", "y18", "vol42", "rib"] + IH_FEATS].to_csv(
        OUT_DIR / "predictions_v107.csv", index=False)
    pd.DataFrame({"t": net107_n.index, "net": net107_n.values, "turnover": turn107_n.values,
                  "scale": s107.reindex(net107_n.index).fillna(1.0).values}).to_csv(
        OUT_DIR / "equity_v107_LS_normal.csv", index=False)
    pd.DataFrame({"t": net107_f.index, "net": net107_f.values, "turnover": turn107_f.values}).to_csv(
        OUT_DIR / "equity_v107_LS_fee_stress.csv", index=False)
    pd.DataFrame({"t": net107_e.index, "net": net107_e.values, "turnover": turn107_e.values}).to_csv(
        OUT_DIR / "equity_v107_LS_execution_stress.csv", index=False)
    for sc, (net, turn) in blend_nets.items():
        pd.DataFrame({"t": net.index, "net": net.values, "turnover": turn.values}).to_csv(
            OUT_DIR / f"equity_v107_blend_{sc}.csv", index=False)
    for k in ("1", "3", "6"):
        for sc, (net, turn) in v108_nets[k].items():
            suffix = {"normal": "normal", "fee_stress": "fee_stress", "execution_stress": "execution_stress"}[sc]
            pd.DataFrame({"t": net.index, "net": net.values, "turnover": turn.values}).to_csv(
                OUT_DIR / f"equity_v108_k{k}_{suffix}.csv", index=False)
    print(json.dumps({"v107": scen107["normal"], "v108_k1_normal": v108["1"]["normal"]}, indent=2))


if __name__ == "__main__":
    main()
