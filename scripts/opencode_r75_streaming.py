"""R75 streaming replay: clock-driven, sequential, past-only. RESEARCH/PAPER ONLY.

Reference policy: opencode_r75_confirmed_dd_guard (see configs/opencode_r75_policy.json).
Reuses the SAME interfaces as the batch reference driver:
  agentic_alpha_lab.data.swing.choose / grid  (feature/inference/policy per row)
  agentic_alpha_lab.backtest.engine run_backtest / CostModel / ExecutionConfig
  (portfolio accounting; stop-first ohlc-v2)
plus the v2 paper-trader replay pattern (walk closed bars, past-only prefix
``candles.iloc[:bar+1]``, snapshot/restore with fingerprint + horizon checks,
refuse-overwrite outputs).

Causality contract (fail-closed):
  - decisions are fed ONE at a time in strictly increasing bar order;
  - at decision time T only candles with close_time <= T are visible;
  - guard sizing reads only control-book exits strictly before T (1us cutoff);
  - no live orders, no network, no fitting/tuning.

No threshold/architecture/frequency/ensemble changes: frozen policy only.
"""

import argparse
import bisect
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

from agentic_alpha_lab.backtest.engine import CostModel, ExecutionConfig, run_backtest
from agentic_alpha_lab.data.swing import choose, grid

ROOT = Path(__file__).resolve().parents[1]
STATE_VERSION = "r75_stream_state/1"
MODE_LABEL = "R75-STREAM-PAPER"
ALERT_ID_SEP = "r75"

VOTE_CONFIRMED = "confirmed"
VOTE_ISO4_ONLY = "iso4_only"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def deterministic_id(*parts: str) -> str:
    body = ALERT_ID_SEP + "|" + "|".join(str(p) for p in parts)
    return "r75-" + hashlib.sha256(body.encode("utf-8")).hexdigest()[:16]


def dir_of(out: dict) -> int:
    if out.get("action") == "LONG":
        return 1
    if out.get("action") == "SHORT":
        return -1
    return 0


def load_policy(policy_path: Path | str) -> dict:
    policy = json.loads(Path(policy_path).read_text())
    for key, tagged in policy["source_shas"].items():
        expect, rel = tagged.split(":", 1)
        actual = sha256_file(ROOT / rel)
        if actual != expect:
            raise ValueError(
                f"policy source changed (refusing): {rel} "
                f"expected={expect[:12]}.. actual={actual[:12]}..")
    return policy


def load_inputs(policy: dict):
    ds = policy["dataset"]
    candles = pd.read_parquet(ROOT / ds["candles"])
    candles = candles.sort_values("open_time").reset_index(drop=True)
    decisions = pd.read_parquet(ROOT / ds["decisions"])
    ds_cfg = json.loads((ROOT / ds["config"]).read_text())
    preds = {}
    idx = None
    for m in ("isotonic_2", "isotonic_4", "isotonic_all"):
        rel = f"artifacts/research/opencode_v02_reproduce_v30/{m}/predictions.npz"
        with np.load(ROOT / rel) as z:
            preds[m] = z["prediction"]
            cur = z["decision_indices"]
        if idx is None:
            idx = cur
        elif not bool((idx == cur).all()):
            raise ValueError("decision_indices must match across maps")
    part = decisions.iloc[idx].reset_index(drop=True)
    if len(preds["isotonic_4"]) != len(part):
        raise ValueError("prediction rows must match decision subset rows")
    if preds["isotonic_4"].shape[1] != len(grid(ds_cfg)):
        raise ValueError("prediction width must match candidate grid")
    return candles, decisions, part, np.asarray(idx), preds, ds_cfg


