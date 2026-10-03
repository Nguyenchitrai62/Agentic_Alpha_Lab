"""Shared helpers for SYSTEM AUDIT 2 (leak_opencode). No returns after 2026-09-23 are used."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[4]
CACHE = ROOT / "artifacts/research/engine_real"
SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
ANCHORS = ["2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24"]
PRICE_CAP = pd.Timestamp("2026-09-23T00:00:00Z")  # never look at returns after 2026-09-23
# Last 4h-boundary open available from the 1m archive is 2026-09-23 20:00; triples need +12h.
OPEN_CAP = pd.Timestamp("2026-09-23T20:00:00Z")


def spearman(x: pd.Series, y: pd.Series) -> float:
    d = pd.concat([x, y], axis=1).dropna()
    if len(d) < 10 or d.iloc[:, 0].nunique() < 3 or d.iloc[:, 1].nunique() < 3:
        return float("nan")
    return float(d.iloc[:, 0].corr(d.iloc[:, 1], method="spearman"))


def leak_flags(c_hold: float, c_next: float) -> dict:
    f1 = bool(np.isfinite(c_hold) and abs(c_hold) > 0.10)
    f2 = bool(np.isfinite(c_hold) and np.isfinite(c_next) and c_hold > 0.06 and c_next != 0
              and c_hold > 3 * abs(c_next) if np.isfinite(c_next) else False)
    # careful: c_next may be negative; rule is corr_hold more than 3x corr_next AND above 0.06
    f2 = bool(np.isfinite(c_hold) and np.isfinite(c_next) and c_hold > 0.06 and c_hold > 3 * c_next)
    return {"flag_abs": f1, "flag_3x": f2, "flag_any": bool(f1 or f2)}


def build_opens_4h_from_1m() -> pd.DataFrame:
    """4h opens from raw 1m klines: open at each 4h boundary. Capped at OPEN_CAP."""
    series = {}
    for sym in SYMS:
        if sym == "BTCUSDT":
            pats = sorted((ROOT / "data/raw/btc_intraday_20260924").glob("klines_1m_20*.parquet"))
        else:
            pats = sorted((ROOT / "data/raw/majors_intraday_20260924").glob(f"{sym}_1m_20*.parquet"))
        parts = []
        for p in pats:
            d = pd.read_parquet(p, columns=["open_time", "open"])
            d["open_time"] = pd.to_datetime(d["open_time"], utc=True)
            parts.append(d)
        m = pd.concat(parts).drop_duplicates("open_time").sort_values("open_time")
        m = m[(m["open_time"].dt.minute == 0) & (m["open_time"].dt.hour % 4 == 0)]
        m = m[m["open_time"] <= OPEN_CAP]
        series[sym] = m.set_index("open_time")["open"].astype(float)
    opens = pd.DataFrame(series).sort_index()
    return opens


def return_triples(opens: pd.DataFrame):
    o = opens
    r_dec = (o.shift(-1) / o - 1)
    r_hold = (o.shift(-2) / o.shift(-1) - 1)
    r_next = (o.shift(-3) / o.shift(-2) - 1)
    return r_dec, r_hold, r_next


def load_members() -> dict:
    """Member book frames exactly as research_books_d2 weights them (reads parquet only)."""
    C = CACHE
    cols = SYMS
    A = pd.read_parquet(C / "member_A_O1_orders.parquet")[cols]
    Aq = pd.read_parquet(C / "member_Aq_O1_orders.parquet")[cols]
    B = pd.read_parquet(C / "member_B_tv.parquet")[cols]
    Bq = pd.read_parquet(C / "member_Bq_tv.parquet")[cols]
    D = pd.read_parquet(C / "members_v154.parquet").xs("D", axis=1, level=0)[cols]
    Dq = pd.read_parquet(C / "members_quarterly_D.parquet")[cols]
    idx = A.index.union(Aq.index).union(D.index).union(Dq.index)
    f = lambda X: X.reindex(idx).fillna(0.0)
    o1 = 0.5 * (f(A) + f(B)) / 2 + 0.5 * (f(Aq) + f(Bq)) / 2
    d2 = 0.8 * f(o1) + 0.2 * (f(D) + f(Dq)) / 2
    return {"A_O1": f(A), "Aq_O1": f(Aq), "B_tv": f(B), "Bq_tv": f(Bq),
            "D_ann": f(D), "D_q": f(Dq), "O1": f(o1), "D2": f(d2)}


def truncate_compare(full: pd.DataFrame, trunc: pd.DataFrame, tol: float = 1e-9):
    """Compare one feature row: return (ok, mismatching columns, max abs diff)."""
    assert full.index.equals(trunc.index)
    row_f, row_t = full.iloc[[-1]], trunc.iloc[[-1]]
    diff = (row_f - row_t).abs().iloc[0]
    diff = diff.where(~(row_f.iloc[0].isna() & row_t.iloc[0].isna()), 0.0)
    bad = diff[diff > tol].index.tolist()
    return (len(bad) == 0, bad, float(diff.max(skipna=True)) if len(diff) else 0.0)
