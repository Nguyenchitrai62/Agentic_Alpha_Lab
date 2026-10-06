import importlib.util
import json
from datetime import timedelta
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "bot_health", Path(__file__).resolve().parents[1] / "scripts" / "bot_health.py")
bh = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bh)

NOW = "2026-10-05T15:30:00+00:00"


def write_dir(tmp_path, name="bot", actions=(), ledger=None, links=None, exchange=None):
    d = tmp_path / name
    d.mkdir(parents=True, exist_ok=True)
    with open(d / "actions.jsonl", "w", encoding="utf-8") as f:
        for r in actions:
            f.write(json.dumps(r) + "\n")
    (d / "state.json").write_text(json.dumps({"ledger": ledger or {}, "links": links or {}}),
                                  encoding="utf-8")
    if exchange is not None:
        (d / "exchange.json").write_text(json.dumps(exchange), encoding="utf-8")
    return d


def act(t, op, **kw):
    return dict(t=t, mode="paper", op=op, **kw)


def link(pid, kind, symbol="BTCUSDT", side="Buy", qty=0.002, meta_kind="book", price=85000.0):
    return {"order": {"link": pid, "symbol": symbol, "side": side, "qty": qty, "kind": kind,
                      "price": price, "trigger": None, "reduce_only": kind in ("tp", "stop"),
                      "position_idx": 1, "piece": pid[:-1] if kind in ("tp", "stop") else pid,
                      "meta": {"kind": meta_kind, "phase": 1}}, "rest": {"symbol": symbol, "qty": qty}}


def book_piece(qty=0.002):
    return {"symbol": "BTCUSDT", "side": 1, "qty": qty, "entry": 85000.0, "kind": "book",
            "phase": 1, "opened": "2026-10-05 04:51:00+00:00", "sl": 78000.0, "tp": 99000.0}


def paper_exchange(orders=None, pos=None, equity_curve=None, execs=None):
    default_pos = {"BTCUSDT|1": {"qty": 0.002, "avg": 85000.0}}
    default_curve = [["2026-10-05 14:00:00+00:00", 5000.0],
                     ["2026-10-05 15:00:00+00:00", 5010.0]]
    return {"cash": 5000.0, "equity0": 5000.0, "orders": orders if orders is not None else {},
            "pos": pos if pos is not None else default_pos,
            "execs": execs if execs is not None else [], "last_ms": {}, "last_close": {"BTCUSDT": 85000.0},
            "funding_paid": 0.0, "fees": 0.0,
            "equity_curve": equity_curve if equity_curve is not None else default_curve}


def plan(tmp_path, age_h=1.0):
    from datetime import datetime, timezone
    now = datetime.fromisoformat(NOW)
    gen = (now - timedelta(hours=age_h)).isoformat()
    p = tmp_path / "plan.json"
    p.write_text(json.dumps({"generated_at": gen}), encoding="utf-8")
    return str(p)


def run(d, tmp_path, **kw):
    kw.setdefault("plan_age_h", 1.0)
    args = [str(d), "--now", NOW, "--plan", plan(tmp_path, kw.pop("plan_age_h"))]
    for k, v in kw.items():
        args += [f"--{k}", str(v)]
    return bh.main(args)


def healthy(tmp_path, name="bot", **kw):
    t = NOW
    pid = "b1BTChrub0"
    ledger = {pid: book_piece()}
    links = {pid + "S": link(pid + "S", "stop"), pid + "T": link(pid + "T", "tp")}
    orders = {pid + "S": {"symbol": "BTCUSDT", "triggerPrice": "78000.0"},
              pid + "T": {"symbol": "BTCUSDT", "price": "99000.0"}}
    d = write_dir(tmp_path, name, actions=[act(t, "place")], ledger=ledger, links=links,
                  exchange=paper_exchange(orders=orders))
    return d


def test_ok_exit_0(tmp_path, capsys):
    assert run(healthy(tmp_path), tmp_path) == 0
    out = capsys.readouterr().out
    assert "[OK]" in out and "unprotected=none" in out and "qty_mismatch=none" in out


