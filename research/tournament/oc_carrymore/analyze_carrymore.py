"""oc_carrymore: SAME oc_cashcarry rule (UNCHANGED, no new thresholds) on
Binance COIN-M quarterly delivery contracts, extended to BNB/SOL/XRP.

Assignment: docs/opencode/OPENCODE_W_oc_carrymore.md
Writes ONLY: research/tournament/oc_carrymore/results.json (this folder).
Scratch (if any): research/tournament/oc_carrymore/tmp/. No commits.
Public data only (data.binance.vision COIN-M `futures/cm` + spot archives,
cached under data/raw/qbasis_20261003 and data/raw/spot_majors_20260925).

Rule frozen in research/tournament/oc_cashcarry/PLAN.md, repeated unchanged:
  one entry per quarterly contract (next-quarter when front has <= 7d left,
  else first availability), ENTER iff annualised basis
  ln(F/S)*365/DTE >= 4 %/yr, long spot + short quarterly in equal notional
  (f per coin), hold to delivery (settlement = spot 4h close of the delivery
  bar). Fees: spot 0.001/side, futures 0.00055 entry + 0.0002 delivery
  (drag 0.00275 of allocated). Delivery D = 08:00 UTC on the code date
  (matches every cm manifest last_open_time).
  COIN-M note: cm contracts are coin-margined (prices in USD, same scale as
  USDT spot, so ln(F/S) + price-return P&L apply unchanged; coin-settlement
  convexity is noted, not modelled -- same approximation as the Bybit
  inverse-quarterly recompute in research/data_fetch/bybitq).

Steps: (1) inventory cm quarterlies per coin (see fetch_cm_quarterly.py +
  MANIFEST.json); (2) replicate on BTC/ETH COIN-M, compare with the
  Bybit-based oc_cashcarry (um) trades as sanity; (3) run on BNB/SOL/XRP;
  (4) overlay on G2 with the oc_carrycompound compounded method REUSED
  UNCHANGED at f = 0.25 per coin for (a) BTC+ETH only, (b) all majors.
  Everything is POST-HOC (years seen). 4h + 1h data only, one process.

  .venv/Scripts/python.exe scripts/heavy_slot.py run --tag oc_carrymore --min-free-gb 2.0 -- .venv/Scripts/python.exe research/tournament/oc_carrymore/analyze_carrymore.py
"""

from __future__ import annotations

import importlib.util
import json
import pickle
import re
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
QDIR = ROOT / "data" / "raw" / "qbasis_20261003"
SDIR = ROOT / "data" / "raw" / "spot_majors_20260925"
CC = ROOT / "research" / "tournament" / "oc_cashcarry"
CCP = ROOT / "research" / "tournament" / "oc_carrycompound"
RD = ROOT / "research" / "parallel" / "rounds" / "parallel-20260906-r2"
V421 = RD / "v421" / "v421_runs.pkl"
HOURLY = ROOT / "research" / "tournament" / "ext" / "hourly_ext.parquet"

COINS = ["BTC", "ETH", "BNB", "SOL", "XRP"]
ANCHORS = [pd.Timestamp(f"{y}-09-24", tz="UTC") for y in (2021, 2022, 2023, 2024, 2025)]
YEAR_LEN = pd.Timedelta(days=365)
THRESHOLD = 0.04
ROLL_DAYS = 7
F_SPOT = 0.001
F_FUT_ENTRY = 0.00055
F_FUT_DELIV = 0.0002
FEE_PAIR = 2 * F_SPOT + F_FUT_ENTRY + F_FUT_DELIV  # 0.00275
FEE_ENTRY_PAID = F_SPOT + F_FUT_ENTRY
F_COIN = 0.25
CAP = pd.Timestamp("2026-09-24 00:00", tz="UTC")


def parse_expiry_cm(fname: str) -> pd.Timestamp:
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


def load_cm_1h(coin: str) -> dict:
    out = {}
    for f in sorted(QDIR.glob(f"cm_{coin}USD_*_1h.parquet")):
        d = pd.read_parquet(f, columns=["open_time", "close"])
        d["open_time"] = pd.to_datetime(d["open_time"], utc=True)
        out[parse_expiry_cm(f.name)] = d.sort_values("open_time").reset_index(drop=True)
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


