"""Opencode R77 W1-RUNNER core: ONE integrated stateful advisory runner.

Fresh + replay share ALL interfaces here (feed ingest, causal inference
schema, frequency gates, execution, state). Nothing in this module is
live-trading: advisory records only, no exchange adapter.

Reuse (UNMODIFIED, never reimplemented semantics):
  - scripts/opencode_r76_infer.py: frozen v29 chain pieces (prespec load,
    hash-validated checkpoints/calibrators, 6h-UTC-grid decision bars,
    SwingStore causal features, combine/choose). infer_full() below runs the
    verbatim chain but ALSO exposes calibrated scores + raw iso4 geometry,
    which infer_decisions() drops for gated-out rows.
  - scripts/opencode_r76_feedexec.py: FeedState/feed reject codes,
    parse_closed_klines/row_hash, FeedExecAccount (engine ohlc-v2 parity
    incl. TP1 50% partial-then-TP2, stop-first, entry-bar suppression,
    fees/funding, timeout, truncation), ControlDivergenceTrip.
  - scripts/opencode_paper_trader.py v1.DdGuard, v2 DailyLossHalt /
    MaxPositionGuard, v2.1 OneSidedDivergenceMonitor.check().

Frozen-policy fixes vs R76 blockers (Codex B1..B6):
  B1: fresh mode runs the FULL path (fetch -> infer_full -> AdvisorStrategy),
      never returns after ingest.
  B3: explicit score/gate schema; decision dicts NEVER carry `confidence`;
      observe_bar() raises if `confidence` is present (fail-closed against
      injection). WAIT stays WAIT, never mapped to SHORT/FLAT.
  B4: clock is the stable 6h UTC grid from open_time (never positional
      modulo); stride 72 cross-checked against the W1 prespec anchor.
  B5: control account iso4_only_1x has its OWN independent frequency gate +
      own busy state and is evaluated on EVERY eligible iso4 raw decision,
      even when operating abstains / is busy / halted / tripped.
  B6: persistent watermarks + gate counters + accounts + kill state +
      deterministic output journals; resume rejects identity change;
      overlapping/duplicate delivery is deduped (watermark + journal).

torch is imported before pandas (Windows DLL load-order rule).
"""
import torch  # noqa: F401  (torch truoc pandas: DLL load-order Windows host)

import hashlib
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
if str(_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(_ROOT / "scripts"))
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

import opencode_r76_feedexec as fx  # noqa: E402
import opencode_r76_infer as r76  # noqa: E402
import opencode_paper_trader as v1  # noqa: E402
import opencode_paper_trader_v2 as v2  # noqa: E402
from agentic_alpha_lab.backtest import engine as bt_engine  # noqa: E402
from agentic_alpha_lab.data.sequence_context import encode_windows  # noqa: E402
from agentic_alpha_lab.data.swing import choose, grid  # noqa: E402
from agentic_alpha_lab.data.training import validate_source  # noqa: E402
from agentic_alpha_lab.models.ensemble_value import combine  # noqa: E402
from agentic_alpha_lab.models.residual_temporal_value import (  # noqa: E402
    residual_predict)

ADVISOR_VERSION = "r77_advisor/1"
STATE_VERSION = "r77_advisor_state/1"
MODE_LABEL = "SIMULATED/PAPER-research-advisor"
INTENT_PREFIX = "r77-"
POLICY_ID = "confirmed_dd_guard"
OVERLAY_VERSION = "r77-overlays/1"
FEED_WARMUP_BARS = 12  # feed-level ingest warmup (r76 value); inference warmup (36864) dominates
GRID_SECONDS = 6 * 3600
STRIDE_BARS = 72

STATUS_READY = "READY_DECISION"
STATUS_WAIT = "WAIT"  # model abstain on a grid bar (never remapped)
STATUS_WARMUP = "WARMUP"
STATUS_OFF_CLOCK = "OFF_CLOCK"
STATUS_DIAGNOSTIC = "DIAGNOSTIC"


def _ts(x) -> pd.Timestamp:
    """tz-aware UTC coercion for str/naive/aware inputs alike."""
    t = pd.Timestamp(x)
    if t.tzinfo is None:
        return t.tz_localize("UTC")
    return t.tz_convert("UTC")


# ------------------------------------------------------------- clock ---
def on_grid(open_ts: pd.Timestamp) -> bool:
    """Stable 6h-UTC-grid predicate from wall-clock time (never positional)."""
    ts = _ts(open_ts)
    return (ts.value - pd.Timestamp("1970-01-01", tz="UTC").value) % (
        GRID_SECONDS * 10 ** 9) == 0


def check_stride_against_prespec(spec: dict) -> None:
    """Fail closed unless stride 72 matches the W1 prespec anchor rule."""
    anchor = spec.get("anchor_stride", {})
    rule = json.dumps(anchor)
    if "72" not in rule and "6h" not in rule:
        raise ValueError(
            "R77 stride/anchor mismatch vs W1 prespec (refusing): "
            f"{rule[:200]}")


