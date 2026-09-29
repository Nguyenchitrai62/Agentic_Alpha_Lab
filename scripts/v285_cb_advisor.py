"""Live Coinbase-premium member (D) for the v285 D2 paper pipeline - research output only, no orders.

Runs only the frozen v154 Coinbase model set (models/frozen/v154_cb_models.pkl, the same v144-style builder with the Coinbase premium
features; audited in v285) after appending the new Coinbase candles, and logs it as candidate 'v285_CB' in the advisor shadow log. The
trade plan converts the row to research units exactly like the other members: (perp + spot) / (0.8 x portfolio scale).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def advise() -> dict:
    v154 = _load("v154_for_v285", ROOT / "scripts/v154_advisor.py")
    appended = v154.cbu.update()
    d = v154.cbm.advise()
    return dict(candidate="v285_CB", decision_bar_close=d["decision_bar_close"], perp_weight=d["perp_weight"], spot_weight=d["spot_weight"],
                portfolio_scale=d["portfolio_scale"], carry_on=d.get("carry_on"), models_cutoff=d.get("models_cutoff"), data_appended=appended,
                note="advisory only; member D (Coinbase premium) of the v285 D2 paper pipeline")


if __name__ == "__main__":
    import json
    print(json.dumps(advise(), indent=1, default=str))
