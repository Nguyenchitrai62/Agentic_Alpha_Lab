"""oc_usdccarry: Bybit USDC-settled (linear) dated futures inventory + frozen-rule carry recompute.

Assignment: docs/opencode/OPENCODE_W_oc_usdccarry.md
Writes ONLY: research/tournament/oc_usdccarry/{fetch_usdccarry.py,results.json,MANIFEST.json,REPORT.md}
  (plus tests/test_oc_usdccarry.py) and scratch under research/tournament/oc_usdccarry/tmp/.

Read-only inputs (never modified):
  research/data_fetch/bybitq/inventory.json          historical V5 instruments-info record
  data/raw/bybit_quarterly_20261006/spot_*_1h.parquet Bybit spot hourly (public kline endpoint)
  data/raw/bybit_quarterly_20261006/lin_*_1h.parquet  Bybit linear dated hourly (public kline endpoint)
  research/tournament/oc_cashcarry/results.json      Binance USDT-M quarterly reference
  research/data_fetch/bybitq/results_bybit_carry.json Bybit inverse-quarterly reference

Public endpoints only (no keys, GET only, never POST, never an order):
  GET /v5/market/instruments-info?category=linear&status=Trading|Closed  (via stored inventory;
    --live refreshes the Trading page only, polite 4 req/s, offline-safe fallback)
  GET /v5/market/kline?category=linear&symbol=...&interval=60            (via stored parquets)

Frozen rule (SAME as oc_cashcarry PLAN.md, quarterly only, f = 0.25, hold to delivery):
  per coin sort quarterly expiries ascending; candidate entry E_k = round_UP(prev delivery - 7d)
  to next spot 4h open (k = 0: first availability); actual entry T_k = first 4h bar >= E_k with
  both spot close and resampled futures 4h close available; ENTER iff annualised basis
  ln(F/S)*365/DTE >= 4 %/yr; equal-notional spot long + dated short, hold to delivery;
  settlement = Bybit spot 4h close of the delivery bar; fees spot 0.001/side + fut 0.00055
  entry + 0.0002 delivery (drag 0.00275 of allocated). POST-HOC: the USDC-quarterly chain
  (2023-03..2025-12, nothing before 2023-03) was selected AFTER seeing inventory.json,
  so every USDC-vs-inverse comparison below is labelled POST-HOC.

  .venv/Scripts/python.exe research/tournament/oc_usdccarry/fetch_usdccarry.py
  .venv/Scripts/python.exe research/tournament/oc_usdccarry/fetch_usdccarry.py --live
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
BDIR = ROOT / "data" / "raw" / "bybit_quarterly_20261006"
BYBITQ = ROOT / "research" / "data_fetch" / "bybitq"
OC = ROOT / "research" / "tournament" / "oc_cashcarry"

COINS = ["BTC", "ETH"]
ANCHORS = [pd.Timestamp(f"{y}-09-24", tz="UTC") for y in (2021, 2022, 2023, 2024, 2025)]
YEAR_LEN = pd.Timedelta(days=365)
THRESHOLD = 0.04
ROLL_DAYS = 7
F_SPOT = 0.001
F_FUT_ENTRY = 0.00055
F_FUT_DELIV = 0.0002
FEE_PAIR = 2 * F_SPOT + F_FUT_ENTRY + F_FUT_DELIV  # 0.00275 of allocated
FEE_ENTRY_PAID = F_SPOT + F_FUT_ENTRY
F_PRIMARY = 0.25

API = "https://api.bybit.com"
RATE_SLEEP = 0.25


def is_quarterly_delivery(delivery_ms: int) -> bool:
    """Quarterly cycle only (same predicate as scripts/carry_paper.py).

    Delivery on the last Friday of Mar/Jun/Sep/Dec (UTC). Weekly / monthly /
    bi-weekly dated contracts are NOT part of the frozen quarterly rule.
    """
    d = datetime.datetime.fromtimestamp(int(delivery_ms) / 1000, tz=datetime.timezone.utc)
    return (
        d.month in (3, 6, 9, 12)
        and d.weekday() == 4
        and (d + datetime.timedelta(days=7)).month != d.month
    )


def api_get(path: str, params: dict, tries: int = 3) -> dict:
    qs = urllib.parse.urlencode(params)
    url = API + path + "?" + qs
    last: Exception | None = None
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=30) as r:
                d = json.loads(r.read().decode("utf-8"))
            if d.get("retCode") != 0:
                raise RuntimeError(f"retCode={d.get('retCode')} retMsg={d.get('retMsg')}")
            time.sleep(RATE_SLEEP)
            return d
        except Exception as e:  # noqa: BLE001 - public network, backoff then give up
            last = e
            time.sleep(RATE_SLEEP * (2 ** (attempt + 1)))
    raise RuntimeError(f"GET {path} failed after {tries}: {last}")


def live_trading_linear() -> list[dict] | None:
    """Best-effort live snapshot of currently-Trading linear dated contracts (public only)."""
    try:
        out: list[dict] = []
        cursor = ""
        for _ in range(5):
            p: dict = {"category": "linear", "status": "Trading", "limit": "1000"}
            if cursor:
                p["cursor"] = cursor
            d = api_get("/v5/market/instruments-info", p)
            out.extend(d["result"]["list"])
            cursor = d["result"].get("nextPageCursor", "")
            if not cursor:
                break
        return out
    except Exception:
        return None


def load_inventory() -> list[dict]:
    inv = json.loads((BYBITQ / "inventory.json").read_text(encoding="utf-8"))["records"]
    return inv


def usdc_quarterly(inv: list[dict]) -> dict[str, list[dict]]:
    """coin -> sorted list of USDC-settled linear QUARTERLY records (Closed+Trading)."""
    out: dict[str, list[dict]] = {c: [] for c in COINS}
    for r in inv:
        if r.get("category") != "linear" or r.get("settleCoin") != "USDC":
            continue
        if r.get("baseCoin") not in COINS:
            continue
        try:
            dlv = int(r["deliveryTime"])
        except (TypeError, ValueError):
            continue
        if dlv <= 0 or not is_quarterly_delivery(dlv):
            continue
        out[r["baseCoin"]].append(r)
    for c in COINS:
        out[c].sort(key=lambda r: int(r["deliveryTime"]))
    return out


def load_1h(path: Path) -> pd.DataFrame:
    d = pd.read_parquet(path, columns=["open_time", "close", "turnover"])
    t = pd.to_datetime(d["open_time"], unit="ms", utc=True)
    return pd.DataFrame(
        {
            "t": t,
            "close": d["close"].to_numpy(dtype=float),
            "turnover": d["turnover"].to_numpy(dtype=float),
        }
    ).sort_values("t").reset_index(drop=True)


def to_4h(h: pd.DataFrame) -> pd.DataFrame:
    """4h bars on 00/04/... UTC grid; close = hourly close of hour 4k+3.

    A 4h bar is valid only if all 4 hours are present (else NaN) — same
    strictness as research/data_fetch/bybitq/analyze_bybit_carry.py.
    """
    hh = h.copy()
    hh["bar"] = hh["t"].dt.floor("4h")
    g = hh.groupby("bar")
    n = g.size()
    c = g["close"].last()
    ok = n[n == 4].index
    bars = pd.DataFrame({"open_time": pd.to_datetime(sorted(ok), utc=True)})
    bars["close"] = bars["open_time"].map(c).to_numpy(dtype=float)
    bars["close_time"] = bars["open_time"] + pd.Timedelta(hours=4)
    return bars.reset_index(drop=True)


def resample_to_spot(f4: pd.DataFrame, spot: pd.DataFrame) -> np.ndarray:
    """Last futures 4h close with fut close_time <= spot close_time (causal)."""
    fo = f4["close_time"].to_numpy(dtype="datetime64[ns]").astype(np.int64)
    fc = f4["close"].to_numpy(dtype=float)
    sc = spot["close_time"].to_numpy(dtype="datetime64[ns]").astype(np.int64)
    idx = np.searchsorted(fo, sc, side="right") - 1
    out = np.full(len(spot), np.nan)
    ok = idx >= 0
    out[ok] = fc[idx[ok]]
    return out


def fut_path(symbol: str) -> Path:
    return BDIR / f"lin_{symbol.replace('-', '_')}_1h.parquet"


def run_usdc_chain(spot4: dict, uq: dict[str, list[dict]]) -> tuple[list[dict], list[dict], dict]:
    """Frozen-rule recompute on the USDC quarterly chain. Returns (trades, contracts_meta, liquidity)."""
    trades: list[dict] = []
    contracts_meta: list[dict] = []
    liquidity: dict = {}
    f4_cache: dict = {}
    fres_cache: dict = {}
    for coin in COINS:
        s = spot4[coin]
        s_open = s["open_time"]
        s_close_t = s["close_time"]
        s_close = s["close"].to_numpy(dtype=float)
        exps = [(pd.Timestamp(r["deliveryTime"], unit="ms", tz="UTC"), r) for r in uq[coin]]
        exps.sort()
        # resample each quarterly future onto the shared spot 4h grid (causal)
        for D, r in exps:
            f4 = to_4h(load_1h(fut_path(r["symbol"])))
            f4_cache[(coin, r["symbol"])] = f4
            fres_cache[(coin, r["symbol"])] = resample_to_spot(f4, s)
        for k, (D, r) in enumerate(exps):
            F = fres_cache[(coin, r["symbol"])]
            if k > 0:
                cand = exps[k - 1][0] - pd.Timedelta(days=ROLL_DAYS)
                pos = int(
                    np.searchsorted(
                        s_open.to_numpy(dtype="datetime64[ns]").astype(np.int64),
                        cand.value,
                        side="left",
                    )
                )
            else:
                pos = 0
            both = np.where(~np.isnan(s_close) & ~np.isnan(F))[0]
            both = both[both >= pos]
            if len(both) == 0:
                contracts_meta.append(
                    {"coin": coin, "symbol": r["symbol"], "delivery": str(D.date()),
                     "status": "no_overlap"}
                )
                continue
            ti = int(both[0])
            T_open = s_open.iloc[ti]
            T_close = s_close_t.iloc[ti]
            F_entry = float(F[ti])
            S_entry = float(s_close[ti])
            dte_days = (D - T_close).total_seconds() / 86400.0
            if not (np.isfinite(F_entry) and np.isfinite(S_entry)) or dte_days <= 0:
                contracts_meta.append(
                    {"coin": coin, "symbol": r["symbol"], "delivery": str(D.date()),
                     "status": "bad_dte"}
                )
                continue
            basis = float(np.log(F_entry / S_entry) * 365.0 / dte_days)
            si = int(
                np.searchsorted(
                    s_close_t.to_numpy(dtype="datetime64[ns]").astype(np.int64),
                    D.value,
                    side="right",
                )
            )
            if si >= len(s):
                contracts_meta.append(
                    {"coin": coin, "symbol": r["symbol"], "delivery": str(D.date()),
                     "entry": str(T_open.date()), "ann_basis": round(basis, 6),
                     "dte_days": round(dte_days, 2), "status": "incomplete_no_spot"}
                )
                continue
            S_del = float(s_close[si])
            entered = bool(basis >= THRESHOLD)
            rec: dict = {
                "coin": coin, "symbol": r["symbol"], "delivery": str(D.date()),
                "entry_open": str(T_open), "entry_close": str(T_close),
                "F_entry": F_entry, "S_entry": S_entry, "S_del": S_del,
                "dte_days": round(dte_days, 2), "ann_basis": round(basis, 6),
                "entered": entered, "ti": ti, "si": si,
            }
            if entered:
                gross = (S_del - S_entry) / S_entry + (F_entry - S_del) / F_entry
                ret_alloc = float(gross - FEE_PAIR)
                rec["ret_alloc"] = round(ret_alloc, 6)
                rec["gross_locked"] = round(float(gross), 6)
                St = s_close[ti + 1: si + 1]
                Ft = F[ti + 1: si + 1]
                okm = ~np.isnan(St) & ~np.isnan(Ft)
                if okm.sum() == 0:
                    rec["worst_mtm_alloc"] = round(float(-FEE_ENTRY_PAID), 6)
                    rec["n_mtm_bars"] = 0
                else:
                    St, Ft = St[okm], Ft[okm]
                    mtm = (St / S_entry - 1.0) + ((F_entry - Ft) / F_entry) - FEE_ENTRY_PAID
                    rec["worst_mtm_alloc"] = round(float(mtm.min()), 6)
                    rec["n_mtm_bars"] = int(okm.sum())
                trades.append(rec)
            contracts_meta.append(
                {"coin": coin, "symbol": r["symbol"], "delivery": str(D.date()),
                 "ann_basis": rec["ann_basis"], "dte_days": rec["dte_days"],
                 "entered": entered,
                 "status": "entered" if entered else "skipped_basis",
                 "entry": str(T_open.date())}
            )
    # liquidity (turnover) per USDC quarterly contract from the stored hourly klines
    for coin in COINS:
        for r in uq[coin]:
            h = load_1h(fut_path(r["symbol"]))
            to = h["turnover"].to_numpy(dtype=float)
            to = to[np.isfinite(to)]
            n_days = max(len(h) / 24.0, 1e-9)
            liquidity[r["symbol"]] = {
                "coin": coin,
                "delivery": str(pd.Timestamp(r["deliveryTime"], unit="ms", tz="UTC").date()),
                "status": r["status"],
                "rows_1h": int(len(h)),
                "turnover_sum": round(float(to.sum()), 1),
                "turnover_mean_1h": round(float(to.mean()) if len(to) else 0.0, 1),
                "turnover_mean_per_day": round(float(to.sum() / n_days), 1),
            }
    return trades, contracts_meta, liquidity


def per_year(trades: list[dict], contracts_meta: list[dict]) -> list[dict]:
    for r in trades:
        r["entry_ts"] = pd.Timestamp(r["entry_open"])
    years = []
    for a0 in ANCHORS:
        a1 = a0 + YEAR_LEN
        yt = [r for r in trades if a0 <= r["entry_ts"] < a1]
        per_coin: dict = {}
        for coin in COINS:
            ct = [r for r in yt if r["coin"] == coin]
            if ct:
                per_coin[coin] = {
                    "n": len(ct),
                    "mean_ann_basis": round(float(np.mean([r["ann_basis"] for r in ct])), 6),
                    "mean_dte": round(float(np.mean([r["dte_days"] for r in ct])), 1),
                    "mean_ret_alloc": round(float(np.mean([r["ret_alloc"] for r in ct])), 6),
                    "sum_ret_alloc": round(float(np.sum([r["ret_alloc"] for r in ct])), 6),
                    "worst_mtm_alloc": round(float(np.min([r["worst_mtm_alloc"] for r in ct])), 6),
                }
            else:
                per_coin[coin] = {"n": 0}
        tot_sum = round(float(sum(r["ret_alloc"] for r in yt)), 6)
        worst = round(float(min([r["worst_mtm_alloc"] for r in yt])), 6) if yt else None
        years.append(
            {"year": str(a0.date()), "n_trades": len(yt),
             "n_skipped_in_year": None, "per_coin": per_coin,
             "sum_ret_alloc": tot_sum, "worst_mtm_alloc": worst,
             "contrib_acct_pct_0.25": {
                 "year_pct": round(float(F_PRIMARY * tot_sum * 100), 4),
                 "per_month_pct": round(float(F_PRIMARY * tot_sum * 100 / 12), 4)},
             "worst_acct_pct_0.25": (round(float(F_PRIMARY * worst * 100), 4)
                                     if worst is not None else None),
             "trades": [(r["coin"], r["symbol"], r["delivery"], r["ann_basis"],
                         r["ret_alloc"], r["worst_mtm_alloc"]) for r in yt]}
        )
    for y in years:
        a0 = pd.Timestamp(y["year"], tz="UTC")
        a1 = a0 + YEAR_LEN
        sk = [c for c in contracts_meta
              if c.get("status") == "skipped_basis"
              and a0 <= pd.Timestamp(c["entry"], tz="UTC") < a1]
        y["n_skipped_in_year"] = len(sk)
    return years


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true",
                    help="best-effort live Trading snapshot (public GET only; offline-safe)")
    args = ap.parse_args()

    inv = load_inventory()
    n_usdc_all = sum(1 for r in inv if r.get("settleCoin") == "USDC" and r.get("baseCoin") in COINS)
    n_lin_all = sum(1 for r in inv if r.get("category") == "linear" and r.get("baseCoin") in COINS)
    uq = usdc_quarterly(inv)
    n_q = sum(len(v) for v in uq.values())

    live_note: dict = {"live_attempted": bool(args.live), "live_ok": False}
    if args.live:
        snap = live_trading_linear()
        if snap is not None:
            live_note["live_ok"] = True
            live_note["live_trading_linear_dated"] = sum(
                1 for it in snap
                if "Perpetual" not in str(it.get("contractType", ""))
                and str(it.get("contractType", "")).endswith("Futures")
                and str(it.get("baseCoin", "")).upper() in ("BTC", "ETH"))
            live_note["live_usdc_trading"] = sorted({
                str(it.get("symbol")) for it in snap
                if str(it.get("settleCoin", "")).upper() == "USDC"
                and str(it.get("baseCoin", "")).upper() in ("BTC", "ETH")})
        else:
            live_note["live_error"] = "offline or rate-limited; stored inventory.json used"

    spot4 = {c: to_4h(load_1h(BDIR / f"spot_{c}USDT_1h.parquet")) for c in COINS}
    trades, contracts_meta, liquidity = run_usdc_chain(spot4, uq)
    years = per_year(trades, contracts_meta)

    in_window = [r for r in trades if ANCHORS[0] <= r["entry_ts"] < ANCHORS[-1] + YEAR_LEN]
    pooled_sum = float(sum(r["ret_alloc"] for r in in_window))
    fac = 1.0
    for y in years:
        fac *= 1.0 + F_PRIMARY * y["sum_ret_alloc"]
    pooled = {
        "n_trades": len(in_window),
        "sum_ret_alloc": round(pooled_sum, 6),
        "acct_total_pct_0.25": round(float(F_PRIMARY * pooled_sum * 100), 4),
        "per_month_pct_0.25": round(float(F_PRIMARY * pooled_sum * 100 / 60), 4),
        "geom_per_month_pct_0.25": round(float((fac ** (1 / 60) - 1) * 100), 4),
    }

    # comparison vs stored references (same frozen rule, different F leg)
    oc_res = json.loads((OC / "results.json").read_text(encoding="utf-8"))
    bb = json.loads((BYBITQ / "results_bybit_carry.json").read_text(encoding="utf-8"))
    inv_bybit = {t["delivery"] + "|" + t["coin"]: t for t in bb["inverse"]["trades"]}
    bin_by_delivery = {}
    for t in oc_res["trades"]:
        bin_by_delivery.setdefault(t["delivery"] + "|" + t["coin"], t)
    overlap = []
    for r in trades:
        key = r["delivery"] + "|" + r["coin"]
        row: dict = {"coin": r["coin"], "delivery": r["delivery"], "symbol_usdc": r["symbol"],
                     "usdc_ann_basis": r["ann_basis"], "usdc_ret_alloc": r["ret_alloc"]}
        ti = inv_bybit.get(key)
        row["inverse_traded"] = ti is not None
        if ti is not None:
            row["inverse_ann_basis"] = ti["ann_basis"]
            row["inverse_ret_alloc"] = ti["ret_alloc"]
            row["basis_diff_usdc_minus_inverse"] = round(r["ann_basis"] - ti["ann_basis"], 6)
            row["ret_diff_usdc_minus_inverse"] = round(r["ret_alloc"] - ti["ret_alloc"], 6)
        tb = bin_by_delivery.get(key)
        row["binance_traded"] = tb is not None
        if tb is not None:
            row["binance_ann_basis"] = tb["ann_basis"]
            row["binance_ret_alloc"] = tb["ret_alloc"]
        overlap.append(row)
    comparison_years = []
    for i, a in enumerate(ANCHORS):
        yb = next(y for y in oc_res["years"] if y["year"] == str(a.date()))
        yi = bb["inverse"]["years"][i]
        comparison_years.append(
            {"year": str(a.date()),
             "usdc_sum_ret_alloc": years[i]["sum_ret_alloc"],
             "usdc_n": years[i]["n_trades"],
             "inverse_sum_ret_alloc": yi["sum_ret_alloc"],
             "inverse_n": yi["n_trades"],
             "binance_sum_ret_alloc": yb["sum_ret_alloc"],
             "binance_n": yb["n_trades"]})

    out = {
        "meta": {
            "post_hoc": True,
            "post_hoc_note": ("POST-HOC: the USDC-quarterly chain was picked AFTER seeing "
                              "inventory.json (only 2023-03..2025-12 exists); the 4 %/7-day/"
                              "hold-to-delivery rule itself is the FROZEN oc_cashcarry rule, "
                              "unchanged."),
            "rule": ("oc_cashcarry PLAN.md unchanged (7d roll, 4 %/yr threshold, quarterly "
                     "only, hold to delivery, fees spot 0.001/side + fut 0.00055 + delivery "
                     "0.0002, f = 0.25 primary)"),
            "spot": "Bybit spot BTCUSDT/ETHUSDT hourly -> 4h grid 00/04/.. UTC (all 4h present)",
            "futures_4h": ("Bybit USDC linear quarterly hourly -> same 4h grid; "
                           "F(t) = last fut 4h close with close_time <= spot close_time"),
            "settlement": "Bybit spot 4h close of delivery bar (delivery = instruments-info deliveryTime)",
            "linear_note": ("USDC-margined linear futures settle in USDC: ln(F/S) basis + "
                            "price-return P&L apply EXACTLY (no coin-margin convexity, "
                            "same UTA collateral as USDT perps)"),
            "live": live_note,
            "spot_4h": {c: {"bars": len(spot4[c]),
                            "first": str(spot4[c]["open_time"].min()),
                            "last": str(spot4[c]["open_time"].max())} for c in COINS},
        },
        "inventory": {
            "endpoint": "GET /v5/market/instruments-info (via research/data_fetch/bybitq/inventory.json)",
            "n_linear_btc_eth": n_lin_all,
            "n_usdc_btc_eth": n_usdc_all,
            "n_usdc_quarterly": n_q,
            "quarterly_per_coin": {
                c: [{"symbol": r["symbol"], "status": r["status"],
                     "delivery": str(pd.Timestamp(r["deliveryTime"], unit="ms",
                                                  tz="UTC").date()),
                     "launch": str(pd.Timestamp(r["launchTime"], unit="ms",
                                                tz="UTC").date())} for r in uq[c]]
                for c in COINS},
            "coverage_note": ("USDC dated futures exist only from 2023-03-20 (first launch) — "
                              "nothing for anchor years 2021/2022 entries; the quarterly chain "
                              "is 12 expiries/coin 2023-03-31..2025-12-26, all Closed; "
                              "non-quarterly USDC dated (weeklies/monthlies) are listed in "
                              "inventory.json but EXCLUDED by the quarterly-only rule."),
        },
        "liquidity": liquidity,
        "n_contracts_seen": len(contracts_meta),
        "n_trades": len(trades),
        "n_skipped": sum(1 for c in contracts_meta if c.get("status") == "skipped_basis"),
        "n_incomplete": sum(1 for c in contracts_meta if c.get("status") == "incomplete_no_spot"),
        "years": years,
        "pooled": pooled,
        "overlap_trades": overlap,
        "comparison_years": comparison_years,
        "reference": {
            "binance_usdtm_pooled_sum": oc_res["pooled"]["sum_ret_alloc"],
            "binance_usdtm_pooled_n": oc_res["pooled"]["n_trades"],
            "bybit_inverse_pooled_sum": bb["inverse"]["pooled"]["sum_ret_alloc"],
            "bybit_inverse_pooled_n": bb["inverse"]["pooled"]["n_trades"],
        },
        "trades": [{k: r[k] for k in ("coin", "symbol", "delivery", "entry_open", "ann_basis",
                                      "dte_days", "ret_alloc", "worst_mtm_alloc",
                                      "F_entry", "S_entry", "S_del")} for r in trades],
    }
    (HERE / "results.json").write_text(json.dumps(out, indent=1))

    # MANIFEST with sha256 (script + outputs + key inputs). REPORT.md hashed if present.
    files = [HERE / "fetch_usdccarry.py", HERE / "results.json"]
    if (HERE / "REPORT.md").exists():
        files.append(HERE / "REPORT.md")
    inputs = [BYBITQ / "inventory.json", OC / "results.json",
              BYBITQ / "results_bybit_carry.json"]
    for coin in COINS:
        inputs.append(BDIR / f"spot_{coin}USDT_1h.parquet")
        for r in uq[coin]:
            inputs.append(fut_path(r["symbol"]))
    manifest = [{"path": str(p.relative_to(ROOT)).replace("\\", "/"),
                 "bytes": p.stat().st_size, "sha256": sha256_file(p)}
                for p in files + inputs if p.exists()]
    (HERE / "MANIFEST.json").write_text(json.dumps(
        {"generated_utc": datetime.datetime.now(datetime.timezone.utc).date().isoformat(),
         "venue": "Bybit V5 public market (no keys)",
         "post_hoc": True,
         "files": manifest}, indent=1))
    print(f"usdc_quarterly={n_q} contracts={len(contracts_meta)} trades={len(trades)} "
          f"skipped={out['n_skipped']} incomplete={out['n_incomplete']}")
    for y in years:
        print("  ", y["year"], "n=", y["n_trades"], "skip=", y["n_skipped_in_year"],
              "sum_alloc=", y["sum_ret_alloc"], "worst=", y["worst_mtm_alloc"])
    print("pooled:", json.dumps(pooled))
    print("MANIFEST files:", len(manifest))


if __name__ == "__main__":
    main()
