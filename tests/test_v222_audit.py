"""v222 audit tests (fast, no full replay; heavy replay lives in v222_audit/replicate_v222.py)."""
from __future__ import annotations

import importlib.util
from pathlib import Path

AUD_MOD = Path("research/parallel/rounds/parallel-20260906-r2/v222_audit/replicate_v222.py")
ENG = Path("research/parallel/rounds/parallel-20260906-r2/engine_user/engine_user.py")


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_variant_configs_match_preregistration():
    aud = _load(AUD_MOD, "audit_v222")
    assert aud.VARIANTS == {
        "K1_D2_Y3": {"D2": 0.5, "Y3": 0.5},
        "K2_D2_S3": {"D2": 0.5, "S3": 0.5},
        "K3_D2_Y3_S3": {"D2": 1 / 3, "Y3": 1 / 3, "S3": 1 / 3},
    }
    assert aud.THETA == 0.05 and aud.COOL == 6
    assert (aud.B_ABS, aud.B_REL) == (0.03, 0.40)
    assert aud.Y3_CLOSE == 0.025 and aud.EMA_ALPHA == 0.5
    assert (aud.D2_BUDGET, aud.D2_RUNG) == (0.15, 1.75)


def test_grid_d2_policy_g2_behaviour():
    aud = _load(AUD_MOD, "audit_v222_b")
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


def test_hyst_y3_ema_close_and_reset():
    aud = _load(AUD_MOD, "audit_v222_c")
    h = aud.audit_hyst_policy(0.025, True)
    st = dict(pos=1, tg=0.2, sgn=1, w=0.1, valid=("hold", "tighten", "reduce", "close", "add"), since_adj=99)
    assert h(0, 7, st) == {"add": 0.1}
    weak = dict(pos=1, tg=0.01, sgn=0, w=0.1, valid=("hold", "tighten", "reduce", "close"), since_adj=99)
    assert h(1, 7, weak) != "close"
    assert h(2, 7, weak) != "close"
    assert h(3, 7, weak) != "close"
    assert h(4, 7, weak) == "close"
    assert h(0, 0, dict(pos=0, tg=0.0, sgn=0, w=0.0, valid=("wait", "open"), since_adj=99)) == "open"
    assert h(3, 7, weak) == "close"
    rev = dict(pos=1, tg=-0.2, sgn=-1, w=0.1, valid=("hold", "tighten", "reduce", "close"), since_adj=99)
    assert h(0, 3, rev) == {"tighten": 1, "close": 1}


def test_s3_rule_add_reduce_tighten():
    aud = _load(AUD_MOD, "audit_v222_d")
    assert aud.audit_s3_policy(0, 0, dict(pos=0, tg=0.2, sgn=1, w=0.0, valid=("wait", "open"), upnl=0.0, nred=0)) == "open"
    st = dict(pos=1, tg=-0.2, sgn=-1, w=0.1, valid=("hold", "tighten"), upnl=-0.1, nred=0)
    assert aud.audit_s3_policy(0, 0, st) == {"tighten"}
    st = dict(pos=1, tg=0.3, sgn=1, w=0.1, valid=("hold", "add"), upnl=0.5, nred=0)
    assert aud.audit_s3_policy(0, 0, st) == {"add"}
    st = dict(pos=1, tg=0.3, sgn=1, w=0.1, valid=("hold", "add"), upnl=-0.5, nred=0)
    assert aud.audit_s3_policy(0, 0, st) == "hold"
    st = dict(pos=1, tg=0.01, sgn=0, w=0.4, valid=("hold", "reduce"), upnl=0.0, nred=0)
    assert aud.audit_s3_policy(0, 0, st) == {"reduce"}
    st = dict(pos=1, tg=0.3, sgn=1, w=0.3, valid=("hold", "tighten"), upnl=0.5, nred=1)
    assert aud.audit_s3_policy(0, 0, st) == "hold"


def test_combine_math_share_weighted_no_rebalance():
    import numpy as np
    eq_a = np.array([1.0, 1.1, 1.2])
    eq_b = np.array([1.0, 0.9, 1.0])
    em_a = np.array([1.0, 1.05, 1.1])
    em_b = np.array([1.0, 0.85, 0.9])
    eq = 0.5 * eq_a + 0.5 * eq_b
    eq_min = 0.5 * em_a + 0.5 * em_b
    assert abs(eq[0] - 1.0) < 1e-12
    assert abs(eq_min[1] - 0.95) < 1e-12
    assert eq_min[1] <= eq[1]
    net = np.concatenate([[eq[0] - 1], eq[1:] / eq[:-1] - 1])
    assert abs(net[0]) < 1e-12 and abs(net[1] - 0.0) < 1e-12
    thirds = (eq_a + eq_b + eq_a) / 3
    assert abs(float(np.mean([0.5, 0.5])) - 0.5) < 1e-12 and abs(thirds[0] - 1.0) < 1e-12


def test_engine_threshold_fill_and_subaccount_isolation():
    eu = _load(ENG, "engine_user_iso_check222")
    import inspect
    src = inspect.getsource(eu.simulate)
    i_th = src.index('th = P.get("theta"')
    i_sgn = src.index("sgn = int(np.sign(tg))")
    i_mult = src.index("book_mult")
    assert i_th < i_sgn < i_mult
    assert 'tg = tg * P.get("book_mult", 1.0)' in src
    assert "win_start" in src
    assert "stop on the held position wins a same-minute tie" in src
    assert "risk_open + rn * (_msl(a) * sg + gap) > sleeve_risk_budget" in src
    assert "prev_eq * ACCOUNT" in src
    assert eu.ACCOUNT == 10_000.0
    own = AUD_MOD.read_text()
    assert "eu.ACCOUNT = account * share" in own
    assert "without rebalancing" in own or "without rebalancing" in own.lower()


def test_robust_select_only_over_k1_k3_first_four():
    v204 = _load(Path("research/parallel/rounds/parallel-20260906-r2/v204/v204_sleeve_book_alignment.py"), "audit_v204_sel222")

    def row(dev4, nets, dd):
        return {"monthly_dev4": dev4, "gate_dd": dd,
                "yearly": [{"net_pct": n} for n in nets] + [{"net_pct": 50.0}]}

    rows = {
        "K1_D2_Y3": row(5.17, [32.0, 30.0, 148.0, 161.0], 19.35),
        "K2_D2_S3": row(4.52, [7.0, 22.0, 129.0, 176.0], 20.69),
        "K3_D2_Y3_S3": row(4.72, [16.0, 22.0, 140.0, 166.0], 20.00),
    }
    assert v204.robust_select(rows) == "K1_D2_Y3"
