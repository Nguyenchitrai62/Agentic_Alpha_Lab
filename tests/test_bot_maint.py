"""bot_maint tests (no network, no keys). Uses tests/mock_bybit_v5.py for exchange I/O.

Covers the opt-in maintenance window (default bit-for-bit unchanged) and the
restart protection check:
  - inactive by default: identical order sets with/without maint params
  - maint_active_at: fake-clock boundary checks (start-30min .. end)
  - active window: no new dip bids / book entries, resting entries cancel,
    protection (TP/SL) and carry legs untouched, op=maint_cancel logged
  - maintenance.json read each cycle (file wins); window exit logs maint_resume
  - startup op=protection_check lists open pieces; bot_health flags missing
    protection as CRITICAL
"""
import json

import pandas as pd

import bot.run as runmod
from bot import mirror
from bot.run import maint_active_at
from tests.mock_bybit_v5 import MockBybitV5

SYM = "BTCUSDT"
PX = 80000.0


def _now():
    return pd.Timestamp.now(tz="UTC")


def _runner(monkeypatch, tmp_path, plan, mock, tag="m", **kw):
    monkeypatch.setenv("BYBIT_TESTNET_API_KEY", "dummy")
    monkeypatch.setenv("BYBIT_TESTNET_API_SECRET", "dummy")
    monkeypatch.setattr(runmod, "ROOT", tmp_path)
    mock.install_session(monkeypatch)
    plan_f = tmp_path / f"plan_{tag}.json"
    plan_f.write_text(json.dumps(plan, default=str))
    kw.setdefault("no_risk_guard", True)  # engine-faithful sizing in tests
    r = runmod.Runner("testnet", plan_f, None, tag=tag, **kw)
    r._kline_cache_dir_override = str(tmp_path / f"kcache_{tag}")
    return r


def _plan_with_entry(now, price=79000.0):
    issued = now - pd.Timedelta(minutes=10)
    valid = now + pd.Timedelta(minutes=60)
    return {
        "generated_at": str(now),
        "phases": [{"phase": 0, "capital": 1.0}],
        "coins": {
            SYM: {
                "subs": [{
                    "phase": 0, "state": "pending",
                    "order": {"kind": "open", "issued": str(issued), "valid_until": str(valid),
                              "side": "BUY", "weight": 0.05, "price": price,
                              "sl_if_filled": price * 0.96, "tp_if_filled": price * 1.04},
                }],
                "dips": [{
                    "phase": 0, "rung": 2.5, "buy_limit": price, "stop": price * 0.97,
                    "tp": price * 1.03, "backstop": price * 0.94, "size_frac": 0.02,
                    "active_from": str(now - pd.Timedelta(minutes=30)),
                    "active_until": str(now + pd.Timedelta(minutes=30)),
                }],
            }
        },
    }


def _ops(r):
    p = r.dir / "actions.jsonl"
    if not p.exists():
        return []
    return [json.loads(x) for x in p.read_text().splitlines() if x.strip()]


# ---- pure window logic with fake clocks -------------------------------------

def test_maint_window_boundaries_fake_clock():
    t0 = pd.Timestamp("2026-10-06 12:00:00+00:00")
    s = t0 + pd.Timedelta(hours=2)  # window 14:00 .. 15:00
    e = t0 + pd.Timedelta(hours=3)
    assert maint_active_at(t0, s, e) is False  # 2h before start
    assert maint_active_at(s - pd.Timedelta(minutes=31), s, e) is False
    assert maint_active_at(s - pd.Timedelta(minutes=30), s, e) is True  # pre-window opens
    assert maint_active_at(s - pd.Timedelta(minutes=1), s, e) is True
    assert maint_active_at(s, s, e) is True
    assert maint_active_at(e, s, e) is True
    assert maint_active_at(e + pd.Timedelta(seconds=1), s, e) is False
    assert maint_active_at(t0, None, e) is False
    assert maint_active_at(t0, s, None) is False


def test_parse_maint_ts_invalid_is_inactive():
    assert runmod._parse_maint_ts(None) is None
    assert runmod._parse_maint_ts("") is None
    assert runmod._parse_maint_ts("not-a-date") is None
    t = runmod._parse_maint_ts("2026-10-06T14:00:00Z")
    assert t is not None and str(t.tzinfo) == "UTC"


# ---- default behaviour unchanged --------------------------------------------

def test_inactive_default_orders_identical(monkeypatch, tmp_path):
    now = _now()
    plan = _plan_with_entry(now)
    m1 = MockBybitV5(prices={SYM: PX}, equity=10000.0)
    r1 = _runner(monkeypatch, tmp_path, plan, m1, tag="moff1")
    a1 = r1.cycle()
    m2 = MockBybitV5(prices={SYM: PX}, equity=10000.0)
    r2 = _runner(monkeypatch, tmp_path, plan, m2, tag="moff2",
                 maint_start=None, maint_end=None)
    a2 = r2.cycle()
    assert r2.maint_start is None and r2.maint_end is None
    assert not r2._maint_is_active(_now())
    norm = lambda acts: sorted((x.get("op"), x.get("link"),
                                getattr(x.get("order"), "link", None)) for x in acts)
    assert norm(a1) == norm(a2)
    assert not [x for x in _ops(r2) if x.get("op") in ("maint_cancel", "maint_resume")]