def run_rule(coin: str, spot: pd.DataFrame, qmap: dict) -> tuple[list, list]:
    """SAME rule as oc_cashcarry/analyze_cashcarry.py, per-coin spot grid."""
    s_open = spot["open_time"]
    s_close_t = spot["close_time"]
    s_close = spot["close"].to_numpy(dtype=float)
    expiries = sorted(qmap)
    trades, meta = [], []
    f_series = {}
    for k, D in enumerate(expiries):
        F = resample_to_spot(qmap[D], spot)
        f_series[D] = F
        if k > 0:
            cand = expiries[k - 1] - pd.Timedelta(days=ROLL_DAYS)
            pos = int(np.searchsorted(
                s_open.to_numpy(dtype="datetime64[ns]").astype(np.int64),
                cand.value, side="left"))
        else:
            pos = 0
        both = np.where(~np.isnan(s_close) & ~np.isnan(F))[0]
        both = both[both >= pos]
        if len(both) == 0:
            meta.append({"coin": coin, "delivery": str(D.date()), "status": "no_overlap"})
            continue
        ti = int(both[0])
        T_open, T_close = s_open.iloc[ti], s_close_t.iloc[ti]
        F_entry, S_entry = float(F[ti]), float(s_close[ti])
        dte_days = (D - T_close).total_seconds() / 86400.0
        if not (np.isfinite(F_entry) and np.isfinite(S_entry)) or dte_days <= 0:
            meta.append({"coin": coin, "delivery": str(D.date()), "status": "bad_dte"})
            continue
        basis = float(np.log(F_entry / S_entry) * 365.0 / dte_days)
        si = int(np.searchsorted(
            s_close_t.to_numpy(dtype="datetime64[ns]").astype(np.int64),
            D.value, side="right"))
        if si >= len(spot):
            meta.append({"coin": coin, "delivery": str(D.date()),
                         "entry": str(T_open.date()), "ann_basis": round(basis, 6),
                         "dte_days": round(dte_days, 2), "status": "incomplete_no_spot"})
            continue
        S_del = float(s_close[si])
        entered = bool(basis >= THRESHOLD)
        rec = {"coin": coin, "delivery": str(D.date()),
               "entry_open": str(T_open), "entry_close": str(T_close),
               "F_entry": F_entry, "S_entry": S_entry, "S_del": S_del,
               "deliver_bar": str(s_open.iloc[si].date()),
               "dte_days": round(dte_days, 2), "ann_basis": round(basis, 6),
               "entered": entered, "ti": ti, "si": si}
        if entered:
            gross = (S_del - S_entry) / S_entry + (F_entry - S_del) / F_entry
            rec["ret_alloc"] = round(float(gross - FEE_PAIR), 6)
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
        meta.append({"coin": coin, "delivery": str(D.date()),
                     "ann_basis": rec["ann_basis"], "dte_days": rec["dte_days"],
                     "entered": entered,
                     "status": "entered" if entered else "skipped_basis",
                     "entry": str(T_open.date())})
    return trades, meta


