"""R80 Track-C: serving-path CLI acceptance (PASSES now; pins R79 fixes).

MOCK-mechanics only, explicitly labeled: synthetic candles (no network),
deterministic raw-inference fixtures (NOT model weights), controlled
observation clocks. Every run below goes through the ACTUAL serving path:
scripts/opencode_r78_roll.py main() (r79_roll/1) with the REAL
core.infer_full replaced ONLY at the inference-input edge; reconcile,
staleness/missed-clock, validity, execution, checkpoint and exports are the
real CLI code (no forked logic).

Covers: CLI smoke + --resume parity on the serving path, per-ingest
provenance on two shifted windows, stale/late-feed decision-vs-availability,
and the corrected R77 scope (fresh already uses observed_at at
scripts/opencode_r77_advisor.py:151,154 -- the real R77 issue is the REPLAY
backdate at :162-164 plus missing wrapper safeguards, hence research-only).
"""
import torch  # noqa: F401  (torch before pandas: Windows DLL load-order rule)

import json
import shutil
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import opencode_r77_advisor_core as core  # noqa: E402
import opencode_r78_roll as roll  # noqa: E402
import opencode_r76_infer as r76  # noqa: E402

ACC_DIR = Path("artifacts/research/opencode_r80/c_cli")
ROLL_CFG = json.loads((ROOT / "configs/opencode_r79_roll.json").read_text())
ADV_CFG = json.loads((ROOT / "configs/opencode_r77_advisor.json").read_text())
SPEC = r76.load_prespec()
LABEL = "MOCK-mechanics CLI acceptance (synthetic candles + raw fixture)"


def candles(n, start):
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


def mock_raw(close_time, action="LONG", entry=100.0):
    s = 1 if action == "LONG" else -1
    return {"status": "READY_RAW", "bar_index": -1,
            "decision_time": core._ts(close_time), "close": 100.1,
            "atr5": 1.0, "atr4": 1.0,
            "scores": {"selection_score_percent": 0.9,
                       "mean_fill_score": 0.9},
            "iso4_raw_action": action, "vote_majority": True,
            "vote_confirmed": True,
            "iso4_raw_geometry": {
                "direction": s, "entry_limit": entry, "stop_loss": 95.0,
                "take_profit_1": 110.0, "take_profit_2": 120.0,
                "holding_bars": 2000, "leverage": 1.0,
                "expected_net_percent": 1.0, "ohlc_fill_score": 0.9,
                "conditional_win_score": 0.8},
            "per_map_action": {}, "htf_last_close_lte_decision": {},
            "device": "test-mock-r80-cli", "MOCK": LABEL}


def fake_fixture(decision_idx, side="LONG", **geo_kw):
    def _fake(df, spec=None, device=None, max_decisions=None):
        df = df.sort_values("open_time").reset_index(drop=True)
        if decision_idx is None:
            return []
        close_t = pd.to_datetime(df["close_time"], utc=True).iloc[
            decision_idx]
        return [{**mock_raw(close_t, side, **geo_kw),
                 "bar_index": int(decision_idx)}]
    return _fake


def run_cli(monkeypatch, candles_path, out_rel, resume, fixture):
    """ACTUAL roll.main entry point; ONLY inference input is mocked."""
    import opencode_r78_roll as _roll_cli
    monkeypatch.setattr(core, "infer_full", fixture)
    argv = ["opencode_r78_roll.py", "--mode", "replay",
            "--config", "configs/opencode_r79_roll.json",
            "--candles", candles_path, "--out", out_rel]
    if resume:
        argv.append("--resume")
    old = sys.argv
    sys.argv = argv
    try:
        _roll_cli.main()
    finally:
        sys.argv = old
    return json.loads((ROOT / out_rel / "summary.json").read_text())


