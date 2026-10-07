"""oc_rearm V1 (DISCLOSED POST-HOC variant, 2026-10-06): cap-unit fix.

V0 (pre-registered, results.json) applied G = 2.0 to B1 size_mult weights
(mean 0.61). Fills cluster in flush bars (median 4, mean 7.2, max 49
candidates per phase-bar) with slow exits (median exit minute 211), so G on
size_mult units binds on the MEDIAN fill bar: 60% of base candidates skipped,
69% of re-armed candidates parent-skipped. In deployment G = 2.0 caps
notional/EQUITY where a rung counts s*g*lsz*mult*kd*base*SIZE/4/S_REF
(engine_user.py:642; v421 only trims DD 18.33 -> 16.91, i.e. binds in
extremes, not routinely). V0's cap behaviour is therefore a unit artifact,
not the assignment's guardrail.

V1 changes ONLY the cap walk: G1 = 2.0 / K on the same size_mult weights,
with K = kd*SIZE/(4*S_REF) = 1.7*0.25/(4*1.657) ~= 0.0641 from engine/G2
constants only (kd = 1.7 G2 registry; SIZE = 0.25, S_REF = 1.657 engine_user;
s*g = 1, R2 agent size lsz = 1, risk-budget skips omitted -- disclosed
approximations, identical for both arms, no data fitting). G1 ~= 31.2, so
the guardrail binds only in the most extreme flush bar, deployment-like.
Candidates, fills, exits, fees, scoring and the decision rule are V0-identical
(raw w*y sums, DD tolerance 0.01, re-armed win >= 0.60).

Reads research/tournament/oc_rearm/fills_candidates.parquet (V0 candidates);
writes results_v1.json. No 1m data, seconds of runtime.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import numpy as np
import pandas as pd

import rearm as R
import run_rearm as RR

KD, SIZE, S_REF = 1.7, 0.25, 1.657
K = KD * SIZE / (4 * S_REF)
G1 = 2.0 / K


def main():
    print(f"K={K:.6f} G1={G1:.4f}", flush=True)
    cand = pd.read_parquet(HERE / "fills_candidates.parquet")
    recs = cand.to_dict("records")
    groups: dict = {}
    for i, r in enumerate(recs):
        groups.setdefault((int(r["s"]), int(r["j"])), []).append(i)

    base_rows, rule_rows = [], []
    n_skip_base = n_skip_rule = n_cut_rule = n_cut_base = n_noparent = 0
    for (s, j), idxs in groups.items():
        order = sorted(idxs, key=lambda i: (recs[i]["f"], recs[i]["k"], recs[i]["sym"]))
        pos_of = {i: p for p, i in enumerate(order)}
        F = [int(recs[i]["f"]) for i in order]
        X = [int(recs[i]["x"]) for i in order]
        W8 = [float(recs[i]["w"]) for i in order]
        bord = [p for p in range(len(order)) if int(recs[order[p]]["kind"]) == 0]
        kb = R.gross_cap_weights([F[p] for p in bord], [X[p] for p in bord],
                                 [W8[p] for p in bord], list(range(len(bord))), G=G1)
        for bp, p in enumerate(bord):
            wk = kb[bp]
            r = recs[order[p]]
            if wk <= 0:
                n_skip_base += 1
            else:
                if wk < r["w"] - 1e-12:
                    n_cut_base += 1
                base_rows.append(dict(s=s, y=int(r["y"]), sym=r["sym"], k=float(r["k"]), f=F[p],
                                      x=X[p], how=r["how"], w=wk, ret=float(r["ret"]), xd=r["xd"]))
        P = [pos_of[int(recs[order[p]]["parent"])] if int(recs[order[p]]["kind"]) == 1 else -1
             for p in range(len(order))]
        kr = R.gross_cap_weights(F, X, W8, list(range(len(order))), G=G1, parent=P)
        for p in range(len(order)):
            wk = kr[p]
            r = recs[order[p]]
            if wk <= 0:
                n_skip_rule += 1
                if int(r["kind"]) == 1 and P[p] >= 0 and kr.get(P[p], 0.0) <= 0.0:
                    n_noparent += 1
            else:
                if wk < r["w"] - 1e-12:
                    n_cut_rule += 1
                rule_rows.append(dict(s=s, y=int(r["y"]), sym=r["sym"], k=float(r["k"]),
                                      kind=int(r["kind"]), f=F[p], x=X[p], how=r["how"],
                                      w=wk, ret=float(r["ret"]), xd=r["xd"]))

    df_b = pd.DataFrame(base_rows)
    df_r = pd.DataFrame(rule_rows)

    def arm_year(s, yi, df):
        sub = df[(df["s"] == s) & (df["y"] == yi)]
        if len(sub):
            wy = sub["w"].to_numpy(float) * sub["ret"].to_numpy(float)
            S, Wd, DD, nd = RR.daily_path(list(zip(sub["xd"].tolist(), wy.tolist())))
        else:
            S, Wd, DD, nd = 0.0, 0.0, 0.0, 0
        return {"n": int(len(sub)), "sum": S, "worst_day": Wd, "max_dd": DD, "ndays": nd}

    def renorm_year(s, yi, df):
        sub = df[(df["s"] == s) & (df["y"] == yi)]
        if len(sub):
            w = sub["w"].to_numpy(float)
            wy = w / w.mean() * sub["ret"].to_numpy(float)
            S, _, _, _ = RR.daily_path(list(zip(sub["xd"].tolist(), wy.tolist())))
        else:
            S = 0.0
        return S

    per_year, per_shift = [], {a: {s: [] for s in RR.SHIFTS} for a in ("base", "rule")}
    for yi in range(5):
        row = {"year": RR.ANCHORS[yi].date().isoformat()}
        for arm, df in (("base", df_b), ("rule", df_r)):
            stats = [arm_year(s, yi, df) for s in RR.SHIFTS]
            for s in RR.SHIFTS:
                per_shift[arm][s].append({"year": row["year"], **{kk: stats[s][kk]
                                          for kk in ("n", "sum", "worst_day", "max_dd")}})
            row[arm] = {"sum_mean": float(np.mean([t["sum"] for t in stats])),
                        "n_mean": float(np.mean([t["n"] for t in stats])),
                        "worst_mean": float(np.mean([t["worst_day"] for t in stats])),
                        "dd_mean": float(np.mean([t["max_dd"] for t in stats])),
                        "sum_renorm_mean": float(np.mean([renorm_year(s, yi, df) for s in RR.SHIFTS]))}
        pb = df_b[df_b["y"] == yi]
        pr = df_r[df_r["y"] == yi]
        pr_re = pr[pr["kind"] == 1]
        row["win_base"] = float((pb["ret"].to_numpy(float) > 0).mean()) if len(pb) else 0.0
        row["win_rule"] = float((pr["ret"].to_numpy(float) > 0).mean()) if len(pr) else 0.0
        row["win_rearm"] = float((pr_re["ret"].to_numpy(float) > 0).mean()) if len(pr_re) else 0.0
        row["n_rearm"] = int(len(pr_re))
        wy_tot = float((pr["w"].to_numpy(float) * pr["ret"].to_numpy(float)).sum()) if len(pr) else 0.0
        wy_re = float((pr_re["w"].to_numpy(float) * pr_re["ret"].to_numpy(float)).sum()) if len(pr_re) else 0.0
        row["rearm_share"] = float(wy_re / wy_tot) if wy_tot != 0 else 0.0
        row["rearm_wy"] = wy_re
        row["rule_wy"] = wy_tot
        row["pass_sum"] = bool(np.isfinite(row["rule"]["sum_mean"]) and np.isfinite(row["base"]["sum_mean"])
                               and row["rule"]["sum_mean"] > row["base"]["sum_mean"])
        row["pass_dd"] = bool(np.isfinite(row["rule"]["dd_mean"]) and np.isfinite(row["base"]["dd_mean"])
                              and row["rule"]["dd_mean"] <= row["base"]["dd_mean"] + 0.01)
        per_year.append(row)

    pr_all_re = df_r[df_r["kind"] == 1]
    rw_all = float((pr_all_re["ret"].to_numpy(float) > 0).mean()) if len(pr_all_re) else 0.0
    n_sum = sum(1 for r in per_year if r["pass_sum"])
    n_dd = sum(1 for r in per_year if r["pass_dd"])
    decision = {"years_sum_higher": int(n_sum), "years_dd_not_worse_1pp": int(n_dd),
                "rearm_win_all": rw_all,
                "promising": bool(n_sum >= 4 and n_dd >= 4 and rw_all >= 0.60)}
    out = {"variant": "V1 (disclosed post-hoc cap-unit fix; see module docstring)",
           "K": K, "G1": G1, "G_deployment": 2.0,
           "cap": {"base_skipped": int(n_skip_base), "base_cut": int(n_cut_base),
                   "rule_skipped": int(n_skip_rule), "rule_cut": int(n_cut_rule),
                   "rearm_parent_skipped": int(n_noparent)},
           "n_fills_base": int(len(df_b)), "n_fills_rule": int(len(df_r)),
           "n_fills_rearm": int(len(pr_all_re)),
           "per_year": per_year, "per_shift": per_shift, "decision": decision}
    (HERE / "results_v1.json").write_text(json.dumps(out, indent=1, default=str))
    print("V1 n_base", len(df_b), "n_rule", len(df_r), "n_rearm", len(pr_all_re), flush=True)
    print(json.dumps(decision, indent=1))


if __name__ == "__main__":
    main()
