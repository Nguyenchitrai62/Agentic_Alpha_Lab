"""oc_expirycb: COMBINATION screen of oc_expirybook + oc_cbpremium (pre-registered in PLAN.md).

Per PLAN.md: rebuild forward_v205.research_books_d2 exactly (as oc_dvolshort /
oc_expirybook / oc_cbpremium), join with v154 4h opens, apply the v410
BTC-only bear-long filter as BASE, then:
  PREM (exactly oc_cbpremium): BASE longs x1.15 when premium z > 1,
    x0.85 when z < -1, else x1.0 (BTC-only signal to all 5 coins;
    shorts/flats/NaN-z unchanged; premium exactly oc_optctx.load_premium,
    as-of last row with end strictly before T, end <= T - 1s).
  EXP (exactly oc_expirybook): BASE x0.5 both sides on holding bars with
    T in [E - 48h, E) for E = last Friday of month 08:00 UTC, else BASE.
  BOTH (this screen): expiry halving applied AFTER the premium tilt,
    w_both = 0.5 * w_prem on expiry bars, else w_prem.
Screen with open-to-open 4h returns and gate costs maker 0.0002 per unit
turnover (each of the 4 paths its own prev chain), exactly as the parents.
Single light process (4h + hourly only, no 1m).

  python research/tournament/oc_expirycb/compute_expirycb.py
"""
from __future__ import annotations

import calendar
import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
CACHE = ROOT / "artifacts/research/engine_real"
CB = ROOT / "data/raw/coinbase_20260925/BTC-USD_1h.parquet"
HOURLY = ROOT / "research/tournament/ext/hourly_ext.parquet"

