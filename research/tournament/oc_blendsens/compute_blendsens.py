"""oc_blendsens: blend-weight SENSITIVITY of the deployed BOT book (pre-registered in PLAN.md).

Per PLAN.md: rebuild O1 and Dmean legs exactly as oc_dvolshort (mirror of
forward_v205.research_books_d2), form raw blends w(alpha) for
alpha in {1.0, 0.9, 0.8, 0.7, 0.0}, apply the audited v410 BTC-only
bear-long filter FIRST (longs x0.5 in bear), then screen with open-to-open
4h returns and 0.05% per unit turnover (each blend own prev chain, first
prev = 0), exactly as oc_dvolshort structurally (its rate was 0.0002).
Per anchor year: book P&L net, worst week, maxDD per blend; plateau verdict
for the deployed 0.8/0.2. Single light process (4h only, no 1m).

  python research/tournament/oc_blendsens/compute_blendsens.py
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
LAST_BOUND = ANCHORS[-1] + pd.Timedelta(days=365)
CUTOFF = pd.Timestamp("2026-09-24", tz="UTC")
COST = 0.0005
ALPHAS = {"O1": 1.0, "a09": 0.9, "a08": 0.8, "a07": 0.7, "D": 0.0}


def rebuild_legs() -> tuple[pd.DataFrame, pd.DataFrame]:
    """o1 and dmean on the union index, missing -> 0.0 (same files/math as oc_dvolshort)."""
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
    o1u, Du, Dqu = g(o1), g(D), g(Dq)
    return o1u, (Du + Dqu) / 2


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


def loyo_holds(e: np.ndarray) -> tuple[list[bool], int]:
    """Strict-sign LOYO: sign(E[h]) == sign(mean of other 4), zeros fail."""
    e = np.asarray(e, dtype=float)
    out = []
    for h in range(len(e)):
        rest = np.delete(e, h)
        m = float(np.mean(rest))
        out.append(bool(np.isfinite(e[h]) and np.isfinite(m) and e[h] != 0 and m != 0
                        and np.sign(e[h]) == np.sign(m)))
    return out, int(sum(out))


def main() -> None:
    o1u, dmeanu = rebuild_legs()
    raw = {name: (a * o1u + (1.0 - a) * dmeanu) for name, a in ALPHAS.items()}

    opens_full = pd.read_parquet(CACHE / "opens_v154.parquet")
    # Grid from the deployed-blend index (all blends share it) x opens inner join.
    books_ref = raw["a08"]
    opens = opens_full.reindex(books_ref.index)
    grid = books_ref.index.intersection(opens.dropna(how="all").index)
    grid = grid[(grid >= ANCHORS[0]) & (grid < CUTOFF)].sort_values()
    opens = opens.reindex(grid).sort_index()
    for name in raw:
        raw[name] = raw[name].reindex(grid).sort_index()

    fwd1 = opens[SYMS].shift(-1) / opens[SYMS] - 1.0
    valid = fwd1.notna().all(axis=1)  # drop last grid bar (no forward open)
    opens, fwd1 = opens[valid], fwd1[valid]
    for name in raw:
        raw[name] = raw[name][valid]
    grid = opens.index
    print(f"book grid: {len(grid)} bars {grid.min()}..{grid.max()}", flush=True)

    # v410 bear filter FIRST (BTC-only, causal, open[T] inclusive).
    btc_full = opens_full["BTCUSDT"].sort_index()
    ma_full = btc_full.rolling(1200, min_periods=600).mean()
    bear_full = (btc_full < ma_full).fillna(False)
    bear = bear_full.reindex(grid).fillna(False).to_numpy(bool)
    print(f"share bear on grid: {float(np.mean(bear)):.4f}", flush=True)

    w = {}  # filtered weights per blend
    for name in ALPHAS:
        arr = raw[name].to_numpy(float)
        w[name] = np.where(bear[:, None] & (arr > 0), arr * 0.5, arr)
    r1 = fwd1.to_numpy(float)

    names = list(ALPHAS)
    pnl, cost, rp = {}, {}, {}
    for name in names:
        prev = np.vstack([np.zeros((1, w[name].shape[1])), w[name][:-1]])
        c = COST * np.abs(w[name] - prev)
        cost[name] = c
        pnl[name] = w[name] * r1 - c
        rp[name] = pnl[name].sum(axis=1)

    # Small per-(T,sym,blend) panel (filtered weights, forwards, net cells).
    rows = []
    for j, s in enumerate(SYMS):
        d = {"T": grid, "sym": s, "r1": r1[:, j], "bear": bear}
        for name in names:
            d[f"w_{name}"] = w[name][:, j]
            d[f"cost_{name}"] = cost[name][:, j]
            d[f"pnl_{name}"] = pnl[name][:, j]
        rows.append(pd.DataFrame(d))
    panel = pd.concat(rows, ignore_index=True)
    panel["T"] = pd.to_datetime(panel["T"], utc=True)
    panel.to_parquet(HERE / "panel.parquet")

    bounds = ANCHORS + [LAST_BOUND]
    years = []
    for k, a0 in enumerate(ANCHORS):
        m = np.asarray((grid >= bounds[k]) & (grid < bounds[k + 1]))
        row: dict = {"year": str(a0.date()), "n_bars": int(m.sum()),
                     "share_bear": round(float(bear[m].mean()), 6)}
        for name in names:
            r = rp[name][m]
            eq = equity_path(r)
            n = float(pnl[name][m].sum())
            # Global-chain turnover sliced to the year (boundary prev is global).
            prev_g = np.vstack([np.zeros((1, w[name].shape[1])), w[name][:-1]])
            t = float(np.abs(w[name] - prev_g)[m].sum())
            row[f"net_{name}"] = round(n, 6)
            row[f"worst_week_{name}"] = round(worst_week(eq), 6)
            row[f"maxDD_{name}"] = round(max_dd(eq), 6)
            row[f"turnover_{name}"] = round(t, 4)
            row[f"cost_{name}"] = round(float(cost[name][m].sum()), 6)
        years.append(row)

    net = {name: np.array([y[f"net_{name}"] for y in years]) for name in names}
    E1 = net["a08"] - net["a07"]
    E2 = net["a09"] - net["a08"]
    EO = net["O1"] - net["D"]
    pos1, neg1 = int(np.sum(E1 > 0)), int(np.sum(E1 < 0))
    pos2, neg2 = int(np.sum(E2 > 0)), int(np.sum(E2 < 0))
    posO, negO = int(np.sum(EO > 0)), int(np.sum(EO < 0))
    same1 = max(pos1, neg1)
    same2 = max(pos2, neg2)
    sameO = max(posO, negO)
    loyo1, loyo1_n = loyo_holds(E1)
    loyo2, loyo2_n = loyo_holds(E2)
    loyoO, loyoO_n = loyo_holds(EO)
    mean_step = float((np.abs(E1) + np.abs(E2)).mean() / 2.0)

    full = {}
    for name in names:
        r = rp[name]
        eq = equity_path(r)
        full[name] = {"maxDD": round(max_dd(eq), 6),
                      "total_net": round(float(pnl[name].sum()), 6),
                      "total_cost": round(float(cost[name].sum()), 6)}

    plateau_a = not ((same1 >= 4 and loyo1_n >= 4) or (same2 >= 4 and loyo2_n >= 4))
    plateau_b = bool(mean_step < 0.01)
    plateau = bool(plateau_a and plateau_b)
    if plateau:
        verdict = ("PLATEAU (sensitivity, no selection): deployed 0.8/0.2 sits on "
                   "a plateau — no consistent local slope through 0.8.")
    else:
        if same1 >= 4 and same2 >= 4 and pos1 + pos2 >= 7:
            direction = "UPHILL toward more O1 (both steps help with consistent sign)"
        elif same1 >= 4 and same2 >= 4 and neg1 + neg2 >= 7:
            direction = "DOWNHILL toward more D (both steps hurt with consistent sign)"
        else:
            direction = "MIXED / non-plateau (local steps not jointly consistent or not small)"
        verdict = (f"NOT a clean plateau (sensitivity, no selection): {direction}; "
                   f"mean adjacent step {mean_step:.4f} "
                   f"({'<' if plateau_b else '>='} 0.01).")

    res = {
        "meta": {
            "book": ("forward_v205.research_books_d2 legs rebuilt exactly "
                     "(cf oc_dvolshort/oc_bookic): o1 = 0.5*(A+B)/2 + 0.5*(Aq+Bq)/2, "
                     "dmean = (D+Dq)/2; blends w(alpha) = alpha*o1 + (1-alpha)*dmean"),
            "blends": {"O1": 1.0, "a09": 0.9, "a08": 0.8, "a07": 0.7, "D": 0.0},
            "deployed": "a08 = 0.8 x O1 + 0.2 x Dmean",
            "opens": "engine_real opens_v154.parquet",
            "bear": ("v410 BTC-only bear filter FIRST: longs x0.5 when BTC 4h open < "
                     "1200-bar mean (rolling(1200,min600) on FULL history, strict, NaN->False)"),
            "costs": "0.0005 per unit turnover (|wb - wprev| per sym, first prev=0, own blend chain)",
            "path": ("per-year equity reset to 1, eq*=1+sum_s net pnl; maxDD peak-to-trough; "
                     "worst week = min 42-bar return"),
            "symbols": SYMS, "cutoff": str(CUTOFF),
            "grid_start": str(grid.min()), "grid_end": str(grid.max()),
            "n_bars": int(len(grid)), "n_panel": int(len(panel)),
            "anchor_years": [str(a.date()) for a in ANCHORS],
            "light": "one process, 4h inputs only, no 1m",
        },
        "years": years,
        "effects": {
            "E1_a08_minus_a07": [round(float(v), 6) for v in E1],
            "E2_a09_minus_a08": [round(float(v), 6) for v in E2],
            "EO_O1_minus_D": [round(float(v), 6) for v in EO],
            "same_sign_E1": f"{same1}/5 (pos {pos1}, neg {neg1})",
            "same_sign_E2": f"{same2}/5 (pos {pos2}, neg {neg2})",
            "same_sign_EO": f"{sameO}/5 (pos {posO}, neg {negO})",
            "loyo_E1": {"per_heldout": loyo1, "count": f"{loyo1_n}/5"},
            "loyo_E2": {"per_heldout": loyo2, "count": f"{loyo2_n}/5"},
            "loyo_EO": {"per_heldout": loyoO, "count": f"{loyoO_n}/5"},
            "mean_adjacent_step": round(mean_step, 6),
        },
        "full_path": full,
        "plateau": {
            "no_consistent_local_slope": plateau_a,
            "mean_step_lt_0.01": plateau_b,
            "on_plateau": plateau,
        },
        "verdict": verdict,
    }
    (HERE / "results.json").write_text(json.dumps(res, indent=1))
    print(verdict)
    print(json.dumps(res["effects"], indent=1))
    for y in years:
        print(y)
    print("full_path:", json.dumps(full, indent=1))


if __name__ == "__main__":
    main()