def test_stale_cycle_is_critical(tmp_path, capsys):
    d = healthy(tmp_path)
    old = (bh.parse_ts(NOW) - timedelta(minutes=30)).isoformat()
    (d / "actions.jsonl").write_text(json.dumps(act(old, "place")) + "\n", encoding="utf-8")
    assert run(d, tmp_path) == 2
    assert "last cycle" in capsys.readouterr().out


def test_missing_actions_is_critical(tmp_path, capsys):
    d = tmp_path / "empty"
    d.mkdir()
    assert bh.main([str(d), "--now", NOW, "--plan", plan(tmp_path)]) == 2
    assert "missing actions.jsonl" in capsys.readouterr().out


def test_stale_plan_is_warning(tmp_path, capsys):
    assert run(healthy(tmp_path), tmp_path, plan_age_h=2.0) == 1
    assert "plan age 2.0h" in capsys.readouterr().out


def test_stale_plan_is_critical(tmp_path, capsys):
    assert run(healthy(tmp_path), tmp_path, plan_age_h=5.0) == 2
    assert "plan age 5.0h" in capsys.readouterr().out


def test_op_counts_24h(tmp_path):
    t = bh.parse_ts(NOW)
    recs = [act((t - timedelta(hours=h)).isoformat(), op)
            for h, op in [(0, "place"), (2, "amend"), (3, "cancel"), (4, "fill",),
                          (5, "market_exit"), (6, "stale_plan")]]
    recs.append(act((t - timedelta(hours=30)).isoformat(), "place"))  # outside the window
    d = write_dir(tmp_path, actions=recs, ledger={}, links={},
                  exchange=paper_exchange(pos={}, equity_curve=[]))
    rep = bh.check_dir(d, {"generated_at": NOW}, t, 20.0)
    assert rep["counts_24h"]["place"] == 1  # only the in-window one
    for op in ("amend", "cancel", "fill", "market_exit", "stale_plan"):
        assert rep["counts_24h"][op] == 1
    assert rep["status"] == "ok"  # counts alone are not warnings


def test_rate_limit_errors_warn(tmp_path, capsys):
    t = NOW
    recs = [act(t, "cycle_error", note="BybitError('10006: Too many visits. Exceeded the API Rate Limit.')"),
            act(t, "error", call="place", note="boom")]
    d = write_dir(tmp_path, actions=recs, ledger={}, links={},
                  exchange=paper_exchange(pos={}, equity_curve=[]))
    assert run(d, tmp_path) == 1
    out = capsys.readouterr().out
    assert "errors=2" in out and "rate_limit=1" in out


def test_open_piece_without_stop_and_tp_is_critical(tmp_path):
    pid = "b1BTChrub0"
    ledger = {pid: book_piece()}
    links = {pid + "T": link(pid + "T", "tp")}  # stop missing on the exchange
    d = write_dir(tmp_path, actions=[act(NOW, "place")], ledger=ledger, links=links,
                  exchange=paper_exchange(orders={pid + "T": {"symbol": "BTCUSDT", "price": "99000.0"}},
                                          pos={"BTCUSDT|1": {"qty": 0.002, "avg": 85000.0}}))
    rep = bh.check_dir(d, {"generated_at": NOW}, bh.parse_ts(NOW), 20.0)
    assert rep["status"] == "critical"
    assert rep["unprotected"] == [f"{pid}(BTCUSDT:no-stop)"]


def test_unprotected_falls_back_to_state_rest_without_exchange(tmp_path):
    pid = "b1BTChrub0"
    d = write_dir(tmp_path, actions=[act(NOW, "place")], ledger={pid: book_piece()},
                  links={pid + "S": link(pid + "S", "stop"), pid + "T": link(pid + "T", "tp")},
                  exchange=None)
    rep = bh.check_dir(d, {"generated_at": NOW}, bh.parse_ts(NOW), 20.0)
    assert rep["unprotected"] == [] and rep["qty_mismatch"] == []


def test_qty_disagreement_is_critical(tmp_path, capsys):
    d = healthy(tmp_path)
    ex = json.loads((d / "exchange.json").read_text(encoding="utf-8"))
    ex["pos"] = {"BTCUSDT|1": {"qty": 0.001, "avg": 85000.0}}  # ledger holds 0.002
    (d / "exchange.json").write_text(json.dumps(ex), encoding="utf-8")
    assert run(d, tmp_path) == 2
    assert "qty disagreement" in capsys.readouterr().out


