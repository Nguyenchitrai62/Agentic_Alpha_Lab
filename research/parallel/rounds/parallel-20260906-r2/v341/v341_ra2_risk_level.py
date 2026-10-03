"""v341: overall RISK LEVEL of the reallocated MANUAL design RA2 (registry v341, registered before running; parent v340).

v340 RA2 (M2 book x0.75 + one native-bracket dip limit per coin at 3.0 sigma, dip size_mult 4.375) transferred on both dev folds: dev4 4.551, worst
dev year 1.733, dev DD 16.0; 5y 4.386, last year 3.725, gate DD 16.0 - DD headroom to the 20% floor. The engine's vol-scaling target scales BOTH the
book and the dip sizes (s = min(target / vol, cap)); cap stays 2 (AGENTS baseline; v314 showed caps > 2 do not generalise). Rows (fixed before running):
  RA2  = v340 RA2 (reference; target 0.25)
  RT28 = RA2 at target 0.28
  RT31 = RA2 at target 0.31
Fitness / protocol as v338-v340 (v310 MANUAL fitness with the all-trade win rate - it rewards return only up to 5 %/month and penalises DD > 20):
dev folds k = 2, 3 on years [:k]; TRANSFER if RT28 / RT31 is chosen and beats RA2 on the unseen dev year in both folds; final choice on dev4; most
recent year once; stress row sleeve_start 31. Contaminated by design; prospective paper log = clean evidence.

  python research/parallel/rounds/parallel-20260906-r2/v341/v341_ra2_risk_level.py
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
DIP = dict(RA2=(3.0, 4.375, 0.75, 0.25), RT28=(3.0, 4.375, 0.75, 0.28), RT31=(3.0, 4.375, 0.75, 0.31))


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

    v306 = _load("v306_rt", RD / "v306/v306_walkforward_evolution.py")
    v306.init_worker()
    T = v306.W["T"]
    v310 = _load("v310_rt", RD / "v310/v310_manual_book_robust_evolution.py")
    v315 = _load("v315_rt", RD / "v315/v315_manual_pullback_entry.py")
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
            depth, smult, bmult, tgt = DIP[row]
            ku = U.index(depth)

            def sim(*a, **kw):
                kw.update(sleeve=True, rungs=(depth,), sleeve_stop_mode="touch", m_sleeve_sl=8.0, sleeve_risk_budget=0.26, size_mult=smult,
                          align=(1.5, 0.5), sleeve_start=sleeve_start,
                          sleeve_fill_size=lambda i, aa, r, f: float(size[i, aa, ku]), sleeve_tp=lambda i, aa, r, f: float(tp[i, aa, ku]))
                kw["target"] = tgt
                if bmult != 1.0:
                    kw["trade"] = dict(kw["trade"], book_mult=bmult)
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

    res = {k: run(k) for k in DIP}
    assert abs(v310.metrics(res["RA2"], [0, 1, 2, 3])["R"] - 4.551) < 0.003
    out = {"version": "v341", "rows": {k: dict(dev4=v310.metrics(r, [0, 1, 2, 3]), F=round(fit_all(r, [0, 1, 2, 3]), 4),
                                               years=[v310.metrics(r, [y]) for y in range(4)]) for k, r in res.items()}, "folds": {}}
    for k, v in out["rows"].items():
        log(f"{k} dev4 {v['dev4']} F {v['F']}")
    gains = []
    for k in (2, 3):
        ys = list(range(k))
        ch = max(res, key=lambda x: fit_all(res[x], ys))
        f_ch, f0 = fit_all(res[ch], [k]), fit_all(res["RA2"], [k])
        out["folds"][k] = dict(choice=ch, test=v310.metrics(res[ch], [k]), F_test=round(f_ch, 4), F_RA2=round(f0, 4))
        gains.append(ch != "RA2" and f_ch > f0)
        log(f"FOLD {k} choice {ch} TEST {out['folds'][k]['test']} F {f_ch:.4f} vs RA2 {f0:.4f}")
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
    (HERE / "v341_result.json").write_text(raw)
    log("sha256 " + hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
