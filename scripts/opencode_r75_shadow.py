"""Runnable advisory shadow service (round75 track C). SIMULATED/PAPER ONLY.

EXPLORATORY (research plumbing, not a production bot). Read-only: no order
adapter, no exchange credentials, no external messaging, no schedules. The only
network call permitted is an unauthenticated public-klines GET in live-fetch
mode (fresh public observations); default mode replays a local fixture file.

Single command:
    .venv/Scripts/python.exe scripts/opencode_r75_shadow.py ^
        --config configs/opencode_r75_shadow.json ^
        --candles <fixture.parquet | live> --out <dir>
        [--start-bar INT] [--end-bar INT] [--resume] [--live-limit N]

Policy: the frozen reference policy from B's bundle
(artifacts/research/opencode_r75_practical/streaming/reference_policy.json) is
adopted IF present and valid; otherwise the runner falls back to its own frozen
documented policy pinned in the config chain (confirmed iso4-vote replay +
dd_guard sizing recomputed live, past-only). No weights are invented anywhere:
without a frozen signals file the run degrades to all-WAIT (CHECKPOINT_MISSING)
and never emits. Reuses v2.1 Strategy/Predictor/Guard/Account interfaces
without modifying v1/v2/v2.1 files.

Outputs per eligible decision bar: LONG/SHORT/WAIT + decision/observation time,
entry, stop, targets, expiry, policy/model identity, data freshness
(REHEARSAL-NOT-LIVE vs FRESH-OBSERVATION), and abstention reasons (incl. WAIT).
Logs ALL eligible decisions (incl. WAIT), alerts, simulated fills/cancels, and
portfolio state append-only, with a manifest + restart parity via --resume.

Safe WAIT/halt: missing/stale data, missing checkpoints, nonfinite outputs, and
risk limits (v2.1 daily-halt + one-sided divergence-trip on a window-rebased
frozen curve; rebase is a disclosed no-fit transform, see config).

Rehearsal proves functionality, NOT edge.
"""

import torch  # noqa: F401  (import order: torch before pandas on this host)

import argparse
import bisect
import hashlib
import json
import math
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import opencode_paper_trader as v1  # noqa: E402  (UNMODIFIED)
import opencode_paper_trader_v2 as v2  # noqa: E402  (UNMODIFIED)
import opencode_paper_trader_v21 as v21  # noqa: E402  (UNMODIFIED)

SHADOW_VERSION = "r75_shadow/1"
REHEARSAL_LABEL = "REHEARSAL-NOT-LIVE"
FRESH_LABEL = "FRESH-OBSERVATION"
REHEARSAL_DISCLAIMER = ("Rehearsal proves functionality, NOT edge. Fixture/replay "
                        "outcomes are historical plumbing exercises, never forward "
                        "validation and never expected future returns.")

REQUIRED_CANDLE_COLS = ["open_time", "open", "high", "low", "close", "volume", "close_time"]


# ---------------------------------------------------------------- live interlock
def _refuse_tokens(tokens: tuple[str, ...]) -> None:
    for token in sys.argv[1:]:
        if any(token == b or token.startswith(b + "=") for b in tokens):
            raise SystemExit(f"REFUSED: live-trading flag is not supported: {token} (paper only).")


# ---------------------------------------------------------------- public klines
def fetch_public_klines(symbol: str, interval: str, limit: int, base_url: str,
                        timeout: int, now=None, opener=None) -> tuple[pd.DataFrame, dict]:
    """GET public klines (no keys). Returns (closed-candles df, meta). Forming candle dropped."""
    now = now or datetime.now(timezone.utc)
    url = f"{base_url}/api/v3/klines?symbol={symbol}&interval={interval}&limit={int(limit)}"
    req = urllib.request.Request(url, headers={"User-Agent": "agentic-alpha-lab/research-shadow"})
    opener = opener or urllib.request.urlopen
    resp = opener(req, timeout=timeout)
    try:
        raw = resp.read()
    finally:
        try:
            resp.close()
        except Exception:
            pass
    rows = json.loads(raw)
    recs = []
    for r in rows:
        recs.append({"open_time": pd.Timestamp(int(r[0]), unit="ms", tz="UTC"),
                     "open": float(r[1]), "high": float(r[2]), "low": float(r[3]),
                     "close": float(r[4]), "volume": float(r[5]),
                     "close_time": pd.Timestamp(int(r[6]), unit="ms", tz="UTC")})
    df = pd.DataFrame(recs)
    n_raw = len(df)
    df = df[df["close_time"] <= pd.Timestamp(now)].reset_index(drop=True)  # drop forming candle
    meta = {"source": "public_klines_get", "url_host": base_url, "symbol": symbol,
            "interval": interval, "requested_limit": int(limit), "rows_raw": n_raw,
            "rows_closed": len(df), "fetched_at": pd.Timestamp(now).isoformat()}
    return df, meta


