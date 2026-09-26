"""v178 diagnostics (labelled; the v176 audit asked for these before any promotion):

1. Causality fix: the sleeve leg of the vol estimate uses sleeve_unit[i-2] (the i-1 exit fill range is only known one
   minute after the decision); the payoff leg is unchanged.
2. Cost stress (gate scenarios under the realistic engine): books maker 0.0004 / taker 0.0007 + 5 bps on taker fills;
   sleeve entry fee 0.0004, exit fee 0.0007 + 5 bps.
3. 1m mark-to-market full-path DD: every minute of every holding bar, equity = previous close equity * (1 + books
   path R_b(m) + sleeve path R_s(m) - execution cost + min(funding, 0)), with R_b(m) = sum_j w_j (close_j(m)/open_j(T) - 1)
   and R_s(m) = sum over filled rungs from their fill minute of s*g/1.657 * 0.25/4 * (close_j(m)/L - 1).
Rows: fixed (normal costs), fixed + stress; each with 4h-close full-path DD and 1m-marked DD.

  python research/parallel/rounds/parallel-20260906-r2/v178/v178_diagnostics.py
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


v178 = _load("v178", HERE / "v178_limit_ladder.py")
v176, v175, v172, v171, v170, er = v178.v176, v178.v175, v178.v172, v178.v171, v178.v170, v178.er
v99, v110, PD = er.v99, er.v110, er.PD


def ladder(G, cols, A, maker, taker, extra):
    """Per bar/asset: sleeve return (avg over rungs, size-free) and per-rung fill minute / limit (for the 1m mark)."""
    opens = pd.DataFrame({s: pd.read_parquet(er.XS / f"{s}_4h.parquet").assign(t=lambda d: pd.to_datetime(d["open_time"], utc=True))
                          .set_index("t")["open"] for s in cols}).reindex(G)
    o1, o2 = opens.shift(-1).to_numpy(), opens.shift(-2).to_numpy()
    sig = opens.pct_change().rolling(60 * PD, min_periods=20 * PD).std().to_numpy()
    fund = np.column_stack([er.funding_at_bar_open(s, G).shift(-2).fillna(0.0).to_numpy() for s in cols])
    O, H, L = A["open"], A["high"], A["low"]
    low = L[:, 16:239, :].astype(float)
    xr = np.full(o1.shape, np.nan)
    xr[:-1] = (H[1:, 0, :] - L[1:, 0, :]) / O[1:, 0, :]
    s_out = np.maximum(0.0002, 0.25 * np.nan_to_num(xr)) + extra
    ret = np.zeros(o1.shape)
    rungs = []
    for k in v178.RUNGS:
        lim = o1 * (1 - k * sig)
        hit = low < lim[:, None, :]
        filled = hit.any(axis=1) & np.isfinite(o2) & np.isfinite(lim)
        fmin = np.where(filled, np.argmax(hit, axis=1) + 16, -1)
        val = o2 * (1 - s_out) / lim - 1 - maker - taker - fund
        ret += np.nan_to_num(np.where(filled, val, 0.0)) / len(v178.RUNGS)
        rungs.append((lim, fmin))
    return ret, rungs


def run(books, ctx, cube_c, sleeve_ret, rungs, G, mark=True):
    idx, B, cols = books.index, books.to_numpy(), list(books.columns)
    r_next, lo, hi, fund = ctx["mkt"]
    fee_b, rel_b, fee_s, rel_s = ctx["exec"]
    carry, expo = ctx["carry_real"]
    o = ctx["opens"].reindex(idx)[cols]
    o1 = o.shift(-1).to_numpy()
    su = pd.Series(v171.SIZE * sleeve_ret.sum(axis=1), index=G).reindex(idx).fillna(0.0) / v176.S_REF
    realized = (v99.W_BOOKS * (books.shift(2) * (o / o.shift(1) - 1)).sum(axis=1)
                + v99.W_CARRY * v99.CARRY_LEV * pd.Series(carry, index=idx).shift(1) + su.shift(2))
    vol = (realized.rolling(60 * PD, min_periods=20 * PD).std() * np.sqrt(PD * 365)).to_numpy()
    s = np.where(np.isnan(vol), 1.0, np.minimum(0.25 / np.where(np.isnan(vol), 1.0, vol), v99.CAP))
    sl = su.to_numpy()
    gpos = pd.Series(np.arange(len(G)), index=G).reindex(idx).to_numpy()
    live = np.asarray((idx >= v110.START) & (idx < v110.END))
    mins = np.array([er.MIN_NOTIONAL.get(c, 5.0) for c in cols])
    n = len(idx)
    net, turn, g, eq, eq_min = np.zeros(n), np.zeros(n), np.ones(n), np.ones(n), np.ones(n)
    prev_w, prev_c = np.zeros(len(cols)), 0.0
    rung_size = v171.SIZE / len(v178.RUNGS) / v176.S_REF
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
        fnd = -(w * fund[i]).sum()
        net[i] = (w * r_next[i]).sum() - ex + fnd + c * carry[i] - cc + (s[i] * g[i] * sl[i] if live[i] else 0.0)
        prev_eq = eq[i - 1] if i else 1.0
        eq[i] = prev_eq * (1 + net[i])
        if mark and live[i] and not np.isnan(gpos[i]):
            gi = int(gpos[i])
            Cm = cube_c[gi].astype(float)  # [240, asset]
            path = ((Cm / o1[i] - 1) * w).sum(axis=1)
            for lim, fmin in rungs:
                for jj in range(len(cols)):
                    f = fmin[gi, jj]
                    if f >= 0:
                        seg = np.zeros(240)
                        seg[f:] = Cm[f:, jj] / lim[gi, jj] - 1
                        path += s[i] * g[i] * rung_size * seg
            eq_min[i] = prev_eq * (1 + min(0.0, float(np.nanmin(path))) - ex + min(fnd, 0.0))
        else:
            eq_min[i] = eq[i]
        prev_w, prev_c = w, c
    out = v110.summarize(pd.Series(net, index=idx), pd.Series(turn, index=idx), pd.Series(g, index=idx))
    full = np.asarray((idx >= v110.START) & (idx < v110.END))
    e, em = eq[full] / eq[full][0], eq_min[full] / eq[full][0]
    out["dd_1m_mark"] = round(100 * float(np.max(1 - np.minimum(e, em) / np.maximum.accumulate(e))), 2)
    worst = int(np.argmax(1 - np.minimum(e, em) / np.maximum.accumulate(e)))
    out["dd_1m_worst_bar"] = str(idx[full][worst])
    return out


def stress_exec(idx, cols):
    (fee_b, rel_b, fee_s, rel_s), _ = v170.exec_costs_w(idx, cols, 60)
    maker_b, maker_s = fee_b == 0.0002, fee_s == 0.0002
    fee_b = np.where(maker_b, 0.0004, 0.0007)
    fee_s = np.where(maker_s, 0.0004, 0.0007)
    rel_b = np.where(maker_b, rel_b, rel_b + 0.0005)
    rel_s = np.where(maker_s, rel_s, rel_s - 0.0005)
    return fee_b, rel_b, fee_s, rel_s


def main():
    books, opens = er.v154_books()
    idx, cols = books.index, list(books.columns)
    G = pd.date_range(v171.START, idx.max(), freq="4h")
    A = v172.cube_ohlc(G, cols)
    base = er.context(books, opens)
    ex60, _ = v170.exec_costs_w(idx, cols, 60)
    out = {"note": "DIAGNOSTIC for v178 (labelled): causality fix, cost stress, 1m-marked DD"}
    for key, maker, taker, extra, ex in (("fixed_normal", 0.0002, 0.0005, 0.0, ex60),
                                         ("fixed_stress", 0.0004, 0.0007, 0.0005, stress_exec(idx, cols))):
        ret, rungs = ladder(G, cols, A, maker, taker, extra)
        r = run(books, dict(base, exec=ex), A["close"], ret, rungs, G)
        out[key] = r
        print(key, r["monthly_pct"], "fullDD(4h)", r["full_path_dd"], "DD(1m)", r["dd_1m_mark"], r["dd_1m_worst_bar"],
              [(y["anchor"][:4], y["net_pct"], y["max_drawdown_percent"]) for y in r["yearly"]], flush=True)
    (HERE / "v178_diagnostics.json").write_text(json.dumps(out, indent=1, default=str))


if __name__ == "__main__":
    main()
