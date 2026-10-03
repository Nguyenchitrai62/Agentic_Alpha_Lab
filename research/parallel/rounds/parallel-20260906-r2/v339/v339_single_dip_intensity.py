"""v339: INTENSITY of the MANUAL-feasible single dip limit (registry v339, registered before running; parent v338).

v338 MD30 (M2 book + ONE native-bracket dip limit per coin at 3.0 sigma, fills from minute 16, touch stop 8 sigma, budget 0.26 counted at 8 sigma,
R2 agents' size / TP at the bar open) transferred on both dev folds: dev4 3.905, worst dev year 0.872, DD 16.77; 5y 3.95, last year 4.13, gate DD 18.83.
3.0 beat 3.5 sigma (closer = more fills), and one rung per coin carries ~1/5 of the R2 ladder's risk -> two intensity variants (fixed before running):
  MD30   = v338 MD30 (reference; dev4 3.905)
  MD25   = the single dip at 2.5 sigma (everything else as MD30)
  MD30x2 = the single dip at 3.0 sigma with twice the per-rung size (size_mult 3.5 instead of 1.75; the 0.26 budget at 8 sigma still binds)
Everything else, the fitness (v310 MANUAL fitness with the all-trade win rate), and the protocol are as v338: dev folds k = 2, 3 on years [:k];
TRANSFER if a variant (not MD30) is chosen and beats MD30 on the unseen dev year in both folds; final choice on dev4; most recent year once;
stress row sleeve_start 31 (30-min reaction) for the final. Contaminated by design (see v338); prospective paper log = clean evidence.

  python research/parallel/rounds/parallel-20260906-r2/v339/v339_single_dip_intensity.py
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
DIP = dict(MD30=(3.0, 1.75), MD25=(2.5, 1.75), MD30x2=(3.0, 3.5))


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

    v306 = _load("v306_mi", RD / "v306/v306_walkforward_evolution.py")
    v306.init_worker()
    T = v306.W["T"]
    v310 = _load("v310_mi", RD / "v310/v310_manual_book_robust_evolution.py")
    v315 = _load("v315_mi", RD / "v315/v315_manual_pullback_entry.py")
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
            depth, smult = DIP[row]
            ku = U.index(depth)

            def sim(*a, **kw):
                kw.update(sleeve=True, rungs=(depth,), sleeve_stop_mode="touch", m_sleeve_sl=8.0, sleeve_risk_budget=0.26, size_mult=smult,
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

    res = {k: run(k) for k in DIP}
    assert abs(v310.metrics(res["MD30"], [0, 1, 2, 3])["R"] - 3.905) < 0.003
    out = {"version": "v339", "rows": {k: dict(dev4=v310.metrics(r, [0, 1, 2, 3]), F=round(fit_all(r, [0, 1, 2, 3]), 4),
                                               years=[v310.metrics(r, [y]) for y in range(4)]) for k, r in res.items()}, "folds": {}}
    for k, v in out["rows"].items():
        log(f"{k} dev4 {v['dev4']} F {v['F']}")
    gains = []
    for k in (2, 3):
        ys = list(range(k))
        ch = max(res, key=lambda x: fit_all(res[x], ys))
        f_ch, f0 = fit_all(res[ch], [k]), fit_all(res["MD30"], [k])
        out["folds"][k] = dict(choice=ch, test=v310.metrics(res[ch], [k]), F_test=round(f_ch, 4), F_MD30=round(f0, 4))
        gains.append(ch != "MD30" and f_ch > f0)
        log(f"FOLD {k} choice {ch} TEST {out['folds'][k]['test']} F {f_ch:.4f} vs MD30 {f0:.4f}")
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
    (HERE / "v339_result.json").write_text(raw)
    log("sha256 " + hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
