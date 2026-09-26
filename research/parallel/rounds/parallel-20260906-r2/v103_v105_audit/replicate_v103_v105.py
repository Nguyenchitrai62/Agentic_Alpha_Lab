"""Blind v103+v104+v105 audit reproduction from OPENCODE_V103_V105_AUDIT.md spec.

Reads only raw data under data/raw/*, artifacts/research/carry/*, audited
replications v92_audit/predictions_5asset.csv + v93_v94_audit/predictions_v94.csv,
and 1m intraday for hidden execution. Does NOT read research/.../v103/*,
v104/* or v105/* (blind until replication.json is saved).

A1 (v103): v92 panel (5 majors, spot prefix, v92 features, BTC context) plus
  10 flow features per asset from same 4h klines. Targets y6,y18.
  Embargo 78 bars: cutoff=anchor-78*4h, rows need t+(h+1)*4h<cutoff per horizon.
  One HGB per horizon (v92 hyperparams), pred=mean. Book=v94 weights_ls
  (shorts=True), v94 vol_target_scale (20%, cap2), v92.simulate. Report IC vs
  y6/y18/y42 + yearly normal for LS, long-only, 0.5*v96+0.5*v103scaled (scale 1).
A2 (v104): v99 wrapper (leader carry convention carry_exp[t]*carry[t]) with
  books=0.5*v96+0.5*(v103 LS weights*v103 vol scale). Yearly normal/fee/exec.
  Hidden 1m execution per spec window [T+2m,T+14m], fallback T+15m.
A3 (v105): (i) A1 without 10 flow feats (LS); (ii) v92 7-day model + long-only
  with v92+flow feats on v103 panel, v92 embargo/vol target.
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
H_V92 = 42
EMBARGO_V103 = 78
EMBARGO_V92 = 102
HS_V103 = (6, 18)
BTC_DIR = ROOT / "data/raw/ma_ribbon_20260924"
XS_DIR = ROOT / "data/raw/xs_universe_20260924"
SPOT_DIR = ROOT / "data/raw/spot_majors_20260925"
CARRY_FILE = ROOT / "artifacts/research/carry/carry_oos_fee0.0004.parquet"
HGB_PARAMS = dict(max_depth=4, learning_rate=0.03, max_iter=400,
                  min_samples_leaf=300, l2_regularization=1.0, random_state=0)
FLOW_FEATS = ["tbr_1", "tbr_6", "tbr_42", "flow_6", "flow_42", "tbr_z",
              "tsize_z", "ntr_z", "rng6", "clv6"]
SCEN = {"normal": (0.0002, 0.0), "fee_stress": (0.0006, 0.0), "execution_stress": (0.0006, 0.0005)}
W_BOOKS, W_CARRY, CARRY_LEV, TARGET, CAP = 0.8, 0.2, 3.0, 0.15, 2.0


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
    # --- flow features from same 4h klines (causal) ---
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
    # --- labels ---
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


FEATS_ALL = None
FEATS_V92 = None


def train_predict_v103(panel, anchor, feats):
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


def train_predict_7d(panel, anchor, feats):
    a = pd.Timestamp(anchor, tz="UTC")
    end = a + pd.Timedelta(days=365)
    cutoff = a - pd.Timedelta(hours=4 * EMBARGO_V92)
    tr = panel[(panel.t < cutoff) & panel["y42"].notna()]
    tr = tr[tr.t + pd.Timedelta(hours=4 * (H_V92 + 1)) < cutoff]
    te = panel[(panel.t >= a) & (panel.t < end)].copy()
    m = HistGradientBoostingRegressor(**HGB_PARAMS)
    m.fit(tr[feats], tr["y42"])
    te["pred"] = m.predict(te[feats])
    return te, int(len(tr))


def weights_ls(oos, shorts):
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
    keep = pd.Series(np.arange(len(W)) % PD == 0, index=W.index)
    W = W.where(keep, np.nan).ffill().fillna(0.0)
    return W


def vol_target_scale(o, W, target=0.20, cap=2.0):
    # leader convention: no fillna in realized, NaN->1 default scale
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
    W92 = weights_ls(oos92.assign(pred=oos92["pred"]), False)  # long-only via same formula
    # recompute W92 with long-only rib logic (weights_ls shorts=False == v92 long-only)
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
    return dict(books=books, o=o, W92=W92a, s92=s92a, W94=W94a, s94=s94a)


def run_v99_wrapper(books104, o):
    carry = pd.read_parquet(CARRY_FILE)
    carry.index = pd.to_datetime(carry.index, utc=True)
    c = carry.reindex(o.index)["carry"].astype(float).fillna(0.0)
    ret1 = o / o.shift(1) - 1
    realized = W_BOOKS * (books104.shift(2) * ret1).sum(axis=1) + W_CARRY * CARRY_LEV * c.shift(1)
    vol = realized.rolling(60 * PD, min_periods=20 * PD).std(ddof=1) * np.sqrt(PD * 365)
    s = (TARGET / vol).clip(upper=CAP).fillna(1.0)
    s = s.replace([np.inf, -np.inf], 2.0).fillna(1.0)
    Wt = books104.mul(W_BOOKS * s, axis=0)
    r_fwd = (o.shift(-2) / o.shift(-1) - 1).fillna(0.0)
    carry_exp = W_CARRY * CARRY_LEV * s
    out = {}
    for sc, (fee, slip) in SCEN.items():
        turn = Wt.diff().abs().sum(axis=1).fillna(Wt.abs().sum(axis=1))
        cost = turn * (fee + slip)
        model_gross = (Wt * r_fwd).sum(axis=1)
        model_funding = Wt.clip(lower=0).sum(axis=1) * 0.00005
        carry_gross = carry_exp * c  # leader contemporaneous
        carry_turn = carry_exp.diff().abs().fillna(0.0)
        carry_cost = carry_turn * 2 * 0.0004 / 1.2
        net = model_gross - cost - model_funding + carry_gross - carry_cost
        out[sc] = dict(net=net, turn=turn, scale=s, Wt=Wt, carry=c)
    return out


def load_1m(sym, start, end):
    if sym == "BTCUSDT":
        files = [ROOT / f"data/raw/btc_intraday_20260924/klines_1m_{y}.parquet" for y in (2025, 2026)]
    else:
        files = [ROOT / f"data/raw/majors_intraday_20260924/{sym}_1m_{y}.parquet" for y in (2025, 2026)]
    parts = [pd.read_parquet(f) for f in files if f.exists()]
    df = pd.concat(parts, ignore_index=True)
    df["open_time"] = pd.to_datetime(df["open_time"], utc=True)
    df = df[(df["open_time"] >= start - pd.Timedelta(days=2)) & (df["open_time"] < end + pd.Timedelta(days=2))]
    return df.sort_values("open_time").reset_index(drop=True)


def run_hidden_execution_v104(Wt, o):
    HIDDEN = pd.Timestamp("2025-09-24", tz="UTC")
    HEND = HIDDEN + pd.Timedelta(days=365)
    mask = (Wt.index >= HIDDEN) & (Wt.index < HEND)
    idx = Wt.index
    pos = {t: i for i, t in enumerate(idx)}
    m1 = {s: load_1m(s, HIDDEN, HEND) for s in SYMS}
    look = {}
    for s in SYMS:
        df = m1[s]
        ot = df["open_time"].to_numpy().astype("datetime64[ns]")
        look[s] = (ot, df["open"].to_numpy(float), df["high"].to_numpy(float),
                   df["low"].to_numpy(float), df["open_time"])
    diff = Wt.diff().fillna(Wt)
    total = 0
    maker = 0
    missing_1m = 0
    extra = pd.Series(0.0, index=Wt.index)
    for t in Wt.index[mask]:
        i = pos[t]
        if i + 1 >= len(idx):
            continue
        t_exec = idx[i + 1]
        if t_exec not in o.index:
            continue
        limit_row = o.loc[t_exec]
        for s in SYMS:
            dd = float(diff.loc[t, s])
            if abs(dd) <= 1e-9:
                continue
            side = 1 if dd > 0 else -1
            limit_px = float(limit_row[s])
            if not np.isfinite(limit_px):
                continue
            total += 1
            ot, oo, oh, ol, ott = look[s]
            j0 = int(np.searchsorted(ot, np.datetime64(t_exec)))
            exact = j0 < len(ot) and pd.Timestamp(ot[j0]).tz_localize("UTC") == t_exec
            if not exact:
                missing_1m += 1
                fill_px = limit_px * (1 + 0.0002 * side)
                drag = abs(fill_px / limit_px - 1) * abs(dd) if limit_px != 0 else 0.0
                extra.loc[t] += abs(dd) * (0.0005 - 0.0002) + drag
                continue
            p0 = float(oo[j0])
            # window [T+2m, T+14m] inclusive
            t_lo = t_exec + pd.Timedelta(minutes=2)
            t_hi = t_exec + pd.Timedelta(minutes=14)
            sel = (ott >= t_lo) & (ott <= t_hi)
            wh = np.asarray(m1[s].loc[sel, "high"], dtype=float)
            wl = np.asarray(m1[s].loc[sel, "low"], dtype=float)
            through = False
            if wh.size and wl.size:
                through = bool(np.any(wl < p0)) if side > 0 else bool(np.any(wh > p0))
            if through:
                maker += 1
            else:
                t15 = t_exec + pd.Timedelta(minutes=15)
                m15 = m1[s][m1[s]["open_time"] == t15]
                px15 = float(m15["open"].iloc[0]) if len(m15) else p0
                fill_px = px15 * (1 + 0.0002 * side)
                drag = abs(fill_px / limit_px - 1) * abs(dd) if limit_px != 0 else 0.0
                extra.loc[t] += abs(dd) * (0.0005 - 0.0002) + drag
    maker_rate = (maker / total) if total else float("nan")
    return dict(maker_fills=int(maker), total_orders=int(total),
                maker_rate=round(float(maker_rate), 4) if total else float("nan"),
                missing_1m=int(missing_1m), extra=extra)


def main():
    global FEATS_ALL, FEATS_V92
    panel = build_panel()
    FEATS_ALL = [c for c in panel.columns if c not in ("t", "open", "sym", "bar", "y6", "y18", "y42",
                                                       "pred", "pred_h6", "pred_h18")]
    FEATS_V92 = [c for c in FEATS_ALL if c not in FLOW_FEATS]
    assert len(FEATS_V92) == 26, len(FEATS_V92)
    assert len(FEATS_ALL) == 36, len(FEATS_ALL)
    # --- A1 v103 ---
    a1_anchors, oos_parts = [], []
    for anchor in ANCHORS:
        te, ntrs = train_predict_v103(panel, anchor, FEATS_ALL)
        ic6 = spearman(te["pred"], te["y6"])
        ic18 = spearman(te["pred"], te["y18"])
        ic42 = spearman(te["pred"], te["y42"])
        ev6 = int(te["y6"].notna().sum()); ev18 = int(te["y18"].notna().sum()); ev42 = int(te["y42"].notna().sum())
        a1_anchors.append(dict(anchor=anchor, train_rows_h6=ntrs[0], train_rows_h18=ntrs[1],
                               n_pred_rows=int(len(te)), n_pred_rows_with_y6=ev6,
                               n_pred_rows_with_y18=ev18, n_pred_rows_with_y42=ev42,
                               ic_vs_y6=round(ic6, 4), ic_vs_y18=round(ic18, 4), ic_vs_y42=round(ic42, 4)))
        oos_parts.append(te)
        print(anchor, ntrs, round(ic6, 4), round(ic18, 4), round(ic42, 4), flush=True)
    oos103 = pd.concat(oos_parts, ignore_index=True).sort_values(["t", "sym"]).reset_index(drop=True)
    o103 = oos103.pivot_table(index="t", columns="sym", values="open")
    o103 = o103[list(SYMS)]
    Wls = weights_ls(oos103, True)
    Wlo = weights_ls(oos103, False)
    sls = vol_target_scale(o103, Wls, 0.20, 2.0)
    slo = vol_target_scale(o103, Wlo, 0.20, 2.0)
    net_ls, turn_ls = simulate(o103, Wls, sls, 0.0002, 0.0)
    net_lo, turn_lo = simulate(o103, Wlo, slo, 0.0002, 0.0)
    yearly_ls = yearly_slices(net_ls, turn_ls)
    yearly_lo = yearly_slices(net_lo, turn_lo)
    # blend with v96
    v96 = build_v96_books()
    idx = v96["books"].index.union(Wls.index).union(o103.index)
    books96 = v96["books"].reindex(idx).fillna(0.0)
    o_all = v96["o"].reindex(idx).fillna(method="ffill")
    # align o103 to idx
    o103a = o103.reindex(idx)
    # use o_all where available else o103a (they should match on overlap)
    o_blend = o_all.combine_first(o103a).sort_index()
    Wls_a = Wls.reindex(idx).fillna(0.0)
    sls_a = sls.reindex(idx).fillna(1.0)
    v103_scaled = Wls_a.mul(sls_a, axis=0)
    blend_books = 0.5 * books96 + 0.5 * v103_scaled
    net_bl, turn_bl = simulate(o_blend, blend_books, 1.0, 0.0002, 0.0)
    yearly_bl = yearly_slices(net_bl, turn_bl)
    # --- A2 v104 ---
    books104 = blend_books  # same construction per spec
    o104 = o_blend
    v104_paths = run_v99_wrapper(books104.reindex(o104.index).fillna(0.0), o104)
    yearly_v104 = {sc: yearly_slices(v["net"], v["turn"]) for sc, v in v104_paths.items()}
    Wt_hidden = v104_paths["normal"]["Wt"]
    hid = run_hidden_execution_v104(Wt_hidden, o104)
    # execution net = normal net - extra (trend-leg extra only; carry unchanged)
    exec_net_full = v104_paths["normal"]["net"] - hid["extra"].reindex(v104_paths["normal"]["net"].index).fillna(0.0)
    HIDDEN = pd.Timestamp("2025-09-24", tz="UTC")
    HEND = HIDDEN + pd.Timedelta(days=365)
    hm = (exec_net_full.index >= HIDDEN) & (exec_net_full.index < HEND)
    exec_stats = stats(exec_net_full[hm], v104_paths["normal"]["turn"][hm])
    # --- A3(i) no-flow LS ---
    a3a_anchors, a3a_parts = [], []
    for anchor in ANCHORS:
        te, ntrs = train_predict_v103(panel, anchor, FEATS_V92)
        ic6 = spearman(te["pred"], te["y6"])
        ic18 = spearman(te["pred"], te["y18"])
        ic42 = spearman(te["pred"], te["y42"])
        a3a_anchors.append(dict(anchor=anchor, train_rows_h6=ntrs[0], train_rows_h18=ntrs[1],
                                n_pred_rows=int(len(te)), ic_vs_y6=round(ic6, 4),
                                ic_vs_y18=round(ic18, 4), ic_vs_y42=round(ic42, 4)))
        a3a_parts.append(te)
        print("v105a", anchor, ntrs, round(ic6, 4), round(ic18, 4), flush=True)
    oos105a = pd.concat(a3a_parts, ignore_index=True).sort_values(["t", "sym"]).reset_index(drop=True)
    o105a = oos105a.pivot_table(index="t", columns="sym", values="open")[list(SYMS)]
    W105a = weights_ls(oos105a, True)
    s105a = vol_target_scale(o105a, W105a, 0.20, 2.0)
    net105a, turn105a = simulate(o105a, W105a, s105a, 0.0002, 0.0)
    yearly105a = yearly_slices(net105a, turn105a)
    # --- A3(ii) 7-day flow long-only ---
    a3b_anchors, a3b_parts = [], []
    for anchor in ANCHORS:
        te, ntr = train_predict_7d(panel, anchor, FEATS_ALL)
        ic42 = spearman(te["pred"], te["y42"])
        ic6 = spearman(te["pred"], te["y6"])
        ic18 = spearman(te["pred"], te["y18"])
        a3b_anchors.append(dict(anchor=anchor, train_rows=int(ntr), n_pred_rows=int(len(te)),
                                ic_vs_y42=round(ic42, 4), ic_vs_y6=round(ic6, 4), ic_vs_y18=round(ic18, 4)))
        a3b_parts.append(te)
        print("v105b", anchor, ntr, round(ic42, 4), flush=True)
    oos105b = pd.concat(a3b_parts, ignore_index=True).sort_values(["t", "sym"]).reset_index(drop=True)
    o105b = oos105b.pivot_table(index="t", columns="sym", values="open")[list(SYMS)]
    W105b = weights_ls(oos105b, False)
    s105b = vol_target_scale(o105b, W105b, 0.20, 2.0)
    net105b, turn105b = simulate(o105b, W105b, s105b, 0.0002, 0.0)
    yearly105b = yearly_slices(net105b, turn105b)
    result = {
        "anchors": list(ANCHORS),
        "cutoff_rule_v103": "cutoff = anchor - 78*4h = anchor - 312h; per-horizon train t<cutoff and t+(h+1)*4h<cutoff and y_h not NaN",
        "cutoff_rule_v105b": "cutoff = anchor - 102*4h = anchor - 408h; train t<cutoff and t+43*4h<cutoff and y42 not NaN",
        "model": HGB_PARAMS,
        "features_v92": FEATS_V92,
        "features_flow": FLOW_FEATS,
        "features_all": FEATS_ALL,
        "assets": list(SYMS),
        "v103": {"anchors": a1_anchors, "yearly_LS_normal": yearly_ls, "yearly_LO_normal": yearly_lo,
                 "yearly_blend_normal": yearly_bl},
        "v104": {"yearly": yearly_v104,
                 "hidden_1m_execution": {**exec_stats, "maker_fills": hid["maker_fills"],
                                         "total_orders": hid["total_orders"], "maker_rate": hid["maker_rate"],
                                         "missing_1m": hid["missing_1m"],
                                         "rule": "per nonzero diff(Wt) at t, T=t+4h; missing T 1m -> taker 0.0005 at 4h open*(1+/-0.0002); else p0=1m open at T, maker 0.0002 at p0 if any 1m open_time in [T+2m,T+14m] has low<p0 (buy)/high>p0 (sell); else taker 0.0005 at T+15m 1m open (p0 if missing) with 0.0002 adverse; extra vs normal = 0.0003*|d|+|fill/limit-1|*|d|"}},
        "v105a_noflow_LS": {"anchors": a3a_anchors, "yearly_normal": yearly105a},
        "v105b_7dflow_LO": {"anchors": a3b_anchors, "yearly_normal": yearly105b},
        "data": {"usdm_btc": "data/raw/ma_ribbon_20260924", "usdm_others": "data/raw/xs_universe_20260924",
                 "spot_prefix": "data/raw/spot_majors_20260925/{SYM}_spot_{4h,1d}_2017.parquet open_time < first USD-M bar (SOL none)",
                 "carry": "artifacts/research/carry/carry_oos_fee0.0004.parquet",
                 "v96_books_source": "v92_audit/predictions_5asset.csv + v93_v94_audit/predictions_v94.csv, leader vol_target_scale (no fillna, NaN->1)"},
        "execution": {"fee_per_unit_turnover": 0.0002, "long_funding_per_4h_bar": 5e-05,
                      "v103_weight": "v94.weights_ls; long=min(max(p,0)/0.5,1) rib!=-1; short=min(max(-p,0)/0.5,1) rib!=+1; raw=(l-s)/(vol42*sqrt(2190)); /sum|raw| *min(1,count/5); every 6th bar ffill",
                      "v103_vol": "v94.vol_target_scale target 0.20 cap 2 (realized=W.shift(2)*ret1 no fillna, rolling360 min120, NaN->1)",
                      "v103_blend": "blend_books=0.5*v96books+0.5*(W103LS*s103); simulate with scale 1.0 (no further vol target)",
                      "v104_wrapper": "v99 leader convention: realized=0.8*(books.shift(2)*ret1).sum+0.6*carry.shift(1); vol 360/min120; s=min(0.15/vol,2) NaN->1; Wt=0.8*s*books; model earns o[t+2]/o[t+1]-1 fee on turn + funding; carry earns carry_exp[t]*carry[t] cost |diff|*2*0.0004/1.2 first diff 0"},
        "assumptions": ["flow features causal rolling on prefixed 4h klines (incl spot); HGB NaN-native",
                        "v103 ICs spearman(mean pred, y_h) on OOS rows with y_h not NaN",
                        "v96 books recomputed from audited CSVs (no retrain) with leader scales",
                        "v104 scenarios use v92.SCEN fees/slips; fills = trend-leg turnover bars",
                        "hidden execution extra charged on trend leg only; carry unchanged"],
    }
    with open(OUT_DIR / "replication.json", "w") as f:
        json.dump(result, f, indent=2)
    oos103[["t", "sym", "open", "pred", "pred_h6", "pred_h18", "y6", "y18", "y42", "vol42", "rib"]].to_csv(
        OUT_DIR / "predictions_v103.csv", index=False)
    pd.DataFrame({"t": net_ls.index, "net": net_ls.values, "turnover": turn_ls.values, "scale": sls.reindex(net_ls.index).fillna(1.0).values}).to_csv(
        OUT_DIR / "equity_v103_LS.csv", index=False)
    pd.DataFrame({"t": net_lo.index, "net": net_lo.values, "turnover": turn_lo.values, "scale": slo.reindex(net_lo.index).fillna(1.0).values}).to_csv(
        OUT_DIR / "equity_v103_LO.csv", index=False)
    pd.DataFrame({"t": net_bl.index, "net": net_bl.values, "turnover": turn_bl.values}).to_csv(
        OUT_DIR / "equity_v103_blend.csv", index=False)
    for sc, v in v104_paths.items():
        pd.DataFrame({"t": v["net"].index, "net": v["net"].values, "turnover": v["turn"].values,
                      "scale": v["scale"].values}).to_csv(OUT_DIR / f"equity_v104_{sc}.csv", index=False)
    pd.DataFrame({"t": exec_net_full.index, "net_exec": exec_net_full.values,
                  "extra_cost": hid["extra"].reindex(exec_net_full.index).fillna(0.0).values}).to_csv(
        OUT_DIR / "equity_v104_hidden_exec.csv", index=False)
    oos105a[["t", "sym", "open", "pred", "y6", "y18", "y42", "vol42", "rib"]].to_csv(
        OUT_DIR / "predictions_v105a_noflow.csv", index=False)
    pd.DataFrame({"t": net105a.index, "net": net105a.values, "turnover": turn105a.values}).to_csv(
        OUT_DIR / "equity_v105a_noflow.csv", index=False)
    oos105b[["t", "sym", "open", "pred", "y6", "y18", "y42", "vol42", "rib"]].to_csv(
        OUT_DIR / "predictions_v105b_7dflow.csv", index=False)
    pd.DataFrame({"t": net105b.index, "net": net105b.values, "turnover": turn105b.values}).to_csv(
        OUT_DIR / "equity_v105b_7dflow.csv", index=False)
    print(json.dumps({"v103": yearly_ls, "v104_normal": yearly_v104["normal"],
                      "v105a": yearly105a, "v105b": yearly105b}, indent=2))


if __name__ == "__main__":
    main()
