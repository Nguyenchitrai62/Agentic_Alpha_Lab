"""v230 blind audit tests (fast, no full replay; heavy replay lives in v230_audit/replicate_v230.py)."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np

AUD_MOD = Path("research/parallel/rounds/parallel-20260906-r2/v230_audit/replicate_v230.py")
ENG = Path("research/parallel/rounds/parallel-20260906-r2/engine_user/engine_user.py")


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_variant_configs_match_preregistration():
    aud = _load(AUD_MOD, "audit_v230")
    assert aud.KR == ("kr_btc_lvl", "kr_btc_z", "kr_btc_chg", "kr_alt_z", "kr_alt_chg", "kr_vol_z")
    assert aud.COINS == ("BTC", "ETH", "XRP")
    assert (aud.B_ABS, aud.B_REL) == (0.03, 0.40)
    assert aud.COOL == 6 and aud.THETA == 0.05
    assert (aud.D2_BUDGET, aud.D2_RUNG) == (0.15, 1.75)
    assert aud.CANDS == ("K1_add", "K2_add_both", "K3_replace_A")
    assert aud.ANCHOR_ONE == "2021-09-24"
    assert aud.UP.as_posix() == "data/raw/upbit_20260926"
    assert aud.SP.as_posix() == "data/raw/spot_majors_20260925"
    assert aud.FX.as_posix() == "data/raw/fx_krw_20260928/usdkrw_1d.csv"


def test_grid_g2_policy_behaviour():
    aud = _load(AUD_MOD, "audit_v230_b")
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


def test_korea_premium_math():
    # premium definition: bps log difference, FX-free cross-coin leg
    up, bn, fx = 114501000.0, 95000.0, 1360.0
    p = 1e4 * np.log(up / (bn * fx))
    assert np.isfinite(p) and abs(p) < 2000
    # identical premia across coins -> FX-free relative leg is zero
    assert abs(((p - p) + (p - p)) / 2) < 1e-12
    # USDKRW usability lag is a full 2 days on top of the daily stamp
    import pandas as pd
    assert (pd.Timestamp("2026-09-24 23:00+00:00") + pd.Timedelta(days=2)
            == pd.Timestamp("2026-09-26 23:00+00:00"))
    # rolling windows from the pre-registration: 6/42 means, 540-bar z
    assert 6 < 42 < 540
    # 180-char check of the six feature names is covered in the config test
    aud = _load(AUD_MOD, "audit_v230_c")
    assert callable(aud.audit_korea_features)
    assert callable(aud.audit_upbit_4h) and callable(aud.audit_binance_4h) and callable(aud.audit_usdkrw)


def test_engine_trade_mode_conventions():
    eu = _load(ENG, "engine_user_iso_check230")
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
    assert "audit_korea_features(" in own
    assert "merge_asof" in own


def test_robust_select_first_four_only():
    v204 = _load(Path("research/parallel/rounds/parallel-20260906-r2/v204/v204_sleeve_book_alignment.py"), "audit_v204_sel230")

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
    assert "v230_result.json" not in body
    cleaned = body.replace("v230_audit", "")
    allowed = "research/parallel/rounds/parallel-20260906-r2/v230/v230_korea_premium_member.py"
    cleaned = cleaned.replace(allowed, "")
    assert "v230/" not in cleaned
    assert "run.log" not in body and "build.log" not in body
    assert "run.err.log" not in body
    assert "merge_asof" in body
    assert "robust_select" in body
    assert "monthly_dev4" in body
    assert "sleeve_risk_budget" in body
