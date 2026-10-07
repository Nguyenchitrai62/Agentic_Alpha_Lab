"""oc_cadence: slower book cadence (idea #47, pre-registered in PLAN.md).

Per PLAN.md: rebuild forward_v205.research_books_d2 exactly (as
oc_dvolshort/oc_bullbook), join with v154 4h opens, apply the audited v410
bear-long filter (longs x0.5 in bear, MA1200 on FULL BTC history) as BASE,
then 8H = BASE with 8h cadence (only even 4h ordinals may CHANGE the
target, odd rows hold the previous target per coin) and 12H = BASE with
12h cadence (only ordinals i%3==0 may change). Screen with open-to-open 4h
returns and 0.05% per unit L1 turnover (each path with its own prev).
Book path compounded per-bar per year (as oc_dvolshort). Single light
process (4h + book inputs only, no 1m).

  python research/tournament/oc_cadence/compute_cadence.py
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
YEAR_END = ANCHORS[-1] + pd.Timedelta(days=365)
CUTOFF = pd.Timestamp("2026-09-24", tz="UTC")
COST = 0.0005


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


def build_bear(opens_full: pd.DataFrame, grid: pd.DatetimeIndex) -> pd.Series:
    """Causal v410 bear flag, exactly as oc_bullbook (full-history MA1200).

    MA1200[T] = mean(BTC_open[T-1199..T]) via rolling(1200, min_periods=600);
    bear[T] iff open[T] < MA (strict, NaN -> False). open[T] inclusive,
    known at the close of bar T.
    """
    btc = opens_full["BTCUSDT"].sort_index()
    ma = btc.rolling(1200, min_periods=600).mean()
    return (btc < ma).fillna(False).reindex(grid).fillna(False)


def apply_bear(books: pd.DataFrame, bear: pd.Series) -> pd.DataFrame:
    """BASE = raw books with longs x0.5 on bear rows (shorts/flat unchanged)."""
    arr = books.to_numpy()
    barr = bear.to_numpy()[:, None]
    return pd.DataFrame(np.where(barr & (arr > 0), arr * 0.5, arr),
                        index=books.index, columns=books.columns)


def apply_cadence(base: pd.DataFrame, step: int) -> pd.DataFrame:
    """Hold targets between update rows (causal, time-only mask).

    Ordinal i in the sorted grid; row i may CHANGE iff i % step == 0,
    else hold the previous row's value per coin. Row 0 always equals BASE.
    step=2 -> 8h cadence; step=3 -> 12h cadence.
    """
    arr = base.to_numpy()
    n = len(arr)
    can = (np.arange(n) % step == 0)
    out = np.empty_like(arr)
    out[0] = arr[0]
    for i in range(1, n):
        out[i] = arr[i] if can[i] else out[i - 1]
    return pd.DataFrame(out, index=base.index, columns=base.columns)


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


def main() -> None:
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

    bear = build_bear(opens_full, grid)
    w_base = apply_bear(books_raw, bear)
    w_8h = apply_cadence(w_base, 2)
    w_12h = apply_cadence(w_base, 3)
    paths = {"base": w_base, "h8": w_8h, "h12": w_12h}
    print(f"share bear: {float(bear.mean()):.4f}", flush=True)

    gross, cost, pnl, rp = {}, {}, {}, {}
    for name, w in paths.items():
        prev = w.shift(1).fillna(0.0)
        c = COST * (w - prev).abs()
        cost[name] = c
        gross[name] = w * fwd1
        pnl[name] = gross[name] - c
        rp[name] = pnl[name].sum(axis=1)

    bounds = ANCHORS + [YEAR_END]
    masks = [((grid >= bounds[k]) & (grid < bounds[k + 1])) for k in range(5)]

    years = []
    pnl_wins = 0
    dd_wins = 0
    for k, a0 in enumerate(ANCHORS):
        m = np.asarray(masks[k])
        row: dict = {"year": str(a0.date()), "n_bars": int(m.sum()),
                     "share_bear": round(float(bear.to_numpy()[m].mean()), 6)}
        eqs, dds, wws = {}, {}, {}
        for name in ("base", "h8", "h12"):
            r = rp[name][m].to_numpy(float)
            eq = equity_path(r)
            eqs[name] = eq
            dds[name] = max_dd(eq)
            wws[name] = worst_week(eq)
            g = float(gross[name][m].to_numpy().sum())
            t = float(((paths[name] - paths[name].shift(1).fillna(0.0)).abs()[m]).to_numpy().sum())
            c = float(cost[name][m].to_numpy().sum())
            n = float(pnl[name][m].to_numpy().sum())
            row[f"gross_{name}"] = round(g, 6)
            row[f"turnover_{name}"] = round(t, 6)
            row[f"cost_{name}"] = round(c, 6)
            row[f"net_{name}"] = round(n, 6)
            row[f"ret_{name}"] = round(float(eq[-1] - 1.0), 6)
            row[f"worst_week_{name}"] = round(wws[name], 6)
            row[f"maxDD_{name}"] = round(dds[name], 6)
        pnl_win = bool(row["net_h8"] > row["net_base"])
        dd_win = bool(row["maxDD_h8"] <= row["maxDD_base"])
        pnl_wins += int(pnl_win)
        dd_wins += int(dd_win)
        row["pnl_higher_8h"] = pnl_win
        row["dd_not_worse_8h"] = dd_win
        row["pnl_higher_12h"] = bool(row["net_h12"] > row["net_base"])
        row["dd_not_worse_12h"] = bool(row["maxDD_h12"] <= row["maxDD_base"])
        years.append(row)

    # LOYO side row on the 8h net-P&L effect (descriptive, NOT for selection).
    d = np.array([y["net_h8"] - y["net_base"] for y in years], dtype=float)
    loyo = []
    for h in range(5):
        tr = [d[k] for k in range(5) if k != h]
        mrt = float(np.mean(tr))
        loyo.append(bool(np.isfinite(mrt) and mrt > 0 and np.sign(d[h]) == np.sign(mrt)))
    loyo_n = int(sum(loyo))

    full_dd = {n: max_dd(equity_path(rp[n].to_numpy(float))) for n in paths}
    promising = bool(pnl_wins >= 4 and dd_wins >= 4)
    res = {
        "meta": {
            "books": "forward_v205.research_books_d2 (rebuilt exactly, cf oc_dvolshort/oc_bookic)",
            "opens": "engine_real opens_v154.parquet",
            "bear": "v410 bear-long filter first: longs x0.5 when BTC 4h open < 1200-bar mean (rolling(1200,min600) on FULL history, strict, NaN->False)",
            "rule": "8H: only even 4h ordinals (i%2==0, i=0 is 2021-09-24 00:00 UTC) may CHANGE a coin's BASE target, odd rows hold; 12H sensitivity: only i%3==0 may change",
            "costs": "0.0005 per unit L1 turnover (|w - w_prev| per sym, first prev=0, own-path prev)",
            "path": "per-year equity reset to 1, eq*=1+sum_s net pnl; maxDD peak-to-trough; worst week = min 42-bar return",
            "symbols": SYMS, "cutoff": str(CUTOFF),
            "grid_start": str(grid.min()), "grid_end": str(grid.max()),
            "n_bars": int(len(grid)),
        },
        "years": years,
        "loyo_net8h": {"per_heldout": loyo, "count": f"{loyo_n}/5",
                       "note": "descriptive stability only (no fitted parameter); NOT part of the verdict"},
        "full_path": {
            "maxDD_base": round(full_dd["base"], 6),
            "maxDD_h8": round(full_dd["h8"], 6),
            "maxDD_h12": round(full_dd["h12"], 6),
            "total_net_base": round(float(pnl["base"].to_numpy().sum()), 6),
            "total_net_h8": round(float(pnl["h8"].to_numpy().sum()), 6),
            "total_net_h12": round(float(pnl["h12"].to_numpy().sum()), 6),
        },
        "totals": {
            "total_turnover_base": round(float(((w_base - w_base.shift(1).fillna(0.0)).abs().sum().sum())), 4),
            "total_turnover_h8": round(float(((w_8h - w_8h.shift(1).fillna(0.0)).abs().sum().sum())), 4),
            "total_turnover_h12": round(float(((w_12h - w_12h.shift(1).fillna(0.0)).abs().sum().sum())), 4),
            "total_cost_base": round(float(cost["base"].sum().sum()), 6),
            "total_cost_h8": round(float(cost["h8"].sum().sum()), 6),
            "total_cost_h12": round(float(cost["h12"].sum().sum()), 6),
        },
        "decision": {
            "pnl_higher_count": f"{pnl_wins}/5",
            "dd_not_worse_count": f"{dd_wins}/5",
            "promising": promising,
            "rule": "PROMISING iff net 8h > net base in >=4/5 years AND maxDD 8h <= maxDD base in >=4/5 (12h sensitivity not for selection)",
        },
    }
    (HERE / "results.json").write_text(json.dumps(res, indent=1))
    print(json.dumps(res["decision"], indent=1))
    for y in years:
        print(y)


if __name__ == "__main__":
    main()
