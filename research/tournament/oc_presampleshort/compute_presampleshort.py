"""oc_presampleshort: re-score STORED pre-sample book-member predictions at SHORT horizons.

Pre-registered in PLAN.md (read it first). Identical yardstick to
oc_bookichorizon: target y(t,coin,h) = (open[t+h]/open[t]-1)/sigma[t],
sigma = trailing-360-bar std of 1-bar open returns (min120, causal, ddof1),
opens from the SAME price series each prediction file was built on
(spot 1m-built for pre-sample TV; perp for reference TV; stitched spot for
FLOW/PREMIUM/BLEND -- see PLAN), h in {1,2,6,18,42}. Metrics per
(series,year,h): pooled Spearman IC + block bootstrap CI (L=max(h,6), B=500,
seed 7), per-coin IC (TS) + TS mean, XS mean + CI.

Light: 4h data only, one coin's 1m slice at a time, no GPU. Run:
  .venv/Scripts/python.exe research/tournament/oc_presampleshort/compute_presampleshort.py
Checkpointed per (year, h) in tmp/parts/ so a timeout can resume.
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
PARTS = HERE / "tmp" / "parts"
SPOT1M = ROOT / "data/raw/spot_1m_presample_20261007"
BTC4H = ROOT / "data/raw/ma_ribbon_20260924/klines_4h.parquet"
XS = ROOT / "data/raw/xs_universe_20260924"
SPOT4H = ROOT / "data/raw/spot_majors_20260925"
STITCH_CUT = pd.Timestamp("2020-10-01", tz="UTC")

COINS = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT"]
HORIZONS = (1, 2, 6, 18, 42)
SERIES_ORDER = ("TV", "FLOW", "PREMIUM", "BLEND")
ANCHORS = ["2019-03-01", "2019-09-24", "2020-03-01",
           "2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24"]
PRESAMPLE = {"2019-03-01", "2019-09-24", "2020-03-01"}
B_BOOT = 500
SEED = 7
BARH = pd.Timedelta(hours=4)


def build_spot_4h(sym: str) -> pd.DataFrame:
    """Same as presamplebook.py / presampleflow.py build_spot_4h."""
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


def boot_corr(x, y, idx, L, B, rng):
    n = len(idx)
    if n < L:
        return None
    nblocks = int(np.ceil(n / L))
    xv, yv = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
    boots = np.empty(B)
    boots[:] = np.nan
    for b in range(B):
        starts = rng.integers(0, n, size=nblocks)
        sel = np.concatenate([(s + np.arange(L)) % n for s in starts])[:n]
        sel = idx[sel]
        m = np.isfinite(xv[sel]) & np.isfinite(yv[sel])
        xx, yy = xv[sel][m], yv[sel][m]
        if len(xx) < 3 or np.std(xx) == 0.0 or np.std(yy) == 0.0:
            continue
        rx, ry = rankdata(xx), rankdata(yy)
        if np.std(rx) == 0.0 or np.std(ry) == 0.0:
            continue
        boots[b] = np.corrcoef(rx, ry)[0, 1]
    ok = boots[np.isfinite(boots)]
    if len(ok) < 50:
        return None
    return [round(float(np.percentile(ok, 2.5)), 4), round(float(np.percentile(ok, 97.5)), 4)]


def xs_point(Pv, Yv):
    n = Pv.shape[0]
    fin = np.isfinite(Pv) & np.isfinite(Yv)
    nvalid = fin.sum(axis=1)
    full = nvalid == Pv.shape[1]
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


def main():
    t0 = time.time()
    PARTS.mkdir(parents=True, exist_ok=True)
    print("oc_presampleshort: rebuilding price histories ...", flush=True)
    spot_pre, perp, post = {}, {}, {}
    for sym in COINS:
        print(f"-- {sym}: spot 1m -> 4h ...", flush=True)
        spot_pre[sym] = build_spot_4h(sym)
        print(f"   spot_pre={len(spot_pre[sym])} "
              f"{spot_pre[sym]['open_time'].iloc[0]} .. {spot_pre[sym]['open_time'].iloc[-1]}",
              flush=True)
        perp[sym] = load_perp_4h(sym)
        post[sym] = load_spot4h_after(sym)
    stitched = {}
    for sym in COINS:
        pre = spot_pre[sym][spot_pre[sym]["open_time"] < STITCH_CUT]
        po = post[sym][post[sym]["open_time"] >= STITCH_CUT]
        st = pd.concat([pre[["open_time", "open"]], po[["open_time", "open"]]],
                       ignore_index=True)
        st = st.drop_duplicates("open_time").sort_values("open_time").reset_index(drop=True)
        stitched[sym] = st
        print(f"-- {sym}: stitched={len(st)} "
              f"{st['open_time'].iloc[0]} .. {st['open_time'].iloc[-1]}", flush=True)

    # Full opens/sigma per (study side, coin): book-spot, book-perp, flow-stitched.
    hist = {}
    for sym in COINS:
        hist[("spot", sym)] = opens_series(spot_pre[sym][["open_time", "open"]])
        hist[("perp", sym)] = opens_series(perp[sym][["open_time", "open"]])
        hist[("stitched", sym)] = opens_series(stitched[sym])
    sig = {k: sigma_series(v) for k, v in hist.items()}
    print(f"histories ready in {time.time()-t0:.0f}s", flush=True)

    # Load stored preds.
    preds = {}
    for a in ANCHORS:
        b = pd.read_csv(BOOK / f"preds_{a}.csv", parse_dates=["open_time"])
        b["open_time"] = pd.to_datetime(b["open_time"], utc=True)
        f = pd.read_csv(FLOWD / f"preds_{a}.csv", parse_dates=["open_time"])
        f["open_time"] = pd.to_datetime(f["open_time"], utc=True)
        preds[a] = (b, f)
        print(f"anchor {a}: book rows={len(b)} flow rows={len(f)}", flush=True)

    # Verify rebuilt opens match stored opens (tolerance 1e-6 rel).
    maxdiff = 0.0
    for a in ANCHORS:
        b, f = preds[a]
        for sym in COINS:
            key = "spot" if a in PRESAMPLE else "perp"
            s = hist[(key, sym)]
            sub = b[b["sym"] == sym].sort_values("open_time")
            got = s.reindex(pd.DatetimeIndex(sub["open_time"])).to_numpy()
            exp = sub["open"].to_numpy(dtype=float)
            m = np.isfinite(got) & np.isfinite(exp) & (exp != 0)
            d = np.max(np.abs(got[m] / exp[m] - 1.0)) if int(m.sum()) else float("nan")
            maxdiff = max(maxdiff, float(d) if np.isfinite(d) else 0.0)
            s2 = hist[("stitched", sym)]
            sub2 = f[f["sym"] == sym].sort_values("open_time")
            got2 = s2.reindex(pd.DatetimeIndex(sub2["open_time"])).to_numpy()
            exp2 = sub2["open"].to_numpy(dtype=float)
            m2 = np.isfinite(got2) & np.isfinite(exp2) & (exp2 != 0)
            d2 = np.max(np.abs(got2[m2] / exp2[m2] - 1.0)) if int(m2.sum()) else float("nan")
            maxdiff = max(maxdiff, float(d2) if np.isfinite(d2) else 0.0)
    print(f"open verify: max abs rel diff = {maxdiff:.2e} (tolerance 1e-6)", flush=True)
    assert maxdiff < 1e-6, f"rebuilt opens do not match stored opens: {maxdiff}"

    for yi, a in enumerate(ANCHORS):
        b, f = preds[a]
        # PLAN: test set = exactly the stored rows of EACH preds file
        # (book and flow files have different row sets, e.g. flow 2020-03-01
        # runs the full year while book 2020-03-01 is truncated at 2020-09-23).
        times_TV = np.sort(pd.DatetimeIndex(b["open_time"].unique()))
        times_flow = np.sort(pd.DatetimeIndex(f["open_time"].unique()))
        # pivot stored preds to (n_times, 4) in COINS order, per own file
        P, TIMES = {}, {}
        bp = b.pivot(index="open_time", columns="sym", values="pred")
        P["TV"] = bp.reindex(times_TV).reindex(columns=COINS).to_numpy(dtype=float)
        TIMES["TV"] = times_TV
        for sname, col in (("FLOW", "pred_flow"), ("PREMIUM", "pred_prem"),
                           ("BLEND", "pred_blend")):
            pv = f.pivot(index="open_time", columns="sym", values=col)
            P[sname] = pv.reindex(times_flow).reindex(columns=COINS).to_numpy(dtype=float)
            TIMES[sname] = times_flow
        HKEY = {"TV": ("spot" if a in PRESAMPLE else "perp"),
                "FLOW": "stitched", "PREMIUM": "stitched", "BLEND": "stitched"}
        for h in HORIZONS:
            part = PARTS / f"part_{a}_h{int(h)}.json"
            if part.exists():
                print(f"year {a} h={h}: cached, skip", flush=True)
                continue
            t1 = time.time()
            L = max(int(h), 6)
            rng = np.random.default_rng((SEED, yi, int(h)))
            # targets per series (different histories AND bar sets for TV vs flow families)
            Y = {}
            for sname in SERIES_ORDER:
                key = HKEY[sname]
                times = TIMES[sname]
                n = len(times)
                fwd = np.full((n, len(COINS)), np.nan)
                sg = np.full((n, len(COINS)), np.nan)
                for j, sym in enumerate(COINS):
                    s = hist[(key, sym)]
                    sg[:, j] = sig[(key, sym)].reindex(times).to_numpy()
                    ot = s.reindex(times).to_numpy()
                    oh = s.reindex(times + h * BARH).to_numpy()
                    with np.errstate(divide="ignore", invalid="ignore"):
                        fwd[:, j] = oh / ot - 1.0
                with np.errstate(divide="ignore", invalid="ignore"):
                    yh = fwd / sg
                bad = (~np.isfinite(sg)) | (sg <= 0) | (~np.isfinite(fwd))
                yh[bad] = np.nan
                Y[sname] = yh
            out_rows = []
            for sname in SERIES_ORDER:
                Pv, Yv = P[sname], Y[sname]
                pm = np.isfinite(Pv) & np.isfinite(Yv)
                pic, pn = spearman_xy(Pv[pm], Yv[pm])
                pidx = np.where(pm.any(axis=1))[0]
                if np.isfinite(pic) and len(pidx) >= L:
                    n = len(pidx)
                    nblocks = int(np.ceil(n / L))
                    boots = []
                    for bb in range(B_BOOT):
                        starts = rng.integers(0, n, size=nblocks)
                        sel = pidx[np.concatenate([(s + np.arange(L)) % n for s in starts])[:n]]
                        xx, yy = Pv[sel].ravel(), Yv[sel].ravel()
                        m = np.isfinite(xx) & np.isfinite(yy)
                        xx, yy = xx[m], yy[m]
                        if len(xx) < 3 or np.std(xx) == 0 or np.std(yy) == 0:
                            boots.append(np.nan)
                            continue
                        rx, ry = rankdata(xx), rankdata(yy)
                        boots.append(float(np.corrcoef(rx, ry)[0, 1]))
                    boots = np.array(boots)
                    boots = boots[np.isfinite(boots)]
                    pic_ci = [round(float(np.percentile(boots, 2.5)), 4),
                              round(float(np.percentile(boots, 97.5)), 4)] if len(boots) >= 50 else None
                else:
                    pic_ci = None
                per_coin = []
                for j in range(len(COINS)):
                    col_p, col_y = Pv[:, j], Yv[:, j]
                    ic, nn = spearman_xy(col_p, col_y)
                    cidx = np.where(np.isfinite(col_p) & np.isfinite(col_y))[0]
                    ic_ci = boot_corr(col_p, col_y, cidx, L, B_BOOT, rng) if np.isfinite(ic) else None
                    per_coin.append({"coin": COINS[j],
                                     "ic": round(float(ic), 4) if np.isfinite(ic) else None,
                                     "n": int(nn), "ic_ci": ic_ci})
                valid = [c["ic"] for c in per_coin if c["ic"] is not None]
                ts_mean = round(float(np.mean(valid)), 4) if len(valid) == 4 else None
                ts_npos = int(sum(1 for v in valid if v > 0)) if len(valid) == 4 else 0
                xs_vals = xs_point(Pv, Yv)
                good = xs_vals[np.isfinite(xs_vals)]
                xs_mean = round(float(good.mean()), 4) if len(good) else None
                xs_std = round(float(good.std(ddof=1)), 4) if len(good) >= 2 else None
                xs_pos = round(float(np.mean(good > 0)), 4) if len(good) else None
                gidx = np.where(np.isfinite(xs_vals))[0]
                if len(gidx) >= L and len(good):
                    n = len(gidx)
                    nblocks = int(np.ceil(n / L))
                    arr = xs_vals[gidx]
                    mb = []
                    for bb in range(B_BOOT):
                        starts = rng.integers(0, n, size=nblocks)
                        sel = np.concatenate([(s + np.arange(L)) % n for s in starts])[:n]
                        mb.append(float(arr[sel].mean()))
                    xs_ci = [round(float(np.percentile(mb, 2.5)), 4),
                             round(float(np.percentile(mb, 97.5)), 4)]
                else:
                    xs_ci = None
                out_rows.append({
                    "series": sname, "year": a, "h": int(h), "L": int(L),
                    "n_bars": int(len(TIMES[sname])),
                    "pooled_ic": round(float(pic), 4) if np.isfinite(pic) else None,
                    "pooled_n": int(pn), "pooled_ci": pic_ci,
                    "per_coin": per_coin, "ts_mean": ts_mean, "ts_npos": ts_npos,
                    "xs_mean": xs_mean, "xs_std": xs_std, "xs_posfrac": xs_pos,
                    "xs_n": int(len(good)), "xs_ci": xs_ci,
                })
            part.write_text(json.dumps(out_rows))
            print(f"year {a} h={h}: wrote {len(out_rows)} series in {time.time()-t1:.0f}s "
                  f"(total {time.time()-t0:.0f}s)", flush=True)

    rows = []
    for a in ANCHORS:
        for h in HORIZONS:
            rows.extend(json.loads((PARTS / f"part_{a}_h{int(h)}.json").read_text()))
    out = {
        "meta": {
            "series": list(SERIES_ORDER),
            "series_def": "TV=rebuilt TV-only member stored pred (oc_presamplebook); "
                          "FLOW/PREMIUM/BLEND=rebuilt spot-flow / coinbase-premium / "
                          "stored 0.8/0.2 blend (oc_presampleflow). Rebuilt members, "
                          "NOT the deployed perp-flow blend.",
            "histories": "TV pre-sample anchors: spot 1m-built 4h; TV reference "
                         "anchors: perp 4h (BTC ma_ribbon, others xs_universe); "
                         "FLOW/PREMIUM/BLEND all anchors: stitched spot "
                         "(1m-built for t<2020-10-01 + spot_majors after). "
                         "Rebuilt opens match stored csv opens (max rel diff "
                         f"{maxdiff:.2e} < 1e-6).",
            "sigma": "std of 1-bar open-to-open simple returns over trailing 360 bars ending at t (min120, ddof1); target=fwd_h/sigma",
            "fwd": "open[t+h*4h]/open[t]-1 by timestamp, h in [1,2,6,18,42] 4h bars",
            "years": list(ANCHORS),
            "year_def": "exactly the stored rows of each preds file ([A,A+365d) with realised 7d label); identical test set across h",
            "pooled": "Spearman over stacked (bar,coin) rows in year",
            "ts": "per-coin Spearman over bars in year; ts_mean=mean of 4 coins (NaN if any coin NaN)",
            "xs": "per-bar Spearman across 4 coins (needs >=3 valid, non-constant), averaged over bars",
            "bootstrap": f"block bootstrap over bars, L=max(h,6), B={B_BOOT}, seed={SEED} "
                         "(independent per-(year,h) Generator streams, series in fixed order TV,FLOW,PREMIUM,BLEND)",
            "selection": "none (descriptive; no most-recent year stored)",
            "costs": "IC diagnostic only, no PnL/fees/funding",
            "yardstick": "identical to oc_bookichorizon (same target math, same B/L/seed family, same rank definition)",
        },
        "rows": rows,
    }
    (HERE / "results.json").write_text(json.dumps(out, indent=1))
    print(f"wrote results.json rows={len(rows)} in {time.time()-t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
