"""v338: MANUAL product + ONE human-placeable dip limit per coin (registry v338, registered before running).

Why: the user's MANUAL rule set (2026-09-28) allows, when flat, ONE resting limit order at a distance from the price, valid for a few hours, with
a stop-loss and take-profit attached; in a position, discrete limit adds. The BOT's dip LADDER (20 bids re-placed every 4h, bot-watched
5m-close stops) is not human-placeable, but a single deep limit buy per coin with exchange-native TP / SL attached at placement is: it is
the same kind of order as the v315 pullback entry, placed at the same moment (each 4h close, the plan lists price, size, TP, SL).
MANUAL-FEASIBLE DIP (fixed before running):
  - one rung per coin at depth k sigma_4h below the 4h open (the R2 sizing: per-rung size of the R2 sleeve, align (1.5, 0.5), size_mult 1.75,
    R2 dip agents' size / take-profit read at the BAR OPEN from the audited v306 gene tables, fit "U", up 2.0 x1.5 / down 0.0 x0.5, tp_margin 0.001);
  - placed by a human: fills only from minute 16 of the bar (sleeve_start 16 = the R2 / legacy window, ~15 min reaction), on a 1m trade-through;
  - the stop is EXCHANGE-NATIVE (attached to the order): touch stop at 8 sigma below the fill level (sleeve_stop_mode "touch", m_sleeve_sl 8);
    no bot-watched close stop; the risk budget 0.26 counts the 8-sigma stop distance (honest risk);
  - take-profit limit attached (maker); a rung still open at the bar end is closed at the next 4h open (taker) - the human closes it at the next
    check (approximation: a 15-min-late close is modelled at the open; labelled);
  - needs hedge mode (or a sub-account) on the exchange so a dip buy does not net against a book short.
ROWS: M2 = MANUAL reference (2A + 2PT + D)/5, pullback 0.75 sigma / 3 bars, target 0.25, cap 2 (dev4 3.011)
      MD30 = M2 + single dip at 3.0 sigma | MD35 = M2 + single dip at 3.5 sigma
FITNESS: v310 MANUAL fitness (fitness / fitness_pooled) with the book win rate replaced by the win rate of ALL trades the human places
(book trades + dip fills). CHOICE: dev folds k = 2, 3 on years [:k]; TRANSFER if a dip row is chosen and beats M2 on the unseen dev year in both
folds. Final choice on dev4; the most recent year computed once for it. Stress rows for the final (reported, never chosen on): sleeve_start 31
(30-min reaction) and cost stress is not re-run here.
Contaminated by design (the R2 agents / M2 mix were built after earlier looks at the most recent year): prospective paper log = clean evidence.

  python research/parallel/rounds/parallel-20260906-r2/v338/v338_manual_single_dip.py
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
RD = HERE.parent
C = Path("artifacts/research/engine_real")
U = (2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0)
R2_AGENT = dict(fit="U", up_th=2.0, up_mult=1.5, dn_th=0.0, dn_mult=0.5, tp_margin=0.001)
DIP = dict(MD30=3.0, MD35=3.5)


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    logf = (HERE / "run_detail.log").open("a")

    def log(s):
        print(s, flush=True)
        logf.write(s + "\n"); logf.flush()

    v306 = _load("v306_md", RD / "v306/v306_walkforward_evolution.py")
    v306.init_worker()
    T = v306.W["T"]
    v310 = _load("v310_md", RD / "v310/v310_manual_book_robust_evolution.py")
    v315 = _load("v315_md", RD / "v315/v315_manual_pullback_entry.py")
    v310.init_worker()
    W0 = v310.W
    idx, cols = W0["idx"], W0["cols"]
    assert list(v306.W["idx"]) == list(idx) and list(v306.W["cols"]) == list(cols)
    v306.W.update(T=T)
    rd = lambda f: pd.read_parquet(C / f).reindex(idx).ffill().fillna(0.0)[cols].to_numpy(float)
    PT = (rd("member_PT_pooledtv.parquet") + rd("member_PTq_pooledtv.parquet")) / 2
    A, D = W0["grp"]["wA"].copy(), W0["grp"]["wD"].copy()
    M2 = (2 * A + 2 * PT + D) / 5
    size, tp = v306._tables(R2_AGENT)
    eu = W0["eu"]
    sim0 = eu.simulate
    base_p9 = v310._policy9

    def run(row, full=False, sleeve_start=16):
        W0["grp"]["wA"] = W0["grp"]["wB"] = W0["grp"]["wD"] = M2
        v310._policy9 = v315.with_entry(0.75)
        v315.BASE_P9 = base_p9
        if row in DIP:
            ku = U.index(DIP[row])

            def sim(*a, **kw):
                kw.update(sleeve=True, rungs=(DIP[row],), sleeve_stop_mode="touch", m_sleeve_sl=8.0, sleeve_risk_budget=0.26, size_mult=1.75,
                          align=(1.5, 0.5), sleeve_start=sleeve_start,
                          sleeve_fill_size=lambda i, aa, r, f: float(size[i, aa, ku]), sleeve_tp=lambda i, aa, r, f: float(tp[i, aa, ku]))
                ev = kw.get("events")
                out = sim0(*a, **kw)
                rows = v306._trade_rows(ev)
                for y in range(5):
                    a0 = W0["anchors"][y]
                    rg = [x[2] for x in rows if x[0] == "rung" and a0 <= x[1] < a0 + pd.Timedelta(days=365)]
                    RUNG[y] = (len(rg), int(sum(v > 0 for v in rg)))
                return out
            eu.simulate = sim
        RUNG = {}
        try:
            res = v310.run_genome(v310.encode(dict(target=0.25, cap=2.0, n_valid=3)), full)
        finally:
            eu.simulate = sim0
            v310._policy9 = base_p9
        for y, yy in enumerate(res["years"]):
            if y in RUNG:
                yy["n_rung"], yy["w_rung"] = RUNG[y]
        return res

    def fit_all(res, ys):
        """v310 fitness with the all-trade win rate in place of the book win rate."""
        r2 = json.loads(json.dumps(res))
        for yy in r2["years"]:
            yy["n_book"], yy["w_book"] = yy["n_book"] + yy["n_rung"], yy["w_book"] + yy["w_rung"]
            yy["n_rung"] = yy["w_rung"] = 0
        return v310.fitness(r2, ys)

    res = {k: run(k) for k in ("M2", *DIP)}
    assert abs(v310.metrics(res["M2"], [0, 1, 2, 3])["R"] - 3.011) < 0.003
    out = {"version": "v338", "rows": {k: dict(dev4=v310.metrics(r, [0, 1, 2, 3]), F=round(fit_all(r, [0, 1, 2, 3]), 4),
                                               years=[v310.metrics(r, [y]) for y in range(4)]) for k, r in res.items()}, "folds": {}}
    for k, v in out["rows"].items():
        log(f"{k} dev4 {v['dev4']} F {v['F']}")
    gains = []
    for k in (2, 3):
        ys = list(range(k))
        ch = max(res, key=lambda x: fit_all(res[x], ys))
        f_ch, f0 = fit_all(res[ch], [k]), fit_all(res["M2"], [k])
        out["folds"][k] = dict(choice=ch, test=v310.metrics(res[ch], [k]), F_test=round(f_ch, 4), F_M2=round(f0, 4))
        gains.append(ch in DIP and f_ch > f0)
        log(f"FOLD {k} choice {ch} TEST {out['folds'][k]['test']} F {f_ch:.4f} vs M2 {f0:.4f}")
    out["transfer"] = dict(holds=bool(all(gains)))
    log(f"TRANSFER {out['transfer']}")
    ch = max(res, key=lambda x: fit_all(res[x], [0, 1, 2, 3]))
    full = run(ch, True)
    out["final"] = dict(choice=ch, dev4=v310.metrics(res[ch], [0, 1, 2, 3]), last_year=v310.metrics(full, [4]), five_years=v310.metrics(full, [0, 1, 2, 3, 4]),
                        full={q: full[q] for q in ("monthly_5y", "monthly_last_year", "gate_dd", "losing_years")})
    if ch in DIP:
        late = run(ch, True, sleeve_start=31)
        out["final"]["stress_start31"] = dict(dev4=v310.metrics(late, [0, 1, 2, 3]), last_year=v310.metrics(late, [4]),
                                              full={q: late[q] for q in ("monthly_5y", "monthly_last_year", "gate_dd", "losing_years")})
    log(f"FINAL {json.dumps(out['final'], default=str)}")
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v338_result.json").write_text(raw)
    log("sha256 " + hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
