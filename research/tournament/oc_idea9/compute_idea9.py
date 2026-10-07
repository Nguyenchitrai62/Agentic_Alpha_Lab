"""oc_idea9: US-equity overnight-gap book tilt (IDEAS.md idea #9).

Per PLAN.md (pre-registered): BASE = deployed 60d book-vol scale on
forward_v205.research_books_d2 (rebuilt exactly) x v154 4h opens;
TILT = BASE x dial, dial = 0.75 iff SPX prior-session log-return
(strictly before T) is below the pre-anchor 25th percentile, else 1.0.
Vectorised open-to-open replay: pn[t] = ws.r - 0.0005*TO. Causal:
every scale/dial at t uses only information strictly before t.

  python research/tournament/oc_idea9/compute_idea9.py
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
CACHE = ROOT / "artifacts/research/engine_real"
SPX_CSV = ROOT / "data/raw/newinfo_idea9/spx_daily.csv"
SYMS = ["BNBUSDT", "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]
ANCHORS = [pd.Timestamp(f"{y}-09-24", tz="UTC") for y in (2021, 2022, 2023, 2024, 2025)]
YEAR_END = ANCHORS[-1] + pd.Timedelta(days=365)
ANN = float(np.sqrt(6 * 365))  # 4h bars/year annualisation
COST = 0.0005
TARGET, CAP = 0.25, 2.0
DIAL_DOWN = 0.75
EMBARGO = pd.Timedelta(days=7)
SPX_START = dt.date(2016, 1, 1)


# ---------------------------------------------------------------- books

def research_books_d2() -> pd.DataFrame:
    """Mirror of scripts/forward_v205.py::research_books_d2 (same as oc_bookvol)."""
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


# ---------------------------------------------------------------- SPX gap

def _dst_bounds(year: int) -> tuple[dt.date, dt.date]:
    """US DST: [2nd Sunday of March, 1st Sunday of November) (dates, EDT inside)."""
    def nth_sunday(y: int, m: int, n: int) -> dt.date:
        d = dt.date(y, m, 1)
        first = d + dt.timedelta(days=(6 - d.weekday()) % 7)
        return first + dt.timedelta(weeks=n - 1)
    return nth_sunday(year, 3, 2), nth_sunday(year, 11, 1)


def close_utc_for(day: dt.date) -> pd.Timestamp:
    """SPX 16:00 ET close as UTC: 20:00 in DST, else 21:00."""
    s, e = _dst_bounds(day.year)
    hour = 20 if (s <= day < e) else 21
    return pd.Timestamp(day.year, day.month, day.day, hour, tz="UTC")


def load_spx() -> pd.DataFrame:
    """Daily ^GSPC with close_utc and prior-session log-return gap (causal per row)."""
    d = pd.read_csv(SPX_CSV, parse_dates=["date"])
    d["day"] = d["date"].dt.date
    d["close_utc"] = [close_utc_for(x) for x in d["day"]]
    d = d.sort_values("close_utc").reset_index(drop=True)
    d["prev_close"] = d["close"].shift(1)
    d["gap"] = np.log(d["close"] / d["prev_close"])
    return d[["day", "close_utc", "close", "prev_close", "gap"]]


def thresholds(daily: pd.DataFrame) -> dict[str, float]:
    """q25(A_k): 25th pct of gap over rows with close_utc < A_k - 7d (expanding)."""
    out = {}
    for a in ANCHORS:
        cut = a - EMBARGO
        g = daily.loc[daily["close_utc"] < cut, "gap"].dropna()
        out[str(a.date())] = float(g.quantile(0.25))
    return out


def gaps_for_T(grid_idx: pd.DatetimeIndex, daily: pd.DataFrame) -> pd.Series:
    """gap(T): session log-return of latest SPX day with close_utc strictly < T."""
    left = pd.DataFrame({"T": grid_idx}).sort_values("T")
    right = daily[["close_utc", "gap"]].sort_values("close_utc")
    m = pd.merge_asof(left, right, left_on="T", right_on="close_utc",
                       direction="backward", allow_exact_matches=False)
    return pd.Series(m["gap"].to_numpy(), index=grid_idx)


def dial_for(grid_idx: pd.DatetimeIndex, daily: pd.DataFrame,
             q: dict[str, float]) -> pd.Series:
    """0.75 iff gap(T) < q25 of T's anchor year, else 1.0 (NaN gap -> 1.0)."""
    gap = gaps_for_T(grid_idx, daily)
    bounds = ANCHORS + [YEAR_END]
    year_of = np.zeros(len(grid_idx), dtype=int)
    for k in range(5):
        year_of[(grid_idx >= bounds[k]) & (grid_idx < bounds[k + 1])] = k
    qv = np.array([q[str(ANCHORS[k].date())] for k in year_of])
    dial = np.where(gap.to_numpy() < qv, DIAL_DOWN, 1.0)
    dial = np.where(np.isfinite(gap.to_numpy()), dial, 1.0)
    return pd.Series(dial, index=grid_idx)


