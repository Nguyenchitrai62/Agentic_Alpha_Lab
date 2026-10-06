import importlib.util
from datetime import datetime, timezone
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "alert_watch", Path(__file__).resolve().parents[1] / "scripts" / "alert_watch.py")
aw = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(aw)

NOW = datetime(2026, 10, 6, 3, 0, 0, tzinfo=timezone.utc)


def healthy_rep():
    return {"unprotected": [], "qty_mismatch": [], "cycle_age_s": 10.0, "plan_age_h": 1.0}


def healthy_stop():
    return {"stops": {"dd": "OK", "month": "OK", "percentile": "OK"}}


def test_healthy_has_no_incidents():
    out = aw.extract_incidents("paper_d17bfg2", healthy_rep(), healthy_stop(), {}, False)
    assert out == []


def test_all_six_kinds_fire():
    rep = {"unprotected": ["b1(BTCUSDT:no-stop)"], "qty_mismatch": ["BTCUSDT|1:ledger=0.002 exch=0.001"],
           "cycle_age_s": 600.0, "plan_age_h": 5.0}
    stop = {"stops": {"dd": "STOP", "month": "OK", "percentile": "STOP"}}
    carry = {"BTC": {"unhedged_cycles": 3}, "ETH": {"unhedged_cycles": 1}}
    out = aw.extract_incidents("paper_d17bfg2c", rep, stop, carry, True, "plan age 5.0h")
    kinds = sorted(i["kind"] for i in out)
    assert kinds == ["carry_unhedged", "cycle_stale", "plan_stale", "qty_mismatch",
                     "stop_rule", "stop_rule", "unprotected"]
    keys = [i["key"] for i in out]
    assert len(set(keys)) == len(keys)  # key on dinh, duy nhat
    assert "paper_d17bfg2c:carry_unhedged:BTC" in keys
    assert "paper_d17bfg2c:stop:dd" in keys and "paper_d17bfg2c:stop:percentile" in keys


def test_watch_is_not_critical():
    stop = {"stops": {"dd": "WATCH", "month": "WATCH", "percentile": "WATCH"}}
    out = aw.extract_incidents("paper_d17bfg2", healthy_rep(), stop, {}, False)
    assert out == []
    carry = {"BTC": {"unhedged_cycles": 2}}  # dung nguong: chua incident
    assert aw.extract_incidents("r", healthy_rep(), healthy_stop(), carry, False) == []


def test_missing_cycle_is_stale():
    rep = dict(healthy_rep(), cycle_age_s=None)
    out = aw.extract_incidents("paper_d17bfg2", rep, healthy_stop(), {}, False)
    assert [i["kind"] for i in out] == ["cycle_stale"]


def test_dedup_no_repeat_toast_for_same_open_incident(tmp_path):
    rep = {"unprotected": ["b1(BTCUSDT:no-stop)"], "qty_mismatch": [],
           "cycle_age_s": 10.0, "plan_age_h": 1.0}
    incs = aw.extract_incidents("paper_d17bfg2", rep, healthy_stop(), {}, False)
    calls = []
    open_map: dict = {}
    log = tmp_path / "alerts.log"
    r1 = aw.poll_once(tmp_path, NOW, open_map, log_path=log,
                      notifier=lambda t, b: calls.append((t, b)),
                      collect_fn=lambda _r, _n: incs)
    assert len(r1["new"]) == 1 and len(calls) == 1
    r2 = aw.poll_once(tmp_path, NOW, open_map, log_path=log,
                      notifier=lambda t, b: calls.append((t, b)),
                      collect_fn=lambda _r, _n: incs)
    assert r2["new"] == [] and len(calls) == 1  # khong toast lap
    assert r2["resolved"] == []
    lines = log.read_text(encoding="utf-8").splitlines()
    assert sum("ALERT" in l for l in lines) == 1


