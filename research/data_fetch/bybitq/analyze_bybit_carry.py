"""Recompute the oc_cashcarry rule (UNCHANGED) on Bybit data.

Rule frozen in research/tournament/oc_cashcarry/PLAN.md: one entry per
quarterly contract (next contract when front has <= 7d left, else first
availability), ENTER iff annualised basis ln(F/S)*365/DTE >= 4 %/yr, long
spot + short dated future in equal notional, hold to delivery, settlement =
spot 4h close of the delivery bar. Fees: spot 0.001/side, futures 0.00055
entry + 0.0002 delivery (drag 0.00275 of allocated). f rows 0.25 / 0.50.

Bybit input: hourly klines under data/raw/bybit_quarterly_20261006/
resampled to 4h on the 00/04/08/12/16/20 UTC grid (close = last hourly
close with hour-open < 4h close_time, strictly causal; a 4h bar is NaN
unless all 4 hours are present). Delivery timestamps are exact ms from
inventory.json (Bybit deliveryTime), not parsed codes.

Series run (same code path, different F leg):
  inverse     BTCUSD*/ETHUSD* quarterly H/M/U/Z chain (Bybit-native,
              coin-margined; prices in USD, same scale as USDT spot, so the
              ln(F/S) basis and price-return P&L formula apply unchanged —
              coin-settlement convexity is noted, not modelled).
  usdt_linear BTCUSDT-*/ETHUSDT-* dated (weekly + a few quarterlies; only
              exists from 2025-02-18, so it can only cover anchor year 2025).
USDC weeklies (BTC-*/ETH-*, 2023-03..2025-03) are listed in inventory only:
weekly cadence + USDC settle != the quarterly rule; no recompute.

  .venv/Scripts/python.exe research/data_fetch/bybitq/analyze_bybit_carry.py

Writes research/data_fetch/bybitq/results_bybit_carry.json (inputs to REPORT.md).
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
BDIR = ROOT / "data" / "raw" / "bybit_quarterly_20261006"
OC = ROOT / "research" / "tournament" / "oc_cashcarry"

COINS = ["BTC", "ETH"]
ANCHORS = [pd.Timestamp(f"{y}-09-24", tz="UTC") for y in (2021, 2022, 2023, 2024, 2025)]
YEAR_LEN = pd.Timedelta(days=365)
THRESHOLD = 0.04
ROLL_DAYS = 7
F_SPOT = 0.001
F_FUT_ENTRY = 0.00055
F_FUT_DELIV = 0.0002
FEE_PAIR = 2 * F_SPOT + F_FUT_ENTRY + F_FUT_DELIV
FEE_ENTRY_PAID = F_SPOT + F_FUT_ENTRY
F_ROWS = [0.25, 0.5]


def load_1h(path: Path) -> pd.DataFrame:
    d = pd.read_parquet(path, columns=["open_time", "close"])
    t = pd.to_datetime(d["open_time"], unit="ms", utc=True)
    return pd.DataFrame({"t": t, "close": d["close"].to_numpy(dtype=float)}).sort_values(
        "t"
    ).reset_index(drop=True)


def to_4h(h: pd.DataFrame) -> pd.DataFrame:
    """4h bars on 00/04/... UTC grid; close = hourly close of hour 4k+3.

    A 4h bar is valid only if all 4 hours are present (else NaN, same as a
    missing resampled quarterly bar in analyze_cashcarry.py).
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


