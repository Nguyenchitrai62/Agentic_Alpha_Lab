"""v221 audit tests (fast, no full replay; heavy replay lives in v221_audit/replicate_v221.py)."""
from __future__ import annotations

import importlib.util
from pathlib import Path

AUD_MOD = Path("research/parallel/rounds/parallel-20260906-r2/v221_audit/replicate_v221.py")
ENG = Path("research/parallel/rounds/parallel-20260906-r2/engine_user/engine_user.py")


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_variant_configs_match_preregistration():
    aud = _load(AUD_MOD, "audit_v221")
    assert aud.VARIANTS == {
        "Y1_hyst25": (0.025, False),
        "Y2_hyst10": (0.010, False),
        "Y3_hyst25_ema": (0.025, True),
    }
    assert aud.THETA == 0.05 and aud.COOL == 6
    assert (aud.B_ABS, aud.B_REL) == (0.03, 0.40) and aud.EMA_ALPHA == 0.5
    assert (aud.D2_BUDGET, aud.D2_RUNG) == (0.15, 1.75)


def test_hyst_policy_reversal_close_cooldown_grid():
    aud = _load(AUD_MOD, "audit_v221_b")
    h = aud.audit_hyst_policy(0.025, False)
    assert h(0, 0, dict(pos=0, tg=0.2, sgn=1, w=0.0, valid=("wait", "open"), since_adj=99)) == "open"
    st = dict(pos=1, tg=-0.2, sgn=-1, w=0.1, valid=("hold", "tighten", "reduce", "close"), since_adj=99)
    assert h(0, 0, st) == {"tighten": 1, "close": 1}
    st = dict(pos=1, tg=-0.2, sgn=-1, w=0.1, valid=("hold", "tighten"), since_adj=99)
    assert h(0, 0, st) == "tighten"
    st = dict(pos=1, tg=0.01, sgn=0, w=0.1, valid=("hold", "tighten", "reduce", "close"), since_adj=99)
    assert h(0, 0, st) == "close"
    st = dict(pos=1, tg=0.01, sgn=0, w=0.1, valid=("hold",), since_adj=99)
    assert h(0, 0, st) == "hold"
    st = dict(pos=1, tg=0.3, sgn=1, w=0.1, valid=("hold", "tighten", "reduce", "close", "add"), since_adj=3)
    assert h(0, 0, st) == "hold"
    st = dict(pos=1, tg=0.3, sgn=1, w=0.1, valid=("hold", "tighten", "reduce", "close", "add"), since_adj=6)
    got = h(0, 0, st)
    assert set(got) == {"add"} and abs(got["add"] - 0.2) < 1e-9
    st = dict(pos=1, tg=0.1, sgn=1, w=0.4, valid=("hold", "tighten", "reduce", "close"), since_adj=6)
    got = h(0, 1, st)
    assert set(got) == {"reduce"} and abs(got["reduce"] - 0.75) < 1e-9


def test_hyst_ema_smooths_single_weak_bar_and_resets_flat():
    aud = _load(AUD_MOD, "audit_v221_c")
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


def test_grid_reference_policy_g2_behaviour():
    aud = _load(AUD_MOD, "audit_v221_d")
    g = aud.audit_grid_policy(0.03, 0.40, cool=6)
    assert g(0, 0, dict(pos=0, tg=0.2, sgn=1, w=0.0, valid=("wait", "open"), since_adj=99)) == "open"
    st = dict(pos=1, tg=-0.2, sgn=-1, w=0.1, valid=("hold", "tighten", "reduce", "close"), since_adj=99)
    assert g(0, 0, st) == {"tighten": 1, "close": 1}
    st = dict(pos=1, tg=0.01, sgn=0, w=0.1, valid=("hold", "tighten", "reduce", "close"), since_adj=99)
    assert g(0, 0, st) == "close"


def test_engine_threshold_fill_and_sleeve_isolation():
    eu = _load(ENG, "engine_user_iso_check221")
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
    assert "* size_mult *" in src


def test_robust_select_y3_when_only_dd_passing_row():
    v204 = _load(Path("research/parallel/rounds/parallel-20260906-r2/v204/v204_sleeve_book_alignment.py"), "audit_v204_sel221")

    def row(dev4, nets, dd):
        return {"monthly_dev4": dev4, "gate_dd": dd,
                "yearly": [{"net_pct": n} for n in nets] + [{"net_pct": 50.0}]}

    rows = {
        "Y1_hyst25": row(5.096, [35.0, 23.0, 154.0, 155.0], 20.13),
        "Y2_hyst10": row(5.170, [31.0, 27.0, 154.0, 162.0], 21.13),
        "Y3_hyst25_ema": row(5.075, [35.0, 21.0, 157.0, 153.0], 19.65),
    }
    assert v204.robust_select(rows) == "Y3_hyst25_ema"
