"""oc_dombook: walk-forward test of ONE pre-registered BTC-dominance book scaler.

Per PLAN.md (pre-registered): rebuilds forward_v205.research_books_d2 exactly,
joins with v154 4h opens, computes dom30 (BTC 30d log return minus
equal-weight majors 30d log return, 180 bars) causally on full opens history,
and compares the deployed vol-targeted book (0.25 / trailing-60d realised vol
of unscaled book P&L, cap 2) against the SAME book tilted by the dominance
regime (x1.25 top tercile / x0.75 bottom tercile / x1.0 middle, cut-offs from
strictly-previous history). Net P&L = weight x next-bar return minus 0.05%
per unit L1 turnover. Single process, 4h inputs only, no 1m data.

  python research/tournament/oc_dombook/compute_dombook.py
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
CUTOFF = pd.Timestamp("2026-09-24", tz="UTC")
ANN = float(np.sqrt(6 * 365))  # 4h bars/year annualisation
COST = 0.0005
TARGET, CAP = 0.25, 2.0
B30 = 180
TOL = 1e-12


def research_books_d2() -> pd.DataFrame:
    """Mirror of oc_bookic compute (same files, same math)."""
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


def compute_dom30(opens_full: pd.DataFrame) -> pd.Series:
    """Causal dom30 on full opens history (NaN until 180-bar lag available)."""
    o = opens_full.sort_index()[SYMS]
    r30 = np.log(o / o.shift(B30))
    return r30["BTCUSDT"] - r30[SYMS].mean(axis=1)


def year_stats(pn: pd.Series) -> dict:
    v = pn.dropna().to_numpy(float)
    n = len(v)
    if n == 0:
        return dict(n_bars=0, ret=None, dd=None, sharpe=None)
    eq = np.cumprod(1.0 + v)
    peak = np.maximum.accumulate(np.concatenate([[1.0], eq]))[1:]
    dd = float(np.max(1.0 - eq / peak)) if n else None
    ret = float(eq[-1] - 1.0)
    if n < 30:
        sh = None
    else:
        sd = float(np.std(v, ddof=1))
        sh = float(np.mean(v) / sd * ANN) if sd > 0 else None
    return dict(n_bars=int(n), ret=ret, dd=dd, sharpe=sh)


def main() -> None:
    books_full = research_books_d2()
    opens_full = pd.read_parquet(CACHE / "opens_v154.parquet")
    grid_all = books_full.index.intersection(opens_full.dropna(how="all").index)
    grid_all = grid_all.sort_values()
    grid_all = grid_all[grid_all < CUTOFF]
    books = books_full.reindex(grid_all)
    opens = opens_full.reindex(grid_all)[SYMS]
    assert books.index.is_monotonic_increasing and books.index.tz is not None

    fwd1 = opens.shift(-1) / opens - 1.0
    valid = fwd1.notna().all(axis=1)
    books, opens, fwd1 = books[valid], opens[valid], fwd1[valid]

    dom_full = compute_dom30(opens_full)
    dom = dom_full.reindex(books.index)

    # Deployed vol scale, window ends at t-1 (strictly before t).
    u = (books.to_numpy() * fwd1.to_numpy()).sum(axis=1)
    U = pd.Series(u, index=books.index)
    sig0 = U.shift(1).rolling(360, min_periods=120).std(ddof=1) * ANN
    s0 = pd.Series(
        np.where(sig0.notna() & (sig0 > 0),
                 np.minimum(TARGET / sig0.where(sig0 > 0, np.nan), CAP), 1.0),
        index=books.index).fillna(1.0)

    # Literal year masks [A_k, A_k+365d); orphans belong to no year.
    masks = [(books.index >= a) & (books.index < a + YEAR_LEN) for a in ANCHORS]
    scored = pd.Series(False, index=books.index)
    for m_ in masks:
        scored |= m_
    # Orphans = scored-range grid bars inside [2021-09-24, 2026-09-24) in no year.
    in_range = (books.index >= ANCHORS[0]) & (books.index < ANCHORS[-1] + YEAR_LEN)
    n_orphan = int((in_range & ~scored).sum())

    wb = books.mul(s0, axis=0)  # base weights (identical vol scale in both legs)
    to_base_full = (wb - wb.shift(1).fillna(0.0)).abs().sum(axis=1)
    pn_base_full = (wb * fwd1).sum(axis=1) - COST * to_base_full

    per_year, loo_years = [], []
    for k, a0 in enumerate(ANCHORS):
        ylab = str(a0.date())
        # PLAN-literal: cut-offs over the FULL opens-history dom30 strictly
        # before the anchor (bars < A_k from 2017), NOT the books grid
        # (which starts at 2021-09-24 and is empty for year 1).
        hist = dom_full[(dom_full.index < a0) & dom_full.notna()]
        lo, hi = float(hist.quantile(0.33)), float(hist.quantile(0.67))
        ym = masks[k]
        d = dom[ym]
        mult = pd.Series(1.0, index=books.index[ym])
        mult[d < lo] = 0.75  # boundary ties stay mid (strict inequalities)
        mult[d > hi] = 1.25
        n_lo = int(((d < lo)).sum())
        n_hi = int(((d > hi)).sum())
        n_mid = int(ym.sum()) - n_lo - n_hi
        n_nan = int(d.isna().sum())
        # Scaled series with THESE walk-forward cuts, built on the full grid so
        # turnover stays a causal global chain (vs previous grid bar); sliced to
        # this year below. s0 is identical in both legs by construction.
        ws_full = books.mul(s0, axis=0)
        mfull = pd.Series(1.0, index=books.index)
        dall = dom
        mfull[dall < lo] = 0.75
        mfull[dall > hi] = 1.25
        mfull[dall.isna()] = 1.0
        ws_full = ws_full.mul(mfull, axis=0)
        to_s = (ws_full - ws_full.shift(1).fillna(0.0)).abs().sum(axis=1)
        pn_s_full = (ws_full * fwd1).sum(axis=1) - COST * to_s
        pb, ps = pn_base_full[ym], pn_s_full[ym]
        sb, ss = year_stats(pb), year_stats(ps)
        dret = ss["ret"] - sb["ret"]
        ddd = sb["dd"] - ss["dd"]
        per_year.append(dict(
            year=ylab, cut_lo=lo, cut_hi=hi, hist_bars=int(len(hist)),
            n=int(ym.sum()), n_lo=n_lo, n_mid=n_mid, n_hi=n_hi, n_nan_regime=n_nan,
            mean_scale=float(s0[ym].mean()),
            base_ret=sb["ret"], base_dd=sb["dd"], base_sharpe=sb["sharpe"],
            scaled_ret=ss["ret"], scaled_dd=ss["dd"], scaled_sharpe=ss["sharpe"],
            dret=dret, ddd=ddd,
            ret_better=bool(dret is not None and dret > 0),
            dd_not_worse=bool(ddd is not None and ddd >= -TOL),
            cost_base=float((COST * to_base_full[ym]).sum()),
            cost_scaled=float((COST * to_s[ym]).sum()),
        ))
        loo_years.append(dict(mfull=mfull, ws_full=ws_full, pn_s_full=pn_s_full))

    # Leave-one-year-out: cuts from pooled other-4-years bars, applied to held-out year.
    loo = []
    for h, a0 in enumerate(ANCHORS):
        others = pd.Series(False, index=books.index)
        for k2 in range(5):
            if k2 != h:
                others |= masks[k2]
        pool = dom[others & dom.notna()]
        lo, hi = float(pool.quantile(0.33)), float(pool.quantile(0.67))
        # Training: pooled other-4-years excess with THESE cuts (full-grid recompute).
        mfull = pd.Series(1.0, index=books.index)
        mfull[dom < lo] = 0.75
        mfull[dom > hi] = 1.25
        mfull[dom.isna()] = 1.0
        ws_loo = books.mul(s0, axis=0).mul(mfull, axis=0)
        to_loo = (ws_loo - ws_loo.shift(1).fillna(0.0)).abs().sum(axis=1)
        pn_loo = (ws_loo * fwd1).sum(axis=1) - COST * to_loo
        train_excess = float(
            np.prod(1.0 + pn_loo[others].to_numpy(float)) - np.prod(1.0 + pn_base_full[others].to_numpy(float)))
        train_ddd_list = []
        for k2 in range(5):
            if k2 == h:
                continue
            sb2, ss2 = year_stats(pn_base_full[masks[k2]]), year_stats(pn_loo[masks[k2]])
            train_ddd_list.append(ss2["dd"] is not None and sb2["dd"] is not None
                                  and (sb2["dd"] - ss2["dd"]) >= -TOL)
        hm = masks[h]
        d = dom[hm]
        n_lo = int((d < lo).sum())
        n_mid = int(hm.sum()) - n_lo - int((d > hi).sum())
        n_hi = int((d > hi).sum())
        sb, ss = year_stats(pn_base_full[hm]), year_stats(pn_loo[hm])
        dret = ss["ret"] - sb["ret"]
        ddd = sb["dd"] - ss["dd"]
        side_ok = bool(min(n_lo, n_hi) >= 50)
        train_ret_ok = bool(train_excess > 0)
        train_dd_ok = bool(all(train_ddd_list))
        loo.append(dict(
            heldout=str(a0.date()), cut_lo=lo, cut_hi=hi, pool_bars=int(len(pool)),
            n_lo=n_lo, n_mid=n_mid, n_hi=n_hi,
            train_excess=train_excess, train_ret_ok=train_ret_ok, train_dd_ok=train_dd_ok,
            test_dret=dret, test_ddd=ddd,
            ret_holds=bool(train_ret_ok and dret is not None and dret > 0 and side_ok),
            dd_holds=bool(train_dd_ok and ddd is not None and ddd >= -TOL and side_ok),
        ))

    # Pooled 5y (concatenated year bars, orphans excluded), descriptive.
    base_5y = pn_base_full[scored]
    # Walk-forward scaled pooled: stitch per-year scaled series (turnover at year
    # boundaries uses the global chain stored in loo_years of each year).
    ps_list = [loo_years[k]["pn_s_full"][masks[k]] for k in range(5)]
    scaled_5y = pd.concat(ps_list).sort_index()
    s5_base, s5_scaled = year_stats(base_5y), year_stats(scaled_5y)

    ret_sign = sum(1 for r in per_year if r["ret_better"])
    dd_ok = sum(1 for r in per_year if r["dd_not_worse"])
    ret_loo = sum(1 for r in loo if r["ret_holds"])
    dd_loo = sum(1 for r in loo if r["dd_holds"])
    verdict = (ret_sign >= 4 and ret_loo >= 4 and dd_ok >= 4)

    out = dict(
        meta=dict(
            anchors=[str(a.date()) for a in ANCHORS],
            year_def="[A_k, A_k+365d) literal; orphan 4h bars excluded from per-year and pooled",
            book="forward_v205.research_books_d2 rebuilt exactly; same s0 vol scale (0.25/60d sig, cap 2) in both legs",
            dom30="log(BTC[t]/BTC[t-180]) - mean_s log(S[t]/S[t-180]) on full 4h opens history, causal",
            scaler="x1.25 top tercile / x0.75 bottom tercile / x1.0 middle; cuts = 33rd/67th pct of dom30 over bars < anchor",
            pnl="pn[t]=sum ws[t]*r[t] - 0.0005*sum|ws[t]-ws[t-1]| (first grid bar vs flat 0); r=open[t+1]/open[t]-1",
            equity="per-year stats on year-rebased equity from 1.0; Sharpe=mean/std*sqrt(2190)",
            cutoff="2026-09-24T00:00Z",
            grid_start=str(books.index.min()), grid_end=str(books.index.max()),
            n_grid_bars=int(len(books)), n_orphan_bars=n_orphan,
        ),
        per_year=per_year, loo=loo,
        pooled=dict(base=s5_base, scaled=s5_scaled,
                    dret=(s5_scaled["ret"] - s5_base["ret"])
                    if s5_scaled["ret"] is not None else None,
                    ddd=(s5_base["dd"] - s5_scaled["dd"])
                    if s5_scaled["dd"] is not None else None),
        gates=dict(ret_sign_years=ret_sign, dd_not_worse_years=dd_ok,
                   ret_loo_holds=ret_loo, dd_loo_holds=dd_loo,
                   promising=bool(verdict)),
        definitions=("PROMISING = dRet>0 in >=4/5 years AND return-LOO holds >=4/5 "
                     "AND DD not worse (dDD>=0) in >=4/5 years; DD-LOO descriptive"),
    )
    (HERE / "results.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(dict(per_year=[(r["year"], round(r["dret"], 4), round(r["ddd"], 4)) for r in per_year],
                        gates=out["gates"]), indent=1))


if __name__ == "__main__":
    main()
