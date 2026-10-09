"""oc_bookband Part A: descriptive book turnover + small-change P&L (LIGHT, 4h only).

Rebuilds forward_v205.research_books_d2 exactly, applies the v421 bear filter
(BTC 4h open < rolling-1200 mean halves positive weights) to get the deployed G2
target T, trailing-90d typical, then per-year turnover / fee proxy / small-change
shares and marginal P&L (4h open-to-open proxy, disclosed simplification).

  python research/tournament/oc_bookband/compute_turnover.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
CACHE = ROOT / "artifacts/research/engine_real"
sys.path.insert(0, str(HERE))
import bookband as bb  # noqa: E402

BOUND = pd.Timestamp("2026-09-24 00:00", tz="UTC")
ANCHORS = [pd.Timestamp(f"{y}-09-24", tz="UTC") for y in (2021, 2022, 2023, 2024, 2025)]
YEAR_LEN = pd.Timedelta(days=365)
SYMS = bb.SYMS


def research_books_d2() -> pd.DataFrame:
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


def main() -> None:
    raw = research_books_d2()
    opens_full = pd.read_parquet(CACHE / "opens_v154.parquet")
    grid = raw.index.intersection(opens_full.dropna(how="all").index).sort_values()
    step = grid[1:] - grid[:-1]
    assert bool((step == pd.Timedelta(hours=4)).all()), "grid is not a regular 4h grid"
    R = raw.reindex(grid)
    o = opens_full.reindex(grid)[SYMS]
    nxt = grid + pd.Timedelta(hours=4)
    scored = (grid < BOUND) & (nxt <= BOUND) & nxt.isin(opens_full.index)
    grid = grid[scored]
    R = R.reindex(grid)
    o = o.reindex(grid)
    o1 = opens_full.reindex(nxt[scored])
    o1.index = grid
    fwd1 = (o1 / o - 1.0)[SYMS]
    assert bool(fwd1.notna().all().all()), "NaN forward return inside bound"
    # Bear filter FIRST (v421): T = deployed G2 target.
    btc = opens_full["BTCUSDT"].sort_index()
    ma = btc.rolling(1200, min_periods=600).mean()
    bear = (btc < ma).reindex(grid).fillna(False)
    T = R.copy()
    pos = (R > 0).to_numpy()
    T = T.where(~(bear.to_numpy()[:, None] & pos), R * 0.5)
    typ = bb.trailing_typical(T)
    bounds = [(a0, a0 + YEAR_LEN) for a0 in ANCHORS]
    per_year = []
    for k, a0 in enumerate(ANCHORS):
        m = (grid >= bounds[k][0]) & (grid < bounds[k][1])
        seg_T = T[m]
        # typical for the segment needs history before the segment: recompute on
        # the full history then slice (causal, no leakage: typ[t] uses only <t).
        seg_typ = typ[m]
        seg_fwd = fwd1[m]
        # turnover needs previous-bar value: for the first bar of the year the
        # delta is vs the last bar BEFORE the year (position carried in).
        # Recompute d on the full path then slice for exact yearly partition.
        per_year.append((str(a0.date()), seg_T, seg_typ, seg_fwd))
    # full-path d for exact partition
    d_full = T.diff()
    d_full.iloc[0] = T.iloc[0]  # first grid bar vs flat 0
    full_out = []
    for ylab, seg_T, seg_typ, seg_fwd in per_year:
        m = (grid >= pd.Timestamp(ylab, tz="UTC")) & (grid < pd.Timestamp(ylab, tz="UTC") + YEAR_LEN)
        dv = d_full.to_numpy()[m]
        Tv_np, ty_np, fw_np = seg_T.to_numpy(), seg_typ.to_numpy(), seg_fwd.to_numpy()
        ok = ~np.isnan(fw_np).any(axis=1)
        Tv_np, dv_np, fw_np, ty_np = Tv_np[ok], dv[ok], fw_np[ok], ty_np[ok]
        to_total = float(np.abs(dv_np).sum())
        gross_total = float((Tv_np * fw_np).sum())
        row = dict(year=ylab, n_bars=int(m.sum()),
                   turnover_total=round(to_total, 4),
                   fee_total=round(to_total * 0.0002, 4),
                   gross_total=round(gross_total, 6))
        for p, key in ((0.10, "p10"), (0.25, "p25")):
            active = np.isfinite(ty_np) & (ty_np > bb.EPS_TYP)
            small = active & (np.abs(dv_np) <= p * np.where(active, ty_np, np.inf))
            n_nonzero = int(((dv_np != 0.0) & active).sum())
            n_small = int(small.sum())
            to_s = float(np.abs(dv_np[small]).sum())
            gross_s = float((dv_np[small] * fw_np[small]).sum())
            row[key] = dict(
                n_nonzero=n_nonzero, n_small=n_small,
                count_share=(round(n_small / n_nonzero, 4) if n_nonzero else None),
                turnover_small=round(to_s, 4),
                turnover_share=(round(to_s / to_total, 4) if to_total else None),
                fee_small=round(to_s * 0.0002, 4),
                gross_small=round(gross_s, 6),
                net_small=round(gross_s - to_s * 0.0002, 6))
        # suppressed-turnover estimate vs band-filtered paths
        full_out.append(row)
    # suppressed turnover: L1 distance between T and F paths per year
    F10 = bb.apply_band(T, typ, 0.10)
    F25 = bb.apply_band(T, typ, 0.25)
    for row in full_out:
        ylab = row["year"]
        m = (grid >= pd.Timestamp(ylab, tz="UTC")) & (grid < pd.Timestamp(ylab, tz="UTC") + YEAR_LEN)
        for F, key in ((F10, "save10"), (F25, "save25")):
            dF = F.diff()
            dF.iloc[0] = F.iloc[0]
            saved = float((d_full[m].abs().sum().sum() - dF[m].abs().sum().sum()))
            row[key] = dict(turnover_saved=round(saved, 4),
                            fee_saved_proxy=round(saved * 0.0002, 4))
    out = dict(
        meta=dict(books="forward_v205.research_books_d2 rebuilt exactly",
                  opens="engine_real opens_v154.parquet",
                  target="T = raw + v421 bear filter (longs x0.5 in bear)",
                  typical="trailing-90d (540-bar) mean |T| strictly before t, min 120",
                  years=[str(a.date()) for a in ANCHORS],
                  proxy="4h open-to-open; fee proxy maker 0.0002/unit turnover; "
                        "gross_small = sum d*fwd1 over small cells (marginal increment)",
                  grid_start=str(grid.min()), grid_end=str(grid.max()),
                  n_bars=int(len(grid))),
        per_year=full_out)
    (HERE / "turnover.json").write_text(json.dumps(out, indent=1))
    for r in full_out:
        print({k: r[k] for k in ("year", "n_bars", "turnover_total", "fee_total",
                                 "gross_total")}, r["p10"], r["p25"],
              r["save10"], r["save25"], flush=True)


def np_abs_le(dnp, typnp, p):
    import numpy as np
    with np.errstate(invalid="ignore"):
        return np.abs(dnp) <= p * typnp


if __name__ == "__main__":
    main()
