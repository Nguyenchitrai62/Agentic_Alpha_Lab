"""Reusable promotion gate-checker (opencode_gatecheck v1.0.0).

Reads ANY branch summary.json + its normal_trades.csv (standard asdict-Trade
schema) and emits: (a) gate verdict, (b) concentration score (v61 method),
(c) robustness score, (d) one-line PROMOTE/HOLD/REJECT with reasons.

Analysis/code ONLY. No backtests, no training, no fitting, no live orders.
Thresholds are config-gated via configs/opencode_gatecheck.json (never hardcoded).

Usage:
    .venv/Scripts/python.exe scripts/opencode_gatecheck.py \
        --summary <summary.json> --trades <normal_trades.csv> \
        [--branch <branch_name>] [--baseline <baseline_trades.csv>] \
        [--config <gatecheck.json>] [--out <result.json>]

Summary schemas accepted (branch node shapes seen across rounds):
  A. flat scenarios:  branches.B = {normal: {...}, fee_stress: {...}, ...}
  B. nested scenarios: branches.B = {scenarios: {normal: {...}, ...}, ...}
  C. flat fee-tier:    branches.B = {monthly_geometric_net, max_drawdown,
                                     trades, fee_rate_per_fill, ...}
     (treated as a single present scenario named "normal").
A scenario dict is any mapping holding "trades" or "monthly_geometric_net".
Missing scenarios are reported as missing, never assumed to pass.
--out refuses to overwrite an existing file (no-overwrite rule).
Exit code is 0 on successful analysis regardless of verdict (verdicts live in
the payload so leaders can audit PROMOTE/HOLD/REJECT uniformly); nonzero only
on tool/input errors.
"""

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "configs" / "opencode_gatecheck.json"
KNOWN_SCENARIOS = ("normal", "fee_stress", "execution_stress")


def _pct_or_na(x, ndigits=1) -> str:
    """None-safe percent formatting; 'n/a' when x is None/non-numeric.

    Crash-proofing for losing books (total_net <= 0 -> None shares/gini).
    For numeric x the output is byte-identical to f"{x:.{ndigits}%}".
    """
    return f"{x:.{ndigits}%}" if isinstance(x, (int, float)) else "n/a"


def _num_or_na(x, fmt: str) -> str:
    """None-safe numeric formatting with an explicit format spec."""
    return format(x, fmt) if isinstance(x, (int, float)) else "n/a"


def _signed_pct_or_na(x, ndigits=1) -> str:
    """None-safe signed percent formatting (baseline deltas)."""
    return f"{x:+.{ndigits}%}" if isinstance(x, (int, float)) else "n/a"


def load_json(path: Path) -> dict:
    with Path(path).open("r", encoding="utf-8") as fh:
        return json.load(fh)


def scenario_dicts(branch_node: dict) -> dict:
    """Normalize any branch-node shape to {scenario_name: metrics_dict}."""
    if not isinstance(branch_node, dict):
        raise ValueError("branch node is not a JSON object")
    if isinstance(branch_node.get("scenarios"), dict):
        out = {k: v for k, v in branch_node["scenarios"].items()
               if isinstance(v, dict)}
        if out:
            return out
    found = {k: branch_node[k] for k in KNOWN_SCENARIOS
             if isinstance(branch_node.get(k), dict)}
    if found:
        extra = {k: v for k, v in branch_node.items()
                 if isinstance(v, dict)
                 and ("trades" in v or "monthly_geometric_net" in v)
                 and k not in found and k != "gate"}
        found.update(extra)
        return found
    if "monthly_geometric_net" in branch_node or "trades" in branch_node:
        return {"normal": branch_node}
    raise ValueError(
        "branch node matches no known shape (flat scenarios / "
        "'scenarios' nesting / flat fee-tier metrics)")