# ---- active window blocks + cancels, protection untouched --------------------

def test_active_window_blocks_new_entries_and_cancels_resting(monkeypatch, tmp_path):
    now = _now()
    plan = _plan_with_entry(now)
    mock = MockBybitV5(prices={SYM: PX}, equity=10000.0)
    r = _runner(monkeypatch, tmp_path, plan, mock, tag="mon",
                maint_start=str(now + pd.Timedelta(minutes=10)),
                maint_end=str(now + pd.Timedelta(hours=2)))
    assert r._maint_is_active(now) is True
    # seed one resting dip-bid entry + one resting book entry on the exchange
    for link, qty in (("d0BTColdE", 0.002), ("b0BTColdE", 0.006)):
        o = mirror.Order(link, SYM, "Buy", qty, "entry", price=79000.0,
                         position_idx=1, piece=link[:-1],
                         meta=dict(kind="dip" if link.startswith("d") else "book",
                                   phase=0))
        r.state["links"][link] = dict(order=runmod.asdict(o),
                                      rest=dict(symbol=SYM, price=79000.0, qty=qty))
        mock.orders[link] = dict(symbol=SYM, side="Buy", orderType="Limit",
                                 price="79000", qty=str(qty), orderLinkId=link,
                                 positionIdx=1)
    # seed an open book piece WITH protection resting (must survive maintenance)
    pid = "b0BTCkeep"
    r.state["ledger"][pid] = dict(symbol=SYM, side=1, qty=0.01, entry=79000.0,
                                  kind="book", phase=0, opened=str(now),
                                  sl=75000.0, tp=83000.0)
    for link, kind, px in ((pid + "T", "tp", 83000.0), (pid + "S", "stop", 75000.0)):
        o = mirror.Order(link, SYM, "Sell", 0.01, kind,
                         price=px if kind == "tp" else None,
                         trigger=px if kind == "stop" else None,
                         reduce_only=True, position_idx=1, piece=pid)
        r.state["links"][link] = dict(order=runmod.asdict(o),
                                      rest=dict(symbol=SYM, price=px, qty=0.01))
        mock.orders[link] = dict(symbol=SYM, side="Sell",
                                 orderType="Limit" if kind == "tp" else "Market",
                                 price=str(px), qty="0.01", orderLinkId=link,
                                 positionIdx=1)
    acts = r.cycle()
    ops = _ops(r)
    mc = [x for x in ops if x.get("op") == "maint_cancel"]
    assert len(mc) >= 1
    # no NEW entry was placed
    placed = [a for a in acts if a.get("op") == "place"]
    assert not [a for a in placed
                if getattr(a.get("order"), "kind", None) == "entry"]
    # both seeded resting entries were cancelled ...
    cancelled = {a.get("link") for a in acts if a.get("op") == "cancel"}
    assert {"d0BTColdE", "b0BTColdE"} <= cancelled
    # ... while protection was neither cancelled nor amended away
    assert pid + "T" not in cancelled and pid + "S" not in cancelled
    assert (pid + "T") in mock.orders and (pid + "S") in mock.orders


def test_maintenance_json_read_each_cycle_and_resume(monkeypatch, tmp_path):
    now = _now()
    plan = _plan_with_entry(now)
    mock = MockBybitV5(prices={SYM: PX}, equity=10000.0)
    r = _runner(monkeypatch, tmp_path, plan, mock, tag="mfile")
    assert r._maint_is_active(now) is False
    mf = r.dir / "maintenance.json"
    mf.write_text(json.dumps({"start": str(now + pd.Timedelta(minutes=10)),
                              "end": str(now + pd.Timedelta(hours=1))}))
    s, e = r.maint_window()
    assert s is not None and e is not None  # file wins over (empty) flags
    r.cycle()
    assert r._maint_active is True
    assert any(x.get("op") == "maint_cancel" for x in _ops(r))
    # window passes -> next cycle resumes with op=maint_resume, entries flow again
    mf.write_text(json.dumps({"start": str(now - pd.Timedelta(hours=3)),
                              "end": str(now - pd.Timedelta(hours=2))}))
    n_before = len(_ops(r))
    acts = r.cycle()
    after = _ops(r)[n_before:]
    assert any(x.get("op") == "maint_resume" for x in after)
    assert r._maint_active is False
    assert any(a.get("op") == "place"
               and getattr(a.get("order"), "kind", None) == "entry" for a in acts)


