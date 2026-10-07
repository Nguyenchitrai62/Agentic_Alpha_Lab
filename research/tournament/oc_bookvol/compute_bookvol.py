"""oc_bookvol: book-level volatility-targeting variants on vectorised book P&L.

Per PLAN.md (pre-registered): rebuilds forward_v205.research_books_d2 exactly,
joins with v154 4h opens, and compares the deployed book-level scale
(0.25 / trailing-60d realised vol of the book P&L, cap 2) against
(a) per-coin 30d risk-parity tilt, (b) slower 120d book window,
(c) 60d downside-semivariance target — all on weight x next-bar return
minus 0.05% per unit L1 turnover. Causal: every scale at t uses only bars
strictly before t. Single process, 4h inputs only.

  python research/tournament/oc_bookvol/compute_bookvol.py
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


def roll_std(s: pd.Series, window: int, min_periods: int) -> pd.Series:
    return s.rolling(window, min_periods=min_periods).std(ddof=1)


def compute_scales(books: pd.DataFrame, fwd1: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Per-variant scaled weights. All windows end at t-1 (strictly before t).

    books/fwd1 share the scored index; u[s] = (books*fwd1).sum(axis=1).
    sigma[t] uses u[t-W..t-1] via shift(1).rolling(W) — never u[t].
    """
    W = books.to_numpy()
    R = fwd1.to_numpy()
    U = pd.Series((W * R).sum(axis=1), index=books.index)

    # V0 deployed: 60d book vol, window ends t-1
    sig0 = roll_std(U.shift(1), 360, 120) * ANN
    s0 = pd.Series(np.where(sig0.notna() & (sig0 > 0),
                            np.minimum(TARGET / sig0.where(sig0 > 0, np.nan), CAP), 1.0),
                   index=books.index).fillna(1.0)
    # Vb slow: 120d book vol
    sigB = roll_std(U.shift(1), 720, 240) * ANN
    sB = pd.Series(np.where(sigB.notna() & (sigB > 0),
                            np.minimum(TARGET / sigB.where(sigB > 0, np.nan), CAP), 1.0),
                   index=books.index).fillna(1.0)
    # Vc semivariance 60d: sqrt(mean(min(0,u-mu)^2))*sqrt(2)*ANN, window ends t-1
    def semi(col: pd.Series) -> float:
        v = col.dropna().to_numpy()
        if len(v) < 120:
            return np.nan
        mu = v.mean()
        return float(np.sqrt(np.mean(np.minimum(0.0, v - mu) ** 2)) * np.sqrt(2.0) * ANN)
    semi_raw = U.shift(1).rolling(360, min_periods=120).apply(semi, raw=False)
    sC = pd.Series(np.where(semi_raw.notna() & (semi_raw > 0),
                            np.minimum(TARGET / semi_raw.where(semi_raw > 0, np.nan), CAP), 1.0),
                   index=books.index).fillna(1.0)

    # Va risk parity: per-coin 30d vol, windows end at t-1
    sigc = {}
    for c in SYMS:
        sigc[c] = roll_std(fwd1[c].shift(1), 180, 60) * ANN
    sigc_df = pd.DataFrame(sigc)
    inv = 1.0 / sigc_df
    ok = np.isfinite(inv.to_numpy()).all(axis=1) & (sigc_df > 0).all(axis=1).to_numpy()
    tilt = pd.DataFrame(np.ones((len(books), len(SYMS))), index=books.index, columns=SYMS)
    m = inv.mean(axis=1)
    raw_tilt = inv.div(m, axis=0).clip(0.5, 2.0)
    tilt[ok] = raw_tilt[ok]

    out = {
        "base_60d": books.mul(s0, axis=0),
        "a_riskparity30d": books * tilt,
        "b_slow120d": books.mul(sB, axis=0),
        "c_semi60d": books.mul(sC, axis=0),
    }
    aux = {"s0": s0, "sB": sB, "sC": sC, "tilt": tilt,
           "sig0": sig0, "sigB": sigB, "semi": semi_raw, "sigc": sigc_df}
    return out, aux


