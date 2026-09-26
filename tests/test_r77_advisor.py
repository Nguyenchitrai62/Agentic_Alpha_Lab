"""R77 W1-RUNNER tests: shared fresh/replay interfaces, persistent state,
control independence, TP1-split execution, no-backdate, exactly-once.

Fast: a deterministic fake raw-decision provider drives AdvisorStrategy
directly (no model weights). The REAL-model path is exercised by the bounded
replay demo + fresh smoke (see runner artifacts), not here.
"""
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

import torch  # noqa: F401,E402  (torch truoc pandas: DLL load-order)
import opencode_r77_advisor_core as core  # noqa: E402

CONFIG = json.loads((ROOT / "configs/opencode_r77_advisor.json").read_text())
T0 = pd.Timestamp("2023-01-01T00:00:00Z")


# ------------------------------------------------------------ helpers ---
def flat_candles(n: int, patches: dict | None = None) -> pd.DataFrame:
    rows = []
    for i in range(n):
        o = T0 + pd.Timedelta(minutes=5 * i)
        rows.append({"open_time": o, "open": 100.0, "high": 100.2,
                     "low": 99.8, "close": 100.1, "volume": 10.0,
                     "close_time": o + pd.Timedelta(minutes=5)})
    if patches:
        for idx, patch in patches.items():
            rows[idx].update(patch)
    return pd.DataFrame(rows)


def fake_raw(bar_idx: int, close_time, action: str,
             entry: float = 100.0, stop: float = 95.0,
             tp1: float = 110.0, tp2: float = 120.0,
             holding: int = 2000, confirmed: bool = True) -> dict:
    geo = None
    if action in ("LONG", "SHORT"):
        s = 1 if action == "LONG" else -1
        geo = {"direction": s, "entry_limit": entry,
               "stop_loss": stop, "take_profit_1": tp1,
               "take_profit_2": tp2, "holding_bars": holding,
               "leverage": 1.0, "expected_net_percent": 1.0,
               "ohlc_fill_score": 0.9, "conditional_win_score": 0.8}
    voted = confirmed and action in ("LONG", "SHORT")
    return {"status": "READY_RAW", "bar_index": bar_idx,
            "decision_time": core._ts(close_time),
            "close": 100.0, "atr5": 1.0, "atr4": 1.0,
            "scores": {"selection_score_percent": 0.9,
                       "mean_fill_score": 0.9},
            "iso4_raw_action": action, "iso4_raw_geometry": geo,
            "per_map_action": {"isotonic_2": action, "isotonic_4": action,
                               "isotonic_all": action},
            "vote_majority": voted, "vote_confirmed": voted,
            "htf_last_close_lte_decision": {}, "device": "test"}


def fresh_strategy(n_bars=None):
    st = core.AdvisorStrategy(CONFIG, n_bars=n_bars)
    st._identity = st.identity_block(CONFIG, __import__(
        "opencode_r76_infer").load_prespec())
    return st


def drive(strategy, df, raw_by_bar, observed_at, skip_settled=False,
          idx_offset=0):
    """Runner-equivalent driver: optional watermark skip for overlaps."""
    for pos in range(len(df)):
        bar_idx = idx_offset + pos
        row = df.iloc[pos]
        if skip_settled and strategy.last_settled is not None and \
                core._ts(row["close_time"]) <= strategy.last_settled:
            continue
        bar = {"open_time": row["open_time"], "close_time": row["close_time"],
               "open": row["open"], "high": row["high"], "low": row["low"],
               "close": row["close"], "volume": row["volume"]}
        strategy.observe_bar(bar_idx, bar, raw_by_bar.get(bar_idx),
                             observed_at)


# ------------------------------------------------------------- tests ---
def test_statuses_distinct_and_timestamped():
    st = fresh_strategy()
    st.begin_observation("2022-12-31T00:00:00+00:00", "2023-01-01T00:00:00+00:00")
    df = flat_candles(3)
    obs = "2023-01-01T00:00:00+00:00"
    warm = {"status": "WARMUP", "reason": "short history"}
    r0 = st.observe_bar(0, df.iloc[0].to_dict(), warm, obs)
    r1 = st.observe_bar(1, df.iloc[1].to_dict(), None, obs)  # off grid
    raw_w = fake_raw(72, df.iloc[2]["close_time"], "WAIT")
    r2 = st.observe_bar(72, df.iloc[2].to_dict(), raw_w, obs)
    assert (r0["status"], r1["status"], r2["status"]) == (
        "WARMUP", "OFF_CLOCK", "WAIT")
    for r in (r0, r1, r2):
        assert r["observed_at"] == obs and "bar_time" in r
    assert st.counters["wait_rows"] == 1


