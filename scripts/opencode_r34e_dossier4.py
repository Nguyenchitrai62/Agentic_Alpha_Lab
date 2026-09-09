"""R34 E-dossier4: evidence compiler v4 — analysis ONLY, no backtests/training.

Extends R31 scripts/opencode_r31e_dossier3.py pattern (v3, 46 families):
reads configs/opencode_v99_dossier4.json (pre-spec: branch list + ranking
rules + queue + forward-readiness, written BEFORE compiling), walks
artifacts/research/opencode_*/ summaries + portfolio.json files, copies
EXACT floats (never invents), and writes the v4 comparison dossier into a
NEW dir (never touches v3/v2/v1):
  artifacts/research/opencode_dossier_v4/promotion_table.json
  artifacts/research/opencode_dossier_v4/promotion_table.csv
  artifacts/research/opencode_dossier_v4/summary.json (23-line RANKING +
  CLOUD_TRACK + QUEUE + FORWARD_READINESS + delta_vs_v3)
New vs v3 (rounds 31-33, 6 rows): volscale_38iso (4th/4th capacity book
closed), v55c_rankonly (dead) + v55c_bench (321.50ms/19.75MB special),
forward_sealed (pristine asset, no numbers), v96_staged (no numbers yet),
promorunner_validated (3/3 + 11/11 special). Carried 46 rows byte-identical
to v3 spec (verified in build step). Exploratory labels only. No live
orders. No registry writes. No overwriting existing files.
"""
import csv
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPEC_PATH = os.path.join(ROOT, "configs", "opencode_v99_dossier4.json")
OUT_DIR = os.path.join(ROOT, "artifacts", "research", "opencode_dossier_v4")
V3_TABLE = os.path.join(ROOT, "artifacts", "research", "opencode_dossier_v3",
                         "promotion_table.json")
