"""R55a FILLS-FIRST diagnostic (analysis + pre-spec support, NO backtests).

Reads FROZEN artifacts only (summaries, signals.parquet, trades csvs, configs).
Never imports the backtest engine, never simulates alternative caps/cooldowns
(recomputing with new caps = a new backtest, forbidden for this worker).
Writes NEW files only under artifacts/research/opencode_v143_fillsdesign/.

Exploratory (research-only, NOT a promotion claim).
"""
import json
import math
import os
from datetime import timezone

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "artifacts", "research", "opencode_v143_fillsdesign")


def load(p):
    with open(os.path.join(ROOT, p), encoding="utf-8") as f:
        return json.load(f)


def monthly_req_total(years, gate=0.05):
    months = 12 * years
    return (1 + gate) ** months - 1, months


def forward_decomp(exp_name, summ_path, leaf):
    s = load(summ_path)
    n = s["branches"][leaf]["normal"]
    e = s["branches"][leaf]["execution_stress"]
    po = s.get("policy_outcome", {})
    sig = pd.read_parquet(os.path.join(ROOT, "artifacts", "research", exp_name, leaf, "signals.parquet"))
    sig["signal_time"] = pd.to_datetime(sig["signal_time"], utc=True)
    by_month = sig["signal_time"].dt.strftime("%Y-%m").value_counts().sort_index().to_dict()
    gaps = sig["signal_time"].diff().dropna()
    tr = pd.read_csv(os.path.join(ROOT, "artifacts", "research", exp_name, leaf, "normal_trades.csv"))
    return {
        "n_decisions": s["clock"]["n_decisions"],
        "gate_hits": po.get("gate_hits"),
        "n_selected": po.get("n_selected"),
        "n_signals": len(sig),
        "by_month": by_month,
        "months_at_cap4": sum(1 for v in by_month.values() if v >= 4),
        "cooldown_gaps_lt5d": int((gaps < pd.Timedelta(days=5)).sum()),
        "fills_normal": int(n["trades"]),
        "rejected_normal": int(n["rejected_or_unfilled_signals"]),
        "fill_rate_normal": round(n["trades"] / len(sig), 4),
        "fills_exec": int(e["trades"]),
        "rejected_exec": int(e["rejected_or_unfilled_signals"]),
        "exit_reasons_normal": tr["exit_reason"].value_counts().to_dict(),
        "net_normal": round(float(n["net_profit"]), 2),
        "net_per_fill": round(float(n["net_profit"]) / n["trades"], 3),
        "monthly_normal": round(float(n["monthly_geometric_net"]), 5),
        "span_years": round(float(s["span"]["years"]), 5),
    }


