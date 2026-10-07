"""oc_calendar: near-vs-far quarterly roll-down spread (long near / short far).

Per PLAN.md (pre-registered, frozen): at each oc_cashcarry roll date, per
coin, if ann_far - ann_near >= 0.02 (2 pp/yr), long near + short far in
equal USD notional (f = 0.125 per coin per pair), hold to the near delivery;
near leg settles via delivery, far leg closed at market (taker) in the same
hour (same delivery bar). Fees: taker 0.00055 per leg per side, delivery
0.0002 -> drag 0.00185 per allocated unit. No funding.

Two series, same rule:
  binance  um_BTCUSDT_*/um_ETHUSDT_* quarterly delivery (data.binance.vision)
           + Binance spot 4h; delivery 08:00 UTC on code date.
  bybit    inv_BTCUSD*/inv_ETHUSD* quarterly H/M/U/Z chain
           + Bybit spot hourly -> 4h grid; delivery = inventory deliveryTime.
4h/hourly data only, one process, RAM << 2 GB.

  python research/tournament/oc_calendar/analyze_calendar.py
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
QDIR = ROOT / "data/raw/qbasis_20261003"
SDIR = ROOT / "data/raw/spot_majors_20260925"
BDIR = ROOT / "data/raw/bybit_quarterly_20261006"
OC = ROOT / "research/tournament/oc_cashcarry"
BYBITQ = ROOT / "research/data_fetch/bybitq"

COINS = ["BTC", "ETH"]
ANCHORS = [pd.Timestamp(f"{y}-09-24", tz="UTC") for y in (2021, 2022, 2023, 2024, 2025)]
YEAR_LEN = pd.Timedelta(days=365)
SPREAD_THRESHOLD = 0.02
ROLL_DAYS = 7
F_TAKER = 0.00055
F_DELIV = 0.0002
FEE_PAIR = 3 * F_TAKER + F_DELIV  # 0.00185 per allocated unit
FEE_ENTRY_PAID = 2 * F_TAKER  # for MtM (exit fees not yet paid)
F_ALLOC = 0.125


def parse_expiry_binance(fname: str) -> pd.Timestamp:
    m = re.search(r"_(\d{6})_1h\.parquet$", fname)
    assert m, fname
    s = m.group(1)
    return pd.Timestamp(f"20{s[:2]}-{s[2:4]}-{s[4:6]} 08:00", tz="UTC")


def load_spot_binance(coin: str) -> pd.DataFrame:
    p = SDIR / f"{coin}USDT_spot_4h.parquet"
    d = pd.read_parquet(p, columns=["open_time", "close", "close_time"])
    d["open_time"] = pd.to_datetime(d["open_time"], utc=True)
    d["close_time"] = pd.to_datetime(d["close_time"], utc=True)
    return d.sort_values("open_time").reset_index(drop=True)


def load_q_1h_binance(coin: str) -> dict:
    out = {}
    for f in sorted(QDIR.glob(f"um_{coin}USDT_*_1h.parquet")):
        d = pd.read_parquet(f, columns=["open_time", "close"])
        d["open_time"] = pd.to_datetime(d["open_time"], utc=True)
        out[parse_expiry_binance(f.name)] = d.sort_values("open_time").reset_index(drop=True)
    return out


def resample_binance_to_spot(q: pd.DataFrame, spot: pd.DataFrame) -> np.ndarray:
    """Last 1h close with 1h open_time < spot close_time (causal, oc_cashcarry)."""
    qo = q["open_time"].to_numpy(dtype="datetime64[ns]").astype(np.int64)
    qc = q["close"].to_numpy(dtype=float)
    sc = spot["close_time"].to_numpy(dtype="datetime64[ns]").astype(np.int64)
    idx = np.searchsorted(qo, sc, side="left") - 1
    out = np.full(len(spot), np.nan)
    ok = idx >= 0
    out[ok] = qc[idx[ok]]
    return out


def load_1h_bybit(path: Path) -> pd.DataFrame:
    d = pd.read_parquet(path, columns=["open_time", "close"])
    t = pd.to_datetime(d["open_time"], unit="ms", utc=True)
    return pd.DataFrame({"t": t, "close": d["close"].to_numpy(dtype=float)}).sort_values(
        "t"
    ).reset_index(drop=True)


def to_4h(h: pd.DataFrame) -> pd.DataFrame:
    """4h bars on 00/04/... UTC grid; valid only if all 4 hours present."""
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


def resample_bybit_to_spot(f4: pd.DataFrame, spot: pd.DataFrame) -> np.ndarray:
    """Last futures 4h close with fut close_time <= spot close_time (causal)."""
    fo = f4["close_time"].to_numpy(dtype="datetime64[ns]").astype(np.int64)
    fc = f4["close"].to_numpy(dtype=float)
    sc = spot["close_time"].to_numpy(dtype="datetime64[ns]").astype(np.int64)
    idx = np.searchsorted(fo, sc, side="right") - 1
    out = np.full(len(spot), np.nan)
    ok = idx >= 0
    out[ok] = fc[idx[ok]]
    return out


def run_binance() -> dict:
    spot = {c: load_spot_binance(c) for c in COINS}
    assert (spot["BTC"]["open_time"].to_numpy() == spot["ETH"]["open_time"].to_numpy()).all()
    trades: list[dict] = []
    pairs_meta: list[dict] = []
    for coin in COINS:
        s = spot[coin]
        s_open = s["open_time"]
        s_close_t = s["close_time"]
        s_close = s["close"].to_numpy(dtype=float)
        qmap = load_q_1h_binance(coin)
        expiries = sorted(qmap)
        F_by_D = {D: resample_binance_to_spot(qmap[D], s) for D in expiries}
        for k in range(len(expiries) - 1):
            D_near, D_far = expiries[k], expiries[k + 1]
            if k > 0:
                cand = expiries[k - 1] - pd.Timedelta(days=ROLL_DAYS)
                pos = int(np.searchsorted(
                    s_open.to_numpy(dtype="datetime64[ns]").astype(np.int64),
                    cand.value, side="left"))
            else:
                pos = 0
            Fn, Ff = F_by_D[D_near], F_by_D[D_far]
            # T_k = oc_cashcarry roll bar for the NEAR contract (near+spot only)
            both_near = np.where(~np.isnan(s_close) & ~np.isnan(Fn))[0]
            both_near = both_near[both_near >= pos]
            tag = {"coin": coin, "near": str(D_near.date()), "far": str(D_far.date())}
            if len(both_near) == 0:
                pairs_meta.append(tag | {"status": "no_pair"})
                continue
            ti = int(both_near[0])
            T_open = s_open.iloc[ti]
            T_close = s_close_t.iloc[ti]
            N_entry = float(Fn[ti])
            S_entry = float(s_close[ti])
            dte_n = (D_near - T_close).total_seconds() / 86400.0
            if not (np.isfinite(N_entry) and np.isfinite(S_entry)) or dte_n <= 0:
                pairs_meta.append(tag | {"status": "bad_dte"})
                continue
            ann_n = float(np.log(N_entry / S_entry) * 365.0 / dte_n)
            F_entry = float(Ff[ti])
            if not np.isfinite(F_entry):
                pairs_meta.append(tag | {"entry": str(T_open.date()),
                                         "ann_near": round(ann_n, 6),
                                         "dte_near": round(dte_n, 2),
                                         "status": "no_far_at_roll"})
                continue
            dte_f = (D_far - T_close).total_seconds() / 86400.0
            if dte_f <= 0:
                pairs_meta.append(tag | {"status": "bad_dte"})
                continue
            ann_f = float(np.log(F_entry / S_entry) * 365.0 / dte_f)
            spread = float(ann_f - ann_n)
            si = int(np.searchsorted(
                s_close_t.to_numpy(dtype="datetime64[ns]").astype(np.int64),
                D_near.value, side="right"))
            if si >= len(s):
                pairs_meta.append(tag | {"entry": str(T_open.date()),
                                         "ann_near": round(ann_n, 6),
                                         "ann_far": round(ann_f, 6),
                                         "spread": round(spread, 6),
                                         "status": "incomplete_no_spot"})
                continue
            S_del = float(s_close[si])
            F_far_del = float(Ff[si])
            if not (np.isfinite(S_del) and np.isfinite(F_far_del)):
                pairs_meta.append(tag | {"entry": str(T_open.date()),
                                         "ann_near": round(ann_n, 6),
                                         "ann_far": round(ann_f, 6),
                                         "spread": round(spread, 6),
                                         "status": "incomplete_no_far_exit"})
                continue
            entered = bool(spread >= SPREAD_THRESHOLD)
            rec: dict = {"coin": coin, "near": str(D_near.date()), "far": str(D_far.date()),
                         "entry_open": str(T_open), "entry_close": str(T_close),
                         "N_entry": N_entry, "F_entry": F_entry, "S_entry": S_entry,
                         "S_del": S_del, "F_far_del": F_far_del,
                         "dte_near": round(dte_n, 2), "dte_far": round(dte_f, 2),
                         "ann_near": round(ann_n, 6), "ann_far": round(ann_f, 6),
                         "spread": round(spread, 6), "entered": entered,
                         "ti": ti, "si": si}
            if entered:
                gross = (S_del - N_entry) / N_entry + (F_entry - F_far_del) / F_entry
                rec["ret_alloc"] = round(float(gross - FEE_PAIR), 6)
                rec["gross"] = round(float(gross), 6)
                Nt = Fn[ti + 1: si + 1]
                Ft = Ff[ti + 1: si + 1]
                St = s_close[ti + 1: si + 1]
                okm = ~np.isnan(Nt) & ~np.isnan(Ft) & ~np.isnan(St)
                if okm.sum() == 0:
                    rec["worst_mtm_alloc"] = round(float(-FEE_ENTRY_PAID), 6)
                    rec["n_mtm_bars"] = 0
                else:
                    mtm = (Nt[okm] / N_entry - 1.0) + ((F_entry - Ft[okm]) / F_entry) \
                        - FEE_ENTRY_PAID
                    rec["worst_mtm_alloc"] = round(float(mtm.min()), 6)
                    rec["worst_mtm_date"] = str(
                        s_open.iloc[ti + 1: si + 1][okm].iloc[int(mtm.argmin())])
                    rec["n_mtm_bars"] = int(okm.sum())
                trades.append(rec)
            pairs_meta.append(tag | {"entry": str(T_open.date()),
                                     "ann_near": rec["ann_near"], "ann_far": rec["ann_far"],
                                     "spread": rec["spread"],
                                     "status": "entered" if entered else "skipped_spread"})
    return {"trades": trades, "pairs_meta": pairs_meta, "spot": spot}


def run_bybit() -> dict:
    inv = json.loads((BYBITQ / "inventory.json").read_text(encoding="utf-8"))["records"]
    spot4 = {c: to_4h(load_1h_bybit(BDIR / f"spot_{c}USDT_1h.parquet")) for c in COINS}
    fut_files: dict = {}
    for coin in COINS:
        lst = []
        for r in inv:
            if r["baseCoin"] != coin or r["category"] != "inverse":
                continue
            D = pd.Timestamp(r["deliveryTime"], unit="ms", tz="UTC")
            path = BDIR / f"inv_{r['symbol']}_1h.parquet"
            if not path.exists():
                continue
            lst.append((D, path, r["symbol"]))
        lst.sort()
        fut_files[coin] = lst
    trades: list[dict] = []
    pairs_meta: list[dict] = []
    F_cache: dict = {}
    for coin in COINS:
        s = spot4[coin]
        s_open = s["open_time"]
        s_close_t = s["close_time"]
        s_close = s["close"].to_numpy(dtype=float)
        exps = fut_files[coin]
        F_by_D = {}
        for D, path, _sym in exps:
            F_by_D[D] = resample_bybit_to_spot(to_4h(load_1h_bybit(path)), s)
        F_cache[coin] = F_by_D
        for k in range(len(exps) - 1):
            D_near = exps[k][0]
            D_far = exps[k + 1][0]
            sym_n, sym_f = exps[k][2], exps[k + 1][2]
            if k > 0:
                cand = exps[k - 1][0] - pd.Timedelta(days=ROLL_DAYS)
                pos = int(np.searchsorted(
                    s_open.to_numpy(dtype="datetime64[ns]").astype(np.int64),
                    cand.value, side="left"))
            else:
                pos = 0
            Fn, Ff = F_by_D[D_near], F_by_D[D_far]
            # T_k = oc_cashcarry roll bar for the NEAR contract (near+spot only)
            both_near = np.where(~np.isnan(s_close) & ~np.isnan(Fn))[0]
            both_near = both_near[both_near >= pos]
            tag = {"coin": coin, "near": str(D_near.date()), "far": str(D_far.date()),
                   "near_sym": sym_n, "far_sym": sym_f}
            if len(both_near) == 0:
                pairs_meta.append(tag | {"status": "no_pair"})
                continue
            ti = int(both_near[0])
            T_open = s_open.iloc[ti]
            T_close = s_close_t.iloc[ti]
            N_entry = float(Fn[ti])
            S_entry = float(s_close[ti])
            dte_n = (D_near - T_close).total_seconds() / 86400.0
            if not (np.isfinite(N_entry) and np.isfinite(S_entry)) or dte_n <= 0:
                pairs_meta.append(tag | {"status": "bad_dte"})
                continue
            ann_n = float(np.log(N_entry / S_entry) * 365.0 / dte_n)
            F_entry = float(Ff[ti])
            if not np.isfinite(F_entry):
                pairs_meta.append(tag | {"entry": str(T_open.date()),
                                         "ann_near": round(ann_n, 6),
                                         "dte_near": round(dte_n, 2),
                                         "status": "no_far_at_roll"})
                continue
            dte_f = (D_far - T_close).total_seconds() / 86400.0
            if dte_f <= 0:
                pairs_meta.append(tag | {"status": "bad_dte"})
                continue
            ann_f = float(np.log(F_entry / S_entry) * 365.0 / dte_f)
            spread = float(ann_f - ann_n)
            si = int(np.searchsorted(
                s_close_t.to_numpy(dtype="datetime64[ns]").astype(np.int64),
                D_near.value, side="right"))
            if si >= len(s):
                pairs_meta.append(tag | {"entry": str(T_open.date()),
                                         "ann_near": round(ann_n, 6),
                                         "ann_far": round(ann_f, 6),
                                         "spread": round(spread, 6),
                                         "status": "incomplete_no_spot"})
                continue
            S_del = float(s_close[si])
            F_far_del = float(Ff[si])
            if not (np.isfinite(S_del) and np.isfinite(F_far_del)):
                pairs_meta.append(tag | {"entry": str(T_open.date()),
                                         "ann_near": round(ann_n, 6),
                                         "ann_far": round(ann_f, 6),
                                         "spread": round(spread, 6),
                                         "status": "incomplete_no_far_exit"})
                continue
            entered = bool(spread >= SPREAD_THRESHOLD)
            rec: dict = {"coin": coin, "near": str(D_near.date()), "far": str(D_far.date()),
                         "near_sym": sym_n, "far_sym": sym_f,
                         "entry_open": str(T_open), "entry_close": str(T_close),
                         "N_entry": N_entry, "F_entry": F_entry, "S_entry": S_entry,
                         "S_del": S_del, "F_far_del": F_far_del,
                         "dte_near": round(dte_n, 2), "dte_far": round(dte_f, 2),
                         "ann_near": round(ann_n, 6), "ann_far": round(ann_f, 6),
                         "spread": round(spread, 6), "entered": entered,
                         "ti": ti, "si": si}
            if entered:
                gross = (S_del - N_entry) / N_entry + (F_entry - F_far_del) / F_entry
                rec["ret_alloc"] = round(float(gross - FEE_PAIR), 6)
                rec["gross"] = round(float(gross), 6)
                Nt = Fn[ti + 1: si + 1]
                Ft = Ff[ti + 1: si + 1]
                St = s_close[ti + 1: si + 1]
                okm = ~np.isnan(Nt) & ~np.isnan(Ft) & ~np.isnan(St)
                if okm.sum() == 0:
                    rec["worst_mtm_alloc"] = round(float(-FEE_ENTRY_PAID), 6)
                    rec["n_mtm_bars"] = 0
                else:
                    mtm = (Nt[okm] / N_entry - 1.0) + ((F_entry - Ft[okm]) / F_entry) \
                        - FEE_ENTRY_PAID
                    rec["worst_mtm_alloc"] = round(float(mtm.min()), 6)
                    rec["worst_mtm_date"] = str(
                        s_open.iloc[ti + 1: si + 1][okm].iloc[int(mtm.argmin())])
                    rec["n_mtm_bars"] = int(okm.sum())
                trades.append(rec)
            pairs_meta.append(tag | {"entry": str(T_open.date()),
                                     "ann_near": rec["ann_near"], "ann_far": rec["ann_far"],
                                     "spread": rec["spread"],
                                     "status": "entered" if entered else "skipped_spread"})
    return {"trades": trades, "pairs_meta": pairs_meta, "spot4": spot4}


def summarize(trades: list[dict], pairs_meta: list[dict],
              base_trades: list[dict], base_years: list[dict], venue: str) -> dict:
    for r in trades:
        r["entry_ts"] = pd.Timestamp(r["entry_open"])
    years = []
    for a0 in ANCHORS:
        a1 = a0 + YEAR_LEN
        yt = [r for r in trades if a0 <= r["entry_ts"] < a1]
        considered = [c for c in pairs_meta
                      if c.get("entry") is not None
                      and a0 <= pd.Timestamp(c["entry"], tz="UTC") < a1
                      and c.get("status") in ("entered", "skipped_spread")]
        per_coin: dict = {}
        for coin in COINS:
            ct = [r for r in yt if r["coin"] == coin]
            cc = [c for c in considered if c["coin"] == coin]
            if ct:
                per_coin[coin] = {
                    "n": len(ct),
                    "n_considered": len(cc),
                    "mean_spread": round(float(np.mean([r["spread"] for r in ct])), 6),
                    "mean_dte_near": round(float(np.mean([r["dte_near"] for r in ct])), 1),
                    "mean_ret_alloc": round(float(np.mean([r["ret_alloc"] for r in ct])), 6),
                    "sum_ret_alloc": round(float(np.sum([r["ret_alloc"] for r in ct])), 6),
                    "worst_mtm_alloc": round(float(np.min([r["worst_mtm_alloc"] for r in ct])), 6),
                }
            else:
                per_coin[coin] = {"n": 0,
                                  "n_considered": len(cc)}
        tot_sum = round(float(sum(r["ret_alloc"] for r in yt)), 6)
        worst = round(float(min([r["worst_mtm_alloc"] for r in yt])), 6) if yt else None
        n_skip = sum(1 for c in considered if c.get("status") == "skipped_spread")
        spr = [c["spread"] for c in considered if c.get("spread") is not None]
        max_spr = round(float(max(spr)), 6) if spr else None
        years.append({"year": str(a0.date()), "n_trades": len(yt),
                      "n_considered": len(considered), "n_skipped_spread": n_skip,
                      "max_spread_considered": max_spr,
                      "per_coin": per_coin, "sum_ret_alloc": tot_sum,
                      "worst_mtm_alloc": worst,
                      "contrib_acct_pct": {
                          "year_pct": round(float(F_ALLOC * tot_sum * 100), 4),
                          "per_month_pct": round(float(F_ALLOC * tot_sum * 100 / 12), 4)},
                      "worst_acct_pct": (round(float(F_ALLOC * worst * 100), 4)
                                         if worst is not None else None),
                      "trades": [(r["coin"], r["near"], r["far"], r["spread"],
                                  r["ret_alloc"], r["worst_mtm_alloc"]) for r in yt]})
    in_window = [r for r in trades if ANCHORS[0] <= r["entry_ts"] < ANCHORS[-1] + YEAR_LEN]
    pre_window = [r for r in trades if r["entry_ts"] < ANCHORS[0]]
    pooled_sum = float(sum(r["ret_alloc"] for r in in_window))
    fac = 1.0
    for y in years:
        fac *= 1.0 + F_ALLOC * y["sum_ret_alloc"]
    pooled = {"n_trades": len(in_window), "sum_ret_alloc": round(pooled_sum, 6),
              "n_pre_window_trades_excluded": len(pre_window),
              "pre_window_sum_ret_alloc_excluded": round(
                  float(sum(r["ret_alloc"] for r in pre_window)), 6),
              "total_acct_pct": round(float(F_ALLOC * pooled_sum * 100), 4),
              "per_month_pct": round(float(F_ALLOC * pooled_sum * 100 / 60), 4),
              "geom_per_month_pct": round(float((fac ** (1 / 60) - 1) * 100), 4)}
    # correlations vs base carry
    base_by_year = {y["year"]: y["sum_ret_alloc"] for y in base_years}
    xs = [y["sum_ret_alloc"] for y in years]
    bs = [base_by_year.get(y["year"], 0.0) for y in years]
    if float(np.std(xs)) > 0 and float(np.std(bs)) > 0:
        r_year = round(float(np.corrcoef(xs, bs)[0, 1]), 4)
    else:
        r_year = None
    base_map = {(t["coin"], t["delivery"]): t["ret_alloc"] for t in base_trades}
    # Bybit base deliveries are date-only strings too; spread near keys match that format
    matched = []
    for r in trades:
        b = base_map.get((r["coin"], r["near"]))
        if b is not None:
            matched.append((r["ret_alloc"], b))
    if len(matched) >= 2:
        sa = np.array([m[0] for m in matched], dtype=float)
        ba = np.array([m[1] for m in matched], dtype=float)
        if float(np.std(sa)) > 0 and float(np.std(ba)) > 0:
            r_trade = round(float(np.corrcoef(sa, ba)[0, 1]), 4)
        else:
            r_trade = None
    else:
        r_trade = None
    corr = {"year_sums_pearson_n5": r_year,
            "year_sums_spread": xs, "year_sums_base": bs,
            "matched_trades_pearson": r_trade,
            "n_matched": len(matched)}
    n_pos_years = sum(1 for y in years if y["sum_ret_alloc"] > 0)
    return {"venue": venue, "years": years, "pooled": pooled,
            "correlation_vs_base_carry": corr,
            "n_years_positive": n_pos_years,
            "n_considered": sum(1 for c in pairs_meta
                                if c.get("status") in ("entered", "skipped_spread")),
            "n_no_pair": sum(1 for c in pairs_meta if c.get("status") == "no_pair"),
            "n_no_far_at_roll": sum(1 for c in pairs_meta
                                    if c.get("status") == "no_far_at_roll"),
            "n_incomplete": sum(1 for c in pairs_meta
                                if str(c.get("status", "")).startswith("incomplete")),
            "trades": [{k: r[k] for k in ("coin", "near", "far", "entry_open", "spread",
                                          "ann_near", "ann_far", "dte_near", "dte_far",
                                          "ret_alloc", "worst_mtm_alloc",
                                          "N_entry", "F_entry", "S_entry",
                                          "S_del", "F_far_del")} for r in trades]}


def main() -> None:
    bin_res = run_binance()
    byb_res = run_bybit()
    oc_res = json.loads((OC / "results.json").read_text(encoding="utf-8"))
    byb_all = json.loads((BYBITQ / "results_bybit_carry.json").read_text(encoding="utf-8"))
    bin_sum = summarize(bin_res["trades"], bin_res["pairs_meta"],
                        oc_res["trades"], oc_res["years"], "binance_proxy_um")
    byb_sum = summarize(byb_res["trades"], byb_res["pairs_meta"],
                        byb_all["inverse"]["trades"], byb_all["inverse"]["years"],
                        "bybit_inverse")
    verdict_useful = bool(bin_sum["n_years_positive"] >= 4 and byb_sum["n_years_positive"] >= 4)
    out = {
        "meta": {
            "rule": "long near / short far equal notional f=0.125 iff ann_far - ann_near >= 0.02; "
                    "hold to near delivery; far closed at market in same hour",
            "fees": {"taker_per_fill": F_TAKER, "delivery": F_DELIV,
                     "pair_drag": FEE_PAIR, "entry_paid_mtm": FEE_ENTRY_PAID},
            "threshold_spread": SPREAD_THRESHOLD,
            "f_alloc": F_ALLOC,
            "roll": "oc_cashcarry roll (prev delivery - 7d round_UP to next spot 4h open)",
            "settlement": "near delivery bar spot 4h close; far close at same bar",
            "venues": "binance_proxy um_* delivery 08:00 code date; "
                      "bybit_inverse deliveryTime from inventory.json",
            "inverse_note": "coin-margined inverse prices used in price-return form "
                            "unchanged (convexity not modelled, as in bybit carry recompute)",
            "base_carry_src": "oc_cashcarry/results.json (binance), "
                              "bybitq/results_bybit_carry.json inverse (bybit)",
            "verdict_rule": "USEFUL iff yearly net on allocated > 0 in >= 4/5 years "
                            "on BOTH venues; else CLOSE",
        },
        "binance": bin_sum,
        "bybit": byb_sum,
        "verdict": "USEFUL" if verdict_useful else "CLOSE",
    }
    (HERE / "results.json").write_text(json.dumps(out, indent=1))
    for tag, s in (("BIN", bin_sum), ("BYB", byb_sum)):
        print(f"== {tag}: considered={s['n_considered']} entered={s['pooled']['n_trades']} "
              f"no_pair={s['n_no_pair']} incomplete={s['n_incomplete']} "
              f"pos_years={s['n_years_positive']}/5 pooled_alloc={s['pooled']['sum_ret_alloc']}")
        for y in s["years"]:
            print("  ", y["year"], "n=", y["n_trades"], "cons=", y["n_considered"],
                  "sum_alloc=", y["sum_ret_alloc"], "worst=", y["worst_mtm_alloc"],
                  "acct%/mo=", y["contrib_acct_pct"]["per_month_pct"])
        print("   corr:", json.dumps(s["correlation_vs_base_carry"]))
    print("verdict:", out["verdict"])


if __name__ == "__main__":
    main()
