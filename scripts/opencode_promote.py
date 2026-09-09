"""One-command promotion runner (opencode_promote v1.0.0).

Runs the FULL promotion chain for one frozen branch in a single command:

  gatecheck (gate + concentration + robustness, via scripts/opencode_gatecheck.py)
  -> forward-protocol verdict (via scripts/opencode_forward_test.py;
     REFUSES forward on already-opened dates, BLOCKED until new data)
  -> paper checklist status (existing rehearsal summaries are reused ONLY if
     the same signals were rehearsed, else MISSING)
  -> single PROMOTE/HOLD/REJECT with a reasons file.

Thin wrapper by design: every gate / concentration / robustness / forward /
paper / decide computation is IMPORTED from the two tools, never re-implemented
here. This module owns only the CLI, the paper-by-signal-match lookup, the
mirror-check, the orchestration, and the reasons-file assembly.

Analysis/code ONLY. No backtests, no training, no fitting, no live orders.

Usage:
    .venv/Scripts/python.exe scripts/opencode_promote.py \
        --summary <summary.json> --trades <normal_trades.csv> \
        --branch <branch> --signals <signals.parquet> \
        --backtest-config <plan.json> \
        [--paper-summary <paper.json> [--paper-summary <drill.json>]] \
        [--forward-summary <fwd.json> --forward-trades <fwd.csv>] \
        [--forward-start YYYY-MM-DD] \
        [--config configs/opencode_promote.json] \
        --out <reasons.json>

Paper handling:
  * Explicit --paper-summary files are always evaluated (match/mismatch vs the
    candidate --signals is recorded per file for audit).
  * With NO --paper-summary, the runner auto-looks-up
    configs/opencode_promote.json:paper_matching.rehearsal_index[branch] and
    reuses ONLY entries whose signal-identity fields suffix-match the candidate
    signals. If nothing matches, paper_paths=[] and paper_source=MISSING, so
    the forward verdict caps at HOLD (never PROMOTE).

Exit codes: 0 on successful analysis regardless of verdict (the verdict lives
in the payload); 2 on tool/input/refusal errors (missing file, bad branch,
forward on opened dates, overlapping forward trades, --out already exists).
A refusal writes NO verdict file.
"""

import argparse
import importlib.util
import json
import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROMOTE_CONFIG = ROOT / "configs" / "opencode_promote.json"

_GC_SPEC = importlib.util.spec_from_file_location(
    "opencode_gatecheck", _SCRIPTS_DIR / "opencode_gatecheck.py")
GC = importlib.util.module_from_spec(_GC_SPEC)
_GC_SPEC.loader.exec_module(GC)

_FT_SPEC = importlib.util.spec_from_file_location(
    "opencode_forward_test", _SCRIPTS_DIR / "opencode_forward_test.py")
FT = importlib.util.module_from_spec(_FT_SPEC)
_FT_SPEC.loader.exec_module(FT)

REUSE_RECORD = {
    "gatecheck": "scripts/opencode_gatecheck.py imported as GC; "
                 "gatecheck stage calls GC.run() verbatim",
    "forward": "scripts/opencode_forward_test.py imported as FT; "
               "forward+paper+decide stages call FT.run() verbatim "
               "(which itself calls GC.run() for the in-sample window)",
    "no_copied_logic": True,
    "wrapper_owns_only": "CLI + paper-by-signal-match lookup + "
                         "threshold mirror-check + orchestration + "
                         "reasons-file assembly",
}

MATCH_FIELDS = (
    ("halt_trip_params", "divergence_baseline_signals"),
    ("config_snapshot.data", "signals_replay_only"),
    ("signal_set_identity", "baseline_signals_path"),
)


def load_json(path: Path) -> dict:
    with Path(path).open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _posix(path_str: str) -> str:
    return str(path_str).replace("\\", "/")


