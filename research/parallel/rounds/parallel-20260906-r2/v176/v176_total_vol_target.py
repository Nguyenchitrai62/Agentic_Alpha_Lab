"""v176: portfolio vol targeting that includes the dip sleeve's risk (registry v176).

Why: in v175 the portfolio vol target measures only books + carry; the limit dip sleeve (size 0.25 per event) sits on
top, so total risk exceeds the 0.25 target and the full-path DD rises to 22.8%. A portfolio vol target should measure
the whole portfolio. This is a definitional fix, not a new parameter: target, cap, governor and the sleeve rule are
unchanged.
Fixed before running:
- Sleeve: v175 limit dip sleeve (same walk-forward k per anchor). sleeve_unit = sleeve(size 0.25) / S_REF with
  S_REF = 1.657 = mean portfolio scale s of v154 on engine_real (measured before any sleeve existed), so the average
  sleeve size stays ~0.25 when multiplied by s.
- realized_total[i] = 0.8 * sum(books[i-2] * r_i) + 0.6 * carry[i-1] + sleeve_unit[i-1] (all known at the decision);
  vol = std over 360 bars (min 120) * sqrt(2190); s = min(0.25 / vol, 2).
- Weights: books 0.8 * s * B * g, carry 0.6 * s * g, sleeve s * g * sleeve_unit; engine_real realism, v170 execution,
  20% governor (2-bar lag), budget/min-notional as engine_real.
Primary row: this portfolio. Reference: v175 5.627 / 22.81 (sleeve outside the vol target).

  python research/parallel/rounds/parallel-20260906-r2/v176/v176_total_vol_target.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
S_REF = 1.657


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


v175 = _load("v175", HERE.parent / "v175/v175_limit_dip_sleeve.py")
v172, v171, v170, er = v175.v172, v175.v171, v175.v170, v175.er
v99, v110, PD = er.v99, er.v110, er.PD


def run_total(books, ctx, sleeve_unit, target=0.25):
    idx, B, cols = books.index, books.to_numpy(), list(books.columns)
    r_next, lo, hi, fund = ctx["mkt"]
    fee_b, rel_b, fee_s, rel_s = ctx["exec"]
    carry, expo = ctx["carry_real"]
    o = ctx["opens"].reindex(idx)[cols]
    su = sleeve_unit.reindex(idx).fillna(0.0)
    realized = (v99.W_BOOKS * (books.shift(2) * (o / o.shift(1) - 1)).sum(axis=1)
                + v99.W_CARRY * v99.CARRY_LEV * pd.Series(carry, index=idx).shift(1) + su.shift(1))
    vol = (realized.rolling(60 * PD, min_periods=20 * PD).std() * np.sqrt(PD * 365)).to_numpy()
    s = np.where(np.isnan(vol), 1.0, np.minimum(target / np.where(np.isnan(vol), 1.0, vol), v99.CAP))
    sl = su.to_numpy()
    live = np.asarray((idx >= v110.START) & (idx < v110.END))
    mins = np.array([er.MIN_NOTIONAL.get(c, 5.0) for c in cols])
    n = len(idx)
    net, turn, g, eq = np.zeros(n), np.zeros(n), np.ones(n), np.ones(n)
    prev_w, prev_c = np.zeros(len(cols)), 0.0
    for i in range(n):
        if i >= 2:
            j = i - 2
            peak = eq[max(0, j - 90 * PD + 1): j + 1].max()
            g[i] = float(np.clip((0.20 - (1 - eq[j] / peak)) / 0.10, 0.0, 1.0))
        w = v99.W_BOOKS * s[i] * B[i] * g[i] if live[i] else np.zeros(len(cols))
        c = v99.W_CARRY * v99.CARRY_LEV * s[i] * g[i] if live[i] else 0.0
        if c * expo[i] + np.abs(w).sum() / er.MARGIN > er.BUFFER:
            c = min(c, max(0.0, (er.BUFFER - np.abs(w).sum() / er.MARGIN) / max(expo[i], 1e-9)))
            if np.abs(w).sum() / er.MARGIN > er.BUFFER:
                w = w * er.BUFFER * er.MARGIN / np.abs(w).sum()
        eq_usdt = er.ACCOUNT_USDT * (eq[i - 1] if i else 1.0)
        w = np.where((np.abs(w - prev_w) * eq_usdt < mins) & (w != 0), prev_w, w)
        dw = w - prev_w
        buy = dw > 0
        ex = np.sum(np.abs(dw) * np.where(buy, fee_b[i], fee_s[i]) + dw * np.where(buy, rel_b[i], rel_s[i]))
        turn[i] = np.abs(dw).sum()
        cc = abs(c - prev_c) / er.CARRY_CAPITAL * expo[i] * (er.SPOT_FEE + er.PERP_TAKER)
        net[i] = ((w * r_next[i]).sum() - ex - (w * fund[i]).sum() + c * carry[i] - cc
                  + (s[i] * g[i] * sl[i] if live[i] else 0.0))
        eq[i] = (eq[i - 1] if i else 1.0) * (1 + net[i])
        prev_w, prev_c = w, c
    out = v110.summarize(pd.Series(net, index=idx), pd.Series(turn, index=idx), pd.Series(g, index=idx))
    out["mean_scale"] = round(float(np.mean(s[live])), 3)
    return out


def main():
    books, opens = er.v154_books()
    idx, cols = books.index, list(books.columns)
    G = pd.date_range(v171.START, idx.max(), freq="4h")
    A = v172.cube_ohlc(G, cols)
    ev = v175.limit_returns(G, cols, A)
    del A
    sleeve, events, chosen = v171.sleeve_walk_forward(G, ev)
    print("chosen k", chosen, flush=True)
    ctx = er.context(books, opens)
    ex60, _ = v170.exec_costs_w(idx, cols, 60)
    ctx = dict(ctx, exec=ex60)
    r = run_total(books, ctx, sleeve / S_REF)
    print("primary", r["monthly_pct"], "fullDD", r["full_path_dd"], "mean s", r["mean_scale"],
          [(y["anchor"][:4], y["net_pct"], y["max_drawdown_percent"]) for y in r["yearly"]], flush=True)
    out = {"version": "v176", "chosen": chosen, "primary_total_vol_target": r, "reference_v175": (5.627, 22.81), "S_REF": S_REF}
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v176_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
