"""Tests for oc_bookvol (research/tournament/oc_bookvol). Lightweight checks on results.json + causality of scales."""

import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parents[1] / "research" / "tournament" / "oc_bookvol"
RES = HERE / "results.json"
SYMS = ["BNBUSDT", "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]


def _load():
    return json.loads(RES.read_text())


def _mod():
    spec = importlib.util.spec_from_file_location("oc_bookvol_compute", HERE / "compute_bookvol.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _synthetic(n=500, seed=7):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2023-01-01", periods=n + 1, freq="4h", tz="UTC")
    opens = pd.DataFrame({s: 100.0 * np.cumprod(1 + 0.005 * rng.standard_normal(n + 1)) for s in SYMS}, index=idx)
    books = pd.DataFrame(rng.standard_normal((n + 1, len(SYMS))) * 0.05,
                        index=idx, columns=SYMS)
    fwd1 = opens.shift(-1) / opens - 1.0
    books, fwd1 = books.iloc[:-1], fwd1.iloc[:-1]
    return books, fwd1, opens


def test_results_exists_and_schema():
    assert RES.exists(), "run research/tournament/oc_bookvol/compute_bookvol.py first"
    r = _load()
    for k in ("variants", "decision", "definitions", "anchor_years", "n_bars"):
        assert k in r, k
    assert set(r["variants"]) == {"base_60d", "a_riskparity30d", "b_slow120d", "c_semi60d"}
    assert set(r["decision"]) == {"a_riskparity30d", "b_slow120d", "c_semi60d"}
    for name, v in r["variants"].items():
        assert len(v["per_year"]) == 5, name
        for row in v["per_year"]:
            for k in ("n_bars", "ret", "dd", "sharpe"):
                assert k in row, (name, row)
    assert r["n_bars"] == 10955


def test_year_partition_covers_grid():
    r = _load()
    per = r["variants"]["base_60d"]["per_year"]
    ns = [row["n_bars"] for row in per]
    assert sum(ns) == r["n_bars"], ns
    assert ns[2] == 2196  # leap-year partition 2023-09-24..2024-09-24
    assert ns[0] == 2190 and ns[1] == 2190 and ns[3] == 2190 and ns[4] == 2189


def test_turnover_cost_nonnegative():
    r = _load()
    for name, v in r["variants"].items():
        assert v["total_turnover"] >= 0, name
        assert v["total_cost"] >= 0, name
        assert abs(v["total_cost"] - 0.0005 * v["total_turnover"]) < 5e-4, name


def test_decision_matches_counts():
    r = _load()
    for name, d in r["decision"].items():
        n_sh = sum(1 for x in d["dSharpe"] if x is not None and x > 0)
        n_dd = sum(1 for x in d["dDD"] if x is not None and x > 0)
        assert d["sharpe_pos"] == f"{n_sh}/5", name
        assert d["dd_pos"] == f"{n_dd}/5", name
        expect = n_sh >= 4 and n_dd >= 4 and int(d["loyo_sharpe"][0]) >= 4 and int(d["loyo_dd"][0]) >= 4
        assert d["promising"] == expect, name
    assert all(not r["decision"][k]["promising"] for k in r["decision"])


def test_scales_causal_on_truncation():
    mod = _mod()
    books, fwd1, _ = _synthetic()
    full, _ = mod.compute_scales(books, fwd1)
    for cut in (300, 420):
        part, _ = mod.compute_scales(books.iloc[: cut + 1], fwd1.iloc[: cut + 1])
        for name in full:
            pd.testing.assert_frame_equal(full[name].iloc[: cut + 1], part[name], check_dtype=False)


def test_scale_uses_only_bars_before_t():
    mod = _mod()
    books, fwd1, opens = _synthetic()
    k = 350  # perturb opens strictly after opens[k]; fwd rows <= k-1 keep, so scaled rows <= k-1 keep
    opens2 = opens.copy()
    opens2.iloc[k + 1 :] *= 2.0
    fwd2 = opens2.shift(-1) / opens2 - 1.0
    fwd2 = fwd2.iloc[:-1]
    assert len(fwd2) == len(fwd1)
    full, _ = mod.compute_scales(books, fwd1)
    pert, _ = mod.compute_scales(books, fwd2)
    for name in full:
        pd.testing.assert_frame_equal(full[name].iloc[:k], pert[name].iloc[:k], check_dtype=False)
