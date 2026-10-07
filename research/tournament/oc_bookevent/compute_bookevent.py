"""oc_bookevent: book exposure around scheduled US macro events (idea #51).

Per PLAN.md (pre-registered, read it first): rebuild
forward_v205.research_books_d2 exactly (as oc_dvolshort), apply the
audited v410 bear-long filter FIRST (BASE = control), then halve ALL book
targets on RULEBARs (the 4h bar containing a scheduled FOMC/CPI release
instant and the bar before it; calendar from oc_eventblk, read-only).
Screen with open-to-open 4h returns and gate costs (maker 0.0002 per unit
turnover, each path with its own prev), exactly as oc_dvolshort. Single
light process (4h + calendar only, no 1m).

  python research/tournament/oc_bookevent/compute_bookevent.py
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
CACHE = ROOT / "artifacts/research/engine_real"
CAL = ROOT / "research/tournament/oc_eventblk/event_calendar.csv"

SYMS = ["BNBUSDT", "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]
ANCHORS = [pd.Timestamp(f"{y}-09-24", tz="UTC") for y in (2021, 2022, 2023, 2024, 2025)]
LAST_BOUND = ANCHORS[-1] + pd.Timedelta(days=365)
CUTOFF = pd.Timestamp("2026-09-24", tz="UTC")
MAKER = 0.0002
BAR4H_NS = 4 * 3_600 * 1_000_000_000


def research_books_d2() -> pd.DataFrame:
    """Mirror of oc_dvolshort.compute_dvolshort.research_books_d2 (same files, same math)."""
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


def rulebar_flags(grid: pd.DatetimeIndex, cal: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """EVENTBAR + RULEBAR from grid times + calendar only (causal: schedule pre-published).

    EVENTBAR(T) = 1 iff [T, T+4h) contains a release instant R.
    RULEBAR(T) = EVENTBAR(T) or EVENTBAR(T+4h) (containing bar + bar before).
    The T+4h lookup uses only grid time + calendar (no market data after T).
    """
    Tns = grid.to_numpy(dtype="datetime64[ns]").astype(np.int64)
    R = pd.to_datetime(cal["release_utc"], utc=True).to_numpy(dtype="datetime64[ns]").astype(np.int64)
    ev = ((Tns[:, None] <= R[None, :]) & (R[None, :] < Tns[:, None] + BAR4H_NS)).any(axis=1)
    nxt = ((Tns[:, None] + BAR4H_NS <= R[None, :])
           & (R[None, :] < Tns[:, None] + 2 * BAR4H_NS)).any(axis=1)
    return ev, (ev | nxt)


def bear_flags(opens_full: pd.DataFrame, grid: pd.DatetimeIndex) -> pd.Series:
    """v410 bear flag on the FULL BTC opens history, reindexed to grid."""
    btc = opens_full["BTCUSDT"].sort_index()
    ma = btc.rolling(1200, min_periods=600).mean()
    bear = (btc < ma).reindex(grid)
    return bear.fillna(False)


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
    cal = pd.read_csv(CAL)
    assert (pd.to_datetime(cal["release_utc"], utc=True) < CUTOFF).all(), "calendar must end before CUTOFF"

    books_raw = research_books_d2()
    opens_full = pd.read_parquet(CACHE / "opens_v154.parquet")
    opens = opens_full.reindex(books_raw.index)
    grid = books_raw.index.intersection(opens.dropna(how="all").index)
    grid = grid[(grid >= ANCHORS[0]) & (grid < CUTOFF)].sort_values()
    books_raw = books_raw.reindex(grid).sort_index()
    opens = opens.reindex(grid).sort_index()

    fwd1 = opens[SYMS].shift(-1) / opens[SYMS] - 1.0
    valid = fwd1.notna().all(axis=1)  # drop last grid bar (no forward open)
    books_raw, opens, fwd1 = books_raw[valid], opens[valid], fwd1[valid]
    grid = books_raw.index
    print(f"book grid: {len(grid)} bars {grid.min()}..{grid.max()}", flush=True)

    bear = bear_flags(opens_full, grid).to_numpy(bool)
    eventbar, rulebar = rulebar_flags(grid, cal)

    w_raw = books_raw.to_numpy(float)
    w_base = np.where(bear[:, None] & (w_raw > 0), w_raw * 0.5, w_raw)
    w_rule = np.where(rulebar[:, None], w_base * 0.5, w_base)
    r1 = fwd1.to_numpy(float)

    prev0 = np.zeros((1, w_base.shape[1]))
    cost_base = MAKER * np.abs(w_base - np.vstack([prev0, w_base[:-1]]))
    cost_rule = MAKER * np.abs(w_rule - np.vstack([prev0, w_rule[:-1]]))
    pnl_base = w_base * r1 - cost_base
    pnl_rule = w_rule * r1 - cost_rule

    rp_base = pnl_base.sum(axis=1)
    rp_rule = pnl_rule.sum(axis=1)

    rows = []
    for j, s in enumerate(SYMS):
        rows.append(pd.DataFrame({
            "T": grid,
            "sym": s,
            "w_raw": w_raw[:, j],
            "w_base": w_base[:, j],
            "w_rule": w_rule[:, j],
            "bear": bear,
            "eventbar": eventbar,
            "rulebar": rulebar,
            "r1": r1[:, j],
            "cost_base": cost_base[:, j],
            "cost_rule": cost_rule[:, j],
            "pnl_base": pnl_base[:, j],
            "pnl_rule": pnl_rule[:, j],
        }))
    panel = pd.concat(rows, ignore_index=True)
    panel["T"] = pd.to_datetime(panel["T"], utc=True)
    panel.to_parquet(HERE / "panel.parquet")

    bounds = ANCHORS + [LAST_BOUND]
    years = []
    dd_wins = 0
    pnl_wins = 0
    for k, a0 in enumerate(ANCHORS):
        m = np.asarray((grid >= bounds[k]) & (grid < bounds[k + 1]))
        rb = rulebar[m]
        rp_b = rp_base[m]
        rp_r = rp_rule[m]
        eq_b = equity_path(rp_b)
        eq_r = equity_path(rp_r)
        dd_b, dd_r = max_dd(eq_b), max_dd(eq_r)
        ww_b, ww_r = worst_week(eq_b), worst_week(eq_r)
        pb = float(pnl_base[m].sum())
        pr = float(pnl_rule[m].sum())
        eb = float(pnl_base[m][rb].sum())
        er = float(pnl_rule[m][rb].sum())
        dd_pass = bool(np.isfinite(dd_b) and np.isfinite(dd_r) and dd_r <= dd_b + 1e-12)
        if np.isfinite(pb) and np.isfinite(pr) and pb > 0:
            pnl_pass = bool(pr >= 0.97 * pb)
        else:
            pnl_pass = False
        retention = float(pr / pb) if pb != 0 else float("nan")
        years.append({
            "year": str(a0.date()),
            "n_bars": int(np.sum(m)),
            "share_eventbar": round(float(eventbar[m].mean()) if m.sum() else 0.0, 6),
            "share_rulebar": round(float(rulebar[m].mean()) if m.sum() else 0.0, 6),
            "share_bear": round(float(bear[m].mean()) if m.sum() else 0.0, 6),
            "eventbar_pnl_base": round(eb, 6),
            "eventbar_pnl_rule": round(er, 6),
            "book_pnl_base": round(pb, 6),
            "book_pnl_rule": round(pr, 6),
            "retention": round(retention, 6) if np.isfinite(retention) else None,
            "worst_week_base": round(ww_b, 6),
            "worst_week_rule": round(ww_r, 6),
            "maxDD_base": round(dd_b, 6),
            "maxDD_rule": round(dd_r, 6),
            "dd_not_worse": dd_pass,
            "pnl_ge97": pnl_pass,
        })
        dd_wins += int(dd_pass)
        pnl_wins += int(pnl_pass)

    # LOYO descriptive (no fitted parameter; majority-agreement per indicator).
    dd_ind = [bool(y["dd_not_worse"]) for y in years]
    rt_ind = [bool(y["pnl_ge97"]) for y in years]
    loyo = []
    for h in range(5):
        others_dd = [dd_ind[k] for k in range(5) if k != h]
        others_rt = [rt_ind[k] for k in range(5) if k != h]
        maj_dd = sum(others_dd) >= 2
        maj_rt = sum(others_rt) >= 2
        loyo.append({
            "heldout": str(ANCHORS[h].date()),
            "dd_agree": bool(dd_ind[h] == maj_dd),
            "ret_agree": bool(rt_ind[h] == maj_rt),
        })
    loyo_dd = sum(1 for L in loyo if L["dd_agree"])
    loyo_rt = sum(1 for L in loyo if L["ret_agree"])

    full_dd_b = max_dd(equity_path(rp_base))
    full_dd_r = max_dd(equity_path(rp_rule))
    promising = bool(dd_wins >= 4 and pnl_wins >= 4)
    res = {
        "meta": {
            "books": "forward_v205.research_books_d2 (rebuilt exactly, cf oc_dvolshort)",
            "opens": "engine_real opens_v154.parquet",
            "calendar": "research/tournament/oc_eventblk/event_calendar.csv (read-only, 54 FOMC + 82 CPI before CUTOFF)",
            "base": "v410 BTC-only bear filter FIRST: longs x0.5 when BTC open < 1200-bar mean (rolling 1200, min 600, open[T] inclusive)",
            "rule": "RULEBAR(T)=EVENTBAR(T)|EVENTBAR(T+4h); RULE=0.5*BASE on RULEBAR rows (all coins), else BASE",
            "flag": "EVENTBAR(T)=1 iff [T,T+4h) contains an FOMC/CPI release instant; RULEBAR adds the bar before",
            "costs": "maker 0.0002 per unit turnover (|w - w_prev| per sym, first prev=0, each path own prev)",
            "path": "per-year equity reset to 1, eq*=1+sum_s pnl; maxDD peak-to-trough; worst week = min 42-bar return",
            "symbols": SYMS,
            "cutoff": str(CUTOFF),
            "grid_start": str(grid.min()),
            "grid_end": str(grid.max()),
            "n_bars": int(len(grid)),
            "n_panel": int(len(panel)),
            "anchor_years": [str(a.date()) for a in ANCHORS],
        },
        "years": years,
        "loyo": {"per_heldout": loyo, "dd_agree_count": f"{loyo_dd}/5",
                 "ret_agree_count": f"{loyo_rt}/5",
                 "note": "descriptive majority-agreement only (no fitted parameter); NOT part of the verdict"},
        "full_path": {
            "maxDD_base": round(full_dd_b, 6),
            "maxDD_rule": round(full_dd_r, 6),
            "total_pnl_base": round(float(rp_base.sum()), 6),
            "total_pnl_rule": round(float(rp_rule.sum()), 6),
        },
        "decision": {
            "dd_not_worse_count": f"{dd_wins}/5",
            "pnl_ge97_count": f"{pnl_wins}/5",
            "promising": promising,
            "rule": "PROMISING iff book maxDD not worse (rule<=base) in >=4/5 AND total book P&L >=97% of base in >=4/5",
        },
    }
    (HERE / "results.json").write_text(json.dumps(res, indent=1))
    print(json.dumps(res["decision"], indent=1))
    for y in years:
        print(y)


if __name__ == "__main__":
    main()