# ---------------------------------------------------------------- scales

def roll_std(s: pd.Series, window: int, min_periods: int) -> pd.Series:
    return s.rolling(window, min_periods=min_periods).std(ddof=1)


def compute_scales(books: pd.DataFrame, fwd1: pd.DataFrame,
                   dial: pd.Series) -> tuple[dict[str, pd.DataFrame], dict]:
    """BASE (deployed 60d book-vol, windows end at t-1) and TILT = BASE x dial."""
    W = books.to_numpy()
    R = fwd1.to_numpy()
    U = pd.Series((W * R).sum(axis=1), index=books.index)
    sig0 = roll_std(U.shift(1), 360, 120) * ANN
    s0 = pd.Series(np.where(sig0.notna() & (sig0 > 0),
                            np.minimum(TARGET / sig0.where(sig0 > 0, np.nan), CAP), 1.0),
                   index=books.index).fillna(1.0)
    base = books.mul(s0, axis=0)
    tilt = base.mul(dial.reindex(books.index).fillna(1.0), axis=0)
    return {"base_60d": base, "tilt_gap075": tilt}, {"s0": s0, "sig0": sig0}


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


def worst_day(pn: pd.Series) -> float:
    d = pn.groupby(pn.index.floor("D")).sum()
    return float(d.min()) if len(d) else float("nan")