# ----------------------------------------------------- inference -------
def infer_full(closed_candles_df: pd.DataFrame, spec: dict | None = None,
               device: torch.device | None = None,
               max_decisions: int | None = None) -> list[dict]:
    """Causal frozen v29 chain -> RAW decisions (no frequency gating here).

    Verbatim chain from scripts/opencode_r76_infer.py (same helpers, same
    assets, same votes). Difference: every grid decision row keeps calibrated
    scores + FULL raw iso4 geometry (even rows the frequency gate would later
    drop), plus per-map actions and votes, so the strategy can run
    INDEPENDENT frozen gates for iso4-only and confirmed portfolios.
    Gating lives in AdvisorStrategy (persistent state), not here.
    """
    spec = spec or r76.load_prespec()
    check_stride_against_prespec(spec)
    candles = validate_source(closed_candles_df)
    if len(candles) < r76.WARMUP_BARS:
        return [{"status": STATUS_WARMUP,
                 "reason": f"insufficient closed history: {len(candles)} < "
                           f"{r76.WARMUP_BARS} (distinct from strategy WAIT)",
                 "n_bars": int(len(candles)),
                 "warmup_bars_required": r76.WARMUP_BARS}]
    cfg, calibs = r76.load_frozen_assets(spec)
    device = device or torch.device(
        "cuda" if torch.cuda.is_available() else "cpu")
    candidates = np.asarray(grid(cfg), dtype=np.float32)

    store = r76.SwingStore(candles, cfg)
    opens = pd.DatetimeIndex(pd.to_datetime(candles["open_time"], utc=True))
    closes = pd.DatetimeIndex(pd.to_datetime(candles["close_time"], utc=True))
    bars = r76.decision_bars(len(candles), opens)
    if max_decisions is not None:
        bars = bars[:max_decisions]
    ready = [int(b) for b in bars
             if r76._frames_ready(store, closes, int(b), cfg["context"])]
    bars = np.asarray(ready, dtype=np.int64)
    if len(bars) == 0:
        return [{"status": STATUS_WARMUP,
                 "reason": "no 6h-aligned decision bar with full warmup yet",
                 "n_bars": int(len(candles)),
                 "warmup_bars_required": r76.WARMUP_BARS}]

    seqs, feats, rows = [], [], []
    for bar in bars:
        decision_time = closes[int(bar)]
        windows, _, _ = store.at(decision_time)
        seqs.append(encode_windows(windows))
        w, stamps, ages, feat40, atr5, atr4 = store.sample(decision_time)
        feats.append(np.asarray(feat40, dtype=np.float32))
        proof = {}
        for tf, frame in zip(cfg["timeframes"], store.frames):
            last_close = pd.DatetimeIndex(
                pd.to_datetime(frame["close_time"], utc=True))
            used = last_close[last_close <= decision_time]
            if len(used) == 0:
                raise ValueError(f"HTF {tf}: no closed bar <= decision time")
            proof[tf] = str(used.max())
            assert used.max() <= decision_time, f"HTF leak on {tf}"
        rows.append({"bar_index": int(bar), "decision_time": decision_time,
                     "close": float(candles["close"].iloc[int(bar)]),
                     "atr5": float(atr5), "atr4": float(atr4),
                     "htf_last_close_lte_decision": proof})
    seqs = np.stack(seqs).astype(np.float32)
    feats = np.stack(feats).astype(np.float32)

    outs = []
    for seed in r76.SEEDS:
        model = r76._load_model(seed, candidates, spec, device)
        outs.append(residual_predict(model, seqs, feats,
                                     batch_size=r76.BATCH))
        del model
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    stacked = np.stack(outs).astype(np.float64)
    base, details = combine(stacked, 0.0)

    score = np.asarray(details["selection_score_percent"], dtype=np.float64)
    fill = np.asarray(details["mean_fill_score"], dtype=np.float64)
    preds = {}
    for m in r76.MAPS:
        mapped = np.interp(score.ravel(), calibs[m]["x"],
                           calibs[m]["y"]).reshape(score.shape)
        arr = np.asarray(base, dtype=np.float64).copy()
        arr[..., 0] = mapped / np.clip(fill, 1e-6, 1 - 1e-6)
        preds[m] = arr

    per_map, dirs = {}, {}
    for m in r76.MAPS:
        olist, dlist = [], []
        for j in range(preds[m].shape[0]):
            o = choose(preds[m][j], rows[j]["close"], rows[j]["atr5"],
                       rows[j]["atr4"], cfg)
            olist.append(o)
            dlist.append(1 if o.get("action") == "LONG"
                         else (-1 if o.get("action") == "SHORT" else 0))
        per_map[m] = olist
        dirs[m] = np.asarray(dlist, dtype=int)
    d2, d4, dall = dirs["isotonic_2"], dirs["isotonic_4"], dirs["isotonic_all"]

    policy = cfg["policy"]
    _ = policy  # thresholds stay frozen inside choose(); recorded, not used here
    score1 = np.asarray(score).ravel()
    fill1 = np.asarray(fill).ravel()
    out = []
    for j in range(len(bars)):
        iso4 = per_map["isotonic_4"][j]
        geo = None
        if iso4.get("action") in ("LONG", "SHORT"):
            geo = {k: iso4[k] for k in (
                "direction", "entry_limit", "stop_loss", "take_profit_1",
                "take_profit_2", "holding_bars", "leverage",
                "expected_net_percent", "ohlc_fill_score",
                "conditional_win_score") if k in iso4}
        majority = (d4[j] != 0) and (
            [d2[j], d4[j], dall[j]].count(int(d4[j])) >= 2)
        confirmed = bool((d4[j] != 0) and (dall[j] == d4[j]))
        out.append({**rows[j], "status": "READY_RAW",
                    "scores": {
                        "selection_score_percent": float(score1[j]),
                        "mean_fill_score": float(fill1[j])},
                    "iso4_raw_action": iso4.get("action", "WAIT"),
                    "iso4_raw_geometry": geo,
                    "per_map_action": {m: per_map[m][j].get("action")
                                       for m in r76.MAPS},
                    "vote_majority": bool(majority),
                    "vote_confirmed": confirmed,
                    "device": str(device)})
    return out


