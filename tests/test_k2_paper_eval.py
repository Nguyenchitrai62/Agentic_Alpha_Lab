"""Tests for scripts/k2_paper_eval.py (synthetic runner dirs + kronos rows)."""
import importlib.util
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("k2_paper_eval", ROOT / "scripts/k2_paper_eval.py")
k2 = importlib.util.module_from_spec(SPEC)
sys.modules["k2_paper_eval"] = k2
SPEC.loader.exec_module(k2)


def t36(ts):
    n = int(pd.Timestamp(ts).timestamp() // 60)
    alpha = "0123456789abcdefghijklmnopqrstuvwxyz"
    s = ""
    while n:
        n, r = divmod(n, 36)
        s = alpha[r] + s
    return s or "0"


def dip_pid(phase, sym, rung, bar):
    coin = sym[:-4]
    return f"d{phase}{coin}{int(round(float(rung) * 10))}{t36(bar)}"


def write_runner(root, name, ledger, links, execs, actions_extra=(), corrections=None):
    d = root / name
    d.mkdir(parents=True, exist_ok=True)
    actions = []
    for e in execs:
        # minimal fill action for fallback path parity (not needed when execs exist)
        pass
    recs = list(actions_extra)
    (d / "actions.jsonl").write_text(
        "\n".join(json.dumps(r) for r in recs) + ("\n" if recs else ""), encoding="utf-8")
    (d / "state.json").write_text(
        json.dumps({"ledger": ledger, "links": links}), encoding="utf-8")
    (d / "exchange.json").write_text(json.dumps({
        "cash": 1000.0, "equity0": 1000.0, "orders": {}, "pos": {},
        "execs": execs, "fees": 0.0, "funding_paid": 0.0, "equity_curve": [],
    }), encoding="utf-8")
    return d


def mk_exec(link, qty, px, ms):
    return {"execId": link, "orderLinkId": link, "execQty": str(qty),
            "execPrice": str(px), "execTime": str(ms)}


def ms(ts):
    return int(pd.Timestamp(ts).timestamp() * 1000)


def write_kronos(path, rows):
    pd.DataFrame(rows).to_parquet(path, index=False)


def test_join_on_phase_shift_symbol_and_T(tmp_path):
    # Two dip pieces, same symbol/T but different phases; kronos row only for phase 2.
    T = "2026-10-07 10:00:00+00:00"
    p2 = dip_pid(2, "BTCUSDT", 2.5, T)
    p3 = dip_pid(3, "BTCUSDT", 2.5, T)
    ledger = {
        p2: {"symbol": "BTCUSDT", "side": 1, "qty": 0.0, "kind": "dip", "phase": 2},
        p3: {"symbol": "BTCUSDT", "side": 1, "qty": 0.0, "kind": "dip", "phase": 3},
    }
    links = {
        p2 + "E": {"order": {"link": p2 + "E", "symbol": "BTCUSDT", "side": "Buy",
                             "qty": 1.0, "kind": "entry", "piece": p2, "meta": {"kind": "dip"}}},
        p2 + "T": {"order": {"link": p2 + "T", "symbol": "BTCUSDT", "side": "Sell",
                             "qty": 1.0, "kind": "tp", "piece": p2, "meta": {"kind": "dip"}}},
        p3 + "E": {"order": {"link": p3 + "E", "symbol": "BTCUSDT", "side": "Buy",
                             "qty": 1.0, "kind": "entry", "piece": p3, "meta": {"kind": "dip"}}},
        p3 + "T": {"order": {"link": p3 + "T", "symbol": "BTCUSDT", "side": "Sell",
                             "qty": 1.0, "kind": "tp", "piece": p3, "meta": {"kind": "dip"}}},
    }
    t0, t1 = ms("2026-10-07 10:05:00+00:00"), ms("2026-10-07 11:00:00+00:00")
    execs = [mk_exec(p2 + "E", 0.01, 80000, t0), mk_exec(p2 + "T", 0.01, 81000, t1),
             mk_exec(p3 + "E", 0.01, 80000, t0), mk_exec(p3 + "T", 0.01, 81000, t1)]
    d = write_runner(tmp_path, "paper_x", ledger, links, execs)
    kp = tmp_path / "k.parquet"
    write_kronos(kp, [{"sym": "BTCUSDT", "shift": 2, "T": pd.Timestamp(T, tz="UTC"),
                       "k2_mult": 1.25, "mode": "prospective"}])
    res = k2.evaluate(d, kp, tmp_path / "nocorr.json")
    assert res["n_joined_prospective"] == 1
    assert res["n_unjoined"] == 1


def test_exposure_normalisation_hand_checked(tmp_path):
    # Two joined pieces, k2 0.75 and 1.25 (mean 1.0): normalised sum = 0.75*a + 1.25*b.
    T = "2026-10-07 10:00:00+00:00"
    pa = dip_pid(2, "BTCUSDT", 2.5, T)
    pb = dip_pid(2, "ETHUSDT", 2.5, T)
    ledger = {pa: {"symbol": "BTCUSDT", "side": 1, "qty": 0.0, "kind": "dip", "phase": 2},
              pb: {"symbol": "ETHUSDT", "side": 1, "qty": 0.0, "kind": "dip", "phase": 2}}
    links = {}
    for p, s in ((pa, "BTCUSDT"), (pb, "ETHUSDT")):
        links[p + "E"] = {"order": {"link": p + "E", "symbol": s, "side": "Buy",
                                    "qty": 1.0, "kind": "entry", "piece": p, "meta": {"kind": "dip"}}}
        links[p + "T"] = {"order": {"link": p + "T", "symbol": s, "side": "Sell",
                                    "qty": 1.0, "kind": "tp", "piece": p, "meta": {"kind": "dip"}}}
    t0, t1 = ms("2026-10-07 10:05:00+00:00"), ms("2026-10-07 11:00:00+00:00")
    execs = [mk_exec(pa + "E", 1.0, 100.0, t0), mk_exec(pa + "T", 1.0, 110.0, t1),
             mk_exec(pb + "E", 1.0, 100.0, t0), mk_exec(pb + "T", 1.0, 120.0, t1)]
    d = write_runner(tmp_path, "paper_n", ledger, links, execs)
    kp = tmp_path / "k.parquet"
    write_kronos(kp, [
        {"sym": "BTCUSDT", "shift": 2, "T": pd.Timestamp(T, tz="UTC"), "k2_mult": 0.75, "mode": "prospective"},
        {"sym": "ETHUSDT", "shift": 2, "T": pd.Timestamp(T, tz="UTC"), "k2_mult": 1.25, "mode": "prospective"}])
    res = k2.evaluate(d, kp, tmp_path / "nocorr.json")
    assert res["mean_k2"] == 1.0
    # gross: BTC 10 - fees(0.02+0.022)=9.958; ETH 20 - fees(0.02+0.024)=19.956
    pa_net = 10.0 - (1.0 * 100.0 * 0.0002 + 1.0 * 110.0 * 0.0002)
    pb_net = 20.0 - (1.0 * 100.0 * 0.0002 + 1.0 * 120.0 * 0.0002)
    assert res["sum_pnl"] == pa_net + pb_net
    assert res["sum_k2_pnl"] == pa_net * 0.75 + pb_net * 1.25
    assert res["diff"] == (pa_net * 0.75 + pb_net * 1.25) - (pa_net + pb_net)


def test_correction_window_excludes_exit_inside(tmp_path):
    T = "2026-10-07 10:00:00+00:00"
    p = dip_pid(2, "BTCUSDT", 2.5, T)
    ledger = {p: {"symbol": "BTCUSDT", "side": 1, "qty": 0.0, "kind": "dip", "phase": 2}}
    links = {p + "E": {"order": {"link": p + "E", "symbol": "BTCUSDT", "side": "Buy",
                                 "qty": 1.0, "kind": "entry", "piece": p, "meta": {"kind": "dip"}}},
             p + "Xw": {"order": {"link": p + "Xw", "symbol": "BTCUSDT", "side": "Sell",
                                  "qty": 1.0, "kind": "reduce", "piece": p, "meta": {"kind": "dip"}}}}
    t0 = ms("2026-10-07 10:05:00+00:00")
    t1 = ms("2026-10-07 10:30:00+00:00")  # inside the window below
    execs = [mk_exec(p + "E", 1.0, 100.0, t0), mk_exec(p + "Xw", 1.0, 110.0, t1)]
    d = write_runner(tmp_path, "paper_d17bfg2", ledger, links, execs)
    kp = tmp_path / "k.parquet"
    write_kronos(kp, [{"sym": "BTCUSDT", "shift": 2, "T": pd.Timestamp(T, tz="UTC"),
                       "k2_mult": 1.25, "mode": "prospective"}])
    corr = tmp_path / "corr.json"
    corr.write_text(json.dumps([{"start": "2026-10-07T10:00:00+00:00",
                                 "end": "2026-10-07T11:00:00+00:00", "runners": "all"}]),
                    encoding="utf-8")
    res = k2.evaluate(d, kp, corr)
    assert res["n_excluded_correction"] == 1
    assert res["n_joined_prospective"] == 0


def test_prospective_filter_late_and_backfill_apart(tmp_path):
    T = "2026-10-07 10:00:00+00:00"
    pa = dip_pid(2, "BTCUSDT", 2.5, T)
    pb = dip_pid(2, "ETHUSDT", 2.5, T)
    ledger = {pa: {"symbol": "BTCUSDT", "side": 1, "qty": 0.0, "kind": "dip", "phase": 2},
              pb: {"symbol": "ETHUSDT", "side": 1, "qty": 0.0, "kind": "dip", "phase": 2}}
    links = {}
    for p, s in ((pa, "BTCUSDT"), (pb, "ETHUSDT")):
        links[p + "E"] = {"order": {"link": p + "E", "symbol": s, "side": "Buy",
                                    "qty": 1.0, "kind": "entry", "piece": p, "meta": {"kind": "dip"}}}
        links[p + "T"] = {"order": {"link": p + "T", "symbol": s, "side": "Sell",
                                    "qty": 1.0, "kind": "tp", "piece": p, "meta": {"kind": "dip"}}}
    t0, t1 = ms("2026-10-07 10:05:00+00:00"), ms("2026-10-07 11:00:00+00:00")
    execs = [mk_exec(pa + "E", 1.0, 100.0, t0), mk_exec(pa + "T", 1.0, 110.0, t1),
             mk_exec(pb + "E", 1.0, 100.0, t0), mk_exec(pb + "T", 1.0, 110.0, t1)]
    d = write_runner(tmp_path, "paper_q", ledger, links, execs)
    kp = tmp_path / "k.parquet"
    write_kronos(kp, [
        {"sym": "BTCUSDT", "shift": 2, "T": pd.Timestamp(T, tz="UTC"), "k2_mult": 1.25, "mode": "prospective"},
        {"sym": "ETHUSDT", "shift": 2, "T": pd.Timestamp(T, tz="UTC"), "k2_mult": 0.75, "mode": "late"}])
    res = k2.evaluate(d, kp, tmp_path / "nocorr.json")
    assert res["n_joined_prospective"] == 1
    assert res["n_joined_nonprospective"] == 1
    # main sums cover only the prospective piece
    assert res["n_unjoined"] == 0


def test_pid_parsing_matches_mirror_convention():
    assert k2.parse_dip_pid("d3BTC25hrwmc")[0] == 3
    ph, sym, rung, bar = k2.parse_dip_pid("d3BTC25hrwmc")
    assert (ph, sym, rung) == (3, "BTCUSDT", 2.5)
    assert bar == pd.Timestamp("2026-10-06 23:00:00+00:00")
    assert bar.hour % 4 == ph
    assert k2.parse_dip_pid("b2ETHhrvgo") is None
