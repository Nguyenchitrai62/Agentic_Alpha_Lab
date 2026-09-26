"""Opencode R78 W1-ROLLING: repaired rolling + durable state for the R77 runner.

W1 may NOT edit r77/v21 files. This module imports them UNMODIFIED and
repairs the runner-level interface:

  UPSTREAM BUG (scripts/opencode_r77_advisor.py:108 + :178-185):
    start_bar = last_bar_idx + 1, then `start_bar >= len(df)` returns
    'nothing new' forever on a same-length shifted window. Watermark
    timestamps are saved but never used for suffix selection.
    FIX HERE: reconcile by MARKET + TIMESTAMP identity
    (symbol/interval/open_time), select ONLY unseen closed candles, map
    local inference indices to stable execution indices.
  (:190-209 positional raw_by_bar + iloc slicing assumes stable cache
  origin -> open_time identity mapping here.)
  (:69-71,180-181,213-214 direct write_text overwrites -> atomic
  temp+fsync+rename checkpoint + append-only journal + export rebuild.)
  (core:674-688 declared hashes, no byte check -> hash bytes on resume.)

Frozen policy only: AdvisorStrategy/execution imported, never reimplemented.
Advisory only: public klines GET, no keys, no orders, no scheduler, no cloud.

torch is imported before pandas (Windows DLL load-order rule).
"""
import torch  # noqa: F401  (torch truoc pandas: DLL load-order Windows host)

import argparse
import hashlib
import json
import math
import os
import sys
import time
from pathlib import Path

import pandas as pd

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
if str(_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(_ROOT / "scripts"))

import opencode_r77_advisor_core as core  # noqa: E402

ROLL_VERSION = "r80_roll/1"
# ROLL_STATE_VERSION unchanged: r80 checkpoints stay resume-compatible with
# r78_roll_state/1 envelopes; new exec_state/counts keys default on resume.
# Clean pre-r80 states (no gap-pause flags, counter indices consistent with
# the derived origin) resume; time-unstable pre-r80 gap states are REFUSED
# with an explicit message (see _ensure_origin_migrate).
ROLL_STATE_VERSION = "r78_roll_state/1"

# Timestamp-stable economic grid step (5m BTCUSDT candles).
GRID_STEP_SECONDS = 300

UPSTREAM_FIX_NOTES = [
    "scripts/opencode_r77_advisor.py:108 + :178-185 positional start_bar resume "
    "-> identity-based unseen selection (this module reconcile_window).",
    "scripts/opencode_r77_advisor.py:190-209 positional raw_by_bar/iloc -> "
    "map_inference_to_exec (this module).",
    "scripts/opencode_r77_advisor.py:69-71,180-181,213-214 direct write_text "
    "-> atomic_commit + journal + rebuild_missing_exports (this module).",
    "scripts/opencode_r77_advisor_core.py:674-688 declared hashes -> "
    "verify_identity_bytes (this module).",
    "CRASH-CONSISTENCY (r78-int4, ROLL v2): reconcile marks the full "
    "window seen BEFORE per-bar settle+commit, so a kill between commits "
    "orphaned settles (resume 'nothing new', outputs lost). resume() now "
    "flags seen-keys absent from committed bar_close_by_idx for "
    "deterministic replay with the ORIGINAL exec_idx (exactly-once).",
    "OBSERVATION-TIME (r79_roll/1): fresh bootstrap shadow was "
    "df['close_time'].iloc[0] (main fresh path), backdating observation so "
    "pre-observation inferences settled actionable LONG/SHORT intents and "
    "filled on historical bars (leader r78 repro: equity 99.98 at "
    "bootstrap). Fresh shadow is now the ACTUAL observed_at; ALL "
    "pre-observation inference is diagnostic-only (zero actionable intents, "
    "fills, gate consumption, funding, account PnL from historical warmup).",
    "MISSED-CLOCK (r79_roll/1): resume/catch-up decisions whose execution "
    "window already passed before actual availability are DIAGNOSTIC-only "
    "(choice: diagnostic-only, NO delayed-entry policy shipped; a 2h "
    "signal-age rule alone cannot authorize retroactive next-bar fills). "
    "Only decisions on the latest new bar of an ingest may be actionable; "
    "already-observed pending/open positions still settle causally through "
    "catch-up bars. No separately-versioned delayed-entry policy exists, so "
    "late placement is refused, never simulated retroactively.",
    "FEED-VALIDITY (r79_roll/1): new gaps pause post-gap bars (PAUSED, no "
    "economic settlement, replayable after verified backfill); ingests "
    "containing OHLC revisions force the whole ingest diagnostic-only "
    "(revised bytes must not reach inference silently); non-finite/forming "
    "bars are excluded from both settlement and the inference frame (never "
    "synthesized). Empty AND open portfolios covered; restored data "
    "recovers without duplicated outputs via identity replay.",
    "RAW-PROVENANCE (r79_roll/1): every ingest writes its own immutable "
    "raw_ingest_<ts>_<sha8>.parquet snapshot (never a write-once-shared "
    "file); each commit associates exactly the bytes consumed (sha256 + "
    "range); the append-only ingest_manifest.jsonl carries "
    "bootstrap/resume observation times + lineage (prev_sha, generation).",
    "ECONOMIC-CLOCK (r80_roll/1): execution-bar indices are "
    "timestamp-stable origin-anchored 5m grid steps "
    "(exec_idx = round((open - origin)/300s)). Same candle time -> same "
    "exec_idx across uninterrupted/chunked/duplicated/gapped-backfilled/"
    "restarted consumption, so pending expiry / holding timeout / control "
    "trace follow ACTUAL candle times. The r79 first-seen counter that "
    "allocated fresh indices to post-gap bars (and replayed backfill at "
    "NEW indices past the elapsed-index expiry) is removed; replay reuses "
    "the SAME stable idx. Gapless in-order runs reproduce 0..N-1 exactly.",
    "COMPLETE-VALIDITY (r80_roll/1): a gap stays unresolved until EVERY "
    "expected valid closed candle on the absolute 5m grid between its "
    "(after, before) boundaries is in the seen-valid set (the r79 ANY-seen-"
    "inside test that cleared a 3-bar gap on 1-bar partial backfill is "
    "removed). While any gap is unresolved, EVERY new row past the "
    "earliest divergence point stays PAUSED (nothing settles, preserving "
    "global time order for later backfill). Invalid OHLC/grid/close-time "
    "bars are never marked seen/settled.",
]

ROLL_CONFIG_DEFAULT = "configs/opencode_r80_roll.json"
ROLL_CONFIG_LEGACY = "configs/opencode_r79_roll.json"


# ------------------------------------------------------------- helpers ---
def _sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha_file(path: Path) -> str:
    return _sha_bytes(Path(path).read_bytes())


def candle_key(symbol: str, interval: str, open_iso: str) -> str:
    return f"{symbol}|{interval}|{open_iso}"


def ohlc_hash(row) -> str:
    body = "|".join(f"{float(row[k]):.8f}" for k in
                    ("open", "high", "low", "close", "volume"))
    return hashlib.sha256(body.encode()).hexdigest()[:16]


def _is_finite_row(row) -> bool:
    try:
        return all(math.isfinite(float(row[k])) for k in
                   ("open", "high", "low", "close", "volume"))
    except (TypeError, ValueError, KeyError):
        return False


def load_roll_config(path: str | Path | None = None) -> dict:
    p = _ROOT / (path or ROLL_CONFIG_DEFAULT)
    cfg = json.loads(p.read_text(encoding="utf-8"))
    tp = cfg.get("timeliness_policy", {})
    # Timeliness policy must be pre-specified in config BEFORE implementation
    # runs: refuse if N or rationale is missing.
    if (not isinstance(tp.get("stale_after_bars"), int)
            or tp["stale_after_bars"] <= 0 or not tp.get("rationale")):
        raise ValueError("REFUSED: timeliness_policy.stale_after_bars + "
                         "rationale must be pre-specified in config.")
    return cfg


# ---------------------------------------------------------- reconcile ---
def new_execution_state() -> dict:
    return {"seen": {}, "exec_counter": 0,
            "origin_open_iso": None,
            "last_settled_open_iso": None,
            "last_settled_close_iso": None,
            "revisions": [], "gaps": [],
            "validity": {"paused": False, "reason": None,
                          "since_observed_at": None,
                          "paused_exec_idxs": [],
                          "gap_boundaries": []},
            "bootstrap_observed_at": None,
            "ingest_ids": []}


def _origin_open(exec_state: dict) -> "pd.Timestamp | None":
    iso = exec_state.get("origin_open_iso")
    if not iso:
        return None
    return core._ts(iso)


def _stable_idx(origin: "pd.Timestamp", open_t: "pd.Timestamp") -> int:
    return int(round((core._ts(open_t) - core._ts(origin)
                      ).total_seconds() / GRID_STEP_SECONDS))


