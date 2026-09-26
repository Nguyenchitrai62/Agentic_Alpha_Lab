"""Blind v118+v119 audit replication (Part A). Does NOT read research/.../v118/* nor v119/*.

Base (per OPENCODE_V118_V119_AUDIT.md):
  audited v115 replication (books, v110 engine) and v113_v114 (v114 panel) replications.

A1 (v118): v115 primary (target 0.15, ungoverned) in a sequential loop where
  per asset the held weight h changes to target w only if |w-h| > band
  (band 0.02 primary, 0.05 secondary, 0 reference); outside live span weights
  are 0 (targets 0 taken immediately); turnover = sum|new-held|; carry
  exposure 0.6*s unchanged with v110 carry cost; long funding 0.00005 on held
  long gross. Report yearly net/DD/fills (turnover>1e-6) and full-path DD.

A2 (v119): on the v114 panel, per anchor: cutoff = anchor-102*4h; training
  rows t<cutoff with y and t+43*4h<cutoff; validation = training rows with
  t>=cutoff-730d; inner-train = training rows with t+43*4h<val_start-102*4h.
  Grid max_depth (3,4,6) x min_samples_leaf (300,1000), lr 0.03, max_iter 400,
  l2 1.0, seed 0; score=Spearman on validation; refit best on all training
  rows; predict test year. Report chosen configs, val scores, test IC,
  v92 LO book (v92 vol target) and v96 blend with v114-panel v94 LS book.

Blind choices (fixed before running, documented):
  - A1: books/s/carry/opens/live/scenarios identical to audited v115 primary
    (replicate_v115.py): books=0.25*b_lo+0.25*b94+0.5*b103, 20%-cap-2 scales,
    daily ffill k=6, union t>=first-v103-t, opens=v103 OOS opens, live
    [2021-09-24,2026-09-23), s target 0.15 via realized=0.8*sum(books.shift(2)
    *ret1)+0.6*carry.shift(1), rolling-360/min-120*sqrt(2190), cap2 NaN->1.
    Targets w=0.8*s*books (ungoverned, g=1); carry c=0.6*s unchanged.
    Band applied per asset vs previous HELD (not target): if live and
    |w-h_prev|>band -> h=w else h=h_prev; if not live -> h=0 immediately
    (targets 0 taken immediately). Turnover=sum|h-h_prev|; gross=sum(h*fwd)
    with fwd=o[i+2]/o[i+1]-1 (last two ->0); funding=0.00005*sum(max(h,0));
    carry cost=|dc|*2*0.0004/1.2. Scenarios normal(0.0002,0)/fee(0.0006,0)/
    exec(0.0006,0.0005). Band 0 reference must equal v115 primary exactly.
  - A2: v114 panel rebuilt from raw data with inline audited formulas from
    replicate_v113_v114.py (Bitstamp>=2013-01-01 + Coinbase BTC, Coinbase ETH,
    spot prefix + USD-M, UTC floor agg 4h cnt>=3/1d cnt>=20, v92 26 feats).
    No retraining reuse: full grid retrained locally (replay + small HGB grid,
    not heavy cloud training). y=y42; cutoff=anchor-408h; val_start=cutoff-
    730d; inner embargo t+43*4h<val_start-408h. Spearman on validation
    (pred vs y, pairwise, NaN-dropped). Test IC on test-year rows with y.
    LO book = audited v92 LO execution (daily ffill, 20%-cap-2 vol target);
    blend Wc=0.5*Wnew*snew+0.5*W94*s94 (W94/s94 from audited v114 v94 CSVs,
    scale 1, v92 costs). Yearly slices [A,A+365d), fills turnover>1e-6.
"""
import json
from itertools import product
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.ensemble import HistGradientBoostingRegressor

ROOT = Path(__file__).resolve().parents[5]
OUT_DIR = Path(__file__).resolve().parent