def pick_branch(summary: dict, requested: str | None,
                trades_n: int | None) -> str:
    branches = summary.get("branches")
    if not isinstance(branches, dict) or not branches:
        raise ValueError("summary.json has no non-empty 'branches' object")
    if requested:
        if requested not in branches:
            raise ValueError(
                f"branch '{requested}' not in summary; "
                f"available: {sorted(branches)}")
        return requested
    if len(branches) == 1:
        return next(iter(branches))
    if trades_n is not None:
        matches = []
        for name, node in branches.items():
            try:
                sc = scenario_dicts(node)
            except ValueError:
                continue
            normal = sc.get("normal")
            if (isinstance(normal, dict) and normal.get("trades") == trades_n):
                matches.append(name)
        if len(matches) == 1:
            return matches[0]
    raise ValueError(
        "summary holds several branches; pass --branch explicitly. "
        f"Available: {sorted(branches)}")


def check_gate(scenarios: dict, gate_cfg: dict) -> tuple[dict, bool, list]:
    monthly_min = gate_cfg["monthly_min"]
    dd_max = gate_cfg["dd_max"]
    fills_min = gate_cfg["fills_min"]
    per, reasons, overall = {}, [], True
    for name, m in scenarios.items():
        mo = m.get("monthly_geometric_net")
        dd = m.get("max_drawdown")
        fills = m.get("trades")
        mo_pass = mo is not None and mo >= monthly_min
        dd_pass = dd is not None and dd >= -dd_max
        fills_pass = fills is not None and fills >= fills_min
        scen_pass = mo_pass and dd_pass and fills_pass
        per[name] = {"monthly_geometric_net": mo, "max_drawdown": dd,
                     "fills": fills, "monthly_pass": bool(mo_pass),
                     "dd_pass": bool(dd_pass), "fills_pass": bool(fills_pass),
                     "scenario_pass": bool(scen_pass)}
        if not scen_pass:
            overall = False
    if any(not v["monthly_pass"] for v in per.values()):
        bad = sorted(k for k, v in per.items() if not v["monthly_pass"])
        reasons.append("monthly-fail")
        reasons.extend(f"monthly-fail({s})" for s in bad)
    if any(not v["fills_pass"] for v in per.values()):
        bad = sorted(k for k, v in per.items() if not v["fills_pass"])
        reasons.append("fills-fail")
        if "execution_stress" in bad:
            reasons.append("fills-exec-fail")
        reasons.extend(f"fills-fail({s})" for s in bad)
    if any(not v["dd_pass"] for v in per.values()):
        bad = sorted(k for k, v in per.items() if not v["dd_pass"])
        reasons.append("dd-breach")
        reasons.extend(f"dd-breach({s})" for s in bad)
    return per, overall, reasons


def gini_relative_mean_abs_diff(values) -> float | None:
    """v61 Gini: sum|x_i-x_j| / (2 n^2 mu); None if mu <= 0."""
    import numpy as np

    x = np.asarray(values, dtype=float)
    n = x.size
    mu = x.mean() if n else float("nan")
    if n == 0 or not (mu > 0):
        return None
    return float(abs(x[:, None] - x[None, :]).sum() / (2 * n * n * mu))