def run_series(coin_spot4: dict, fut_files: dict, label: str) -> dict:
    """coin_spot4: coin -> spot 4h DataFrame. fut_files: coin -> [(D, path)]."""
    trades: list[dict] = []
    contracts_meta: list[dict] = []
    for coin in COINS:
        s = coin_spot4[coin]
        s_open = s["open_time"]
        s_close_t = s["close_time"]
        s_close = s["close"].to_numpy(dtype=float)
        exps = sorted(fut_files[coin])
        F_by_D = {}
        for D, path in exps:
            f4 = to_4h(load_1h(path))
            F_by_D[D] = resample_to_spot(f4, s)
        for k, (D, _path) in enumerate(exps):
            F = F_by_D[D]
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
                    {"coin": coin, "delivery": str(D.date()), "status": "no_overlap"}
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
                    {"coin": coin, "delivery": str(D.date()), "status": "bad_dte"}
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
                    {
                        "coin": coin,
                        "delivery": str(D.date()),
                        "entry": str(T_open.date()),
                        "ann_basis": round(basis, 6),
                        "dte_days": round(dte_days, 2),
                        "status": "incomplete_no_spot",
                    }
                )
                continue
            S_del = float(s_close[si])
            D_bar = str(s_open.iloc[si].date())
            entered = bool(basis >= THRESHOLD)
            rec: dict = {
                "coin": coin,
                "delivery": str(D.date()),
                "entry_open": str(T_open),
                "entry_close": str(T_close),
                "F_entry": F_entry,
                "S_entry": S_entry,
                "S_del": S_del,
                "deliver_bar": D_bar,
                "dte_days": round(dte_days, 2),
                "ann_basis": round(basis, 6),
                "entered": entered,
                "ti": ti,
                "si": si,
            }
            if entered:
                gross = (S_del - S_entry) / S_entry + (F_entry - S_del) / F_entry
                ret_alloc = float(gross - FEE_PAIR)
                rec["ret_alloc"] = round(ret_alloc, 6)
                rec["gross_locked"] = round(float(gross), 6)
                St = s_close[ti + 1 : si + 1]
                Ft = F[ti + 1 : si + 1]
                okm = ~np.isnan(St) & ~np.isnan(Ft)
                if okm.sum() == 0:
                    rec["worst_mtm_alloc"] = round(float(-FEE_ENTRY_PAID), 6)
                    rec["n_mtm_bars"] = 0
                else:
                    St, Ft = St[okm], Ft[okm]
                    mtm = (St / S_entry - 1.0) + ((F_entry - Ft) / F_entry) - FEE_ENTRY_PAID
                    rec["worst_mtm_alloc"] = round(float(mtm.min()), 6)
                    rec["worst_mtm_date"] = str(
                        s_open.iloc[ti + 1 : si + 1][okm].iloc[int(mtm.argmin())]
                    )
                    rec["n_mtm_bars"] = int(okm.sum())
                trades.append(rec)
            contracts_meta.append(
                {
                    k2: rec[k2]
                    for k2 in ("coin", "delivery", "ann_basis", "dte_days", "entered")
                }
                | {
                    "status": "entered" if entered else "skipped_basis",
                    "entry": str(T_open.date()),
                }
            )
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
        contrib = {
            str(f): {
                "year_pct": round(float(f * tot_sum * 100), 4),
                "per_month_pct": round(float(f * tot_sum * 100 / 12), 4),
            }
            for f in F_ROWS
        }
        acct_worst = {
            str(f): (round(float(f * worst * 100), 4) if worst is not None else None)
            for f in F_ROWS
        }
        years.append(
            {
                "year": str(a0.date()),
                "n_trades": len(yt),
                "n_skipped_in_year": None,
                "per_coin": per_coin,
                "sum_ret_alloc": tot_sum,
                "worst_mtm_alloc": worst,
                "contrib_acct_pct": contrib,
                "worst_acct_pct": acct_worst,
                "trades": [
                    (r["coin"], r["delivery"], r["ann_basis"], r["ret_alloc"], r["worst_mtm_alloc"])
                    for r in yt
                ],
            }
        )
    for y in years:
        a0 = pd.Timestamp(y["year"], tz="UTC")
        a1 = a0 + YEAR_LEN
        sk = [
            c
            for c in contracts_meta
            if c.get("status") == "skipped_basis"
            and a0 <= pd.Timestamp(c["entry"], tz="UTC") < a1
        ]
        y["n_skipped_in_year"] = len(sk)
    in_window = [r for r in trades if ANCHORS[0] <= r["entry_ts"] < ANCHORS[-1] + YEAR_LEN]
    pre_window = [r for r in trades if r["entry_ts"] < ANCHORS[0]]
    pooled_sum = float(sum(r["ret_alloc"] for r in in_window))
    pooled = {
        "n_trades": len(in_window),
        "sum_ret_alloc": round(pooled_sum, 6),
        "n_pre_window_trades_excluded": len(pre_window),
        "pre_window_sum_ret_alloc_excluded": round(
            float(sum(r["ret_alloc"] for r in pre_window)), 6
        ),
        "per_f": {
            str(f): {
                "total_acct_pct": round(float(f * pooled_sum * 100), 4),
                "per_month_pct": round(float(f * pooled_sum * 100 / 60), 4),
            }
            for f in F_ROWS
        },
    }
    for f in F_ROWS:
        fac = 1.0
        for y in years:
            fac *= 1.0 + f * y["sum_ret_alloc"]
        pooled["per_f"][str(f)]["geom_per_month_pct"] = round(float((fac ** (1 / 60) - 1) * 100), 4)
    return {
        "label": label,
        "n_contracts_seen": len(contracts_meta),
        "n_trades": len(trades),
        "n_skipped": sum(1 for c in contracts_meta if c.get("status") == "skipped_basis"),
        "n_incomplete": sum(
            1 for c in contracts_meta if c.get("status") == "incomplete_no_spot"
        ),
        "years": years,
        "pooled": pooled,
        "trades": [
            {k: r[k] for k in ("coin", "delivery", "entry_open", "ann_basis", "dte_days",
                               "ret_alloc", "worst_mtm_alloc", "F_entry", "S_entry", "S_del")}
            for r in trades
        ],
    }


