"""oc_jitter joint-jitter analyzer (OpenCode task ops_jitteranalyze).

Reads the Kaggle engine-kernel output for job jitter_g2_joint (BASE R2B1D17BFG2
+ 12 seeded joint +-10% jitters of kd, G, flush k) and checks the deployed
point sits on a plateau:

  (1) GATE: BASE row must equal v421 (5y 5.41 %/mo / worst year 2.588 /
      max yearly DD 16.91 / full-path DD 16.82) within rounding, else stop.
  (2) Per-row table: parameters, 5y %/mo, worst year, max yearly DD,
      full-path DD, losing years.
  (3) Distribution over the 12 jitter rows (min/median/max of 5y and DDs;
      shares with 5y >= 5.0, DD < 20, no losing year) + plateau verdict
      (ROBUST iff all 12 keep 5y >= 5.0 and DD < 20 and no losing year;
      else list failing rows and which parameter moved most).
  (4) Writes REPORT.md + results.json next to this script.

The Kaggle job (account 2, kernel trainguyenchi/oc-engine-4p) is running; its
output is downloaded by the leader into artifacts/kaggle/engine_jitter_v2/
(this script finds results.json recursively under that dir).

Usage:
  .venv/Scripts/python.exe research/diagnostics/oc_jitter/analyze_jitter.py
  .venv/Scripts/python.exe research/diagnostics/oc_jitter/analyze_jitter.py --results <results.json> --outdir <dir>
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parents[2]  # research/diagnostics/oc_jitter -> repo root
DEFAULT_SEARCH = ROOT / "artifacts" / "kaggle" / "engine_jitter_v2"
DEFAULT_JOB = ROOT / "artifacts" / "kaggle_stage" / "engine_kernel" / "jobs" / "jitter_g2.json"

BASE_NAME = "R2B1D17BFG2"
# v421 reference (oc_plateau2 REPORT: base reproduced v421 run.log exactly).
EXPECTED_BASE = {"mean5y": 5.41, "worst": 2.588, "maxDD": 16.91, "full_path_dd": 16.82}
# "within rounding": engine_harness rounds mean5y to 3dp and DDs to 2dp, so a
# 0.011 tolerance covers 2dp rounding on every field.
GATE_TOL = 0.011
# Deployed sleeve values (jitter_g2.json base).
DEPLOYED = {"kd": 1.7, "G": 2.0, "k": 1.0}

ROBUST_5Y = 5.0
ROBUST_DD = 20.0


class GateError(RuntimeError):
    pass


def find_results(search_root: Path = DEFAULT_SEARCH) -> Path:
    cands = sorted(search_root.rglob("results.json")) if search_root.exists() else []
    if not cands:
        raise FileNotFoundError(
            f"results.json not found under {search_root} "
            "(Kaggle job trainguyenchi/oc-engine-4p output not downloaded yet; "
            "leader downloads it into artifacts/kaggle/engine_jitter_v2/)."
        )
    return cands[0]


def load_job(job_path: Path = DEFAULT_JOB) -> dict:
    job = json.loads(Path(job_path).read_text())
    out = {}
    for r in job.get("rows", []):
        out[r["name"]] = dict(r.get("sleeve", {}))
    return out


def _get(rec: dict, *keys, default=None):
    for k in keys:
        if k in rec:
            return rec[k]
    return default


def gate_check(rows: dict) -> None:
    if BASE_NAME not in rows:
        raise GateError(f"GATE FAIL: BASE row '{BASE_NAME}' missing from results.json rows {sorted(rows)}.")
    base = rows[BASE_NAME]
    bad = []
    for k, exp in EXPECTED_BASE.items():
        got = base.get(k)
        if got is None:
            bad.append(f"{k}: missing (expected {exp})")
        elif abs(float(got) - exp) > GATE_TOL:
            bad.append(f"{k}: got {got}, expected {exp} (tol {GATE_TOL})")
    if bad:
        raise GateError(
            "GATE FAIL: BASE row does not reproduce v421 "
            "(5y 5.41 / worst 2.588 / max yearly DD 16.91 / full-path DD 16.82 within rounding). "
            + "; ".join(bad) + ". STOP: engine output does not match the deployed baseline; "
            "do not trust the jitter rows."
        )


def summarize_row(name: str, rec: dict, params: dict) -> dict:
    return {
        "name": name,
        "kd": params.get("kd"),
        "G": params.get("G"),
        "k": params.get("k"),
        "rule": params.get("rule"),
        "mean5y": float(rec["mean5y"]),
        "worst": float(rec["worst"]),
        "maxDD": float(rec["maxDD"]),
        "full_path_dd": float(_get(rec, "full_path_dd", "fullDD")),
        "losing": int(rec["losing"]),
        "years": rec.get("years"),
    }


def param_moved_most(params: dict) -> str:
    """Which jittered parameter deviated most from deployed (relative move)."""
    moves = {}
    for p, base in DEPLOYED.items():
        v = params.get(p)
        if v is not None:
            moves[p] = (abs(float(v) - base) / base, float(v), base)
    if not moves:
        return "n/a"
    p = max(moves, key=lambda q: moves[q][0])
    rel, v, base = moves[p]
    sign = "+" if v >= base else "-"
    return f"{p} ({v} vs deployed {base}, {sign}{100 * rel:.1f}%)"


def _stats(xs: list) -> dict:
    return {"min": min(xs), "median": statistics.median(xs), "max": max(xs)}


def analyze(results_path: Path, job_path: Path = DEFAULT_JOB) -> tuple[dict, str]:
    res = json.loads(Path(results_path).read_text())
    rows = res.get("rows", {})
    gate_check(rows)
    params = load_job(job_path)
    table = [summarize_row(n, rows[n], params.get(n, {})) for n in rows]
    jitter = [s for s in table if s["name"] != BASE_NAME]
    if len(jitter) != 12:
        raise GateError(
            f"GATE FAIL: expected 12 jitter rows + 1 BASE (13 total), found "
            f"{len(jitter)} jitter rows: {sorted(s['name'] for s in jitter)}."
        )
    dist = {
        "n": len(jitter),
        "mean5y": _stats([s["mean5y"] for s in jitter]),
        "maxDD": _stats([s["maxDD"] for s in jitter]),
        "full_path_dd": _stats([s["full_path_dd"] for s in jitter]),
        "share_5y_ge_5": sum(s["mean5y"] >= ROBUST_5Y for s in jitter) / len(jitter),
        "share_dd_lt_20": sum(s["maxDD"] < ROBUST_DD and s["full_path_dd"] < ROBUST_DD for s in jitter) / len(jitter),
        "share_no_losing": sum(s["losing"] == 0 for s in jitter) / len(jitter),
        "share_all": sum(
            s["mean5y"] >= ROBUST_5Y and s["maxDD"] < ROBUST_DD
            and s["full_path_dd"] < ROBUST_DD and s["losing"] == 0 for s in jitter
        ) / len(jitter),
    }
    failing = []
    for s in jitter:
        reasons = []
        if s["mean5y"] < ROBUST_5Y:
            reasons.append(f"5y {s['mean5y']} < 5.0")
        if s["maxDD"] >= ROBUST_DD:
            reasons.append(f"maxDD {s['maxDD']} >= 20")
        if s["full_path_dd"] >= ROBUST_DD:
            reasons.append(f"fullDD {s['full_path_dd']} >= 20")
        if s["losing"] > 0:
            reasons.append(f"losing years {s['losing']}")
        if reasons:
            failing.append({
                "name": s["name"],
                "reasons": reasons,
                "moved_most": param_moved_most(params.get(s["name"], {})),
            })
    verdict = "ROBUST" if not failing else "NOT-ROBUST"
    out = {
        "version": "oc_jitter",
        "job": res.get("job", "jitter_g2_joint"),
        "gate": {"base": BASE_NAME, "expected_v421": EXPECTED_BASE, "passed": True},
        "rows": {s["name"]: s for s in table},
        "distribution_jitter12": dist,
        "verdict": verdict,
        "failing": failing,
    }
    return out, render_report(out)


def render_report(a: dict) -> str:
    L = ["# oc_jitter REPORT — joint +-10% jitter around R2B1D17BFG2",
         "",
         "## Setup",
         "Job jitter_g2_joint: BASE R2B1D17BFG2 (deployed v421 settings: rule inv, k 1.0, "
         "kd 1.7, bear true, G 2.0, book_hook bear) + 12 seeded joint uniform draws "
         "within +-10% of kd/G/k (numpy default_rng seed 20261006, draws consumed in "
         "kd,G,k order per row J01..J12, rounded to 4 decimals; see "
         "artifacts/kaggle_stage/engine_kernel/jobs/jitter_g2.json). Harness = "
         "artifacts/kaggle_stage/engine_kernel/engine_harness.py (4-phase reset-metric "
         "scoring, v388.mix full-path DD). One-at-a-time plateau: "
         "research/diagnostics/oc_plateau2/REPORT.md. Diagnostic only; deployment pick "
         "stays R2B1D17BFG2 regardless.",
         "",
         "## Gate",
         "BASE reproduces v421 (5y 5.41 / worst 2.588 / max yearly DD 16.91 / full-path "
         "DD 16.82 within rounding): PASS.",
         "",
         "## Per-row summary (params kd/G/k | 5y %/mo | worst year | max yearly DD | full-path DD | losing years)",
         "| row | kd | G | k | 5y %/mo | worst | maxDD | fullDD | losing |",
         "|---|---|---|---|---|---|---|---|---|"]
    for name, s in a["rows"].items():
        L.append(f"| {name} | {s['kd']} | {s['G']} | {s['k']} | {s['mean5y']} | "
                 f"{s['worst']} | {s['maxDD']} | {s['full_path_dd']} | {s['losing']} |")
    d = a["distribution_jitter12"]
    L += ["",
          "## Distribution over the 12 jitter rows",
          f"5y %/mo: min {d['mean5y']['min']}, median {d['mean5y']['median']}, max {d['mean5y']['max']}.",
          f"max yearly DD: min {d['maxDD']['min']}, median {d['maxDD']['median']}, max {d['maxDD']['max']}.",
          f"full-path DD: min {d['full_path_dd']['min']}, median {d['full_path_dd']['median']}, "
          f"max {d['full_path_dd']['max']}.",
          f"share 5y >= 5.0: {d['share_5y_ge_5']:.3f}; share DD < 20 (both DDs): "
          f"{d['share_dd_lt_20']:.3f}; share no losing year: {d['share_no_losing']:.3f}; "
          f"share all three: {d['share_all']:.3f}.",
          "",
          "## Verdict",
          f"VERDICT: {a['verdict']}" + (
              " — all 12 joint jitters keep 5y >= 5.0, DD < 20 and no losing year; "
              "the deployed point sits on a joint plateau."
              if a["verdict"] == "ROBUST" else
              " — failing rows: " + "; ".join(
                  f"{f['name']} ({', '.join(f['reasons'])}; moved most {f['moved_most']})"
                  for f in a["failing"]) + ".")]
    return "\n".join(L) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default=None)
    ap.add_argument("--job", default=str(DEFAULT_JOB))
    ap.add_argument("--outdir", default=str(HERE))
    ns = ap.parse_args(argv)
    try:
        rp = Path(ns.results) if ns.results else find_results()
        out, report = analyze(rp, Path(ns.job))
    except (FileNotFoundError, GateError) as e:
        print(str(e), file=sys.stderr)
        return 2
    od = Path(ns.outdir)
    od.mkdir(parents=True, exist_ok=True)
    (od / "results.json").write_text(json.dumps(out, indent=1, default=str))
    (od / "REPORT.md").write_text(report)
    print(f"verdict={out['verdict']} rows={len(out['rows'])} -> {od / 'REPORT.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
