"""R48 E-dossier10: evidence compiler v10 — analysis ONLY, no backtests/training.

Extends R46 scripts/opencode_r46e_dossier9.py pattern (v9, 83 families):
reads configs/opencode_v134_dossier10.json (pre-spec: branch list + ranking
rules + queue + forward-readiness + cloud-accounts + capacity-verdict,
written BEFORE compiling), walks artifacts/research/opencode_*/ summaries +
portfolio.json files, copies EXACT floats (never invents), and writes the v10
comparison dossier into a NEW dir (never touches v9/v8/v7/v6/v5/v4/v3/v2/v1):
  artifacts/research/opencode_dossier_v10/promotion_table.json
  artifacts/research/opencode_dossier_v10/promotion_table.csv
  artifacts/research/opencode_dossier_v10/summary.json (RANKING +
  CLOUD_TRACK + CLOUD_ACCOUNTS + CAPACITY_VERDICT + QUEUE +
  FORWARD_READINESS + delta_vs_v9)
New vs v9 (rounds 46-47, 7 rows): v96_dead_worst (v96b Transformer
COMPLETE-DEAD worst-ever: rank -0.034 negative, bias +5.79 worst, monthly
negative all 3, DD-breach, portfolio), scorediag_v96_attention (v127
attention-close mechanism: peaky softmax fits train order, methods),
verify_8of8 (v125 bit-identical PASS, methods), verify_9of9 (v128
bit-identical PASS incl v96, methods), conc_v96_fail (v129 losing-book hard
FAIL, methods), feeBE_v96_undefined (v130 flat schema, BE
undefined-negative, closes 8/8 ladder set, portfolio-flat),
student_running (v106 SUBMITTED RUNNING acc2, pending).
Carried 83 rows byte-identical to v9 spec (verified in build step).
Exploratory labels only. No live orders. No registry writes. No overwriting
existing files.
"""
import csv
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPEC_PATH = os.path.join(ROOT, "configs", "opencode_v134_dossier10.json")
OUT_DIR = os.path.join(ROOT, "artifacts", "research", "opencode_dossier_v10")
V8_TABLE = os.path.join(ROOT, "artifacts", "research", "opencode_dossier_v8",
                         "promotion_table.json")
V9_TABLE = os.path.join(ROOT, "artifacts", "research", "opencode_dossier_v9",
                         "promotion_table.json")
FAMILIES_OLD = 83

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
    """Return (scenarios dict, flat_bool). Same schema handling as v9/v8/v7/v6/v5/v4."""
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
    "student_running": "SUBMITTED RUNNING acc2, pending audit (no numbers yet)",
}