def test_injected_confidence_refused():
    st = fresh_strategy()
    st.begin_observation("2022-12-31T00:00:00+00:00", "obs")
    df = flat_candles(1)
    raw = fake_raw(0, df.iloc[0]["close_time"], "LONG")
    raw["confidence"] = 1.0  # forbidden injection (Codex B3)
    with pytest.raises(ValueError, match="confidence"):
        st.observe_bar(0, df.iloc[0].to_dict(), raw, "obs")


def test_wait_stays_wait_never_mapped():
    st = fresh_strategy()
    st.begin_observation("2022-12-31T00:00:00+00:00", "obs")
    df = flat_candles(150)
    raws = {0: fake_raw(0, df.iloc[0]["close_time"], "WAIT"),
            72: fake_raw(72, df.iloc[72]["close_time"], "WAIT")}
    drive(st, df, raws, "obs")
    assert st.intents == {} and st.operating.exits == 0
    assert st.control.exits == 0
    actions = [d["action"] for d in st.decision_log]
    assert set(actions) == {"WAIT"}


def test_tp1_split_long_then_tp2():
    st = fresh_strategy()
    st.begin_observation("2022-12-31T00:00:00+00:00", "obs")
    patches = {
        1: {"low": 99.9, "open": 100.5},   # entry touch (suppressed targets)
        2: {"high": 101.5},                 # TP1 50%
        3: {"high": 102.5},                 # TP2 remainder
    }
    df = flat_candles(20, patches)
    raw = fake_raw(0, df.iloc[0]["close_time"], "LONG", entry=100.0,
                   stop=95.0, tp1=101.0, tp2=102.0, holding=2000)
    drive(st, df, {0: raw}, "obs")
    for acct in (st.operating, st.control):
        assert acct.exits == 1, acct.name
        assert acct.open is None and acct.pending is None
        assert len(acct.events) == 1
    ev = st.control.events[0]
    assert ev["fees"] > 0 and ev["gross"] > 0
    # TP1-split proof: engine partial events are journaled via intents path;
    # account-level exit carries full gross/fees; operating == control (1x).
    assert st.operating.events[0]["gross"] == pytest.approx(ev["gross"])
    assert any(i["portfolio"] == "iso4_only_1x"
               for i in st.intents.values())
    assert any(i["portfolio"] == "operating"
               for i in st.intents.values())


def test_tp1_split_short_then_stop():
    st = fresh_strategy()
    st.begin_observation("2022-12-31T00:00:00+00:00", "obs")
    patches = {
        1: {"high": 100.1, "open": 99.5},  # SHORT entry touch at 100
        2: {"low": 98.5},                   # TP1 50% (short target down)
        3: {"high": 106.0},                 # stop takes remainder (stop-first)
    }
    df = flat_candles(20, patches)
    raw = fake_raw(0, df.iloc[0]["close_time"], "SHORT", entry=100.0,
                   stop=105.0, tp1=99.0, tp2=98.0, holding=2000)
    drive(st, df, {0: raw}, "obs")
    assert st.control.exits == 1 and st.operating.exits == 1
    assert st.control.open is None


def test_stop_first_ambiguous_bar():
    st = fresh_strategy()
    st.begin_observation("2022-12-31T00:00:00+00:00", "obs")
    patches = {
        1: {"low": 99.9, "open": 100.5},
        2: {"low": 94.0, "high": 111.0},  # touches BOTH stop(95) and tp1(101)
    }
    df = flat_candles(20, patches)
    raw = fake_raw(0, df.iloc[0]["close_time"], "LONG", entry=100.0,
                   stop=95.0, tp1=101.0, tp2=102.0, holding=2000)
    drive(st, df, {0: raw}, "obs")
    assert st.control.exits == 1
    assert st.control.events[0]["gross"] < 0  # full remainder stopped


def test_timeout_exit():
    st = fresh_strategy()
    st.begin_observation("2022-12-31T00:00:00+00:00", "obs")
    df = flat_candles(20, {1: {"low": 99.9, "open": 100.5}})
    raw = fake_raw(0, df.iloc[0]["close_time"], "LONG", entry=100.0,
                   stop=50.0, tp1=200.0, tp2=300.0, holding=5)
    drive(st, df, {0: raw}, "obs")
    assert st.control.exits == 1
    assert st.control.events[0]["reason"] in ("time", "time_after_tp1")


def test_entry_expiry_cancel():
    st = fresh_strategy()
    st.begin_observation("2022-12-31T00:00:00+00:00", "obs")
    df = flat_candles(30)  # flat 100.2/99.8 never touches limit 50.0
    raw = fake_raw(0, df.iloc[0]["close_time"], "LONG", entry=50.0,
                   stop=40.0, tp1=60.0, tp2=70.0, holding=2000)
    drive(st, df, {0: raw}, "obs")
    assert st.control.pending is None and st.control.rejected == 1
    assert st.control.exits == 0


