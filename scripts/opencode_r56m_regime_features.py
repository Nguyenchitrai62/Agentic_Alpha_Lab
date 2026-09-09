"""Opencode R56-M (v145): tai su dung VERBATIM builders causal cua v28/v35/v38/v39/v40/v41.

Layout DONG BANG: [:40] price, [40:80] deriv, [80:120] flow, [120:125] funding,
[125:129] macro, [129:133] calendar = 133 features. Khong viet lai join.
v145 khong doi features (chi them upweight quiet trong ranking loss).
"""
import torch  # noqa: F401  (torch truoc pandas)
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from opencode_r9m_nextarch_features import (  # noqa: E402
    N_CAL,
    N_DERIV,
    N_FLAT,
    N_FLOW,
    N_FUND,
    N_MACRO,
    N_PRICE,
    build_flat,
    build_calendar,
    build_flow,
    build_funding,
    build_macro,
)

assert N_FLAT == 133
assert (N_PRICE, N_DERIV, N_FLOW, N_FUND, N_MACRO, N_CAL) == (40, 40, 40, 5, 4, 4)

__all__ = ["N_FLAT", "N_PRICE", "N_DERIV", "N_FLOW", "N_FUND", "N_MACRO", "N_CAL",
           "build_flat", "build_calendar", "build_flow", "build_funding", "build_macro"]
