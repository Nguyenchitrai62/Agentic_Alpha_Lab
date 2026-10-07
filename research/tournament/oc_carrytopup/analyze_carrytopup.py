"""oc_carrytopup: delivery-week carry top-up (IDEAS3_20261006 idea 2).

Per PLAN.md (pre-registered, frozen): 7 days before each BTC/ETH quarterly
delivery, if that contract's annualised basis ln(F/S)*365/DTE >= 4%/yr,
enter an EXTRA spot + short pair at f = 0.125 per coin, hold to delivery;
same fees as the base sleeve (spot 0.001/side, fut 0.00055 entry + 0.0002
delivery => 0.00275 drag). Two series: Binance um_ quarterly proxy and
Bybit inverse quarterlies. Stacked cash check vs frozen base f = 0.25.

  python research/tournament/oc_carrytopup/analyze_carrytopup.py

4h data only, one process, RAM << 2 GB. No 1m. No commits.
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
KPI = ROOT / "research/tournament/oc_kpi_g2"

COINS = ["BTC", "ETH"]
ANCHORS = [pd.Timestamp(f"{y}-09-24", tz="UTC") for y in (2021, 2022, 2023, 2024, 2025)]
YEAR_LEN = pd.Timedelta(days=365)
THRESHOLD = 0.04
WINDOW_DAYS = 7
F_TOP = 0.125
F_BASE = 0.25
F_SPOT = 0.001
F_FUT_ENTRY = 0.00055
F_FUT_DELIV = 0.0002
FEE_PAIR = 2 * F_SPOT + F_FUT_ENTRY + F_FUT_DELIV  # 0.00275 per allocated unit
FEE_ENTRY_PAID = F_SPOT + F_FUT_ENTRY
GRID_START = pd.Timestamp("2021-09-24 00:00", tz="UTC")
CUT = pd.Timestamp("2026-09-24", tz="UTC")
UTA_WORST = pd.Timestamp("2025-09-25 18:00", tz="UTC")  # oc_utamargin worst hour


# ---------------- Binance proxy helpers (oc_cashcarry conventions) ----------------

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


def resample_binance(q: pd.DataFrame, spot: pd.DataFrame) -> np.ndarray:
    """Last 1h close with 1h open_time < spot close_time (causal)."""
    qo = q["open_time"].to_numpy(dtype="datetime64[ns]").astype(np.int64)
    qc = q["close"].to_numpy(dtype=float)
    sc = spot["close_time"].to_numpy(dtype="datetime64[ns]").astype(np.int64)
    idx = np.searchsorted(qo, sc, side="left") - 1
    out = np.full(len(spot), np.nan)
    ok = idx >= 0
    out[ok] = qc[idx[ok]]
    return out


# ---------------- Bybit inverse helpers (bybitq conventions) ----------------

def load_1h_bybit(path: Path) -> pd.DataFrame:
    d = pd.read_parquet(path, columns=["open_time", "close"])
    t = pd.to_datetime(d["open_time"], unit="ms", utc=True)
    return pd.DataFrame({"t": t, "close": d["close"].to_numpy(dtype=float)}).sort_values(
        "t").reset_index(drop=True)


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


def resample_bybit(f4: pd.DataFrame, spot: pd.DataFrame) -> np.ndarray:
    """Last futures 4h close with fut close_time <= spot close_time (causal)."""
    fo = f4["close_time"].to_numpy(dtype="datetime64[ns]").astype(np.int64)
    fc = f4["close"].to_numpy(dtype=float)
    sc = spot["close_time"].to_numpy(dtype="datetime64[ns]").astype(np.int64)
    idx = np.searchsorted(fo, sc, side="right") - 1
    out = np.full(len(spot), np.nan)
    ok = idx >= 0
    out[ok] = fc[idx[ok]]
    return out


# ---------------- core top-up leg (shared) ----------------

def run_topup(spot: pd.DataFrame, contracts: list[tuple[pd.Timestamp, np.ndarray]],
              label: str) -> dict:
    """spot: 4h DataFrame(open_time, close, close_time).
    contracts: [(D, F resampled on spot grid)]. One 7d-window shot each."""
    s_open = spot["open_time"]
    s_close_t = spot["close_time"]
    s_close = spot["close"].to_numpy(dtype=float)
    s_open_ns = s_open.to_numpy(dtype="datetime64[ns]").astype(np.int64)
    s_close_ns = s_close_t.to_numpy(dtype="datetime64[ns]").astype(np.int64)
    trades: list[dict] = []
    meta: list[dict] = []
    for coin, D, F in contracts:
        E = D - pd.Timedelta(days=WINDOW_DAYS)
        pos = int(np.searchsorted(s_open_ns, E.value, side="left"))  # round UP
        both = np.where(~np.isnan(s_close) & ~np.isnan(F))[0]
        both = both[both >= pos]
        if len(both) == 0:
            meta.append({"coin": coin, "delivery": str(D.date()), "status": "no_overlap"})
            continue
        ti = int(both[0])
        T_open = s_open.iloc[ti]
        T_close = s_close_t.iloc[ti]
        F_entry = float(F[ti])
        S_entry = float(s_close[ti])
        dte_days = (D - T_close).total_seconds() / 86400.0
        if not (np.isfinite(F_entry) and np.isfinite(S_entry)) or dte_days <= 0:
            meta.append({"coin": coin, "delivery": str(D.date()), "status": "bad_dte"})
            continue
        basis = float(np.log(F_entry / S_entry) * 365.0 / dte_days)
        si = int(np.searchsorted(s_close_ns, D.value, side="right"))
        if si >= len(spot):
            meta.append({"coin": coin, "delivery": str(D.date()),
                         "entry": str(T_open.date()), "ann_basis": round(basis, 6),
                         "dte_days": round(dte_days, 2), "status": "incomplete_no_spot"})
            continue
        S_del = float(s_close[si])
        entered = bool(basis >= THRESHOLD)
        rec: dict = {"coin": coin, "delivery": str(D.date()),
                     "entry_open": str(T_open), "entry_close": str(T_close),
                     "F_entry": F_entry, "S_entry": S_entry,
                     "S_del": S_del, "deliver_bar": str(s_open.iloc[si].date()),
                     "dte_days": round(dte_days, 2), "ann_basis": round(basis, 6),
                     "entered": entered, "ti": ti, "si": si,
                     "D_ns": int(D.value),
                     "Te_ns": int(s_close_t.iloc[ti].value)}
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
                rec["worst_mtm_date"] = str(
                    s_open.iloc[ti + 1: si + 1][okm].iloc[int(mtm.argmin())])
                rec["n_mtm_bars"] = int(okm.sum())
            trades.append(rec)
        meta.append({k: rec[k] for k in ("coin", "delivery", "ann_basis", "dte_days",
                                        "entered")}
                     | {"status": "entered" if entered else "skipped_basis",
                        "entry": str(T_open.date())})
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
                    "mean_dte": round(float(np.mean([r["dte_days"] for r in ct])), 2),
                    "mean_ret_alloc": round(float(np.mean([r["ret_alloc"] for r in ct])), 6),
                    "sum_ret_alloc": round(float(np.sum([r["ret_alloc"] for r in ct])), 6),
                    "worst_mtm_alloc": round(float(np.min([r["worst_mtm_alloc"] for r in ct])), 6),
                }
            else:
                per_coin[coin] = {"n": 0}
        tot_sum = round(float(sum(r["ret_alloc"] for r in yt)), 6)
        worst = round(float(min([r["worst_mtm_alloc"] for r in yt])), 6) if yt else None
        contrib = {"year_pct": round(float(F_TOP * tot_sum * 100), 4),
                   "per_month_pct": round(float(F_TOP * tot_sum * 100 / 12), 4)}
        acct_worst = round(float(F_TOP * worst * 100), 4) if worst is not None else None
        years.append({"year": str(a0.date()), "n_trades": len(yt),
                      "n_skipped_in_year": None, "per_coin": per_coin,
                      "sum_ret_alloc": tot_sum, "worst_mtm_alloc": worst,
                      "contrib_acct_pct": contrib, "worst_acct_pct": acct_worst,
                      "n_positive": sum(1 for r in yt if r["ret_alloc"] > 0),
                      "trades": [(r["coin"], r["delivery"], r["ann_basis"],
                                  r["ret_alloc"], r["worst_mtm_alloc"]) for r in yt]})
    for y in years:
        a0 = pd.Timestamp(y["year"], tz="UTC")
        a1 = a0 + YEAR_LEN
        y["n_skipped_in_year"] = len(
            [c for c in meta if c.get("status") == "skipped_basis"
             and a0 <= pd.Timestamp(c["entry"], tz="UTC") < a1])
    in_window = [r for r in trades if ANCHORS[0] <= r["entry_ts"] < ANCHORS[-1] + YEAR_LEN]
    pre_window = [r for r in trades if r["entry_ts"] < ANCHORS[0]]
    pooled_sum = float(sum(r["ret_alloc"] for r in in_window))
    fac = 1.0
    for y in years:
        fac *= 1.0 + F_TOP * y["sum_ret_alloc"]
    pooled = {"n_trades": len(in_window), "sum_ret_alloc": round(pooled_sum, 6),
              "n_pre_window_trades_excluded": len(pre_window),
              "pre_window_sum_ret_alloc_excluded": round(
                  float(sum(r["ret_alloc"] for r in pre_window)), 6),
              "total_acct_pct": round(float(F_TOP * pooled_sum * 100), 4),
              "per_month_pct": round(float(F_TOP * pooled_sum * 100 / 60), 4),
              "geom_per_month_pct": round(float((fac ** (1 / 60) - 1) * 100), 4),
              "n_years_positive": sum(1 for y in years if y["sum_ret_alloc"] > 0)}
    return {"label": label, "n_contracts_seen": len(meta), "n_trades": len(trades),
            "n_skipped": sum(1 for c in meta if c.get("status") == "skipped_basis"),
            "n_no_overlap": sum(1 for c in meta if c.get("status") == "no_overlap"),
            "n_incomplete": sum(1 for c in meta if c.get("status") == "incomplete_no_spot"),
            "years": years, "pooled": pooled,
            "trades": [{k: r[k] for k in ("coin", "delivery", "entry_open", "ann_basis",
                                         "dte_days", "ret_alloc", "worst_mtm_alloc",
                                         "F_entry", "S_entry", "S_del",
                                         "D_ns", "Te_ns")} for r in trades]}


def build_binance() -> tuple[dict, pd.DataFrame]:
    spot = {c: load_spot_binance(c) for c in COINS}
    assert (spot["BTC"]["open_time"].to_numpy()
            == spot["ETH"]["open_time"].to_numpy()).all()
    contracts = []
    for coin in COINS:
        s = spot[coin]
        qmap = load_q_1h_binance(coin)
        for D in sorted(qmap):
            contracts.append((coin, D, resample_binance(qmap[D], s)))
    return run_topup(spot["BTC"], contracts, "binance_proxy"), spot["BTC"]


def build_bybit() -> tuple[dict, pd.DataFrame]:
    inv = json.loads((BYBITQ / "inventory.json").read_text(encoding="utf-8"))["records"]
    spot4 = {c: to_4h(load_1h_bybit(BDIR / f"spot_{c}USDT_1h.parquet")) for c in COINS}
    contracts = []
    for coin in COINS:
        s = spot4[coin]
        rows = sorted([r for r in inv if r["baseCoin"] == coin and r["category"] == "inverse"],
                      key=lambda r: r["deliveryTime"])
        for r in rows:
            D = pd.Timestamp(r["deliveryTime"], unit="ms", tz="UTC")
            safe = r["symbol"].replace("-", "_")
            f4 = to_4h(load_1h_bybit(BDIR / f"inv_{safe}_1h.parquet"))
            contracts.append((coin, D, resample_bybit(f4, s)))
    return run_topup(spot4["BTC"], contracts, "bybit_inverse"), spot4["BTC"]


# ---------------- stacked cash check ----------------

def base_intervals(kind: str) -> list[tuple[int, int]]:
    """(entry_close_ns, delivery_ns) for frozen base pairs. Eq_entry=1 indexed."""
    out = []
    if kind == "binance":
        res = json.loads((OC / "results.json").read_text())
        for r in res["trades"]:
            te = pd.Timestamp(r["entry_open"], tz="UTC") + pd.Timedelta(hours=4)
            dd = pd.Timestamp(r["delivery"] + " 08:00", tz="UTC")
            out.append((int(te.value), int(dd.value)))
    else:
        res = json.loads((BYBITQ / "results_bybit_carry.json").read_text(encoding="utf-8"))
        inv = json.loads((BYBITQ / "inventory.json").read_text(encoding="utf-8"))["records"]
        dmap = {}
        for r in inv:
            if r["category"] == "inverse" and r["baseCoin"] in ("BTC", "ETH"):
                dmap[(r["baseCoin"],
                      pd.Timestamp(r["deliveryTime"], unit="ms", tz="UTC").date().isoformat())] \
                    = int(pd.Timestamp(r["deliveryTime"], unit="ms", tz="UTC").value)
        for t in res["inverse"]["trades"]:
            te = pd.Timestamp(t["entry_open"], tz="UTC") + pd.Timedelta(hours=4)
            out.append((int(te.value), dmap[(t["coin"], t["delivery"])]))
    return out


def load_eq_mix() -> tuple[np.ndarray, np.ndarray] | tuple[None, None]:
    try:
        eqs, ts = [], None
        for ph in range(4):
            b = pd.read_parquet(KPI / f"barsum_s{ph}.parquet", columns=["t", "equity"])
            b["t"] = pd.to_datetime(b["t"], utc=True)
            b = b.sort_values("t").reset_index(drop=True)
            if ts is None:
                ts = b["t"].to_numpy(dtype="datetime64[ns]").astype(np.int64)
            eqs.append(b["equity"].to_numpy(dtype=float))
        return np.stack(eqs).mean(0), ts
    except Exception:
        return None, None


def cash_check(grid: pd.DataFrame, base_iv: list[tuple[int, int]],
                top_trades: list[dict]) -> dict:
    g = grid[(grid["open_time"] >= GRID_START) & (grid["open_time"] < CUT)].reset_index(drop=True)
    tns = g["open_time"].to_numpy(dtype="datetime64[ns]").astype(np.int64)
    B = np.zeros(len(g))
    U = np.zeros(len(g))
    for te, dd in base_iv:
        B += ((tns >= te) & (tns < dd)).astype(float)
    top_iv = [(r["Te_ns"], r["D_ns"]) for r in top_trades]
    for te, dd in top_iv:
        U += ((tns >= te) & (tns < dd)).astype(float)
    C = F_BASE * B + F_TOP * U
    i_max = int(C.argmax())
    eq_mix, eq_ts = load_eq_mix()
    # Live-scaled (oc_carrycombo/utamargin sizing: legs = f x mix equity at
    # ENTRY hour, held; spot cost basis = f*Eq_entry, scaled by live Eq):
    # C_live(t) = sum_open f*Eq_entry[k]/Eq_mix(t). NOT C_idx/Eq (that
    # double-deflates once equity has compounded; fixed post-hoc, see PLAN).
    src = "oc_kpi_g2/barsum_s0..s3 mean equity (ffill)"
    C_live = None
    miss = None
    if eq_mix is None:
        miss = src + " MISSING -> analytic_only"
    else:
        def eq_at(qns: np.ndarray) -> np.ndarray:
            j = np.searchsorted(eq_ts, qns, side="right") - 1
            return eq_mix[np.maximum(j, 0)]
        Eq = eq_at(tns)
        TE = np.array([te for te, _ in base_iv] + [te for te, _ in top_iv])
        DD = np.array([dd for _, dd in base_iv] + [dd for _, dd in top_iv])
        FF = np.array([F_BASE] * len(base_iv) + [F_TOP] * len(top_iv))
        EQE = eq_at(TE)
        open_m = (tns[:, None] >= TE[None, :]) & (tns[:, None] < DD[None, :])
        C_live = (open_m * (FF * EQE)[None, :]).sum(1) / np.maximum(Eq, 1e-12)
    i_lmax = int(C_live.argmax()) if C_live is not None else i_max
    # utamargin worst hour -> containing 4h bar
    i_uta = int(np.searchsorted(tns, UTA_WORST.value, side="right") - 1)
    i_uta = max(min(i_uta, len(g) - 1), 0)
    return {
        "grid_bars": len(g),
        "grid_from": str(g["open_time"].min()), "grid_to": str(g["open_time"].max()),
        "max_C_idx": round(float(C.max()), 4),
        "max_bar": str(g["open_time"].iloc[i_max]),
        "max_B_open": int(B[i_max]), "max_U_open": int(U[i_max]),
        "max_C_live": (round(float(C_live.max()), 4) if C_live is not None else None),
        "max_C_live_bar": (str(g["open_time"].iloc[i_lmax])
                            if C_live is not None else None),
        "uta_bar": str(g["open_time"].iloc[i_uta]),
        "uta_B_open": int(B[i_uta]), "uta_U_open": int(U[i_uta]),
        "uta_C_idx": round(float(C[i_uta]), 4),
        "C_live_at_uta": (round(float(C_live[i_uta]), 4)
                          if C_live is not None else None),
        "eq_src": src if miss is None else miss,
        "borrow_needed": bool(C.max() > 1.0 or (C_live is not None
                                                and C_live.max() > 1.0)),
    }


def main() -> None:
    res_b, grid_b = build_binance()
    res_i, grid_i = build_bybit()
    cash = {"binance": cash_check(grid_b, base_intervals("binance"), res_b["trades"]),
            "bybit_inverse": cash_check(grid_i, base_intervals("bybit"), res_i["trades"])}
    verdict_in = {
        "binance_years_positive": res_b["pooled"]["n_years_positive"],
        "bybit_years_positive": res_i["pooled"]["n_years_positive"],
        "borrow_binance": cash["binance"]["borrow_needed"],
        "borrow_bybit": cash["bybit_inverse"]["borrow_needed"],
    }
    useful = (verdict_in["binance_years_positive"] >= 4
              and verdict_in["bybit_years_positive"] >= 4
              and not verdict_in["borrow_binance"]
              and not verdict_in["borrow_bybit"])
    out = {
        "meta": {
            "rule": "7d before each BTC/ETH quarterly delivery, ENTER iff ann_basis >= 4%/yr, "
                    "extra spot+short f=0.125/coin held to delivery; fees spot 0.001/side + "
                    "fut 0.00055 entry + 0.0002 delivery (drag 0.00275)",
            "f_topup": F_TOP, "f_base": F_BASE, "threshold_ann_basis": THRESHOLD,
            "window_days": WINDOW_DAYS,
            "settlement": "spot 4h close of delivery bar; incomplete (D past last spot bar) excluded",
            "binance_src": "data/raw/qbasis_20261003 um_* + spot_majors_20260925 (delivery = code date 08:00 UTC)",
            "bybit_src": "data/raw/bybit_quarterly_20261006 inv_* + Bybit spot (delivery = instruments-info "
                         "deliveryTime; coin-settlement convexity not modelled, as in bybitq recompute)",
            "base_src": "oc_cashcarry/results.json (33 Binance trades) + bybitq results_bybit_carry.json "
                        "inverse series, reused verbatim for the stacked cash check",
            "verdict_rule": "USEFUL iff >=4/5 years net>0 after fees on EACH venue AND no borrow on either stack; else CLOSE",
        },
        "binance": res_b,
        "bybit_inverse": res_i,
        "cash": cash,
        "verdict_inputs": verdict_in,
        "suggested_verdict": "USEFUL" if useful else "CLOSE",
    }
    (HERE / "results.json").write_text(json.dumps(out, indent=1))
    for tag, r in (("BIN", res_b), ("INV", res_i)):
        print(f"== {tag}: contracts={r['n_contracts_seen']} trades={r['n_trades']} "
              f"skipped={r['n_skipped']} no_overlap={r['n_no_overlap']} "
              f"incomplete={r['n_incomplete']}")
        for y in r["years"]:
            print(f"   {y['year']} n={y['n_trades']} skip={y['n_skipped_in_year']} "
                  f"sum_alloc={y['sum_ret_alloc']} acct%/mo={y['contrib_acct_pct']['per_month_pct']} "
                  f"worst={y['worst_mtm_alloc']}")
        print("   pooled:", json.dumps(r["pooled"]))
    print("cash:", json.dumps(cash, indent=1))
    print("verdict_inputs:", json.dumps(verdict_in), "suggested:", out["suggested_verdict"])


if __name__ == "__main__":
    main()