# ---------------------------------------------------------------- policy loading
def load_policy(config: dict, root: Path) -> dict:
    """Adopt B's bundle if present+valid, else own frozen chain. Never invent weights."""
    b_rel = config.get("shadow", {}).get(
        "b_bundle_path",
        "artifacts/research/opencode_r75_practical/streaming/reference_policy.json")
    b_path = root / b_rel
    if b_path.exists():
        try:
            bundle = json.loads(b_path.read_text())
            need = ("signals_parquet", "baseline_trades", "baseline_signals", "policy_id")
            if all(bundle.get(k) for k in need):
                cand = {k: root / bundle[k] for k in need if k != "policy_id"}
                if all(p.exists() for p in cand.values()):
                    sig = pd.read_parquet(cand["signals_parquet"])
                    v21.fingerprint_signals(sig)  # fail-closed on bad schema
                    return {"source": "B-BUNDLE", "policy_id": bundle["policy_id"],
                            "signals": sig, "signals_path": str(cand["signals_parquet"]),
                            "baseline_trades": str(cand["baseline_trades"]),
                            "baseline_signals": str(cand["baseline_signals"]),
                            "reason": f"adopted B bundle at {b_rel}"}
        except Exception as exc:  # corrupt bundle -> fall back, loudly
            return {"source": "OWN-FROZEN", "policy_id": config["shadow"]["policy_id"],
                    "signals": None, "fallback_note": f"B bundle unreadable ({exc}); OWN-FROZEN fallback",
                    "bundle_error": str(exc)}
        return {"source": "OWN-FROZEN", "policy_id": config["shadow"]["policy_id"],
                "signals": None,
                "fallback_note": "B bundle present but invalid/incomplete; OWN-FROZEN fallback"}
    chain = config["shadow"]["chain"]
    sig_path = root / chain["signals"]
    if not sig_path.exists():
        return {"source": "OWN-FROZEN", "policy_id": config["shadow"]["policy_id"],
                "signals": None, "signals_path": str(sig_path),
                "fallback_note": "frozen signals file missing -> CHECKPOINT_MISSING all-WAIT mode",
                "reason": ("B bundle absent (streaming/ has no reference_policy.json); "
                           "own frozen chain pinned but signals file missing")}
    sig = pd.read_parquet(sig_path)
    return {"source": "OWN-FROZEN", "policy_id": config["shadow"]["policy_id"],
            "signals": sig, "signals_path": str(sig_path),
            "baseline_trades": str(root / chain["baseline_trades"]),
            "baseline_signals": str(root / chain["baseline_signals"]),
            "reason": ("B bundle absent (streaming/ has no reference_policy.json as of run); "
                       "own frozen documented chain from config")}


def rebased_curve(baseline_trades: Path, start_bar_id: int, initial_equity: float) -> tuple[list, list, float]:
    """Rebase the frozen backtest equity path at the window start (disclosed, no fit)."""
    idx, eq = v2.load_expected_curve(baseline_trades, initial_equity)
    j = bisect.bisect_right(idx, int(start_bar_id))
    ref = float(eq[j - 1]) if j > 0 else float(initial_equity)
    ridx = [i for i in idx if i >= int(start_bar_id)]
    req = [e / ref * float(initial_equity) for i, e in zip(idx, eq) if i >= int(start_bar_id)]
    return ridx, req, ref


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------- decisions core
WAIT_REASONS = ("NO_SIGNAL", "LOW_CONFIDENCE", "BUSY_POSITION", "DAILY_HALT",
                "DIVERGENCE_LATCH", "DATA_GAP", "DATA_NONFINITE_OHLC", "STALE_FEED",
                "CHECKPOINT_MISSING", "PREDICTOR_ERROR", "NONFINITE_OUTPUT",
                "POLICY_GEOMETRY_INVALID", "UNKNOWN_WAIT")