def batch_control_reference(policy: dict, candles: pd.DataFrame,
                             ds_cfg: dict):
    """Frozen control inputs for the guard: iso4_only_1x signals + its book."""
    sig_path = ROOT / "artifacts/research/opencode_v15_mapensemble/iso4_only_1x/signals.parquet"
    control_signals = pd.read_parquet(sig_path)
    costs = CostModel(**ds_cfg["costs"])
    cap = int(max(ds_cfg["holding_days"]) * 288)
    execution = ExecutionConfig(entry_expiry_bars=ds_cfg["entry_expiry_bars"],
                                max_holding_bars=cap, leverage=1.0, max_leverage=1.0)
    _, control_trades = run_backtest(candles, control_signals, 100, costs, execution)
    exits = sorted((pd.Timestamp(t.exit_time), float(t.equity_after)) for t in control_trades)
    return control_signals, exits


class R75StreamReplay:
    """Sequential clock-driven replayer over frozen decision rows."""

    def __init__(self, policy: dict, candles: pd.DataFrame, part: pd.DataFrame,
                 preds: dict, ds_cfg: dict, control_exits,
                 vote: str = VOTE_CONFIRMED, n_bars: int | None = None,
                 sizing: str | None = None):
        if vote not in (VOTE_CONFIRMED, VOTE_ISO4_ONLY):
            raise ValueError("vote must be confirmed or iso4_only (frozen set)")
        # Sizing is part of the frozen policy, not a tuning knob: the reference
        # (confirmed_dd_guard) applies dd_guard; the control (iso4_only_1x) is 1x.
        self.sizing = sizing if sizing is not None else (
            "dd_guard" if vote == VOTE_CONFIRMED else "1x")
        if self.sizing not in ("1x", "dd_guard"):
            raise ValueError("sizing must be 1x or dd_guard (frozen set)")
        self.policy = policy
        self.candles = candles
        self.part = part.reset_index(drop=True)
        self.preds = preds
        self.ds_cfg = ds_cfg
        self.vote = vote
        self.n_bars = n_bars if n_bars is not None else len(candles)
        self.close_times = pd.to_datetime(candles["close_time"], utc=True)
        # Guard reference: sorted control exits (trade-candle-close sampled book).
        self._exit_times = [t for t, _ in control_exits]
        self._exit_equity = [e for _, e in control_exits]
        cap_days = int(ds_cfg["policy"]["cooldown_days"])
        self._cooldown = pd.Timedelta(days=cap_days)
        self._cap = int(ds_cfg["policy"]["maximum_signals_per_month"])
        # Mutable streaming state (the ONLY state a live loop would carry).
        self.monthly: Counter = Counter()
        self.next_allowed = pd.Timestamp.min.tz_localize("UTC")
        self.last_bar: int | None = None
        self.rows_seen = 0
        self.emitted: dict[int, dict] = {}
        self.decisions_log: list[dict] = []
        self.alerts: list[dict] = []
        self.missing_bars: list[int] = []

    # -- guard: incremental past-only lookup (binary search, 1us cutoff) ----
    def guard_leverage(self, signal_time: pd.Timestamp) -> tuple[float, str]:
        cutoff = pd.Timestamp(signal_time).tz_convert("UTC") - pd.Timedelta(microseconds=1)
        k = bisect.bisect_right(self._exit_times, cutoff)
        if k == 0:
            return 1.0, "FULL"
        curve = self._exit_equity[:k]
        peak = 100.0
        level = 100.0
        for eq in curve:
            peak = max(peak, eq)
            level = eq
        if level / peak < 1.0 - 0.10:
            return 0.5, "GUARD"
        return 1.0, "FULL"

    # -- one clock tick ----------------------------------------------------
    def on_decision(self, row_pos: int) -> dict | None:
        """Feed decision row ``row_pos`` (position inside the frozen subset).

        ``candles.iloc[:bar+1]`` is the only market data consulted, mirroring
        the v2 paper-trader ``on_bar(candles.iloc[:i+1])`` past-only pattern.
        """
        if row_pos != self.rows_seen:
            raise AssertionError(
                f"decisions must be fed sequentially without gaps/replays "
                f"(expected row {self.rows_seen}, got {row_pos})")
        row = self.part.iloc[row_pos]
        bar_idx = int(row["bar_index"])
        signal_time = pd.Timestamp(row["signal_time"])
        if signal_time.tzinfo is None:
            signal_time = signal_time.tz_localize("UTC")
        else:
            signal_time = signal_time.tz_convert("UTC")
        if self.last_bar is not None and bar_idx <= self.last_bar:
            raise ValueError(
                f"REFUSED out-of-order/duplicate/stale bar: bar {bar_idx} "
                f"after last_bar {self.last_bar} (exactly-once, increasing clock)")
        if bar_idx < 0 or bar_idx >= self.n_bars:
            raise ValueError(f"bar {bar_idx} outside horizon n_bars={self.n_bars}")
        # Closed-candle enforcement: the signal bar itself must be closed,
        # i.e. its close_time equals the decision time and nothing newer leaks.
        visible = self.candles.iloc[:bar_idx + 1]
        if len(visible) == 0 or visible.index[-1] != bar_idx:
            raise ValueError("candle frame must be a contiguous prefix ending at the signal bar")
        bar_close = pd.Timestamp(visible.iloc[-1]["close_time"])
        if bar_close.tzinfo is None:
            bar_close = bar_close.tz_localize("UTC")
        else:
            bar_close = bar_close.tz_convert("UTC")
        if bar_close != signal_time:
            raise ValueError(
                f"REFUSED unclosed/unknown signal bar: bar {bar_idx} closes {bar_close}, "
                f"decision time is {signal_time}")
        if pd.Timestamp(visible.iloc[-1]["open_time"]) >= signal_time:
            raise ValueError("signal bar must be fully closed before the decision")
        self.last_bar = bar_idx
        self.rows_seen += 1
        # SAME inference/policy interfaces as the batch driver (same-row only).
        o4 = choose(self.preds["isotonic_4"][row_pos], row["close"], row["atr5"],
                    row["atr4"], self.ds_cfg)
        oall = choose(self.preds["isotonic_all"][row_pos], row["close"], row["atr5"],
                      row["atr4"], self.ds_cfg)
        d4, dall = dir_of(o4), dir_of(oall)
        if self.vote == VOTE_CONFIRMED:
            vote_pass = d4 != 0 and dall == d4
        else:
            vote_pass = d4 != 0
        iso_out = None if o4.get("action") == "WAIT" else dict(o4)
        reason = "ok"
        if not vote_pass:
            reason = "vote_fail"
        elif iso_out is None:
            reason = "choose_wait"
        month = signal_time.strftime("%Y-%m")
        if reason == "ok" and (signal_time < self.next_allowed
                               or self.monthly[month] >= self._cap):
            reason = "cooldown" if signal_time < self.next_allowed else "monthly_cap"
        alert_id = deterministic_id("decision", bar_idx, signal_time.isoformat(), self.vote)
        entry = None
        if reason == "ok":
            if self.sizing == "1x":
                lev, gstate = 1.0, "NOT-APPLIED-1X"
            else:
                lev, gstate = self.guard_leverage(signal_time)
            sig = dict(iso_out)
            sig.pop("action", None)
            entry = {"bar_index": bar_idx, "signal_time": signal_time, **sig,
                     "leverage": float(lev), "guard_state": gstate,
                     "signal_id": deterministic_id("signal", bar_idx, d4,
                                                   signal_time.isoformat()),
                     "entry_start_bar": bar_idx + 1,
                     "entry_last_bar": min(bar_idx + int(sig.get("entry_expiry_bars", 12)),
                                           self.n_bars - 1)}
            self.emitted[bar_idx] = entry
            self.monthly[month] += 1
            self.next_allowed = signal_time + self._cooldown
        self.decisions_log.append({"row_pos": row_pos, "bar_index": bar_idx,
                                   "signal_time": signal_time.isoformat(),
                                   "d4": int(d4), "dall": int(dall),
                                   "vote_pass": bool(vote_pass), "reason": reason,
                                   "alert_id": alert_id,
                                   "emitted": entry is not None})
        self.alerts.append({"kind": "DECISION", "status": "EMITTED" if entry else "WAIT",
                            "alert_id": alert_id, "bar_idx": bar_idx,
                            "bar_time": signal_time.isoformat(), "reason": reason})
        return entry

    # -- snapshot / restore (restart + resume, v21-style checks) -------------
    def snapshot_state(self) -> dict:
        return {"version": STATE_VERSION, "mode": MODE_LABEL, "exploratory": True,
                "policy_id": self.policy["policy_id"], "vote": self.vote,
                "sizing": self.sizing,
                "source_shas": self.policy["source_shas"],
                "n_bars": self.n_bars, "n_decision_rows": int(len(self.part)),
                "last_bar": self.last_bar, "rows_seen": self.rows_seen,
                "monthly": dict(self.monthly),
                "next_allowed": self.next_allowed.isoformat(),
                "emitted_ids": [self.emitted[b]["signal_id"] for b in sorted(self.emitted)],
                "n_emitted": len(self.emitted),
                "n_decisions": len(self.decisions_log),
                "n_alerts": len(self.alerts),
                "decisions_log": self.decisions_log,
                "alerts": self.alerts}

    def save_state(self, path: Path | str) -> None:
        path = Path(path)
        if str(path.parent) not in ("", "."):
            path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(self.snapshot_state(), indent=1, default=str))
        tmp.replace(path)

    def restore_state(self, snap: dict) -> None:
        if snap.get("version") != STATE_VERSION:
            raise ValueError("state version mismatch (refusing)")
        if snap.get("mode") != MODE_LABEL:
            raise ValueError("state mode mismatch (refusing)")
        if snap.get("policy_id") != self.policy["policy_id"]:
            raise ValueError("policy mismatch on restore (refusing)")
        if snap.get("vote") != self.vote:
            raise ValueError("vote mismatch on restore (refusing)")
        if snap.get("sizing") != self.sizing:
            raise ValueError("sizing mismatch on restore (refusing)")
        if snap.get("source_shas") != self.policy["source_shas"]:
            raise ValueError("source fingerprint mismatch on restore (refusing)")
        if snap.get("n_bars") != self.n_bars:
            raise ValueError("horizon (n_bars) mismatch on restore (refusing)")
        if snap.get("n_decision_rows") != len(self.part):
            raise ValueError("decision-row count mismatch on restore (refusing)")
        self.last_bar = snap["last_bar"]
        self.rows_seen = int(snap["rows_seen"])
        self.monthly = Counter(snap["monthly"])
        self.next_allowed = pd.Timestamp(snap["next_allowed"])
        self.decisions_log = list(snap["decisions_log"])
        self.alerts = list(snap["alerts"])
        self.emitted = {}
        # Re-derive emitted rows deterministically is unnecessary: the log
        # already pins every decision; rebuild the emitted map from it.
        for rec in self.decisions_log:
            if rec["emitted"]:
                self._rebuild_emitted(rec)

    def _rebuild_emitted(self, rec: dict) -> None:
        row_pos = int(rec["row_pos"])
        row = self.part.iloc[row_pos]
        o4 = choose(self.preds["isotonic_4"][row_pos], row["close"], row["atr5"],
                    row["atr4"], self.ds_cfg)
        sig = dict(o4)
        sig.pop("action", None)
        signal_time = pd.Timestamp(rec["signal_time"])
        if self.sizing == "1x":
            lev, gstate = 1.0, "NOT-APPLIED-1X"
        else:
            lev, gstate = self.guard_leverage(signal_time)
        self.emitted[int(rec["bar_index"])] = {
            "bar_index": int(rec["bar_index"]), "signal_time": signal_time, **sig,
            "leverage": float(lev), "guard_state": gstate,
            "signal_id": deterministic_id("signal", int(rec["bar_index"]),
                                          int(rec["d4"]), signal_time.isoformat()),
            "entry_start_bar": int(rec["bar_index"]) + 1,
            "entry_last_bar": min(int(rec["bar_index"])
                                  + int(sig.get("entry_expiry_bars", 12)),
                                  self.n_bars - 1)}

    # -- outputs -------------------------------------------------------------
    def signals_frame(self) -> pd.DataFrame:
        if not self.emitted:
            return pd.DataFrame(columns=["bar_index", "direction", "signal_time"])
        rows = [self.emitted[b] for b in sorted(self.emitted)]
        frame = pd.DataFrame(rows)
        frame["signal_time"] = pd.to_datetime(frame["signal_time"], utc=True)
        return frame.sort_values("bar_index").reset_index(drop=True)

    def write_signals(self, path: Path | str) -> Path:
        path = Path(path)
        if path.exists():
            raise FileExistsError(f"Refusing to overwrite existing artifact: {path}")
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        self.signals_frame().to_parquet(tmp, index=False)
        tmp.replace(path)
        return path