def year_table(trades: list, metas: list, coins: list) -> tuple[list, dict]:
    for r in trades:
        r["entry_ts"] = pd.Timestamp(r["entry_open"])
    years = []
    for a0 in ANCHORS:
        a1 = a0 + YEAR_LEN
        yt = [r for r in trades if a0 <= r["entry_ts"] < a1]
        per_coin = {}
        for coin in coins:
            ct = [r for r in yt if r["coin"] == coin]
            per_coin[coin] = {
                "n": len(ct),
                **({"mean_ann_basis": round(float(np.mean([r["ann_basis"] for r in ct])), 6),
                    "mean_dte": round(float(np.mean([r["dte_days"] for r in ct])), 1),
                    "mean_ret_alloc": round(float(np.mean([r["ret_alloc"] for r in ct])), 6),
                    "sum_ret_alloc": round(float(np.sum([r["ret_alloc"] for r in ct])), 6),
                    "worst_mtm_alloc": round(float(np.min([r["worst_mtm_alloc"] for r in ct])), 6)}
                   if ct else {})}
        tot = round(float(sum(r["ret_alloc"] for r in yt)), 6)
        worst = round(float(min([r["worst_mtm_alloc"] for r in yt])), 6) if yt else None
        years.append({"year": str(a0.date()), "n_trades": len(yt),
                      "per_coin": per_coin, "sum_ret_alloc": tot,
                      "worst_mtm_alloc": worst,
                      "trades": [(r["coin"], r["delivery"], r["ann_basis"],
                                  r["ret_alloc"], r["worst_mtm_alloc"]) for r in yt]})
    for y in years:
        a0 = pd.Timestamp(y["year"], tz="UTC")
        a1 = a0 + YEAR_LEN
        y["n_skipped_in_year"] = sum(
            1 for c in metas if c.get("status") == "skipped_basis"
            and a0 <= pd.Timestamp(c["entry"], tz="UTC") < a1)
    in_w = [r for r in trades if ANCHORS[0] <= r["entry_ts"] < ANCHORS[-1] + YEAR_LEN]
    pre = [r for r in trades if r["entry_ts"] < ANCHORS[0]]
    psum = float(sum(r["ret_alloc"] for r in in_w))
    fac = 1.0
    for y in years:
        fac *= 1.0 + F_COIN * y["sum_ret_alloc"]
    pooled = {"n_trades": len(in_w), "sum_ret_alloc": round(psum, 6),
              "n_pre_window_excluded": len(pre),
              "pre_window_sum_excluded": round(float(sum(r["ret_alloc"] for r in pre)), 6),
              "acct_total_pct_f025": round(F_COIN * psum * 100, 4),
              "acct_per_month_pct_f025": round(F_COIN * psum * 100 / 60, 4),
              "geom_per_month_pct_f025": round(float((fac ** (1 / 60) - 1) * 100), 4)}
    return years, pooled


# ---------- compound overlay (method REUSED UNCHANGED from oc_carrycompound) ----------

def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def last_close_before(times_ns: np.ndarray, closes: np.ndarray, ts_ns: np.ndarray) -> np.ndarray:
    """Close of the last bar with bar_time strictly before each query time."""
    idx = np.searchsorted(times_ns, ts_ns, side="left") - 1
    out = np.full(len(ts_ns), np.nan)
    ok = idx >= 0
    out[ok] = closes[idx[ok]]
    return out


