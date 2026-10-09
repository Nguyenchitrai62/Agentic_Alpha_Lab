"""oc_ideascan3 verification tests: probes are valid + deliverable shape (scan only)."""
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
PROBES = os.path.join(HERE, "probes")
DOC = os.path.join(HERE, "..", "..", "..", "docs", "opencode", "IDEAS_20261007c.md")

VERIFIED = ["d1_deribit_instruments", "d2b_deribit_trades_by_instr", "d3_bybit_opt_instruments",
            "d4b_bybit_opt_trades_live", "d5_binance_eapi_exchangeinfo", "d6_hyperliquid_meta",
            "d7_hyperliquid_funding", "d8_coinbase_intl_instruments", "d10_farside_etf_btc",
            "d11_coingecko_stablecoins", "d12_binance_sysstatus", "d13b_okx_instruments",
            "d14b_bitfinex_ticker", "d17_hl_assetctxs", "d18_bybit_delivery_price",
            "d20_yahoo_cme_btc"]


def test_probe_files_valid_and_small():
    total = 0
    files = [f for f in os.listdir(PROBES) if f.endswith(".json")]
    assert len(files) >= 16, f"expected >=16 probe files, got {len(files)}"
    for f in files:
        p = os.path.join(PROBES, f)
        total += os.path.getsize(p)
        with open(p, encoding="utf-8") as fh:
            rec = json.load(fh)
        assert rec["name"] and rec["url"] and rec["method"]
        assert rec.get("http") is not None or rec.get("error"), f
    assert total < 5 * 1024 * 1024, total


def test_verified_probes_have_payload():
    for name in VERIFIED:
        with open(os.path.join(PROBES, name + ".json"), encoding="utf-8") as fh:
            rec = json.load(fh)
        assert rec["http"] == 200, f"{name}: {rec}"
        assert len(rec["head"]) > 20, f"{name}: empty head"


def test_hand_checked_deribit_payload_shape():
    # hand-checked: d2b head must contain 3 real trades with price/index_price/trade_id
    with open(os.path.join(PROBES, "d2b_deribit_trades_by_instr.json"), encoding="utf-8") as fh:
        rec = json.load(fh)
    head = json.loads(rec["head"] if rec["head"].startswith("{") else "{}")
    trades = head["result"]["trades"]
    assert len(trades) == 3
    for t in trades:
        assert t["price"] > 0 and t["index_price"] > 0 and t["trade_id"]


def test_deliverable_shape():
    with open(os.path.abspath(DOC), encoding="utf-8") as fh:
        text = fh.read()
    assert "## A." in text and "## B." in text and "## C." in text
    assert len(re.findall(r"^### B\d+\.", text, re.M)) == 10, "section B must hold exactly 10 ideas"
    assert len(re.findall(r"^### D\d+\.", text, re.M)) >= 8, "section A must hold >= 8 data candidates"