SYMS = ["BNBUSDT", "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]
ANCHORS = [pd.Timestamp(f"{y}-09-24", tz="UTC") for y in (2021, 2022, 2023, 2024, 2025)]
LAST_BOUND = ANCHORS[-1] + pd.Timedelta(days=365)
CUTOFF = pd.Timestamp("2026-09-24", tz="UTC")
MAKER = 0.0002
LONG_MULT_BEAR = 0.5
UP_MULT = 1.15
DOWN_MULT = 0.85
Z_HI = 1.0
Z_LO = -1.0
NS = 1_000_000_000


def research_books_d2() -> pd.DataFrame:
    """Mirror of oc_dvolshort.compute_dvolshort.research_books_d2 (same files, same math)."""
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


def expiry(y: int, m: int) -> pd.Timestamp:
    """Last Friday of month m, 08:00 UTC (Deribit monthly expiry, exactly oc_expirybook)."""
    last_day = calendar.monthrange(y, m)[1]
    d = pd.Timestamp(y, m, last_day, tz="UTC")
    back = (d.weekday() - 4) % 7  # Friday == 4
    return (d - pd.Timedelta(days=int(back))).replace(hour=8, minute=0, second=0)


def expiries() -> pd.DataFrame:
    rows = []
    for y in range(2021, 2027):
        for mm in range(1, 13):
            e = expiry(y, mm)
            if e < pd.Timestamp("2021-01-01", tz="UTC") or e >= CUTOFF + pd.Timedelta(days=1):
                continue
            rows.append(dict(E=e))
    return pd.DataFrame(rows)


def in_expiry_window(t: pd.DatetimeIndex, exp: pd.DataFrame) -> np.ndarray:
    """Vectorised flag: T in [E - 48h, E) for some expiry E (pure timestamps, exactly oc_expirybook)."""
    ti = t.astype("int64").to_numpy()
    H = np.int64(3_600_000_000_000)
    flag = np.zeros(len(t), bool)
    for r in exp.itertuples():
        e = np.int64(r.E.value)
        flag |= (ti >= e - np.int64(48) * H) & (ti < e)
    return flag


def load_premium() -> pd.DataFrame:
    """Hourly Coinbase/Binance premium grid exactly as oc_optctx.load_premium / oc_cbpremium."""
    cb = pd.read_parquet(CB).copy()
    cb["t"] = pd.to_datetime(cb["open_time"], utc=True)
    cb = cb[cb["t"] < CUTOFF][["t", "close"]].rename(columns={"close": "cb"})
    h = pd.read_parquet(HOURLY, columns=["t", "close", "sym"])
    h = h[h["sym"] == "BTCUSDT"].copy()
    h["t"] = pd.to_datetime(h["t"], utc=True)
    h = h[h["t"] < CUTOFF][["t", "close"]].rename(columns={"close": "bin"})
    g = pd.merge(cb, h, on="t", how="inner").sort_values("t").reset_index(drop=True)
    g["prem"] = g["cb"] / g["bin"] - 1
    g["mean24"] = g["prem"].rolling(24, min_periods=20).mean()
    r = g["mean24"].rolling(2160, min_periods=1728)
    g["cbprem_z90"] = (g["mean24"] - r.mean().shift(1)) / r.std(ddof=1).shift(1)
    g["end"] = g["t"] + pd.Timedelta(hours=1)
    return g


def asof_z(prem: pd.DataFrame, T: pd.DatetimeIndex) -> np.ndarray:
    """z(T) = cbprem_z90 of last premium row with end strictly before T (end <= T-1s), exactly oc_cbpremium."""
    ends_ns = prem["end"].to_numpy(dtype="datetime64[ns]").astype(np.int64)
    vals = prem["cbprem_z90"].to_numpy(float)
    Tns = T.to_numpy(dtype="datetime64[ns]").astype(np.int64)
    ii = np.searchsorted(ends_ns, Tns - NS, side="left") - 1
    out = np.full(len(T), np.nan)
    ok = ii >= 0
    out[ok] = vals[ii[ok]]
    return out


def max_dd(equity: np.ndarray) -> float:
    eq = np.asarray(equity, dtype=float)
    if len(eq) == 0:
        return float("nan")
    peak = np.maximum.accumulate(eq)
    dd = 1.0 - eq / peak
    return float(np.max(dd))


def worst_week(equity: np.ndarray) -> float:
    eq = np.asarray(equity, dtype=float)
    if len(eq) < 43:
        return float(eq[-1] / eq[0] - 1.0) if len(eq) > 1 else 0.0
    rets = eq[42:] / eq[:-42] - 1.0
    return float(np.min(rets))


def equity_path(rp: np.ndarray) -> np.ndarray:
    rp = np.asarray(rp, dtype=float)
    return np.concatenate([[1.0], np.cumprod(1.0 + rp)])


def main() -> None:
    exp = expiries()
    prem = load_premium()
    print(f"premium: rows={len(prem)} span={prem['t'].iloc[0]}..{prem['t'].iloc[-1]} "
          f"median_prem_bps={prem['prem'].median() * 1e4:.2f}", flush=True)

    books_raw = research_books_d2()
    opens_full = pd.read_parquet(CACHE / "opens_v154.parquet")
    opens = opens_full.reindex(books_raw.index)
    grid = books_raw.index.intersection(opens.dropna(how="all").index)
    grid = grid[(grid >= ANCHORS[0]) & (grid < CUTOFF)].sort_values()
    books_raw = books_raw.reindex(grid).sort_index()
    opens = opens.reindex(grid).sort_index()

    # Forward open-to-open returns; drop last grid bar (no forward open);
    # forward exit must be at/before CUTOFF (same boundary as parents).
    fwd1 = opens.shift(-1) / opens - 1.0
    exit_ok = opens.index.shift(-1) <= CUTOFF
    keep = np.asarray(exit_ok)
    books_raw, opens, fwd1 = books_raw[keep], opens[keep], fwd1[keep]
    valid = fwd1.notna().all(axis=1)
    books_raw, opens, fwd1 = books_raw[valid], opens[valid], fwd1[valid]
    grid = books_raw.index
    print(f"book grid: {len(grid)} bars {grid.min()}..{grid.max()}", flush=True)
    print(f"expiries: {len(exp)} {exp['E'].min()}..{exp['E'].max()}", flush=True)

    # v410 bear regime FIRST (BTC-only, causal at close of T, open[T] inclusive).
    btc_full = opens_full["BTCUSDT"].sort_index()
    ma_full = btc_full.rolling(1200, min_periods=600).mean()
    bear_full = (btc_full < ma_full).fillna(False)
    bear = bear_full.reindex(grid).fillna(False).to_numpy(bool)

    # BASE = raw book + v410 bear-long filter (control).
    w_raw = books_raw[SYMS].to_numpy(float)  # (n_bars, 5)
    w_base = np.where(bear[:, None] & (w_raw > 0), w_raw * LONG_MULT_BEAR, w_raw)

    # PREMIUM-ONLY (exactly oc_cbpremium): one z per bar, all coins.
    zbar = asof_z(prem, grid)
    mult_bar = np.ones(len(grid))
    mult_bar[np.isfinite(zbar) & (zbar > Z_HI)] = UP_MULT
    mult_bar[np.isfinite(zbar) & (zbar < Z_LO)] = DOWN_MULT
    w_prem = np.where(w_base > 0, w_base * mult_bar[:, None], w_base)

    # EXPIRY-ONLY (exactly oc_expirybook): holding bars in [E-48h, E) -> x0.5 both sides.
    inexp = in_expiry_window(grid, exp)
    w_exp = w_base.copy()
    w_exp[inexp, :] = 0.5 * w_base[inexp, :]

    # BOTH (this screen): expiry halving applied AFTER the premium tilt.
    w_both = w_prem.copy()
    w_both[inexp, :] = 0.5 * w_prem[inexp, :]

    r1 = fwd1[SYMS].to_numpy(float)

    # Turnover costs in grid order per sym (first bar prev = 0), each path own prev.
    cost_base = np.zeros_like(w_base)
    cost_exp = np.zeros_like(w_base)
    cost_prem = np.zeros_like(w_base)
    cost_both = np.zeros_like(w_base)
    for j in range(len(SYMS)):
        for w, c in ((w_base, cost_base), (w_exp, cost_exp),
                     (w_prem, cost_prem), (w_both, cost_both)):
            col = w[:, j]
            c[:, j] = MAKER * np.abs(col - np.concatenate([[0.0], col[:-1]]))
    pnl_base = w_base * r1 - cost_base
    pnl_exp = w_exp * r1 - cost_exp
    pnl_prem = w_prem * r1 - cost_prem
    pnl_both = w_both * r1 - cost_both

    # Per-(T,sym) panel (small).
    panel = pd.DataFrame({
        "T": np.repeat(grid.to_numpy(), len(SYMS)),
        "sym": np.tile(np.asarray(SYMS), len(grid)),
        "bear": np.repeat(bear, len(SYMS)),
        "in_exp": np.repeat(inexp, len(SYMS)),
        "z": np.repeat(zbar, len(SYMS)),
        "mult": np.repeat(mult_bar, len(SYMS)),
        "w_raw": w_raw.reshape(-1),
        "w_base": w_base.reshape(-1),
        "w_exp": w_exp.reshape(-1),
        "w_prem": w_prem.reshape(-1),
        "w_both": w_both.reshape(-1),
        "r1": r1.reshape(-1),
        "cost_base": cost_base.reshape(-1),
        "cost_exp": cost_exp.reshape(-1),
        "cost_prem": cost_prem.reshape(-1),
        "cost_both": cost_both.reshape(-1),
        "pnl_base": pnl_base.reshape(-1),
        "pnl_exp": pnl_exp.reshape(-1),
        "pnl_prem": pnl_prem.reshape(-1),
        "pnl_both": pnl_both.reshape(-1),
    })
    panel["T"] = pd.to_datetime(panel["T"], utc=True)
    panel.to_parquet(HERE / "panel.parquet")

    bar_base = pnl_base.sum(axis=1)
    bar_exp = pnl_exp.sum(axis=1)
    bar_prem = pnl_prem.sum(axis=1)
    bar_both = pnl_both.sum(axis=1)

    bounds = ANCHORS + [LAST_BOUND]
    years = []
    dd_wins = 0
    pnl_wins = 0
    for k, a0 in enumerate(ANCHORS):
        m = np.asarray((grid >= bounds[k]) & (grid < bounds[k + 1]))
        rp = {v: b[m] for v, b in
              (("base", bar_base), ("exp", bar_exp), ("prem", bar_prem), ("both", bar_both))}
        eq = {v: equity_path(rp[v]) for v in rp}
        dd = {v: max_dd(eq[v]) for v in rp}
        ww = {v: worst_week(eq[v]) for v in rp}
        tot = {v: float(np.sum(p)) for v, p in
               (("base", pnl_base[m]), ("exp", pnl_exp[m]),
                ("prem", pnl_prem[m]), ("both", pnl_both[m]))}
        cost_tot = {v: float(np.sum(c[m])) for v, c in
                    (("base", cost_base), ("exp", cost_exp),
                     ("prem", cost_prem), ("both", cost_both))}
        dd_ok = bool(dd["both"] <= dd["base"] + 1e-12)
        pnl_ok = bool(tot["both"] > tot["base"])
        row = {
            "year": str(a0.date()),
            "n_bars": int(m.sum()),
            "n_exp_bars": int(inexp[m].sum()),
            "exp_share": round(float(inexp[m].mean()), 6),
            "coverage_z": round(float(np.isfinite(zbar[m]).mean()), 6),
            "book_pnl_base": round(tot["base"], 6),
            "book_pnl_exp": round(tot["exp"], 6),
            "book_pnl_prem": round(tot["prem"], 6),
            "book_pnl_both": round(tot["both"], 6),
            "worst_week_base": round(ww["base"], 6),
            "worst_week_exp": round(ww["exp"], 6),
            "worst_week_prem": round(ww["prem"], 6),
            "worst_week_both": round(ww["both"], 6),
            "maxDD_base": round(dd["base"], 6),
            "maxDD_exp": round(dd["exp"], 6),
            "maxDD_prem": round(dd["prem"], 6),
            "maxDD_both": round(dd["both"], 6),
            "cost_base": round(cost_tot["base"], 6),
            "cost_exp": round(cost_tot["exp"], 6),
            "cost_prem": round(cost_tot["prem"], 6),
            "cost_both": round(cost_tot["both"], 6),
            "dd_not_worse_vs_base": dd_ok,
            "pnl_higher_vs_base": pnl_ok,
        }
        years.append(row)
        dd_wins += int(dd_ok)
        pnl_wins += int(pnl_ok)

    full = {}
    for v, b in (("base", bar_base), ("exp", bar_exp),
                 ("prem", bar_prem), ("both", bar_both)):
        full[v] = {"maxDD": round(max_dd(equity_path(b)), 6),
                   "total_pnl": round(float(np.sum(
                       {"base": pnl_base, "exp": pnl_exp,
                        "prem": pnl_prem, "both": pnl_both}[v])), 6)}

    res = {
        "meta": {
            "books": "forward_v205.research_books_d2 (rebuilt exactly, cf oc_dvolshort/oc_expirybook/oc_cbpremium)",
            "opens": "engine_real opens_v154.parquet",
            "base": "BASE = raw book + v410 bear-long filter (longs x0.5 where BTC 4h open < rolling-1200 mean, min 600)",
            "premium": "cb/bin-1 hourly inner join; mean24 rolling(24,min20); z90 rolling(2160,min1728) shift(1); as-of last row end<T (end<=T-1s); longs x1.15 z>1 / x0.85 z<-1 (exactly oc_cbpremium)",
            "expiry": "68 monthly expiries (last Friday 08:00 UTC); holding bars in [E-48h,E) -> x0.5 both sides (exactly oc_expirybook)",
            "both": "expiry halving applied AFTER the premium tilt: w_both = 0.5*w_prem on expiry bars else w_prem",
            "costs": "maker 0.0002 per unit turnover (|w - w_prev| per sym, first prev=0; each of the 4 paths own prev). NOTE: assignment text says 0.05%; 0.0002 used to reproduce the parents exactly (see PLAN.md).",
            "path": "per-year equity reset to 1, eq*=1+sum_s pnl; maxDD peak-to-trough; worst week = min 42-bar return",
            "symbols": SYMS, "cutoff": str(CUTOFF),
            "grid_start": str(grid.min()), "grid_end": str(grid.max()),
            "n_bars": int(len(grid)), "n_panel": int(len(panel)),
            "anchor_years": [str(a.date()) for a in ANCHORS],
        },
        "years": years,
        "full_path": full,
        "decision": {
            "dd_not_worse_count": f"{dd_wins}/5",
            "pnl_higher_count": f"{pnl_wins}/5",
            "promising": bool(dd_wins >= 4 and pnl_wins >= 4),
        },
    }
    (HERE / "results.json").write_text(json.dumps(res, indent=1))
    print(json.dumps(res["decision"], indent=1))
    for y in years:
        print(y)


if __name__ == "__main__":
    main()