def _finite_record(intent: dict) -> bool:
    try:
        for k in ("entry_limit", "tp", "sl", "size", "confidence", "leverage", "equity_before"):
            v = float(intent[k])
            if not math.isfinite(v):
                return False
        side = intent["side"]
        lo, hi = (intent["sl"], intent["tp"]) if side == "LONG" else (intent["tp"], intent["sl"])
        if side not in ("LONG", "SHORT"):
            return False
        return bool(lo < float(intent["entry_limit"]) < hi)
    except (KeyError, TypeError, ValueError):
        return False


def _infer_exit_reason(direction: int, entry_bar: int, bar_id: int, bar: pd.Series,
                       sl: float, tp: float, holding: int) -> str:
    """Mirror account close precedence (stop -> tp -> time); SIMULATED+INFERRED label."""
    hit_sl = float(bar["low"]) <= float(sl) if direction == 1 else float(bar["high"]) >= float(sl)
    if hit_sl:
        return "STOP"
    if int(bar_id) > int(entry_bar):
        hit_tp = float(bar["high"]) >= float(tp) if direction == 1 else float(bar["low"]) <= float(tp)
        if hit_tp:
            return "TARGET"
    if int(bar_id) >= int(entry_bar) + int(holding):
        return "TIMEOUT"
    return "EXIT_OTHER"


