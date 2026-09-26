"""Blind v127+v128 audit replication (Part A).
Does NOT read research/.../v127/* nor research/.../v128/*.

Base (per OPENCODE_V127_V128_AUDIT.md):
  audited v123_v125 (tranching), v126 (phase runs) and v115 replications.

Blind specs implemented:
A1 (v127): v125 tranched books (un-subsampled LO/LS frames from audited OOS
  CSVs -> per phase keep pos%6==phase ffill fillna0, mean over 6 phases; own
  0.20-cap-2 vol scales on tranched; books 0.25/0.25/0.5), v115 primary
  portfolio (target 0.15 ungoverned sequential v110 engine, three v92
  scenarios) + hidden year with v104 strict fill rule and vectorised v104
  cost path on the tranched weights. Report scenarios, full-path DDs and
  hidden-year net/DD/maker rate/orders.
A2 (v128): rebuild v114 extended panel from raw; add hv_days =
  (t - last halving)/1461 days (halvings 2012-11-28, 2016-07-09, 2020-05-11,
  2024-04-20 UTC; last halving <= t), hv_sin/hv_cos = sin/cos(2*pi*hv_days);
  retrain v92 LO (HGB h42, cutoff anchor-408h) / v94 LS (3x HGB h18/42/84,
  cutoff anchor-576h) with all non-target columns; v115 portfolio
  (0.25/0.25/0.5, unchanged v103) evaluated per rebalance phase 0..5
  (v126 method: phase_frame per book, own 0.20-cap-2 scales, target 0.15
  ungoverned sequential). Report per-anchor v92 IC and phase mean monthly /
  worst full-path DD, with (retrained) and without (audited OOS CSV baseline
  recomputed with identical phase code) the features.

Blind choices documented in replication.json meta:
  - hv t = bar open_time (panel t); same hv triple for all 5 assets at same t.
  - No retraining for A1 or the A2 baseline; A2 with-hv trains 20 HGB fits.
  - Hidden A1 has NO band (spec mentions none); whole-index s target 0.15.
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.ensemble import HistGradientBoostingRegressor

ROOT = Path(__file__).resolve().parents[5]
OUT_DIR = Path(__file__).resolve().parent

SYMS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
ANCHORS = ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")
PD = 6
ANN = np.sqrt(PD * 365)
ROLL, ROLL_MIN, CAP = 60 * PD, 20 * PD, 2.0
W_BOOKS, W_CARRY, CARRY_LEV = 0.8, 0.2, 3.0
SCEN = {"normal": (0.0002, 0.0), "fee_stress": (0.0006, 0.0), "execution_stress": (0.0006, 0.0005)}
START = pd.Timestamp("2021-09-24", tz="UTC")
END = START + pd.Timedelta(days=5 * 365)
HIDDEN = pd.Timestamp("2025-09-24", tz="UTC")
H_V92 = 42
HS = (18, 42, 84)
EMB_V92 = H_V92 + 10 * PD  # 102 bars = 408h
EMB_V94 = 84 + 60  # 144 bars = 576h
HGB = dict(max_depth=4, learning_rate=0.03, max_iter=400, min_samples_leaf=300,
           l2_regularization=1.0, random_state=0)
HALVINGS = [pd.Timestamp(d, tz="UTC") for d in
            ("2012-11-28", "2016-07-09", "2020-05-11", "2024-04-20")]

V114_LO_CSV = ROOT / "research/parallel/rounds/parallel-20260906-r2/v113_v114_audit/predictions_v114_v92.csv"
V114_LS_CSV = ROOT / "research/parallel/rounds/parallel-20260906-r2/v113_v114_audit/predictions_v114_v94.csv"
V103_CSV = ROOT / "research/parallel/rounds/parallel-20260906-r2/v103_v105_audit/predictions_v103.csv"
CARRY_FILE = ROOT / "artifacts/research/carry/carry_oos_fee0.0004.parquet"
BTC_DIR = ROOT / "data/raw/ma_ribbon_20260924"
XS_DIR = ROOT / "data/raw/xs_universe_20260924"
SPOT_DIR = ROOT / "data/raw/spot_majors_20260925"
CB_DIR = ROOT / "data/raw/coinbase_20260925"
BS_FILE = ROOT / "data/raw/bitstamp_20260925/btcusd_1h_2011_2015.parquet"


# ---------- shared weight/scale/sim (audited v115/v125/v126 formulas) ----------
def weights_lo_from_oos(oos):
    Wd = {}
    for s, g in oos.groupby("sym"):
        g = g.set_index("t").sort_index()
        sig = g["pred"].clip(lower=0) / 0.5
        sig = sig.where(g["rib"] != -1, 0.0).clip(upper=1.0)
        Wd[s] = sig / (g["vol42"].astype(float) * ANN)
    W = pd.DataFrame(Wd).sort_index().fillna(0.0)
    gross = W.abs().sum(axis=1)
    n_pos = W.gt(0).sum(axis=1).clip(lower=1)
    W = W.div(gross.clip(lower=1e-9), axis=0).mul(gross.gt(0), axis=0)
    W = W.mul((n_pos / 5).clip(upper=1.0), axis=0)
    return W


def weights_ls_from_oos(oos):
    Wd = {}
    for s, g in oos.groupby("sym"):
        g = g.set_index("t").sort_index()
        p = g["pred"].astype(float)
        rib = g["rib"].astype(float)
        long_ = (p.clip(lower=0) / 0.5).clip(upper=1.0).where(rib != -1, 0.0)
        short = ((-p).clip(lower=0) / 0.5).clip(upper=1.0).where(rib != 1, 0.0)
        raw = (long_ - short) / (g["vol42"].astype(float) * ANN)
        Wd[s] = raw.replace([np.inf, -np.inf], np.nan).fillna(0.0)
    rawW = pd.DataFrame(Wd).sort_index()
    gross = rawW.abs().sum(axis=1)
    n_nz = (rawW != 0).sum(axis=1).clip(lower=1)
    W = rawW.div(gross.clip(lower=1e-9), axis=0).mul(gross.gt(0), axis=0)
    W = W.mul((n_nz / 5).clip(upper=1.0), axis=0).fillna(0.0)
    return W


def tranche_mean(W_raw):
    phases = []
    for ph in range(PD):
        keep = pd.Series(np.arange(len(W_raw)) % PD == ph, index=W_raw.index)
        phases.append(W_raw.where(keep, np.nan).ffill().fillna(0.0))
    return sum(phases) / len(phases), phases


def phase_frame(W_raw, phase):
    keep = pd.Series(np.arange(len(W_raw)) % PD == phase, index=W_raw.index)
    return W_raw.where(keep, np.nan).ffill().fillna(0.0)


def vol_scale(o, W, target=0.20):
    ret1 = o / o.shift(1) - 1
    realized = (W.shift(2) * ret1).sum(axis=1)
    vol = realized.rolling(ROLL, min_periods=ROLL_MIN).std(ddof=1) * ANN
    sc = (target / vol).clip(upper=CAP).fillna(1.0)
    return sc.replace([np.inf, -np.inf], CAP).fillna(1.0)


def stats(net, turn):
    eq = (1 + net).cumprod()
    days = len(net) / PD
    g = float(eq.iloc[-1]) if len(eq) else float("nan")
    dd = float(np.max(1 - eq / eq.cummax())) if len(eq) else float("nan")
    return dict(
        net_pct=round(100 * (g - 1), 2),
        monthly_geometric_net_percent=round(100 * (g ** (30.4375 / days) - 1), 3) if days > 0 else float("nan"),
        max_drawdown_percent=round(100 * dd, 2),
        sharpe=round(float(net.mean() / net.std() * ANN), 2) if float(net.std()) > 0 else 0.0,
        fills=int((turn > 1e-6).sum()),
        months=round(days / 30.4375, 1),
    )


def yearly(net, turn):
    out = []
    for a in ANCHORS:
        a0 = pd.Timestamp(a, tz="UTC")
        m = (net.index >= a0) & (net.index < a0 + pd.Timedelta(days=365))
        st = stats(net[m], turn[m])
        st["anchor"] = a
        out.append(st)
    return out


def run_seq(o_vals, books_vals, carry_vals, s_vals, live_mask, fee, slip):
    n, k = o_vals.shape
    fwd = np.zeros_like(o_vals)
    with np.errstate(divide="ignore", invalid="ignore"):
        fm = o_vals[2:] / o_vals[1:-1] - 1.0
    fm = np.where(np.isfinite(fm), fm, 0.0)
    fwd[: n - 2] = fm
    net = np.zeros(n)
    turn = np.zeros(n)
    prev_w = np.zeros(k)
    prev_c = 0.0
    for i in range(n):
        if live_mask[i]:
            w = W_BOOKS * s_vals[i] * books_vals[i]
            c = W_CARRY * CARRY_LEV * s_vals[i]
        else:
            w = np.zeros(k)
            c = 0.0
        gross = float(np.sum(w * fwd[i]))
        tcost = float(np.sum(np.abs(w - prev_w)) * (fee + slip))
        fund = float(np.sum(np.maximum(w, 0.0)) * 0.00005)
        cgross = float(c * carry_vals[i])
        ccost = float(abs(c - prev_c) * 2 * 0.0004 / 1.2)
        net[i] = gross - tcost - fund + cgross - ccost
        turn[i] = float(np.sum(np.abs(w - prev_w)))
        prev_w, prev_c = w, c
    return net, turn


def summarize_seq(net_s, turn_s):
    ys = yearly(net_s, turn_s)
    geo = np.prod([1 + y["net_pct"] / 100 for y in ys]) ** (1 / 5) - 1
    full = (net_s.index >= START) & (net_s.index < END)
    eq = (1 + net_s[full]).cumprod()
    return dict(yearly=ys, monthly_pct=round(100 * ((1 + geo) ** (1 / 12) - 1), 3),
                worst_year_dd=max(y["max_drawdown_percent"] for y in ys),
                full_path_dd=round(100 * float((1 - eq / eq.cummax()).max()), 2))


def load_1m(sym):
    d = ROOT / ("data/raw/btc_intraday_20260924" if sym == "BTCUSDT" else "data/raw/majors_intraday_20260924")
    pat = "klines_1m_202[56].parquet" if sym == "BTCUSDT" else f"{sym}_1m_202[56].parquet"
    m = pd.concat([pd.read_parquet(f, columns=["open_time", "open", "high", "low"]) for f in sorted(d.glob(pat))])
    m["open_time"] = pd.to_datetime(m["open_time"], utc=True)
    return m.drop_duplicates("open_time").set_index("open_time").sort_index()


def fill_strict_v104(W):
    rel = pd.DataFrame(0.0, index=W.index, columns=W.columns)
    maker = pd.DataFrame(True, index=W.index, columns=W.columns)
    dW = W.diff().fillna(W)
    for s in W.columns:
        m = load_1m(s)
        for t in dW.index[(dW[s].abs() > 1e-9) & (dW.index >= HIDDEN)]:
            T = t + pd.Timedelta(hours=4)
            buy = dW.at[t, s] > 0
            if T not in m.index:
                maker.at[t, s] = False
                rel.at[t, s] = 0.0002 if buy else -0.0002
                continue
            p0 = m.at[T, "open"]
            w = m.loc[T + pd.Timedelta(minutes=2): T + pd.Timedelta(minutes=14)]
            through = (w["low"] < p0).any() if buy else (w["high"] > p0).any()
            if not through:
                T15 = T + pd.Timedelta(minutes=15)
                px = m.at[T15, "open"] if T15 in m.index else p0
                rel.at[t, s] = px / p0 - 1 + (0.0002 if buy else -0.0002)
                maker.at[t, s] = False
    return rel, maker


# ---------- A1: v125 tranched books + v115 primary + hidden on tranched ----------
def part_a1_v127():
    o114_lo = pd.read_csv(V114_LO_CSV, parse_dates=["t"])
    o114_ls = pd.read_csv(V114_LS_CSV, parse_dates=["t"])
    o103_df = pd.read_csv(V103_CSV, parse_dates=["t"])
    for df in (o114_lo, o114_ls, o103_df):
        df["t"] = pd.to_datetime(df["t"], utc=True)
    o_v114 = o114_lo.pivot_table(index="t", columns="sym", values="open")[list(SYMS)].sort_index()
    o_v103 = o103_df.pivot_table(index="t", columns="sym", values="open")[list(SYMS)].sort_index()
    Wlo_raw = weights_lo_from_oos(o114_lo.sort_values(["t", "sym"]).reset_index(drop=True))
    W94_raw = weights_ls_from_oos(o114_ls.sort_values(["t", "sym"]).reset_index(drop=True))
    W103_raw = weights_ls_from_oos(o103_df.sort_values(["t", "sym"]).reset_index(drop=True))
    Wlo_t, _ = tranche_mean(Wlo_raw)
    W94_t, _ = tranche_mean(W94_raw)
    W103_t, _ = tranche_mean(W103_raw)
    s_lo_t = vol_scale(o_v114.reindex(Wlo_t.index).ffill(), Wlo_t)
    s94_t = vol_scale(o_v114.reindex(W94_t.index).ffill(), W94_t)
    s103_t = vol_scale(o_v103.reindex(W103_t.index), W103_t)
    idx = Wlo_t.index.union(W94_t.index).union(W103_t.index).sort_values()
    first_v103 = o_v103.index.min()
    idx = idx[idx >= first_v103]
    b_lo_t = Wlo_t.reindex(idx).fillna(0.0).mul(s_lo_t.reindex(idx).fillna(1.0), axis=0)
    b94_t = W94_t.reindex(idx).fillna(0.0).mul(s94_t.reindex(idx).fillna(1.0), axis=0)
    b103_t = W103_t.reindex(idx).fillna(0.0).mul(s103_t.reindex(idx).fillna(1.0), axis=0)
    books_t = 0.25 * b_lo_t + 0.25 * b94_t + 0.5 * b103_t
    o = o_v103.reindex(idx).sort_index()
    books_t = books_t[o.columns]
    carry = pd.read_parquet(CARRY_FILE)
    carry.index = pd.to_datetime(carry.index, utc=True)
    carry_s = carry.reindex(idx)["carry"].astype(float).fillna(0.0)
    ret1 = o / o.shift(1) - 1
    realized = W_BOOKS * (books_t.shift(2) * ret1).sum(axis=1) + W_CARRY * CARRY_LEV * carry_s.shift(1)
    vol = realized.rolling(ROLL, min_periods=ROLL_MIN).std(ddof=1) * ANN
    s15_t = (0.15 / vol).clip(upper=CAP).fillna(1.0).replace([np.inf, -np.inf], CAP).fillna(1.0)
    live_mask = np.asarray((idx >= START) & (idx < END))
    o_vals = o.to_numpy(dtype=float)
    books_vals = books_t.to_numpy(dtype=float)
    carry_vals = carry_s.to_numpy(dtype=float)
    s_vals = s15_t.to_numpy(dtype=float)
    scenarios = {}
    for sc, (fee, slip) in SCEN.items():
        net, turn = run_seq(o_vals, books_vals, carry_vals, s_vals, live_mask, fee, slip)
        scenarios[sc] = summarize_seq(pd.Series(net, index=idx), pd.Series(turn, index=idx))
        print("v127 tranched", sc, scenarios[sc]["monthly_pct"], scenarios[sc]["full_path_dd"], flush=True)
    # hidden year: vectorised v104 cost path on tranched weights, target 0.15, NO band
    realized_h = W_BOOKS * (books_t.shift(2) * ret1).sum(axis=1) + W_CARRY * CARRY_LEV * carry_s.shift(1)
    vol_h = realized_h.rolling(ROLL, min_periods=ROLL_MIN).std(ddof=1) * ANN
    s_hv = (0.15 / vol_h).clip(upper=CAP).fillna(1.0).replace([np.inf, -np.inf], CAP).fillna(1.0)
    Wt = books_t.mul(W_BOOKS * s_hv, axis=0)
    r_next = (o.shift(-2) / o.shift(-1) - 1).fillna(0.0)
    carry_exp = W_CARRY * CARRY_LEV * s_hv
    rel, maker = fill_strict_v104(Wt)
    dW = Wt.diff().fillna(Wt)
    rate = np.where(maker.reindex_like(dW).to_numpy(), 0.0002, 0.0005)
    cost = pd.Series((dW.abs().to_numpy() * rate).sum(axis=1), index=idx) + (dW * rel.reindex_like(dW).fillna(0.0)).sum(axis=1)
    net_h = ((Wt * r_next).sum(axis=1) - cost - Wt.clip(lower=0).sum(axis=1) * 0.00005
             + carry_exp * carry_s - carry_exp.diff().abs().fillna(0.0) * 2 * 0.0004 / 1.2)
    turn_h = dW.abs().sum(axis=1)
    mk = (idx >= HIDDEN) & (idx < HIDDEN + pd.Timedelta(days=365))
    orders_mask = (dW.abs() > 1e-9) & (idx >= HIDDEN)[:, None]
    maker_rate = round(float(maker[orders_mask].stack().mean()) if orders_mask.values.any() else float("nan"), 3)
    hid = stats(net_h[mk], turn_h[mk])
    hid.update(maker_fill_rate=maker_rate,
               orders_hidden_year=int((dW.abs() > 1e-9).loc[mk].sum().sum()),
               fills_hidden_year=int((turn_h[mk] > 1e-6).sum()))
    print("v127 hidden", hid, flush=True)
    return dict(scenarios=scenarios, hidden_year_1m_execution_strict=hid,
                union_bars=int(len(idx)), oos_span=[str(idx[0]), str(idx[-1])])


# ---------- A2 panel rebuild (v114) + halving features ----------
def load_hourly_coinbase(pair):
    pre = pd.read_parquet(CB_DIR / f"{pair}_1h_pre2017.parquet")
    main = pd.read_parquet(CB_DIR / f"{pair}_1h.parquet")
    h = pd.concat([pre, main], ignore_index=True)
    h["open_time"] = pd.to_datetime(h["open_time"], utc=True)
    return h.sort_values("open_time").drop_duplicates("open_time", keep="last").sort_values("open_time").reset_index(drop=True)


def load_hourly_btc_v114(cb_btc):
    bs = pd.read_parquet(BS_FILE)
    bs["open_time"] = pd.to_datetime(bs["open_time"], utc=True)
    first_cb = cb_btc["open_time"].min()
    part = bs[(bs["open_time"] >= pd.Timestamp("2013-01-01", tz="UTC")) & (bs["open_time"] < first_cb)].copy()
    h = pd.concat([part, cb_btc], ignore_index=True)
    return h.sort_values("open_time").drop_duplicates("open_time", keep="last").sort_values("open_time").reset_index(drop=True)


def aggregate(hourly, rule):
    h = hourly.sort_values("open_time").copy()
    for c in ("open", "high", "low", "close", "volume"):
        h[c] = h[c].astype(float)
    h["quote"] = h["volume"] * h["close"]
    freq = "4h" if rule == "4h" else "D"
    key = h["open_time"].dt.floor(freq).rename("grp")
    g = h.groupby(key)
    need = 3 if rule == "4h" else 20
    out = pd.DataFrame({
        "open_time": g["open_time"].first().to_numpy(),
        "open": g["open"].first().to_numpy(),
        "high": g["high"].max().to_numpy(),
        "low": g["low"].min().to_numpy(),
        "close": g["close"].last().to_numpy(),
        "volume": g["volume"].sum().to_numpy(),
        "quote_volume": g["quote"].sum().to_numpy(),
        "cnt": g.size().to_numpy(),
    })
    out["open_time"] = pd.to_datetime(out["open_time"], utc=True).dt.floor(freq)
    out = out[out["cnt"] >= need].copy()
    delta = pd.Timedelta(hours=4) if rule == "4h" else pd.Timedelta(days=1)
    out["close_time"] = out["open_time"] + delta - pd.Timedelta(milliseconds=1)
    return out[["open_time", "open", "high", "low", "close", "volume", "quote_volume", "close_time", "cnt"]].sort_values("open_time").reset_index(drop=True)


def load_base(sym):
    if sym == "BTCUSDT":
        b = pd.read_parquet(BTC_DIR / "klines_4h.parquet")
        d = pd.read_parquet(BTC_DIR / "klines_1d.parquet")
        f = pd.read_parquet(BTC_DIR / "funding.parquet")
    else:
        b = pd.read_parquet(XS_DIR / f"{sym}_4h.parquet")
        d = pd.read_parquet(XS_DIR / f"{sym}_1d.parquet")
        f = pd.read_parquet(XS_DIR / f"{sym}_funding.parquet")
    for x in (b, d):
        x["open_time"] = pd.to_datetime(x["open_time"], utc=True)
        x["close_time"] = pd.to_datetime(x["close_time"], utc=True)
    f["fundingTime"] = pd.to_datetime(f["fundingTime"], utc=True)
    b = b.sort_values("open_time").reset_index(drop=True)
    d = d.sort_values("open_time").reset_index(drop=True)
    if not (SPOT_DIR / f"{sym}_spot_4h_2017.parquet").exists():
        s4, s1 = b.iloc[:0].copy(), d.iloc[:0].copy()
    else:
        s4 = pd.read_parquet(SPOT_DIR / f"{sym}_spot_4h_2017.parquet")
        s1 = pd.read_parquet(SPOT_DIR / f"{sym}_spot_1d_2017.parquet")
    for x in (s4, s1):
        x["open_time"] = pd.to_datetime(x["open_time"], utc=True)
        x["close_time"] = pd.to_datetime(x["close_time"], utc=True)
    pre4 = s4[s4["open_time"] < b["open_time"].min()].copy()
    pre1 = s1[s1["open_time"] < d["open_time"].min()].copy()
    b = pd.concat([pre4, b], ignore_index=True).sort_values("open_time").reset_index(drop=True)
    d = pd.concat([pre1, d], ignore_index=True).sort_values("open_time").reset_index(drop=True)
    return b, d, f


def extend_asset(sym, base_b, base_d, agg4, agg1):
    add4 = agg4[agg4["open_time"] < base_b["open_time"].min()].copy() if agg4 is not None else base_b.iloc[:0].copy()
    add1 = agg1[agg1["open_time"] < base_d["open_time"].min()].copy() if agg1 is not None else base_d.iloc[:0].copy()
    b = pd.concat([add4, base_b], ignore_index=True).sort_values("open_time").reset_index(drop=True)
    d = pd.concat([add1, base_d], ignore_index=True).sort_values("open_time").reset_index(drop=True)
    return b, d


def features_v114(b, d, f):
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
    for h in HS:
        fwd = np.full(n, np.nan)
        if n > 1 + h:
            fwd[: n - 1 - h] = np.log(o[1 + h:] / o[1: n - h])
        x[f"y{h}"] = np.clip(fwd / (vol42.to_numpy() * np.sqrt(h)), -4, 4)
    x["y"] = x["y42"]
    return x


def add_halving_features(panel):
    """hv_days=(t-last halving)/1461 days; hv_sin/cos=sin/cos(2*pi*hv_days).

    Blind choice: t = bar open_time (panel t); last halving <= t from the four
    listed UTC dates; identical triple for all assets sharing t (causal: only
    past halvings used).
    """
    t = pd.to_datetime(panel["t"], utc=True)
    halv = np.array([h.value for h in HALVINGS])
    tv = t.values.astype("datetime64[ns]").astype(np.int64)
    last = np.full(len(t), halv[0])
    for h in halv[1:]:
        last = np.where(tv >= h, h, last)
    hv_days = (tv - last) / 1e9 / 86400.0 / 1461.0
    panel = panel.copy()
    panel["hv_days"] = hv_days
    panel["hv_sin"] = np.sin(2 * np.pi * hv_days)
    panel["hv_cos"] = np.cos(2 * np.pi * hv_days)
    return panel


def run_phases(Wlo_raw, W94_raw, W103_raw, o_lo, o_103, carry, tag):
    """v126 method: per phase keep pos%6==p ffill, own 0.20-cap-2 scales,
    books 0.25/0.25/0.5, target 0.15 ungoverned sequential."""
    first_v103 = o_103.index.min()
    phases = {}
    for p in range(PD):
        Wlo_p = phase_frame(Wlo_raw, p)
        W94_p = phase_frame(W94_raw, p)
        W103_p = phase_frame(W103_raw, p)
        s_lo = vol_scale(o_lo.reindex(Wlo_p.index).ffill(), Wlo_p)
        s94 = vol_scale(o_lo.reindex(W94_p.index).ffill(), W94_p)
        s103 = vol_scale(o_103.reindex(W103_p.index), W103_p)
        idx = Wlo_p.index.union(W94_p.index).union(W103_p.index).sort_values()
        idx = idx[idx >= first_v103]
        b_lo = Wlo_p.reindex(idx).fillna(0.0).mul(s_lo.reindex(idx).fillna(1.0), axis=0)
        b94 = W94_p.reindex(idx).fillna(0.0).mul(s94.reindex(idx).fillna(1.0), axis=0)
        b103 = W103_p.reindex(idx).fillna(0.0).mul(s103.reindex(idx).fillna(1.0), axis=0)
        books = 0.25 * b_lo + 0.25 * b94 + 0.5 * b103
        o = o_103.reindex(idx).sort_index()
        books = books[o.columns]
        carry_s = carry.reindex(idx)["carry"].astype(float).fillna(0.0)
        ret1 = o / o.shift(1) - 1
        realized = W_BOOKS * (books.shift(2) * ret1).sum(axis=1) + W_CARRY * CARRY_LEV * carry_s.shift(1)
        vol = realized.rolling(ROLL, min_periods=ROLL_MIN).std(ddof=1) * ANN
        s15 = (0.15 / vol).clip(upper=CAP).fillna(1.0).replace([np.inf, -np.inf], CAP).fillna(1.0)
        live_mask = np.asarray((idx >= START) & (idx < END))
        o_vals = o.to_numpy(dtype=float)
        books_vals = books.to_numpy(dtype=float)
        carry_vals = carry_s.to_numpy(dtype=float)
        s_vals = s15.to_numpy(dtype=float)
        res = {}
        for sc, (fee, slip) in SCEN.items():
            net, turn = run_seq(o_vals, books_vals, carry_vals, s_vals, live_mask, fee, slip)
            res[sc] = summarize_seq(pd.Series(net, index=idx), pd.Series(turn, index=idx))
        phases[str(p)] = res
        print(f"{tag} phase {p} normal monthly={res['normal']['monthly_pct']} fullDD={res['normal']['full_path_dd']}", flush=True)
    summary = {}
    for sc in SCEN:
        monthlies = [phases[str(p)][sc]["monthly_pct"] for p in range(PD)]
        fulldds = [phases[str(p)][sc]["full_path_dd"] for p in range(PD)]
        summary[sc] = {
            "monthly_pct_mean": round(float(np.mean(monthlies)), 3),
            "monthly_pct_min": round(float(np.min(monthlies)), 3),
            "monthly_pct_max": round(float(np.max(monthlies)), 3),
            "full_path_dd_mean": round(float(np.mean(fulldds)), 2),
            "full_path_dd_min": round(float(np.min(fulldds)), 2),
            "full_path_dd_max": round(float(np.max(fulldds)), 2),
        }
    return phases, summary


def part_a2_v128():
    cb_btc = load_hourly_coinbase("BTC-USD")
    cb_eth = load_hourly_coinbase("ETH-USD")
    bs_btc = load_hourly_btc_v114(cb_btc)
    agg = {"BTCUSDT": (aggregate(bs_btc, "4h"), aggregate(bs_btc, "1d")),
           "ETHUSDT": (aggregate(cb_eth, "4h"), aggregate(cb_eth, "1d"))}
    ext = {}
    for s in SYMS:
        b0, d0, f = load_base(s)
        if s in agg:
            b, d = extend_asset(s, b0, d0, agg[s][0], agg[s][1])
        else:
            b, d = b0, d0
        ext[s] = (b, d, f)
    rows = []
    for i, s in enumerate(SYMS):
        b, d, f = ext[s]
        x = features_v114(b, d, f)
        x["asset"] = i
        x["t"] = b["open_time"]
        x["open"] = b["open"].astype(float).to_numpy()
        x["sym"] = s
        x["bar"] = np.arange(len(b))
        rows.append(x)
    panel = pd.concat(rows, ignore_index=True)
    btc = panel[panel.sym == "BTCUSDT"].set_index("t")[["ret42", "ret180", "rib", "snr42"]].add_prefix("btc_")
    panel = panel.join(btc, on="t")
    panel = add_halving_features(panel)
    base_feats = [c for c in panel.columns if c not in ("t", "open", "sym", "bar", "y", "y18", "y42", "y84")]
    assert set(("hv_days", "hv_sin", "hv_cos")) <= set(base_feats)
    feats = base_feats  # all non-target columns (26 v114 + 3 hv = 29)
    # v92 LO retrain (with hv)
    anchors92, parts92 = [], []
    for anchor in ANCHORS:
        a = pd.Timestamp(anchor, tz="UTC")
        end = a + pd.Timedelta(days=365)
        cutoff = a - pd.Timedelta(hours=4 * EMB_V92)
        tr = panel[(panel.t < cutoff) & panel.y.notna()]
        tr = tr[tr.t + pd.Timedelta(hours=4 * (H_V92 + 1)) < cutoff]
        te = panel[(panel.t >= a) & (panel.t < end)].copy()
        m = HistGradientBoostingRegressor(**HGB)
        m.fit(tr[feats], tr["y"])
        te["pred"] = m.predict(te[feats])
        ev = te.dropna(subset=["y"])
        rho = float(spearmanr(ev["pred"], ev["y"]).statistic) if len(ev) > 2 else float("nan")
        anchors92.append(dict(anchor=anchor, train_rows=int(len(tr)), n_pred_rows=int(len(te)),
                              n_pred_rows_with_y=int(len(ev)), ic=round(rho, 4)))
        parts92.append(te)
        print("v128 v92+hv", anchor, len(tr), round(rho, 4), flush=True)
    oos92 = pd.concat(parts92, ignore_index=True).sort_values(["t", "sym"]).reset_index(drop=True)
    # v94 LS retrain (with hv)
    anchors94, parts94 = [], []
    for anchor in ANCHORS:
        a = pd.Timestamp(anchor, tz="UTC")
        end = a + pd.Timedelta(days=365)
        cutoff = a - pd.Timedelta(hours=4 * EMB_V94)
        te = panel[(panel.t >= a) & (panel.t < end)].copy()
        preds = np.zeros((len(te), len(HS)))
        ntrs = []
        for j, h in enumerate(HS):
            yh = f"y{h}"
            tr = panel[(panel.t < cutoff) & panel[yh].notna()]
            tr = tr[tr.t + pd.Timedelta(hours=4 * (h + 1)) < cutoff]
            ntrs.append(int(len(tr)))
            m = HistGradientBoostingRegressor(**HGB)
            m.fit(tr[feats], tr[yh])
            preds[:, j] = m.predict(te[feats])
        te["pred"] = preds.mean(axis=1)
        for j, h in enumerate(HS):
            te[f"pred_h{h}"] = preds[:, j]
        ev = te.dropna(subset=["y42"])
        rho = float(spearmanr(ev["pred"], ev["y42"]).statistic) if len(ev) > 2 else float("nan")
        anchors94.append(dict(anchor=anchor, train_rows_h18=ntrs[0], train_rows_h42=ntrs[1],
                              train_rows_h84=ntrs[2], n_pred_rows=int(len(te)),
                              n_pred_rows_with_y=int(len(ev)), ic_mean_vs_h42=round(rho, 4)))
        parts94.append(te)
        print("v128 v94+hv", anchor, ntrs, round(rho, 4), flush=True)
    oos94 = pd.concat(parts94, ignore_index=True).sort_values(["t", "sym"]).reset_index(drop=True)
    oos92[["t", "sym", "open", "pred", "y", "vol42", "rib"]].to_csv(OUT_DIR / "predictions_v128_v92.csv", index=False)
    oos94[["t", "sym", "open", "pred", "pred_h18", "pred_h42", "pred_h84", "y42", "vol42", "rib"]].to_csv(OUT_DIR / "predictions_v128_v94.csv", index=False)
    # books with hv (un-subsampled) + unchanged v103
    W92_raw = weights_lo_from_oos(oos92)
    W94_raw = weights_ls_from_oos(oos94)
    o103_df = pd.read_csv(V103_CSV, parse_dates=["t"])
    o103_df["t"] = pd.to_datetime(o103_df["t"], utc=True)
    o103_df = o103_df.sort_values(["t", "sym"]).reset_index(drop=True)
    W103_raw = weights_ls_from_oos(o103_df)
    o_panel = panel.pivot_table(index="t", columns="sym", values="open").sort_index()[list(SYMS)]
    o_panel.index = pd.to_datetime(o_panel.index, utc=True)
    o_v103 = o103_df.pivot_table(index="t", columns="sym", values="open")[list(SYMS)].sort_index()
    carry = pd.read_parquet(CARRY_FILE)
    carry.index = pd.to_datetime(carry.index, utc=True)
    o_lo_hv = o_panel.loc[W92_raw.index].copy() if set(W92_raw.index) <= set(o_panel.index) else o_panel
    phases_with, summary_with = run_phases(W92_raw, W94_raw, W103_raw, o_lo_hv, o_v103, carry, "v128+hv")
    # baseline without hv: audited OOS CSVs + identical phase code (must match v126)
    o114_lo = pd.read_csv(V114_LO_CSV, parse_dates=["t"])
    o114_ls = pd.read_csv(V114_LS_CSV, parse_dates=["t"])
    for df in (o114_lo, o114_ls):
        df["t"] = pd.to_datetime(df["t"], utc=True)
    Wlo_base = weights_lo_from_oos(o114_lo.sort_values(["t", "sym"]).reset_index(drop=True))
    W94_base = weights_ls_from_oos(o114_ls.sort_values(["t", "sym"]).reset_index(drop=True))
    o_v114 = o114_lo.pivot_table(index="t", columns="sym", values="open")[list(SYMS)].sort_index()
    phases_wo, summary_wo = run_phases(Wlo_base, W94_base, W103_raw, o_v114, o_v103, carry, "v128-base")
    return dict(
        features_with_hv=feats,
        anchors_v92_with=anchors92,
        anchors_v94_with=anchors94,
        phases_with=phases_with,
        phase_summary_with=summary_with,
        phases_without=phases_wo,
        phase_summary_without=summary_wo,
    )


def main():
    v127 = part_a1_v127()
    v128 = part_a2_v128()
    out = {
        "version": "v127_v128_audit_replication",
        "v127": v127,
        "v128": v128,
        "meta": {
            "anchors": list(ANCHORS),
            "scenarios": {k: {"fee": v[0], "slip": v[1]} for k, v in SCEN.items()},
            "v127_spec": "v125 tranched books (un-subsampled LO/LS -> per-phase keep pos%6==phase ffill mean over 6; own 0.20-cap-2 scales) ; books 0.25/0.25/0.5; s 0.15 sequential v110 ungoverned; hidden v104 fill_strict [T+2m,T+14m] T+15m fallback missing-T taker + v104 cost path on tranched weights, no band",
            "v128_spec": "v114 panel + hv_days=(t-last halving)/1461 days (halvings 2012-11-28, 2016-07-09, 2020-05-11, 2024-04-20 UTC; last<=t; t=bar open_time) + hv_sin/cos=sin/cos(2*pi*hv_days); HGB v92 h42 cutoff-408h / v94 h18/42/84 cutoff-576h all non-target cols (29 feats); v115 portfolio (unchanged v103) per phase 0..5 v126 method (own 0.20-cap-2 scales, 0.25/0.25/0.5, s 0.15 sequential ungoverned)",
            "data": {"v103": "v103_v105_audit/predictions_v103.csv",
                     "carry": "artifacts/research/carry/carry_oos_fee0.0004.parquet",
                     "panel": "v114 extended Bitstamp>=2013-01-01+Coinbase BTC, Coinbase ETH, spot+USD-M, UTC floor agg 4h>=3/1d>=20"},
            "model": HGB,
        },
    }
    with open(OUT_DIR / "replication.json", "w") as f:
        json.dump(out, f, indent=2)
    print(json.dumps({"v127_monthly_normal": v127["scenarios"]["normal"]["monthly_pct"],
                      "v127_hidden": v127["hidden_year_1m_execution_strict"],
                      "v128_v92_IC_with": [a["ic"] for a in v128["anchors_v92_with"]],
                      "v128_summary_with_normal": v128["phase_summary_with"]["normal"],
                      "v128_summary_without_normal": v128["phase_summary_without"]["normal"]}, indent=2))


if __name__ == "__main__":
    main()
