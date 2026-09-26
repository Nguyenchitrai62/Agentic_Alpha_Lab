"""W3 acceptance harness (r78_accept/1): rolling/CLI, crash-recovery, stress.

PAPER ONLY, exploratory, no training/fitting/tuning, no live orders.
torch is imported before pandas (Windows DLL load-order rule).
"""
import torch  # noqa: F401  (torch truoc pandas: DLL load-order Windows host)

import copy
import json
import subprocess
import sys
from pathlib import Path

import pandas as pd

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
if str(_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(_ROOT / "scripts"))

import opencode_r76_feedexec as fx  # noqa: E402
import opencode_r77_advisor_core as core  # noqa: E402
from agentic_alpha_lab.backtest import engine as bt_engine  # noqa: E402

W3_DIR = _ROOT / "artifacts" / "research" / "opencode_r78_rolling" / "w3"
ACCEPT_VERSION = "r78_accept/1"
STRESS_ID = "r78-accept-adverse/1"
SLIP_BPS = 10
SLIP = SLIP_BPS / 10_000.0
FEE = 0.0002
T0 = pd.Timestamp("2023-01-01T00:00:00Z")


# ------------------------------------------------------- synthetic feed ---
def synth_candles(n: int, start: pd.Timestamp = T0,
                  patches: dict | None = None) -> pd.DataFrame:
    rows = []
    for i in range(n):
        o = start + pd.Timedelta(minutes=5 * i)
        rows.append({"open_time": o, "open": 100.0, "high": 100.2,
                     "low": 99.8, "close": 100.1, "volume": 10.0,
                     "close_time": o + pd.Timedelta(minutes=4,
                                                   seconds=59,
                                                   milliseconds=999)})
    if patches:
        for idx, patch in patches.items():
            rows[idx].update(patch)
    df = pd.DataFrame(rows)
    # CLI replay path validates the full source schema (quote_volume) and
    # the 5m grid; keep the synthetic feed conformant.
    df["quote_volume"] = df["volume"] * df["close"]
    return df


def write_parquet(df: pd.DataFrame, path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)
    import hashlib
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ------------------------------------------------------------- CLI driver ---
def run_r77_cli(candles_rel: str, out_rel: str,
                resume: bool = False) -> subprocess.CompletedProcess:
    cmd = [sys.executable, "scripts/opencode_r77_advisor.py",
           "--mode", "replay",
           "--config", "configs/opencode_r77_advisor.json",
           "--candles", candles_rel, "--out", out_rel]
    if resume:
        cmd.append("--resume")
    return subprocess.run(cmd, cwd=str(_ROOT), capture_output=True, text=True,
                          timeout=600)


def run_w1_cli(candles_rel: str, out_rel: str, resume: bool = False,
               extra: tuple = ()) -> subprocess.CompletedProcess:
    """W1 fixed rolling runner (read-only coordination: never edited here).
    --stub-infer keeps it deterministic without model weights; stub rows are
    settlement/recovery evidence only, never production inference."""
    cmd = [sys.executable, "scripts/opencode_r78_roll.py",
           "--mode", "replay",
           "--config", "configs/opencode_r78_roll.json",
           "--candles", candles_rel, "--out", out_rel, "--stub-infer",
           *extra]
    if resume:
        cmd.append("--resume")
    return subprocess.run(cmd, cwd=str(_ROOT), capture_output=True, text=True,
                          timeout=900)


def out_state(out: Path) -> dict:
    return json.loads((out / "state.json").read_text(encoding="utf-8"))


# ------------------------------------------------- adverse-fill scenario ---
def _adverse_wrap(fn, is_entry: bool):
    def inner(bar, direction, level):
        px = fn(bar, direction, level)
        if px is None:
            return None
        if direction == 1:
            return px * (1.0 + SLIP) if is_entry else px * (1.0 - SLIP)
        return px * (1.0 - SLIP) if is_entry else px * (1.0 + SLIP)
    return inner


class AdverseFills:
    """Monkeypatch bt_engine fill helpers so the INCREMENTAL FeedExecAccount
    path executes the versioned adverse scenario; batch counterpart runs
    pristine first. Restores on exit."""

    def __init__(self):
        self._orig = {}

    def __enter__(self):
        for name, is_entry in (("_entry_fill", True), ("_stop_fill", False),
                               ("_take_profit_fill", False),
                               ("_liquidation_fill", False)):
            self._orig[name] = getattr(bt_engine, name)
            setattr(bt_engine, name,
                    _adverse_wrap(self._orig[name], is_entry))
        return self

    def __exit__(self, *exc):
        for name, fn in self._orig.items():
            setattr(bt_engine, name, fn)
        return False