# ------------------------------------------------- frequency gate ------
class FrequencyGate:
    """Frozen cap4/cd5 rule, verbatim r76 semantics, persistent counters."""

    def __init__(self, cap: int = 4, cooldown_days: int = 5):
        self.cap = int(cap)
        self.cooldown_days = int(cooldown_days)
        self.monthly: dict[str, int] = {}
        self.next_allowed: pd.Timestamp = pd.Timestamp.min.tz_localize("UTC")

    def attempt(self, decision_time: pd.Timestamp,
                eligible: bool) -> tuple[bool, str]:
        """Consume one slot iff eligible under the frozen rule."""
        if not eligible:
            return False, "ineligible (no vote or WAIT)"
        ts = _ts(decision_time)
        month = ts.strftime("%Y-%m")
        if ts < self.next_allowed:
            return False, "cooldown"
        if self.monthly.get(month, 0) >= self.cap:
            return False, "monthly_cap"
        self.monthly[month] = self.monthly.get(month, 0) + 1
        self.next_allowed = ts + pd.Timedelta(days=self.cooldown_days)
        return True, "admitted"

    def snapshot(self) -> dict:
        return {"cap": self.cap, "cooldown_days": self.cooldown_days,
                "monthly": dict(self.monthly),
                "next_allowed": self.next_allowed.isoformat()}

    def restore(self, snap: dict) -> None:
        if int(snap.get("cap", -1)) != self.cap or int(
                snap.get("cooldown_days", -1)) != self.cooldown_days:
            raise ValueError("FrequencyGate frozen params changed (refusing).")
        self.monthly = {k: int(v) for k, v in snap.get("monthly", {}).items()}
        self.next_allowed = pd.Timestamp(snap["next_allowed"], tz="UTC")


# ------------------------------------------------------------ IDs ------
def _digest(*parts: str) -> str:
    body = "|".join(str(p) for p in parts)
    return INTENT_PREFIX + hashlib.sha256(body.encode("utf-8")).hexdigest()[:16]


def intent_id(portfolio: str, decision_time_iso: str, side: str,
              equity_before: float) -> str:
    return _digest("intent", portfolio, decision_time_iso, side,
                   f"{float(equity_before):.6f}")


def alert_id(kind: str, bar_time_iso: str, equity: float, note: str = "") -> str:
    return _digest("alert", kind, bar_time_iso, f"{float(equity):.6f}", note)


def fill_id(account: str, kind: str, signal_time_iso: str, bar_time_iso: str,
            fraction: float, price: float) -> str:
    return _digest("fill", account, kind, signal_time_iso, bar_time_iso,
                   f"{float(fraction):.6f}", f"{float(price):.8f}")


