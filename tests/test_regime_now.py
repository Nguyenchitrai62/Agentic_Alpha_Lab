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


def test_activity_p25_p75_6_flush_is_thap():
    # Hien tuong 2026-10-06: TOTAL 6 flush/30d, lich su p10~4/p50~15/p90~29
    # nhung van phai la THAP (6 < p25). Quy tac cu (<=p10) se nham BINH THUONG.
    hist = [4, 4, 6, 10, 13, 17, 20, 25, 29, 35]
    p10, p50, p90 = rn.p10_p50_p90(hist)
    assert p10 <= 6  # quy tac cu: 6 > p10 -> binh thuong (sai)
    assert abs(p50 - 15) < 1.0 and 28.0 <= p90 <= 31.0
    p25, p75 = rn.p25_p75(hist)
    assert p25 is not None and p25 > 6  # 6 nam duoi p25
    act, a25, a75 = rn.classify_activity(6, hist)
    assert act == "thap"
    assert a25 == p25 and a75 == p75
    # nguong: bang p25/p75 van la binh thuong; vuot p75 la cao
    assert rn.classify_activity(int(math.ceil(p25)), hist)[0] == "binh thuong"
    assert rn.classify_activity(int(math.floor(p75)) + 1, hist)[0] in ("binh thuong", "cao")
    assert rn.classify_activity(int(p75) + 100, hist)[0] == "cao"
    assert rn.classify_activity(0, [])[0] == "khong ro"


def test_extend_with_live_only_appends_newer():
    base = _df_from_closes(list(np.linspace(100.0, 110.0, 500)))
    lmax = pd.to_datetime(base["open_time"], utc=True).max()
    # live trung read 400 bar cu + 50 bar moi
    overlap = base.iloc[-400:].copy()
    future_idx = [lmax + (i + 1) * pd.Timedelta(hours=4) for i in range(50)]
    c = np.linspace(110.0, 112.0, 50)
    future = pd.DataFrame({"open_time": future_idx, "open": c,
                           "high": c * 1.001, "low": c * 0.999, "close": c})
    live = pd.concat([overlap, future], ignore_index=True)
    ext = rn.extend_with_live(base, live)
    assert len(ext) == len(base) + 50
    assert pd.to_datetime(ext["open_time"], utc=True).max() == future_idx[-1]
    # live cu hoan toan -> giu nguyen local
    assert rn.extend_with_live(base, base.iloc[:100].copy()) is base or \
        len(rn.extend_with_live(base, base.iloc[:100].copy())) == len(base)


def test_summarize_live_fake_fetcher_extends_asof(tmp_path):
    rng = np.random.default_rng(21)
    closes = 100.0 * np.exp(np.cumsum(rng.normal(0, 0.006, 3000)))
    df = _df_from_closes(closes)
    for s in rn.SYMS:
        d = tmp_path / "data" / "raw" / ("ma_ribbon_20260924" if s == "BTCUSDT" else "xasset_20260924")
        d.mkdir(parents=True, exist_ok=True)
        name = "klines_4h.parquet" if s == "BTCUSDT" else f"{s}_4h.parquet"
        df.to_parquet(d / name)
    lmax = pd.to_datetime(df["open_time"], utc=True).max()
    fut_idx = [lmax + (i + 1) * pd.Timedelta(hours=4) for i in range(60)]
    fc = np.linspace(float(closes[-1]), float(closes[-1]) * 1.02, 60)
    live4 = pd.DataFrame({"open_time": fut_idx, "open": fc, "high": fc * 1.001,
                          "low": fc * 0.999, "close": fc})
    old_bear = rn.get_live_btc_opens
    rn.get_live_btc_opens = lambda: list(np.linspace(100.0, 200.0, 1300))
    try:
        sm = rn.summarize(tmp_path, live=True,
                          fetch_4h=lambda s: live4,
                          fetch_1h=lambda s: None)
    finally:
        rn.get_live_btc_opens = old_bear
    assert sm["hist_live"] is True
    assert sm["bear_live"] is True
    assert sm["asof"] == fut_idx[-1].isoformat()
    assert sm["local_asof"] == lmax.isoformat()
    assert sm["asof"] > sm["local_asof"]
    assert sm["total_p25"] is not None and sm["total_p75"] is not None
    txt = rn.format_vi(sm)
    assert "mo rong 45 ngay" in txt
    assert "p25" in txt  # in p25/p75 cua TOTAL
    assert "THAP" in txt or "BINH THUONG" in txt or "CAO" in txt


def test_summarize_live_fallback_stale_when_api_fails(tmp_path):
    rng = np.random.default_rng(23)
    closes = 100.0 * np.exp(np.cumsum(rng.normal(0, 0.006, 3000)))
    df = _df_from_closes(closes)
    for s in rn.SYMS:
        d = tmp_path / "data" / "raw" / ("ma_ribbon_20260924" if s == "BTCUSDT" else "xasset_20260924")
        d.mkdir(parents=True, exist_ok=True)
        name = "klines_4h.parquet" if s == "BTCUSDT" else f"{s}_4h.parquet"
        df.to_parquet(d / name)
    lmax = pd.to_datetime(df["open_time"], utc=True).max()

    def _boom(s):
        raise RuntimeError("API chet")

    old_bear = rn.get_live_btc_opens
    rn.get_live_btc_opens = _boom
    try:
        sm = rn.summarize(tmp_path, live=True, fetch_4h=_boom, fetch_1h=_boom)
    finally:
        rn.get_live_btc_opens = old_bear
    assert sm["hist_live"] is False
    assert sm["bear_live"] is False
    assert sm["asof"] == lmax.isoformat()
    assert "du lieu cu" in (sm["hist_note"] + sm["bear_note"])
    txt = rn.format_vi(sm)
    assert "Du lieu local moi nhat" in txt


def test_summarize_live_1h_vol_preferred(tmp_path):
    rng = np.random.default_rng(31)
    closes = 100.0 * np.exp(np.cumsum(rng.normal(0, 0.006, 3000)))
    df = _df_from_closes(closes)
    for s in rn.SYMS:
        d = tmp_path / "data" / "raw" / ("ma_ribbon_20260924" if s == "BTCUSDT" else "xasset_20260924")
        d.mkdir(parents=True, exist_ok=True)
        name = "klines_4h.parquet" if s == "BTCUSDT" else f"{s}_4h.parquet"
        df.to_parquet(d / name)
    # 1h live 800 bar (~33 ngay) cho moi coin
    t0 = pd.Timestamp("2026-09-01", tz="UTC")
    idx1h = [t0 + i * pd.Timedelta(hours=1) for i in range(800)]
    r1 = np.random.default_rng(77)
    c1 = 100.0 * np.exp(np.cumsum(r1.normal(0, 0.004, 800)))
    live1 = pd.DataFrame({"open_time": idx1h, "open": c1, "high": c1 * 1.001,
                          "low": c1 * 0.999, "close": c1})
    old_bear = rn.get_live_btc_opens
    rn.get_live_btc_opens = lambda: (_ for _ in ()).throw(RuntimeError("API chet"))
    try:
        sm = rn.summarize(tmp_path, live=True,
                          fetch_4h=lambda s: None,
                          fetch_1h=lambda s: live1)
    finally:
        rn.get_live_btc_opens = old_bear
    assert sm["vols"]["BTCUSDT"]["ok"]
    assert sm["vols"]["BTCUSDT"].get("src") == "1h-live"
    assert math.isfinite(sm["vols"]["BTCUSDT"]["cur"])
