"""Tests for scripts/fm_paper_eval.py (synthetic fixtures, no artifacts writes)."""
import importlib.util
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("fm_paper_eval", ROOT / "scripts/fm_paper_eval.py")
fm = importlib.util.module_from_spec(SPEC)
sys.modules["fm_paper_eval"] = fm
SPEC.loader.exec_module(fm)


def t36(ts):
    n = int(pd.Timestamp(ts).timestamp() // 60)
    alpha = "0123456789abcdefghijklmnopqrstuvwxyz"
    s = ""
    while n:
        n, r = divmod(n, 36)
        s = alpha[r] + s
    return s or "0"


def dip_pid(phase, sym, rung, bar):
    return f"d{phase}{sym[:-4]}{int(round(float(rung) * 10))}{t36(bar)}"


def ms(ts):
    return int(pd.Timestamp(ts).timestamp() * 1000)


def mk_exec(link, qty, px, t):
    return {"execId": link, "orderLinkId": link, "execQty": str(qty),
            "execPrice": str(px), "execTime": str(ms(t))}


def dip_links(p, sym):
    return {
        p + "E": {"order": {"link": p + "E", "symbol": sym, "side": "Buy",
                            "qty": 1.0, "kind": "entry", "piece": p,
                            "meta": {"kind": "dip"}}},
        p + "T": {"order": {"link": p + "T", "symbol": sym, "side": "Sell",
                            "qty": 1.0, "kind": "tp", "piece": p,
                            "meta": {"kind": "dip"}}},
    }


def write_runner(root, name, ledger, links, execs, curve=(), actions=()):
    d = root / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "actions.jsonl").write_text(
        "\n".join(json.dumps(r) for r in actions) + ("\n" if actions else ""),
        encoding="utf-8")
    (d / "state.json").write_text(
        json.dumps({"ledger": ledger, "links": links}), encoding="utf-8")
    (d / "exchange.json").write_text(json.dumps({
        "cash": 1000.0, "equity0": 1000.0, "orders": {}, "pos": {},
        "execs": execs, "fees": 0.0, "funding_paid": 0.0,
        "equity_curve": [[t, v] for t, v in curve],
    }), encoding="utf-8")
    return d


def write_feed(path, rows):
    pd.DataFrame(rows).to_parquet(path, index=False)


def nocorr(tmp_path):
    return tmp_path / "nocorr.json"  # missing file -> no correction windows


def test_feed_defaults_resolve(tmp_path):
    k = fm.resolve_config("kronos")
    assert k["runner"].name == "paper_d17bfg2k2"
    assert k["feed_path"].name == "kronos_features_live.parquet"
    assert k["mult_col"] == "k2_mult"
    assert k["twin"].name == "paper_d17bfg2"
    c = fm.resolve_config("chronos")
    assert c["runner"].name == "paper_d17bfg2ch"
    assert c["feed_path"].name == "chronos_features_live.parquet"
    assert c["mult_col"] == "c2_mult"
    try:
        fm.resolve_config("nope")
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError for unknown feed")


def test_qualify_rule_mode_and_is_prospective(tmp_path):
    # prospective+True and late+True join; late+False, backfill+True,
    # prospective+False do not (backfill/missing rows never leak in).
    T = "2026-10-07 10:00:00+00:00"
    syms = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
    modes = [("prospective", True), ("late", True), ("late", False),
             ("backfill", True), ("prospective", False)]
    ledger, links, execs = {}, {}, []
    t0, t1 = "2026-10-07 10:05:00+00:00", "2026-10-07 11:00:00+00:00"
    for sym, (mode, prosp) in zip(syms, modes):
        p = dip_pid(2, sym, 2.5, T)
        ledger[p] = {"symbol": sym, "side": 1, "qty": 0.0,
                     "kind": "dip", "phase": 2}
        links.update(dip_links(p, sym))
        execs += [mk_exec(p + "E", 1.0, 100.0, t0), mk_exec(p + "T", 1.0, 110.0, t1)]
    twin = write_runner(tmp_path, "paper_d17bfg2", ledger, links, execs,
                        curve=[("2026-10-07 10:00:00+00:00", 5000.0),
                               ("2026-10-07 11:00:00+00:00", 5010.0)])
    run = write_runner(tmp_path, "paper_d17bfg2k2", {}, {},
                       [], curve=[("2026-10-07 10:00:00+00:00", 5000.0),
                                  ("2026-10-07 11:00:00+00:00", 5005.0)])
    fp = tmp_path / "f.parquet"
    write_feed(fp, [{"sym": s, "shift": 2, "T": pd.Timestamp(T, tz="UTC"),
                     "k2_mult": 1.0, "mode": m, "is_prospective": pr}
                    for s, (m, pr) in zip(syms, modes)])
    res = fm.evaluate("kronos", run, twin, fp, nocorr(tmp_path), boot=50, seed=0)
    cf = res["counterfactual"]
    assert cf["n_joined"] == 2
    assert cf["n_nonqualifying_feed_row"] == 3
    assert cf["n_missing_feed_row"] == 0


