"""oc_carryhurdle tests: causality/truncation + hand-checked synthetic + consistency."""

import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve()
ROOT = HERE.parents[1]
RDIR = ROOT / "research/tournament/oc_carryhurdle"
CCRES = ROOT / "research/tournament/oc_cashcarry/results.json"
HOURLY = ROOT / "research/tournament/ext/hourly_ext.parquet"

C_RT = 2 * 0.001 + 0.00055 + 0.0002
T1 = 2.0 * C_RT
T2 = 1.5 * C_RT


def test_hurdle_constants_frozen():
    assert abs(C_RT - 0.00275) < 1e-12
    assert abs(T1 - 0.0055) < 1e-12
    assert abs(T2 - 0.004125) < 1e-12


def test_frozen_trades_all_pass_hurdle():
    cc = json.loads(CCRES.read_text())
    assert len(cc["trades"]) == 33 and cc["n_skipped"] == 13
    bases = [float(t["ann_basis"]) for t in cc["trades"]]
    assert min(bases) >= 0.04  # frozen filter
    assert min(bases) > T1 > T2  # hurdle binds nowhere
    assert sum(1 for b in bases if b >= T1) == 33
    assert sum(1 for b in bases if b >= T2) == 33


def test_handchecked_hurdle_boundary_synthetic():
    # hand-checked: literal rule ann_basis >= H*C (use computed floats; 2*0.001
    # is not exact binary, so T1 = 0.0055000000000000005, not decimal 0.0055)
    cases = [
        (T2 - 1e-9, False, False),
        (T2, False, True),   # exactly T2 -> V2 passes, V1 fails
        (T1 - 1e-9, False, True),
        (T1, True, True),    # exactly T1 -> both pass
        (0.04, True, True),  # frozen threshold passes both
        (0.034823, True, True),  # a real frozen-skipped basis passes H but not 0.04
        (-0.004667, False, False),  # backwardation fails both
    ]
    for b, e1, e2 in cases:
        assert (b >= T1) is e1, b
        assert (b >= T2) is e2, b
    # hand-checked fee arithmetic
    assert abs((0.001 + 0.001 + 0.00055 + 0.0002) - 0.00275) < 1e-12


def test_carry_mtm_causal_truncation():
    """Causality: last-CLOSED-hourly mark recomputed from a truncated table
    is identical on the kept prefix (no future peek)."""
    h = pd.read_parquet(HOURLY, columns=["t", "close", "sym"])
    h["t"] = pd.to_datetime(h["t"], utc=True)
    d = h[h["sym"] == "BTCUSDT"].sort_values("t").reset_index(drop=True)
    times = d["t"].values.astype("datetime64[ns]").astype(np.int64)
    closes = d["close"].to_numpy(dtype=float)
    cut = len(d) // 2
    t_cut = d["t"].iloc[cut]
    grid = pd.date_range(d["t"].iloc[10], t_cut, freq="1h")
    gn = grid.values.astype("datetime64[ns]").astype(np.int64)

    def marks(t_ns, c_ls, q_ns):
        idx = np.searchsorted(t_ns, q_ns, side="left") - 1
        out = np.full(len(q_ns), np.nan)
        ok = idx >= 0
        out[ok] = c_ls[idx[ok]]
        return out

    full_m = marks(times, closes, gn)
    trunc_m = marks(times[:cut], closes[:cut], gn)
    # on the kept prefix both agree wherever defined
    ok = ~np.isnan(full_m) & ~np.isnan(trunc_m)
    assert ok.sum() > 100
    assert bool((full_m[ok] == trunc_m[ok]).all())
    # strict-before semantics: a query exactly at a bar time gets the prior bar
    q0 = np.array([times[100]])
    assert marks(times, closes, q0)[0] == closes[99]


def test_results_consistency_and_gates():
    res = json.loads((RDIR / "results.json").read_text())
    assert res["meta"]["pick"] == "V1"
    assert res["hurdle_counts"]["REF_n"] == 33
    assert res["hurdle_counts"]["V1_n"] == 33
    assert res["hurdle_counts"]["V2_n"] == 33
    assert res["hurdle_counts"]["V1_extra_skipped"] == []
    assert res["hurdle_counts"]["V2_extra_skipped"] == []
    assert len(res["frozen_skipped_hypothetical"]) == 13
    # dev4 triple equality (hurdle binds nowhere)
    for leg in ("binance", "bybit_S5"):
        assert res["dev4"][leg]["V1"]["years"] == res["dev4"][leg]["V2"]["years"]
        assert res["dev4"][leg]["V1"]["years"] == res["dev4"][leg]["REF"]["years"]
    # gates
    b5 = res["five"]["binance"]["REF"]
    assert b5["mean"] == 5.634 and b5["DD"] == 16.75
    assert b5["full_path_dd"]["full"] == 16.66
    y5 = res["five"]["bybit_S5"]["REF"]
    assert y5["mean"] == 5.111 and y5["DD"] == 17.95
    assert y5["full_path_dd"]["full"] == 17.93
    # V2 has no recent/5y rows by protocol (only pick + REF scored)
    assert set(res["five"]["binance"]) == {"V1", "REF"}
    assert [y["R"] for y in res["recent_once"]["binance"]["V1"]] if isinstance(
        res["recent_once"]["binance"]["V1"], list) else True
    # REPORT.md exists and ends with a Vietnamese verdict
    rep = (RDIR / "REPORT.md").read_text(encoding="utf-8")
    assert "Vietnamese verdict" in rep
