"""v184: add an hourly-anchored dip ladder to v183, sharing its open-notional stress budget (registry v184).

EX POST CONTEXT: after v171-v183 on the same span; the mechanism (minute-scale liquidation overshoot) was confirmed
out-of-universe in v181. Anchoring the ladder to the 4h open is arbitrary; an hourly ladder catches shorter overshoots
that recover within the hour, and short holding keeps them inside the open-notional budget.
Fixed before running:
- v183 unchanged (4h ladder 2.5/3/3.5/4 sigma_4h, TP at L(1+sigma_4h) maker, else next 4h open taker).
- Hourly ladder: for each hour H = T + h*60 min (h = 0..3) of the 4h holding bar, sigma_1h = std of 1h open-to-open
  returns over the 1440 hourly bars ending at the decision (t, i.e. before T; min 480). Rungs k = 2.5/3/3.5/4 sigma_1h
  below the 1m open of minute 0 of H; bids live in minutes 4..57 of H (h = 0: minutes 16..57, after the book
  execution window); maker 0.0002 fill at the bid on a 1m trade-through; TP sell at L(1 + sigma_1h) in the first later
  minute of the same 4h bar with high > TP (maker); otherwise exit at the 1m open of minute 0 of the next hour by taker
  0.0005 with slippage max(2 bps, 0.25 * range/open of that minute) (the h = 3 rung exits at T + 4h, pays that
  settlement's funding). Rung size = the 4h rung size (0.25/4 per asset before scaling).
- One shared budget: all fills of both ladders in the 4h bar, in (minute, ladder 4h first, rung, asset) order, taken iff
  (open rungs at that minute + 1) * rn <= 1/6 equity; rn = s*g*0.25/4/1.657.
- Vol leg: unbudgeted sum of both ladders' rung returns, shifted by 2 bars. 1m mark over open rungs.
Rows: normal and stress; gate DD = max(4h, 1m-marked). Reference v183 4.284 / 19.01 (stress 3.882 / 19.13).

  python research/parallel/rounds/parallel-20260906-r2/v184/v184_hourly_ladder.py
"""

from __future__ import annotations

import hashlib
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


v183 = _load("v183", HERE.parent / "v183/v183_tp_exit_open_budget.py")
v179, diag, v178, v176, v172, v171, v170, er = v183.v179, v183.diag, v183.v178, v183.v176, v183.v172, v183.v171, v183.v170, v183.er
v99, v110, PD = er.v99, er.v110, er.PD
N_MAX = v183.N_MAX


def hourly_table(G, cols, A, maker, taker, extra):
    """Hourly ladder: arrays [rung, bar, asset, hour] of limit, fill minute (in the 4h bar), exit minute, return."""
    O, H, L = A["open"].astype(float), A["high"].astype(float), A["low"].astype(float)
    n, _, na = O.shape
    # sigma_1h from 1h opens (minute 0/60/120/180 opens of each 4h bar), rolling 1440 hours ending before T
    h_open = O[:, [0, 60, 120, 180], :].reshape(n * 4, na)
    ret = pd.DataFrame(h_open).pct_change()
    sig_h = ret.rolling(1440, min_periods=480).std().to_numpy().reshape(n, 4, na)
    sig_t = np.full((n, na), np.nan)
    sig_t[1:] = sig_h[:-1, 3, :]  # last hourly std known before bar T starts (computed through the previous bar)
    fund = np.column_stack([er.funding_at_bar_open(s, G).shift(-2).fillna(0.0).to_numpy() for s in cols])
    xr_next = np.full((n, na), np.nan)
    xr_next[:-1] = (H[1:, 0, :] - L[1:, 0, :]) / O[1:, 0, :]
    o_next = np.full((n, na), np.nan)
    o_next[:-1] = O[1:, 0, :]
    nr = len(v178.RUNGS)
    lim = np.full((nr, n, na, 4), np.nan)
    fm = np.full((nr, n, na, 4), -1)
    xm = np.full((nr, n, na, 4), -1)
    rt = np.zeros((nr, n, na, 4))
    minute = np.arange(240)[None, :, None]
    for h in range(4):
        a0 = 16 if h == 0 else 60 * h + 4
        a1 = 60 * h + 57
        base = O[:, 60 * h, :]
        if h < 3:
            xo = O[:, 60 * (h + 1), :]
            xr = (H[:, 60 * (h + 1), :] - L[:, 60 * (h + 1), :]) / xo
            fh = np.zeros((n, na))
        else:
            xo, xr, fh = o_next, xr_next, fund
        s_out = np.maximum(0.0002, 0.25 * np.nan_to_num(xr)) + extra
        for r, k in enumerate(v178.RUNGS):
            lv = base * (1 - k * sig_t)
            hit = L[:, a0:a1 + 1, :] < lv[:, None, :]
            filled = hit.any(axis=1) & np.isfinite(xo) & np.isfinite(lv)
            f = np.where(filled, np.argmax(hit, axis=1) + a0, -1)
            tp = lv * (1 + sig_t)
            end_min = 60 * (h + 1)
            after = (minute > f[:, None, :]) & (minute < end_min) & (H > tp[:, None, :]) & filled[:, None, :]
            has_tp = after.any(axis=1)
            x = np.where(has_tp, np.argmax(after, axis=1), end_min)
            r_tp = tp / lv - 1 - 2 * maker
            r_hold = xo * (1 - s_out) / lv - 1 - maker - taker - fh
            lim[r, :, :, h] = lv
            fm[r, :, :, h] = f
            xm[r, :, :, h] = np.where(filled, x, -1)
            rt[r, :, :, h] = np.nan_to_num(np.where(filled, np.where(has_tp, r_tp, r_hold), 0.0))
    return lim, fm, xm, rt