def recent_windows():
    now = pd.Timestamp.now(tz="UTC")
    end_close = now.floor("5min") - pd.Timedelta(minutes=10)
    start = end_close - pd.Timedelta(seconds=30 * 300)
    win_a = candles(30, start)
    extra = start + pd.Timedelta(seconds=30 * 300)
    last = {"open_time": extra, "open": 100.0, "high": 100.5, "low": 99.8,
            "close": 100.4, "volume": 10.0,
            "close_time": extra + pd.Timedelta(minutes=5)}
    win_b = pd.concat([win_a.iloc[1:].reset_index(drop=True),
                       pd.DataFrame([last])], ignore_index=True)
    win_b["open_time"] = pd.to_datetime(win_b["open_time"], utc=True)
    win_b["close_time"] = pd.to_datetime(win_b["close_time"], utc=True)
    return win_a, win_b


def ckpt_strategy(out_rel):
    out = ROOT / out_rel
    gen = int((out / "CURRENT").read_text().strip())
    return json.loads((out / f"checkpoint-{gen}.json").read_text())[
        "strategy"]


def write_windows():
    win_a, win_b = recent_windows()
    acc = ROOT / ACC_DIR
    acc.mkdir(parents=True, exist_ok=True)
    rel_a, rel_b = f"{ACC_DIR}/c_winA.parquet", f"{ACC_DIR}/c_winB.parquet"
    win_a.to_parquet(ROOT / rel_a, index=False)
    win_b.to_parquet(ROOT / rel_b, index=False)
    return rel_a, rel_b, win_a, win_b


def test_cli_smoke_and_restart_share_serving_path(monkeypatch):
    """Smoke + --resume through the real CLI: bootstrap stays
    diagnostic-only (zero actionable/fills/PnL), resume consumes only the
    new bar, provenance lineage links prev_sha. PASSES now."""
    rel_a, rel_b, _, _ = write_windows()
    out = f"{ACC_DIR}/c_smoke"
    shutil.rmtree(ROOT / out, ignore_errors=True)
    s1 = run_cli(monkeypatch, rel_a, out, False, fake_fixture(27, "LONG"))
    assert s1["actionable_count"] == 0
    assert s1["diagnostic_count"] > 0
    # Serving-path identity: summary version must equal the code under test
    # (Track A bumped r79_roll/1 -> r80_roll/1 mid-round; pin behavior, not
    # a stale literal).
    assert s1["roll_version"] == roll.ROLL_VERSION
    st = ckpt_strategy(out)
    assert st["intents"] == {} and st["fills"] == {}
    assert st["operating"]["equity"] == pytest.approx(100.0)
    snaps1 = sorted((ROOT / out).glob("raw_ingest_*.parquet"))
    assert len(snaps1) == 1
    s2 = run_cli(monkeypatch, rel_b, out, True, fake_fixture(27, "LONG"))
    snaps2 = sorted((ROOT / out).glob("raw_ingest_*.parquet"))
    assert len(snaps2) == 2  # resume never reuses the shared snapshot
    manifest = (ROOT / out / "ingest_manifest.jsonl").read_text(
        encoding="utf-8").splitlines()
    assert len(manifest) == 2
    m1, m2 = (json.loads(m) for m in manifest)
    assert m2["prev_sha256"] == m1["sha256"]
    assert m2["sha256"] == s2["raw_candle_artifact"]["sha256"]
    assert s2["counts"].get("duplicates", 0) >= 29  # overlap deduped