def run_compound(label: str, trade_recs: list, fut_1h: dict, spot_h: dict,
                 grid, gn, n: int, ANCH, Es, Ms, Etot, Mtot, v388) -> dict:
    """ONE account A(t)=A(t-1)*(1+r_bot(t))+dU(t); f=0.25 per coin.
    Verbatim method of oc_carrycompound/analyze_carrycompound.py."""
    YEAR = pd.Timedelta(days=365)
    trades = []
    s4 = pd.read_parquet(SDIR / "BTCUSDT_spot_4h.parquet", columns=["open_time", "close_time"])
    s4o = pd.to_datetime(s4["open_time"], utc=True)
    s4c = pd.to_datetime(s4["close_time"], utc=True)
    for t in trade_recs:
        te = pd.Timestamp(t["entry_open"], tz="UTC")
        tc = te + pd.Timedelta(hours=4)
        D = pd.Timestamp(t["delivery"] + " 08:00", tz="UTC")
        si = int(np.searchsorted(s4c.values.astype("datetime64[ns]").astype(np.int64),
                                 D.value, side="right"))
        ts = s4c.iloc[si]
        trades.append({"coin": t["coin"], "delivery": t["delivery"],
                       "F_entry": float(t["F_entry"]), "S_entry": float(t["S_entry"]),
                       "ret_alloc": float(t["ret_alloc"]),
                       "tc_ns": tc.value, "ts_ns": ts.value})
    for tr in trades:
        st, sc = spot_h[tr["coin"]]
        ft, fc = fut_1h[(tr["coin"], tr["delivery"])]
        S = last_close_before(st, sc, gn)
        F = last_close_before(ft, fc, gn)
        with np.errstate(divide="ignore", invalid="ignore"):
            mtm = ((S / tr["S_entry"] - 1.0)
                   + ((tr["F_entry"] - F) / tr["F_entry"]) - FEE_ENTRY_PAID)
        mtm[~np.isfinite(mtm)] = np.nan
        mtm = pd.Series(mtm, index=grid).ffill().to_numpy()
        v = np.zeros(n)
        open_m = gn > tr["tc_ns"]
        settled_m = gn >= tr["ts_ns"]
        hold_m = open_m & ~settled_m
        v[hold_m] = mtm[hold_m]
        v[hold_m & ~np.isfinite(mtm)] = 0.0
        v[settled_m] = tr["ret_alloc"]
        tr["mtm"] = v

    def mtm_at_anchor(tr, a_ns: int) -> float:
        if a_ns <= tr["tc_ns"]:
            return 0.0
        if a_ns >= tr["ts_ns"]:
            return float(tr["ret_alloc"])
        st, sc = spot_h[tr["coin"]]
        ft, fc = fut_1h[(tr["coin"], tr["delivery"])]
        qa = np.array([a_ns])
        S = last_close_before(st, sc, qa)[0]
        F = last_close_before(ft, fc, qa)[0]
        if np.isfinite(S) and np.isfinite(F) and tr["F_entry"] and tr["S_entry"]:
            return float((S / tr["S_entry"] - 1.0)
                         + ((tr["F_entry"] - F) / tr["F_entry"]) - FEE_ENTRY_PAID)
        return 0.0

    a_ns_all = np.array([a.value for a in ANCH])
    anchor_mtm = np.array([[mtm_at_anchor(tr, a) for tr in trades] for a in a_ns_all])
    f = F_COIN
    years = []
    for y, a0 in enumerate(ANCH):
        a1 = a0 + YEAR
        seg = (grid > a0) & (grid <= a1)
        idx = np.where(np.asarray(seg))[0]
        le = gn <= a0.value
        b = np.array([float(Es[s][le][-1]) if le.any() else 1.0 for s in range(4)])
        E4 = [Es[s][idx] / b[s] for s in range(4)]
        M4 = [Ms[s][idx] / b[s] for s in range(4)]
        es = np.mean(E4, axis=0)
        ms = np.mean(M4, axis=0)
        es_prev = np.concatenate([[1.0], es[:-1]])
        g = es / es_prev
        hh = ms / es_prev
        mtm_a = anchor_mtm[y]
        rel = [k for k, tr in enumerate(trades) if tr["tc_ns"] < a1.value and tr["ts_ns"] > a0.value]
        span = {k for k in rel if trades[k]["tc_ns"] <= a0.value}
        N = {k: f * 1.0 for k in span}
        mtm_seg = {k: trades[k]["mtm"][idx] - mtm_a[k] for k in rel}
        A_prev, U_prev = 1.0, 0.0
        A_arr = np.empty(len(idx))
        M_arr = np.empty(len(idx))
        tc_map: dict[int, list[int]] = {}
        for k in rel:
            if k in span:
                continue
            pos = int(np.searchsorted(gn[idx], trades[k]["tc_ns"], side="right"))
            if 0 <= pos < len(idx):
                tc_map.setdefault(pos, []).append(k)
        U_open: dict[int, float] = dict(N)
        for i in range(len(idx)):
            for k in tc_map.get(i, []):
                U_open[k] = f * A_prev
            U_i = sum(nk * mtm_seg[k][i] for k, nk in U_open.items())
            dU = U_i - U_prev
            A_arr[i] = A_prev * g[i] + dU
            M_arr[i] = A_prev * hh[i] + dU
            A_prev, U_prev = A_arr[i], U_i
        pk = np.maximum.accumulate(A_arr)
        R = round(100 * float(A_arr[-1] ** (1 / 12) - 1), 3)
        DD = round(100 * float(np.max(1 - M_arr / pk)), 2)
        years.append({"anchor": str(a0.date()), "R": R, "DD": DD,
                      "end": round(float(A_arr[-1]), 6)})
    R5 = round(float(np.prod([1 + yy["R"] / 100 for yy in years]) ** (1 / 5) - 1) * 100, 3)
    # continuous full-path pass
    A_c = np.empty(n)
    M_c = np.empty(n)
    g0_mtm = np.array([mtm_at_anchor(tr, gn[0]) for tr in trades])
    rel_c = [k for k, tr in enumerate(trades) if tr["ts_ns"] > gn[0]]
    span_c = {k for k in rel_c if trades[k]["tc_ns"] <= gn[0]}
    N_c: dict[int, float] = {k: f * float(Etot[0]) for k in span_c}
    mtm_r = {k: trades[k]["mtm"] - g0_mtm[k] for k in rel_c}
    tc_pos: dict[int, list[int]] = {}
    for k in rel_c:
        if k in span_c:
            continue
        pos = int(np.searchsorted(gn, trades[k]["tc_ns"], side="right"))
        if 0 <= pos < n:
            tc_pos.setdefault(pos, []).append(k)
    A_c[0], M_c[0] = float(Etot[0]), float(Mtot[0])
    A_prev = float(Etot[0])
    U_prev = 0.0
    U_open_c: dict[int, float] = dict(N_c)
    for i in range(1, n):
        for k in tc_pos.get(i, []):
            U_open_c[k] = f * A_prev
        U_i = sum(nk * mtm_r[k][i] for k, nk in U_open_c.items())
        dU = U_i - U_prev
        A_c[i] = A_prev * (Etot[i] / Etot[i - 1]) + dU
        M_c[i] = A_prev * (Mtot[i] / Etot[i - 1]) + dU
        A_prev, U_prev = A_c[i], U_i
    segf = np.asarray(grid > pd.Timestamp("2021-09-24", tz="UTC"))
    esf, msf = A_c[segf], M_c[segf]
    dd_m = round(100 * float(np.max(1 - msf / np.maximum.accumulate(esf))), 2)
    dd_c = round(100 * float(np.max(1 - esf / np.maximum.accumulate(esf))), 2)
    return {"label": label, "years": years, "R": R5,
            "W": min(yy["R"] for yy in years), "DD": max(yy["DD"] for yy in years),
            "losing": sum(yy["R"] < 0 for yy in years),
            "full_path_dd": {"marked": dd_m, "close": dd_c, "full": max(dd_m, dd_c)}}


