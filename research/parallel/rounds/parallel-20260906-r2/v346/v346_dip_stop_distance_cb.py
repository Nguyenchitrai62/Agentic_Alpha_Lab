"""v346: STOP DISTANCE of the two MANUAL bracket dip limits, on the deployed CB books (registry v346, registered before running; parent v344).

M3 = L2 on CB books (book x0.75 + bracket dip limits at 3.0 / 4.0 sigma, size_mult 4.375, budget 0.26) uses an exchange-native touch stop at
8 sigma below the fill level (the R2 backstop distance, never tuned for the MANUAL product). The risk budget counts the stop distance, so a nearer
stop both cuts losses earlier and lets more rungs be open at once. Rows (fixed before running; everything else as L2):
  L2    = touch stop 8 sigma (reference, dev4 6.233)
  ST6   = touch stop 6 sigma
  ST10  = touch stop 10 sigma
Fitness / protocol as v338-v344 (v310 MANUAL fitness with the all-trade win rate): dev folds k = 2, 3 on years [:k]; TRANSFER if ST6 / ST10 is
chosen and beats L2 on the unseen dev year in both folds; final choice on dev4; most recent year once; stress row sleeve_start 31.
Contaminated by design; prospective paper log = clean evidence.

  python research/parallel/rounds/parallel-20260906-r2/v346/v346_dip_stop_distance_cb.py
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
DIP = dict(L2=((3.0, 4.0), 4.375, 0.75, 8.0), ST6=((3.0, 4.0), 4.375, 0.75, 6.0), ST10=((3.0, 4.0), 4.375, 0.75, 10.0))


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

    v306 = _load("v306_st", RD / "v306/v306_walkforward_evolution.py")
    v306.init_worker()
    T = v306.W["T"]
    v310 = _load("v310_st", RD / "v310/v310_manual_book_robust_evolution.py")
    v315 = _load("v315_st", RD / "v315/v315_manual_pullback_entry.py")
    v310.init_worker()
    W0 = v310.W
    idx, cols = W0["idx"], W0["cols"]
    assert list(v306.W["idx"]) == list(idx) and list(v306.W["cols"]) == list(cols)
    v306.W.update(T=T)
    rd = lambda f: pd.read_parquet(C / f).reindex(idx).ffill().fillna(0.0)[cols].to_numpy(float)
    PT = (rd("member_PT_pooledtv.parquet") + rd("member_PTq_pooledtv.parquet")) / 2
    A, D = W0["grp"]["wA"].copy(), W0["grp"]["wD"].copy()
    B = W0["grp"]["wB"].copy()
    M2 = (2 * A + 2 * B + D) / 5  # CB books (the deployed form; name kept for the shared wiring)
    size, tp = v306._tables(R2_AGENT)
    eu = W0["eu"]
    sim0 = eu.simulate
    base_p9 = v310._policy9

    def run(row, full=False, sleeve_start=16):
        W0["grp"]["wA"] = W0["grp"]["wB"] = W0["grp"]["wD"] = M2
        v310._policy9 = v315.with_entry(0.75)
        v315.BASE_P9 = base_p9
        if row in DIP:
            depths, smult, bmult, stop = DIP[row]
            kus = [U.index(k) for k in depths]

            def sim(*a, **kw):
                kw.update(sleeve=True, rungs=depths, sleeve_stop_mode="touch", m_sleeve_sl=stop, sleeve_risk_budget=0.26, size_mult=smult,
                          align=(1.5, 0.5), sleeve_start=sleeve_start,
                          sleeve_fill_size=lambda i, aa, r, f: float(size[i, aa, kus[r]]), sleeve_tp=lambda i, aa, r, f: float(tp[i, aa, kus[r]]))
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
    assert abs(v310.metrics(res["L2"], [0, 1, 2, 3])["R"] - 6.233) < 0.003
    out = {"version": "v346", "rows": {k: dict(dev4=v310.metrics(r, [0, 1, 2, 3]), F=round(fit_all(r, [0, 1, 2, 3]), 4),
                                               years=[v310.metrics(r, [y]) for y in range(4)]) for k, r in res.items()}, "folds": {}}
    for k, v in out["rows"].items():
        log(f"{k} dev4 {v['dev4']} F {v['F']}")
    gains = []
    for k in (2, 3):
        ys = list(range(k))
        ch = max(res, key=lambda x: fit_all(res[x], ys))
        f_ch, f0 = fit_all(res[ch], [k]), fit_all(res["L2"], [k])
        out["folds"][k] = dict(choice=ch, test=v310.metrics(res[ch], [k]), F_test=round(f_ch, 4), F_L2=round(f0, 4))
        gains.append(ch != "L2" and f_ch > f0)
        log(f"FOLD {k} choice {ch} TEST {out['folds'][k]['test']} F {f_ch:.4f} vs L2 {f0:.4f}")
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
    (HERE / "v346_result.json").write_text(raw)
    log("sha256 " + hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
