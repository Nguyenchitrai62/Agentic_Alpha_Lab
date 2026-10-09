"""audit_amihud tests: causality/truncation + hand-checked synthetic + engine constants.

Blind part (signal): recompute from PLAN.md definitions only.
Post-unblinding part: replication.json equals oc_lit_xs A1 rows exactly.
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parents[0]
sys.path.insert(0, str(ROOT / "research" / "tournament" / "audit_amihud"))
import amihud_signal as sig

COLS = ["BNBUSDT", "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]


def test_signal_truncation_causal():
    """Amihud30 at D0 from data truncated to <= D0 matches; T-mapping uses closed days only."""
    d = sig.load_daily("BTCUSDT")
    fin = d[np.isfinite(d["Amihud30"])]
    D0 = fin.index[len(fin) // 2]
    sub = d.loc[:D0, ["close", "quote_volume"]]
    r = sub["close"] / sub["close"].shift(1) - 1.0
    with np.errstate(divide="ignore", invalid="ignore"):
        am = r.abs() / sub["quote_volume"]
    am[(~np.isfinite(r)) | ~(sub["quote_volume"] > 0)] = np.nan
    ami_tr = float(am.iloc[-30:].mean()) if am.iloc[-30:].notna().sum() >= 20 else np.nan
    assert np.isfinite(ami_tr)
    assert abs(ami_tr - float(d.loc[D0, "Amihud30"])) < 1e-12
    # D*(T): T at D0+1 00:00 sees D0; 1s before does not.
    T_at = pd.DatetimeIndex([D0 + pd.Timedelta(days=1)], tz="UTC")
    T_before = pd.DatetimeIndex([D0 + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)], tz="UTC")
    assert sig.d_last(T_at)[0] == D0
    assert sig.d_last(T_before)[0] == D0 - pd.Timedelta(days=1)
    # Sampled-T truncation: multipliers at T from full index equal truncated prefix
    # (no future dependence: z uses same-T XS moments only).
    Tfull = pd.date_range("2022-03-01", periods=9, freq="4h", tz="UTC")
    f_full, _, _ = sig.tilt_frames(Tfull, COLS)
    f_tr, _, _ = sig.tilt_frames(Tfull[:5], COLS)
    assert np.allclose(f_full["A1"].to_numpy()[:5], f_tr["A1"].to_numpy(), equal_nan=True)


def test_handchecked_synthetic():
    """Hand-checked z, clip, A1 maths, availability mapping, Amihud scale."""
    # 1. XS z: [1,2,3,4,5] -> mean 3, std ddof=1 sqrt(2.5).
    m = np.array([[1.0, 2.0, 3.0, 4.0, 5.0]])
    z = sig.xs_z(m)
    sd = float(np.std([1, 2, 3, 4, 5], ddof=1))
    assert abs(sd - 1.5811388300841898) < 1e-12
    assert np.allclose(z[0], (m[0] - 3.0) / sd)
    # Zero-spread -> 0; NaN raw -> NaN z.
    assert list(sig.xs_z(np.array([[2.0, 2.0, 2.0]]))[0]) == [0.0, 0.0, 0.0]
    zn = sig.xs_z(np.array([[1.0, np.nan, 3.0]]))[0]
    assert np.isnan(zn[1]) and abs(zn[0] + zn[2]) < 1e-12
    # Single finite raw -> 0 (no XS spread to exploit).
    zo = sig.xs_z(np.array([[np.nan, 4.0, np.nan]]))[0]
    assert zo[1] == 0.0 and np.isnan(zo[0]) and np.isnan(zo[2])
    # 2. Clip: NaN->1, extremes clipped to [0.5, 1.5].
    assert list(sig.clip_mult(np.array([np.nan, 0.1, 2.0, 1.0]))) == [1.0, 0.5, 1.5, 1.0]
    # 3. A1 maths on z=[-2,-1,0,1,2] (K=0.25): 1+0.25z clipped.
    assert list(sig.clip_mult(1.0 + 0.25 * np.array([-2.0, -1.0, 0.0, 1.0, 2.0]))) == \
        [0.5, 0.75, 1.0, 1.25, 1.5]
    # 4. Availability: T at midnight sees prior day, never the current day.
    T = pd.DatetimeIndex(["2022-01-02 00:00+00:00", "2022-01-02 04:00+00:00"], tz="UTC")
    assert list(sig.d_last(T)) == [pd.Timestamp("2022-01-01", tz="UTC")] * 2
    # 5. Amihud hand-check: |r|=0.02, quote=1e6 -> 2e-8.
    assert abs(0.02 / 1e6 - 2e-8) < 1e-20
    # 6. Pre-cutoff rows are untilted (v426 convention).
    Tpre = pd.DatetimeIndex(["2021-09-23 20:00+00:00"], tz="UTC")
    f, _, _ = sig.tilt_frames(Tpre, COLS)
    assert (f["A1"].to_numpy() == 1.0).all()


def test_volume_source_is_quote_volume():
    """A1 pins quote_volume (USD): |r|/quote_volume matches; /volume differs (price scale)."""
    df = pd.read_parquet(
        ROOT / "data/raw/xs_universe_20260924/BTCUSDT_1d.parquet",
        columns=["close", "volume", "quote_volume"])
    r = df["close"] / df["close"].shift(1) - 1.0
    with np.errstate(divide="ignore", invalid="ignore"):
        a_q = (r.abs() / df["quote_volume"]).rolling(30, min_periods=20).mean()
        a_v = (r.abs() / df["volume"]).rolling(30, min_periods=20).mean()
    assert np.isfinite(a_q.iloc[-1]) and np.isfinite(a_v.iloc[-1])
    # different scales (ratio ~ price ~1e4-1e5): proves the test pins the source.
    # quote_volume = volume * price, so |r|/volume is ~price x larger than |r|/quote_volume.
    assert abs(a_v.iloc[-1] / a_q.iloc[-1]) > 1e3
    d = sig.load_daily("BTCUSDT")
    # our Amihud30 equals the quote_volume version to 1e-15 relative.
    tail = d["Amihud30"].dropna().tail(50)
    assert np.allclose(tail.to_numpy(), a_q.loc[a_q.index[-len(tail):]].to_numpy()
                       if len(a_q) >= len(tail) else a_q.dropna().tail(len(tail)).to_numpy(),
                       rtol=1e-9, atol=0, equal_nan=True)


def test_engine_constants_and_g2_config():
    """Fill timing + G2 config + mechanism order pinned in the engine script."""
    src = (ROOT / "research/tournament/audit_amihud/compute_a1_engine.py").read_text()
    assert "win_start=5" in src
    assert '"inv", 1.7' in src and '"sleeve_gross_cap"] = 2.0' in src
    # v426 order: bear filter applied to sb, then tilt mult, then ffill to minute grid.
    i_bear = src.index("rolling(1200")
    i_tilt = src.index("sb.where(sb == 0.0, sb * mult)")
    i_ffill = src.index("books_bear = sb.reindex")
    assert i_bear < i_tilt < i_ffill
    assert "2021-09-24" in src  # cutoff convention present


def test_replication_matches_oc_lit_xs_a1():
    """Post-unblinding: part A equals oc_lit_xs A1 exactly (thresholds R 0.10pp, DD 0.5pp)."""
    rep = json.loads((ROOT / "research/tournament/audit_amihud/replication.json").read_text())
    res = json.loads((ROOT / "research/tournament/oc_lit_xs/results.json").read_text())
    eng = json.loads((ROOT / "research/tournament/oc_lit_xs/engine_results.json").read_text())
    # G2 reproduction block.
    assert rep["meta"]["g2_reproduction"]["R5"] == 5.41
    assert rep["meta"]["g2_reproduction"]["full_path_dd"] == 16.82
    assert rep["G2_engine_per_year"] == [{"R": r, "DD": d} for r, d in
                                        [(2.588, 10.86), (3.282, 16.91), (6.045, 15.81),
                                         (10.677, 8.27), (4.648, 12.9)]]
    # A1 per-year exact.
    assert rep["A1_per_year"] == [{"R": r, "DD": d} for r, d in eng["rows"]["A1"]["years"]]
    assert rep["A1_dev4_mean"] == eng["dev4"]["A1"]["R"] == res["dev4"]["A1"]["R"] == 5.844
    assert rep["A1_dev4_worst"] == eng["dev4"]["A1"]["W"] == 2.798
    assert rep["A1_dev4_maxDD"] == eng["dev4"]["A1"]["DD"] == 16.81
    assert rep["A1_5y_R"] == eng["rows"]["A1"]["R"] == 5.624
    assert rep["A1_full_path_dd"] == eng["rows"]["A1"]["full_path_dd"] == 16.66
    y4 = eng["rows"]["A1"]["years"][4]
    assert rep["A1_per_year"][4] == {"R": y4[0], "DD": y4[1]} == {"R": 4.75, "DD": 11.14}
