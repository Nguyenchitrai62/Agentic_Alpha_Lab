"""oc_dvolshort: DVOL gate on BOOK SHORTS (idea #13, pre-registered in PLAN.md).

Per PLAN.md: rebuild forward_v205.research_books_d2 exactly, join with the
v154 4h opens, compute dvol_z90 EXACTLY as oc_dvolbook defines it
(as-of = last hourly DVOL bar with END <= T; z vs trailing 2160 asof
samples, current excluded), walk-forward q67 per year from strictly
previous data, gate per (T,sym): short rows with z > q67 -> weight x0.5.
Screen with open-to-open 4h returns and gate costs (maker 0.0002 per unit
turnover). Single light process (4h + hourly DVOL only, no 1m).

  python research/tournament/oc_dvolshort/compute_dvolshort.py
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
CACHE = ROOT / "artifacts/research/engine_real"
OC_DVOL = ROOT / "research/tournament/oc_dvol"

SYMS = ["BNBUSDT", "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]
COINMAP = {"BTCUSDT": "BTC", "ETHUSDT": "ETH", "SOLUSDT": "BTC",
           "BNBUSDT": "BTC", "XRPUSDT": "BTC"}
ANCHORS = [pd.Timestamp(f"{y}-09-24", tz="UTC") for y in (2021, 2022, 2023, 2024, 2025)]
LAST_BOUND = ANCHORS[-1] + pd.Timedelta(days=365)
FEAT_START = pd.Timestamp("2021-06-30", tz="UTC")
CUTOFF = pd.Timestamp("2026-09-24", tz="UTC")
MAKER = 0.0002
NS = 1_000_000_000
H = 3_600 * NS


def research_books_d2() -> pd.DataFrame:
    """Mirror of oc_bookic.compute_bookic.research_books_d2 (same files, same math)."""
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


def load_dvol() -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """Per mapped coin: (bar_END_ns sorted int64, closes float64), t < CUTOFF."""
    panel = pd.read_parquet(OC_DVOL / "dvol_hourly.parquet")
    panel = panel[panel["t"] < CUTOFF].copy()
    out = {}
    for sym, cur in (("BTCDVOL", "BTC"), ("ETHDVOL", "ETH")):
        g = panel[panel["sym"] == sym].sort_values("t")
        ends = (g["t"] + pd.Timedelta(hours=1)).to_numpy(dtype="datetime64[ns]").astype(np.int64)
        out[cur] = (ends, g["close"].to_numpy(float))
    return out


def z90_for_times(Tns: np.ndarray, dvol) -> dict[str, np.ndarray]:
    """dvol_z90 per unique decision time, per mapped coin (exactly oc_dvolbook math).

    Fast exact equivalent: DVOL hourly ends are a gap-free hourly grid, so
    asof(T-k*1h) is the hourly close at end == T-k*1h and W is the 2160
    closes before the as-of bar. Rolling(2160, min_periods=1728).mean/std
    shifted by one reproduces the loop's cnt/mean/std (ddof=1) exactly.
    """
    out = {}
    for cur in ("BTC", "ETH"):
        ends, cl = dvol[cur]
        s = pd.Series(cl, index=pd.to_datetime(ends, utc=True, unit="ns")).sort_index()
        roll_mean = s.rolling(2160, min_periods=1728).mean()
        roll_std = s.rolling(2160, min_periods=1728).std(ddof=1)
        rm = roll_mean.to_numpy(float)
        rs = roll_std.to_numpy(float)
        cc = s.to_numpy(float)
        j = np.searchsorted(ends, Tns, side="right") - 1
        v0 = np.full(len(Tns), np.nan)
        mean = np.full(len(Tns), np.nan)
        std = np.full(len(Tns), np.nan)
        ok = j >= 0
        v0[ok] = cc[j[ok]]
        has_prev = j >= 1
        mean[has_prev] = rm[j[has_prev] - 1]
        std[has_prev] = rs[j[has_prev] - 1]
        std[std == 0] = np.nan
        out[cur] = (v0 - mean) / std
    return out


def max_dd(equity: np.ndarray) -> float:
    eq = np.asarray(equity, dtype=float)
    if len(eq) == 0:
        return float("nan")
    peak = np.maximum.accumulate(eq)
    dd = 1.0 - eq / peak
    return float(np.max(dd))


def worst_week(equity: np.ndarray) -> float:
    eq = np.asarray(equity, dtype=float)
    if len(eq) < 43:
        return float(eq[-1] / eq[0] - 1.0) if len(eq) > 1 else 0.0
    rets = eq[42:] / eq[:-42] - 1.0
    return float(np.min(rets))


def equity_path(rp: np.ndarray) -> np.ndarray:
    rp = np.asarray(rp, dtype=float)
    return np.concatenate([[1.0], np.cumprod(1.0 + rp)])


def main() -> None:
    dvol = load_dvol()
    books = research_books_d2()
    opens_full = pd.read_parquet(CACHE / "opens_v154.parquet")
    opens = opens_full.reindex(books.index)
    grid = books.index.intersection(opens.dropna(how="all").index)
    grid = grid[(grid >= ANCHORS[0]) & (grid < CUTOFF)].sort_values()
    books, opens = books.reindex(grid), opens.reindex(grid)

    o = opens[SYMS]
    ot = opens.index
    fwd1 = o.shift(-1) / o - 1.0
    exit1_ok = (ot.shift(-1) <= CUTOFF)
    keep = exit1_ok
    books, opens = books[keep], opens[keep]
    fwd1 = fwd1.reindex(books.index)
    valid1 = fwd1.notna().all(axis=1)
    books, opens = books[valid1], opens[valid1]
    fwd1 = fwd1.reindex(books.index)
    grid = books.index
    print(f"book grid: {len(grid)} bars {grid.min()}..{grid.max()}", flush=True)

    pre = opens_full.index[(opens_full.index >= FEAT_START) & (opens_full.index < ANCHORS[0])].sort_values()
    T_all = pre.union(grid).sort_values()
    Tns = T_all.to_numpy(dtype="datetime64[ns]").astype(np.int64)
    zfeat = z90_for_times(Tns, dvol)
    Z = {}
    for s in SYMS:
        Z[s] = pd.Series(zfeat[COINMAP[s]], index=T_all)

    rows = []
    for s in SYMS:
        rows.append(pd.DataFrame({
            "T": grid, "sym": s,
            "w": books[s].to_numpy(float),
            "r1": fwd1[s].reindex(grid).to_numpy(float),
            "z": Z[s].reindex(grid).to_numpy(float),
        }))
    panel = pd.concat(rows, ignore_index=True)
    panel["T"] = pd.to_datetime(panel["T"], utc=True)

    pool_rows = []
    for s in SYMS:
        pool_rows.append(pd.DataFrame({
            "T": T_all, "sym": s,
            "z": Z[s].to_numpy(float),
        }))
    pool = pd.concat(pool_rows, ignore_index=True)
    pool["T"] = pd.to_datetime(pool["T"], utc=True)
    pT = pool["T"].to_numpy()
    px = pool["z"].to_numpy(float)

    w = panel["w"].to_numpy(float)
    r1 = panel["r1"].to_numpy(float)
    z = panel["z"].to_numpy(float)
    T = panel["T"].to_numpy()
    sym = panel["sym"].to_numpy()

    bounds = ANCHORS + [LAST_BOUND]
    year_m = [((panel["T"] >= bounds[k]) & (panel["T"] < bounds[k + 1])).to_numpy()
              for k in range(5)]

    q67 = []
    pTs = pd.to_datetime(pool["T"], utc=True)
    for k, a0 in enumerate(ANCHORS):
        tr = ((pTs >= FEAT_START) & (pTs < a0)).to_numpy() & np.isfinite(px)
        assert int(tr.sum()) >= 100, f"year {k}: only {int(tr.sum())} training values"
        q67.append(float(np.quantile(px[tr], 2 / 3)))

    gated_mask = np.zeros(len(panel), dtype=bool)
    w_g = w.copy()
    for k in range(5):
        m = year_m[k] & (w < 0) & np.isfinite(z) & (z > q67[k])
        gated_mask[m] = True
    w_g[gated_mask] = 0.5 * w[gated_mask]

    # Turnover costs in grid order per sym (first bar prev = 0).
    cost = np.zeros(len(panel))
    cost_g = np.zeros(len(panel))
    for s in SYMS:
        sm = sym == s
        idx = np.where(sm)[0]
        # panel rows are blocked by sym, but sort by T within sym for safety
        order = np.argsort(T[idx])
        ii = idx[order]
        ww = w[ii]
        gg = w_g[ii]
        prev_w = np.concatenate([[0.0], ww[:-1]])
        prev_g = np.concatenate([[0.0], gg[:-1]])
        cost[ii] = MAKER * np.abs(ww - prev_w)
        cost_g[ii] = MAKER * np.abs(gg - prev_g)

    pnl = w * r1 - cost
    pnl_g = w_g * r1 - cost_g
    panel["w_g"] = w_g
    panel["gated"] = gated_mask
    panel["cost"] = cost
    panel["cost_g"] = cost_g
    panel["pnl"] = pnl
    panel["pnl_g"] = pnl_g
    panel.to_parquet(HERE / "panel.parquet")

    years = []
    dd_wins = 0
    pnl_wins = 0
    bar = panel.groupby("T", sort=True)[["pnl", "pnl_g"]].sum().sort_index()
    bar_idx = bar.index
    for k, a0 in enumerate(ANCHORS):
        m = year_m[k]
        sel = (bar_idx >= bounds[k]) & (bar_idx < bounds[k + 1])
        sel = np.asarray(sel)
        rp = bar["pnl"].to_numpy()[sel]
        rp_g = bar["pnl_g"].to_numpy()[sel]
        eq = equity_path(rp)
        eq_g = equity_path(rp_g)
        dd, dd_g = max_dd(eq), max_dd(eq_g)
        ww, ww_g = worst_week(eq), worst_week(eq_g)
        short_m = m & (w < 0)
        row = {
            "year": str(a0.date()),
            "q67": round(q67[k], 6),
            "coverage": round(float(np.isfinite(z[m]).mean()), 6),
            "n_rows": int(m.sum()),
            "n_short": int(short_m.sum()),
            "share_short_gated": round(float(gated_mask[short_m].mean()) if short_m.sum() else 0.0, 6),
            "short_pnl": round(float(np.sum(pnl[short_m])), 6),
            "short_pnl_gated": round(float(np.sum(pnl_g[short_m])), 6),
            "total_pnl": round(float(np.sum(pnl[m])), 6),
            "total_pnl_gated": round(float(np.sum(pnl_g[m])), 6),
            "worst_week": round(ww, 6),
            "worst_week_gated": round(ww_g, 6),
            "maxDD": round(dd, 6),
            "maxDD_gated": round(dd_g, 6),
            "dd_improves": bool(dd_g < dd),
            "pnl_not_lower": bool(np.sum(pnl_g[m]) >= np.sum(pnl[m])),
        }
        years.append(row)
        dd_wins += int(row["dd_improves"])
        pnl_wins += int(row["pnl_not_lower"])

    # Full-path context (compounded from year-1 start, no reset).
    rp_full = bar["pnl"].to_numpy()
    rp_full_g = bar["pnl_g"].to_numpy()
    full_dd = max_dd(equity_path(rp_full))
    full_dd_g = max_dd(equity_path(rp_full_g))

    promising = bool(dd_wins >= 4 and pnl_wins >= 3)
    res = {
        "meta": {
            "books": "forward_v205.research_books_d2 (rebuilt exactly, cf oc_bookic)",
            "opens": "engine_real opens_v154.parquet",
            "dvol": "research/tournament/oc_dvol/dvol_hourly.parquet (t<CUTOFF)",
            "asof": "last hourly bar with end <= T; z90 vs trailing 2160 asof samples",
            "rule": "short rows with mapped dvol_z90 > walk-forward q67 -> weight x0.5",
            "costs": "maker 0.0002 per unit turnover (|w - w_prev| per sym, first prev=0)",
            "path": "per-year equity reset to 1, eq*=1+sum_s pnl; maxDD peak-to-trough; worst week = min 42-bar return",
            "symbols": SYMS, "cutoff": str(CUTOFF),
            "grid_start": str(panel["T"].min()), "grid_end": str(panel["T"].max()),
            "n_panel": int(len(panel)),
            "anchor_years": [str(a.date()) for a in ANCHORS],
        },
        "years": years,
        "full_path": {
            "maxDD": round(full_dd, 6), "maxDD_gated": round(full_dd_g, 6),
            "total_pnl": round(float(rp_full.sum()), 6),
            "total_pnl_gated": round(float(rp_full_g.sum()), 6),
        },
        "decision": {
            "dd_improve_count": f"{dd_wins}/5",
            "pnl_not_lower_count": f"{pnl_wins}/5",
            "promising": promising,
        },
    }
    (HERE / "results.json").write_text(json.dumps(res, indent=1))
    print(json.dumps(res["decision"], indent=1))
    for y in years:
        print(y)


if __name__ == "__main__":
    main()
