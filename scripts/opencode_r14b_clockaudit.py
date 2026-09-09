"""Opencode v47 (R14-B): live-clock fidelity audit of the standing-best feature chain.

Question: at a 5m-close decision time T, ONLY the 5m candle is guaranteed closed
while 15m/1h/4h/1d bars containing T are still FORMING. Does the backtest feature
pipeline (resample_closed_ohlcv -> WindowStore.at + SwingStore.sample) use
finalized (future) HTF values = look-ahead leak, or only fully-closed bars?

Method (read-only; no engine/cost/registry changes):
  A. signal_time <-> bar_index alignment over all decisions.
  B. Per-TF closed-only proof over ALL decisions (vectorized searchsorted math).
  C. HTF bucket structure proof (epoch alignment, contiguity, close exactness).
  D. Live-faithful rebuild: truncate base candles to close_time <= T and prove
     the rebuilt sample is bit-identical to the full-history sample + stored row.
  E. Boundary timestamp math (15m/1h, 4h, 1d boundaries + non-boundary).
  F. Entry alignment on frozen standing-best trades (entry >= bar_index + 1).

Verdict per timeframe: CLEAN or LEAK. If any LEAK -> exit(2), no fix applied here.
"""
import torch  # noqa: F401  (import order: torch before pandas on this host)
import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from agentic_alpha_lab.data.swing import SwingStore
from agentic_alpha_lab.data.training import sha256

TF_NS = {tf: int(pd.Timedelta(tf).value) for tf in ("5min", "15min", "1h", "4h", "1d")}
BASE_NS = TF_NS["5min"]
MS = 1_000_000


def load_inputs(root, cfg):
    candles = pd.read_parquet(root / cfg["inputs"]["candles"])
    decisions = pd.read_parquet(root / cfg["inputs"]["decisions"])
    ds_cfg = json.loads((root / cfg["inputs"]["dataset_config"]).read_text())
    return candles, decisions, ds_cfg


def ns_of(series):
    return pd.DatetimeIndex(pd.to_datetime(series, utc=True)).asi8


def check_A(candles, decisions):
    ct = pd.to_datetime(candles["close_time"], utc=True).reset_index(drop=True)
    st = pd.to_datetime(decisions["signal_time"], utc=True).reset_index(drop=True)
    bi = decisions["bar_index"].to_numpy()
    ct_ns = ns_of(ct)
    assert ((np.diff(ct_ns) == BASE_NS).all()), "base candles must be a contiguous 5m grid"
    assert (((ct_ns - (BASE_NS - MS)) % BASE_NS) == 0).all(), "base closes must sit on the 5m grid"
    assert (ct.iloc[bi].reset_index(drop=True) == st).all(), "signal_time must equal close_time[bar_index]"
    return {"rows": int(len(decisions)), "grid_contiguous": True,
            "signal_time_eq_close_of_bar_index": True}


def check_B(store, decisions):
    t_all = ns_of(decisions["signal_time"])
    per_tf = {}
    for j, tf in enumerate(store.config["timeframes"]):
        ends = store.ends[j]
        pos = np.searchsorted(ends, t_all, side="right") - 1
        assert (pos >= 0).all(), f"{tf}: decision before first closed bar"
        used_close = ends[pos]
        stale = t_all - used_close
        assert (used_close <= t_all).all(), f"{tf}: used bar closes AFTER signal_time (LEAK)"
        assert (stale >= 0).all() and (stale < TF_NS[tf]).all(), f"{tf}: staleness out of [0, TF)"
        per_tf[tf] = {
            "n_checked": int(len(t_all)),
            "all_used_close_le_T": True,
            "max_staleness": str(pd.Timedelta(int(stale.max()))),
            "min_staleness": str(pd.Timedelta(int(stale.min()))),
            "median_staleness": str(pd.Timedelta(int(np.median(stale)))),
        }
    return per_tf


