"""Tests for research/tournament/oc_placebo (seeded screen placebo study)."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve()
ROOT = HERE.parents[1]
OC = ROOT / "research" / "tournament" / "oc_placebo"
OC_CME = ROOT / "research" / "tournament" / "oc_cmegap"
CACHE = ROOT / "artifacts" / "research" / "engine_real"

SPEC = importlib.util.spec_from_file_location(
    "oc_placebo_mod", OC / "compute_placebo.py")
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


def _results():
    return json.loads((OC / "results.json").read_text())


def test_files_exist_and_schema():
    assert (OC / "compute_placebo.py").exists()
    assert (OC / "REPORT.md").exists()
    assert (OC / "results.json").exists()
    r = _results()
    assert set(r) == {"meta", "base", "real", "placebo_expiry",
                      "placebo_cme", "stricter"}
    assert r["meta"]["n_bars"] == 10955
    assert r["meta"]["seed"] == 20261006
    assert r["placebo_expiry"]["n"] == 1000
    assert r["placebo_cme"]["n"] == 1000
    for k in ("dPnl_5y", "dDD_full", "pass"):
        assert len(r["placebo_expiry"][k]) == 1000, k
    for k in ("dPnl_5y", "dDD_full", "pass_strict", "pass_loose"):
        assert len(r["placebo_cme"][k]) == 1000, k


def test_base_matches_cme_base():
    r = _results()
    # Rebuilt base bit-matches the oc_cmegap base (same books + bear filter).
    orig = json.loads((OC_CME / "results.json").read_text())
    for y_new, y_old in zip(r["base"]["year_totals"],
                            [y["book_pnl_base"] for y in orig["years"]]):
        assert abs(y_new - y_old) < 1e-6
    assert abs(r["base"]["full_total"] - orig["full_path"]["total_pnl_base"]) < 1e-6
    assert abs(r["base"]["full_maxDD"] - orig["full_path"]["maxDD_base"]) < 1e-9


def test_real_cme_matches_original():
    r = _results()
    orig = json.loads((OC_CME / "results.json").read_text())
    d_pnl = orig["full_path"]["total_pnl_rule"] - orig["full_path"]["total_pnl_base"]
    d_dd = orig["full_path"]["maxDD_rule"] - orig["full_path"]["maxDD_base"]
    assert abs(r["real"]["cme"]["dPnl_5y"] - d_pnl) < 1e-6
    assert abs(r["real"]["cme"]["dDD_full"] - d_dd) < 1e-9
    assert r["real"]["cme"]["passes_cme_strict"] is True


def test_decision_counts_consistent():
    r = _results()
    e = r["placebo_expiry"]
    assert abs(e["fpr_expiry_criterion"] - float(np.mean(e["pass"]))) < 1e-9
    c = r["placebo_cme"]
    assert abs(c["fpr_cme_strict_4pnl_5dd"] - float(np.mean(c["pass_strict"]))) < 1e-9
    assert abs(c["fpr_cme_loose_4pnl_4dd"] - float(np.mean(c["pass_loose"]))) < 1e-9
    # Real-rule pass flags follow the stated leg thresholds.
    re_ = r["real"]["expiry"]
    assert re_["passes_expiry_criterion"] == bool(
        re_["dd_wins"] >= 4 and re_["ret98_wins"] >= 4)
    rc = r["real"]["cme"]
    assert rc["passes_cme_strict"] == bool(
        rc["pnl_ge_wins"] >= 4 and rc["dd_wins"] == 5)


def test_percentiles_recomputed():
    r = _results()
    for fam, real in (("placebo_expiry", r["real"]["expiry"]),
                      ("placebo_cme", r["real"]["cme"])):
        dp = np.asarray(r[fam]["dPnl_5y"])
        dd = np.asarray(r[fam]["dDD_full"])
        assert abs(r[fam]["real_dPnl_percentile"]
                   - round(float(np.mean(dp <= real["dPnl_5y"])) * 100, 2)) < 1e-9
        assert abs(r[fam]["real_dDD_percentile"]
                   - round(float(np.mean(dd <= real["dDD_full"])) * 100, 2)) < 1e-9


def test_stricter_gates_and_fpr_budget():
    r = _results()
    s = r["stricter"]
    e, c = r["placebo_expiry"], r["placebo_cme"]
    assert abs(s["gate_exp_pnl_p95"] - float(np.quantile(e["dPnl_5y"], 0.95))) < 2e-6
    assert abs(s["gate_exp_dd_p05"] - float(np.quantile(e["dDD_full"], 0.05))) < 2e-6
    assert abs(s["gate_cme_pnl_p95"] - float(np.quantile(c["dPnl_5y"], 0.95))) < 2e-6
    assert abs(s["gate_cme_dd_p05"] - float(np.quantile(c["dDD_full"], 0.05))) < 2e-6
    for k in ("exp_legs_plus_both_tails_fpr", "cme_strict_plus_both_tails_fpr",
              "exp_legs_plus_pnl_tail_fpr", "exp_legs_plus_dd_tail_fpr",
              "cme_strict_plus_pnl_tail_fpr", "cme_strict_plus_dd_tail_fpr"):
        assert 0.0 <= s[k] <= 0.05, (k, s[k])
    # Joint gate rejects both real rules (matches both engine NOs).
    assert s["real_exp_passes_legs_plus_both"] is False
    assert s["real_cme_passes_strict_plus_both"] is False


def test_helpers_hand_checked():
    assert abs(MOD.max_dd(np.array([1.0, 1.1, 1.05, 1.2]))
               - (1.0 - 1.05 / 1.1)) < 1e-12
    eq = MOD.equity_path(np.array([0.1, -0.05]))
    assert np.allclose(eq, [1.0, 1.1, 1.045])
    w = np.array([[0.5, -0.2], [0.25, -0.2], [0.25, 0.0]])
    c = MOD.turnover_cost(w)
    assert np.allclose(c, 0.0005 * np.abs(
        w - np.vstack([np.zeros((1, 2)), w[:-1, :]])))


def _grid_sample():
    # Small synthetic grid (September 2021 has 7 days on the real grid edge).
    return pd.DatetimeIndex(pd.date_range("2021-09-24", periods=200, freq="4h", tz="UTC"))


def test_expiry_mask_shape_and_reproducibility():
    grid = pd.DatetimeIndex(pd.date_range("2021-09-24", periods=2190, freq="4h", tz="UTC"))
    a = MOD.gen_expiry_mask(grid, np.random.default_rng(20261006))
    b = MOD.gen_expiry_mask(grid, np.random.default_rng(20261006))
    assert bool((a == b).all())  # seeded reproducibility
    # One 12-bar contiguous window per calendar month, fully inside the month.
    months = pd.Series(grid).dt.tz_localize(None).dt.to_period("M").to_numpy()
    n_months = len(pd.unique(months))
    assert int(a.sum()) == n_months * 12
    for key in pd.unique(months):
        loc = np.where(months == key)[0]
        win = np.where(a[loc])[0]
        assert len(win) == 12
        assert bool((np.diff(win) == 1).all())  # contiguous
    assert 0.06 < float(a.mean()) < 0.075  # ~12/180 per month
    # Generator uses only grid + RNG (never returns/weights).
    import inspect
    params = list(inspect.signature(MOD.gen_expiry_mask).parameters)
    assert not any(p in params for p in ("returns", "pnl", "weights", "r1"))


def test_cme_mask_shape():
    year_pos = np.arange(2190)
    taken, mult = MOD.gen_cme_masks(year_pos, np.random.default_rng(7))
    assert int(taken.sum()) >= 10 * 12 and int(taken.sum()) <= 10 * 24
    # Runs are the placed windows: 10 non-overlapping, lengths in {12,18,24}.
    idx = np.where(taken)[0]
    runs = np.split(idx, np.where(np.diff(idx) != 1)[0] + 1)
    assert len(runs) == 10
    assert all(len(w) in (12, 18, 24) for w in runs)
    assert set(np.unique(mult[taken])).issubset({0.75, 1.25})
    assert bool((mult[~taken] == 1.0).all())
    import inspect
    params = list(inspect.signature(MOD.gen_cme_masks).parameters)
    assert not any(p in params for p in ("returns", "pnl", "weights", "r1"))


def test_bear_matches_v410_sampled():
    opens_full = pd.read_parquet(CACHE / "opens_v154.parquet")
    btc = opens_full["BTCUSDT"].sort_index()
    ma = btc.rolling(1200, min_periods=600).mean()
    bear_full = (btc < ma).fillna(False)
    # Sample real 4h grid timestamps; MOD.bear_flags must match v410 exactly.
    grid = btc.index[(btc.index >= pd.Timestamp("2021-09-24", tz="UTC"))
                     & (btc.index < pd.Timestamp("2026-09-24", tz="UTC"))]
    sample = grid[::997][:10]
    got = MOD.bear_flags(opens_full, sample)
    for t, g in zip(sample, got):
        assert bool(g) == bool(bear_full.reindex([t]).fillna(False).iloc[0])


def test_report_has_verdict_line():
    text = (OC / "REPORT.md").read_text()
    assert "## Verdict" in text
    assert "FPR" in text or "fpr" in text
    assert "placebo" in text.lower()