def main() -> None:
    books = research_books_d2()
    opens_full = pd.read_parquet(CACHE / "opens_v154.parquet")
    opens = opens_full.reindex(books.index)
    grid = books.index.intersection(opens.dropna(how="all").index)
    books, opens = books.reindex(grid).sort_index(), opens.reindex(grid).sort_index()

    fwd1 = opens.shift(-1) / opens - 1.0
    valid = fwd1.notna().all(axis=1)  # drop last grid bar
    books, opens, fwd1 = books[valid], opens[valid], fwd1[valid]

    daily = load_spx()
    assert (daily["day"] < pd.Timestamp("2026-09-24").date()).all()
    q = thresholds(daily)
    dial = dial_for(books.index, daily, q)
    fire = float((dial == DIAL_DOWN).mean())

    scaled, aux = compute_scales(books, fwd1, dial)

    bounds = ANCHORS + [YEAR_END]
    masks = [((books.index >= bounds[k]) & (books.index < bounds[k + 1])) for k in range(5)]

    variants = {}
    for name, ws in scaled.items():
        pn, to = score_variant(ws, fwd1)
        per_year = []
        for k, a0 in enumerate(ANCHORS):
            st = year_stats(pn[masks[k]])
            wd = worst_day(pn[masks[k]])
            fr = float((dial[masks[k]] == DIAL_DOWN).mean())
            per_year.append(dict(year=str(a0.date()), worst_day=round(wd, 6),
                                 fire_rate=round(fr, 4), **st))
        all_st = year_stats(pn)
        variants[name] = dict(per_year=per_year, pooled=all_st,
                              pooled_worst_day=round(worst_day(pn), 6),
                              mean_abs_w=round(float(ws.abs().mean().mean()), 6),
                              total_turnover=round(float(to.sum()), 4),
                              total_cost=round(float((COST * to).sum()), 6))
        print(f"{name}: " + " | ".join(
            f"{r['year']} ret={r['ret']} dd={r['dd']} sh={r['sharpe']} "
            f"wd={r['worst_day']} fire={r['fire_rate']}" for r in per_year),
            flush=True)

    base, tilt = variants["base_60d"]["per_year"], variants["tilt_gap075"]["per_year"]
    ddd = [None if (r["dd"] is None or b["dd"] is None) else round(b["dd"] - r["dd"], 6)
           for r, b in zip(tilt, base)]
    dret = [None if (r["ret"] is None or b["ret"] is None) else round(r["ret"] - b["ret"], 6)
            for r, b in zip(tilt, base)]
    dsh = [None if (r["sharpe"] is None or b["sharpe"] is None) else round(r["sharpe"] - b["sharpe"], 4)
           for r, b in zip(tilt, base)]
    tail = [bool(r["worst_day"] >= b["worst_day"]) for r, b in zip(tilt, base)]
    n_dd = sum(1 for d in ddd if d is not None and d > 0)
    loyo = []
    for h in range(5):
        tr = [d for k, d in enumerate(ddd) if k != h and d is not None]
        m = float(np.mean(tr)) if len(tr) == 4 else float("nan")
        loyo.append(bool(ddd[h] is not None and np.isfinite(m) and m > 0
                          and np.sign(ddd[h]) == np.sign(m)))
    promising = bool(n_dd >= 4 and sum(loyo) >= 4 and sum(tail) >= 4)
    decision = dict(dDD=ddd, dd_pos=f"{n_dd}/5", loyo_dd=f"{sum(loyo)}/5",
                    loyo_detail=[bool(x) for x in loyo],
                    tail_ok=[bool(x) for x in tail], tail_pos=f"{sum(tail)}/5",
                    dRet=dret, dSharpe=dsh, promising=promising,
                    first4_dd_pos=f"{sum(1 for d in ddd[:4] if d is not None and d > 0)}/4",
                    first4_tail_pos=f"{sum(1 for x in tail[:4] if x)}/4")

    out = {
        "definitions": ("grid=books_d2 x opens_v154 inner join; r=open[t+1]/open[t]-1; "
                        "BASE V0 scale=min(2,0.25/sig60d), sig=std(u[t-360..t-1])*sqrt(2190) min120; "
                        "gap(T)=ln(C(D)/C(prev)), D=latest ^GSPC day with close_utc<T (16:00 ET=20:00UTC DST/21:00UTC); "
                        "q25(A_k)=25th pct of gap over close_utc<A_k-7d from 2016-01-01; "
                        "dial=0.75 if gap<q25 else 1.0; TILT=BASE*dial; "
                        "TO=sum|ws[t]-ws[t-1]| (first vs 0, per-variant); pn=sum(ws*r)-0.0005*TO; "
                        "eq compounded from 1; years [A_k,A_k+1) x4 + [A4,A4+365d); "
                        "Sharpe=mean/std*sqrt(2190); DD on year-rebased eq; worst_day=min UTC-day sum"),
        "symbols": SYMS, "anchor_years": [str(a.date()) for a in ANCHORS],
        "grid_start": str(books.index.min()), "grid_end": str(books.index.max()),
        "n_bars": int(len(books)),
        "spx": dict(rows=int(len(daily)), first=str(daily['day'].iloc[0]),
                    last=str(daily['day'].iloc[-1]),
                    q25={k: round(v, 6) for k, v in q.items()},
                    fire_rate_5y=round(fire, 4)),
        "variants": variants, "decision": decision,
        "scale_summary": dict(s0_mean=round(float(aux["s0"].mean()), 4),
                              s0_p5=round(float(aux["s0"].quantile(0.05)), 4),
                              s0_p95=round(float(aux["s0"].quantile(0.95)), 4)),
    }
    (HERE / "results.json").write_text(json.dumps(out, indent=1))
    print(json.dumps({"q25": out["spx"]["q25"], "decision": decision}, indent=1))


if __name__ == "__main__":
    main()
