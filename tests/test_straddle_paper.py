"""straddle_paper: prospective weekly short-straddle ledger on REAL Bybit quotes.

Fake public client only (no network, no keys, no orders). Covers: Friday entry
window, nearest-strike tie->lower, fill at bid / buy-back at ask, fee caps,
SL/TP math on a synthetic path (incl. TP only on 4h closes), expiry settlement
payoff, restart idempotence (no double entry), qty flooring, public-only paths.
"""
import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "straddle_paper", Path(__file__).resolve().parents[1] / "scripts" / "straddle_paper.py")
sp = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(sp)

MS_HOUR = 3_600_000


def ms(y, mo, d, h=0, mi=0):
    return int(datetime(y, mo, d, h, mi, tzinfo=timezone.utc).timestamp() * 1000)


FRI_ENTRY = ms(2026, 10, 9, 8, 30)      # Friday, inside 08:05-09:00
FRI_EXPIRY = ms(2026, 10, 16, 8, 0)     # next Friday 08:00 UTC
DVOL = lambda cur, now: 60.0            # noqa: E731 - injected, no network


class FakePublic:
    """Bybit V5 PUBLIC surface the ledger reads (option only)."""

    def __init__(self, contracts, quotes, delivery=None, fail_first=()):
        # contracts: [{symbol, coin, delivery_ms, otype, step}]
        self.contracts = list(contracts)
        self.quotes = dict(quotes)        # symbol -> ticker row
        self.delivery = dict(delivery or {})
        self.fail_first = dict(fail_first)
        self.calls = []

    def public(self, path, **params):
        self.calls.append((path, dict(params)))
        if self.fail_first.get(path, 0) > 0:
            self.fail_first[path] -= 1
            raise RuntimeError("10006: Too many visits (fake rate limit)")
        if path == "/v5/market/instruments-info":
            rows = [{"symbol": c["symbol"], "status": "Trading", "baseCoin": c["coin"],
                     "optionsType": c["otype"], "deliveryTime": str(c["delivery_ms"]),
                     "lotSizeFilter": {"qtyStep": str(c.get("step", 0.01)),
                                       "minOrderQty": str(c.get("step", 0.01))},
                     "deliveryFeeRate": "0.00015"}
                    for c in self.contracts
                    if c["coin"] == params.get("baseCoin")]
            return {"list": rows, "nextPageCursor": ""}
        if path == "/v5/market/tickers":
            rows = [dict(self.quotes[s]) for s in self.quotes
                    if s in self.quotes and
                    (params.get("symbol") in (None, s) or
                     s.startswith(params.get("baseCoin", "###")) or True)]
            if params.get("baseCoin"):
                rows = [r for r in rows if r["symbol"].startswith(params["baseCoin"] + "-")]
            return {"list": rows}
        if path == "/v5/market/delivery-price":
            rows = [{"symbol": s, "deliveryPrice": str(px), "deliveryTime": "1"}
                    for s, px in self.delivery.items()]
            return {"list": rows}
        raise AssertionError(f"unexpected public path {path}")


def quote(symbol, bid, ask, mark, s_ref, bid_iv=0.31, mark_iv=0.32):
    return {"symbol": symbol, "bid1Price": str(bid), "ask1Price": str(ask),
            "markPrice": str(mark), "bid1Iv": str(bid_iv), "markIv": str(mark_iv),
            "underlyingPrice": str(s_ref), "indexPrice": str(s_ref)}


def coin_contracts(coin, expiry_ms, strikes, step):
    exp = "16OCT26"
    out = []
    for k in strikes:
        ki = int(k)
        for typ in ("Call", "Put"):
            out.append({"symbol": f"{coin}-{exp}-{ki}-{typ[0]}-USDT", "coin": coin,
                        "delivery_ms": expiry_ms, "otype": typ, "step": step})
    return out


def _actions(sdir):
    p = Path(sdir) / "actions.jsonl"
    if not p.exists():
        return []
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]


def _state(sdir):
    return json.loads((Path(sdir) / "state.json").read_text(encoding="utf-8"))


def test_rule_frozen_sha_and_window():
    assert sp.RULE_PARAMS["entry_window_utc"] == ["08:05", "09:00"]
    assert sp.TP_HOURS == (0, 4, 8, 12, 16, 20)
    sha = sp.rule_sha256()
    assert len(sha) == 64 and all(c in "0123456789abcdef" for c in sha)
    assert sp.in_entry_window(FRI_ENTRY) is True
    assert sp.in_entry_window(ms(2026, 10, 9, 8, 4)) is False
    assert sp.in_entry_window(ms(2026, 10, 9, 9, 0)) is False
    assert sp.in_entry_window(ms(2026, 10, 8, 8, 30)) is False  # Thursday
    assert sp.next_friday_0800_ms(FRI_ENTRY) == FRI_EXPIRY
    assert sp.next_friday_0800_ms(ms(2026, 10, 8, 12, 0)) == ms(2026, 10, 9, 8, 0)  # Thu -> this Fri
    assert sp.is_tp_hour(ms(2026, 10, 12, 12, 0)) is True
    assert sp.is_tp_hour(ms(2026, 10, 12, 10, 0)) is False


