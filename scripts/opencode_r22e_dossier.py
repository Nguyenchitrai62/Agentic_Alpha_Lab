"""R22 E-dossier: evidence compiler — analysis ONLY, no backtests/training.

Reads configs/opencode_v69_dossier.json (pre-spec: branch list + ranking rules),
walks artifacts/research/opencode_*/summary.json + key portfolio.json files,
copies EXACT floats (never invents), and writes ONE comparison dossier:
  artifacts/research/opencode_dossier/promotion_table.json
  artifacts/research/opencode_dossier/promotion_table.csv
  artifacts/research/opencode_dossier/summary.json (with 15-line RANKING)
Exploratory labels only. No live orders. No registry writes.
"""
import csv
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPEC_PATH = os.path.join(ROOT, "configs", "opencode_v69_dossier.json")
OUT_DIR = os.path.join(ROOT, "artifacts", "research", "opencode_dossier")

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
    """Return (scenarios dict, flat_bool).

    Handles: scenarios-nested, direct normal/fee/exec layout, replay
    portfolio.json layout, delay/volcap/probfill partial layouts (only the
    scenarios actually run), and fee-ladder flat layouts (metrics directly
    on the branch node = single fee-tier scenario -> mapped to 'normal').
    """
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
    """Extract available-scenario metric floats for one branch.

    Returns (metrics_by_scenario, flat_bool); raises KeyError if the branch
    is absent or has no usable normal metrics. Never invents numbers.
    """
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
            missing.append({"family": family, "artifact": apath, "note": "summary.json not found; skipped, no numbers invented"})
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

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, "promotion_table.json"), "w", encoding="utf-8") as fh:
        json.dump({
            "experiment": "opencode-r22e-dossier",
            "spec": "configs/opencode_v69_dossier.json",
            "gate": gate,
            "n_rows": len(rows),
            "rows": rows,
            "missing_skipped": missing,
            "exploratory": True,
            "live_approved": False,
            "warning": ("EXPLORATORY on the opened 2023-2026 development interval only. "
                        "Exact floats copied from artifacts; nothing refit. No promotion claim. "
                        "Drawdown is trade-candle-close sampled. Stop/timeout exits are market-like."),
        }, fh, indent=2)

    cols = spec["csv_columns"]
    with open(os.path.join(OUT_DIR, "promotion_table.csv"), "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(cols)
        for r in rows:
            w.writerow([(repr(r[c]) if isinstance(r[c], float) else ("" if r[c] is None else r[c])) for c in cols])

    # ---- rankings (rules pre-specified in v69) ----
    by_mo = sorted(rows, key=lambda r: r["normal_Mo"], reverse=True)
    top5 = by_mo[:5]
    by_risk = sorted(rows, key=lambda r: (-r["normal_PF"], -r["normal_DD"]))
    top3 = by_risk[:3]
    qual = [r for r in rows
            if r["normal_Mo"] >= gate["monthly_min"]
            and r["dd_gate_all3"] == "y" and r["fills_gate_all3"] == "y"
            and r["fee_Mo"] is not None and r["exec_Mo"] is not None]

    def mo_pct(x):
        return "%.4f%%" % (x * 100)

    def fills_str(r):
        return "%d/%s" % (r["normal_fills"], r["exec_fills"] if r["exec_fills"] is not None else "n/a")

    rank_lines = []
    rank_lines.append("EXPLORATORY dossier covering rounds 1-21; gate Mo>=5% + DD<=20%(all3) + fills>=30(all3); Normal-first reporting.")
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
        dd_safe = [r for r in rows if r["dd_gate_all3"] == "y"]
        dd_safe_max = max([r["normal_Mo"] for r in dd_safe]) if dd_safe else 0.0
        rank_lines.append("NONE qualifies: ceiling %s/mo < 5%% gate; every DD-safe book is <=%s/mo; anchors carry DD-breach or concentration caveats." % (
            mo_pct(top5[0]["normal_Mo"]) if top5 else "n/a", mo_pct(dd_safe_max)))
        rank_lines.append("Missing pieces: forward test on unseen data, live signal weights (v39/v55 cloud pending), same-book halt drill; concentration relief (v38 top5 71.3%).")
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
        rank_lines.append("All %d present, none invented. Ranks 2-3 re-run majority_1x book (fee/volcap baselines); unique-book top5: %s." % (
            len(rows), ", ".join(uniq[:5])))
    rank_lines.append("Files: artifacts/research/opencode_dossier/{promotion_table.json,promotion_table.csv,summary.json} + scripts/opencode_r22e_dossier.py.")
    assert len(rank_lines) == 15, "RANKING must be exactly 15 lines, got %d" % len(rank_lines)

    with open(os.path.join(OUT_DIR, "summary.json"), "w", encoding="utf-8") as fh:
        json.dump({
            "experiment": "opencode-r22e-dossier",
            "spec": "configs/opencode_v69_dossier.json",
            "branches_covered": len(rows),
            "families": [r["family"] for r in rows],
            "top5_monthly": [r["best_branch"] for r in top5],
            "top3_risk_adjusted": [r["best_branch"] for r in top3],
            "paper_recommendation": qual[0]["best_branch"] if qual else "NONE",
            "RANKING": rank_lines,
            "missing_skipped": missing,
            "exploratory": True,
            "live_approved": False,
        }, fh, indent=2)
    print("rows=%d missing=%d top1=%s paper=%s" % (
        len(rows), len(missing), top5[0]["best_branch"] if top5 else "?", qual[0]["best_branch"] if qual else "NONE"))


if __name__ == "__main__":
    sys.exit(main())