def _get_nested(doc: dict, dotted: str):
    node = doc
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def signal_match(candidate_signals: Path, paper_doc: dict) -> dict:
    """Suffix-match a paper summary against candidate signals (audit layer).

    Returns {"matched": bool, "field": str|None, "value": str|None}.
    Pure path-suffix comparison; never reads trades or scores.
    """
    cand = _posix(Path(candidate_signals).as_posix())
    tail_parts = cand.split("/")
    tail = "/".join(tail_parts[-3:]) if len(tail_parts) >= 3 else cand
    for dotted, leaf in (("halt_trip_params", "divergence_baseline_signals"),
                         ("config_snapshot", None),
                         ("signal_set_identity", "baseline_signals_path")):
        candidates = []
        if dotted == "halt_trip_params":
            v = _get_nested(paper_doc, "halt_trip_params.divergence_baseline_signals")
            if isinstance(v, str):
                candidates.append(("halt_trip_params.divergence_baseline_signals", v))
        elif dotted == "config_snapshot":
            v = _get_nested(paper_doc, "config_snapshot.data.signals_replay_only")
            if isinstance(v, str):
                candidates.append(("config_snapshot.data.signals_replay_only", v))
        else:
            v = _get_nested(paper_doc, "signal_set_identity.baseline_signals_path")
            if isinstance(v, str):
                candidates.append(("signal_set_identity.baseline_signals_path", v))
        for field, value in candidates:
            fp = _posix(value)
            if cand.endswith(fp) or fp.endswith(tail) or fp == cand:
                return {"matched": True, "field": field, "value": value}
    void = [f for f, _ in
            ([("halt_trip_params.divergence_baseline_signals",
               _get_nested(paper_doc, "halt_trip_params.divergence_baseline_signals")),
              ("config_snapshot.data.signals_replay_only",
               _get_nested(paper_doc, "config_snapshot.data.signals_replay_only")),
              ("signal_set_identity.baseline_signals_path",
               _get_nested(paper_doc, "signal_set_identity.baseline_signals_path"))])]
    return {"matched": False, "field": None, "value": None,
            "checked": [f for f, _ in void]}


def resolve_papers(branch: str, signals_path: Path, explicit: list,
                   promote_cfg: dict) -> tuple[list, dict]:
    """Resolve paper rehearsal files + signal-match audit trail."""
    if explicit:
        paths = [Path(p) for p in explicit]
        missing = [str(p) for p in paths if not p.exists()]
        if missing:
            raise FileNotFoundError(f"paper summary missing: {missing}")
        per_file = []
        for p in paths:
            doc = load_json(p)
            m = signal_match(signals_path, doc)
            per_file.append({"file": str(p), **m})
        matched = sum(1 for e in per_file if e["matched"])
        source = {"mode": "explicit",
                  "files": [str(p) for p in paths],
                  "match": f"{matched}/{len(per_file)} explicit files "
                           f"suffix-match candidate signals",
                  "per_file": per_file}
        return paths, source
    index = (promote_cfg.get("paper_matching", {})
             .get("rehearsal_index", {}).get(branch, []))
    per_file, kept = [], []
    for raw in index:
        p = Path(raw)
        if not p.is_absolute():
            p = ROOT / raw
        if not p.exists():
            per_file.append({"file": str(raw), "matched": False,
                             "field": None, "value": None,
                             "note": "indexed file not found on disk"})
            continue
        doc = load_json(p)
        m = signal_match(signals_path, doc)
        per_file.append({"file": str(p), **m})
        if m["matched"]:
            kept.append(p)
    if kept:
        source = {"mode": "rehearsal-index-match",
                  "files": [str(p) for p in kept],
                  "match": f"{len(kept)}/{len(per_file)} indexed rehearsals "
                           f"suffix-match candidate signals",
                  "per_file": per_file}
        return kept, source
    source = {"mode": "MISSING(no rehearsal for these signals)",
              "files": [],
              "match": "0 indexed rehearsals suffix-match candidate signals; "
                       "paper checklist evaluates to NOT_GREEN (MISSING)",
              "per_file": per_file}
    return [], source


