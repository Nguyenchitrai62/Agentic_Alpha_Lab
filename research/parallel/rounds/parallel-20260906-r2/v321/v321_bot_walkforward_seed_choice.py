"""v321: BOT product - walk-forward choice among the existing BOT pipelines (the v306 seeds), scored once on the most recent year (registry v321).

v306 (Kaggle, BOT walk-forward GA): the evolved winners lost to the best SEED on every unseen dev year (deltas -0.217 / -0.207 / -0.046), and the
best seed on the training years was R2 in all three folds (R2 = G2 + a 5.0-sigma rung, dip ladder 2.5..5.0, dip agents fitted on all seven rung
depths, bar-open form). The procedure "pick the best existing pipeline by the BOT fitness on the years before the test year" is therefore the
walk-forward-validated BOT procedure; its unseen-year record (from v306): 2022 4.25 %/month DD 16.4, 2023 10.22 DD 18.4, 2024 10.05 DD 12.7 (G2 on
the same years: 3.80 / 9.28 / 9.35).
v321 applies the same procedure for the most recent year: choice = the seed with the highest v306 BOT fitness on the four dev years; the most recent
year is computed ONCE for that choice (G2's most-recent-year number 5.349 is already known from its deployment and is reported for comparison).

  python research/parallel/rounds/parallel-20260906-r2/v321/v321_bot_walkforward_seed_choice.py
"""
import hashlib
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).parent
RD = HERE.parent


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    v306 = _load("v306_s", RD / "v306/v306_walkforward_evolution.py")
    v306.init_worker()
    seeds = {k: v306.encode(v) for k, v in v306.SEEDS.items()}
    res = {k: v306.run_genome(g) for k, g in seeds.items()}
    F = {k: v306.fitness(r, [0, 1, 2, 3]) for k, r in res.items()}
    assert abs(v306.metrics(res["G2"], [0, 1, 2, 3])["R"] - 6.504) < 0.003
    choice = max(F, key=F.get)
    full = v306.run_genome(seeds[choice], True)
    prev = json.loads((RD / "v306/v306_result.json").read_text())
    out = {"version": "v321", "dev4": {k: dict(v306.metrics(r, [0, 1, 2, 3]), F=round(F[k], 4)) for k, r in res.items()}, "choice": choice,
           "wf_record": {k: dict(best_seed=f["best_seed"], test=f["best_seed_test"]) for k, f in prev["folds"].items()},
           "final": dict(genome=v306.decode(seeds[choice]), last_year=v306.metrics(full, [4]), five_years=v306.metrics(full, [0, 1, 2, 3, 4]),
                         full={q: full[q] for q in ("monthly_5y", "monthly_last_year", "gate_dd", "dd_1m", "dd_4h", "losing_years", "monthly_dev4")}),
           "G2_known_last_year_monthly": 5.349}
    for k, v in out["dev4"].items():
        print(k, v, flush=True)
    print("CHOICE", choice, "FINAL", out["final"], flush=True)
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v321_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