def test_cli_provenance_shifted_windows_exact(monkeypatch):
    """Per-ingest immutable snapshots: hash+range exact on 2 shifted
    windows; first snapshot bytes untouched by resume. PASSES now."""
    rel_a, rel_b, win_a, win_b = write_windows()
    out = f"{ACC_DIR}/c_prov"
    shutil.rmtree(ROOT / out, ignore_errors=True)
    s1 = run_cli(monkeypatch, rel_a, out, False, fake_fixture(27, "LONG"))
    snaps1 = sorted((ROOT / out).glob("raw_ingest_*.parquet"))
    h1 = roll.sha_file(snaps1[0])
    assert s1["raw_candle_artifact"]["sha256"] == h1
    assert s1["raw_candle_artifact"]["first_open"] == core._ts(
        win_a["open_time"].iloc[0]).isoformat()
    s2 = run_cli(monkeypatch, rel_b, out, True, fake_fixture(27, "LONG"))
    assert roll.sha_file(snaps1[0]) == h1
    new_snap = [p for p in sorted((ROOT / out).glob("raw_ingest_*.parquet"))
                if p != snaps1[0]][0]
    assert s2["raw_candle_artifact"]["sha256"] == roll.sha_file(new_snap)
    assert s2["raw_candle_artifact"]["sha256"] != h1
    assert s2["raw_candle_artifact"]["last_close"] == core._ts(
        win_b["close_time"].iloc[-1]).isoformat()


def test_stale_decision_is_diagnostic_only(monkeypatch):
    """A decision 25 bars (> stale_after 24) before observed_at is
    DIAGNOSTIC-only even on the latest bar: decision time without
    availability is not authorization. PASSES now."""
    now = pd.Timestamp.now(tz="UTC")
    end_close = now.floor("5min") - pd.Timedelta(minutes=10)
    win = candles(30, end_close - pd.Timedelta(seconds=30 * 300))
    acc = ROOT / ACC_DIR
    acc.mkdir(parents=True, exist_ok=True)
    rel = f"{ACC_DIR}/c_stale.parquet"
    win.to_parquet(ROOT / rel, index=False)
    out = f"{ACC_DIR}/c_stale"
    shutil.rmtree(ROOT / out, ignore_errors=True)

    def _old(df, spec=None, device=None, max_decisions=None):
        df = df.sort_values("open_time").reset_index(drop=True)
        close_t = pd.to_datetime(df["close_time"], utc=True).iloc[29]
        row = mock_raw(close_t, "LONG")
        # Backdate the decision 25 bars: stale even though it is latest.
        row["decision_time"] = core._ts(close_t) - pd.Timedelta(minutes=125)
        row["bar_index"] = 29
        return [row]

    s = run_cli(monkeypatch, rel, out, False, _old)
    assert s["actionable_count"] == 0
    assert s["counts"].get("stale_forced_diagnostic", 0) >= 1
    assert ckpt_strategy(out)["operating"]["equity"] == pytest.approx(100.0)


def test_r77_scope_corrected_fresh_ok_replay_research_only():
    """Corrected R77 scope (Codex correction): FRESH already anchors at the
    real fetch instant (observed_at = prov['fetched_at'], :151/:154) -- the
    old 'R77 main backdates' note overstated. The REAL R77 issues are the
    REPLAY shadow backdate (df['close_time'].iloc[0], :162-164) and the
    missing wrapper safeguards (missed-clock/gap-pause/revision guards live
    only in the roll wrapper). R77 CLI is research-only until routed through
    the supported interface (see c_supported_cli.md). PASSES now."""
    src = (ROOT / "scripts/opencode_r77_advisor.py").read_text()
    assert 'observed_at = prov["fetched_at"]' in src, \
        "R77 fresh must anchor observation at the fetch instant"
    assert 'df["close_time"].iloc[0]' in src, \
        "R77 replay backdate marker must still be documented"
    core_src = (ROOT / "scripts/opencode_r77_advisor_core.py").read_text()
    roll_src = (ROOT / "scripts/opencode_r78_roll.py").read_text()
    for marker in ("missed_clock_diagnostic", "gap-unresolved",
                   "revision_forced_diagnostic"):
        assert marker in roll_src, f"wrapper guard missing: {marker}"
        assert marker not in core_src, \
            f"safeguard unexpectedly in core (scope drift): {marker}"
    doc = ROOT / "artifacts/research/opencode_r80/c_supported_cli.md"
    assert doc.is_file(), "supported-CLI routing doc must exist"
    text = doc.read_text(encoding="utf-8")
    assert "opencode_r78_roll.py" in text and "research-only" in text
