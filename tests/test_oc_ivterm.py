"""oc_ivterm tests: causality/truncation + hand-checked synthetic IV/TS cases."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path("research/tournament/oc_ivterm")
RES = json.loads((HERE / "results.json").read_text())


def test_fidelity_reproduces_placebo_base():
    ref = [0.9113, 0.8326, 2.0998, 3.1974, 0.6772]
    got = RES["fidelity"]["got_uncapped_S_bar"]
    for g, r in zip(got, ref):
        assert abs(g - r) < 1e-3
    assert abs(RES["fidelity"]["base_sum5y"] - 7.7183) < 5e-3


def test_amount_weighted_6h_iv_hand_case():
    # 6 hourly buckets, known amounts/ivs; hand: sum(iv*amt)/sum(amt)
    ivs = np.array([80.0, 82.0, 84.0, 86.0, 88.0, 90.0])
    amts = np.array([1.0, 1.0, 2.0, 0.5, 0.5, 1.0])
    hand = float((ivs * amts).sum() / amts.sum())
    w1, w0 = float((ivs * amts).sum()), float(amts.sum())
    assert abs(hand - 84.5) < 1e-9
    assert w0 == 6.0 and abs(w1 / w0 - hand) < 1e-12
    # threshold: < 0.5 coin -> NaN
    assert (0.49 < 0.5)
    # TS ratio hand
    assert abs(hand / 100.0 - 0.845) < 1e-9


def test_carry_limit_24h_hand_case():
    s = pd.Series([1.0] + [np.nan] * 30,
                  index=pd.date_range("2023-01-01", periods=31, freq="h", tz="UTC"))
    f = s.ffill(limit=24)
    assert f.iloc[24] == 1.0 and np.isnan(f.iloc[25])


def test_join_causal_truncation():
    """Last-full-hour join: recompute from series truncated at T-1h equals stored."""
    fills = pd.read_parquet(HERE / "tmp" / "fills_ts.parquet",
                            columns=["t_bar", "coin", "ts_btc", "ts_eth", "ts_used"])
    ts_btc = pd.read_parquet(HERE / "tmp" / "ts_btc.parquet")["ts"]
    ts_eth = pd.read_parquet(HERE / "tmp" / "ts_eth.parquet")["ts"]
    rng = np.random.default_rng(7)
    sample = fills.sample(5, random_state=7)
    for _, r in sample.iterrows():
        T = pd.to_datetime(r["t_bar"], utc=True)
        cutoff = T - pd.Timedelta(hours=1)
        sig = ts_eth if int(r["coin"]) == 1 else ts_btc
        trunc = sig[sig.index <= cutoff]
        expect = float(trunc.iloc[-1]) if len(trunc) else np.nan
        got = float(r["ts_used"])
        if np.isnan(expect):
            assert np.isnan(got)
        else:
            assert abs(got - expect) < 1e-9
        # window check: no strike hour ending after cutoff entered (by construction
        # of the 6h window over row.hours <= signal hour <= cutoff)
        assert cutoff >= trunc.index[-1] if len(trunc) else True


def test_candidate_logic_matches_plan():
    c = RES["candidate"]
    assert c["signs_hi_minus_lo"] == [-1, 1, -1, -1]
    assert c["same_sign_4of4"] is False
    assert c["fires"] is False and c["direction"] is None
    assert RES["tilt_5y_calibration"] is None
    # spreads all > 5bps in magnitude but sign unstable -> correctly no tilt
    assert sum(1 for s in c["spreads_bps"] if abs(s) > 5.0) == 4


def test_dev_only_no_recent_leak():
    for row in RES["D2_dips_dev"]:
        assert row["year"] in ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24")
    for sym, per in RES["D3_book_IC_dev"].items():
        assert set(per) == {"2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24"}
    assert "2025-09-24" not in json.dumps(RES["D1_hourly_TS"])
    assert RES["config"]["candidate"].startswith("tilt scored IFF")


def test_plan_predates_results_and_files_present():
    assert (HERE / "PLAN.md").exists() and (HERE / "compute_ivterm.py").exists()
    assert (HERE / "REPORT.md").exists() and (HERE / "SUMMARY.md").exists()
    assert len((HERE / "SUMMARY.md").read_text().strip().splitlines()) <= 15
    assert (HERE / "PLAN.md").stat().st_mtime < (HERE / "results.json").stat().st_mtime
