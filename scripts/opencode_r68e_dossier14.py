"""R68 E-dossier14: evidence compiler v14 — analysis ONLY, no backtests/training.

Extends R65 scripts/opencode_r65e_dossier13.py pattern (v13_r65, 109 table rows)
and configs/opencode_v153_dossier13.json (rounds 1-64):
reads configs/opencode_v157_dossier14.json (pre-spec: branch list + ranking
rules + queue + forward-readiness + forward-eval x4 + cloud-accounts +
capacity-verdict + strategic-options + reframe, written BEFORE compiling via
pre-registered prespec step: v153 deep-copy + 5 declared new rows), walks
artifacts/research/opencode_*/ summaries + portfolio.json files, copies EXACT
floats (never invents), and writes the v14 comparison dossier into a NEW dir
(never touches v13_r65/v13-r61/v12/v11/v10/v9/v8/v7/v6/v5/v4/v3/v2/v1):
  artifacts/research/opencode_dossier_v14/promotion_table.json
  artifacts/research/opencode_dossier_v14/promotion_table.csv
  artifacts/research/opencode_dossier_v14/summary.json (RANKING +
  CLOUD_TRACK + CLOUD_ACCOUNTS + CAPACITY_VERDICT + QUEUE +
  FORWARD_READINESS + FORWARD_EVAL x4 + REFRAME + STRATEGIC_OPTIONS +
  delta_vs_v13)
New vs v153 (rounds 65-67, 5 spec rows -> 5 table rows,
0 skipped-missing beyond carried student_harness): fwd_third_eval (v152
mae-isoall 3rd forward: NEGATIVE OOS -5.39%/-0.99%/mo DD-breach, fills PASS 46,
REJECT), fwd_majority (v154 FIRST forward of standing-best majority_1x:
+6.92%/+1.21%/mo DD-safe all 3, 11 fills REJECT fills+conc top1mo 149.3%;
s0004 scope NEGATIVE OOS -1.88%/mo), seal_verify_maj (v155 seal 4/4 PASS +
bit-identical repro, verification 12/12, methods), oosdecomp_reframe (v156
per-decision conversion FLAT 1.55%->1.62%, window arithmetic 6.00x,
gate-vote-only real decay, ~1850 decisions needed, methods), verify_12of12
(v155 majority repro bit-identical PASS, methods).
Carried 110 rows content-identical to v153 spec (verified in build step).
Exploratory labels only. No live orders. No registry writes. No overwriting
existing files.
"""
import csv
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPEC_PATH = os.path.join(ROOT, "configs", "opencode_v157_dossier14.json")
V153_PATH = os.path.join(ROOT, "configs", "opencode_v153_dossier13.json")
OUT_DIR = os.path.join(ROOT, "artifacts", "research", "opencode_dossier_v14")
V13_TABLE = os.path.join(ROOT, "artifacts", "research", "opencode_dossier_v13_r65",
                         "promotion_table.json")
FAMILIES_OLD = 109

SCEN_KEYS = ["normal", "fee_stress", "execution_stress"]


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def branch_container(doc):
    """Return {branch_name: node} handling results/branches/portfolio schemas."""
    if isinstance(doc, dict):
        for key in ("branches", "results"):
            if isinstance(doc.get(key), dict):
                return doc[key]
    return {}


def scenarios_of(node):
    """Return (scenarios dict, flat_bool). Same schema handling as v11/v10/v9/v8/v7/v6/v5/v4."""
    if not isinstance(node, dict):
        return {}, False
    sc = node.get("scenarios")
    if isinstance(sc, dict) and "normal" in sc:
        avail = {k: sc[k] for k in SCEN_KEYS if isinstance(sc.get(k), dict)}
        return avail, False
    if "normal" in node and isinstance(node["normal"], dict):
        avail = {k: node[k] for k in SCEN_KEYS if isinstance(node.get(k), dict)}
        return avail, False
    if "monthly_geometric_net" in node and "total_return" in node:
        return {"normal": node}, True
    return {}, False


def get_avail(doc_path, branch):
    """Extract available-scenario metric floats for one branch."""
    doc = load_json(doc_path)
    cont = branch_container(doc)
    if branch not in cont:
        raise KeyError("branch %r not in %s" % (branch, doc_path))
    scen, flat = scenarios_of(cont[branch])
    if "normal" not in scen:
        raise KeyError("branch %r has no normal metrics in %s" % (branch, doc_path))
    out = {}
    for s, m in scen.items():
        out[s] = {
            "total_return": m["total_return"],
            "max_drawdown": m["max_drawdown"],
            "monthly_geometric_net": m["monthly_geometric_net"],
            "trades": m["trades"],
            "profit_factor": m["profit_factor"],
            "win_rate": m["win_rate"],
        }
    return out, flat


def load_concentration():
    """Map measured branch -> short flag string from v61/v62 (else absent)."""
    flags = {}
    for path in (
        os.path.join(ROOT, "artifacts", "research", "opencode_v61_monthattr", "summary.json"),
        os.path.join(ROOT, "artifacts", "research", "opencode_v62_v38conc", "summary.json"),
    ):
        if not os.path.exists(path):
            continue
        doc = load_json(path)
        branches = doc.get("branches", [])
        if not isinstance(branches, list):
            continue
        for b in branches:
            name = b.get("branch")
            if not name or name in flags:
                continue
            tc = b.get("trade_concentration", {}) or {}
            conc = b.get("concentration", {}) or {}
            top5 = tc.get("top5_trades_share")
            neg = conc.get("n_negative")
            nmo = conc.get("n_months_total")
            verdict = b.get("verdict", "?")
            flag = "%s top5=%s" % (verdict, ("%.1f%%" % (top5 * 100)) if top5 is not None else "?")
            if neg is not None and nmo is not None:
                flag += " neg%d/%d" % (neg, nmo)
            flags[name] = flag
    return flags