def main() -> None:
    all_trades, all_meta = [], []
    per_coin_summary = {}
    for coin in COINS:
        spot = load_spot(coin)
        qmap = load_cm_1h(coin)
        trades, meta = run_rule(coin, spot, qmap)
        all_trades.extend(trades)
        all_meta.extend(meta)
        n_in = sum(1 for r in trades
                 if ANCHORS[0] <= pd.Timestamp(r["entry_open"]) < ANCHORS[-1] + YEAR_LEN)
        per_coin_summary[coin] = {
            "n_contracts": len(meta),
            "n_entered_total": len(trades),
            "n_entered_in_window": n_in,
            "n_skipped": sum(1 for c in meta if c.get("status") == "skipped_basis"),
            "n_incomplete": sum(1 for c in meta if c.get("status") == "incomplete_no_spot"),
            "first_delivery": meta[0]["delivery"] if meta else None,
            "last_delivery": meta[-1]["delivery"] if meta else None,
        }
        print(f"{coin}: contracts={len(meta)} entered={len(trades)} "
              f"in_window={n_in} skipped={per_coin_summary[coin]['n_skipped']} "
              f"incomplete={per_coin_summary[coin]['n_incomplete']}")

    years_all, pooled_all = year_table(all_trades, all_meta, COINS)
    bteth = [r for r in all_trades if r["coin"] in ("BTC", "ETH")]
    years_be, pooled_be = year_table(bteth, [c for c in all_meta if c["coin"] in ("BTC", "ETH")],
                                     ["BTC", "ETH"])
    for y in years_all:
        print(y["year"], "n=", y["n_trades"], "skip=", y["n_skipped_in_year"],
              "sum_alloc=", y["sum_ret_alloc"], "worst=", y["worst_mtm_alloc"])

    # ---- sanity: cm BTC/ETH vs oc_cashcarry um BTC/ETH ----
    cc = json.loads((CC / "results.json").read_text())
    um_by_deliv = {(t["coin"], t["delivery"]): t for t in cc["trades"]}
    cm_be_by_deliv = {(t["coin"], t["delivery"]): t for t in bteth}
    common = sorted(set(um_by_deliv) & set(cm_be_by_deliv))
    d_basis = [cm_be_by_deliv[k]["ann_basis"] - um_by_deliv[k]["ann_basis"] for k in common]
    d_ret = [cm_be_by_deliv[k]["ret_alloc"] - um_by_deliv[k]["ret_alloc"] for k in common]
    entry_match = sum(1 for k in common
                      if cm_be_by_deliv[k]["entry_open"][:10] == um_by_deliv[k]["entry_open"][:10])
    sanity = {"n_common_deliveries": len(common),
              "entry_date_match": entry_match,
              "mean_abs_basis_diff": round(float(np.mean(np.abs(d_basis))), 6) if d_basis else None,
              "mean_abs_ret_diff": round(float(np.mean(np.abs(d_ret))), 6) if d_ret else None,
              "um_n_trades": len(cc["trades"]), "cm_btceth_n_trades": len(bteth),
              "um_skipped": cc["n_skipped"],
              "cm_btceth_skipped": sum(1 for c in all_meta
                                       if c["coin"] in ("BTC", "ETH")
                                       and c.get("status") == "skipped_basis")}
    print("sanity:", json.dumps(sanity))

    # ---- compound overlay on G2 (method reused unchanged) ----
    v388 = _load("v388_for_carrymore", RD / "v388" / "v388_bot_stop_distance.py")
    g1 = v388.Y1 + pd.Timedelta(hours=12)
    ANCH = [pd.Timestamp(a, tz="UTC") for a in v388.ANCH]
    from pandas import date_range as _dr
    GRID0 = pd.Timestamp("2021-09-24 04:00", tz="UTC")
    grid = _dr(GRID0, g1, freq="1h")
    gn = grid.values.astype("datetime64[ns]").astype(np.int64)
    n = len(grid)
    runs = pickle.loads(V421.read_bytes())
    strat = "R2B1D17BFG2"
    Es, Ms = [], []
    for s in range(4):
        e1, m1 = v388.hourly(runs[s][strat], GRID0, g1)
        assert (e1.index == grid).all()
        Es.append(e1.to_numpy(dtype=float))
        Ms.append(m1.to_numpy(dtype=float))
    Es = np.stack(Es)
    Ms = np.stack(Ms)
    Etot = Es.mean(axis=0)
    Mtot = Ms.mean(axis=0)

    h = pd.read_parquet(HOURLY, columns=["t", "close", "sym"])
    h["t"] = pd.to_datetime(h["t"], utc=True)
    assert bool((h["t"] < CAP).all())
    spot_h: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    for coin in COINS:
        d = h[h["sym"] == f"{coin}USDT"].sort_values("t")
        spot_h[coin] = (d["t"].values.astype("datetime64[ns]").astype(np.int64),
                        d["close"].to_numpy(dtype=float))

    def fut_map(prefix: str, trade_list: list) -> dict:
        qm = {}
        for t in trade_list:
            key = (t["coin"], t["delivery"])
            if key in qm:
                continue
            y, mth, dd = t["delivery"].split("-")
            code = f"{y[2:]}{mth}{dd}"
            sym = (f"{prefix}_{t['coin']}USDT_{code}_1h.parquet"
                   if prefix == "um" else f"{prefix}_{t['coin']}USD_{code}_1h.parquet")
            (f,) = sorted(QDIR.glob(sym))
            q = pd.read_parquet(f, columns=["open_time", "close"])
            qo = pd.to_datetime(q["open_time"], utc=True).values.astype(
                "datetime64[ns]").astype(np.int64)
            o = np.argsort(qo)
            qm[key] = (qo[o], q["close"].to_numpy(dtype=float)[o])
        return qm

    # (a) validation: um BTC+ETH must reproduce oc_carrycompound to the digit
    ccp = json.loads((CCP / "results.json").read_text())
    um_trades = [{k: t[k] for k in ("coin", "delivery", "entry_open", "F_entry",
                                    "S_entry", "ret_alloc")} for t in cc["trades"]]
    row_um = run_compound("um_BTC+ETH_f0.25", um_trades, fut_map("um", cc["trades"]),
                          spot_h, grid, gn, n, ANCH, Es, Ms, Etot, Mtot, v388)
    exp = ccp["rows"]["G2_f0.25"]
    assert [yy["R"] for yy in row_um["years"]] == [yy["R"] for yy in exp["years"]], row_um
    assert [yy["DD"] for yy in row_um["years"]] == [yy["DD"] for yy in exp["years"]], row_um
    assert row_um["R"] == exp["R"] and row_um["W"] == exp["W"] and row_um["DD"] == exp["DD"]
    assert row_um["full_path_dd"] == exp["full_path_dd"], row_um["full_path_dd"]
    assert row_um["losing"] == exp["losing"] == 0
    print("validation OK: um BTC+ETH reproduces oc_carrycompound G2_f0.25 to the digit")

    be_recs = [{k: t[k] for k in ("coin", "delivery", "entry_open", "F_entry",
                                  "S_entry", "ret_alloc")} for t in bteth]
    row_be = run_compound("cm_BTC+ETH_f0.25", be_recs, fut_map("cm", bteth),
                          spot_h, grid, gn, n, ANCH, Es, Ms, Etot, Mtot, v388)
    all_recs = [{k: t[k] for k in ("coin", "delivery", "entry_open", "F_entry",
                                   "S_entry", "ret_alloc")} for t in all_trades]
    row_all = run_compound("cm_ALL_f0.25", all_recs, fut_map("cm", all_trades),
                           spot_h, grid, gn, n, ANCH, Es, Ms, Etot, Mtot, v388)
    base = ccp["rows"]["G2_f0.0"]
    for row in (row_be, row_all):
        print(row["label"], "R=", row["R"], "W=", row["W"], "DD=", row["DD"],
              "losing=", row["losing"], "full=", row["full_path_dd"])

    # ---- capital: concurrent open pairs (spot cash + short notional vs equity) ----
    conc: dict = {}
    for tag, tl in (("cm_BTC+ETH", bteth), ("cm_ALL", all_trades)):
        ev = []
        for t in tl:
            ev.append((pd.Timestamp(t["entry_open"]).value,
                       pd.Timestamp(t["delivery"] + " 08:00", tz="UTC").value))
        pts = sorted({v for e in ev for v in e})
        mx = 0
        for p in pts:
            mx = max(mx, sum(1 for s, e in ev if s <= p < e))
        conc[tag] = {"max_concurrent_pairs": mx,
                     "spot_cash_vs_equity": round(mx * F_COIN, 4),
                     "short_notional_vs_equity": round(mx * F_COIN, 4),
                     "gross_vs_equity": round(2 * mx * F_COIN, 4),
                     "needs_borrow": bool(mx * F_COIN > 1.0)}
    print("capital:", json.dumps(conc))

    out = {
        "meta": {
            "label": "POST-HOC: all anchor years 2021-2026 were seen; rule frozen from oc_cashcarry",
            "rule": "SAME as oc_cashcarry PLAN.md unchanged (7d roll, 4%/yr, hold to delivery, fees 0.001/0.001/0.00055/0.0002)",
            "contracts": "Binance COIN-M cm_<COIN>USD_<YYMMDD> quarterly delivery (no funding); coin-settlement convexity not modelled",
            "delivery_rule": "08:00 UTC on code date; settlement = own-spot 4h close of delivery bar",
            "f_per_coin": F_COIN,
            "compound_method": "oc_carrycompound reused unchanged: A(t)=A(t-1)*(1+r_bot(t))+dU(t), r_bot on WHOLE equity (UTA), N=f x A at entry, hourly causal marks",
            "g2_src": "research/parallel/rounds/parallel-20260906-r2/v421/v421_runs.pkl strat R2B1D17BFG2",
        },
        "inventory": per_coin_summary,
        "cm_all_years": years_all,
        "cm_all_pooled": pooled_all,
        "cm_btceth_years": years_be,
        "cm_btceth_pooled": pooled_be,
        "sanity_cm_vs_um_btceth": sanity,
        "compound": {
            "G2_base_f0": {"years": base["years"], "R": base["R"], "W": base["W"],
                           "DD": base["DD"], "losing": base["losing"],
                           "full_path_dd": base["full_path_dd"]},
            "G2_um_BTC+ETH_f0.25_reproduces_oc_carrycompound": row_um,
            "G2_cm_BTC+ETH_f0.25": row_be,
            "G2_cm_ALL_f0.25": row_all,
            "carry_add_pp": {
                "um_BTC+ETH": round(row_um["R"] - base["R"], 3),
                "cm_BTC+ETH": round(row_be["R"] - base["R"], 3),
                "cm_ALL": round(row_all["R"] - base["R"], 3),
            },
        },
        "capital": conc,
        "trades": [{k: r[k] for k in ("coin", "delivery", "entry_open", "ann_basis",
                                      "dte_days", "ret_alloc", "worst_mtm_alloc",
                                      "F_entry", "S_entry", "S_del")} for r in all_trades],
    }
    (HERE / "results.json").write_text(json.dumps(out, indent=1))
    print(f"trades={len(all_trades)} pooled_sum={pooled_all['sum_ret_alloc']} "
          f"add_all={round(row_all['R'] - base['R'], 3)}pp/mo")


if __name__ == "__main__":
    main()
