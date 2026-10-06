"""Tests for oc_deepcheck: FIFO misattribution forensics (no simulation).

Fast checks only: file presence, results.json schema/consistency, synthetic
demonstration that time-sorted FIFO swaps depth P&L when same-coin rungs exit
out of order while positional (engine append order) pairing keeps it, and the
adjacency property on the real R2B1D17BF s=0 events.
"""
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
ME = ROOT / "research/diagnostics/oc_deepcheck"
KPI = ROOT / "research/tournament/oc_kpi"


def _load():
    import importlib.util
    spec = importlib.util.spec_from_file_location("oc_deepcheck_an", ME / "analyze_deepcheck.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _res():
    return json.loads((ME / "results.json").read_text())


def test_files_present():
    for f in ("analyze_deepcheck.py", "run_s0.py", "results.json", "REPORT.md"):
        assert (ME / f).exists(), f


def test_year_of_boundaries():
    a = _load()
    assert a.year_of("2021-09-24 00:00:00+00:00") == 0
    assert a.year_of("2022-09-23 23:59:00+00:00") == 0
    assert a.year_of("2022-09-24 00:00:00+00:00") == 1
    assert a.year_of("2026-09-23 23:59:00+00:00") == 4
    assert a.year_of("2026-09-24 00:00:00+00:00") is None


def _synth_out_of_order():
    """Two same-coin rungs fill together; the DEEP one exits first (fast TP).

    Engine append order: (shallow fill, shallow exit later, ...) is NOT how the
    engine logs -- it logs (fill, own exit) consecutively per fill in fill
    order: shallow fill, shallow exit, deep fill, deep exit. To reproduce the
    real layout, fills share one timestamp and exits carry their own times.
    """
    return pd.DataFrame([
        dict(t="2022-01-01 00:20:00+00:00", symbol="XRPUSDT", kind="rung_fill",
             side="buy", price=1.00, weight=0.10, rung=2.5, ret=float("nan")),
        dict(t="2022-01-01 00:50:00+00:00", symbol="XRPUSDT", kind="rung_timeout",
             side="sell", price=0.99, weight=0.10, rung=float("nan"), ret=-0.02),
        dict(t="2022-01-01 00:20:00+00:00", symbol="XRPUSDT", kind="rung_fill",
             side="buy", price=0.98, weight=0.10, rung=5.0, ret=float("nan")),
        dict(t="2022-01-01 00:25:00+00:00", symbol="XRPUSDT", kind="rung_tp",
             side="sell", price=1.00, weight=0.10, rung=float("nan"), ret=+0.03),
    ])


def test_fifo_swaps_depth_pnl_when_exits_invert():
    a = _load()
    ev = _synth_out_of_order()
    ev["t"] = pd.to_datetime(ev["t"], utc=True)
    true_rows, viol = a.pair_true(ev)
    fifo_rows, unpaired, left, _ = a.pair_fifo(ev)
    assert viol == 0 and unpaired == 0 and left == 0
    tp = {r["depth"]: r["pnl"] for r in true_rows}
    fp = {r["depth"]: r["pnl"] for r in fifo_rows}
    # engine truth: shallow loses (-0.002), deep wins (+0.003)
    assert abs(tp[2.5] + 0.002) < 1e-12 and abs(tp[5.0] - 0.003) < 1e-12
    # FIFO credits the shallow fill with the deep rung's fast TP and debits
    # the deep fill with the shallow rung's timeout: signs swap
    assert abs(fp[2.5] - 0.003) < 1e-12 and abs(fp[5.0] + 0.002) < 1e-12
    # totals agree (pure re-attribution)
    assert abs(sum(tp.values()) - sum(fp.values())) < 1e-12


def test_adjacency_on_real_s0_events():
    a = _load()
    ev = pd.read_parquet(KPI / "events_s0.parquet")
    kinds = ev["kind"].tolist()
    n_fill = sum(1 for k in kinds if k == "rung_fill")
    assert n_fill == 5466
    for i, k in enumerate(kinds):
        if k == "rung_fill":
            nxt = ev.iloc[i + 1]
            assert nxt["kind"] in ("rung_sl", "rung_tp", "rung_timeout")
            assert nxt["symbol"] == ev.iloc[i]["symbol"]
            assert abs(float(nxt["weight"]) - float(ev.iloc[i]["weight"])) < 1e-12


def test_results_consistency():
    a = _load()
    r = _res()
    assert r["checks"]["n_rungs_true"] == r["checks"]["n_rungs_fifo"] == 21389
    assert r["checks"]["adjacency_violations"] == 0
    assert r["checks"]["fifo_unpaired"] == 0 and r["checks"]["fifo_left_open"] == 0
    # totals identical between methods (re-attribution only)
    t = r["by_depth_fill_year"]["true"]["pooled"]
    f = r["by_depth_fill_year"]["fifo"]["pooled"]
    assert abs((t["deep"]["pnl_mix_pct"] + t["shallow"]["pnl_mix_pct"])
               - (f["deep"]["pnl_mix_pct"] + f["shallow"]["pnl_mix_pct"])) < 0.01
    # the headline: true deep is positive pooled, fifo deep negative
    assert t["deep"]["pnl_mix_pct"] > 0 and f["deep"]["pnl_mix_pct"] < 0
    # per-year true deep is positive in all five years (fill-year clock)
    for y in range(5):
        assert r["by_depth_fill_year"]["true"][str(y)]["deep"]["pnl_mix_pct"] > 0, y
    # oc_contrib cross-check: fifo pooled deep matches its -80.72 (tolerance 0.05)
    assert abs(f["deep"]["pnl_mix_pct"] + 80.72) < 0.05
    # inversion mechanism present
    assert r["mechanism"]["inversion_rate"] > 0.5
    # exit speed falls with depth (deep exits first)
    sp = r["mechanism"]["exit_speed_true"]
    assert sp["5.0"]["median_hold_min"] < sp["2.5"]["median_hold_min"]
