"""Synthetic tests for scripts/paper_compare.py (oc_papercmp). No market data."""
import importlib.util
import json
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "scripts" / "paper_compare.py"

spec = importlib.util.spec_from_file_location("paper_compare", TOOL)
pc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pc)


def test_equity_return_and_dd():
    curve = [["t0", 100.0], ["t1", 110.0], ["t2", 99.0], ["t3", 121.0]]
    s = pc.equity_stats(curve)
    assert abs(s["return_pct"] - 21.0) < 1e-9
    # peak 110 -> 99 = 10% is the worst drawdown (peak 110 before t2)
    assert abs(s["max_dd_pct"] - 10.0) < 1e-9
    assert s["curve"] == curve


def test_classify_and_win_rate_synthetic(tmp_path=None):
    tmp = Path(tempfile.mkdtemp())
    state_links = {
        "b1XYZ0E": ("entry", "b1XYZ0", "book"),
        "b1XYZ0T": ("tp", "b1XYZ0", "book"),
        "d1AAA25xE": ("entry", "d1AAA25x", "dip"),
    }
    assert pc.classify_exec("b1XYZ0E", state_links)[0] == "book_entry"
    assert pc.classify_exec("d1AAA25xE", state_links)[0] == "dip"
    assert pc.classify_exec("b1XYZ0T", state_links)[0] == "tp"
    assert pc.classify_exec("zzz9S", {})[0] == "stop"  # naming-rule fallback
    # one winning closed piece (buy 100, sell 110) + one open piece
    ex = {"orders": {}, "execs": [
        {"orderLinkId": "b1XYZ0E", "execQty": "1", "execPrice": "100"},
        {"orderLinkId": "b1XYZ0T", "execQty": "1", "execPrice": "110"},
        {"orderLinkId": "d1AAA25xE", "execQty": "2", "execPrice": "50"},
    ], "equity_curve": [["t0", 1000.0], ["t1", 1010.0]]}
    exp = tmp / "ex.json"
    exp.write_text(json.dumps(ex))
    stp = tmp / "st.json"
    stp.write_text(json.dumps({"links": {
        "b1XYZ0E": {"order": {"kind": "entry", "piece": "b1XYZ0",
                              "symbol": "BTCUSDT", "meta": {"kind": "book"}}},
        "b1XYZ0T": {"order": {"kind": "tp", "piece": "b1XYZ0",
                              "symbol": "BTCUSDT", "meta": {}}},
        "d1AAA25xE": {"order": {"kind": "entry", "piece": "d1AAA25x",
                               "symbol": "ETHUSDT", "meta": {"kind": "dip"}}}}}))
    logp = tmp / "run.log"
    logp.write_text('{"op": "place"}\n{"op": "fill"}\n')
    s = pc.summarize_bot("syn", exp, logp, stp)
    assert s["fills_by_kind"]["book_entry"] == 1
    assert s["fills_by_kind"]["dip"] == 1
    assert s["fills_by_kind"]["tp"] == 1
    assert s["pieces"]["closed"] == 1
    assert s["pieces"]["wins"] == 1
    assert s["pieces"]["win_rate"] == 1.0


def test_divergence_return_diff():
    bot = {"return_pct": 0.5, "entries_by_symbol": {"BTCUSDT": 2},
           "pieces": {"closed_ids": []}}
    plan = {"return_pct": 0.1, "book_fills_by_symbol": {"BTCUSDT": 1},
            "book_fills": [{"t": "t", "symbol": "BTCUSDT", "price": 1.0}]}
    d = pc.divergence(bot, plan)
    assert abs(d["return_diff_pp"] - 0.4) < 1e-9
    assert d["per_symbol"]["BTCUSDT"]["only_in_bot"] == 1