# ---------------- shared ----------------
SYMS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
ANCHORS = ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")
PD = 6
ANN = np.sqrt(PD * 365)
ROLL, ROLL_MIN, CAP = 60 * PD, 20 * PD, 2.0
W_BOOKS, W_CARRY, CARRY_LEV = 0.8, 0.2, 3.0
SCEN = {"normal": (0.0002, 0.0), "fee_stress": (0.0006, 0.0), "execution_stress": (0.0006, 0.0005)}
START = pd.Timestamp("2021-09-24", tz="UTC")
END = START + pd.Timedelta(days=5 * 365)
TARGET15 = 0.15
BANDS = {"primary_band002": 0.02, "secondary_band005": 0.05, "reference_band000": 0.0}

V114_LO_CSV = ROOT / "research/parallel/rounds/parallel-20260906-r2/v113_v114_audit/predictions_v114_v92.csv"
V114_LS_CSV = ROOT / "research/parallel/rounds/parallel-20260906-r2/v113_v114_audit/predictions_v114_v94.csv"
V103_CSV = ROOT / "research/parallel/rounds/parallel-20260906-r2/v103_v105_audit/predictions_v103.csv"
CARRY_FILE = ROOT / "artifacts/research/carry/carry_oos_fee0.0004.parquet"


def weights_lo(oos):
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
    keep = pd.Series(np.arange(len(W)) % PD == 0, index=W.index)
    return W.where(keep, np.nan).ffill().fillna(0.0)


def weights_ls(oos):
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
    keep = pd.Series(np.arange(len(W)) % PD == 0, index=W.index)
    return W.where(keep, np.nan).ffill().fillna(0.0)


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


def summarize_seq(net_s, turn_s):
    ys = []
    for a in ANCHORS:
        a0 = pd.Timestamp(a, tz="UTC")
        mk = (net_s.index >= a0) & (net_s.index < a0 + pd.Timedelta(days=365))
        ys.append(dict(anchor=a, **stats(net_s[mk], turn_s[mk])))
    geo = np.prod([1 + y["net_pct"] / 100 for y in ys]) ** (1 / 5) - 1
    full = (net_s.index >= START) & (net_s.index < END)
    eq = (1 + net_s[full]).cumprod()
    return dict(
        yearly=ys,
        monthly_pct=round(100 * ((1 + geo) ** (1 / 12) - 1), 3),
        worst_year_dd=max(y["max_drawdown_percent"] for y in ys),
        full_path_dd=round(100 * float((1 - eq / eq.cummax()).max()), 2),
    )


def run_band(o_vals, targ_vals, carry_vals, s_vals, live_mask, fee, slip, band):
    n, k = o_vals.shape
    fwd = np.zeros_like(o_vals)
    with np.errstate(divide="ignore", invalid="ignore"):
        fm = o_vals[2:] / o_vals[1:-1] - 1.0
    fm = np.where(np.isfinite(fm), fm, 0.0)
    fwd[: n - 2] = fm
    net = np.zeros(n)
    turn = np.zeros(n)
    held = np.zeros(k)
    prev_c = 0.0
    for i in range(n):
        if live_mask[i]:
            w = targ_vals[i]
            diff = np.abs(w - held)
            take = diff > band
            new = np.where(take, w, held)
        else:
            new = np.zeros(k)  # targets 0 taken immediately
        c = W_CARRY * CARRY_LEV * s_vals[i] if live_mask[i] else 0.0
        gross = float(np.sum(new * fwd[i]))
        tcost = float(np.sum(np.abs(new - held)) * (fee + slip))
        fund = float(np.sum(np.maximum(new, 0.0)) * 0.00005)
        cgross = float(c * carry_vals[i])
        ccost = float(abs(c - prev_c) * 2 * 0.0004 / 1.2)
        ni = gross - tcost - fund + cgross - ccost
        net[i] = ni
        turn[i] = float(np.sum(np.abs(new - held)))
        held = new
        prev_c = c
    return net, turn