def test_resolved_logged_when_incident_clears(tmp_path):
    bad = aw.extract_incidents("paper_d17bfg2",
                               {"unprotected": ["b1(BTCUSDT:no-stop)"],
                                "qty_mismatch": [], "cycle_age_s": 10.0, "plan_age_h": 1.0},
                               healthy_stop(), {}, False)
    good: list = []
    calls = []
    open_map: dict = {}
    log = tmp_path / "alerts.log"
    aw.poll_once(tmp_path, NOW, open_map, log_path=log,
                 notifier=lambda t, b: calls.append((t, b)),
                 collect_fn=lambda _r, _n: bad)
    r = aw.poll_once(tmp_path, NOW, open_map, log_path=log,
                     notifier=lambda t, b: calls.append((t, b)),
                     collect_fn=lambda _r, _n: good)
    assert len(r["resolved"]) == 1 and open_map == {}
    text = log.read_text(encoding="utf-8")
    assert "ALERT" in text and "RESOLVED" in text
    assert len(calls) == 1  # resolved khong toast


def test_new_incident_while_other_open_toasts_only_new(tmp_path):
    one = aw.extract_incidents("paper_d17bfg2", healthy_rep(), healthy_stop(), {}, False)
    two = aw.extract_incidents("paper_d17bfg2",
                               dict(healthy_rep(), cycle_age_s=900.0),
                               healthy_stop(), {}, False)
    assert len(two) == 1
    calls = []
    open_map: dict = {}
    log = tmp_path / "alerts.log"
    aw.poll_once(tmp_path, NOW, open_map, log_path=log,
                 notifier=lambda t, b: calls.append((t, b)),
                 collect_fn=lambda _r, _n: one)
    r = aw.poll_once(tmp_path, NOW, open_map, log_path=log,
                     notifier=lambda t, b: calls.append((t, b)),
                     collect_fn=lambda _r, _n: two)
    assert [i["key"] for i in r["new"]] == ["paper_d17bfg2:cycle_stale"]
    assert len(calls) == 1


def test_backend_down_fires_critical():
    out = aw.extract_incidents("paper_d17bfg2", healthy_rep(), healthy_stop(), {}, False,
                               backend_down=True, backend_detail="khong noi duoc")
    assert [i["kind"] for i in out] == ["backend_down"]
    assert out[0]["severity"] == "critical"
    assert out[0]["key"] == "backend:down"
    # poll_once toast 1 lan cho incident backend moi (fake collect)
    calls = []
    open_map: dict = {}
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        from pathlib import Path as _P
        log = _P(td) / "alerts.log"
        r = aw.poll_once(_P(td), NOW, open_map, log_path=log,
                         notifier=lambda t, b: calls.append((t, b)),
                         collect_fn=lambda _r, _n: out)
        assert len(r["new"]) == 1 and len(calls) == 1


def test_plan_warn_vs_stale_levels():
    warn = aw.extract_incidents("r", healthy_rep(), healthy_stop(), {}, False,
                                plan_warn=True, plan_warn_detail="plan cu 2.0h")
    assert [i["kind"] for i in warn] == ["plan_warn"]
    assert warn[0]["severity"] == "warning"
    stale = aw.extract_incidents("r", healthy_rep(), healthy_stop(), {}, True, "plan CU 5.0h")
    assert [i["kind"] for i in stale] == ["plan_stale"]
    assert stale[0]["severity"] == "critical"
    # stale uu tien hon warn (khong double-count)
    both = aw.extract_incidents("r", healthy_rep(), healthy_stop(), {}, True, "stale",
                                plan_warn=True, plan_warn_detail="warn")
    assert [i["kind"] for i in both] == ["plan_stale"]