def yn(cond):
    return "y" if cond else "n"


SPECIAL_BRANCH_LABEL = {
    "v55_infradead": "no-branch (infra ERROR x3 at v3 time; retest=v55c COMPLETE-DEAD, see v55c_rankonly row)",
    "paper_rehearsal": "138-intent rehearsal (ops only)",
    "paper_38iso_trip": "37-intent 38iso run, first real UNDER trip (ops only)",
    "resume_proven": "138/138 kill+resume parity (ops only)",
    "verify_3of3": "v79+v88+v92 bit-identical PASS (methods only)",
    "verify_4of4": "v79+v88+v92+v98 bit-identical PASS (methods only)",
    "fwd_machine": "majority HOLD validation + opened-date refusal (infra only)",
    "gatecheck_validated": "3/3 vs ledger (infra only)",
    "monthattr": "4-branch concentration evidence (methods only)",
    "v41_staged": "package-ready, smoke-proven, SUBMIT-DISPATCHED round34 (no numbers yet)",
    "v41_acc2_running": "COMPLETE-DEAD on account-2, see v41_dead row (terminal)",
    "quota_failover": "acc1 quota-block infra event (no numbers)",
    "clock_clean": "all-5-TFs CLEAN",
    "audit_1m": "63-trade 1m replay",
    "v55c_bench": "GTX1650 bench 321.50ms/window, 19.75MB VRAM (infra only)",
    "forward_sealed": "48,819 klines + 509 funding + 233 macro, SEAL pristine (asset only)",
    "fwfeatures_sealed": "679 forward decisions x133 features, seal intact (asset only)",
    "distill_targets": "soft-targets (4076,16) + teacher diagnostic (asset only)",
    "scorediag_v38v55c": "value-prior mechanism diagnostic (methods only)",
    "v96_staged": "8.77M Transformer staged, smoke-proven (no numbers yet)",
    "promorunner_validated": "integrated promote CLI 3/3 + 11/11 tests (infra only)",
    "fwdshakedown_weak": "Kronos-mini zero-shot FORWARD weak REJECT (methods only, excluded from ranking)",
    "seal_verified_4of4": "seal 4/4 PASS + bit-identical repro (methods only)",
    "fwdonly_path": "FORWARD_ONLY verdict path + Kronos REJECT re-verdict (infra only)",
    "gatecheck_none_safe": "None-safe patch 4/4 incl losing book (infra only)",
    "v55b_staging_fix_missing": "staging lacks allowlist fix, correct hold (process catch, no numbers)",
    "conc_rescued_veto": "rescued-leg concentration veto evidence (methods only)",
    "teacherlose_guidance": "quiet-market teacher-lose diagnostic (methods only)",
    "student_staged": "0.6M distill-student staged, queued 8th (no numbers yet)",
    "verify_5of5": "v79+v88+v92+v98+v104 bit-identical PASS (methods only)",
    "verify_6of6": "v79+v88+v92+v98+v104+v115 bit-identical PASS incl v41-valfit (methods only)",
    "conc_v41_worst": "v41 identity+valfit concentration WORST ever (methods only)",
    "v55bfix_acc2_running": "COMPLETE-DEAD on account-2, see v55bfix_dead row (terminal)",
    "conc_v55bfix_fail": "losing book hard FAIL (methods only)",
    "verify_7of7": "v79+v88+v92+v98+v104+v115+v122 bit-identical PASS (methods only)",
    "v96_running": "COMPLETE-DEAD on account-2, see v96_dead_worst row (terminal)",
    "scorediag_v96_attention": "attention-close mechanism diagnostic (methods only)",
    "verify_8of8": "v79+v88+v92+v98+v104+v115+v122+v125 bit-identical PASS (methods only)",
    "verify_9of9": "v79+v88+v92+v98+v104+v115+v122+v125+v128 bit-identical PASS incl v96 (methods only)",
    "conc_v96_fail": "losing book hard FAIL (methods only)",
    "student_running": "SUBMITTED acc2 r47 record (FROZEN: r49 terminal state is student_infradead row; r53 audit is student_dead row)",
    "student_infradead": "r49 kernel ERROR missing-module family, fix known, M rebuilt r50 (no numbers yet)",
    "seal_prep": "v136 PREP-READY verifier skeleton (infra only; FINAL 4/4 PASS is seal_final row)",
    "verify_10of10": "v79+v88+v92+v98+v104+v115+v122+v125+v128+v133 bit-identical PASS incl scorediag anchors (methods only)",
    "attndistill_stop": "STOP pre-packaging 0 submissions, attention family FULLY closed (no numbers)",
    "seal_final": "v136 FINAL seal 4/4 PASS + bit-identical repro vs completed L artifacts (methods only)",
    "student_rebuild": "r50 M-v106rebuild WITH fix + SUBMITTED acc2 RUNNING -> terminal COMPLETE-DEAD r53, see student_dead row (process record)",
    "verify_11of11": "v149 regime-identity normal+fee055 bit-identical PASS (methods only)",
    "seal_verify_maj": "seal 4/4 PASS + bit-identical majority repro (methods only)",
    "oosdecomp_reframe": "per-decision conversion flat + window arithmetic (methods only)",
    "verify_12of12": "11/11 + v155 majority repro bit-identical PASS (methods only)",
}