def check_C(store, candles):
    base_open = ns_of(candles["open_time"])
    out = {}
    for j, tf in enumerate(store.config["timeframes"]):
        frame = store.frames[j]
        opens = ns_of(frame["open_time"])
        closes = ns_of(frame["close_time"])
        period = TF_NS[tf]
        expected = period // BASE_NS
        assert ((opens % period) == 0).all(), f"{tf}: bucket opens not epoch-aligned"
        assert (np.diff(opens) == period).all(), f"{tf}: buckets not contiguous"
        assert (closes == opens + period - MS).all(), f"{tf}: bucket close != open + TF - 1ms"
        # Constituent-count proof on evenly spaced sample buckets (full scan is O(N*M)).
        sample_idx = np.linspace(0, len(frame) - 1, min(200, len(frame))).astype(int)
        for k in sample_idx:
            n = int(((base_open >= opens[k]) & (base_open < opens[k] + period)).sum())
            assert n == expected, f"{tf} bucket {k}: {n} constituents != {expected}"
        out[tf] = {"bars": int(len(frame)), "epoch_aligned": True, "contiguous": True,
                   "close_eq_open_plus_TF_minus_1ms": True,
                   "constituent_count_eq_expected": True, "constituents_sampled": int(len(sample_idx)),
                   "expected_per_bucket": int(expected)}
    return out


def check_D(candles, ds_cfg, decisions, subset):
    store_full = SwingStore(candles, ds_cfg)
    detail = []
    for r in subset:
        row = decisions.iloc[r]
        t = pd.Timestamp(row["signal_time"])
        i = int(row["bar_index"])
        # Live-faithful view: only base candles with close_time <= T exist yet.
        live = candles.loc[pd.to_datetime(candles["close_time"], utc=True) <= t].reset_index(drop=True)
        assert pd.Timestamp(live["close_time"].iloc[-1]) == t, "truncation must end exactly at T"
        store_live = SwingStore(live, ds_cfg)
        full = store_full.sample(t)
        liv = store_live.sample(t)
        for name, a, b in (("windows", full[0], liv[0]), ("stamps", full[1], liv[1]),
                           ("ages", full[2], liv[2]), ("features", full[3], liv[3])):
            np.testing.assert_array_equal(a, b, err_msg=f"row {r} {name} differs live vs full")
        assert full[4] == liv[4] and full[5] == liv[5], f"row {r} ATR differs"
        assert abs(float(row["close"]) - float(candles["close"].iloc[i])) == 0.0
        assert full[4] == float(row["atr5"]) and full[5] == float(row["atr4"]), f"row {r} stored atr mismatch"
        detail.append({"row": int(r), "bar_index": i, "signal_time": str(t),
                       "live_rebuild_bit_identical": True, "stored_close_atr_match": True})
    return detail


def boundary_case(store, candles, when, label):
    t = pd.Timestamp(when)
    assert t in set(pd.to_datetime(candles["close_time"], utc=True)), f"{label}: {when} not a real 5m close"
    w, _, ages, _, a5, a4 = store.sample(t)
    assert w.shape[0] == len(store.config["timeframes"])
    rows = {}
    for j, tf in enumerate(store.config["timeframes"]):
        ends = store.ends[j]
        pos = int(np.searchsorted(ends, t.value, side="right")) - 1
        bar = store.frames[j].iloc[pos]
        stale = t.value - ends[pos]
        assert ends[pos] <= t.value, f"{label} {tf}: forming-bar leak"
        rows[tf] = {"last_bar_open": str(pd.Timestamp(bar["open_time"])),
                    "last_bar_close": str(pd.Timestamp(bar["close_time"])),
                    "staleness": str(pd.Timedelta(int(stale))),
                    "closed_before_or_at_T": True}
    return {"label": label, "T": str(t), "atr5": float(a5), "atr4": float(a4),
            "ages_periods": {tf: float(a) for tf, a in zip(store.config["timeframes"], ages)},
            "per_tf": rows}


