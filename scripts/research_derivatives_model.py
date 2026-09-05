"""Run the two preregistered archive-lag scenarios using unchanged v8 model/policy."""
import torch
import argparse
import json
from pathlib import Path
from types import SimpleNamespace
from walkforward_action_model import run
from agentic_alpha_lab.data.training import sha256


def main(a):
    plan = json.loads(a.plan.read_text())
    parent = json.loads(Path(plan["parent_plan"]).read_text())
    if a.output.exists():
        raise FileExistsError("Choose a new immutable experiment")
    a.output.mkdir(parents=True)
    (a.output / "plan.json").write_text(json.dumps(plan, indent=2))
    (a.output / "driver_source.py").write_text(Path(__file__).read_text())
    summaries = {}
    for scenario in plan["runs"]:
        child = dict(parent, experiment=plan["experiment"] + "-" + scenario["name"],
                     feature_cache=scenario["feature_cache"], data_status=plan["decision"])
        child_path = a.output / (scenario["name"] + "_plan.json")
        child_path.write_text(json.dumps(child, indent=2))
        target = a.output / scenario["name"]
        run(SimpleNamespace(plan=child_path, output=target))
        summaries[scenario["name"]] = json.loads((target / "summary.json").read_text())
    result = {"plan": plan, "plan_sha256": sha256(a.plan), "driver_sha256": sha256(Path(__file__)),
              "runs": summaries, "both_delays_pass": all(r["advance_to_further_research"] for r in summaries.values()),
              "independent_test": False, "live_approved": False}
    (a.output / "summary.json").write_text(json.dumps(result, indent=2))
    print(json.dumps({"both_delays_pass": result["both_delays_pass"]}), flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--plan", type=Path, default=Path("configs/swing_v10_derivatives.json"))
    p.add_argument("--output", type=Path, required=True)
    main(p.parse_args())
