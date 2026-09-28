"""v227: allocate the dip sleeve across coins by their own recent dip-bid results (multi-armed bandit, causal) (registry v227).

Why: in the first four years the D2 dip bids differ by coin (avg net per bid: XRP +0.38%, SOL +0.52%, ETH +0.27%, BTC +0.21%, BNB +0.08%
with losses in 2021-2022). A trader shifts the dip budget toward the markets where dip buying has been working. The result of a standard
dip bid can be computed from market data alone (did the price reach the level, then TP / SL / next open), so the allocation may use the
outcomes of every standard bid that exited before the decision - no leakage.
Fixed before running (everything else = v218 D2: v216 G2 grid trader, sleeve budget 0.15, rung x1.75, minute-5 rule, limits, SL market /
TP limit, governor, aligned sleeve, Bybit fees, adverse funding). Information = the bid outcomes of the unfiltered D2 run.
  Q1_no_bnb          no dip bids on BNBUSDT (LABEL: motivated by the first-four-year diagnostic above).
  Q2_coin_bandit     bid size x clip(ewma_coin / ewma_all, 0.5, 1.5); ewma = exponentially weighted mean of net bid returns with a
                     180-day half-life over bids that exited before the decision; x1 until a coin has 50 finished bids.
  Q3_coin_rung       as Q2 per (coin, rung) cell, 30 finished bids minimum.
Reference: v218_D2. SELECTION = robust criterion among Q1..Q3; the most recent year is scored once for the selected row.

  python research/parallel/rounds/parallel-20260906-r2/v227/v227_sleeve_coin_bandit.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


v220 = _load("v220", HERE.parent / "v220/v220_sleeve_bandit.py")
eu, v216, v204, v213 = v220.eu, v220.v216, v220.v204, v220.v213
KW = v220.KW
HALF = pd.Timedelta(days=180)


def main():
    books154, opens = eu.er.v154_books()
    cols = list(books154.columns)
    mem = pd.read_parquet(eu.er.CACHE / "members_v154.parquet")
    A, B = (mem.xs(k, axis=1, level=0).reindex(books154.index).fillna(0.0)[cols] for k in ("A", "B"))
    mq = pd.read_parquet(eu.er.CACHE / "members_quarterly.parquet")
    Aq, Bq = (mq.xs(k, axis=1, level=0).reindex(books154.index).fillna(0.0)[cols] for k in ("A", "B"))
    books = 0.5 * (A + B) / 2 + 0.5 * (Aq + Bq) / 2
    prep = eu.prepare(books154, opens)
    idx = books.index
    trade = dict(v216.GRID, policy=v216.grid_policy(0.03, 0.40))
    ev0 = []
    base = eu.simulate(books, opens, prep, trade=trade, win_start=5, events=ev0, **KW)
    assert abs(base["monthly_dev4"] - 5.261) < 0.002
    obs = v220.sleeve_outcomes(ev0, idx)  # (i, coin, rung, exit time, net return)
    obs.sort(key=lambda o: o[3])
    t_exit = np.array([o[3].value for o in obs])
    ret = np.array([o[4] for o in obs])
    coin = np.array([cols.index(o[1]) for o in obs])
    rung = np.array([o[2] for o in obs])
    lam = np.log(2) / HALF.value

    def ewma(mask, t_now):
        m = mask & (t_exit < t_now)
        if not m.any():
            return np.nan, 0
        w = np.exp(-lam * (t_now - t_exit[m]))
        return float((w * ret[m]).sum() / w.sum()), int(m.sum())

    def bandit(per_rung, min_n):
        cache = {}

        def flt(i, a, r):
            key = (i, a, r if per_rung else -1)
            if key not in cache:
                t_now = idx[i].value + 4 * 3600 * 10**9  # decision = close of bar i
                cell = (coin == a) & ((rung == r) if per_rung else True)
                mu, n = ewma(cell, t_now)
                mu_all, _ = ewma(np.ones(len(ret), bool), t_now)
                if n < min_n or not np.isfinite(mu) or not np.isfinite(mu_all) or mu_all <= 0:
                    cache[key] = 1.0
                else:
                    cache[key] = float(np.clip(mu / mu_all, 0.5, 1.5))
            return cache[key]
        return flt

    bnb = cols.index("BNBUSDT")
    runs = {"v218_D2": None, "Q1_no_bnb": (lambda i, a, r: 0.0 if a == bnb else 1.0), "Q2_coin_bandit": bandit(False, 50),
            "Q3_coin_rung": bandit(True, 30)}
    out = {"version": "v227", "rows": {}, "trades": {}}
    for key, flt in runs.items():
        ev = []
        r = eu.simulate(books, opens, prep, trade=trade, win_start=5, events=ev, sleeve_filter=flt, **KW)
        r["worst_dev_month_pct"] = round(v204.worst_month(r), 3)
        out["rows"][key], out["trades"][key] = r, v213.trade_stats(ev)
        print(key, "dev4", r["monthly_dev4"], "worst", r["worst_dev_month_pct"], "gateDD", r["gate_dd"],
              "dev years (net, dd1m)", [(y["anchor"][:4], y["net_pct"], y["dd_1m_pct"]) for y in r["yearly"][:4]], flush=True)
    cands = ("Q1_no_bnb", "Q2_coin_bandit", "Q3_coin_rung")
    sel = v204.robust_select({k: out["rows"][k] for k in cands})
    s = out["rows"][sel]
    out["selected"] = sel
    out["final_score_selected"] = {"monthly_5y": s["monthly_5y"], "monthly_last_year": s["monthly_last_year"],
                                   "losing_years": s["losing_years"], "gate_dd": s["gate_dd"], "gate_pass": s["gate_pass"],
                                   "yearly": [(y["anchor"][:4], y["net_pct"], y["dd_1m_pct"]) for y in s["yearly"]],
                                   "hidden_year_trades": out["trades"][sel]["_hidden"]}
    for k in out["trades"]:
        if k != sel:
            out["trades"][k].pop("_hidden", None)
    print("SELECTED", sel, out["final_score_selected"], flush=True)
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v227_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