def _halt_scenario():
    """Frozen-policy scenario: D1 (Jan1) both lose 5% at bar 1440 (Jan6
    00:00) -> daily halt Jan6; D2 decision on that SAME bar is halt-blocked
    for operating while control arms and then loses 15% (bar 1560); D3
    (Jan11, bar 2880) proves guard sizing from strictly-prior control exits
    (DD_GUARD_0.5x). Cooldown 5d / cap 4 respected throughout."""
    patches = {
        1: {"low": 99.9, "open": 100.5},
        1440: {"open": 100.0, "low": 94.0, "high": 100.2},  # D1 stop
        1441: {"low": 99.9, "open": 100.5},                 # D2 ctrl entry
        1560: {"low": 84.0, "high": 100.2},                 # D2 ctrl stop -15%
        2881: {"low": 99.9, "open": 100.5},                 # D3 entry
        2882: {"high": 101.5},                              # D3 TP1
        2883: {"high": 102.5},                              # D3 TP2
    }
    df = flat_candles(2950, patches)
    raws = {
        0: fake_raw(0, df.iloc[0]["close_time"], "LONG", entry=100.0,
                    stop=95.0, tp1=110.0, tp2=120.0, holding=3000),
        1440: fake_raw(1440, df.iloc[1440]["close_time"], "LONG",
                       entry=100.0, stop=85.0, tp1=200.0, tp2=300.0,
                       holding=2000),
        2880: fake_raw(2880, df.iloc[2880]["close_time"], "LONG",
                       entry=100.0, stop=99.0, tp1=101.0, tp2=102.0,
                       holding=2000),
    }
    return df, raws


def test_control_independence_under_halt_and_guard_sizing():
    st = fresh_strategy()
    st.begin_observation("2022-12-31T00:00:00+00:00", "obs")
    df, raws = _halt_scenario()
    drive(st, df, raws, "obs")
    # Operating halted on the D2 bar (daily halt from the D1 stop exit).
    assert st.counters["operating_halted"] >= 1
    halts = [a for a in st.alerts.values()
             if a.get("kind") == "DAILY_LOSS_HALT"]
    assert len(halts) >= 1
    # Control STILL evolved while operating was halted: D2 control intent.
    ctrl_intents = [i for i in st.intents.values()
                    if i["portfolio"] == "iso4_only_1x"]
    op_intents = [i for i in st.intents.values()
                  if i["portfolio"] == "operating"]
    assert len(ctrl_intents) == 3  # D1, D2 (halted day), D3
    assert len(op_intents) == 2    # D1, D3 (D2 halt-blocked)
    # Guard sizing on D3 reads strictly-prior control exits -> DD_GUARD.
    d3 = [i for i in op_intents
          if i["signal_time"] == df.iloc[2880]["close_time"].isoformat()]
    assert len(d3) == 1
    assert d3[0]["guard_state"] == "DD_GUARD_0.5x"
    assert d3[0]["leverage"] == pytest.approx(0.5)
    d3_time = core._ts(d3[0]["signal_time"])
    assert st.guard._exits, "guard must read control exits"
    # Strictly-prior proof: the guard record written AT the D3 decision
    # reflects only control exits with exit_time < decision_time (later
    # exits, e.g. D3's own, must not leak into the sizing read).
    rec = [h for h in st.guard.history
           if h["signal_time"] == d3[0]["signal_time"]]
    assert len(rec) == 1 and rec[0]["state"] == "DD_GUARD_0.5x"
    prior = [(t, e) for t, e in st.guard._exits if t < d3_time]
    assert prior and max(t for t, _ in prior) < d3_time
    assert rec[0]["level"] == pytest.approx(prior[-1][1])
    assert rec[0]["peak"] == pytest.approx(
        max([100.0] + [e for _, e in prior]))
    # Control kept evolving after the halt: D2 loss then D3 win are realized.
    assert st.control.exits == 3
    assert st.control.equity != pytest.approx(100.0)