def test_carry_legs_untouched_during_maint(monkeypatch, tmp_path):
    now = _now()
    plan = {"generated_at": str(now), "phases": [{"phase": 0, "capital": 0.25}],
            "coins": {}}
    mock = MockBybitV5(prices={SYM: PX}, equity=10000.0)
    r = _runner(monkeypatch, tmp_path, plan, mock, tag="mcarry", carry_f=0.25,
                maint_start=str(now + pd.Timedelta(minutes=5)),
                maint_end=str(now + pd.Timedelta(hours=1)))
    n = int(pd.Timestamp(now).timestamp() * 1000)
    r._carry_contracts_override = {"BTC": [
        dict(symbol="BTC-FRONT", category="linear", delivery_ms=n + 3 * 86_400_000),
        dict(symbol="BTCQ", category="linear", delivery_ms=n + 90 * 86_400_000)]}
    r._carry_quotes_override = {"BTC": dict(spot_mid=80000.0, spot_ask=80000.0,
                                            spot_bid=80000.0,
                                            fut_by_sym={"BTCQ": dict(bid=82000.0,
                                                                     ask=82000.0,
                                                                     mid=82000.0)})}
    r.inst["BTCQ"] = dict(qty_step="0.001", min_qty="0.001",
                          min_notional="5", tick="0.1")
    r.cycle()
    ops = _ops(r)
    assert any(x.get("op") == "carry_entry" for x in ops)  # carry still enters
    assert [k for k in mock.orders if str(k).startswith("c")]  # carry rests
    assert r._maint_is_active(now) is True


# ---- startup protection check + bot_health CRITICAL --------------------------

def test_startup_protection_check_and_health_critical(monkeypatch, tmp_path):
    import importlib.util
    from pathlib import Path
    now = _now()
    plan = {"generated_at": str(now), "phases": [{"phase": 0, "capital": 0.25}],
            "coins": {}}
    mock = MockBybitV5(prices={SYM: PX}, equity=10000.0)
    r = _runner(monkeypatch, tmp_path, plan, mock, tag="mprot")
    # one open book piece WITHOUT any resting exits on the exchange
    pid = "b0BTCprot"
    r.state["ledger"][pid] = dict(symbol=SYM, side=1, qty=0.01, entry=79000.0,
                                  kind="book", phase=0, opened=str(now),
                                  sl=75000.0, tp=83000.0)
    rec = r._startup_protection_check()
    assert pid in rec["open"] and rec["missing"]
    ops = _ops(r)
    pc = [x for x in ops if x.get("op") == "protection_check"]
    assert pc and pc[-1]["missing"]
    # the same gap is a CRITICAL line in bot_health (existing unprotected rule)
    spec = importlib.util.spec_from_file_location(
        "bot_health", Path(runmod.__file__).resolve().parents[1] / "scripts" / "bot_health.py")
    bh = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bh)
    from datetime import datetime, timezone
    tnow = datetime.now(timezone.utc)
    r.state_f.write_text(json.dumps(r.state, default=str))
    with open(r.dir / "actions.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps({"t": tnow.isoformat(), "op": "protection_check"}) + "\n")
    rep = bh.check_dir(r.dir, {"generated_at": tnow.isoformat()}, tnow, 20.0)
    assert rep["status"] == "critical"
    assert rep["unprotected"]
    assert any("CRITICAL" in line for line in bh.fmt_report(rep).splitlines())


def test_startup_protection_check_clean_when_guarded(monkeypatch, tmp_path):
    now = _now()
    plan = {"generated_at": str(now), "phases": [{"phase": 0, "capital": 0.25}],
            "coins": {}}
    mock = MockBybitV5(prices={SYM: PX}, equity=10000.0)
    r = _runner(monkeypatch, tmp_path, plan, mock, tag="mprotok")
    pid = "b0BTCok"
    r.state["ledger"][pid] = dict(symbol=SYM, side=1, qty=0.01, entry=79000.0,
                                  kind="book", phase=0, opened=str(now),
                                  sl=75000.0, tp=83000.0)
    for link, kind, px in ((pid + "T", "tp", 83000.0), (pid + "S", "stop", 75000.0)):
        o = mirror.Order(link, SYM, "Sell", 0.01, kind,
                         price=px if kind == "tp" else None,
                         trigger=px if kind == "stop" else None,
                         reduce_only=True, position_idx=1, piece=pid)
        r.state["links"][link] = dict(order=runmod.asdict(o),
                                      rest=dict(symbol=SYM, price=px, qty=0.01))
        mock.orders[link] = dict(symbol=SYM, side="Sell",
                                 orderType="Limit" if kind == "tp" else "Market",
                                 price=str(px), qty="0.01", orderLinkId=link,
                                 positionIdx=1)
    rec = r._startup_protection_check()
    assert rec["missing"] == []
