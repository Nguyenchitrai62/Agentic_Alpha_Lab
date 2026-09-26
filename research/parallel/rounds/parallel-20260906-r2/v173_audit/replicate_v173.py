"""v173 blind audit Part A replication.

Blind rule: does NOT read research/.../v173/* nor v173_result.json until
replication.json is saved. Independent implementation from
OPENCODE_V173_AUDIT.md only (plus engine_real for v154_books/context/
constants and v144/v135/v110/v92 for the W=60 execution books, like the
v172 audit which is the stated base: crash-aware sleeve costs, 60-minute
execution books on engine_real).

Spec (frozen before running):
  Decision grid t = 4h bars from 2020-02-01 00:00 UTC to last books bar;
  holding bar T = t + 4h. 1m OHLCV + taker_buy_volume (BTC:
  btc_intraday klines_1m, others: majors_intraday <SYM>_1m; prices
  forward-filled inside a bar only, missing volume = 0).
  sigma(t) = std of 4h open-to-open pct changes over 360 bars ending at t
  (min_periods 120). Candidate points: for c in (2, 3, 4) the first minute
  m in 16..238 with close(m)/open(T) - 1 <= -c*sigma.
  y = open(T+4h)*(1-s_out)/(open(m+1)*(1+s_in)) - 1 - 0.001 - funding(T+4h),
  s = max(0.0002, 0.25*(high-low)/open) of minute m+1 (in) and of minute 0
  of T+4h (out).
  Features: depth=(close(m)/open(T)-1)/sigma; c; m/240;
  r5=(close(m)/close(m-5)-1)/sigma; r15 likewise with m-15;
  vspike=volume(m-4..m)/(5*mean volume(0..m-6));
  taker15=taker_buy(m-14..m)/volume(m-14..m);
  rng=(high(m)-low(m))/close(m)/sigma;
  breadth=#OTHER assets with depth<=-2 at minute m; btc_depth;
  trend=open(T)/mean(last 42 4h opens incl open(T))-1;
  r1d=(open(T)/open(T-24h)-1)/sigma;
  funding=last non-zero settled rate at or before t;
  asset one-hot (column order BNB, BTC, ETH, SOL, XRP).
  Per anchor: HistGradientBoostingRegressor(max_depth=3, learning_rate=0.03,
  max_iter=300, min_samples_leaf=50, l2_regularization=1.0, random_state=0)
  fit on points with T+4h < anchor-1day and T >= 2020-03-02; test points with
  t in [anchor, anchor+365d); per (t, asset) take earliest point with
  pred > 0; sleeve per bar = 0.25*sum of taken y.
  Report IC (Spearman pred vs y on test points), taken count, sleeve net/DD
  per anchor, and combined engine_real row (books + g*sleeve).
  Books: engine_real (all realism), execution W=60 (v170/v172 arrays),
  target 0.25, governor; net[i] += g[i]*sleeve[i] on live bars.

Frozen blind assumptions (documented before running):
  A1 Grid pd.date_range(2020-02-01 00:00 UTC, last books bar, freq 4h);
     T=grid+4h, T2=grid+8h. Anchors=v92.ANCHORS (2021-09-24..2025-09-24).
  A2 sigma finite and >0 else no candidate point for that (t, asset).
  A3 1m: drop duplicate open_time keep last, sort, reindex to full minute
     grid; prices (O/H/L/C) within-bar forward-fill only (leading NaNs stay
     NaN); volume/taker_buy_volume missing (=NaN) -> 0.0, no ffill.
  A4 Trigger close and depth/breadth closes use ffilled close grid; entry
     open/high/low use ffilled O/H/L grids at minute m+1.
  A5 s_in from entry minute (m+1) ffilled H/L/O: max(0.0002, 0.25*(H-L)/O);
     if H/L/O non-finite, O<=0 or H<L -> 0.0002. Entry=O(m+1)*(1+s_in).
  A6 Exit base = 1m open at cube row i+1 minute 0 (minute starting at T+4h)
     if finite and >0 else 4h open(T+4h) fallback; s_out likewise from that
     minute's H/L/O else 0.0002. Exit=base*(1-s_out). Row i+1>=n -> no point
     (y undefined). Both missing/nonpositive -> no point.
  A7 No point whenever: 4h open(T) missing/nonpositive, trigger needs finite
     dip, entry open missing/nonpositive, or no trigger minute. Funding cost
     missing -> 0.0 (bucket sum reindexed, fillna 0).
  A8 r5/r15 need finite closes, close(lag)>0, finite sigma>0 else 0.0.
  A9 vspike: numerator=sum volume(m-4..m) (zero-filled); denominator=
     5*mean(volume(0..m-6)); if den<=0/nonfinite or num nonfinite -> 1.0.
  A10 taker15: sum taker_buy(m-14..m)/sum volume(m-14..m); if den<=0 or
     nonfinite -> 0.5; else clip to [0,1].
  A11 rng: needs finite H/L/close, close>0, H>=L, finite sigma>0 else 0.0.
  A12 breadth: per OTHER asset depth_o=(close_o(m)/open_o(T)-1)/sigma_o;
     counted iff finite and <=-2 (missing -> not counted). btc_depth same
     formula for BTC, missing/nonfinite -> 0.0.
  A13 trend: mean of last 42 4h opens incl open(T) via rolling(42,
     min_periods=42); if NaN/nonpositive mean or open(T) missing -> 0.0.
  A14 r1d: open(T-24h)=4h open at T-24h; missing/nonpositive or bad sigma
     -> 0.0.
  A15 funding feature: per asset, last fundingRate != 0 with fundingTime <= t
     (ffill, zeros treated as missing); none -> 0.0.
  A16 Asset encoding: 5 one-hot columns in order BNB, BTC, ETH, SOL, XRP.
  A17 Train mask: (T2 < anchor-1day) & (T >= 2020-03-02); test mask:
     t in [anchor, anchor+365d). Takes: per (i, asset) test points sorted by
     (m, c), first with pred>0. Sleeve[i]=0.25*sum taken y (0 if none).
  A18 IC=Spearman(pred, y) on test points via pandas corr; <3 points or NaN
     -> null. Sleeve per-anchor net/DD from sleeve-only equity in applied
     window. Combined loop mirrors engine_real.run FULL with W=60 exec and
     net[i]+=g[i]*sleeve_books[i] on live bars; governor (20%, 2-bar lag) on
     combined equity.
"""

