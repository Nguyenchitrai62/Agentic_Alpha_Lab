"""Tests for oc_manualtsmom (PLAN.md frozen before outcomes)."""
from __future__ import annotations

import importlib.util
import json
import pickle
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).parents[1]
HERE = ROOT / "research/tournament/oc_manualtsmom"
RES = json.loads((HERE / "results.json").read_text())
RD = ROOT / "research/parallel/rounds/parallel-20260906-r2"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_data_cap():
    h = pd.read_parquet(ROOT / "research/tournament/ext/hourly_ext.parquet", columns=["t"])
    t = pd.to_datetime(h["t"], utc=True)
    assert bool((t < pd.Timestamp("2026-09-24 00:00", tz="UTC")).all())


def test_sleeve_exact_vs_octsmom():
    assert RES["checks"]["max_sleeve_abs_gap_vs_octsmom"] < 1e-6


def test_day_boundary_and_eqmin():
    assert RES["checks"]["max_day_boundary_gap"] < 1e-9
    assert RES["checks"]["max_eqmin_above_eq"] <= 1e-9


def test_base_proof_vs_oc_manualcap():
    assert RES["base_proof"]["match_R"] and RES["base_proof"]["match_DD"]
    ref = json.loads((ROOT / "research/diagnostics/oc_manualcap/results.json").read_text())["rows"]["M5_human"]
    assert RES["book"]["pool_nb"] == ref["book_trades"]
    assert abs(RES["book"]["pool_win"] - ref["book_win"]) < 1e-9


def test_hand_cases():
    # flat closes -> zero position; straight-up trend -> +1 scaled; costs/funding exact
    import sys
    sys.path.insert(0, str(HERE))
    run = _load("run_mtm_test", HERE / "run_manualtsmom.py")
    days = pd.date_range("2021-01-01", periods=70, freq="D", tz="UTC")
    flat = pd.DataFrame(100.0, index=days, columns=run.COINS)
    _s, _v, p = run.compute_positions(flat)
    assert bool((p.to_numpy() == 0.0).all())
    up = pd.DataFrame({"BTCUSDT": 100 * 1.001 ** np.arange(70),
                       "ETHUSDT": 100 * 1.001 ** np.arange(70)}, index=days)
    _s2, v2, p2 = run.compute_positions(up)
    assert bool((p2.iloc[-1] > 0).all()) and bool((p2.iloc[-1] <= 1.0).all())
    # one-day open-to-open gain, short position: no funding, no rebalance cost
    opens = pd.DataFrame({"BTCUSDT": [100.0, 110.0], "ETHUSDT": [100.0, 100.0]},
                         index=[days[0], days[1]])
    pos = pd.DataFrame({"BTCUSDT": [-0.5], "ETHUSDT": [0.0]}, index=[days[0] - pd.Timedelta(days=1)])
    # emulate sleeve_daily single day via the real function on a 1-day frame
    pos_full = pd.DataFrame(0.0, index=days, columns=run.COINS)
    pos_full.loc[days[0] - pd.Timedelta(days=1)] = [-0.5, 0.0]
    opens_full = pd.DataFrame(np.nan, index=days, columns=run.COINS)
    opens_full.loc[days[0]] = [100.0, 100.0]
    opens_full.loc[days[1]] = [110.0, 100.0]
    sdf = run.sleeve_daily(opens_full, pos_full, [days[0]])
    # short gains when price rises? no: short loses: -0.5*(0.10) = -0.05; cost from prev=0: 0.00055*0.5
    assert abs(float(sdf.loc[days[0], "gross"]) - (-0.05)) < 1e-12
    assert abs(float(sdf.loc[days[0], "cost"]) - 0.00055 * 0.5) < 1e-12
    assert float(sdf.loc[days[0], "fund"]) == 0.0


def test_recompute():
    for c in RES["combos"]:
        for y in c["years"]:
            for tot, m in ((y["total_pct"], y["monthly_pct"]),
                           (y["base_total_pct"], y["base_monthly_pct"])):
                m2 = (1 + tot / 100) ** (1 / 12) - 1
                assert abs(m2 * 100 - m) < 1e-3, (c, y)
            nb, wb, ns, ws = y["book_nb"], y["book_wb"], y["sleeve_n"], y["sleeve_w"]
            assert abs(y["win"] - (wb + ws) / (nb + ns)) < 1e-4
        tots = [y["total_pct"] / 100 for y in c["years"]]
        r5 = (float(np.prod([1 + t for t in tots])) ** (1 / 60) - 1) * 100
        assert abs(r5 - c["R_5y"]) < 1e-3
        assert c["W"] == min(y["monthly_pct"] for y in c["years"])
        assert c["DD_maxyearly"] == max(y["maxDD_pct"] for y in c["years"])
        ex = np.array([y["excess_monthly_pp"] for y in c["years"]])
        full = float(np.mean(ex))
        n_pos = int((ex > 0).sum())
        loyo = sum(bool(np.sign(float(np.mean([ex[k] for k in range(5) if k != h]))) == np.sign(full))
                   for h in range(5)) if full != 0 else 0
        assert c["excess_pos_years"] == f"{n_pos}/5"
        assert c["loyo_sign_hold"] == f"{loyo}/5"
        assert c["promising_default"] == bool(n_pos >= 4 and loyo >= 4)
        pool_win = (sum(y["book_wb"] for y in c["years"]) + sum(y["sleeve_w"] for y in c["years"])) / \
            (sum(y["book_nb"] for y in c["years"]) + sum(y["sleeve_n"] for y in c["years"]))
        assert abs(pool_win - c["pool_win"]) < 1e-4
        assert c["base_hit"] == bool(c["R_5y"] >= 5.0 and c["DD_maxyearly"] < 20.0
                                     and c["full_path_dd"] < 20.0 and c["pool_win"] >= 0.55)
    assert RES["checks"]["max_monthly_total_residual_pp"] < 1e-3


def test_fullpath_dd_recompute():
    v388 = _load("v388_mtm_t", RD / "v388" / "v388_bot_stop_distance.py")
    g1 = v388.Y1 + pd.Timedelta(hours=12)
    allres = pickle.loads((ROOT / "research/diagnostics/oc_manualcap/oc_manualcap_runs.pkl").read_bytes())
    runs = {s: {"M5_human": allres[s]["M5_human"]["run"]} for s in allres}
    e_full, mn_full = v388.mix(runs, "M5_human", g1)
    segf = e_full.index > pd.Timestamp("2021-09-24", tz="UTC")
    ef = e_full[segf].to_numpy(float)
    mf = mn_full[segf].to_numpy(float)
    # pure-base full-path DD sanity: finite and in a plausible band around reference 17.79
    fp = float(np.max(1 - mf / np.maximum.accumulate(ef))) * 100
    assert abs(fp - 17.79) < 0.01
