"""oc_skewbook: Deribit options skew / put-buy share as BOOK context (5 years).

Per PLAN.md (pre-registered): rebuilds forward_v205.research_books_d2 exactly,
joins with v154 4h opens, attaches the causally-aligned BTC skew
(iv_otm_put - iv_otm_call of the last COMPLETE 4h bar) and put-buy share via
merge_asof(backward), and computes per anchor year x coin: Spearman IC of
skew with next 1-day (R6) / 7-day (R42) returns; plus gross vectorised book
P&L (w[t] x next-bar return, no costs) by skew tercile (cut-offs from
previous years only, expanding window) split into long/short legs.
Primary effect E_y = high-tercile minus low-tercile total P&L in year y.

Single process, only 4h parquet inputs (no 1m). RAM << 1 GB.

  python research/tournament/oc_skewbook/compute_skewbook.py
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
CACHE = ROOT / "artifacts/research/engine_real"
OPT = ROOT / "data/raw/deribit_opt_20260926"
SYMS = ["BNBUSDT", "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]
ANCHORS = [pd.Timestamp(f"{y}-09-24", tz="UTC") for y in (2021, 2022, 2023, 2024, 2025)]
YEAR_LEN = pd.Timedelta(days=365)
CUTOFF = pd.Timestamp("2026-09-24", tz="UTC")


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


def opt_context(frame: pd.DataFrame) -> pd.DataFrame:
    """Per-4h-bar skew and put-buy share from one options parquet."""
    d = frame.copy()
    d["bar"] = pd.to_datetime(d["bar"], utc=True)
    total = d["call_buy"] + d["call_sell"] + d["put_buy"] + d["put_sell"]
    out = pd.DataFrame({
        "bar": d["bar"],
        "skew": d["iv_otm_put"] - d["iv_otm_call"],
        "putbuy": np.where(total > 0, d["put_buy"] / total, 0.0),
    }).sort_values("bar").reset_index(drop=True)
    return out


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
    grid = grid[grid < CUTOFF]
    books, opens = books.reindex(grid), opens.reindex(grid)

    # Causal context: last COMPLETE options bar as of the decision at t+4h is
    # the bar labelled t; merge_asof(backward) also covers missing bars with
    # the most recent earlier complete bar (never any later bar).
    btc = opt_context(pd.read_parquet(OPT / "BTC_options_4h.parquet"))
    eth = opt_context(pd.read_parquet(OPT / "ETH_options_4h.parquet"))
    g = pd.DataFrame({"t": grid}).sort_values("t")
    g = pd.merge_asof(g, btc.rename(columns={"bar": "t", "skew": "skew_btc",
                                             "putbuy": "putbuy_btc"}), on="t",
                      direction="backward")
    g = pd.merge_asof(g.sort_values("t"),
                      eth[["bar", "skew"]].rename(columns={"bar": "t", "skew": "skew_eth"}),
                      on="t", direction="backward")
    g = g.set_index("t").sort_index()
    assert (g.index == grid).all()
    skew_btc, putbuy_btc = g["skew_btc"], g["putbuy_btc"]
    skew_eth = g["skew_eth"]

    fwd1 = opens.shift(-1) / opens - 1.0
    fwd6 = opens.shift(-6) / opens - 1.0
    fwd42 = opens.shift(-42) / opens - 1.0
    pnl = books * fwd1  # vectorised gross P&L, no costs
    valid = fwd1.notna().all(axis=1)  # drop last grid bar (no forward return)
    books_v, opens_v, pnl_v = books[valid], opens[valid], pnl[valid]

    long_m = books_v > 0
    short_m = books_v < 0
    bounds = ANCHORS + [ANCHORS[-1] + YEAR_LEN]  # partition: [A_k, A_{k+1}); last +365d

    # --- IC tables (skew vs forward returns; needs R availability, not pnl) ---
    ic_rows = []
    for k, a0 in enumerate(ANCHORS):
        ylab = f"{a0.date()}"
        ym = (grid >= a0) & (grid < bounds[k + 1])
        for s in SYMS:
            r6 = fwd6[s][ym]
            r42 = fwd42[s][ym]
            sk = skew_btc[ym]
            pb = putbuy_btc[ym]
            ic6, n6 = spearman(sk, r6)
            ic42, n42 = spearman(sk, r42)
            ic6p, _ = spearman(pb, r6)
            ic42p, _ = spearman(pb, r42)
            row = dict(
                year=ylab, coin=s, n_bars=int(ym.sum()),
                n_skew=int(sk.notna().sum()),
                ic6=round(ic6, 4) if np.isfinite(ic6) else None, n_ic6=int(n6),
                ic42=round(ic42, 4) if np.isfinite(ic42) else None, n_ic42=int(n42),
                ic6_putbuy=round(ic6p, 4) if np.isfinite(ic6p) else None,
                ic42_putbuy=round(ic42p, 4) if np.isfinite(ic42p) else None,
            )
            if s in ("BTCUSDT", "ETHUSDT"):
                se = skew_eth[ym]
                e6, ne6 = spearman(se, r6)
                e42, ne42 = spearman(se, r42)
                row["ic6_ethskew"] = round(e6, 4) if np.isfinite(e6) else None
                row["n_ic6_ethskew"] = int(ne6)
                row["ic42_ethskew"] = round(e42, 4) if np.isfinite(e42) else None
                row["n_ic42_ethskew"] = int(ne42)
            ic_rows.append(row)

    # --- Tercile cut-offs from previous years only (expanding, causal) ---
    # History = the raw BTC 4h options skew for bar < A_k (back to 2019), NOT
    # the book grid (which starts 2021-09-24 and would leave year 1 empty).
    cutoffs, terc_rows, leg_rows = [], [], []
    E = {}
    pv_idx = pnl_v.index
    btc_hist = btc.dropna(subset=["skew"]).set_index("bar").sort_index()["skew"]
    btc_hist = btc_hist[btc_hist.index < CUTOFF]
    for k, a0 in enumerate(ANCHORS):
        ylab = f"{a0.date()}"
        hist = btc_hist[btc_hist.index < a0]
        q33, q67 = float(hist.quantile(1 / 3)), float(hist.quantile(2 / 3))
        cutoffs.append(dict(year=ylab, q33=round(q33, 4), q67=round(q67, 4),
                            n_hist=int(len(hist)),
                            hist_from=str(hist.index.min()),
                            hist_to=str(hist.index.max())))
        ym = (pv_idx >= a0) & (pv_idx < bounds[k + 1])
        sk = skew_btc.reindex(pv_idx)[ym]
        lo = sk <= q33
        hi = sk > q67
        mid = (~lo) & (~hi) & sk.notna()
        nan_m = sk.isna()
        masks = {"low": lo, "mid": mid, "high": hi}
        tot_y = 0.0
        P = pnl_v[ym].values  # rows = year bars, cols = SYMS order
        W = books_v[ym].values
        for tname, tm in masks.items():
            tarr = tm.values  # positional: tm is indexed by pv_idx[ym], same order
            sub = P[tarr]
            row = dict(year=ylab, tercile=tname, n_bars=int(tarr.sum()),
                       pnl_total=round(float(sub.sum()), 6),
                       pnl_long=round(float(sub[(W[tarr] > 0)].sum()), 6),
                       pnl_short=round(float(sub[(W[tarr] < 0)].sum()), 6))
            per_coin = {}
            for j, s in enumerate(SYMS):
                per_coin[s] = round(float(sub[:, j].sum()), 6)
            row["per_coin"] = per_coin
            terc_rows.append(row)
        Ey = float(P[hi.values].sum() - P[lo.values].sum())
        E[ylab] = round(Ey, 6)
        tot_y = float(pnl_v[ym].sum().sum())
        leg_rows.append(dict(
            year=ylab, n_bars=int(ym.sum()), n_nan_skew=int(nan_m.sum()),
            pnl_total=round(tot_y, 6),
            E_high_minus_low=round(Ey, 6),
            sign="neg" if Ey < 0 else ("pos" if Ey > 0 else "zero"),
        ))

    S = "neg" if sum(E.values()) < 0 else ("pos" if sum(E.values()) > 0 else "zero")
    loyo = []
    for ylab in [f"{a.date()}" for a in ANCHORS]:
        rest = sum(v for k2, v in enumerate(E.values()) if list(E)[k2] != ylab)
        sj = "neg" if rest < 0 else ("pos" if rest > 0 else "zero")
        loyo.append(dict(excluded_year=ylab, sign_rest=sj, holds=bool(sj == S)))
    n_sign = sum(1 for r in leg_rows if r["sign"] == S)
    verdict = "PROMISING" if (n_sign >= 4 and sum(l["holds"] for l in loyo) >= 4) else "NOT PROMISING"

    out = {
        "books": "forward_v205.research_books_d2 (rebuilt exactly)",
        "opens": "engine_real opens_v154.parquet",
        "options": {"primary": "BTC_options_4h skew=iv_otm_put-iv_otm_call, putbuy=put_buy/total",
                    "secondary": "ETH_options_4h skew (ETH/BTC diagnostics only)"},
        "symbols": SYMS,
        "anchor_years": [str(a.date()) for a in ANCHORS],
        "definitions": ("skew[t]=last COMPLETE 4h options bar as of decision (bar==t, asof-backward); "
                        "R6=open[t+6]/open[t]-1; R42=open[t+42]/open[t]-1; "
                        "IC=spearman(context[t], R[t]); cut-offs q33/q67 of BTC skew over t<A_k; "
                        "pnl[t]=w[t]x(open[t+1]/open[t]-1) gross, no costs"),
        "grid_start": str(grid.min()), "grid_end": str(grid.max()),
        "n_grid": int(len(grid)), "n_pnl": int(valid.sum()),
        "ic": ic_rows, "cutoffs": cutoffs, "terciles": terc_rows,
        "E_high_minus_low": E, "full_sign": S, "loyo": loyo,
        "per_year": leg_rows, "verdict_rule": verdict,
    }
    (HERE / "results.json").write_text(json.dumps(out, indent=1))
    print(json.dumps({"E": E, "sign": S,
                      "n_same_sign": n_sign,
                      "loyo_holds": sum(l["holds"] for l in loyo),
                      "verdict_rule": verdict}, indent=1))


if __name__ == "__main__":
    main()
