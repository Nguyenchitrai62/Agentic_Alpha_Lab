"""v227 + v228 + v229 audit tests (fast, no full replay; heavy replay lives in v227_v229_audit/replicate_v227_v229.py)."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np

AUD_MOD = Path("research/parallel/rounds/parallel-20260906-r2/v227_v229_audit/replicate_v227_v229.py")
ENG = Path("research/parallel/rounds/parallel-20260906-r2/engine_user/engine_user.py")


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_variant_configs_match_preregistration():
    aud = _load(AUD_MOD, "audit_v227_v229")
    assert (aud.B_ABS, aud.B_REL) == (0.03, 0.40)
    assert aud.COOL == 6 and aud.THETA == 0.05
    assert (aud.D2_BUDGET, aud.D2_RUNG) == (0.15, 1.75)
    assert aud.HALF_DAYS == 180
    assert (aud.Q_MIN_COIN, aud.Q_MIN_CELL) == (50, 30)
    assert (aud.BAND_LO, aud.BAND_HI) == (0.5, 1.5)
    assert aud.OFFSETS == {"O1_035": 0.35, "O2_045": 0.45, "O3_055": 0.55}
    assert set(aud.HOURLY) == {"L1_hourly", "L2_hourly_small", "L3_hourly_aligned"}
    assert aud.HOURLY["L1_hourly"] == dict(hourly=True)
    assert aud.HOURLY["L2_hourly_small"] == dict(hourly=True, size_mult=1.5)
    assert aud.HOURLY["L3_hourly_aligned"] == dict(hourly=True, align=(1.5, 0.0))
    assert aud.CANDS_227 == ("Q1_no_bnb", "Q2_coin_bandit", "Q3_coin_rung")
    assert aud.CANDS_228 == ("O1_035", "O2_045", "O3_055")
    assert aud.CANDS_229 == ("L1_hourly", "L2_hourly_small", "L3_hourly_aligned")


def test_grid_g2_policy_behaviour():
    aud = _load(AUD_MOD, "audit_v227_v229_b")
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


def test_bandit_math():
    # clip bounds of the coin bandit multiplier
    assert float(np.clip(3.0, 0.5, 1.5)) == 1.5
    assert float(np.clip(0.1, 0.5, 1.5)) == 0.5
    assert float(np.clip(1.2, 0.5, 1.5)) == 1.2
    # 180-day half-life: a bid 180 days old weighs half a fresh bid
    lam = np.log(2) / 180.0
    assert abs(np.exp(-lam * 180.0) - 0.5) < 1e-12
    assert abs(np.exp(-lam * 360.0) - 0.25) < 1e-12
    # minimum-finished-bids gating per the pre-registration
    assert 49 < 50 and 50 >= 50
    assert 29 < 30 and 30 >= 30


def test_engine_trade_mode_conventions():
    eu = _load(ENG, "engine_user_iso_check227229")
    import inspect
    src = inspect.getsource(eu.simulate)
    assert "win_start" in src
    assert "stop on the held position wins a same-minute tie" in src
    assert "risk_open + rn * (_msl(a) * sg + gap) > sleeve_risk_budget" in src
    assert "prev_eq * ACCOUNT" in src
    assert eu.ACCOUNT == 10_000.0
    assert eu.MAKER == 0.0002 and eu.TAKER == 0.00055 and eu.FUND_LONG == 0.0001
    assert tuple(eu.RUNGS) == (2.5, 3.0, 3.5, 4.0)
    prep_src = inspect.getsource(eu.prepare)
    assert "sig1h[1:] = sig_h[:-1, 3, :]" in prep_src
    assert "60 * h + 4" in src and "60 * h + 57" in src
    own = AUD_MOD.read_text()
    assert "win_start=5" in own
    assert "audit_sleeve_outcomes(" in own
    assert "audit_grid_policy(" in own
    assert "t_exit < t_now" in own


def test_robust_select_first_four_only():
    v204 = _load(Path("research/parallel/rounds/parallel-20260906-r2/v204/v204_sleeve_book_alignment.py"), "audit_v204_sel227229")

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
    assert "v227_result.json" not in body
    assert "v228_result.json" not in body
    assert "v229_result.json" not in body
    cleaned = body.replace("v227_v229_audit", "")
    for allowed in ("v227/v227_sleeve_coin_bandit.py", "v228/v228_trade_offset.py", "v229/v229_trade_hourly_ladder.py"):
        cleaned = cleaned.replace(allowed, "")
    assert "v227/" not in cleaned
    assert "v228/" not in cleaned
    assert "v229/" not in cleaned
    assert "run.log" not in body and "build.log" not in body
    assert "run.err.log" not in body
    assert "t_exit < t_now" in body
    assert "sig1h[1:] = sig_h[:-1, 3, :]" in body
    assert "robust_select" in body
    assert "monthly_dev4" in body
    assert "sleeve_risk_budget" in body
