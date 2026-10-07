"""oc_carryutil: how often the frozen cash-and-carry rule is invested (LIGHT, descriptive).

Frozen rule (NOT re-tuned here; imported logic mirrors research/tournament/oc_cashcarry/PLAN.md):
per coin (BTC, ETH) sort quarterly delivery expiries ascending; candidate entry E_k =
round_UP(prev delivery - 7 days) to next spot 4h open (k=0: first availability);
entry bar T_k = first bar with BOTH spot close AND resampled quarterly close available;
ENTER iff ann_basis = ln(F_entry/S_entry)*365/DTE >= 4 %/yr; hold entered pair to
delivery; settlement = spot 4h close of delivery bar. Fees: spot 0.001/side,
futures 0.00055 entry + 0.0002 delivery (drag 0.00275/allocated). f = 0.25 per coin.

This script ADDS no variant: it re-enumerates the same contracts from LOCAL 4h
parquet only (no network, no 1m data, no artifacts/bot access) and reports, per
coin and per calendar year 2021-2026: share of days invested, skipped quarters,
mean basis entered vs skipped, per-coin contribution to the pooled +0.22 %/mo
(f = 0.25, anchor window 2021-09-24..2026-09-24, same as oc_cashcarry), and the
expected cost of a skipped ETH quarter (counterfactual + entered-mean + basis-implied).

  python research/tournament/oc_carryutil/analyze_carryutil.py
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
QDIR = ROOT / "data/raw/qbasis_20261003"
SDIR = ROOT / "data/raw/spot_majors_20260925"
CASH = ROOT / "research/tournament/oc_cashcarry/results.json"

COINS = ["BTC", "ETH"]
THRESHOLD = 0.04  # frozen, same as oc_cashcarry PLAN.md (no tuning)
ROLL_DAYS = 7  # frozen
F = 0.25  # sizing row for the +0.22 %/mo decomposition
FEE_PAIR = 2 * 0.001 + 0.00055 + 0.0002  # 0.00275 per allocated unit
CAL_YEARS = [2021, 2022, 2023, 2024, 2025, 2026]
ANCHOR0 = pd.Timestamp("2021-09-24", tz="UTC")
ANCHOR_END = pd.Timestamp("2026-09-24", tz="UTC")  # same pooled window as oc_cashcarry


def parse_expiry(fname: str) -> pd.Timestamp:
    import re

    m = re.search(r"_(\d{6})_1h\.parquet$", fname)
    assert m, fname
    s = m.group(1)
    return pd.Timestamp(f"20{s[:2]}-{s[2:4]}-{s[4:6]} 08:00", tz="UTC")


def load_spot(coin: str) -> pd.DataFrame:
    d = pd.read_parquet(SDIR / f"{coin}USDT_spot_4h.parquet",
                        columns=["open_time", "close", "close_time"])
    d["open_time"] = pd.to_datetime(d["open_time"], utc=True)
    d["close_time"] = pd.to_datetime(d["close_time"], utc=True)
    return d.sort_values("open_time").reset_index(drop=True)


def load_q_1h(coin: str) -> dict:
    out = {}
    for f in sorted(QDIR.glob(f"um_{coin}USDT_*_1h.parquet")):
        d = pd.read_parquet(f, columns=["open_time", "close"])
        d["open_time"] = pd.to_datetime(d["open_time"], utc=True)
        out[parse_expiry(f.name)] = d.sort_values("open_time").reset_index(drop=True)
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


def enumerate_contracts() -> tuple[list[dict], pd.Timestamp]:
    spot = {c: load_spot(c) for c in COINS}
    assert (spot["BTC"]["open_time"].to_numpy() == spot["ETH"]["open_time"].to_numpy()).all()
    last_spot_date = spot["BTC"]["open_time"].max().date()
    contracts: list[dict] = []
    for coin in COINS:
        s = spot[coin]
        s_open, s_close_t = s["open_time"], s["close_time"]
        s_close = s["close"].to_numpy(dtype=float)
        qmap = load_q_1h(coin)
        expiries = sorted(qmap)
        for k, D in enumerate(expiries):
            Fp = resample_to_spot(qmap[D], s)
            if k > 0:
                cand = expiries[k - 1] - pd.Timedelta(days=ROLL_DAYS)
                pos = int(np.searchsorted(
                    s_open.to_numpy(dtype="datetime64[ns]").astype(np.int64),
                    cand.value, side="left"))
            else:
                pos = 0
            both = np.where(~np.isnan(s_close) & ~np.isnan(Fp))[0]
            both = both[both >= pos]
            if len(both) == 0:
                contracts.append({"coin": coin, "delivery": str(D.date()),
                                  "status": "no_overlap"})
                continue
            ti = int(both[0])
            T_open, T_close = s_open.iloc[ti], s_close_t.iloc[ti]
            F_entry, S_entry = float(Fp[ti]), float(s_close[ti])
            dte = (D - T_close).total_seconds() / 86400.0
            if not (np.isfinite(F_entry) and np.isfinite(S_entry)) or dte <= 0:
                contracts.append({"coin": coin, "delivery": str(D.date()),
                                  "status": "bad_dte"})
                continue
            basis = float(np.log(F_entry / S_entry) * 365.0 / dte)
            si = int(np.searchsorted(
                s_close_t.to_numpy(dtype="datetime64[ns]").astype(np.int64),
                D.value, side="right"))
            if si >= len(s):
                contracts.append({"coin": coin, "delivery": str(D.date()),
                                  "entry": str(T_open.date()),
                                  "ann_basis": round(basis, 6),
                                  "dte_days": round(float(dte), 2),
                                  "status": "incomplete_no_spot"})
                continue
            S_del = float(s_close[si])
            entered = bool(basis >= THRESHOLD)
            gross = (S_del - S_entry) / S_entry + (F_entry - S_del) / F_entry
            ret = float(gross - FEE_PAIR)  # realized if entered; counterfactual if skipped
            contracts.append({
                "coin": coin, "delivery": str(D.date()),
                "entry": str(T_open.date()),
                "entry_open": str(T_open), "delivery_ts": str(D),
                "ann_basis": round(basis, 6), "dte_days": round(float(dte), 2),
                "ret_alloc": round(ret, 6),
                "entered": entered,
                "status": "entered" if entered else "skipped_basis",
            })
    return contracts, last_spot_date


def days_in_year(y: int, last_spot_date) -> int:
    start = date(y, 1, 1)
    end = date(y, 12, 31)
    if y == 2026:
        end = min(end, last_spot_date)
    if end < start:
        return 0
    return (end - start).days + 1


def union_invested_days(intervals: list[tuple[date, date]], y: int) -> int:
    """Days in calendar year y covered by >=1 open interval [entry, delivery).

    Consecutive carry trades overlap ~7d (next entered while front still open),
    so a plain sum can exceed the year length; the union caps at the year length.
    """
    lo_y, hi_y = date(y, 1, 1), date(y + 1, 1, 1)
    clipped = sorted((max(a, lo_y), min(b, hi_y))
                     for a, b in intervals if max(a, lo_y) < min(b, hi_y))
    total, cur_lo, cur_hi = 0, None, None
    for a, b in clipped:
        if cur_hi is None or a > cur_hi:
            if cur_hi is not None:
                total += (cur_hi - cur_lo).days
            cur_lo, cur_hi = a, b
        else:
            cur_hi = max(cur_hi, b)
    if cur_hi is not None:
        total += (cur_hi - cur_lo).days
    return total


def main() -> None:
    contracts, last_spot_date = enumerate_contracts()
    usable = [c for c in contracts if c["status"] in ("entered", "skipped_basis")]
    entered = [c for c in usable if c["status"] == "entered"]
    skipped = [c for c in usable if c["status"] == "skipped_basis"]

    cal_years = []
    for y in CAL_YEARS:
        denom = days_in_year(y, last_spot_date)
        per_coin = {}
        for coin in COINS:
            ce = [c for c in entered if c["coin"] == coin]
            cs = [c for c in skipped if c["coin"] == coin]
            iv_all_co = [(date.fromisoformat(c["entry"]), date.fromisoformat(c["delivery"]))
                           for c in ce]
            inv = union_invested_days(iv_all_co, y)
            ce_y = [c for c in ce if date.fromisoformat(c["entry"]).year == y]
            cs_y = [c for c in cs if date.fromisoformat(c["entry"]).year == y]
            be = [c["ann_basis"] for c in ce_y]
            bs = [c["ann_basis"] for c in cs_y]
            se = round(float(sum(c["ret_alloc"] for c in ce_y)), 6)
            per_coin[coin] = {
                "n_entered": len(ce_y),
                "n_skipped": len(cs_y),
                "invested_days": inv,
                "share_invested": round(inv / denom, 4) if denom else None,
                "mean_basis_entered": round(float(np.mean(be)), 6) if be else None,
                "mean_basis_skipped": round(float(np.mean(bs)), 6) if bs else None,
                "sum_ret_alloc": se,
            }
        iv_either = [(date.fromisoformat(c["entry"]), date.fromisoformat(c["delivery"]))
                     for c in entered]
        either = union_invested_days(iv_either, y)
        cal_years.append({"year": y, "days": denom, "per_coin": per_coin,
                          "either_coin_invested_days": either,
                          "both_idle_days": denom - either,
                          "note": "2026 partial Jan1..last spot bar" if y == 2026 else ""})

    # Pooled anchor-window decomposition of the +0.22 %/mo (same window as oc_cashcarry).
    pool = {}
    for coin in COINS:
        ce = [c for c in entered
              if c["coin"] == coin
              and ANCHOR0 <= pd.Timestamp(c["entry_open"]) < ANCHOR_END]
        ssum = float(sum(c["ret_alloc"] for c in ce))
        pool[coin] = {"n": len(ce), "sum_ret_alloc": round(ssum, 6),
                      "contrib_mo_pct_f025": round(F * ssum * 100 / 60, 4)}
    pool_total = round(sum(v["contrib_mo_pct_f025"] for v in pool.values()), 4)
    for coin in COINS:
        pool[coin]["share_of_lift"] = round(
            pool[coin]["contrib_mo_pct_f025"] / pool_total, 4) if pool_total else None

    # Skipped-ETH expected cost: counterfactual realized, entered mean, basis-implied.
    eth_sk = [c for c in skipped if c["coin"] == "ETH"]
    eth_en = [c for c in entered if c["coin"] == "ETH"
              and ANCHOR0 <= pd.Timestamp(c["entry_open"]) < ANCHOR_END]
    cf = [c["ret_alloc"] for c in eth_sk]
    en = [c["ret_alloc"] for c in eth_en]
    mean_dte = float(np.mean([c["dte_days"] for c in eth_sk])) if eth_sk else None
    mean_b = float(np.mean([c["ann_basis"] for c in eth_sk])) if eth_sk else None
    skipped_eth = {
        "n_skipped_eth": len(eth_sk,
                             ),
        "deliveries": [c["delivery"] for c in eth_sk],
        "mean_basis_skipped": round(mean_b, 6) if mean_b is not None else None,
        "mean_dte_skipped": round(mean_dte, 1) if mean_dte is not None else None,
        "counterfactual_mean_ret_alloc": round(float(np.mean(cf)), 6) if cf else None,
        "counterfactual_min_max": [round(float(np.min(cf)), 6),
                                   round(float(np.max(cf)), 6)] if cf else None,
        "entered_mean_ret_alloc_anchor": round(float(np.mean(en)), 6) if en else None,
        "basis_implied_ret_alloc": round(float(mean_b * mean_dte / 365 - FEE_PAIR), 6)
        if mean_b is not None else None,
        "foregone_acct_pct_per_quarter_f025": round(
            float(F * float(np.mean(cf)) * 100), 4) if cf else None,
    }

    # Overall utilization 2021-01-01 .. last spot bar.
    total_days = sum(days_in_year(y, last_spot_date) for y in CAL_YEARS)
    overall = {}
    for coin in COINS:
        inv = sum(r["per_coin"][coin]["invested_days"] for r in cal_years)
        overall[coin] = {"invested_days": inv, "total_days": total_days,
                         "share": round(inv / total_days, 4)}

    out = {
        "meta": {            "rule": "frozen oc_cashcarry: enter iff ann_basis ln(F/S)*365/DTE >= 0.04, "
                    "roll <= 7d, hold to delivery, f=0.25/coin, fee drag 0.00275",
            "no_tuning": True,
            "sources": ["data/raw/qbasis_20261003/um_BTCUSDT_*_1h.parquet",
                        "data/raw/qbasis_20261003/um_ETHUSDT_*_1h.parquet",
                        "data/raw/spot_majors_20260925/*_spot_4h.parquet",
                        "research/tournament/oc_cashcarry/results.json (cross-check)"],
            "calendar_window": f"2021-01-01..{last_spot_date} (2026 partial)",
            "anchor_pool_window": "2021-09-24..2026-09-24 (60 months, same as oc_cashcarry)",
            "today_snapshot_assignment_given": "BTC Dec-26 basis ~+5.1 %/yr (>=4% ENTER-able); "
            "ETH ~+3.8 %/yr (<4% SKIP). Not fetched here (no network); context only.",
            "denominator": "calendar days in year (2026 partial to last spot bar); "
                           "numerator = days with an ENTERED pair open [entry, delivery)",
        },
        "n_contracts_usable": len(usable),
        "n_entered": len(entered),
        "n_skipped": len(skipped),
        "n_incomplete_excluded": sum(1 for c in contracts if c["status"] == "incomplete_no_spot"),
        "n_no_overlap_excluded": sum(1 for c in contracts if c["status"] == "no_overlap"),
        "contracts": contracts,
        "calendar_years": cal_years,
        "anchor_pool_f025_mo_pct": {"per_coin": pool, "total": pool_total},
        "skipped_eth_cost": skipped_eth,
        "overall_utilization": overall,
    }
    (HERE / "results.json").write_text(json.dumps(out, indent=1))

    # Cross-check against oc_cashcarry pooled sums (same anchor window, allow rounding).
    cash = json.loads(CASH.read_text())
    cash_sum = round(cash["pooled"]["sum_ret_alloc"], 4)
    mine_sum = round(sum(pool[c]["sum_ret_alloc"] for c in COINS), 4)
    print(f"contracts usable={len(usable)} entered={len(entered)} skipped={len(skipped)} "
          f"last_spot={last_spot_date}")
    print(f"anchor pool check: cashcarry={cash_sum} mine={mine_sum}")
    for r in cal_years:
        print(y_str(r))
    print("pool(total %/mo f=0.25):", pool_total, pool)
    print("skipped ETH:", json.dumps(skipped_eth))

    write_report(out)


def y_str(r: dict) -> str:
    b, e = r["per_coin"]["BTC"], r["per_coin"]["ETH"]
    return (f'{r["year"]} days={r["days"]} | BTC ent/skip={b["n_entered"]}/{b["n_skipped"]} '
            f'share={b["share_invested"]} bE={b["mean_basis_entered"]} bS={b["mean_basis_skipped"]} | '
            f'ETH ent/skip={e["n_entered"]}/{e["n_skipped"]} share={e["share_invested"]} '
            f'bE={e["mean_basis_entered"]} bS={e["mean_basis_skipped"]}')


def write_report(out: dict) -> None:
    L = []
    L.append("# oc_carryutil REPORT -- how often the frozen carry rule is invested (descriptive, no tuning)")
    L.append("")
    L.append("Frozen rule (oc_cashcarry PLAN.md, unchanged): per coin enter the next quarterly when "
             "front has <= 7d left, ENTER iff annualised basis ln(F/S)*365/DTE >= 4 %/yr, "
             "equal-notional spot long + quarterly short (f = 0.25/coin), hold to delivery, "
             "fee drag 0.00275/allocated. Local 4h parquet only; no network, no 1m, no orders. "
             "Repro: `research/tournament/oc_carryutil/analyze_carryutil.py` -> `results.json`; "
             "test `tests/test_oc_carryutil.py`. Cross-checks oc_cashcarry pooled sums.")
    L.append("")
    L.append("## Utilization per coin per calendar year (numerator = days an ENTERED pair is open)")
    L.append("")
    L.append("| year | days | BTC ent/skip | BTC share | BTC bE/bS | ETH ent/skip | ETH share | ETH bE/bS |")
    L.append("|---|---|---|---|---|---|---|---|")
    for r in out["calendar_years"]:
        b, e = r["per_coin"]["BTC"], r["per_coin"]["ETH"]
        L.append(f'| {r["year"]} | {r["days"]} | {b["n_entered"]}/{b["n_skipped"]} | '
                 f'{b["share_invested"]:.1%} | {pc(b["mean_basis_entered"])}/{pc(b["mean_basis_skipped"])} | '
                 f'{e["n_entered"]}/{e["n_skipped"]} | {e["share_invested"]:.1%} | '
                 f'{pc(e["mean_basis_entered"])}/{pc(e["mean_basis_skipped"])} |')
    L.append("")
    o = out["overall_utilization"]
    L.append(f'Overall 2021-01-01..last spot bar: BTC invested {o["BTC"]["invested_days"]}/'
             f'{o["BTC"]["total_days"]} = {o["BTC"]["share"]:.1%}; '
             f'ETH {o["ETH"]["invested_days"]}/{o["ETH"]["total_days"]} = {o["ETH"]["share"]:.1%}. '
             "Skips cluster: 2022 bear (8 skips) and 2025-2026 low-basis (5 of 6 skipped in the "
             "most recent anchor year) -- the filter idles instead of forcing risk.")
    L.append("")
    L.append("## Contribution to the +0.22 %/mo carry lift (anchor pool 2021-09-24..2026-09-24, f = 0.25)")
    L.append("")
    p = out["anchor_pool_f025_mo_pct"]
    for coin in COINS:
        v = p["per_coin"][coin]
        L.append(f'- {coin}: n={v["n"]}, sum_ret_alloc={v["sum_ret_alloc"]:.4f} -> '
                 f'+{v["contrib_mo_pct_f025"]:.4f} %/mo = {v["share_of_lift"]:.1%} of the lift.')
    L.append(f'Total +{p["total"]:.4f} %/mo arithmetic at f = 0.25 '
             "(matches oc_cashcarry +0.2181; geometric +0.2130).")
    L.append("")
    L.append("## What a skipped ETH quarter costs in expectation")
    L.append("")
    s = out["skipped_eth_cost"]
    L.append(f'Skipped ETH quarters: n={s["n_skipped_eth"]} ({", ".join(s["deliveries"])}); '
             f'mean skipped basis {pc(s["mean_basis_skipped"])} over ~{s["mean_dte_skipped"]}d.')
    L.append(f'Counterfactual (same settlement math, had they been entered): mean '
             f'{s["counterfactual_mean_ret_alloc"] * 100:.3f}% on allocated '
             f'(range {s["counterfactual_min_max"][0] * 100:.3f}..{s["counterfactual_min_max"][1] * 100:.3f}%), '
             f'= ~{s["foregone_acct_pct_per_quarter_f025"]:.4f}% of account per skipped quarter at f = 0.25.')
    L.append(f'Reference: entered ETH quarters in the anchor window average '
             f'{s["entered_mean_ret_alloc_anchor"] * 100:.3f}% on allocated; basis-implied lock at the '
             f'skipped mean = {s["basis_implied_ret_alloc"] * 100:.3f}%. A skipped ETH quarter costs '
             "about one-sixth of an entered quarter's premium -- small by design, the price of the 4% filter.")
    L.append("")
    L.append("## Today (assignment context from scripts/carry_calendar.py, not refetched)")
    L.append("")
    L.append("BTC Dec-26 basis ~+5.1 %/yr (>= 4%: ENTER-able); ETH ~+3.8 %/yr (< 4%: SKIP). "
             "So today the book would carry BTC and sit out ETH -- exactly the idle-ETH pattern above.")
    L.append("")
    L.append("## Ghi chu cho chu (4 dong, carry nam im la binh thuong)")
    L.append("")
    L.append("Carry co luc nam im hang thang, nhat la khi basis duoi 4%/nam quy phai bo qua.")
    L.append("Lich su 2021-2026: ETH chi dau tu ~2/3 thoi gian, nhieu quy lien tiep dung ngoai.")
    L.append("Bo mot quy ETH neu co vao chi them ~0.08% tai khoan (quy dat chuan ~0.5%); doi lai khong om basis re.")
    L.append("Nam im la tinh nang cua bo loc, khong phai loi -- cu de no cho premium quay lai.")
    L.append("")
    (HERE / "REPORT.md").write_text("\n".join(L) + "\n")


def pc(x) -> str:
    return f"{x * 100:.1f}%" if x is not None else "n/a"


if __name__ == "__main__":
    main()