def test_collect_incidents_reads_real_runner_dirs(tmp_path):
    import json
    t = NOW.isoformat()
    for runner in ("paper_d17bfg2", "paper_d17bfg2c"):
        d = tmp_path / "artifacts" / "bot" / runner
        d.mkdir(parents=True, exist_ok=True)
        (d / "actions.jsonl").write_text(json.dumps({"t": t, "mode": "paper", "op": "place"}) + "\n",
                                         encoding="utf-8")
        (d / "state.json").write_text(json.dumps({"ledger": {}, "links": {}}), encoding="utf-8")
        (d / "exchange.json").write_text(json.dumps({
            "cash": 5000.0, "equity0": 5000.0, "orders": {}, "pos": {}, "execs": [],
            "funding_paid": 0.0, "fees": 0.0,
            "equity_curve": [[t, 5000.0]]}), encoding="utf-8")
    p = tmp_path / "artifacts" / "research" / "advisor_shadow" / "trade_plan_v376.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"generated_at": t}), encoding="utf-8")
    out = aw.collect_incidents(tmp_path, NOW,
                               check_backend_fn=lambda: (False, "backend song (fake)"))
    assert out == []  # runner khoe + plan tuoi + backend ok -> khong incident


def test_collect_backend_down_and_state_stale(tmp_path):
    import json
    import os
    t = NOW.isoformat()
    d = tmp_path / "artifacts" / "bot" / "paper_d17bfg2"
    d.mkdir(parents=True, exist_ok=True)
    (d / "actions.jsonl").write_text("", encoding="utf-8")  # khong timestamp -> stale
    (d / "state.json").write_text(json.dumps({"ledger": {}, "links": {}}), encoding="utf-8")
    old = NOW.timestamp() - 600  # state.json cu 10 phut
    os.utime(d / "state.json", (old, old))
    os.utime(d / "actions.jsonl", (old, old))
    p = tmp_path / "artifacts" / "research" / "advisor_shadow" / "trade_plan_v376.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"generated_at": t}), encoding="utf-8")
    out = aw.collect_incidents(tmp_path, NOW,
                               check_backend_fn=lambda: (True, "khong noi duoc (fake)"),
                               runners=("paper_d17bfg2",))
    kinds = sorted(i["kind"] for i in out)
    assert "backend_down" in kinds  # (a) /health khong dap ung -> CRITICAL
    assert "cycle_stale" in kinds  # (c) state.json > 5 phut -> CRITICAL


def test_collect_plan_warn_and_stale(tmp_path):
    import json
    from datetime import timedelta
    for age_h, want in ((2.0, "plan_warn"), (5.0, "plan_stale")):
        t = (NOW - timedelta(hours=age_h)).isoformat()
        d = tmp_path / "artifacts" / "bot" / "paper_d17bfg2"
        d.mkdir(parents=True, exist_ok=True)
        (d / "actions.jsonl").write_text(json.dumps({"t": NOW.isoformat()}) + "\n", encoding="utf-8")
        (d / "state.json").write_text(json.dumps({"ledger": {}, "links": {}}), encoding="utf-8")
        p = tmp_path / "artifacts" / "research" / "advisor_shadow" / "trade_plan_v376.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"generated_at": t}), encoding="utf-8")
        out = aw.collect_incidents(tmp_path, NOW,
                                   check_backend_fn=lambda: (False, "ok (fake)"),
                                   runners=("paper_d17bfg2",))
        kinds = [i["kind"] for i in out]
        assert want in kinds, (age_h, kinds)  # (b) 1h15m WARNING / 4h30m CRITICAL


def test_once_prints_incident_list_and_exits(tmp_path, capsys):
    import json
    t = NOW.isoformat()
    d = tmp_path / "artifacts" / "bot" / "paper_d17bfg2"
    d.mkdir(parents=True, exist_ok=True)
    (d / "actions.jsonl").write_text(json.dumps({"t": t}) + "\n", encoding="utf-8")
    (d / "state.json").write_text(json.dumps({"ledger": {}, "links": {}}), encoding="utf-8")
    p = tmp_path / "artifacts" / "research" / "advisor_shadow" / "trade_plan_v376.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"generated_at": t}), encoding="utf-8")
    rc = aw.main(["--once", "--no-toast", "--root", str(tmp_path),
                  "--log", str(tmp_path / "alerts.log"), "paper_d17bfg2"])
    assert rc in (0, 2)  # 2 neu backend that dang tat, 0 neu backend dang song
    txt = capsys.readouterr().out.lower()
    assert "incident" in txt  # --once in danh sach incident hien tai roi thoat