def main() -> None:
    inv = json.loads((HERE / "inventory.json").read_text(encoding="utf-8"))["records"]
    spot4 = {c: to_4h(load_1h(BDIR / f"spot_{c}USDT_1h.parquet")) for c in COINS}
    print({c: (len(spot4[c]), str(spot4[c]["open_time"].min()), str(spot4[c]["open_time"].max())) for c in COINS})

    def series_files(prefix: str, usdt: bool | None) -> dict:
        out: dict = {}
        for coin in COINS:
            lst = []
            for r in inv:
                if r["baseCoin"] != coin:
                    continue
                is_inv = r["category"] == "inverse"
                if prefix == "inv" and not is_inv:
                    continue
                if prefix == "lin":
                    if is_inv:
                        continue
                    if (r["settleCoin"] == "USDT") != usdt:
                        continue
                D = pd.Timestamp(r["deliveryTime"], unit="ms", tz="UTC")
                safe = r["symbol"].replace("-", "_")
                px = "inv" if r["category"] == "inverse" else "lin"
                lst.append((D, BDIR / f"{px}_{safe}_1h.parquet"))
            lst.sort()
            out[coin] = lst
        return out

    res_inv = run_series(spot4, series_files("inv", None), "inverse_quarterly")
    res_lin = run_series(spot4, series_files("lin", True), "usdt_linear_dated")

    oc_res = json.loads((OC / "results.json").read_text(encoding="utf-8"))
    comparison = []
    for i, a in enumerate(ANCHORS):
        b = next(y for y in oc_res["years"] if y["year"] == str(a.date()))
        comparison.append(
            {
                "year": str(a.date()),
                "binance_sum_ret_alloc": b["sum_ret_alloc"],
                "binance_n": b["n_trades"],
                "bybit_inv_sum_ret_alloc": res_inv["years"][i]["sum_ret_alloc"],
                "bybit_inv_n": res_inv["years"][i]["n_trades"],
                "bybit_lin_sum_ret_alloc": res_lin["years"][i]["sum_ret_alloc"],
                "bybit_lin_n": res_lin["years"][i]["n_trades"],
            }
        )

    # coverage gaps (from inventory, no kline stats needed)
    def span(rows):
        import datetime

        return {
            "n": len(rows),
            "first_launch": str(datetime.datetime.fromtimestamp(min(r["launchTime"] for r in rows) / 1000, datetime.timezone.utc).date()),
            "last_delivery": str(datetime.datetime.fromtimestamp(max(r["deliveryTime"] for r in rows) / 1000, datetime.timezone.utc).date()),
        }

    gaps = {}
    for coin in COINS:
        lin_u = sorted([r for r in inv if r["baseCoin"] == coin and r["category"] == "linear" and r["settleCoin"] == "USDT"], key=lambda r: r["deliveryTime"])
        lin_c = sorted([r for r in inv if r["baseCoin"] == coin and r["category"] == "linear" and r["settleCoin"] == "USDC"], key=lambda r: r["deliveryTime"])
        iv = sorted([r for r in inv if r["baseCoin"] == coin and r["category"] == "inverse"], key=lambda r: r["deliveryTime"])
        gaps[coin] = {
            "linear_usdt": span(lin_u),
            "linear_usdc_weekly": span(lin_c),
            "inverse_quarterly": span(iv),
        }

    out = {
        "meta": {
            "rule": "oc_cashcarry PLAN.md unchanged (7d roll, 4 pct threshold, hold to delivery, fees 0.001/0.001/0.00055/0.0002)",
            "spot": "Bybit spot BTCUSDT/ETHUSDT hourly -> 4h grid 00/04/.. UTC",
            "futures_4h": "Bybit hourly -> same 4h grid; F(t) = last fut 4h close with close_time <= spot close_time",
            "settlement": "Bybit spot 4h close of delivery bar (delivery = instruments-info deliveryTime)",
            "inverse_note": "coin-margined InverseFutures prices in USD; ln(F/S) basis + price-return P&L used unchanged (coin-settlement convexity not modelled)",
        },
        "spot_4h": {c: {"bars": len(spot4[c]), "first": str(spot4[c]["open_time"].min()), "last": str(spot4[c]["open_time"].max())} for c in COINS},
        "inverse": res_inv,
        "usdt_linear": res_lin,
        "comparison_vs_binance": comparison,
        "coverage_gaps": gaps,
    }
    (HERE / "results_bybit_carry.json").write_text(json.dumps(out, indent=1))
    for tag, r in (("INV", res_inv), ("LIN", res_lin)):
        print(f"== {tag}: contracts={r['n_contracts_seen']} trades={r['n_trades']} skipped={r['n_skipped']} incomplete={r['n_incomplete']}")
        for y in r["years"]:
            print("  ", y["year"], "n=", y["n_trades"], "skip=", y["n_skipped_in_year"], "sum_alloc=", y["sum_ret_alloc"], "worst=", y["worst_mtm_alloc"])
        print("   pooled:", json.dumps(r["pooled"]))
    print("comparison:", json.dumps(comparison, indent=1))


if __name__ == "__main__":
    main()
