"""Tests for oc_tailhedge (monthly long-BTC-put overlay on G2 / G2K20)."""

import importlib.util
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / "research" / "tournament" / "oc_tailhedge"
CAP = pd.Timestamp("2026-09-24 00:00", tz="UTC")


def _mod():
    spec = importlib.util.spec_from_file_location(
        "oc_tailhedge_mod", HERE / "analyze_tailhedge.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _res():
    return json.loads((HERE / "results.json").read_text())


def _led():
    return pd.read_csv(HERE / "hedge_ledger.csv", parse_dates=["t"])


# ---- hand-checked synthetic cases ----
def test_bs_put_hand_values():
    m = _mod()
    # S=K=100, T=1, sigma=0.2, r=0: d1=0.1, d2=-0.1 ->
    # 100*(N(0.1)-N(-0.1)) = 7.9656
    assert abs(m.bs_put(100.0, 100.0, 1.0, 0.2) - 7.9656) < 0.01
    assert m.bs_put(100.0, 120.0, 1.0, 0.2) > 20.0  # time value on top of intrinsic
    assert m.bs_put(100.0, 120.0, 0.0, 0.2) == 20.0  # T=0 -> intrinsic
    assert m.bs_put(100.0, 80.0, 0.0, 0.2) == 0.0
    assert m.bs_put(100.0, 120.0, 1.0, 0.0) == 20.0  # sigma=0 -> intrinsic
    assert m.bs_put(100.0, 80.0, 1.0, 0.0) == 0.0


def test_fee_caps():
    m = _mod()
    assert abs(m.fee_buy_side(40000.0, 690.0) - 12.0) < 1e-9
    assert m.fee_buy_side(40000.0, 10.0) == 1.25  # 0.125*price binds
    assert abs(m.fee_settle_side(30000.0, 2000.0) - 4.5) < 1e-9
    assert m.fee_settle_side(30000.0, 10.0) == 1.25


def test_expiry_calendar_last_fridays():
    m = _mod()
    assert m.last_friday(2021, 9) == 24
    assert m.last_friday(2022, 5) == 27
    exps = m.monthly_expiries()
    assert exps[0] == pd.Timestamp("2021-09-24 08:00", tz="UTC")
    assert all(e.hour == 8 and e.weekday() == 4 for e in exps)


# ---- causality / truncation ----
def test_nothing_uses_data_at_or_after_cap():
    led = _led()
    assert (led["t"] < CAP).all(), led["t"].max()
    r = _res()
    assert r["meta"]["grid"][1] < "2026-09-24"
    for row in r["rows"].values():
        for y in row["years"]:
            assert y["anchor"] < "2026-09-24"


def test_roll_settle_timing_is_causal():
    # settles post at the first grid hour after 08:05 on the expiry day itself
    led = _led()
    st = led[led["type"] == "settle"]
    assert len(st) > 0
    assert ((st["t"].dt.date.astype(str) == st["expiry"]) & (st["t"].dt.hour == 9)).all()
    # TP fires only at >= 5x entry premium (per-unit), sold at mark minus fee
    tp = led[led["type"] == "tp"]
    assert len(tp) > 0 and bool((tp["mult"] >= 5.0).all())


def test_settlement_window_recomputed_from_raw_1m():
    # Expiry 2022-06-24, m=0.15 row K=24000: intr must equal max(K - mean(07:30..07:59), 0)
    m1 = pd.read_parquet(ROOT / "data/raw/btc_intraday_20260924/klines_1m_2022.parquet",
                         columns=["open_time", "close"])
    m1["open_time"] = pd.to_datetime(m1["open_time"], utc=True)
    day = m1[m1["open_time"].dt.date.astype(str) == "2022-06-24"]
    s_settle = day[(day["open_time"].dt.hour == 7)
                   & (day["open_time"].dt.minute.between(30, 59))]["close"].mean()
    assert len(day[(day["open_time"].dt.hour == 7)
                   & (day["open_time"].dt.minute.between(30, 59))]) == 30
    led = _led()
    got = led[(led["type"] == "settle") & (led["expiry"] == "2022-06-24")
              & (led["row"] == "G2K20+H(m0.15,h1.0)")]["intr"].iloc[0]
    assert abs(got - max(24000 - s_settle, 0.0)) < 0.01, (got, s_settle)


# ---- published-baseline + protocol regression ----
def test_baselines_reproduced_to_the_digit():
    r = _res()
    exp21 = json.loads((ROOT / "research/parallel/rounds/parallel-20260906-r2/v421"
                        "/v421_result.json").read_text())["rows"]["R2B1D17BFG2"]
    exp22 = json.loads((ROOT / "research/parallel/rounds/parallel-20260906-r2/v422"
                        "/v422_result.json").read_text())["rows"]["G2K20"]
    g2, k20 = r["rows"]["G2"], r["rows"]["G2K20"]
    assert [(y["R"], y["DDc"]) for y in g2["years"]] == [tuple(x) for x in exp21["years"]]
    assert [(y["R"], y["DDc"]) for y in k20["years"]] == [tuple(x) for x in exp22["years"]]
    assert (g2["R4"] if "R4" in g2 else None) is not None
    assert g2["full"]["full"] == exp21["full_path_dd"]
    assert k20["full"]["full"] == exp22["full_path_dd"]


def test_selection_protocol():
    r = _res()
    assert r["meta"]["chosen"] == "G2K20+H(m0.25,h1.0)"
    assert r["meta"]["key_answer"] is False
    assert set(r["last_year_once"]) == {r["meta"]["chosen"], "G2"}
    assert len(r["top5_g2_dd_episodes"]) == 5
    # every hedge row is worse than naked G2 on dev4 mean (negative result pins)
    g2r4 = r["rows"]["G2"]["R4"]
    for k, v in r["rows"].items():
        if "+H(" in k:
            assert v["R4"] < g2r4, k
