"""engine_real: evaluation engine closer to live Binance trading (infrastructure, not a model hypothesis).

User request (2026-09-26): "cơ chế đánh giá pipeline phải làm sao cho khớp với thực tế nhất". Same books, same v144
sequential loop (v135 10 bps limit on 1m data: maker 0.0002 on trade-through in minutes 2..14, else taker 0.0005 at
minute 15 + 2 bps; v110 governor on the 90-day peak lagged 2 bars; vol target, cap 2x; 0.8 books + 0.2 carry x3), with
these realism changes, all fixed before running (no parameter is chosen on results):
  R1 funding: actual signed Binance USD-M funding per symbol (data/raw/xs_universe_20260924/<SYM>_funding.parquet) at
     each settlement. A settlement at time T is paid/received by the position held at T; a decision at bar close t is
     filled during bar t+1 (minutes 0..15), so it is held at the bar-open settlement of bar t+2, not t+1. Longs pay
     positive rates, shorts receive them (and pay negative rates). Replaces "longs 0.01%/8h flat, shorts zero".
  R2 carry sleeve rebuilt with real fees and timing: spot taker 0.001 + perp taker 0.0005 per leg switch (was 0.0004
     per leg), funding received at the t+2 settlement (was t+1); parameters still chosen per anchor on pre-anchor data
     by Sharpe (scripts/carry_lab.py GRID); capital 1.2 per unit notional. Sleeve size changes cost the same per leg on
     the notional that is currently on.
  R3 capital budget (classic account: spot paid in cash, USD-M margin at 1/5 of perp gross, 5% buffer):
     carry capital in use (c * exposure) + directional perp gross / 5 <= 0.95 of equity; carry is cut first, then books.
  R4 minimum order notional at a 10,000 USDT account (BTC 100, ETH 20, others 5 USDT): a weight change smaller than the
     minimum is not sent (the symbol keeps its previous weight), unless it closes the position.
  R5 intrabar drawdown: conservative bound that marks every held position at its adverse 4h extreme of the holding bar
     (all assets at their worst simultaneously); reported next to the close-sampled full-path DD.
Reported per row: monthly %, yearly net/DD, full-path DD, intrabar DD bound, gross, fees+slippage, funding, carry, net,
turnover, and an ablation (each realism change alone on top of the v144 engine) so its cost is visible.

  python research/parallel/rounds/parallel-20260906-r2/engine_real/engine_real.py            # v154 books
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parents[4]
CACHE = ROOT / "artifacts/research/engine_real"
XS = ROOT / "data/raw/xs_universe_20260924"
SP = ROOT / "data/raw/spot_majors_20260925"
SPOT_FEE, PERP_TAKER, CARRY_CAPITAL = 0.001, 0.0005, 1.2
MARGIN, BUFFER = 5.0, 0.95
ACCOUNT_USDT = 10_000.0
MIN_NOTIONAL = {"BTCUSDT": 100.0, "ETHUSDT": 20.0}
FULL = dict(funding=True, carry=True, budget=True, min_notional=True)
NONE = dict(funding=False, carry=False, budget=False, min_notional=False)


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


v144 = _load("v144", HERE.parent / "v144/v144_deploy_v3.py")
carry_lab = _load("carry_lab", ROOT / "scripts/carry_lab.py")
v99, v110, v135, v92 = v144.v99, v144.v110, v144.v135, v144.v110.v92
PD, D = v144.PD, v144.D


def funding_at_bar_open(sym, idx):
    """Sum of funding rates settled at each bar open (settlements floored to the 4h grid)."""
    f = pd.read_parquet(XS / f"{sym}_funding.parquet")
    t = pd.to_datetime(f["fundingTime"], utc=True).dt.floor("4h")
    return f.groupby(t)["fundingRate"].sum().reindex(idx).fillna(0.0)


def carry_real(idx):
    """Carry sleeve return per unit capital and mean exposure, rebuilt with real fees and t+2 funding timing."""
    rets, expo = {}, {}
    for sym in carry_lab.SYMS:
        d = carry_lab.load(sym)
        po, so = d["po"], d["so"]
        rp, rs = po.shift(-2) / po.shift(-1) - 1, so.shift(-2) / so.shift(-1) - 1
        fund = d["rate"].shift(-2)

        def ret(pos):
            cost = pos.diff().abs().fillna(pos.iloc[0]) * (SPOT_FEE + PERP_TAKER)
            return ((pos * (fund + rs - rp) - cost) / CARRY_CAPITAL).fillna(0.0)

        cache = {json.dumps(q): carry_lab.position(d, q) for q in carry_lab.GRID}
        r_parts, e_parts = [], []
        for anchor in carry_lab.ANCHORS:
            a = pd.Timestamp(anchor, tz="UTC")
            s0, s1 = d["idx"][0] + pd.Timedelta(days=30), a - pd.Timedelta(days=carry_lab.EMBARGO_DAYS)

            def score(q):
                r = ret(cache[json.dumps(q)])
                r = r[(r.index >= s0) & (r.index <= s1)]
                return r.mean() / r.std() if r.std() > 0 else -9

            best = max(carry_lab.GRID, key=score)
            pos = cache[json.dumps(best)]
            mk = (pos.index >= a) & (pos.index < a + pd.Timedelta(days=365))
            r_parts.append(ret(pos)[mk])
            e_parts.append(pos[mk])
        rets[sym], expo[sym] = pd.concat(r_parts), pd.concat(e_parts)
    r = pd.DataFrame(rets).reindex(idx).fillna(0.0).mean(axis=1)
    e = pd.DataFrame(expo).reindex(idx).fillna(0.0).mean(axis=1)
    return r.to_numpy(), e.to_numpy()


def market(opens, idx, cols):
    """Per-bar arrays: next-bar returns, adverse extremes of the holding bar, funding paid at the t+2 settlement."""
    o = opens.reindex(idx)[cols]
    r_next = (o.shift(-2) / o.shift(-1) - 1).fillna(0.0).to_numpy()
    lo, hi, fund = np.zeros(o.shape), np.zeros(o.shape), np.zeros(o.shape)
    for j, s in enumerate(cols):
        k = pd.read_parquet(XS / f"{s}_4h.parquet")
        k.index = pd.to_datetime(k["open_time"], utc=True)
        k = k.reindex(idx)
        base = o[s].shift(-1)
        lo[:, j] = (k["low"].shift(-1) / base - 1).fillna(0.0).to_numpy()
        hi[:, j] = (k["high"].shift(-1) / base - 1).fillna(0.0).to_numpy()
        fund[:, j] = funding_at_bar_open(s, idx).shift(-2).fillna(0.0).to_numpy()
    return r_next, lo, hi, fund


def exec_costs(idx, cols):
    """v144 execution: fee and price offset per buy/sell for the fill during bar t+1 (unchanged)."""
    st = {s: v135.bar_stats(s).reindex(idx + pd.Timedelta(hours=4)).set_axis(idx) for s in cols}
    fee_b, rel_b, fee_s, rel_s = (np.zeros((len(idx), len(cols))) for _ in range(4))
    for j, s in enumerate(cols):
        p0, lo_, hi_, p15 = st[s]["p0"].to_numpy(), st[s]["lo"].to_numpy(), st[s]["hi"].to_numpy(), st[s]["p15"].to_numpy()
        have = ~np.isnan(p0)
        p15 = np.where(np.isnan(p15), p0, p15)
        mv = np.where(have, p15 / np.where(have, p0, 1.0) - 1, 0.0)
        fb, fs = have & (lo_ < p0 * (1 - D)), have & (hi_ > p0 * (1 + D))
        fee_b[:, j], rel_b[:, j] = np.where(fb, 0.0002, 0.0005), np.where(fb, -D, mv + 0.0002)
        fee_s[:, j], rel_s[:, j] = np.where(fs, 0.0002, 0.0005), np.where(fs, D, mv - 0.0002)
    return fee_b, rel_b, fee_s, rel_s


def run(books, ctx, target, gov, real):
    idx, B, cols = books.index, books.to_numpy(), list(books.columns)
    r_next, lo, hi, fund = ctx["mkt"]
    fee_b, rel_b, fee_s, rel_s = ctx["exec"]
    carry, expo = ctx["carry_real"] if real["carry"] else (ctx["carry_old"], np.ones(len(idx)))
    o = ctx["opens"].reindex(idx)[cols]
    realized = v99.W_BOOKS * (books.shift(2) * (o / o.shift(1) - 1)).sum(axis=1) + v99.W_CARRY * v99.CARRY_LEV * pd.Series(carry, index=idx).shift(1)
    vol = (realized.rolling(60 * PD, min_periods=20 * PD).std() * np.sqrt(PD * 365)).to_numpy()
    s = np.where(np.isnan(vol), 1.0, np.minimum(target / np.where(np.isnan(vol), 1.0, vol), v99.CAP))
    live = np.asarray((idx >= v110.START) & (idx < v110.END))
    mins = np.array([MIN_NOTIONAL.get(c, 5.0) for c in cols])
    n = len(idx)
    net, turn, g, eq, eq_lo = np.zeros(n), np.zeros(n), np.ones(n), np.ones(n), np.ones(n)
    parts = {k: np.zeros(n) for k in ("gross", "exec", "funding", "carry", "carry_cost")}
    budget_cut = np.zeros(n)
    prev_w, prev_c = np.zeros(len(cols)), 0.0
    for i in range(n):
        if gov and i >= 2:
            j = i - 2
            peak = eq[max(0, j - 90 * PD + 1): j + 1].max()
            g[i] = float(np.clip((0.20 - (1 - eq[j] / peak)) / 0.10, 0.0, 1.0))
        w = v99.W_BOOKS * s[i] * B[i] * g[i] if live[i] else np.zeros(len(cols))
        c = v99.W_CARRY * v99.CARRY_LEV * s[i] * g[i] if live[i] else 0.0
        if real["budget"]:
            used = c * expo[i] + np.abs(w).sum() / MARGIN
            if used > BUFFER:
                c_max = max(0.0, (BUFFER - np.abs(w).sum() / MARGIN) / max(expo[i], 1e-9))
                budget_cut[i] = 1.0
                if c > c_max:
                    c = c_max
                if np.abs(w).sum() / MARGIN > BUFFER:
                    w = w * BUFFER * MARGIN / np.abs(w).sum()
        if real["min_notional"]:
            eq_usdt = ACCOUNT_USDT * (eq[i - 1] if i else 1.0)
            small = (np.abs(w - prev_w) * eq_usdt < mins) & (w != 0)
            w = np.where(small, prev_w, w)
        dw = w - prev_w
        buy = dw > 0
        parts["exec"][i] = np.sum(np.abs(dw) * np.where(buy, fee_b[i], fee_s[i]) + dw * np.where(buy, rel_b[i], rel_s[i]))
        turn[i] = np.abs(dw).sum()
        parts["gross"][i] = (w * r_next[i]).sum()
        parts["funding"][i] = -(w * fund[i]).sum() if real["funding"] else -np.clip(w, 0, None).sum() * 0.00005
        parts["carry"][i] = c * carry[i]
        parts["carry_cost"][i] = (abs(c - prev_c) / CARRY_CAPITAL * expo[i] * (SPOT_FEE + PERP_TAKER) if real["carry"]
                                  else abs(c - prev_c) * 2 * 0.0004 / 1.2)
        net[i] = parts["gross"][i] - parts["exec"][i] + parts["funding"][i] + parts["carry"][i] - parts["carry_cost"][i]
        prev_eq = eq[i - 1] if i else 1.0
        eq[i] = prev_eq * (1 + net[i])
        adverse = np.where(w > 0, w * lo[i], w * hi[i]).sum()
        eq_lo[i] = prev_eq * (1 + adverse - parts["exec"][i] + min(parts["funding"][i], 0.0))
        prev_w, prev_c = w, c
    out = v110.summarize(pd.Series(net, index=idx), pd.Series(turn, index=idx), pd.Series(g, index=idx))
    full = np.asarray((idx >= v110.START) & (idx < v110.END))
    e, el = eq[full] / eq[full][0], eq_lo[full] / eq[full][0]
    out["intrabar_dd_bound"] = round(100 * float(np.max(1 - el / np.maximum.accumulate(e))), 2)
    out["components_pct_of_start_equity_sum"] = {k: round(100 * float(v[full].sum()), 2) for k, v in parts.items()}
    out["budget_binding_share"] = round(float(budget_cut[full].mean()), 3)
    out["mean_scale"] = round(float(np.mean(np.where(live, s, np.nan)[full])), 3)
    return out


def context(books, opens):
    idx, cols = books.index, list(books.columns)
    carry_old = pd.read_parquet(ROOT / "artifacts/research/carry/carry_oos_fee0.0004.parquet")["carry"].reindex(idx).fillna(0.0).to_numpy()
    return dict(opens=opens, mkt=market(opens, idx, cols), exec=exec_costs(idx, cols), carry_old=carry_old,
                carry_real=carry_real(idx))


def evaluate(books, opens, target=0.25, gov=True, ablation=True):
    ctx = context(books, opens)
    res = {"v144_engine": run(books, ctx, target, gov, NONE), "engine_real": run(books, ctx, target, gov, FULL)}
    if ablation:
        for k in FULL:
            res[f"only_{k}"] = run(books, ctx, target, gov, {**NONE, k: True})
    for k, r in res.items():
        print(k, r["monthly_pct"], "fullDD", r["full_path_dd"], "intrabarDD", r["intrabar_dd_bound"],
              r["components_pct_of_start_equity_sum"], "budget", r["budget_binding_share"], flush=True)
    return res


def v154_books():
    CACHE.mkdir(parents=True, exist_ok=True)
    bp, op = CACHE / "books_v154.parquet", CACHE / "opens_v154.parquet"
    if bp.exists() and op.exists():
        return pd.read_parquet(bp), pd.read_parquet(op)
    v151 = _load("v151", HERE.parent / "v151/v151_info_ensemble.py")
    v154 = _load("v154", HERE.parent / "v154/v154_ensemble_coinbase.py")
    p103, A = v144.books_v142()
    _, Bk = v151.books_with_options()
    _, Dk = v154.books_coinbase()
    idx = A.index.union(Bk.index).union(Dk.index)
    books = (A.reindex(idx).fillna(0.0) + Bk.reindex(idx).fillna(0.0) + Dk.reindex(idx).fillna(0.0)) / 3
    opens = p103.pivot_table(index="t", columns="sym", values="open")
    books.to_parquet(bp)
    opens.to_parquet(op)
    return books, opens


def main():
    books, opens = v154_books()
    out = {"engine": "engine_real", "books": "v154 (A+B+D)/3", "target": 0.25, "governor": True,
           "reference_v154": {"monthly_pct": 3.515, "full_path_dd": 19.15}, "rows": evaluate(books, opens)}
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "engine_real_v154_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    sys.exit(main())
