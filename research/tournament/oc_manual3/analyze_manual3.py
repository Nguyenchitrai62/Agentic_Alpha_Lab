"""oc_manual3: STATIC placement-time proxy for v399-B1 correlation-aware dip sizing.

Frozen PLAN.md definitions. LIGHT: one process, < 1 GB, 1m read one coin-year
at a time. n per fill exactly as v399 (rule "inv"); no per-fill n is reused
from v399 (only equity paths are stored there).
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
import sys
sys.path.insert(0, str(ROOT / "research" / "tournament" / "ext"))
import harness5 as H5

OUT = ROOT / "research" / "tournament" / "oc_manual3"
MAJORS = H5.MAJORS
R2 = tuple(H5.R2)
ANCHORS = list(H5.ANCHORS)
EMBARGO = pd.Timedelta(days=7)
DEV_END = H5.DEV_END
MIN_FILLS = 30
EPS = 1e-12

BTC_DIR = ROOT / "data" / "raw" / "btc_intraday_20260924"
MAJ_DIR = ROOT / "data" / "raw" / "majors_intraday_20260924"


def count_n_row(O_row: np.ndarray, C_row: np.ndarray, SG_row: np.ndarray,
                own: int) -> int:
    """Exact v399-B1 rule: # other majors with C <= O*(1-2.5*sig).

    Skips the own coin and any coin with non-finite O/C/sig or sig <= 0.
    Flush at exactly 2.5 sigma counts (<=). Pure helper (unit-tested).
    """
    cnt = 0
    for b in range(len(O_row)):
        if b == own:
            continue
        if not (np.isfinite(O_row[b]) and np.isfinite(C_row[b]) and np.isfinite(SG_row[b])):
            continue
        if SG_row[b] <= 0:
            continue
        if float(C_row[b]) <= float(O_row[b]) * (1 - 2.5 * float(SG_row[b])):
            cnt += 1
    return cnt


def maxdd_of_cumsum(cum: np.ndarray) -> float:
    """Max peak-to-trough decline of a cumsum path from 0 (native units)."""
    if len(cum) == 0:
        return 0.0
    peak = np.maximum.accumulate(np.concatenate([[0.0], cum]))[:-1]
    return float(np.maximum(0.0, np.max(peak - cum)))


def recovery_and_pass(dd_a: float, dd_b: float, dd_c: float,
                      eps: float = 1e-12) -> tuple[float | None, bool]:
    """Recovery share + PASS(Y): needs red_dyn > eps and recovery >= 0.50."""
    red_dyn = dd_a - dd_c
    if not np.isfinite(red_dyn) or red_dyn <= eps:
        return None, False
    rec = (dd_a - dd_b) / red_dyn
    return rec, bool(np.isfinite(rec) and rec >= 0.50)


def coin_files(sym: str) -> list[Path]:
    if sym == "BTCUSDT":
        pats = sorted(BTC_DIR.glob("klines_1m_20*.parquet"))
    else:
        pats = sorted(MAJ_DIR.glob(f"{sym}_1m_20*.parquet"))
    # Strict bound: no 1m bar at/after 2026-09-24 00:00 UTC is ever used.
    return pats


def compute_n_for_coin(sym: str, Tuniq: pd.DatetimeIndex,
                       need_min: set) -> tuple[pd.Series, dict, dict]:
    """Per-coin opens at 4h grid G, sig4 at T, open@T and close dict.

    Returns (sig_at_T, open_at_T, close_by_minute). 1m files read one at a
    time; only peak = one yearly file in RAM.
    """
    G = pd.date_range("2020-06-01", "2026-09-24", freq="4h", tz="UTC")
    G = G[G < DEV_END]
    gset = set(G)
    open_at: dict[int, float] = {}
    close_by: dict[int, float] = {}
    for fp in coin_files(sym):
        df = pd.read_parquet(fp, columns=["open_time", "open", "close"])
        df["open_time"] = pd.to_datetime(df["open_time"], utc=True)
        df = df[(df["open_time"] >= pd.Timestamp("2020-06-01", tz="UTC"))
                & (df["open_time"] < DEV_END)]
        if df.empty:
            del df
            continue
        df = df.drop_duplicates("open_time").set_index("open_time").sort_index()
        # 4h-grid opens (for sig4 + O_b(T))
        hit_g = df.index.intersection(G)
        if len(hit_g):
            o = df["open"].reindex(hit_g)
            for ts, v in zip(hit_g, o.to_numpy(float)):
                if np.isfinite(v):
                    open_at[int(ts.value)] = float(v)
        # needed bar-minutes closes (T..T+239 grid + nothing else)
        want = need_min.intersection(set(df.index))
        if want:
            idx = pd.DatetimeIndex(sorted(want))
            c = df["close"].reindex(idx)
            arr = c.to_numpy(float)
            for ts, v in zip(idx, arr):
                if np.isfinite(v):
                    close_by[int(ts.value)] = float(v)
        del df
    o = pd.Series({pd.Timestamp(v, tz="UTC"): open_at[v] for v in open_at})
    o = o.reindex(G).astype(float)
    sig = o.pct_change().rolling(360, min_periods=120).std()
    sig_T = {int(t.value): (float(sig.loc[t]) if t in sig.index and np.isfinite(sig.loc[t]) else np.nan)
             for t in Tuniq}
    open_T = {int(t.value): float(open_at.get(int(t.value), np.nan)) for t in Tuniq}
    return sig_T, open_T, close_by


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    d = H5.load()
    d["T"] = pd.to_datetime(d["T"], utc=True)
    d["t_fill"] = pd.to_datetime(d["t_fill"], utc=True)
    grid = d[d["sym"].isin(MAJORS) & d["x1"].isin(R2)].copy().reset_index(drop=True)
    grid = grid[grid["t_fill"] < DEV_END].reset_index(drop=True)
    # Tuniq: bar opens of grid fills; need_min: every bar minute T..T+239.
    Tuniq = pd.DatetimeIndex(sorted(grid["T"].unique()))
    need_min: set = set()
    for t in Tuniq:
        base = pd.Timestamp(t)
        need_min.update(pd.date_range(base, base + pd.Timedelta(minutes=239), freq="min"))
    Tn = grid["T"].to_numpy(dtype="datetime64[ns]").astype(np.int64)
    fn = grid["f"].to_numpy(int)
    Mns = (grid["T"] + pd.to_timedelta(grid["f"] - 1, unit="min")).to_numpy(
        dtype="datetime64[ns]").astype(np.int64)

    ncoin = len(MAJORS)
    O = np.full((len(grid), ncoin), np.nan)
    C = np.full((len(grid), ncoin), np.nan)
    SG = np.full((len(grid), ncoin), np.nan)
    for j, sym in enumerate(MAJORS):
        sig_T, open_T, close_by = compute_n_for_coin(sym, Tuniq, need_min)
        Tns = Tn
        ocol = np.array([open_T.get(int(v), np.nan) for v in Tns], float)
        scol = np.array([sig_T.get(int(v), np.nan) for v in Tns], float)
        ccol = np.full(len(grid), np.nan)
        get = close_by.get
        for i in range(len(grid)):
            m = int(Mns[i])
            v = get(m, None)
            if v is None or not np.isfinite(v):
                # engine within-bar ffill: last available close in [T, M]
                t0 = int(Tns[i])
                mm = m - 60_000_000_000  # step back 1 minute in ns
                while mm >= t0:
                    v = get(mm, None)
                    if v is not None and np.isfinite(v):
                        break
                    mm -= 60_000_000_000
                else:
                    v = np.nan
            ccol[i] = v if v is not None else np.nan
        O[:, j], C[:, j], SG[:, j] = ocol, ccol, scol
        print(f"coin {sym}: sig cov {np.isfinite(scol).mean():.3f} "
              f"open cov {np.isfinite(ocol).mean():.3f} "
              f"close cov {np.isfinite(ccol).mean():.3f}", flush=True)
        del sig_T, open_T, close_by

    sym_j = {s: j for j, s in enumerate(MAJORS)}
    own = np.array([sym_j[s] for s in grid["sym"].to_numpy()])
    n = np.zeros(len(grid), dtype=int)
    for i in range(len(grid)):
        n[i] = count_n_row(O[i], C[i], SG[i], int(own[i]))
    grid["n"] = n
    grid["mult_dyn"] = 1.0 / (1.0 + n)
    grid[["sym", "x1", "T", "t_fill", "f", "t_exit", "size_dep", "y_dep",
          "n", "mult_dyn"]].to_parquet(OUT / "n_per_fill.parquet")

    # --- scoring on TEST rows (size_dep non-NaN), walk-forward static m(c,d) ---
    test = grid[grid["size_dep"].notna()].copy().reset_index(drop=True)
    years = []
    for k, a0 in enumerate(ANCHORS):
        a0 = pd.Timestamp(a0)
        te = ((test["T"] >= a0) & (test["T"] < a0 + pd.Timedelta(days=365))).to_numpy()
        tr = (grid["t_fill"] < a0 - EMBARGO).to_numpy()
        gtr = grid[tr]
        # static m(c,d): cell mean, else pooled depth mean, else 1.0
        cell = gtr.groupby(["sym", "x1"])["mult_dyn"].agg(["mean", "size"])
        pool = gtr.groupby(["x1"])["mult_dyn"].agg(["mean", "size"])
        mval = np.ones(int(te.sum()))
        idx = np.where(te)[0]
        fallbacks = 0
        for ii, r in enumerate(idx):
            c, dd = test.loc[r, "sym"], float(test.loc[r, "x1"])
            m = np.nan
            if (c, dd) in cell.index and cell.loc[(c, dd), "size"] >= MIN_FILLS:
                m = float(cell.loc[(c, dd), "mean"])
            elif dd in pool.index and pool.loc[dd, "size"] >= MIN_FILLS:
                m = float(pool.loc[dd, "mean"])
                fallbacks += 1
            else:
                m = 1.0
                fallbacks += 1
            mval[ii] = m
        sd = test["size_dep"].to_numpy()[te]
        yd = test["y_dep"].to_numpy()[te]
        sb_raw = sd * mval
        sc_raw = sd * test["mult_dyn"].to_numpy()[te]
        sb = sb_raw * sd.mean() / max(sb_raw.mean(), 1e-12)
        sc = sc_raw * sd.mean() / max(sc_raw.mean(), 1e-12)
        day = test["T"][te].dt.floor("D").to_numpy()
        arms = {}
        for nm, sz in (("a", sd), ("b", sb), ("c", sc)):
            s = pd.Series(sz * yd).groupby(day).sum().sort_index()
            S = float((sz * yd).sum())
            W = float(s.min())
            cum = s.cumsum().to_numpy()
            dd = maxdd_of_cumsum(cum)
            arms[nm] = dict(S=round(S, 4), W=round(W, 4), DD=round(dd, 4))
        red_dyn = arms["a"]["DD"] - arms["c"]["DD"]
        red_stat = arms["a"]["DD"] - arms["b"]["DD"]
        rec, ok = recovery_and_pass(arms["a"]["DD"], arms["b"]["DD"],
                                    arms["c"]["DD"], EPS)
        n_dist = pd.Series(test["n"].to_numpy()[te]).value_counts().sort_index()
        years.append({
            "anchor": str(a0.date()), "n": int(te.sum()),
            "n_train": int(tr.sum()), "pooled_fallbacks": int(fallbacks),
            "mean_m": round(float(mval.mean()), 4) if len(mval) else None,
            "S_a": arms["a"]["S"], "S_b": arms["b"]["S"], "S_c": arms["c"]["S"],
            "W_a": arms["a"]["W"], "W_b": arms["b"]["W"], "W_c": arms["c"]["W"],
            "DD_a": arms["a"]["DD"], "DD_b": arms["b"]["DD"], "DD_c": arms["c"]["DD"],
            "red_dyn": round(red_dyn, 4), "red_stat": round(red_stat, 4),
            "recovery": round(float(rec), 4) if rec is not None else None,
            "pass": bool(ok),
            "n_dist": {str(k): int(v) for k, v in n_dist.items()},
        })
    n_pass = sum(1 for y in years if y["pass"])
    promising = bool(n_pass >= 4)
    # m(c,d) table of the last anchor (illustrative; per-year cells in REPORT)
    res = {
        "meta": {
            "fills": str(H5.FILLS), "table": str(H5.TABLE),
            "universe": "majors x R2(2.5,3,3.5,4,5), outcome y_dep (deployed TP, exact net)",
            "n_def": "v399-B1 exact: n = # other majors with C[f-1] <= O[0]*(1-2.5*sig4); sig4 = 4h-open pct_change rolling(360,min120).std; O = 1m open at T (no ffill); C = 1m close at T+f-1 (within-bar ffill)",
            "n_source": "recomputed from 1m (BTC: btc_intraday_20260924/klines_1m_*.parquet; others: majors_intraday_20260924/{SYM}_1m_*.parquet), one coin-year at a time; no per-fill n reused from v399",
            "static": "m(c,d) = walk-forward mean of 1/(1+n) over majors-R2 fills with t_fill < anchor-7d; min 30 cells else pooled depth mean else 1.0",
            "renorm": "per-year mean-match to (a): s_b,s_c rescaled so mean equals mean(size_dep)",
            "maxDD": "max peak-to-trough decline of cumsum of calendar-day sums from 0 (native units)",
            "rule": "PASS(Y) iff red_dyn > 1e-12 and recovery=(DDa-DDb)/(DDa-DDc) >= 0.50; PROMISING iff >= 4/5 years",
            "T_min": str(test["T"].min()), "T_max": str(test["T"].max()),
            "grid_rows": int(len(grid)), "test_rows": int(len(test)),
        },
        "years": years,
        "decision": {
            "pass_years": f"{n_pass}/5",
            "promising": promising,
        },
    }
    (OUT / "results.json").write_text(json.dumps(res, indent=1))
    print(json.dumps(res["decision"], indent=1))
    for y in years:
        print(y["anchor"], "n", y["n"], "n_train", y["n_train"],
              "DD", y["DD_a"], y["DD_b"], y["DD_c"],
              "rec", y["recovery"], "pass", y["pass"])


if __name__ == "__main__":
    main()
