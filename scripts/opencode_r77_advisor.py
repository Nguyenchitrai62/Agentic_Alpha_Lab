"""Opencode R77 W1-RUNNER CLI: ONE integrated stateful advisory runner.

  replay: scripts/opencode_r77_advisor.py --mode replay \\
            --config configs/opencode_r77_advisor.json \\
            --candles data/processed/<slice>/candles.parquet --out <dir> [--resume]
  fresh:  scripts/opencode_r77_advisor.py --mode fresh \\
            --config configs/opencode_r77_advisor.json \\
            --candles live --out <dir> [--resume]

Both modes share ALL interfaces in scripts/opencode_r77_advisor_core.py
(feed ingest, infer_full causal adapter, AdvisorStrategy, state).
Advisory only: public klines GET, no keys, no orders, no scheduler.
torch is imported before pandas (Windows DLL load-order rule).
"""
import torch  # noqa: F401  (torch truoc pandas: DLL load-order Windows host)

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

import pandas as pd
import numpy as np

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
if str(_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(_ROOT / "scripts"))

import opencode_r77_advisor_core as core  # noqa: E402
import opencode_r76_feedexec as fx  # noqa: E402
import opencode_r76_infer as r76  # noqa: E402


def _sha_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_candles_replay(candles_path: Path) -> pd.DataFrame:
    df = pd.read_parquet(candles_path)
    need = {"open_time", "open", "high", "low", "close", "volume",
            "close_time"}
    missing = need - set(df.columns)
    if missing:
        raise ValueError(f"replay candles lack {sorted(missing)} (refusing).")
    df = df.sort_values("open_time").reset_index(drop=True)
    df["open_time"] = pd.to_datetime(df["open_time"], utc=True)
    df["close_time"] = pd.to_datetime(df["close_time"], utc=True)
    return df


def stream_bars(df: pd.DataFrame, raw_by_bar: dict, strategy,
                observed_at: str, state_path: Path,
                persist_every: int, idx_offset: int = 0) -> list[dict]:
    statuses = []
    for pos in range(len(df)):
        bar_idx = idx_offset + pos
        row = df.iloc[pos]
        bar = {"open_time": row["open_time"], "close_time": row["close_time"],
               "open": float(row["open"]), "high": float(row["high"]),
               "low": float(row["low"]), "close": float(row["close"]),
               "volume": float(row["volume"])}
        st = strategy.observe_bar(bar_idx, bar, raw_by_bar.get(bar_idx),
                                  observed_at)
        statuses.append(st)
        if persist_every and (bar_idx + 1) % persist_every == 0:
            state_path.write_text(json.dumps(
                strategy.snapshot_state(strategy._identity), indent=1,
                default=str))
    return statuses


