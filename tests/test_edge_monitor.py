import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "edge_monitor", Path(__file__).resolve().parents[1] / "scripts" / "edge_monitor.py")
em = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(em)


def _ms(iso):
    t = datetime.fromisoformat(iso)
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    return str(int(t.timestamp() * 1000))


def write_runner(root, name="runner", months=None, exits=None, actions_extra=(),
                 use_execs=True):
    """months: [(iso_ts, eq)]; exits: [(link, kind, piece, iso)] (kind tp/stop/time)."""
    d = root / name
    d.mkdir(parents=True, exist_ok=True)
    months = months or []
    exits = exits or []
    links, ledger = {}, {}
    for link, kind, piece, _iso in exits:
        links[link] = {"order": {"link": link, "symbol": "BTCUSDT", "side": "Sell",
                                 "qty": 0.01, "kind": kind, "piece": piece,
                                 "meta": {"kind": "dip"}}}
        ledger.setdefault(piece, {"symbol": "BTCUSDT", "side": 1, "qty": 0.0,
                                  "kind": "dip"})
    for link, kind, piece, _iso in exits:
        if kind == "entry":
            continue
    execs = []
    if use_execs:
        for i, (link, _kind, _piece, iso) in enumerate(exits):
            execs.append({"execId": f"e{i}", "orderLinkId": link,
                          "execQty": "0.01", "execPrice": "80000",
                          "execTime": _ms(iso)})
    (d / "state.json").write_text(json.dumps({"ledger": ledger, "links": links}),
                                  encoding="utf-8")
    (d / "exchange.json").write_text(json.dumps(
        {"cash": 1000.0, "equity0": 1000.0, "orders": {}, "pos": {},
         "execs": execs, "fees": 0.0, "funding_paid": 0.0,
         "equity_curve": [[t, v] for t, v in months]}), encoding="utf-8")
    recs = []
    for link, kind, piece, iso in exits:
        if kind == "reduce":  # market exit can co ly do time/stop
            recs.append({"t": iso, "mode": "paper", "op": "market_exit",
                         "piece": piece, "reason": "time_exit",
                         "payload": {"orderLinkId": link, "symbol": "BTCUSDT"}})
    for r in actions_extra:
        recs.append(r)
    if not use_execs:
        for link, _kind, _piece, iso in exits:
            recs.append({"t": iso, "mode": "paper", "op": "fill",
                         "link": link, "qty": "0.01", "price": "80000"})
    with open(d / "actions.jsonl", "w", encoding="utf-8") as f:
        for r in recs:
            f.write(json.dumps(r) + "\n")
    return d


def healthy_months(start_eq=1000.0, ret=0.06, n=6):
    stamps = ["2026-04-30 12:00:00+00:00", "2026-05-31 12:00:00+00:00",
              "2026-06-30 12:00:00+00:00", "2026-07-31 12:00:00+00:00",
              "2026-08-31 12:00:00+00:00", "2026-09-15 12:00:00+00:00"]
    out, eq = [], start_eq
    for s in stamps[:n]:
        eq = eq * (1 + ret)
        out.append((s, round(eq, 4)))
    return out


def flat_months(n=6):
    return healthy_months(ret=0.0, n=n)


def dip_exits(n_tp, n_stop, n_time, day="2026-09-10 12:00:00+00:00"):
    out = []
    for i in range(n_tp):
        out.append((f"d{i:03d}T", "tp", f"d{i:03d}", day))
    for i in range(n_stop):
        out.append((f"s{i:03d}S", "stop", f"s{i:03d}", day))
    for i in range(n_time):
        out.append((f"x{i:03d}X{i:03d}", "reduce", f"x{i:03d}", day))
    return out


def test_not_enough_data_never_investigate(tmp_path):
    d = write_runner(tmp_path, months=[("2026-09-15 12:00:00+00:00", 1010.0)],
                     exits=dip_exits(3, 1, 1))
    rep = em.summarize_dir(d)
    assert rep["n_months"] < 2 and rep["tp_trail_n"] < 30
    assert rep["worst"] != "INVESTIGATE" and rep["exit"] == 0
    for line in rep["lines"]:
        assert "CHUA DU DU LIEU" in line and "INVESTIGATE" not in line


def test_healthy_ok(tmp_path):
    d = write_runner(tmp_path, months=healthy_months(), exits=dip_exits(25, 8, 7))
    rep = em.summarize_dir(d)
    assert rep["mean6"] is not None and rep["mean6"] > 5.0
    assert rep["tp_trail"] is not None and rep["tp_trail"] > 0.488
    assert rep["worst"] == "OK" and rep["exit"] == 0
    txt = "\n".join(rep["lines"])
    assert "1.61" in txt and "0.434" in txt and "OK" in txt


