"""oc_cmegap: CME weekend-gap fill as a BOOK tilt (idea #69, pre-registered in PLAN.md).

Per PLAN.md: rebuild forward_v205.research_books_d2 exactly (as oc_dvolshort /
oc_bookweekend), join with v154 4h opens, apply audited v410 bear-long filter
FIRST (BASE = control), then apply the fixed CME-gap long tilt (RULE) on
standard book rows T in each weekend's active window:
  gap > +2% and BASE long -> x0.75; gap < -2% and BASE long -> x1.25.
Gap/fill from Binance BTCUSDT 1m only (assignment-stated 1m use).
Screen with open-to-open 4h returns and 0.0005/unit turnover (own prev).
Single light process (4h + BTC 1m only, no other inputs).

  python research/tournament/oc_cmegap/compute_cmegap.py
"""
from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
CACHE = ROOT / "artifacts/research/engine_real"
BTC1M = ROOT / "data/raw/btc_intraday_20260924"

SYMS = ["BNBUSDT", "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]
ANCHORS = [pd.Timestamp(f"{y}-09-24", tz="UTC") for y in (2021, 2022, 2023, 2024, 2025)]
LAST_BOUND = ANCHORS[-1] + pd.Timedelta(days=365)
BOUNDS = ANCHORS + [LAST_BOUND]
CUTOFF = pd.Timestamp("2026-09-24", tz="UTC")
MAKER = 0.0005
GAP_TH = 0.02
WIN_H = 72


def research_books_d2() -> pd.DataFrame:
    """Mirror of oc_dvolshort.compute_dvolshort.research_books_d2."""
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


def bear_flags(opens_full: pd.DataFrame, grid: pd.DatetimeIndex) -> np.ndarray:
    """v410 bear flag on the FULL BTC opens history, reindexed to grid."""
    btc = opens_full["BTCUSDT"].sort_index()
    ma = btc.rolling(1200, min_periods=600).mean()
    bear = (btc < ma).reindex(grid)
    return bear.fillna(False).to_numpy(bool)


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> _dt.date:
    """n-th weekday (Mon=0..Sun=6) of a month (n>=1)."""
    d = _dt.date(year, month, 1)
    off = (weekday - d.weekday()) % 7
    return d + _dt.timedelta(days=off + 7 * (n - 1))


def dst_start_end(year: int) -> tuple[_dt.date, _dt.date]:
    """US DST: second Sunday of March .. first Sunday of November (dates)."""
    return (_nth_weekday(year, 3, 6, 2), _nth_weekday(year, 11, 6, 1))


def is_summer_friday(friday_date: _dt.date) -> bool:
    s, e = dst_start_end(friday_date.year)
    return s <= friday_date < e


def max_dd(equity: np.ndarray) -> float:
    eq = np.asarray(equity, dtype=float)
    if len(eq) == 0:
        return float("nan")
    peak = np.maximum.accumulate(eq)
    return float(np.max(1.0 - eq / peak))


def worst_week(equity: np.ndarray) -> float:
    eq = np.asarray(equity, dtype=float)
    if len(eq) < 43:
        return float(eq[-1] / eq[0] - 1.0) if len(eq) > 1 else 0.0
    return float(np.min(eq[42:] / eq[:-42] - 1.0))


def equity_path(rp: np.ndarray) -> np.ndarray:
    rp = np.asarray(rp, dtype=float)
    return np.concatenate([[1.0], np.cumprod(1.0 + rp)])


def load_btc1m() -> pd.DataFrame:
    frames = []
    for y in (2021, 2022, 2023, 2024, 2025, 2026):
        f = BTC1M / f"klines_1m_{y}.parquet"
        if not f.exists():
            continue
        df = pd.read_parquet(f, columns=["open_time", "high", "low", "close"])
        frames.append(df)
    m = pd.concat(frames, ignore_index=True)
    m["open_time"] = pd.to_datetime(m["open_time"], utc=True)
    m = m[(m["open_time"] < CUTOFF)].drop_duplicates("open_time").sort_values("open_time")
    return m.reset_index(drop=True)


def enumerate_weekends() -> pd.DataFrame:
    """All Fri->Sun weekends with reopen < CUTOFF (close/reopen per DST rule)."""
    days = pd.date_range("2021-09-17", "2026-09-23", freq="D", tz="UTC")
    fridays = [d for d in days if d.weekday() == 4]
    rows = []
    for f in fridays:
        fd = f.date()
        summer = is_summer_friday(fd)
        close_h = 20 if summer else 21
        reopen_h = 21 if summer else 22
        close_min = pd.Timestamp(fd, tz="UTC") + pd.Timedelta(hours=close_h)
        reopen_min = pd.Timestamp(fd + _dt.timedelta(days=2), tz="UTC") + pd.Timedelta(hours=reopen_h)
        if reopen_min >= CUTOFF:
            continue
        rows.append({
            "friday": str(fd),
            "season": "summer" if summer else "winter",
            "close_min": close_min,
            "reopen_min": reopen_min,
        })
    return pd.DataFrame(rows)


def main() -> None:
    books_raw = research_books_d2()
    opens_full = pd.read_parquet(CACHE / "opens_v154.parquet")
    opens = opens_full.reindex(books_raw.index)
    grid = books_raw.index.intersection(opens.dropna(how="all").index)
    grid = grid[(grid >= ANCHORS[0]) & (grid < CUTOFF)].sort_values()
    books_raw = books_raw.reindex(grid)

    o = opens.reindex(grid)[SYMS]
    fwd1 = o.shift(-1) / o - 1.0
    exit1_ok = (grid.shift(-1) <= CUTOFF)
    keep = np.asarray(exit1_ok)
    books_raw, fwd1 = books_raw[keep], fwd1[keep]
    valid1 = fwd1.notna().all(axis=1)
    books_raw, fwd1 = books_raw[valid1], fwd1[valid1]
    grid = books_raw.index
    print(f"book grid: {len(grid)} bars {grid.min()}..{grid.max()}", flush=True)

    bear = bear_flags(opens_full, grid)
    w0 = books_raw[SYMS].to_numpy(float)
    base = w0.copy()
    pos = w0 > 0
    base[bear[:, None] & pos] = 0.5 * w0[bear[:, None] & pos]
    r1 = fwd1[SYMS].to_numpy(float)

    # --- CME gaps from BTC 1m (assignment-stated 1m use) ---
    m1 = load_btc1m()
    print(f"btc 1m: {len(m1)} bars {m1['open_time'].min()}..{m1['open_time'].max()}", flush=True)
    close_s = pd.Series(m1["close"].to_numpy(float), index=m1["open_time"])
    tns = m1["open_time"].to_numpy(dtype="datetime64[ns]").astype(np.int64)
    highs = m1["high"].to_numpy(float)
    lows = m1["low"].to_numpy(float)

    weekends = enumerate_weekends()
    Pf, Ps, gaps = [], [], []
    for _, r in weekends.iterrows():
        c = close_s.get(r["close_min"], np.nan)
        s = close_s.get(r["reopen_min"], np.nan)
        Pf.append(float(c) if c is not None else np.nan)
        Ps.append(float(s) if s is not None else np.nan)
        gaps.append(float(s) / float(c) - 1.0 if np.isfinite(c) and np.isfinite(s) and float(c) > 0 else np.nan)
    weekends["P_fri"] = Pf
    weekends["P_sun"] = Ps
    weekends["gap"] = gaps
    weekends["large"] = weekends["gap"].abs() > GAP_TH

    # Fill scan for every finite non-zero gap (vectorised slice per weekend).
    grid_ns = grid.to_numpy(dtype="datetime64[ns]").astype(np.int64)
    fill_list: list = []
    filled_list: list = []
    for _, r in weekends.iterrows():
        g = float(r["gap"])
        if not np.isfinite(g) or g == 0.0:
            fill_list.append(pd.NaT)
            filled_list.append(False)
            continue
        ro = r["reopen_min"].value
        lo = int(np.searchsorted(tns, ro + 1, side="left"))
        hi = int(np.searchsorted(tns, ro + WIN_H * 3_600_000_000_000, side="left"))
        if hi > lo:
            seg_o = tns[lo:hi]
            if g > 0:
                hit = np.where(lows[lo:hi] <= float(r["P_fri"]))[0]
            else:
                hit = np.where(highs[lo:hi] >= float(r["P_fri"]))[0]
            if len(hit):
                fm = pd.to_datetime(int(seg_o[int(hit[0])]), utc=True)
                fill_list.append(fm)
                filled_list.append(True)
                continue
        fill_list.append(pd.NaT)
        filled_list.append(False)
    weekends["fill_minute"] = pd.to_datetime(pd.Series(fill_list), utc=True)
    weekends["filled_72h"] = np.asarray(filled_list, dtype=bool)

    # --- Map windows onto the 4h grid ---
    n = len(grid)
    gap_at = np.full(n, np.nan)
    affected = np.zeros(n, dtype=bool)
    wk_idx = np.full(n, -1, dtype=np.int64)
    reopen_ns = weekends["reopen_min"].to_numpy(dtype="datetime64[ns]").astype(np.int64)
    fill_ns = weekends["fill_minute"].to_numpy(dtype="datetime64[ns]")
    fill_ns_i = fill_ns.astype(np.int64)  # NaT -> iNaT
    INAT = np.datetime64("NaT").astype(np.int64)
    gvals = weekends["gap"].to_numpy(float)
    large = weekends["large"].to_numpy(bool)
    for j in range(len(weekends)):
        if not large[j] or not np.isfinite(gvals[j]):
            continue
        ro = int(reopen_ns[j])
        end = ro + WIN_H * 3_600_000_000_000
        fm = int(fill_ns_i[j]) if fill_ns_i[j] != INAT else None
        m = (grid_ns > ro) & (grid_ns <= end)
        if fm is not None:
            m = m & (grid_ns <= fm)
        if m.any():
            assert not np.any(affected[m]), "overlapping large-gap windows"
            affected[m] = True
            gap_at[m] = gvals[j]
            wk_idx[m] = j

    rule = base.copy()
    up = affected & np.isfinite(gap_at) & (gap_at > GAP_TH)
    dn = affected & np.isfinite(gap_at) & (gap_at < -GAP_TH)
    for sel, mult in ((up, 0.75), (dn, 1.25)):
        if sel.any():
            longs = sel[:, None] & (base > 0)
            rule[longs] = mult * base[longs]

    cost_b = np.zeros_like(base)
    cost_r = np.zeros_like(base)
    for j in range(len(SYMS)):
        wb, wr = base[:, j], rule[:, j]
        cost_b[:, j] = MAKER * np.abs(wb - np.concatenate([[0.0], wb[:-1]]))
        cost_r[:, j] = MAKER * np.abs(wr - np.concatenate([[0.0], wr[:-1]]))
    pnl_b = base * r1 - cost_b
    pnl_r = rule * r1 - cost_r

    panel = pd.DataFrame({
        "T": np.repeat(grid.to_numpy(), len(SYMS)),
        "sym": np.tile(np.asarray(SYMS), len(grid)),
        "bear": np.repeat(bear, len(SYMS)),
        "affected": np.repeat(affected, len(SYMS)),
        "gap": np.repeat(gap_at, len(SYMS)),
        "w_raw": w0.reshape(-1),
        "w_base": base.reshape(-1),
        "w_rule": rule.reshape(-1),
        "r1": r1.reshape(-1),
        "cost_base": cost_b.reshape(-1),
        "cost_rule": cost_r.reshape(-1),
        "pnl_base": pnl_b.reshape(-1),
        "pnl_rule": pnl_r.reshape(-1),
    })
    panel["T"] = pd.to_datetime(panel["T"], utc=True)
    panel.to_parquet(HERE / "panel.parquet")

    weekends["n_affected_bars"] = [
        int(np.sum((wk_idx == j))) for j in range(len(weekends))
    ]
    weekends.to_parquet(HERE / "gaps.parquet")

    bar_b = pd.Series(pnl_b.sum(axis=1), index=grid)
    bar_r = pd.Series(pnl_r.sum(axis=1), index=grid)
    aff_b = pd.Series((pnl_b[affected][:, :] if affected.any() else np.zeros((0, 5))).sum(axis=1)
           if affected.any() else pd.Series(dtype=float))

    years = []
    pnl_wins = 0
    dd_wins = 0
    for k, a0 in enumerate(ANCHORS):
        m = np.asarray((grid >= BOUNDS[k]) & (grid < BOUNDS[k + 1]))
        rp_b = bar_b.to_numpy()[m]
        rp_r = bar_r.to_numpy()[m]
        eq_b, eq_r = equity_path(rp_b), equity_path(rp_r)
        dd_b, dd_r = max_dd(eq_b), max_dd(eq_r)
        ww_b, ww_r = worst_week(eq_b), worst_week(eq_r)
        tot_b = float(np.sum(pnl_b[m]))
        tot_r = float(np.sum(pnl_r[m]))
        am = m & affected
        aff_pnl_b = float(np.sum(pnl_b[am]))
        aff_pnl_r = float(np.sum(pnl_r[am]))
        # weekends counted by reopen in the year
        ro_in = (weekends["reopen_min"] >= BOUNDS[k]) & (weekends["reopen_min"] < BOUNDS[k + 1])
        wky = weekends[ro_in]
        n_wk = int(len(wky))
        n_gap = int(wky["gap"].notna().sum())
        n_large = int(wky["large"].sum())
        fill_rate = (float(wky.loc[wky["large"], "filled_72h"].mean())
                     if n_large else float("nan"))
        pnl_ok = bool(tot_r >= tot_b)
        dd_ok = bool(dd_r <= dd_b)
        years.append({
            "year": str(a0.date()),
            "n_bars": int(m.sum()),
            "n_weekends": n_wk,
            "n_gap": n_gap,
            "n_large": n_large,
            "fill_rate_large": round(fill_rate, 6) if np.isfinite(fill_rate) else None,
            "n_affected_bars": int(am.sum() // 1) if False else int(np.sum(am)),
            "affected_share": round(float(am.mean()), 6),
            "affected_pnl_base": round(aff_pnl_b, 6),
            "affected_pnl_rule": round(aff_pnl_r, 6),
            "book_pnl_base": round(tot_b, 6),
            "book_pnl_rule": round(tot_r, 6),
            "worst_week_base": round(ww_b, 6),
            "worst_week_rule": round(ww_r, 6),
            "maxDD_base": round(dd_b, 6),
            "maxDD_rule": round(dd_r, 6),
            "pnl_not_lower": pnl_ok,
            "dd_not_worse": dd_ok,
        })
        pnl_wins += int(pnl_ok)
        dd_wins += int(dd_ok)

    full_dd_b = max_dd(equity_path(bar_b.to_numpy()))
    full_dd_r = max_dd(equity_path(bar_r.to_numpy()))

    pnl_ind = np.array([y["pnl_not_lower"] for y in years], dtype=bool)
    dd_ind = np.array([y["dd_not_worse"] for y in years], dtype=bool)
    loyo_pnl = sum(bool(pnl_ind[h] == (np.sum(pnl_ind[np.arange(5) != h]) >= 3)) for h in range(5))
    loyo_dd = sum(bool(dd_ind[h] == (np.sum(dd_ind[np.arange(5) != h]) >= 3)) for h in range(5))

    promising = bool(pnl_wins >= 4 and dd_wins >= 4)
    res = {
        "meta": {
            "books": "forward_v205.research_books_d2 (rebuilt exactly, cf oc_dvolshort)",
            "opens": "engine_real opens_v154.parquet",
            "base": "BASE = raw book + v410 bear-long filter (longs x0.5 where BTC 4h open < rolling-1200 mean, min 600)",
            "rule": "RULE: large-gap active window (first 4h row after Sun reopen .. fill or +72h): longs x0.75 if gap>+2%, x1.25 if gap<-2%; shorts unchanged",
            "dst": "weekend season by Friday date in [2nd-Sun-Mar, 1st-Sun-Nov): summer Fri 20:00/Sun 21:00 UTC, else winter Fri 21:00/Sun 22:00 UTC",
            "gap": "P_sun/P_fri-1 from Binance BTCUSDT 1m closes at reopen/close minutes; NaN if either 1m bar missing",
            "fill": "first 1m bar with open_time in (reopen, reopen+72h): low<=P_fri (up-gap) or high>=P_fri (down-gap); row T affected iff T>reopen, T<=reopen+72h, no fill with open_time<T",
            "costs": "0.0005 per unit turnover (|w - w_prev| per sym, first prev=0; each path own prev)",
            "path": "per-year equity reset to 1, eq*=1+sum_s pnl; maxDD peak-to-trough; worst week = min 42-bar return",
            "symbols": SYMS, "cutoff": str(CUTOFF),
            "grid_start": str(grid.min()), "grid_end": str(grid.max()),
            "n_bars": int(len(grid)), "n_panel": int(len(panel)),
            "n_weekends": int(len(weekends)),
            "n_large_gaps": int(weekends["large"].sum()),
            "anchor_years": [str(a.date()) for a in ANCHORS],
        },
        "years": years,
        "full_path": {
            "maxDD_base": round(full_dd_b, 6), "maxDD_rule": round(full_dd_r, 6),
            "total_pnl_base": round(float(np.sum(pnl_b)), 6),
            "total_pnl_rule": round(float(np.sum(pnl_r)), 6),
        },
        "loyo": {"pnl_stability": f"{loyo_pnl}/5", "dd_stability": f"{loyo_dd}/5"},
        "decision": {
            "pnl_not_lower_count": f"{pnl_wins}/5",
            "dd_not_worse_count": f"{dd_wins}/5",
            "promising": promising,
        },
    }
    (HERE / "results.json").write_text(json.dumps(res, indent=1))
    print(json.dumps(res["decision"], indent=1))
    print(json.dumps(res["loyo"], indent=1))
    for y in years:
        print(y)


if __name__ == "__main__":
    main()