def part_a1():
    o114_lo = pd.read_csv(V114_LO_CSV, parse_dates=["t"])
    o114_ls = pd.read_csv(V114_LS_CSV, parse_dates=["t"])
    o103_df = pd.read_csv(V103_CSV, parse_dates=["t"])
    for df in (o114_lo, o114_ls, o103_df):
        df["t"] = pd.to_datetime(df["t"], utc=True)
    o114_lo = o114_lo.sort_values(["t", "sym"]).reset_index(drop=True)
    o114_ls = o114_ls.sort_values(["t", "sym"]).reset_index(drop=True)
    o103_df = o103_df.sort_values(["t", "sym"]).reset_index(drop=True)

    W_lo = weights_lo(o114_lo)
    W94 = weights_ls(o114_ls)
    W103 = weights_ls(o103_df)
    o_v114 = o114_lo.pivot_table(index="t", columns="sym", values="open")[list(SYMS)].sort_index()
    o_v103 = o103_df.pivot_table(index="t", columns="sym", values="open")[list(SYMS)].sort_index()
    s_lo = vol_scale(o_v114, W_lo.reindex(o_v114.index).fillna(0.0))
    s94 = vol_scale(o_v114, W94.reindex(o_v114.index).fillna(0.0))
    s103 = vol_scale(o_v103, W103.reindex(o_v103.index).fillna(0.0))
    idx = W_lo.index.union(W94.index).union(W103.index).sort_values()
    first_v103 = o_v103.index.min()
    idx = idx[idx >= first_v103]
    b_lo = W_lo.reindex(idx).fillna(0.0).mul(s_lo.reindex(idx).fillna(1.0), axis=0)
    b94 = W94.reindex(idx).fillna(0.0).mul(s94.reindex(idx).fillna(1.0), axis=0)
    b103 = W103.reindex(idx).fillna(0.0).mul(s103.reindex(idx).fillna(1.0), axis=0)
    books = 0.25 * b_lo + 0.25 * b94 + 0.5 * b103
    o = o_v103.reindex(idx).sort_index()
    books = books[o.columns]
    carry = pd.read_parquet(CARRY_FILE)
    carry.index = pd.to_datetime(carry.index, utc=True)
    carry_s = carry.reindex(idx)["carry"].astype(float).fillna(0.0)
    ret1 = o / o.shift(1) - 1
    realized = W_BOOKS * (books.shift(2) * ret1).sum(axis=1) + W_CARRY * CARRY_LEV * carry_s.shift(1)
    vol = realized.rolling(ROLL, min_periods=ROLL_MIN).std(ddof=1) * ANN
    s = (TARGET15 / vol).clip(upper=CAP).fillna(1.0).replace([np.inf, -np.inf], CAP).fillna(1.0)

    live_mask = np.asarray((idx >= START) & (idx < END))
    o_vals = o.to_numpy(dtype=float)
    targ_vals = (W_BOOKS * s.values[:, None] * books.to_numpy(dtype=float))
    carry_vals = carry_s.to_numpy(dtype=float)
    s_vals = s.to_numpy(dtype=float)

    out = {}
    for bkey, band in BANDS.items():
        res = {}
        for sc, (fee, slip) in SCEN.items():
            net, turn = run_band(o_vals, targ_vals, carry_vals, s_vals, live_mask, fee, slip, band)
            net_s = pd.Series(net, index=idx)
            turn_s = pd.Series(turn, index=idx)
            res[sc] = summarize_seq(net_s, turn_s)
            print("A1", bkey, sc, res[sc]["monthly_pct"], res[sc]["worst_year_dd"],
                  res[sc]["full_path_dd"], flush=True)
        out[bkey] = res
    meta = {"union_bars": int(len(idx)), "n_live_bars": int(live_mask.sum()),
            "oos_span": [str(idx[0]), str(idx[-1])], "first_v103_t": str(first_v103)}
    return out, meta, idx


# ---------------- A2: v114 panel rebuild (audited formulas) ----------------
BTC_DIR = ROOT / "data/raw/ma_ribbon_20260924"
XS_DIR = ROOT / "data/raw/xs_universe_20260924"
SPOT_DIR = ROOT / "data/raw/spot_majors_20260925"
CB_DIR = ROOT / "data/raw/coinbase_20260925"
BS_FILE = ROOT / "data/raw/bitstamp_20260925/btcusd_1h_2011_2015.parquet"
HS_V94 = (18, 42, 84)
GRID = list(product((3, 4, 6), (300, 1000)))


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