def check_F(root, cfg):
    out = {}
    for sig_path, trd_path in zip(cfg["inputs"]["standing_signals"], cfg["inputs"]["standing_trades"]):
        name = Path(sig_path).parent.name
        sig = pd.read_parquet(root / sig_path)
        trd = pd.read_csv(root / trd_path)
        # Trade.signal_index is the candle bar_index of the signal (engine.py:191,345);
        # signals.parquet carries the same bar_index column. Entry must be >= +1 (engine.py:203).
        assert set(trd["signal_index"]).issubset(set(sig["bar_index"])), f"{name}: trade->signal mapping broken"
        gap = (trd["entry_index"].to_numpy() - trd["signal_index"].to_numpy())
        assert (gap >= 1).all(), f"{name}: entry not strictly after signal bar (LEAK)"
        out[name] = {"trades": int(len(trd)), "min_entry_minus_signal_bar": int(gap.min()),
                     "all_entries_ge_bar_plus_1": True}
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--config", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    root = Path(__file__).resolve().parents[1]
    cfg = json.loads(a.config.read_text())
    if a.output.exists():
        raise FileExistsError("Choose a new output; do not overwrite historical evidence")
    candles, decisions, ds_cfg = load_inputs(root, cfg)

    store = SwingStore(candles, ds_cfg)
    rep_A = check_A(candles, decisions)
    rep_B = check_B(store, decisions)
    rep_C = check_C(store, candles)
    n = len(decisions)
    subset = [0, 1500, 3000, 4500, n - 1]
    rep_D = check_D(candles, ds_cfg, decisions, subset)
    rep_E = [
        boundary_case(store, candles, "2022-05-09 00:04:59.999+00:00", "non_boundary_T (actual decision row 0)"),
        boundary_case(store, candles, "2023-01-01 00:59:59.999+00:00", "on_15m_and_1h_boundary"),
        boundary_case(store, candles, "2023-01-01 03:59:59.999+00:00", "on_4h_boundary"),
        boundary_case(store, candles, "2023-01-02 23:59:59.999+00:00", "on_1d_boundary"),
    ]
    rep_F = check_F(root, cfg)

    verdicts = {tf: "CLEAN" for tf in ds_cfg["timeframes"]}
    report = {
        "experiment": cfg["experiment"], "verdicts": verdicts,
        "overall": "CLEAN: every timeframe uses only fully-closed bars; live rebuild bit-identical; no fix required",
        "A_alignment": rep_A, "B_closed_only": rep_B, "C_bucket_structure": rep_C,
        "D_live_rebuild_subset": rep_D, "E_boundary_math": rep_E, "F_entry_alignment": rep_F,
        "fix_applied": False, "old_vs_new": None,
        "mechanism_notes": {
            "resample": "src/agentic_alpha_lab/data/timeframes.py:37-40 resample left-closed + drop incomplete buckets (count==expected)",
            "at": "src/agentic_alpha_lab/data/kronos_trading.py:51 searchsorted(ends, as_of, side=right); last bar close_time <= T",
            "sample": "src/agentic_alpha_lab/data/swing.py:115-119 same ends semantics for atr5/atr4",
            "entry_engine": "src/agentic_alpha_lab/backtest/engine.py:203 first_entry_bar = signal_index + 1; :142-151 bar_index from signal_time->close_time lookup",
            "live_loop": "scripts/opencode_paper_trader.py:303 predictor sees only closed bars <= just-closed bar; frozen signals replayed by bar_index",
        },
        "input_sha256": {
            "candles": sha256(root / cfg["inputs"]["candles"]),
            "decisions": sha256(root / cfg["inputs"]["decisions"]),
            "dataset_config": sha256(root / cfg["inputs"]["dataset_config"]),
            "audit_config": sha256(a.config),
            "audit_script": sha256(Path(__file__)),
        },
        "exploratory": True, "live_approved": False,
        "warning": "Exploratory audit on opened development data. NOT an independent test. No live approval.",
    }
    a.output.mkdir(parents=True)
    (a.output / "config.json").write_text(json.dumps(cfg, indent=2))
    (a.output / "clockaudit_report.json").write_text(json.dumps(report, indent=2, default=str))
    summary = {"experiment": cfg["experiment"], "verdicts": verdicts, "overall": report["overall"],
               "fix_applied": False, "old_vs_new": None,
               "staleness_bounds": {tf: {"max": v["max_staleness"], "median": v["median_staleness"]}
                                    for tf, v in rep_B.items()},
               "entry_gap_min_bars": {k: v["min_entry_minus_signal_bar"] for k, v in rep_F.items()},
               "input_sha256": report["input_sha256"]}
    (a.output / "summary.json").write_text(json.dumps(summary, indent=2, default=str))
    print(json.dumps(summary, indent=2, default=str))
    print("WROTE", str(a.output / "summary.json"))


if __name__ == "__main__":
    sys.exit(main())
