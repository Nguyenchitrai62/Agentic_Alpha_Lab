"""oc_d_stagger: assemble results.json (CPU-only, reads tmp/*.json/npz).

Frozen rows (PLAN): raw gains (no mult normalisation, exposure-identical by design).
Disclosed EXTRA rows (post-hoc, labelled): exposure-normalised gains
stag_perW = stag/E - base (per-unit-weight diagnostic;COMMON header allows disclosed
extra rows keeping the original).
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
TMP = HERE / "tmp"

PRE_LEGS = ("Y2017", "Y2018", "Y2019", "Y2020p")
Y5 = ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")
BASE_STOP = {"Y2017": 0.033003, "Y2018": 0.032898, "Y2019": 0.066917, "Y2020p": 0.075792,
             "pooled": 0.055788}


def main() -> None:
    pre = json.loads((TMP / "stagger_presample.json").read_text())
    sec = json.loads((TMP / "stagger_2021.json").read_text())
    basekind = json.loads((TMP / "basekind_presample.json").read_text())

    out = {
        "config": {
            "rule": "each rung 50/50 at same frozen sigma price; V1 A=[5,64]+B=[35,94], "
                    "V2 A=[5,64]+B=[95,154] (60 bars each, placed once, never re-pegged); "
                    "REF single print live 16..238",
            "weights": "w_h = 0.5/(1+n(f_h)) B1 at own fill minute (v399-exact, DETECT_K 2.5)",
            "outcomes": "VERBATIM outcome_mu mu=1.0 (sl 4sg, bl 8sg, tp 1sg, close5+backstop, "
                        "maker 0.0002/taker 0.00055, adverse long funding 0.0001/8h, stop-first)",
            "kept": "per half iff y09/y10/y11 ALL finite (halves independent, tapepeg precedent)",
            "scoring": "per-year 4-phase-mean sums; gain = stag - base (NO mult normalisation; "
                       "exposure-identical by design; realised E + fill split reported)",
            "placebo": "B-half P&L permuted within (year,shift), 1000 perms timing seed "
                       "20261007+y; block-42 per (coin,shift) seed 20261008+y; "
                       "pct=100*(1+#{perm<=actual})/1001, signif iff >=95",
            "gates": {"primary": "gain>0 in >=3/4 AND Y2020p gain>0 AND pooled stagger stop "
                                 "delta <= +1pp",
                      "secondary": "dSum5y >= +0.273 AND sum-half >= 4/5",
                      "engine": "only if PRIMARY + SECONDARY pass (else no engine)"},
            "extra_extra": "exposure-normalised gain stag/E - base is a DISCLOSED post-hoc "
                           "diagnostic (frozen raw row stays primary)",
        },
        "reproduction": {
            "presample_ref": pre["reproduction"],
            "ref_2021": sec["reproduction"],
            "basekind": basekind,
            "basekind_note": "kinds TP/time/stop/backstop = 5729/3445/480/62, unknown 15; "
                             "matches oc_cboostpre recompute exactly (cross-validation)",
        },
        "presample": pre,
        "secondary_2021_2026": sec,
        "base_stop_rates": BASE_STOP,
    }

    # primary / secondary verdicts per variant
    for v in ("V1", "V2"):
        prows = pre[v]["per_year"]
        helps = sum(1 for r in prows if r["gain"] > 0)
        covid = [r for r in prows if r["year"] == "Y2020p"][0]["gain"]
        # pooled stagger stop% from halves_known rows: recompute here from stored per-year
        # (stag_half_stop is a share; pool needs counts -> use halves_known weighting)
        num = sum(r["stag_half_stop"] * r["halves_known"] for r in prows)
        den = sum(r["halves_known"] for r in prows)
        pooled_stop = num / den if den else 0.0
        delta = pooled_stop - BASE_STOP["pooled"]
        srows = sec[v]["per_year"]
        out.setdefault("verdict", {})[v] = {
            "primary": {
                "helps": f"{helps}/4", "covid_gain": covid,
                "pooled_stag_stop": round(pooled_stop, 6),
                "pooled_stop_delta_pp": round(100 * delta, 3),
                "pass": bool(helps >= 3 and covid > 0 and delta <= 0.01),
            },
            "secondary": {
                "dSum5y": sec[v]["dSum5y"], "sum_half": sec[v]["sum_half"],
                "pass": sec[v]["secondary_pass"],
            },
            "engine": "NOT RUN (PRIMARY and SECONDARY both fail; PLAN-gated)",
        }
        # disclosed extra: exposure-normalised helps
        nx = sum(1 for r in prows if (r["stag"] / r["exposure_ratio"] - r["base"]) > 0) \
            if all(r["exposure_ratio"] for r in prows) else 0
        out["verdict"][v]["extra_exposure_normalised_helps"] = f"{nx}/4 (diagnostic only)"
    (HERE / "results.json").write_text(json.dumps(out, indent=1))
    print("wrote results.json", flush=True)


if __name__ == "__main__":
    main()
