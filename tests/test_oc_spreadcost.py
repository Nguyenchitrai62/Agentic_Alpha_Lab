"""oc_spreadcost tests: synthetic hand checks + cap/constant guards + results consistency."""
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path("research/tournament/oc_spreadcost")
RES = HERE / "results.json"
FILLS = HERE / "fills.parquet"


def _load(name):
    spec = importlib.util.spec_from_file_location(f"oc_spreadcost_{name}", str(HERE / f"{name}.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_spread_hand_case():
    S = _load("spreadcost")
    out = S.spread_bps([100.0], [100.01])
    assert abs(float(out[0]) - 0.01 / 100.005 * 1e4) < 1e-9


def test_spread_invalid_quotes_nan():
    S = _load("spreadcost")
    out = S.spread_bps([100.0, 0.0, -5.0, np.nan, 100.0],
                       [100.0, 100.0, 100.0, 100.0, np.nan])
    assert bool((~np.isfinite(out)).all())  # equal/zero/negative/NaN all excluded


def test_summarize_empty():
    S = _load("spreadcost")
    s = S.summarize([])
    assert s["n"] == 0 and s["median"] == 0.0 and s["max"] == 0.0


def test_top_volatile_ranks_by_range_and_filters_thin():
    S = _load("spreadcost")
    # minute A: flat mid 100 (30 samples); minute B: mid 100..110 (30 samples)
    mA = np.full(30, 60000, dtype=np.int64)
    mB = np.full(30, 120000, dtype=np.int64)
    mC = np.full(3, 180000, dtype=np.int64)  # thin minute, wide but excluded
    minutes = np.concatenate([mA, mB, mC])
    mids = np.concatenate([np.full(30, 100.0),
                           np.linspace(100.0, 110.0, 30),
                           np.array([100.0, 200.0, 100.0])])
    spreads = np.ones(63)
    out = S.top_volatile_minutes(minutes, mids, spreads, top_n=20, min_n=20)
    keys = [m["minute_ms"] for m in out["minutes"]]
    assert keys[0] == 120000 and 180000 not in keys
    assert out["minutes"][0]["range_bps"] > 900.0  # ~10% range


def test_n_vector_exact_threshold_counts():
    S = _load("spreadcost")
    o = np.array([100.0])
    sg = np.array([0.01])  # thr = 97.5
    c = np.array([[97.5, 97.6, np.nan]])
    assert list(S.n_vector(c, o, sg)) == [1, 0, 0]


def test_find_fill_strict():
    S = _load("spreadcost")
    assert S.find_fill(np.array([10.0, 9.0]), 9.0) is None
    assert S.find_fill(np.array([9.0, 8.999, 8.0]), 9.0) == 1


def test_outcome_tp_net_and_stop_first_tie():
    S = _load("spreadcost")
    px, sg = 100.0, 0.01
    tp = px * (1 + sg)
    n = 240
    Ha = np.full(n, tp * 1.01)
    La = np.full(n, px * 0.999)
    Ca = np.full(n, px)
    Oa = np.full(n, px)
    ret, x, how = S.outcome_from_fill(Ha, La, Ca, Oa, 16, px, sg, px, False)
    assert how == "tp"
    assert abs(ret - (tp / px - 1 - 2 * S.MAKER)) < 1e-12
    bl = px * (1 - 8 * sg)
    Ha2 = np.full(n, px)
    Ha2[17] = tp * 1.01
    La2 = np.full(n, px)
    La2[17] = bl - 1.0
    ret2, x2, how2 = S.outcome_from_fill(Ha2, La2, Ca, Oa, 16, px, sg, px, False)
    assert how2 == "backstop" and x2 == 17


def test_apply_extra_cost_routing():
    S = _load("spreadcost")
    assert S.apply_extra_cost(0.01, "tp", 1e-4, 2e-4) == 0.01
    assert S.apply_extra_cost(0.01, "stop", 1e-4, 2e-4) == 0.01 - 2e-4
    assert S.apply_extra_cost(0.01, "backstop", 1e-4, 2e-4) == 0.01 - 2e-4
    assert S.apply_extra_cost(0.01, "time", 1e-4, 2e-4) == 0.01 - 1e-4


def test_phase_grid_offsets():
    S = _load("spreadcost")
    a = S.phase_bar_starts(100000, 0)
    b = S.phase_bar_starts(100000, 1)
    assert int(a[0]) == 0 and int(b[0]) == 60  # 1h clock shift
    assert (np.diff(a) == 240).all()


def test_cost_constants_match_b1_replica():
    S = _load("spreadcost")
    assert (S.MAKER, S.TAKER, S.FUND) == (0.0002, 0.00055, 0.0001)
    assert tuple(S.RUNGS) == (2.5, 3.0, 3.5, 4.0, 5.0)
    assert (S.LIVE_A, S.LIVE_B) == (16, 238)
    assert tuple(S.PHASES) == (0, 1, 2, 3)


def test_year_bucketing_edges():
    S = _load("spreadcost")
    A = [pd.Timestamp(a, tz="UTC") for a in
         ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")]
    YE = pd.Timestamp("2026-09-24 00:00", tz="UTC")
    assert S.year_of(pd.Timestamp("2021-09-24 00:00", tz="UTC"), A, YE) == 0
    assert S.year_of(pd.Timestamp("2022-09-24 00:00", tz="UTC"), A, YE) == 1
    assert S.year_of(pd.Timestamp("2026-09-24 00:00", tz="UTC"), A, YE) is None
    assert S.year_of(pd.Timestamp("2021-09-23 23:59", tz="UTC"), A, YE) is None


def test_replica_cap_at_20260924():
    R = _load("run")
    assert R.END == pd.Timestamp("2026-09-24 00:00", tz="UTC")
    assert R.YEAR_END == pd.Timestamp("2026-09-24 00:00", tz="UTC")


def test_results_internal_consistency():
    out = json.loads(RES.read_text())
    for s, c in out["extra_cost"].items():
        byb = out["spreads"][f"bybit:{s}"]["spread_bps"]
        assert abs(c["extra_p90_frac"] - 0.5 * byb["p90"] / 1e4) < 1e-15
        assert abs(c["extra_med_frac"] - 0.5 * byb["median"] / 1e4) < 1e-15
    tot = out["replica"]["total"]
    assert abs(tot["delta_eq"] - (tot["eq_adj"]["sum"] - tot["eq"]["sum"])) < 1e-9
    assert abs(tot["delta_w"] - (tot["w_adj"]["sum"] - tot["w"]["sum"])) < 1e-9
    per_phase_n = sum(p["n"] for p in out["replica"]["per_phase"])
    assert per_phase_n == out["replica"]["n_fills"] == tot["n"]
    df = pd.read_parquet(FILLS)
    assert len(df) == out["replica"]["n_fills"]
    assert set(df["how"].unique()) <= {"tp", "stop", "backstop", "time"}
    assert abs(float(df["ret"].sum()) - tot["eq"]["sum"]) < 1e-6
