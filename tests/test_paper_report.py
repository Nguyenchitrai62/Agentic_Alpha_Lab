import importlib.util
import json
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "paper_report", Path(__file__).resolve().parents[1] / "scripts" / "paper_report.py")
pr = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pr)


def write_dir(root, name="bot", actions=(), ledger=None, links=None, exchange=None, stdout=None):
    d = root / name
    d.mkdir(parents=True, exist_ok=True)
    with open(d / "actions.jsonl", "w", encoding="utf-8") as f:
        for r in actions:
            f.write(json.dumps(r) + "\n")
    (d / "state.json").write_text(json.dumps({"ledger": ledger or {}, "links": links or {}}),
                                  encoding="utf-8")
    if exchange is not None:
        (d / "exchange.json").write_text(json.dumps(exchange), encoding="utf-8")
    if stdout is not None:
        (d / "stdout.log").write_text(stdout, encoding="utf-8")
    return d


def act(t, op, **kw):
    return dict(t=t, mode="paper", op=op, **kw)


T0 = "2026-10-05 04:00:00+00:00"
T1 = "2026-10-05 05:00:00+00:00"


def ex_curve(vals):
    return {"cash": 5000.0, "equity0": 5000.0, "orders": {}, "pos": {},
            "execs": [], "funding_paid": 0.0, "fees": 1.5,
            "equity_curve": [[T0, vals[0]], [T1, vals[1]]]}


def test_equity_return_dd(tmp_path):
    d = write_dir(tmp_path, actions=[act(T0, "place")], exchange=ex_curve([5000.0, 5100.0]))
    r = pr.summarize_dir(d)
    assert r["equity_now"] == 5100.0
    assert r["return_pct"] == pytest.approx(2.0)
    assert r["max_dd_pct"] == pytest.approx(0.0)
    d2 = write_dir(tmp_path, name="b2", actions=[act(T0, "place")],
                   exchange={"cash": 0, "equity0": 100.0, "orders": {}, "pos": {},
                             "execs": [], "fees": 0.0, "funding_paid": 0.0,
                             "equity_curve": [[T0, 100.0], [T1, 110.0], [T1, 99.0]]})
    r2 = pr.summarize_dir(d2)
    assert r2["max_dd_pct"] == pytest.approx(100.0 * (110.0 - 99.0) / 110.0)


def test_fills_and_win_rates_split(tmp_path):
    dip, book = "d0BNB1", "b1BTC1"
    links = {"dE": {"order": {"link": "dE", "symbol": "BNBUSDT", "side": "Buy", "qty": 1.0,
                              "kind": "entry", "piece": dip, "meta": {"kind": "dip"}}},
             "dX": {"order": {"link": "dX", "symbol": "BNBUSDT", "side": "Sell", "qty": 1.0,
                              "kind": "tp", "piece": dip, "meta": {"kind": "dip"}}},
             "bE": {"order": {"link": "bE", "symbol": "BTCUSDT", "side": "Buy", "qty": 0.002,
                              "kind": "entry", "piece": book, "meta": {"kind": "book"}}},
             "bX": {"order": {"link": "bX", "symbol": "BTCUSDT", "side": "Sell", "qty": 0.002,
                              "kind": "stop", "piece": book, "meta": {"kind": "book"}}}}
    ledger = {dip: {"symbol": "BNBUSDT", "side": 1, "qty": 0.0, "kind": "dip"},
              book: {"symbol": "BTCUSDT", "side": 1, "qty": 0.0, "kind": "book"}}
    ms = str(int(pr.parse_ts(T1).timestamp() * 1000))
    exchange = ex_curve([5000.0, 5005.0])
    exchange["execs"] = [
        {"execId": "1", "orderLinkId": "dE", "execQty": "1.0", "execPrice": "700.0", "execTime": ms},
        {"execId": "2", "orderLinkId": "dX", "execQty": "1.0", "execPrice": "710.0", "execTime": ms},
        {"execId": "3", "orderLinkId": "bE", "execQty": "0.002", "execPrice": "85000.0", "execTime": ms},
        {"execId": "4", "orderLinkId": "bX", "execQty": "0.002", "execPrice": "84000.0", "execTime": ms}]
    d = write_dir(tmp_path, actions=[act(T0, "fill", link="dE")], ledger=ledger,
                  links=links, exchange=exchange)
    r = pr.summarize_dir(d)
    assert (r["dip_fills"], r["book_fills"]) == (1, 1)
    assert r["wr_all"] == {"n": 2, "wins": 1, "losses": 1, "rate": pytest.approx(0.5)}
    assert r["wr_dip"]["rate"] == pytest.approx(1.0)
    assert r["wr_book"]["rate"] == pytest.approx(0.0)


def test_error_counts_and_flags(tmp_path):
    recs = [act(T0, "stale_plan"), act(T0, "stale_plan"), act(T0, "plan_error"),
            act(T0, "cycle_error", note="x"), act(T0, "error", note="y"),
            act(T0, "bear_state", bear=False, opens=1200)]
    d = write_dir(tmp_path, actions=recs, exchange=ex_curve([5000.0, 5000.0]))
    r = pr.summarize_dir(d)
    assert (r["stale_plan"], r["plan_error"], r["errors"]) == (2, 1, 2)
    assert "bear-book=on" in r["flags"]
    d2 = write_dir(tmp_path, name="plain", actions=[act(T0, "place")],
                   exchange=ex_curve([5000.0, 5000.0]))
    r2 = pr.summarize_dir(d2)
    assert "n/a" in r2["flags"]  # unrecorded CLI flags are n/a


def test_missing_files_tolerant(tmp_path):
    d = tmp_path / "empty"
    d.mkdir()
    r = pr.summarize_dir(d)
    assert r["equity_now"] is None and r["dip_fills"] == 0 and r["errors"] == 0
    assert r["start"] == "n/a"


def test_cli_text_md_json(tmp_path, capsys):
    a = write_dir(tmp_path, name="aa", actions=[act(T0, "place")], exchange=ex_curve([5000.0, 5001.0]))
    b = write_dir(tmp_path, name="bb", actions=[act(T0, "stale_plan")], exchange=ex_curve([5000.0, 5000.0]))
    md, js = tmp_path / "r.md", tmp_path / "r.json"
    assert pr.main([str(a), str(b), "--md", str(md), "--json", str(js)]) == 0
    out = capsys.readouterr().out
    assert "aa" in out and "bb" in out and "dip fills" in out
    mdt = md.read_text(encoding="utf-8")
    assert mdt.startswith("| metric |") and "aa" in mdt
    payload = json.loads(js.read_text(encoding="utf-8"))
    assert [x["name"] for x in payload["dirs"]] == ["aa", "bb"]
