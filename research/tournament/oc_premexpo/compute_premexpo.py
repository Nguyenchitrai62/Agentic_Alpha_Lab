"""oc_premexpo: are the two premium-tilt return gains alpha or just extra long exposure?

Per assignment OPENCODE_W_oc_premexpo.md: for each premium signal (USDT/USD
inflow z as in oc_usdtprem; Coinbase BTC premium z as in oc_cbpremium) and each
anchor year, report (1) average long multiplier + long gross exposure base vs
rule; (2) exposure-matched control = constant long multiplier equal to the
rule's average multiplier in that year (computed in-year, diagnostic NOT a
rule); (3) placebo = 500 seeded block-shuffles by run (permute (value,length)
run pairs, preserving the exact multiset of run values/lengths, re-timing only)
and the rule's long-leg P&L gain vs the control plus its percentile within the
placebo-gain distribution, per year and 5y. Also z-vs-z correlation and the
combined rule (average of both multipliers) on the same tests.
Verdict per signal: ALPHA only if yearly gain over control > 0 in >= 4/5 years
AND 5y placebo percentile >= 95; else EXPOSURE.

Mechanics (LIGHT, vectorised only, 4h + hourly, no 1m):
  books = forward_v205.research_books_d2 rebuilt exactly as oc_dvolshort /
    oc_cbpremium / oc_usdtprem; opens = v154 4h opens; BASE = v410 BTC-only
    bear-long filter FIRST (longs x0.5 when BTC 4h open < 1200-bar mean).
  RULE_s = BASE longs x mult_s (1.15 when z_s > 1, 0.85 when z_s < -1, else 1.0;
    market-wide, shorts/flats/NaN-z bit-identical). Combined mult =
    (mult_usdt + mult_cb) / 2 applied to BASE longs the same way.
  Screen = open-to-open 4h returns with gate costs MAKER = 0.0002/unit turnover
    (oc_dvolshort / oc_cbpremium mechanics, each path its own prev chain, first
    prev = 0). Unified 0.0002 for all three signals so they are comparable;
    note oc_usdtprem's report used 0.0005, so its absolute P&L levels here
    differ slightly by cost only (tilt structure identical).
  Long-leg sums use fixed BASE-sign membership (w_base > 0) so paths compare
    identical rows.
  Control (diagnostic, in-year): control_mult[k] = gross_rule_weights[k] /
    gross_base_weights[k] over base-long cells in year k (exposure-weighted
    average multiplier); w_control = w_base * control_mult[k] on longs in year
    k, else w_base. Own turnover chain (global, first prev = 0).
  Placebo (diagnostic, in-year timing only): runs = maximal constant-mult
    segments of the rule mult series; each draw permutes the (value, length)
    run pairs with a seeded RNG and rebuilds the same-length series (total
    tilted-row counts per level exact; note adjacent equal-valued pairs merge
    on rebuild, so the run list can only shrink by merges — row counts stay
    exact). Yearly draws
    shuffle runs strictly inside year k (other years fixed) with seed
    6100 + i (i = 0..499, same seeds each year/signal, documented); 5y draws
    shuffle runs over the full 10955-bar series with seed 9100 + i. Placebo
    gain = placebo long-leg P&L - control long-leg P&L (same control, same
    fixed membership, own chain); percentile = 100 * mean(placebo <= rule).

  python research/tournament/oc_premexpo/compute_premexpo.py
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
CACHE = ROOT / "artifacts/research/engine_real"
USDT = ROOT / "data/raw/coinbase_usdt_20261006/USDT-USD_1h.parquet"
CB = ROOT / "data/raw/coinbase_20260925/BTC-USD_1h.parquet"
HOURLY = ROOT / "research/tournament/ext/hourly_ext.parquet"

SYMS = ["BNBUSDT", "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]
ANCHORS = [pd.Timestamp(f"{y}-09-24", tz="UTC") for y in (2021, 2022, 2023, 2024, 2025)]
LAST_BOUND = ANCHORS[-1] + pd.Timedelta(days=365)
CUTOFF = pd.Timestamp("2026-09-24", tz="UTC")
MAKER = 0.0002  # unified gate cost (oc_dvolshort mechanics) for comparability
LONG_MULT_BEAR = 0.5
UP_MULT = 1.15
DOWN_MULT = 0.85
Z_HI = 1.0
Z_LO = -1.0
NS = 1_000_000_000
N_PLACEBO = 500
YEAR_SEED_BASE = 6100
FULL_SEED_BASE = 9100


def research_books_d2() -> pd.DataFrame:
    """Mirror of oc_dvolshort.compute_dvolshort.research_books_d2."""
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


def load_usdt() -> pd.DataFrame:
    u = pd.read_parquet(USDT).copy()
    u["t"] = pd.to_datetime(u["open_time"], utc=True)
    u = u[u["t"] < CUTOFF].sort_values("t").reset_index(drop=True)
    u["prem"] = pd.to_numeric(u["close"], errors="coerce") - 1.0
    u["mean24"] = u["prem"].rolling(24, min_periods=20).mean()
    r = u["mean24"].rolling(2160, min_periods=1728)
    u["usdt_z90"] = (u["mean24"] - r.mean().shift(1)) / r.std(ddof=1).shift(1)
    u["end"] = u["t"] + pd.Timedelta(hours=1)
    return u


def load_cbpremium() -> pd.DataFrame:
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


def asof_col(df: pd.DataFrame, col: str, T: pd.DatetimeIndex) -> np.ndarray:
    ends_ns = df["end"].to_numpy(dtype="datetime64[ns]").astype(np.int64)
    vals = df[col].to_numpy(float)
    Tns = T.to_numpy(dtype="datetime64[ns]").astype(np.int64)
    ii = np.searchsorted(ends_ns, Tns - NS, side="left") - 1
    out = np.full(len(T), np.nan)
    ok = ii >= 0
    out[ok] = vals[ii[ok]]
    return out


def mult_from_z(z: np.ndarray) -> np.ndarray:
    m = np.ones(len(z))
    m[np.isfinite(z) & (z > Z_HI)] = UP_MULT
    m[np.isfinite(z) & (z < Z_LO)] = DOWN_MULT
    return m


def runs_of(mult: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Maximal constant-value runs -> (values, lengths). Exact equality (assigned levels)."""
    mult = np.asarray(mult, dtype=float)
    if len(mult) == 0:
        return np.array([]), np.array([], dtype=int)
    change = np.empty(len(mult), dtype=bool)
    change[0] = True
    change[1:] = mult[1:] != mult[:-1]
    starts = np.where(change)[0]
    lengths = np.diff(np.append(starts, len(mult)))
    return mult[starts], lengths.astype(int)


