"""v171: intrabar dip-reversal sleeve on 1m data, added to v154 under the realistic engine (registry v171).

Origin (labelled ex post): v169 showed that exiting after large intrabar portfolio drops loses ~1pp/month, i.e. such
drops tend to recover before the next 4h open. This version tests the mirror trade as a separate sleeve with a
walk-forward choice of its only parameter, so the anchor years are not used to set it. Still, the idea itself came from
seen data: treat any gain as a hypothesis for the prospective log, not as validated.

Fixed before running:
- Universe BTC/ETH/SOL/BNB/XRP USD-M perps; 4h grid of decision bars t from 2020-02-01; holding bar T = t + 4h.
- sigma_j(t) = std of 4h open-to-open returns over the 360 bars ending at t (min 120), known at the decision.
- Event: first minute m in 16..238 of T with close_j(m)/open_j(T) - 1 <= -k sigma_j(t). Buy at the minute m+1 open
  * (1 + 0.0002) with taker fee 0.0005; sell at the next 4h open * (1 - 0.0002) with taker fee 0.0005; the long pays the
  funding settled at that open (conservative). At most one event per asset per bar. Size 0.25 of equity per event.
- k per anchor from (2, 2.5, 3, 3.5, 4): best Sharpe of the per-bar sleeve return on [2020-02-01 + 30 d,
  anchor - 1 d]; applied to [anchor, anchor + 365 d).
- Rows: sleeve alone (yearly net, DD, events, hit rate, corr of daily returns with v154 engine_real);
  primary = v154 engine_real loop (target 0.25, 20% governor, all realism) + sleeve * g (the governor also scales the
  sleeve; the sleeve's margin (<= 0.25 of equity) is inside the 5% budget buffer and not modelled separately).
  Reference v154 engine_real 3.708 / 18.87 (and v170 execution 3.802 once audited; v171 keeps the 15-minute execution
  so that the comparison isolates the sleeve).

  python research/parallel/rounds/parallel-20260906-r2/v171/v171_intrabar_reversal.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
KGRID = (2.0, 2.5, 3.0, 3.5, 4.0)
SIZE, TAKER, SLIP = 0.25, 0.0005, 0.0002
START = pd.Timestamp("2020-02-01", tz="UTC")


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


er = _load("engine_real", HERE.parent / "engine_real/engine_real.py")
v169 = _load("v169", HERE.parent / "v169/v169_intrabar_stop.py")
v99, v110, PD = er.v99, er.v110, er.PD
ANCHORS = er.v92.ANCHORS


def event_returns(G, cols):
    """ret[k][i, j]: net event return (0 if no event) for each k in KGRID."""
    opens = pd.DataFrame({s: pd.read_parquet(er.XS / f"{s}_4h.parquet").assign(t=lambda d: pd.to_datetime(d["open_time"], utc=True))
                          .set_index("t")["open"] for s in cols}).reindex(G)
    o1, o2 = opens.shift(-1).to_numpy(), opens.shift(-2).to_numpy()
    sig = opens.pct_change().rolling(60 * PD, min_periods=20 * PD).std().to_numpy()
    fund = np.column_stack([er.funding_at_bar_open(s, G).shift(-2).fillna(0.0).to_numpy() for s in cols])
    C, O = v169.minute_cube(G, cols)
    path = C[:, 16:239, :] / o1[:, None, :] - 1  # minutes 16..238
    out = {}
    for k in KGRID:
        thr = -k * sig
        hit = path <= thr[:, None, :]
        anyhit = hit.any(axis=1)
        first = np.argmax(hit, axis=1) + 16
        ii, jj = np.nonzero(anyhit & np.isfinite(o2) & np.isfinite(thr))
        entry = O[ii, first[ii, jj] + 1, jj] * (1 + SLIP)
        exitp = o2[ii, jj] * (1 - SLIP)
        r = np.zeros(C.shape[0:1] + (len(cols),))
        ok = np.isfinite(entry) & np.isfinite(exitp)
        r[ii[ok], jj[ok]] = exitp[ok] / entry[ok] - 1 - 2 * TAKER - fund[ii[ok], jj[ok]]
        ev = np.zeros_like(r, dtype=bool)
        ev[ii[ok], jj[ok]] = True
        out[k] = (r, ev)
    return out


def sleeve_walk_forward(G, ev_ret):
    sleeve = pd.Series(0.0, index=G)
    events = pd.Series(0, index=G)
    chosen = {}
    for a in ANCHORS:
        a0 = pd.Timestamp(a, tz="UTC")
        tr = np.asarray((G >= START + pd.Timedelta(days=30)) & (G <= a0 - pd.Timedelta(days=1)))

        def sharpe(k):
            x = SIZE * ev_ret[k][0][tr].sum(axis=1)
            return x.mean() / x.std() if x.std() > 0 else -9

        k = max(KGRID, key=sharpe)
        chosen[a] = {"k": k, "train_sharpe_per_bar": round(float(sharpe(k)), 4)}
        te = np.asarray((G >= a0) & (G < a0 + pd.Timedelta(days=365)))
        sleeve[te] = SIZE * ev_ret[k][0][te].sum(axis=1)
        events[te] = ev_ret[k][1][te].sum(axis=1)
    return sleeve, events, chosen


def run_combined(books, ctx, sleeve, target=0.25):
    idx, B, cols = books.index, books.to_numpy(), list(books.columns)
    r_next, lo, hi, fund = ctx["mkt"]
    fee_b, rel_b, fee_s, rel_s = ctx["exec"]
    carry, expo = ctx["carry_real"]
    o = ctx["opens"].reindex(idx)[cols]
    sl = sleeve.reindex(idx).fillna(0.0).to_numpy()
    realized = v99.W_BOOKS * (books.shift(2) * (o / o.shift(1) - 1)).sum(axis=1) + v99.W_CARRY * v99.CARRY_LEV * pd.Series(carry, index=idx).shift(1)
    vol = (realized.rolling(60 * PD, min_periods=20 * PD).std() * np.sqrt(PD * 365)).to_numpy()
    s = np.where(np.isnan(vol), 1.0, np.minimum(target / np.where(np.isnan(vol), 1.0, vol), v99.CAP))
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
        net[i] = (w * r_next[i]).sum() - ex - (w * fund[i]).sum() + c * carry[i] - cc + (g[i] * sl[i] if live[i] else 0.0)
        eq[i] = (eq[i - 1] if i else 1.0) * (1 + net[i])
        prev_w, prev_c = w, c
    return v110.summarize(pd.Series(net, index=idx), pd.Series(turn, index=idx), pd.Series(g, index=idx)), pd.Series(net, index=idx)


def main():
    books, opens = er.v154_books()
    cols = list(books.columns)
    G = pd.date_range(START, books.index.max(), freq="4h")
    ev = event_returns(G, cols)
    sleeve, events, chosen = sleeve_walk_forward(G, ev)
    print("chosen k", chosen, flush=True)
    ctx = er.context(books, opens)
    base, base_net = run_combined(books, ctx, sleeve * 0.0)
    comb, _ = run_combined(books, ctx, sleeve)
    alone = []
    for a in ANCHORS:
        a0 = pd.Timestamp(a, tz="UTC")
        mk = (sleeve.index >= a0) & (sleeve.index < a0 + pd.Timedelta(days=365))
        x = sleeve[mk]
        eqs = (1 + x).cumprod()
        e = events[mk]
        hits = float((x[e > 0] > 0).mean()) if (e > 0).any() else None
        alone.append(dict(anchor=a, k=chosen[a]["k"], net_pct=round(100 * float(eqs.iloc[-1] - 1), 2),
                          dd_pct=round(100 * float((1 - eqs / eqs.cummax()).max()), 2), events=int(e.sum()), hit_rate_bars=hits))
    live = (sleeve.index >= v110.START) & (sleeve.index < v110.END)
    d_s = sleeve[live].groupby(sleeve[live].index.floor("D")).sum()
    d_b = base_net.groupby(base_net.index.floor("D")).sum().reindex(d_s.index)
    out = {"version": "v171", "chosen": chosen, "sleeve_alone": alone,
           "corr_daily_sleeve_vs_v154": round(float(d_s.corr(d_b)), 3),
           "baseline_v154_engine_real": base, "primary_v154_plus_sleeve": comb,
           "reference_engine_real_v154": {"monthly_pct": 3.708, "full_path_dd": 18.87}}
    for k in ("baseline_v154_engine_real", "primary_v154_plus_sleeve"):
        r = out[k]
        print(k, r["monthly_pct"], "fullDD", r["full_path_dd"], [(y["anchor"][:4], y["net_pct"], y["max_drawdown_percent"]) for y in r["yearly"]], flush=True)
    print("sleeve alone", alone, "corr", out["corr_daily_sleeve_vs_v154"], flush=True)
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v171_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
