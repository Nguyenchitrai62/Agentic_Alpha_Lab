"""W9 blind-audit tests (Part A only). No leader imports."""
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

AUDIT = Path(__file__).resolve().parents[1] / "research" / "vf_audit"
REP = AUDIT / "replication.json"
REPL_MOD = AUDIT / "replicate.py"


def _load_replicate():
    spec = importlib.util.spec_from_file_location("vf_audit_replicate", REPL_MOD)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_replication_json_exists_and_schema():
    assert REP.exists(), "run research/vf_audit/replicate.py first (Part A)"
    d = json.loads(REP.read_text())
    assert d["window"]["n_bars"] == 2190
    assert d["window"]["start"] == "2025-09-24T00:00:00+00:00"
    assert set(d["targets"]["unique_values"]) <= {-0.325, 0.0, 0.325, 0.65}
    for side in ("normal", "stress"):
        for k in ("net_pct", "fees_pct", "funding_pct", "n_exec_trades_incl_liquidation",
                  "max_dd_close_pct", "max_dd_intrabar_pct", "final_equity"):
            assert k in d[side], (side, k)
    assert len(d["target_changes"]) == d["targets"]["n_target_changes_decision_basis"]
    # decision times sorted, unique, inside window
    t = [c["decision_open_time"] for c in d["target_changes"]]
    assert t == sorted(t) and len(set(t)) == len(t)
    assert t[0] >= "2025-09-24" and t[-1] <= "2026-09-23T20:00:00+00:00"


def test_bookT_edge_triggered_blocked_edge():
    mod = _load_replicate()
    # L: F,T,T,T,F,T ; d: 0,-1,1,1,0,0 -> first edge blocked, holds 0 while L true, new edge enters
    L = pd.Series([False, True, True, True, False, True])
    d = pd.Series([0, -1, 1, 1, 0, 0])
    T = mod.compute_T(L, d).tolist()
    assert T == [0, 0, 0, 0, 0, 1], T


def test_bookT_holds_while_L_true():
    mod = _load_replicate()
    L = pd.Series([False, True, True, False, False])
    d = pd.Series([0, 1, -1, 1, 1])  # d turns -1 mid-hold must NOT exit T
    assert mod.compute_T(L, d).tolist() == [0, 1, 1, 0, 0]


def _bars(close, high=None, low=None, start="2020-01-01 00:00"):
    n = len(close)
    t = pd.date_range(start, periods=n, freq="4h", tz="UTC")
    close = np.asarray(close, float)
    high = np.asarray(high if high is not None else close + 1.0, float)
    low = np.asarray(low if low is not None else close - 1.0, float)
    return pd.DataFrame({"open_time": t, "open": close, "high": high, "low": low,
                         "close": close,
                         "close_time": t + pd.Timedelta(hours=4) - pd.Timedelta(milliseconds=1)})


def test_donchian_long_entry_exit_handchecked():
    mod = _load_replicate()
    # 55 flat bars at 100 (high 101 low 99), then breakout close 102 > max(prev high)=101
    n0 = 55
    close = [100.0] * n0 + [102.0, 98.0]
    high = [101.0] * n0 + [103.0, 99.0]
    low = [99.0] * n0 + [101.0, 97.0]
    # exit bar: close 98 <= min(prev 10 lows)=99 -> exit
    bars = _bars(close, high, low)
    d = pd.Series([0] * len(bars))
    D = mod.compute_D(bars, d).tolist()
    assert D[n0] == 1, D  # entry on breakout bar
    assert D[n0 + 1] == 0, D  # exit next bar


def test_donchian_short_needs_d_minus1_and_no_overlap():
    mod = _load_replicate()
    n0 = 55
    # recent 10 highs low (99) so short exit (close>=99) need not coincide with long entry (close>101)
    close = [100.0] * n0 + [98.0, 100.0]
    high = [101.0] * 45 + [99.0] * 10 + [99.0, 100.0]
    low = [99.0] * n0 + [97.0, 97.0]
    bars = _bars(close, high, low)
    # d=0: no short even though breakdown
    D0 = mod.compute_D(bars, pd.Series([0] * len(bars))).tolist()
    assert D0[n0] == 0, D0
    # d=-1 on breakdown bars: short enters; exit to flat when 99<=close<=101
    dd = [0] * n0 + [-1, -1]
    D1 = mod.compute_D(bars, pd.Series(dd)).tolist()
    assert D1[n0] == -1, D1
    assert D1[n0 + 1] == 0, D1


def test_target_formula_values():
    assert 0.65 * (0.5 * 1 + 0.5 * 1) == 0.65
    assert 0.65 * (0.5 * 1 + 0.5 * 0) == 0.325
    assert 0.65 * (0.5 * 0 + 0.5 * -1) == -0.325


def test_portfolio_fee_funding_drawdown_tiny():
    mod = _load_replicate()
    # decisions target[0]=0.65 traded at open[1]=100; target[1]=0 traded at open[2]=110
    w = _bars([100.0, 100.0, 110.0], [101, 101, 111], [99, 99, 99])
    w["close_time"] = w["open_time"] + pd.Timedelta(hours=4) - pd.Timedelta(milliseconds=1)
    targets = np.array([0.65, 0.0, 0.0])
    funding = pd.DataFrame({"fundingTime": pd.to_datetime([], utc=True)})
    r = mod.simulate(w, targets, funding, fee_rate=0.0002, slip_rate=0.0)
    # trade1 at open[1]=100: Q=0.65*100/100=0.65, notional 65, fee 0.013
    # hold to open[2]=110: pnl 0.65*10=6.5 ; trade2 to flat at 110: notional 0.65*110=71.5 fee 0.0143
    # final liquidation 0 (already flat) -> E ≈ 100-0.013+6.5-0.0143
    assert r["n_exec_trades"] == 2, r
    assert abs(r["final_equity"] - (100 - 0.013 + 6.5 - 0.0143)) < 1e-9, r
    assert r["total_funding"] == 0.0
    # funding case: one event inside bar1 with long
    funding2 = pd.DataFrame({"fundingTime": [w["open_time"].iloc[1] + pd.Timedelta(hours=1)]})
    r2 = mod.simulate(w, targets, funding2, fee_rate=0.0, slip_rate=0.0)
    # fund = 0.0001 * (0.65*100) = 0.0065
    assert abs(r2["total_funding"] - 0.0065) < 1e-9, r2