FAMILIES_OLD = 46

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
    """Return (scenarios dict, flat_bool). Same schema handling as v3/v2/v1."""
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
    "fwd_machine": "majority HOLD validation + opened-date refusal (infra only)",
    "gatecheck_validated": "3/3 vs ledger (infra only)",
    "monthattr": "4-branch concentration evidence (methods only)",
    "v41_staged": "package-ready, smoke-proven, SUBMIT-DISPATCHED round34 (no numbers yet)",
    "clock_clean": "all-5-TFs CLEAN",
    "audit_1m": "63-trade 1m replay",
    "v55c_bench": "GTX1650 bench 321.50ms/window, 19.75MB VRAM (infra only)",
    "forward_sealed": "48,819 klines + 509 funding + 233 macro, SEAL pristine (asset only)",
    "v96_staged": "8.77M Transformer staged, smoke-proven (no numbers yet)",
    "promorunner_validated": "integrated promote CLI 3/3 + 11/11 tests (infra only)",
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
            "experiment": "opencode-r34e-dossier4",
            "spec": "configs/opencode_v99_dossier4.json",
            "extends": "artifacts/research/opencode_dossier_v3/promotion_table.json (v3, 46 families; untouched)",
            "gate": gate,
            "n_rows": len(rows),
            "n_portfolio_rows": len(ranked),
            "n_special_rows": len(rows) - len(ranked),
            "rows": rows,
            "missing_skipped": missing,
            "pipeline_verdicts": spec.get("pipeline_verdicts"),
            "cloud_track": spec.get("cloud_track"),
            "queue_exact_order": spec.get("queue_exact_order"),
            "queue_note": spec.get("queue_note"),
            "forward_readiness": spec.get("forward_readiness"),
            "exploratory": True,
            "live_approved": False,
            "warning": ("EXPLORATORY on the opened 2023-2026 development interval only. "
                        "Exact floats copied from artifacts; nothing refit. No promotion claim. "
                        "Drawdown is trade-candle-close sampled. Stop/timeout exits are market-like. "
                        "v55c_rankonly carries v55d replay floats (COMPLETE-DEAD); v55_infradead is the "
                        "frozen v3-time record. Forward window is a sealed asset, never evaluated here. "
                        "Paper rehearsals/resume are OPENED-interval ops only, not forward validation."),
        }, fh, indent=2)

    cols = spec["csv_columns"]
    with open(os.path.join(OUT_DIR, "promotion_table.csv"), "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(cols)
        for r in rows:
            w.writerow([(repr(r[c]) if isinstance(r[c], float) else ("" if r[c] is None else r[c])) for c in cols])

    # ---- rankings (rules pre-specified in v99) ----
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
    rank_lines = []
    rank_lines.append("EXPLORATORY dossier v4 covering rounds 1-33, %d rows (46 old + %d new); gate Mo>=5%% + DD<=20%%(all3) + fills>=30(all3); Normal-first reporting." % (len(rows), len(rows) - FAMILIES_OLD))
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
        rank_lines.append("NONE qualifies: ceiling %s/mo < 5%% gate; every DD-safe book is <=%s/mo; monthly-top1 carries DD-breach; v55c DEAD (rank-alone rejected); v96 untested, v41 unaudited." % (
            mo_pct(top5[0]["normal_Mo"]) if top5 else "n/a", mo_pct(dd_safe_max)))
        rank_lines.append("Missing pieces: gate-passing frozen candidate (only blocker); window+protocol READY; halt-block-real-signal observation; concentration relief not needed for L2/L3 (both diffuse PASS).")
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
    rank_lines.append("QUEUE (v55c terminal -> v41 dispatched -> nothing queued):")
    for q in spec.get("queue_exact_order", []):
        rank_lines.append("Q: %s" % q)
    rank_lines.append("FORWARD-READINESS (first forward validation needs 3 pieces):")
    rank_lines.append("FWD candidate: %s" % fwd.get("candidate", "?"))
    rank_lines.append("FWD window: %s" % fwd.get("window", "?"))
    rank_lines.append("FWD protocol: %s" % fwd.get("protocol", "?"))
    rank_lines.append("FWD overall: %s" % fwd.get("overall", "?"))
    rank_lines.append("Files: artifacts/research/opencode_dossier_v4/{promotion_table.json,promotion_table.csv,summary.json} + scripts/opencode_r34e_dossier4.py + configs/opencode_v99_dossier4.json (v3/v2/v1 untouched).")
    assert len(rank_lines) == 23, "RANKING must be exactly 23 lines, got %d" % len(rank_lines)

    # ---- delta vs v3 (read-only comparison, no recompute) ----
    delta = {"v3_top5_monthly": [], "v4_top5_monthly": [r["best_branch"] for r in top5],
             "new_monthly_no1": None, "risk_top3_changed": None, "note": ""}
    try:
        v3 = load_json(V3_TABLE)
        v3rows = v3.get("rows", [])
        v3ranked = [r for r in v3rows if isinstance(r.get("normal_Mo"), (int, float))]
        v3top5 = sorted(v3ranked, key=lambda r: r["normal_Mo"], reverse=True)[:5]
        delta["v3_top5_monthly"] = [r["best_branch"] for r in v3top5]
        delta["new_monthly_no1"] = top5[0]["best_branch"] if top5 else None
        v3risk = sorted(v3ranked, key=lambda r: (-r["normal_PF"], -r["normal_DD"]))[:3]
        delta["v3_top3_risk"] = [r["best_branch"] for r in v3risk]
        delta["v4_top3_risk"] = [r["best_branch"] for r in top3]
        delta["risk_top3_changed"] = ([r["best_branch"] for r in top3] != [r["best_branch"] for r in v3risk])
        delta["monthly_top1_changed"] = ((top5[0]["best_branch"] if top5 else None) !=
                                         (v3top5[0]["best_branch"] if v3top5 else None))

        def _uniq(rows):
            seen, out = set(), []
            for r in rows:
                key = (r["normal_Ret"], r["normal_DD"], r["normal_Mo"],
                       r["normal_fills"], r["normal_PF"], r["normal_WR"])
                if key not in seen:
                    seen.add(key)
                    out.append(r["best_branch"])
            return out

        v3uniq3 = _uniq(sorted(v3ranked, key=lambda r: (-r["normal_PF"], -r["normal_DD"])))[:3]
        v4uniq3 = _uniq(by_risk)[:3]
        delta["v3_top3_risk_unique_books"] = v3uniq3
        delta["v4_top3_risk_unique_books"] = v4uniq3
        v3ceil = v3top5[0]["normal_Mo"] if v3top5 else 0.0
        v4ceil = top5[0]["normal_Mo"] if top5 else 0.0
        delta["note"] = ("Monthly top-1 changed=%s (v3 %s %.4f%%/mo -> v4 %s %.4f%%/mo); "
                         "v4 ceiling still < 5%% gate. Risk top-3 RAW changed=%s; "
                         "UNIQUE-book risk top-3 %s vs %s. New v4 rows add no monthly driver "
                         "(volscale-38iso 1.82%% capacity leg, v55c negative, 4 specials carry no floats)." % (
                             delta["monthly_top1_changed"],
                             delta["v3_top5_monthly"][0] if delta["v3_top5_monthly"] else "?",
                             v3ceil * 100,
                             delta["new_monthly_no1"], v4ceil * 100,
                             delta["risk_top3_changed"], v3uniq3, v4uniq3))
    except (OSError, ValueError, KeyError) as e:
        delta["note"] = "v3 table unreadable, delta skipped: %s" % e

    cloud_lines = []
    for m in spec.get("cloud_track", []):
        cloud_lines.append("%s | %s | audit: %s | lesson: %s" % (
            m.get("model"), m.get("status"), m.get("audit"), m.get("lesson")))

    with open(os.path.join(OUT_DIR, "summary.json"), "w", encoding="utf-8") as fh:
        json.dump({
            "experiment": "opencode-r34e-dossier4",
            "spec": "configs/opencode_v99_dossier4.json",
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
            "QUEUE": spec.get("queue_exact_order"),
            "QUEUE_NOTE": spec.get("queue_note"),
            "FORWARD_READINESS": spec.get("forward_readiness"),
            "delta_vs_v3": delta,
            "missing_skipped": missing,
            "exploratory": True,
            "live_approved": False,
        }, fh, indent=2)
    print("rows=%d (portfolio=%d special=%d) missing=%d top1=%s paper=%s" % (
        len(rows), len(ranked), len(rows) - len(ranked), len(missing),
        top5[0]["best_branch"] if top5 else "?", qual[0]["best_branch"] if qual else "NONE"))


if __name__ == "__main__":
    sys.exit(main())