def mirror_check(promote_cfg: dict, gc_cfg: dict, protocol: dict) -> dict:
    """Verify the promote-config mirror block equals the two source configs."""
    m = promote_cfg.get("thresholds_mirror", {})
    g, fw = m.get("gate", {}), m.get("forward_window", {})
    rm = m.get("robustness_margins", {})
    conc = m.get("concentration", {})
    checks = {
        "gate.monthly_min": (g.get("monthly_min"),
                             gc_cfg.get("gate", {}).get("monthly_min")),
        "gate.dd_max": (g.get("dd_max"),
                        gc_cfg.get("gate", {}).get("dd_max")),
        "gate.fills_min": (g.get("fills_min"),
                           gc_cfg.get("gate", {}).get("fills_min")),
        "concentration.top1": (conc.get("top1_month_share_gt"),
                               gc_cfg.get("concentration_rule", {})
                               .get("top1_month_share_gt")),
        "concentration.top3": (conc.get("top3_months_share_gt"),
                               gc_cfg.get("concentration_rule", {})
                               .get("top3_months_share_gt")),
        "forward.min_months": (fw.get("min_forward_months"),
                               protocol.get("forward_window", {})
                               .get("min_forward_months", {}).get("value")),
        "forward.degradation_ratio_min": (
            fw.get("degradation_ratio_min"),
            protocol.get("degradation_vs_backtest", {})
            .get("forward_monthly_ge_backtest_ratio_min", {}).get("value")),
        "margins.max_exec_drop_pp": (
            rm.get("max_exec_drop_pp"),
            protocol.get("robustness_margins", {})
            .get("max_exec_drop_pp", {}).get("value")),
        "margins.max_fee_drag_pp": (
            rm.get("max_fee_drag_pp"),
            protocol.get("robustness_margins", {})
            .get("max_fee_drag_pp", {}).get("value")),
        "margins.min_dd_margin_pp": (
            rm.get("min_dd_margin_pp"),
            protocol.get("robustness_margins", {})
            .get("min_dd_margin_pp", {}).get("value")),
    }
    bad = sorted(k for k, (a, b) in checks.items() if a != b)
    return {"checks": {k: {"promote_mirror": a, "source": b,
                                 "match": a == b}
                             for k, (a, b) in checks.items()},
            "mirror_ok": not bad,
            "mismatches": bad}