def analyze_concentration(trades_path: Path, rule: dict) -> dict:
    """v61 concentration on a normal_trades.csv (exit_time + net_pnl)."""
    df = pd.read_csv(trades_path)
    for col in ("exit_time", "net_pnl"):
        if col not in df.columns:
            raise ValueError(f"{trades_path}: missing column {col}")
    df["exit_time"] = pd.to_datetime(df["exit_time"], utc=True)
    df = df.sort_values("exit_time").reset_index(drop=True)
    total_net = float(df["net_pnl"].sum())

    df["month"] = df["exit_time"].dt.strftime("%Y-%m")
    monthly = df.groupby("month").agg(n_trades=("net_pnl", "size"),
                                      net_pnl=("net_pnl", "sum")).reset_index()
    span = pd.period_range(monthly["month"].min(), monthly["month"].max(),
                           freq="M").strftime("%Y-%m")
    monthly = monthly.set_index("month").reindex(span, fill_value=0)
    monthly.index.name = "month"
    monthly = monthly.reset_index()
    nets = monthly["net_pnl"].tolist()
    best_row = monthly.loc[monthly["net_pnl"].idxmax()]
    worst_row = monthly.loc[monthly["net_pnl"].idxmin()]
    top3_sum = float(monthly["net_pnl"].nlargest(3).sum())
    top1_share = float(best_row["net_pnl"] / total_net) if total_net > 0 else None
    top3_share = float(top3_sum / total_net) if total_net > 0 else None

    px = df.sort_values("net_pnl", ascending=False).reset_index(drop=True)
    top1_trade_share = float(px["net_pnl"].iloc[0] / total_net) if total_net > 0 else None
    top5_share = float(px["net_pnl"].head(5).sum() / total_net) if total_net > 0 else None

    reasons, verdict = [], "diffuse (PASS)"
    if not (total_net > 0):
        verdict = "concentrated (FAIL)"
        reasons.append("total_net <= 0 (no positive base)")
    else:
        if top1_share is not None and top1_share > rule["top1_month_share_gt"]:
            reasons.append(
                f"top1 month {top1_share:.1%} > {rule['top1_month_share_gt']:.0%}")
        if top3_share is not None and top3_share > rule["top3_months_share_gt"]:
            reasons.append(
                f"top3 months {top3_share:.1%} > {rule['top3_months_share_gt']:.0%}")
        if reasons:
            verdict = "concentrated (FAIL)"
    return {
        "n_trades": int(len(df)),
        "exit_span": [str(df["exit_time"].min()), str(df["exit_time"].max())],
        "total_net": total_net,
        "n_months_total": int(len(monthly)),
        "n_positive_months": int((monthly["net_pnl"] > 0).sum()),
        "n_negative_months": int((monthly["net_pnl"] < 0).sum()),
        "best_month": {"month": str(best_row["month"]),
                       "net": float(best_row["net_pnl"])},
        "worst_month": {"month": str(worst_row["month"]),
                        "net": float(worst_row["net_pnl"])},
        "top1_month_share": top1_share,
        "top3_months_share": top3_share,
        "gini_monthly_net": gini_relative_mean_abs_diff(nets),
        "top1_trade_share": top1_trade_share,
        "top5_trades_share": top5_share,
        "verdict": verdict,
        "verdict_reasons": reasons,
    }


def fee_slope_from_summary(summary: dict) -> dict | None:
    """OLS d(monthly)/d(fee_rate) over sibling fee-tier branches, if present."""
    import numpy as np

    xs, ys, names = [], [], []
    branches = summary.get("branches", {})
    for name, node in branches.items():
        if isinstance(node, dict) and "fee_rate_per_fill" in node \
                and isinstance(node.get("monthly_geometric_net"), (int, float)):
            xs.append(float(node["fee_rate_per_fill"]))
            ys.append(float(node["monthly_geometric_net"]))
            names.append(name)
    if len(xs) < 2:
        return None
    x = np.asarray(xs)
    y = np.asarray(ys)
    slope, intercept = np.polyfit(x, y, 1)
    breakeven = (-intercept / slope) if slope < 0 else None
    return {"n_tiers": len(xs), "branches": names,
            "slope_dmonthly_dfee": float(slope),
            "intercept": float(intercept),
            "breakeven_fee_per_fill": float(breakeven) if breakeven else None}


def analyze_robustness(scenarios: dict, summary: dict,
                       rob_cfg: dict, gate_cfg: dict) -> dict:
    normal = scenarios.get("normal", {})
    fee = scenarios.get("fee_stress", {})
    ex = scenarios.get("execution_stress", {})
    n_mo = normal.get("monthly_geometric_net")
    fee_drag = (n_mo - fee["monthly_geometric_net"]
                if n_mo is not None
                and isinstance(fee.get("monthly_geometric_net"), (int, float))
                else None)
    exec_drop = (n_mo - ex["monthly_geometric_net"]
                 if n_mo is not None
                 and isinstance(ex.get("monthly_geometric_net"), (int, float))
                 else None)
    dds = [m["max_drawdown"] for m in scenarios.values()
           if isinstance(m.get("max_drawdown"), (int, float))]
    worst_dd = min(dds) if dds else None
    dd_margin = (gate_cfg["dd_max"] + worst_dd) if worst_dd is not None else None
    warns = []
    if exec_drop is not None and exec_drop > rob_cfg["exec_drop_warn_pp_gt"]:
        warns.append(f"exec-drop {exec_drop * 100:.2f}pp normal->exec "
                     f"> {rob_cfg['exec_drop_warn_pp_gt'] * 100:.2f}pp")
    if dd_margin is not None and dd_margin < rob_cfg["dd_margin_warn_lt"]:
        warns.append(f"DD margin thin: {dd_margin * 100:.2f}pp "
                     f"< {rob_cfg['dd_margin_warn_lt'] * 100:.2f}pp")
    return {"normal_monthly": n_mo,
            "fee_monthly": fee.get("monthly_geometric_net"),
            "exec_monthly": ex.get("monthly_geometric_net"),
            "fee_drag_pp": fee_drag, "exec_drop_pp": exec_drop,
            "worst_scenario_dd": worst_dd, "dd_margin": dd_margin,
            "fee_slope": fee_slope_from_summary(summary),
            "warns": warns}