class ShadowRunner:
    def __init__(self, config: dict, policy: dict, candles: pd.DataFrame, freshness: str,
                 data_meta: dict, out_dir: Path, root: Path, start_bar_id=None, end_bar_id=None):
        self.config = config
        self.policy = policy
        self.df = candles
        self.freshness = freshness
        self.data_meta = data_meta
        self.out = out_dir
        self.root = root
        ids = list(self.df.index)
        if start_bar_id is None:
            start_bar_id = ids[0]
        if end_bar_id is None:
            end_bar_id = ids[-1]
        if start_bar_id not in set(ids) or end_bar_id not in set(ids):
            raise ValueError(f"window [{start_bar_id}, {end_bar_id}] outside data ids [{ids[0]}, {ids[-1]}]")
        if int(end_bar_id) < int(start_bar_id):
            raise ValueError("end-bar precedes start-bar (refusing).")
        self.start_id, self.end_id = int(start_bar_id), int(end_bar_id)
        self.pos0 = ids.index(self.start_id)
        self.pos1 = ids.index(self.end_id)
        self.min_conf = float(config["policy_geometry"]["min_confidence"])
        self.persist_every = int(config.get("state", {}).get("persist_every_n_bars", 50))
        self.strategy = None
        self.degraded_reason = None
        if policy.get("signals") is not None:
            predictor = v1.ReplayPredictor(policy["signals"])
            init_eq = float(config["account"]["initial_equity_indexed"])
            ridx, req, ref = rebased_curve(Path(policy["baseline_trades"] or
                                                config["divergence"]["baseline"]),
                                           self.start_id, init_eq)
            self.rebase = {"ref_baseline_equity": ref, "ref_bar": self.start_id,
                           "n_curve_points": len(ridx)}
            n_bars = (int(self.df.index.max()) + 1) if str(freshness) == REHEARSAL_LABEL else None
            self.n_bars = n_bars
            cfg = dict(config)
            if policy.get("source") == "B-BUNDLE":
                cfg = json.loads(json.dumps(config))
                cfg["divergence"] = dict(cfg["divergence"])
                cfg["divergence"]["baseline"] = policy["baseline_trades"]
                cfg["divergence"]["baseline_signals"] = policy["baseline_signals"]
            self.strategy = v21.PaperStrategyV21(predictor, cfg, expected_curve=(ridx, req),
                                                 n_bars=n_bars, root=root)
            self.signals_fp = v21.fingerprint_signals(policy["signals"])
        else:
            self.degraded_reason = policy.get("fallback_note", "CHECKPOINT_MISSING")
            self.rebase = None
            self.n_bars = None
            self.signals_fp = None
        self.n_flushed_alerts = 0
        self.active = None  # open-position geometry for exit inference
        self.counts = {"decisions": 0, "LONG": 0, "SHORT": 0, "WAIT": 0,
                       "intents": 0, "fills": 0, "cancels": 0, "exits": 0,
                       "halts": 0, "trips": 0}
        self.wait_reasons: dict[str, int] = {}
        self.exit_reasons: dict[str, int] = {}

    # -- logging ------------------------------------------------------------
    def _append(self, name: str, rec: dict) -> None:
        with open(self.out / name, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, default=str) + "\n")

    def _alert(self, bar_id, bar_time, kind, detail) -> None:
        self._append("alerts.jsonl", {"bar_id": bar_id, "bar_time": bar_time, "kind": kind,
                                      "detail": detail, "freshness": self.freshness,
                                      "label": "SIMULATED/PAPER-research-shadow"})

    def _drain_strategy_alerts(self) -> None:
        if self.strategy is None:
            return
        while self.n_flushed_alerts < len(self.strategy.alerts):
            ev = self.strategy.alerts[self.n_flushed_alerts]
            self.n_flushed_alerts += 1
            self._append("alerts.jsonl", {"strategy_alert": ev, "freshness": self.freshness,
                                          "label": "SIMULATED/PAPER-research-shadow"})
        if self.strategy.divergence.tripped:
            self.counts["trips"] = 1
        self.counts["halts"] = len(self.strategy.daily_halt.halt_events)

    # -- one bar -------------------------------------------------------------
    def _wait(self, bar_id, bar_time, reason, equity, extra=None) -> dict:
        rec = {"bar_id": int(bar_id), "decision_time": bar_time, "action": "WAIT",
               "entry": None, "stop": None, "targets": None, "expiry_bar": None,
               "confidence": None, "policy_id": self.policy.get("policy_id"),
               "policy_source": self.policy.get("source"),
               "model_identity": getattr(getattr(self.strategy, "predictor", None), "kind", None),
               "signals_fingerprint": self.signals_fp,
               "freshness": self.freshness, "reason": reason,
               "equity_after": equity, "label": "SIMULATED/PAPER-research-shadow"}
        if extra:
            rec.update(extra)
        self._append("decisions.jsonl", rec)
        self.counts["decisions"] += 1
        self.counts["WAIT"] += 1
        self.wait_reasons[reason] = self.wait_reasons.get(reason, 0) + 1
        return rec

    def _data_ok(self, pos: int, row: pd.Series) -> str | None:
        try:
            for k in ("open", "high", "low", "close", "volume"):
                v = float(row[k])
                if not math.isfinite(v):
                    return "DATA_NONFINITE_OHLC"
        except (KeyError, TypeError, ValueError):
            return "DATA_NONFINITE_OHLC"
        if pos > 0:
            prev = self.df.iloc[pos - 1]
            try:
                gap = (pd.Timestamp(row["open_time"]) - pd.Timestamp(prev["open_time"])).total_seconds()
            except Exception:
                return "DATA_GAP"
            expect = float(self.config["data"].get("expected_bar_seconds", 300))
            if abs(gap - expect) > 1e-6:
                return "DATA_GAP"
        return None

    def step(self, pos: int) -> dict:
        bar_id = int(self.df.index[pos])
        row = self.df.iloc[pos]
        try:
            bar_time = pd.Timestamp(row["close_time"]).isoformat()
        except Exception:
            bar_time = None
        equity_now = (self.strategy.account.equity if self.strategy is not None
                      else float(self.config["account"]["initial_equity_indexed"]))
        bad = self._data_ok(pos, row)
        if bad is not None:
            self._alert(bar_id, bar_time, "SHADOW_" + bad, "closed-candle row failed validation; WAIT")
            return self._wait(bar_id, bar_time, bad, equity_now)
        if self.strategy is None:
            if self.counts["decisions"] == 0:
                self._alert(bar_id, bar_time, "SHADOW_CHECKPOINT_MISSING", self.degraded_reason)
            return self._wait(bar_id, bar_time, "CHECKPOINT_MISSING", equity_now)
        frame = self.df.iloc[:pos + 1]
        try:
            pred = self.strategy.predictor.predict_proba(frame)
            action, conf = pred.get("action"), float(pred.get("confidence", float("nan")))
        except Exception as exc:
            self._alert(bar_id, bar_time, "SHADOW_PREDICTOR_ERROR", str(exc))
            return self._wait(bar_id, bar_time, "PREDICTOR_ERROR", equity_now)
        if pred.get("action") not in ("LONG", "SHORT", "FLAT") or not math.isfinite(conf):
            self._alert(bar_id, bar_time, "SHADOW_NONFINITE_OUTPUT",
                        f"predictor returned action={pred.get('action')} conf={pred.get('confidence')}")
            return self._wait(bar_id, bar_time, "NONFINITE_OUTPUT", equity_now)
        c0 = (self.strategy.signals_seen, self.strategy.skipped_low_conf, self.strategy.skipped_busy,
              self.strategy.skipped_daily_halt, self.strategy.skipped_divergence)
        before = {"pending": self.strategy.account.pending is not None,
                  "open": self.strategy.account.open is not None,
                  "exits": self.strategy.account.exits,
                  "guard_exits": len(self.strategy.guard._exits)}  # noqa: SLF001
        open_before = dict(self.strategy.account.open) if self.strategy.account.open else None
        pending_before = dict(self.strategy.account.pending) if self.strategy.account.pending else None
        intent = self.strategy.on_bar(frame)
        self._drain_strategy_alerts()
        self._track_fills(bar_id, bar_time, row, before, open_before, pending_before)
        if intent is None:
            c1 = (self.strategy.signals_seen, self.strategy.skipped_low_conf, self.strategy.skipped_busy,
                  self.strategy.skipped_daily_halt, self.strategy.skipped_divergence)
            if action == "FLAT":
                reason = "NO_SIGNAL"
            elif conf < self.min_conf:
                reason = "LOW_CONFIDENCE"
            elif c1[4] > c0[4]:
                reason = "DIVERGENCE_LATCH"
            elif c1[3] > c0[3]:
                reason = "DAILY_HALT"
            elif c1[2] > c0[2]:
                reason = "BUSY_POSITION"
            else:
                reason = "UNKNOWN_WAIT"
                self._alert(bar_id, bar_time, "SHADOW_UNKNOWN_WAIT",
                            f"no intent without a counted gate (action={action} conf={conf})")
            return self._wait(bar_id, bar_time, reason, self.strategy.account.equity,
                              {"confidence": conf})
        if not _finite_record(intent):
            self._alert(bar_id, bar_time, "SHADOW_POLICY_GEOMETRY_INVALID",
                        "nonfinite/ill-formed intent DISARMED (pending cleared); WAIT")
            self.strategy.intents.pop()
            self.strategy.account.pending = None
            return self._wait(bar_id, bar_time, "POLICY_GEOMETRY_INVALID",
                              self.strategy.account.equity)
        pend = self.strategy.account.pending or {}
        rec = {"bar_id": int(bar_id), "decision_time": bar_time,
               "action": ("LONG" if intent["side"] == "LONG" else "SHORT"),
               "entry": intent["entry_limit"], "stop": intent["sl"],
               "targets": [intent["tp"]], "expiry_bar": pend.get("entry_last_bar"),
               "confidence": intent["confidence"], "policy_id": self.policy.get("policy_id"),
               "policy_source": self.policy.get("source"),
               "model_identity": getattr(self.strategy.predictor, "kind", None),
               "signals_fingerprint": self.signals_fp,
               "freshness": self.freshness, "reason": "SIGNAL",
               "guard_state": intent.get("guard_state"),
               "equity_before": intent.get("equity_before"),
               "equity_after": self.strategy.account.equity,
               "label": "SIMULATED/PAPER-research-shadow"}
        self._append("decisions.jsonl", rec)
        self.counts["decisions"] += 1
        self.counts[rec["action"]] += 1
        self.counts["intents"] += 1
        return rec

    def _track_fills(self, bar_id, bar_time, row, before, open_before, pending_before) -> None:
        acc = self.strategy.account
        after = {"pending": acc.pending is not None, "open": acc.open is not None, "exits": acc.exits}
        base = {"bar_id": int(bar_id), "bar_time": bar_time, "freshness": self.freshness,
                "label": "SIMULATED/PAPER-research-shadow"}
        if not before["pending"] and after["pending"]:
            self._append("fills.jsonl", {**base, "event": "INTENT_ARMED",
                                         "signal_bar": acc.pending["signal_bar"],
                                         "direction": acc.pending["direction"],
                                         "entry_limit": acc.pending["entry_limit"],
                                         "expiry_bar": acc.pending["entry_last_bar"]})
        if before["pending"] and not after["pending"] and not after["open"] and after["exits"] == before["exits"]:
            if pending_before and after["exits"] == before["exits"]:
                # pending consumed by entry AND closed same bar is handled below; pure expiry:
                if open_before is None:
                    self.counts["cancels"] += 1
                    self._append("fills.jsonl", {**base, "event": "PENDING_EXPIRED",
                                                 "signal_bar": pending_before["signal_bar"],
                                                 "note": "simulated cancel: entry limit untouched within expiry"})
        if not before["open"] and after["open"]:
            self.counts["fills"] += 1
            o = acc.open
            self.active = {"entry_bar": o["entry_bar"], "direction": o["direction"],
                           "sl": o["stop_loss"], "tp": o["take_profit_2"],
                           "holding": o["holding_bars"]}
            self._append("fills.jsonl", {**base, "event": "ENTRY_FILL",
                                         "direction": o["direction"],
                                         "entry_bar": o["entry_bar"],
                                         "entry_price": o.get("entry_price"),
                                         "note": "simulated fill at limit-touch (conservative OHLC assumption)"})
        if after["exits"] > before["exits"] and open_before is not None:
            g = self.active or {"entry_bar": open_before.get("entry_bar", bar_id),
                                "direction": open_before.get("direction", 0),
                                "sl": open_before.get("stop_loss", float("nan")),
                                "tp": open_before.get("take_profit_2", float("nan")),
                                "holding": open_before.get("holding_bars", 0)}
            reason = _infer_exit_reason(g["direction"], g["entry_bar"], bar_id, row,
                                        g["sl"], g["tp"], g["holding"])
            self.counts["exits"] += 1
            self.exit_reasons[reason] = self.exit_reasons.get(reason, 0) + 1
            self.active = None
            self._append("fills.jsonl", {**base, "event": "POSITION_EXIT",
                                         "exit_reason_inferred": reason,
                                         "reason_note": "simulated+inferred (stop-first precedence); not a market record",
                                         "equity_after": acc.equity})
        if before["pending"] and not after["pending"] and after["open"] and after["exits"] == before["exits"]:
            pass  # pending -> open transition already logged as ENTRY_FILL


