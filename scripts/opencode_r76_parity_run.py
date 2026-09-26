"""W3-VERIFY runner: full raw->equity verification + persist NEW parity files.

RESEARCH ONLY. GPU inference. Writes ONLY to
artifacts/research/opencode_r76_real_inference/parity/VERIFY_*.json
(never touches PREP_READY.json / summary.json).
"""
import torch  # noqa: F401  (torch truoc pandas)

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import opencode_r76_parity_verify as V  # noqa: E402


def main() -> int:
    out = V.run_full_comparison()
    files = V.save_verification(out)
    print(json.dumps({"verdict": "PASS" if out["pass"] else "FAIL",
                      "files": files,
                      "signal_identity": out["signal_identity"],
                      "equity_parity": out["equity_parity"],
                      "equity_deltas": out["equity_deltas"],
                      "no_replay_pass": out["no_replay_audit"]["pass"],
                      "prefix": out["prefix"],
                      "future": out["future_perturbation"],
                      "restart": out["restart"],
                      "coverage": {k: v for k, v in out["coverage"].items()
                                   if k != "stream_actions"}},
                     indent=2, default=str))
    return 0 if out["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
