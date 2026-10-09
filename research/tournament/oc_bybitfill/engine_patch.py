"""oc_bybitfill engine_patch: vendored engine_user.simulate with two extra price hooks.

Byte-identical to research/parallel/rounds/parallel-20260906-r2/engine_user/engine_user.py
except two extra kwargs:
  dip_rung_mult (default 1.0): every dip rung limit lv -> lv * dip_rung_mult
    (fill detection `L < lv`, fill price lv, stop/backstop from lv all follow).
  dip_tp_mult (default 1.0): every dip TP limit tp -> tp * dip_tp_mult
    (touch `H > tp`, exit price tp follow).

PLAN mapping: REF = (1.0, 1.0) must reproduce G2 to the digit;
TPm3 = (1.0, 0.9997); RUNp3 = (1.0003, 0.9997).
Book logic, costs, funding, governor, budgets, win_start/stop-first untouched.
"""

from __future__ import annotations

from pathlib import Path

_ENGINE = Path(__file__).resolve().parents[3] / "research/parallel/rounds/parallel-20260906-r2/engine_user/engine_user.py"

_SRC = _ENGINE.read_text()

_SIG_OLD = "sleeve_sl_coin=None, sleeve_gross_cap=None):"
_SIG_NEW = "sleeve_sl_coin=None, sleeve_gross_cap=None, dip_rung_mult=1.0, dip_tp_mult=1.0):"
assert _SRC.count(_SIG_OLD) == 1, "engine signature changed - inspect manually"
_SRC = _SRC.replace(_SIG_OLD, _SIG_NEW)

_LV4_OLD = "                    lv = o1[i][a] * (1 - k * sig_sl[i][a])"
_LV4_NEW = "                    lv = o1[i][a] * (1 - k * sig_sl[i][a]) * float(dip_rung_mult)"
assert _SRC.count(_LV4_OLD) == 1, "4h rung line changed - inspect manually"
_SRC = _SRC.replace(_LV4_OLD, _LV4_NEW)

_LV1_OLD = "                            lv = float(O[i, 60 * h, a]) * (1 - k * s1[a])"
_LV1_NEW = "                            lv = float(O[i, 60 * h, a]) * (1 - k * s1[a]) * float(dip_rung_mult)"
assert _SRC.count(_LV1_OLD) == 1, "hourly rung line changed - inspect manually"
_SRC = _SRC.replace(_LV1_OLD, _LV1_NEW)

_TP_OLD = "                tp = lv * (1 + (m_sleeve_tp if sleeve_tp is None else float(sleeve_tp(i, a, r, f))) * sg)"
_TP_NEW = "                tp = lv * (1 + (m_sleeve_tp if sleeve_tp is None else float(sleeve_tp(i, a, r, f))) * sg) * float(dip_tp_mult)"
assert _SRC.count(_TP_OLD) == 1, "dip TP line changed - inspect manually"
_SRC = _SRC.replace(_TP_OLD, _TP_NEW)

_ns: dict = {"__file__": str(_ENGINE), "__name__": "oc_bybitfill_engine_vendored"}
exec(compile(_SRC, str(_ENGINE), "exec"), _ns)

simulate = _ns["simulate"]
prepare = _ns["prepare"]
summarize_orig = _ns["summarize"]
_NS = _ns  # module namespace of the vendored engine (patch summarize/v110 here)
v110 = _ns["v110"]
er = _ns["er"]
MAKER = _ns["MAKER"]
TAKER = _ns["TAKER"]
FUND_LONG = _ns["FUND_LONG"]
RUNGS = _ns["RUNGS"]
SIZE = _ns["SIZE"]
S_REF = _ns["S_REF"]

# PLAN constants for this study
RUNG_MULT = {  # dip_rung_mult per variant
    "REF": 1.0,
    "TPm3": 1.0,
    "RUNp3": 1.0003,
}
TP_MULT = {  # dip_tp_mult per variant
    "REF": 1.0,
    "TPm3": 0.9997,
    "RUNp3": 0.9997,
}