# ---------------------------------------------------------------- main
def main() -> None:
    _refuse_tokens((*v1.LIVE_ARGV_BLOCKLIST, *v2.EXTRA_LIVE_ARGV_BLOCKLIST,
                    *v21.EXTRA_V21_ARGV_BLOCKLIST))
    ap = argparse.ArgumentParser(description="Advisory shadow service (SIMULATED/PAPER ONLY).")
    ap.add_argument("--config", type=Path, default=Path("configs/opencode_r75_shadow.json"))
    ap.add_argument("--candles", type=str, required=True,
                    help="fixture parquet path OR the literal 'live' (public klines, no keys)")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--start-bar", type=int, default=None)
    ap.add_argument("--end-bar", type=int, default=None)
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--live-limit", type=int, default=None)
    ap.add_argument("--persist-every", type=int, default=None)
    a = ap.parse_args()
    root = Path(__file__).resolve().parents[1]
    config = json.loads((root / a.config).read_text())
    v21.assert_no_live_path_v21(config)
    if a.persist_every is not None:
        config.setdefault("state", {})["persist_every_n_bars"] = int(a.persist_every)
    live = (a.candles.strip().lower() == "live")
    if live and (a.resume or a.start_bar is not None or a.end_bar is not None):
        raise SystemExit("REFUSED: live observations are always a fresh fetch "
                         "(no --resume/--start-bar/--end-bar with live; never mixed with rehearsal).")
    if live:
        pc = config.get("public_klines", {})
        df, fetch_meta = fetch_public_klines(pc.get("symbol", "BTCUSDT"), pc.get("interval", "5m"),
                                             a.live_limit or pc.get("default_limit", 500),
                                             pc.get("host", "https://api.binance.com"),
                                             int(pc.get("timeout_seconds", 20)))
        if df.empty:
            raise SystemExit("REFUSED: live fetch returned no closed candles.")
        df = df.reset_index(drop=True)
        freshness = FRESH_LABEL
        data_meta = {"mode": "live_public_klines", "fetch": fetch_meta,
                     "last_close": pd.Timestamp(df["close_time"].iloc[-1]).isoformat()}
        banner = ("[FRESH-OBSERVATION] live public klines, no keys. "
                  "Fresh market data, NOT a rehearsal. Paper advisory only.")
    else:
        cpath = root / a.candles
        if not cpath.exists():
            raise SystemExit(f"REFUSED: candles file not found: {cpath}")
        df = pd.read_parquet(cpath)
        missing = [c for c in REQUIRED_CANDLE_COLS if c not in df.columns]
        if missing:
            raise SystemExit(f"REFUSED: candles missing columns {missing}.")
        if "bar_index" in df.columns:
            df = df.sort_values("open_time").copy()
            df.index = df["bar_index"].astype(int)
        else:
            df = df.sort_values("open_time").reset_index(drop=True)
        freshness = REHEARSAL_LABEL
        data_meta = {"mode": "fixture_replay", "file": str(cpath),
                     "sha256": sha256_file(cpath)[:16], "rows": len(df),
                     "range": [pd.Timestamp(df["open_time"].iloc[0]).isoformat(),
                               pd.Timestamp(df["close_time"].iloc[-1]).isoformat()]}
        banner = ("[REHEARSAL-NOT-LIVE] fixture replay. " + REHEARSAL_DISCLAIMER)
    print(f"[{v1.MODE_LABEL}-shadow] {banner}", flush=True)
    print(f"[{v1.MODE_LABEL}-shadow] version={SHADOW_VERSION} policy-check: reading B bundle "
          f"(if any) else own frozen chain. No weights invented.", flush=True)
    policy = load_policy(config, root)
    print(f"[{v1.MODE_LABEL}-shadow] policy_source={policy.get('source')} "
          f"policy_id={policy.get('policy_id')} reason={policy.get('reason', policy.get('fallback_note'))}",
          flush=True)
    out = root / a.out
    started_at = datetime.now(timezone.utc).isoformat()
    if a.resume:
        man_path = out / "manifest.json"
        if not man_path.exists():
            raise SystemExit(f"REFUSED: --resume asked but no manifest at {man_path}.")
        man = json.loads(man_path.read_text())
        if man.get("config_sha256") != hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest():
            raise SystemExit("REFUSED: config changed since the recorded run (restart parity requires identical config).")
        if man.get("data_meta") != data_meta:
            raise SystemExit("REFUSED: candle data changed since the recorded run (restart parity requires identical data).")
        if man.get("signals_fingerprint") != (v21.fingerprint_signals(policy["signals"])
                                              if policy.get("signals") is not None else None):
            raise SystemExit("REFUSED: policy signals changed (restart parity requires identical policy).")
        runner = ShadowRunner(config, policy, df, freshness, data_meta, out, root,
                              man["window"][0], a.end_bar if a.end_bar is not None else man["window"][1])
        if runner.start_id != man["window"][0]:
            raise SystemExit("REFUSED: resume window start differs from the recorded run.")
        if runner.end_id < man["window"][1]:
            raise SystemExit("REFUSED: resume window end precedes the recorded run end.")
        if runner.signals_fp != man.get("signals_fingerprint"):
            raise SystemExit("REFUSED: signal-set fingerprint mismatch on resume.")
        if runner.n_bars != man.get("n_bars"):
            raise SystemExit("REFUSED: horizon (n_bars) mismatch on resume.")
        runner.strategy.restore_state(json.loads((out / "state.json").read_text()))
        last_bar = runner.strategy.snapshot_state()["last_bar"]
        start_pos = runner.pos0 if last_bar is None else list(df.index).index(int(last_bar)) + 1
        runner.n_flushed_alerts = sum(1 for _ in open(out / "alerts.jsonl", encoding="utf-8"))
        prev_summary_path = out / "summary.json"
        if prev_summary_path.exists():  # accumulate segment stats so resume == single run
            prev = json.loads(prev_summary_path.read_text())
            runner.counts = {k: int(prev.get("counts", {}).get(k, 0)) for k in runner.counts}
            runner.wait_reasons = dict(prev.get("wait_reasons", {}))
            runner.exit_reasons = dict(prev.get("exit_reasons", {}))
        print(f"[{v1.MODE_LABEL}-shadow] resumed: state ends at bar {last_bar}; "
              f"continuing at position {start_pos}. Appending (no rewrite).", flush=True)
        man["resumed_at"] = started_at
        man["resume_from_bar"] = last_bar
        man["window"][1] = runner.end_id
        (out / "manifest.json").write_text(json.dumps(man, indent=2))
    else:
        if out.exists() and any((out / f).exists() for f in ("manifest.json", "decisions.jsonl", "summary.json")):
            raise FileExistsError(f"Refusing to overwrite existing run in {out} (use --resume).")
        out.mkdir(parents=True, exist_ok=True)
        runner = ShadowRunner(config, policy, df, freshness, data_meta, out, root,
                              a.start_bar, a.end_bar)
        for f in ("decisions.jsonl", "alerts.jsonl", "fills.jsonl"):
            (out / f).write_text("", encoding="utf-8")
        man = {"run": "SIMULATED/PAPER-research-shadow", "exploratory": True, "live_orders": False,
               "shadow_version": SHADOW_VERSION, "banner": banner,
               "freshness": freshness, "disclaimer": REHEARSAL_DISCLAIMER if not live else None,
               "policy_source": policy.get("source"), "policy_id": policy.get("policy_id"),
               "policy_reason": policy.get("reason", policy.get("fallback_note")),
               "signals_path": policy.get("signals_path"),
               "signals_fingerprint": runner.signals_fp,
               "baseline_trades": policy.get("baseline_trades", config["divergence"]["baseline"]),
               "rebase": runner.rebase, "n_bars": runner.n_bars,
               "config_sha256": hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest(),
               "config_path": str(a.config), "data_meta": data_meta,
               "window": [runner.start_id, runner.end_id], "started_at": started_at,
               "execution_assumptions": config["policy_geometry"].get("paper_exit_note", "")}
        (out / "manifest.json").write_text(json.dumps(man, indent=2))
        start_pos = runner.pos0
    # staleness gate for live mode (fresh data must be fresh)
    if live:
        last_close = pd.Timestamp(df["close_time"].iloc[-1])
        age_min = (datetime.now(timezone.utc) - last_close.to_pydatetime()).total_seconds() / 60.0
        max_stale = float(config["data"].get("max_live_stale_minutes", 15))
        if age_min > max_stale:
            for pos in range(0, len(df)):
                bar_id = int(df.index[pos])
                runner._alert(bar_id, pd.Timestamp(df["close_time"].iloc[pos]).isoformat(),
                              "SHADOW_STALE_FEED",
                              f"last closed bar age {age_min:.1f}min > {max_stale}min; all-WAIT")
                runner._wait(bar_id, pd.Timestamp(df["close_time"].iloc[pos]).isoformat(),
                             "STALE_FEED", runner.strategy.account.equity if runner.strategy else 100.0)
            return _finish(runner, out, live, degraded="STALE_FEED")
    for k, pos in enumerate(range(start_pos, runner.pos1 + 1)):
        runner.step(pos)
        if runner.strategy is not None and (k % max(1, runner.persist_every) == 0):
            runner.strategy.save_state(out / "state.json")
    if runner.strategy is not None:
        runner.strategy.save_state(out / "state.json")
        intents_df = runner.strategy.intents_df()
        intents_df.to_csv(out / "intents.csv", index=False)
        verify = v21.verify_intents_v21(intents_df, runner.strategy)
    else:
        intents_df = pd.DataFrame()
        verify = {"intents": 0, "causality": "vacuous-pass (NO_POLICY all-WAIT mode)"}
    _finish(runner, out, live, verify=verify, intents=int(len(intents_df)))