def analyze_baseline(baseline_path: Path | None, rule: dict) -> dict | None:
    if baseline_path is None:
        return None
    conc = analyze_concentration(baseline_path, rule)
    return {"trades_csv": str(baseline_path), "total_net": conc["total_net"],
            "top1_month_share": conc["top1_month_share"],
            "top3_months_share": conc["top3_months_share"],
            "top5_trades_share": conc["top5_trades_share"]}


def decide(gate_overall: bool, gate_reasons: list, conc: dict,
           trade_notes: dict, rule: dict) -> tuple[str, list]:
    reasons = list(gate_reasons)
    conc_fail = conc["verdict"].startswith("concentrated")
    if conc_fail:
        reasons.append("concentrated")
        reasons.extend(f"concentrated({r})" for r in conc["verdict_reasons"])
    if not (conc["total_net"] > 0):
        return "REJECT", reasons or ["total_net <= 0"]
    if "fills-fail" in gate_reasons or conc_fail:
        return "REJECT", reasons
    if gate_overall:
        return "PROMOTE", ["all present scenarios pass gate",
                           "concentration diffuse (PASS)"]
    caveats = []
    top5 = conc["top5_trades_share"]
    if top5 is not None and top5 > trade_notes["top5_share_severe_gt"]:
        caveats.append(f"trade-concentration SEVERE: top5={top5:.1%}")
    elif top5 is not None and top5 > trade_notes["top5_share_warn_gt"]:
        caveats.append(f"trade-concentration warn: top5={top5:.1%}")
    return "HOLD", reasons + caveats


