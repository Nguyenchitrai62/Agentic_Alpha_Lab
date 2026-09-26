"""Blind v129+v130+v131 audit replication (Part A).
Does NOT read research/.../v129/*, v130/* nor v131/*.

Base (per OPENCODE_V129_V131_AUDIT.md):
  audited v126 (phase runs of the v115 portfolio) and v103_v105 replications.
  All three report the PHASE MEAN over rebalance phases 0..5 (v126 method).

Blind specs implemented:
A1 (v129): per panel (v114 panel with v92 features; v103 panel with v103
  features) fv = log(rolling-42 std of diff(log open)) shifted by -43 (std of
  returns t+2..t+43); HGB (v92 params) per anchor, cutoff = anchor - 102*4h,
  rows need t + 44*4h < cutoff and finite fv; pvol = exp(pred). Replace vol42
  by pvol (where available) in the OOS prediction frames of v92 LO / v94 LS
  (v114-panel pvol) and v103 LS (v103-panel pvol) before the weight formulas;
  own vol scales unchanged in form. Report Spearman(pvol, realized) and
  Spearman(vol42, realized) per anchor, phase mean with pvol and with vol42.
A2 (v130): per asset join USD-M perp 4h and spot 4h
  (data/raw/spot_majors_20260925/{SYM}_spot_4h.parquet) on open_time;
  share = log(max(spot qv,1)/max(perp qv,1));
  sp_share_z = (share - roll180 mean)/roll180 std;
  sp_share_chg = roll6 mean - roll42 mean;
  tbr = clip(taker_buy_qv/max(qv,1),0,1);
  tbr_gap6/42 = roll6/roll42 mean of (spot tbr - perp tbr);
  basis = 1e4*log(perp close/spot close); basis6 = roll6 mean;
  basis_chg = basis6 - roll42 mean; basis_z = (basis6 - roll180 mean)/roll180 std;
  left-join on (t, sym) to the v103 panel; retrain v103 with them;
  v115 portfolio phase mean.
A3 (v131): per book strength_t = mean over assets at t of max(pred,0)*(rib != -1)
  (v92 LO) or |pred| (v94, v103);
  k = clip(strength / (rolling-2160-row median shifted 1, min 360 rows), 0.5, 2),
  NaN -> 1, sampled on the phase's daily rows and ffilled;
  book = weights * own vol scale * k; v115 portfolio phase mean.

Blind choices documented in replication.json meta.
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
HGB = dict(max_depth=4, learning_rate=0.03, max_iter=400, min_samples_leaf=300,
           l2_regularization=1.0, random_state=0)
EMB_VOL = 102  # bars of 4h
HS_V103 = (6, 18)
EMB_V103 = 78
FLOW_FEATS = ["tbr_1", "tbr_6", "tbr_42", "flow_6", "flow_42", "tbr_z",
              "tsize_z", "ntr_z", "rng6", "clv6"]
NEW_SPOT_FEATS = ["sp_share_z", "sp_share_chg", "tbr_gap6", "tbr_gap42",
                  "basis6", "basis_chg", "basis_z"]

V114_LO_CSV = ROOT / "research/parallel/rounds/parallel-20260906-r2/v113_v114_audit/predictions_v114_v92.csv"
V114_LS_CSV = ROOT / "research/parallel/rounds/parallel-20260906-r2/v113_v114_audit/predictions_v114_v94.csv"
V103_CSV = ROOT / "research/parallel/rounds/parallel-20260906-r2/v103_v105_audit/predictions_v103.csv"
CARRY_FILE = ROOT / "artifacts/research/carry/carry_oos_fee0.0004.parquet"
BTC_DIR = ROOT / "data/raw/ma_ribbon_20260924"
XS_DIR = ROOT / "data/raw/xs_universe_20260924"
SPOT_DIR = ROOT / "data/raw/spot_majors_20260925"
SPOT17_DIR = SPOT_DIR  # prefix files live here too
CB_DIR = ROOT / "data/raw/coinbase_20260925"
BS_FILE = ROOT / "data/raw/bitstamp_20260925/btcusd_1h_2011_2015.parquet"


# ---------- shared weight/scale/engine (audited v126 formulas) ----------
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


def run_phases(Wlo_raw, W94_raw, W103_raw, o_lo, o_103, carry):
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


def run_phases_with_k(Wlo_raw, W94_raw, W103_raw, o_lo, o_103, carry, k_lo, k_94, k_103):
    """v131: book = phased weights * own vol scale * k (k sampled on phase daily rows, ffilled)."""
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
        # sample k on this phase's daily rows (pos%6==p on the full raw index) then ffill
        def sample_k(k_full, ref_index):
            # k_full indexed like W_raw (full 4h OOS index); keep phase rows, ffill to idx
            pos = pd.Series(np.arange(len(ref_index)) % PD == p, index=ref_index)
            ks = k_full.reindex(ref_index)
            ks = ks.where(pos, np.nan).ffill().fillna(1.0)
            return ks.reindex(idx).fillna(1.0)
        k_lo_p = sample_k(k_lo, Wlo_raw.index)
        k_94_p = sample_k(k_94, W94_raw.index)
        k_103_p = sample_k(k_103, W103_raw.index)
        b_lo = Wlo_p.reindex(idx).fillna(0.0).mul(s_lo.reindex(idx).fillna(1.0), axis=0).mul(k_lo_p, axis=0)
        b94 = W94_p.reindex(idx).fillna(0.0).mul(s94.reindex(idx).fillna(1.0), axis=0).mul(k_94_p, axis=0)
        b103 = W103_p.reindex(idx).fillna(0.0).mul(s103.reindex(idx).fillna(1.0), axis=0).mul(k_103_p, axis=0)
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


def spearman(a, b):
    m = pd.DataFrame({"a": a, "b": b}).dropna()
    if len(m) < 3:
        return float("nan")
    return float(spearmanr(m["a"], m["b"]).statistic)


# ---------- panels ----------
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
    if not (SPOT17_DIR / f"{sym}_spot_4h_2017.parquet").exists():
        s4, s1 = b.iloc[:0].copy(), d.iloc[:0].copy()
    else:
        s4 = pd.read_parquet(SPOT17_DIR / f"{sym}_spot_4h_2017.parquet")
        s1 = pd.read_parquet(SPOT17_DIR / f"{sym}_spot_1d_2017.parquet")
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


def features_base(b, d, f, with_flow):
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
    if with_flow:
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


def add_fv(panel_bars):
    """panel_bars: dict sym -> b (extended/base bars sorted). Returns dict sym -> Series fv/realized aligned to bars.

    fv[t] = log(rolling-42 std of diff(log open) shifted by -43), i.e. std of
    log-open returns t+2..t+43. Blind choice: diff = log(open).diff() on that
    asset's own bar order; rolling(42).std() (ddof=1, min_periods=42); shift(-43).
    """
    out = {}
    for s, b in panel_bars.items():
        lo = np.log(b["open"].astype(float))
        r = lo.diff()
        s42 = r.rolling(42).std(ddof=1)
        fv = np.log(s42.shift(-43))
        out[s] = (fv.to_numpy(), s42.shift(-43).to_numpy())
    return out


def build_v114_panel():
    cb_btc = load_hourly_coinbase("BTC-USD")
    cb_eth = load_hourly_coinbase("ETH-USD")
    bs_btc = load_hourly_btc_v114(cb_btc)
    agg = {"BTCUSDT": (aggregate(bs_btc, "4h"), aggregate(bs_btc, "1d")),
           "ETHUSDT": (aggregate(cb_eth, "4h"), aggregate(cb_eth, "1d"))}
    ext = {}
    bars = {}
    for s in SYMS:
        b0, d0, f = load_base(s)
        if s in agg:
            b, d = extend_asset(s, b0, d0, agg[s][0], agg[s][1])
        else:
            b, d = b0, d0
        ext[s] = (b, d, f)
        bars[s] = b
    rows = []
    for i, s in enumerate(SYMS):
        b, d, f = ext[s]
        x = features_base(b, d, f, with_flow=False)
        x["asset"] = i
        x["t"] = b["open_time"]
        x["open"] = b["open"].astype(float).to_numpy()
        x["sym"] = s
        x["bar"] = np.arange(len(b))
        rows.append(x)
    panel = pd.concat(rows, ignore_index=True)
    btc = panel[panel.sym == "BTCUSDT"].set_index("t")[["ret42", "ret180", "rib", "snr42"]].add_prefix("btc_")
    panel = panel.join(btc, on="t")
    fv_map = add_fv(bars)
    # map fv/realized onto panel rows per sym in bar order
    panel["fv"] = np.nan
    panel["realized_vol"] = np.nan
    for s in SYMS:
        m = panel["sym"] == s
        # bars[s] order == panel rows for s in bar order (both sorted by open_time)
        fv_arr, rv_arr = fv_map[s]
        # align by t
        tmp = pd.DataFrame({"t": bars[s]["open_time"].to_numpy(), "fv": fv_arr, "rv": rv_arr})
        tmp["t"] = pd.to_datetime(tmp["t"], utc=True)
        j = panel.loc[m, ["t"]].merge(tmp, on="t", how="left")
        panel.loc[m, "fv"] = j["fv"].to_numpy()
        panel.loc[m, "realized_vol"] = j["rv"].to_numpy()
    return panel, bars


def build_v103_panel():
    rows = []
    bars = {}
    for i, s in enumerate(SYMS):
        b, d, f = load_base(s)
        bars[s] = b
        x = features_base(b, d, f, with_flow=True)
        x["asset"] = i
        x["t"] = b["open_time"]
        x["open"] = b["open"].astype(float).to_numpy()
        x["sym"] = s
        x["bar"] = np.arange(len(b))
        rows.append(x)
    panel = pd.concat(rows, ignore_index=True)
    btc = panel[panel.sym == "BTCUSDT"].set_index("t")[["ret42", "ret180", "rib", "snr42"]].add_prefix("btc_")
    panel = panel.join(btc, on="t")
    fv_map = add_fv(bars)
    panel["fv"] = np.nan
    panel["realized_vol"] = np.nan
    for s in SYMS:
        m = panel["sym"] == s
        fv_arr, rv_arr = fv_map[s]
        tmp = pd.DataFrame({"t": bars[s]["open_time"].to_numpy(), "fv": fv_arr, "rv": rv_arr})
        tmp["t"] = pd.to_datetime(tmp["t"], utc=True)
        j = panel.loc[m, ["t"]].merge(tmp, on="t", how="left")
        panel.loc[m, "fv"] = j["fv"].to_numpy()
        panel.loc[m, "realized_vol"] = j["rv"].to_numpy()
    return panel, bars


def train_pvol(panel, feats):
    """HGB per anchor on fv; cutoff anchor-102*4h; rows t<cutoff, t+44*4h<cutoff, finite fv."""
    anchors = []
    parts = []
    for anchor in ANCHORS:
        a = pd.Timestamp(anchor, tz="UTC")
        end = a + pd.Timedelta(days=365)
        cutoff = a - pd.Timedelta(hours=4 * EMB_VOL)
        tr = panel[(panel.t < cutoff) & panel["fv"].notna()]
        tr = tr[tr.t + pd.Timedelta(hours=4 * 44) < cutoff]
        te = panel[(panel.t >= a) & (panel.t < end)].copy()
        m = HistGradientBoostingRegressor(**HGB)
        m.fit(tr[feats], tr["fv"])
        te["pred_fv"] = m.predict(te[feats])
        te["pvol"] = np.exp(te["pred_fv"])
        ev = te[te["realized_vol"].notna() & te["pvol"].notna()]
        rho_p = spearman(te["pvol"], te["realized_vol"])
        rho_v = spearman(te["vol42"], te["realized_vol"])
        anchors.append(dict(anchor=anchor, train_rows=int(len(tr)), n_pred_rows=int(len(te)),
                            n_eval_rows=int((te["realized_vol"].notna()).sum()),
                            spearman_pvol_realized=round(float(rho_p), 4) if np.isfinite(rho_p) else None,
                            spearman_vol42_realized=round(float(rho_v), 4) if np.isfinite(rho_v) else None))
        parts.append(te)
        print(f"pvol {anchor} tr={len(tr)} rho_p={anchors[-1]['spearman_pvol_realized']} rho_v={anchors[-1]['spearman_vol42_realized']}", flush=True)
    oos = pd.concat(parts, ignore_index=True).sort_values(["t", "sym"]).reset_index(drop=True)
    return oos, anchors


def part_a1_v129(panel114, panel103, feats114, feats103):
    oos114, a114 = train_pvol(panel114, feats114)
    oos103_pvol, a103 = train_pvol(panel103, feats103)
    # join pvol onto audited OOS frames
    o114_lo = pd.read_csv(V114_LO_CSV, parse_dates=["t"])
    o114_ls = pd.read_csv(V114_LS_CSV, parse_dates=["t"])
    o103_df = pd.read_csv(V103_CSV, parse_dates=["t"])
    for df in (o114_lo, o114_ls, o103_df):
        df["t"] = pd.to_datetime(df["t"], utc=True)
    j114 = oos114[["t", "sym", "pvol"]].copy()
    j114["t"] = pd.to_datetime(j114["t"], utc=True)
    j103 = oos103_pvol[["t", "sym", "pvol"]].copy()
    j103["t"] = pd.to_datetime(j103["t"], utc=True)
    def replace_vol(oos, j):
        m = oos.merge(j, on=["t", "sym"], how="left")
        n_have = int(m["pvol"].notna().sum())
        m["vol42"] = m["pvol"].where(m["pvol"].notna(), m["vol42"])
        return m.drop(columns=["pvol"]), n_have
    o114_lo_p, n_lo = replace_vol(o114_lo.sort_values(["t", "sym"]).reset_index(drop=True), j114)
    o114_ls_p, n_ls = replace_vol(o114_ls.sort_values(["t", "sym"]).reset_index(drop=True), j114)
    o103_p, n_103 = replace_vol(o103_df.sort_values(["t", "sym"]).reset_index(drop=True), j103)
    # weights
    Wlo_p = weights_lo_from_oos(o114_lo_p)
    W94_p = weights_ls_from_oos(o114_ls_p)
    W103_p = weights_ls_from_oos(o103_p)
    Wlo_b = weights_lo_from_oos(o114_lo.sort_values(["t", "sym"]).reset_index(drop=True))
    W94_b = weights_ls_from_oos(o114_ls.sort_values(["t", "sym"]).reset_index(drop=True))
    W103_b = weights_ls_from_oos(o103_df.sort_values(["t", "sym"]).reset_index(drop=True))
    o_v114 = o114_lo.pivot_table(index="t", columns="sym", values="open")[list(SYMS)].sort_index()
    o_v103 = o103_df.pivot_table(index="t", columns="sym", values="open")[list(SYMS)].sort_index()
    carry = pd.read_parquet(CARRY_FILE)
    carry.index = pd.to_datetime(carry.index, utc=True)
    phases_p, summary_p = run_phases(Wlo_p, W94_p, W103_p, o_v114, o_v103, carry)
    phases_b, summary_b = run_phases(Wlo_b, W94_b, W103_b, o_v114, o_v103, carry)
    print("v129 pvol normal mean", summary_p["normal"], flush=True)
    print("v129 base normal mean", summary_b["normal"], flush=True)
    return dict(anchors_v114=a114, anchors_v103=a103,
                n_replaced=dict(v114_lo=int(n_lo), v114_ls=int(n_ls), v103=int(n_103)),
                phases_with_pvol=phases_p, phase_summary_with_pvol=summary_p,
                phases_with_vol42=phases_b, phase_summary_with_vol42=summary_b,
                feats_v114=feats114, feats_v103=feats103)


def load_perp(sym):
    if sym == "BTCUSDT":
        b = pd.read_parquet(BTC_DIR / "klines_4h.parquet")
    else:
        b = pd.read_parquet(XS_DIR / f"{sym}_4h.parquet")
    b["open_time"] = pd.to_datetime(b["open_time"], utc=True)
    return b.sort_values("open_time").reset_index(drop=True)


def load_spot(sym):
    f = SPOT_DIR / f"{sym}_spot_4h.parquet"
    s = pd.read_parquet(f)
    s["open_time"] = pd.to_datetime(s["open_time"], utc=True)
    return s.sort_values("open_time").reset_index(drop=True)


def spot_features_per_asset(sym):
    perp = load_perp(sym)
    spot = load_spot(sym)
    j = perp.merge(spot, on="open_time", how="inner", suffixes=("", "_spot"))
    j = j.sort_values("open_time").reset_index(drop=True)
    perp_qv = j["quote_volume"].astype(float).clip(lower=1)
    spot_qv = j["quote_volume_spot"].astype(float).clip(lower=1)
    share = np.log(spot_qv.clip(lower=1) / perp_qv.clip(lower=1))
    sp_share_z = (share - share.rolling(180).mean()) / share.rolling(180).std()
    sp_share_chg = share.rolling(6).mean() - share.rolling(42).mean()
    tbr_perp = (j["taker_buy_quote_volume"].astype(float) / perp_qv).clip(lower=0, upper=1)
    tbr_spot = (j["taker_buy_quote_volume_spot"].astype(float) / spot_qv).clip(lower=0, upper=1)
    gap = tbr_spot - tbr_perp
    tbr_gap6 = gap.rolling(6).mean()
    tbr_gap42 = gap.rolling(42).mean()
    basis = 1e4 * np.log(j["close"].astype(float) / j["close_spot"].astype(float))
    basis6 = basis.rolling(6).mean()
    basis_chg = basis6 - basis.rolling(42).mean()
    basis_z = (basis6 - basis6.rolling(180).mean()) / basis6.rolling(180).std()
    out = pd.DataFrame({"t": j["open_time"], "sym": sym,
                        "sp_share_z": sp_share_z.to_numpy(), "sp_share_chg": sp_share_chg.to_numpy(),
                        "tbr_gap6": tbr_gap6.to_numpy(), "tbr_gap42": tbr_gap42.to_numpy(),
                        "basis6": basis6.to_numpy(), "basis_chg": basis_chg.to_numpy(),
                        "basis_z": basis_z.to_numpy()})
    return out


def train_predict_v103(panel, anchor, feats):
    a = pd.Timestamp(anchor, tz="UTC")
    end = a + pd.Timedelta(days=365)
    cutoff = a - pd.Timedelta(hours=4 * EMB_V103)
    te = panel[(panel.t >= a) & (panel.t < end)].copy()
    preds = np.zeros((len(te), len(HS_V103)))
    ntrs = []
    for j, h in enumerate(HS_V103):
        yh = f"y{h}"
        tr = panel[(panel.t < cutoff) & panel[yh].notna()]
        tr = tr[tr.t + pd.Timedelta(hours=4 * (h + 1)) < cutoff]
        ntrs.append(int(len(tr)))
        m = HistGradientBoostingRegressor(**HGB)
        m.fit(tr[feats], tr[yh])
        preds[:, j] = m.predict(te[feats])
    te["pred"] = preds.mean(axis=1)
    for j, h in enumerate(HS_V103):
        te[f"pred_h{h}"] = preds[:, j]
    return te, ntrs


def part_a2_v130(panel103, feats103_base):
    feats_new = []
    for s in SYMS:
        feats_new.append(spot_features_per_asset(s))
    newf = pd.concat(feats_new, ignore_index=True)
    newf["t"] = pd.to_datetime(newf["t"], utc=True)
    panel = panel103.merge(newf, on=["t", "sym"], how="left")
    feats = feats103_base + NEW_SPOT_FEATS
    anchors = []
    parts = []
    for anchor in ANCHORS:
        te, ntrs = train_predict_v103(panel, anchor, feats)
        ic6 = spearman(te["pred"], te["y6"])
        ic18 = spearman(te["pred"], te["y18"])
        ic42 = spearman(te["pred"], te["y42"]) if "y42" in te.columns else float("nan")
        anchors.append(dict(anchor=anchor, train_rows_h6=ntrs[0], train_rows_h18=ntrs[1],
                            n_pred_rows=int(len(te)), ic_vs_y6=round(float(ic6), 4) if np.isfinite(ic6) else None,
                            ic_vs_y18=round(float(ic18), 4) if np.isfinite(ic18) else None,
                            ic_vs_y42=round(float(ic42), 4) if np.isfinite(ic42) else None))
        parts.append(te)
        print("v130", anchor, ntrs, anchors[-1]["ic_vs_y6"], anchors[-1]["ic_vs_y18"], flush=True)
    oos103 = pd.concat(parts, ignore_index=True).sort_values(["t", "sym"]).reset_index(drop=True)
    W103_new = weights_ls_from_oos(oos103)
    o114_lo = pd.read_csv(V114_LO_CSV, parse_dates=["t"])
    o114_ls = pd.read_csv(V114_LS_CSV, parse_dates=["t"])
    for df in (o114_lo, o114_ls):
        df["t"] = pd.to_datetime(df["t"], utc=True)
    Wlo = weights_lo_from_oos(o114_lo.sort_values(["t", "sym"]).reset_index(drop=True))
    W94 = weights_ls_from_oos(o114_ls.sort_values(["t", "sym"]).reset_index(drop=True))
    o_v114 = o114_lo.pivot_table(index="t", columns="sym", values="open")[list(SYMS)].sort_index()
    o_v103_new = oos103.pivot_table(index="t", columns="sym", values="open")[list(SYMS)].sort_index()
    o_v103_old = pd.read_csv(V103_CSV, parse_dates=["t"])
    o_v103_old["t"] = pd.to_datetime(o_v103_old["t"], utc=True)
    o_v103_old = o_v103_old.pivot_table(index="t", columns="sym", values="open")[list(SYMS)].sort_index()
    # engine opens: use retrained panel opens (should match audited span)
    o_eng = o_v103_new
    carry = pd.read_parquet(CARRY_FILE)
    carry.index = pd.to_datetime(carry.index, utc=True)
    phases, summary = run_phases(Wlo, W94, W103_new, o_v114, o_eng, carry)
    print("v130 new normal mean", summary["normal"], flush=True)
    return dict(anchors=anchors, features=feats, n_new_rows=int(newf.dropna().shape[0]),
                new_feature_coverage={c: int(panel[c].notna().sum()) for c in NEW_SPOT_FEATS},
                phases=phases, phase_summary=summary)


def strength_k(oos, mode):
    """mode 'lo' -> mean(max(pred,0)*(rib!=-1)); 'ls' -> mean(|pred|). Returns strength Series indexed by t."""
    df = oos.copy()
    if mode == "lo":
        df["v"] = df["pred"].clip(lower=0).where(df["rib"] != -1, 0.0)
    else:
        df["v"] = df["pred"].abs()
    st = df.groupby("t")["v"].mean().sort_index()
    st.index = pd.to_datetime(st.index, utc=True)
    med = st.rolling(2160, min_periods=360).median().shift(1)
    k = (st / med).clip(lower=0.5, upper=2.0).fillna(1.0)
    k = k.replace([np.inf, -np.inf], 1.0).fillna(1.0)
    return st, k


def part_a3_v131():
    o114_lo = pd.read_csv(V114_LO_CSV, parse_dates=["t"])
    o114_ls = pd.read_csv(V114_LS_CSV, parse_dates=["t"])
    o103_df = pd.read_csv(V103_CSV, parse_dates=["t"])
    for df in (o114_lo, o114_ls, o103_df):
        df["t"] = pd.to_datetime(df["t"], utc=True)
    o114_lo = o114_lo.sort_values(["t", "sym"]).reset_index(drop=True)
    o114_ls = o114_ls.sort_values(["t", "sym"]).reset_index(drop=True)
    o103_df = o103_df.sort_values(["t", "sym"]).reset_index(drop=True)
    Wlo_raw = weights_lo_from_oos(o114_lo)
    W94_raw = weights_ls_from_oos(o114_ls)
    W103_raw = weights_ls_from_oos(o103_df)
    st_lo, k_lo = strength_k(o114_lo, "lo")
    st_94, k_94 = strength_k(o114_ls, "ls")
    st_103, k_103 = strength_k(o103_df, "ls")
    o_v114 = o114_lo.pivot_table(index="t", columns="sym", values="open")[list(SYMS)].sort_index()
    o_v103 = o103_df.pivot_table(index="t", columns="sym", values="open")[list(SYMS)].sort_index()
    carry = pd.read_parquet(CARRY_FILE)
    carry.index = pd.to_datetime(carry.index, utc=True)
    phases, summary = run_phases_with_k(Wlo_raw, W94_raw, W103_raw, o_v114, o_v103, carry, k_lo, k_94, k_103)
    phases_b, summary_b = run_phases(Wlo_raw, W94_raw, W103_raw, o_v114, o_v103, carry)
    print("v131 k normal mean", summary["normal"], flush=True)
    def kstat(k):
        return dict(mean=round(float(k.mean()), 4), frac_capped_lo=float((k <= 0.5001).mean()),
                    frac_capped_hi=float((k >= 1.9999).mean()), n=int(len(k)))
    return dict(phases=phases, phase_summary=summary,
                phases_without_k=phases_b, phase_summary_without_k=summary_b,
                k_stats=dict(lo=kstat(k_lo), ls94=kstat(k_94), ls103=kstat(k_103)))


def main():
    panel114, _bars114 = build_v114_panel()
    feats114 = [c for c in panel114.columns if c not in ("t", "open", "sym", "bar", "y", "y6", "y18", "y42", "y84",
                                                         "fv", "realized_vol", "pred_fv", "pvol")]
    panel103, _bars103 = build_v103_panel()
    feats103_base = [c for c in panel103.columns if c not in ("t", "open", "sym", "bar", "y6", "y18", "y42",
                                                              "fv", "realized_vol", "pred", "pred_fv", "pvol",
                                                              "pred_h6", "pred_h18")]
    assert len(feats114) == 26, len(feats114)
    assert len(feats103_base) == 36, len(feats103_base)
    v129 = part_a1_v129(panel114, panel103, feats114, feats103_base)
    v130 = part_a2_v130(panel103, feats103_base)
    v131 = part_a3_v131()
    out = {
        "version": "v129_v131_audit_replication",
        "anchors": list(ANCHORS),
        "scenarios": {k: {"fee": v[0], "slip": v[1]} for k, v in SCEN.items()},
        "v129": v129,
        "v130": v130,
        "v131": v131,
        "meta": {
            "v129_spec": "per panel (v114 with v92 feats; v103 with v103 feats) fv=log(rolling-42 std of diff(log open)) shifted by -43 (std t+2..t+43); HGB v92 params per anchor cutoff=anchor-102*4h rows t+44*4h<cutoff & finite fv; pvol=exp(pred); vol42 replaced by pvol where available in v92LO/v94LS/v103LS OOS frames before un-subsampled LO/LS formulas; own 0.20-cap-2 scales unchanged; v115 portfolio (0.25/0.25/0.5, target 0.15 sequential ungoverned) phase mean 0..5",
            "v129_choices": "diff=log(open).diff() per asset bar order; rolling(42).std(ddof=1,min42).shift(-43); realized=shifted std; feats exclude y*/fv/realized/pvol; vol replacement via left-join (t,sym); opens/engine/carry identical to v126 (v103 opens)",
            "v130_spec": "per asset inner-join perp 4h (ma_ribbon BTC else xs_universe) + spot 4h (spot_majors_20260925/{SYM}_spot_4h.parquet) on open_time; share=log(max(spotqv,1)/max(perpqv,1)); sp_share_z=(share-roll180mean)/roll180std; sp_share_chg=roll6-roll42; tbr=clip(tbqv/max(qv,1),0,1); tbr_gap6/42=roll6/42 of (spot-perp); basis=1e4*log(perpclose/spotclose); basis6=roll6; basis_chg=basis6-roll42; basis_z=(basis6-roll180mean)/roll180std; left-join (t,sym) to v103 panel; retrain v103 (HGB h6/h18 embargo78 pred=mean) with 36+7 feats; v115 phase mean",
            "v130_choices": "rolling default min_periods=window ddof=1; inner join for feature computation then left-join to panel (NaN where spot missing); added feats exactly sp_share_z,sp_share_chg,tbr_gap6,tbr_gap42,basis6,basis_chg,basis_z (share/basis raw are intermediates, not added); v114 books unchanged from audited CSVs; engine opens from retrained OOS",
            "v131_spec": "per book strength_t=mean over assets of max(pred,0)*(rib!=-1) (v92LO) or |pred| (v94,v103); k=clip(strength/(rolling-2160 median shifted1 min360),0.5,2) NaN->1, sampled on phase daily rows ffilled; book=weights*own scale*k; v115 phase mean",
            "v131_choices": "strength on audited OOS CSV preds/ribs grouped by t; median rolling(2160,min360).median().shift(1); k clip NaN/inf->1; per phase sample k on rows pos%6==p (of that book raw index) ffill to idx; own scales on phased weights without k then *k; books 0.25/0.25/0.5 s0.15 sequential ungoverned",
            "model": HGB,
            "data": {"v114_panel": "Bitstamp>=2013-01-01+Coinbase BTC, Coinbase ETH, spot_2017 prefix, UTC floor agg 4h>=3/1d>=20",
                     "v103_panel": "spot_2017 prefix + USD-M, v92+flow feats",
                     "spot_join": "spot_majors_20260925/{SYM}_spot_4h.parquet (inner on open_time per asset)",
                     "carry": "artifacts/research/carry/carry_oos_fee0.0004.parquet",
                     "oos_base": "v113_v114_audit/predictions_v114_v92.csv + predictions_v114_v94.csv + v103_v105_audit/predictions_v103.csv"},
        },
    }
    with open(OUT_DIR / "replication.json", "w") as f:
        json.dump(out, f, indent=2)
    print(json.dumps({"v129_pvol_mean": v129["phase_summary_with_pvol"]["normal"],
                      "v129_base_mean": v129["phase_summary_with_vol42"]["normal"],
                      "v130_mean": v130["phase_summary"]["normal"],
                      "v131_mean": v131["phase_summary"]["normal"]}, indent=2))


if __name__ == "__main__":
    main()
