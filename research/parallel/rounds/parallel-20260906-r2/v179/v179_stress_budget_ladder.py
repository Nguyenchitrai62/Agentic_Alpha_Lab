"""v179: v178 ladder with a stress-loss budget on the sleeve's open notional (registry v179).

EX POST LABEL: the rule was designed after the v178 diagnostics showed a 27.8% 1m-marked DD on the 2025-10-10
liquidation crash (bids filled, prices kept falling inside the bar). Treat any improvement as hypothesis-grade.
Rule (a stress budget, not fitted): in a further -30% move of every asset the sleeve may lose at most 5% of equity, so
the sleeve's open notional per holding bar is capped at N_MAX = 0.05 / 0.30 = 1/6 of equity. Rung fills are taken in
time order (fill minute, then shallower rung, then column order BNB, BTC, ETH, SOL, XRP) while the cumulative notional
stays <= N_MAX; later fills in that bar are cancelled (whole rungs only). Causal: a live system knows its fills.
Everything else as v178 with the v176-audit causality fix (vol estimate uses the UNCAPPED sleeve unit shifted by 2
bars, conservative): rungs 2.5/3/3.5/4 sigma, base size 0.25/4 per rung and asset, rung notional s*g*0.25/4/1.657,
maker entry, taker exit at the next 4h open with crash-aware slippage, funding; books v154 + v170 execution on
engine_real, target 0.25, governor.
Gate DD = max(4h-close full-path DD, 1m-marked full-path DD). Rows: normal costs, cost stress (maker 0.0004 / taker
0.0007 + 5 bps). Reference v178: 5.508 / 18.57 / 27.79 (normal), 4.788 / 19.23 / 27.81 (stress).

  python research/parallel/rounds/parallel-20260906-r2/v179/v179_stress_budget_ladder.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
N_MAX = 0.05 / 0.30


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


diag = _load("v178d", HERE.parent / "v178/v178_diagnostics.py")
v178, v176, v172, v171, v170, er = diag.v178, diag.v176, diag.v172, diag.v171, diag.v170, diag.er
v99, v110, PD = er.v99, er.v110, er.PD


def rung_table(G, cols, A, maker, taker, extra):
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
    lims, fmins, rets = [], [], []
    for k in v178.RUNGS:
        lim = o1 * (1 - k * sig)
        hit = low < lim[:, None, :]
        filled = hit.any(axis=1) & np.isfinite(o2) & np.isfinite(lim)
        fmins.append(np.where(filled, np.argmax(hit, axis=1) + 16, -1))
        rets.append(np.nan_to_num(np.where(filled, o2 * (1 - s_out) / lim - 1 - maker - taker - fund, 0.0)))
        lims.append(lim)
    return np.stack(lims), np.stack(fmins), np.stack(rets)  # [rung, bar, asset]


def run(books, ctx, closes, G, lims, fmins, rets):
    idx, B, cols = books.index, books.to_numpy(), list(books.columns)
    r_next, lo, hi, fund = ctx["mkt"]
    fee_b, rel_b, fee_s, rel_s = ctx["exec"]
    carry, expo = ctx["carry_real"]
    o = ctx["opens"].reindex(idx)[cols]
    o1 = o.shift(-1).to_numpy()
    nr = len(v178.RUNGS)
    unit = pd.Series(v171.SIZE / nr * rets.sum(axis=(0, 2)), index=G).reindex(idx).fillna(0.0) / v176.S_REF
    realized = (v99.W_BOOKS * (books.shift(2) * (o / o.shift(1) - 1)).sum(axis=1)
                + v99.W_CARRY * v99.CARRY_LEV * pd.Series(carry, index=idx).shift(1) + unit.shift(2))
    vol = (realized.rolling(60 * PD, min_periods=20 * PD).std() * np.sqrt(PD * 365)).to_numpy()
    s = np.where(np.isnan(vol), 1.0, np.minimum(0.25 / np.where(np.isnan(vol), 1.0, vol), v99.CAP))
    gpos = pd.Series(np.arange(len(G)), index=G).reindex(idx).to_numpy()
    live = np.asarray((idx >= v110.START) & (idx < v110.END))
    mins = np.array([er.MIN_NOTIONAL.get(c, 5.0) for c in cols])
    n = len(idx)
    net, turn, g, eq, eq_min = np.zeros(n), np.zeros(n), np.ones(n), np.ones(n), np.ones(n)
    taken_total, cancelled_total = 0, 0
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
        fnd = -(w * fund[i]).sum()
        sleeve_pnl, taken = 0.0, []
        gi = int(gpos[i]) if not np.isnan(gpos[i]) else -1
        if live[i] and gi >= 0:
            rn = s[i] * g[i] * v171.SIZE / nr / v176.S_REF
            fills = [(fmins[r, gi, a], r, a) for r in range(nr) for a in range(len(cols)) if fmins[r, gi, a] >= 0]
            fills.sort()
            used = 0.0
            for f, r, a in fills:
                if used + rn <= N_MAX + 1e-12:
                    used += rn
                    taken.append((f, r, a))
                    sleeve_pnl += rn * rets[r, gi, a]
                else:
                    cancelled_total += 1
            taken_total += len(taken)
        net[i] = (w * r_next[i]).sum() - ex + fnd + c * carry[i] - cc + sleeve_pnl
        prev_eq = eq[i - 1] if i else 1.0
        eq[i] = prev_eq * (1 + net[i])
        if live[i] and gi >= 0:
            Cm = closes[gi].astype(float)
            path = ((Cm / o1[i] - 1) * w).sum(axis=1)
            for f, r, a in taken:
                seg = np.zeros(240)
                seg[f:] = Cm[f:, a] / lims[r, gi, a] - 1
                path += rn * seg
            eq_min[i] = prev_eq * (1 + min(0.0, float(np.nanmin(path))) - ex + min(fnd, 0.0))
        else:
            eq_min[i] = eq[i]
        prev_w, prev_c = w, c
    out = v110.summarize(pd.Series(net, index=idx), pd.Series(turn, index=idx), pd.Series(g, index=idx))
    full = np.asarray((idx >= v110.START) & (idx < v110.END))
    e, em = eq[full] / eq[full][0], eq_min[full] / eq[full][0]
    dd1 = 1 - np.minimum(e, em) / np.maximum.accumulate(e)
    out["dd_1m_mark"] = round(100 * float(dd1.max()), 2)
    out["dd_1m_worst_bar"] = str(idx[full][int(np.argmax(dd1))])
    out["gate_dd"] = max(out["full_path_dd"], out["dd_1m_mark"])
    out["rungs_taken"], out["rungs_cancelled"] = taken_total, cancelled_total
    return out


def main():
    books, opens = er.v154_books()
    idx, cols = books.index, list(books.columns)
    G = pd.date_range(v171.START, idx.max(), freq="4h")
    A = v172.cube_ohlc(G, cols)
    base = er.context(books, opens)
    ex60, _ = v170.exec_costs_w(idx, cols, 60)
    out = {"version": "v179", "N_MAX": N_MAX, "reference_v178": {"normal": (5.508, 18.57, 27.79), "stress": (4.788, 19.23, 27.81)}}
    for key, maker, taker, extra, ex in (("primary_normal", 0.0002, 0.0005, 0.0, ex60),
                                         ("stress", 0.0004, 0.0007, 0.0005, diag.stress_exec(idx, cols))):
        lims, fmins, rets = rung_table(G, cols, A, maker, taker, extra)
        r = run(books, dict(base, exec=ex), A["close"], G, lims, fmins, rets)
        out[key] = r
        print(key, r["monthly_pct"], "4hDD", r["full_path_dd"], "1mDD", r["dd_1m_mark"], r["dd_1m_worst_bar"], "gateDD", r["gate_dd"],
              "rungs", r["rungs_taken"], "cancelled", r["rungs_cancelled"],
              [(y["anchor"][:4], y["net_pct"], y["max_drawdown_percent"]) for y in r["yearly"]], flush=True)
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v179_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
