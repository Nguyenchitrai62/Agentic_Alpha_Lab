"""v183: ladder with take-profit limit exits and a budget on concurrently OPEN sleeve notional (registry v183).

EX POST CONTEXT: follows v178-v182 on the same span; hypothesis-grade.
Why: v179-v182 show the stress budget (open sleeve notional <= 1/6 equity) binds, not fill selection. The v179 budget
counted every fill of a bar for the whole bar although crash risk only sits in positions still open. A resting
take-profit sell closes rebounds early (maker fee, no further crash exposure), and the budget then only needs to cover
positions that are open at the same minute, so more rungs fit under the same tail budget.
Fixed before running:
- Ladder as v178 (rungs 2.5/3/3.5/4 sigma, bids live minutes 16..238, maker 0.0002 fill at L on a 1m trade-through).
- After a fill at minute f, a take-profit sell rests at TP = L * (1 + sigma) (one sigma of the 4h return); it fills at TP
  in the first minute m > f whose 1m high > TP (strict), maker 0.0002, no funding. Otherwise the rung exits at the next
  4h open as before (taker 0.0005, crash-aware slippage, funding at T+4h). Stress costs: maker 0.0004, taker 0.0007 +
  5 bps.
- Budget: fills processed in (minute, rung, asset) order; a fill is taken only if the notional of rungs OPEN at that
  minute (filled at or before it and not yet taken profit) plus the new rung <= 1/6 equity. Rung notional s*g*0.25/4/1.657.
- Vol leg: unbudgeted sleeve unit shifted by 2 bars (conservative, as v179). Books, engine, governor as v179.
- 1m mark: each taken rung is marked from its fill minute until its exit minute (then its return is locked).
Rows: normal and stress; gate DD = max(4h, 1m-marked). References v179 4.141 / 19.81, v182 4.143 / 20.04.

  python research/parallel/rounds/parallel-20260906-r2/v183/v183_tp_exit_open_budget.py
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
TP_SIG = 1.0


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


v179 = _load("v179", HERE.parent / "v179/v179_stress_budget_ladder.py")
diag, v178, v176, v172, v171, v170, er = v179.diag, v179.v178, v179.v176, v179.v172, v179.v171, v179.v170, v179.er
v99, v110, PD = er.v99, er.v110, er.PD


def rung_table_tp(G, cols, A, maker, taker, extra):
    """Per rung/bar/asset: limit L, fill minute f, exit minute x (240 = next 4h open), net return."""
    opens = pd.DataFrame({s: pd.read_parquet(er.XS / f"{s}_4h.parquet").assign(t=lambda d: pd.to_datetime(d["open_time"], utc=True))
                          .set_index("t")["open"] for s in cols}).reindex(G)
    o1, o2 = opens.shift(-1).to_numpy(), opens.shift(-2).to_numpy()
    sig = opens.pct_change().rolling(60 * PD, min_periods=20 * PD).std().to_numpy()
    fund = np.column_stack([er.funding_at_bar_open(s, G).shift(-2).fillna(0.0).to_numpy() for s in cols])
    O, H, L = A["open"], A["high"], A["low"]
    xr = np.full(o1.shape, np.nan)
    xr[:-1] = (H[1:, 0, :] - L[1:, 0, :]) / O[1:, 0, :]
    s_out = np.maximum(0.0002, 0.25 * np.nan_to_num(xr)) + extra
    Hf = H.astype(float)
    lims, fm, xm, rets = [], [], [], []
    minute = np.arange(240)[None, :, None]
    for k in v178.RUNGS:
        lim = o1 * (1 - k * sig)
        hit = L[:, 16:239, :].astype(float) < lim[:, None, :]
        filled = hit.any(axis=1) & np.isfinite(o2) & np.isfinite(lim)
        f = np.where(filled, np.argmax(hit, axis=1) + 16, -1)
        tp = lim * (1 + TP_SIG * sig)
        after = (minute > f[:, None, :]) & (Hf > tp[:, None, :]) & filled[:, None, :]
        has_tp = after.any(axis=1)
        x = np.where(has_tp, np.argmax(after, axis=1), 240)
        r_tp = tp / lim - 1 - 2 * maker
        r_hold = o2 * (1 - s_out) / lim - 1 - maker - taker - fund
        r = np.where(filled, np.where(has_tp, r_tp, r_hold), 0.0)
        lims.append(lim); fm.append(f); xm.append(np.where(filled, x, -1)); rets.append(np.nan_to_num(r))
    return np.stack(lims), np.stack(fm), np.stack(xm), np.stack(rets)


def run(books, ctx, closes, G, lims, fmins, xmins, rets):
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
    taken_total, cancelled_total, tp_total = 0, 0, 0
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
            fills = sorted((fmins[r, gi, a], r, a) for r in range(nr) for a in range(len(cols)) if fmins[r, gi, a] >= 0)
            for f, r, a in fills:
                open_now = sum(1 for (f2, r2, a2) in taken if xmins[r2, gi, a2] > f)
                if (open_now + 1) * rn <= N_MAX + 1e-12:
                    taken.append((f, r, a))
                    sleeve_pnl += rn * rets[r, gi, a]
                    tp_total += int(xmins[r, gi, a] < 240)
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
                x = xmins[r, gi, a]
                seg = np.zeros(240)
                end = min(x, 240)
                seg[f:end] = Cm[f:end, a] / lims[r, gi, a] - 1
                if x < 240:
                    seg[x:] = rets[r, gi, a]
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
    out["rungs_taken"], out["rungs_cancelled"], out["tp_exits"] = taken_total, cancelled_total, tp_total
    return out


def main():
    books, opens = er.v154_books()
    idx, cols = books.index, list(books.columns)
    G = pd.date_range(v171.START, idx.max(), freq="4h")
    A = v172.cube_ohlc(G, cols)
    base = er.context(books, opens)
    ex60, _ = v170.exec_costs_w(idx, cols, 60)
    out = {"version": "v183", "N_MAX": N_MAX, "TP_SIG": TP_SIG, "reference": {"v179": (4.141, 19.81), "v182": (4.143, 20.04)}}
    for key, maker, taker, extra, ex in (("primary_normal", 0.0002, 0.0005, 0.0, ex60),
                                         ("stress", 0.0004, 0.0007, 0.0005, diag.stress_exec(idx, cols))):
        lims, fm, xm, rets = rung_table_tp(G, cols, A, maker, taker, extra)
        r = run(books, dict(base, exec=ex), A["close"], G, lims, fm, xm, rets)
        out[key] = r
        print(key, r["monthly_pct"], "4hDD", r["full_path_dd"], "1mDD", r["dd_1m_mark"], r["dd_1m_worst_bar"], "gateDD", r["gate_dd"],
              "rungs", r["rungs_taken"], "tp", r["tp_exits"], "cancelled", r["rungs_cancelled"],
              [(y["anchor"][:4], y["net_pct"], y["max_drawdown_percent"]) for y in r["yearly"]], flush=True)
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v183_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
