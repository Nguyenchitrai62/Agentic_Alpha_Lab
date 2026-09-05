"""Apply declared research gates to an existing report; never tune or trade."""
import argparse
import json
import math
from pathlib import Path


def assess(report, gates):
    result, stress = report["result"], report["fee_stress"]
    checks = {
        "net_positive": result["total_return"] > 0,
        "fee_stress_net_positive": stress["total_return"] > 0,
        "drawdown_within_user_limit": result["max_drawdown"] >= -gates["user_confirmed_maximum_drawdown"],
        "stress_drawdown_within_user_limit": stress["max_drawdown"] >= -gates["user_confirmed_maximum_drawdown"],
        "frequency_within_maximum": all(n <= gates["maximum_alerts_per_month"] for n in report["signals_by_month"].values()),
        "provisional_sample_floor": result["trades"] >= gates["research_minimum_filled_trades"],
        "provisional_month_floor": len(report["signals_by_month"]) >= gates["research_minimum_evaluation_months"],
        "heldout_evaluation": report["split"] == "historical_holdout_no_tuning",
    }
    if "user_target_monthly_geometric_net_return" in gates:
        years=report.get("duration_years")
        valid=isinstance(years,(int,float)) and math.isfinite(years) and years>0
        checks["continuous_calendar_duration_available"]=valid
        target=gates["user_target_monthly_geometric_net_return"]
        for name,scenario in (("normal",result),("fee_stress",stress)):
            ratio=scenario.get("final_equity",0)/scenario.get("initial_equity",100) if scenario.get("initial_equity",100)>0 else 0
            checks[f"{name}_monthly_geometric_target"]=bool(valid and math.isfinite(ratio) and ratio>0 and ratio**(1/(12*years))-1>=target-1e-12)
    return {"checks": checks, "failed_checks": [k for k, v in checks.items() if not v],
            "passes_basic_research_screen": all(checks.values()), "approved_for_live": False,
            "warning": "Even passing this screen does not establish mark-price/queue robustness, calibrated uncertainty or future profit."}


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--report", type=Path, required=True)
    p.add_argument("--gates", type=Path, default=Path("configs/swing_acceptance.json"))
    a = p.parse_args()
    print(json.dumps(assess(json.loads(a.report.read_text()), json.loads(a.gates.read_text())), indent=2))