def shuffle_runs(mult: np.ndarray, seed: int) -> np.ndarray:
    vals, lens = runs_of(mult)
    rng = np.random.default_rng(seed)
    perm = rng.permutation(len(vals))
    return np.repeat(vals[perm], lens[perm])


def path_long_pnls(
    w_base: np.ndarray, r1: np.ndarray, mult_full: np.ndarray, maker: float,
    year_id: np.ndarray, n_years: int = 5,
) -> tuple[np.ndarray, np.ndarray]:
    """Long-leg net P&L per year and total for a bar-level long multiplier path.

    w_path = w_base * mult on base longs, else w_base; own global turnover
    chain (first prev = 0); long-leg sums over fixed base-long membership.
    Returns (per_year[5], total). Weights/Costs in portfolio-return units.
    """
    w_path = np.where(w_base > 0, w_base * mult_full[:, None], w_base)
    prev0 = np.zeros((1, w_base.shape[1]))
    cost = maker * np.abs(w_path - np.vstack([prev0, w_path[:-1]]))
    pnl = w_path * r1 - cost
    long_m = w_base > 0
    per_year = np.array([
        float(np.sum(pnl[(year_id == k)[:, None] & long_m])) for k in range(n_years)
    ])
    return per_year, float(np.sum(pnl[long_m]))


def pearson(a: np.ndarray, b: np.ndarray) -> float:
    m = np.isfinite(a) & np.isfinite(b)
    if int(m.sum()) < 3:
        return float("nan")
    x, y = a[m], b[m]
    if float(np.std(x)) == 0.0 or float(np.std(y)) == 0.0:
        return float("nan")
    return float(np.corrcoef(x, y)[0, 1])


