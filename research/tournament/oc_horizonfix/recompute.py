"""oc_horizonfix Task 2: re-score both studies old vs strictly-forward yardstick.

Read-only inputs (never written): preds_*.csv of oc_presamplebook /
oc_presampleflow, price histories rebuilt with the workers' own
construction, cached member/book series in artifacts/research/engine_real.

Pre-registered in PLAN.md BEFORE any outcome:
  availability(T) = T+4h (close of bar opening at T).
  t_trade = T+4h (first bar open at/after availability).
  y_old[T,h]  = (open[T+h]/open[T]-1)/sigma[T]
  y_corr[T,h] = (open[t_trade+h]/open[t_trade]-1)/sigma[t_trade]
sigma math, histories, test sets, horizons, metrics IDENTICAL to the two
original studies. Point ICs only (no bootstrap recompute; old CIs quoted
from published results.json for reference in REPORT).

Writes: results.json (old reproduced + corrected + published-old reference).
Light: 4h data only, no GPU, no engine run.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import rankdata

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
BOOK = ROOT / "research/tournament/oc_presamplebook"
FLOWD = ROOT / "research/tournament/oc_presampleflow"
PSHORT = ROOT / "research/tournament/oc_presampleshort"
BICH = ROOT / "research/tournament/oc_bookichorizon"
CACHE = ROOT / "artifacts/research/engine_real"
SPOT1M = ROOT / "data/raw/spot_1m_presample_20261007"
BTC4H = ROOT / "data/raw/ma_ribbon_20260924/klines_4h.parquet"
XS = ROOT / "data/raw/xs_universe_20260924"
SPOT4H = ROOT / "data/raw/spot_majors_20260925"
STITCH_CUT = pd.Timestamp("2020-10-01", tz="UTC")

COINS4 = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT"]
SYMS5 = ["BNBUSDT", "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]
HORIZONS = (1, 2, 6, 18, 42)
PS_SERIES = ("TV", "FLOW", "PREMIUM", "BLEND")
BK_SERIES = ("A", "Aq", "B", "Bq", "D", "Dq", "O1", "CB", "FULL", "FINAL")
PS_ANCHORS = ["2019-03-01", "2019-09-24", "2020-03-01",
              "2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24"]
PRESAMPLE = {"2019-03-01", "2019-09-24", "2020-03-01"}
BK_ANCHORS = [pd.Timestamp(f"{y}-09-24", tz="UTC") for y in (2021, 2022, 2023, 2024, 2025)]
YEAR_LEN = pd.Timedelta(days=365)
BARH = pd.Timedelta(hours=4)


def spearman_xy(x, y):
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    m = np.isfinite(x) & np.isfinite(y)
    x, y = x[m], y[m]
    n = int(len(x))
    if n < 3:
        return float("nan"), n
    if np.std(x) == 0.0 or np.std(y) == 0.0:
        return float("nan"), n
    rx = rankdata(x)
    ry = rankdata(y)
    if np.std(rx) == 0.0 or np.std(ry) == 0.0:
        return float("nan"), n
    return float(np.corrcoef(rx, ry)[0, 1]), n


def xs_point(Pv, Yv):
    n = Pv.shape[0]
    fin = np.isfinite(Pv) & np.isfinite(Yv)
    nvalid = fin.sum(axis=1)
    ncols = Pv.shape[1]
    full = nvalid == ncols
    xs_vals = np.full(n, np.nan)
    if full.any():
        Pf, Yf = Pv[full], Yv[full]
        rx = rankdata(Pf, axis=1)
        ry = rankdata(Yf, axis=1)
        rx_c = rx - rx.mean(axis=1, keepdims=True)
        ry_c = ry - ry.mean(axis=1, keepdims=True)
        sx = rx.std(axis=1)
        sy = ry.std(axis=1)
        denom = sx * sy
        ok = denom > 0
        r = np.full(full.sum(), np.nan)
        r[ok] = (rx_c[ok] * ry_c[ok]).mean(axis=1) / denom[ok]
        xs_vals[np.where(full)[0]] = r
    part = np.where(~full & (nvalid >= 3))[0]
    for i in part:
        pv, yv = Pv[i], Yv[i]
        m = np.isfinite(pv) & np.isfinite(yv)
        if np.std(pv[m]) == 0.0 or np.std(yv[m]) == 0.0:
            continue
        ic, _ = spearman_xy(pv[m], yv[m])
        xs_vals[i] = ic
    return xs_vals


def block_stats(Pv, Yv, ncols_require):
    """Pooled / per-coin / TS / XS point ICs (no bootstrap)."""
    pm = np.isfinite(Pv) & np.isfinite(Yv)
    pic, pn = spearman_xy(Pv[pm], Yv[pm])
    per = []
    for j in range(Pv.shape[1]):
        ic, nn = spearman_xy(Pv[:, j], Yv[:, j])
        per.append(ic)
    valid = [v for v in per if v is not None and np.isfinite(v)]
    ts = float(np.mean(valid)) if len(valid) == ncols_require else float("nan")
    xs_vals = xs_point(Pv, Yv)
    good = xs_vals[np.isfinite(xs_vals)]
    xs = float(good.mean()) if len(good) else float("nan")
    r = lambda v: round(float(v), 4) if np.isfinite(v) else None
    return {
        "pooled": r(pic), "pooled_n": int(pn),
        "per_coin": [r(v) for v in per],
        "ts_mean": r(ts),
        "xs_mean": r(xs), "xs_n": int(len(good)),
    }


# ---------------- presample side ----------------

def build_spot_4h(sym: str) -> pd.DataFrame:
    m = pd.read_parquet(SPOT1M / f"{sym}.parquet",
                        columns=["open_time", "o", "h", "l", "c", "volume"])
    m["open_time"] = pd.to_datetime(m["open_time"], utc=True)
    m["bar"] = m["open_time"].dt.floor("4h")
    g = m.groupby("bar", sort=True)
    first_fin = lambda s: s.dropna().iloc[0] if s.notna().any() else np.nan  # noqa: E731
    last_fin = lambda s: s.dropna().iloc[-1] if s.notna().any() else np.nan  # noqa: E731
    bars = pd.DataFrame({"open_time": sorted(m["bar"].dropna().unique())})
    bars = bars.set_index("open_time").sort_index()
    bars["open"] = g["o"].apply(first_fin).to_numpy()
    bars["high"] = g["h"].max().to_numpy()
    bars["low"] = g["l"].min().to_numpy()
    bars["close"] = g["c"].apply(last_fin).to_numpy()
    bars["volume"] = g["volume"].sum(min_count=1).to_numpy()
    bars = bars.reset_index().sort_values("open_time").reset_index(drop=True)
    del m
    return bars


def load_perp_4h(sym: str) -> pd.DataFrame:
    src = BTC4H if sym == "BTCUSDT" else XS / f"{sym}_4h.parquet"
    b = pd.read_parquet(src, columns=["open_time", "open", "high", "low",
                                      "close", "volume"])
    b["open_time"] = pd.to_datetime(b["open_time"], utc=True)
    return b.sort_values("open_time").reset_index(drop=True)


def load_spot4h_after(sym: str) -> pd.DataFrame:
    b = pd.read_parquet(SPOT4H / f"{sym}_spot_4h.parquet",
                        columns=["open_time", "open", "high", "low", "close", "volume"])
    b["open_time"] = pd.to_datetime(b["open_time"], utc=True)
    return b.sort_values("open_time").reset_index(drop=True)


def opens_series(df: pd.DataFrame) -> pd.Series:
    d = df.sort_values("open_time").drop_duplicates("open_time")
    return pd.Series(d["open"].to_numpy(dtype=float),
                     index=pd.DatetimeIndex(d["open_time"]))


def sigma_series(opens: pd.Series) -> pd.Series:
    o = opens.sort_index()
    r1 = o / o.shift(1) - 1.0
    return r1.rolling(360, min_periods=120).std(ddof=1)


def targets_for(opens_hist, sig_hist, times, h, shift_bars):
    """shift_bars=0 -> old (anchor T); =1 -> corrected (anchor T+4h)."""
    t2 = times + shift_bars * BARH
    th = t2 + h * BARH
    n = len(times)
    fwd = np.full((n, len(COINS4)), np.nan)
    sg = np.full((n, len(COINS4)), np.nan)
    for j, sym in enumerate(COINS4):
        s = opens_hist[sym]
        sg[:, j] = sig_hist[sym].reindex(t2).to_numpy()
        ot = s.reindex(t2).to_numpy()
        oh = s.reindex(th).to_numpy()
        with np.errstate(divide="ignore", invalid="ignore"):
            fwd[:, j] = oh / ot - 1.0
    with np.errstate(divide="ignore", invalid="ignore"):
        yh = fwd / sg
    bad = (~np.isfinite(sg)) | (sg <= 0) | (~np.isfinite(fwd))
    yh[bad] = np.nan
    return yh


# ---------------- book side ----------------

def load_book_series():
    m = lambda f: pd.read_parquet(CACHE / f)[SYMS5]  # noqa: E731
    A = m("member_A_O1_orders.parquet")
    Aq = m("member_Aq_O1_orders.parquet")
    B = m("member_B_tv.parquet")
    Bq = m("member_Bq_tv.parquet")
    D = pd.read_parquet(CACHE / "members_v154.parquet").xs("D", axis=1, level=0)[SYMS5]
    Dq = m("members_quarterly_D.parquet")
    books_std = pd.read_parquet(CACHE / "books_v154.parquet")[SYMS5]
    opens_full = pd.read_parquet(CACHE / "opens_v154.parquet")[SYMS5].sort_index()
    std_idx = books_std.index.sort_values()
    f = lambda X: X.reindex(std_idx).fillna(0.0)  # noqa: E731
    A, Aq, B, Bq, D, Dq = f(A), f(Aq), f(B), f(Bq), f(D), f(Dq)
    o1 = (A + Aq + B + Bq) / 4.0
    cb = (D + Dq) / 2.0
    full = 0.8 * o1 + 0.2 * cb
    opens_std = opens_full.reindex(std_idx)
    btc = opens_std["BTCUSDT"]
    bear = (btc < btc.rolling(1200, min_periods=600).mean()).fillna(False)
    final = full.copy()
    final[bear] = final[bear].where(final[bear] <= 0, final[bear] * 0.5)
    series = {"A": A, "Aq": Aq, "B": B, "Bq": Bq, "D": D, "Dq": Dq,
              "O1": o1, "CB": cb, "FULL": full, "FINAL": final}
    return series, std_idx, opens_full


def book_targets(opens_full, std_idx, h, shift_bars):
    opens_full = opens_full.sort_index()
    r1_full = opens_full / opens_full.shift(1) - 1.0
    sigma_full = r1_full.rolling(360, min_periods=120).std(ddof=1)
    base = std_idx + shift_bars * BARH
    ahead = base + pd.Timedelta(hours=4 * h)
    o_t = opens_full.reindex(base)
    o_th = opens_full.reindex(ahead)
    fh = o_th.to_numpy() / o_t.to_numpy() - 1.0
    fh = pd.DataFrame(fh, index=std_idx, columns=SYMS5)
    sg = sigma_full.reindex(base).set_axis(std_idx)
    with np.errstate(divide="ignore", invalid="ignore"):
        yh = fh / sg
    yh[(sg.isna()) | (sg <= 0) | (fh.isna())] = np.nan
    return yh.to_numpy()


def main():
    t0 = time.time()
    print("oc_horizonfix recompute: rebuilding presample histories ...", flush=True)
    spot_pre, perp, post = {}, {}, {}
    for sym in COINS4:
        spot_pre[sym] = build_spot_4h(sym)
        perp[sym] = load_perp_4h(sym)
        post[sym] = load_spot4h_after(sym)
    stitched = {}
    for sym in COINS4:
        pre = spot_pre[sym][spot_pre[sym]["open_time"] < STITCH_CUT]
        po = post[sym][post[sym]["open_time"] >= STITCH_CUT]
        st = pd.concat([pre[["open_time", "open"]], po[["open_time", "open"]]],
                       ignore_index=True)
        stitched[sym] = st.drop_duplicates("open_time").sort_values("open_time").reset_index(drop=True)
    hist, sig = {}, {}
    for sym in COINS4:
        hist[("spot", sym)] = opens_series(spot_pre[sym][["open_time", "open"]])
        hist[("perp", sym)] = opens_series(perp[sym][["open_time", "open"]])
        hist[("stitched", sym)] = opens_series(stitched[sym])
    sig = {k: sigma_series(v) for k, v in hist.items()}
    print(f"histories ready in {time.time()-t0:.0f}s", flush=True)

    preds = {}
    for a in PS_ANCHORS:
        b = pd.read_csv(BOOK / f"preds_{a}.csv", parse_dates=["open_time"])
        b["open_time"] = pd.to_datetime(b["open_time"], utc=True)
        f = pd.read_csv(FLOWD / f"preds_{a}.csv", parse_dates=["open_time"])
        f["open_time"] = pd.to_datetime(f["open_time"], utc=True)
        preds[a] = (b, f)

    pub_ps = {(r["series"], r["year"], r["h"]): r
              for r in json.loads((PSHORT / "results.json").read_text())["rows"]}
    pub_bk = {(r["series"], r["year"], r["h"]): r
              for r in json.loads((BICH / "results.json").read_text())["rows"]}

    HKEY = {"TV": None, "FLOW": "stitched", "PREMIUM": "stitched", "BLEND": "stitched"}
    ps_rows = []
    maxdiff = 0.0
    for a in PS_ANCHORS:
        b, f = preds[a]
        times_TV = np.sort(pd.DatetimeIndex(b["open_time"].unique()))
        times_flow = np.sort(pd.DatetimeIndex(f["open_time"].unique()))
        P, TIMES, HK = {}, {}, {}
        bp = b.pivot(index="open_time", columns="sym", values="pred")
        P["TV"] = bp.reindex(times_TV).reindex(columns=COINS4).to_numpy(dtype=float)
        TIMES["TV"] = times_TV
        HK["TV"] = "spot" if a in PRESAMPLE else "perp"
        for sname, col in (("FLOW", "pred_flow"), ("PREMIUM", "pred_prem"),
                           ("BLEND", "pred_blend")):
            pv = f.pivot(index="open_time", columns="sym", values=col)
            P[sname] = pv.reindex(times_flow).reindex(columns=COINS4).to_numpy(dtype=float)
            TIMES[sname] = times_flow
            HK[sname] = "stitched"
        for h in HORIZONS:
            for sname in PS_SERIES:
                times = TIMES[sname]
                oh_ = {sym: hist[(HK[sname], sym)] for sym in COINS4}
                sh_ = {sym: sig[(HK[sname], sym)] for sym in COINS4}
                Y_old = targets_for(oh_, sh_, times, h, 0)
                Y_new = targets_for(oh_, sh_, times, h, 1)
                s_old = block_stats(P[sname], Y_old, 4)
                s_new = block_stats(P[sname], Y_new, 4)
                pub = pub_ps.get((sname, a, int(h)), {})
                po = pub.get("pooled_ic")
                if po is not None and s_old["pooled"] is not None:
                    maxdiff = max(maxdiff, abs(po - s_old["pooled"]))
                ps_rows.append({
                    "study": "presample", "series": sname, "year": a, "h": int(h),
                    "n_bars": int(len(times)),
                    "old": s_old, "new": s_new,
                    "published_pooled": po, "published_ts": pub.get("ts_mean"),
                    "published_xs": pub.get("xs_mean"),
                })
            print(f"presample {a} h={h} done ({time.time()-t0:.0f}s)", flush=True)
    print(f"presample old-repro max |pub-old| pooled diff = {maxdiff:.4f}", flush=True)

    print("loading book caches ...", flush=True)
    series, std_idx, opens_full = load_book_series()
    P_all = {k: v.to_numpy() for k, v in series.items()}
    bounds = list(BK_ANCHORS) + [BK_ANCHORS[-1] + YEAR_LEN]
    bk_rows = []
    maxdiff_b = 0.0
    Y_old_cache, Y_new_cache = {}, {}
    for h in HORIZONS:
        Y_old_cache[h] = book_targets(opens_full, std_idx, h, 0)
        Y_new_cache[h] = book_targets(opens_full, std_idx, h, 1)
    for yi, a0 in enumerate(BK_ANCHORS):
        ylab = str(a0.date())
        ymask = np.asarray((std_idx >= a0) & (std_idx < bounds[yi + 1]))
        ypos = np.where(ymask)[0]
        for h in HORIZONS:
            Yo = Y_old_cache[h][ypos]
            Yn = Y_new_cache[h][ypos]
            for sname in BK_SERIES:
                Pv = P_all[sname][ypos]
                s_old = block_stats(Pv, Yo, 5)
                s_new = block_stats(Pv, Yn, 5)
                pub = pub_bk.get((sname, ylab, int(h)), {})
                po = pub.get("pooled_ic")
                if po is not None and s_old["pooled"] is not None:
                    maxdiff_b = max(maxdiff_b, abs(po - s_old["pooled"]))
                bk_rows.append({
                    "study": "book", "series": sname, "year": ylab, "h": int(h),
                    "n_bars": int(len(ypos)),
                    "old": s_old, "new": s_new,
                    "published_pooled": po, "published_ts": pub.get("ts_mean"),
                    "published_xs": pub.get("xs_mean"),
                })
            print(f"book {ylab} h={h} done ({time.time()-t0:.0f}s)", flush=True)
    print(f"book old-repro max |pub-old| pooled diff = {maxdiff_b:.4f}", flush=True)

    out = {
        "meta": {
            "timing": "row T (bar-open ts) available at T+4h; t_trade=T+4h",
            "y_old": "y_old[T,h]=(open[T+h]/open[T]-1)/sigma[T]",
            "y_corr": "y_corr[T,h]=(open[T+4h+h]/open[T+4h]-1)/sigma[T+4h]",
            "sigma": "std of 1-bar open-to-open simple returns, trailing 360 ending at anchor (min120, ddof1); identical math, anchor shifted +1 bar",
            "histories": "presample: TV pre-sample=spot1m-built, TV reference=perp, FLOW/PREMIUM/BLEND=stitched; book: opens_v154 full history; test sets identical to originals",
            "horizons": list(HORIZONS),
            "metrics": "pooled Spearman over stacked (bar,coin); per-coin; ts_mean=mean of per-coin (NaN unless all coins finite); xs=per-bar cross-sectional rank corr averaged (needs >=3 valid); point ICs only, no bootstrap",
            "verify": f"old-repro max|pub-old| pooled: presample {round(maxdiff,4)}, book {round(maxdiff_b,4)}",
            "leakage": "fits frozen before anchors (read-only); sigma causal; targets are scoring labels only; no test-year statistic used",
        },
        "presample_rows": ps_rows,
        "book_rows": bk_rows,
    }
    (HERE / "results.json").write_text(json.dumps(out, indent=1))
    print(f"wrote results.json ps={len(ps_rows)} bk={len(bk_rows)} in {time.time()-t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
