"""oc_spotlongs engine: verbatim engine_user.simulate + SPOT PATCH (book-long venue).

The audited engine (research/parallel/rounds/parallel-20260906-r2/engine_user/
engine_user.py) is loaded from source, asserted verbatim at the patched sites,
then patched minimally:
  P1 signature: + spot_route=None, borrow_apr=0.0.
  P2 book funding: a spot-routed long pays 0 funding (saved tracked).
  P3 borrow: per-bar USDT interest on the spot-routed long leg where leveraged,
      deducted from bar cash (same convention as funding: close-equity only).
  P4 bars: record per-bar funding_saved + borrow (for CTRL/stress overlays).
With spot_route=None and borrow_apr=0.0 the patched simulate is bit-identical
to the audited engine (V0 gate asserts REF == v421 G2 to the digit).
Dip sleeve is untouched (stays perp, pays gate funding on timeouts as base).
Spot-perp fill basis assumed 0 (same 1m cube; labelled in PLAN/REPORT).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
EU_PATH = (ROOT / "research/parallel/rounds/parallel-20260906-r2"
           / "engine_user/engine_user.py")

_ANCHOR_SIG = "sleeve_sl_coin=None, sleeve_gross_cap=None):"
_ANCHOR_HERE = "HERE = Path(__file__).parent"
_ANCHOR_FUND_A = ("            if fr_bar is not None:  # actual signed funding "
                  "(side row): longs pay, shorts receive rate * notional")
_ANCHOR_FUND_B = ("                fund = FUND_LONG * max(cur_q, 0.0) * o2[i][a] "
                  "if settle[i] else 0.0")
_ANCHOR_ASSET = "        asset_pnl = np.zeros(na)"
_ANCHOR_LOOP_END = ("            q[a], entry[a] = cur_q, cur_e\n"
                    "        # dip sleeve")
_ANCHOR_BARS = ("                             pending=[float(T[\"px\"][k]) if T[\"side\"][k] "
                "else float(\"nan\") for k in range(na)]))")


def patched_source() -> str:
    src = EU_PATH.read_text(encoding="utf-8")
    for anchor in (_ANCHOR_SIG, _ANCHOR_HERE, _ANCHOR_FUND_A, _ANCHOR_FUND_B,
                   _ANCHOR_ASSET, _ANCHOR_LOOP_END, _ANCHOR_BARS):
        assert src.count(anchor) == 1, anchor  # verbatim gate: exactly one site
    eu_dir = EU_PATH.parent.as_posix()
    src = src.replace(
        _ANCHOR_HERE,
        f"HERE = Path({eu_dir!r})  # SPOT PATCH P0: keep audited relative imports",
        1)
    src = src.replace(
        _ANCHOR_SIG,
        "sleeve_sl_coin=None, sleeve_gross_cap=None, spot_route=None, borrow_apr=0.0):",
        1)
    src = src.replace(
        _ANCHOR_FUND_B,
        ("                fund = FUND_LONG * max(cur_q, 0.0) * o2[i][a] if settle[i] else 0.0\n"
         "                if fund > 0.0 and spot_route is not None and bool(spot_route(i, a)):  # SPOT PATCH P2\n"
         "                    fsave_bar += fund\n"
         "                    stats[\"funding_saved\"] = stats.get(\"funding_saved\", 0.0) + fund\n"
         "                    fund = 0.0"),
        1)
    src = src.replace(
        _ANCHOR_ASSET,
        "        asset_pnl = np.zeros(na)\n        fsave_bar = 0.0  # SPOT PATCH P2/P4",
        1)
    src = src.replace(
        _ANCHOR_LOOP_END,
        ("            q[a], entry[a] = cur_q, cur_e\n"
         "        if borrow_apr and spot_route is not None:  # SPOT PATCH P3\n"
         "            lspot = 0.0\n"
         "            for _a in range(na):\n"
         "                if spot_route(i, _a) and np.isfinite(q[_a]) and np.isfinite(o2[i][_a]) and q[_a] > 0:\n"
         "                    lspot += float(q[_a] * o2[i][_a])\n"
         "            bbar = max(0.0, lspot - 1.0) * float(borrow_apr) * (4.0 / 8760.0)\n"
         "            if bbar:\n"
         "                cash -= bbar\n"
         "                stats[\"borrow\"] = stats.get(\"borrow\", 0.0) + bbar\n"
         "        else:\n"
         "            bbar = 0.0\n"
         "        # dip sleeve"),
        1)
    src = src.replace(
        _ANCHOR_BARS,
        ("                             pending=[float(T[\"px\"][k]) if T[\"side\"][k] "
         "else float(\"nan\") for k in range(na)],\n"
         "                             borrow=float(bbar), funding_saved=float(fsave_bar)))  # SPOT PATCH P4"),
        1)
    return src


def load(name: str = "spot_engine_user"):
    """Load the patched engine as a module (same interface as engine_user)."""
    src = patched_source()
    assert src.count("SPOT PATCH") == 5, src.count("SPOT PATCH")
    assert "spot_route=None, borrow_apr=0.0" in src
    mod = importlib.util.module_from_spec(
        importlib.util.spec_from_loader(name, loader=None))
    mod.__dict__["__file__"] = str(HERE / "spot_patch.py")
    exec(compile(src, str(EU_PATH) + "#spotlongs", "exec"), mod.__dict__)
    return mod
