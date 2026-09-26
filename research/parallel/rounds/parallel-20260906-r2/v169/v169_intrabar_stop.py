"""v169: intrabar portfolio stop on 1m data under the realistic engine (registry v169).

Motivation (descriptive v154 error analysis, research/diagnostics/v154_error_analysis/REPORT.md): 4 of the 5 deepest
drawdown episodes are long books caught in fast sell-offs (e.g. 2025-09-21 -> 09-25: -15.2% in 4 days); the 4h engine
cannot react inside a bar, and the intrabar DD bound (21.4%) exceeds the 20% limit. A protective stop is not in the
tried list. This is a risk rule, not a fitted model: nothing is estimated on test data.

Fixed before running:
- Books: v154 (A+B+D)/3 (cached by engine_real), engine_real with all realism on (actual funding, real carry, capital
  budget, min notional), target 0.25, 20% governor. The loop is engine_real.run copied, plus the stop.
- Holding bar of decision i starts at T = t_i + 4h. Portfolio path on 1m closes: R(m) = sum_j w_j (close_j(m)/o_j(T) - 1),
  o_j(T) = the 4h open used by the engine. Monitoring runs over minutes 16..239 (after the v135 fill window).
- Threshold: L_i = k * sqrt(w' S_i w), S_i = covariance of 4h open-to-open asset returns over the 360 bars ending at
  bar i (min 120; known at the decision). Primary k = 3; k = 2 and k = 4 are reported as labelled sensitivities only.
- Trigger: first minute m with R(m) <= -L_i. Exit every position at the 1m open of minute m + 1 (taker 0.0005 plus
  5 bps crash slippage per unit of |w|); flat until the next decision, which re-enters through the normal v135
  execution from zero; a stopped position does not pay the funding settlement at the next bar open. Carry is untouched.
- Also reported for every row: 1m mark-to-market full-path DD (equity marked on every 1m close of the live span,
  using R(m) up to the exit), replacing the conservative 4h bound as the realistic intrabar DD.
Rows: no-stop baseline (must equal engine_real v154: 3.708 / 18.87), k = 3 primary, k = 2 / 4 sensitivity; stop count,
monthly %, yearly, full-path DD (4h close) and 1m DD.

  python research/parallel/rounds/parallel-20260906-r2/v169/v169_intrabar_stop.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
KS = (None, 3.0, 2.0, 4.0)
EXIT_COST = 0.0005 + 0.0005
MON0 = 16


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


er = _load("engine_real", HERE.parent / "engine_real/engine_real.py")
v99, v110, v135, PD = er.v99, er.v110, er.v135, er.PD


def minute_cube(idx, cols):
    """close[i, m, j] and open[i, m, j] of the holding bar T = t_i + 4h, minutes 0..239 (NaN where missing)."""
    starts = idx + pd.Timedelta(hours=4)
    n = len(idx)
    C, O = np.full((n, 240, len(cols)), np.nan), np.full((n, 240, len(cols)), np.nan)
    pos = pd.Series(np.arange(n), index=starts)
    for j, s in enumerate(cols):
        d = Path("data/raw/btc_intraday_20260924") if s == "BTCUSDT" else Path("data/raw/majors_intraday_20260924")
        pat = "klines_1m_20*.parquet" if s == "BTCUSDT" else f"{s}_1m_20*.parquet"
        m = pd.concat([pd.read_parquet(f, columns=["open_time", "open", "close"]) for f in sorted(d.glob(pat))])
        m["open_time"] = pd.to_datetime(m["open_time"], utc=True)
        m = m.drop_duplicates("open_time")
        T = m["open_time"].dt.floor("4h")
        i = pos.reindex(T).to_numpy()
        ok = ~np.isnan(i)
        off = ((m["open_time"] - T).dt.total_seconds() // 60).astype(int).to_numpy()
        ii, oo = i[ok].astype(int), off[ok]
        C[ii, oo, j] = m["close"].to_numpy(float)[ok]
        O[ii, oo, j] = m["open"].to_numpy(float)[ok]
    # forward-fill missing minutes inside a bar
    for A in (C, O):
        for m in range(1, 240):
            miss = np.isnan(A[:, m, :])
            A[:, m, :][miss] = A[:, m - 1, :][miss]
    return C, O


def run_stop(books, ctx, cube, cov, k, target=0.25, gov=True):
    real = er.FULL
    idx, B, cols = books.index, books.to_numpy(), list(books.columns)
    r_next, lo, hi, fund = ctx["mkt"]
    fee_b, rel_b, fee_s, rel_s = ctx["exec"]
    carry, expo = ctx["carry_real"]
    o = ctx["opens"].reindex(idx)[cols]
    o1 = o.shift(-1).to_numpy()
    C, O = cube
    realized = v99.W_BOOKS * (books.shift(2) * (o / o.shift(1) - 1)).sum(axis=1) + v99.W_CARRY * v99.CARRY_LEV * pd.Series(carry, index=idx).shift(1)
    vol = (realized.rolling(60 * PD, min_periods=20 * PD).std() * np.sqrt(PD * 365)).to_numpy()
    s = np.where(np.isnan(vol), 1.0, np.minimum(target / np.where(np.isnan(vol), 1.0, vol), v99.CAP))
    live = np.asarray((idx >= v110.START) & (idx < v110.END))
    mins = np.array([er.MIN_NOTIONAL.get(c, 5.0) for c in cols])
    n = len(idx)
    net, turn, g, eq = np.zeros(n), np.zeros(n), np.ones(n), np.ones(n)
    eq_min = np.ones(n)
    stops = np.zeros(n, dtype=bool)
    prev_w, prev_c = np.zeros(len(cols)), 0.0
    for i in range(n):
        if gov and i >= 2:
            j = i - 2
            peak = eq[max(0, j - 90 * PD + 1): j + 1].max()
            g[i] = float(np.clip((0.20 - (1 - eq[j] / peak)) / 0.10, 0.0, 1.0))
        w = v99.W_BOOKS * s[i] * B[i] * g[i] if live[i] else np.zeros(len(cols))
        c = v99.W_CARRY * v99.CARRY_LEV * s[i] * g[i] if live[i] else 0.0
        used = c * expo[i] + np.abs(w).sum() / er.MARGIN
        if used > er.BUFFER:
            c = min(c, max(0.0, (er.BUFFER - np.abs(w).sum() / er.MARGIN) / max(expo[i], 1e-9)))
            if np.abs(w).sum() / er.MARGIN > er.BUFFER:
                w = w * er.BUFFER * er.MARGIN / np.abs(w).sum()
        eq_usdt = er.ACCOUNT_USDT * (eq[i - 1] if i else 1.0)
        small = (np.abs(w - prev_w) * eq_usdt < mins) & (w != 0)
        w = np.where(small, prev_w, w)
        dw = w - prev_w
        buy = dw > 0
        ex = np.sum(np.abs(dw) * np.where(buy, fee_b[i], fee_s[i]) + dw * np.where(buy, rel_b[i], rel_s[i]))
        turn[i] = np.abs(dw).sum()
        base = o1[i]
        path = None
        if np.any(w != 0) and np.all(np.isfinite(base)):
            path = ((C[i] / base - 1) * w).sum(axis=1)  # R(m), m = 0..239
        stopped = False
        if k is not None and path is not None and cov[i] is not None:
            L = k * float(np.sqrt(max(w @ cov[i] @ w, 0.0)))
            hit = np.nonzero(path[MON0:239] <= -L)[0] if L > 0 else []
            if len(hit):
                m = MON0 + int(hit[0])
                xo = O[i, m + 1]
                if np.all(np.isfinite(xo)):
                    stopped = True
                    stops[i] = True
                    gross = float((w * (xo / base - 1)).sum())
                    ex += float(np.abs(w).sum() * EXIT_COST)
                    fnd = 0.0
                    path_used = path[: m + 1]
        if not stopped:
            gross = float((w * r_next[i]).sum())
            fnd = -float((w * fund[i]).sum())
            path_used = path
        cc = abs(c - prev_c) / er.CARRY_CAPITAL * expo[i] * (er.SPOT_FEE + er.PERP_TAKER)
        net[i] = gross - ex + fnd + c * carry[i] - cc
        prev_eq = eq[i - 1] if i else 1.0
        eq[i] = prev_eq * (1 + net[i])
        eq_min[i] = prev_eq * (1 + min(0.0, float(np.nanmin(path_used)) if path_used is not None else 0.0) - ex)
        prev_w = np.zeros(len(cols)) if stopped else w
        prev_c = c
    out = v110.summarize(pd.Series(net, index=idx), pd.Series(turn, index=idx), pd.Series(g, index=idx))
    full = np.asarray((idx >= v110.START) & (idx < v110.END))
    e, em = eq[full] / eq[full][0], eq_min[full] / eq[full][0]
    out["dd_1m_mark"] = round(100 * float(np.max(1 - np.minimum(e, em) / np.maximum.accumulate(e))), 2)
    out["stops"] = int(stops[full].sum())
    out["stops_per_year"] = [int(stops[full & np.asarray((idx >= pd.Timestamp(a, tz="UTC")) & (idx < pd.Timestamp(a, tz="UTC") + pd.Timedelta(days=365)))].sum())
                             for a in v110.v92.ANCHORS]
    return out


def main():
    books, opens = er.v154_books()
    idx, cols = books.index, list(books.columns)
    ctx = er.context(books, opens)
    cube = minute_cube(idx, cols)
    rets = opens.reindex(idx)[cols].pct_change()
    cv = rets.rolling(60 * PD, min_periods=20 * PD).cov()
    cov = [None] * len(idx)
    for i, t in enumerate(idx):
        try:
            m = cv.loc[t].reindex(index=cols, columns=cols).to_numpy()
            cov[i] = m if np.all(np.isfinite(m)) else None
        except KeyError:
            pass
    out = {"version": "v169", "reference_engine_real_v154": {"monthly_pct": 3.708, "full_path_dd": 18.87}}
    for k in KS:
        key = "baseline_no_stop" if k is None else ("primary_k3" if k == 3.0 else f"sensitivity_k{int(k)}")
        r = run_stop(books, ctx, cube, cov, k)
        out[key] = r
        print(key, r["monthly_pct"], "fullDD", r["full_path_dd"], "dd1m", r["dd_1m_mark"], "stops", r["stops"], r["stops_per_year"],
              [(y["anchor"][:4], y["net_pct"], y["max_drawdown_percent"]) for y in r["yearly"]], flush=True)
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v169_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