def _seen_open_set(exec_state: dict) -> set:
    opens = set()
    for key in (exec_state.get("seen") or {}):
        try:
            opens.add(core._ts(key.rsplit("|", 1)[1]))
        except (ValueError, IndexError, TypeError, AttributeError):
            continue
    return opens


def _expected_opens(after_iso: str, before_iso: str,
                    step_seconds: int = GRID_STEP_SECONDS) -> list:
    """Every expected valid closed-candle open strictly inside (after, before).

    Absolute grid enumeration: a gap resolves only when ALL of these are
    in the seen-valid set (complete validity; no ANY-inside shortcut).
    """
    after, before = core._ts(after_iso), core._ts(before_iso)
    step = pd.Timedelta(seconds=int(step_seconds))
    out, cur = [], after + step
    while cur < before:
        out.append(cur)
        cur += step
    return out


def _ensure_origin_migrate(exec_state: dict,
                           valid_opens: list | None = None) -> object:
    """Anchor (or migrate) the timestamp-stable origin of an exec_state.

    Fresh states anchor at the first valid open. Pre-r80 states without an
    origin migrate by deriving origin = min_seen_open - min_idx*300s and
    verifying EVERY seen key is consistent with it; pre-r80 states with
    gap-pause/counter-unstable indices are REFUSED explicitly (replay from
    the complete window instead). Within-r80 states (origin present) pass
    through untouched, including states with open gaps/paused flags.
    """
    if exec_state.get("origin_open_iso"):
        return core._ts(exec_state["origin_open_iso"])
    seen = exec_state.get("seen", {}) or {}
    pairs = []
    for key, val in seen.items():
        try:
            pairs.append((core._ts(key.rsplit("|", 1)[1]),
                          int((val or {}).get("exec_idx"))))
        except (ValueError, IndexError, TypeError, AttributeError):
            continue
    if not pairs:
        if not valid_opens:
            return None
        origin = min(core._ts(o) for o in valid_opens)
        exec_state["origin_open_iso"] = origin.isoformat()
        return origin
    validity = RollingAdvisor._ensure_validity(exec_state)
    dirty = (any(bool((sv or {}).get("uncommitted"))
                 or bool((sv or {}).get("paused"))
                 for sv in seen.values())
             or bool(validity.get("paused"))
             or bool(validity.get("unresolved_gaps"))
             or bool(exec_state.get("gaps")))
    min_idx = min(i for _, i in pairs)
    min_open = min(o for o, i in pairs if i == min_idx)
    origin = min_open - pd.Timedelta(seconds=GRID_STEP_SECONDS * min_idx)
    consistent = all(o == origin + pd.Timedelta(
        seconds=GRID_STEP_SECONDS * i) for o, i in pairs)
    if dirty or not consistent:
        raise ValueError(
            "REFUSED: pre-r80 checkpoint carries gap-pause or "
            "counter-compressed indices that are time-unstable "
            f"(consistent={consistent}, gap_state={dirty}). r80's "
            "timestamp-stable clock cannot adopt them: start an explicit "
            "new run or replay from the complete window.")
    exec_state["origin_open_iso"] = origin.isoformat()
    return origin


def _refresh_unresolved(exec_state: dict, extra_gaps: list) -> list:
    """Merge gap events; recompute each gap's missing set vs seen-valid.

    Returns the still-unresolved gaps, each carrying an explicit
    missing_opens list. Persists the merged view on validity so partial /
    out-of-order / overlapping backfills and restarts preserve the missing
    set. A gap with zero missing opens is resolved (dropped).
    """
    validity = RollingAdvisor._ensure_validity(exec_state)
    seen = _seen_open_set(exec_state)

    def _missing(g):
        try:
            expected = _expected_opens(g["after"], g["before"])
        except (ValueError, TypeError, KeyError, AttributeError):
            return None  # unparseable: keep as-is, never resolve
        return [o.isoformat() for o in expected if o not in seen]

    still = []
    covered: set = set()
    for g in validity.get("unresolved_gaps", []):
        missing = _missing(g)
        if missing is None:
            still.append(g)
            continue
        if missing:
            entry = {"after": g.get("after"), "before": g.get("before"),
                     "missing_bars": len(_expected_opens(g["after"],
                                                         g["before"])),
                     "missing_opens": missing}
            still.append(entry)
            covered.update(missing)
    known = {(g.get("after"), g.get("before")) for g in still}
    for g in (extra_gaps or []):
        if (g.get("after"), g.get("before")) in known:
            continue
        known.add((g.get("after"), g.get("before")))
        missing = _missing(g)
        if missing is None:
            still.append({"after": g.get("after"),
                          "before": g.get("before"),
                          "missing_bars": g.get("missing_bars")})
            continue
        if not missing:
            continue  # fully observed window jump: no gap at all
        if set(missing) <= covered:
            continue  # same hole, different anchor: keep one record
        still.append({"after": g.get("after"), "before": g.get("before"),
                      "missing_bars": len(_expected_opens(g["after"],
                                                          g["before"])),
                      "missing_opens": missing})
        covered.update(missing)
    validity["unresolved_gaps"] = still
    return still


def fresh_shadow_start(df: pd.DataFrame, observed_at: str) -> str:
    """Fresh-bootstrap observation start (r79_roll/1).

    Returns the ACTUAL observation instant. Pre-observation inference is
    diagnostic-only via the core shadow rule (decision_time <= shadow_start).
    The df argument is accepted for call-site symmetry/logging only and is
    NEVER used to backdate observation (the r78 bug was
    ``df['close_time'].iloc[0]`` here). Warmup may still prime read-only
    feature state, but moves no money or gates.
    """
    _ = df  # intentionally unused: observation is the fetch instant.
    return core._ts(observed_at).isoformat()


def _invalid_reason(open_t, close_t, row: dict) -> str | None:
    """r80 validity reason for a finite, closed bar (None == valid).

    Mirrors the core observe_bar reject conditions plus absolute-grid
    identity: OHLC consistency, volume>=0, close>open, close==open+300s,
    open on the absolute 5m grid. NaT/unparseable timestamps are invalid.
    Invalid bars must NEVER be marked seen/settled.
    """
    try:
        ot, ct = core._ts(open_t), core._ts(close_t)
    except (ValueError, TypeError, AttributeError):
        return "unparseable-timestamp"
    try:
        if pd.isna(ot) or pd.isna(ct):
            return "NaT-timestamp"
    except (ValueError, TypeError):
        return "NaT-timestamp"
    try:
        dur = (ct - ot).total_seconds()
    except (ValueError, TypeError):
        return "close-time-not-after-open"
    # Real 5m candles close at open+300s (synthetic) or open+300s-1ms
    # (Binance klines convention: close_time = open + interval - 1ms).
    if not (GRID_STEP_SECONDS - 1.0 <= dur <= GRID_STEP_SECONDS):
        return "close-time-not-5m-candle"
    try:
        if int(ot.value) % (GRID_STEP_SECONDS * 10 ** 9) != 0:
            return "off-5m-grid"
    except (ValueError, TypeError, AttributeError):
        return "off-5m-grid"
    try:
        o, h, lo, c, v = (float(row["open"]), float(row["high"]),
                           float(row["low"]), float(row["close"]),
                           float(row["volume"]))
    except (TypeError, ValueError, KeyError):
        return "non-numeric-OHLCV"
    if not (h >= lo and h >= o and h >= c and lo <= o and lo <= c
            and v >= 0):
        return "ohlc-inconsistent"
    return None


def sanitize_inference_frame(df: pd.DataFrame,
                             observed_at: str) -> tuple[pd.DataFrame, dict]:
    """Return the inference-safe frame: only closed, finite, valid bars.

    Drops forming bars (close_time > observed_at), non-finite
    OHLC/volume rows AND r80-invalid rows (bad OHLC/grid/close-time),
    sorted by open_time. Never synthesizes. The report counts dropped
    rows so callers can fail closed on contamination.
    """
    report = {"input_rows": int(len(df)) if df is not None else 0,
              "forming_dropped": 0, "nonfinite_dropped": 0,
              "invalid_dropped": 0, "output_rows": 0}
    if df is None or len(df) == 0:
        return df, report
    obs = core._ts(observed_at)
    work = df.copy()
    work["open_time"] = pd.to_datetime(work["open_time"], utc=True,
                                       errors="coerce")
    work["close_time"] = pd.to_datetime(work["close_time"], utc=True,
                                        errors="coerce")
    forming = work["close_time"] > obs
    report["forming_dropped"] = int(forming.sum())
    work = work.loc[~forming]
    finite_mask = work.apply(
        lambda r: _is_finite_row(
            {"open": r["open"], "high": r["high"], "low": r["low"],
             "close": r["close"], "volume": r["volume"]}), axis=1)
    report["nonfinite_dropped"] = int((~finite_mask).sum())
    work = work.loc[finite_mask]
    valid_mask = work.apply(
        lambda r: _invalid_reason(r["open_time"], r["close_time"],
                                  {"open": r["open"], "high": r["high"],
                                   "low": r["low"], "close": r["close"],
                                   "volume": r["volume"]}) is None, axis=1)
    report["invalid_dropped"] = int((~valid_mask).sum())
    work = work.loc[valid_mask].sort_values(
        "open_time").reset_index(drop=True)
    report["output_rows"] = int(len(work))
    return work, report