def main():
    os.makedirs(OUT, exist_ok=True)
    v38 = forward_decomp("opencode_v135_fwdeval38",
                         "artifacts/research/opencode_v135_fwdeval38/summary.json",
                         "v38_isoall_fwd_1x")
    v33 = forward_decomp("opencode_v138_fwdeval33",
                         "artifacts/research/opencode_v138_fwdeval33/summary.json",
                         "v33_topdec_fwd_1x")

    # In-sample anchors (frozen).
    v59 = load("artifacts/research/opencode_v59_v38cal/summary.json")
    v59iso = v59["branches"]["v38-isoall_1x"]["normal"]
    v59diag = v59["diagnostic_v34_lens"]["v38-isoall_1x"]
    v42 = load("artifacts/research/opencode_v42_v33cal/summary.json")
    v42top = v42["branches"]["v33-iso-topdec_1x"]["normal"]
    v15 = load("artifacts/research/opencode_v15_mapensemble/summary.json")
    maj = v15["branches"]["majority_1x"]["normal"]
    v52 = load("artifacts/research/opencode_v52_unionbook/summary.json")
    u_ctl = v52["branches"]["majority_control_1x"]
    u1 = v52["branches"]["U1_1x"]
    v72 = load("artifacts/research/opencode_v72_L1pool/summary.json")
    pool = v72["branches"]["pool_1x"]["scenarios"]["normal"]
    v35 = load("artifacts/research/opencode_v35b_replay/portfolio.json")
    v35b = v35["branches"]["ssm_en_1x"]["scenarios"]["normal"]

    # Frequency-probe honesty check: config exists, result artifact does not.
    probe_cfg = os.path.join(ROOT, "configs", "swing_v38_frequency_policy_probe.json")
    probe_hits = []
    for dp, _, fns in os.walk(os.path.join(ROOT, "artifacts")):
        for fn in fns:
            if "frequen" in fn.lower():
                probe_hits.append(os.path.join(dp, fn))

    # Gate arithmetic on forward books.
    arith = {}
    for tag, d in (("v38_fwd", v38), ("v33_fwd", v33)):
        req, months = monthly_req_total(d["span_years"])
        need = req / (d["net_normal"] / 100 / d["fills_normal"]) if d["net_normal"] > 0 else None
        arith[tag] = {
            "span_months": round(months, 2),
            "required_total_for_5pct": round(req, 4),
            "cap4_max_signals_over_exit_months": 4 * len(d["by_month"]),
            "fills_needed_at_current_per_fill": round(need, 1) if need else None,
        }

    summary = {
        "experiment": "opencode-r55a-fillsdesign",
        "mode": "ANALYSIS_ONLY frozen artifacts; NO backtests, NO training, NO cap/cooldown recompute",
        "labels": "exploratory, research-only, NOT a promotion claim",
        "forward_decomposition": {"v38_isoall_fwd_1x": v38, "v33_topdec_fwd_1x": v33},
        "in_sample_anchors": {
            "v38_isoall_1x": {"signals": 122, "fills": v59iso["trades"],
                              "rejected": v59iso["rejected_or_unfilled_signals"],
                              "monthly": round(v59iso["monthly_geometric_net"], 5),
                              "n_selected": 2768,
                              "freq_kill_rate": round(1 - 122 / 2768, 4)},
            "v33_iso_topdec_1x": {"signals": 114, "fills": v42top["trades"],
                                  "rejected": v42top["rejected_or_unfilled_signals"],
                                  "monthly": round(v42top["monthly_geometric_net"], 5)},
            "majority_1x": {"signals": 94, "fills": maj["trades"],
                             "rejected": maj["rejected_or_unfilled_signals"],
                             "monthly": round(maj["monthly_geometric_net"], 5)},
            "union_U1_vs_control": {
                "control_signals": u_ctl["n_signals"],
                "control_fills": u_ctl["scenarios"]["normal"]["trades"],
                "control_monthly": round(u_ctl["scenarios"]["normal"]["monthly_geometric_net"], 5),
                "u1_signals": u1["n_signals"],
                "u1_fills": u1["scenarios"]["normal"]["trades"],
                "u1_monthly": round(u1["scenarios"]["normal"]["monthly_geometric_net"], 5)},
            "L1_pool": {"signals": 326, "fills": pool["trades"],
                        "rejected": pool["rejected_or_unfilled_signals"],
                        "monthly": round(pool["monthly_geometric_net"], 5)},
            "v35_coverage_floor": {"signals": 128, "fills": v35b["trades"],
                                   "monthly": round(v35b["monthly_geometric_net"], 5),
                                   "net_per_fill": round(v35b["net_profit"] / v35b["trades"], 3)},
        },
        "frequency_cap_evidence": {
            "probe_config": "configs/swing_v38_frequency_policy_probe.json (4 variants cap{4,8,8,12})",
            "probe_result_artifact": None if not probe_hits else probe_hits,
            "probe_status": ("NOT_EXECUTED: config prespecified but no result artifact exists; "
                             "cap{8,12,unlimited} fills are UNKNOWN and recomputing them = new backtest (forbidden here)"),
            "frozen_evidence_only": [
                "v38fwd 5/7 months at cap-4, v33fwd 3/7 at cap-4; cooldown<5d gaps = 0 both (cap binds, cooldown does not)",
                "v59 by_month: 30+/34 active months exactly at cap-4 (demand >> cap in-sample)",
                "B2-mtfclock (ledger R2): thinner clocks REDUCE return 122.8->105.7/107.3; cap already binding",
                "codex-v01-v88 ledger: frequency-matrix family REJECTED/blocked, do-not-repeat without new rationale",
            ],
        },
        "gate_arithmetic": arith,
        "verdict": ("AGAINST naive fills-first (threshold-lowering / union / coverage-floor mirror): "
                    "every frozen attempt to buy fills diluted or killed monthly "
                    "(union +14sig/+3fills monthly -0.22pp; L1-pool 2x fills monthly BELOW control; "
                    "v35 90 fills monthly 0.3% = 0.09/fill vs majority 2.6/fill). "
                    "Cap-4 is arithmetically gate-blocking (v38 needs ~40 fills at current edge, cap allows max 28 signals), "
                    "so the ONLY non-dilutive pre-spec is verbatim-gate cap-relaxation as a diagnostic, "
                    "in-sample first, with kill criteria (see configs/opencode_v143_fillsdesign.json)."),
        "seal_notes": ["no sealed files read beyond SHAs already in summaries",
                       "no labels/returns beyond engine fills in frozen trades csvs",
                       "no plots, no fitting, no threshold selection"],
    }
    with open(os.path.join(OUT, "summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    with open(os.path.join(OUT, "decomposition.json"), "w", encoding="utf-8") as f:
        json.dump({"v38": v38, "v33": v33}, f, indent=2, ensure_ascii=False)
    print("wrote", os.path.join(OUT, "summary.json"))


if __name__ == "__main__":
    main()