def test_equity_and_max_dd(tmp_path):
    d = write_dir(tmp_path, actions=[act(NOW, "place")], ledger={}, links={},
                  exchange=paper_exchange(pos={}, equity_curve=[
                      ["2026-10-05 12:00:00+00:00", 5000.0],
                      ["2026-10-05 13:00:00+00:00", 5100.0],
                      ["2026-10-05 14:00:00+00:00", 4845.0]]))
    rep = bh.check_dir(d, {"generated_at": NOW}, bh.parse_ts(NOW), 20.0)
    assert rep["equity_now"] == 4845.0 and rep["equity_pnl"] == pytest.approx(-155.0)
    assert rep["max_dd"] == pytest.approx((5100.0 - 4845.0) / 5100.0)


def test_dip_book_fills_and_closed_win_loss(tmp_path):
    t = bh.parse_ts(NOW)
    dip_pid, book_pid = "d0BNB25hrumo", "b1BTChrub0"
    links = {"dlink": {"order": {"link": "dlink", "symbol": "BNBUSDT", "side": "Buy", "qty": 1.0,
                                 "kind": "entry", "piece": dip_pid, "meta": {"kind": "dip"}}},
             "blink": {"order": {"link": "blink", "symbol": "BTCUSDT", "side": "Buy", "qty": 0.002,
                                 "kind": "entry", "piece": book_pid, "meta": {"kind": "book"}}},
             "dexit": {"order": {"link": "dexit", "symbol": "BNBUSDT", "side": "Sell", "qty": 1.0,
                                 "kind": "tp", "piece": dip_pid, "meta": {"kind": "dip"}}},
             "bexit": {"order": {"link": "bexit", "symbol": "BTCUSDT", "side": "Sell", "qty": 0.002,
                                 "kind": "stop", "piece": book_pid, "meta": {"kind": "book"}}}}
    ledger = {dip_pid: {"symbol": "BNBUSDT", "side": 1, "qty": 0.0, "kind": "dip"},  # closed win
              book_pid: {"symbol": "BTCUSDT", "side": 1, "qty": 0.0, "kind": "book"}}  # closed loss
    ms = str(int(t.timestamp() * 1000))
    execs = [{"execId": "a", "orderLinkId": "dlink", "execQty": "1.0", "execPrice": "700.0", "execTime": ms},
             {"execId": "b", "orderLinkId": "dexit", "execQty": "1.0", "execPrice": "710.0", "execTime": ms},
             {"execId": "c", "orderLinkId": "blink", "execQty": "0.002", "execPrice": "85000.0", "execTime": ms},
             {"execId": "d", "orderLinkId": "bexit", "execQty": "0.002", "execPrice": "84000.0", "execTime": ms}]
    recs = [act(NOW, "fill", link="dlink", qty="1.0", price="700.0"),
            act(NOW, "fill", link="blink", qty="0.002", price="85000.0")]
    d = write_dir(tmp_path, actions=recs, ledger=ledger, links=links,
                  exchange=paper_exchange(pos={}, execs=execs))
    rep = bh.check_dir(d, {"generated_at": NOW}, t, 20.0)
    assert rep["fills_24h"] == {"dip": 1, "book": 1, "other": 0}
    assert rep["closed_24h"]["wins"] == 1 and rep["closed_24h"]["losses"] == 1
    assert rep["closed_24h"]["pnl"] == pytest.approx(10.0 - 2.0, abs=1e-6)


def test_json_output_and_multi_dir_exit_code(tmp_path, capsys):
    ok_d = healthy(tmp_path, name="ok")
    bad_d = healthy(tmp_path, name="bad")
    old = (bh.parse_ts(NOW) - timedelta(minutes=30)).isoformat()
    (bad_d / "actions.jsonl").write_text(json.dumps(act(old, "place")) + "\n", encoding="utf-8")
    rc = bh.main([str(ok_d), str(bad_d), "--now", NOW, "--plan", plan(tmp_path), "--json"])
    assert rc == 2  # worst of ok + critical
    payload = json.loads(capsys.readouterr().out)
    assert [r["status"] for r in payload["dirs"]] == ["ok", "critical"]