def write_raw_snapshot(df: pd.DataFrame, out: Path, observed_at: str,
                       kind: str, prev_sha: str | None,
                       generation: int) -> dict:
    """Write ONE immutable per-ingest raw snapshot; append manifest lineage.

    Never reuses a write-once-shared file: filename embeds the observation
    instant + content hash. Returns the artifact record (path/sha256/range)
    that the commit snapshot must reference EXACTLY (hash + range of the
    bytes consumed). Appends one line to the append-only
    ingest_manifest.jsonl with bootstrap/resume observation times + lineage.
    """
    import datetime as _dt
    # Serialize exactly the bytes consumed (never a shared live file).
    import io as _io
    buf = _io.BytesIO()
    df.to_parquet(buf, index=False)
    raw_bytes = buf.getvalue()
    sha = _sha_bytes(raw_bytes)
    stamp = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    name = f"raw_ingest_{stamp}_{sha[:8]}_g{generation}.parquet"
    out.mkdir(parents=True, exist_ok=True)
    (out / name).write_bytes(raw_bytes)
    n = int(len(df))
    if n:
        first_open = core._ts(df["open_time"].iloc[0]).isoformat()
        last_close = core._ts(df["close_time"].iloc[-1]).isoformat()
    else:
        first_open, last_close = None, None
    ingest_id = f"{stamp}-{sha[:8]}"
    manifest = {"ingest_id": ingest_id, "kind": kind,
                "observed_at": core._ts(observed_at).isoformat(),
                "path": name, "sha256": sha, "row_count": n,
                "first_open": first_open, "last_close": last_close,
                "prev_sha256": prev_sha, "generation": int(generation)}
    with open(out / "ingest_manifest.jsonl", "a",
              encoding="utf-8") as f:
        f.write(json.dumps(manifest, default=str) + "\n")
        f.flush()
        os.fsync(f.fileno())
    return {"path": name, "sha256": sha, "row_count": n,
            "first_open": first_open, "last_close": last_close,
            "ingest_id": ingest_id, "prev_sha256": prev_sha}


def reconcile_window(df: pd.DataFrame, symbol: str, interval: str,
                     observed_at: str, exec_state: dict,
                     expected_bar_seconds: int = 300,
                     market_of_rows: tuple | None = None) -> dict:
    """Select ONLY unseen closed candles by (symbol/interval/open_time).

    Returns dict with new_rows [(exec_idx, row_dict)], duplicates, revised,
    gaps, out_of_order, nonfinite, forming, market_mismatch, invalid, late.
    Never synthesizes missing bars. Positional-index modulo is FORBIDDEN:
    identity is absolute open_time; clock checks use core.on_grid
    (absolute 6h UTC grid).

    r80 economic clock: exec_idx is the timestamp-stable origin-anchored
    grid step (same candle time -> same idx across uninterrupted, chunked,
    duplicated, gapped/backfilled and restarted consumption). Replay after
    verified backfill reuses the SAME stable idx (the r79 fresh-index
    replay that expired pending past the elapsed-index window is removed).
    Invalid OHLC/grid/close-time bars are never marked seen/settled.
    """
    out: dict = {"new_rows": [], "duplicates": [], "revised": [],
                 "gaps": list(exec_state.get("gaps", [])),
                 "out_of_order": [], "nonfinite": [], "forming": [],
                 "market_mismatch": [], "revisions": list(
                     exec_state.get("revisions", [])),
                 "invalid": [], "late": []}
    if market_of_rows is not None:
        msym, mint = market_of_rows
        if msym != symbol or mint != interval:
            out["market_mismatch"].append(
                {"expected": f"{symbol}/{interval}",
                 "got": f"{msym}/{mint}"})
            return out
    if df is None or len(df) == 0:
        return out
    obs = core._ts(observed_at)
    work = df.copy()
    work["open_time"] = pd.to_datetime(work["open_time"], utc=True,
                                       errors="coerce")
    work["close_time"] = pd.to_datetime(work["close_time"], utc=True,
                                        errors="coerce")
    opens = list(work["open_time"])
    try:
        ordered = opens == sorted(opens)
    except TypeError:
        ordered = False
    if not ordered:
        out["out_of_order"].append(
            {"note": "input not sorted by open_time; sorted for processing",
             "n": len(work)})
    try:
        work = work.sort_values("open_time").reset_index(drop=True)
    except TypeError:
        pass
    seen = exec_state.setdefault("seen", {})
    # PASS 1: validate every row. Invalid/forming/non-finite rows are
    # categorized and NEVER marked seen/settled. Rows on already-seen
    # keys are deferred to PASS 2 FIRST: a revision (hash mismatch) on a
    # settled bar must surface as a revision event even when the incoming
    # bytes themselves break OHLC consistency (the settled record is kept
    # either way; validity gating applies to UNSEEN keys only).
    valid: list = []
    deferred: list = []
    for pos in range(len(work)):
        r = work.iloc[pos]
        try:
            floats = {"open": float(r["open"]), "high": float(r["high"]),
                      "low": float(r["low"]), "close": float(r["close"]),
                      "volume": float(r["volume"])}
        except (TypeError, ValueError, KeyError):
            out["invalid"].append({"open_time": None,
                                   "reason": "non-numeric-OHLCV"})
            continue
        try:
            open_t, close_t = core._ts(r["open_time"]), core._ts(
                r["close_time"])
            open_iso, close_iso = open_t.isoformat(), close_t.isoformat()
        except (ValueError, TypeError, AttributeError):
            out["invalid"].append({"open_time": None,
                                   "reason": "unparseable-timestamp"})
            continue
        row = {"open_time": open_t, "close_time": close_t, **floats}
        key = candle_key(symbol, interval, open_iso)
        if key in seen:
            deferred.append({"open_time": open_t, "close_time": close_t,
                             "open_iso": open_iso, "close_iso": close_iso,
                             "row": row, "hash": ohlc_hash(row)})
            continue
        if close_t > obs:
            out["forming"].append({"open_time": open_iso,
                                   "reason": "close_time > observed_at"})
            continue
        if not _is_finite_row(row):
            out["nonfinite"].append({"open_time": open_iso,
                                     "reason": "non-finite OHLC/volume"})
            continue
        bad = _invalid_reason(open_t, close_t, floats)
        if bad is not None:
            out["invalid"].append({"open_time": open_iso, "reason": bad})
            continue
        valid.append({"open_time": open_t, "close_time": close_t,
                      "open_iso": open_iso, "close_iso": close_iso,
                      "row": row, "hash": ohlc_hash(row)})
    valid.sort(key=lambda v: v["open_time"])
    origin = _ensure_origin_migrate(
        exec_state, [v["open_time"] for v in valid])
    if origin is None:
        exec_state["gaps"] = out["gaps"]
        exec_state["revisions"] = out["revisions"]
        return out
    # Gap detection over the FULL valid window (seen or not) so restarts
    # and overlapping windows preserve every missing range; plus the
    # leading jump vs the last economically-settled open (never bridge).
    events: list = []
    last_open = (core._ts(exec_state["last_settled_open_iso"])
                 if exec_state.get("last_settled_open_iso") else None)
    seq = [v["open_time"] for v in valid]
    if last_open is not None and seq:
        delta = (seq[0] - last_open).total_seconds()
        if delta > expected_bar_seconds * 1.5:
            n_missing = int(round(delta / expected_bar_seconds)) - 1
            events.append({"after": last_open.isoformat(),
                           "before": seq[0].isoformat(),
                           "missing_bars": max(n_missing, 1),
                           "note": "gap recorded; missing bars NOT "
                                   "synthesized"})
    for a, b in zip(seq, seq[1:]):
        try:
            delta = (b - a).total_seconds()
        except (ValueError, TypeError):
            continue
        if delta > expected_bar_seconds * 1.5:
            n_missing = int(round(delta / expected_bar_seconds)) - 1
            events.append({"after": a.isoformat(), "before": b.isoformat(),
                           "missing_bars": max(n_missing, 1),
                           "note": "gap recorded; missing bars NOT "
                                   "synthesized"})
    known_bounds = {(g.get("after"), g.get("before"))
                    for g in out["gaps"]}
    for ev in events:
        if (ev.get("after"), ev.get("before")) not in known_bounds:
            out["gaps"].append(ev)
            known_bounds.add((ev.get("after"), ev.get("before")))
    # Complete-validity pause derived BEFORE committing, so the settled
    # pointer never advances across unobserved price paths.
    still = _refresh_unresolved(exec_state, out["gaps"])
    diverge = min((core._ts(g["after"]) for g in still),
                  default=None)
    # PASS 2 (time order): duplicates / revisions / stable-idx new rows.
    # Crash-recovery replay (r78-int4): resume() flags seen-keys whose
    # settle outputs never committed. Flagged keys re-enter the new-row
    # path with the SAME timestamp-stable exec_idx, so re-settlement is
    # bit-identical to uninterrupted consumption. Unflagged seen-keys keep
    # duplicate/revised semantics (idempotent resume).
    max_idx = int(exec_state.get("exec_counter", 0))

    def _settle_candidate(v, is_replay: bool) -> None:
        nonlocal max_idx
        key = candle_key(symbol, interval, v["open_iso"])
        if is_replay:
            idx = _stable_idx(origin, v["open_time"])
            if idx != int(seen[key]["exec_idx"]):
                # Index moved under a replay key: fail closed, never
                # settle under a colliding economic position in time.
                out["late"].append(
                    {"open_time": v["open_iso"],
                     "reason": "stable-idx moved under replay key"})
                return
            if seen[key]["ohlc_hash"] != v["hash"]:
                incoming_bad = (
                    not _is_finite_row(v["row"])
                    or _invalid_reason(v["open_time"], v["close_time"],
                                       v["row"]) is not None)
                if bool(seen[key].get("paused")) and not incoming_bad:
                    ev = {"open_time": v["open_iso"],
                          "kept_hash": seen[key]["ohlc_hash"],
                          "incoming_hash": v["hash"],
                          "note": "OHLC revision on never-settled "
                                  "(paused/uncommitted) bar: accepted "
                                  "incoming bytes, still replays exactly "
                                  "once at the stable idx"}
                    out["revised"].append(ev)
                    out["revisions"].append(ev)
                else:
                    ev = {"open_time": v["open_iso"],
                          "kept_hash": seen[key]["ohlc_hash"],
                          "incoming_hash": v["hash"],
                          "note": "OHLC revision on crash-uncommitted bar: "
                                  "kept settled record, no re-settlement"}
                    out["revised"].append(ev)
                    out["revisions"].append(ev)
                    return
            seen[key] = {"exec_idx": idx, "ohlc_hash": v["hash"],
                         "close_iso": v["close_iso"]}
            out["new_rows"].append((idx, v["row"]))
            max_idx = max(max_idx, idx + 1)
            return
        # Unseen candle: late rows (at/before the settled pointer) would
        # settle out of time order -> fail closed, never seen/settled.
        if last_open is not None and v["open_time"] <= last_open:
            out["late"].append({"open_time": v["open_iso"],
                                "reason": "at/before settled pointer; "
                                          "refusing out-of-order settle"})
            return
        idx = _stable_idx(origin, v["open_time"])
        if idx < 0:
            out["late"].append({"open_time": v["open_iso"],
                                "reason": "before run origin; refusing"})
            return
        seen[key] = {"exec_idx": idx, "ohlc_hash": v["hash"],
                     "close_iso": v["close_iso"]}
        out["new_rows"].append((idx, v["row"]))
        max_idx = max(max_idx, idx + 1)

    for d in sorted(deferred, key=lambda v: v["open_time"]):
        key = candle_key(symbol, interval, d["open_iso"])
        if bool(seen[key].get("uncommitted")):
            continue  # replayed in time order below
        if seen[key]["ohlc_hash"] == d["hash"]:
            out["duplicates"].append({"open_time": d["open_iso"]})
        else:
            ev = {"open_time": d["open_iso"],
                  "kept_hash": seen[key]["ohlc_hash"],
                  "incoming_hash": d["hash"],
                  "note": "OHLC revision on settled bar: kept settled "
                          "record, no re-settlement"}
            out["revised"].append(ev)
            out["revisions"].append(ev)
    timeline = sorted(
        valid + [d for d in deferred if bool(seen[candle_key(
            symbol, interval, d["open_iso"])].get("uncommitted"))],
        key=lambda v: v["open_time"])
    for v in timeline:
        key = candle_key(symbol, interval, v["open_iso"])
        _settle_candidate(v, is_replay=bool(key in seen))
    out["new_rows"].sort(key=lambda pair: pair[0])
    exec_state["exec_counter"] = max_idx
    # The settled pointer advances only over bars that are NOT paused
    # (paused bars are replayed after verified backfill, in time order).
    advanced = last_open
    for v in timeline:
        if diverge is None or v["open_time"] <= diverge:
            if advanced is None or v["open_time"] > advanced:
                advanced = v["open_time"]
    if advanced is not None:
        exec_state["last_settled_open_iso"] = advanced.isoformat()
        try:
            exec_state["last_settled_close_iso"] = (
                advanced + pd.Timedelta(
                    seconds=int(expected_bar_seconds))).isoformat()
        except (ValueError, TypeError):
            pass
    exec_state["gaps"] = out["gaps"]
    exec_state["revisions"] = out["revisions"]
    return out


