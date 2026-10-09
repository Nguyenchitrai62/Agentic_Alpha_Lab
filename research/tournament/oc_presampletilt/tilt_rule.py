"""Pure tilt-rule helpers for oc_presampletilt (no data access; unit-tested).

Frozen rule (see PLAN.md): the EARLIEST fits (anchor 2021-09-24) from oc_voltilt
(V_RV6 / V_GARCH) and oc_chronos (C2), applied to ALL pre-sample years on all
4 shifts. hi/lo = 1.25/0.75, missing/NaN risk -> 1. Labelled everywhere
"fit from later data, rule frozen".
"""
from __future__ import annotations

import numpy as np

# Frozen anchor-2021 fits (copied verbatim from oc_voltilt/fits.json + oc_chronos/fits.json).
FROZEN_2021 = {
    "V_RV6": {"direction": 1, "q20": 0.837211709240698,
              "q80": 1.9839920144443897, "rho": 0.0805},
    "V_GARCH": {"direction": 1, "q20": 1.0241413111212145,
                "q80": 1.8039629065556178, "rho": 0.0929},
    "C2": {"direction": 1, "q20": 1.110054237503456,
           "q80": 2.8608138206510407, "rho": 0.0364},
}

HI = 1.25
LO = 0.75


def assign_mult(risk: float, direction: int, q20: float, q80: float,
                hi: float = HI, lo: float = LO) -> float:
    """Final multiplier for one (coin, holding bar); NaN risk -> 1.0."""
    r = float(risk)
    if not np.isfinite(r):
        return 1.0
    if direction > 0:  # high risk favourable
        if r >= q80:
            return hi
        if r <= q20:
            return lo
        return 1.0
    if r >= q80:  # high risk unfavourable
        return lo
    if r <= q20:
        return hi
    return 1.0


def variant_mult(risk: float, variant: str) -> float:
    """Multiplier for a frozen variant name (V_RV6 / V_GARCH / C2)."""
    f = FROZEN_2021[variant]
    return assign_mult(risk, f["direction"], f["q20"], f["q80"], HI, LO)
