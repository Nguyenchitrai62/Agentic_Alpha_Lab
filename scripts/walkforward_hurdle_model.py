import torch
import argparse
from pathlib import Path
from walkforward_action_model import run
from agentic_alpha_lab.models import hurdle_value


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path, default=Path("configs/swing_v9_hurdle_walkforward.json"))
    parser.add_argument("--output", type=Path, required=True)
    run(parser.parse_args(), hurdle_value.fit_hurdle, hurdle_value.predict_hurdle,
        "hurdle_action_model", Path(hurdle_value.__file__))