def map_inference_to_exec(raw_rows: list[dict], df: pd.DataFrame,
                          symbol: str, interval: str,
                          exec_state: dict) -> dict[int, dict]:
    """Map LOCAL inference bar_index -> STABLE execution index via open_time.

    raw_rows use local positional bar_index into df. Stability comes from the
    (symbol/interval/open_time) identity recorded in exec_state['seen'].
    Unknown keys (no stable index) are dropped, never guessed.
    """
    mapped: dict[int, dict] = {}
    if not raw_rows:
        return mapped
    work = df.copy()
    work["open_time"] = pd.to_datetime(work["open_time"], utc=True)
    seen = exec_state.get("seen", {})
    for r in raw_rows:
        if r.get("status") not in ("READY_RAW", None) and "bar_index" not in r:
            continue
        bi = r.get("bar_index")
        if bi is None or int(bi) < 0 or int(bi) >= len(work):
            continue
        open_iso = core._ts(work["open_time"].iloc[int(bi)]).isoformat()
        key = candle_key(symbol, interval, open_iso)
        if key in seen:
            mapped[int(seen[key]["exec_idx"])] = r
    return mapped


def is_stale(decision_time_iso: str, observed_at: str,
             stale_after_bars: int, bar_seconds: int = 300) -> bool:
    age_s = (core._ts(observed_at) - core._ts(decision_time_iso)
             ).total_seconds()
    return age_s > stale_after_bars * bar_seconds


# ------------------------------------------------- identity verify ---
def collect_identity_files(roll_cfg: dict, advisor_cfg: dict,
                           spec: dict) -> list[str]:
    files = list(roll_cfg.get("identity_verification", {}).get(
        "pinned_files", []))
    advisor_rel = roll_cfg.get("advisor_config",
                               "configs/opencode_r77_advisor.json")
    if advisor_rel not in files:
        files.append(advisor_rel)
    prespec_rel = advisor_cfg.get("frozen_reference", {}).get(
        "inference_prespec", "configs/opencode_r76_infer.json")
    if prespec_rel not in files and prespec_rel:
        files.append(prespec_rel)
    for p in spec.get("checkpoints", {}).get("paths", []):
        if p not in files:
            files.append(p)
    for m in spec.get("calibrators", {}).get("maps", {}).values():
        mp = m.get("path") if isinstance(m, dict) else m
        if mp and mp not in files:
            files.append(mp)
    return files


def hash_identity_bytes(roll_cfg: dict, advisor_cfg: dict,
                        spec: dict) -> dict[str, str]:
    """Hash ACTUAL file bytes (never accept declared hashes). Missing model
    files fail closed with a named field (no stub substitution)."""
    out: dict[str, str] = {}
    for rel in collect_identity_files(roll_cfg, advisor_cfg, spec):
        p = _ROOT / rel
        if not p.exists():
            # Source/config pins must exist; model artifacts fail closed.
            raise FileNotFoundError(f"identity file missing: {rel} "
                                    "(refusing; no stub substitution)")
        out[rel] = sha_file(p)
    return out


def verify_identity_bytes(stored: dict[str, str],
                          current: dict[str, str]) -> None:
    for k, v in current.items():
        if stored.get(k) != v:
            raise ValueError(f"identity change on resume: {k} "
                             f"({stored.get(k)} -> {v}) (refusing; start an "
                             "explicit new run).")
    for k in stored:
        if k not in current:
            raise ValueError(f"identity change on resume: {k} removed "
                             "(refusing).")


# ------------------------------------------------- durable state ---
def _atomic_write_json(path: Path, obj: dict) -> None:
    tmp = path.with_suffix(path.suffix + f".tmp-{os.getpid()}")
    tmp.write_text(json.dumps(obj, indent=1, default=str),
                   encoding="utf-8")
    with open(tmp, "ab") as f:
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def _read_current(out: Path) -> int | None:
    cur = out / "CURRENT"
    if not cur.exists():
        return None
    try:
        return int(cur.read_text(encoding="utf-8").strip())
    except (ValueError, OSError):
        return None


def _write_current(out: Path, gen: int) -> None:
    tmp = out / f"CURRENT.tmp-{os.getpid()}"
    tmp.write_text(str(gen), encoding="utf-8")
    with open(tmp, "ab") as f:
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, out / "CURRENT")