def run(summary_path: Path, trades_path: Path, branch: str | None,
        baseline_path: Path | None, config: dict) -> dict:
    summary = load_json(summary_path)
    n_trades = None
    try:
        n_trades = int(pd.read_csv(trades_path, usecols=["net_pnl"]).shape[0])
    except Exception:
        n_trades = None
    branch_name = pick_branch(summary, branch, n_trades)
    scenarios = scenario_dicts(summary["branches"][branch_name])
    per, overall, gate_reasons = check_gate(scenarios, config["gate"])
    conc = analyze_concentration(trades_path, config["concentration_rule"])
    rob = analyze_robustness(scenarios, summary, config["robustness"],
                             config["gate"])
    base = analyze_baseline(baseline_path, config["concentration_rule"])
    base_block = None
    if base is not None:
        base_block = {
            **base,
            "d_total_net_vs_baseline": conc["total_net"] - base["total_net"],
            "d_top5_share_vs_baseline":
                (conc["top5_trades_share"] - base["top5_trades_share"]
                 if conc["top5_trades_share"] is not None
                 and base["top5_trades_share"] is not None else None),
        }
    decision, decision_reasons = decide(overall, gate_reasons, conc,
                                       config["trade_concentration_notes"],
                                       config["decision_rule"])
    best_mo = max((v["monthly_geometric_net"] for v in per.values()
                   if isinstance(v["monthly_geometric_net"], (int, float))),
                  default=None)
    # None-safe: losing books carry None shares/gini; keep the exact legacy
    # formatting whenever values are numeric (winning books unchanged).
    best_mo_s = (f"{best_mo * 100:.3f}%"
                 if isinstance(best_mo, (int, float)) else "n/a")
    line = (f"{decision} -- {branch_name}: "
            + ("gate PASS all present scenarios; "
               if overall else
               f"gate FAIL [{'; '.join(gate_reasons)}] "
               f"(best monthly {best_mo_s} vs "
               f"{config['gate']['monthly_min'] * 100:.0f}% min); ")
            + f"concentration {conc['verdict']} "
            f"(top1mo={_pct_or_na(conc['top1_month_share'])}, "
            f"top3mo={_pct_or_na(conc['top3_months_share'])}, "
            f"top5tr={_pct_or_na(conc['top5_trades_share'])}, "
            f"gini={_num_or_na(conc['gini_monthly_net'], '.3f')}); "
            + (f"exec-drop {rob['exec_drop_pp'] * 100:.2f}pp; " if rob["exec_drop_pp"] is not None else "")
            + (f"DD margin {rob['dd_margin'] * 100:.2f}pp."
               if rob["dd_margin"] is not None else ""))
    return {
        "tool": "opencode_gatecheck",
        "version": config.get("version", "1.0.0"),
        "inputs": {"summary": str(summary_path), "branch": branch_name,
                   "trades": str(trades_path),
                   "baseline": str(baseline_path) if baseline_path else None,
                   "scenarios_present": sorted(per)},
        "gate": {"thresholds": config["gate"], "per_scenario": per,
                 "overall_pass": overall, "fail_reasons": gate_reasons},
        "concentration": {**conc, "rule": config["concentration_rule"]},
        "robustness": rob,
        "baseline_comparison": base_block,
        "decision": decision,
        "decision_line": line,
        "decision_reasons": decision_reasons,
        "warnings": config.get("warnings", []),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Gate + concentration + robustness check for one branch.")
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--trades", type=Path, required=True)
    parser.add_argument("--branch", default=None)
    parser.add_argument("--baseline", type=Path, default=None)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)

    config = load_json(args.config)
    result = run(args.summary, args.trades, args.branch, args.baseline, config)

    g = result["gate"]
    c = result["concentration"]
    r = result["robustness"]
    print(f"branch: {result['inputs']['branch']} "
          f"(scenarios: {', '.join(result['inputs']['scenarios_present'])})")
    print(f"gate: {'PASS' if g['overall_pass'] else 'FAIL'} "
          f"[{'; '.join(g['fail_reasons']) or 'all sub-gates pass'}]")
    for name, v in g["per_scenario"].items():
        mo, dd = v["monthly_geometric_net"], v["max_drawdown"]
        mo_s = f"{mo * 100:.3f}%" if isinstance(mo, (int, float)) else "n/a"
        dd_s = f"{dd * 100:.2f}%" if isinstance(dd, (int, float)) else "n/a"
        print(f"  {name}: mo={mo_s} "
              f"dd={dd_s} fills={v['fills']} "
              f"-> {'pass' if v['scenario_pass'] else 'FAIL'}")
    print(f"concentration: {c['verdict']} top1mo={_pct_or_na(c['top1_month_share'])} "
          f"top3mo={_pct_or_na(c['top3_months_share'])} gini={_num_or_na(c['gini_monthly_net'], '.3f')} "
          f"top5tr={_pct_or_na(c['top5_trades_share'])}")
    fee_slope = r["fee_slope"]
    print(f"robustness: exec_drop="
          f"{r['exec_drop_pp'] * 100:.2f}pp" if r["exec_drop_pp"] is not None
          else "robustness: exec_drop=n/a", end="")
    print(f" fee_drag={r['fee_drag_pp'] * 100:.2f}pp"
          if r["fee_drag_pp"] is not None else " fee_drag=n/a", end="")
    print(f" dd_margin={r['dd_margin'] * 100:.2f}pp"
          if r["dd_margin"] is not None else " dd_margin=n/a", end="")
    print(f" fee_slope={fee_slope['slope_dmonthly_dfee']:.3f}"
          if fee_slope else " fee_slope=n/a (no fee-tier branches)", end="; ")
    print(f"warns=[{'; '.join(r['warns']) or 'none'}]")
    if result["baseline_comparison"] is not None:
        b = result["baseline_comparison"]
        print(f"vs baseline: d_total_net={b['d_total_net_vs_baseline']:+.2f} "
              f"d_top5={_signed_pct_or_na(b['d_top5_share_vs_baseline'])}")
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