def features(b, d, f):
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
    dfe = pd.DataFrame({"t": d["close_time"],
                        "d50": np.log(dc / sma50), "d200": np.log(dc / sma200),
                        "rib": np.where((dc > sma50) & (sma50 > sma200), 1.0,
                                        np.where((dc < sma50) & (sma50 < sma200), -1.0, 0.0))})
    j = pd.merge_asof(pd.DataFrame({"t": b["close_time"]}), dfe.sort_values("t"), on="t", direction="backward")
    x[["d50", "d200", "rib"]] = j[["d50", "d200", "rib"]].to_numpy()
    fr = f.set_index("fundingTime")["fundingRate"].astype(float)
    fm = pd.DataFrame({"t": fr.index, "f7": fr.rolling(21, min_periods=3).mean().to_numpy(),
                       "f30": fr.rolling(90, min_periods=9).mean().to_numpy()})
    jf = pd.merge_asof(pd.DataFrame({"t": b["close_time"]}), fm.sort_values("t"), on="t", direction="backward")
    x["f7"] = jf["f7"].to_numpy() * 1e4
    x["f30"] = jf["f30"].to_numpy() * 1e4
    lv = np.log(b["quote_volume"].astype(float).clip(lower=1))
    x["volz"] = (lv - lv.rolling(180).mean()) / lv.rolling(180).std()
    o = b["open"].astype(float).to_numpy()
    n = len(b)
    for h in HS_V94:
        fwd = np.full(n, np.nan)
        if n > 1 + h:
            fwd[: n - 1 - h] = np.log(o[1 + h:] / o[1: n - h])
        x[f"y{h}"] = np.clip(fwd / (vol42.to_numpy() * np.sqrt(h)), -4, 4)
    x["y"] = x["y42"]
    return x


def build_panel(ext_bars):
    rows = []
    for i, s in enumerate(SYMS):
        b, d, f = ext_bars[s]
        x = features(b, d, f)
        x["asset"] = i
        x["t"] = b["open_time"]
        x["open"] = b["open"].astype(float).to_numpy()
        x["sym"] = s
        x["bar"] = np.arange(len(b))
        rows.append(x)
    panel = pd.concat(rows, ignore_index=True)
    btc = panel[panel.sym == "BTCUSDT"].set_index("t")[["ret42", "ret180", "rib", "snr42"]].add_prefix("btc_")
    return panel.join(btc, on="t")


def spearman(a, b):
    m = np.isfinite(a) & np.isfinite(b)
    if m.sum() < 3:
        return float("nan")
    return float(spearmanr(a[m], b[m]).statistic)