def score_variant(ws: pd.DataFrame, fwd1: pd.DataFrame) -> pd.Series:
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
    books = research_books_d2()
    opens_full = pd.read_parquet(CACHE / "opens_v154.parquet")
    opens = opens_full.reindex(books.index)
    grid = books.index.intersection(opens.dropna(how="all").index)
    books, opens = books.reindex(grid).sort_index(), opens.reindex(grid).sort_index()

    fwd1 = opens.shift(-1) / opens - 1.0
    valid = fwd1.notna().all(axis=1)  # drop last grid bar
    books, opens, fwd1 = books[valid], opens[valid], fwd1[valid]

    scaled, aux = compute_scales(books, fwd1)

    # year masks: partition [A_k, A_{k+1}), last +365d
    bounds = ANCHORS + [YEAR_END]
    masks = [((books.index >= bounds[k]) & (books.index < bounds[k + 1])) for k in range(5)]

    variants = {}
    for name, ws in scaled.items():
        pn, to = score_variant(ws, fwd1)
        per_year = []
        for k, a0 in enumerate(ANCHORS):
            st = year_stats(pn[masks[k]])
            per_year.append(dict(year=str(a0.date()), **st))
        all_st = year_stats(pn[pd.Series(np.ones(len(pn), bool), index=pn.index)])
        variants[name] = dict(per_year=per_year, pooled=all_st,
                              mean_abs_w=round(float(ws.abs().mean().mean()), 6),
                              total_turnover=round(float(to.sum()), 4),
                              total_cost=round(float((COST * to).sum()), 6))
        print(f"{name}: " + " | ".join(
            f"{r['year']} ret={r['ret']} dd={r['dd']} sh={r['sharpe']}" for r in per_year),
            flush=True)

    # decision: effects vs base + LOYO per metric
    base = variants["base_60d"]["per_year"]
    decision = {}
    for name in ("a_riskparity30d", "b_slow120d", "c_semi60d"):
        rows = variants[name]["per_year"]
        dsh = [None if (r["sharpe"] is None or b["sharpe"] is None) else round(r["sharpe"] - b["sharpe"], 4)
               for r, b in zip(rows, base)]
        ddd = [None if (r["dd"] is None or b["dd"] is None) else round(b["dd"] - r["dd"], 6)
               for r, b in zip(rows, base)]
        n_sh = sum(1 for d in dsh if d is not None and d > 0)
        n_dd = sum(1 for d in ddd if d is not None and d > 0)
        loyo_sh, loyo_dd = [], []
        for h in range(5):
            tr_sh = [d for k, d in enumerate(dsh) if k != h and d is not None]
            tr_dd = [d for k, d in enumerate(ddd) if k != h and d is not None]
            msh = float(np.mean(tr_sh)) if len(tr_sh) == 4 else float("nan")
            mdd = float(np.mean(tr_dd)) if len(tr_dd) == 4 else float("nan")
            hs = dsh[h] is not None and np.isfinite(msh) and msh > 0 and np.sign(dsh[h]) == np.sign(msh)
            hd = ddd[h] is not None and np.isfinite(mdd) and mdd > 0 and np.sign(ddd[h]) == np.sign(mdd)
            loyo_sh.append(bool(hs))
            loyo_dd.append(bool(hd))
        promising = bool(n_sh >= 4 and n_dd >= 4 and sum(loyo_sh) >= 4 and sum(loyo_dd) >= 4)
        decision[name] = dict(dSharpe=dsh, dDD=ddd,
                              sharpe_pos=f"{n_sh}/5", dd_pos=f"{n_dd}/5",
                              loyo_sharpe=f"{sum(loyo_sh)}/5", loyo_dd=f"{sum(loyo_dd)}/5",
                              promising=promising)
        # descriptive first-four-year sensitivity (repo selection window)
        decision[name]["first4_sharpe_pos"] = f"{sum(1 for d in dsh[:4] if d is not None and d > 0)}/4"
        decision[name]["first4_dd_pos"] = f"{sum(1 for d in ddd[:4] if d is not None and d > 0)}/4"

    out = {
        "definitions": ("grid=books_d2 x opens_v154 inner join; r=open[t+1]/open[t]-1; "
                        "u=sum(w*r); V0 scale=min(2,0.25/sig60d), sig=std(u[t-360..t-1])*sqrt(2190) min120; "
                        "Va tilt=(1/sig_c30d)/mean clipped [0.5,2], sig_c=std(r_c[t-180..t-1])*sqrt(2190) min60, no book scale; "
                        "Vb same as V0 window 720 min240; Vc semi=sqrt(mean(min(0,u-mu)^2))*sqrt(2)*sqrt(2190) window 360 min120; "
                        "all scales use bars strictly before t; TO=sum|ws[t]-ws[t-1]| (first vs 0); "
                        "pn=sum(ws*r)-0.0005*TO; eq compounded from 1; years partition [A_k,A_k+1) x4 + [A4,A4+365d); "
                        "Sharpe=mean/std*sqrt(2190); DD on year-rebased eq"),
        "symbols": SYMS, "anchor_years": [str(a.date()) for a in ANCHORS],
        "grid_start": str(books.index.min()), "grid_end": str(books.index.max()),
        "n_bars": int(len(books)),
        "variants": variants, "decision": decision,
        "scale_summary": {k: dict(mean=round(float(v.stack().mean() if isinstance(v, pd.DataFrame) else v.mean()), 4),
                                  p5=round(float(v.stack().quantile(0.05) if isinstance(v, pd.DataFrame) else v.quantile(0.05)), 4),
                                  p95=round(float(v.stack().quantile(0.95) if isinstance(v, pd.DataFrame) else v.quantile(0.95)), 4))
                          for k, v in (("s0", aux["s0"]), ("sB", aux["sB"]), ("sC", aux["sC"]))},
    }
    (HERE / "results.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(decision, indent=1))


if __name__ == "__main__":
    main()
