"""oc_bookoffset: volatility-scaled book entry offset vs fixed 10 bps.

Per PLAN.md (pre-registered): rebuilds forward_v205.research_books_d2 exactly,
joins with v154 4h opens, computes causal sigma4h (trailing 360-bar std,
windows ending strictly before the holding-bar open T), posts fixed 10 bps vs
vol-scaled offset = clip(0.10*sigma4h, [5,40] bps) limits around the minute-0
price, checks strict 1m trade-through fills in minutes [5,65), and scores the
one-holding-bar episode (exit at the next 4h open) to the episode end.
One coin at a time, float32 1m arrays, one process.

  python research/tournament/oc_bookoffset/compute_bookoffset.py
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
CACHE = ROOT / "artifacts/research/engine_real"
SYMS = ["BNBUSDT", "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]
ANCHORS = [pd.Timestamp(f"{y}-09-24", tz="UTC") for y in (2021, 2022, 2023, 2024, 2025)]
BOUND = pd.Timestamp("2026-09-24 00:00", tz="UTC")
WIN_START, WIN_END = 5, 65  # minutes [5,65): 60 resting bars
OFF_FIX = 0.001
OFF_MIN, OFF_MAX = 0.0005, 0.004
MAKER = 0.0002
FLAT_TOL = 1e-12


def research_books_d2() -> pd.DataFrame:
    """Mirror of scripts/forward_v205.py::research_books_d2 (same files, same math)."""
    m = lambda f: pd.read_parquet(CACHE / f)[SYMS]  # noqa: E731
    A, Aq = m("member_A_O1_orders.parquet"), m("member_Aq_O1_orders.parquet")
    B, Bq = m("member_B_tv.parquet"), m("member_Bq_tv.parquet")
    idx = A.index.union(Aq.index)
    f = lambda X: X.reindex(idx).fillna(0.0)  # noqa: E731
    o1 = 0.5 * (f(A) + f(B)) / 2 + 0.5 * (f(Aq) + f(Bq)) / 2
    D = pd.read_parquet(CACHE / "members_v154.parquet").xs("D", axis=1, level=0)[SYMS]
    Dq = pd.read_parquet(CACHE / "members_quarterly_D.parquet")[SYMS]
    idx2 = o1.index.union(D.index).union(Dq.index)
    g = lambda X: X.reindex(idx2).fillna(0.0)  # noqa: E731
    return 0.8 * g(o1) + 0.2 * (g(D) + g(Dq)) / 2


def sigma4h_at_T(opens_full: pd.DataFrame, T_grid: pd.DatetimeIndex) -> pd.DataFrame:
    """Trailing 360-bar std of 4h simple returns, windows ending strictly before T.

    sigma[T] = std(R[T-360*4h .. T-4h]), R[s] = O[s]/O[s-4h]-1, i.e.
    O.pct_change().rolling(360, min_periods=120).std().shift(1) at T.
    Uses only opens <= T-4h < T, hence known at the decision and at T.
    """
    ret = opens_full.pct_change()
    sig = ret.rolling(360, min_periods=120).std(ddof=1).shift(1)
    return sig.reindex(T_grid)


def load_1m_cube_one_coin(sym: str, T_grid: pd.DatetimeIndex, need: int = 65):
    """1m open/high/low for minutes [0,need) of each holding bar T (float32).

    Returns (O0, H, L) each (n, need) float32 with within-bar forward-fill from
    minute 0; minute-0 NaN stays NaN (event unscored). Also returns the
    originally-missing mask count per (i) in the fill window for the coverage
    rule (>10 originally missing -> unscored).
    """
    if sym == "BTCUSDT":
        files = sorted((ROOT / "data/raw/btc_intraday_20260924").glob("klines_1m_20*.parquet"))
    else:
        files = sorted((ROOT / f"data/raw/majors_intraday_20260924").glob(f"{sym}_1m_20*.parquet"))
    parts = []
    for f in files:
        df = pd.read_parquet(f, columns=["open_time", "open", "high", "low"])
        parts.append(df)
    m = pd.concat(parts, ignore_index=True)
    m["open_time"] = pd.to_datetime(m["open_time"], utc=True)
    m = m.drop_duplicates("open_time").sort_values("open_time")
    n = len(T_grid)
    O = np.full((n, need), np.nan, dtype=np.float32)
    H = np.full((n, need), np.nan, dtype=np.float32)
    L = np.full((n, need), np.nan, dtype=np.float32)
    pos = pd.Series(np.arange(n), index=T_grid)
    Tf = m["open_time"].dt.floor("4h")
    # map only rows that could belong to a scored bar's first `need` minutes
    mi = pos.reindex(Tf).to_numpy()
    off = ((m["open_time"] - Tf).dt.total_seconds().to_numpy() // 60).astype(int)
    ok = ~np.isnan(mi) & (off >= 0) & (off < need)
    ii = mi[ok].astype(int)
    oo = off[ok]
    O[ii, oo] = m["open"].to_numpy(float)[ok]
    H[ii, oo] = m["high"].to_numpy(float)[ok]
    L[ii, oo] = m["low"].to_numpy(float)[ok]
    # originally-missing count in the fill window before forward-fill
    miss_win = np.isnan(H[:, WIN_START:WIN_END]).sum(axis=1) + np.isnan(L[:, WIN_START:WIN_END]).sum(axis=1)
    miss_win = miss_win // 2  # H and L missing together; count bars
    # within-bar forward-fill from minute 0
    for mm in range(1, need):
        for X in (O, H, L):
            miss = np.isnan(X[:, mm])
            X[miss, mm] = X[miss, mm - 1]
    return O, H, L, miss_win


def main() -> None:
    books = research_books_d2()
    opens_full = pd.read_parquet(CACHE / "opens_v154.parquet")
    # decision grid t (books x opens inner join)
    grid_t = books.index.intersection(opens_full.dropna(how="all").index).sort_values()
    # holding-bar opens T = t+4h, exits X = T+4h; require T in range and X <= BOUND
    T_all = grid_t + pd.Timedelta(hours=4)
    X_all = T_all + pd.Timedelta(hours=4)
    keep = (T_all >= ANCHORS[0]) & (T_all < BOUND) & (X_all <= BOUND)
    grid_t = grid_t[keep]
    T_grid = T_all[keep]
    X_grid = X_all[keep]
    books = books.reindex(grid_t).sort_index()
    # 4h opens at T and X (per coin, full history for sigma)
    O_T = opens_full.reindex(T_grid)
    O_X = opens_full.reindex(X_grid)
    sig = sigma4h_at_T(opens_full[SYMS], T_grid)

    # year masks by T in [A_k, A_k+365d)
    bounds = [(a0, a0 + pd.Timedelta(days=365)) for a0 in ANCHORS]
    year_of = np.full(len(T_grid), -1, dtype=int)
    for k, (s, e) in enumerate(bounds):
        year_of[(T_grid >= s) & (T_grid < e)] = k
    orphans = int((year_of < 0).sum())

    rows = []  # one row per scored (coin, bar) attempt, both rules share the attempt
    off_vol_dist, sig_dist = [], []
    clip_lo = clip_hi = 0
    n_vol_fallback = 0
    unscored = 0
    for sym in SYMS:
        w = books[sym].to_numpy(float)
        oT = O_T[sym].to_numpy(float)
        oX = O_X[sym].to_numpy(float)
        sg = sig[sym].to_numpy(float)
        O0, H, L, miss_win = load_1m_cube_one_coin(sym, T_grid)
        p0_1m = O0[:, 0].astype(float)
        # P0 = 1m minute-0 open, fallback to 4h open
        P0 = np.where(np.isfinite(p0_1m), p0_1m, oT)
        off_vol = np.clip(0.10 * sg, OFF_MIN, OFF_MAX)
        fb = ~np.isfinite(sg)
        off_vol[fb] = OFF_FIX
        n_vol_fallback += int(fb.sum())
        # clipping shares among finite-sigma bars
        fin = np.isfinite(sg)
        clip_lo += int(((0.10 * sg[fin]) < OFF_MIN).sum())
        clip_hi += int(((0.10 * sg[fin]) > OFF_MAX).sum())
        off_vol_dist.extend(list(off_vol[fin]))
        sig_dist.extend(list(sg[fin]))
        for i in range(len(T_grid)):
            if abs(w[i]) < FLAT_TOL:
                continue
            if not (np.isfinite(P0[i]) and np.isfinite(oX[i]) and P0[i] > 0 and oX[i] > 0):
                unscored += 1
                continue
            if not np.isfinite(O0[i, 0]):
                # minute-0 missing and 4h fallback used? P0 fallback ok, but fill
                # needs 1m window; if minute-0 1m missing the ffill base is gone
                unscored += 1
                continue
            if miss_win[i] > 10:
                unscored += 1
                continue
            if year_of[i] < 0:
                continue  # leap-gap orphan (counted separately)
            side = 1.0 if w[i] > 0 else -1.0
            for name, off in (("fix", OFF_FIX), ("vol", float(off_vol[i]))):
                lim = P0[i] * (1 - side * off)
                if side > 0:
                    win = L[i, WIN_START:WIN_END] < lim
                else:
                    win = H[i, WIN_START:WIN_END] > lim
                filled = bool(np.isfinite(lim) and win.any())
                fill_m = int(np.argmax(win)) + WIN_START if filled else -1
                E = lim if filled else np.nan
                gross = float(w[i] * (oX[i] / E - 1)) if filled else 0.0
                net = float(gross - abs(w[i]) * MAKER) if filled else 0.0
                hyp = float(w[i] * (oX[i] / P0[i] - 1))
                rows.append(dict(sym=sym, T=str(T_grid[i]), year=int(year_of[i]),
                                 w=float(w[i]), side=int(side), P0=float(P0[i]),
                                 PX=float(oX[i]), sigma=float(sg[i]) if np.isfinite(sg[i]) else None,
                                 rule=name, off_bps=round(off * 1e4, 4),
                                 filled=int(filled), fill_m=int(fill_m),
                                 gross=round(gross, 8), net=round(net, 8), hyp=round(hyp, 8)))
    ev = pd.DataFrame(rows)
    # per (rule, year) aggregates
    per_rule = {}
    for rule in ("fix", "vol"):
        d = ev[ev.rule == rule]
        years = []
        for k, a0 in enumerate(ANCHORS):
            dd = d[d.year == k]
            att = len(dd)
            fl = int(dd.filled.sum()) if att else 0
            fr = round(fl / att, 6) if att else None
            mo_att = round(float(dd.off_bps.mean()), 4) if att else None
            mfl = dd[dd.filled == 1]
            mo_fl = round(float(mfl.off_bps.mean()), 4) if len(mfl) else None
            fg = round(float(mfl.gross.sum()), 6) if att else 0.0
            fn = round(float(mfl.net.sum()), 6) if att else 0.0
            mh = round(float(dd[dd.filled == 0].hyp.sum()), 6) if att else 0.0
            # compounded year return over bar-level net (bars in time order)
            if att:
                bar = mfl.groupby("T")["net"].sum() if len(mfl) else pd.Series(dtype=float)
                # include zero bars implicitly (prod unaffected)
                eq = float(np.prod(1.0 + bar.to_numpy())) - 1.0 if len(bar) else 0.0
                comp = round(eq, 6)
            else:
                comp = 0.0
            years.append(dict(year=str(a0.date()), attempted=int(att), filled=int(fl),
                              fill_rate=fr, mean_off_attempted_bps=mo_att,
                              mean_off_filled_bps=mo_fl, filled_gross=fg,
                              filled_net=fn, missed_hyp=round(float(mh), 6),
                              total_net=fn, compounded=comp))
        tot = round(float(d[d.filled == 1].net.sum()), 6) if len(d) else 0.0
        per_rule[rule] = dict(per_year=years, total_net_5y=tot,
                              attempted_5y=int(len(d[d.filled == 1]) + len(d[d.filled == 0])),
                              filled_5y=int(d.filled.sum()) if len(d) else 0)

    effects, loyo = [], []
    fix_tot = [r["total_net"] for r in per_rule["fix"]["per_year"]]
    vol_tot = [r["total_net"] for r in per_rule["vol"]["per_year"]]
    for k in range(5):
        a, b = fix_tot[k], vol_tot[k]
        if a is None or b is None or not np.isfinite(a) or not np.isfinite(b):
            effects.append(None)
        else:
            effects.append(round(float(b - a), 6))
    for h in range(5):
        tr = [e for k, e in enumerate(effects) if k != h and e is not None]
        if len(tr) == 4 and effects[h] is not None:
            mtr = float(np.mean(tr))
            loyo.append(bool(mtr > 0 and np.sign(effects[h]) == np.sign(mtr)))
        else:
            loyo.append(False)
    n_pos = sum(1 for e in effects if e is not None and e > 0)
    promising = bool(n_pos >= 4)
    decision = dict(d_net=effects, loyo=[bool(x) for x in loyo],
                    loyo_pass=f"{sum(loyo)}/5", pos_years=f"{n_pos}/5",
                    promising=promising,
                    first4_pos=f"{sum(1 for e in effects[:4] if e is not None and e > 0)}/4")

    out = {
        "definitions": ("grid=books_d2 x opens_v154 inner join, decision t, holding T=t+4h, exit X=T+4h, "
                        "scored T in [2021-09-24,2026-09-24) with X<=BOUND; sigma4h[T]=std(R[T-360*4h..T-4h]) "
                        "ddof=1 min120 (pct_change rolling 360 shift 1), NaN->10bps; off_fix=10bps, "
                        "off_vol=clip(0.10*sigma,[5,40]bps); L=P0*(1-side*off), P0=1m minute-0 open "
                        "(fallback 4h); fill buy low[5:65)<L / sell high[5:65)>L strict; "
                        "episode=[T,X), PX=4h open at X; filled gross=w*(PX/L-1), net=gross-|w|*0.0002, "
                        "missed actual 0 hyp=w*(PX/P0-1); year k=T in [A_k,A_k+365d); "
                        "PROMISING iff vol total_net>fix in >=4/5 years"),
        "symbols": SYMS,
        "anchor_years": [str(a.date()) for a in ANCHORS],
        "grid_T_start": str(T_grid.min()), "grid_T_end": str(T_grid.max()),
        "n_T_bars": int(len(T_grid)), "orphan_T_bars": int(orphans),
        "n_attempted_events": int(len(ev) // 2), "n_scored_rows": int(len(ev)),
        "unscored_missing": int(unscored),
        "vol_fallback_sigma_nan": int(n_vol_fallback),
        "sigma4h_summary": dict(mean=round(float(np.mean(sig_dist)), 6) if sig_dist else None,
                                p5=round(float(np.quantile(sig_dist, 0.05)), 6) if sig_dist else None,
                                p50=round(float(np.quantile(sig_dist, 0.50)), 6) if sig_dist else None,
                                p95=round(float(np.quantile(sig_dist, 0.95)), 6) if sig_dist else None),
        "off_vol_bps_summary": dict(mean=round(float(np.mean(off_vol_dist) * 1e4), 3) if off_vol_dist else None,
                                    p5=round(float(np.quantile(off_vol_dist, 0.05) * 1e4), 3) if off_vol_dist else None,
                                    p50=round(float(np.quantile(off_vol_dist, 0.50) * 1e4), 3) if off_vol_dist else None,
                                    p95=round(float(np.quantile(off_vol_dist, 0.95) * 1e4), 3) if off_vol_dist else None,
                                    clip_lo_share=round(clip_lo / max(len(sig_dist), 1), 4),
                                    clip_hi_share=round(clip_hi / max(len(sig_dist), 1), 4)),
        "per_rule": per_rule, "decision": decision,
    }
    (HERE / "results.json").write_text(json.dumps(out, indent=1))
    print(json.dumps({"decision": decision,
                      "fix_total_5y": per_rule["fix"]["total_net_5y"],
                      "vol_total_5y": per_rule["vol"]["total_net_5y"],
                      "fix_fill": round(per_rule["fix"]["filled_5y"] / max(per_rule["fix"]["attempted_5y"], 1), 4),
                      "vol_fill": round(per_rule["vol"]["filled_5y"] / max(per_rule["vol"]["attempted_5y"], 1), 4)}, indent=1))


if __name__ == "__main__":
    main()