def test_resume_parity_after_kill():
    df, raws = _halt_scenario()
    full = fresh_strategy(n_bars=len(df))
    full.begin_observation("2022-12-31T00:00:00+00:00", "obs")
    drive(full, df, raws, "obs")
    snap_full = full.snapshot_state(full._identity)

    part = fresh_strategy(n_bars=len(df))
    part.begin_observation("2022-12-31T00:00:00+00:00", "obs")
    cut = 1500
    sub = df.iloc[:cut]
    drive(part, sub, {k: v for k, v in raws.items() if k < cut}, "obs")
    snap = part.snapshot_state(part._identity)

    cont = core.AdvisorStrategy(CONFIG, n_bars=len(df))
    ident = cont.identity_block(CONFIG, __import__(
        "opencode_r76_infer").load_prespec())
    cont.restore_state(json.loads(json.dumps(snap)), ident)
    cont._identity = ident
    for bar_idx in range(cut, len(df)):
        row = df.iloc[bar_idx]
        bar = {"open_time": row["open_time"], "close_time": row["close_time"],
               "open": row["open"], "high": row["high"], "low": row["low"],
               "close": row["close"], "volume": row["volume"]}
        cont.observe_bar(bar_idx, bar, raws.get(bar_idx), "obs")
    assert cont.intents == full.intents
    assert cont.alerts == full.alerts
    assert cont.fills == full.fills
    assert cont.decision_log == full.decision_log
    assert cont.counters == full.counters
    assert cont.operating.equity == pytest.approx(full.operating.equity)
    assert cont.control.equity == pytest.approx(full.control.equity)
    assert snap_full == cont.snapshot_state(cont._identity)


def test_overlapping_window_determinism():
    df, raws = _halt_scenario()
    ref = fresh_strategy(n_bars=len(df))
    ref.begin_observation("2022-12-31T00:00:00+00:00", "obs")
    drive(ref, df, raws, "obs")
    overlap = fresh_strategy(n_bars=len(df))
    overlap.begin_observation("2022-12-31T00:00:00+00:00", "obs")
    drive(overlap, df.iloc[:2000], raws, "obs")            # batch 1
    drive(overlap, df.iloc[1500:], raws, "obs",            # batch 2 overlaps
          skip_settled=True, idx_offset=1500)
    # driver-level watermark skip feeds bars 2000..; duplicate delivery of an
    # already-settled bar index is fail-closed:
    with pytest.raises(AssertionError):
        overlap.observe_bar(2000, df.iloc[2000].to_dict(), None, "obs")
    assert overlap.intents == ref.intents
    assert overlap.alerts == ref.alerts
    assert overlap.fills == ref.fills
    assert overlap.decision_log == ref.decision_log
    assert overlap.operating.equity == pytest.approx(ref.operating.equity)
    assert overlap.control.equity == pytest.approx(ref.control.equity)


def test_no_backdate_on_fresh_bootstrap():
    st = fresh_strategy()
    df, raws = _halt_scenario()
    latest = df["close_time"].iloc[-1].isoformat()
    st.begin_observation(latest, latest)  # bootstrap NOW: all older = past
    drive(st, df, raws, "obs")
    actionable = [d for d in st.decision_log
                  if d["status"] in ("READY_DECISION", "WAIT")]
    assert actionable == []
    assert st.intents == {}
    assert [a for a in st.alerts.values()
            if a.get("kind") not in ("DIVERGENCE_OVER_INFO",)] == []
    assert len(st.diagnostics) == 3  # all three past decisions diagnostic


def test_identity_change_rejected_on_resume():
    st = fresh_strategy()
    st.begin_observation("2022-12-31T00:00:00+00:00", "obs")
    df = flat_candles(10)
    drive(st, df, {}, "obs")
    snap = st.snapshot_state(st._identity)
    bad_config = dict(CONFIG)
    bad_config["execution"] = dict(CONFIG["execution"], tp1_fraction=0.75)
    bad = core.AdvisorStrategy(bad_config, n_bars=None)
    bad_ident = bad.identity_block(bad_config, __import__(
        "opencode_r76_infer").load_prespec())
    with pytest.raises(ValueError, match="config_sha256"):
        bad.restore_state(json.loads(json.dumps(snap)), bad_ident)


def test_frequency_gate_frozen_rule():
    gate = core.FrequencyGate(4, 5)
    t0 = pd.Timestamp("2023-01-01T00:00:00Z")
    ok, _ = gate.attempt(t0, True)
    assert ok
    ok, reason = gate.attempt(t0 + pd.Timedelta(hours=6), True)
    assert not ok and reason == "cooldown"
    ok, _ = gate.attempt(t0 + pd.Timedelta(days=5), True)
    assert ok
    snap = gate.snapshot()
    gate2 = core.FrequencyGate(4, 5)
    gate2.restore(snap)
    ok, reason = gate2.attempt(t0 + pd.Timedelta(days=6), True)
    assert not ok  # counters persist across restore


def test_on_grid_predicate_matches_prespec():
    assert core.on_grid(pd.Timestamp("2022-05-09T00:00:00Z"))
    assert core.on_grid(pd.Timestamp("2023-01-01T06:00:00Z"))
    assert not core.on_grid(pd.Timestamp("2023-01-01T00:05:00Z"))
    assert core.STRIDE_BARS == 72
