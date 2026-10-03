"""v334: BOT goal 2 (DD < 15%) - R2 with a tighter drawdown governor (registry v334, registered before running).

R2 (v321): 5y 6.79 %/month, DD 18.39. The governor g = clip((dd_zero - dd) / width, 0, 1) on the trailing 90-day peak (engine hook gov) cuts book
targets AND dip-rung sizes in a drawdown; the audited setting (0.20, 0.10) starts cutting at DD 10% and stops trading at 20%. Rows (fixed before
running; R2 otherwise unchanged): G0 (0.20, 0.10) = R2 | G1 (0.17, 0.08) | G2 (0.15, 0.06).
CHOICE: dev folds k = 1, 2, 3 with the v306 BOT fitness (R / 8, W / 5, 15 / DD, win / 0.65) on years [:k]; TRANSFER if a tighter row is chosen and
beats G0 on the unseen dev year in >= 2 of 3 folds. Final on dev4; the most recent year computed once for the final choice.

  python research/parallel/rounds/parallel-20260906-r2/v334/v334_r2_tighter_governor.py
"""
import hashlib
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).parent
RD = HERE.parent
ROWS = {"G0": (0.20, 0.10), "G1": (0.17, 0.08), "G2": (0.15, 0.06)}


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    v306 = _load("v306_gv", RD / "v306/v306_walkforward_evolution.py")
    v306.init_worker()
    eu = v306.W["eu"]
    sim0 = eu.simulate
    g = v306.encode(v306.SEEDS["R2"])

    def run(k, full=False):
        def sim(*a, **kw):
            kw["gov"] = ROWS[k]
            return sim0(*a, **kw)
        eu.simulate = sim
        try:
            return v306.run_genome(g, full)
        finally:
            eu.simulate = sim0

    res = {k: run(k) for k in ROWS}
    assert abs(v306.metrics(res["G0"], [0, 1, 2, 3])["R"] - 7.079) < 0.003
    out = {"version": "v334", "rows": {k: dict(dev4=v306.metrics(r, [0, 1, 2, 3]), F=round(v306.fitness(r, [0, 1, 2, 3]), 4),
                                               years=[v306.metrics(r, [y]) for y in range(4)]) for k, r in res.items()}, "folds": {}}
    for k, v in out["rows"].items():
        print(k, v["dev4"], v["F"], flush=True)
    gains = 0
    for k in (1, 2, 3):
        ys = list(range(k))
        ch = max(res, key=lambda x: v306.fitness(res[x], ys))
        f_ch, f0 = v306.fitness(res[ch], [k]), v306.fitness(res["G0"], [k])
        out["folds"][k] = dict(choice=ch, test=v306.metrics(res[ch], [k]), F_test=round(f_ch, 4), F_G0=round(f0, 4))
        gains += int(ch != "G0" and f_ch > f0)
        print("FOLD", k, out["folds"][k], flush=True)
    out["transfer"] = dict(gain_folds=gains, holds=bool(gains >= 2))
    ch = max(res, key=lambda x: v306.fitness(res[x], [0, 1, 2, 3]))
    full = run(ch, True)
    out["final"] = dict(choice=ch, dev4=v306.metrics(res[ch], [0, 1, 2, 3]), last_year=v306.metrics(full, [4]), five_years=v306.metrics(full, [0, 1, 2, 3, 4]),
                        full={q: full[q] for q in ("monthly_5y", "monthly_last_year", "gate_dd", "losing_years")})
    print("TRANSFER", out["transfer"], "FINAL", out["final"], flush=True)
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v334_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
