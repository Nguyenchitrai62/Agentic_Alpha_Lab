"""oc_carryfar: FAR-tenor variant (second-next quarterly at the same roll times).

Per PLAN.md (pre-registered, frozen): FAR opportunity k (k = 0..N-2) evaluates
contract C_{k+1} at the SAME roll time E_k as the base opportunity for C_k
(E_k = round_UP(D_{k-1} - 7d) for k >= 1, first availability for k = 0),
ENTER iff its own annualised basis ln(F/S)*365/DTE >= 4 %/yr, hold to
delivery D_{k+1}. Same fees (spot 0.001/side, fut 0.00055 entry + 0.0002
delivery), same sizing (f per open pair), same settlement (spot 4h close of
the delivery bar). Base is recomputed in-script for like-for-like comparison
and must match the frozen results within 1e-6.

Venues: binance proxy (um_* delivery quarterlies + Binance spot 4h, delivery
08:00 UTC on code date) and bybit inverse (inv_* quarterly + Bybit spot,
delivery = exact inventory deliveryTime). 4h data only, one process.

  .venv/Scripts/python.exe research/tournament/oc_carryfar/analyze_carryfar.py
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
BYBITQ = ROOT / "research/data_fetch/bybitq"
CASH = ROOT / "research/tournament/oc_cashcarry"
KPI = ROOT / "research/tournament/oc_kpi_g2"

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
LEV = 5
BLOCK_FRAC = 0.95
MMR_TIER1 = 0.0033  # binding Bybit tier-1 BTC/ETH MMR (oc_utamargin, live 2026-10-06)


# ---------------- Binance proxy side ----------------

def parse_expiry(fname: str) -> pd.Timestamp:
    m = re.search(r"_(\d{6})_1h\.parquet$", fname)
    assert m, fname
    s = m.group(1)
    return pd.Timestamp(f"20{s[:2]}-{s[2:4]}-{s[4:6]} 08:00", tz="UTC")


def load_spot(coin: str) -> pd.DataFrame:
    p = SDIR / f"{coin}USDT_spot_4h.parquet"
    d = pd.read_parquet(p, columns=["open_time", "close", "close_time"])
    d["open_time"] = pd.to_datetime(d["open_time"], utc=True)
    d["close_time"] = pd.to_datetime(d["close_time"], utc=True)
    return d.sort_values("open_time").reset_index(drop=True)


def load_q_1h(coin: str) -> dict:
    out = {}
    for f in sorted(QDIR.glob(f"um_{coin}USDT_*_1h.parquet")):
        d = pd.read_parquet(f, columns=["open_time", "close"])
        d["open_time"] = pd.to_datetime(d["open_time"], utc=True)
        d = d.sort_values("open_time").reset_index(drop=True)
        out[parse_expiry(f.name)] = d
    return out


def resample_to_spot(q: pd.DataFrame, spot: pd.DataFrame) -> np.ndarray:
    qo = q["open_time"].to_numpy(dtype="datetime64[ns]").astype(np.int64)
    qc = q["close"].to_numpy(dtype=float)
    sc = spot["close_time"].to_numpy(dtype="datetime64[ns]").astype(np.int64)
    idx = np.searchsorted(qo, sc, side="left") - 1
    out = np.full(len(spot), np.nan)
    ok = idx >= 0
    out[ok] = qc[idx[ok]]
    return out


def run_binance() -> dict:
    spot = {c: load_spot(c) for c in COINS}
    assert (spot["BTC"]["open_time"].to_numpy() == spot["ETH"]["open_time"].to_numpy()).all()
    out = {"spot": spot, "series": {}, "base": [], "far": [],
           "meta_base": [], "meta_far": []}
    for coin in COINS:
        s = spot[coin]
        s_open, s_close_t = s["open_time"], s["close_time"]
        s_close = s["close"].to_numpy(dtype=float)
        s_open_ns = s_open.to_numpy(dtype="datetime64[ns]").astype(np.int64)
        s_close_ns = s_close_t.to_numpy(dtype="datetime64[ns]").astype(np.int64)
        qmap = load_q_1h(coin)
        expiries = sorted(qmap)
        F = {D: resample_to_spot(qmap[D], s) for D in expiries}
        out["series"][coin] = F

        def roll_pos(k: int) -> int:
            if k == 0:
                return 0
            cand = expiries[k - 1] - pd.Timedelta(days=ROLL_DAYS)
            return int(np.searchsorted(s_open_ns, cand.value, side="left"))

        def try_enter(D, pos, tag_list, meta_list):
            arr = F[D]
            both = np.where(~np.isnan(s_close) & ~np.isnan(arr))[0]
            both = both[both >= pos]
            if len(both) == 0:
                meta_list.append({"coin": coin, "delivery": str(D.date()),
                                  "status": "no_overlap"})
                return
            ti = int(both[0])
            T_open, T_close = s_open.iloc[ti], s_close_t.iloc[ti]
            F_entry, S_entry = float(arr[ti]), float(s_close[ti])
            dte = (D - T_close).total_seconds() / 86400.0
            if not (np.isfinite(F_entry) and np.isfinite(S_entry)) or dte <= 0:
                meta_list.append({"coin": coin, "delivery": str(D.date()),
                                  "status": "bad_dte"})
                return
            basis = float(np.log(F_entry / S_entry) * 365.0 / dte)
            si = int(np.searchsorted(s_close_ns, D.value, side="right"))
            if si >= len(s):
                meta_list.append({"coin": coin, "delivery": str(D.date()),
                                  "entry": str(T_open.date()),
                                  "ann_basis": round(basis, 6),
                                  "dte_days": round(dte, 2),
                                  "status": "incomplete_no_spot"})
                return
            S_del = float(s_close[si])
            entered = bool(basis >= THRESHOLD)
            rec = {"coin": coin, "delivery": str(D.date()),
                   "entry_open": str(T_open), "entry_close": str(T_close),
                   "F_entry": F_entry, "S_entry": S_entry, "S_del": S_del,
                   "dte_days": round(dte, 2), "ann_basis": round(basis, 6),
                   "entered": entered, "ti": ti, "si": si}
            if entered:
                gross = (S_del - S_entry) / S_entry + (F_entry - S_del) / F_entry
                rec["ret_alloc"] = round(float(gross - FEE_PAIR), 6)
                St, Ft = s_close[ti + 1: si + 1], arr[ti + 1: si + 1]
                okm = ~np.isnan(St) & ~np.isnan(Ft)
                if okm.sum() == 0:
                    rec["worst_mtm_alloc"] = round(float(-FEE_ENTRY_PAID), 6)
                else:
                    mtm = (St[okm] / S_entry - 1.0) + ((F_entry - Ft[okm]) / F_entry) \
                        - FEE_ENTRY_PAID
                    rec["worst_mtm_alloc"] = round(float(mtm.min()), 6)
                tag_list.append(rec)
            meta_list.append({"coin": coin, "delivery": str(D.date()),
                              "ann_basis": round(basis, 6),
                              "dte_days": round(dte, 2),
                              "entered": entered,
                              "status": "entered" if entered else "skipped_basis",
                              "entry": str(T_open.date())})

        for k, D in enumerate(expiries):
            try_enter(D, roll_pos(k), out["base"], out["meta_base"])
        for k in range(len(expiries) - 1):
            try_enter(expiries[k + 1], roll_pos(k), out["far"], out["meta_far"])
    return out


# ---------------- Bybit inverse side ----------------

def load_1h(path: Path) -> pd.DataFrame:
    d = pd.read_parquet(path, columns=["open_time", "close"])
    t = pd.to_datetime(d["open_time"], unit="ms", utc=True)
    return pd.DataFrame({"t": t,
                         "close": d["close"].to_numpy(dtype=float)}).sort_values(
        "t").reset_index(drop=True)


def to_4h(h: pd.DataFrame) -> pd.DataFrame:
    hh = h.copy()
    hh["bar"] = hh["t"].dt.floor("4h")
    g = hh.groupby("bar")
    n, c = g.size(), g["close"].last()
    ok = n[n == 4].index
    bars = pd.DataFrame({"open_time": pd.to_datetime(sorted(ok), utc=True)})
    bars["close"] = bars["open_time"].map(c).to_numpy(dtype=float)
    bars["close_time"] = bars["open_time"] + pd.Timedelta(hours=4)
    return bars.reset_index(drop=True)


def resample_fut_to_spot(f4: pd.DataFrame, spot: pd.DataFrame) -> np.ndarray:
    fo = f4["close_time"].to_numpy(dtype="datetime64[ns]").astype(np.int64)
    fc = f4["close"].to_numpy(dtype=float)
    sc = spot["close_time"].to_numpy(dtype="datetime64[ns]").astype(np.int64)
    idx = np.searchsorted(fo, sc, side="right") - 1
    out = np.full(len(spot), np.nan)
    ok = idx >= 0
    out[ok] = fc[idx[ok]]
    return out


def run_bybit() -> dict:
    inv = json.loads((BYBITQ / "inventory.json").read_text(encoding="utf-8"))["records"]
    spot4 = {c: to_4h(load_1h(BDIR / f"spot_{c}USDT_1h.parquet")) for c in COINS}
    assert (spot4["BTC"]["open_time"].to_numpy() == spot4["ETH"]["open_time"].to_numpy()).all()
    fut: dict = {}
    for coin in COINS:
        lst = []
        for r in inv:
            if r["baseCoin"] != coin or r["category"] != "inverse":
                continue
            D = pd.Timestamp(r["deliveryTime"], unit="ms", tz="UTC")
            safe = r["symbol"].replace("-", "_")
            lst.append((D, BDIR / f"inv_{safe}_1h.parquet"))
        lst.sort()
        fut[coin] = lst
    out = {"spot": spot4, "series": {}, "base": [], "far": [],
           "meta_base": [], "meta_far": []}
    for coin in COINS:
        s = spot4[coin]
        s_open, s_close_t = s["open_time"], s["close_time"]
        s_close = s["close"].to_numpy(dtype=float)
        s_open_ns = s_open.to_numpy(dtype="datetime64[ns]").astype(np.int64)
        s_close_ns = s_close_t.to_numpy(dtype="datetime64[ns]").astype(np.int64)
        exps = fut[coin]
        Farr = {}
        for D, path in exps:
            Farr[D] = resample_fut_to_spot(to_4h(load_1h(path)), s)
        out["series"][coin] = Farr

        def roll_pos(k: int) -> int:
            if k == 0:
                return 0
            cand = exps[k - 1][0] - pd.Timedelta(days=ROLL_DAYS)
            return int(np.searchsorted(s_open_ns, cand.value, side="left"))

        def try_enter(D, pos, tag_list, meta_list):
            arr = Farr[D]
            both = np.where(~np.isnan(s_close) & ~np.isnan(arr))[0]
            both = both[both >= pos]
            if len(both) == 0:
                meta_list.append({"coin": coin, "delivery": str(D.date()),
                                  "status": "no_overlap"})
                return
            ti = int(both[0])
            T_open, T_close = s_open.iloc[ti], s_close_t.iloc[ti]
            F_entry, S_entry = float(arr[ti]), float(s_close[ti])
            dte = (D - T_close).total_seconds() / 86400.0
            if not (np.isfinite(F_entry) and np.isfinite(S_entry)) or dte <= 0:
                meta_list.append({"coin": coin, "delivery": str(D.date()),
                                  "status": "bad_dte"})
                return
            basis = float(np.log(F_entry / S_entry) * 365.0 / dte)
            si = int(np.searchsorted(s_close_ns, D.value, side="right"))
            if si >= len(s):
                meta_list.append({"coin": coin, "delivery": str(D.date()),
                                  "entry": str(T_open.date()),
                                  "ann_basis": round(basis, 6),
                                  "dte_days": round(dte, 2),
                                  "status": "incomplete_no_spot"})
                return
            S_del = float(s_close[si])
            entered = bool(basis >= THRESHOLD)
            rec = {"coin": coin, "delivery": str(D.date()),
                   "entry_open": str(T_open), "entry_close": str(T_close),
                   "F_entry": F_entry, "S_entry": S_entry, "S_del": S_del,
                   "dte_days": round(dte, 2), "ann_basis": round(basis, 6),
                   "entered": entered, "ti": ti, "si": si}
            if entered:
                gross = (S_del - S_entry) / S_entry + (F_entry - S_del) / F_entry
                rec["ret_alloc"] = round(float(gross - FEE_PAIR), 6)
                St, Ft = s_close[ti + 1: si + 1], arr[ti + 1: si + 1]
                okm = ~np.isnan(St) & ~np.isnan(Ft)
                if okm.sum() == 0:
                    rec["worst_mtm_alloc"] = round(float(-FEE_ENTRY_PAID), 6)
                else:
                    mtm = (St[okm] / S_entry - 1.0) + ((F_entry - Ft[okm]) / F_entry) \
                        - FEE_ENTRY_PAID
                    rec["worst_mtm_alloc"] = round(float(mtm.min()), 6)
                tag_list.append(rec)
            meta_list.append({"coin": coin, "delivery": str(D.date()),
                              "ann_basis": round(basis, 6),
                              "dte_days": round(dte, 2),
                              "entered": entered,
                              "status": "entered" if entered else "skipped_basis",
                              "entry": str(T_open.date())})

        for k, (D, _p) in enumerate(exps):
            try_enter(D, roll_pos(k), out["base"], out["meta_base"])
        for k in range(len(exps) - 1):
            try_enter(exps[k + 1][0], roll_pos(k), out["far"], out["meta_far"])
    return out


# ---------------- shared stats ----------------

def yearly_stats(trades: list, metas: list) -> tuple[list, dict]:
    for r in trades:
        r["entry_ts"] = pd.Timestamp(r["entry_open"])
    years = []
    for a0 in ANCHORS:
        a1 = a0 + YEAR_LEN
        yt = [r for r in trades if a0 <= r["entry_ts"] < a1]
        per_coin = {}
        for coin in COINS:
            ct = [r for r in yt if r["coin"] == coin]
            per_coin[coin] = {"n": len(ct)} if not ct else {
                "n": len(ct),
                "mean_ann_basis": round(float(np.mean([r["ann_basis"] for r in ct])), 6),
                "mean_dte": round(float(np.mean([r["dte_days"] for r in ct])), 1),
                "mean_ret_alloc": round(float(np.mean([r["ret_alloc"] for r in ct])), 6),
                "sum_ret_alloc": round(float(np.sum([r["ret_alloc"] for r in ct])), 6),
                "worst_mtm_alloc": round(float(np.min([r["worst_mtm_alloc"] for r in ct])), 6),
            }
        tot = round(float(sum(r["ret_alloc"] for r in yt)), 6)
        worst = round(float(min([r["worst_mtm_alloc"] for r in yt])), 6) if yt else None
        years.append({
            "year": str(a0.date()), "n_trades": len(yt),
            "n_skipped_in_year": sum(
                1 for c in metas if c.get("status") == "skipped_basis"
                and a0 <= pd.Timestamp(c["entry"], tz="UTC") < a1),
            "per_coin": per_coin, "sum_ret_alloc": tot, "worst_mtm_alloc": worst,
            "contrib_acct_pct": {
                str(f): {"year_pct": round(float(f * tot * 100), 4),
                         "per_month_pct": round(float(f * tot * 100 / 12), 4)}
                for f in F_ROWS},
            "worst_acct_pct": {
                str(f): (round(float(f * worst * 100), 4) if worst is not None else None)
                for f in F_ROWS},
            "trades": [(r["coin"], r["delivery"], r["ann_basis"],
                        r["ret_alloc"], r["worst_mtm_alloc"]) for r in yt]})
    in_w = [r for r in trades if ANCHORS[0] <= r["entry_ts"] < ANCHORS[-1] + YEAR_LEN]
    psum = float(sum(r["ret_alloc"] for r in in_w))
    pooled = {"n_trades": len(in_w), "sum_ret_alloc": round(psum, 6),
              "per_f": {str(f): {"total_acct_pct": round(float(f * psum * 100), 4),
                                 "per_month_pct": round(float(f * psum * 100 / 60), 4)}
                        for f in F_ROWS}}
    for f in F_ROWS:
        fac = 1.0
        for y in years:
            fac *= 1.0 + f * y["sum_ret_alloc"]
        pooled["per_f"][str(f)]["geom_per_month_pct"] = round(float((fac ** (1 / 60) - 1) * 100), 4)
    return years, pooled


def yearly_overlap(trades: list, spot: pd.DataFrame) -> dict:
    """Max simultaneous open pairs within each anchor-year window.

    Counts, on the spot 4h grid, pairs with entry <= t < delivery;
    per-year max over grid bars in [A, A+365d). Units: pairs (x f = allocation).
    """
    s_open = spot["open_time"]
    s_ns = s_open.to_numpy(dtype="datetime64[ns]").astype(np.int64)
    n = len(s_open)
    series = {}
    for coin in COINS + ["total"]:
        cnt = np.zeros(n, dtype=np.int16)
        for r in trades:
            if coin != "total" and r["coin"] != coin:
                continue
            cnt[r["ti"] + 1: r["si"] + 1] += 1
        series[coin] = cnt
    out = {}
    for a0 in ANCHORS:
        a1 = a0 + YEAR_LEN
        m = (s_open >= a0) & (s_open < a1)
        out[str(a0.date())] = {k: int(v[m].max()) if m.any() else 0
                               for k, v in series.items()}
    return out


def overlap_stats(trades: list, spot_grid_len: dict) -> dict:
    res = {}
    for coin in COINS:
        n = spot_grid_len[coin]
        cnt = np.zeros(n, dtype=np.int16)
        for r in [t for t in trades if t["coin"] == coin]:
            cnt[r["ti"] + 1: r["si"] + 1] += 1
        res[coin] = {"max_open": int(cnt.max()),
                     "max_alloc_f025": round(float(cnt.max() * 0.25), 4)}
    n0 = spot_grid_len[COINS[0]]
    tot = np.zeros(n0, dtype=np.int16)
    for r in trades:
        tot[r["ti"] + 1: r["si"] + 1] += 1
    res["total"] = {"max_open": int(tot.max()),
                    "max_alloc_f025": round(float(tot.max() * 0.25), 4)}
    return res


def margin_check(far_trades: list, series: dict, spot: pd.DataFrame,
                 venue: str) -> dict:
    """oc_utamargin UTA rule on the spot 4h grid at f = 0.25 / 0.50.

    G2 envelope: book_gross(t) + 2.0 dip cap per phase (same conservative
    envelope as the oc_cashcarry margin section). IM = (G_bot + carry_short)
    / 5; balance = Eq_tot - 0.05 x spot value; blocked iff IM > 0.95 balance;
    MM bound with tier-1 MMR = 0.0033. 4h proxy (stated limitation vs the
    hourly UTA replay).
    """
    s_open = spot["open_time"]
    s_close_all = spot["close"].to_numpy(dtype=float)
    s_open_ns = s_open.to_numpy(dtype="datetime64[ns]").astype(np.int64)
    f_by_cd = {}
    for coin, smap in series.items():
        for D, arr in smap.items():
            f_by_cd[(coin, str(D.date()))] = arr
    bsm = {}
    for ph in range(4):
        b = pd.read_parquet(KPI / f"barsum_s{ph}.parquet")
        b["t"] = pd.to_datetime(b["t"], utc=True)
        bsm[ph] = b.sort_values("t").reset_index(drop=True)
    margin = {}
    for f in F_ROWS:
        per_phase, worst = {}, 0.0
        for ph, b in bsm.items():
            bt = b["t"].to_numpy(dtype="datetime64[ns]").astype(np.int64)
            sp_idx = np.searchsorted(s_open_ns, bt, side="right") - 1
            book = b["gross_book"].to_numpy(dtype=float)
            eq = b["equity"].to_numpy(dtype=float)
            max_ratio, worst_t, max_mm, max_spot = 0.0, None, 0.0, 0.0
            worst_cs, worst_g = 0.0, 0.0
            n_blocked = 0
            for i in range(len(b)):
                j = sp_idx[i]
                if j < 0 or eq[i] <= 0:
                    continue
                cs, cu, scost = 0.0, 0.0, 0.0
                for r in far_trades:
                    Dd = pd.Timestamp(r["delivery"] + " 08:00", tz="UTC").value
                    Te = pd.Timestamp(r["entry_open"]).value
                    tt = bt[i]
                    if Te <= tt < Dd:
                        Fnow_arr = f_by_cd.get((r["coin"], r["delivery"]))
                        if Fnow_arr is None or j >= len(Fnow_arr):
                            continue
                        Fnow = float(Fnow_arr[j])
                        if not np.isfinite(Fnow):
                            continue
                        cs += f * (Fnow / r["F_entry"]) / eq[i]
                        Snow = float(s_close_all[j])
                        if np.isfinite(Snow):
                            mtm = ((Snow / r["S_entry"] - 1.0)
                                   + ((r["F_entry"] - Fnow) / r["F_entry"])
                                   - FEE_ENTRY_PAID)
                            cu += f * mtm / eq[i]
                            scost += f * (Snow / r["S_entry"]) / eq[i]
                G_bot = max(float(book[i]) + 2.0, 0.0)
                im = (G_bot + cs) / LEV
                eq_ratio = 1.0 + cu
                ratio = im / max(eq_ratio, 1e-9)
                mm_ratio = (MMR_TIER1 * (G_bot + cs)) / max(eq_ratio, 1e-9)
                spot_ratio = scost / max(eq_ratio, 1e-9)
                max_mm = max(max_mm, mm_ratio)
                max_spot = max(max_spot, spot_ratio)
                if ratio > max_ratio:
                    max_ratio, worst_t = ratio, str(b["t"].iloc[i])
                    worst_cs, worst_g = cs, G_bot
                if ratio > BLOCK_FRAC:
                    n_blocked += 1
            per_phase[f"s{ph}"] = {
                "max_IM_over_balance": round(float(max_ratio), 4),
                "blocked_closes": int(n_blocked),
                "blocked_any": bool(max_ratio > BLOCK_FRAC),
                "worst_t": worst_t,
                "worst_carry_short_frac": round(float(worst_cs), 4),
                "worst_G2_gross_frac": round(float(worst_g), 4),
                "max_MM_over_balance": round(float(max_mm), 4),
                "max_spot_cost_over_equity": round(float(max_spot), 4)}
            worst = max(worst, max_ratio)
        margin[str(f)] = {"per_phase": per_phase,
                          "worst_IM_over_balance": round(float(worst), 4),
                          "blocked_any": bool(worst > BLOCK_FRAC)}
    margin["src"] = ("barsum_s0..s3_book_gross_plus_G2_dip_cap_2.0;"
                     "uta_rule_tier1_MMR0.0033;4h_proxy")
    margin["venue"] = venue
    return margin


def slim(trades: list) -> list:
    return [{k: r[k] for k in ("coin", "delivery", "entry_open", "ann_basis",
                               "dte_days", "ret_alloc", "worst_mtm_alloc",
                               "F_entry", "S_entry", "S_del")} for r in trades]


def main() -> None:
    bz = run_binance()
    bb = run_bybit()

    frozen = json.loads((CASH / "results.json").read_text())
    frozen_bybit = json.loads((BYBITQ / "results_bybit_carry.json").read_text())
    by_, bb_ = yearly_stats(bz["base"], bz["meta_base"])
    iy_, ib_ = yearly_stats(bb["base"], bb["meta_base"])
    assert abs(bb_["sum_ret_alloc"] - frozen["pooled"]["sum_ret_alloc"]) < 1e-6, (
        bb_["sum_ret_alloc"], frozen["pooled"]["sum_ret_alloc"])
    assert abs(ib_["sum_ret_alloc"]
               - frozen_bybit["inverse"]["pooled"]["sum_ret_alloc"]) < 1e-6
    assert frozen["n_trades"] == 33 and len(bz["base"]) == 33, len(bz["base"])
    assert len(bb["base"]) == frozen_bybit["inverse"]["n_trades"], len(bb["base"])

    fy_, fb_ = yearly_stats(bz["far"], bz["meta_far"])
    gy_, gb_ = yearly_stats(bb["far"], bb["meta_far"])

    # per-year max simultaneous open pairs (allocation = pairs x f)
    yo_b_base = yearly_overlap(bz["base"], bz["spot"]["BTC"])
    yo_b_far = yearly_overlap(bz["far"], bz["spot"]["BTC"])
    yo_i_base = yearly_overlap(bb["base"], bb["spot"]["BTC"])
    yo_i_far = yearly_overlap(bb["far"], bb["spot"]["BTC"])
    for y in by_:
        y["max_open_pairs"] = yo_b_base[y["year"]]
    for y in fy_:
        y["max_open_pairs"] = yo_b_far[y["year"]]
    for y in iy_:
        y["max_open_pairs"] = yo_i_base[y["year"]]
    for y in gy_:
        y["max_open_pairs"] = yo_i_far[y["year"]]

    def h2h(yb, yf):
        wins = sum(1 for a, b in zip(yb, yf) if b["sum_ret_alloc"] > a["sum_ret_alloc"])
        return {"per_year": [
            {"year": a["year"], "base_sum_ret_alloc": a["sum_ret_alloc"],
             "far_sum_ret_alloc": b["sum_ret_alloc"],
             "diff_far_minus_base": round(b["sum_ret_alloc"] - a["sum_ret_alloc"], 6),
             "far_wins": bool(b["sum_ret_alloc"] > a["sum_ret_alloc"])}
            for a, b in zip(yb, yf)],
            "far_win_years": wins}

    grid_len_b = {c: len(bz["spot"][c]) for c in COINS}
    grid_len_i = {c: len(bb["spot"][c]) for c in COINS}
    margin_bin = margin_check(bz["far"], bz["series"], bz["spot"]["BTC"], "binance_proxy")
    margin_inv = margin_check(bb["far"], bb["series"], bb["spot"]["BTC"], "bybit_inverse")
    margin_ok = (not margin_bin["0.25"]["blocked_any"]
                 and not margin_inv["0.25"]["blocked_any"])

    h_b, h_i = h2h(by_, fy_), h2h(iy_, gy_)
    far_better = (h_b["far_win_years"] >= 4 and h_i["far_win_years"] >= 4 and margin_ok)
    verdict = ("FAR BETTER" if far_better
               else "BASE STAYS — carry direction closes (no further variants)")

    out = {
        "meta": {
            "threshold_ann_basis": THRESHOLD, "roll_days": ROLL_DAYS,
            "fees": {"spot_per_side": F_SPOT, "fut_entry": F_FUT_ENTRY,
                     "fut_delivery": F_FUT_DELIV, "pair_drag": FEE_PAIR},
            "far_rule": ("FAR opportunity k evaluates contract k+1 at the same roll "
                         "time E_k as base C_k; hold to D_{k+1}; pairs overlap"),
            "base_repro": {"binance_pooled_sum": bb_["sum_ret_alloc"],
                           "bybit_inv_pooled_sum": ib_["sum_ret_alloc"],
                           "match": True},
            "margin_rule": ("oc_utamargin UTA: IM=(G2+carry_short)/5, balance=Eq-0.05*spot, "
                            "blocked iff IM>0.95*balance, tier-1 MM bound 0.0033; "
                            "G2 envelope book_gross+2.0 dip cap; 4h proxy"),
            "margin_ok_f025_no_blocked_both_venues": margin_ok,
            "spot_last_binance": str(bz["spot"]["BTC"]["open_time"].max()),
            "spot_last_bybit": str(bb["spot"]["BTC"]["open_time"].max()),
        },
        "binance": {
            "base": {"years": by_, "pooled": bb_,
                     "n_trades": len(bz["base"]),
                     "n_skipped": sum(1 for c in bz["meta_base"]
                                      if c.get("status") == "skipped_basis"),
                     "n_incomplete": sum(1 for c in bz["meta_base"]
                                         if c.get("status") == "incomplete_no_spot"),
                     "overlap": overlap_stats(bz["base"], grid_len_b),
                     "trades": slim(bz["base"])},
            "far": {"years": fy_, "pooled": fb_,
                    "n_trades": len(bz["far"]),
                    "n_skipped": sum(1 for c in bz["meta_far"]
                                     if c.get("status") == "skipped_basis"),
                    "n_incomplete": sum(1 for c in bz["meta_far"]
                                        if c.get("status") == "incomplete_no_spot"),
                    "overlap": overlap_stats(bz["far"], grid_len_b),
                    "trades": slim(bz["far"])},
            "head_to_head": h_b,
        },
        "bybit_inverse": {
            "base": {"years": iy_, "pooled": ib_,
                     "n_trades": len(bb["base"]),
                     "n_skipped": sum(1 for c in bb["meta_base"]
                                      if c.get("status") == "skipped_basis"),
                     "n_incomplete": sum(1 for c in bb["meta_base"]
                                         if c.get("status") == "incomplete_no_spot"),
                     "overlap": overlap_stats(bb["base"], grid_len_i),
                     "trades": slim(bb["base"])},
            "far": {"years": gy_, "pooled": gb_,
                    "n_trades": len(bb["far"]),
                    "n_skipped": sum(1 for c in bb["meta_far"]
                                     if c.get("status") == "skipped_basis"),
                    "n_incomplete": sum(1 for c in bb["meta_far"]
                                        if c.get("status") == "incomplete_no_spot"),
                    "overlap": overlap_stats(bb["far"], grid_len_i),
                    "trades": slim(bb["far"])},
            "head_to_head": h_i,
        },
        "margin_bin": margin_bin,
        "margin_inv": margin_inv,
        "verdict": verdict,
    }
    (HERE / "results.json").write_text(json.dumps(out, indent=1))
    for tag, yb, yf in (("BIN", by_, fy_), ("INV", iy_, gy_)):
        print(f"== {tag}")
        for a, b in zip(yb, yf):
            print(f"  {a['year']} base n={a['n_trades']} sum={a['sum_ret_alloc']} worst={a['worst_mtm_alloc']} | "
                  f"far n={b['n_trades']} sum={b['sum_ret_alloc']} worst={b['worst_mtm_alloc']} | "
                  f"acct025 base={a['contrib_acct_pct']['0.25']['per_month_pct']} "
                  f"far={b['contrib_acct_pct']['0.25']['per_month_pct']}")
    print("pooled base BIN:", json.dumps(bb_), "far BIN:", json.dumps(fb_))
    print("pooled base INV:", json.dumps(ib_), "far INV:", json.dumps(gb_))
    print("h2h BIN:", json.dumps(h_b), "h2h INV:", json.dumps(h_i))
    print("margin_bin:", json.dumps(margin_bin))
    print("margin_inv:", json.dumps(margin_inv))
    print("VERDICT:", verdict)


if __name__ == "__main__":
    main()
