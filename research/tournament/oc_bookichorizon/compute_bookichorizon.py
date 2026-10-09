"""oc_bookichorizon: at which horizon does the DEPLOYED book's skill live?

Descriptive only (see PLAN.md, pre-registered 2026-10-07). Uses the CACHED
research predictions of the deployed members and the final blended book
weights (after the bear filter) on the standard grid, 2021-09-24 .. 2026-09-23.
Per year x member x horizon h in {1,2,6,18,42}: Spearman IC of prediction vs
vol-normalised forward open-to-open return, pooled / per-coin (TS) /
cross-sectional (XS, ranks across 5 coins per bar, averaged), plus sign hit
rates, all with block bootstrap CIs (block = max(h,6), B = 500, seed 7).

Light: 4h parquets only, no 1m, no GPU. Run:
  .venv/Scripts/python.exe research/tournament/oc_bookichorizon/compute_bookichorizon.py
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
CACHE = ROOT / "artifacts/research/engine_real"
PARTS = HERE / "tmp" / "parts"
SYMS = ["BNBUSDT", "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]
HORIZONS = (1, 2, 6, 18, 42)
SERIES_ORDER = ("A", "Aq", "B", "Bq", "D", "Dq", "O1", "CB", "FULL", "FINAL")
ANCHORS = [pd.Timestamp(f"{y}-09-24", tz="UTC") for y in (2021, 2022, 2023, 2024, 2025)]
YEAR_LEN = pd.Timedelta(days=365)
B_BOOT = 500
SEED = 7


def load_series():
    m = lambda f: pd.read_parquet(CACHE / f)[SYMS]  # noqa: E731
    A = m("member_A_O1_orders.parquet")
    Aq = m("member_Aq_O1_orders.parquet")
    B = m("member_B_tv.parquet")
    Bq = m("member_Bq_tv.parquet")
    D = pd.read_parquet(CACHE / "members_v154.parquet").xs("D", axis=1, level=0)[SYMS]
    Dq = m("members_quarterly_D.parquet")
    books_std = pd.read_parquet(CACHE / "books_v154.parquet")[SYMS]
    opens_full = pd.read_parquet(CACHE / "opens_v154.parquet")[SYMS].sort_index()
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
    return series, std_idx, opens_full, opens_std, bear


def build_targets(opens_full, std_idx):
    opens_full = opens_full.sort_index()
    r1_full = opens_full / opens_full.shift(1) - 1.0
    sigma_full = r1_full.rolling(360, min_periods=120).std(ddof=1)
    sigma = sigma_full.reindex(std_idx)
    tgt = {}
    for h in HORIZONS:
        ahead_idx = std_idx + pd.Timedelta(hours=4 * h)
        o_t = opens_full.reindex(std_idx)
        o_th = opens_full.reindex(ahead_idx)
        fh = o_th.to_numpy() / o_t.to_numpy() - 1.0
        fh = pd.DataFrame(fh, index=std_idx, columns=SYMS)
        sg = sigma
        with np.errstate(divide="ignore", invalid="ignore"):
            yh = fh / sg
        yh[(sg.isna()) | (sg <= 0) | (fh.isna())] = np.nan
        tgt[h] = yh
    return sigma, tgt


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
    """Block-bootstrap Spearman CI for vectors x, y given valid positions idx."""
    n = len(idx)
    if n < L:
        return None
    nblocks = int(np.ceil(n / L))
    xv, yv = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
    boots = np.empty(B)
    boots[:] = np.nan
    for b in range(B):
        starts = rng.integers(0, n, size=nblocks)
        sel = np.concatenate([(starts + np.arange(L)) % n for starts in starts])[:n]
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


def boot_hit(p, y, idx, L, B, rng):
    n = len(idx)
    if n < 1:
        return None
    nblocks = int(np.ceil(n / L))
    pv, yv = np.asarray(p, dtype=float), np.asarray(y, dtype=float)
    hb = np.empty(B)
    hb[:] = np.nan
    for b in range(B):
        starts = rng.integers(0, n, size=nblocks)
        sel = np.concatenate([(starts + np.arange(L)) % n for starts in starts])[:n]
        sel = idx[sel]
        a, cc = pv[sel], yv[sel]
        m = np.isfinite(a) & np.isfinite(cc) & (a != 0) & (cc != 0)
        if int(m.sum()) == 0:
            continue
        hb[b] = np.mean(np.sign(a[m]) == np.sign(cc[m]))
    ok = hb[np.isfinite(hb)]
    if len(ok) < 50:
        return None
    return [round(float(np.percentile(ok, 2.5)), 4), round(float(np.percentile(ok, 97.5)), 4)]


def xs_point(Pv, Yv):
    """Vectorised XS point stats for an (n,5) year block. Returns dict."""
    n = Pv.shape[0]
    fin = np.isfinite(Pv) & np.isfinite(Yv)
    nvalid = fin.sum(axis=1)
    full = nvalid == 5
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
        # rows where pred or target constant across 5 -> std 0 -> nan already;
        # also need per-row std of raw values > 0 check (rank std 0 covers it)
    # partial rows (rare: tail of h=42 in Y4): loop the few
    part = np.where(~full & (nvalid >= 3))[0]
    for i in part:
        pv, yv = Pv[i], Yv[i]
        m = np.isfinite(pv) & np.isfinite(yv)
        if np.std(pv[m]) == 0.0 or np.std(yv[m]) == 0.0:
            continue
        ic, _ = spearman_xy(pv[m], yv[m])
        xs_vals[i] = ic
    good = xs_vals[np.isfinite(xs_vals)]
    # XS hits vectorised
    hm = fin & (Pv != 0) & (Yv != 0)
    hcount = hm.sum(axis=1)
    eq = (np.sign(Pv) == np.sign(Yv)) & hm
    xh = np.full(n, np.nan)
    has = hcount >= 1
    xh[has] = eq[has].sum(axis=1) / hcount[has]
    return xs_vals, xh


def main():
    t0 = time.time()
    PARTS.mkdir(parents=True, exist_ok=True)
    print("oc_bookichorizon: loading caches ...", flush=True)
    series, std_idx, opens_full, opens_std, bear = load_series()
    print(f"grid {std_idx.min()} .. {std_idx.max()} rows={len(std_idx)} "
          f"bear_frac={round(float(bear.mean()), 4)}", flush=True)
    sigma, tgt = build_targets(opens_full, std_idx)
    print(f"targets built horizons={list(HORIZONS)} "
          f"sigma_cov={round(float(sigma.notna().all(axis=1).mean()), 4)} "
          f"in {time.time()-t0:.0f}s", flush=True)
    P_all = {k: v.to_numpy() for k, v in series.items()}
    Y_all = {h: tgt[h].to_numpy() for h in HORIZONS}

    bounds = ANCHORS + [ANCHORS[-1] + YEAR_LEN]
    for yi, a0 in enumerate(ANCHORS):
        ylab = str(a0.date())
        ymask = np.asarray((std_idx >= a0) & (std_idx < bounds[yi + 1]))
        ypos = np.where(ymask)[0]
        for h in HORIZONS:
            part = PARTS / f"part_{ylab}_h{int(h)}.json"
            if part.exists():
                print(f"year {ylab} h={h}: cached, skip", flush=True)
                continue
            t1 = time.time()
            L = max(int(h), 6)
            rng = np.random.default_rng((SEED, yi, int(h)))
            Yv_full = Y_all[h][ypos]
            out_rows = []
            for sname in SERIES_ORDER:
                Pv = P_all[sname][ypos]
                Yv = Yv_full
                pm = np.isfinite(Pv) & np.isfinite(Yv)
                pic, pn = spearman_xy(Pv[pm], Yv[pm])
                pidx = np.where(pm.any(axis=1))[0]
                hm_all = pm & (Pv != 0) & (Yv != 0)
                phit = float(np.mean(np.sign(Pv[hm_all]) == np.sign(Yv[hm_all]))) if int(hm_all.sum()) else float("nan")
                hidx_all = np.where(hm_all.any(axis=1))[0]
                # Pooled bootstrap resamples BARS (bar structure preserved).
                if np.isfinite(pic) and len(pidx) >= L:
                    n = len(pidx)
                    nblocks = int(np.ceil(n / L))
                    boots = []
                    for b in range(B_BOOT):
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
                if np.isfinite(phit) and len(hidx_all) >= 1:
                    n = len(hidx_all)
                    nblocks = int(np.ceil(n / L))
                    hb = []
                    for b in range(B_BOOT):
                        starts = rng.integers(0, n, size=nblocks)
                        sel = hidx_all[np.concatenate([(s + np.arange(L)) % n for s in starts])[:n]]
                        a, cc = Pv[sel].ravel(), Yv[sel].ravel()
                        m = np.isfinite(a) & np.isfinite(cc) & (a != 0) & (cc != 0)
                        hb.append(float(np.mean(np.sign(a[m]) == np.sign(cc[m]))) if int(m.sum()) else np.nan)
                    hb = np.array(hb)
                    hb = hb[np.isfinite(hb)]
                    phit_ci = [round(float(np.percentile(hb, 2.5)), 4),
                               round(float(np.percentile(hb, 97.5)), 4)] if len(hb) >= 50 else None
                else:
                    phit_ci = None

                per_coin = []
                for j in range(len(SYMS)):
                    col_p, col_y = Pv[:, j], Yv[:, j]
                    ic, nn = spearman_xy(col_p, col_y)
                    hm = np.isfinite(col_p) & np.isfinite(col_y) & (col_p != 0) & (col_y != 0)
                    hit = float(np.mean(np.sign(col_p[hm]) == np.sign(col_y[hm]))) if int(hm.sum()) else float("nan")
                    cidx = np.where(np.isfinite(col_p) & np.isfinite(col_y))[0]
                    ic_ci = boot_corr(col_p, col_y, cidx, L, B_BOOT, rng) if np.isfinite(ic) else None
                    hidx = np.where(hm)[0]
                    hit_ci = boot_hit(col_p, col_y, hidx, L, B_BOOT, rng) if np.isfinite(hit) else None
                    per_coin.append({"coin": SYMS[j],
                                     "ic": round(float(ic), 4) if np.isfinite(ic) else None,
                                     "n": int(nn), "ic_ci": ic_ci,
                                     "hit": round(float(hit), 4) if np.isfinite(hit) else None,
                                     "hit_n": int(hm.sum()), "hit_ci": hit_ci})
                valid_ics = []
                for c in per_coin:
                    if c["ic"] is not None:
                        valid_ics.append(c["ic"])
                ts_mean = round(float(np.mean(valid_ics)), 4) if len(valid_ics) == 5 else None

                xs_vals, xh = xs_point(Pv, Yv)
                good = xs_vals[np.isfinite(xs_vals)]
                xs_mean = round(float(good.mean()), 4) if len(good) else None
                xs_std = round(float(good.std(ddof=1)), 4) if len(good) >= 2 else None
                xs_pos = round(float(np.mean(good > 0)), 4) if len(good) else None
                xgood = xh[np.isfinite(xh)]
                xsh_mean = round(float(xgood.mean()), 4) if len(xgood) else None
                gidx = np.where(np.isfinite(xs_vals))[0]
                if len(gidx) >= L and len(good):
                    n = len(gidx)
                    nblocks = int(np.ceil(n / L))
                    arr = xs_vals[gidx]
                    mb = []
                    for b in range(B_BOOT):
                        starts = rng.integers(0, n, size=nblocks)
                        sel = np.concatenate([(s + np.arange(L)) % n for s in starts])[:n]
                        mb.append(float(arr[sel].mean()))
                    xs_ci = [round(float(np.percentile(mb, 2.5)), 4), round(float(np.percentile(mb, 97.5)), 4)]
                else:
                    xs_ci = None
                hidx2 = np.where(np.isfinite(xh))[0]
                if len(hidx2) >= 1 and len(xgood):
                    n = len(hidx2)
                    nblocks = int(np.ceil(n / L))
                    arr = xh[hidx2]
                    mb = []
                    for b in range(B_BOOT):
                        starts = rng.integers(0, n, size=nblocks)
                        sel = np.concatenate([(s + np.arange(L)) % n for s in starts])[:n]
                        mb.append(float(arr[sel].mean()))
                    xsh_ci = [round(float(np.percentile(mb, 2.5)), 4), round(float(np.percentile(mb, 97.5)), 4)]
                else:
                    xsh_ci = None

                out_rows.append({
                    "series": sname, "year": ylab, "h": int(h), "L": int(L),
                    "n_bars": int(len(ypos)),
                    "pooled_ic": round(float(pic), 4) if np.isfinite(pic) else None,
                    "pooled_n": int(pn), "pooled_ci": pic_ci,
                    "pooled_hit": round(float(phit), 4) if np.isfinite(phit) else None,
                    "pooled_hit_n": int(hm_all.sum()), "pooled_hit_ci": phit_ci,
                    "per_coin": per_coin, "ts_mean": ts_mean,
                    "xs_mean": xs_mean, "xs_std": xs_std, "xs_posfrac": xs_pos,
                    "xs_n": int(len(good)), "xs_ci": xs_ci,
                    "xs_hit": xsh_mean, "xs_hit_nbars": int(len(xgood)), "xs_hit_ci": xsh_ci,
                })
            part.write_text(json.dumps(out_rows))
            print(f"year {ylab} h={h}: wrote {len(out_rows)} series in {time.time()-t1:.0f}s "
                  f"(total {time.time()-t0:.0f}s)", flush=True)

    rows = []
    for yi, a0 in enumerate(ANCHORS):
        ylab = str(a0.date())
        for h in HORIZONS:
            part = PARTS / f"part_{ylab}_h{int(h)}.json"
            rows.extend(json.loads(part.read_text()))
    out = {
        "meta": {
            "series": list(SERIES_ORDER),
            "series_def": "A/Aq/B/Bq/D/Dq cached members reindexed to books_v154 grid fillna 0; "
                          "O1=(A+Aq+B+Bq)/4; CB=(D+Dq)/2; FULL=0.8*O1+0.2*CB; "
                          "FINAL=FULL with v421 x0.5 bear filter on longs "
                          "(bear=BTCopen<trailing1200-mean, min600)",
            "grid": f"{std_idx.min()} .. {std_idx.max()} rows={len(std_idx)}",
            "opens": "opens_v154 (full 2017.. history for sigma; forwards by timestamp t+h*4h)",
            "sigma": "std of 1-bar open-to-open simple returns over trailing 360 bars ending at t (min120, ddof1); target=fwd_h/sigma",
            "fwd": "open[t+h]/open[t]-1, h in [1,2,6,18,42] 4h bars",
            "years": [str(a.date()) for a in ANCHORS],
            "year_def": "[A, A+365d) on grid timestamp; last year 2025-09-24..2026-09-23 labelled most-recent",
            "pooled": "Spearman over stacked (bar,coin) rows in year",
            "ts": "per-coin Spearman over bars in year; ts_mean=mean of 5 coins",
            "xs": "per-bar Spearman across 5 coins (needs >=3 valid, non-constant), averaged over bars",
            "hit": "sign agreement on rows with pred!=0 and target!=0 (pooled/per-coin/XS-bar-fraction)",
            "bootstrap": f"block bootstrap over bars, L=max(h,6), B={B_BOOT}, seed={SEED} "
                         f"(independent per-(year,h) Generator streams for checkpoint resume; same distribution)",
            "selection": "none (descriptive; most-recent year labelled, never used to choose)",
            "costs": "IC diagnostic only, no PnL/fees/funding",
        },
        "rows": rows,
    }
    (HERE / "results.json").write_text(json.dumps(out, indent=1))
    print(f"wrote results.json rows={len(rows)} in {time.time()-t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
