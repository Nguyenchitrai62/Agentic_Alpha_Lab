"""R79 Track-A: fresh-bootstrap observation-time regression.

Mechanical regression only: deterministic synthetic candles + stub-like raw
fixtures (MOCK-mechanics, explicitly NOT model inference) producing both LONG
and SHORT fill opportunities, on-grid and off-grid bootstraps.

CONFIRMED BUG (r78): scripts/opencode_r78_roll.py main() fresh path set
``shadow = df['close_time'].iloc[0]``, backdating observation so
pre-observation decisions settled actionable LONG/SHORT intents and filled
on historical bars (leader repro: observed_at 2026-09-10T07:10:01Z, shadow
05:55Z, LONG 06:05Z filled historically, equity 99.98 at bootstrap).

FIX (r79_roll/1): ``roll.fresh_shadow_start`` (the exact helper main uses)
returns the ACTUAL observed_at; ALL pre-observation inference is
diagnostic-only. Committed first as failing-before evidence against the
buggy line; now gates the fixed path (fails on reintroduction).
"""
import torch  # noqa: F401  (torch truoc pandas: DLL load-order Windows host)

import json
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import opencode_r77_advisor_core as core  # noqa: E402
import opencode_r78_roll as roll  # noqa: E402
import opencode_r76_infer as r76  # noqa: E402

SYM, INT = "BTCUSDT", "5m"
T0 = pd.Timestamp("2026-09-10T00:00:00Z")  # on-grid start (6h UTC grid)
ROLL_CFG = json.loads((ROOT / "configs/opencode_r79_roll.json").read_text())
ADV_CFG = json.loads((ROOT / "configs/opencode_r77_advisor.json").read_text())
SPEC = r76.load_prespec()

# MOCK-mechanics observed_at values (synthetic clock, no network):
OBS_ON_GRID = "2026-09-10T18:00:00+00:00"      # on-grid bootstrap instant
OBS_OFF_GRID = "2026-09-10T16:47:23+00:00"     # off-grid bootstrap instant


def candles(n=200, start=T0):
    rows = []
    for i in range(n):
        o = start + pd.Timedelta(minutes=5 * i)
        rows.append({"open_time": o, "open": 100.0, "high": 100.2,
                     "low": 99.8, "close": 100.1, "volume": 10.0,
                     "close_time": o + pd.Timedelta(minutes=5)})
    df = pd.DataFrame(rows)
    df["open_time"] = pd.to_datetime(df["open_time"], utc=True)
    df["close_time"] = pd.to_datetime(df["close_time"], utc=True)
    return df


def mock_raw(exec_idx, close_time, action):
    """MOCK-mechanics stub-like raw row (NOT model inference): fill-guaranteed
    geometry so a wrongly-actionable decision demonstrably fills."""
    s = 1 if action == "LONG" else -1
    entry = 100.0 if action == "LONG" else 100.1  # strictly inside the
    # synthetic bar range (99.8-100.2) so a wrongly-actionable MOCK fills.
    geo = {"direction": s, "entry_limit": entry, "stop_loss": 95.0,
           "take_profit_1": 110.0, "take_profit_2": 120.0,
           "holding_bars": 2000, "leverage": 1.0,
           "expected_net_percent": 1.0, "ohlc_fill_score": 0.9,
           "conditional_win_score": 0.8}
    return {"status": "READY_RAW", "bar_index": exec_idx,
            "decision_time": core._ts(close_time), "close": 100.1,
            "atr5": 1.0, "atr4": 1.0,
            "scores": {"selection_score_percent": 0.9,
                       "mean_fill_score": 0.9},
            "iso4_raw_action": action, "iso4_raw_geometry": geo,
            "per_map_action": {}, "vote_majority": True,
            "vote_confirmed": True,
            "htf_last_close_lte_decision": {}, "device": "test-mock"}


