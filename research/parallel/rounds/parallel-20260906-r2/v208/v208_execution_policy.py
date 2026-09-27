"""v208: execution policy for the v205 books - volatility-scaled limit, market on strong opens, no-trade band (registry v208).

Why (user, 2026-09-27): every book order of v205 is a limit exactly 0.10% better than the 4h open, rebalanced every bar
(e.g. 162 small fills in one BTC position). The user wants the pipeline to choose a real limit price, to go market when
urgency pays for the taker fee, and to stop churning tiny rebalances.

Fixed before running (constants chosen a priori, never tuned; everything else = v205: ensemble books 0.5 annual +
0.5 quarterly v151, aligned sleeve x1.5/x0.5, engine_user after the v188 fix, Bybit fees maker 0.02% / taker 0.055%,
adverse funding, 1m execution, limit resting minutes 2..238, unfilled limits expire):
  ref_v205                  the v205 pipeline (limit = open -/+ 0.10%); must reproduce dev4 5.824.
  A_vol_limit               limit offset = max(0.10%, 0.25 * sigma_4h), sigma_4h = std of 4h open-to-open returns over
                            the last 360 bars (known at the decision).
  B_market_on_open          A, but a MARKET order at the holding bar's minute-0 open (taker) when the order opens a
                            position from flat (|w| < 0.5% equity) or flips its side AND |target| >= 10% equity.
  C_market_open_band        B plus a no-trade band: a same-side rebalance is skipped when |change| < max(2% equity,
                            25% of |target|); closing to zero and flips are always sent.
Causality: sigma_4h, the current weight w and the target are all known at the decision (close of bar t); orders act in
bar t+1 only. No statistic of any test year feeds a choice.
SELECTION = robust criterion (AGENTS.md): among rows with gate DD <= 20% and no losing year in the first four anchors,
prefer dev4 mean >= 5%/month, then the highest worst dev year (monthly), ties -> higher mean. If ref_v205 is selected
the direction is rejected. Only the selected row's most recent year is the one-time final score.
Diagnostics: fills, unfilled limits, market orders, skipped rebalances, fees, mean limit offset.

  python research/parallel/rounds/parallel-20260906-r2/v208/v208_execution_policy.py
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


eu = _load("engine_user", HERE.parent / "engine_user/engine_user.py")
v204 = _load("v204", HERE.parent / "v204/v204_sleeve_book_alignment.py")

K_SIGMA, MIN_OFF = 0.25, 0.001
URGENT_TARGET, FLAT = 0.10, 0.005
BAND_ABS, BAND_REL = 0.02, 0.25


def vol_offset(s4):
    return max(MIN_OFF, K_SIGMA * s4) if np.isfinite(s4) else MIN_OFF


def policy_a(i, a, dw, w, tgt, s4):
    return "limit", vol_offset(s4)


def _opening(w, tgt):
    return (abs(w) < FLAT and abs(tgt) >= FLAT) or (np.sign(w) != np.sign(tgt) and abs(w) >= FLAT and abs(tgt) >= FLAT)


def policy_b(i, a, dw, w, tgt, s4):
    if _opening(w, tgt) and abs(tgt) >= URGENT_TARGET:
        return "market", 0.0
    return policy_a(i, a, dw, w, tgt, s4)


def policy_c(i, a, dw, w, tgt, s4):
    closing = abs(tgt) < 1e-12 and abs(w) > 0
    if not closing and not _opening(w, tgt) and abs(dw) < max(BAND_ABS, BAND_REL * abs(tgt)):
        return "skip", 0.0
    return policy_b(i, a, dw, w, tgt, s4)


def main():
    books154, opens = eu.er.v154_books()
    cols = list(books154.columns)
    mem = pd.read_parquet(eu.er.CACHE / "members_v154.parquet")
    A, B = (mem.xs(k, axis=1, level=0).reindex(books154.index).fillna(0.0)[cols] for k in ("A", "B"))
    mq = pd.read_parquet(eu.er.CACHE / "members_quarterly.parquet")
    Aq, Bq = (mq.xs(k, axis=1, level=0).reindex(books154.index).fillna(0.0)[cols] for k in ("A", "B"))
    books = 0.5 * (A + B) / 2 + 0.5 * (Aq + Bq) / 2
    prep = eu.prepare(books154, opens)
    kw = dict(m_sl=4.0, m_sleeve_sl=5.0, sleeve=True, d_limit=0.001, win_end=239, sleeve_risk_budget=0.12, size_mult=1.5, align=(1.5, 0.5))
    out = {"version": "v208", "criterion": "robust worst-year (AGENTS.md)", "constants": dict(
        K_SIGMA=K_SIGMA, MIN_OFF=MIN_OFF, URGENT_TARGET=URGENT_TARGET, FLAT=FLAT, BAND_ABS=BAND_ABS, BAND_REL=BAND_REL), "rows": {}}
    for key, pol in (("ref_v205", None), ("A_vol_limit", policy_a), ("B_market_on_open", policy_b), ("C_market_open_band", policy_c)):
        r = eu.simulate(books, opens, prep, exec_policy=pol, **kw)
        r["worst_dev_month_pct"] = round(v204.worst_month(r), 3)
        st = r["stats"]
        if pol is not None and st["fills"] - st.get("market", 0) > 0:
            st["mean_limit_offset_pct"] = round(100 * st["limit_offset_sum"] / (st["fills"] - st["market"]), 4)
        out["rows"][key] = r
        print(key, "dev4", r["monthly_dev4"], "worst", r["worst_dev_month_pct"], "gateDD", r["gate_dd"],
              "dev years", [(y["anchor"][:4], y["net_pct"]) for y in r["yearly"][:4]],
              "fills", st["fills"], "unfilled", st["unfilled"], "market", st.get("market"), "skipped", st.get("skipped"),
              "fees", st["fees"], "offset%", st.get("mean_limit_offset_pct"), flush=True)
        if key == "ref_v205":
            assert abs(r["monthly_dev4"] - 5.824) < 0.002, "reference must reproduce v205"
    sel = v204.robust_select(out["rows"])
    s = out["rows"][sel]
    out["selected"] = sel
    out["final_score_selected"] = {"monthly_5y": s["monthly_5y"], "monthly_last_year": s["monthly_last_year"],
                                   "losing_years": s["losing_years"], "gate_dd": s["gate_dd"], "gate_pass": s["gate_pass"],
                                   "yearly": [(y["anchor"][:4], y["net_pct"], y["dd_1m_pct"]) for y in s["yearly"]]}
    print("SELECTED", sel, out["final_score_selected"], flush=True)
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v208_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
