"""oc_papercmp driver: reuses scripts/paper_compare.py, writes results.json.

Single process, JSON only, no market data (see PLAN.md).
"""

import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
TOOL = ROOT / "scripts" / "paper_compare.py"

spec = importlib.util.spec_from_file_location("paper_compare", TOOL)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def main():
    rep = mod.build_report()
    out = HERE / "results.json"
    out.write_text(json.dumps(rep, indent=1, default=str))
    print(f"saved {out}")
    mod.print_tables(rep)


if __name__ == "__main__":
    main()
