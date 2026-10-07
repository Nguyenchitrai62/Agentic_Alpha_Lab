"""oc_bullshort: mirror of the v410 bear-book filter — gate book SHORTS in bull regimes.

Per PLAN.md (pre-registered): rebuilds forward_v205.research_books_d2 exactly,
joins with v154 4h opens, and compares on vectorised book P&L
(weight x next-bar return, 0.05% per unit L1 turnover, deployed vol scale
0.25 / trailing-60d realised vol of each variant's own P&L, cap 2):
  B0 = book with the v410 bear-long filter (longs x0.5 in bear),
  B1 = B0 + shorts x0.5 in bull (BTC 4h open > its 1200-bar mean),
  B2 = B0 + shorts x0 in bull.
Causal: flags at t use open[t] inclusive (known at close of t, as v410);
every vol scale at t uses only bars strictly before t. Single process,
4h inputs only.

  python research/tournament/oc_bullshort/compute_bullshort.py
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
ANN = float(np.sqrt(6 * 365))  # 4h bars/year annualisation
COST = 0.0005
TARGET, CAP = 0.25, 2.0


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


def build_regimes(opens_full: pd.DataFrame, grid: pd.DatetimeIndex) -> tuple[pd.Series, pd.Series]:
    """BTC bull/bear flags, causal, mirrored from v410 (rolling 1200, min 600).

    MA1200[t] = mean(BTC_open[t-1199..t]); bear iff open < MA, bull iff open > MA.
    Computed on the FULL opens history (from 2017), then reindexed to grid.
    NaN-MA -> neither (False, False).
    """
    btc = opens_full["BTCUSDT"].sort_index()
    ma = btc.rolling(1200, min_periods=600).mean()
    bear_full = (btc < ma).fillna(False)
    bull_full = (btc > ma).fillna(False)
    return bear_full.reindex(grid).fillna(False), bull_full.reindex(grid).fillna(False)


def apply_filters(books: pd.DataFrame, bear: pd.Series, bull: pd.Series) -> dict[str, pd.DataFrame]:
    """Raw (unscaled) filtered weights B0/B1/B2 per PLAN.md."""
    arr = books.to_numpy()
    bear_arr = bear.to_numpy()[:, None]
    bull_arr = bull.to_numpy()[:, None]
    b0_arr = np.where(bear_arr & (arr > 0), arr * 0.5, arr)
    b0 = pd.DataFrame(b0_arr, index=books.index, columns=books.columns)
    b1_arr = np.where(bull_arr & (b0_arr < 0), b0_arr * 0.5, b0_arr)
    b1 = pd.DataFrame(b1_arr, index=books.index, columns=books.columns)
    b2_arr = np.where(bull_arr & (b0_arr < 0), 0.0, b0_arr)
    b2 = pd.DataFrame(b2_arr, index=books.index, columns=books.columns)
    return {"B0_bearLong05": b0, "B1_bullShort05": b1, "B2_bullShort00": b2}


def compute_scales(filtered: dict[str, pd.DataFrame], fwd1: pd.DataFrame) -> tuple[dict[str, pd.DataFrame], dict[str, pd.Series]]:
    """Deployed vol scale per variant on its OWN trailing P&L, windows ending at t-1."""
    scaled, scales = {}, {}
    for name, w in filtered.items():
        u = pd.Series((w.to_numpy() * fwd1.to_numpy()).sum(axis=1), index=w.index)
        sig = u.shift(1).rolling(360, min_periods=120).std(ddof=1) * ANN
        s = pd.Series(
            np.where(sig.notna() & (sig > 0), np.minimum(TARGET / sig.where(sig > 0, np.nan), CAP), 1.0),
            index=w.index,
        ).fillna(1.0)
        scaled[name] = w.mul(s, axis=0)
        scales[name] = s
    return scaled, scales


def score_variant(ws: pd.DataFrame, fwd1: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """Net vectorised P&L per bar (causal turnover vs previous scaled weight)."""
    prev = ws.shift(1).fillna(0.0)
    to = (ws - prev).abs().sum(axis=1)
    return (ws * fwd1).sum(axis=1) - COST * to, to


def year_stats(pn: pd.Series) -> dict:
    v = pn.dropna().to_numpy(float)
    n = len(v)
    if n == 0:
        return dict(n_bars=0, ret=None, dd=None, sharpe=None)
    eq = np.cumprod(1.0 + v)
    peak = np.maximum.accumulate(np.concatenate([[1.0], eq]))[1:]
    dd = float(np.max(1.0 - eq / peak)) if n else 0.0
    ret = float(eq[-1] - 1.0)
    sh = float(v.mean() / v.std(ddof=1) * ANN) if n >= 30 and v.std(ddof=1) > 0 else float("nan")
    return dict(n_bars=int(n), ret=round(ret, 6),
                dd=round(dd, 6), sharpe=round(sh, 4) if np.isfinite(sh) else None)


def main() -> None:
    books_raw = research_books_d2()
    opens_full = pd.read_parquet(CACHE / "opens_v154.parquet")
    opens = opens_full.reindex(books_raw.index)
    grid = books_raw.index.intersection(opens.dropna(how="all").index)
    books_raw = books_raw.reindex(grid).sort_index()
    opens = opens.reindex(grid).sort_index()

    fwd1 = opens.shift(-1) / opens - 1.0
    valid = fwd1.notna().all(axis=1)  # drop last grid bar
    books_raw, opens, fwd1 = books_raw[valid], opens[valid], fwd1[valid]

    bear, bull = build_regimes(opens_full, books_raw.index)
    filtered = apply_filters(books_raw, bear, bull)
    scaled, scales = compute_scales(filtered, fwd1)

    bounds = ANCHORS + [YEAR_END]
    masks = [((books_raw.index >= bounds[k]) & (books_raw.index < bounds[k + 1])) for k in range(5)]

    variants = {}
    for name, ws in scaled.items():
        pn, to = score_variant(ws, fwd1)
        per_year = []
        for k, a0 in enumerate(ANCHORS):
            st = year_stats(pn[masks[k]])
            gross = (ws[masks[k]] * fwd1[masks[k]])
            lp = float(gross[ws[masks[k]] > 0].sum().sum())
            sp = float(gross[ws[masks[k]] < 0].sum().sum())
            per_year.append(dict(year=str(a0.date()), **st,
                                 pnl_long=round(lp, 6), pnl_short=round(sp, 6)))
        allm = pd.Series(np.ones(len(pn), bool), index=pn.index)
        all_st = year_stats(pn[allm])
        variants[name] = dict(per_year=per_year, pooled=all_st,
                              mean_abs_w=round(float(ws.abs().mean().mean()), 6),
                              total_turnover=round(float(to.sum()), 4),
                              total_cost=round(float((COST * to).sum()), 6))
        print(f"{name}: " + " | ".join(
            f"{r['year']} ret={r['ret']} dd={r['dd']} sh={r['sharpe']} L={r['pnl_long']} S={r['pnl_short']}"
            for r in per_year), flush=True)

    # decision: effects vs B0 on return AND DD + LOYO per metric
    base = variants["B0_bearLong05"]["per_year"]
    decision = {}
    for name in ("B1_bullShort05", "B2_bullShort00"):
        rows = variants[name]["per_year"]
        dret = [None if (r["ret"] is None or b["ret"] is None) else round(r["ret"] - b["ret"], 6)
                for r, b in zip(rows, base)]
        ddd = [None if (r["dd"] is None or b["dd"] is None) else round(b["dd"] - r["dd"], 6)
               for r, b in zip(rows, base)]
        n_ret = sum(1 for d in dret if d is not None and d > 0)
        n_dd = sum(1 for d in ddd if d is not None and d > 0)
        loyo_ret, loyo_dd = [], []
        for h in range(5):
            tr_ret = [d for k, d in enumerate(dret) if k != h and d is not None]
            tr_dd = [d for k, d in enumerate(ddd) if k != h and d is not None]
            mrt = float(np.mean(tr_ret)) if len(tr_ret) == 4 else float("nan")
            mdd = float(np.mean(tr_dd)) if len(tr_dd) == 4 else float("nan")
            hr = dret[h] is not None and np.isfinite(mrt) and mrt > 0 and np.sign(dret[h]) == np.sign(mrt)
            hd = ddd[h] is not None and np.isfinite(mdd) and mdd > 0 and np.sign(ddd[h]) == np.sign(mdd)
            loyo_ret.append(bool(hr))
            loyo_dd.append(bool(hd))
        promising = bool(n_ret >= 4 and n_dd >= 4 and sum(loyo_ret) >= 4 and sum(loyo_dd) >= 4)
        decision[name] = dict(dRet=dret, dDD=ddd,
                              ret_pos=f"{n_ret}/5", dd_pos=f"{n_dd}/5",
                              loyo_ret=f"{sum(loyo_ret)}/5", loyo_dd=f"{sum(loyo_dd)}/5",
                              promising=promising)
        decision[name]["first4_ret_pos"] = f"{sum(1 for d in dret[:4] if d is not None and d > 0)}/4"
        decision[name]["first4_dd_pos"] = f"{sum(1 for d in ddd[:4] if d is not None and d > 0)}/4"

    out = {
        "definitions": ("grid=books_d2 x opens_v154 inner join; r=open[t+1]/open[t]-1; "
                        "MA1200=mean(BTCopen[t-1199..t]) rolling1200/min600 on full history; "
                        "bear=open<MA bull=open>MA (strict, NaN->neither); "
                        "B0=w*0.5 where bear&long; B1=B0*0.5 where bull&short; B2=0 where bull&short; "
                        "per-variant scale s=min(2,0.25/sig), sig=std(u[t-360..t-1])*sqrt(2190) min120, own u; "
                        "TO=sum|ws[t]-ws[t-1]| (first vs 0); pn=sum(ws*r)-0.0005*TO; eq compounded from 1; "
                        "legs=sum(ws*r) by sign(ws) before costs; years partition [A_k,A_k+1) x4 + [A4,A4+365d); "
                        "Sharpe=mean/std*sqrt(2190); DD on year-rebased eq"),
        "symbols": SYMS, "anchor_years": [str(a.date()) for a in ANCHORS],
        "grid_start": str(books_raw.index.min()), "grid_end": str(books_raw.index.max()),
        "n_bars": int(len(books_raw)),
        "share_bear": round(float(bear.mean()), 4), "share_bull": round(float(bull.mean()), 4),
        "variants": variants, "decision": decision,
        "scale_summary": {k: dict(mean=round(float(v.mean()), 4),
                                  p5=round(float(v.quantile(0.05)), 4),
                                  p95=round(float(v.quantile(0.95)), 4))
                          for k, v in scales.items()},
    }
    (HERE / "results.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(decision, indent=1))


if __name__ == "__main__":
    main()