def test_nearest_strike_tie_goes_lower():
    assert sp.nearest_strike([83000, 84000], 83500) == 83000
    assert sp.nearest_strike([83000, 84000], 83750) == 84000
    assert sp.parse_strike("BTC-16OCT26-84000-C-USDT") == 84000.0


def _entry_setup(s_ref=84000.0, bid_c=1735.0, bid_p=1570.0, step=0.01, coin="BTC"):
    contracts = coin_contracts(coin, FRI_EXPIRY, [83000, 84000, 85000], step)
    c_sym = f"{coin}-16OCT26-84000-C-USDT"
    p_sym = f"{coin}-16OCT26-84000-P-USDT"
    quotes = {c["symbol"]: quote(c["symbol"], bid_c, bid_c + 5, bid_c - 2, s_ref)
              for c in contracts}
    quotes[c_sym] = quote(c_sym, bid_c, bid_c + 5, bid_c - 2, s_ref)
    quotes[p_sym] = quote(p_sym, bid_p, bid_p + 5, bid_p - 2, s_ref)
    return FakePublic(contracts, quotes), c_sym, p_sym


def test_entry_fills_at_bid_and_skips_without_bid(tmp_path):
    cli, c_sym, p_sym = _entry_setup()
    res = sp.run_once(cli, tmp_path, 50000.0, 0.25, "straddle",
                      now_ms=FRI_ENTRY, dvol_fetcher=DVOL)
    assert res["entered"] == 1
    pos = _state(tmp_path)["positions"]["BTC"]
    assert pos["K"] == 84000.0 and pos["call_symbol"] == c_sym
    q = (0.5 * 0.25 * 50000.0 / 84000.0 // 0.01) * 0.01
    assert pos["q"] == pytest.approx(q)
    assert pos["premium"] == pytest.approx(q * (1735.0 + 1570.0))  # filled at BID
    assert pos["bs_premium_097dvol"] is not None  # research comparison recorded

    # a leg with no bid -> skip the coin, logged
    cli2, c2, p2 = _entry_setup()
    cli2.quotes[c2] = quote(c2, 0, 1740, 1733, 84000.0)  # bid missing/zero
    res2 = sp.run_once(cli2, tmp_path / "nobid",
                       50000.0, 0.25, "straddle", now_ms=FRI_ENTRY, dvol_fetcher=DVOL)
    assert res2["entered"] == 0 and res2["skipped"] >= 1


def test_qty_floor_and_zero_skip(tmp_path):
    assert sp.floor_to_step(0.00742, 0.01) == 0.0
    assert sp.floor_to_step(0.0149, 0.01) == pytest.approx(0.01)
    cli, _, _ = _entry_setup()
    res = sp.run_once(cli, tmp_path, 1.0, 0.25, "straddle",  # dust equity -> q rounds to 0
                      now_ms=FRI_ENTRY, dvol_fetcher=DVOL)
    assert res["entered"] == 0 and res["skipped"] >= 1


def test_fee_caps():
    assert sp.fee_taker(100000.0, 84000.0) == pytest.approx(0.0003 * 84000.0)  # rate binds
    assert sp.fee_taker(100.0, 84000.0) == pytest.approx(0.07 * 100.0)  # 7% cap binds
    assert sp.delivery_fee(84000.0, 100000.0) == pytest.approx(0.00015 * 84000.0)
    assert sp.delivery_fee(84000.0, 10.0) == pytest.approx(0.125 * 10.0)  # 12.5% cap binds
    assert sp.delivery_fee(84000.0, 0.0) == 0.0


def test_sl_triggers_on_synthetic_path(tmp_path):
    cli, c_sym, p_sym = _entry_setup()
    sp.run_once(cli, tmp_path, 50000.0, 0.25, "straddle", now_ms=FRI_ENTRY, dvol_fetcher=DVOL)
    pos = _state(tmp_path)["positions"]["BTC"]
    prem, q = pos["premium"], pos["q"]
    # crash: ask cost far above premium + fees -> SL buys back at the ASK
    big = (prem + pos["entry_fees"] + prem + 1.0) / q / 2.0
    cli.quotes[c_sym] = quote(c_sym, big - 50, big, big - 10, 90000.0)
    cli.quotes[p_sym] = quote(p_sym, big - 50, big, big - 10, 90000.0)
    res = sp.run_once(cli, tmp_path, 5000.0, 0.25, "straddle",
                      now_ms=ms(2026, 10, 12, 10, 0), dvol_fetcher=DVOL)
    assert res["settled"] == 1
    hist = _state(tmp_path)["history"]
    assert hist[-1]["reason"] == "sl"
    assert hist[-1]["close_ask_c"] == pytest.approx(big)  # bought back at ASK
    assert hist[-1]["realised_pnl"] <= -prem


def test_tp_only_at_4h_close(tmp_path):
    cli, c_sym, p_sym = _entry_setup()
    sp.run_once(cli, tmp_path, 50000.0, 0.25, "straddle", now_ms=FRI_ENTRY, dvol_fetcher=DVOL)
    pos = _state(tmp_path)["positions"]["BTC"]
    prem = pos["premium"]
    tiny = (0.2 * prem) / pos["q"] / 2.0  # ask cost = 0.2 x premium -> TP condition met
    cli.quotes[c_sym] = quote(c_sym, tiny - 1, tiny, tiny, 84000.0)
    cli.quotes[p_sym] = quote(p_sym, tiny - 1, tiny, tiny, 84000.0)
    res = sp.run_once(cli, tmp_path, 50000.0, 0.25, "straddle",
                      now_ms=ms(2026, 10, 12, 10, 0), dvol_fetcher=DVOL)  # 10:00, not a TP hour
    assert res["settled"] == 0 and "BTC" in _state(tmp_path)["positions"]
    res = sp.run_once(cli, tmp_path, 50000.0, 0.25, "straddle",
                      now_ms=ms(2026, 10, 12, 12, 0), dvol_fetcher=DVOL)  # 12:00 TP hour
    assert res["settled"] == 1
    hist = _state(tmp_path)["history"]
    assert hist[-1]["reason"] == "tp" and "maker_side_cost" in hist[-1]


def test_settlement_payoff(tmp_path):
    cli, c_sym, p_sym = _entry_setup()
    sp.run_once(cli, tmp_path, 50000.0, 0.25, "straddle", now_ms=FRI_ENTRY, dvol_fetcher=DVOL)
    pos = _state(tmp_path)["positions"]["BTC"]
    q, prem, efee = pos["q"], pos["premium"], pos["entry_fees"]
    cli.delivery[c_sym] = 86000.0  # ITM call, intrinsic 2000
    res = sp.run_once(cli, tmp_path, 50000.0, 0.25, "straddle",
                      now_ms=FRI_EXPIRY + MS_HOUR, dvol_fetcher=DVOL)
    assert res["settled"] == 1
    hist = _state(tmp_path)["history"]
    assert hist[-1]["reason"] == "expired" and hist[-1]["settle_source"] == "delivery-price"
    dfee = min(0.00015 * 86000.0, 0.125 * 2000.0) * q
    assert hist[-1]["realised_pnl"] == pytest.approx(prem - efee - q * 2000.0 - dfee)


def test_restart_idempotence_no_double_entry(tmp_path):
    cli, _, _ = _entry_setup()
    r1 = sp.run_once(cli, tmp_path, 50000.0, 0.25, "straddle", now_ms=FRI_ENTRY, dvol_fetcher=DVOL)
    r2 = sp.run_once(cli, tmp_path, 50000.0, 0.25, "straddle",
                     now_ms=FRI_ENTRY + 5 * 60_000, dvol_fetcher=DVOL)  # restart 5 min later
    assert (r1["entered"], r2["entered"]) == (1, 0)
    assert len(_state(tmp_path)["positions"]) == 1
    ops = [a["op"] for a in _actions(tmp_path)]
    assert ops.count("entry") == 1 and "skip" in ops


def test_outside_window_waits_and_missed_friday_skips(tmp_path):
    cli, _, _ = _entry_setup()
    res = sp.run_once(cli, tmp_path, 5000.0, 0.25, "straddle",
                      now_ms=ms(2026, 10, 7, 8, 0), dvol_fetcher=DVOL)  # Wednesday
    assert res["entered"] == 0 and "no entry window" in res["summary"]
    res = sp.run_once(cli, tmp_path, 5000.0, 0.25, "straddle",
                      now_ms=ms(2026, 10, 9, 10, 0), dvol_fetcher=DVOL)  # Friday, window missed
    assert res["entered"] == 0 and res["skipped"] >= 1


def test_public_only_and_error_robustness(tmp_path):
    cli, _, _ = _entry_setup()
    cli.fail_first["/v5/market/tickers"] = 5  # persistent API failure
    res = sp.run_once(cli, tmp_path, 5000.0, 0.25, "straddle", now_ms=FRI_ENTRY, dvol_fetcher=DVOL)
    assert res["errors"] >= 1 and res["status"] == "ok"  # logged, exit-0 style
    for path, _ in cli.calls:
        assert path.startswith("/v5/market/")  # public market data only, never orders
    src = (Path(__file__).resolve().parents[1] / "scripts" / "straddle_paper.py").read_text()
    assert ".post(" not in src and "X-BAPI" not in src and "api_key" not in src  # no signing, no POST
    assert "Bybit(None, None" in src  # keyless public client only
