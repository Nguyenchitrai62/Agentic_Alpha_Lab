"""oc_spotlongs2 engine: verbatim engine_user.simulate + SPOT-FEE PATCH.

The audited engine (research/parallel/rounds/parallel-20260906-r2/engine_user/
engine_user.py) is loaded from source, asserted verbatim at the patched sites,
then patched minimally (the ONLY behavioural change vs oc_spotlongs is P5):

  P1 signature: + spot_route=None, borrow_apr=0.0, spot_maker=MAKER,
      spot_taker=TAKER (defaults reproduce the audited engine bit-exact).
  P2 book funding: a spot-routed long pays 0 funding (saved tracked).
  P3 borrow: per-bar USDT interest on the spot-routed long leg where leveraged,
      deducted from bar cash (same convention as funding: close-equity only).
  P4 bars: record per-bar funding_saved + funding_paid + borrow + turnover +
      spot/perp fee split (for the fee/funding attribution).
  P5 book fee-rate switch (THE ONE CHANGE vs oc_spotlongs): a book leg on the
      LONG side (entry of ps>0, TP/SL/partial/scale of cur_q>0) while
      spot-routed pays the spot rate (limit legs -> spot_maker, market stop
      legs -> spot_taker); short-side legs stay on the gate MAKER/TAKER.
      Turnover and the spot/perp fee split are accumulated per bar and in
      stats (stats["book_turnover"], stats["book_spot_fees"],
      stats["book_perp_fees"]).

With spot_route=None the patched simulate is bit-identical to the audited
engine (REF/V0 gate asserts == v421 G2 to the digit). Routing here is
unconditional V1 (all book longs spot), so any long book leg is a spot leg.
Dip sleeve is untouched (stays perp, pays gate funding on timeouts as base).
Spot-perp fill basis assumed 0 (same 1m cube; labelled in PLAN/REPORT).
The non-trade branch (trade=None) is never executed by this pipe and is left
byte-identical (stated limitation in PLAN.md).
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
_ANCHOR_STATS = ("stats = dict(fills=0, unfilled=0, stops=0, tps=0, rungs=0, "
                 "rung_stops=0, rung_tps=0, liq=0, fees=0.0, funding=0.0, "
                 "gross_sum=0.0, gross_max=0.0, bars=0)")
_ANCHOR_TRADE_OPEN = ("        carr, qarr = np.zeros(240), np.full(240, qa)\n"
                        "        cur_q, cur_e = qa, ea")
_ANCHOR_ENTRY = ("            carr[m0:] -= dq * px + abs(dq) * px * MAKER\n"
                 "            stats[\"fees\"] += abs(dq) * px * MAKER")
_ANCHOR_STOP = ("                carr[mm:] += cur_q * px - abs(cur_q) * px * TAKER\n"
                "                stats[\"fees\"] += abs(cur_q) * px * TAKER")
_ANCHOR_TP = ("                carr[mm:] += cur_q * tp - abs(cur_q) * tp * MAKER\n"
              "                stats[\"fees\"] += abs(cur_q) * tp * MAKER")
_ANCHOR_ADD = ("                    carr[mm:] -= dq * apx + abs(dq) * apx * MAKER\n"
               "                    stats[\"fees\"] += abs(dq) * apx * MAKER")
_ANCHOR_REDUCE = ("                    carr[mm:] += dq * apx - abs(dq) * apx * MAKER\n"
                  "                    stats[\"fees\"] += abs(dq) * apx * MAKER")
_ANCHOR_PARTIAL = ("                carr[mm:] += dq * tp1 - abs(dq) * tp1 * MAKER\n"
                   "                stats[\"fees\"] += abs(dq) * tp1 * MAKER")


def patched_source() -> str:
    src = EU_PATH.read_text(encoding="utf-8")
    for anchor in (_ANCHOR_SIG, _ANCHOR_HERE, _ANCHOR_FUND_A, _ANCHOR_FUND_B,
                   _ANCHOR_ASSET, _ANCHOR_LOOP_END, _ANCHOR_BARS,
                   _ANCHOR_STATS, _ANCHOR_TRADE_OPEN, _ANCHOR_ENTRY,
                   _ANCHOR_TP, _ANCHOR_ADD, _ANCHOR_REDUCE, _ANCHOR_PARTIAL):
        assert src.count(anchor) == 1, anchor  # verbatim gate: exactly one site
    assert src.count(_ANCHOR_STOP) == 2, "stop sites"  # close-triggered + touch
    eu_dir = EU_PATH.parent.as_posix()
    src = src.replace(
        _ANCHOR_HERE,
        f"HERE = Path({eu_dir!r})  # SPOT-FEE PATCH P0: keep audited relative imports",
        1)
    src = src.replace(
        _ANCHOR_SIG,
        "sleeve_sl_coin=None, sleeve_gross_cap=None, spot_route=None, borrow_apr=0.0, spot_maker=MAKER, spot_taker=TAKER):",
        1)
    src = src.replace(
        _ANCHOR_STATS,
        (_ANCHOR_STATS + "\n"
         "    stats[\"book_turnover\"] = 0.0  # SPOT-FEE PATCH P4: book notional (frac of bar-start equity)\n"
         "    stats[\"book_spot_fees\"] = 0.0  # SPOT-FEE PATCH P4\n"
         "    stats[\"book_perp_fees\"] = 0.0  # SPOT-FEE PATCH P4\n"
         "    _spot_acc = dict(turn=0.0, sfee=0.0, pfee=0.0)  # SPOT-FEE PATCH P4/P5 per-bar accumulators"),
        1)
    src = src.replace(
        _ANCHOR_TRADE_OPEN,
        (_ANCHOR_TRADE_OPEN + "\n"
         "        def _bkfee(is_long, taker):  # SPOT-FEE PATCH P5: honest spot rate for spot-routed long legs\n"
         "            if spot_route is not None and is_long and bool(spot_route(i, a)):\n"
         "                return spot_taker if taker else spot_maker\n"
         "            return TAKER if taker else MAKER\n"
         "        def _bkacc(notional, rate, is_long):  # SPOT-FEE PATCH P5: turnover + fee-split accumulators\n"
         "            _n = abs(float(notional))\n"
         "            _spot_acc[\"turn\"] += _n\n"
         "            if spot_route is not None and is_long and bool(spot_route(i, a)):\n"
         "                _spot_acc[\"sfee\"] += _n * float(rate)\n"
         "                stats[\"book_spot_fees\"] = stats.get(\"book_spot_fees\", 0.0) + _n * float(rate)\n"
         "            else:\n"
         "                _spot_acc[\"pfee\"] += _n * float(rate)\n"
         "                stats[\"book_perp_fees\"] = stats.get(\"book_perp_fees\", 0.0) + _n * float(rate)\n"
         "            stats[\"book_turnover\"] = stats.get(\"book_turnover\", 0.0) + _n"),
        1)
    src = src.replace(
        _ANCHOR_ENTRY,
        ("            _rtE = _bkfee(ps > 0, False)  # SPOT-FEE PATCH P5 entry: long entries pay spot maker\n"
         "            carr[m0:] -= dq * px + abs(dq) * px * _rtE\n"
         "            stats[\"fees\"] += abs(dq) * px * _rtE\n"
         "            _bkacc(dq * px, _rtE, ps > 0)  # SPOT-FEE PATCH P5"),
        1)
    src = src.replace(
        _ANCHOR_STOP,
        ("                _rtS = _bkfee(cur_q > 0, True)  # SPOT-FEE PATCH P5 stop: long SL pays spot taker\n"
         "                carr[mm:] += cur_q * px - abs(cur_q) * px * _rtS\n"
         "                stats[\"fees\"] += abs(cur_q) * px * _rtS\n"
         "                _bkacc(cur_q * px, _rtS, cur_q > 0)  # SPOT-FEE P5"),
        2)
    src = src.replace(
        _ANCHOR_TP,
        ("                _rtT = _bkfee(cur_q > 0, False)  # SPOT-FEE PATCH P5 TP: long TPs pay spot maker\n"
         "                carr[mm:] += cur_q * tp - abs(cur_q) * tp * _rtT\n"
         "                stats[\"fees\"] += abs(cur_q) * tp * _rtT\n"
         "                _bkacc(cur_q * tp, _rtT, cur_q > 0)  # SPOT-FEE P5"),
        1)
    src = src.replace(
        _ANCHOR_ADD,
        ("                    _rtA = _bkfee(cur_q > 0, False)  # SPOT-FEE PATCH P5 scale-in: long adds pay spot maker\n"
         "                    carr[mm:] -= dq * apx + abs(dq) * apx * _rtA\n"
         "                    stats[\"fees\"] += abs(dq) * apx * _rtA\n"
         "                    _bkacc(dq * apx, _rtA, cur_q > 0)  # SPOT-FEE P5"),
        1)
    src = src.replace(
        _ANCHOR_REDUCE,
        ("                    _rtR = _bkfee(cur_q > 0, False)  # SPOT-FEE PATCH P5 scale-out: long reduces pay spot maker\n"
         "                    carr[mm:] += dq * apx - abs(dq) * apx * _rtR\n"
         "                    stats[\"fees\"] += abs(dq) * apx * _rtR\n"
         "                    _bkacc(dq * apx, _rtR, cur_q > 0)  # SPOT-FEE P5"),
        1)
    src = src.replace(
        _ANCHOR_PARTIAL,
        ("                _rtP = _bkfee(cur_q > 0, False)  # SPOT-FEE PATCH P5 partial: long partials pay spot maker\n"
         "                carr[mm:] += dq * tp1 - abs(dq) * tp1 * _rtP\n"
         "                stats[\"fees\"] += abs(dq) * tp1 * _rtP\n"
         "                _bkacc(dq * tp1, _rtP, cur_q > 0)  # SPOT-FEE P5"),
        1)
    src = src.replace(
        _ANCHOR_FUND_B,
        (_ANCHOR_FUND_B + "\n"
         "                if fund > 0.0 and spot_route is not None and bool(spot_route(i, a)):  # SPOT-FEE PATCH P2\n"
         "                    fsave_bar += fund\n"
         "                    stats[\"funding_saved\"] = stats.get(\"funding_saved\", 0.0) + fund\n"
         "                    fund = 0.0\n"
         "                fpaid_bar += fund  # SPOT-FEE PATCH P4 funding actually charged"),
        1)
    src = src.replace(
        _ANCHOR_ASSET,
        (_ANCHOR_ASSET + "\n"
         "        fsave_bar = 0.0  # SPOT-FEE PATCH P2/P4\n"
         "        fpaid_bar = 0.0  # SPOT-FEE PATCH P4\n"
         "        _spot_acc[\"turn\"] = 0.0  # SPOT-FEE PATCH P4/P5\n"
         "        _spot_acc[\"sfee\"] = 0.0  # SPOT-FEE PATCH P4/P5\n"
         "        _spot_acc[\"pfee\"] = 0.0  # SPOT-FEE PATCH P4/P5"),
        1)
    src = src.replace(
        _ANCHOR_LOOP_END,
        ("            q[a], entry[a] = cur_q, cur_e\n"
         "        if borrow_apr and spot_route is not None:  # SPOT-FEE PATCH P3\n"
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
         "        _turn_bar = float(_spot_acc[\"turn\"])  # SPOT-FEE PATCH P4\n"
         "        _sfee_bar = float(_spot_acc[\"sfee\"])  # SPOT-FEE PATCH P4\n"
         "        _pfee_bar = float(_spot_acc[\"pfee\"])  # SPOT-FEE PATCH P4\n"
         "        # dip sleeve"),
        1)
    src = src.replace(
        _ANCHOR_BARS,
        ("                             pending=[float(T[\"px\"][k]) if T[\"side\"][k] "
         "else float(\"nan\") for k in range(na)],\n"
         "                             borrow=float(bbar), funding_saved=float(fsave_bar), funding_paid=float(fpaid_bar), turnover=float(_turn_bar), spot_fees=float(_sfee_bar), perp_fees=float(_pfee_bar)))  # SPOT-FEE PATCH P4"),
        1)
    return src


def load(name: str = "spotfee_engine_user"):
    """Load the patched engine as a module (same interface as engine_user)."""
    src = patched_source()
    assert src.count("SPOT-FEE PATCH") >= 20, src.count("SPOT-FEE PATCH")
    assert "spot_route=None, borrow_apr=0.0, spot_maker=MAKER, spot_taker=TAKER" in src
    mod = importlib.util.module_from_spec(
        importlib.util.spec_from_loader(name, loader=None))
    mod.__dict__["__file__"] = str(HERE / "spot_patch2.py")
    exec(compile(src, str(EU_PATH) + "#spotlongs2", "exec"), mod.__dict__)
    return mod
