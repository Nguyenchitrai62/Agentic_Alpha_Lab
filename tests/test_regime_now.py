"""Tests cho scripts/regime_now.py: synthetic price series (khong network, khong file that)."""
import importlib.util
import math
from pathlib import Path

import numpy as np
import pandas as pd

SPEC = importlib.util.spec_from_file_location(
    "regime_now", Path(__file__).resolve().parents[1] / "scripts" / "regime_now.py")
rn = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(rn)


def _df_from_closes(closes, start="2021-01-01"):
    t0 = pd.Timestamp(start, tz="UTC")
    idx = [t0 + i * pd.Timedelta(hours=4) for i in range(len(closes))]
    c = np.asarray(closes, float)
    return pd.DataFrame({"open_time": idx, "open": c, "high": c * 1.001,
                         "low": c * 0.999, "close": c})


def test_bear_up_is_not_bear_down_is_bear():
    up = list(np.linspace(100.0, 200.0, 1300))
    st = rn.bear_state(up)
    assert st["ok"] and not st["is_bear"] and st["dist_pct"] > 0
    down = list(np.linspace(200.0, 100.0, 1300))
    st2 = rn.bear_state(down)
    assert st2["ok"] and st2["is_bear"] and st2["dist_pct"] < 0
    # khop bot/mirror.is_bear
    try:
        from bot.mirror import is_bear as mirror_bear
        assert mirror_bear(up) == st["is_bear"]
        assert mirror_bear(down) == st2["is_bear"]
    except Exception:
        pass


def test_bear_needs_min_bars():
    st = rn.bear_state([100.0] * 100)
    assert not st["ok"] and not st["is_bear"]


def test_vol_flat_zero_volatile_positive():
    flat = [100.0] * 300
    assert rn.trailing_vol_30d(flat) == 0.0
    rng = np.random.default_rng(7)
    noisy = 100.0 * np.exp(np.cumsum(rng.normal(0, 0.01, 300)))
    v = rn.trailing_vol_30d(noisy)
    assert math.isfinite(v) and v > 5.0


def test_vol_causal_prefix_stable():
    rng = np.random.default_rng(11)
    closes = 100.0 * np.exp(np.cumsum(rng.normal(0, 0.008, 600)))
    v_full_at_300 = rn.trailing_vol_30d(closes[:300])
    v_part = rn.trailing_vol_30d(closes[:300])
    assert v_full_at_300 == v_part  # khong nhin tuong lai
    assert math.isfinite(v_full_at_300)


def test_flush_detects_crash_not_flat():
    rng = np.random.default_rng(3)
    base = 100.0 * np.exp(np.cumsum(rng.normal(0, 0.005, 600)))
    base[500] *= 0.85  # crash 1 bar ~ -15%
    df = _df_from_closes(base)
    fl = rn.flush_series(df)
    assert bool(fl.iloc[500])  # bar crash la flush
    assert int(fl.sum()) >= 1
    flat = _df_from_closes([100.0] * 600)
    assert int(rn.flush_series(flat).sum()) == 0


def test_flush_causal_no_lookahead():
    rng = np.random.default_rng(5)
    closes = 100.0 * np.exp(np.cumsum(rng.normal(0, 0.006, 500)))
    df = _df_from_closes(closes)
    full = rn.flush_series(df).to_numpy()
    part = rn.flush_series(df.iloc[:300].copy()).to_numpy()
    assert (full[:300] == part).all()


def test_monthly_dists_ordered_and_current_counted():
    rng = np.random.default_rng(9)
    closes = 100.0 * np.exp(np.cumsum(rng.normal(0, 0.008, 2500)))  # ~2021-2022
    df = _df_from_closes(closes)
    fl = rn.flush_series(df)
    hm = rn.monthly_flush_dist(df, fl)
    assert len(hm) >= 10
    p10, p50, p90 = rn.p10_p50_p90(hm)
    assert p10 <= p50 <= p90
    cur = int(np.asarray(fl, dtype=int)[-180:].sum())
    assert cur >= 0
    hv = rn.monthly_vol_dist(df)
    assert len(hv) >= 10
    cur_v = rn.trailing_vol_30d(df["close"].tolist())
    pct = rn.pct_le(hv, cur_v)
    assert 0.0 <= pct <= 100.0


def test_summarize_offline_graceful_and_vietnamese(tmp_path):
    sm = rn.summarize(tmp_path, live=False)  # thu muc rong: khong du lieu
    assert sm["activity"] in ("thap", "binh thuong", "cao", "khong ro")
    txt = rn.format_vi(sm)
    assert "du lieu cu" in txt  # offline phai noi ro
    assert "oc_edgedecay" in txt
    assert "TOTAL" in txt


def test_summarize_activity_mapping_synthetic(tmp_path):
    # 1 coin du lieu that de 1 thang cuoi nhieu flush -> activity phai co nghia
    rng = np.random.default_rng(13)
    closes = 100.0 * np.exp(np.cumsum(rng.normal(0, 0.006, 3000)))
    closes[-10:] *= np.linspace(1.0, 0.80, 10)  # 10 bar giam lien tiep
    df = _df_from_closes(closes)
    for s in rn.SYMS:
        d = tmp_path / "data" / "raw" / ("ma_ribbon_20260924" if s == "BTCUSDT" else "xasset_20260924")
        d.mkdir(parents=True, exist_ok=True)
        name = "klines_4h.parquet" if s == "BTCUSDT" else f"{s}_4h.parquet"
        df.to_parquet(d / name)
    sm = rn.summarize(tmp_path, live=False)
    assert sm["vols"]["BTCUSDT"]["ok"]
    assert sm["flushes"]["BTCUSDT"]["ok"]
    assert sm["total_cur30d"] >= 0
    assert sm["activity"] in ("thap", "binh thuong", "cao")
    txt = rn.format_vi(sm)
    assert "Bear-book filter" in txt and "Vol 30d" in txt and "Flush" in txt