def test_counterfactual_normalisation_hand_checked(tmp_path):
    T = "2026-10-07 10:00:00+00:00"
    pa, pb = dip_pid(2, "BTCUSDT", 2.5, T), dip_pid(2, "ETHUSDT", 2.5, T)
    ledger = {pa: {"symbol": "BTCUSDT", "side": 1, "qty": 0.0, "kind": "dip", "phase": 2},
              pb: {"symbol": "ETHUSDT", "side": 1, "qty": 0.0, "kind": "dip", "phase": 2}}
    links = {**dip_links(pa, "BTCUSDT"), **dip_links(pb, "ETHUSDT")}
    t0, t1 = "2026-10-07 10:05:00+00:00", "2026-10-07 11:00:00+00:00"
    execs = [mk_exec(pa + "E", 1.0, 100.0, t0), mk_exec(pa + "T", 1.0, 110.0, t1),
             mk_exec(pb + "E", 1.0, 100.0, t0), mk_exec(pb + "T", 1.0, 120.0, t1)]
    curve = [("2026-10-07 10:00:00+00:00", 5000.0), ("2026-10-07 11:00:00+00:00", 5010.0)]
    twin = write_runner(tmp_path, "paper_d17bfg2", ledger, links, execs, curve=curve)
    run = write_runner(tmp_path, "paper_d17bfg2k2", {}, {}, [], curve=curve)
    fp = tmp_path / "f.parquet"
    write_feed(fp, [
        {"sym": "BTCUSDT", "shift": 2, "T": pd.Timestamp(T, tz="UTC"),
         "k2_mult": 0.75, "mode": "prospective", "is_prospective": True},
        {"sym": "ETHUSDT", "shift": 2, "T": pd.Timestamp(T, tz="UTC"),
         "k2_mult": 1.25, "mode": "prospective", "is_prospective": True}])
    res = fm.evaluate("kronos", run, twin, fp, nocorr(tmp_path), boot=50, seed=0)
    cf = res["counterfactual"]
    assert cf["mean_mult"] == 1.0
    pa_net = 10.0 - (100.0 * 0.0002 + 110.0 * 0.0002)
    pb_net = 20.0 - (100.0 * 0.0002 + 120.0 * 0.0002)
    assert cf["sum_pnl"] == pa_net + pb_net
    assert cf["sum_tilt_pnl"] == pa_net * 0.75 + pb_net * 1.25
    assert cf["diff"] == (pa_net * 0.75 + pb_net * 1.25) - (pa_net + pb_net)


def test_chronos_prefers_c2_mult(tmp_path):
    T = "2026-10-07 10:00:00+00:00"
    p = dip_pid(2, "BTCUSDT", 2.5, T)
    ledger = {p: {"symbol": "BTCUSDT", "side": 1, "qty": 0.0, "kind": "dip", "phase": 2}}
    links = dip_links(p, "BTCUSDT")
    t0, t1 = "2026-10-07 10:05:00+00:00", "2026-10-07 11:00:00+00:00"
    execs = [mk_exec(p + "E", 1.0, 100.0, t0), mk_exec(p + "T", 1.0, 110.0, t1)]
    curve = [("2026-10-07 10:00:00+00:00", 5000.0), ("2026-10-07 11:00:00+00:00", 5010.0)]
    twin = write_runner(tmp_path, "paper_d17bfg2", ledger, links, execs, curve=curve)
    run = write_runner(tmp_path, "paper_d17bfg2ch", {}, {}, [], curve=curve)
    fp = tmp_path / "c.parquet"
    write_feed(fp, [{"sym": "BTCUSDT", "shift": 2, "T": pd.Timestamp(T, tz="UTC"),
                     "c2_mult": 0.5, "k2_mult": 2.0,
                     "mode": "prospective", "is_prospective": True}])
    res = fm.evaluate("chronos", run, twin, fp, nocorr(tmp_path), boot=50, seed=0)
    assert res["mult_col"] == "c2_mult"
    cf = res["counterfactual"]
    assert cf["mean_mult"] == 0.5
    net = 10.0 - (100.0 * 0.0002 + 110.0 * 0.0002)
    assert cf["sum_tilt_pnl"] == net  # single piece normalises to itself


