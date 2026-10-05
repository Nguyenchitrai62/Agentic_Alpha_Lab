"""oc_bookic: where does the deployed BOT book earn and lose (5 years).

Per PLAN.md: rebuilds forward_v205.research_books_d2 exactly, joins with the
v154 4h opens, and computes per anchor year x coin: Spearman IC of the book
weight vs the next 42-bar open-to-open return; vectorised gross P&L
(weight x next-bar return, no costs) split into long/short legs and into
BTC-trend / BTC-vol regimes; plus P&L inside four drawdown windows.

Single process, only 4h parquet inputs (no 1m needed for this diagnostic).

  python research/tournament/oc_bookic/compute_bookic.py
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
YEAR_LEN = pd.Timedelta(days=365)
WINDOWS = {
    "W1_2022-07-20__2022-11-10": ("2022-07-20", "2022-11-10"),
    "W2_2023-04-17__2023-06-14": ("2023-04-17", "2023-06-14"),
    "W3_2022-01-13__2022-01-22": ("2022-01-13", "2022-01-22"),
    "W4_2024-01-03": ("2024-01-03", "2024-01-03"),
}


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


def spearman(x: pd.Series, y: pd.Series) -> tuple[float, int]:
    both = pd.DataFrame({"x": x, "y": y}).dropna()
    n = len(both)
    if n < 3 or both["x"].std() == 0 or both["y"].std() == 0:
        return float("nan"), int(n)
    return float(both["x"].corr(both["y"], method="spearman")), int(n)


def main() -> None:
    books = research_books_d2()
    opens_full = pd.read_parquet(CACHE / "opens_v154.parquet")
    opens = opens_full.reindex(books.index)
    assert books.index.is_monotonic_increasing and books.index.tz is not None
    grid = books.index.intersection(opens.dropna(how="all").index)
    books, opens = books.reindex(grid), opens.reindex(grid)

    r1 = opens / opens.shift(1)  # placeholder, replaced below (forward-aligned)
    fwd1 = opens.shift(-1) / opens - 1.0  # r[t] = open[t+1]/open[t]-1
    fwd42 = opens.shift(-42) / opens - 1.0
    pnl = books * fwd1  # vectorised gross P&L, no costs
    valid = fwd1.notna().all(axis=1)  # drop last grid bar (no forward return)
    books, opens, fwd1, fwd42, pnl = (d[valid] for d in (books, opens, fwd1, fwd42, pnl))
    del r1

    # Causal BTC regimes on the FULL opens history (from 2017), then reindexed.
    btc = opens_full["BTCUSDT"].sort_index()
    ma1200 = btc.rolling(1200, min_periods=1200).mean()
    above = (btc >= ma1200).reindex(pnl.index)
    lr = np.log(btc / btc.shift(1))
    sig = lr.rolling(180, min_periods=180).std()
    med = sig.rolling(2190, min_periods=1000).median()
    hivol = (sig >= med).reindex(pnl.index)

    long_m = books > 0
    short_m = books < 0

    per_coin, per_year = [], []
    bounds = ANCHORS + [ANCHORS[-1] + YEAR_LEN]  # partition: [A_k, A_{k+1}); last year +365d
    for k, a0 in enumerate(ANCHORS):
        ylab = f"{a0.date()}"
        ym = (pnl.index >= a0) & (pnl.index < bounds[k + 1])
        for s in SYMS:
            w, R, p = books[s][ym], fwd42[s][ym], pnl[s][ym]
            ic, n = spearman(w, R)
            tot = float(p.sum())
            lp = float(p[long_m[s][ym]].sum())
            sp = float(p[short_m[s][ym]].sum())
            ab = above[ym]
            hv = hivol[ym]
            per_coin.append(dict(
                year=ylab, coin=s, n_bars=int(ym.sum()), n_ic=int(n),
                ic_42b=round(ic, 4) if np.isfinite(ic) else None,
                pnl_total=round(tot, 6), pnl_long=round(lp, 6), pnl_short=round(sp, 6),
                pnl_btc_above=round(float(p[ab.fillna(True)].sum()), 6),
                pnl_btc_below=round(float(p[(~ab).fillna(False)].sum()), 6),
                pnl_vol_high=round(float(p[hv.fillna(True)].sum()), 6),
                pnl_vol_low=round(float(p[(~hv).fillna(False)].sum()), 6),
                share_long=round(float(long_m[s][ym].mean()), 4),
                share_short=round(float(short_m[s][ym].mean()), 4),
                mean_abs_w=round(float(books[s][ym].abs().mean()), 6),
            ))
        tot = float(pnl[ym].sum().sum())
        per_year.append(dict(year=ylab, n_bars=int(ym.sum()), pnl_total=round(tot, 6),
                             pnl_long=round(float(pnl[ym][long_m[ym]].sum().sum()), 6),
                             pnl_short=round(float(pnl[ym][short_m[ym]].sum().sum()), 6)))

    win_rows = []
    for wname, (d0, d1) in WINDOWS.items():
        s0 = pd.Timestamp(d0, tz="UTC")
        s1 = pd.Timestamp(d1, tz="UTC") + pd.Timedelta(days=1)
        wm = (pnl.index >= s0) & (pnl.index < s1)
        row = dict(window=wname, n_bars=int(wm.sum()),
                   total=round(float(pnl[wm].sum().sum()), 6))
        for s in SYMS:
            row[s] = round(float(pnl[s][wm].sum()), 6)
        win_rows.append(row)

    totals, legs, regimes, coins = {}, {}, {}, {}
    P = pnl
    totals["pnl_5y_total"] = round(float(P.sum().sum()), 6)
    legs["long"] = round(float(P[long_m].sum().sum()), 6)
    legs["short"] = round(float(P[short_m].sum().sum()), 6)
    regimes["btc_above"] = round(float(P[above.fillna(True)].sum().sum()), 6)
    regimes["btc_below"] = round(float(P[(~above).fillna(False)].sum().sum()), 6)
    regimes["vol_high"] = round(float(P[hivol.fillna(True)].sum().sum()), 6)
    regimes["vol_low"] = round(float(P[(~hivol).fillna(False)].sum().sum()), 6)
    for s in SYMS:
        coins[s] = round(float(P[s].sum()), 6)

    out = {
        "books": "forward_v205.research_books_d2 (rebuilt exactly)",
        "opens": "engine_real opens_v154.parquet",
        "symbols": SYMS,
        "anchor_years": [str(a.date()) for a in ANCHORS],
        "definitions": ("w[t]x(open[t+1]/open[t]-1); IC=spearman(w[t], open[t+42]/open[t]-1); "
                        "trend=BTCopen>=trailing1200b-mean; vol=trailing180b-std vs trailing2190b median; "
                        "windows on bar open_time, end-exclusive+1d; gross, no costs"),
        "per_coin": per_coin, "per_year": per_year, "windows": win_rows,
        "totals_5y": totals, "legs_5y": legs, "regimes_5y": regimes, "coins_5y": coins,
        "grid_start": str(pnl.index.min()), "grid_end": str(pnl.index.max()),
    }
    (HERE / "results.json").write_text(json.dumps(out, indent=1))
    print(json.dumps({"totals_5y": totals, "legs_5y": legs,
                      "regimes_5y": regimes, "coins_5y": coins}, indent=1))


if __name__ == "__main__":
    main()