def main() -> None:
    usdt = load_usdt()
    cb = load_cbpremium()
    print(f"usdt rows={len(usdt)} cb rows={len(cb)}", flush=True)

    books_raw = research_books_d2()
    opens_full = pd.read_parquet(CACHE / "opens_v154.parquet")
    opens = opens_full.reindex(books_raw.index)
    grid = books_raw.index.intersection(opens.dropna(how="all").index)
    grid = grid[(grid >= ANCHORS[0]) & (grid < CUTOFF)].sort_values()
    books_raw = books_raw.reindex(grid).sort_index()
    opens = opens.reindex(grid).sort_index()

    fwd1 = opens.shift(-1) / opens - 1.0
    valid = fwd1.notna().all(axis=1)
    books_raw, opens, fwd1 = books_raw[valid], opens[valid], fwd1[valid]
    grid = books_raw.index
    grid_ts = pd.to_datetime(grid, utc=True)
    print(f"book grid: {len(grid)} bars {grid.min()}..{grid.max()}", flush=True)

    btc_full = opens_full["BTCUSDT"].sort_index()
    ma_full = btc_full.rolling(1200, min_periods=600).mean()
    bear_full = (btc_full < ma_full).fillna(False)
    bear = bear_full.reindex(grid).fillna(False).to_numpy(bool)

    w_raw = books_raw[SYMS].to_numpy(float)
    w_base = np.where(bear[:, None] & (w_raw > 0), w_raw * LONG_MULT_BEAR, w_raw)
    r1 = fwd1[SYMS].to_numpy(float)

    z_usdt = asof_col(usdt, "usdt_z90", grid)
    z_cb = asof_col(cb, "cbprem_z90", grid)
    mult_usdt = mult_from_z(z_usdt)
    mult_cb = mult_from_z(z_cb)
    mult_comb = (mult_usdt + mult_cb) / 2.0

    bounds = ANCHORS + [LAST_BOUND]
    year_id = np.zeros(len(grid), dtype=int)
    for k, a0 in enumerate(ANCHORS):
        sel = (grid_ts >= bounds[k]) & (grid_ts < bounds[k + 1])
        year_id[np.asarray(sel)] = k

    corr_full = pearson(z_usdt, z_cb)
    corr_years = [pearson(z_usdt[year_id == k], z_cb[year_id == k]) for k in range(5)]

    signals: dict[str, np.ndarray] = {"usdt": mult_usdt, "cb": mult_cb, "combined": mult_comb}
    # Base long P&L per year (shared; global chain, fixed membership).
    base_year, base_total = path_long_pnls(w_base, r1, np.ones(len(grid)), MAKER, year_id)

    out_signals = {}
    for sname, mult in signals.items():
        rule_year, rule_total = path_long_pnls(w_base, r1, mult, MAKER, year_id)

        # (1) exposure: weight sums over base-long cells + exposure-weighted avg mult.
        avg_mult, gross_base, gross_rule = [], [], []
        control_mult = np.ones(len(grid))
        for k in range(5):
            m_long = (year_id == k)[:, None] & (w_base > 0)
            gb = float(np.sum(w_base[m_long]))
            gr = float(np.sum((w_base * mult[:, None])[m_long]))
            gross_base.append(gb)
            gross_rule.append(gr)
            cm = (gr / gb) if gb != 0 else 1.0
            avg_mult.append(cm)
            control_mult[year_id == k] = cm
        ctrl_year, ctrl_total = path_long_pnls(w_base, r1, control_mult, MAKER, year_id)
        gain_year = rule_year - ctrl_year
        gain_total = float(rule_total - ctrl_total)

        # (3) placebos: yearly (shuffle inside year k, rest fixed) + full-series.
        rng_check_vals, rng_check_lens = runs_of(mult)
        n_runs = int(len(rng_check_vals))
        per_year_pct: list[float] = []
        per_year_n_up: list[int] = []
        for k in range(5):
            idx = np.where(year_id == k)[0]
            seg = mult[idx]
            plac_gains = np.empty(N_PLACEBO)
            for i in range(N_PLACEBO):
                pm = mult.copy()
                pm[idx] = shuffle_runs(seg, YEAR_SEED_BASE + i)
                py, _ = path_long_pnls(w_base, r1, pm, MAKER, year_id)
                plac_gains[i] = float(py[k] - ctrl_year[k])
            pct = float(100.0 * np.mean(plac_gains <= gain_year[k] + 1e-18))
            per_year_pct.append(round(pct, 2))
            per_year_n_up.append(int(np.sum(plac_gains <= gain_year[k] + 1e-18)))

        full_gains = np.empty(N_PLACEBO)
        for i in range(N_PLACEBO):
            pm = shuffle_runs(mult, FULL_SEED_BASE + i)
            _, ptot = path_long_pnls(w_base, r1, pm, MAKER, year_id)
            full_gains[i] = float(ptot - ctrl_total)
        pct_5y = float(100.0 * np.mean(full_gains <= gain_total + 1e-18))

        n_gain_pos = int(np.sum(gain_year > 1e-12))
        verdict = "ALPHA" if (n_gain_pos >= 4 and pct_5y >= 95.0) else "EXPOSURE"

        years = []
        for k, a0 in enumerate(ANCHORS):
            sel = year_id == k
            years.append({
                "year": str(a0.date()),
                "n_bars": int(sel.sum()),
                "coverage": round(float(np.isfinite(mult[sel]).mean()), 6),
                "avg_long_mult": round(float(avg_mult[k]), 6),
                "control_mult": round(float(avg_mult[k]), 6),
                "long_gross_w_base": round(float(gross_base[k]), 6),
                "long_gross_w_rule": round(float(gross_rule[k]), 6),
                "long_pnl_base": round(float(base_year[k]), 6),
                "long_pnl_rule": round(float(rule_year[k]), 6),
                "long_pnl_control": round(float(ctrl_year[k]), 6),
                "gain_vs_control": round(float(gain_year[k]), 6),
                "gain_positive": bool(gain_year[k] > 1e-12),
                "placebo_pct": per_year_pct[k],
                "placebo_wins": f"{per_year_n_up[k]}/{N_PLACEBO}",
            })
        out_signals[sname] = {
            "n_runs_full": n_runs,
            "years": years,
            "total": {
                "long_pnl_base": round(float(base_total), 6),
                "long_pnl_rule": round(float(rule_total), 6),
                "long_pnl_control": round(float(ctrl_total), 6),
                "gain_vs_control": round(float(gain_total), 6),
                "years_gain_positive": f"{n_gain_pos}/5",
                "placebo_pct_5y": round(float(pct_5y), 2),
                "placebo_mean_5y": round(float(np.mean(full_gains)), 6),
                "placebo_sd_5y": round(float(np.std(full_gains, ddof=1)), 6),
                "verdict": verdict,
            },
        }
        print(f"{sname}: gain_total={gain_total:.6f} pos_years={n_gain_pos}/5 "
              f"pct5y={pct_5y:.1f} verdict={verdict}", flush=True)

    res = {
        "meta": {
            "books": "forward_v205.research_books_d2 (rebuilt exactly, cf oc_dvolshort/oc_cbpremium/oc_usdtprem)",
            "opens": "engine_real opens_v154.parquet",
            "base": "v410 BTC-only bear filter FIRST (longs x0.5 when BTC 4h open < 1200-bar mean)",
            "signals": "usdt: coinbase USDT-USD prem=close-1 mean24(24,min20) z90(2160,min1728,shift1); "
                       "cb: coinbase/binance prem=cb/bin-1 same smooth/z; as-of last row end<T (end<=T-1s)",
            "rules": "BASE longs x1.15 when z>1, x0.85 when z<-1 else x1.0 (market-wide); "
                     "combined mult=(mult_usdt+mult_cb)/2 on BASE longs; shorts/flats unchanged",
            "costs": "unified maker 0.0002/unit turnover (|w-w_prev| per sym, first prev=0, each path own global chain); "
                     "note oc_usdtprem report used 0.0005, so usdt absolute P&L here differs by cost only",
            "control": "DIAGNOSTIC not a rule: per-year constant long mult = gross_rule_w/gross_base_w "
                       "(exposure-weighted avg mult, in-year); w_control=w_base*mult on longs in that year",
            "placebo": "DIAGNOSTIC: 500 block-shuffles by run: permute (value,length) run pairs of the rule "
                       "mult series (same-length rebuild; total row counts per mult level exact; adjacent "
                       "equal-valued pairs merge on rebuild so the run list can only shrink by merges); yearly seeds 6100+i shuffle "
                       "runs strictly inside year k (rest fixed); 5y seeds 9100+i shuffle full-series runs; "
                       "gain=long P&L-placebo/control minus control; pct=100*mean(placebo<=rule)",
            "screen": "open-to-open 4h returns; long-leg sums over fixed BASE-long membership (w_base>0)",
            "symbols": SYMS, "cutoff": str(CUTOFF),
            "grid_start": str(pd.to_datetime(grid_ts.min())),
            "grid_end": str(pd.to_datetime(grid_ts.max())),
            "n_bars": int(len(grid)), "n_panel": int(len(grid) * len(SYMS)),
            "anchor_years": [str(a.date()) for a in ANCHORS],
            "n_placebo": N_PLACEBO,
        },
        "correlation_z_vs_z": {
            "full": round(float(corr_full), 6),
            "years": [round(float(c), 6) for c in corr_years],
        },
        "signals": out_signals,
    }
    (HERE / "results.json").write_text(json.dumps(res, indent=1))

    # Minimal per-(T,sym) panel for audit (weights + signals only; small).
    panel = pd.DataFrame({
        "T": np.tile(grid_ts, len(SYMS)),
        "sym": np.repeat(SYMS, len(grid)),
        "w_base": w_base.T.reshape(-1),
        "z_usdt": np.tile(z_usdt, len(SYMS)),
        "z_cb": np.tile(z_cb, len(SYMS)),
        "mult_usdt": np.tile(mult_usdt, len(SYMS)),
        "mult_cb": np.tile(mult_cb, len(SYMS)),
        "mult_comb": np.tile(mult_comb, len(SYMS)),
    })
    panel["T"] = pd.to_datetime(panel["T"], utc=True)
    panel.to_parquet(HERE / "panel.parquet")
    print("wrote results.json + panel.parquet", flush=True)


if __name__ == "__main__":
    main()