from __future__ import annotations

import glob
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parents[4]
ROUND2 = ROOT / "research" / "parallel" / "rounds" / "parallel-20260906-r2"
OUT = HERE / "replication.json"

SYMS = ["BNBUSDT", "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]
SHORT = ["BNB", "BTC", "ETH", "SOL", "XRP"]
CS = (2, 3, 4)
GRID_START = pd.Timestamp("2020-02-01 00:00:00+00:00")
TRAIN_T_MIN = pd.Timestamp("2020-03-02 00:00:00+00:00")
TARGET = 0.25
W_EXEC = 60
D = 0.001
FEATURE_COLS = ["depth", "c", "m_norm", "r5", "r15", "vspike", "taker15",
                "rng", "breadth", "btc_depth", "trend", "r1d", "funding",
                "asset_BNB", "asset_BTC", "asset_ETH", "asset_SOL",
                "asset_XRP"]


def _load_engine_real():
    spec = importlib.util.spec_from_file_location(
        "v173_audit_engine_real", ROUND2 / "engine_real" / "engine_real.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _ffill_rows(a: np.ndarray) -> np.ndarray:
    out = a.copy()
    for i in range(out.shape[0]):
        last = np.nan
        row = out[i]
        for k in range(row.shape[0]):
            if np.isnan(row[k]):
                row[k] = last
            else:
                last = row[k]
    return out


def _bar_stats_W(m_1m: pd.DataFrame, W: int) -> pd.DataFrame:
    T = m_1m["open_time"].dt.floor("4h")
    off = ((m_1m["open_time"] - T).dt.total_seconds() // 60).astype(int)
    p0 = m_1m[off == 0].set_index(T[off == 0])["open"]
    wmask = (off >= 2) & (off <= W - 1)
    lo = m_1m[wmask].groupby(T[wmask])["low"].min()
    hi = m_1m[wmask].groupby(T[wmask])["high"].max()
    pW = m_1m[off == W].set_index(T[off == W])["open"]
    return pd.DataFrame({"p0": p0, "lo": lo, "hi": hi, "pW": pW})


def main():
    from sklearn.ensemble import HistGradientBoostingRegressor

    er = _load_engine_real()
    v110 = er.v144.v110
    v92 = er.v144.v110.v92
    v135 = er.v144.v135
    ANCHORS = list(v92.ANCHORS)
    START, END = v110.START, v110.END
    print("anchors", ANCHORS, "live", START, "->", END, flush=True)

    books, opens_full = er.v154_books()
    books = books.sort_index()
    opens_full = opens_full.sort_index()
    last_books = books.index.max()
    grid = pd.date_range(GRID_START, last_books, freq="4h", tz="UTC")
    n = len(grid)
    T_all = grid + pd.Timedelta(hours=4)
    T2_all = grid + pd.Timedelta(hours=8)
    print(f"grid {n} bars {grid.min()} -> {grid.max()}", flush=True)

    # ---- 4h per-asset arrays ----
    openT = np.zeros((n, len(SYMS)))
    exitOpen4h = np.zeros((n, len(SYMS)))
    fundT2 = np.zeros((n, len(SYMS)))
    sigma = np.zeros((n, len(SYMS)))
    trend_base = np.zeros((n, len(SYMS)))
    open_m24 = np.zeros((n, len(SYMS)))
    fund_feat = np.zeros((n, len(SYMS)))
    for j, sym in enumerate(SYMS):
        k = pd.read_parquet(ROOT / "data/raw/xs_universe_20260924" / f"{sym}_4h.parquet")
        ot = pd.to_datetime(k["open_time"], utc=True)
        o = pd.Series(k["open"].to_numpy(dtype=float), index=ot).sort_index()
        o = o[~o.index.duplicated(keep="last")]
        ret = o / o.shift(1) - 1
        sig = ret.rolling(360, min_periods=120).std()
        sigma[:, j] = sig.reindex(grid).to_numpy(dtype=float)
        openT[:, j] = o.reindex(T_all).to_numpy(dtype=float)
        exitOpen4h[:, j] = o.reindex(T2_all).to_numpy(dtype=float)
        trend_base[:, j] = o.rolling(42, min_periods=42).mean().reindex(T_all).to_numpy(dtype=float)
        open_m24[:, j] = o.reindex(T_all - pd.Timedelta(hours=24)).to_numpy(dtype=float)
        f = pd.read_parquet(ROOT / "data/raw/xs_universe_20260924" / f"{sym}_funding.parquet")
        ft = pd.to_datetime(f["fundingTime"], utc=True)
        fr = f["fundingRate"].to_numpy(dtype=float)
        fser = pd.Series(fr, index=ft).sort_index()
        fser = fser[~fser.index.duplicated(keep="last")]
        fser_nz = fser.mask(fser == 0.0).ffill()
        fund_feat[:, j] = fser_nz.reindex(grid, method="ffill").fillna(0.0).to_numpy(dtype=float)
        fbucket = fser.groupby(ft.dt.floor("4h")).sum()
        fundT2[:, j] = fbucket.reindex(T2_all).fillna(0.0).to_numpy(dtype=float)
        print(f"{sym}: sigma_finite={int(np.isfinite(sigma[:, j]).sum())}/{n}", flush=True)

    # ---- 1m close cube (all assets) for triggers/depth/breadth ----
    n_min = n * 240
    mgrid = pd.date_range(T_all.min(), T_all.min() + pd.Timedelta(minutes=n_min - 1),
                          freq="1min", tz="UTC")
    assert len(mgrid) == n_min
    close_g = np.zeros((n, 240, len(SYMS)))
    for j, sym in enumerate(SYMS):
        if sym == "BTCUSDT":
            files = sorted(glob.glob(str(ROOT / "data/raw/btc_intraday_20260924/klines_1m_20*.parquet")))
        else:
            files = sorted(glob.glob(str(ROOT / f"data/raw/majors_intraday_20260924/{sym}_1m_20*.parquet")))
        assert files, f"no 1m files for {sym}"
        parts = [pd.read_parquet(f, columns=["open_time", "close"]) for f in files]
        d = pd.concat(parts, ignore_index=True)
        d["open_time"] = pd.to_datetime(d["open_time"], utc=True)
        d = d.sort_values("open_time").drop_duplicates("open_time", keep="last").set_index("open_time")
        co = d["close"].astype(float).reindex(mgrid).to_numpy(dtype=float).reshape(n, 240)
        close_g[:, :, j] = _ffill_rows(co)
        print(f"{sym}: close cube done", flush=True)

    MO = np.arange(16, 239)
    btc_j = SYMS.index("BTCUSDT")

    # ---- per-asset points ----
    rec_i, rec_j, rec_c, rec_m, rec_y = [], [], [], [], []
    F = {c: [] for c in FEATURE_COLS}
    for j, sym in enumerate(SYMS):
        if sym == "BTCUSDT":
            files = sorted(glob.glob(str(ROOT / "data/raw/btc_intraday_20260924/klines_1m_20*.parquet")))
        else:
            files = sorted(glob.glob(str(ROOT / f"data/raw/majors_intraday_20260924/{sym}_1m_20*.parquet")))
        parts = [pd.read_parquet(f, columns=["open_time", "open", "high", "low", "close",
                                             "volume", "taker_buy_volume"]) for f in files]
        d = pd.concat(parts, ignore_index=True)
        d["open_time"] = pd.to_datetime(d["open_time"], utc=True)
        d = d.sort_values("open_time").drop_duplicates("open_time", keep="last").set_index("open_time")
        op = d["open"].astype(float).reindex(mgrid).to_numpy(dtype=float).reshape(n, 240)
        hi = d["high"].astype(float).reindex(mgrid).to_numpy(dtype=float).reshape(n, 240)
        lo = d["low"].astype(float).reindex(mgrid).to_numpy(dtype=float).reshape(n, 240)
        cl = d["close"].astype(float).reindex(mgrid).to_numpy(dtype=float).reshape(n, 240)
        vo = d["volume"].astype(float).reindex(mgrid).to_numpy(dtype=float).reshape(n, 240)
        tb = d["taker_buy_volume"].astype(float).reindex(mgrid).to_numpy(dtype=float).reshape(n, 240)
        op = _ffill_rows(op)
        hi = _ffill_rows(hi)
        lo = _ffill_rows(lo)
        cl = _ffill_rows(cl)
        vo = np.where(np.isfinite(vo), vo, 0.0)
        tb = np.where(np.isfinite(tb), tb, 0.0)
        sig = sigma[:, j]
        oT = openT[:, j]
        e4 = exitOpen4h[:, j]
        fu = fundT2[:, j]
        base_ok = np.isfinite(sig) & (sig > 0) & np.isfinite(oT) & (oT > 0)
        n_pts_sym = 0
        for c in CS:
            with np.errstate(invalid="ignore", divide="ignore"):
                dip = cl[:, MO] / oT[:, None] - 1
                thr = (-c * sig)[:, None]
                mask = base_ok[:, None] & np.isfinite(dip) & (dip <= thr)
            has = mask.any(axis=1)
            first = mask.argmax(axis=1)
            m_abs = MO[first]
            idx_all = np.arange(n)
            ok_row = has & (idx_all + 1 < n)
            # entry/exit/costs per row with trigger
            for i in np.flatnonzero(ok_row):
                m = int(m_abs[i])
                m1 = m + 1
                e_o = op[i, m1]
                e_h = hi[i, m1]
                e_l = lo[i, m1]
                if not (np.isfinite(e_o) and e_o > 0):
                    continue
                if np.isfinite(e_h) and np.isfinite(e_l) and e_o > 0 and e_h >= e_l:
                    with np.errstate(invalid="ignore", divide="ignore"):
                        s_in = max(0.0002, 0.25 * (e_h - e_l) / e_o)
                else:
                    s_in = 0.0002
                if not np.isfinite(s_in) or s_in < 0:
                    s_in = 0.0002
                x_o1m = op[i + 1, 0]
                x_h = hi[i + 1, 0]
                x_l = lo[i + 1, 0]
                if np.isfinite(x_o1m) and x_o1m > 0:
                    x_base = x_o1m
                    if (np.isfinite(x_h) and np.isfinite(x_l) and x_o1m > 0
                            and x_h >= x_l):
                        with np.errstate(invalid="ignore", divide="ignore"):
                            s_out = max(0.0002, 0.25 * (x_h - x_l) / x_o1m)
                    else:
                        s_out = 0.0002
                else:
                    x_base = e4[i]
                    s_out = 0.0002
                if not (np.isfinite(x_base) and x_base > 0):
                    continue
                if not np.isfinite(s_out) or s_out < 0:
                    s_out = 0.0002
                with np.errstate(invalid="ignore", divide="ignore"):
                    y = (x_base * (1 - s_out)) / (e_o * (1 + s_in)) - 1 - 0.001 - fu[i]
                if not np.isfinite(y):
                    continue
                # ---- features (all at or before minute m) ----
                c_close = cl[i, m]
                if not (np.isfinite(c_close) and np.isfinite(oT[i]) and oT[i] > 0
                        and np.isfinite(sig[i]) and sig[i] > 0):
                    continue
                depth = (c_close / oT[i] - 1) / sig[i]
                if not np.isfinite(depth):
                    continue
                c5 = cl[i, m - 5]
                if (np.isfinite(c5) and c5 > 0 and np.isfinite(c_close)
                        and np.isfinite(sig[i]) and sig[i] > 0):
                    r5 = (c_close / c5 - 1) / sig[i]
                else:
                    r5 = 0.0
                c15 = cl[i, m - 15]
                if (np.isfinite(c15) and c15 > 0 and np.isfinite(c_close)
                        and np.isfinite(sig[i]) and sig[i] > 0):
                    r15 = (c_close / c15 - 1) / sig[i]
                else:
                    r15 = 0.0
                if not np.isfinite(r5):
                    r5 = 0.0
                if not np.isfinite(r15):
                    r15 = 0.0
                v_num = float(vo[i, m - 4:m + 1].sum())
                v_den_win = vo[i, 0:m - 5]
                v_den = 5 * float(v_den_win.mean()) if (m - 5) > 0 else np.nan
                if (np.isfinite(v_num) and np.isfinite(v_den) and v_den > 0):
                    vspike = v_num / v_den
                else:
                    vspike = 1.0
                if not np.isfinite(vspike):
                    vspike = 1.0
                tb_num = float(tb[i, m - 14:m + 1].sum())
                v15 = float(vo[i, m - 14:m + 1].sum())
                if np.isfinite(tb_num) and np.isfinite(v15) and v15 > 0:
                    taker15 = float(np.clip(tb_num / v15, 0.0, 1.0))
                else:
                    taker15 = 0.5
                h_m = hi[i, m]
                l_m = lo[i, m]
                if (np.isfinite(h_m) and np.isfinite(l_m) and np.isfinite(c_close)
                        and c_close > 0 and h_m >= l_m and np.isfinite(sig[i])
                        and sig[i] > 0):
                    rng = (h_m - l_m) / c_close / sig[i]
                else:
                    rng = 0.0
                if not np.isfinite(rng):
                    rng = 0.0
                # breadth over OTHER assets at same minute m
                br = 0
                for oj in range(len(SYMS)):
                    if oj == j:
                        continue
                    co_o = close_g[i, m, oj]
                    oT_o = openT[i, oj]
                    s_o = sigma[i, oj]
                    if (np.isfinite(co_o) and np.isfinite(oT_o) and oT_o > 0
                            and np.isfinite(s_o) and s_o > 0):
                        dd = (co_o / oT_o - 1) / s_o
                        if np.isfinite(dd) and dd <= -2:
                            br += 1
                co_b = close_g[i, m, btc_j]
                if (np.isfinite(co_b) and np.isfinite(openT[i, btc_j])
                        and openT[i, btc_j] > 0 and np.isfinite(sigma[i, btc_j])
                        and sigma[i, btc_j] > 0):
                    btc_depth = (co_b / openT[i, btc_j] - 1) / sigma[i, btc_j]
                    if not np.isfinite(btc_depth):
                        btc_depth = 0.0
                else:
                    btc_depth = 0.0
                tb42 = trend_base[i, j]
                if (np.isfinite(tb42) and tb42 > 0 and np.isfinite(oT[i])
                        and oT[i] > 0):
                    trend = oT[i] / tb42 - 1
                else:
                    trend = 0.0
                if not np.isfinite(trend):
                    trend = 0.0
                om24 = open_m24[i, j]
                if (np.isfinite(om24) and om24 > 0 and np.isfinite(oT[i])
                        and oT[i] > 0 and np.isfinite(sig[i]) and sig[i] > 0):
                    r1d = (oT[i] / om24 - 1) / sig[i]
                else:
                    r1d = 0.0
                if not np.isfinite(r1d):
                    r1d = 0.0
                rec_i.append(i)
                rec_j.append(j)
                rec_c.append(c)
                rec_m.append(m)
                rec_y.append(float(y))
                F["depth"].append(float(depth))
                F["c"].append(float(c))
                F["m_norm"].append(float(m / 240))
                F["r5"].append(float(r5))
                F["r15"].append(float(r15))
                F["vspike"].append(float(vspike))
                F["taker15"].append(float(taker15))
                F["rng"].append(float(rng))
                F["breadth"].append(float(br))
                F["btc_depth"].append(float(btc_depth))
                F["trend"].append(float(trend))
                F["r1d"].append(float(r1d))
                F["funding"].append(float(fund_feat[i, j]))
                for sj, sname in enumerate(SHORT):
                    F[f"asset_{sname}"].append(1.0 if sj == j else 0.0)
                n_pts_sym += 1
        print(f"{sym}: points={n_pts_sym}", flush=True)
        del op, hi, lo, cl, vo, tb

    rec_i = np.asarray(rec_i, dtype=int)
    rec_j = np.asarray(rec_j, dtype=int)
    rec_c = np.asarray(rec_c, dtype=float)
    rec_m = np.asarray(rec_m, dtype=int)
    rec_y = np.asarray(rec_y, dtype=float)
    X = np.column_stack([np.asarray(F[c], dtype=float) for c in FEATURE_COLS])
    t_arr = grid[rec_i]
    T_arr = T_all[rec_i]
    T2_arr = T2_all[rec_i]
    n_pts = len(rec_y)
    print(f"total points={n_pts}", flush=True)

    anchors_ts = [pd.Timestamp(a, tz="UTC") for a in ANCHORS]
    sleeve = np.zeros(n)
    per_anchor = []
    ic_all = {}
    taken_all = {}
    train_n_all = {}
    test_n_all = {}
    for a, a_ts in zip(ANCHORS, anchors_ts):
        train_mask = (T2_arr < a_ts - pd.Timedelta(days=1)) & (T_arr >= TRAIN_T_MIN)
        test_mask = (t_arr >= a_ts) & (t_arr < a_ts + pd.Timedelta(days=365))
        tr_idx = np.flatnonzero(train_mask)
        te_idx = np.flatnonzero(test_mask)
        train_n_all[a] = int(len(tr_idx))
        test_n_all[a] = int(len(te_idx))
        if len(tr_idx) == 0 or len(te_idx) == 0:
            ic = None
            pred_te = np.zeros(len(te_idx))
        else:
            mdl = HistGradientBoostingRegressor(
                max_depth=3, learning_rate=0.03, max_iter=300,
                min_samples_leaf=50, l2_regularization=1.0, random_state=0)
            mdl.fit(X[tr_idx], rec_y[tr_idx])
            pred_te = mdl.predict(X[te_idx])
            s_pred = pd.Series(pred_te)
            s_y = pd.Series(rec_y[te_idx])
            if len(te_idx) >= 3 and float(s_pred.std()) > 0 and float(s_y.std()) > 0:
                ic_v = float(s_pred.corr(s_y, method="spearman"))
                ic = ic_v if np.isfinite(ic_v) else None
            else:
                ic = None
        ic_all[a] = ic
        # takes: per (i, asset) earliest m with pred > 0
        taken = 0
        if len(te_idx):
            order = np.lexsort((rec_c[te_idx], rec_m[te_idx]))
            seen = set()
            for k in order:
                g = te_idx[k]
                key = (int(rec_i[g]), int(rec_j[g]))
                if key in seen:
                    continue
                if float(pred_te[k]) > 0:
                    seen.add(key)
                    sleeve[int(rec_i[g])] += 0.25 * float(rec_y[g])
                    taken += 1
                # if pred <= 0 for earliest, try next-later point of same key:
                # do not mark seen; later (larger m) point may still trigger.
            # NOTE: keys with all pred<=0 contribute nothing.
        taken_all[a] = int(taken)
        mk = (grid >= a_ts) & (grid < a_ts + pd.Timedelta(days=365))
        s = sleeve[mk]
        eq = np.cumprod(1 + s)
        net_pct = 100 * (float(eq[-1]) - 1) if len(s) else 0.0
        dd = 100 * float(np.max(1 - eq / np.maximum.accumulate(eq))) if len(s) else 0.0
        per_anchor.append({
            "anchor": a,
            "train_points": int(len(tr_idx)),
            "test_points": int(len(te_idx)),
            "ic_spearman": ic,
            "taken": int(taken),
            "sleeve_net_pct": round(float(net_pct), 2),
            "sleeve_dd_pct": round(float(dd), 2),
            "bars_nonzero": int((s != 0).sum()),
            "bars": int(mk.sum()),
            "sleeve_sum": float(s.sum()),
        })
        print(per_anchor[-1], flush=True)

    # ---- books + W=60 execution + combined loop ----
    idx = books.index
    cols = list(books.columns)
    pos = grid.get_indexer(idx)
    assert (pos >= 0).all(), "books times must exist in sleeve grid"
    sleeve_books = sleeve[pos]

    ctx = er.context(books, opens_full)
    fee_b = np.zeros((len(idx), len(cols)))
    rel_b = np.zeros((len(idx), len(cols)))
    fee_s = np.zeros((len(idx), len(cols)))
    rel_s = np.zeros((len(idx), len(cols)))
    for j, s in enumerate(cols):
        m = v135.load_1m(s)
        st = _bar_stats_W(m, W_EXEC).reindex(idx + pd.Timedelta(hours=4)).set_axis(idx)
        p0 = st["p0"].to_numpy(dtype=float)
        lo = st["lo"].to_numpy(dtype=float)
        hi = st["hi"].to_numpy(dtype=float)
        pW = st["pW"].to_numpy(dtype=float)
        have = ~np.isnan(p0)
        pWf = np.where(np.isnan(pW), p0, pW)
        with np.errstate(invalid="ignore", divide="ignore"):
            mv = np.where(have, pWf / np.where(have, p0, 1.0) - 1, 0.0)
        mv = np.nan_to_num(mv, nan=0.0, posinf=0.0, neginf=0.0)
        fb = have & (lo < p0 * (1 - D))
        fs = have & (hi > p0 * (1 + D))
        fee_b[:, j] = np.where(fb, 0.0002, 0.0005)
        rel_b[:, j] = np.where(fb, -D, mv + 0.0002)
        fee_s[:, j] = np.where(fs, 0.0002, 0.0005)
        rel_s[:, j] = np.where(fs, D, mv - 0.0002)

    o = ctx["opens"].reindex(idx)[cols]
    r_next, _, _, fund = ctx["mkt"]
    carry, expo = ctx["carry_real"]
    B = books.to_numpy(dtype=float)
    v99 = er.v144.v99
    PD = er.v144.PD
    live = np.asarray((idx >= START) & (idx < END))
    nB = len(idx)
    realized = (v99.W_BOOKS * (books.shift(2) * (o / o.shift(1) - 1)).sum(axis=1)
                + v99.W_CARRY * v99.CARRY_LEV * pd.Series(carry, index=idx).shift(1))
    vol = (realized.rolling(60 * PD, min_periods=20 * PD).std() * np.sqrt(PD * 365)).to_numpy(dtype=float)
    s_arr = np.where(np.isnan(vol), 1.0, np.minimum(TARGET / np.where(np.isnan(vol), 1.0, vol), v99.CAP))
    mins = np.array([er.MIN_NOTIONAL.get(c, 5.0) for c in cols])

    def run_loop(sleeve_arr):
        m = len(cols)
        net = np.zeros(nB)
        turn = np.zeros(nB)
        g = np.ones(nB)
        eq = np.ones(nB)
        prev_w = np.zeros(m)
        prev_c = 0.0
        for i in range(nB):
            if i >= 2:
                j = i - 2
                peak = eq[max(0, j - 90 * PD + 1): j + 1].max()
                g[i] = float(np.clip((0.20 - (1 - eq[j] / peak)) / 0.10, 0.0, 1.0))
            if live[i]:
                w = v99.W_BOOKS * s_arr[i] * B[i] * g[i]
                c = v99.W_CARRY * v99.CARRY_LEV * s_arr[i] * g[i]
            else:
                w = np.zeros(m)
                c = 0.0
            ex = expo[i]
            tot = c * ex + np.abs(w).sum() / er.MARGIN
            if tot > er.BUFFER:
                c_allow = (er.BUFFER - np.abs(w).sum() / er.MARGIN) / max(ex, 1e-9)
                c = min(c, max(0.0, c_allow))
            if np.abs(w).sum() / er.MARGIN > er.BUFFER:
                w = w * er.BUFFER * er.MARGIN / np.abs(w).sum()
            eq_usdt = er.ACCOUNT_USDT * (eq[i - 1] if i else 1.0)
            small = (np.abs(w - prev_w) * eq_usdt < mins) & (w != 0)
            w = np.where(small, prev_w, w)
            dw = w - prev_w
            buy = dw > 0
            exec_c = float(np.sum(np.abs(dw) * np.where(buy, fee_b[i], fee_s[i])
                                  + dw * np.where(buy, rel_b[i], rel_s[i])))
            gross = float(np.sum(w * r_next[i]))
            fundp = float(-np.sum(w * fund[i]))
            carry_p = float(c * carry[i])
            dc = c - prev_c
            carry_c = float(abs(dc) / er.CARRY_CAPITAL * ex * (er.SPOT_FEE + er.PERP_TAKER))
            ni = gross - exec_c + fundp + carry_p - carry_c
            if live[i]:
                ni += g[i] * float(sleeve_arr[i])
            net[i] = ni
            turn[i] = float(np.abs(dw).sum())
            eq[i] = (eq[i - 1] if i else 1.0) * (1 + ni)
            prev_w, prev_c = w.copy(), c
        return net, turn, g

    net0, turn0, g0 = run_loop(np.zeros(nB))
    s0 = v110.summarize(pd.Series(net0, index=idx), pd.Series(turn0, index=idx), pd.Series(g0, index=idx))
    print("books-alone W60 monthly", s0["monthly_pct"], "DD", s0["full_path_dd"], flush=True)
    assert s0["monthly_pct"] == 3.802, s0["monthly_pct"]
    assert s0["full_path_dd"] == 18.93, s0["full_path_dd"]
    print("audit loop books-alone reproduces 3.802/18.93", flush=True)

    netC, turnC, gC = run_loop(sleeve_books)
    summC = v110.summarize(pd.Series(netC, index=idx), pd.Series(turnC, index=idx), pd.Series(gC, index=idx))

    replication = {
        "version": "v173_audit_replication",
        "blind": "did_not_open_research_v173_until_this_file_saved",
        "books": "cached v154 books (A+B+D)/3",
        "target": TARGET,
        "governor": "20% with 2-bar lag on combined equity",
        "realism": "all on (funding, carry_real, budget, min_notional); W=60 execution",
        "feature_columns": FEATURE_COLS,
        "model": {"name": "HistGradientBoostingRegressor", "max_depth": 3,
                  "learning_rate": 0.03, "max_iter": 300,
                  "min_samples_leaf": 50, "l2_regularization": 1.0,
                  "random_state": 0},
        "spec": {
            "symbols": SYMS,
            "grid": f"{grid.min()} -> {grid.max()} ({n} 4h bars)",
            "holding_bar": "T = t + 4h",
            "sigma": "std of 4h open-to-open pct changes, 360 bars ending at t, min 120",
            "trigger": "for c in (2,3,4): first m in 16..238 with close1m(m)/open4h(T)-1 <= -c*sigma(t)",
            "entry": "open1m(m+1)*(1+s_in), s_in=max(0.0002,0.25*(H-L)/O of minute m+1)",
            "exit": "open(T+4h)*(1-s_out), base=O[i+1,0] else 4h open, s_out=max(0.0002,0.25*(H-L)/O of minute 0 of T+4h)",
            "y": "exit/entry-1-0.001-funding(T+4h floored-4h sum)",
            "train": "T+4h < anchor-1d and T >= 2020-03-02",
            "test": "t in [anchor, anchor+365d)",
            "take": "per (t,asset) earliest m with pred>0",
            "sleeve_per_bar": "0.25*sum over taken assets of y (0 without take)",
            "books_exec": "W=60 (p0@0, lo/hi 2..59, pW@60 NaN->p0; maker 0.0002 rel -/+0.001 else taker 0.0005 + drift)",
            "combined": "net[i] += g[i]*sleeve[i] on live bars",
        },
        "assumptions": {f"A{i}": v for i, v in enumerate(
            ["grid date_range 2020-02-01 to last books bar; v92 anchors",
             "sigma finite and >0 else no point",
             "1m keep-last dedup + within-bar ffill prices; volume/taker missing->0",
             "trigger/depth closes from ffilled grid; entry from ffilled O/H/L",
             "s_in from entry minute else 0.0002",
             "exit base O[i+1,0] else 4h open; s_out else 0.0002; i+1>=n -> skip",
             "missing/nonpositive opens/entry/no-trigger -> skip; funding missing->0",
             "r5/r15 fallback 0.0",
             "vspike fallback 1.0",
             "taker15 fallback 0.5, clipped [0,1]",
             "rng fallback 0.0",
             "breadth counts finite depth<=-2 others; btc_depth fallback 0.0",
             "trend rolling42 min42 else 0.0",
             "r1d open(T-24h) else 0.0",
             "funding feature last non-zero rate at or before t else 0.0",
             "asset one-hot BNB,BTC,ETH,SOL,XRP",
             "train/test/take/sleeve as spec A17",
             "IC Spearman else null; combined mirrors engine_real FULL W60"],
            start=1)},
        "points_total": int(n_pts),
        "per_anchor": per_anchor,
        "sleeve_totals": {
            "bars_nonzero": int((sleeve != 0).sum()),
            "taken": int(sum(taken_all.values())),
            "taken_per_anchor": {a: int(taken_all[a]) for a in ANCHORS},
            "ic_per_anchor": {a: ic_all[a] for a in ANCHORS},
            "train_points": {a: int(train_n_all[a]) for a in ANCHORS},
            "test_points": {a: int(test_n_all[a]) for a in ANCHORS},
            "sum": float(sleeve.sum()),
        },
        "books_alone_W60": {
            "monthly_pct": s0["monthly_pct"],
            "yearly": s0["yearly"],
            "full_path_dd": s0["full_path_dd"],
            "worst_year_dd": s0["worst_year_dd"],
        },
        "combined": {
            "monthly_pct": summC["monthly_pct"],
            "yearly": summC["yearly"],
            "full_path_dd": summC["full_path_dd"],
            "worst_year_dd": summC["worst_year_dd"],
        },
        "params": {
            "start": str(START), "end": str(END),
            "account_usdt": er.ACCOUNT_USDT, "margin": er.MARGIN, "buffer": er.BUFFER,
            "vol": "rolling std 360 min 120 *sqrt(6*365); s=min(0.25/vol,2) else 1",
            "governor": "clip((0.20-(1-eq[j]/peak540))/0.10) j=i-2 on combined eq",
        },
    }
    OUT.write_text(json.dumps(replication, indent=1, default=str))
    print("saved", OUT)


if __name__ == "__main__":
    main()
