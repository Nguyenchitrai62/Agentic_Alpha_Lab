"""v232+v233 blind audit tests (fast, no full replay; heavy replay lives in v232_v233_audit/replicate_v232_v233.py)."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np

AUD_MOD = Path("research/parallel/rounds/parallel-20260906-r2/v232_v233_audit/replicate_v232_v233.py")
ENG = Path("research/parallel/rounds/parallel-20260906-r2/engine_user/engine_user.py")
PTV = Path("research/parallel/rounds/parallel-20260906-r2/v231/tv_indicators.py")
PRL = Path("research/parallel/rounds/parallel-20260906-r2/rl/trader_rl.py")


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_variant_configs_match_preregistration():
    aud = _load(AUD_MOD, "audit_v232_v233")
    assert aud.SYMS == ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
    assert (aud.B_ABS, aud.B_REL) == (0.03, 0.40)
    assert aud.COOL == 6 and aud.THETA == 0.05
    assert (aud.D2_BUDGET, aud.D2_RUNG) == (0.15, 1.75)
    assert (aud.EPS, aud.N_RUNS, aud.SEED0, aud.GAMMA) == (0.03, 40, 100, 0.98)
    assert aud.EMBARGO_DAYS == 7
    assert aud.VARIANTS232 == {"R1_cut": (False, 0.10), "R2_cut_pyramid": (True, 0.10), "R3_strict": (True, 0.25)}
    assert aud.CANDS233 == ("T1_A_both", "T2_AB_annual", "T3_all")
    assert aud.ANCHOR_Q == "2021-09-24"


def test_grid_g2_policy_behaviour():
    aud = _load(AUD_MOD, "audit_v232_v233_b")
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
    assert 10 < 14  # ST(10,3) ATR shorter than the ATR(14) distance unit
    c = np.array([100.0] * 21 + [110.0])
    wvf_last = 100 * (c.max() - 90.0) / c.max()
    assert abs(wvf_last - 100 * 20 / 110) < 1e-9
    for p_avg, i in ((0.001, 0.0001), (-0.002, 0.0001), (0.0, 0.0)):
        f = p_avg + float(np.clip(i - p_avg, -0.0005, 0.0005))
        assert abs(f - i) <= 0.0005 + 1e-15 or abs(f - (p_avg + 0.0005)) < 1e-15 or abs(f - (p_avg - 0.0005)) < 1e-15
    aud = _load(AUD_MOD, "audit_v232_v233_c")
    assert callable(aud.audit_supertrend) and callable(aud.audit_wvf_z) and callable(aud.audit_ms_trend)
    assert callable(aud.audit_market_features) and callable(aud.audit_grid_policy)
    tvm = _load(PTV, "tv_indicators_iso232233")
    assert len(tvm.TV) == 17
    rl = _load(PRL, "trader_rl_iso232233")
    assert tuple(rl.FLAT_ACTIONS) == ("wait", "open", "open_deep")
    assert tuple(rl.POS_ACTIONS) == ("hold", "tighten", "reduce", "close", "add")
    assert rl.encode({"close": 1}) == "close" and rl.encode("hold") == "hold"


def test_engine_trade_mode_conventions():
    eu = _load(ENG, "engine_user_iso_check232233")
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
    assert "audit_supertrend(" in own
    assert "Recorder(" in own and "QModel(" in own
    assert "robust_select" in own


def test_robust_select_first_four_only():
    v204 = _load(Path("research/parallel/rounds/parallel-20260906-r2/v204/v204_sleeve_book_alignment.py"), "audit_v204_sel232233")

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
    assert "v232_result.json" not in body
    assert "v233_result.json" not in body
    cleaned = body.replace("v232_v233_audit", "")
    for allowed in (
        "research/parallel/rounds/parallel-20260906-r2/v232/v232_disciplined_rl.py",
        "research/parallel/rounds/parallel-20260906-r2/v233/v233_tv_all_members.py",
        "research/parallel/rounds/parallel-20260906-r2/rl/trader_rl.py",
        "research/parallel/rounds/parallel-20260906-r2/v231/tv_indicators.py",
        "research/parallel/rounds/parallel-20260906-r2/v231/v231_quality_features.py",
    ):
        cleaned = cleaned.replace(allowed, "")
    assert "v232/" not in cleaned
    assert "v233/" not in cleaned
    assert "run.log" not in body and "build.log" not in body
    assert "run.err.log" not in body
    assert "robust_select" in body
    assert "monthly_dev4" in body
    assert "sleeve_risk_budget" in body