def _seen_opens(exec_state: dict) -> list:
    opens = []
    for key in (exec_state.get("seen") or {}):
        try:
            opens.append(core._ts(key.rsplit("|", 1)[1]))
        except (ValueError, IndexError):
            continue
    return opens


def apply_validity_pause(advisor, rec: dict, new_gaps: list,
                         observed_at: str) -> set[int]:
    """r80 complete-validity pause (fail closed, no synthesis, no bridge).

    A gap stays UNRESOLVED until EVERY expected valid closed candle on the
    absolute 5m grid inside its missing (after, before) range is present
    in the seen-valid set (or the run is explicitly censored/invalid).
    Partial, out-of-order and overlapping backfills, repeated pauses and
    multiple restarts preserve the missing set (explicit missing_opens per
    gap) and positions. While any gap is unresolved, EVERY new row past
    the earliest divergence point stays PAUSED: no economic settlement
    (never settle past, or inside, a still-missing price path, and never
    settle backfill out of time order). Paused bars replay deterministically
    after verified backfill with the SAME timestamp-stable exec_idx
    (exactly-once: identity map + uncommitted flags, no duplicated
    outputs). Empty AND open portfolios are both covered: with an empty
    book nothing can move, but the pause still applies so no actionable
    intent is ever armed across a gap. Restored (backfilled) data recovers
    by resuming with the complete window.
    """
    validity = RollingAdvisor._ensure_validity(advisor.exec_state)
    still_open = _refresh_unresolved(advisor.exec_state, new_gaps)
    paused: set[int] = set()
    if still_open:
        try:
            diverge = min(core._ts(g["after"]) for g in still_open)
        except (ValueError, TypeError, KeyError):
            diverge = None
        for exec_idx, row in rec["new_rows"]:
            try:
                if diverge is None or core._ts(
                        row["open_time"]) > diverge:
                    paused.add(int(exec_idx))
            except (ValueError, TypeError, KeyError, AttributeError):
                paused.add(int(exec_idx))
        validity.update({
            "paused": True,
            "reason": f"gap-unresolved: {len(still_open)} gap(s); "
                      f"{len(paused)} bar(s) paused",
            "since_observed_at": validity.get("since_observed_at") or
                                 core._ts(observed_at).isoformat(),
            "paused_exec_idxs": sorted(paused),
            "gap_boundaries": [g.get("before") for g in still_open],
            "unresolved_gaps": still_open,
        })
        advisor._journal({"t": "validity-pause",
                          "observed_at": observed_at,
                          "new_gaps": new_gaps,
                          "unresolved_gaps": still_open,
                          "paused_exec_idxs": sorted(paused)})
    else:
        if validity.get("paused"):
            advisor._journal({"t": "validity-resumed",
                              "observed_at": observed_at,
                              "note": "all gaps backfilled; pause lifted"})
        validity.update({"paused": False, "reason": None,
                         "since_observed_at": None,
                         "paused_exec_idxs": [],
                         "gap_boundaries": [],
                         "unresolved_gaps": []})
    return paused


