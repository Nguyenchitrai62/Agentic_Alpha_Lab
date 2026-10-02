"""Restart/gap recovery without network access or writes to research artifacts."""

import importlib
import importlib.util
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from test_web_backend import backend
from agentic_alpha_lab.data.coverage import missing_ranges, require_closed_coverage

ROOT = Path(__file__).resolve().parents[1]


def script(name):
    spec = importlib.util.spec_from_file_location(name + "_gap_test", ROOT / "scripts" / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def freeze(monkeypatch, module, at):
    class Clock(datetime):
        current = pd.Timestamp(at).to_pydatetime()

        @classmethod
        def now(cls, tz=None):
            return cls.current if tz else cls.current.replace(tzinfo=None)

    monkeypatch.setattr(module, "datetime", Clock)
    return Clock


def test_gap_ranges_include_prefix_interior_tail_and_ignore_forming_bar():
    assert missing_ranges([20, 20, 40, 70], 0, 60, 10) == [(0, 10), (30, 30), (50, 60)]
    assert missing_ranges([], 0, 20, 10) == [(0, 20)]
    assert missing_ranges([], 20, 10, 10) == []
    with pytest.raises(ValueError, match="grid"):
        missing_ranges([11], 0, 20, 10)


def test_closed_coverage_rejects_missing_minute_but_not_future():
    start = pd.Timestamp("2026-10-02T00:00:00Z")
    frame = pd.DataFrame({"open_time": pd.date_range(start, periods=3, freq="min")})
    require_closed_coverage(frame, start, start + pd.Timedelta(minutes=3, seconds=20), "1min")
    with pytest.raises(RuntimeError, match="Missing closed"):
        require_closed_coverage(frame.drop(index=1), start, start + pd.Timedelta(minutes=3), "1min")


@pytest.mark.parametrize("interval", ["4h", "1h", "1d"])
def test_candles_repair_old_interior_and_tail_gaps(backend, monkeypatch, interval):
    _, db, _ = backend
    pipe = importlib.import_module("backend.pipeline")
    source = importlib.import_module("agentic_alpha_lab.data.binance_usdm")
    clock = freeze(monkeypatch, pipe, "2026-10-02T12:02:00Z")
    step = pipe.INTERVALS[interval]
    first = pipe._ms("2026-09-01T00:00:00Z")
    last = pipe._ms(clock.current) // step * step - step
    monkeypatch.setattr(pipe, "SYMS", ["BTCUSDT"])
    monkeypatch.setattr(pipe, "INTERVALS", {interval: step})
    monkeypatch.setattr(pipe, "HISTORY_START", {interval: "2026-09-01"})
    with db.write() as c:
        c.executemany("INSERT INTO candles VALUES(?,?,?,?,?,?,?,?)",
                      [("BTCUSDT", interval, t, 1, 2, .5, 1.5, 10) for t in (first, first + 2 * step, last - step)])
    fetched = []

    def fetch(sym, iv, start, end, **kwargs):
        a, b = pipe._ms(start), min(pipe._ms(end), last + step)
        fetched.append((a, b))
        return pd.DataFrame({"open_time": pd.to_datetime(list(range(a, b, step)), unit="ms", utc=True),
                             "open": 1, "high": 2, "low": .5, "close": 1.5, "volume": 10})

    monkeypatch.setattr(source, "fetch_klines", fetch)
    pipe.job_candles()
    assert [r["t"] for r in db.rows("SELECT t FROM candles ORDER BY t")] == list(range(first, last + step, step))
    assert db.kv_get("pipeline_candle_check")["status"] == "complete"
    assert any(b - a > 14 * 86400_000 for a, b in fetched)
    # A deletion at the start must still be found after its original boundary was persisted.
    with db.write() as c:
        c.execute("DELETE FROM candles WHERE t IN (?, ?)", (first, first + step))
    pipe.job_candles()
    assert db.one("SELECT MIN(t) AS t FROM candles")["t"] == first


def test_candles_cannot_claim_success_when_source_leaves_gaps(backend, monkeypatch):
    _, db, _ = backend
    pipe = importlib.import_module("backend.pipeline")
    source = importlib.import_module("agentic_alpha_lab.data.binance_usdm")
    freeze(monkeypatch, pipe, "2026-10-02T12:02:00Z")
    monkeypatch.setattr(pipe, "SYMS", ["BTCUSDT"])
    monkeypatch.setattr(pipe, "INTERVALS", {"4h": pipe.H4_MS})
    monkeypatch.setattr(pipe, "HISTORY_START", {"4h": "2026-10-02"})
    monkeypatch.setattr(source, "fetch_klines", lambda *a, **kw: pd.DataFrame({
        "open_time": [pd.Timestamp("2026-10-02T00:00:00Z")],
        "open": [1], "high": [2], "low": [.5], "close": [1.5], "volume": [10]}))
    with pytest.raises(RuntimeError, match="missing closed candles remain"):
        pipe.job_candles()
    assert not db.kv_get("pipeline_candle_check")


@pytest.mark.parametrize("failed", ["candles", "aggflow", "backfill", "shadow"])
def test_failed_prerequisite_blocks_plans_and_records_failure(backend, monkeypatch, failed):
    _, db, _ = backend
    pipe = importlib.import_module("backend.pipeline")
    calls = []
    names = ["candles", "aggflow", "backfill", "shadow", "trade_plan"]
    for name, attr in zip(names, ["job_candles", "job_aggflow", "job_backfill", "job_shadow_fast", "job_trade_plan"]):
        def run(name=name):
            calls.append(name)
            if name == failed:
                raise RuntimeError("source unavailable")
            return "ok"
        monkeypatch.setattr(pipe, attr, run)
    with pytest.raises(RuntimeError, match=failed):
        pipe.job_cycle()
    assert calls == names[:names.index(failed) + 1]
    assert db.kv_get("pipeline_input_check")["failed_step"] == failed


def test_periodic_refresh_checks_full_cycle_and_releases_lock(backend, monkeypatch):
    _, db, _ = backend
    pipe = importlib.import_module("backend.pipeline")
    calls = []
    for attr in ["job_candles", "job_aggflow", "job_backfill", "job_shadow_fast", "job_trade_plan"]:
        monkeypatch.setattr(pipe, attr, lambda attr=attr: calls.append(attr) or "ok")
    assert pipe.refresh_candles_quietly()
    assert calls == ["job_candles", "job_aggflow", "job_backfill", "job_shadow_fast", "job_trade_plan"]
    assert db.kv_get("pipeline_input_check")["status"] == "complete"
    monkeypatch.setattr(pipe, "job_candles", lambda: (_ for _ in ()).throw(RuntimeError("gap")))
    assert not pipe.refresh_candles_quietly()
    assert pipe._job_lock.acquire(blocking=False)
    try:
        assert not pipe.refresh_candles_quietly()
    finally:
        pipe._job_lock.release()


def test_backfill_and_flow_nonzero_exit_propagate(backend, monkeypatch):
    _, db, _ = backend
    pipe = importlib.import_module("backend.pipeline")
    calls = []
    def fail(cmd, **kw):
        calls.append(cmd)
        return SimpleNamespace(returncode=1, stderr="missing input", stdout="error")
    monkeypatch.setattr(pipe.subprocess, "run", fail)
    with pytest.raises(RuntimeError, match="backfill failed"):
        pipe.job_backfill()
    with pytest.raises(RuntimeError, match="aggflow incomplete"):
        pipe.job_aggflow()
    assert len(calls) == 4  # backfill, archive and both live feeds
    assert not db.kv_get("aggflow_archive_day")


@pytest.mark.parametrize("failure", ["stale", "history"])
def test_stale_or_unstored_plan_does_not_complete_but_other_four_run(backend, tmp_path, monkeypatch, failure):
    _, db, _ = backend
    pipe = importlib.import_module("backend.pipeline")
    history = importlib.import_module("backend.history_tm")
    folder = tmp_path / "artifacts/research/advisor_shadow"
    folder.mkdir(parents=True)
    slot = db.now_ms() // pipe.H4_MS * pipe.H4_MS
    for name in pipe.catalog.PIPELINES:
        t = slot - pipe.H4_MS if name == "v301" and failure == "stale" else slot
        (folder / f"trade_plan_{name}.json").write_text(json.dumps({
            "decision_bar": str(pd.Timestamp(t, unit="ms", tz="UTC")), "coins": {}, "net_return_pct": 0, "bars": []}))
    monkeypatch.setattr(pipe, "ROOT", tmp_path)
    calls = []
    def run(cmd, **kw):
        calls.append(cmd[cmd.index("--candidate") + 1])
        return SimpleNamespace(returncode=0, stderr="")
    def store(name, *a):
        if name == "v301" and failure == "history":
            raise RuntimeError("history transaction failed")
    monkeypatch.setattr(pipe.subprocess, "run", run)
    monkeypatch.setattr(history, "store_paper", store)
    with pytest.raises(RuntimeError, match="v301"):
        pipe.job_trade_plan()
    assert len(calls) == len(pipe.catalog.PIPELINES)
    assert not db.kv_get("plan_status_v301") and not db.kv_get("trade_plan_v301")
    assert all(db.kv_get(f"plan_status_{p}")["completed_slot"] == slot for p in pipe.catalog.PIPELINES if p != "v301")
    assert pipe.plan_order(slot)[0] == "v301"


class StopScheduler(BaseException):
    pass


def test_startup_always_checks_and_resume_crossing_closes_runs_immediately(backend, monkeypatch):
    _, db, _ = backend
    server = importlib.import_module("backend.server")
    clock = freeze(monkeypatch, server, "2026-10-02T00:02:00Z")
    monkeypatch.setattr(db, "now_ms", lambda: int(clock.current.timestamp() * 1000))
    monkeypatch.setattr(server, "_keep_awake", lambda: None)
    monkeypatch.setattr(server, "_cycle_incomplete", lambda t: False)
    events = []
    def run(trigger):
        events.append(trigger)
        if len(events) > 1:
            raise StopScheduler()
    def sleep(seconds):
        assert events == ["startup"]  # inspection happened before the first wait
        clock.current += timedelta(hours=8)
    monkeypatch.setattr(server, "_run_cycle_until_done", run)
    monkeypatch.setattr(server.time, "sleep", sleep)
    with pytest.raises(StopScheduler):
        server._scheduler()
    assert events == ["startup", "scheduler"]


def test_startup_error_retries_instead_of_killing_scheduler(backend, monkeypatch):
    server = importlib.import_module("backend.server")
    monkeypatch.setattr(server, "_keep_awake", lambda: None)
    events = []
    def run(trigger):
        events.append(trigger)
        if len(events) == 1:
            raise RuntimeError("DB temporarily busy")
        raise StopScheduler()
    sleeps = []
    monkeypatch.setattr(server, "_run_cycle_until_done", run)
    monkeypatch.setattr(server.time, "sleep", sleeps.append)
    with pytest.raises(StopScheduler):
        server._scheduler()
    assert events == ["startup", "startup"] and sleeps == [60]


def test_due_cycle_requires_all_five_stored_plans(backend):
    _, db, _ = backend
    server = importlib.import_module("backend.server")
    slot = server.pipeline._ms("2026-10-02T08:00:00Z")
    assert server._due_slot(slot) == slot - server.pipeline.H4_MS
    now = slot + server.SETTINGS.schedule_offset_minutes * 60_000
    assert server._due_slot(now) == slot and server._cycle_incomplete(now)
    for name in server.catalog.PIPELINES:
        db.kv_set(f"plan_status_{name}", {"completed_slot": slot})
        db.kv_set(f"trade_plan_{name}", {"decision_bar": "present"})
    assert not server._cycle_incomplete(now)
    db.kv_set("trade_plan_v266", {})
    assert server._cycle_incomplete(now)


def shadow_fixture(monkeypatch, tmp_path, at="2026-10-25T00:02:00Z"):
    mod = script("advisor_shadow")
    monkeypatch.setattr(mod, "LOG", tmp_path / "shadow.jsonl")
    freeze(monkeypatch, mod, at)
    monkeypatch.setattr(mod, "FAST", (("fake_advisor", "v240_O1"),))
    return mod


def test_fresh_shadow_repairs_beyond_14_days_including_latest_and_is_idempotent(tmp_path, monkeypatch):
    mod = shadow_fixture(monkeypatch, tmp_path)
    calls = []
    def advise():
        t = os.environ["ADVISOR_ASOF"]
        calls.append(t)
        return {"candidate": "v240_O1", "decision_bar_close": t,
                "perp_weight": {"BTCUSDT": .1}, "spot_weight": {"BTCUSDT": 0}}
    monkeypatch.setattr(mod, "_member", lambda *a: SimpleNamespace(advise=advise))
    monkeypatch.setenv("ADVISOR_ASOF", "preserve-me")
    mod.LOG.write_text('{"partial":')
    assert mod.backfill() == 0
    rows = mod._read_rows()
    assert pd.Timestamp(rows[0]["decision_bar_close"]) == pd.Timestamp(mod.PAPER_STARTS["v240_O1"])
    assert pd.Timestamp(rows[-1]["decision_bar_close"]) == pd.Timestamp("2026-10-24T23:59:59.999Z")
    assert len(rows) > 14 * 6 and all(r["asof"] for r in rows)
    assert rows[0]["mode"] == "backfill" and rows[-1]["mode"] == "prospective"
    assert os.environ["ADVISOR_ASOF"] == "preserve-me"
    n = len(calls)
    assert mod.backfill() == 0 and len(calls) == n
    # The repaired log must also be consumable by the paper replay despite the partial line.
    forward = script("forward_v205")
    monkeypatch.setattr(forward, "ROOT", tmp_path)
    folder = tmp_path / "artifacts/research/advisor_shadow"
    folder.mkdir(parents=True)
    (folder / "shadow.jsonl").write_text(mod.LOG.read_text())
    assert len(forward.live_books("v240_O1")) == len(rows)


def test_failed_shadow_row_is_retried_and_not_counted_as_complete(tmp_path, monkeypatch):
    mod = shadow_fixture(monkeypatch, tmp_path, "2026-09-28T12:02:00Z")
    calls = []
    def advise():
        calls.append(os.environ["ADVISOR_ASOF"])
        if len(calls) == 1:
            raise RuntimeError("source temporarily missing")
        return {"candidate": "v240_O1", "decision_bar_close": os.environ["ADVISOR_ASOF"],
                "perp_weight": {}, "spot_weight": {}}
    monkeypatch.setattr(mod, "_member", lambda *a: SimpleNamespace(advise=advise))
    monkeypatch.delenv("ADVISOR_ASOF", raising=False)
    assert mod.backfill() == 1
    assert mod.backfill() == 0
    assert len(calls) == 3 and calls[-1] == calls[0]
    assert "ADVISOR_ASOF" not in os.environ


@pytest.mark.parametrize("alive", [True, False])
def test_shadow_lock_uses_process_liveness_not_age(tmp_path, monkeypatch, alive):
    mod = shadow_fixture(monkeypatch, tmp_path)
    lock = tmp_path / "run.lock"
    lock.write_text("12345")
    os.utime(lock, (1, 1))
    monkeypatch.setattr(mod, "_pid_alive", lambda pid: alive)
    calls = []
    monkeypatch.setattr(mod, "main", lambda: calls.append(True) or 0)
    assert mod._locked_main() == (3 if alive else 0)
    assert bool(calls) != alive and lock.exists() == alive


def test_pid_liveness_query_does_not_terminate_current_process():
    assert script("advisor_shadow")._pid_alive(os.getpid())


def test_flow_backlog_persists_cursor_and_fails_until_closed_data_is_reached(tmp_path, monkeypatch):
    mod = script("aggflow_live")
    monkeypatch.setattr(mod, "OUT", tmp_path)
    monkeypatch.setattr(mod, "MAX_CALLS", 1)
    closed = pd.Timestamp.now(tz="UTC").floor("4h")
    arch = pd.DataFrame(0.0, index=[closed - pd.Timedelta(hours=8)], columns=mod.COLS)
    monkeypatch.setattr(mod, "FLOW_CHECK_START", arch.index.min())
    monkeypatch.setattr(mod, "_archive", lambda *a: arch)
    old_ms = int((closed - pd.Timedelta(hours=4)).timestamp() * 1000)
    def trade(i, t):
        return {"a": i, "T": t, "p": "100", "q": "1", "m": False}
    batches = [[trade(10, old_ms)], [trade(i, old_ms + i) for i in range(10, 1010)],
               [trade(1010, int(closed.timestamp() * 1000) + 1)]]
    params = []
    class Session:
        def get(self, url, **kw):
            params.append(kw["params"])
            return SimpleNamespace(json=lambda: batches.pop(0), status_code=200, headers={}, raise_for_status=lambda: None)
    with pytest.raises(RuntimeError, match="backlog remains"):
        mod.update("BTCUSDT", Session())
    state = tmp_path / "live_state_BTCUSDT.json"
    assert json.loads(state.read_text())["closed_coverage_complete"] is False
    assert json.loads(state.read_text())["last_id"] == 1009
    mod.update("BTCUSDT", Session())
    assert params[-1]["fromId"] == 1010
    assert json.loads(state.read_text())["closed_coverage_complete"] is True


def test_short_rest_response_does_not_hide_missing_live_bars(tmp_path, monkeypatch):
    mod = script("aggflow_live")
    monkeypatch.setattr(mod, "OUT", tmp_path)
    closed = pd.Timestamp.now(tz="UTC").floor("4h")
    arch = pd.DataFrame(0.0, index=[closed - pd.Timedelta(hours=12)], columns=mod.COLS)
    monkeypatch.setattr(mod, "FLOW_CHECK_START", arch.index.min())
    monkeypatch.setattr(mod, "_archive", lambda *a: arch)
    old_ms = int((closed - pd.Timedelta(hours=8)).timestamp() * 1000)
    payload = [{"a": 10, "T": old_ms, "p": "100", "q": "1", "m": False}]
    session = SimpleNamespace(get=lambda *a, **kw: SimpleNamespace(json=lambda: payload, status_code=200,
                                                                  headers={}, raise_for_status=lambda: None))
    with pytest.raises(RuntimeError, match="backlog remains"):
        mod.update("BTCUSDT", session)
    assert json.loads((tmp_path / "live_state_BTCUSDT.json").read_text())["closed_coverage_complete"] is False


def test_refreshed_archive_replaces_cursor_from_old_downtime(tmp_path, monkeypatch):
    mod = script("aggflow_live")
    monkeypatch.setattr(mod, "OUT", tmp_path)
    closed = pd.Timestamp.now(tz="UTC").floor("4h")
    arch = pd.DataFrame(0.0, index=[closed - pd.Timedelta(hours=4)], columns=mod.COLS)
    monkeypatch.setattr(mod, "FLOW_CHECK_START", arch.index.min())
    monkeypatch.setattr(mod, "_archive", lambda *a: arch)
    state = tmp_path / "live_state_BTCUSDT.json"
    state.write_text(json.dumps({"last_id": 7, "updated_at": str(closed - pd.Timedelta(days=5))}))
    params = []
    class Session:
        def get(self, url, **kw):
            params.append(kw["params"])
            return SimpleNamespace(json=lambda: [])
    mod.update("BTCUSDT", Session())
    assert params[0]["startTime"] == int(closed.timestamp() * 1000)
    assert "fromId" not in params[0]


def test_flow_partial_cursor_rebuilds_from_archive_and_writes_atomically(tmp_path, monkeypatch):
    mod = script("aggflow_live")
    monkeypatch.setattr(mod, "OUT", tmp_path)
    closed = pd.Timestamp.now(tz="UTC").floor("4h")
    arch = pd.DataFrame(0.0, index=[closed - pd.Timedelta(hours=8)], columns=mod.COLS)
    monkeypatch.setattr(mod, "FLOW_CHECK_START", arch.index.min())
    monkeypatch.setattr(mod, "_archive", lambda *a: arch)
    state = tmp_path / "live_state_BTCUSDT.json"
    state.write_text('{"last_id":')
    ms = int((closed-pd.Timedelta(hours=4)).timestamp()*1000)
    payload = [{"a": 10, "T": ms, "p": "100", "q": "1", "m": False}]
    params = []
    def get(url, **kw):
        params.append(kw["params"])
        return SimpleNamespace(json=lambda: payload, status_code=200, headers={}, raise_for_status=lambda: None)
    mod.update("BTCUSDT", SimpleNamespace(get=get))
    assert params[0]["startTime"] == ms and params[1]["fromId"] == 10
    assert json.loads(state.read_text())["closed_coverage_complete"]
    before = state.read_text()
    def fail_dump(*a):
        raise RuntimeError("writer interrupted")
    monkeypatch.setattr(mod.json, "dump", fail_dump)
    with pytest.raises(RuntimeError, match="writer interrupted"):
        mod._save_state(state, {})
    assert state.read_text() == before and not list(tmp_path.glob("*.tmp"))


def test_old_research_flow_gaps_do_not_block_frozen_paper_window(tmp_path, monkeypatch):
    mod = script("aggflow_live")
    monkeypatch.setattr(mod, "OUT", tmp_path)
    closed = pd.Timestamp.now(tz="UTC").floor("4h")
    recent = pd.date_range(mod.FLOW_CHECK_START, closed - pd.Timedelta(hours=4), freq="4h")
    times = pd.DatetimeIndex([pd.Timestamp("2022-01-01", tz="UTC")]).append(recent)
    arch = pd.DataFrame(0.0, index=times, columns=mod.COLS)
    monkeypatch.setattr(mod, "_archive", lambda *a: arch)
    session = SimpleNamespace(get=lambda *a, **kw: SimpleNamespace(json=lambda: []))
    assert "no trades" in mod.update("BTCUSDT", session)


@pytest.mark.parametrize("empty", [True, False])
def test_flow_rejects_missing_archive_or_interior_gap(tmp_path, monkeypatch, empty):
    mod = script("aggflow_live")
    monkeypatch.setattr(mod, "OUT", tmp_path)
    arch = pd.DataFrame(columns=mod.COLS) if empty else pd.DataFrame(
        0.0, index=pd.to_datetime(["2026-09-28T00:00:00Z", "2026-09-28T08:00:00Z"]), columns=mod.COLS)
    monkeypatch.setattr(mod, "_archive", lambda *a: arch)
    with pytest.raises(RuntimeError, match="archive"):
        mod.update("BTCUSDT", SimpleNamespace())


def test_archive_refetches_missing_manifest_rows_without_doubling_flow(tmp_path, monkeypatch):
    mod = script("fetch_aggtrades_flow")
    monkeypatch.setattr(mod, "OUT", tmp_path)
    month = "data/futures/um/monthly/aggTrades/BTCUSDT/BTCUSDT-2026-09.zip"
    day = "data/futures/um/daily/aggTrades/BTCUSDT/BTCUSDT-2026-10-01.zip"
    times = pd.date_range("2026-09-01", "2026-10-01T20:00:00", freq="4h", tz="UTC")
    complete = pd.DataFrame({"buy_lt10k": 10.0}, index=times)
    broken = complete.drop(times[10])
    broken.to_parquet(tmp_path / "BTCUSDT_flow_4h.parquet")
    manifest = tmp_path / "manifest_BTCUSDT.json"
    manifest.write_text(json.dumps({"done": {"BTCUSDT": [month.rsplit("/", 1)[-1], day.rsplit("/", 1)[-1]]}}))
    monkeypatch.setattr(mod, "keys", lambda prefix: [month] if "monthly" in prefix else [day])
    downloads = []
    def fetch(url, **kw):
        downloads.append(url)
        return SimpleNamespace(read=lambda: b"fake-archive")
    monkeypatch.setattr(mod.urllib.request, "urlopen", fetch)
    monkeypatch.setattr(mod, "aggregate", lambda raw, store: complete.loc[complete.index.month == 9])
    mod.run("BTCUSDT")
    repaired = pd.read_parquet(tmp_path / "BTCUSDT_flow_4h.parquet")
    assert len(downloads) == 1 and month in downloads[0]
    assert repaired.equals(complete)
    mod.run("BTCUSDT")
    assert len(downloads) == 1
    assert not mod.source_complete(complete.drop(times[-1]), day)


@pytest.mark.parametrize("kind", ["coinbase", "spot"])
@pytest.mark.parametrize("partial", [False, True])
def test_coinbase_and_spot_repair_interior_and_long_tail_with_pagination(tmp_path, monkeypatch, kind, partial):
    mod = script("coinbase_spot_update")
    monkeypatch.setattr(mod, "CB", tmp_path)
    monkeypatch.setattr(mod, "SP", tmp_path)
    step = pd.Timedelta(hours=1 if kind == "coinbase" else 4)
    now = pd.Timestamp.now(tz="UTC").floor("h" if kind == "coinbase" else "4h")
    start = now - 1010 * step
    monkeypatch.setattr(mod, "CHECK_START", start)
    path = tmp_path / ("BTC-USD_1h.parquet" if kind == "coinbase" else "BTCUSDT_spot_4h.parquet")
    old = pd.DataFrame({"open_time": [start, start + 2 * step], "open": 1.0, "high": 2.0, "low": .5,
                        "close": 1.5, "volume": 10.0})
    old.to_parquet(path, index=False)
    calls = []
    class Session:
        def get(self, url, **kw):
            args = kw["params"]
            calls.append(args)
            if kind == "coinbase":
                times = pd.date_range(pd.Timestamp(args["start"]), pd.Timestamp(args["end"]), freq=step, inclusive="left")
                payload = [[int(t.timestamp()), .5, 2, 1, 1.5, 10] for t in times]
            else:
                a = pd.Timestamp(args["startTime"], unit="ms", tz="UTC")
                b = pd.Timestamp(args["endTime"] + 1, unit="ms", tz="UTC")
                times = pd.date_range(a, b, freq=step, inclusive="left")[:1000]
                payload = [[int(t.timestamp() * 1000), 1, 2, .5, 1.5, 10,
                            int((t + step).timestamp() * 1000) - 1, 10, 1, 5, 5, 0] for t in times]
            if partial:
                payload = []
            return SimpleNamespace(json=lambda: payload, raise_for_status=lambda: None)
    run = mod.update_coinbase if kind == "coinbase" else mod.update_spot
    if partial:
        with pytest.raises(RuntimeError, match="Missing closed"):
            run("BTC-USD" if kind == "coinbase" else "BTCUSDT", Session())
    else:
        run("BTC-USD" if kind == "coinbase" else "BTCUSDT", Session())
        repaired = pd.read_parquet(path)
        assert len(repaired) == 1010
        assert repaired.open_time.max() == now - step
        assert len(calls) >= 3
        calls.clear()
        assert run("BTC-USD" if kind == "coinbase" else "BTCUSDT", Session()) == 0
        assert not calls


@pytest.mark.parametrize("kind", ["coinbase", "spot"])
def test_old_coinbase_spot_research_holes_are_preserved(tmp_path, monkeypatch, kind):
    mod = script("coinbase_spot_update")
    monkeypatch.setattr(mod, "CB", tmp_path)
    monkeypatch.setattr(mod, "SP", tmp_path)
    step = pd.Timedelta(hours=1 if kind == "coinbase" else 4)
    now = pd.Timestamp.now(tz="UTC").floor("h" if kind == "coinbase" else "4h")
    times = pd.DatetimeIndex([pd.Timestamp("2020-01-01", tz="UTC")]).append(
        pd.date_range(mod.CHECK_START, now-step, freq=step))
    path = tmp_path / ("BTC-USD_1h.parquet" if kind == "coinbase" else "BTCUSDT_spot_4h.parquet")
    pd.DataFrame({"open_time": times, "open": 1., "high": 2., "low": .5, "close": 1.5, "volume": 10.}).to_parquet(path,index=False)
    run = mod.update_coinbase if kind == "coinbase" else mod.update_spot
    assert run("BTC-USD" if kind == "coinbase" else "BTCUSDT", SimpleNamespace()) == 0
    assert len(pd.read_parquet(path)) == len(times)