def test_common_uptime_restricts_realised(tmp_path):
    # Twin runs Oct 5->8, tilt runner Oct 7->8: a piece closed Oct 6 is in the
    # counterfactual (no window restriction there) but out of realised stats.
    T_old, T_new = "2026-10-05 10:00:00+00:00", "2026-10-07 10:00:00+00:00"
    po = dip_pid(2, "BTCUSDT", 2.5, T_old)
    pn = dip_pid(2, "BTCUSDT", 2.5, T_new)
    ledger = {po: {"symbol": "BTCUSDT", "side": 1, "qty": 0.0, "kind": "dip", "phase": 2},
              pn: {"symbol": "BTCUSDT", "side": 1, "qty": 0.0, "kind": "dip", "phase": 2}}
    links = {**dip_links(po, "BTCUSDT"), **dip_links(pn, "BTCUSDT")}
    execs = [mk_exec(po + "E", 1.0, 100.0, "2026-10-05 10:05:00+00:00"),
             mk_exec(po + "T", 1.0, 90.0, "2026-10-06 09:00:00+00:00"),  # loss, before window
             mk_exec(pn + "E", 1.0, 100.0, "2026-10-07 10:05:00+00:00"),
             mk_exec(pn + "T", 1.0, 110.0, "2026-10-07 11:00:00+00:00")]  # win, in window
    twin_curve = [("2026-10-05 10:00:00+00:00", 5000.0),
                  ("2026-10-06 10:00:00+00:00", 4990.0),
                  ("2026-10-07 10:00:00+00:00", 4990.0),
                  ("2026-10-08 10:00:00+00:00", 5020.0)]
    run_curve = [("2026-10-07 10:00:00+00:00", 5000.0),
                 ("2026-10-08 10:00:00+00:00", 5010.0)]
    twin = write_runner(tmp_path, "paper_d17bfg2", ledger, links, execs, curve=twin_curve)
    run = write_runner(tmp_path, "paper_d17bfg2k2", {}, {}, [], curve=run_curve)
    fp = tmp_path / "f.parquet"
    write_feed(fp, [
        {"sym": "BTCUSDT", "shift": 2, "T": pd.Timestamp(T_old, tz="UTC"),
         "k2_mult": 1.0, "mode": "prospective", "is_prospective": True},
        {"sym": "BTCUSDT", "shift": 2, "T": pd.Timestamp(T_new, tz="UTC"),
         "k2_mult": 1.0, "mode": "prospective", "is_prospective": True}])
    res = fm.evaluate("kronos", run, twin, fp, nocorr(tmp_path), boot=50, seed=0)
    assert res["common_uptime"]["start"] == "2026-10-07T10:00:00+00:00"
    assert res["common_uptime"]["end"] == "2026-10-08T10:00:00+00:00"
    tw = res["realised"]["twin"]
    assert tw["wr_dip"]["n"] == 1 and tw["wr_dip"]["wins"] == 1  # Oct-6 loss excluded
    assert tw["dip_fills"] == 1  # only the Oct-7 entry fill is in-window
    assert res["counterfactual"]["n_joined"] == 2  # counterfactual keeps both
    # twin return over the common window only: 4990 -> 5020
    assert tw["return_pct"] == 100.0 * (5020.0 - 4990.0) / 4990.0


