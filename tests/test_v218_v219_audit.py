"""v218+v219 audit tests (fast, no full replay; heavy replay lives in v218_v219_audit/replicate_v218_v219.py)."""
from __future__ import annotations

import importlib.util
from pathlib import Path

AUD_MOD = Path("research/parallel/rounds/parallel-20260906-r2/v218_v219_audit/replicate_v218_v219.py")
ENG = Path("research/parallel/rounds/parallel-20260906-r2/engine_user/engine_user.py")


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_variant_configs_match_preregistration():
    aud = _load(AUD_MOD, "audit_v218_v219")
    assert aud.GRID_G2 == (1.0, 0.12, 1.5)
    assert aud.V218_VARIANTS == {
        "D1_book110": (1.10, 0.12, 1.5),
        "D2_sleeve": (1.0, 0.15, 1.75),
        "D3_mix": (1.05, 0.135, 1.6),
    }
    assert aud.V219_VARIANTS == {
        "H1_book90": (0.90, 0.18, 2.0),
        "H2_book100": (1.0, 0.18, 2.0),
        "H3_book80": (0.80, 0.21, 2.25),
    }
    assert aud.G2_BAND == (0.03, 0.40) and aud.COOL == 6


def test_grid_policy_g2_band_behaviour():
    aud = _load(AUD_MOD, "audit_v218_v219_b")
    g = aud.audit_grid_policy(0.03, 0.40, cool=6)
    assert g(0, 0, dict(pos=0, tg=0.2, sgn=1, w=0.0, valid=("wait", "open", "open_deep"), since_adj=99)) == "open"
    st = dict(pos=1, tg=-0.2, sgn=-1, w=0.1, valid=("hold", "tighten", "reduce", "close"), since_adj=99)
    assert g(0, 0, st) == {"tighten": 1, "close": 1}
    st = dict(pos=1, tg=0.01, sgn=0, w=0.1, valid=("hold", "tighten", "reduce", "close"), since_adj=99)
    assert g(0, 0, st) == "close"
    st = dict(pos=1, tg=0.3, sgn=1, w=0.1, valid=("hold", "tighten", "reduce", "close", "add"), since_adj=3)
    assert g(0, 0, st) == "hold"
    st = dict(pos=1, tg=0.3, sgn=1, w=0.1, valid=("hold", "tighten", "reduce", "close", "add"), since_adj=6)
    got = g(0, 0, st)
    assert set(got) == {"add"} and abs(got["add"] - 0.2) < 1e-9


def test_book_mult_threshold_unscaled_and_sleeve_isolation_in_engine():
    eu = _load(ENG, "engine_user_iso_check")
    import inspect
    src = inspect.getsource(eu.simulate)
    i_th = src.index('th = P.get("theta"')
    i_sgn = src.index("sgn = int(np.sign(tg))")
    i_mult = src.index("book_mult")
    assert i_th < i_sgn < i_mult
    assert 'tg = tg * P.get("book_mult", 1.0)' in src
    assert sum(1 for ln in src.splitlines() if "book_mult" in ln) == 1
    assert "risk_open + rn * (_msl(a) * sg + gap) > sleeve_risk_budget" in src
    assert "* size_mult *" in src


def test_robust_select_prefers_best_worst_year():
    v204 = _load(Path("research/parallel/rounds/parallel-20260906-r2/v204/v204_sleeve_book_alignment.py"), "audit_v204_sel")

    def row(dev4, nets, dd=10.0):
        return {"monthly_dev4": dev4, "gate_dd": dd,
                "yearly": [{"net_pct": n} for n in nets] + [{"net_pct": 50.0}]}

    rows = {
        "a": row(4.0, [10.0, 20.0, 30.0, 40.0]),
        "b": row(4.5, [25.0, 20.0, 30.0, 40.0]),
        "c": row(4.2, [5.0, 20.0, 30.0, 40.0]),
    }
    assert v204.robust_select(rows) == "b"
    bad = dict(rows, b=row(4.5, [-1.0, 20.0, 30.0, 40.0]))
    assert v204.robust_select(bad) == "a"
