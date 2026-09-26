"""R69a realistic acceptance re-rank (ANALYSIS ONLY).

Reads ALREADY-MEASURED frozen summaries, never runs backtests/training.
Scoring weights/formulas/branch map are loaded from
configs/opencode_v160_realistic.json (fixed BEFORE compiling).

Outputs (new only) under artifacts/research/opencode_v160_realistic/:
  robustness_matrix.json / .csv, ranking.json / .csv, summary.json

Exploratory labels: opened DEV interval only. No live orders. No promotion claim.
"""
import csv
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CFG_PATH = ROOT / "configs" / "opencode_v160_realistic.json"
OUT_DIR = ROOT / "artifacts" / "research" / "opencode_v160_realistic"


def load(p):
    with open(ROOT / p, "r", encoding="utf-8") as f:
        return json.load(f)


def clip(x, lo, hi):
    return max(lo, min(hi, x))


def main():
    cfg = json.loads(CFG_PATH.read_text(encoding="utf-8"))
    w = cfg["weights"]
    assert abs(sum(w.values()) - 1.0) < 1e-9, "weights must sum to 1.0"

    dossier = load("artifacts/research/opencode_dossier_v14/promotion_table.json")
    rows = {r["family"]: r for r in dossier["rows"]}

    # ---- frozen robustness sources (read-only) ----
    v30 = load("artifacts/research/opencode_v30_probfill/summary.json")["branches"]
    v32 = load("artifacts/research/opencode_v32_volcap/summary.json")["branches"]
    v33 = load("artifacts/research/opencode_v33_latency/majority-delay/summary.json")["branches"]
    v37 = load("artifacts/research/opencode_v37_decay/opencode-profit-round1/summary.json")["branches"]
    v68 = load("artifacts/research/opencode_v68_volscaleband2/summary.json")["branches"]
    v86 = load("artifacts/research/opencode_v86_volscalecombo/summary.json")["branches"]
    v93 = load("artifacts/research/opencode_v93_volscale38iso/summary.json")["branches"]
    be_majority = load("artifacts/research/opencode_v39_feeladder/summary.json")["breakeven_extrapolated_ols"]["1x"]["monthly_breakeven_fee_extrapolated"]
    be_band2 = load("artifacts/research/opencode_v71_feeband2/summary.json")["breakeven_extrapolated_ols"]["1x"]["monthly_breakeven_fee_extrapolated"]
    be_s0004 = load("artifacts/research/opencode_v76_L2fee/summary.json")["breakeven_extrapolated_ols"]["1x"]["monthly_breakeven_fee_extrapolated"]
    be_combo = load("artifacts/research/opencode_v81_feecombo/summary.json")["breakeven_extrapolated_ols"]["as-combo-frozen"]["monthly_breakeven_fee_extrapolated"]
    be_conf = load("artifacts/research/opencode_v87_feeconfirmed/summary.json")["breakeven_extrapolated_ols"]["1x"]["monthly_breakeven_fee_extrapolated"]
    fwd38 = load("artifacts/research/opencode_v135_fwdeval38/summary.json")
    fwdmaj = load("artifacts/research/opencode_v154_fwdmaj/summary.json")["branches"]

    # ---- top-8 by Normal monthly (dossier r14; mission-fixed list) ----
    # family -> (book id, dossier row, normal branch label)
    top8 = [
        ("s0004_1x", "L2_s0004", "s0004_1x"),
        ("majority_1x", "majority_1x", "majority_1x"),
        ("L3-combo", "L3_combo", "dd_guard_tp075"),
        ("confirmed_dd", "confirmed_dd_guard", "confirmed_dd_guard"),
        ("band2", "band2confirmed", "confirmed_band2_1x"),
        ("t050", "t050", "t050_1x"),
        ("agreeweight_dd", "agreeweight_dd", "U1_agreeweight_dd_guard"),
        ("v38-isoall", "v38_isoall", "v38-isoall_1x"),
    ]

    mos = [rows[f]["normal_Mo"] for _, f, _ in top8]
    min_mo, max_mo = min(mos), max(mos)

    def fee_frac(book):
        return {
            "majority_1x": (be_majority, "artifacts/research/opencode_v39_feeladder/summary.json breakeven_extrapolated_ols.1x.monthly (0.0079169)"),
            "band2": (be_band2, "artifacts/research/opencode_v71_feeband2/summary.json breakeven_extrapolated_ols.1x.monthly (0.0140254)"),
            "s0004_1x": (be_s0004, "artifacts/research/opencode_v76_L2fee/summary.json breakeven_extrapolated_ols.1x.monthly (0.0054467)"),
            "L3-combo": (be_combo, "artifacts/research/opencode_v81_feecombo/summary.json breakeven_extrapolated_ols.as-combo-frozen.monthly (0.0051048)"),
            "confirmed_dd": (be_conf, "artifacts/research/opencode_v87_feeconfirmed/summary.json breakeven_extrapolated_ols.1x.monthly (0.0080831)"),
        }.get(book, (None, "UNKNOWN (never measured)"))

    matrix = []
    for book, fam, branch in top8:
        r = rows[fam]
        mo = r["normal_Mo"]
        dd = r["normal_DD"]
        fills = r["normal_fills"]
        exec_mo = r["exec_Mo"]
        exec_fills = r["exec_fills"]
        conc_flag = r.get("concentration_flag", "unknown")

        # sub-scores
        norm_mo = (mo - min_mo) / (max_mo - min_mo) if max_mo > min_mo else 0.0
        dd_margin = clip((0.20 - abs(dd)) / 0.20, 0.0, 1.0)
        exec_ret = clip((exec_mo / mo) if mo else 0.0, 0.0, 1.2) / 1.2

        be_frac, be_src = fee_frac(book)
        if be_frac:
            fee_h = clip(math.log(be_frac / 0.0002) / math.log(0.015 / 0.0002), 0.0, 1.0)
            be_disp = {"fraction": be_frac, "bps_at_1bp_eq_0p0001": round(be_frac / 0.0001, 1), "source": be_src, "status": "measured"}
        else:
            fee_h = 0.0
            be_disp = {"fraction": None, "bps_at_1bp_eq_0p0001": None, "source": be_src, "status": "UNKNOWN"}

        # prob-fill p=0.2 (only majority + confirmed ever measured in v30)
        if book == "majority_1x":
            b = v30["majority_pf020_ps00"]["scenarios"]["normal"]
            pf = {"fills": b["trades"], "monthly": b["monthly_geometric_net"], "dd": b["max_drawdown"],
                  "source": "artifacts/research/opencode_v30_probfill/summary.json majority_pf020_ps00.normal",
                  "status": "measured"}
            probfill = 1.0 if (b["trades"] >= 30 and abs(b["max_drawdown"]) <= 0.20) else (0.6 if b["trades"] >= 30 else 0.0)
        elif book == "confirmed_dd":
            b = v30["confirmed_pf020_ps50"]["scenarios"]["normal"]
            pf = {"fills": b["trades"], "monthly": b["monthly_geometric_net"], "dd": b["max_drawdown"],
                  "source": "artifacts/research/opencode_v30_probfill/summary.json confirmed_pf020_ps50.normal",
                  "status": "measured"}
            probfill = 1.0 if (b["trades"] >= 30 and abs(b["max_drawdown"]) <= 0.20) else (0.6 if b["trades"] >= 30 else 0.0)
        else:
            pf = {"fills": None, "monthly": None, "dd": None,
                  "source": "UNKNOWN (never measured)", "status": "UNKNOWN"}
            probfill = 0.0

        # volume-cap k=5% at indexed capital (measured on 4/8 books)
        if book == "majority_1x":
            c, ctl = v32["majority_k05"]["scenarios"]["normal"], v32["majority_k100"]["scenarios"]["normal"]
            vc = {"fills": c["trades"], "control_fills": ctl["trades"],
                  "skipped": c["volcap"]["n_volcap_skipped_bars"],
                  "source": "artifacts/research/opencode_v32_volcap/summary.json majority_k05.normal (0 skipped, 63==63)",
                  "status": "measured"}
            volcap = 1.0 if (c["trades"] == ctl["trades"] and c["volcap"]["n_volcap_skipped_bars"] == 0) else 0.0
        elif book == "band2":
            c = v68["cap100_k05"]["scenarios"]["normal"]
            ctl = v68["cap100_k100"]["scenarios"]["normal"]
            vc = {"fills": c["trades"], "control_fills": ctl["trades"],
                  "skipped": c["volcap"]["n_volcap_skipped_bars"],
                  "source": "artifacts/research/opencode_v68_volscaleband2/summary.json cap100_k05.normal (30==30)",
                  "status": "measured"}
            volcap = 1.0 if c["trades"] == ctl["trades"] else 0.0
        elif book == "L3-combo":
            c = v86["cap100_k05"]["scenarios"]["normal"]
            ctl = v86["cap100_k100"]["scenarios"]["normal"]
            vc = {"fills": c["trades"], "control_fills": ctl["trades"],
                  "skipped": c["volcap"]["n_volcap_skipped_bars"],
                  "source": "artifacts/research/opencode_v86_volscalecombo/summary.json cap100_k05.normal (101==101)",
                  "status": "measured"}
            volcap = 1.0 if c["trades"] == ctl["trades"] else 0.0
        elif book == "v38-isoall":
            c = v93["cap100_k05"]["scenarios"]["normal"]
            ctl = v93["cap100_k100"]["scenarios"]["normal"]
            vc = {"fills": c["trades"], "control_fills": ctl["trades"],
                  "skipped": c["volcap"]["n_volcap_skipped_bars"],
                  "source": "artifacts/research/opencode_v93_volscale38iso/summary.json cap100_k05.normal (68==68)",
                  "status": "measured"}
            volcap = 1.0 if c["trades"] == ctl["trades"] else 0.0
        else:
            vc = {"fills": None, "control_fills": None, "skipped": None,
                  "source": "UNKNOWN (never measured)", "status": "UNKNOWN"}
            volcap = 0.0

        # latency d2 (d6 display for majority only; others UNKNOWN)
        if book == "majority_1x":
            d2 = v33["majority_d2"]["scenarios"]["normal"]
            d6 = v37["majority_d6"]["scenarios"]["normal"]
            lat = {"d2_fills": d2["trades"], "d2_monthly": d2["monthly_geometric_net"],
                   "d6_fills": d6["trades"], "d6_monthly": d6["monthly_geometric_net"],
                   "source": "artifacts/research/opencode_v33_latency/majority-delay/summary.json majority_d2.normal + artifacts/research/opencode_v37_decay/.../summary.json majority_d6.normal",
                   "status": "measured"}
            latency = 1.0 if (d2["trades"] >= 30 and d2["monthly_geometric_net"] >= 0.9 * mo) else 0.0
        elif book == "confirmed_dd":
            d2 = v33["confirmed_d2"]["scenarios"]["normal"]
            lat = {"d2_fills": d2["trades"], "d2_monthly": d2["monthly_geometric_net"],
                   "d6_fills": None, "d6_monthly": None,
                   "source": "artifacts/research/opencode_v33_latency/majority-delay/summary.json confirmed_d2.normal",
                   "status": "measured"}
            latency = 1.0 if (d2["trades"] >= 30 and d2["monthly_geometric_net"] >= 0.9 * mo) else 0.0
        else:
            lat = {"d2_fills": None, "d2_monthly": None, "d6_fills": None, "d6_monthly": None,
                   "source": "UNKNOWN (never measured)", "status": "UNKNOWN"}
            latency = 0.0

        # concentration (dossier flag; v61 diffuse set; v62 v38 concentrated)
        if "CONCENTRATED" in conc_flag:
            conc = 0.0
            conc_src = "artifacts/research/opencode_v62_v38conc/summary.json (top5 71.3%, Gini 1.45) via dossier flag"
            conc_status = "measured-CONCENTRATED"
        elif "diffuse" in conc_flag:
            conc = 1.0
            conc_src = ("artifacts/research/opencode_v61_monthattr/summary.json"
                        if fam in ("majority_1x", "confirmed_dd_guard", "band2confirmed", "agreeweight_dd")
                        else "artifacts/research/opencode_v75_L3real/gatecheck_official.json (v79) via dossier flag")
            conc_status = "measured-diffuse"
        else:
            conc = 0.4
            conc_src = "UNKNOWN (never measured)"
            conc_status = "UNKNOWN"

        # forward OOS (display only)
        if book == "majority_1x":
            n = fwdmaj["majority_1x"]["normal"]
            fwd = {"window": "2026-03-23->2026-09-08", "ret": n["total_return"],
                   "monthly": n["monthly_geometric_net"], "dd": n["max_drawdown"], "fills": n["trades"],
                   "verdict": "FORWARD_ONLY REJECT (fills 11<30, top1mo 149.3%; sign/DD hold)",
                   "source": "artifacts/research/opencode_v154_fwdmaj/summary.json majority_1x.normal",
                   "status": "measured"}
        elif book == "s0004_1x":
            n = fwdmaj["majority_s0004_1x"]["normal"]
            fwd = {"window": "2026-03-23->2026-09-08", "ret": n["total_return"],
                   "monthly": n["monthly_geometric_net"], "dd": n["max_drawdown"], "fills": n["trades"],
                   "verdict": "OOS NEGATIVE (-1.88%/mo, fills 13<30)",
                   "source": "artifacts/research/opencode_v154_fwdmaj/summary.json majority_s0004_1x.normal",
                   "status": "measured"}
        elif book == "v38-isoall":
            n = {"total_return": 0.13109249132208323, "monthly_geometric_net": 0.022365042200029217,
                 "max_drawdown": -0.10953042282083492, "trades": 17}
            fwd = {"window": "2026-03-23->2026-09-08", "ret": n["total_return"],
                   "monthly": n["monthly_geometric_net"], "dd": n["max_drawdown"], "fills": n["trades"],
                   "verdict": "FORWARD_ONLY REJECT (fills 17<30, top1mo 68.9%; sign/DD hold)",
                   "source": "artifacts/research/opencode_v135_fwdeval38/summary.json v38_isoall_fwd_1x.normal",
                   "status": "measured"}
        else:
            fwd = {"window": None, "ret": None, "monthly": None, "dd": None, "fills": None,
                   "verdict": "never forward-tested",
                   "source": "UNKNOWN (never measured)", "status": "UNKNOWN"}

        score = 100.0 * (w["normal_monthly_norm"] * norm_mo + w["dd_margin"] * dd_margin
                         + w["exec_retention"] * exec_ret
                         + w["fee_headroom"] * fee_h + w["probfill"] * probfill
                         + w["volcap"] * volcap + w["latency"] * latency
                         + w["concentration"] * conc)

        matrix.append({
            "book": book, "family": fam, "branch": branch,
            "normal": {"monthly": mo, "dd": dd, "fills": fills, "pf": r["normal_PF"], "wr": r["normal_WR"],
                       "source": f"artifacts/research/opencode_dossier_v14/promotion_table.json row {fam}", "status": "measured"},
            "dd_margin": {"value": dd_margin, "source": "derived clip((0.20-|DD|)/0.20) from dossier normal_DD", "status": "derived"},
            "probfill_p02": pf, "volcap_k05": vc, "latency": lat,
            "fee_breakeven": be_disp,
            "exec_stress": {"monthly": exec_mo, "fills": exec_fills,
                            "retention": (exec_mo / mo) if mo else None,
                            "source": f"artifacts/research/opencode_dossier_v14/promotion_table.json row {fam} exec_Mo/exec_fills",
                            "status": "measured"},
            "concentration": {"flag": conc_flag, "score": conc, "source": conc_src, "status": conc_status},
            "forward_oos": fwd,
            "subscores": {"normal_monthly_norm": norm_mo, "dd_margin": dd_margin,
                          "exec_retention": exec_ret, "fee_headroom": fee_h,
                          "probfill": probfill, "volcap": volcap, "latency": latency,
                          "concentration": conc},
            "realistic_score": score,
        })

    matrix.sort(key=lambda x: x["realistic_score"], reverse=True)
    for i, m in enumerate(matrix, 1):
        m["realistic_rank"] = i
    normal_rank = sorted(matrix, key=lambda x: x["normal"]["monthly"], reverse=True)
    for i, m in enumerate(normal_rank, 1):
        m["normal_rank"] = i

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "robustness_matrix.json").write_text(json.dumps(matrix, indent=1), encoding="utf-8")
    with open(OUT_DIR / "robustness_matrix.csv", "w", newline="", encoding="utf-8") as f:
        wr = csv.writer(f)
        wr.writerow(["book", "normal_Mo_pct", "normal_DD_pct", "normal_fills",
                     "probfill_p02_fills", "probfill_p02_Mo_pct", "probfill_src",
                     "volcap_k05_fills", "volcap_src", "latency_d2_fills", "latency_d2_Mo_pct",
                     "fee_BE_frac", "fee_BE_bps", "exec_Mo_pct", "exec_fills",
                     "concentration", "forward_OOS_Mo_pct", "forward_OOS_fills",
                     "realistic_score", "realistic_rank", "normal_rank"])
        for m in matrix:
            pf, vc, lt, be, fw = m["probfill_p02"], m["volcap_k05"], m["latency"], m["fee_breakeven"], m["forward_oos"]
            wr.writerow([
                m["book"], round(m["normal"]["monthly"] * 100, 4), round(m["normal"]["dd"] * 100, 2), m["normal"]["fills"],
                pf["fills"] if pf["fills"] is not None else "UNKNOWN",
                round(pf["monthly"] * 100, 4) if pf["monthly"] is not None else "UNKNOWN",
                pf["source"], vc["fills"] if vc["fills"] is not None else "UNKNOWN", vc["source"],
                lt["d2_fills"] if lt["d2_fills"] is not None else "UNKNOWN",
                round(lt["d2_monthly"] * 100, 4) if lt["d2_monthly"] is not None else "UNKNOWN",
                be["fraction"] if be["fraction"] is not None else "UNKNOWN",
                be["bps_at_1bp_eq_0p0001"] if be["bps_at_1bp_eq_0p0001"] is not None else "UNKNOWN",
                round(m["exec_stress"]["monthly"] * 100, 4), m["exec_stress"]["fills"],
                m["concentration"]["flag"][:50],
                round(fw["monthly"] * 100, 4) if fw["monthly"] is not None else "UNKNOWN",
                fw["fills"] if fw["fills"] is not None else "UNKNOWN",
                round(m["realistic_score"], 2), m["realistic_rank"], m["normal_rank"]])

    ranking = [{"realistic_rank": m["realistic_rank"], "book": m["book"], "branch": m["branch"],
                "realistic_score": round(m["realistic_score"], 2),
                "normal_rank": m["normal_rank"], "normal_Mo_pct": round(m["normal"]["monthly"] * 100, 4),
                "unknown_count": sum(1 for k in ("probfill_p02", "volcap_k05", "latency", "fee_breakeven", "forward_oos")
                                     if m[k]["status"] == "UNKNOWN" or m[k]["status"].startswith("UNKNOWN"))}
               for m in matrix]
    (OUT_DIR / "ranking.json").write_text(json.dumps(ranking, indent=1), encoding="utf-8")
    with open(OUT_DIR / "ranking.csv", "w", newline="", encoding="utf-8") as f:
        wr = csv.writer(f)
        wr.writerow(["realistic_rank", "book", "realistic_score", "normal_rank", "normal_Mo_pct", "unknown_count"])
        for r_ in ranking:
            wr.writerow([r_["realistic_rank"], r_["book"], r_["realistic_score"], r_["normal_rank"], r_["normal_Mo_pct"], r_["unknown_count"]])

    top = matrix[0]
    normal_top = normal_rank[0]
    summary = {
        "experiment": "opencode-r69a-realistic",
        "spec": "configs/opencode_v160_realistic.json (weights fixed BEFORE compiling; script loads them)",
        "test_policy": cfg["test_policy"],
        "weights": w,
        "formulas": cfg["formulas"],
        "books": [m["book"] for m in matrix],
        "ranking_realistic": [(m["realistic_rank"], m["book"], round(m["realistic_score"], 2)) for m in matrix],
        "ranking_normal": [(m["normal_rank"], m["book"], round(m["normal"]["monthly"] * 100, 4)) for m in normal_rank],
        "most_deployable_shaped": {
            "book": top["book"], "branch": top["branch"], "score": round(top["realistic_score"], 2),
            "why": ("Highest realistic score: DD-safe with shallow drawdown, strong exec retention, "
                    "highest fee headroom tier, indexed volcap intact, diffuse concentration; "
                    "it degrades least across the measured bundle even though it is NOT the Normal-monthly leader."),
            "distinct_from_most_profitable": f"Most PROFITABLE (Normal) is {normal_top['book']} "
            f"({round(normal_top['normal']['monthly']*100,4)}%/mo) but carries DD-breach and a NEGATIVE s0004-scope OOS; "
            f"most DEPLOYABLE-shaped is {top['book']} by least-degradation scoring.",
            "caveats": ["UNKNOWN prob-fill/latency on this book score 0 (conservative, not imputed)",
                        "fee BE is OLS-extrapolated, not a measured zero-crossing",
                        "DD is trade-candle-close sampled; exits market-like; no maker-queue claim from OHLC"],
        },
        "single_most_informative_next_measurement": {
            "proposal": "Seeded prob-fill p=0.2 (+1-tick adverse slippage) survival run on the realistic top-3 DD-safe books (band2confirmed, L3-combo, confirmed_dd_guard) with identical v30 RNG/seed protocol — PROPOSED ONLY, not run.",
            "why": ("Entry is the proven leak (42.9% touch-no-cross, v31); prob-fill is measured on only 2/8 books, "
                    "and the current top ranks hinge on UNKNOWN=0 there. A single v30-verbatim prob-fill pass on the "
                    "three DD-safe leaders would flip or confirm the ranking with one comparable number (fills + monthly + DD at p=0.2)."),
            "kill_criterion": "If a leader keeps fills>=30 but monthly halves vs control, it loses deployable-shape to the survivor; if all three collapse equally, the ranking stands and attention shifts to latency d2 on the same books.",
        },
        "unknown_cells": sum(r["unknown_count"] for r in ranking),
        "files": ["configs/opencode_v160_realistic.json", "scripts/opencode_r69a_realistic.py",
                  "artifacts/research/opencode_v160_realistic/robustness_matrix.json",
                  "artifacts/research/opencode_v160_realistic/robustness_matrix.csv",
                  "artifacts/research/opencode_v160_realistic/ranking.json",
                  "artifacts/research/opencode_v160_realistic/ranking.csv",
                  "artifacts/research/opencode_v160_realistic/summary.json"],
        "exploratory": True,
        "live_approved": False,
        "analysis_only": "read frozen summaries; no backtests, no training, no live orders; no registry/CONTINUOUS_RESEARCH/NEXT_AGENT/rounds writes; no commit/push",
    }
    (OUT_DIR / "summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print(json.dumps(summary["ranking_realistic"], indent=1))
    print("deployable:", summary["most_deployable_shaped"]["book"], "| profitable:", normal_top["book"])


if __name__ == "__main__":
    main()
