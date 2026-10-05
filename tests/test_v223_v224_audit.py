"""v223 + v224 audit tests (fast, no full replay; heavy replay lives in v223_v224_audit/replicate_v223_v224.py)."""
from __future__ import annotations

import importlib.util
from pathlib import Path

AUD_MOD = Path("research/parallel/rounds/parallel-20260906-r2/v223_v224_audit/replicate_v223_v224.py")
ENG = Path("research/parallel/rounds/parallel-20260906-r2/engine_user/engine_user.py")


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_variant_configs_match_preregistration():
    aud = _load(AUD_MOD, "audit_v223_v224")
    assert aud.MIXES_223 == {
        "ref_mix": (0.25, 0.25, 0.50),
        "W1_slower": (0.35, 0.35, 0.30),
        "W2_slow": (0.40, 0.40, 0.20),
        "W3_noflow": (0.50, 0.50, 0.00),
    }
    assert aud.MIXES_224 == {
        "ref_mix": (0.25, 0.25, 0.50),
        "F1_faster": (0.20, 0.20, 0.60),
        "F2_fast": (0.125, 0.125, 0.75),
        "F3_no_lo": (0.00, 0.30, 0.70),
    }
    assert aud.CANDS_223 == ("W1_slower", "W2_slow", "W3_noflow")
    assert aud.CANDS_224 == ("F1_faster", "F2_fast", "F3_no_lo")
    assert aud.THETA == 0.05 and aud.COOL == 6
    assert (aud.B_ABS, aud.B_REL) == (0.03, 0.40)
    assert (aud.D2_BUDGET, aud.D2_RUNG) == (0.15, 1.75)


def test_grid_g2_policy_behaviour():
    aud = _load(AUD_MOD, "audit_v223_v224_b")
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


def test_member_weighting_math():
    # member book = w_lo lo/0.25 + w_ls ls/0.25 + w_fl fl/0.5; ref must equal the plain sum
    lo, ls, fl = 0.10, -0.04, 0.06
    ref = 0.25 * lo / 0.25 + 0.25 * ls / 0.25 + 0.50 * fl / 0.5
    assert abs(ref - (lo + ls + fl)) < 1e-12
    w1 = 0.35 * lo / 0.25 + 0.35 * ls / 0.25 + 0.30 * fl / 0.5
    assert abs(w1 - (1.4 * lo + 1.4 * ls + 0.6 * fl)) < 1e-12
    f3 = 0.00 * lo / 0.25 + 0.30 * ls / 0.25 + 0.70 * fl / 0.5
    assert abs(f3 - (1.2 * ls + 1.4 * fl)) < 1e-12
    # ensemble weights sum to one
    assert abs(0.5 * 0.5 + 0.5 * 0.5 + 0.5 * 0.5 + 0.5 * 0.5 - 1.0) < 1e-12


def test_engine_trade_mode_conventions():
    eu = _load(ENG, "engine_user_iso_check223224")
    import inspect
    src = inspect.getsource(eu.simulate)
    assert "win_start" in src
    assert "stop on the held position wins a same-minute tie" in src
    assert "risk_open + rn * (_msl(a) * sg + gap) > sleeve_risk_budget" in src
    assert "prev_eq * ACCOUNT" in src
    assert eu.ACCOUNT == 10_000.0
    assert eu.MAKER == 0.0002 and eu.TAKER == 0.00055 and eu.FUND_LONG == 0.0001
    own = AUD_MOD.read_text()
    assert "win_start=5" in own
    assert "audit_member(" in own
    assert "audit_grid_policy(" in own


def test_robust_select_first_four_only():
    v204 = _load(Path("research/parallel/rounds/parallel-20260906-r2/v204/v204_sleeve_book_alignment.py"), "audit_v204_sel223224")

    def row(dev4, nets, dd):
        return {"monthly_dev4": dev4, "gate_dd": dd,
                "yearly": [{"net_pct": n} for n in nets] + [{"net_pct": 50.0}]}

    # DD breach and losing year are excluded; among the rest the best
    # worst-year monthly (ties -> higher mean) wins, last year never ranked
    rows = {
        "good": row(5.0, [30.0, 30.0, 140.0, 150.0], 19.0),
        "dd_breach": row(9.0, [100.0, 100.0, 200.0, 200.0], 20.69),
        "loser": row(9.0, [-5.0, 100.0, 200.0, 200.0], 19.0),
    }
    assert v204.robust_select(rows) == "good"
    # worst-year decides, not the mean: lower mean but higher worst year wins
    rows2 = {
        "high_mean_low_worst": row(6.0, [7.0, 60.0, 150.0, 170.0], 19.0),
        "low_mean_high_worst": row(5.2, [30.0, 35.0, 140.0, 150.0], 19.0),
    }
    assert v204.robust_select(rows2) == "low_mean_high_worst"


def test_blind_script_does_not_open_results():
    src = AUD_MOD.read_text()
    body = src.split('"""', 2)[2] if src.startswith('"""') else src
    assert "v223_result.json" not in body
    assert "v224_result.json" not in body
    cleaned = body.replace("v223_v224_audit", "")
    for allowed in ("v223/build_components.py", "v223/v223_component_mix.py",
                    "v224/v224_component_fast.py"):
        cleaned = cleaned.replace(allowed, "")
    assert "v223/" not in cleaned
    assert "v224/" not in cleaned
    assert "run.log" not in body and "build.log" not in body
    assert "mix[0] * lo / 0.25" in body
    assert "0.5 * (A + B) / 2 + 0.5 * (Aq + Bq) / 2" in body
    assert "robust_select" in body
    assert "monthly_dev4" in body
    assert "sleeve_risk_budget" in body