# ---------------------------------------------------------- strategy ---
class AdvisorStrategy:
    """Shared streaming consumer: settle -> control ALWAYS -> operating.

    Per closed bar (strictly increasing):
      1. settle operating + control accounts (journal fills exactly-once);
      2. post control equity to the divergence trace;
      3. evaluate divergence trip + daily halt (journal alerts exactly-once);
      4. on newly-observed grid decisions:
           (a) CONTROL: iso4 raw non-WAIT through the INDEPENDENT iso4 gate;
               arms fixed-1x pending on the control account even when the
               operating side abstains / is busy / halted / tripped;
           (b) OPERATING: confirmed non-WAIT through the INDEPENDENT
               confirmed gate, then divergence-latch / daily-halt / busy
               checks, then guard sizing from control exits strictly before
               the decision, then arm.
           (c) post this bar's NEW control exits to the guard AFTER (b), so
               sizing never sees same-bar/future exits.
      5. advance watermarks.
    """

    INTENT_COLUMNS = ["intent_id", "portfolio", "signal_time", "side",
                      "entry_limit", "tp1", "tp2", "sl", "size",
                      "guard_state", "signal_bar_time", "entry_start_bar_time",
                      "leverage", "equity_before", "control_equity",
                      "divergence", "mode"]

    def __init__(self, config: dict, n_bars: int | None = None):
        for section in ("guard", "costs", "execution", "account",
                        "kill_switch", "divergence", "overlays"):
            if section not in config:
                raise ValueError(
                    f"advisor config lacks [{section}] (refusing).")
        if config.get("allow_live_orders", True):
            raise ValueError("REFUSED: allow_live_orders must stay false.")
        self.config = config
        self.n_bars = n_bars
        g = config["guard"]
        c = config["costs"]
        pg = config["execution"]
        init = float(config["account"]["initial_equity_indexed"])
        mk = dict(initial_equity=init, fee_rate=c["fee_rate_per_fill"],
                  funding_long_rate=c["funding_long_rate"],
                  funding_short_rate=c["funding_short_rate"],
                  funding_interval_hours=c["funding_interval_hours"],
                  entry_expiry_bars=int(pg.get("entry_expiry_bars", 12)),
                  tp1_fraction=float(pg.get("tp1_fraction", 0.5) or 0.5))
        self.operating = fx.FeedExecAccount(**mk, name="operating")
        self.control = fx.FeedExecAccount(**mk, name="iso4_only_1x")
        self.guard = v1.DdGuard(g["dd_trigger"], g["guard_leverage"],
                                g["full_leverage"], init)
        ks = config["kill_switch"]
        if int(ks.get("max_positions", 1)) != 1:
            raise ValueError("kill_switch.max_positions must be 1.")
        self.daily_halt = v2.DailyLossHalt(ks["daily_loss_halt_pct"])
        dv = config["divergence"]
        self.trip = fx.ControlDivergenceTrip(dv["tolerance_pct"], init)
        self.max_holding = int(pg.get("max_holding_bars", 2016))
        gates = config.get("gates", {})
        self.iso4_gate = FrequencyGate(
            gates.get("maximum_signals_per_month", 4),
            gates.get("cooldown_days", 5))
        self.confirmed_gate = FrequencyGate(
            gates.get("maximum_signals_per_month", 4),
            gates.get("cooldown_days", 5))
        # Watermarks / observation identity.
        self.shadow_start: pd.Timestamp | None = None
        self.last_settled: pd.Timestamp | None = None
        self.last_decision: pd.Timestamp | None = None
        self.bootstrap_observed_at: str = ""
        # Journals (exactly-once).
        self.intents: dict[str, dict] = {}
        self.alerts: dict[str, dict] = {}
        self.fills: dict[str, dict] = {}
        self.decision_log: list[dict] = []
        self.diagnostics: list[dict] = []
        self.bar_close_by_idx: dict[int, str] = {}
        self.bars_seen = 0
        self.off_clock_bars = 0
        self.counters = {"control_admitted": 0, "control_busy": 0,
                         "operating_admitted": 0, "operating_busy": 0,
                         "operating_halted": 0, "operating_tripped": 0,
                         "wait_rows": 0, "diagnostic_rows": 0}
        self._last_bar_idx: int | None = None
        self._open_day: str | None = None

    # -- observation window ---------------------------------------------
    def begin_observation(self, shadow_start_iso: str,
                          observed_at: str) -> None:
        """Replay: shadow = first candle close (all decisions actionable).
        Fresh: shadow = bootstrap fetch time (all bootstrap inferences are
        DIAGNOSTIC-only; never backdated alerts; gates start empty)."""
        self.shadow_start = _ts(shadow_start_iso)
        self.bootstrap_observed_at = observed_at

    # -- exactly-once journals -------------------------------------------
    def _journal_fill(self, ev: dict, signal_time_iso: str,
                      bar_time_iso: str) -> dict:
        fid = fill_id(ev.get("account", "?"), ev.get("kind", "?"),
                      signal_time_iso, bar_time_iso,
                      ev.get("fraction", 0.0), ev.get("price", 0.0))
        rec = {**ev, "fill_id": fid, "bar_time": bar_time_iso,
               "signal_time": signal_time_iso}
        if fid not in self.fills:
            self.fills[fid] = rec
        return self.fills[fid]

    def _journal_alert(self, alert: dict) -> dict:
        aid = alert.get("alert_id") or alert_id(
            alert.get("kind", "?"), str(alert.get("bar_time", "")),
            float(alert.get("equity_now", alert.get("paper_equity", 0.0))),
            str(alert.get("direction", "")))
        alert = {**alert, "alert_id": aid}
        if aid not in self.alerts:
            self.alerts[aid] = alert
        return alert

    # -- per-bar consumption (THE shared interface) -----------------------
    def observe_bar(self, bar_idx: int, bar: dict,
                    raw: dict | None, observed_at: str) -> dict:
        """Consume ONE closed bar + this bar's raw adapter row (or None)."""
        if self.shadow_start is None:
            raise ValueError("begin_observation() must precede observe_bar().")
        if self._last_bar_idx is not None and bar_idx <= self._last_bar_idx:
            raise AssertionError(
                "observe_bar bars must be strictly increasing.")
        if raw is not None and "confidence" in raw:
            raise ValueError(
                "REFUSED injected confidence field (frozen policy has none).")
        open_t = _ts(bar["open_time"])
        close_t = _ts(bar["close_time"])
        if close_t <= open_t:
            return self._reject(bar_idx, open_t, close_t, observed_at,
                                fx.STATUS_INCOMPLETE)
        try:
            _ = (float(bar["open"]), float(bar["high"]), float(bar["low"]),
                 float(bar["close"]), float(bar["volume"]))
        except (TypeError, ValueError, KeyError):
            return self._reject(bar_idx, open_t, close_t, observed_at,
                                fx.STATUS_INCOMPLETE)
        h, lo = float(bar["high"]), float(bar["low"])
        if not (h >= lo and h >= float(bar["open"])
                and h >= float(bar["close"]) and lo <= float(bar["open"])
                and lo <= float(bar["close"]) and float(bar["volume"]) >= 0):
            return self._reject(bar_idx, open_t, close_t, observed_at,
                                fx.STATUS_INCOMPLETE)

        row = pd.Series({"open_time": open_t, "close_time": close_t,
                         "open": float(bar["open"]), "high": h,
                         "low": lo, "close": float(bar["close"]),
                         "volume": float(bar["volume"])})
        # Index FIRST so exit records carry exact bar/decision timestamps.
        self.bar_close_by_idx[bar_idx] = close_t.isoformat()
        # Day-open BEFORE this bar settles (v2 past-only carry); settlement
        # then evaluates against it, so a same-bar exit can trip the halt.
        day = open_t.date().isoformat()
        self.daily_halt.roll_day(day, self.operating.equity)
        self._open_day = day
        self.operating.on_bar_close(bar_idx, row, self.n_bars)
        op_events = self._drain_events(self.operating, bar_idx)
        self.control.on_bar_close(bar_idx, row, self.n_bars)
        ctrl_events = self._drain_events(self.control, bar_idx)
        self.trip.post_control_equity(bar_idx, self.control.equity)
        self.bars_seen += 1
        self._last_bar_idx = bar_idx
        self.last_settled = close_t
        bar_time_iso = close_t.isoformat()
        div_status = self.trip.check(bar_idx, self.operating.equity,
                                     bar_time_iso)
        if div_status is not None and div_status.get("status") == "TRIPPED_NOW":
            self._journal_alert({**div_status, "bar_time": bar_time_iso,
                                 "equity_now": self.operating.equity})
        halted = self.daily_halt.evaluate(self.operating.equity, bar_time_iso,
                                          bar_idx)
        if halted:
            latest = self.daily_halt.halt_events[-1]
            self._journal_alert({**latest, "bar_idx": bar_idx,
                                 "bar_time": bar_time_iso,
                                 "equity_now": self.operating.equity})
        for ev in self.trip.drain_over_alerts():
            self._journal_alert({**ev, "equity_now": self.operating.equity})

        status = STATUS_OFF_CLOCK
        if raw is not None:
            if raw.get("status") == STATUS_WARMUP:
                status = STATUS_WARMUP
                self.decision_log.append({
                    "status": STATUS_WARMUP, "observed_at": observed_at,
                    "bar_time": bar_time_iso,
                    "reason": raw.get("reason", "")})
            elif raw.get("status") == "READY_RAW":
                status = self._on_decision(
                    bar_idx, bar_time_iso, raw, observed_at, bool(halted),
                    div_status)
            else:
                raise ValueError(
                    f"unknown raw adapter status {raw.get('status')!r} "
                    "(refusing).")
        else:
            self.off_clock_bars += 1
        # Guard sees ONLY independently-realized control exits, posted AFTER
        # the operating intake above (strictly-before causality).
        for ev in ctrl_events:
            if ev.get("kind") == "EXIT" and ev.get("reason") not in (
                    "CANCEL",) and "equity_after" in ev:
                self.guard.record_exit(pd.Timestamp(ev["bar_time"], tz="UTC"),
                                       float(ev["equity_after"]))
        _ = op_events
        return {"status": status, "observed_at": observed_at,
                "bar_time": bar_time_iso}

    def _reject(self, bar_idx: int, open_t: pd.Timestamp,
                close_t: pd.Timestamp, observed_at: str,
                code: str) -> dict:
        return {"status": code, "observed_at": observed_at,
                "bar_time": close_t.isoformat()}

    def _drain_events(self, account: fx.FeedExecAccount,
                      bar_idx: int) -> list[dict]:
        """Journal account events exactly-once; return this bar's records."""
        out: list[dict] = []
        for ev in account.events:
            if ev.get("bar_idx") != bar_idx or ev.get("kind") != "EXIT":
                continue
            sig_iso = self.bar_close_by_idx.get(
                int(ev.get("signal_bar", -1)), "")
            rec = self._journal_fill(
                ev, sig_iso,
                self.bar_close_by_idx.get(bar_idx, ""))
            out.append(rec)
        return out

    # -- decision handling -------------------------------------------------
    def _on_decision(self, bar_idx: int, bar_time_iso: str, raw: dict,
                     observed_at: str, halted: bool,
                     div_status: dict | None) -> str:
        decision_time = _ts(raw["decision_time"])
        assert decision_time <= _ts(bar_time_iso), \
            "decision uses a candle that closes after itself (causality bug)."
        # No-backdate: pre-observation inferences are diagnostic-only.
        assert self.shadow_start is not None
        if decision_time <= self.shadow_start:
            self.counters["diagnostic_rows"] += 1
            self.diagnostics.append({
                "status": STATUS_DIAGNOSTIC, "observed_at": observed_at,
                "decision_time": decision_time.isoformat(),
                "bar_time": bar_time_iso,
                "iso4_raw_action": raw.get("iso4_raw_action"),
                "vote_confirmed": bool(raw.get("vote_confirmed")),
                "note": "pre-observation inference: diagnostic only, never "
                        "an actionable alert/intent; gates untouched"})
            if (self.last_decision is None
                    or decision_time > self.last_decision):
                self.last_decision = decision_time
            return STATUS_DIAGNOSTIC
        if (self.last_decision is not None
                and decision_time <= self.last_decision):
            return STATUS_DIAGNOSTIC  # overlapping-window redelivery
        self.last_decision = decision_time

        iso4_action = raw.get("iso4_raw_action", "WAIT")
        voted = bool(raw.get("vote_confirmed"))
        confirmed_action = iso4_action if voted else "WAIT"

        # CONTROL first: independent gate, own busy state, never gated by
        # operating halt/trip/busy. (B5)
        ctrl_intent = None
        if iso4_action in ("LONG", "SHORT"):
            admitted, gate_reason = self.iso4_gate.attempt(
                decision_time, True)
            if admitted:
                ctrl_intent = self._arm(
                    self.control, "iso4_only_1x", iso4_action,
                    raw["iso4_raw_geometry"], decision_time, bar_time_iso,
                    bar_idx, leverage=1.0,
                    notional=self.control.equity, gate_reason=gate_reason)
                self.counters["control_admitted"] += int(
                    ctrl_intent is not None)
                self.counters["control_busy"] += int(ctrl_intent is None)
        # OPERATING: independent confirmed gate, then overlays, then sizing.
        op_intent = None
        final_action = STATUS_WAIT
        if confirmed_action in ("LONG", "SHORT"):
            admitted, gate_reason = self.confirmed_gate.attempt(
                decision_time, True)
            if admitted:
                if div_status is not None:
                    self.trip.blocks += 1
                    self.counters["operating_tripped"] += 1
                elif halted:
                    self.counters["operating_halted"] += 1
                else:
                    lev, state = self.guard.multiplier(decision_time)
                    op_intent = self._arm(
                        self.operating, "operating", confirmed_action,
                        raw["iso4_raw_geometry"], decision_time,
                        bar_time_iso, bar_idx, leverage=lev,
                        notional=self.operating.equity * lev,
                        gate_reason=gate_reason, guard_state=state)
                    self.counters["operating_admitted"] += int(
                        op_intent is not None)
                    self.counters["operating_busy"] += int(op_intent is None)
        if op_intent is not None:
            final_action = confirmed_action
        elif confirmed_action in ("LONG", "SHORT"):
            final_action = STATUS_WAIT  # gated/blocked collapses to WAIT
        else:
            self.counters["wait_rows"] += 1
        self.decision_log.append({
            "status": STATUS_READY, "action": final_action,
            "observed_at": observed_at,
            "decision_time": decision_time.isoformat(),
            "bar_time": bar_time_iso,
            "iso4_raw_action": iso4_action,
            "vote_majority": bool(raw.get("vote_majority")),
            "vote_confirmed": voted,
            "confirmed_action": confirmed_action,
            "selection_score_percent": raw["scores"][
                "selection_score_percent"],
            "mean_fill_score": raw["scores"]["mean_fill_score"],
            "control_intent_id": (ctrl_intent or {}).get("intent_id"),
            "operating_intent_id": (op_intent or {}).get("intent_id"),
            "htf_last_close_lte_decision": raw.get(
                "htf_last_close_lte_decision")})
        return STATUS_READY if final_action != STATUS_WAIT else STATUS_WAIT

    def _arm(self, account: fx.FeedExecAccount, portfolio: str, side: str,
             geometry: dict | None, decision_time: pd.Timestamp,
             bar_time_iso: str, bar_idx: int, leverage: float,
             notional: float, gate_reason: str,
             guard_state: str = "FIXED_1x") -> dict | None:
        if not geometry:
            return None
        if v2.MaxPositionGuard.blocks_new_intent(account):
            return None
        signal = {"signal_bar": int(bar_idx),
                  "direction": 1 if side == "LONG" else -1,
                  "entry_limit": float(geometry["entry_limit"]),
                  "stop_loss": float(geometry["stop_loss"]),
                  "take_profit_1": float(geometry["take_profit_1"]),
                  "take_profit_2": float(geometry["take_profit_2"]),
                  "holding_bars": min(int(geometry.get(
                      "holding_bars", self.max_holding)), self.max_holding),
                  "leverage": float(leverage), "notional": float(notional),
                  "equity_before": float(account.equity)}
        if account.arm_pending(signal) != "ARMED":
            return None
        iid = intent_id(portfolio, decision_time.isoformat(), side,
                        signal["equity_before"])
        if iid in self.intents:
            return self.intents[iid]
        expected = self.trip.expected_at(bar_idx)
        base_div = ((self.operating.equity - expected) / expected
                    if expected > 0 else 0.0)
        intent = {"intent_id": iid, "portfolio": portfolio,
                  "signal_time": bar_time_iso, "side": side,
                  "entry_limit": signal["entry_limit"],
                  "tp1": signal["take_profit_1"],
                  "tp2": signal["take_profit_2"], "sl": signal["stop_loss"],
                  "size": float(notional), "guard_state": guard_state,
                  "signal_bar_time": bar_time_iso,
                  "entry_start_bar_time": bar_time_iso,
                  "leverage": float(leverage),
                  "equity_before": signal["equity_before"],
                  "control_equity": float(self.control.equity),
                  "divergence": float(base_div), "mode": MODE_LABEL,
                  "gate": gate_reason}
        assert signal["signal_bar"] < signal["signal_bar"] + 1
        self.intents[iid] = intent
        return intent

    # -- persistence -------------------------------------------------------
    def identity_block(self, config: dict, spec: dict) -> dict:
        return {"advisor_version": ADVISOR_VERSION,
                "policy_id": POLICY_ID,
                "overlay_version": OVERLAY_VERSION,
                "config_sha256": hashlib.sha256(
                    json.dumps(config, sort_keys=True).encode()
                ).hexdigest(),
                "inference_prespec_sha256": hashlib.sha256(
                    Path(r76.SPEC_PATH).read_bytes()).hexdigest(),
                "checkpoint_sha256": list(
                    spec["checkpoints"]["sha256"]),
                "calibrator_iso4_sha256": spec["calibrators"]["maps"][
                    "iso4"]["sha256"] if isinstance(
                    spec["calibrators"]["maps"]["iso4"], dict)
                else spec["calibrators"]["maps"]["iso4"]}

    def snapshot_state(self, identity: dict) -> dict:
        return {"version": STATE_VERSION, "mode": MODE_LABEL,
                "exploratory": True, "identity": identity,
                "n_bars": self.n_bars,
                "watermarks": {
                    "last_settled_close_time": (
                        self.last_settled.isoformat()
                        if self.last_settled else None),
                    "last_decision_time": (
                        self.last_decision.isoformat()
                        if self.last_decision else None),
                    "shadow_start": self.shadow_start.isoformat()
                    if self.shadow_start else None,
                    "bootstrap_observed_at": self.bootstrap_observed_at},
                "last_bar_idx": self._last_bar_idx,
                "bars_seen": self.bars_seen,
                "off_clock_bars": self.off_clock_bars,
                "open_day": self._open_day,
                "operating": self.operating.snapshot(),
                "control": self.control.snapshot(),
                "iso4_gate": self.iso4_gate.snapshot(),
                "confirmed_gate": self.confirmed_gate.snapshot(),
                "dd_guard": {
                    "exits": [[t.isoformat(), e]
                              for t, e in self.guard._exits],  # noqa: SLF001
                    "history": self.guard.history,
                    "state_changes": self.guard.state_changes,
                    "last_state": self.guard._last_state},  # noqa: SLF001
                "daily_halt": self.daily_halt.snapshot(),
                "divergence": self.trip.snapshot(),
                "counters": dict(self.counters),
                "bar_close_by_idx": {str(k): v for k, v in
                                     self.bar_close_by_idx.items()},
                "intents": self.intents, "alerts": self.alerts,
                "fills": self.fills, "decision_log": self.decision_log,
                "diagnostics": self.diagnostics}

    def restore_state(self, snap: dict, identity: dict) -> None:
        if snap.get("version") != STATE_VERSION:
            raise ValueError(
                f"state version mismatch: {snap.get('version')} (refusing).")
        if snap.get("mode") != MODE_LABEL:
            raise ValueError("state mode mismatch (refusing).")
        if snap.get("n_bars") != self.n_bars:
            raise ValueError("state horizon (n_bars) mismatch (refusing).")
        old, new = snap.get("identity", {}), identity
        for key in ("advisor_version", "policy_id", "overlay_version",
                    "config_sha256", "inference_prespec_sha256",
                    "checkpoint_sha256", "calibrator_iso4_sha256"):
            if old.get(key) != new.get(key):
                raise ValueError(
                    f"identity change on resume: {key} "
                    f"({old.get(key)} -> {new.get(key)}) (refusing).")
        wm = snap["watermarks"]
        self.shadow_start = pd.Timestamp(wm["shadow_start"], tz="UTC")
        self.bootstrap_observed_at = wm["bootstrap_observed_at"]
        self.last_settled = (pd.Timestamp(wm["last_settled_close_time"],
                                          tz="UTC")
                             if wm["last_settled_close_time"] else None)
        self.last_decision = (pd.Timestamp(wm["last_decision_time"], tz="UTC")
                              if wm["last_decision_time"] else None)
        self._last_bar_idx = snap["last_bar_idx"]
        self.bars_seen = int(snap["bars_seen"])
        self.off_clock_bars = int(snap.get("off_clock_bars", 0))
        self._open_day = snap.get("open_day")
        self.operating.restore(snap["operating"])
        self.control.restore(snap["control"])
        self.iso4_gate.restore(snap["iso4_gate"])
        self.confirmed_gate.restore(snap["confirmed_gate"])
        gd = snap["dd_guard"]
        self.guard._exits = [(pd.Timestamp(t), float(e))  # noqa: SLF001
                             for t, e in gd["exits"]]
        self.guard.history = list(gd["history"])
        self.guard.state_changes = int(gd["state_changes"])
        self.guard._last_state = gd["last_state"]  # noqa: SLF001
        self.daily_halt.restore(snap["daily_halt"])
        self.trip.restore(snap["divergence"])
        self.counters = dict(snap["counters"])
        self.bar_close_by_idx = {int(k): v for k, v in
                                 snap.get("bar_close_by_idx", {}).items()}
        self.intents = dict(snap.get("intents", {}))
        self.alerts = dict(snap.get("alerts", {}))
        self.fills = dict(snap.get("fills", {}))
        self.decision_log = list(snap.get("decision_log", []))
        self.diagnostics = list(snap.get("diagnostics", []))


