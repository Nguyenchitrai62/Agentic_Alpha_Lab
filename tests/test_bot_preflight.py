"""bot_preflight: read-only account checks before testnet/live. No network, no keys.

The real ``bot.bybit_v5.Bybit`` client talks to ``tests/mock_bybit_v5.py`` (or a
small subclass below that adds the real-API fields the base mock omits:
query-api permissions, position leverage/tradeMode, server time). Every test
drives ``scripts/bot_preflight.run_preflight`` / ``main`` with that
monkeypatched client. No test may touch a real endpoint, print a key, place,
amend or cancel an order, or call a settings-changing endpoint.
"""
import importlib.util
import json
import time
from pathlib import Path

import pytest

from bot.bybit_v5 import TESTNET, Bybit, BybitError
from tests.mock_bybit_v5 import MockBybitV5

SPEC = importlib.util.spec_from_file_location(
    "bot_preflight", Path(__file__).resolve().parents[1] / "scripts" / "bot_preflight.py")
pf = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pf)

SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]


class RichMock(MockBybitV5):
    """Base mock + the real-API fields preflight reads (no behaviour change otherwise)."""

    def __init__(self, *a, api_info="missing", leverage=None, trade_mode=None,
                 fail_signed_code=None, fail_wallet_msg=None, server_ms=None, **kw):
        super().__init__(*a, **kw)
        self.api_info = api_info  # "missing" -> base behaviour (no query-api route)
        self.leverage = dict(leverage or {})
        self.trade_mode = dict(trade_mode or {})
        self.fail_signed_code = fail_signed_code  # e.g. "10003: Invalid API key"
        self.fail_wallet_msg = fail_wallet_msg    # e.g. classic-account error
        self.server_ms = server_ms                # int ms, or None -> no time route

    def _route(self, method, path, query, body):
        if self.fail_signed_code and not self._is_public(path):
            raise BybitError(self.fail_signed_code)
        if method == "GET" and path == "/v5/user/query-api":
            if self.api_info == "missing":
                raise BybitError("10001: mock has no route for GET /v5/user/query-api")
            return dict(self.api_info)
        if method == "GET" and path == "/v5/market/time":
            if self.server_ms is None:
                raise BybitError("10001: mock has no route for GET /v5/market/time")
            return {"timeSecond": str(self.server_ms // 1000),
                    "timeNano": str(int(self.server_ms * 1_000_000))}
        if method == "GET" and path == "/v5/account/wallet-balance":
            if self.fail_wallet_msg:
                raise BybitError(self.fail_wallet_msg)
        res = super()._route(method, path, query, body)
        if method == "GET" and path == "/v5/position/list":
            for p in res.get("list", []):
                if p.get("symbol") in self.leverage:
                    p["leverage"] = self.leverage[p["symbol"]]
                if p.get("symbol") in self.trade_mode:
                    p["tradeMode"] = self.trade_mode[p["symbol"]]
        return res


def _client(monkeypatch, mock):
    mock.install_session(monkeypatch)
    return Bybit("k", "s", base=TESTNET)


def _plan(tmp_path, btc_frac=0.03, btc_weight=0.05):
    plan = {"generated_at": "2026-10-06T04:00:00+00:00", "phases": [{"phase": 0, "capital": 0.25}],
            "coins": {}}
    px = {"BTCUSDT": 80000.0, "ETHUSDT": 3000.0, "SOLUSDT": 150.0, "BNBUSDT": 600.0, "XRPUSDT": 2.0}
    for s in SYMS:
        plan["coins"][s] = {
            "price": px[s],
            "subs": [{"phase": 0, "state": "pending",
                      "order": {"kind": "open", "side": "BUY", "price": px[s], "weight": btc_weight,
                                "issued": "2026-10-06T03:00:00+00:00",
                                "valid_until": "2026-10-06T07:00:00+00:00",
                                "sl_if_filled": px[s] * 0.9, "tp_if_filled": px[s] * 1.1}}],
            "dips": [{"rung": 2.5, "phase": 0, "buy_limit": px[s] * 0.975, "tp": px[s] * 0.985,
                      "stop": px[s] * 0.94, "backstop": px[s] * 0.9, "size_frac": btc_frac,
                      "active_from": "2026-10-06T03:00:00+00:00",
                      "active_until": "2026-10-06T07:00:00+00:00"}]}
    f = tmp_path / "plan.json"
    f.write_text(json.dumps(plan))
    return json.loads(f.read_text())


def _rows(rows):
    return {name: (st, detail, fix) for name, st, detail, fix in rows}


def _clean_mock(monkeypatch, equity=10000.0, **kw):
    kw.setdefault("api_info", {"id": 1, "readOnly": 0,
                               "permissions": {"ContractTrade": ["Order", "Position"]}})
    kw.setdefault("server_ms", int(time.time() * 1000))
    mock = RichMock(equity=equity, **kw)
    return mock, _client(monkeypatch, mock)


def test_all_pass_clean_account(monkeypatch, tmp_path):
    mock, client = _clean_mock(monkeypatch, equity=10000.0,
                               leverage={"BTCUSDT": "5"},
                               trade_mode={"BTCUSDT": 0})
    mock.pos = {("BTCUSDT", 1): {"qty": 0.01, "avg": 80000.0}}
    rows, code = pf.run_preflight(client, _plan(tmp_path))
    assert code == 0
    d = _rows(rows)
    assert d["API key"][0] == "PASS"
    assert d["Hedge Mode"][0] == "PASS"
    assert d["Cross margin"][0] == "PASS"
    assert d["Đòn bẩy 5x"][0] == "PASS"
    assert d["Vốn"][0] == "PASS"
    assert d["Lệnh/vị thế lạ"][0] == "WARN"  # the open BTC position has unknown owner
    assert "BTCUSDT" in d["Lệnh/vị thế lạ"][1]
    assert d["Giờ server"][0] == "PASS"
    assert d["Minima sàn"][0] == "PASS"
    assert all(v[0] != "FAIL" for v in d.values())


def test_all_pass_no_positions_warns_but_exits_zero(monkeypatch, tmp_path):
    mock = MockBybitV5(equity=12000.0)  # base mock: no query-api / time / leverage fields
    client = _client(monkeypatch, mock)
    rows, code = pf.run_preflight(client, _plan(tmp_path))
    assert code == 0  # WARN-only rows never fail the exit code
    d = _rows(rows)
    assert d["API key"][0] == "WARN"
    assert d["Hedge Mode"][0] == "WARN"
    assert d["Cross margin"][0] == "WARN"
    assert d["Đòn bẩy 5x"][0] == "WARN"
    assert d["Vốn"][0] == "PASS"
    assert d["Lệnh/vị thế lạ"][0] == "PASS"
    assert d["Giờ server"][0] == "WARN"


def test_fail_invalid_key_aborts(monkeypatch, tmp_path):
    mock, client = _clean_mock(monkeypatch, fail_signed_code="10003: Invalid API key")
    rows, code = pf.run_preflight(client, _plan(tmp_path))
    assert code == 1
    assert rows[0][0] == "API key" and rows[0][1] == "FAIL"
    assert rows[0][3]  # exact Bybit UI step present


def test_fail_readonly_key(monkeypatch, tmp_path):
    mock, client = _clean_mock(monkeypatch, api_info={"id": 1, "readOnly": 1, "permissions": {}})
    rows, code = pf.run_preflight(client, _plan(tmp_path))
    assert code == 1
    assert _rows(rows)["API key"][0] == "FAIL"


def test_fail_classic_account(monkeypatch, tmp_path):
    mock, client = _clean_mock(monkeypatch, fail_wallet_msg="10001: accountType UNIFIED not supported")
    rows, code = pf.run_preflight(client, _plan(tmp_path))
    assert code == 1
    d = _rows(rows)
    assert d["Tài khoản"][0] == "FAIL" and d["Tài khoản"][2]


def test_fail_oneway_position_mode(monkeypatch, tmp_path):
    mock, client = _clean_mock(monkeypatch)
    mock.pos = {("BTCUSDT", 0): {"qty": 0.01, "avg": 80000.0}}
    rows, code = pf.run_preflight(client, _plan(tmp_path))
    assert code == 1
    d = _rows(rows)
    assert d["Hedge Mode"][0] == "FAIL" and "BTCUSDT" in d["Hedge Mode"][1]
    assert d["Hedge Mode"][2]


def test_fail_isolated_margin(monkeypatch, tmp_path):
    mock, client = _clean_mock(monkeypatch, trade_mode={"BTCUSDT": 1})
    mock.pos = {("BTCUSDT", 1): {"qty": 0.01, "avg": 80000.0}}
    rows, code = pf.run_preflight(client, _plan(tmp_path))
    assert code == 1
    d = _rows(rows)
    assert d["Cross margin"][0] == "FAIL" and d["Cross margin"][2]


def test_fail_wrong_leverage(monkeypatch, tmp_path):
    mock, client = _clean_mock(monkeypatch, leverage={"BTCUSDT": "3"},
                               trade_mode={"BTCUSDT": 0})
    mock.pos = {("BTCUSDT", 1): {"qty": 0.01, "avg": 80000.0}}
    rows, code = pf.run_preflight(client, _plan(tmp_path))
    assert code == 1
    d = _rows(rows)
    assert d["Đòn bẩy 5x"][0] == "FAIL" and "3x" in d["Đòn bẩy 5x"][1]
    assert d["Đòn bẩy 5x"][2]


def test_fail_server_skew(monkeypatch, tmp_path):
    mock, client = _clean_mock(monkeypatch)
    monkeypatch.setattr(pf, "fetch_server_time_ms",
                        lambda c: int(time.time() * 1000) + 2500)
    rows, code = pf.run_preflight(client, _plan(tmp_path))
    assert code == 1
    assert _rows(rows)["Giờ server"][0] == "FAIL"


def test_warn_equity_thresholds(monkeypatch, tmp_path):
    mock, client = _clean_mock(monkeypatch, equity=6000.0)
    d = _rows(pf.run_preflight(client, _plan(tmp_path))[0])
    assert d["Vốn"][0] == "WARN" and "thoải mái" in d["Vốn"][1]
    mock2, client2 = _clean_mock(monkeypatch, equity=3000.0)
    d2 = _rows(pf.run_preflight(client2, _plan(tmp_path))[0])
    assert d2["Vốn"][0] == "WARN" and "tối thiểu" in d2["Vốn"][1]


def test_warn_foreign_order_but_not_bot_links(monkeypatch, tmp_path):
    mock, client = _clean_mock(monkeypatch)
    mock.orders["manual123"] = dict(symbol="BTCUSDT", side="Buy", orderType="Limit",
                                    price="79000", triggerPrice=None, qty="0.01",
                                    positionIdx=1, reduceOnly=False)
    mock.orders["b0BTCxyzE"] = dict(symbol="BTCUSDT", side="Buy", orderType="Limit",
                                    price="79000", triggerPrice=None, qty="0.01",
                                    positionIdx=1, reduceOnly=False)
    rows, code = pf.run_preflight(client, _plan(tmp_path))
    assert code == 0
    d = _rows(rows)
    assert d["Lệnh/vị thế lạ"][0] == "WARN"
    assert "manual123" in d["Lệnh/vị thế lạ"][1]
    assert "b0BTCxyzE" not in d["Lệnh/vị thế lạ"][1]


def test_warn_below_minimum_names_coins(monkeypatch, tmp_path):
    # equity 3000 + tiny BTC dip rung (0.01*3000*1.7/78000 < 0.001 BTC) -> BTC below minimum
    mock, client = _clean_mock(monkeypatch, equity=3000.0)
    rows, code = pf.run_preflight(client, _plan(tmp_path, btc_frac=0.01))
    assert code == 0
    d = _rows(rows)
    assert d["Minima sàn"][0] == "WARN" and "BTCUSDT" in d["Minima sàn"][1]


def test_never_posts_or_changes_settings(monkeypatch, tmp_path):
    mock, client = _clean_mock(monkeypatch, leverage={"BTCUSDT": "5"},
                               trade_mode={"BTCUSDT": 0})
    mock.pos = {("BTCUSDT", 1): {"qty": 0.01, "avg": 80000.0}}
    pf.run_preflight(client, _plan(tmp_path))
    posts = [c for c in mock.calls if c[0] == "POST"]
    assert posts == []  # read-only: no order / switch-mode / leverage call may ever fire


def test_main_vietnamese_output_hides_keys_and_live_needs_no_unlock(monkeypatch, tmp_path, capsys):
    mock = RichMock(equity=10000.0,
                    api_info={"id": 1, "readOnly": 0,
                              "permissions": {"ContractTrade": ["Order", "Position"]}},
                    server_ms=int(time.time() * 1000))
    mock.install_session(monkeypatch)
    monkeypatch.setenv("BYBIT_API_KEY", "DUMMYLIVEKEY123")
    monkeypatch.setenv("BYBIT_API_SECRET", "DUMMYLIVESECRET456")
    monkeypatch.delenv("BOT_ALLOW_LIVE", raising=False)
    plan_f = tmp_path / "plan.json"
    plan_f.write_text(json.dumps(_plan(tmp_path)))
    code = pf.main(["--mode", "live", "--plan", str(plan_f)])
    out = capsys.readouterr().out
    assert code == 0
    assert "[PASS]" in out and "KẾT QUẢ" in out
    assert "DUMMYLIVEKEY123" not in out and "DUMMYLIVESECRET456" not in out
