"""v335: MANUAL product - a DAILY decision cadence that a human can actually follow (registry v335, registered before running).

M2 robustness (research/diagnostics/m2_robustness): the 4h MANUAL book needs the trader within ~15-30 minutes of each of six daily closes
(60 min late: 5y 2.39 %/month, DD 23; missing one decision a day: 2.71 / DD 22.3). A human can reliably act ONCE a day at a fixed time. Rows (fixed
before running; books / rules = M2: (2A + 2PT + D)/5, pullback entry 0.75 sigma_4h, grid trader, SL 4 / TP 8 sigma_d (exchange-native, always
active), target 0.25, cap 2):
  M2      the 4h cadence (reference)
  D00     new entries, adds, reduces and signal-loss closes only at the decision bar closing 00:00 UTC (07:00 Vietnam); every other bar: flat -> wait,
          in a position -> hold (SL / TP keep working); the opening limit rests 6 bars (24 h)
  D12     the same at 12:00 UTC (19:00 Vietnam)
Every row is run at the realistic human latency of 60 minutes (win_start 60: no fill in the first hour after the decision close) and, for reference,
at 5 minutes. CHOICE (primary = latency 60): dev folds k = 2, 3 with the v310 robust MANUAL fitness on years [:k]; TRANSFER if a daily row is chosen and
beats M2 (latency 60) on the unseen year in both folds. Final on dev4; the most recent year once (M2 shaped with knowledge of it - contaminated).

  python research/parallel/rounds/parallel-20260906-r2/v335/v335_manual_daily_cadence.py
"""
import hashlib
import importlib.util
import json
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent
RD = HERE.parent
C = Path("artifacts/research/engine_real")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    v310 = _load("v310_dc", RD / "v310/v310_manual_book_robust_evolution.py")
    v310.init_worker()
    W0 = v310.W
    idx, cols = W0["idx"], W0["cols"]
    rd = lambda f: pd.read_parquet(C / f).reindex(idx).ffill().fillna(0.0)[cols].to_numpy(float)
    PT = (rd("member_PT_pooledtv.parquet") + rd("member_PTq_pooledtv.parquet")) / 2
    mix = (2 * W0["grp"]["wA"] + 2 * PT + W0["grp"]["wD"]) / 5
    W0["grp"]["wA"] = W0["grp"]["wB"] = W0["grp"]["wD"] = mix
    base_p9 = v310._policy9
    close_hour = ((idx + pd.Timedelta(hours=4)).hour).to_numpy()  # the decision at bar i is taken at the close of bar idx[i] (= idx[i] + 4h)
    eu = W0["eu"]
    sim0 = eu.simulate

    def make(hour):
        def p9(*a):
            base = base_p9(*a)

            def pol(i, aa, st):
                if hour is not None and close_hour[i] != hour:
                    return "wait" if st["pos"] == 0 else "hold"
                return {"open": 0.75} if st["pos"] == 0 else base(i, aa, st)
            return pol
        return p9

    def run(row, lat, full=False):
        hour = {"M2": None, "D00": 0, "D12": 12}[row]
        nv = 3 if hour is None else 6

        def sim(*a, **kw):
            kw["win_start"] = lat
            return sim0(*a, **kw)
        v310._policy9, eu.simulate = make(hour), sim
        try:
            return v310.run_genome(v310.encode(dict(target=0.25, cap=2.0, n_valid=nv)), full)
        finally:
            v310._policy9, eu.simulate = base_p9, sim0

    res = {(r, lat): run(r, lat) for r in ("M2", "D00", "D12") for lat in (5, 60)}
    assert abs(v310.metrics(res[("M2", 5)], [0, 1, 2, 3])["R"] - 3.011) < 0.003
    out = {"version": "v335", "rows": {f"{r}:{lat}": dict(dev4=v310.metrics(x, [0, 1, 2, 3]), F=round(v310.fitness(x, [0, 1, 2, 3]), 4))
                                       for (r, lat), x in res.items()}, "folds": {}}
    for k, v in out["rows"].items():
        print(k, v, flush=True)
    prim = {r: res[(r, 60)] for r in ("M2", "D00", "D12")}
    gains = []
    for k in (2, 3):
        ys = list(range(k))
        ch = max(prim, key=lambda x: v310.fitness(prim[x], ys))
        f_ch, f0 = v310.fitness(prim[ch], [k]), v310.fitness(prim["M2"], [k])
        out["folds"][k] = dict(choice=ch, test=v310.metrics(prim[ch], [k]), F_test=round(f_ch, 4), F_M2_lat60=round(f0, 4))
        gains.append(ch != "M2" and f_ch > f0)
        print("FOLD", k, out["folds"][k], flush=True)
    out["transfer"] = dict(holds=bool(all(gains)))
    ch = max(prim, key=lambda x: v310.fitness(prim[x], [0, 1, 2, 3]))
    full = run(ch, 60, True)
    out["final"] = dict(choice=ch, latency=60, dev4=v310.metrics(prim[ch], [0, 1, 2, 3]), last_year=v310.metrics(full, [4]),
                        five_years=v310.metrics(full, [0, 1, 2, 3, 4]), full={q: full[q] for q in ("monthly_5y", "monthly_last_year", "gate_dd", "losing_years")})
    print("TRANSFER", out["transfer"], "FINAL", out["final"], flush=True)
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v335_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
