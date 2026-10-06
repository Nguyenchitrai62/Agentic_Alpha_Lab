"""Tests for oc_usdccarry (USDC linear dated as carry leg, POST-HOC).

Covers: frozen-rule threshold, quarterly-only universe, fee math, entry causality,
delivery-bar settlement, year/pooled accounting, liquidity presence, MANIFEST sha256,
REPORT.md consistency (POST-HOC label, comparison, Vietnamese 3-line verdict), and
research-only hygiene (public endpoints only, no orders, no artifacts/bot paths, no 1m).
"""

import datetime
import hashlib
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / "research/tournament/oc_usdccarry"
BDIR = ROOT / "data" / "raw" / "bybit_quarterly_20261006"


def _res():
    return json.loads((HERE / "results.json").read_text())


def _is_quarterly(delivery_ymd: str) -> bool:
    d = datetime.datetime.strptime(delivery_ymd, "%Y-%m-%d").replace(
        tzinfo=datetime.timezone.utc)
    return (d.month in (3, 6, 9, 12) and d.weekday() == 4
            and (d + datetime.timedelta(days=7)).month != d.month)


def test_counts_and_threshold():
    out = _res()
    assert out["meta"]["post_hoc"] is True
    assert out["n_contracts_seen"] == 24  # 12 BTC + 12 ETH USDC quarterlies
    assert out["n_trades"] == 20
    assert out["n_skipped"] == 4
    assert out["n_incomplete"] == 0
    for t in out["trades"]:
        assert t["ann_basis"] >= 0.04 - 1e-9, t
        assert _is_quarterly(t["delivery"]), t  # quarterly only
    assert out["pooled"]["n_trades"] == 20
    assert abs(out["pooled"]["sum_ret_alloc"] - 0.424373) < 1e-6


def test_quarterly_universe_from_inventory():
    out = _res()
    per = out["inventory"]["quarterly_per_coin"]
    assert set(per) == {"BTC", "ETH"}
    assert len(per["BTC"]) == 12 and len(per["ETH"]) == 12
    assert out["inventory"]["n_usdc_quarterly"] == 24
    inv = json.loads((ROOT / "research/data_fetch/bybitq/inventory.json").read_text())["records"]
    by_sym = {(r["category"], r["symbol"]): r for r in inv}
    for coin, rows in per.items():
        for r in rows:
            rec = by_sym[("linear", r["symbol"])]
            assert rec["settleCoin"] == "USDC"
            assert rec["baseCoin"] == coin
            assert _is_quarterly(r["delivery"])


def test_fee_math_handcheck():
    out = _res()
    for t in out["trades"][:6] + out["trades"][-6:]:
        gross = ((t["S_del"] - t["S_entry"]) / t["S_entry"]
                 + (t["F_entry"] - t["S_del"]) / t["F_entry"])
        expect = round(gross - 0.00275, 6)
        assert abs(t["ret_alloc"] - expect) < 1e-9, t


def test_entry_causal_spot_check():
    """Recompute one mid-history entry from truncated spot closes (<= entry)."""
    out = _res()
    t = next(r for r in out["trades"]
             if r["coin"] == "BTC" and r["delivery"] == "2024-03-29")
    spot = pd.read_parquet(BDIR / "spot_BTCUSDT_1h.parquet", columns=["open_time", "close"])
    hh = pd.DataFrame({"t": pd.to_datetime(spot["open_time"], unit="ms", utc=True),
                       "close": spot["close"].to_numpy(dtype=float)}).sort_values("t")
    hh["bar"] = hh["t"].dt.floor("4h")
    g = hh.groupby("bar")
    ok = g.size()[lambda n: n == 4].index
    bars = pd.DataFrame({"open_time": pd.to_datetime(sorted(ok), utc=True)})
    bars["close"] = bars["open_time"].map(g["close"].last()).to_numpy(dtype=float)
    te = pd.Timestamp(t["entry_open"], tz="UTC")
    trunc = bars[bars["open_time"] <= te]
    assert abs(float(trunc["close"].iloc[-1]) - t["S_entry"]) < 1e-9
    assert float(bars["close"].iloc[-1]) != float(trunc["close"].iloc[-1])