def stress_candles() -> pd.DataFrame:
    """Bounded scenario candles: LONG entry bar1, TP1 bar2, TP2 bar3."""
    base_ms = int(pd.Timestamp("2023-01-02 01:00", tz="UTC").value // 10 ** 6)

    def bar(i, o, h, lo, c):
        ms = base_ms + i * 300_000
        return {"open_time": pd.Timestamp(ms, unit="ms", tz="UTC"),
                "open": o, "high": h, "low": lo, "close": c, "volume": 10.0,
                "close_time": pd.Timestamp(ms + 299_999, unit="ms",
                                           tz="UTC")}
    return pd.DataFrame([
        bar(0, 100, 100, 100, 100),
        bar(1, 99, 101, 98, 100),
        bar(2, 100, 112, 99, 111),
        bar(3, 111, 121, 110, 120),
        bar(4, 120, 120, 119, 119),
        # trailing flat bars: keep entry+holding inside the batch horizon
        # (entry bar1 + holding 6 < 9 bars), exits already settled by bar3.
        bar(5, 119, 120, 118, 119),
        bar(6, 119, 120, 118, 119),
        bar(7, 119, 120, 118, 119),
        bar(8, 119, 120, 118, 119),
    ]).reset_index(drop=True)


def stress_signal(holding: int = 6) -> dict:
    return {"signal_bar": 0, "direction": 1, "entry_limit": 100.0,
            "stop_loss": 90.0, "take_profit_1": 110.0,
            "take_profit_2": 120.0, "holding_bars": holding,
            "leverage": 1.0, "notional": 100.0, "equity_before": 100.0}


def run_batch_reference(candles: pd.DataFrame, signal: dict) -> tuple:
    sig = pd.DataFrame([{"bar_index": signal["signal_bar"],
                         "direction": signal["direction"],
                         "entry_limit": signal["entry_limit"],
                         "stop_loss": signal["stop_loss"],
                         "take_profit_1": signal["take_profit_1"],
                         "take_profit_2": signal["take_profit_2"],
                         "holding_bars": signal["holding_bars"],
                         "leverage": signal["leverage"]}])
    return bt_engine.run_backtest(
        candles, sig, initial_equity=100.0, costs=bt_engine.CostModel(),
        execution=bt_engine.ExecutionConfig(
            entry_expiry_bars=12, max_holding_bars=2016,
            tp1_fraction=0.5, leverage=1.0, max_leverage=1.0))


def run_incremental(candles: pd.DataFrame, signal: dict,
                    adverse: bool = False, n_bars: int | None = None,
                    ) -> fx.FeedExecAccount:
    """Fresh open-ended settlement (n_bars=None: no truncation, matching the
    runner's fresh mode). Pass n_bars explicitly to exercise TRUNCATED."""
    cfg = json.loads((_ROOT / "configs/opencode_r76_feedexec.json")
                     .read_text(encoding="utf-8"))
    ac = fx.FeedExecAccount(100.0, cfg["costs"]["fee_rate_per_fill"],
                            cfg["costs"]["funding_long_rate"],
                            cfg["costs"]["funding_short_rate"],
                            cfg["costs"]["funding_interval_hours"],
                            cfg["execution"]["entry_expiry_bars"],
                            cfg["execution"]["tp1_fraction"], "w3")
    ctx = AdverseFills() if adverse else _NullCtx()
    with ctx:
        ac.on_bar_close(0, candles.iloc[0])
        ac.arm_pending(dict(signal))
        for i in range(1, len(candles)):
            ac.on_bar_close(i, candles.iloc[i], n_bars=n_bars)
    return ac


class _NullCtx:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


# --------------------------------------- integrated-runner continuation ---
def fake_raw(bar_idx: int, close_time, action: str,
             entry: float = 100.0, stop: float = 95.0,
             tp1: float = 110.0, tp2: float = 120.0,
             holding: int = 2000, confirmed: bool = True) -> dict:
    geo = None
    if action in ("LONG", "SHORT"):
        s = 1 if action == "LONG" else -1
        geo = {"direction": s, "entry_limit": entry, "stop_loss": stop,
               "take_profit_1": tp1, "take_profit_2": tp2,
               "holding_bars": holding, "leverage": 1.0,
               "expected_net_percent": 1.0, "ohlc_fill_score": 0.9,
               "conditional_win_score": 0.8}
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
    import opencode_r76_infer as r76
    cfg = json.loads((_ROOT / "configs/opencode_r77_advisor.json")
                     .read_text(encoding="utf-8"))
    st = core.AdvisorStrategy(cfg, n_bars=n_bars)
    st._identity = st.identity_block(cfg, r76.load_prespec())
    return st, cfg


def drive(strategy, df, raw_by_bar, observed_at="obs", idx_offset=0):
    for pos in range(len(df)):
        row = df.iloc[pos]
        bar = {"open_time": row["open_time"],
               "close_time": row["close_time"], "open": row["open"],
               "high": row["high"], "low": row["low"],
               "close": row["close"], "volume": row["volume"]}
        strategy.observe_bar(idx_offset + pos, bar,
                             raw_by_bar.get(idx_offset + pos), observed_at)


def snapshot_json(strategy) -> dict:
    return json.loads(json.dumps(strategy.snapshot_state(
        strategy._identity), default=str))


def restore_strategy(snap: dict, n_bars=None):
    import opencode_r76_infer as r76
    cfg = json.loads((_ROOT / "configs/opencode_r77_advisor.json")
                     .read_text(encoding="utf-8"))
    st = core.AdvisorStrategy(cfg, n_bars=n_bars)
    ident = st.identity_block(cfg, r76.load_prespec())
    st.restore_state(copy.deepcopy(snap), ident)
    st._identity = ident
    return st
