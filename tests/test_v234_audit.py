"""v234 blind audit tests (fast, no full replay; heavy replay lives in v234_audit/replicate_v234.py)."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd

AUD_MOD = Path("research/parallel/rounds/parallel-20260906-r2/v234_audit/replicate_v234.py")
ENG = Path("research/parallel/rounds/parallel-20260906-r2/engine_user/engine_user.py")
PTV = Path("research/parallel/rounds/parallel-20260906-r2/v231/tv_indicators.py")
PQ234 = Path("research/parallel/rounds/parallel-20260906-r2/v234/v234_htf_indicators.py")


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_variant_configs_match_preregistration():
    aud = _load(AUD_MOD, "audit_v234")
    assert aud.SYMS == ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
    assert aud.AUDIT_SYMS == ("BTCUSDT", "XRPUSDT")
    assert (aud.B_ABS, aud.B_REL) == (0.03, 0.40)
    assert aud.COOL == 6 and aud.THETA == 0.05
    assert (aud.D2_BUDGET, aud.D2_RUNG) == (0.15, 1.75)
    assert aud.CANDS == ("H1_daily", "H2_daily_weekly")
    assert aud.TFS_H1 == ("1d",) and aud.TFS_H2 == ("1d", "1w")
    assert aud.ANCHOR_Q == "2021-09-24"
    assert aud.N_SAMPLE >= 10 and aud.SEED == 7


def test_htf_availability_math_spot():
    htf = _load(PQ234, "v234_htf_iso")
    tvm = _load(PTV, "tv_indicators_iso234")
    assert len(tvm.TV) == 17
    assert tuple(htf.SYMS) == ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
    src = PQ234.read_text()
    assert "merge_asof" in src and "backward" in src
    assert "W-MON" in src and 'w["n"] == 7' in src
    assert "avail" in src and "close_at" in src
    assert "pd.Timedelta(days=1 if tf" in src
    # weekly helper: complete weeks only, Monday-start + 7 days availability
    idx = pd.date_range("2024-01-01", periods=14, freq="D", tz="UTC")  # two Mondays: 2024-01-01, 2024-01-08
    d = pd.DataFrame({"open_time": idx, "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5, "volume": 10.0})
    w = htf.weekly(d)
    assert len(w) == 2  # two complete Monday weeks
    assert (w["open_time"] == pd.to_datetime(["2024-01-01", "2024-01-08"], utc=True)).all()
    # incomplete week is dropped
    d_short = d.iloc[:10].copy()
    w_short = htf.weekly(d_short)
    assert len(w_short) == 1
    assert w_short["open_time"].iloc[0] == pd.Timestamp("2024-01-01", tz="UTC")
    # daily availability: open + 1 day; weekly: week start + 7 days
    assert d["open_time"].iloc[0] + pd.Timedelta(days=1) == pd.Timestamp("2024-01-02", tz="UTC")
    assert w["open_time"].iloc[0] + pd.Timedelta(days=7) == pd.Timestamp("2024-01-08", tz="UTC")


def test_grid_g2_policy_behaviour():
    aud = _load(AUD_MOD, "audit_v234_b")
    assert callable(aud.rebuild_member_single_anchor_htf)
    v216 = _load(Path("research/parallel/rounds/parallel-20260906-r2/v216/v216_trade_grid.py"), "v216_iso234")
    g = v216.grid_policy(0.03, 0.40)
    assert g(0, 0, dict(pos=0, tg=0.2, sgn=1, w=0.0, valid=("wait", "open"), since_adj=99)) == "open"
    st = dict(pos=1, tg=-0.2, sgn=-1, w=0.1, valid=("hold", "tighten", "reduce", "close"), since_adj=99)
    assert g(0, 0, st) == {"tighten": 1, "close": 1}
    st = dict(pos=1, tg=0.01, sgn=0, w=0.1, valid=("hold", "tighten", "reduce", "close"), since_adj=99)
    assert g(0, 0, st) == "close"


def test_engine_trade_mode_conventions():
    eu = _load(ENG, "engine_user_iso_check234")
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
    assert "htf_frame(" in own
    assert "robust_select" in own
    assert "monthly_dev4" in own
    assert "sleeve_risk_budget" in own


def test_robust_select_first_four_only():
    v204 = _load(Path("research/parallel/rounds/parallel-20260906-r2/v204/v204_sleeve_book_alignment.py"), "audit_v204_sel234")

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
    assert "v234_result.json" not in body
    cleaned = body.replace("research/parallel/rounds/parallel-20260906-r2/v234/v234_htf_indicators.py", "")
    cleaned = cleaned.replace("research/parallel/rounds/parallel-20260906-r2/v234_audit", "")
    cleaned = cleaned.replace("v234_audit", "")
    cleaned = cleaned.replace("v234_htf", "")
    cleaned = cleaned.replace("replicate_v234", "")
    assert "v234/" not in cleaned
    assert "run.log" not in body and "build.log" not in body
    assert "run.err.log" not in body
    assert "robust_select" in body
    assert "monthly_dev4" in body
    assert "sleeve_risk_budget" in body
