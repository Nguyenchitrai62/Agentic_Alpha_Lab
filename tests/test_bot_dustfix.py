"""bot_dustfix: SOL 0.0999 dust cause (exact-float chain) + F2 min-lot close proof.

Tests the PROPOSED fix against the copies under
research/diagnostics/bot_dustfix/tmp/ (run_fixed.py = bot/run.py + F2 diff,
mirror_fixed.py identical to bot/mirror.py). bot/ itself is never touched.
No network, no keys (fake HTTP session to tests/mock_bybit_v5.py).
"""
import importlib.util
import json
import time

import pandas as pd
import pytest

from bot import mirror
from bot.bybit_v5 import BybitError, round_step
from tests.mock_bybit_v5 import MockBybitV5

FIXDIR = None  # resolved per-test from this file's path
SOL_INST = dict(qty_step="0.1", min_qty="0.1", min_notional="5", tick="0.01")

# exact production values from soak_dust6h (d0SOL40hgrf0, 2025-10-10 flush)
ENTRY_PX = 170.17
TP_PX = 171.5399938483654
BACKSTOP = 126.23148632291513
STOP5 = 148.2050258243372


def _fixdir():
    from pathlib import Path
    return Path(__file__).resolve().parents[1] / "research/diagnostics/bot_dustfix/tmp"


def _load_fixed():
    # leader 2026-10-07: the F2 fix is now applied in bot/run.py itself -> test the real module
    # (the tmp copy under research/diagnostics is gitignored and not needed any more).
    from pathlib import Path
    import bot.run as mod
    src = Path(mod.__file__).read_text(encoding="utf-8")
    assert "bot_dustfix 2026-10-07" in src, "bot/run.py must carry the F2 dust-close fix"
    return mod


def _dust_ledger(now):
    return {"d0SOL40hgrf0": dict(
        kind="dip", phase=0, symbol="SOLUSDT", side=1,
        qty=0.09999999999999987, entry=170.17000000000002,
        tp=TP_PX, stop5=STOP5, backstop=BACKSTOP,
        t_exit=str(now + pd.Timedelta(hours=4)), frac=0.009999999999999998,
        dist=0.05, opened=str(now - pd.Timedelta(minutes=30)),
        planned_qty=0.9, entry_px=ENTRY_PX, entry_remaining=0.0)}


# ---- 1. hand-checked synthetic: the exact cause chain ------------------------

def test_cause_chain_amend_then_tp_leaves_00999():
    """Entry 0.9 amended to 0.7 + remainder 0.2; TP sized by round-DOWN (0.8);
    its fill leaves exactly 0.09999999999999987, whose protection is unplaceable."""
    led = {}
    entry = mirror.Order("d0SOL40hgrf0E", "SOLUSDT", "Buy", 0.9, "entry",
                         price=ENTRY_PX, position_idx=1, piece="d0SOL40hgrf0",
                         meta=dict(kind="dip", phase=0, tp=TP_PX, stop=STOP5,
                                   backstop=BACKSTOP, t_exit="t", frac=0.01, dist=0.05))
    t0 = pd.Timestamp("2025-10-10 21:18:20+00:00")
    mirror.apply_fill(led, entry, 0.7, ENTRY_PX, t0)   # amended order fills 0.7
    assert led["d0SOL40hgrf0"]["qty"] == 0.7
    assert led["d0SOL40hgrf0"]["planned_qty"] == 0.9  # Order kept pre-amend size
    mirror.apply_fill(led, entry, 0.2, ENTRY_PX, t0)   # remainder fills
    assert led["d0SOL40hgrf0"]["qty"] == 0.7 + 0.2 == pytest.approx(0.9)
    assert led["d0SOL40hgrf0"]["qty"] < 0.9  # float, not exactly 0.9
    assert round_step(led["d0SOL40hgrf0"]["qty"], "0.1") == "0.8"  # protection truncated
    tp = mirror.Order("d0SOL40hgrf0T", "SOLUSDT", "Sell", 0.8, "tp",
                      price=TP_PX, reduce_only=True, position_idx=1, piece="d0SOL40hgrf0")
    mirror.apply_fill(led, tp, 0.8, TP_PX, t0)
    left = led["d0SOL40hgrf0"]["qty"]
    assert left == 0.09999999999999987  # the soak dust qty, bit-for-bit
    assert mirror.protection_is_dust(left, TP_PX, BACKSTOP, SOL_INST) is True
    from bot.run import to_exchange
    Prot = mirror.Order("d0SOL40hgrf0T", "SOLUSDT", "Sell", left, "tp",
                        price=TP_PX, reduce_only=True, position_idx=1, piece="d0SOL40hgrf0")
    assert to_exchange(Prot, {"SOLUSDT": SOL_INST}) is None
    assert round_step(left, "0.1") == "0"  # dust_close qty 0 -> rejected pre-fix


def test_prefix_zero_qty_close_rejected_by_exchange(monkeypatch):
    """Pre-fix payload (qty 0) is rejected: the piece can never close."""
    mock = MockBybitV5(equity=10000.0)
    mock.install_session(monkeypatch)
    with pytest.raises(BybitError, match="110094"):
        mock._create(dict(symbol="SOLUSDT", side="Sell", orderType="Market", qty="0",
                          reduceOnly=True, orderLinkId="x", positionIdx=1))