def load_forward_block(doc_path, branch):
    """Exact floats for one forward branch, straight from the forward summary artifact."""
    m, _ = get_avail(doc_path, branch)
    return m


def main():
    spec = load_json(SPEC_PATH)
    gate = spec["gate"]
    # Build-step check: carried spec rows (all but the 5 declared new) identical to v153.
    v153 = load_json(V153_PATH)
    assert len(spec["rows"]) == len(v153["rows"]) + 5, \
        "v157 must be v153 + 5 new spec rows"
    assert json.dumps(spec["rows"][:len(v153["rows"])], sort_keys=True) == \
        json.dumps(v153["rows"], sort_keys=True), "carried rows must be content-identical to v153"
    conc_map = load_concentration()
    conc_spec = spec.get("concentration", {})
    rows = []
    missing = []
    for fam in spec["rows"]:
        family = fam["family"]
        apath = fam["artifact"]
        full = os.path.join(ROOT, apath)
        if not os.path.exists(full):
            missing.append({"family": family, "artifact": apath,
                            "note": "artifact not found; skipped, no numbers invented"})
            continue
        if fam.get("special"):
            rows.append({
                "family": family,
                "best_branch": SPECIAL_BRANCH_LABEL.get(family, "n/a (non-portfolio)"),
                "normal_Ret": None,
                "normal_DD": None,
                "normal_Mo": None,
                "normal_fills": None,
                "normal_PF": None,
                "normal_WR": None,
                "fee_Mo": None,
                "exec_Mo": None,
                "exec_fills": None,
                "dd_gate_all3": "n/a",
                "fills_gate_all3": "n/a",
                "scenarios_available": "n/a (non-portfolio)",
                "monthly_best": fam["special_finding"],
                "concentration_flag": "n/a",
                "verdict": fam["verdict"],
                "artifact_path": apath,
                "note": "special=%s: finding string only, no portfolio floats exist" % fam["special"],
            })
            continue
        best_branch, best_m = None, None
        best_flat = False
        per_branch = {}
        per_flat = {}
        branch_missing = []
        for br in fam["candidates"]:
            try:
                m, flat = get_avail(full, br)
                per_branch[br] = m
                per_flat[br] = flat
            except (KeyError, ValueError, TypeError) as e:
                branch_missing.append({"branch": br, "note": str(e)})
        if branch_missing:
            missing.append({"family": family, "artifact": apath, "branch_notes": branch_missing})
        if not per_branch:
            continue
        for br, m in per_branch.items():
            mo = m["normal"]["monthly_geometric_net"]
            if best_m is None or mo > best_m["normal"]["monthly_geometric_net"]:
                best_branch, best_m, best_flat = br, m, per_flat[br]
        avail = [s for s in SCEN_KEYS if s in best_m]
        n = best_m["normal"]
        f = best_m.get("fee_stress")
        e = best_m.get("execution_stress")
        dd_all3 = all(abs(best_m[s]["max_drawdown"]) <= gate["dd_max"] for s in avail)
        fills_all3 = all(best_m[s]["trades"] >= gate["fills_min"] for s in avail)
        note = None
        if best_flat:
            note = ("fee-ladder flat schema: branch node IS one fee tier (fee=%.4f); "
                    "no fee/exec stress scenarios in this experiment" % (
                        load_json(full)["branches"][best_branch].get("fee_rate_per_fill", float("nan"))))
        elif len(avail) < 3:
            note = "partial scenarios only (%s); gates computed over available scenarios" % ",".join(avail)
        if fam.get("finding"):
            monthly_best = fam["finding"]
        else:
            monthly_best = max(best_m[s]["monthly_geometric_net"] for s in avail)
        if fam.get("conc_flag"):
            cflag = fam["conc_flag"]
        else:
            conc_key = conc_spec.get(family, "")
            conc_branch = conc_key.split(":", 1)[1].split(" (")[0] if ":" in conc_key else None
            if conc_branch and conc_branch in conc_map:
                cflag = conc_map[conc_branch]
                if family == "band2confirmed":
                    cflag += " (measured on 1x variant)"
                if family == "v38_isoall":
                    cflag += " CONCENTRATED (top5 71.3%)"
            else:
                cflag = "unknown"
        row = {
            "family": family,
            "best_branch": best_branch,
            "normal_Ret": n["total_return"],
            "normal_DD": n["max_drawdown"],
            "normal_Mo": n["monthly_geometric_net"],
            "normal_fills": n["trades"],
            "normal_PF": n["profit_factor"],
            "normal_WR": n["win_rate"],
            "fee_Mo": f["monthly_geometric_net"] if f else None,
            "exec_Mo": e["monthly_geometric_net"] if e else None,
            "exec_fills": e["trades"] if e else None,
            "dd_gate_all3": yn(dd_all3),
            "fills_gate_all3": yn(fills_all3),
            "scenarios_available": ",".join(avail),
            "monthly_best": monthly_best,
            "concentration_flag": cflag,
            "verdict": fam["verdict"],
            "artifact_path": apath,
        }
        if fam.get("forward_only"):
            row["forward_only"] = True
            row["note"] = ("FORWARD-window only (2026-03-23->2026-09-08 sealed OOS); "
                           "excluded from opened-interval ranking; "
                           + ((" " + note) if note else ""))
        elif note:
            row["note"] = note
        rows.append(row)

    # Opened-interval ranking only: forward-OOS rows never compete with in-sample books.
    ranked = [r for r in rows
              if r["normal_Mo"] is not None and r["normal_PF"] is not None
              and not r.get("forward_only")]
    fwd_rows = [r for r in rows if r.get("forward_only")]

    # Forward blocks: exact floats from artifacts (transcription check vs pre-spec).
    fe_src = os.path.join(ROOT, spec["forward_eval"]["source"])
    fe2_src = os.path.join(ROOT, spec["forward_eval2"]["source"])
    fe3_src = os.path.join(ROOT, spec["forward_eval3"]["source"])
    fe4_src = os.path.join(ROOT, spec["forward_eval4"]["source"])
    fe_branch = spec["forward_eval"]["branch"]
    fe2_branch = spec["forward_eval2"]["branch"]
    fe3_branch = spec["forward_eval3"]["branch"]
    fe4_branch = spec["forward_eval4"]["branch"]
    fe = load_forward_block(fe_src, fe_branch)
    fe2 = load_forward_block(fe2_src, fe2_branch)
    fe3 = load_forward_block(fe3_src, fe3_branch)
    fe4 = load_forward_block(fe4_src, fe4_branch)
    for scen in SCEN_KEYS:
        for key in ("total_return", "max_drawdown", "monthly_geometric_net",
                    "trades", "profit_factor", "win_rate"):
            assert fe[scen][key] == spec["forward_eval"][scen][key], \
                "forward_eval transcription mismatch %s.%s" % (scen, key)
            assert fe2[scen][key] == spec["forward_eval2"][scen][key], \
                "forward_eval2 transcription mismatch %s.%s" % (scen, key)
            assert fe3[scen][key] == spec["forward_eval3"][scen][key], \
                "forward_eval3 transcription mismatch %s.%s" % (scen, key)
            assert fe4[scen][key] == spec["forward_eval4"][scen][key], \
                "forward_eval4 transcription mismatch %s.%s" % (scen, key)

    if os.path.exists(OUT_DIR):
        print("REFUSE: %s already exists (no overwrites)" % OUT_DIR)
        return 1
    os.makedirs(OUT_DIR, exist_ok=False)
    with open(os.path.join(OUT_DIR, "promotion_table.json"), "w", encoding="utf-8") as fh:
        json.dump({
            "experiment": "opencode-r68e-dossier14",
            "spec": "configs/opencode_v157_dossier14.json",
            "extends": "artifacts/research/opencode_dossier_v13_r65/promotion_table.json (v13_r65, 109 families; untouched) + configs/opencode_v153_dossier13.json (carried rows; untouched)",
            "gate": gate,
            "n_rows": len(rows),
            "n_portfolio_rows": len(ranked),
            "n_forward_rows": len(fwd_rows),
            "n_special_rows": len(rows) - len(ranked) - len(fwd_rows),
            "rows": rows,
            "missing_skipped": missing,
            "pipeline_verdicts": spec.get("pipeline_verdicts"),
            "cloud_track": spec.get("cloud_track"),
            "cloud_accounts": spec.get("cloud_accounts"),
            "capacity_verdict": spec.get("capacity_verdict"),
            "queue_exact_order": spec.get("queue_exact_order"),
            "queue_note": spec.get("queue_note"),
            "forward_readiness": spec.get("forward_readiness"),
            "forward_eval": spec.get("forward_eval"),
            "forward_eval2": spec.get("forward_eval2"),
            "forward_eval3": spec.get("forward_eval3"),
            "forward_eval4": spec.get("forward_eval4"),
            "reframe": spec.get("reframe"),
            "strategic_options": spec.get("strategic_options"),
            "exploratory": True,
            "live_approved": False,
            "warning": ("EXPLORATORY on the opened 2023-2026 development interval only, plus FOUR sealed "
                        "forward OOS passes (v135 + v138 + v152 + v154). Exact floats copied from artifacts; "
                        "nothing refit. No promotion claim. Drawdown is trade-candle-close sampled. "
                        "Stop/timeout exits are market-like. fwd_first_eval carries v135 floats, "
                        "fwd_second_eval v138 floats, fwd_third_eval v152 floats and fwd_majority v154 floats "
                        "(FORWARD-window only, excluded from opened-interval ranking; machine FORWARD_ONLY "
                        "REJECT all four: v135/v138/v154 on fills+concentration, v152 on monthly+DD+concentration "
                        "with fills passing). seal_verify_maj carries the v155 4/4 seal PASS + bit-identical "
                        "repro (verify 12/12); oosdecomp_reframe carries the v156 window-arithmetic reframe "
                        "(analysis only, engine never called). student_running is the frozen r47 SUBMITTED "
                        "record; student_infradead is the r49 terminal ERROR record; student_dead is the r53 "
                        "COMPLETE-DEAD audit (no numbers on the first two rows). student_harness has no "
                        "summary.json and is skipped-missing (harness readiness carried in QUEUE/cloud-track "
                        "only). v13_r65 warning lineage otherwise stands (rank-best maelabels COMPLETE-DEAD, "
                        "rescued-leg concentration vetoes, verify methods-only rows, fee-ladder 8/8 close, "
                        "seal/fwdonly infra rows, paper rehearsals/resume as OPENED-interval ops only). "
                        "REFRAME is arithmetic, not a promotion claim: majority forward stays REJECT. "
                        "Strategic options are a catalog only; NO new research was conducted."),
        }, fh, indent=2)

    cols = spec["csv_columns"]
    with open(os.path.join(OUT_DIR, "promotion_table.csv"), "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(cols)
        for r in rows:
            w.writerow([(repr(r[c]) if isinstance(r[c], float) else ("" if r[c] is None else r[c])) for c in cols])

    # ---- rankings (rules pre-specified in v157; opened-interval only) ----
    by_mo = sorted(ranked, key=lambda r: r["normal_Mo"], reverse=True)
    top5 = by_mo[:5]
    by_risk = sorted(ranked, key=lambda r: (-r["normal_PF"], -r["normal_DD"]))
    top3 = by_risk[:3]
    qual = [r for r in ranked
            if r["normal_Mo"] >= gate["monthly_min"]
            and r["dd_gate_all3"] == "y" and r["fills_gate_all3"] == "y"
            and r["fee_Mo"] is not None and r["exec_Mo"] is not None
            and len(r["scenarios_available"].split(",")) == 3]

    def mo_pct(x):
        return "%.4f%%" % (x * 100)

    def fills_str(r):
        return "%d/%s" % (r["normal_fills"], r["exec_fills"] if r["exec_fills"] is not None else "n/a")

    fev = spec.get("forward_eval", {})
    fev2 = spec.get("forward_eval2", {})
    fev3 = spec.get("forward_eval3", {})
    fev4 = spec.get("forward_eval4", {})
    refr = spec.get("reframe", {})
    cap = spec.get("capacity_verdict", {})
    strat = spec.get("strategic_options", [])
    rank_lines = []
    rank_lines.append("EXPLORATORY dossier v14 covering rounds 1-67, %d rows (109 v13_r65-carried + %d new); gate Mo>=5%% + DD<=20%%(all3) + fills>=30(all3); Normal-first reporting; forward OOS x4 excluded from opened-interval ranking." % (len(rows), len(rows) - FAMILIES_OLD))
    for i, r in enumerate(top5, 1):
        rank_lines.append(
            "%d. %s Mo=%s DD=%s fills=%s PF=%.2f WR=%.1f%% dd3=%s fills3=%s [%s]" % (
                i, r["best_branch"], mo_pct(r["normal_Mo"]), mo_pct(r["normal_DD"]),
                fills_str(r), r["normal_PF"], r["normal_WR"] * 100,
                r["dd_gate_all3"], r["fills_gate_all3"], r["verdict"]))
    rank_lines.append("Top-3 risk-adjusted (Normal PF desc, DD tie-break closest-to-zero):")
    for i, r in enumerate(top3, 1):
        rank_lines.append(
            "%d. %s PF=%.2f DD=%s Mo=%s fills=%d [%s; conc=%s]" % (
                i, r["best_branch"], r["normal_PF"], mo_pct(r["normal_DD"]),
                mo_pct(r["normal_Mo"]), r["normal_fills"], r["verdict"], r["concentration_flag"]))
    rank_lines.append("Paper candidate recommendation:")
    if qual:
        q = qual[0]
        rank_lines.append("CANDIDATE: %s Mo=%s dd3=%s fills3=%s [%s]" % (
            q["best_branch"], mo_pct(q["normal_Mo"]), q["dd_gate_all3"], q["fills_gate_all3"], q["verdict"]))
        rank_lines.append("Missing before paper: forward out-of-sample test + live-weight pipeline + kill-switch drill on same book.")
    else:
        dd_safe = [r for r in ranked if r["dd_gate_all3"] == "y"]
        dd_safe_max = max([r["normal_Mo"] for r in dd_safe]) if dd_safe else 0.0
        rank_lines.append("NONE qualifies: ceiling %s/mo < 5%% gate; every DD-safe opened book is <=%s/mo; monthly-top1 carries DD-breach; forward x4 OOS all machine-REJECT (v38-isoall +13.11%%/2.24%%/mo fills 17/17/14<30 + top1mo 68.9%%; v33-topdec +5.36%%/0.94%%/mo fills 10/10/8<30 + top1mo 65.4%%; v152 mae-isoall -5.39%%/-0.99%%/mo DD-breach fills PASS 46; v154 majority_1x +6.92%%/+1.21%%/mo DD-safe fills 11/11/11<30 + top1mo 149.3%%, s0004 scope NEGATIVE -1.88%%); seal 4/4 PASS + repro 12/12 trust the numbers but change no verdict; oosdecomp reframes fills as window arithmetic (~1850 decisions needed); verify 12/12 methods-only; rescued legs concentration-vetoed (top5 74-89%%); queue EMPTY, cloud program CLOSED." % (
            mo_pct(top5[0]["normal_Mo"]) if top5 else "n/a", mo_pct(dd_safe_max)))
        rank_lines.append("Missing pieces: gate-passing frozen candidate (forward line has 4 OOS points; fee 8/8 closed with BE ranking majority 79 < PF7 140 < v41 239 < combo 510 < s0004 544 < confirmed 808; verify 12/12 methods-only; window+protocol READY and exercised 4x but window TOO SHORT (see REFRAME: monthly re-crawl, re-eval at 12mo and 15mo marks); concentration relief not needed for L2/L3, both diffuse PASS).")
    if missing:
        rank_lines.append("Skipped %d missing/partial: %s." % (
            len(missing), "; ".join(m.get("family", "?") for m in missing)))
    else:
        seen, uniq = set(), []
        for r in by_mo:
            key = (r["normal_Ret"], r["normal_DD"], r["normal_Mo"], r["normal_fills"], r["normal_PF"], r["normal_WR"])
            if key not in seen:
                seen.add(key)
                uniq.append(r["best_branch"])
        rank_lines.append("All %d present, none invented. s0004 book repeats across L2/poolsess/feeBE rows; unique-book top5: %s." % (
            len(rows), ", ".join(uniq[:5])))
    rank_lines.append("QUEUE (EMPTY, cloud program CLOSED: no jobs running, nothing staged):")
    if spec.get("queue_exact_order"):
        for q in spec["queue_exact_order"]:
            rank_lines.append("Q: %s" % q)
    else:
        rank_lines.append("Q: (empty) v152/v154 forwards + v155 seal + v156 decomp done; all model lines terminal COMPLETE-DEAD; dead lines never re-queued; forward line waits on re-crawled window (see REFRAME).")
    rank_lines.append("CAPACITY-VERDICT (FINAL, bigger!=better AND distill-closed AND regime/MAE-closed, standalone mortality 15/15, 0.45M->8.77M; rounds 65-67 ran NO new trained models, carried identical):")
    rank_lines.append("RANK by rank_corr: maelabels-v146 +0.0759 NEW BEST (0.6M) > regime-v145 +0.0741 (0.6M) > v41 +0.0727 (0.6M) > v38 +0.066 > student-v137 +0.0568 (0.6M distill, < teacher) > v40 +0.052 > v55c +0.022 > v28 +0.018 > v55bfix +0.0166 > v35 -0.0105 > v33 -0.028 > v96 -0.03422 WORST (8.77M); v39 flat-killed, A1/A2 n/a; monthly all < gate (best fresh 2.62% regime DD-breach, maelabels 1.36% DD-breach, maelabelscal 2.27% DD-breach); verdict: scale, regime-specialization, MAE-labels AND distill all REJECTED as cures; calibrate helps-monthly-costs-DD on bias-dominated bases, hurts strong ones; queue EMPTY.")
    rank_lines.append("CLOUD-ACCOUNTS (spend both accounts):")
    for acc in ("account1", "account2"):
        a = spec.get("cloud_accounts", {}).get(acc, {})
        rank_lines.append("%s (%s, %s) | quota: %s | spend: %s" % (
            acc, a.get("key"), a.get("username"), a.get("quota"), a.get("spend")))
    rank_lines.append("FORWARD-FIRST-EVAL (v38-isoall OOS %s):" % fev.get("window", "?"))
    fen, fef, fee_ = (fe["normal"], fe["fee_stress"], fe["execution_stress"])
    rank_lines.append("FWD %s | normal Ret=%.2f%% DD=%s Mo=%s fills=%d PF=%.2f WR=%.1f%% | fee Mo=%s fills=%d | exec Mo=%s fills=%d | machine: %s" % (
        fev.get("branch", "?"), fen.get("total_return", 0.0) * 100, mo_pct(fen.get("max_drawdown", 0.0)),
        mo_pct(fen.get("monthly_geometric_net", 0.0)), fen.get("trades", -1),
        fen.get("profit_factor", 0.0), fen.get("win_rate", 0.0) * 100,
        mo_pct(fef.get("monthly_geometric_net", 0.0)), fef.get("trades", -1),
        mo_pct(fee_.get("monthly_geometric_net", 0.0)), fee_.get("trades", -1),
        fev.get("machine", "?")))
    rank_lines.append("FORWARD-SECOND-EVAL (v33-topdec OOS %s):" % fev2.get("window", "?"))
    f2n, f2f, f2e = (fe2["normal"], fe2["fee_stress"], fe2["execution_stress"])
    rank_lines.append("FWD %s | normal Ret=%.2f%% DD=%s Mo=%s fills=%d PF=%.2f WR=%.1f%% | fee Mo=%s fills=%d | exec Mo=%s fills=%d | machine: %s" % (
        fev2.get("branch", "?"), f2n.get("total_return", 0.0) * 100, mo_pct(f2n.get("max_drawdown", 0.0)),
        mo_pct(f2n.get("monthly_geometric_net", 0.0)), f2n.get("trades", -1),
        f2n.get("profit_factor", 0.0), f2n.get("win_rate", 0.0) * 100,
        mo_pct(f2f.get("monthly_geometric_net", 0.0)), f2f.get("trades", -1),
        mo_pct(f2e.get("monthly_geometric_net", 0.0)), f2e.get("trades", -1),
        fev2.get("machine", "?")))
    rank_lines.append("FORWARD-THIRD-EVAL (mae-isoall OOS %s):" % fev3.get("window", "?"))
    f3n, f3f, f3e = (fe3["normal"], fe3["fee_stress"], fe3["execution_stress"])
    rank_lines.append("FWD %s | normal Ret=%.2f%% DD=%s Mo=%s fills=%d PF=%.2f WR=%.1f%% | fee Mo=%s fills=%d | exec Mo=%s fills=%d | machine: %s" % (
        fev3.get("branch", "?"), f3n.get("total_return", 0.0) * 100, mo_pct(f3n.get("max_drawdown", 0.0)),
        mo_pct(f3n.get("monthly_geometric_net", 0.0)), f3n.get("trades", -1),
        f3n.get("profit_factor", 0.0), f3n.get("win_rate", 0.0) * 100,
        mo_pct(f3f.get("monthly_geometric_net", 0.0)), f3f.get("trades", -1),
        mo_pct(f3e.get("monthly_geometric_net", 0.0)), f3e.get("trades", -1),
        fev3.get("machine", "?")))
    rank_lines.append("FORWARD-MAJORITY-EVAL (standing-best majority OOS %s):" % fev4.get("window", "?"))
    f4n, f4f, f4e = (fe4["normal"], fe4["fee_stress"], fe4["execution_stress"])
    rank_lines.append("FWD %s | normal Ret=%.2f%% DD=%s Mo=%s fills=%d PF=%.2f WR=%.1f%% | fee Mo=%s fills=%d | exec Mo=%s fills=%d | machine: %s" % (
        fev4.get("branch", "?"), f4n.get("total_return", 0.0) * 100, mo_pct(f4n.get("max_drawdown", 0.0)),
        mo_pct(f4n.get("monthly_geometric_net", 0.0)), f4n.get("trades", -1),
        f4n.get("profit_factor", 0.0), f4n.get("win_rate", 0.0) * 100,
        mo_pct(f4f.get("monthly_geometric_net", 0.0)), f4f.get("trades", -1),
        mo_pct(f4e.get("monthly_geometric_net", 0.0)), f4e.get("trades", -1),
        fev4.get("machine", "?")))
    rank_lines.append("FWD verdict (all four): OOS monthly mixed (v38/v33/majority positive-thin, mae-isoall negative); fills-fail 3/4 is window arithmetic per v156 (only v152 passes fills 46 but fails monthly+DD); seals intact, metrics-once each, no pass-5.")
    rank_lines.append("REFRAME (v156 window-length arithmetic + longer-window need + re-crawl proposal):")
    wa = refr.get("window_arithmetic", {})
    rank_lines.append("window math: decision RATE identical IS %.1f vs FW %.1f/mo; per-decision fill conversion FLAT %.4f%%->%.4f%% (+%.1f%% rel); absolute gap %d vs %d fills = %.2fx window-length ratio (%d decisions/%.2fmo vs %d/%.2fmo), not model collapse." % (
        wa.get("is_decisions_per_month", 0.0), wa.get("fw_decisions_per_month", 0.0),
        wa.get("is_fills_per_decision", 0.0) * 100, wa.get("fw_fills_per_decision", 0.0) * 100,
        wa.get("fills_per_decision_rel_change", 0.0) * 100,
        wa.get("is_fills", -1), wa.get("fw_fills", -1), wa.get("decision_ratio", 0.0),
        wa.get("is_decisions", -1), wa.get("is_months", 0.0),
        wa.get("fw_decisions", -1), wa.get("fw_months", 0.0)))
    rank_lines.append("only real decay: %s" % refr.get("only_real_decay", "?"))
    nw = refr.get("needed_window", {})
    rank_lines.append("needed: %d fills / %.4f%% conversion = ~%d decisions (~%.1fmo at %.1f decisions/mo); at 12mo expect ~%.1f fills (still HOLD), at 15mo ~%.1f (gate-testable)." % (
        nw.get("fills_gate", -1), nw.get("fw_conversion", 0.0) * 100, nw.get("decisions_needed", -1),
        nw.get("months_at_fw_rate", 0.0), wa.get("fw_decisions_per_month", 0.0),
        nw.get("at_12mo_expect_fills", 0.0), nw.get("at_15mo_expect_fills", 0.0)))
    rank_lines.append("proposal: %s" % " | ".join(refr.get("recrawl_proposal", [])))
    rank_lines.append("STRATEGIC-OPTIONS (untried only, cost/benefit each, NO new research conducted):")
    for i, s in enumerate(strat, 1):
        rank_lines.append("SO%d. %s [%s]" % (i, s.get("option", "?"), s.get("status", "?")))
        rank_lines.append("cost: %s" % s.get("cost", "?"))
        rank_lines.append("benefit: %s" % s.get("benefit", "?"))
    rank_lines.append("Files: artifacts/research/opencode_dossier_v14/{promotion_table.json,promotion_table.csv,summary.json} + scripts/opencode_r68e_dossier14.py + configs/opencode_v157_dossier14.json (v13_r65/v13-r61/v12/v11/v10/v9/v8/v7/v6/v5/v4/v3/v2/v1 untouched).")
    assert len(rank_lines) == 37 + 3 * len(strat), \
        "RANKING must be exactly 37+3*strat lines, got %d" % len(rank_lines)

    # ---- delta vs v13_r65 (read-only comparison, no recompute) ----
    delta13 = {"v13_top5_monthly": [], "v14_top5_monthly": [r["best_branch"] for r in top5],
               "new_monthly_no1": None, "risk_top3_changed": None, "note": ""}
    try:
        v13 = load_json(V13_TABLE)
        v13rows = v13.get("rows", [])
        v13ranked = [r for r in v13rows
                     if isinstance(r.get("normal_Mo"), (int, float)) and not r.get("forward_only")]
        v13top5 = sorted(v13ranked, key=lambda r: r["normal_Mo"], reverse=True)[:5]
        delta13["v13_top5_monthly"] = [r["best_branch"] for r in v13top5]
        delta13["new_monthly_no1"] = top5[0]["best_branch"] if top5 else None
        v13risk = sorted(v13ranked, key=lambda r: (-r["normal_PF"], -r["normal_DD"]))[:3]
        delta13["v13_top3_risk"] = [r["best_branch"] for r in v13risk]
        delta13["v14_top3_risk"] = [r["best_branch"] for r in top3]
        delta13["risk_top3_changed"] = ([r["best_branch"] for r in top3] != [r["best_branch"] for r in v13risk])
        delta13["monthly_top1_changed"] = ((top5[0]["best_branch"] if top5 else None) !=
                                          (v13top5[0]["best_branch"] if v13top5 else None))
        v13ceil = v13top5[0]["normal_Mo"] if v13top5 else 0.0
        v14ceil = top5[0]["normal_Mo"] if top5 else 0.0
        newfams13 = [r["family"] for r in rows if r["family"] not in {x.get("family") for x in v13rows}]
        delta13["new_families"] = newfams13
        delta13["note"] = ("Monthly top-1 changed=%s (v13_r65 %s %.4f%%/mo -> v14 %s %.4f%%/mo); "
                           "v14 opened ceiling still < 5%% gate. Risk top-3 RAW changed=%s. "
                           "New v14 table rows vs v13_r65: %s. Forward OOS x4 (excluded from ranking): "
                           "v38_isoall_fwd_1x +13.11%%/2.24%%/mo DD-safe + v33_topdec_fwd_1x +5.36%%/0.94%%/mo "
                           "DD-safe + mae_isoall_fwd_1x -5.39%%/-0.99%%/mo DD-breach (fills PASS 46) + "
                           "majority_1x +6.92%%/1.21%%/mo DD-safe (fills 11 REJECT, top1mo 149.3%%), all machine "
                           "REJECT. REFRAME (v156): per-decision conversion flat 1.55%%->1.62%%, ~1850 decisions "
                           "(~15mo) needed for fills gate; monthly re-crawl + re-eval at 12mo/15mo proposed." % (
                               delta13["monthly_top1_changed"],
                               delta13["v13_top5_monthly"][0] if delta13["v13_top5_monthly"] else "?",
                               v13ceil * 100,
                               delta13["new_monthly_no1"], v14ceil * 100,
                               delta13["risk_top3_changed"], ", ".join(newfams13)))
    except (OSError, ValueError, KeyError) as e:
        delta13["note"] = "v13_r65 table unreadable, delta skipped: %s" % e

    cloud_lines = []
    for m in spec.get("cloud_track", []):
        cloud_lines.append("%s | %s | audit: %s | lesson: %s" % (
            m.get("model"), m.get("status"), m.get("audit"), m.get("lesson")))

    accounts = spec.get("cloud_accounts", {})
    account_lines = []
    for acc in ("account1", "account2"):
        a = accounts.get(acc, {})
        account_lines.append("%s (%s, %s) | quota: %s | spend: %s | refs: %s" % (
            acc, a.get("key"), a.get("username"), a.get("quota"), a.get("spend"), a.get("refs")))

    cap_lines = []
    for t in (cap.get("table", [])):
        cap_lines.append("%s | %s | rank %s | Mo %s | DD %s | %s" % (
            t.get("model"), t.get("params"), t.get("rank_corr"),
            t.get("normal_monthly"), t.get("drawdown"), t.get("verdict")))

    strat_lines = []
    for s in strat:
        strat_lines.append("%s [%s] | cost: %s | benefit: %s" % (
            s.get("option"), s.get("status"), s.get("cost"), s.get("benefit")))
    strat_lines.append("Catalog only from program gaps (ledger rounds 1-67); NO new research conducted; "
                       "no labels inspected, no backtests run, no thresholds selected.")

    with open(os.path.join(OUT_DIR, "summary.json"), "w", encoding="utf-8") as fh:
        json.dump({
            "experiment": "opencode-r68e-dossier14",
            "spec": "configs/opencode_v157_dossier14.json",
            "branches_covered": len(rows),
            "families_old": FAMILIES_OLD,
            "families_new": len(rows) - FAMILIES_OLD,
            "families": [r["family"] for r in rows],
            "top5_monthly": [r["best_branch"] for r in top5],
            "top3_risk_adjusted": [r["best_branch"] for r in top3],
            "paper_recommendation": qual[0]["best_branch"] if qual else "NONE",
            "pipeline_verdicts": spec.get("pipeline_verdicts"),
            "RANKING": rank_lines,
            "CLOUD_TRACK": cloud_lines,
            "CLOUD_ACCOUNTS": account_lines,
            "CAPACITY_VERDICT": cap_lines + [cap.get("verdict", "")],
            "QUEUE": spec.get("queue_exact_order"),
            "QUEUE_NOTE": spec.get("queue_note"),
            "FORWARD_READINESS": spec.get("forward_readiness"),
            "FORWARD_EVAL": spec.get("forward_eval"),
            "FORWARD_EVAL2": spec.get("forward_eval2"),
            "FORWARD_EVAL3": spec.get("forward_eval3"),
            "FORWARD_EVAL4": spec.get("forward_eval4"),
            "REFRAME": spec.get("reframe"),
            "STRATEGIC_OPTIONS": strat_lines,
            "delta_vs_v13": delta13,
            "missing_skipped": missing,
            "exploratory": True,
            "live_approved": False,
        }, fh, indent=2)
    print("rows=%d (portfolio=%d forward=%d special=%d) missing=%d top1=%s paper=%s" % (
        len(rows), len(ranked), len(fwd_rows), len(rows) - len(ranked) - len(fwd_rows), len(missing),
        top5[0]["best_branch"] if top5 else "?", qual[0]["best_branch"] if qual else "NONE"))


if __name__ == "__main__":
    sys.exit(main())