def part_a2():
    cb_btc = load_hourly_coinbase("BTC-USD")
    cb_eth = load_hourly_coinbase("ETH-USD")
    bs_btc = load_hourly_btc_v114(cb_btc)
    agg = {s: (aggregate(h, "4h"), aggregate(h, "1d")) for s, h in (("BTCUSDT", bs_btc), ("ETHUSDT", cb_eth))}
    ext = {}
    for s in SYMS:
        b0, d0, f = load_base(s)
        if s in agg:
            b, d = extend_asset(s, b0, d0, agg[s][0], agg[s][1])
        else:
            b, d = b0, d0
        ext[s] = (b, d, f)
    panel = build_panel(ext)
    feats = [c for c in panel.columns if c not in ("t", "open", "sym", "bar", "y", "y18", "y42", "y84")]
    o_panel = panel.pivot_table(index="t", columns="sym", values="open").sort_index()[list(SYMS)]

    anchors_out = []
    oos_parts = []
    for anchor in ANCHORS:
        a = pd.Timestamp(anchor, tz="UTC")
        cutoff = a - pd.Timedelta(hours=4 * 102)
        val_start = cutoff - pd.Timedelta(days=730)
        tr = panel[(panel.t < cutoff) & panel.y.notna()]
        tr = tr[tr.t + pd.Timedelta(hours=4 * 43) < cutoff]
        val = tr[tr.t >= val_start].copy()
        itr = tr[tr.t + pd.Timedelta(hours=4 * 43) < val_start - pd.Timedelta(hours=4 * 102)].copy()
        te = panel[(panel.t >= a) & (panel.t < a + pd.Timedelta(days=365))].copy()
        print(f"A2 {anchor} cutoff={cutoff} n_train={len(tr)} n_inner={len(itr)} n_val={len(val)} n_test={len(te)}", flush=True)
        scored = []
        for md, msl in GRID:
            m = HistGradientBoostingRegressor(max_depth=md, min_samples_leaf=msl, learning_rate=0.03,
                                              max_iter=400, l2_regularization=1.0, random_state=0)
            m.fit(itr[feats], itr["y"])
            pv = m.predict(val[feats])
            sc = spearman(pv, val["y"].to_numpy(dtype=float))
            scored.append({"max_depth": md, "min_samples_leaf": msl, "val_spearman": round(float(sc), 4)})
            print(f"  depth={md} leaf={msl} val_ic={sc:.4f}", flush=True)
        best = max(scored, key=lambda d: (d["val_spearman"] if np.isfinite(d["val_spearman"]) else -np.inf))
        mf = HistGradientBoostingRegressor(max_depth=best["max_depth"], min_samples_leaf=best["min_samples_leaf"],
                                           learning_rate=0.03, max_iter=400, l2_regularization=1.0, random_state=0)
        mf.fit(tr[feats], tr["y"])
        te["pred"] = mf.predict(te[feats])
        ev = te.dropna(subset=["y"])
        ic = spearman(te["pred"].to_numpy(), te["y"].to_numpy()) if len(ev) > 2 else float("nan")
        anchors_out.append({"anchor": anchor, "cutoff": str(cutoff), "val_start": str(val_start),
                            "train_rows": int(len(tr)), "inner_rows": int(len(itr)), "val_rows": int(len(val)),
                            "n_pred_rows": int(len(te)), "n_pred_rows_with_y": int(len(ev)),
                            "grid_scores": scored, "best": best, "test_ic": round(float(ic), 4)})
        oos_parts.append(te)
        print(f"A2 {anchor} best={best} test_ic={ic:.4f}", flush=True)
    oos = pd.concat(oos_parts, ignore_index=True).sort_values(["t", "sym"]).reset_index(drop=True)

    # LO book from new OOS + vol target; blend with audited v114 v94 LS book
    oos94 = pd.read_csv(V114_LS_CSV, parse_dates=["t"])
    oos94["t"] = pd.to_datetime(oos94["t"], utc=True)
    oos94 = oos94.sort_values(["t", "sym"]).reset_index(drop=True)
    Wnew = weights_lo(oos)
    o_oos = o_panel.loc[Wnew.index].copy() if set(Wnew.index) <= set(o_panel.index) else None
    if o_oos is None or len(o_oos) != len(Wnew):
        # fallback: pivot OOS opens (test-year only spans full OOS)
        o_oos = oos.pivot_table(index="t", columns="sym", values="open").sort_index()[list(SYMS)]
        o_oos = o_oos.loc[Wnew.index]
    snew = vol_scale(o_oos, Wnew)
    W94 = weights_ls(oos94)
    o94 = oos94.pivot_table(index="t", columns="sym", values="open").sort_index()[list(SYMS)]
    s94 = vol_scale(o94, W94.reindex(o94.index).fillna(0.0))
    # align to common OOS index (both should be 10950 test-year bars)
    idx = Wnew.index.intersection(W94.index).sort_values()
    Wnew_a, snew_a = Wnew.reindex(idx).fillna(0.0), snew.reindex(idx).fillna(1.0)
    W94_a, s94_a = W94.reindex(idx).fillna(0.0), s94.reindex(idx).fillna(1.0)
    o_exec = o_oos.reindex(idx).sort_index()
    Wb = 0.5 * Wnew_a.mul(snew_a, axis=0) + 0.5 * W94_a.mul(s94_a, axis=0)

    def simulate(o, W, scale, fee, slip):
        r = (o.shift(-2) / o.shift(-1) - 1).fillna(0.0)
        Wk = W.mul(scale, axis=0) if not np.isscalar(scale) else W * scale
        turn = Wk.diff().abs().sum(axis=1).fillna(Wk.abs().sum(axis=1))
        funding = Wk.clip(lower=0).sum(axis=1) * 0.00005
        return (Wk * r).sum(axis=1) - turn * (fee + slip) - funding, turn

    def yearly(net, turn):
        out = []
        for anchor in ANCHORS:
            a = pd.Timestamp(anchor, tz="UTC")
            m = (net.index >= a) & (net.index < a + pd.Timedelta(days=365))
            st = stats(net[m], turn[m])
            st["anchor"] = anchor
            out.append(st)
        return out

    books_yearly = {}
    for bname, W, sc in (("v92_lo_new", Wnew_a, snew_a), ("v96_blend_new94", Wb, 1.0)):
        for scn, (fee, slip) in SCEN.items():
            if bname.startswith("v96"):
                r = (o_exec.shift(-2) / o_exec.shift(-1) - 1).fillna(0.0)
                turn = W.diff().abs().sum(axis=1).fillna(W.abs().sum(axis=1))
                funding = W.clip(lower=0).sum(axis=1) * 0.00005
                net = (W * r).sum(axis=1) - turn * (fee + slip) - funding
            else:
                net, turn = simulate(o_exec, W, sc, fee, slip)
            books_yearly[f"{bname}_{scn}"] = yearly(net, turn)
            print(bname, scn, [y["net_pct"] for y in books_yearly[f"{bname}_{scn}"]], flush=True)
    oos[["t", "sym", "open", "pred", "y"]].to_csv(OUT_DIR / "predictions_v119.csv", index=False)
    return {"anchors": anchors_out, "yearly": books_yearly, "features": feats,
            "oos_span": [str(idx[0]), str(idx[-1])], "n_oos": int(len(idx))}