def run(books, ctx, closes, G, t4, t1):
    lims, fmins, xmins, rets = t4
    hl, hf, hx, hr = t1
    idx, B, cols = books.index, books.to_numpy(), list(books.columns)
    r_next, lo, hi, fund = ctx["mkt"]
    fee_b, rel_b, fee_s, rel_s = ctx["exec"]
    carry, expo = ctx["carry_real"]
    o = ctx["opens"].reindex(idx)[cols]
    o1 = o.shift(-1).to_numpy()
    nr = len(v178.RUNGS)
    unit_raw = v171.SIZE / nr * (rets.sum(axis=(0, 2)) + hr.sum(axis=(0, 2, 3)))
    unit = pd.Series(unit_raw, index=G).reindex(idx).fillna(0.0) / v176.S_REF
    realized = (v99.W_BOOKS * (books.shift(2) * (o / o.shift(1) - 1)).sum(axis=1)
                + v99.W_CARRY * v99.CARRY_LEV * pd.Series(carry, index=idx).shift(1) + unit.shift(2))
    vol = (realized.rolling(60 * PD, min_periods=20 * PD).std() * np.sqrt(PD * 365)).to_numpy()
    s = np.where(np.isnan(vol), 1.0, np.minimum(0.25 / np.where(np.isnan(vol), 1.0, vol), v99.CAP))
    gpos = pd.Series(np.arange(len(G)), index=G).reindex(idx).to_numpy()
    live = np.asarray((idx >= v110.START) & (idx < v110.END))
    mins = np.array([er.MIN_NOTIONAL.get(c, 5.0) for c in cols])
    n = len(idx)
    net, turn, g, eq, eq_min = np.zeros(n), np.zeros(n), np.ones(n), np.ones(n), np.ones(n)
    taken_4h = taken_1h = cancelled = 0
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
        rn = s[i] * g[i] * v171.SIZE / nr / v176.S_REF
        if live[i] and gi >= 0:
            fills = [(fmins[r, gi, a], 0, r, a, -1) for r in range(nr) for a in range(len(cols)) if fmins[r, gi, a] >= 0]
            fills += [(hf[r, gi, a, h], 1, r, a, h) for r in range(nr) for a in range(len(cols)) for h in range(4) if hf[r, gi, a, h] >= 0]
            fills.sort()
            for f, lad, r, a, h in fills:
                open_now = sum(1 for t in taken if t[1] > f)
                if (open_now + 1) * rn <= N_MAX + 1e-12:
                    if lad == 0:
                        x, lv, rr = xmins[r, gi, a], lims[r, gi, a], rets[r, gi, a]
                        taken_4h += 1
                    else:
                        x, lv, rr = hx[r, gi, a, h], hl[r, gi, a, h], hr[r, gi, a, h]
                        taken_1h += 1
                    taken.append((f, x, lv, a, rr))
                    sleeve_pnl += rn * rr
                else:
                    cancelled += 1
        net[i] = (w * r_next[i]).sum() - ex + fnd + c * carry[i] - cc + sleeve_pnl
        prev_eq = eq[i - 1] if i else 1.0
        eq[i] = prev_eq * (1 + net[i])
        if live[i] and gi >= 0:
            Cm = closes[gi].astype(float)
            path = ((Cm / o1[i] - 1) * w).sum(axis=1)
            for f, x, lv, a, rr in taken:
                seg = np.zeros(240)
                end = min(x, 240)
                seg[f:end] = Cm[f:end, a] / lv - 1
                if x < 240:
                    seg[x:] = rr
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
    out["taken_4h"], out["taken_1h"], out["cancelled"] = taken_4h, taken_1h, cancelled
    return out


def main():
    books, opens = er.v154_books()
    idx, cols = books.index, list(books.columns)
    G = pd.date_range(v171.START, idx.max(), freq="4h")
    A = v172.cube_ohlc(G, cols)
    base = er.context(books, opens)
    ex60, _ = v170.exec_costs_w(idx, cols, 60)
    out = {"version": "v184", "reference_v183": {"normal": (4.284, 19.01), "stress": (3.882, 19.13)}}
    for key, maker, taker, extra, ex in (("primary_normal", 0.0002, 0.0005, 0.0, ex60),
                                         ("stress", 0.0004, 0.0007, 0.0005, diag.stress_exec(idx, cols))):
        t4 = v183.rung_table_tp(G, cols, A, maker, taker, extra)
        t1 = hourly_table(G, cols, A, maker, taker, extra)
        r = run(books, dict(base, exec=ex), A["close"], G, t4, t1)
        out[key] = r
        print(key, r["monthly_pct"], "4hDD", r["full_path_dd"], "1mDD", r["dd_1m_mark"], r["dd_1m_worst_bar"], "gateDD", r["gate_dd"],
              "4h", r["taken_4h"], "1h", r["taken_1h"], "cancelled", r["cancelled"],
              [(y["anchor"][:4], y["net_pct"], y["max_drawdown_percent"]) for y in r["yearly"]], flush=True)
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v184_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