def test_bootstrap_deterministic_and_small_sample_na(tmp_path):
    T1, T2 = "2026-10-01 10:00:00+00:00", "2026-10-07 10:00:00+00:00"
    ledger, links, execs, rows = {}, {}, [], []
    for i, T in enumerate((T1, T2)):
        p = dip_pid(2, "BTCUSDT", 2.5, T)
        ledger[p] = {"symbol": "BTCUSDT", "side": 1, "qty": 0.0, "kind": "dip", "phase": 2}
        links.update(dip_links(p, "BTCUSDT"))
        day = T[:10]
        execs += [mk_exec(p + "E", 1.0, 100.0, f"{day} 10:05:00+00:00"),
                  mk_exec(p + "T", 1.0, 110.0 + i, f"{day} 11:00:00+00:00")]
        rows.append({"sym": "BTCUSDT", "shift": 2, "T": pd.Timestamp(T, tz="UTC"),
                     "k2_mult": 0.75 if i == 0 else 1.25,
                     "mode": "prospective", "is_prospective": True})
    curve = [("2026-10-01 10:00:00+00:00", 5000.0), ("2026-10-07 11:00:00+00:00", 5020.0)]
    twin = write_runner(tmp_path, "paper_d17bfg2", ledger, links, execs, curve=curve)
    run = write_runner(tmp_path, "paper_d17bfg2k2", {}, {}, [], curve=curve)
    fp = tmp_path / "f.parquet"
    write_feed(fp, rows)
    r1 = fm.evaluate("kronos", run, twin, fp, nocorr(tmp_path), boot=200, seed=7)
    r2 = fm.evaluate("kronos", run, twin, fp, nocorr(tmp_path), boot=200, seed=7)
    b1, b2 = r1["bootstrap"], r2["bootstrap"]
    assert b1["status"] == "ok" and b1["n_weeks"] == 2
    assert (b1["mean"], b1["ci_lo"], b1["ci_hi"], b1["p_pos"]) == \
           (b2["mean"], b2["ci_lo"], b2["ci_hi"], b2["p_pos"])
    assert b1["ci_lo"] <= b1["mean"] <= b1["ci_hi"]
    # single joined week -> n/a, not a crash
    fp1 = tmp_path / "f1.parquet"
    write_feed(fp1, [rows[0]])
    r3 = fm.evaluate("kronos", run, twin, fp1, nocorr(tmp_path), boot=200, seed=7)
    assert r3["bootstrap"]["status"].startswith("n/a")


def test_quality_counters(tmp_path):
    curve = [("2026-10-07 10:00:00+00:00", 5000.0),
             ("2026-10-07 11:00:00+00:00", 5005.0),
             ("2026-10-07 14:00:00+00:00", 5002.0)]  # 3h outage gap
    actions = (
        [{"op": "k2_missing", "bar": "b1"},
         {"op": "k2_missing", "bar": "b2"},
         {"op": "k2_mult", "mult": 1.0}]
        + [{"op": "stale_plan", "generated_at": "2026-10-07T10:00:00+00:00",
            "t": "2026-10-07 10:05:00+00:00"}]
        + [{"op": "stale_plan", "generated_at": "2026-10-07T12:00:00+00:00",
            "t": "2026-10-07 12:05:00+00:00"}]
    )
    run = write_runner(tmp_path, "paper_d17bfg2k2", {}, {}, [], curve=curve, actions=actions)
    twin = write_runner(tmp_path, "paper_d17bfg2", {}, {}, [], curve=curve[:2])
    fp = tmp_path / "f.parquet"
    write_feed(fp, [])
    res = fm.evaluate("kronos", run, twin, fp, nocorr(tmp_path), boot=50, seed=0)
    q = res["quality"]["runner"]
    assert q["k2_missing_ops"] == 2
    assert q["k2_mult_ops"] == 1
    assert q["stale_plan_ops"] == 2
    assert q["stale_plan_versions"] == 2
    assert q["stale_span_hours"] == 2.0
    assert q["outage_gaps"] == 1
    assert q["outage_gap_hours"] == 3.0
    assert "outage gaps 1 (3.0h)" in fm.format_text(res)


def test_cli_smoke(tmp_path, capsys):
    curve = [("2026-10-07 10:00:00+00:00", 5000.0), ("2026-10-07 11:00:00+00:00", 5000.0)]
    run = write_runner(tmp_path, "paper_d17bfg2k2", {}, {}, [], curve=curve)
    twin = write_runner(tmp_path, "paper_d17bfg2", {}, {}, [], curve=curve)
    fp = tmp_path / "f.parquet"
    write_feed(fp, [])
    out = tmp_path / "out.json"
    rc = fm.main(["--feed", "kronos", "--runner", str(run), "--twin", str(twin),
                  "--feed-path", str(fp), "--corrections", str(nocorr(tmp_path)),
                  "--boot", "20", "--json", str(out)])
    assert rc == 0
    assert json.loads(out.read_text(encoding="utf-8"))["feed"] == "kronos"
    assert "common uptime" in capsys.readouterr().out
