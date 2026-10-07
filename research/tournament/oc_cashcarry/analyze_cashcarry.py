"""oc_cashcarry: locked cash-and-carry (long spot + short quarterly to delivery).

Per PLAN.md (pre-registered, frozen): one entry per quarterly contract
(enter next-quarter when front has <=7d left, or first availability),
enter iff annualised basis ln(F/S)*365/DTE >= 4%/yr, hold to delivery,
settlement = spot 4h close of delivery bar. Fees: spot 0.001/side,
futures 0.00055 entry + 0.0002 delivery. BTC+ETH only (um_ delivery files).
4h data only, one process, RAM << 2 GB.

  python research/tournament/oc_cashcarry/analyze_cashcarry.py
"""

from __future__ import annotations

import json
import pickle
import re
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
QDIR = ROOT / "data/raw/qbasis_20261003"
SDIR = ROOT / "data/raw/spot_majors_20260925"

COINS = ["BTC", "ETH"]
ANCHORS = [pd.Timestamp(f"{y}-09-24", tz="UTC") for y in (2021, 2022, 2023, 2024, 2025)]
YEAR_LEN = pd.Timedelta(days=365)
THRESHOLD = 0.04
ROLL_DAYS = 7
F_SPOT = 0.001
F_FUT_ENTRY = 0.00055
F_FUT_DELIV = 0.0002
FEE_PAIR = 2 * F_SPOT + F_FUT_ENTRY + F_FUT_DELIV  # 0.00275 per allocated unit
FEE_ENTRY_PAID = F_SPOT + F_FUT_ENTRY  # for MtM (exit fees not yet paid)
F_ROWS = [0.25, 0.5]
HAIRCUT = {"BTC": 0.05, "ETH": 0.10}  # ASSUMPTION (see PLAN.md)
LEV = 5
BLOCK_FRAC = 0.95
MMR = 0.005


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
    d = d.sort_values("open_time").reset_index(drop=True)
    return d


def load_q_1h(coin: str) -> dict:
    """expiry -> DataFrame(open_time, close) sorted; delivery from code."""
    out = {}
    for f in sorted(QDIR.glob(f"um_{coin}USDT_*_1h.parquet")):
        d = pd.read_parquet(f, columns=["open_time", "close"])
        d["open_time"] = pd.to_datetime(d["open_time"], utc=True)
        d = d.sort_values("open_time").reset_index(drop=True)
        out[parse_expiry(f.name)] = d
    return out


def resample_to_spot(q: pd.DataFrame, spot: pd.DataFrame) -> np.ndarray:
    """Last 1h close with 1h open_time < spot close_time (causal)."""
    qo = q["open_time"].to_numpy(dtype="datetime64[ns]").astype(np.int64)
    qc = q["close"].to_numpy(dtype=float)
    sc = spot["close_time"].to_numpy(dtype="datetime64[ns]").astype(np.int64)
    idx = np.searchsorted(qo, sc, side="left") - 1
    out = np.full(len(spot), np.nan)
    ok = idx >= 0
    out[ok] = qc[idx[ok]]
    return out


