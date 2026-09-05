import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from check_swing_acceptance import assess


def test_five_percent_requires_calendar_compounding_not_fold_or_total_gain():
    gates={"user_confirmed_maximum_drawdown":.2,"maximum_alerts_per_month":4,
           "research_minimum_filled_trades":30,"research_minimum_evaluation_months":12,
           "user_target_monthly_geometric_net_return":.05}
    scenario={"total_return":1.05**12-1,"initial_equity":100,"final_equity":100*1.05**12,"max_drawdown":-.1,"trades":40}
    report={"result":scenario,"fee_stress":scenario,"signals_by_month":{str(i):2 for i in range(12)},"split":"historical_holdout_no_tuning","duration_years":1}
    assert assess(report,gates)["checks"]["normal_monthly_geometric_target"]
    report["duration_years"]=3
    assert not assess(report,gates)["checks"]["normal_monthly_geometric_target"]
    del report["duration_years"]
    assert not assess(report,gates)["passes_basic_research_screen"]