def main():
    spec = load_json(SPEC_PATH)
    gate = spec["gate"]
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
        rows.append({
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
        })
        if note:
            rows[-1]["note"] = note

    ranked = [r for r in rows if r["normal_Mo"] is not None and r["normal_PF"] is not None]

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, "promotion_table.json"), "w", encoding="utf-8") as fh:
        json.dump({
            "experiment": "opencode-r48e-dossier10",
            "spec": "configs/opencode_v134_dossier10.json",
            "extends": "artifacts/research/opencode_dossier_v9/promotion_table.json (v9, 83 families; untouched)",
            "gate": gate,
            "n_rows": len(rows),
            "n_portfolio_rows": len(ranked),
            "n_special_rows": len(rows) - len(ranked),
            "rows": rows,
            "missing_skipped": missing,
            "pipeline_verdicts": spec.get("pipeline_verdicts"),
            "cloud_track": spec.get("cloud_track"),
            "cloud_accounts": spec.get("cloud_accounts"),
            "capacity_verdict": spec.get("capacity_verdict"),
            "queue_exact_order": spec.get("queue_exact_order"),
            "queue_note": spec.get("queue_note"),
            "forward_readiness": spec.get("forward_readiness"),
            "exploratory": True,
            "live_approved": False,
            "warning": ("EXPLORATORY on the opened 2023-2026 development interval only. "
                        "Exact floats copied from artifacts; nothing refit. No promotion claim. "
                        "Drawdown is trade-candle-close sampled. Stop/timeout exits are market-like. "
                        "v55c_rankonly carries v55d replay floats (COMPLETE-DEAD); v55_infradead is the "
                        "frozen v3-time record. v55ccal_rescue carries v97 floats (rankonly+isoall rescue). "
                        "v41_dead carries v91b replay floats (COMPLETE-DEAD rank-best-bias-killer); "
                        "scopes33_rescued_dead carries v107 floats (scopes dead on rescued leg). "
                        "v41_valfit_dead carries v112 floats (TRUE val-fit DEAD, bias worsens); "
                        "t050v41 carries v113 floats (single-gate probe, far below gate). "
                        "verify_6of6 carries the v115 finding (6/6 incl v41-valfit + leader spec-error catch). "
                        "conc_v41_worst carries v116 floats (WORST concentration ever). "
                        "v55bfix_acc2_running is the acc2 COMPLETE-DEAD record (see v55bfix_dead row). "
                        "v55bfix_dead carries v111b replay floats (COMPLETE-DEAD rankonly, monthly "
                        "negative, DD-breach). v55bfixcal_rescue4th carries v121 floats "
                        "(4th rescue isoall +55.4%/1.32% DD-breach 2/3). feeBE_v55bfix_undefined "
                        "carries v124 fee0002 floats (flat fee-tier schema, BE undefined-negative) "
                        "with the CLOSED 7/7 fee-ladder ranking in its finding string. "
                        "conc_v55bfix_fail carries v123 finding (losing-book hard FAIL). "
                        "verify_7of7 carries the v122 finding (7/7 incl v55bfix + leader spec-error catch). "
                        "v96_running is the acc2 COMPLETE-DEAD record (see v96_dead_worst row). "
                        "v96_dead_worst carries v96b replay floats (COMPLETE-DEAD Transformer, rank "
                        "-0.03422, bias +5.79 worst-ever, monthly negative all 3, DD-breach). "
                        "scorediag_v96_attention carries the v127 mechanism finding (attention-close, "
                        "no portfolio floats). verify_8of8 carries the v125 finding (8/8 incl "
                        "v55bfixcal). verify_9of9 carries the v128 finding (9/9 incl v96). "
                        "conc_v96_fail carries v129 finding (losing-book hard FAIL). "
                        "feeBE_v96_undefined carries v130 fee0002 floats (flat fee-tier schema, BE "
                        "undefined-negative) with the CLOSED 8/8 fee-ladder ranking in its finding. "
                        "student_running is the acc2 RUNNING record (no numbers yet). "
                        "scopesv41 carries v117 floats (scopes dead on v41-identity too, best normal "
                        "s0004 1.02% / best exec long_only 1.26%, DD-breach all). "
                        "feeBE_v41 carries v119 fee0002 floats (flat fee-tier schema) with the CLOSED "
                        "6/6 fee-ladder ranking in its finding string. "
                        "Forward window is a sealed asset, never evaluated here; fwfeatures are "
                        "inference-only builders (no labels/metrics); fwdshakedown is FORWARD-window only "
                        "(Kronos-mini weak REJECT) and excluded from opened-interval ranking; "
                        "seal/fwdonly/gatecheck/verify rows are infra/methods findings. "
                        "Paper rehearsals/resume are OPENED-interval ops only, not forward validation."),
        }, fh, indent=2)

    cols = spec["csv_columns"]
    with open(os.path.join(OUT_DIR, "promotion_table.csv"), "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(cols)
        for r in rows:
            w.writerow([(repr(r[c]) if isinstance(r[c], float) else ("" if r[c] is None else r[c])) for c in cols])

    # ---- rankings (rules pre-specified in v134) ----
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

    fwd = spec.get("forward_readiness", {})
    cap = spec.get("capacity_verdict", {})
    rank_lines = []
    rank_lines.append("EXPLORATORY dossier v10 covering rounds 1-47, %d rows (83 old + %d new); gate Mo>=5%% + DD<=20%%(all3) + fills>=30(all3); Normal-first reporting." % (len(rows), len(rows) - FAMILIES_OLD))
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
        rank_lines.append("NONE qualifies: ceiling %s/mo < 5%% gate; every DD-safe book is <=%s/mo; monthly-top1 carries DD-breach; v96 DEAD worst-ever (rank -0.034 negative, bias +5.79 worst, monthly negative all 3, DD-breach) + scorediag closes attention-listwise (peaky-softmax fits train order) + conc FAIL veto (v96 losing book) + feeBE undefined-negative 8/8 close; rescued legs concentration-vetoed (top5 74-89%%); verify 9/9 methods-only; student RUNNING untested." % (
            mo_pct(top5[0]["normal_Mo"]) if top5 else "n/a", mo_pct(dd_safe_max)))
        rank_lines.append("Missing pieces: gate-passing frozen candidate (only blocker: v96 line dead incl scorediag/verify/conc/fee probes, fee 8/8 closed, verify 9/9 methods-only, student untested + attention-distill unbuilt); window+protocol+features+seal READY; halt-block-real-signal observation; concentration relief not needed for L2/L3 (both diffuse PASS).")
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
    rank_lines.append("QUEUE (student RUNNING -> attention-distill, dead lines closed):")
    for q in spec.get("queue_exact_order", []):
        rank_lines.append("Q: %s" % q)
    rank_lines.append("CAPACITY-VERDICT (bigger!=better, standalone mortality 12/12, 0.45M->8.77M):")
    rank_lines.append("RANK by rank_corr: v41 +0.0727 (0.6M) > v38 +0.066 > v40 +0.052 > v55c +0.022 > v28 +0.018 > v55bfix +0.0166 > v35 -0.0105 > v33 -0.028 > v96 -0.03422 WORST (8.77M); monthly all < gate or negative; verdict: scale REJECTED as cure, hope = distill (student 0.6M RUNNING) + attention-distill-if-cheap.")
    rank_lines.append("CLOUD-ACCOUNTS (spend both accounts):")
    for acc in ("account1", "account2"):
        a = spec.get("cloud_accounts", {}).get(acc, {})
        rank_lines.append("%s (%s, %s) | quota: %s | spend: %s" % (
            acc, a.get("key"), a.get("username"), a.get("quota"), a.get("spend")))
    rank_lines.append("FORWARD-READINESS (first forward validation needs 3 pieces):")
    rank_lines.append("FWD candidate: %s" % fwd.get("candidate", "?"))
    rank_lines.append("FWD window: %s" % fwd.get("window", "?"))
    rank_lines.append("FWD protocol: %s" % fwd.get("protocol", "?"))
    rank_lines.append("FWD overall: %s" % fwd.get("overall", "?"))
    rank_lines.append("Files: artifacts/research/opencode_dossier_v10/{promotion_table.json,promotion_table.csv,summary.json} + scripts/opencode_r48e_dossier10.py + configs/opencode_v134_dossier10.json (v9/v8/v7/v6/v5/v4/v3/v2/v1 untouched).")
    assert len(rank_lines) == 26 + len(spec.get("queue_exact_order", [])), \
        "RANKING must be exactly 26+queue lines, got %d" % len(rank_lines)

    # ---- delta vs v9 (read-only comparison, no recompute) ----
    delta9 = {"v9_top5_monthly": [], "v10_top5_monthly": [r["best_branch"] for r in top5],
              "new_monthly_no1": None, "risk_top3_changed": None, "note": ""}
    try:
        v9 = load_json(V9_TABLE)
        v9rows = v9.get("rows", [])
        v9ranked = [r for r in v9rows if isinstance(r.get("normal_Mo"), (int, float))]
        v9top5 = sorted(v9ranked, key=lambda r: r["normal_Mo"], reverse=True)[:5]
        delta9["v9_top5_monthly"] = [r["best_branch"] for r in v9top5]
        delta9["new_monthly_no1"] = top5[0]["best_branch"] if top5 else None
        v9risk = sorted(v9ranked, key=lambda r: (-r["normal_PF"], -r["normal_DD"]))[:3]
        delta9["v9_top3_risk"] = [r["best_branch"] for r in v9risk]
        delta9["v10_top3_risk"] = [r["best_branch"] for r in top3]
        delta9["risk_top3_changed"] = ([r["best_branch"] for r in top3] != [r["best_branch"] for r in v9risk])
        delta9["monthly_top1_changed"] = ((top5[0]["best_branch"] if top5 else None) !=
                                          (v9top5[0]["best_branch"] if v9top5 else None))
        v9ceil = v9top5[0]["normal_Mo"] if v9top5 else 0.0
        v10ceil = top5[0]["normal_Mo"] if top5 else 0.0
        newfams9 = [r["family"] for r in rows if r["family"] not in {x.get("family") for x in v9rows}]
        delta9["new_families"] = newfams9
        delta9["note"] = ("Monthly top-1 changed=%s (v9 %s %.4f%%/mo -> v10 %s %.4f%%/mo); "
                          "v10 ceiling still < 5%% gate. Risk top-3 RAW changed=%s. "
                          "New v10 rows vs v9: %s." % (
                              delta9["monthly_top1_changed"],
                              delta9["v9_top5_monthly"][0] if delta9["v9_top5_monthly"] else "?",
                              v9ceil * 100,
                              delta9["new_monthly_no1"], v10ceil * 100,
                              delta9["risk_top3_changed"], ", ".join(newfams9)))
    except (OSError, ValueError, KeyError) as e:
        delta9["note"] = "v9 table unreadable, delta skipped: %s" % e

    # ---- delta vs v8 (read-only comparison, no recompute) ----
    delta8 = {"v8_top5_monthly": [], "v10_top5_monthly": [r["best_branch"] for r in top5],
              "new_monthly_no1": None, "risk_top3_changed": None, "note": ""}
    try:
        v8 = load_json(V8_TABLE)
        v8rows = v8.get("rows", [])
        v8ranked = [r for r in v8rows if isinstance(r.get("normal_Mo"), (int, float))]
        v8top5 = sorted(v8ranked, key=lambda r: r["normal_Mo"], reverse=True)[:5]
        delta8["v8_top5_monthly"] = [r["best_branch"] for r in v8top5]
        delta8["new_monthly_no1"] = top5[0]["best_branch"] if top5 else None
        v8risk = sorted(v8ranked, key=lambda r: (-r["normal_PF"], -r["normal_DD"]))[:3]
        delta8["v8_top3_risk"] = [r["best_branch"] for r in v8risk]
        delta8["v10_top3_risk"] = [r["best_branch"] for r in top3]
        delta8["risk_top3_changed"] = ([r["best_branch"] for r in top3] != [r["best_branch"] for r in v8risk])
        delta8["monthly_top1_changed"] = ((top5[0]["best_branch"] if top5 else None) !=
                                          (v8top5[0]["best_branch"] if v8top5 else None))
        v8ceil = v8top5[0]["normal_Mo"] if v8top5 else 0.0
        v10ceil = top5[0]["normal_Mo"] if top5 else 0.0
        newfams8 = [r["family"] for r in rows if r["family"] not in {x.get("family") for x in v8rows}]
        delta8["new_families"] = newfams8
        delta8["note"] = ("Monthly top-1 changed=%s (v8 %s %.4f%%/mo -> v10 %s %.4f%%/mo); "
                          "v10 ceiling still < 5%% gate. Risk top-3 RAW changed=%s. "
                          "New v10 rows vs v8: %s." % (
                              delta8["monthly_top1_changed"],
                              delta8["v8_top5_monthly"][0] if delta8["v8_top5_monthly"] else "?",
                              v8ceil * 100,
                              delta8["new_monthly_no1"], v10ceil * 100,
                              delta8["risk_top3_changed"], ", ".join(newfams8)))
    except (OSError, ValueError, KeyError) as e:
        delta8["note"] = "v8 table unreadable, delta skipped: %s" % e

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

    with open(os.path.join(OUT_DIR, "summary.json"), "w", encoding="utf-8") as fh:
        json.dump({
            "experiment": "opencode-r48e-dossier10",
            "spec": "configs/opencode_v134_dossier10.json",
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
            "delta_vs_v9": delta9,
            "delta_vs_v8": delta8,
            "missing_skipped": missing,
            "exploratory": True,
            "live_approved": False,
        }, fh, indent=2)
    print("rows=%d (portfolio=%d special=%d) missing=%d top1=%s paper=%s" % (
        len(rows), len(ranked), len(rows) - len(ranked), len(missing),
        top5[0]["best_branch"] if top5 else "?", qual[0]["best_branch"] if qual else "NONE"))


if __name__ == "__main__":
    sys.exit(main())