def _finish(runner: ShadowRunner, out: Path, live: bool, verify=None, intents=0, degraded=None) -> None:
    from datetime import datetime as _dt, timezone as _tz
    summary = {"mode": v1.MODE_LABEL + "-shadow", "exploratory": True, "live_orders": False,
               "shadow_version": SHADOW_VERSION, "freshness": runner.freshness,
               "banner": ("FRESH-OBSERVATION: fresh public data, paper advisory only."
                          if live else "REHEARSAL-NOT-LIVE. " + REHEARSAL_DISCLAIMER),
               "policy_source": runner.policy.get("source"), "policy_id": runner.policy.get("policy_id"),
               "counts": runner.counts, "wait_reasons": runner.wait_reasons,
               "exit_reasons": runner.exit_reasons,
               "final_equity": (round(runner.strategy.account.equity, 4)
                                if runner.strategy is not None else None),
               "intents": intents, "verify": verify or {},
               "degraded": degraded or runner.degraded_reason,
               "halt_events": (runner.strategy.daily_halt.halt_events
                               if runner.strategy is not None else []),
               "divergence_trip": ((runner.strategy.divergence.trip_event or None)
                                   if runner.strategy is not None else None),
               "finished_at": _dt.now(_tz.utc).isoformat(),
               "files": ["manifest.json", "decisions.jsonl", "alerts.jsonl", "fills.jsonl",
                         "intents.csv", "state.json", "summary.json"]}
    (out / "summary.json").write_text(json.dumps(summary, indent=2, default=str))
    print(f"[{v1.MODE_LABEL}-shadow] " + json.dumps(
        {"freshness": runner.freshness, "counts": runner.counts,
         "wait_reasons": runner.wait_reasons, "exit_reasons": runner.exit_reasons,
         "final_equity": summary["final_equity"], "degraded": summary["degraded"]},
        default=str), flush=True)
    print(f"[{v1.MODE_LABEL}-shadow] wrote {out} (decisions={runner.counts['decisions']}). "
          f"{'' if live else REHEARSAL_DISCLAIMER}", flush=True)


if __name__ == "__main__":
    main()
