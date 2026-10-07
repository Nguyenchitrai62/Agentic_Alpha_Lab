"""oc_bookbrake: BOOK loss-cluster brake (idea #17, PLAN pre-registered).

Rebuilds forward_v205.research_books_d2 exactly, segments BASE per-coin
weights into book trades (maximal constant-sign runs), scores each trade net
of 0.05%/turnover, and applies the fixed brake: at holding bar start T,
scale ALL book targets by 0.5 iff >= 3 losing book trades closed in
[T-72h, T) (closures strictly before T, any coin), else 1.0.

Vectorised 4h open-to-open P&L only, one process, no 1m data:

  python research/tournament/oc_bookbrake/compute_bookbrake.py
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
BOUND = pd.Timestamp("2026-09-24 00:00", tz="UTC")
ANCHORS = [pd.Timestamp(f"{y}-09-24", tz="UTC") for y in (2021, 2022, 2023, 2024, 2025)]
YEAR_LEN = pd.Timedelta(days=365)
FLAT_TOL = 1e-12
FEE = 0.0005
LOSS_N = 3
LOSS_WIN = pd.Timedelta(hours=72)
BRAKE_SCALE = 0.5
WEEK = 42  # 4h bars per 7 days


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


def load_grid() -> tuple[pd.DataFrame, pd.DataFrame]:
    books = research_books_d2()
    opens_full = pd.read_parquet(CACHE / "opens_v154.parquet")
    grid = books.index.intersection(opens_full.dropna(how="all").index).sort_values()
    step = grid[1:] - grid[:-1]
    assert bool((step == pd.Timedelta(hours=4)).all()), "grid is not a regular 4h grid"
    w = books.reindex(grid)
    nxt = grid + pd.Timedelta(hours=4)
    scored = (grid < BOUND) & (nxt <= BOUND) & nxt.isin(opens_full.index)
    grid = grid[scored]
    assert bool((((grid[1:] - grid[:-1]) == pd.Timedelta(hours=4)).all())), "scored grid not contiguous 4h"
    w = w.reindex(grid)
    o = opens_full.reindex(grid)
    o1 = opens_full.reindex(nxt[scored])
    o1.index = grid
    r = o1 / o - 1.0  # r[t] = open[t+4h]/open[t]-1, next open inside the bound
    assert bool(r.notna().all().all()), "unexpected NaN forward return inside bound"
    return w, r[SYMS]


def segment_trades(w: pd.DataFrame, r: pd.DataFrame) -> tuple[list[dict], pd.DatetimeIndex]:
    """Maximal constant-sign runs per coin on BASE weights; closure = open[b+1]."""
    grid = w.index
    pos = {t: i for i, t in enumerate(grid)}
    trades: list[dict] = []
    for s in SYMS:
        wv = w[s].to_numpy()
        rv = r[s].to_numpy()
        sgn = np.where(np.abs(wv) < FLAT_TOL, 0, np.sign(wv)).astype(int)
        i, n = 0, len(grid)
        while i < n:
            if sgn[i] == 0:
                i += 1
                continue
            a = i
            while i + 1 < n and sgn[i + 1] == sgn[a]:
                i += 1
            b = i
            gross = float((wv[a:b + 1] * rv[a:b + 1]).sum())
            entry = abs(float(wv[a]))
            intra = float(np.abs(np.diff(wv[a:b + 1])).sum()) if b > a else 0.0
            flatleg = abs(float(wv[b]))
            net = gross - FEE * (entry + intra + flatleg)
            if b + 1 < n:
                close_t = grid[b + 1]
            else:
                close_t = None  # no closure event (exit bar is last scored bar)
            trades.append(dict(coin=s, a=pos[grid[a]], b=pos[grid[b]],
                               entry_t=str(grid[a]), exit_t=str(grid[b]),
                               close_t=None if close_t is None else str(close_t),
                               gross=round(gross, 8), net=round(net, 8),
                               loss=bool(net < 0.0)))
            i += 1
    closes = pd.DatetimeIndex(sorted(
        pd.Timestamp(t["close_t"]) for t in trades if t["loss"] and t["close_t"] is not None
    ))
    return trades, closes


def brake_scale(grid: pd.DatetimeIndex, closes: pd.DatetimeIndex) -> pd.Series:
    cv = closes.values.astype("datetime64[ns]")
    lo = (grid - LOSS_WIN).values.astype("datetime64[ns]")
    hi = grid.values.astype("datetime64[ns]")
    left = np.searchsorted(cv, lo, side="left")
    right = np.searchsorted(cv, hi, side="left")  # strictly before T
    n = right - left
    return pd.Series(np.where(n >= LOSS_N, BRAKE_SCALE, 1.0), index=grid)


def year_masks(grid: pd.DatetimeIndex) -> list[tuple[str, np.ndarray]]:
    bounds = ANCHORS + [ANCHORS[-1] + YEAR_LEN]
    out = []
    for k, a0 in enumerate(ANCHORS):
        out.append((str(a0.date()), np.asarray((grid >= bounds[k]) & (grid < bounds[k + 1]))))
    return out


def path_stats(pn: pd.Series, ym: np.ndarray) -> dict:
    x = pn.to_numpy()[ym]
    if len(x) == 0:
        return dict(n_bars=0, ret=None, maxdd=None, worst_week=None)
    eq = np.cumprod(1.0 + x)
    peak = np.maximum.accumulate(eq)
    dd = 1.0 - eq / peak
    ret = float(eq[-1] - 1.0)
    if len(x) >= WEEK:
        win = pd.Series(1.0 + x).rolling(WEEK, min_periods=WEEK).apply(np.prod, raw=True).to_numpy()
        worst_week = float(np.nanmin(win) - 1.0)
    else:
        worst_week = None
    return dict(n_bars=int(len(x)), ret=round(ret, 6),
                maxdd=round(float(np.max(dd)), 6),
                worst_week=None if worst_week is None else round(worst_week, 6))


def main() -> None:
    w, r = load_grid()
    grid = w.index
    trades, closes = segment_trades(w, r)
    scale = brake_scale(grid, closes)
    ws = w.mul(scale, axis=0)

    to_base = w.diff().abs().fillna(w.abs()).sum(axis=1)
    to_brake = ws.diff().abs().fillna(ws.abs()).sum(axis=1)
    pn_base = (w * r).sum(axis=1) - FEE * to_base
    pn_brake = (ws * r).sum(axis=1) - FEE * to_brake

    lg_base = w.where(w > 0, 0.0).mul(r).sum(axis=1)
    sh_base = w.where(w < 0, 0.0).mul(r).sum(axis=1)
    lg_brake = ws.where(ws > 0, 0.0).mul(r).sum(axis=1)
    sh_brake = ws.where(ws < 0, 0.0).mul(r).sum(axis=1)

    per_year = []
    for ylab, ym in year_masks(grid):
        b = path_stats(pn_base, ym)
        v = path_stats(pn_brake, ym)
        lbl = path_stats(lg_base, ym)
        lbr = path_stats(lg_brake, ym)
        sbl = path_stats(sh_base, ym)
        sbr = path_stats(sh_brake, ym)
        per_year.append(dict(
            year=ylab, n_bars=int(ym.sum()),
            brake_share=round(float((scale.to_numpy()[ym] == BRAKE_SCALE).mean()), 4),
            book_base_ret=b["ret"], book_brake_ret=v["ret"],
            book_base_maxdd=b["maxdd"], book_brake_maxdd=v["maxdd"],
            book_base_worst_week=b["worst_week"], book_brake_worst_week=v["worst_week"],
            long_base_ret=lbl["ret"], long_brake_ret=lbr["ret"],
            long_base_maxdd=lbl["maxdd"], long_brake_maxdd=lbr["maxdd"],
            long_base_worst_week=lbl["worst_week"], long_brake_worst_week=lbr["worst_week"],
            short_base_ret=sbl["ret"], short_brake_ret=sbr["ret"],
            short_base_maxdd=sbl["maxdd"], short_brake_maxdd=sbr["maxdd"],
            short_base_worst_week=sbl["worst_week"], short_brake_worst_week=sbr["worst_week"],
        ))

    n_tr = len(trades)
    n_loss = sum(1 for t in trades if t["loss"])
    per_coin_trades = {s: dict(
        n=sum(1 for t in trades if t["coin"] == s),
        n_loss=sum(1 for t in trades if t["coin"] == s and t["loss"]),
        net=round(sum(t["net"] for t in trades if t["coin"] == s), 6),
    ) for s in SYMS}

    eq_b = np.cumprod(1.0 + pn_base.to_numpy())
    eq_v = np.cumprod(1.0 + pn_brake.to_numpy())
    full = dict(
        book_base_ret=round(float(eq_b[-1] - 1), 6), book_brake_ret=round(float(eq_v[-1] - 1), 6),
        book_base_maxdd=round(float(np.max(1 - eq_b / np.maximum.accumulate(eq_b))), 6),
        book_brake_maxdd=round(float(np.max(1 - eq_v / np.maximum.accumulate(eq_v))), 6),
        brake_share=round(float((scale == BRAKE_SCALE).mean()), 4),
    )

    dd_win = sum(1 for y in per_year if y["book_brake_maxdd"] < y["book_base_maxdd"])
    pnl_ok = sum(1 for y in per_year if y["book_brake_ret"] >= y["book_base_ret"])
    promising = bool(dd_win >= 4 and pnl_ok >= 3)

    out = {
        "books": "forward_v205.research_books_d2 (rebuilt exactly)",
        "opens": "engine_real opens_v154.parquet",
        "bound": "2026-09-24T00:00Z (bars open[t]<BOUND, open[t+1]<=BOUND)",
        "symbols": SYMS,
        "anchor_years": [str(a.date()) for a in ANCHORS],
        "rule": (f"scale[t]=0.5 iff >= {LOSS_N} losing base book trades closed in "
                 f"[T-{int(LOSS_WIN.total_seconds() // 3600)}h, T), else 1.0; "
                 "trade=maximal constant-sign run, net=gross-0.0005*(|w[a]|+intra+|w[b]|), "
                 "loss iff net<0, closure=open[b+1]; brake signal from BASE trades only"),
        "definitions": ("w[t]x(open[t+1]/open[t]-1) per coin; TO=L1 undrifted, cost 0.0005xTO; "
                        "eq compounded from 1.0; year maxDD on year-rebased eq; worst_week=min "
                        "42-bar compounded net; legs=gross before costs (costs at book level only)"),
        "n_trades": n_tr, "n_loss_closures": n_loss, "n_closures_scored": int(len(closes)),
        "per_coin_trades": per_coin_trades,
        "per_year": per_year, "full_period": full,
        "decision": {"dd_years_improved": dd_win, "pnl_years_not_lower": pnl_ok,
                     "PROMISING": promising,
                     "rule_text": ("PROMISING iff book maxDD improves in >=4/5 years AND "
                                   "book P&L not lower in >=3/5 (LOYO not needed)")},
        "grid_start": str(grid.min()), "grid_end": str(grid.max()),
        "n_bars": int(len(grid)),
    }
    (HERE / "results.json").write_text(json.dumps(out, indent=1))
    print(json.dumps({"per_year": [(y["year"], y["book_base_ret"], y["book_brake_ret"],
                                    y["book_base_maxdd"], y["book_brake_maxdd"],
                                    y["brake_share"]) for y in per_year],
                      "decision": out["decision"], "full": full}, indent=1))


if __name__ == "__main__":
    main()