class RollingAdvisor:
    """Rolling wrapper around core.AdvisorStrategy with durable state.

    Owns: strategy + exec_state (identity map) + generation checkpoint +
    append-only journal + exports. Bootstrap rule: decision_time <=
    shadow_start -> DIAGNOSTIC-only (gates untouched), inherited from core.
    Staleness: decisions older than N bars -> DIAGNOSTIC-only (this layer).
    """

    def __init__(self, advisor_cfg: dict, roll_cfg: dict, spec: dict,
                 out: Path, symbol: str, interval: str):
        self.advisor_cfg = advisor_cfg
        self.roll_cfg = roll_cfg
        self.spec = spec
        self.out = out
        self.symbol = symbol
        self.interval = interval
        self.stale_after = int(roll_cfg["timeliness_policy"]
                               ["stale_after_bars"])
        self.strategy = core.AdvisorStrategy(advisor_cfg, n_bars=None)
        self.strategy._identity = self.strategy.identity_block(
            advisor_cfg, spec)
        self.exec_state = new_execution_state()
        self.identity_bytes = hash_identity_bytes(
            roll_cfg, advisor_cfg, spec)
        self.generation = 0
        self.journal_lines = 0
        self.counts = {"settled": 0, "duplicates": 0, "revised": 0,
                       "gaps": 0, "stale_forced_diagnostic": 0,
                       "missed_clock_diagnostic": 0,
                       "revision_forced_diagnostic": 0,
                       "paused_bars": 0, "invalid_dropped": 0,
                       "forming": 0, "nonfinite": 0, "market_mismatch": 0,
                       "out_of_order": 0}
        self.inference_calls = 0

    @staticmethod
    def _ensure_counts(counts: dict) -> dict:
        for k in ("settled", "duplicates", "revised", "gaps",
                  "stale_forced_diagnostic", "missed_clock_diagnostic",
                  "revision_forced_diagnostic", "paused_bars",
                  "invalid_dropped", "forming", "nonfinite",
                  "market_mismatch", "out_of_order"):
            counts.setdefault(k, 0)
        return counts

    @staticmethod
    def _ensure_validity(exec_state: dict) -> dict:
        v = exec_state.setdefault("validity", {})
        v.setdefault("paused", False)
        v.setdefault("reason", None)
        v.setdefault("since_observed_at", None)
        v.setdefault("paused_exec_idxs", [])
        v.setdefault("gap_boundaries", [])
        v.setdefault("unresolved_gaps", [])
        exec_state.setdefault("bootstrap_observed_at", None)
        exec_state.setdefault("ingest_ids", [])
        return v

    # -- lifecycle --
    def begin(self, shadow_start_iso: str, observed_at: str) -> None:
        self.strategy.begin_observation(shadow_start_iso, observed_at)
        RollingAdvisor._ensure_validity(self.exec_state)
        if not self.exec_state.get("bootstrap_observed_at"):
            self.exec_state["bootstrap_observed_at"] = core._ts(
                observed_at).isoformat()

    def _force_diagnostic(self, exec_idx: int, row: dict,
                            raw: dict, observed_at: str, reason: str,
                            counter: str) -> dict:
        """Force one READY_RAW decision to DIAGNOSTIC-only (r79 miss/clock,
        staleness, revision-contamination share this path).

        Gates untouched; the bar still settles economically WITHOUT the
        decision so already-observed pending/open positions advance causally
        through catch-up bars (no silent rewrite of historical fills).
        """
        self.counts[counter] = self.counts.get(counter, 0) + 1
        self.strategy.counters["diagnostic_rows"] += 1
        self.strategy.diagnostics.append({
            "status": core.STATUS_DIAGNOSTIC,
            "observed_at": observed_at,
            "decision_time": str(raw["decision_time"]),
            "bar_time": core._ts(row["close_time"]).isoformat(),
            "iso4_raw_action": raw.get("iso4_raw_action"),
            "vote_confirmed": bool(raw.get("vote_confirmed")),
            "note": reason})
        bar = {"open_time": row["open_time"],
               "close_time": row["close_time"], "open": row["open"],
               "high": row["high"], "low": row["low"],
               "close": row["close"], "volume": row["volume"]}
        st = self.strategy.observe_bar(exec_idx, bar, None, observed_at)
        # observe_bar counted OFF_CLOCK; keep our diagnostic mark:
        status = {"status": core.STATUS_DIAGNOSTIC,
                  "observed_at": observed_at,
                  "bar_time": st["bar_time"]}
        self._journal({"t": "diagnostic", "exec_idx": exec_idx,
                       "bar_time": st["bar_time"], "reason": reason})
        self.counts["settled"] += 1
        return status

    def settle_new(self, new_rows: list, raw_by_exec: dict,
                   observed_at: str, batch_latest_close_iso: str | None = None,
                   paused_exec: set[int] | None = None,
                   revision_contaminated: bool = False) -> list[dict]:
        """Settle new bars. r79 guards (all default-off for backward compat):

        batch_latest_close_iso: only decisions ON the latest new bar may be
          actionable; earlier catch-up decisions are missed-clock
          DIAGNOSTIC-only (their entry window passed before availability; no
          delayed-entry policy exists in r79, so retroactive fills refuse).
        paused_exec: exec_idxs at/after a new gap boundary. PAUSED: no
          economic settlement at all (never settle through unobserved price
          paths); the seen-key is flagged uncommitted for deterministic
          replay after verified backfill (exactly-once, no duplicates).
        revision_contaminated: ingest contains OHLC revisions on settled
          bars, so the inference frame is suspect -> whole ingest
          DIAGNOSTIC-only (revised bytes never reach inference silently).
        """
        paused_exec = set(paused_exec or ())
        latest_close = (core._ts(batch_latest_close_iso)
                        if batch_latest_close_iso else None)
        statuses = []
        for exec_idx, row in new_rows:
            if exec_idx in paused_exec:
                self.counts["paused_bars"] = self.counts.get(
                    "paused_bars", 0) + 1
                # Flag for deterministic replay with the ORIGINAL exec_idx
                # once verified backfill arrives (resume() also flags
                # seen-keys absent from committed bar_close_by_idx).
                for _k, _v in self.exec_state.get("seen", {}).items():
                    try:
                        if int((_v or {}).get("exec_idx")) == int(exec_idx):
                            _v["uncommitted"] = True
                            # r79: mark never-settled so a later backfill
                            # replay takes a fresh time-ordered exec_idx
                            # (reconcile gap-pause exception) instead of
                            # reusing this one out of order.
                            _v["paused"] = True
                    except (TypeError, ValueError):
                        continue
                self._journal({"t": "paused", "exec_idx": exec_idx,
                               "bar_time": core._ts(
                                   row["close_time"]).isoformat(),
                               "reason": "gap-unresolved: no economic "
                                         "settlement through unobserved "
                                         "price paths"})
                statuses.append(
                    {"status": "PAUSED", "observed_at": observed_at,
                     "bar_time": core._ts(
                         row["close_time"]).isoformat()})
                continue
            bar = {"open_time": row["open_time"],
                   "close_time": row["close_time"], "open": row["open"],
                   "high": row["high"], "low": row["low"],
                   "close": row["close"], "volume": row["volume"]}
            raw = raw_by_exec.get(exec_idx)
            if raw is not None and raw.get("status") == "READY_RAW":
                if revision_contaminated:
                    statuses.append(self._force_diagnostic(
                        exec_idx, row, raw, observed_at,
                        "revision-contaminated ingest: DIAGNOSTIC-only, "
                        "revised bytes never reach inference silently",
                        "revision_forced_diagnostic"))
                    continue
                # Missed-clock binds BEFORE the 24-bar staleness outer bound:
                # a decision whose bar is not the latest new bar already had
                # its entry window pass before actual availability.
                if (latest_close is not None
                        and core._ts(row["close_time"]) < latest_close):
                    statuses.append(self._force_diagnostic(
                        exec_idx, row, raw, observed_at,
                        "missed-clock catch-up: decision bar precedes the "
                        "latest new bar; entry window passed before "
                        "availability; DIAGNOSTIC-only (no delayed-entry "
                        "policy in r79)",
                        "missed_clock_diagnostic"))
                    continue
                # Bounded timeliness: stale catch-up is DIAGNOSTIC-only.
                if is_stale(str(raw["decision_time"]), observed_at,
                            self.stale_after):
                    statuses.append(self._force_diagnostic(
                        exec_idx, row, raw, observed_at,
                        f"stale catch-up > {self.stale_after} bars: "
                        "DIAGNOSTIC-only, never a timely alert",
                        "stale_forced_diagnostic"))
                    continue
            st = self.strategy.observe_bar(exec_idx, bar, raw, observed_at)
            statuses.append(st)
            self.counts["settled"] += 1
            self._journal({"t": "status", "exec_idx": exec_idx,
                           "status": st["status"],
                           "bar_time": st["bar_time"]})
        return statuses

    # -- journal (append-only) --
    def _journal(self, rec: dict) -> None:
        self.out.mkdir(parents=True, exist_ok=True)
        with open(self.out / "journal.jsonl", "a",
                  encoding="utf-8") as f:
            f.write(json.dumps(rec, default=str) + "\n")
            f.flush()
            os.fsync(f.fileno())
        self.journal_lines += 1

    # -- checkpoint (atomic, generational) --
    def snapshot_envelope(self) -> dict:
        snap = self.strategy.snapshot_state(self.strategy._identity)
        body = {"version": ROLL_STATE_VERSION, "roll_version": ROLL_VERSION,
                "generation": self.generation + 1,
                "prev_hash": self._last_checkpoint_hash(),
                "identity_bytes": self.identity_bytes,
                "symbol": self.symbol, "interval": self.interval,
                "exec_state": self.exec_state,
                "counts": dict(self.counts),
                "journal_lines": self.journal_lines,
                "strategy": snap}
        body["envelope_hash"] = _sha_bytes(
            json.dumps({k: body[k] for k in
                        ("generation", "prev_hash", "identity_bytes",
                         "exec_state", "strategy")},
                       sort_keys=True, default=str).encode())
        return body

    def _last_checkpoint_hash(self) -> str | None:
        if self.generation <= 0:
            return None
        p = self.out / f"checkpoint-{self.generation}.json"
        if not p.exists():
            return None
        try:
            return _sha_bytes(p.read_bytes())
        except OSError:
            return None

    def atomic_commit(self) -> int:
        self.out.mkdir(parents=True, exist_ok=True)
        env = self.snapshot_envelope()
        _atomic_write_json(
            self.out / f"checkpoint-{env['generation']}.json", env)
        _write_current(self.out, env["generation"])
        self.generation = env["generation"]
        self._journal({"t": "commit", "generation": self.generation,
                       "envelope_hash": env["envelope_hash"]})
        return self.generation

    @classmethod
    def resume(cls, out: Path, roll_cfg: dict, advisor_cfg: dict,
               spec: dict) -> "RollingAdvisor":
        obj = cls.__new__(cls)
        obj.advisor_cfg, obj.roll_cfg, obj.spec = (
            advisor_cfg, roll_cfg, spec)
        obj.out = out
        obj.symbol = advisor_cfg["feed"]["symbol"]
        obj.interval = advisor_cfg["feed"]["interval"]
        obj.stale_after = int(roll_cfg["timeliness_policy"]
                              ["stale_after_bars"])
        current = hash_identity_bytes(roll_cfg, advisor_cfg, spec)
        gen = _read_current(out)
        if gen is None:
            # CURRENT missing/corrupt -> try highest verified generation.
            cands = sorted(
                (int(p.stem.split("-")[1]) for p in
                 out.glob("checkpoint-*.json")
                 if p.stem.split("-")[1].isdigit()),
                reverse=True)
            if not cands:
                raise ValueError("REFUSED: corrupt/missing CURRENT and no "
                                 "checkpoint generation found "
                                 f"(dir={out}).")
            gen = cands[0]
        env = None
        tried = []
        for g in ([gen] + [c for c in
                           sorted((int(p.stem.split("-")[1]) for p in
                                   out.glob("checkpoint-*.json")
                                   if p.stem.split("-")[1].isdigit()),
                                  reverse=True) if c != gen]):
            p = out / f"checkpoint-{g}.json"
            try:
                cand = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, ValueError) as e:
                tried.append(f"{g}:unreadable({e})")
                continue
            # Verify envelope hash before trusting bytes.
            expect = _sha_bytes(
                json.dumps({k: cand[k] for k in
                            ("generation", "prev_hash", "identity_bytes",
                             "exec_state", "strategy")},
                           sort_keys=True, default=str).encode())
            if cand.get("envelope_hash") != expect:
                tried.append(f"{g}:hash-mismatch")
                continue
            env = cand
            gen = g
            break
        if env is None:
            raise ValueError("REFUSED: corrupt/truncated state (tried "
                             f"{tried}); no verified generation. Start an "
                             "explicit new run.")
        verify_identity_bytes(env.get("identity_bytes", {}), current)
        if env.get("version") != ROLL_STATE_VERSION:
            raise ValueError(f"state version mismatch: {env.get('version')} "
                             "(refusing).")
        obj.strategy = core.AdvisorStrategy(advisor_cfg, n_bars=None)
        obj.strategy._identity = obj.strategy.identity_block(
            advisor_cfg, spec)
        obj.strategy.restore_state(env["strategy"],
                                   obj.strategy._identity)
        obj.exec_state = env["exec_state"]
        # r80 timestamp-stable clock: anchor/migrate the origin. Clean
        # pre-r80 states adopt the derived origin; time-unstable pre-r80
        # gap-pause states are REFUSED explicitly (replay complete window).
        _ensure_origin_migrate(obj.exec_state)
        obj.identity_bytes = current
        obj.generation = int(env["generation"])
        obj.counts = RollingAdvisor._ensure_counts(
            dict(env.get("counts", {})))
        RollingAdvisor._ensure_validity(obj.exec_state)
        obj.inference_calls = 0
        # WAL recovery: truncate the append-only journal to the committed
        # generation's journal_lines, discarding the uncommitted tail (status
        # lines settled after the last commit + trailing commit markers).
        # Resume then re-settles deterministically -> exactly-once.
        jl = out / "journal.jsonl"
        keep = int(env.get("journal_lines", 0))
        if jl.exists() and keep >= 0:
            with open(jl, "r", encoding="utf-8") as f:
                lines = f.readlines()
            if len(lines) > keep:
                with open(jl, "w", encoding="utf-8") as f:
                    f.writelines(lines[:keep])
                    f.flush()
                    os.fsync(f.fileno())
                obj.journal_lines = keep
            else:
                obj.journal_lines = len(lines)
        else:
            obj.journal_lines = 0
        # Crash-consistency repair (r78-int4): reconcile marks the whole
        # window seen BEFORE per-bar settle+commit, so a kill between
        # commits leaves seen-keys whose settle outputs were truncated from
        # the journal and rolled back with the strategy state. Flag
        # seen-keys absent from the COMMITTED strategy state
        # (bar_close_by_idx) so reconcile re-emits them deterministically
        # with their original exec_idx -> exactly-once resume. Keys already
        # committed stay untouched (identical resume stays "nothing new").
        committed_idx = set(
            getattr(obj.strategy, "bar_close_by_idx", {}) or {})
        n_replay = 0
        for _k, _v in obj.exec_state.get("seen", {}).items():
            try:
                _idx = int((_v or {}).get("exec_idx"))
            except (TypeError, ValueError):
                continue
            if _idx not in committed_idx and not (_v or {}).get(
                    "uncommitted"):
                _v["uncommitted"] = True
                n_replay += 1
        if n_replay:
            obj._journal({"t": "resume-replay", "generation": gen,
                          "uncommitted_bars": n_replay})
        # Repair CURRENT pointer if it was corrupt/stale.
        _write_current(out, obj.generation)
        return obj

    # -- exports (rebuildable from journal + strategy state) --
    def write_exports(self, snapshot: dict) -> None:
        exp = self.out / "exports"
        exp.mkdir(parents=True, exist_ok=True)

        def _frame(rows, columns):
            if len(rows):
                return pd.DataFrame(rows)
            return pd.DataFrame(columns=columns)
        _frame(self.strategy.decision_log,
               ["status", "action"]).to_csv(
            exp / "decisions.csv", index=False)
        _frame(self.strategy.diagnostics,
               ["status"]).to_csv(exp / "diagnostics.csv", index=False)
        _frame(list(self.strategy.intents.values()),
               core.AdvisorStrategy.INTENT_COLUMNS).to_csv(
            exp / "intents.csv", index=False)
        (exp / "snapshot.json").write_text(
            json.dumps(snapshot, indent=1, default=str), encoding="utf-8")
        (self.out / "snapshot.json").write_text(
            json.dumps(snapshot, indent=1, default=str), encoding="utf-8")

    def rebuild_missing_exports(self, snapshot: dict | None = None) -> bool:
        """Rebuild missing exports from committed state WITHOUT re-emitting
        (exactly-once: deterministic IDs already journaled; no new intents,
        alerts, fills or decisions are created here). Returns True if a
        rebuild happened."""
        exp = self.out / "exports"
        need = ["decisions.csv", "diagnostics.csv", "intents.csv",
                "snapshot.json"]
        if exp.exists() and all((exp / n).exists() for n in need):
            return False
        snap = snapshot or self.build_snapshot(
            first_open_iso=None, last_close_iso=None, n_rows=None,
            raw_artifact=None, observed_at=None, source=None,
            status_counts=None, inference_evidence=None)
        self.write_exports(snap)
        self._journal({"t": "export-rebuild",
                       "generation": self.generation})
        return True

    # -- snapshot/provenance --
    def build_snapshot(self, first_open_iso, last_close_iso, n_rows,
                       raw_artifact, observed_at, source, status_counts,
                       inference_evidence, observation_times=None,
                       lineage=None, validity=None,
                       inference_sanitized=None) -> dict:
        dec = self.strategy.decision_log
        n_action = sum(1 for d in dec if d.get("status") == core.STATUS_READY
                       and d.get("action") in ("LONG", "SHORT"))
        n_diag = len(self.strategy.diagnostics) + sum(
            1 for d in dec if d.get("status") == core.STATUS_DIAGNOSTIC)
        return {
            "roll_version": ROLL_VERSION, "exploratory": True,
            "live_orders": False,
            "symbol": self.symbol, "interval": self.interval,
            "first_candle_open": first_open_iso,
            "last_candle_close": last_close_iso,
            "row_count": n_rows,
            "raw_candle_artifact": raw_artifact,
            "fetched_at": source.get("fetched_at") if source else None,
            "observed_at": observed_at,
            "observation_times": observation_times or {
                "bootstrap_observed_at": self.exec_state.get(
                    "bootstrap_observed_at"),
                "observed_at": observed_at},
            "lineage": lineage or {
                "ingest_ids": list(self.exec_state.get("ingest_ids", []))},
            "validity": validity if validity is not None else dict(
                self.exec_state.get("validity", {})),
            "source": source,
            "checkpoint_hashes": {
                k: v for k, v in self.identity_bytes.items()
                if "checkpoint" in k or "model" in k
                or "seed" in k or "fold" in k},
            "identity_bytes": self.identity_bytes,
            "generation": self.generation,
            "status_counts": status_counts or {},
            "inference_evidence": inference_evidence or {},
            "inference_sanitized": inference_sanitized or {},
            "diagnostic_count": n_diag,
            "actionable_count": n_action,
            "counts": dict(self.counts),
            "upstream_fix_notes": UPSTREAM_FIX_NOTES,
        }