def test_trail6_crossing_investigate(tmp_path):
    d = write_runner(tmp_path, months=flat_months(), exits=dip_exits(25, 8, 7))
    rep = em.summarize_dir(d)
    assert rep["statuses"]["mean6"] == "INVESTIGATE"
    assert rep["exit"] == 2
    assert "INVESTIGATE" in rep["lines"][1] and "1.61" in rep["lines"][1]


def test_tp_crossing_investigate(tmp_path):
    d = write_runner(tmp_path, months=healthy_months(), exits=dip_exits(10, 15, 15))
    rep = em.summarize_dir(d)
    assert rep["tp_trail"] is not None and rep["tp_trail"] < 0.434
    assert rep["statuses"]["tp_trail"] == "INVESTIGATE"
    assert rep["exit"] == 2


def test_watch_bands(tmp_path):
    d = write_runner(tmp_path, months=healthy_months(ret=0.03),
                     exits=dip_exits(18, 12, 10))
    rep = em.summarize_dir(d)
    # mean ~3.0 nam giua p10 (1.61) va trung vi (5.44) -> WATCH
    assert rep["statuses"]["mean6"] == "WATCH"
    # tp 18/40 = 0.45 nam giua 0.434 va 0.488 -> WATCH
    assert rep["statuses"]["tp_trail"] == "WATCH"
    assert rep["exit"] == 1


def test_close5_stop_counts_as_stop_not_time(tmp_path):
    months = healthy_months()
    d = tmp_path / "r"
    d.mkdir()
    links = {
        "p1T": {"order": {"link": "p1T", "symbol": "BTCUSDT", "side": "Sell",
                          "qty": 0.01, "kind": "tp", "piece": "p1",
                          "meta": {"kind": "dip"}}},
        "p2X99": {"order": {"link": "p2X99", "symbol": "BTCUSDT", "side": "Sell",
                            "qty": 0.01, "kind": "reduce", "piece": "p2",
                            "meta": {"kind": "dip"}}},
        "p3X98": {"order": {"link": "p3X98", "symbol": "BTCUSDT", "side": "Sell",
                            "qty": 0.01, "kind": "reduce", "piece": "p3",
                            "meta": {"kind": "dip"}}},
    }
    ledger = {p: {"symbol": "BTCUSDT", "side": 1, "qty": 0.0, "kind": "dip"}
              for p in ("p1", "p2", "p3")}
    day = "2026-09-10 12:00:00+00:00"
    execs = [{"execId": "a", "orderLinkId": "p1T", "execQty": "0.01",
              "execPrice": "80000", "execTime": _ms(day)},
             {"execId": "b", "orderLinkId": "p2X99", "execQty": "0.01",
              "execPrice": "79000", "execTime": _ms(day)},
             {"execId": "c", "orderLinkId": "p3X98", "execQty": "0.01",
              "execPrice": "79000", "execTime": _ms(day)}]
    (d / "state.json").write_text(json.dumps({"ledger": ledger, "links": links}),
                                  encoding="utf-8")
    (d / "exchange.json").write_text(json.dumps(
        {"cash": 1000.0, "equity0": 1000.0, "orders": {}, "pos": {},
         "execs": execs, "fees": 0.0, "funding_paid": 0.0,
         "equity_curve": [[t, v] for t, v in months]}), encoding="utf-8")
    recs = [{"t": day, "mode": "paper", "op": "market_exit", "piece": "p2",
             "reason": "close5_stop", "payload": {"orderLinkId": "p2X99"}},
            {"t": day, "mode": "paper", "op": "market_exit", "piece": "p3",
             "reason": "time_exit", "payload": {"orderLinkId": "p3X98"}}]
    with open(d / "actions.jsonl", "w", encoding="utf-8") as f:
        for r in recs:
            f.write(json.dumps(r) + "\n")
    exits = em.dip_exits(json.loads((d / "state.json").read_text()),
                         json.loads((d / "exchange.json").read_text()),
                         recs)
    buckets = {link: b for _, b, link in exits}
    assert buckets == {"p1T": "tp", "p2X99": "stop", "p3X98": "time"}


def test_actions_fallback_without_exchange_execs(tmp_path):
    exits = dip_exits(20, 10, 10)
    d = write_runner(tmp_path, months=healthy_months(), exits=exits,
                     use_execs=False)
    rep = em.summarize_dir(d)
    assert rep["tp_all_n"] == 40  # dem tu actions.jsonl op=fill
    assert rep["statuses"]["tp_all"] == "OK"


def test_cli_lines_vietnamese_value_threshold_status(tmp_path, capsys):
    d = write_runner(tmp_path, months=healthy_months(), exits=dip_exits(25, 8, 7))
    assert em.main([str(d)]) == 0
    out = capsys.readouterr().out
    assert len([l for l in out.splitlines() if l.strip()]) == 4
    assert "1.61" in out and "0.434" in out
    assert "OK" in out
