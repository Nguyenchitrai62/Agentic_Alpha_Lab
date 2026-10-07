"""Tests for oc_postflush (synthetic + alignment; no outcome tuning)."""
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "research" / "tournament" / "oc_postflush" / "results.json"
EVP = ROOT / "research" / "tournament" / "oc_postflush" / "events_postflush.parquet"
HOURLY = ROOT / "research" / "tournament" / "ext" / "hourly_ext.parquet"

MAKER, TAKER, FUND = 0.0002, 0.00055, 0.0001
CUTOFF = pd.Timestamp("2026-09-24", tz="UTC")


def b1_recovery(O, L, Cc, sg):
    return (L < O * (1 - 2.5 * sg)) and (Cc > O * (1 - 1.0 * sg))


def leg_net(pin, pout, exit_ts):
    fund = FUND if pd.Timestamp(exit_ts).hour in (0, 8, 16) else 0.0
    return pout / pin - 1 - MAKER - TAKER - fund


def sigma_from_opens(o: pd.Series) -> pd.Series:
    pc = o / o.shift(1) - 1
    return pc.rolling(360, min_periods=120).std(ddof=1).shift(1)


def test_event_formula_boundaries():
    O, sg = 100.0, 0.01  # B1 < 97.5, recovery > 99.0
    assert b1_recovery(O, 97.49, 99.01, sg)
    assert not b1_recovery(O, 97.51, 99.01, sg)  # B1 fails just above
    assert not b1_recovery(O, 97.49, 98.99, sg)  # recovery fails just below
    assert not b1_recovery(O, 97.49, 99.01, 0.0)  # sg<=0 unusable


def test_entry_exit_timing():
    C = pd.Timestamp("2022-01-01 00:00", tz="UTC")
    idx = pd.date_range("2021-12-31 20:00", "2022-01-01 05:00", freq="min", tz="UTC")
    px = pd.Series(np.arange(len(idx), dtype=float) + 100.0, index=idx)
    pin = px[C + pd.Timedelta(minutes=5)]
    pout = px[C + pd.Timedelta(hours=4)]
    assert pin == px[pd.Timestamp("2022-01-01 00:05", tz="UTC")]
    assert pout == px[pd.Timestamp("2022-01-01 04:00", tz="UTC")]
    r = leg_net(pin, pout, C + pd.Timedelta(hours=4))
    assert abs(r - (pout / pin - 1 - MAKER - TAKER)) < 1e-12  # 04:00 no funding
    # moving the entry bar changes the return; other minutes do not alias it
    px2 = px.copy()
    px2[pd.Timestamp("2022-01-01 00:05", tz="UTC")] *= 1.01
    assert leg_net(px2[C + pd.Timedelta(minutes=5)], pout, C + pd.Timedelta(hours=4)) != r


def test_funding_rule():
    assert abs(leg_net(100.0, 100.0, pd.Timestamp("2022-01-01 08:00", tz="UTC"))
               - (-MAKER - TAKER - FUND)) < 1e-12
    assert abs(leg_net(100.0, 100.0, pd.Timestamp("2022-01-01 04:00", tz="UTC"))
               - (-MAKER - TAKER)) < 1e-12


def test_sigma_causal_truncate():
    h = pd.read_parquet(HOURLY, columns=["t", "open", "sym"])
    h["t"] = pd.to_datetime(h["t"], utc=True)
    hs = h[(h["sym"] == "BTCUSDT") & (h["t"] < CUTOFF)].sort_values("t")
    grid = pd.date_range("2020-08-01", "2023-06-01", freq="4h", tz="UTC")
    o_full = hs.drop_duplicates("t").set_index("t")["open"].reindex(grid).astype(float)
    sig_full = sigma_from_opens(o_full)
    for T in (pd.Timestamp("2022-01-01 00:00", tz="UTC"),
              pd.Timestamp("2022-09-24 00:00", tz="UTC"),
              pd.Timestamp("2023-01-01 12:00", tz="UTC")):
        o_tr = hs[hs["t"] < T].drop_duplicates("t").set_index("t")["open"]
        o_tr = o_tr.reindex(grid[grid < T]).astype(float)
        pc_tr = o_tr / o_tr.shift(1) - 1
        roll_last = pc_tr.rolling(360, min_periods=120).std(ddof=1).iloc[-1]
        assert np.isfinite(sig_full.loc[T])
        assert abs(roll_last - sig_full.loc[T]) < 1e-9
        # a future spike at/after T cannot leak into sigma at T
        o_sp = o_full.copy()
        o_sp.loc[T] *= 1.20
        assert abs(sigma_from_opens(o_sp).loc[T] - sig_full.loc[T]) < 1e-12


def test_year_counts_and_bounds():
    import json
    r = json.load(open(RES))
    ev = pd.read_parquet(EVP)
    ev["C"] = pd.to_datetime(ev["C"], utc=True)
    assert len(ev) == r["meta"]["n_valid"] == sum(y["n"] for y in r["years"])
    assert r["meta"]["n_dropped_incomplete"] == 0
    assert (ev["C"] >= pd.Timestamp("2021-09-24", tz="UTC")).all()
    assert (ev["C"] < pd.Timestamp("2025-09-24", tz="UTC") + pd.Timedelta(days=365)).all()
    assert (ev["C"] + pd.Timedelta(hours=4) <= CUTOFF).all()
    for k, y in enumerate(r["years"]):
        a0 = pd.Timestamp(y["anchor"], tz="UTC")
        n = int(((ev["C"] >= a0) & (ev["C"] < a0 + pd.Timedelta(days=365))).sum())
        assert n == y["n"]
    assert (ev["n_coins"] >= 3).all()


def test_decision_counts_match():
    import json
    r = json.load(open(RES))
    means = np.array([y["mean_net"] for y in r["years"]], float)
    n_pos = int(((np.isfinite(means)) & (means > 0)).sum())
    n_loyo = int(sum(1 for x in r["loyo"] if x["pass"]))
    min_n = min(y["n"] for y in r["years"])
    assert r["decision"]["mean_pos_years"] == f"{n_pos}/5"
    assert r["decision"]["loyo_pass"] == f"{n_loyo}/5"
    assert r["decision"]["min_events_per_year"] == min_n
    assert r["decision"]["promising"] == bool(n_pos >= 4 and n_loyo >= 4 and min_n >= 10)
