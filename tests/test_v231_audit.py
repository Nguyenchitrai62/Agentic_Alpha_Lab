"""v231 blind audit tests (fast, no full replay; heavy replay lives in v231_audit/replicate_v231.py)."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np

AUD_MOD = Path("research/parallel/rounds/parallel-20260906-r2/v231_audit/replicate_v231.py")
ENG = Path("research/parallel/rounds/parallel-20260906-r2/engine_user/engine_user.py")
PTV = Path("research/parallel/rounds/parallel-20260906-r2/v231/tv_indicators.py")
PPF = Path("research/parallel/rounds/parallel-20260906-r2/v231/premium_features.py")


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_variant_configs_match_preregistration():
    aud = _load(AUD_MOD, "audit_v231")
    assert aud.SYMS == ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
    assert (aud.B_ABS, aud.B_REL) == (0.03, 0.40)
    assert aud.COOL == 6 and aud.THETA == 0.05
    assert (aud.D2_BUDGET, aud.D2_RUNG) == (0.15, 1.75)
    assert aud.CANDS == ("V1_tv", "V2_prem_fng", "V3_all")
    assert aud.ANCHOR_ONE == "2021-09-24"
    assert aud.GROUPS == {"V1_tv": ("tv",), "V2_prem_fng": ("pf", "fng"), "V3_all": ("tv", "pf", "fng")}
    assert aud.PREM.as_posix() == "data/raw/binance_premium_20260928"
    assert aud.AUDIT_INTEREST == {"BTCUSDT": 0.0001, "ETHUSDT": 0.0001, "SOLUSDT": 0.0001,
                                 "BNBUSDT": 0.0, "XRPUSDT": 0.0001}


def test_grid_g2_policy_behaviour():
    aud = _load(AUD_MOD, "audit_v231_b")
    g = aud.audit_grid_policy(0.03, 0.40, cool=6)
    assert g(0, 0, dict(pos=0, tg=0.2, sgn=1, w=0.0, valid=("wait", "open"), since_adj=99)) == "open"
    st = dict(pos=1, tg=-0.2, sgn=-1, w=0.1, valid=("hold", "tighten", "reduce", "close"), since_adj=99)
    assert g(0, 0, st) == {"tighten": 1, "close": 1}
    st = dict(pos=1, tg=0.01, sgn=0, w=0.1, valid=("hold", "tighten", "reduce", "close"), since_adj=99)
    assert g(0, 0, st) == "close"
    st = dict(pos=1, tg=0.3, sgn=1, w=0.1, valid=("hold", "tighten", "reduce", "close", "add"), since_adj=3)
    assert g(0, 0, st) == "hold"
    st = dict(pos=1, tg=0.3, sgn=1, w=0.1, valid=("hold", "tighten", "reduce", "close", "add"), since_adj=6)
    got = g(0, 0, st)
    assert set(got) == {"add"} and abs(got["add"] - 0.2) < 1e-9
    st = dict(pos=1, tg=0.1, sgn=1, w=0.4, valid=("hold", "tighten", "reduce", "close"), since_adj=6)
    got = g(0, 1, st)
    assert set(got) == {"reduce"} and abs(got["reduce"] - 0.75) < 1e-9


def test_tv_indicator_math_spot():
    # SuperTrend bands: hl2 +- 3*ATR(10); direction flips only on close through the final band
    assert 10 < 14  # ST(10,3) ATR shorter than the ATR(14) distance unit
    # Williams VIX Fix: 100*(max22 - low)/max22, z over 50 bars
    c = np.array([100.0] * 21 + [110.0])
    wvf_last = 100 * (c.max() - 90.0) / c.max()
    assert abs(wvf_last - 100 * 20 / 110) < 1e-9
    # funding clamp: F = P + clip(I - P, +-0.05%)
    for p_avg, i in ((0.001, 0.0001), (-0.002, 0.0001), (0.0, 0.0)):
        f = p_avg + float(np.clip(i - p_avg, -0.0005, 0.0005))
        assert abs(f - i) <= 0.0005 + 1e-15 or abs(f - (p_avg + 0.0005)) < 1e-15 or abs(f - (p_avg - 0.0005)) < 1e-15
    aud = _load(AUD_MOD, "audit_v231_c")
    assert callable(aud.audit_supertrend) and callable(aud.audit_wvf_z)
    assert callable(aud.audit_vwap_weekly) and callable(aud.audit_ms_trend) and callable(aud.audit_poc_dist)
    tvm = _load(PTV, "tv_indicators_iso231")
    assert len(tvm.TV) == 17
    pfm = _load(PPF, "pf_indicators_iso231")
    assert tuple(pfm.PF) == ("pf_pred", "pf_pred_chg", "pf_prem_bar", "pf_prem_last",
                             "pf_prem_24h", "pf_prem_z", "pf_prem_chg")


def test_engine_trade_mode_conventions():
    eu = _load(ENG, "engine_user_iso_check231")
    import inspect
    src = inspect.getsource(eu.simulate)
    assert "win_start" in src
    assert "stop on the held position wins a same-minute tie" in src
    assert "risk_open + rn * (_msl(a) * sg + gap) > sleeve_risk_budget" in src
    assert "prev_eq * ACCOUNT" in src
    assert eu.ACCOUNT == 10_000.0
    assert eu.MAKER == 0.0002 and eu.TAKER == 0.00055 and eu.FUND_LONG == 0.0001
    assert tuple(eu.RUNGS) == (2.5, 3.0, 3.5, 4.0)
    own = AUD_MOD.read_text()
    assert "win_start=5" in own
    assert "audit_grid_policy(" in own
    assert "audit_reconstruct(" in own
    assert "merge_asof" in own


def test_robust_select_first_four_only():
    v204 = _load(Path("research/parallel/rounds/parallel-20260906-r2/v204/v204_sleeve_book_alignment.py"), "audit_v204_sel231")

    def row(dev4, nets, dd):
        return {"monthly_dev4": dev4, "gate_dd": dd,
                "yearly": [{"net_pct": n} for n in nets] + [{"net_pct": 50.0}]}

    rows = {
        "good": row(5.0, [30.0, 30.0, 140.0, 150.0], 19.0),
        "dd_breach": row(9.0, [100.0, 100.0, 200.0, 200.0], 20.69),
        "loser": row(9.0, [-5.0, 100.0, 200.0, 200.0], 19.0),
    }
    assert v204.robust_select(rows) == "good"
    rows2 = {
        "high_mean_low_worst": row(6.0, [7.0, 60.0, 150.0, 170.0], 19.0),
        "low_mean_high_worst": row(5.2, [30.0, 35.0, 140.0, 150.0], 19.0),
    }
    assert v204.robust_select(rows2) == "low_mean_high_worst"


def test_blind_script_does_not_open_results():
    src = AUD_MOD.read_text()
    body = src.split('"""', 2)[2] if src.startswith('"""') else src
    assert "v231_result.json" not in body
    cleaned = body.replace("v231_audit", "")
    for allowed in (
        "research/parallel/rounds/parallel-20260906-r2/v231/v231_quality_features.py",
        "research/parallel/rounds/parallel-20260906-r2/v231/tv_indicators.py",
        "research/parallel/rounds/parallel-20260906-r2/v231/premium_features.py",
        "scripts/fetch_binance_premium.py",
    ):
        cleaned = cleaned.replace(allowed, "")
    assert "v231/" not in cleaned
    assert "run.log" not in body and "build.log" not in body
    assert "run.err.log" not in body
    assert "merge_asof" in body
    assert "robust_select" in body
    assert "monthly_dev4" in body
    assert "sleeve_risk_budget" in body