def test_settlement_is_delivery_bar_spot_close():
    out = _res()
    t = next(r for r in out["trades"]
             if r["coin"] == "ETH" and r["delivery"] == "2025-03-28")
    spot = pd.read_parquet(BDIR / "spot_ETHUSDT_1h.parquet", columns=["open_time", "close"])
    hh = pd.DataFrame({"t": pd.to_datetime(spot["open_time"], unit="ms", utc=True),
                       "close": spot["close"].to_numpy(dtype=float)}).sort_values("t")
    hh["bar"] = hh["t"].dt.floor("4h")
    g = hh.groupby("bar")
    ok = g.size()[lambda n: n == 4].index
    bars = pd.DataFrame({"open_time": pd.to_datetime(sorted(ok), utc=True)})
    bars["close"] = bars["open_time"].map(g["close"].last()).to_numpy(dtype=float)
    bars["close_time"] = bars["open_time"] + pd.Timedelta(hours=4)
    D = pd.Timestamp("2025-03-28 08:00", tz="UTC")
    cand = bars[bars["close_time"] > D].iloc[0]
    assert abs(float(cand["close"]) - t["S_del"]) < 1e-9


def test_year_sums_match_trades():
    out = _res()
    tot = 0.0
    for y in out["years"]:
        s = sum(r[4] for r in y["trades"])
        assert abs(s - y["sum_ret_alloc"]) < 1e-6, y["year"]
        assert y["n_trades"] == len(y["trades"])
        tot += s
    assert abs(tot - out["pooled"]["sum_ret_alloc"]) < 1e-6
    # f = 0.25 rows scale linearly from allocated sums
    assert abs(out["pooled"]["acct_total_pct_0.25"] - round(0.25 * tot * 100, 4)) < 1e-9
    assert [y["year"] for y in out["years"]] == [
        "2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24"]
    # no USDC quarterly exists outside 2023-03..2025-12: tail years are empty
    assert out["years"][0]["n_trades"] == 0 and out["years"][-1]["n_trades"] == 0


def test_comparison_present_and_posthoc():
    out = _res()
    assert len(out["comparison_years"]) == 5
    y23 = next(y for y in out["comparison_years"] if y["year"] == "2023-09-24")
    assert abs(y23["usdc_sum_ret_alloc"] - 0.26747) < 1e-6
    assert y23["inverse_n"] == 8 and y23["binance_n"] == 8
    # shared-delivery basis diffs are microstructure noise, not a leg edge
    diffs = [r["ret_diff_usdc_minus_inverse"] for r in out["overlap_trades"]
             if "ret_diff_usdc_minus_inverse" in r]
    assert len(diffs) >= 18
    assert max(abs(d) for d in diffs) <= 0.0061
    # reference pools quoted from the frozen-rule studies
    assert abs(out["reference"]["bybit_inverse_pooled_sum"] - 0.4973) < 1e-3
    assert abs(out["reference"]["binance_usdtm_pooled_sum"] - 0.5234) < 1e-3


def test_liquidity_present():
    out = _res()
    assert len(out["liquidity"]) == 24
    for sym, liq in out["liquidity"].items():
        assert liq["rows_1h"] > 0 and liq["turnover_sum"] > 0, sym
    # stub vs mature contrast is real (Mar-23 stub ~1M, Dec-24 ~500M)
    assert out["liquidity"]["BTC-31MAR23"]["turnover_sum"] < 2_000_000
    assert out["liquidity"]["BTC-27DEC24"]["turnover_sum"] > 400_000_000


def test_manifest_sha256():
    man = json.loads((HERE / "MANIFEST.json").read_text())
    assert man["post_hoc"] is True
    paths = [f["path"] for f in man["files"]]
    for want in ("research/tournament/oc_usdccarry/fetch_usdccarry.py",
                 "research/tournament/oc_usdccarry/results.json",
                 "research/tournament/oc_usdccarry/REPORT.md"):
        assert want in paths, want
    for f in man["files"]:
        p = ROOT / f["path"]
        assert p.exists(), f["path"]
        h = hashlib.sha256()
        with open(p, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
        assert h.hexdigest() == f["sha256"], f["path"]
        assert f["bytes"] == p.stat().st_size


def test_report_consistent():
    rep = (HERE / "REPORT.md").read_text(encoding="utf-8")
    out = _res()
    assert "POST-HOC" in rep
    assert "0.4244" in rep or str(out["pooled"]["sum_ret_alloc"]) in rep
    assert str(out["pooled"]["geom_per_month_pct_0.25"]) in rep
    for y in out["years"]:
        assert y["year"] in rep
    assert "Ba dòng kết luận" in rep  # Vietnamese 3-line verdict
    assert "không tốt hơn" in rep or "KHÔNG" in rep or "NO" in rep


def test_research_only_hygiene():
    src = (HERE / "fetch_usdccarry.py").read_text()
    assert "api.bybit.com" in src  # public V5 market endpoints
    for bad in ("artifacts/bot", "bot/bybit", "paper_", "/proc",
                "_1m.parquet", "klines_1m", "intraday_",
                "place_order", "POST /v5/order", "api_key", "api_secret"):
        assert bad not in src, bad
    assert "urllib.request" in src or "urlopen" in src