def main() -> None:
    spot = {c: load_spot(c) for c in COINS}
    # shared spot grid check: same open_time grid for BTC/ETH
    assert (spot["BTC"]["open_time"].to_numpy() == spot["ETH"]["open_time"].to_numpy()).all()

    trades: list[dict] = []
    contracts_meta: list[dict] = []
    f_series: dict[tuple[str, pd.Timestamp], np.ndarray] = {}

    for coin in COINS:
        s = spot[coin]
        s_open = s["open_time"]
        s_close_t = s["close_time"]
        s_close = s["close"].to_numpy(dtype=float)
        qmap = load_q_1h(coin)
        expiries = sorted(qmap)
        for k, D in enumerate(expiries):
            F = resample_to_spot(qmap[D], s)
            f_series[(coin, D)] = F
            prev_D = expiries[k - 1] if k > 0 else None
            if prev_D is not None:
                cand = prev_D - pd.Timedelta(days=ROLL_DAYS)
                # round UP to next spot open_time
                pos = int(np.searchsorted(s_open.to_numpy(dtype="datetime64[ns]").astype(np.int64),
                                          cand.value, side="left"))
            else:
                pos = 0
            both = np.where(s_close.__ne__(np.nan) & ~np.isnan(F))[0]
            both = both[both >= pos]
            if len(both) == 0:
                contracts_meta.append({"coin": coin, "delivery": str(D.date()),
                                       "status": "no_overlap"})
                continue
            ti = int(both[0])
            T_open = s_open.iloc[ti]
            T_close = s_close_t.iloc[ti]
            F_entry = float(F[ti])
            S_entry = float(s_close[ti])
            dte_days = (D - T_close).total_seconds() / 86400.0
            if not (np.isfinite(F_entry) and np.isfinite(S_entry)) or dte_days <= 0:
                contracts_meta.append({"coin": coin, "delivery": str(D.date()),
                                       "status": "bad_dte"})
                continue
            basis = float(np.log(F_entry / S_entry) * 365.0 / dte_days)
            # settlement: first spot bar with close_time > D
            si = int(np.searchsorted(s_close_t.to_numpy(dtype="datetime64[ns]").astype(np.int64),
                                             D.value, side="right"))
            if si >= len(s):
                contracts_meta.append({"coin": coin, "delivery": str(D.date()),
                                       "entry": str(T_open.date()),
                                       "ann_basis": round(basis, 6),
                                       "dte_days": round(dte_days, 2),
                                       "status": "incomplete_no_spot"})
                continue
            S_del = float(s_close[si])
            D_bar = str(s_open.iloc[si].date())
            entered = bool(basis >= THRESHOLD)
            rec: dict = {"coin": coin, "delivery": str(D.date()),
                         "entry_open": str(T_open), "entry_close": str(T_close),
                         "F_entry": F_entry, "S_entry": S_entry,
                         "S_del": S_del, "deliver_bar": D_bar,
                         "dte_days": round(dte_days, 2),
                         "ann_basis": round(basis, 6),
                         "entered": entered, "ti": ti, "si": si}
            if entered:
                gross = (S_del - S_entry) / S_entry + (F_entry - S_del) / F_entry
                ret_alloc = float(gross - FEE_PAIR)
                rec["ret_alloc"] = round(ret_alloc, 6)
                rec["gross_locked"] = round(float(gross), 6)
                # worst MtM over (ti, si]
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
                    rec["worst_mtm_date"] = str(s_open.iloc[ti + 1: si + 1][okm].iloc[int(mtm.argmin())])
                    rec["n_mtm_bars"] = int(okm.sum())
                trades.append(rec)
            contracts_meta.append({k2: rec[k2] for k2 in
                                   ("coin", "delivery", "ann_basis", "dte_days", "entered")
                                   } | {"status": "entered" if entered else "skipped_basis",
                                        "entry": str(T_open.date())})
    # ---- per anchor year (grouped by ENTRY open_time) ----
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
        contrib = {str(f): {"year_pct": round(float(f * tot_sum * 100), 4),
                            "per_month_pct": round(float(f * tot_sum * 100 / 12), 4)}
                   for f in F_ROWS}
        acct_worst = {str(f): (round(float(f * worst * 100), 4) if worst is not None else None)
                      for f in F_ROWS}
        years.append({"year": str(a0.date()), "n_trades": len(yt),
                      "n_skipped_in_year": None, "per_coin": per_coin,
                      "sum_ret_alloc": tot_sum, "worst_mtm_alloc": worst,
                      "contrib_acct_pct": contrib, "worst_acct_pct": acct_worst,
                      "trades": [(r["coin"], r["delivery"], r["ann_basis"],
                                  r["ret_alloc"], r["worst_mtm_alloc"]) for r in yt]})
    # skipped counts per year (entry opportunities that failed the filter)
    for y in years:
        a0 = pd.Timestamp(y["year"], tz="UTC")
        a1 = a0 + YEAR_LEN
        sk = [c for c in contracts_meta
              if c.get("status") == "skipped_basis"
              and a0 <= pd.Timestamp(c["entry"], tz="UTC") < a1]
        y["n_skipped_in_year"] = len(sk)

    in_window = [r for r in trades
                 if ANCHORS[0] <= r["entry_ts"] < ANCHORS[-1] + YEAR_LEN]
    pre_window = [r for r in trades if r["entry_ts"] < ANCHORS[0]]
    pooled_sum = float(sum(r["ret_alloc"] for r in in_window))
    pooled = {"n_trades": len(in_window), "sum_ret_alloc": round(pooled_sum, 6),
              "n_pre_window_trades_excluded": len(pre_window),
              "pre_window_sum_ret_alloc_excluded": round(float(sum(
                  r["ret_alloc"] for r in pre_window)), 6),
              "per_f": {str(f): {"total_acct_pct": round(float(f * pooled_sum * 100), 4),
                                 "per_month_pct": round(float(f * pooled_sum * 100 / 60), 4)}
                        for f in F_ROWS}}
    # geometric-mean monthly equivalent of the carry sleeve at f:
    # compound yearly account factors (1 + f*year_sum) over 5 years
    for f in F_ROWS:
        fac = 1.0
        for y in years:
            fac *= (1.0 + f * y["sum_ret_alloc"])
        pooled["per_f"][str(f)]["geom_per_month_pct"] = round(float((fac ** (1 / 60) - 1) * 100), 4)

    # ---- margin check (time-varying, per phase + mix-envelope) ----
    margin_src = "analytic_only"
    margin: dict = {}
    try:
        bsm = {}
        for ph in range(4):
            p = ROOT / f"research/tournament/oc_kpi_g2/barsum_s{ph}.parquet"
            b = pd.read_parquet(p)
            b["t"] = pd.to_datetime(b["t"], utc=True)
            bsm[ph] = b.sort_values("t").reset_index(drop=True)
        # v421 availability note
        v421_ok = (ROOT / "research/parallel/rounds/parallel-20260906-r2/v421/v421_runs.pkl").exists()
        margin_src = ("barsum_s0..s3_book_gross_plus_G2_dip_cap_2.0"
                      + (";v421_runs_present" if v421_ok else ";v421_runs_missing"))
        s0 = spot["BTC"]  # shared grid
        s_open_ns = s0["open_time"].to_numpy(dtype="datetime64[ns]").astype(np.int64)
        s_close_all = s0["close"].to_numpy(dtype=float)
        f_by_cd: dict = {(c, str(D.date())): arr for (c, D), arr in f_series.items()}
        # open-trade list with index ranges (ti, si] on the spot grid
        for f in F_ROWS:
            per_phase = {}
            worst = 0.0
            for ph, b in bsm.items():
                bt = b["t"].to_numpy(dtype="datetime64[ns]").astype(np.int64)
                # map each barsum time to last spot bar with open_time <= t
                sp_idx = np.searchsorted(s_open_ns, bt, side="right") - 1
                book = b["gross_book"].to_numpy(dtype=float)
                eq = b["equity"].to_numpy(dtype=float)
                max_ratio = 0.0
                worst_t = None
                for i in range(len(b)):
                    j = sp_idx[i]
                    if j < 0 or eq[i] <= 0:
                        continue
                    # carry short notional / current BOT equity
                    cs = 0.0
                    cu = 0.0  # carry unreal / BOT equity
                    for r in trades:
                        Dd = pd.Timestamp(r["delivery"] + " 08:00", tz="UTC").value \
                            if len(r["delivery"]) == 10 else None
                        Te = pd.Timestamp(r["entry_open"]).value
                        tt = bt[i]
                        if Te <= tt < (Dd if Dd else np.inf):
                            Fnow_arr = f_by_cd.get((r["coin"], r["delivery"]))
                            if Fnow_arr is None or j >= len(Fnow_arr):
                                continue
                            Fnow = float(Fnow_arr[j])
                            if not np.isfinite(Fnow):
                                continue
                            cs += f * (Fnow / r["F_entry"]) / eq[i]
                            # unreal approx (entry-indexed, Eq_entry=1)
                            Snow = float(s_close_all[j])
                            if np.isfinite(Snow):
                                mtm = ((Snow / r["S_entry"] - 1.0)
                                       + ((r["F_entry"] - Fnow) / r["F_entry"])
                                       - FEE_ENTRY_PAID)
                                cu += f * mtm / eq[i]
                    G_bot = float(book[i]) + 2.0  # book leg + G2 dip cap
                    G_bot = max(G_bot, 0.0)
                    im = (G_bot + cs) / LEV
                    eq_tot_over_bot = 1.0 + cu
                    ratio = im / max(eq_tot_over_bot, 1e-9)
                    if ratio > max_ratio:
                        max_ratio = ratio
                        worst_t = str(b["t"].iloc[i])
                per_phase[f"s{ph}"] = {"max_IM_over_equity": round(float(max_ratio), 4),
                                       "blocked_any": bool(max_ratio > BLOCK_FRAC),
                                       "worst_t": worst_t}
                worst = max(worst, max_ratio)
            margin[str(f)] = {"per_phase": per_phase,
                              "worst_IM_over_equity": round(float(worst), 4),
                              "blocked_any": bool(worst > BLOCK_FRAC)}
    except Exception as e:  # keep analytic fallback visible, never silent
        margin = {"error": f"{type(e).__name__}: {e}", "per_f": {}}

    out = {
        "meta": {
            "fees": {"spot_per_side": F_SPOT, "fut_entry": F_FUT_ENTRY,
                     "fut_delivery": F_FUT_DELIV, "pair_drag": FEE_PAIR},
            "threshold_ann_basis": THRESHOLD,
            "roll_days": ROLL_DAYS,
            "delivery_rule": "08:00 UTC on code date; settlement = spot 4h close of delivery bar",
            "contracts": "um_BTCUSDT_*/um_ETHUSDT_* quarterly delivery (no funding); cm_* unused",
            "margin_src": margin_src,
            "haircut_assumption": {"BTC": 0.05, "ETH": 0.10,
                                   "note": "ASSUMPTION: no Bybit haircut table found in repo"},
            "spot_last": str(spot["BTC"]["open_time"].max()),
        },
        "n_contracts_seen": len(contracts_meta),
        "n_trades": len(trades),
        "n_skipped": sum(1 for c in contracts_meta if c.get("status") == "skipped_basis"),
        "n_incomplete": sum(1 for c in contracts_meta if c.get("status") == "incomplete_no_spot"),
        "years": years,
        "pooled": pooled,
        "margin": margin,
        "trades": [{k: r[k] for k in ("coin", "delivery", "entry_open", "ann_basis",
                                      "dte_days", "ret_alloc", "worst_mtm_alloc",
                                      "F_entry", "S_entry", "S_del")} for r in trades],
    }
    (HERE / "results.json").write_text(json.dumps(out, indent=1))
    print(f"contracts={len(contracts_meta)} trades={len(trades)} "
          f"skipped={out['n_skipped']} incomplete={out['n_incomplete']}")
    for y in years:
        print(y["year"], "n=", y["n_trades"], "skip=", y["n_skipped_in_year"],
              "sum_alloc=", y["sum_ret_alloc"], "worst=", y["worst_mtm_alloc"],
              "contrib025/mo=", y["contrib_acct_pct"]["0.25"]["per_month_pct"],
              "contrib05/mo=", y["contrib_acct_pct"]["0.5"]["per_month_pct"])
    print("pooled:", json.dumps(pooled))
    print("margin:", json.dumps(margin))


if __name__ == "__main__":
    main()