def run_stream(policy: dict, candles: pd.DataFrame, part: pd.DataFrame,
               preds: dict, ds_cfg: dict, control_exits,
               vote: str = VOTE_CONFIRMED, end_row: int | None = None,
               start_row: int = 0, restore_from: dict | None = None,
               sizing: str | None = None):
    replay = R75StreamReplay(policy, candles, part, preds, ds_cfg, control_exits,
                             vote=vote, sizing=sizing)
    if restore_from is not None:
        replay.restore_state(restore_from)
        start_row = int(restore_from["rows_seen"])
    stop = len(part) if end_row is None else min(end_row, len(part))
    for pos in range(start_row, stop):
        replay.on_decision(pos)
    return replay.signals_frame(), replay


def main() -> None:
    ap = argparse.ArgumentParser(description="R75 clock-driven streaming replay (paper only).")
    ap.add_argument("--policy", default="configs/opencode_r75_policy.json")
    ap.add_argument("--vote", default=VOTE_CONFIRMED)
    ap.add_argument("--signals-out", type=Path, default=None)
    ap.add_argument("--log-out", type=Path, default=None)
    ap.add_argument("--snapshot", type=Path, default=None)
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--end-row", type=int, default=None)
    a = ap.parse_args()
    policy = load_policy(ROOT / a.policy)
    candles, decisions, part, didx, preds, ds_cfg = load_inputs(policy)
    _, control_exits = batch_control_reference(policy, candles, ds_cfg)
    snap = None
    if a.resume:
        if a.snapshot is None or not a.snapshot.exists():
            raise SystemExit("REFUSED: --resume needs an existing --snapshot file.")
        snap = json.loads(a.snapshot.read_text())
    signals, replay = run_stream(policy, candles, part, preds, ds_cfg, control_exits,
                                 vote=a.vote, end_row=a.end_row,
                                 restore_from=snap)
    print(f"[{MODE_LABEL}] vote={a.vote} rows={replay.rows_seen} "
          f"emitted={len(signals)} waits={len(replay.decisions_log) - len(signals)}", flush=True)
    if a.snapshot is not None and not (a.resume and a.snapshot.exists()):
        replay.save_state(a.snapshot)
    elif a.snapshot is not None:
        replay.save_state(a.snapshot)
    if a.signals_out is not None:
        replay.write_signals(ROOT / a.signals_out)
        print(f"[{MODE_LABEL}] wrote {a.signals_out} ({len(signals)} signals)", flush=True)
    if a.log_out is not None:
        out = ROOT / a.log_out
        if out.exists():
            raise FileExistsError(f"Refusing to overwrite existing artifact: {out}")
        out.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(replay.decisions_log).to_csv(out, index=False)


if __name__ == "__main__":
    main()