"""oc_linvinv: same-expiry linear-vs-inverse quarterly RV (long cheap/short rich).

Per PLAN.md (pre-registered, frozen): at each pair-chain roll date
(prev delivery - 7d, round up to next spot 4h open; first pair = first
availability), for each coin where a linear-USDT and an inverse quarterly
with the SAME deliveryTime both trade, if |ann_lin - ann_inv| >= 3pp/yr,
long the cheaper / short the richer in equal USD notional f=0.125/coin,
hold both to delivery. Fees: taker 0.055%/leg entry + 0.02%/leg delivery
(on entry notional). Inverse P&L in coin converted at delivery price
(= linear formula; convexity noted in PLAN/REPORT). 4h data only.

  .venv/Scripts/python.exe research/tournament/oc_linvinv/analyze_linvinv.py

Writes research/tournament/oc_linvinv/results.json.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
BDIR = ROOT / "data" / "raw" / "bybit_quarterly_20261006"

COINS = ["BTC", "ETH"]
ANCHORS = [pd.Timestamp(f"{y}-09-24", tz="UTC") for y in (2021, 2022, 2023, 2024, 2025)]
YEAR_LEN = pd.Timedelta(days=365)
THRESHOLD = 0.03
ROLL_DAYS = 7
F = 0.125
F_TAKER_ENTRY = 0.00055
F_DELIV = 0.0002
FEE_ENTRY_PAID_ALLOC = 2 * F_TAKER_ENTRY  # 0.0011 on allocated
FEE_PAIR_ALLOC = 2 * (F_TAKER_ENTRY + F_DELIV)  # 0.0015 on allocated


def load_1h(path: Path) -> pd.DataFrame:
    d = pd.read_parquet(path, columns=["open_time", "close"])
    t = pd.to_datetime(d["open_time"], unit="ms", utc=True)
    return pd.DataFrame({"t": t, "close": d["close"].to_numpy(dtype=float)}).sort_values(
        "t"
    ).reset_index(drop=True)


def to_4h(h: pd.DataFrame) -> pd.DataFrame:
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
    fo = f4["close_time"].to_numpy(dtype="datetime64[ns]").astype(np.int64)
    fc = f4["close"].to_numpy(dtype=float)
    sc = spot["close_time"].to_numpy(dtype="datetime64[ns]").astype(np.int64)
    idx = np.searchsorted(fo, sc, side="right") - 1
    out = np.full(len(spot), np.nan)
    ok = idx >= 0
    out[ok] = fc[idx[ok]]
    return out


def main() -> None:
    inv = json.loads((HERE.parents[1] / "data_fetch" / "bybitq" / "inventory.json").read_text(encoding="utf-8"))["records"]
    spot4 = {c: to_4h(load_1h(BDIR / f"spot_{c}USDT_1h.parquet")) for c in COINS}

    # same-delivery pairs from inventory deliveryTime equality
    pairs: dict[str, list[tuple[pd.Timestamp, str, str]]] = {}
    for coin in COINS:
        lin = {r["deliveryTime"]: r["symbol"] for r in inv
               if r["baseCoin"] == coin and r["category"] == "linear" and r["settleCoin"] == "USDT"}
        iv = {r["deliveryTime"]: r["symbol"] for r in inv
              if r["baseCoin"] == coin and r["category"] == "inverse"}
        common = sorted(set(lin) & set(iv))
        pairs[coin] = [(pd.Timestamp(t, unit="ms", tz="UTC"), lin[t], iv[t]) for t in common]

    opportunities: list[dict] = []
    trades: list[dict] = []
    for coin in COINS:
        s = spot4[coin]
        s_open = s["open_time"]
        s_close_t = s["close_time"]
        s_close = s["close"].to_numpy(dtype=float)
        exps = pairs[coin]
        # resample both legs once
        Flin_by_D, Finv_by_D = {}, {}
        for D, lsym, isym in exps:
            Flin_by_D[D] = resample_to_spot(
                to_4h(load_1h(BDIR / f"lin_{lsym.replace('-', '_')}_1h.parquet")), s)
            Finv_by_D[D] = resample_to_spot(
                to_4h(load_1h(BDIR / f"inv_{isym}_1h.parquet")), s)
        for k, (D, lsym, isym) in enumerate(exps):
            Fl, Fi = Flin_by_D[D], Finv_by_D[D]
            if k > 0:
                cand = exps[k - 1][0] - pd.Timedelta(days=ROLL_DAYS)
                pos = int(np.searchsorted(
                    s_open.to_numpy(dtype="datetime64[ns]").astype(np.int64),
                    cand.value, side="left"))
            else:
                pos = 0
            both = np.where(~np.isnan(s_close) & ~np.isnan(Fl) & ~np.isnan(Fi))[0]
            both = both[both >= pos]
            if len(both) == 0:
                opportunities.append({"coin": coin, "delivery": str(D.date()),
                                      "status": "no_overlap"})
                continue
            ti = int(both[0])
            T_open, T_close = s_open.iloc[ti], s_close_t.iloc[ti]
            F_lin, F_inv = float(Fl[ti]), float(Fi[ti])
            S_entry = float(s_close[ti])
            dte = (D - T_close).total_seconds() / 86400.0
            if not (np.isfinite(F_lin) and np.isfinite(F_inv) and np.isfinite(S_entry)) or dte <= 0:
                opportunities.append({"coin": coin, "delivery": str(D.date()),
                                      "status": "bad_dte"})
                continue
            b_lin = float(np.log(F_lin / S_entry) * 365.0 / dte)
            b_inv = float(np.log(F_inv / S_entry) * 365.0 / dte)
            diff = abs(b_lin - b_inv)
            si = int(np.searchsorted(
                s_close_t.to_numpy(dtype="datetime64[ns]").astype(np.int64),
                D.value, side="right"))
            if si >= len(s):
                opportunities.append({"coin": coin, "delivery": str(D.date()),
                    "entry": str(T_open.date()), "ann_lin": round(b_lin, 6),
                    "ann_inv": round(b_inv, 6), "diff": round(float(diff), 6),
                    "dte_days": round(float(dte), 2), "status": "incomplete_no_spot"})
                continue
            S_del = float(s_close[si])
            entered = bool(diff >= THRESHOLD)
            base = {"coin": coin, "delivery": str(D.date()),
                    "lin_symbol": lsym, "inv_symbol": isym,
                    "entry_open": str(T_open), "entry_close": str(T_close),
                    "F_lin_entry": F_lin, "F_inv_entry": F_inv,
                    "S_entry": S_entry, "S_del": S_del,
                    "dte_days": round(float(dte), 2),
                    "ann_lin": round(b_lin, 6), "ann_inv": round(b_inv, 6),
                    "abs_diff": round(float(diff), 6),
                    "entered": entered, "ti": ti, "si": si}
            if entered:
                cheap = "lin" if F_lin < F_inv else "inv"
                Fc = F_lin if cheap == "lin" else F_inv
                Fr = F_inv if cheap == "lin" else F_lin
                gross_alloc = S_del * (1.0 / Fc - 1.0 / Fr)
                ret_alloc = float(gross_alloc - FEE_PAIR_ALLOC)
                base["cheap_leg"] = cheap
                base["ret_alloc"] = round(ret_alloc, 6)
                base["gross_alloc"] = round(float(gross_alloc), 6)
                St = slice(ti + 1, si + 1)
                Lc, Lr = (Fl, Fi) if cheap == "lin" else (Fi, Fl)
                Lct, Lrt = Lc[St], Lr[St]
                okm = ~np.isnan(Lct) & ~np.isnan(Lrt)
                if okm.sum() == 0:
                    base["worst_mtm_alloc"] = round(float(-FEE_ENTRY_PAID_ALLOC), 6)
                    base["n_mtm_bars"] = 0
                else:
                    Lct, Lrt = Lct[okm], Lrt[okm]
                    mtm = (Lct / Fc - 1.0) + (1.0 - Lrt / Fr) - FEE_ENTRY_PAID_ALLOC
                    base["worst_mtm_alloc"] = round(float(mtm.min()), 6)
                    base["worst_mtm_date"] = str(
                        s_open.iloc[St][okm].iloc[int(mtm.argmin())])
                    base["n_mtm_bars"] = int(okm.sum())
                trades.append(base)
            opportunities.append({k2: base[k2] for k2 in
                ("coin", "delivery", "ann_lin", "ann_inv", "abs_diff", "dte_days", "entered")}
                | {"status": "entered" if entered else "skipped_threshold",
                   "entry": str(T_open.date())})

    for r in trades:
        r["entry_ts"] = pd.Timestamp(r["entry_open"])
    for o in opportunities:
        if "entry" in o:
            o["entry_ts"] = str(o["entry"])
    years = []
    for a0 in ANCHORS:
        a1 = a0 + YEAR_LEN
        yt = [r for r in trades if a0 <= r["entry_ts"] < a1]
        opps = [o for o in opportunities if "entry_ts" in o
                and a0 <= pd.Timestamp(o["entry_ts"], tz="UTC") < a1]
        per_coin = {}
        for coin in COINS:
            ct = [r for r in yt if r["coin"] == coin]
            co = [o for o in opps if o["coin"] == coin]
            if ct:
                per_coin[coin] = {
                    "n": len(ct),
                    "mean_abs_diff": round(float(np.mean([r["abs_diff"] for r in ct])), 6),
                    "mean_dte": round(float(np.mean([r["dte_days"] for r in ct])), 1),
                    "mean_ret_alloc": round(float(np.mean([r["ret_alloc"] for r in ct])), 6),
                    "sum_ret_alloc": round(float(np.sum([r["ret_alloc"] for r in ct])), 6),
                    "worst_mtm_alloc": round(float(np.min([r["worst_mtm_alloc"] for r in ct])), 6),
                }
            else:
                per_coin[coin] = {"n": 0}
            per_coin[coin]["n_pairs"] = len(co)
        tot = round(float(sum(r["ret_alloc"] for r in yt)), 6)
        worst = round(float(min(r["worst_mtm_alloc"] for r in yt)), 6) if yt else None
        years.append({"year": str(a0.date()), "n_pairs": len(opps),
            "n_trades": len(yt),
            "n_skipped_in_year": sum(1 for o in opps if o["status"] == "skipped_threshold"),
            "per_coin": per_coin, "sum_ret_alloc": tot, "worst_mtm_alloc": worst,
            "contrib_acct_pct": round(float(F * tot * 100), 4),
            "worst_acct_pct": (round(float(F * worst * 100), 4) if worst is not None else None),
            "trades": [(r["coin"], r["delivery"], r["cheap_leg"], r["abs_diff"],
                        r["ret_alloc"], r["worst_mtm_alloc"]) for r in yt]})

    pooled_sum = round(float(sum(r["ret_alloc"] for r in trades)), 6)
    entry_years = [y for y in years if y["n_trades"] > 0]
    verdict_useful = (len(trades) >= 3
                      and len(entry_years) > 0
                      and all(y["sum_ret_alloc"] > 0 for y in entry_years))
    out = {
        "meta": {
            "rule": "same-delivery lin-vs-inv quarterly RV: |ann_lin-ann_inv|>=0.03, long cheap/short rich f=0.125/coin, hold to shared delivery",
            "pairs": "8 same-deliveryTime pairs/coin (linear USDT quarterly since 2025 x inverse H/M/U/Z); deliveries fixed by inventory.json deliveryTime",
            "spot": "Bybit spot hourly -> 4h grid 00/04/.. UTC (all-4-hours-present else NaN)",
            "futures_4h": "Bybit hourly -> same 4h grid; F(t)=last fut 4h close with close_time<=spot close_time",
            "settlement": "Bybit spot 4h close of delivery bar; beyond last spot bar = incomplete (excluded)",
            "fees": {"taker_entry_per_leg": F_TAKER_ENTRY, "delivery_per_leg": F_DELIV,
                     "pair_drag_alloc": FEE_PAIR_ALLOC, "entry_paid_alloc": FEE_ENTRY_PAID_ALLOC,
                     "note": "both on entry notional (approximation)"},
            "f_per_coin": F,
            "ret_alloc_def": "P&L/f (each leg notional f; follows oc_cashcarry convention)",
            "inverse_note": "inverse P&L in coin x delivery price = N*(S_del/F_entry-1), same as linear; 1/F convexity only in coin path",
            "threshold": THRESHOLD, "roll_days": ROLL_DAYS,
            "spot_last": str(spot4["BTC"]["open_time"].max()),
        },
        "n_pairs_seen": len(opportunities),
        "n_trades": len(trades),
        "n_skipped": sum(1 for o in opportunities if o.get("status") == "skipped_threshold"),
        "n_incomplete": sum(1 for o in opportunities if o.get("status") == "incomplete_no_spot"),
        "years": years,
        "pooled": {"n_trades": len(trades), "sum_ret_alloc": pooled_sum,
                   "contrib_acct_pct": round(float(F * pooled_sum * 100), 4)},
        "verdict": ("USEFUL" if verdict_useful else "NOT_USEFUL_DATA_TOO_SHORT_CLOSE"),
        "verdict_rule": "USEFUL only if net>0 on every entry year with >=3 entries total",
        "trades": [{k: r[k] for k in ("coin", "delivery", "lin_symbol", "inv_symbol",
            "entry_open", "cheap_leg", "ann_lin", "ann_inv", "abs_diff", "dte_days",
            "ret_alloc", "worst_mtm_alloc", "F_lin_entry", "F_inv_entry",
            "S_entry", "S_del")} for r in trades],
        "opportunities": [{k: o[k] for k in o if k != "entry_ts"} for o in opportunities],
    }
    (HERE / "results.json").write_text(json.dumps(out, indent=1))
    print(f"pairs={len(opportunities)} trades={len(trades)} "
          f"skipped={out['n_skipped']} incomplete={out['n_incomplete']} verdict={out['verdict']}")
    for y in years:
        print(y["year"], "pairs=", y["n_pairs"], "n=", y["n_trades"],
              "skip=", y["n_skipped_in_year"], "sum_alloc=", y["sum_ret_alloc"],
              "worst=", y["worst_mtm_alloc"])
    print("pooled:", json.dumps(out["pooled"]))


if __name__ == "__main__":
    main()
