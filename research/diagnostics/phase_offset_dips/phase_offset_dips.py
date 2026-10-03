"""Dev-only diagnostic (not a registered version): do dip ladders on 2h-offset 4h bars diversify the aligned ladder?

Dip-only sleeve (no book), M3 dip rules without the agents: rungs 3.0 / 4.0 sigma_4h below the bar open, bids live minutes 16..238, maker on a
strict trade-through, TP 1 sigma_4h (maker), exchange-native touch stop 8 sigma_4h (taker), timeout at the next bar open (taker), risk budget
0.26 counted at the stop, size_mult 4.375, vol-target scale of zero books = 1 (cap 2), governor on the sleeve's own equity.
Grid A = 4h bars starting 00/04/08/12/16/20 UTC (as deployed); grid B = the same bars shifted by +2h (02/06/...). Funding at settlements falling
inside a bar is ignored on both grids (diagnostic). Only the four dev years (2021-09-24 .. 2025-09-23) are reported; nothing is selected here.
Output: per grid yearly return / DD, daily-return correlation A vs B, and the 50/50 capital split.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
RD = ROOT / "research/parallel/rounds/parallel-20260906-r2"
OUT = Path(__file__).parent
SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
DEV0, DEV1 = pd.Timestamp("2021-09-24", tz="UTC"), pd.Timestamp("2025-09-24", tz="UTC")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def minutes():
    out = {}
    for s in SYMS:
        d = ROOT / ("data/raw/btc_intraday_20260924" if s == "BTCUSDT" else "data/raw/majors_intraday_20260924")
        pat = "klines_1m_20*.parquet" if s == "BTCUSDT" else f"{s}_1m_20*.parquet"
        m = pd.concat([pd.read_parquet(f, columns=["open_time", "open", "high", "low", "close"]) for f in sorted(d.glob(pat))])
        m["open_time"] = pd.to_datetime(m["open_time"], utc=True)
        out[s] = m.drop_duplicates("open_time").set_index("open_time").sort_index()
    return out


def prep_grid(M, shift_h, eu):
    """engine_user.prepare equivalent on a 4h grid shifted by shift_h hours (decision rows idx, holding bar = idx + 4h)."""
    sh = pd.Timedelta(hours=shift_h)
    t0, t1 = DEV0 - pd.Timedelta(days=120) + sh, DEV1 + sh
    idx = pd.date_range(t0, t1, freq="4h")
    n, na = len(idx), len(SYMS)
    cube = {k: np.full((n, 240, na), np.nan) for k in ("open", "high", "low", "close")}
    opens = pd.DataFrame(index=idx, columns=SYMS, dtype=float)
    for j, s in enumerate(SYMS):
        m = M[s]
        m = m[(m.index >= idx[0]) & (m.index < idx[-1] + pd.Timedelta(hours=8))]
        start = (m.index - sh).floor("4h") + sh          # bar start of each minute on the shifted grid
        row = pd.Index(idx + pd.Timedelta(hours=4)).get_indexer(start)  # cube row i = holding bar idx[i] + 4h
        ok = row >= 0
        off = ((m.index - start).total_seconds() // 60).astype(int)
        for k in cube:
            cube[k][row[ok], off[ok], j] = m[k].to_numpy(float)[ok]
        first = m[m.index == start]["open"]
        opens[s] = pd.Series(first.to_numpy(), index=first.index).reindex(idx)
    for k in cube:
        X = cube[k]
        for mm in range(1, 240):
            miss = np.isnan(X[:, mm, :])
            X[:, mm, :][miss] = X[:, mm - 1, :][miss]
    o = opens
    sig4 = o.pct_change().rolling(360, min_periods=120).std().to_numpy()
    settle = np.zeros(n, bool)
    return idx, opens, dict(idx=idx, cols=SYMS, O=cube["open"], H=cube["high"], L=cube["low"], C=cube["close"], sig4=sig4,
                             o1=o.shift(-1).to_numpy(), o2=o.shift(-2).to_numpy(), settle=settle)


def dev_summary(idx, net, eq, eq_min, g, stats, eq_max=None):
    """engine_user.summarize restricted to the four dev anchors (the most recent year is never simulated here)."""
    years = []
    for a in ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24"):
        a0 = pd.Timestamp(a, tz="UTC")
        mk = np.asarray((idx >= a0) & (idx < a0 + pd.Timedelta(days=365)))
        if not mk.any():
            continue
        first = int(np.argmax(mk))
        base = eq[first - 1] if first > 0 else 1.0
        e, em = eq[mk] / base, eq_min[mk] / base
        peak = np.maximum.accumulate(np.concatenate([[1.0], e]))[1:]
        years.append(dict(anchor=a, net_pct=round(100 * float(e[-1] - 1), 2), dd_1m_pct=round(100 * float(np.max(1 - np.minimum(e, em) / peak)), 2)))
    live = eq_min < 1e9
    peak = np.maximum.accumulate(eq)
    return dict(yearly=years, dd_4h=round(100 * float(np.max(1 - eq / peak)), 2), dd_1m=round(100 * float(np.max(1 - np.minimum(eq, eq_min) / peak)), 2),
                stats=stats)


def main():
    eu = _load("eu_phase", RD / "engine_user/engine_user.py")
    eu.summarize = dev_summary
    M = minutes()
    res, daily = {}, {}
    for name, sh in (("A_aligned", 0), ("B_offset2h", 2), ("C_offset1h", 1), ("D_offset3h", 3)):
        idx, opens, prep = prep_grid(M, sh, eu)
        books = pd.DataFrame(0.0, index=idx, columns=SYMS)
        eu.v110.START, eu.v110.END = DEV0 + pd.Timedelta(hours=sh), DEV1 + pd.Timedelta(hours=sh)
        path = {}
        r = eu.simulate(books, opens, prep, sleeve=True, rungs=(3.0, 4.0), sleeve_stop_mode="touch", m_sleeve_sl=8.0, sleeve_risk_budget=0.26,
                        size_mult=4.375, m_sleeve_tp=1.0, sleeve_start=16, win_start=5, path_out=path)
        eq = pd.Series(path["eq"], index=path["t"] + pd.Timedelta(hours=4))
        eq = eq[(eq.index > DEV0) & (eq.index <= DEV1 + pd.Timedelta(hours=8))]
        daily[name] = eq.resample("1D").last().pct_change().dropna()
        res[name] = {k: r[k] for k in ("dd_4h", "dd_1m", "stats")}
        res[name]["years"] = [(y["anchor"], y["net_pct"], y["dd_1m_pct"]) for y in r["yearly"]]
        print(name, res[name]["years"], "DD", r["dd_1m"], flush=True)
    d = pd.concat(daily, axis=1).dropna()
    res["corr_daily"] = round(float(d.corr().iloc[0, 1]), 3)
    res["corr_matrix"] = d.corr().round(3).to_dict()
    for tag, cols_ in (("mix_50_50", ["A_aligned", "B_offset2h"]), ("mix_4_phases", list(d.columns))):
        mix = (1 + d[cols_].mean(axis=1)).cumprod()
        res[tag] = dict(total_pct=round(100 * (mix.iloc[-1] - 1), 2), dd_daily_pct=round(100 * float((1 - mix / mix.cummax()).max()), 2),
                        yearly=[round(100 * float(mix[(mix.index > pd.Timestamp(y, tz="UTC")) & (mix.index <= pd.Timestamp(y, tz="UTC") + pd.Timedelta(days=365))].iloc[-1]
                                                   / mix[mix.index <= pd.Timestamp(y, tz="UTC")].iloc[-1] - 1), 1) if (mix.index <= pd.Timestamp(y, tz="UTC")).any() else None
                                for y in ("2022-09-24", "2023-09-24", "2024-09-24")])
    for name in daily:
        e = (1 + d[name]).cumprod()
        res[name]["total_pct_daily"] = round(100 * (e.iloc[-1] - 1), 2)
        res[name]["dd_daily_pct"] = round(100 * float((1 - e / e.cummax()).max()), 2)
    print(json.dumps({k: v for k, v in res.items() if k.startswith(("mix", "corr"))}), flush=True)
    (OUT / "phase_offset_dips.json").write_text(json.dumps(res, indent=1, default=str))


if __name__ == "__main__":
    main()