def main():
    a1, a1meta, _ = part_a1()
    a2 = part_a2()
    out = {
        "version": "v118_v119_audit_replication",
        "v118_bands": a1,
        "v119": a2,
        "meta": {
            "anchors": list(ANCHORS),
            "a1": dict(a1meta, target=TARGET15, governed=False, bands=BANDS,
                       books_spec="books=0.25*b_lo(v114 LO*scale114)+0.25*b94(v114 LS*scale114)+0.5*b103(v103 LS*scale103); union t>=first v103 t; opens=v103 OOS",
                       wrapper_spec="s=min(0.15/vol,2) NaN->1 (realized=0.8*sum(books.shift(2)*ret1)+0.6*carry.shift(1), rolling-360/min-120*sqrt(2190)); live [2021-09-24,2026-09-23); targets w=0.8*s*books g=1; held per-asset band (|w-h|>band -> w else h), outside h=0 immediately; turnover=sum|new-held|; carry c=0.6*s unchanged; net=held*fwd-turn*(fee+slip)-0.00005*long+c*carry-|dc|*2*0.0004/1.2",
                       scenarios={k: {"fee": v[0], "slip": v[1]} for k, v in SCEN.items()}),
            "a2": {"cutoff_spec": "anchor-102*4h; train t<cutoff & y & t+43*4h<cutoff; val train & t>=cutoff-730d; inner train & t+43*4h<val_start-102*4h",
                   "grid": "max_depth (3,4,6) x min_samples_leaf (300,1000), lr 0.03, max_iter 400, l2 1.0, seed 0; Spearman on val; refit best on train",
                   "books": "LO=s(min(max(pred,0)/0.5,1),rib!=-1)/(vol42*sqrt(2190)) norm + daily ffill + 0.20-cap-2 vol; blend 0.5*Wnew*snew+0.5*W94(v114)*s94 scale1",
                   "panel": "v114 extended (Bitstamp>=2013-01-01+Coinbase BTC, Coinbase ETH, spot+USD-M base, UTC floor agg 4h>=3/1d>=20)"},
        },
    }
    with open(OUT_DIR / "replication.json", "w") as f:
        json.dump(out, f, indent=2)
    print(json.dumps({"a1_bands": list(a1.keys()), "a2_anchors": len(a2["anchors"])}, indent=2))


if __name__ == "__main__":
    main()