def main() -> None:
    ap = argparse.ArgumentParser(
        description="R77 integrated stateful advisory runner (PAPER ONLY).")
    ap.add_argument("--mode", choices=("replay", "fresh"), required=True)
    ap.add_argument("--config", type=str,
                    default="configs/opencode_r77_advisor.json")
    ap.add_argument("--candles", type=str, required=True,
                    help="replay: candles parquet path; fresh: 'live'")
    ap.add_argument("--out", type=str, required=True)
    ap.add_argument("--resume", action="store_true",
                    help="continue from <out>/state.json (identity-checked)")
    ap.add_argument("--max-decisions", type=int, default=None,
                    help="bound real-model inference (replay demo)")
    ap.add_argument("--fresh-max-bars", type=int, default=40000)
    a = ap.parse_args()

    config = json.loads((_ROOT / a.config).read_text(encoding="utf-8"))
    if config.get("allow_live_orders", True):
        raise SystemExit("REFUSED: allow_live_orders must stay false.")
    spec = r76.load_prespec()
    out = _ROOT / a.out
    state_path = out / "state.json"

    resumed_snap = None
    if a.resume:
        if not state_path.exists():
            raise SystemExit("REFUSED: --resume needs <out>/state.json.")
        resumed_snap = json.loads(state_path.read_text(encoding="utf-8"))
        strategy = core.AdvisorStrategy(
            config, n_bars=resumed_snap.get("n_bars"))
        identity = strategy.identity_block(config, spec)
        strategy.restore_state(resumed_snap, identity)
        strategy._identity = identity
        # r78-int2: do NOT derive the restart position from the stored
        # positional index (stale across shifted cache windows). The anchor
        # is the last SETTLED bar timestamp; reconciliation against the new
        # frame happens below once df exists. last_settled None means
        # nothing was ever settled -> whole frame is new.
        resume_anchor = strategy.last_settled
        start_bar = None
        print(f"[{core.MODE_LABEL}] resume: identity OK; "
              f"anchor={resume_anchor}")
    else:
        if out.exists():
            raise FileExistsError(
                f"Refusing to overwrite existing output: {out}")
        strategy = core.AdvisorStrategy(config, n_bars=None)
        strategy._identity = strategy.identity_block(config, spec)
        start_bar = 0

    t0 = time.time()
    if a.mode == "fresh":
        if a.candles != "live":
            raise SystemExit("REFUSED: fresh ingests live public klines only "
                             "(--candles live); stored signals/predictions "
                             "are never matched in fresh mode.")
        closed, prov = core.fetch_warmup_paginated(
            symbol=config["feed"]["symbol"],
            interval=config["feed"]["interval"],
            max_bars=int(a.fresh_max_bars))
        feed = fx.FeedState(symbol=config["feed"]["symbol"],
                            interval=config["feed"]["interval"],
                            expected_bar_seconds=config["feed"][
                                "expected_bar_seconds"],
                            warmup_bars=core.FEED_WARMUP_BARS)
        ok, rejects = [], {}
        for cnd in closed:
            st = feed.validate(cnd)
            if st in (fx.STATUS_OK, fx.STATUS_WARMUP):
                ok.append(cnd)
            else:
                rejects[st] = rejects.get(st, 0) + 1
        df = pd.DataFrame(ok)
        if len(df):
            df = df.sort_values("open_time").reset_index(drop=True)
        observed_at = prov["fetched_at"]
        # Bootstrap rule: every inference from this fetch predates (or meets)
        # the observation instant -> DIAGNOSTIC-only, never backdated alerts.
        shadow = observed_at if not a.resume else None
        n_bars = None  # open-ended: no truncation
        source = {"kind": "FRESH-OBSERVATION", "provenance": prov,
                  "rejects": rejects}
    else:
        if a.candles == "live":
            raise SystemExit("REFUSED: replay needs a candles parquet.")
        df = load_candles_replay(_ROOT / a.candles)
        observed_at = pd.Timestamp.now(tz="UTC").isoformat()
        shadow = (df["close_time"].iloc[0].isoformat()
                  if len(df) else observed_at)
        n_bars = len(df)
        source = {"kind": "REHEARSAL-NOT-LIVE",
                  "candles": str(a.candles),
                  "candles_sha256": _sha_file(_ROOT / a.candles),
                  "n_rows": len(df),
                  "range": [str(df["open_time"].iloc[0]),
                            str(df["close_time"].iloc[-1])]
                  if len(df) else []}

    if not a.resume:
        strategy.n_bars = n_bars
        strategy._identity = strategy.identity_block(config, spec)
        strategy.begin_observation(shadow, observed_at)
    elif strategy.n_bars != n_bars and not (
            a.mode == "fresh" and strategy.n_bars is None):
        raise SystemExit(
            f"REFUSED: resume horizon mismatch (stored={strategy.n_bars}, "
            f"current={n_bars}).")

    # Causal adapter on the OBSERVED stream (real model, fail-closed).
    # r78-int2: reconcile the restart position by TIMESTAMP identity, never
    # by stored positional index (stale across shifted cache windows).
    if a.resume:
        closes = pd.DatetimeIndex(pd.to_datetime(df["close_time"], utc=True))
        if resume_anchor is None:
            start_bar = 0
            anchor_evidence = "no bar ever settled: whole frame is new"
        else:
            hits = np.where(closes == resume_anchor)[0]
            if len(hits) != 1:
                raise SystemExit(
                    f"REFUSED: resume anchor {resume_anchor.isoformat()} "
                    f"found {len(hits)}x in new frame (need exactly 1); "
                    f"history rotated out or duplicated. Start a fresh run "
                    f"instead of guessing.")
            start_bar = int(hits[0]) + 1
            anchor_evidence = (
                f"anchor {resume_anchor.isoformat()} at new-frame pos "
                f"{int(hits[0])}; settling from {start_bar}")
        print(f"[{core.MODE_LABEL}] resume: {anchor_evidence}")
    if a.resume and start_bar >= len(df):
        out.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(
            strategy.snapshot_state(strategy._identity), indent=1,
            default=str))
        print(f"[{core.MODE_LABEL}] resume: nothing new "
              f"(bars={len(df)}, start={start_bar}, anchor matched latest "
              f"close); state re-verified.")
        return
        out.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(
            strategy.snapshot_state(strategy._identity), indent=1,
            default=str))
        print(f"[{core.MODE_LABEL}] resume: nothing new "
              f"(bars={len(df)}, start={start_bar}); state re-verified.")
        return
    t_inf0 = time.time()
    raw_rows = core.infer_full(df, spec, max_decisions=a.max_decisions)
    t_inf1 = time.time()
    raw_by_bar: dict[int, dict] = {}
    warmup_only = (len(raw_rows) == 1
                   and raw_rows[0].get("status") == core.STATUS_WARMUP)
    if warmup_only:
        for b in range(len(df)):
            if core.on_grid(df["open_time"].iloc[b]):
                raw_by_bar[b] = raw_rows[0]
                break
    else:
        for r in raw_rows:
            raw_by_bar[int(r["bar_index"])] = r

    out.mkdir(parents=True, exist_ok=True)
    persist_every = int(config.get("state", {}).get(
        "persist_every_n_bars", 200))
    if a.resume and start_bar:
        # r78-int3: shifted cache windows use a DIFFERENT positional system
        # than the stored run. Continue execution indices past the restored
        # max (strictly increasing invariant) and remap raw rows keyed by
        # new-frame position onto them. Same-window resume is the identity
        # case of this mapping (base == start_bar).
        prev_max = strategy._last_bar_idx
        base = (int(prev_max) + 1) if prev_max is not None else start_bar
        remapped = {(base + (p - start_bar)): r
                    for p, r in raw_by_bar.items() if p >= start_bar}
        # Global bar indices continue uninterrupted (same once-only outputs).
        statuses = stream_bars(df.iloc[start_bar:].reset_index(drop=True),
                               remapped, strategy, observed_at,
                               state_path, persist_every,
                               idx_offset=base)
    else:
        statuses = stream_bars(df, raw_by_bar, strategy, observed_at,
                               state_path, persist_every)
    state_path.write_text(json.dumps(
        strategy.snapshot_state(strategy._identity), indent=1, default=str))

    _write_outputs(out, config, spec, strategy, statuses, source,
                   observed_at, a, raw_rows, t1=time.time() - t0,
                   t_inf=t_inf1 - t_inf0)
    print(f"[{core.MODE_LABEL}] {a.mode}: bars={len(df)} "
          f"decisions={len(strategy.decision_log)} "
          f"op_eq={strategy.operating.equity:.4f} "
          f"ctrl_eq={strategy.control.equity:.4f} -> {out}")


