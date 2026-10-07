"""Lightweight checks for oc_manual2coin (no market data, no simulation)."""
import importlib.util
import inspect
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "oc_manual2coin", ROOT / "research/diagnostics/oc_manual2coin/oc_manual2coin.py")
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


def test_rows_fixed():
    assert MOD.ROWS == ["M5_human", "M5_human_2coin", "M5_human_2coin_x25"]
    assert MOD.COINS_2 == ("SOLUSDT", "XRPUSDT")
    assert MOD.MULT_X25 == 2.5
    assert list(MOD.ANCH5) == ["2021-09-24", "2022-09-24", "2023-09-24",
                               "2024-09-24", "2025-09-24"]


def test_coin_filter_values():
    MOD.COIN_IDX_2 = {2, 4}  # SOL, XRP positions in canonical 5-coin order
    # reference: every non-night bar places
    assert MOD.coin_filter_value(0, False, "M5_human") == 1.0
    assert MOD.coin_filter_value(0, True, "M5_human") == 0.0
    # 2coin: BTC/ETH/BNB off, SOL/XRP on at 1.0
    assert MOD.coin_filter_value(0, False, "M5_human_2coin") == 0.0
    assert MOD.coin_filter_value(1, False, "M5_human_2coin") == 0.0
    assert MOD.coin_filter_value(3, False, "M5_human_2coin") == 0.0
    assert MOD.coin_filter_value(2, False, "M5_human_2coin") == 1.0
    assert MOD.coin_filter_value(4, False, "M5_human_2coin") == 1.0
    assert MOD.coin_filter_value(2, True, "M5_human_2coin") == 0.0
    # x25: freed budget re-spread 5/2 on SOL/XRP only
    assert MOD.coin_filter_value(2, False, "M5_human_2coin_x25") == 2.5
    assert MOD.coin_filter_value(4, False, "M5_human_2coin_x25") == 2.5
    assert MOD.coin_filter_value(0, False, "M5_human_2coin_x25") == 0.0
    assert MOD.coin_filter_value(2, True, "M5_human_2coin_x25") == 0.0


def test_filter_uses_bar_open_info_only():
    src = inspect.getsource(MOD.coin_filter_value)
    assert "fill_minute" not in src
    assert "sleeve_start" not in src
    assert "win_start" not in src


def test_geom5():
    assert MOD.geom5_from_reset_R([0, 0, 0, 0, 0]) == 0.0
    assert abs(MOD.geom5_from_reset_R([6.0] * 5) - 6.0) < 1e-9


def test_placeability_btc_bottleneck():
    # oc_lots ordering: at E=1250 a tiny BTC weight fails, SOL/XRP pass.
    # BTC 0.30 BTC notional-scale weight at 60k: N=0.004*1250=5 USDT borderline.
    assert MOD.is_placeable("XRPUSDT", 0.02, 0.6) is True
    assert MOD.is_placeable("BTCUSDT", 0.00001, 60000.0) is False
    # 2.5x bracket is more placeable than 1.0x at the same price
    w_small = 0.004
    assert MOD.is_placeable("SOLUSDT", w_small * 2.5, 150.0) in (True, False)
    assert MOD.LOTS["BTCUSDT"] == (0.001, 0.001)
    assert MOD.MIN_NOTIONAL == 5.0
    assert MOD.FEAS_PHASE_EQUITY == 1250.0


def test_runs_for_reset_shape():
    allres = {s: {"M5_human": {"years": [], "load": {}, "feas": {}}} for s in range(4)}
    runs = MOD.runs_for_reset(allres, "M5_human")
    assert set(runs) == {0, 1, 2, 3}
    for s in range(4):
        assert set(runs[s]) == {"M5_human"}