# ------------------------------------------------------------- CLI ---
def _load_candles_replay(path: Path) -> pd.DataFrame:
    df = pd.read_parquet(path)
    need = {"open_time", "open", "high", "low", "close", "volume",
            "close_time"}
    missing = need - set(df.columns)
    if missing:
        raise ValueError(f"replay candles lack {sorted(missing)} (refusing).")
    df = df.sort_values("open_time").reset_index(drop=True)
    df["open_time"] = pd.to_datetime(df["open_time"], utc=True)
    df["close_time"] = pd.to_datetime(df["close_time"], utc=True)
    return df


def main() -> None:
    ap = argparse.ArgumentParser(
        description="R78 W1 rolling advisory runner (PAPER ONLY).")
    ap.add_argument("--mode", choices=("replay", "fresh"), required=True)
    ap.add_argument("--config", default="configs/opencode_r78_roll.json")
    ap.add_argument("--candles", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--persist-every", type=int, default=50)
    ap.add_argument("--sleep-per-bar", type=float, default=0.0,
                    help="test hook: slow the settle loop for kill tests")
    ap.add_argument("--stub-infer", action="store_true",
                    help="test hook: deterministic stub raw rows on grid bars "
                         "(never in production evidence)")
    ap.add_argument("--max-bars", type=int, default=None)
    a = ap.parse_args()

    roll_cfg = load_roll_config(a.config)
    advisor_cfg = json.loads(
        (_ROOT / roll_cfg["advisor_config"]).read_text(encoding="utf-8"))
    if advisor_cfg.get("allow_live_orders", True):
        raise SystemExit("REFUSED: allow_live_orders must stay false.")
    import opencode_r76_infer as r76  # noqa: E402
    spec = r76.load_prespec()
    out = _ROOT / a.out
    symbol, interval = (advisor_cfg["feed"]["symbol"],
                        advisor_cfg["feed"]["interval"])

    if a.resume:
        advisor = RollingAdvisor.resume(out, roll_cfg, advisor_cfg, spec)
        print(f"[{ROLL_VERSION}] resume: identity OK, "
              f"generation={advisor.generation}")
    else:
        if out.exists():
            raise FileExistsError(f"Refusing to overwrite: {out}")
        out.mkdir(parents=True, exist_ok=True)
        advisor = RollingAdvisor(advisor_cfg, roll_cfg, spec, out,
                                 symbol, interval)

    if a.mode == "replay":
        if a.candles == "live":
            raise SystemExit("REFUSED: replay needs a candles parquet.")
        df = _load_candles_replay(_ROOT / a.candles)
        observed_at = pd.Timestamp.now(tz="UTC").isoformat()
        fetched_at = None
        if a.max_bars:
            df = df.iloc[:a.max_bars].reset_index(drop=True)
        raw_artifact = {"kind": "REHEARSAL-NOT-LIVE",
                        "candles": str(a.candles)}
    else:
        if a.candles != "live":
            raise SystemExit("REFUSED: fresh ingests live public klines only.")
        closed, prov = core.fetch_warmup_paginated(
            symbol=symbol, interval=interval)
        df = pd.DataFrame(closed)
        if len(df):
            df = df.sort_values("open_time").reset_index(drop=True)
            df["open_time"] = pd.to_datetime(df["open_time"], utc=True)
            df["close_time"] = pd.to_datetime(df["close_time"], utc=True)
        observed_at = prov["fetched_at"]
        fetched_at = prov["fetched_at"]
        raw_artifact = {"kind": "FRESH-OBSERVATION", "provenance": prov}

    # Per-ingest IMMUTABLE raw provenance (r79): every ingest writes its
    # own snapshot file (never a write-once-shared raw_candles.parquet).
    # Each commit below associates exactly these bytes (sha256 + range).
    kind = ("FRESH-OBSERVATION" if a.mode == "fresh"
            else "REHEARSAL-NOT-LIVE")
    prev_sha = None
    try:
        lines = (out / "ingest_manifest.jsonl").read_text(
            encoding="utf-8").splitlines()
        if lines:
            prev_sha = json.loads(lines[-1]).get("sha256")
    except (OSError, ValueError):
        prev_sha = None
    raw_snap = write_raw_snapshot(df, out, observed_at, kind, prev_sha,
                                  advisor.generation + 1)
    raw_hash = raw_snap["sha256"]
    advisor.exec_state.setdefault("ingest_ids", []).append(
        raw_snap["ingest_id"])

    if not a.resume:
        # r79: observation starts at the ACTUAL observed_at. All
        # pre-observation inference is diagnostic-only (zero actionable
        # intents, fills, gate consumption, funding, account PnL from
        # historical warmup). The r78 df['close_time'].iloc[0] backdate is
        # removed (fresh_shadow_start ignores the frame by design).
        shadow = (fresh_shadow_start(df, observed_at) if len(df)
                  else core._ts(observed_at).isoformat())
        advisor.begin(shadow, observed_at)
        advisor._journal({"t": "begin", "shadow_start": shadow,
                          "observed_at": observed_at,
                          "ingest_id": raw_snap["ingest_id"]})
        advisor.atomic_commit()
    else:
        # Resume with no new candles must still rebuild missing exports.
        pass

    gaps_before = len(advisor.exec_state.get("gaps", []))
    rec = reconcile_window(
        df, symbol, interval, observed_at, advisor.exec_state,
        expected_bar_seconds=int(
            advisor_cfg["feed"]["expected_bar_seconds"]))
    for k in ("duplicates", "revised", "forming", "nonfinite",
               "market_mismatch", "out_of_order"):
        advisor.counts[k] = advisor.counts.get(k, 0) + len(rec[k])
    # r80: invalid OHLC/grid/close-time + refused late rows are never
    # seen/settled; counted as invalid-dropped and contaminate inference.
    advisor.counts["invalid_dropped"] = advisor.counts.get(
        "invalid_dropped", 0) + len(rec.get("invalid", [])) + len(
        rec.get("late", []))
    if rec.get("invalid") or rec.get("late"):
        advisor._journal({"t": "invalid-dropped",
                          "observed_at": observed_at,
                          "invalid": rec.get("invalid", []),
                          "late": rec.get("late", [])})
    advisor.counts["gaps"] = len(rec["gaps"])
    new_gaps = rec["gaps"][gaps_before:]

    # r79 feed-validity pause: bars at/after an unresolved gap boundary
    # are PAUSED (no economic settlement through unobserved price paths).
    # The pause persists across ingests until verified backfill; paused
    # bars replay deterministically with their ORIGINAL exec_idx
    # (uncommitted flags; exactly-once, no duplicates).
    paused_exec = apply_validity_pause(advisor, rec, new_gaps, observed_at)
    validity = RollingAdvisor._ensure_validity(advisor.exec_state)
    # r79 revision rule: an ingest carrying OHLC revisions on settled bars
    # forces the whole ingest diagnostic-only (revised bytes must not reach
    # inference silently).
    revision_contaminated = len(rec["revised"]) > 0
    if revision_contaminated:
        advisor._journal({"t": "validity-revision",
                          "observed_at": observed_at,
                          "revised": rec["revised"]})

    new_rows = rec["new_rows"]
    # r79 missed-clock anchor: only decisions ON the latest new bar may be
    # actionable; earlier catch-up decisions are diagnostic-only (their
    # entry window passed before actual availability; no delayed-entry
    # policy exists in r79). Already-observed pending/open positions still
    # settle causally through catch-up bars.
    batch_latest_close_iso = (
        max(core._ts(r["close_time"]) for _, r in new_rows).isoformat()
        if new_rows else None)
    status_counts: dict[str, int] = {}
    inference_evidence: dict = {"calls": 0, "mapped": 0, "stub": bool(
        a.stub_infer)}
    # r79 inference sanitation: never feed forming/non-finite bars to
    # inference; never synthesize. Dropped-row report is journaled.
    infer_df, sanitize_report = sanitize_inference_frame(df, observed_at)
    advisor.counts["invalid_dropped"] = advisor.counts.get(
        "invalid_dropped", 0) + int(
            sanitize_report["nonfinite_dropped"])
    invalid_contaminated = (
        sanitize_report["nonfinite_dropped"] > 0
        or sanitize_report.get("invalid_dropped", 0) > 0
        or len(rec.get("invalid", [])) > 0
        or len(rec.get("late", [])) > 0
        or len(rec["market_mismatch"]) > 0)
    if sanitize_report["nonfinite_dropped"] or sanitize_report[
            "forming_dropped"]:
        advisor._journal({"t": "inference-sanitized",
                          "observed_at": observed_at, **sanitize_report})
    if new_rows:
        if a.stub_infer:
            raw_by_exec: dict = {}
            for exec_idx, row in new_rows:
                if core.on_grid(row["open_time"]):
                    dt = core._ts(row["close_time"])
                    raw_by_exec[exec_idx] = {
                        "status": "READY_RAW", "bar_index": -1,
                        "decision_time": dt, "close": row["close"],
                        "atr5": 1.0, "atr4": 1.0,
                        "scores": {"selection_score_percent": 0.5,
                                    "mean_fill_score": 0.5},
                        "iso4_raw_action": "WAIT",
                        "iso4_raw_geometry": None,
                        "per_map_action": {}, "vote_majority": False,
                        "vote_confirmed": False,
                        "htf_last_close_lte_decision": {}}
            advisor.inference_calls += 1
            inference_evidence = {"calls": 1, "mapped": len(raw_by_exec),
                                  "stub": True}
        else:
            t0 = time.time()
            raw_rows = core.infer_full(infer_df, spec)
            advisor.inference_calls += 1
            inference_evidence = {"calls": 1,
                                  "raw_rows": len(raw_rows),
                                  "seconds": time.time() - t0,
                                  "stub": False}
            raw_by_exec = map_inference_to_exec(raw_rows, infer_df, symbol,
                                                interval, advisor.exec_state)
            inference_evidence["mapped"] = len(raw_by_exec)
            if (len(raw_rows) == 1 and raw_rows[0].get("status")
                    == core.STATUS_WARMUP):
                # Runner parity (r77 :190-196): attach the WARMUP row to the
                # first unseen on-grid bar so warmup is logged, not silent.
                raw_by_exec = {}
                for exec_idx, row in new_rows:
                    if core.on_grid(row["open_time"]):
                        raw_by_exec[exec_idx] = raw_rows[0]
                        break
                inference_evidence["mapped"] = len(raw_by_exec)
                inference_evidence["warmup"] = raw_rows[0].get("reason", "")
        statuses = []
        for i, (exec_idx, row) in enumerate(new_rows):
            chunk = advisor.settle_new(
                [(exec_idx, row)], raw_by_exec, observed_at,
                batch_latest_close_iso=batch_latest_close_iso,
                paused_exec=paused_exec,
                revision_contaminated=(revision_contaminated
                                       or invalid_contaminated))
            statuses.extend(chunk)
            if a.sleep_per_bar:
                time.sleep(a.sleep_per_bar)
            if (i + 1) % max(int(a.persist_every), 1) == 0:
                advisor.atomic_commit()
        for s in statuses:
            status_counts[s["status"]] = status_counts.get(
                s["status"], 0) + 1
        advisor.atomic_commit()
    else:
        if not advisor.rebuild_missing_exports():
            print(f"[{ROLL_VERSION}] resume: nothing new "
                  f"(seen={len(advisor.exec_state.get('seen', {}))}); "
                  "state re-verified.")
        else:
            print(f"[{ROLL_VERSION}] resume: nothing new; missing exports "
                  f"rebuilt without re-emitting.")

    snapshot = advisor.build_snapshot(
        first_open_iso=(core._ts(df['open_time'].iloc[0]).isoformat()
                        if len(df) else None),
        last_close_iso=(core._ts(df['close_time'].iloc[-1]).isoformat()
                        if len(df) else None),
        n_rows=len(df),
        raw_artifact={**raw_artifact, **raw_snap},
        observed_at=observed_at,
        source={"kind": raw_artifact["kind"], "fetched_at": fetched_at,
                "gaps": rec["gaps"], "revisions": rec["revised"]},
        status_counts=status_counts,
        inference_evidence=inference_evidence,
        observation_times={
            "bootstrap_observed_at": advisor.exec_state.get(
                "bootstrap_observed_at"),
            "observed_at": core._ts(observed_at).isoformat()},
        lineage={"ingest_ids": list(advisor.exec_state.get(
            "ingest_ids", [])),
            "ingest_id": raw_snap["ingest_id"],
            "prev_sha256": raw_snap["prev_sha256"]},
        validity=dict(validity),
        inference_sanitized=sanitize_report)
    advisor.write_exports(snapshot)
    (out / "summary.json").write_text(
        json.dumps(snapshot, indent=1, default=str), encoding="utf-8")
    print(f"[{ROLL_VERSION}] {a.mode}: new={len(new_rows)} "
          f"gen={advisor.generation} counts={advisor.counts} -> {out}")


if __name__ == "__main__":
    main()
