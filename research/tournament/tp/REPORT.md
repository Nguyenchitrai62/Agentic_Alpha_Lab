# tp worker report (saved by the leader from the worker's hand-back, 2026-10-05)
Gain vs deployed TP agent (sizes = size_dep), 2021 / 2022 / 2023 / 2024 / total:
- V1 cls: -0.375 / +0.026 / +0.665 / +0.345 / +0.661 (graduates)
- V2 diff: -0.237 / +0.093 / +0.823 / +0.070 / +0.749 (graduates; best)
- V3 mlp: +0.085 total (degenerate, collapsed to 1.5)
- V4 bot_only (V2 + fill-time x): +0.726 (2/4 years, no)
- reference always TP 1.5: -0.468 / +0.043 / +0.482 / +0.309 / +0.366 (graduates!); always 1.0: -1.587
Most of the gain = using TP 1.5 more often; model gain over always-1.5 = +0.30..+0.38, bootstrap P(<=0) ~0.35 (not significant).
Engine test should include the TP-1.5 control. Files: PLAN.md, tp_bandit.py, score_*.json, diagnostics.json.
