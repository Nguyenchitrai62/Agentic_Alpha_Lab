"""v315: MANUAL product - PULLBACK ENTRIES for the book (registry v315): one resting limit in the signal direction, deeper than G2's.

Why: the dip ladder (BOT) earns from intrabar over-extension, but a human cannot run it; the book enters with a limit only 0.25 sigma_4h better than
the bar open (G2), i.e. almost at market. A deeper entry limit in the SIGNAL direction (buy a pullback in an up-signal, sell a rip in a
down-signal), resting a few bars, is one order a human can place (user rule 2026-09-28: one resting limit at a distance, valid a few hours, cancelled
when the signal disappears) and should improve the entry price (win rate) at the cost of missed trades. Low-dimensional on purpose (v307 / v314:
many genes or leverage do not generalise): everything = audited G2 manual (members A2 B2 D1, target 0.25, cap 2, grid trader, SL 4 / TP 8 sigma_d,
break-even +2 sigma_d, theta 0.05, governor 0.20 / 0.10) except two dials of the ENTRY order only:
  k_entry (offset of the opening limit, sigma_4h) 0.25 (G2) / 0.75 / 1.25 / 2.0      n_valid (bars the orders rest) 2 (G2) / 3 / 6
(policy: flat -> {"open": k_entry}; in a position the v216 grid policy unchanged; n_valid also applies to the in-position limit orders.)
CHOICE for test year k: the v310 robust MANUAL fitness on years [:k] averaged over the configuration and its grid neighbours (flat choice); dev
folds k = 2, 3; TRANSFER holds if F_test(choice) > F_test(G2 manual) in both. The most recent year is scored once for the dev4 choice.
Disclosure: designed after v307 / v314 scored their finalists on the most recent year (leverage did not generalise); no v315 choice uses those scores.

  python research/parallel/rounds/parallel-20260906-r2/v315/v315_manual_pullback_entry.py
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).parent
RD = HERE.parent
KS = (0.25, 0.75, 1.25, 2.0)
NV = (2, 3, 6)


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


v310 = _load("v310_pb", RD / "v310/v310_manual_book_robust_evolution.py")
BASE_P9 = v310._policy9


def with_entry(k_entry):
    def p9(*a):
        base = BASE_P9(*a)

        def pol(i, aa, st):
            if st["pos"] == 0:
                return {"open": k_entry}
            return base(i, aa, st)
        return pol
    return p9


def run(k, nv, full=False):
    v310._policy9 = with_entry(k)
    try:
        return v310.run_genome(v310.encode(dict(target=0.25, cap=2.0, n_valid=nv)), full)
    finally:
        v310._policy9 = BASE_P9


def main():
    logf = (HERE / "run_detail.log").open("a")

    def log(s):
        print(s, flush=True)
        logf.write(s + "\n"); logf.flush()

    v310.init_worker()
    res = {(k, nv): run(k, nv) for k in KS for nv in NV}
    ref = res[(0.25, 2)]
    assert abs(v310.metrics(ref, [0, 1, 2, 3])["R"] - 2.502) < 0.003
    for k, r in res.items():
        log(f"entry {k} dev4 {v310.metrics(r, [0, 1, 2, 3])}")

    def flat(c, ys):
        ki, ni = KS.index(c[0]), NV.index(c[1])
        nb = [c] + [(KS[ki + d], c[1]) for d in (-1, 1) if 0 <= ki + d < len(KS)] + [(c[0], NV[ni + d]) for d in (-1, 1) if 0 <= ni + d < len(NV)]
        return float(np.mean([v310.fitness(res[x], ys) for x in nb]))

    out = {"version": "v315", "grid": {str(k): v310.metrics(r, [0, 1, 2, 3]) for k, r in res.items()}, "folds": {}}
    deltas = []
    for k in (2, 3):
        ys = list(range(k))
        ch = max(res, key=lambda x: flat(x, ys))
        f_ch, f_ref = v310.fitness(res[ch], [k]), v310.fitness(ref, [k])
        out["folds"][k] = dict(choice=list(ch), train=v310.metrics(res[ch], ys), test=v310.metrics(res[ch], [k]), F_test=round(f_ch, 4),
                               G2_manual_test=v310.metrics(ref, [k]), F_G2=round(f_ref, 4))
        deltas.append(f_ch - f_ref)
        log(f"FOLD {k} choice {ch} TEST {out['folds'][k]['test']} F {f_ch:.4f} | G2 manual {out['folds'][k]['G2_manual_test']} F {f_ref:.4f}")
    out["transfer"] = dict(deltas=[round(d, 4) for d in deltas], holds=bool(all(d > 0 for d in deltas)))
    log(f"TRANSFER {out['transfer']}")
    ys = [0, 1, 2, 3]
    ch = max(res, key=lambda x: flat(x, ys))
    full = run(ch[0], ch[1], True)
    out["final"] = dict(choice=list(ch), dev4=v310.metrics(res[ch], ys), last_year=v310.metrics(full, [4]), five_years=v310.metrics(full, [0, 1, 2, 3, 4]),
                        full={k: full[k] for k in ("monthly_5y", "monthly_last_year", "gate_dd", "losing_years", "monthly_dev4")},
                        recommended=out["transfer"]["holds"])
    log(f"FINAL choice {ch} dev4 {out['final']['dev4']} | last year {out['final']['last_year']} | 5y {out['final']['five_years']} | full {out['final']['full']}")
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v315_result.json").write_text(raw)
    log("sha256 " + hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