@pytest.fixture
def patched_identity(monkeypatch):
    def _collect(roll_cfg, advisor_cfg, spec):
        return [rel for rel in (
            "scripts/opencode_r77_advisor_core.py",
            "scripts/opencode_r77_advisor.py",
            "scripts/opencode_r78_roll.py",
            "configs/opencode_r77_advisor.json",
            "configs/opencode_r79_roll.json",
            "configs/opencode_r76_infer.json")
            if (ROOT / rel).exists()]
    monkeypatch.setattr(roll, "collect_identity_files", _collect)
    return _collect


def settle_fresh(out, df, observed_at, action, shadow):
    """Fresh-bootstrap settle helper: begin + reconcile + settle exactly as
    main() does (single observed_at for the whole bootstrap window)."""
    adv = roll.RollingAdvisor(ADV_CFG, ROLL_CFG, SPEC, out, SYM, INT)
    adv.begin(shadow, observed_at)
    rec = roll.reconcile_window(df, SYM, INT, observed_at, adv.exec_state)
    assert len(rec["new_rows"]) == len(df)
    target, target_row = rec["new_rows"][-2]
    raws = {target: mock_raw(target, target_row["close_time"], action)}
    for exec_idx, row in rec["new_rows"]:
        adv.settle_new([(exec_idx, row)],
                       {exec_idx: raws[exec_idx]} if exec_idx in raws else {},
                       observed_at)
    snap = adv.build_snapshot(
        core._ts(df["open_time"].iloc[0]).isoformat(),
        core._ts(df["close_time"].iloc[-1]).isoformat(), len(df),
        {"path": "mock", "sha256": "mock"}, observed_at,
        {"kind": "MOCK-bootstrap"}, {}, {"stub": True, "mock": True})
    return adv, snap


@pytest.mark.parametrize("action", ["LONG", "SHORT"])
@pytest.mark.parametrize("observed_at", [OBS_ON_GRID, OBS_OFF_GRID],
                         ids=["on-grid", "off-grid"])
def test_fresh_bootstrap_preobservation_diagnostic_only(
        action, observed_at, patched_identity, tmp_path):
    """The FIXED path: shadow comes from roll.fresh_shadow_start (the exact
    helper main() uses). Fails if the df.iloc[0] backdate is reintroduced."""
    df = candles()
    # Grid sanity: the window really contains grid bars.
    assert any(core.on_grid(r["open_time"]) for _, r in
               df.iterrows())
    shadow = roll.fresh_shadow_start(df, observed_at)
    assert shadow == core._ts(observed_at).isoformat()
    out = tmp_path / f"boot_{action}_{observed_at[11:13]}"
    adv, snap = settle_fresh(out, df, observed_at, action, shadow)
    assert snap["actionable_count"] == 0
    assert len(adv.strategy.intents) == 0
    assert len(adv.strategy.fills) == 0
    assert adv.strategy.counters["operating_admitted"] == 0
    assert adv.strategy.counters["control_admitted"] == 0
    assert adv.strategy.operating.equity == pytest.approx(100.0)
    assert adv.strategy.control.equity == pytest.approx(100.0)
    funding = sum(e.get("funding", 0.0) for e in
                  adv.strategy.operating.events)
    assert funding == pytest.approx(0.0)


@pytest.mark.parametrize("action", ["LONG", "SHORT"])
def test_buggy_shadow_mechanism_pinned(action, patched_identity, tmp_path):
    """Pins the r78 bug MECHANISM (not the product path): the old
    ``df['close_time'].iloc[0]`` shadow demonstrably settles an actionable
    intent + historical fill from a pre-observation bar. Documents why the
    backdate was wrong; the product path above must never do this."""
    df = candles()
    observed_at = OBS_OFF_GRID
    buggy_shadow = core._ts(df["close_time"].iloc[0]).isoformat()
    assert buggy_shadow != core._ts(observed_at).isoformat()
    adv, snap = settle_fresh(tmp_path / f"buggy_{action}", df,
                             observed_at, action, buggy_shadow)
    assert snap["actionable_count"] == 1
    assert len(adv.strategy.intents) == 2  # control + operating arms
    assert adv.strategy.operating.equity != pytest.approx(100.0)