def run(summary_path: Path, trades_path: Path, branch: str | None,
        signals_path: Path, backtest_config_path: Path,
        paper_explicit: list, promote_cfg: dict,
        gc_cfg: dict, protocol: dict,
        forward_summary: Path | None = None,
        forward_trades: Path | None = None,
        forward_start: str | None = None) -> dict:
    for p, label in ((summary_path, "summary"), (trades_path, "trades"),
                     (signals_path, "signals"),
                     (backtest_config_path, "backtest-config")):
        if not Path(p).exists():
            raise FileNotFoundError(f"{label} not found: {p}")
    mirror = mirror_check(promote_cfg, gc_cfg, protocol)
    if not mirror["mirror_ok"]:
        raise ValueError(
            "promote-config mirror MISMATCH vs source configs "
            f"{mirror['mismatches']}: fix configs/opencode_promote.json "
            "thresholds_mirror (source configs win); no verdict written.")
    gatecheck = GC.run(summary_path, trades_path, branch, None, gc_cfg)
    branch_name = gatecheck["inputs"]["branch"]
    paper_paths, paper_source = resolve_papers(
        branch_name, signals_path, paper_explicit, promote_cfg)
    forward_verdict = FT.run(
        summary_path, trades_path, branch_name, signals_path,
        backtest_config_path, paper_paths, protocol, gc_cfg,
        forward_summary, forward_trades, forward_start)
    decision = forward_verdict["decision"]
    reasons = list(forward_verdict["decision_reasons"])
    if paper_source["mode"].startswith("MISSING"):
        if "paper-not-green" not in reasons:
            reasons = reasons + ["paper-not-green(paper-MISSING-no-rehearsal-for-these-signals)"]
    line = (f"{decision} -- {branch_name}: "
            f"gatecheck {gatecheck['decision']} "
            f"[{'; '.join(gatecheck['decision_reasons']) or 'clean'}]; "
            f"forward {forward_verdict['forward']['status']}"
            + (f" -> {forward_verdict['forward'].get('forward_decision')}"
               if forward_verdict["forward"]["status"] == "READY" else "")
            + f"; paper {forward_verdict['paper_rehearsal']['paper_overall']} "
            f"({paper_source['mode']}).")
    return {
        "tool": "opencode_promote",
        "version": promote_cfg.get("version", "1.0.0"),
        "promote_config": str(DEFAULT_PROMOTE_CONFIG),
        "reuse": REUSE_RECORD,
        "mirror_check": mirror,
        "inputs": {"summary": str(summary_path), "branch": branch_name,
                   "trades": str(trades_path), "signals": str(signals_path),
                   "backtest_config": str(backtest_config_path),
                   "forward_summary": str(forward_summary)
                   if forward_summary else None,
                   "forward_trades": str(forward_trades)
                   if forward_trades else None,
                   "forward_start": forward_start},
        "paper_source": paper_source,
        "gatecheck": gatecheck,
        "forward_verdict": forward_verdict,
        "decision": decision,
        "decision_reasons": reasons,
        "decision_line": line,
        "warnings": promote_cfg.get("warnings", []),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="One-command promotion runner: gatecheck -> "
                    "forward-protocol verdict -> paper-by-signal-match -> "
                    "single PROMOTE/HOLD/REJECT with reasons file.")
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--trades", type=Path, required=True)
    parser.add_argument("--branch", default=None)
    parser.add_argument("--signals", type=Path, required=True)
    parser.add_argument("--backtest-config", type=Path, required=True)
    parser.add_argument("--paper-summary", action="append", default=[],
                        help="paper rehearsal summary (repeatable; "
                             "omit for auto-lookup by signal match)")
    parser.add_argument("--forward-summary", type=Path, default=None)
    parser.add_argument("--forward-trades", type=Path, default=None)
    parser.add_argument("--forward-start", default=None)
    parser.add_argument("--config", type=Path, default=DEFAULT_PROMOTE_CONFIG)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)

    try:
        promote_cfg = load_json(args.config)
        gc_cfg_path = Path(promote_cfg["gatecheck_config"])
        proto_path = Path(promote_cfg["forward_protocol"])
        if not gc_cfg_path.is_absolute():
            gc_cfg_path = ROOT / gc_cfg_path
        if not proto_path.is_absolute():
            proto_path = ROOT / proto_path
        gc_cfg = load_json(gc_cfg_path)
        protocol = load_json(proto_path)
        result = run(args.summary, args.trades, args.branch, args.signals,
                     args.backtest_config, args.paper_summary, promote_cfg,
                     gc_cfg, protocol, args.forward_summary,
                     args.forward_trades, args.forward_start)
    except (ValueError, FileNotFoundError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    g = result["gatecheck"]
    fv = result["forward_verdict"]
    print(f"branch: {result['inputs']['branch']} "
          f"(mirror_ok={result['mirror_check']['mirror_ok']}, "
          f"paper_source={result['paper_source']['mode']})")
    print(f"gatecheck: {g['decision']} "
          f"[{'; '.join(g['decision_reasons']) or 'clean'}]")
    fwd = fv["forward"]
    if fwd["status"] == "READY":
        print(f"forward: READY -> {fwd['forward_decision']} "
              f"[{'; '.join(fwd['forward_reasons'])}]")
    else:
        print(f"forward: {fwd['status']} -- {fwd['blocked_reason']}")
    print(f"paper: {fv['paper_rehearsal']['paper_overall']} "
          f"({result['paper_source']['match']})")
    print(result["decision_line"])
    if args.out is not None:
        if args.out.exists():
            print(f"ERROR: refusing to overwrite existing {args.out}",
                  file=sys.stderr)
            return 2
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, indent=2, ensure_ascii=False),
                            encoding="utf-8")
        print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