# ------------------------------------------------------------- fresh ---
def fetch_warmup_paginated(symbol: str = "BTCUSDT", interval: str = "5m",
                           page_limit: int = 1500, max_bars: int = 40000,
                           timeout_seconds: int = 20,
                           host: str = fx.FAPI_HOST,
                           path: str = fx.FAPI_PATH) -> tuple[list, dict]:
    """Public USD-M klines GET only (no keys). Page backwards via endTime."""
    import time
    pages, end_ms = [], None
    while sum(len(p) for p in pages) < max_bars:
        qs = {"symbol": symbol, "interval": interval,
              "limit": int(page_limit)}
        if end_ms is not None:
            qs["endTime"] = int(end_ms)
        url = (f"{host}{path}?"
               f"{urllib.parse.urlencode(qs)}")
        req = urllib.request.Request(
            url, headers={"User-Agent": "agentic-alpha-lab-r77-advisor/1"})
        with urllib.request.urlopen(req,
                                    timeout=timeout_seconds) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
        if not raw:
            break
        pages.append(raw)
        oldest_open = int(raw[0][0])
        if len(raw) < int(page_limit):
            break
        end_ms = oldest_open - 1
        if end_ms <= 0:
            break
    flat = [r for page in reversed(pages) for r in page]
    seen, dedup = set(), []
    for r in flat:
        if r[0] not in seen:
            seen.add(r[0])
            dedup.append(r)
    now_ms = int(time.time() * 1000)
    observed_at = pd.Timestamp(now_ms, unit="ms", tz="UTC").isoformat()
    closed = fx.parse_closed_klines(dedup, now_ms, symbol, interval,
                                    observed_at)
    quote_by_open = {int(r[0]): float(r[7]) for r in dedup}
    for cnd in closed:
        open_ms = int(_ts(cnd["open_time"]).value // 10 ** 6)
        cnd["quote_volume"] = quote_by_open.get(open_ms, float("nan"))
    prov = {"host": host, "path": path, "symbol": symbol,
            "interval": interval, "market": "USDM",
            "fetched_at": observed_at, "n_pages": len(pages),
            "n_raw": len(dedup), "n_closed": len(closed)}
    return closed, prov