def _write_outputs(out: Path, config: dict, spec: dict, strategy,
                   statuses: list, source: dict, observed_at: str,
                   args, raw_rows: list, t1: float, t_inf: float) -> None:
    def _frame(rows, columns):
        if len(rows):
            return pd.DataFrame(rows)
        return pd.DataFrame(columns=columns)
    dec = _frame(strategy.decision_log,
                 ["status", "action", "observed_at", "decision_time",
                  "bar_time", "iso4_raw_action", "vote_majority",
                  "vote_confirmed", "confirmed_action",
                  "selection_score_percent", "mean_fill_score",
                  "control_intent_id", "operating_intent_id",
                  "htf_last_close_lte_decision"])
    dec.to_csv(out / "decisions.csv", index=False)
    _frame(strategy.diagnostics,
           ["status", "observed_at", "decision_time", "bar_time",
            "iso4_raw_action", "vote_confirmed", "note"]).to_csv(
        out / "diagnostics.csv", index=False)
    _frame(list(strategy.intents.values()),
           core.AdvisorStrategy.INTENT_COLUMNS).to_csv(
        out / "intents.csv", index=False)
    _frame(strategy.operating.events, ["account", "kind"]).to_csv(
        out / "operating_exits.csv", index=False)
    _frame(strategy.control.events, ["account", "kind"]).to_csv(
        out / "control_exits.csv", index=False)
    _frame(list(strategy.alerts.values()), ["alert_id", "kind"]).to_csv(
        out / "alerts.csv", index=False)
    manifest = {
        "kind": source["kind"], "mode": core.MODE_LABEL,
        "exploratory": True, "live_orders": False,
        "advisor_version": core.ADVISOR_VERSION,
        "policy_id": core.POLICY_ID,
        "overlay_version": core.OVERLAY_VERSION,
        "clock": {"rule": "6h UTC grid from open_time, stride 72",
                  "positional_modulo": "FORBIDDEN"},
        "feed": {"host": config["feed"]["host"], "path": config["feed"][
            "path"], "symbol": config["feed"]["symbol"],
            "interval": config["feed"]["interval"], "market": "USDM"},
        "source": source,
        "observed_at": observed_at,
        "identity": strategy._identity,
        "status_counts": pd.Series(
            [s["status"] for s in statuses]).value_counts().to_dict(),
        "watermarks": strategy.snapshot_state(
            strategy._identity)["watermarks"]}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1,
                                                  default=str))
    op_ev = strategy.operating.events
    ct_ev = strategy.control.events
    summary = {
        "mode": core.MODE_LABEL, "exploratory": True, "live_orders": False,
        "run_mode": args.mode, "advisor_version": core.ADVISOR_VERSION,
        "policy_id": core.POLICY_ID,
        "overlay_version": core.OVERLAY_VERSION,
        "overlay_note": "daily-halt + divergence-trip are versioned "
                        "operational overlays, NOT part of the historical "
                        "reference; batch and streaming share the SAME "
                        "AdvisorStrategy class (same rules by construction).",
        "config_snapshot": config, "manifest": manifest,
        "timing_s": {"total": t1, "inference": t_inf},
        "operating": {"equity": strategy.operating.equity,
                      "exits": strategy.operating.exits,
                      "net=sum(events)": sum(
                          e.get("net_pnl", 0.0) for e in op_ev)},
        "control_iso4_only_1x": {"equity": strategy.control.equity,
                                 "exits": strategy.control.exits,
                                 "net=sum(events)": sum(
                                     e.get("net_pnl", 0.0) for e in ct_ev)},
        "counters": strategy.counters,
        "alerts": list(strategy.alerts.values()),
        "adapter_first_row_keys": sorted(raw_rows[0].keys())
        if raw_rows else []}
    (out / "summary.json").write_text(json.dumps(summary, indent=1,
                                                 default=str))


if __name__ == "__main__":
    main()
