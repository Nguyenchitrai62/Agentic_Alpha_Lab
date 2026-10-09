"""oc_stopentry engine: verbatim engine_user.simulate + STOP PATCH (breakout entries).

The audited engine (research/parallel/rounds/parallel-20260906-r2/engine_user/
engine_user.py) is loaded from source, asserted verbatim at the patched sites,
then patched minimally:
  P1 signature: + stop_route=None, stop_off=0.0005.
  P2 T state: + is_stop flag per asset (entry order type issued at flat->open).
  P3 issuance: a routed new entry rests THROUGH the minute-0 open
      (long P0*(1+off), short P0*(1-off)) instead of better-than-open.
  P4 fill: a resting stop fills only on a strict 1m trade-THROUGH past the level
      (long high > level, short low < level; touch == no fill), at the level,
      taker 0.00055; passive fills unchanged (maker 0.0002). Minute-5 ban kept
      for new orders (win_start); resting stops fill from minute 0 like resting
      limits. SL/TP/BE/tighten/validity/dip unchanged, stop-first kept.
With stop_route=None the patched simulate is bit-identical to the audited
engine (REF gate asserts V0 == v421 G2 to the digit). In-position adds/reduces/
closes stay passive limits (entry-only scope, disclosed in PLAN.md).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
EU_PATH = (
    ROOT
    / "research/parallel/rounds/parallel-20260906-r2"
    / "engine_user/engine_user.py"
)

_ANCHOR_SIG = "sleeve_sl_coin=None, sleeve_gross_cap=None):"
_ANCHOR_HERE = "HERE = Path(__file__).parent"
_ANCHOR_T = "             nadd=np.zeros(na, int), nred=np.zeros(na, int), open_i=np.full(na, -1), last_adj=np.full(na, -10**6))"
_ANCHOR_CANCEL = '                T["side"][a] = ps = 0\n                T["risk"][a] = 0.0\n            elif ps != 0 and i >= T["exp"][a]:'
_ANCHOR_ISSUE = '                off = max(P.get("min_off", 0.001), k_off * s4_a)\n                T["side"][a], T["px"][a], T["w"][a] = sgn, Oa[0] * (1 - sgn * off), size'
_ANCHOR_EV_ISSUE = '                _ev(i, a, 0, "order_issue", "buy" if sgn > 0 else "sell", T["px"][a], sgn * size, offset=float(off))'
_ANCHOR_HIT = "            hit = La[start:240] < px * (1 - ft) if ps > 0 else Ha[start:240] > px * (1 + ft)"
_ANCHOR_FEE = "            carr[m0:] -= dq * px + abs(dq) * px * MAKER\n            stats[\"fees\"] += abs(dq) * px * MAKER"
_ANCHOR_FILL_EV = '            _ev(i, a, m0, "book_fill", "buy" if ps > 0 else "sell", px, ps * T["w"][a], entry_type="limit", sl=float(T["sl"][a]),'


def patched_source() -> str:
    src = EU_PATH.read_text(encoding="utf-8")
    for anchor in (
        _ANCHOR_SIG,
        _ANCHOR_HERE,
        _ANCHOR_T,
        _ANCHOR_CANCEL,
        _ANCHOR_ISSUE,
        _ANCHOR_EV_ISSUE,
        _ANCHOR_HIT,
        _ANCHOR_FEE,
        _ANCHOR_FILL_EV,
    ):
        assert src.count(anchor) == 1, anchor  # verbatim gate: exactly one site
    eu_dir = EU_PATH.parent.as_posix()
    src = src.replace(
        _ANCHOR_HERE,
        f"HERE = Path({eu_dir!r})  # STOP PATCH P0: keep audited relative imports",
        1,
    )
    src = src.replace(
        _ANCHOR_SIG,
        "sleeve_sl_coin=None, sleeve_gross_cap=None, stop_route=None, stop_off=0.0005):",
        1,
    )
    src = src.replace(
        _ANCHOR_T,
        "             nadd=np.zeros(na, int), nred=np.zeros(na, int), open_i=np.full(na, -1), last_adj=np.full(na, -10**6),\n"
        "             is_stop=np.zeros(na, bool))  # STOP PATCH P2: entry order type",
        1,
    )
    src = src.replace(
        _ANCHOR_CANCEL,
        '                T["side"][a] = ps = 0\n'
        '                T["risk"][a] = 0.0\n'
        '                T["is_stop"][a] = False  # STOP PATCH P2\n'
        '            elif ps != 0 and i >= T["exp"][a]:',
        1,
    )
    # NOTE: the expire site shares the same two lines but is followed by
    # `start = 0` (resting-order carry); patch it via the longer anchor.
    _ANCHOR_EXPIRE = '                T["side"][a] = ps = 0\n                T["risk"][a] = 0.0\n            start = 0  # an order resting from an earlier bar may fill from minute 0'
    assert src.count(_ANCHOR_EXPIRE) == 1, "expire site"
    src = src.replace(
        _ANCHOR_EXPIRE,
        '                T["side"][a] = ps = 0\n'
        '                T["risk"][a] = 0.0\n'
        '                T["is_stop"][a] = False  # STOP PATCH P2\n'
        "            start = 0  # an order resting from an earlier bar may fill from minute 0",
        1,
    )
    src = src.replace(
        _ANCHOR_ISSUE,
        "                _is_stop = bool(stop_route is not None and stop_route(i, a))  # STOP PATCH P3\n"
        '                off = max(P.get("min_off", 0.001), k_off * s4_a)\n'
        "                _px_new = Oa[0] * (1 + sgn * float(stop_off)) if _is_stop else Oa[0] * (1 - sgn * off)  # STOP PATCH P3\n"
        '                T["side"][a], T["px"][a], T["w"][a] = sgn, _px_new, size\n'
        '                T["is_stop"][a] = _is_stop  # STOP PATCH P3',
        1,
    )
    src = src.replace(
        _ANCHOR_EV_ISSUE,
        '                _ev(i, a, 0, "order_issue", "buy" if sgn > 0 else "sell", T["px"][a], sgn * size, offset=float(-float(stop_off) if T["is_stop"][a] else off), entry_type=("stop" if T["is_stop"][a] else "limit"))  # STOP PATCH P3',
        1,
    )
    src = src.replace(
        _ANCHOR_HIT,
        "            _fill_stop = bool(T[\"is_stop\"][a])  # STOP PATCH P4\n"
        "            hit = (Ha[start:240] > px * (1 + ft) if ps > 0 else La[start:240] < px * (1 - ft)) if _fill_stop else (La[start:240] < px * (1 - ft) if ps > 0 else Ha[start:240] > px * (1 + ft))  # STOP PATCH P4",
        1,
    )
    src = src.replace(
        _ANCHOR_FEE,
        "            _fee = TAKER if _fill_stop else MAKER  # STOP PATCH P4\n"
        "            carr[m0:] -= dq * px + abs(dq) * px * _fee\n"
        "            stats[\"fees\"] += abs(dq) * px * _fee  # STOP PATCH P4",
        1,
    )
    src = src.replace(
        _ANCHOR_FILL_EV,
        '            _ev(i, a, m0, "book_fill", "buy" if ps > 0 else "sell", px, ps * T["w"][a], entry_type=("stop" if _fill_stop else "limit"), sl=float(T["sl"][a]),  # STOP PATCH P4',
        1,
    )
    # clear the flag when the position opens (side returns to 0 on fill).
    # NOTE: this site precedes the book_fill event in source order, so the event
    # and the counter must use the pre-clear local _fill_stop (else every stop
    # fill is mislabelled "limit" — caught by tmp/dbg_stop.py, fixed 2026-10-08).
    assert src.count('            T["side"][a] = 0\n            T["ak"][a], T["nadd"][a], T["nred"][a] = 0, 0, 0') == 1
    src = src.replace(
        '            T["side"][a] = 0\n            T["ak"][a], T["nadd"][a], T["nred"][a] = 0, 0, 0',
        '            T["side"][a] = 0\n'
        '            stats["stop_fills"] = stats.get("stop_fills", 0) + (1 if _fill_stop else 0)  # STOP PATCH P4\n'
        '            T["is_stop"][a] = False  # STOP PATCH P4\n'
        '            T["ak"][a], T["nadd"][a], T["nred"][a] = 0, 0, 0',
        1,
    )
    return src


def load(name: str = "stop_engine_user"):
    """Load the patched engine as a module (same interface as engine_user)."""
    src = patched_source()
    assert src.count("STOP PATCH") >= 10, src.count("STOP PATCH")
    assert "stop_route=None, stop_off=0.0005" in src
    mod = importlib.util.module_from_spec(importlib.util.spec_from_loader(name, loader=None))
    mod.__dict__["__file__"] = str(HERE / "stop_patch.py")
    exec(compile(src, str(EU_PATH) + "#stopentry", "exec"), mod.__dict__)
    return mod