# ---- 2. causality: no remainder -> no dust_close ------------------------------

def _fixed_runner(monkeypatch, tmp_path, plan, mock, tag):
    mod = _load_fixed()
    monkeypatch.setenv("BYBIT_TESTNET_API_KEY", "dummy")
    monkeypatch.setenv("BYBIT_TESTNET_API_SECRET", "dummy")
    monkeypatch.setattr(mod, "ROOT", tmp_path)
    mock.install_session(monkeypatch)
    plan_f = tmp_path / f"plan_{tag}.json"
    plan_f.write_text(json.dumps(plan, default=str))
    r = mod.Runner("testnet", plan_f, None, tag=tag)
    r._kline_cache_dir_override = str(tmp_path / f"kcache_{tag}")
    r._carry_contracts_override = {}
    r._carry_quotes_override = {}
    return r


def _empty_sol_plan(now):
    return {"generated_at": str(now), "phases": [{"phase": 0, "capital": 0.25}],
            "coins": {"SOLUSDT": {"price": 170.0, "subs": [], "dips": []}}}


def _ops(r):
    f = r.dir / "actions.jsonl"
    if not f.exists():
        return []
    return [json.loads(x) for x in f.read_text(encoding="utf-8").splitlines() if x.strip()]


def test_no_remainder_no_dust_close(monkeypatch, tmp_path):
    """A whole-lot piece (qty 0.9) is protectable: no dust_close fires (no cause, no effect)."""
    now = pd.Timestamp.now(tz="UTC")
    mock = MockBybitV5(prices={"SOLUSDT": 170.0}, equity=10000.0)
    r = _fixed_runner(monkeypatch, tmp_path, _empty_sol_plan(now), mock, tag="cause")
    led = _dust_ledger(now)
    led["d0SOL40hgrf0"]["qty"] = 0.9  # whole lot: protection placeable
    r.state["ledger"] = led
    mock.pos[("SOLUSDT", 1)] = dict(qty=0.9, avg=ENTRY_PX)
    r.cycle()
    ops = _ops(r)
    assert not [o for o in ops if o.get("op") == "dust_close"]
    assert not [o for o in ops if o.get("op") == "error"]
    assert ("d0SOL40hgrf0T" in mock.orders) and ("d0SOL40hgrf0S" in mock.orders)


# ---- 3. F2 proof on the fixed copy: min-lot close, fills flat, no flip -------

def test_f2_minlot_close_accepted_fills_flat_no_flip(monkeypatch, tmp_path):
    now = pd.Timestamp.now(tz="UTC")
    mock = MockBybitV5(prices={"SOLUSDT": 170.0}, equity=10000.0)
    r = _fixed_runner(monkeypatch, tmp_path, _empty_sol_plan(now), mock, tag="f2")
    r.state["ledger"] = _dust_ledger(now)
    have = 0.09999999999999987
    mock.pos[("SOLUSDT", 1)] = dict(qty=have, avg=ENTRY_PX)

    r.cycle()
    ops = _ops(r)
    closes = [o for o in ops if o.get("op") == "dust_close"]
    assert len(closes) == 1, [o.get("op") for o in ops]  # one close, no resend storm
    assert closes[0]["payload"]["qty"] == "0.1"  # min lot, not 0
    assert closes[0]["piece"] == "d0SOL40hgrf0"
    assert not [o for o in ops if o.get("op") == "error"]  # exchange accepted
    link = closes[0]["payload"]["orderLinkId"]
    assert link in mock.orders
    pc = r.state["ledger"]["d0SOL40hgrf0"]
    assert pc["exit_link"] == link and pc["exit_sent"] is not None
    assert "d0SOL40hgrf0T" not in mock.orders and "d0SOL40hgrf0S" not in mock.orders

    # fill-timing truncation: no fill inside the placement minute
    t_place = int(mock.orders[link]["t_ms"])
    assert mock.process_bar("SOLUSDT", 170.0, 170.1, 169.9, 170.0, t_place) == []
    assert r.state["ledger"]["d0SOL40hgrf0"]["qty"] > 0
    # next minute the market closes the whole remainder, capped at the position
    filled = mock.process_bar("SOLUSDT", 170.0, 170.1, 169.9, 170.0, t_place + 60_000)
    assert filled == [link]
    execs = [e for e in mock.execs if e["orderLinkId"] == link]
    assert len(execs) == 1 and float(execs[0]["execQty"]) == pytest.approx(have)
    assert mock.pos[("SOLUSDT", 1)]["qty"] == pytest.approx(0.0)  # flat, never negative

    # sync: ledger goes flat, no second close (inflight guard), no flip anywhere
    r.cycle()
    assert r.state["ledger"]["d0SOL40hgrf0"]["qty"] == 0.0
    assert len([o for o in _ops(r) if o.get("op") == "dust_close"]) == 1
    for (_s, _i), _p in mock.pos.items():
        assert _p["qty"] >= 0
