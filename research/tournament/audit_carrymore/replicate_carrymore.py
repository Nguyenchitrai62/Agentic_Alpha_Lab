"""Blind audit replication for oc_carrymore (COIN-M quarterly cash-and-carry).

Independent implementation from:
  research/tournament/oc_carrymore/fetch_cm_quarterly.py + MANIFEST.json (data),
  research/tournament/oc_cashcarry/PLAN.md (carry rule),
  research/tournament/oc_carrycompound/ (compounding overlay method).
Does NOT import oc_carrymore/analyze_carrymore.py or open its REPORT/results
until replication.json is written.

Rule (PLAN.md, CM venue): per coin sort expiries ascending, code YYMMDD ->
delivery D at 08:00 UTC. For k>=1 candidate entry E_k = round_UP(D_{k-1}-7d)
to next spot 4h open_time; k=0 first availability. T_k = max(E_k, first bar
with both spot close and resampled quarterly close at its close). F resampled
causally: last 1h close with 1h open_time < spot close_time. ann_basis =
ln(F/S)*365/DTE_days, DTE=(D-close(T))/86400. ENTER iff >=0.04 else SKIP.
Settlement = spot 4h close of bar containing D; D beyond last spot bar ->
INCOMPLETE (excluded, counted). Fees: spot 0.001/side + fut 0.00055/0.0002,
drag 0.00275. ret_alloc = (S_del-S_e)/S_e + (F_e-S_del)/F_e - 0.00275.
Worst MtM per trade over 4h closes in (T,D]: S/S_e-1 + (F_e-F)/F_e - 0.00155.

Overlay: compounding account identical to analyze_carrycompound.py:
A(t)=A(t-1)*(1+r_bot(t))+dU(t), r_bot from stored 4-phase G2 mix hourly,
N_k = f*A at entry, held to delivery, causal hourly marks (last CLOSED hourly
bar strictly before t), 0 before entry-close, frozen ret_alloc from settlement.
Per-year reset to 1.0 + continuous full-path DD (v421 convention). Universes:
(a) BTC+ETH, (b) all majors. f rows 0.0/0.25. Peak concurrent spot notional
vs equity tracked on the continuous path: sum_open N_k / A(t).

Usage:
  .venv/Scripts/python.exe scripts/heavy_slot.py run --tag audit_carrymore \
    --min-free-gb 2.0 -- .venv/Scripts/python.exe \
    research/tournament/audit_carrymore/replicate_carrymore.py
"""

from __future__ import annotations

import importlib.util
import json
import pickle
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
RD = ROOT / "research/parallel/rounds/parallel-20260906-r2"
V421 = RD / "v421/v421_runs.pkl"
QDIR = ROOT / "data/raw/qbasis_20261003"
SDIR = ROOT / "data/raw/spot_majors_20260925"
HOURLY = ROOT / "research/tournament/ext/hourly_ext.parquet"

COINS = ["BTC", "ETH", "BNB", "SOL", "XRP"]
THRESH = 0.04
FEE_FULL = 0.00275
FEE_ENTRY_PAID = 0.001 + 0.00055
ANCH = ["2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24"]
YEAR = pd.Timedelta(days=365)
GRID0 = pd.Timestamp("2021-09-24 04:00", tz="UTC")
F_ROWS = [0.0, 0.25]


def parse_delivery(code: str) -> pd.Timestamp:
    return pd.Timestamp(f"20{code[:2]}-{code[2:4]}-{code[4:6]} 08:00", tz="UTC")


def load_spot(coin: str) -> pd.DataFrame:
    df = pd.read_parquet(SDIR / f"{coin}USDT_spot_4h.parquet",
                         columns=["open_time", "close_time", "close"])
    df["open_time"] = pd.to_datetime(df["open_time"], utc=True)
    df["close_time"] = pd.to_datetime(df["close_time"], utc=True)
    df = df.sort_values("open_time").reset_index(drop=True)
    return df


def load_cm_contract(coin: str, code: str) -> pd.DataFrame:
    pat = f"cm_{coin}USD_{code}_1h.parquet"
    p = QDIR / pat
    if not p.exists():  # XRP/BNB/SOL have no other prefix; fail loudly
        raise FileNotFoundError(pat)
    q = pd.read_parquet(p, columns=["open_time", "close"])
    q["open_time"] = pd.to_datetime(q["open_time"], utc=True)
    q = q.sort_values("open_time").reset_index(drop=True)
    return q


def resample_f_to_spot(spot: pd.DataFrame, q: pd.DataFrame) -> np.ndarray:
    """Last 1h close with 1h open_time < spot close_time (strictly causal)."""
    qo = q["open_time"].values.astype("datetime64[ns]").astype(np.int64)
    qc = q["close"].to_numpy(dtype=float)
    sc = spot["close_time"].values.astype("datetime64[ns]").astype(np.int64)
    idx = np.searchsorted(qo, sc, side="left") - 1
    out = np.full(len(spot), np.nan)
    ok = idx >= 0
    out[ok] = qc[idx[ok]]
    return out


def carry_trades_for_coin(coin: str) -> tuple[list[dict], dict]:
    spot = load_spot(coin)
    so = spot["open_time"].to_numpy()
    so_ns = so.astype("datetime64[ns]").astype(np.int64)
    s_close = spot["close"].to_numpy(dtype=float)
    s_close_time = spot["close_time"]

    files = sorted(QDIR.glob(f"cm_{coin}USD_*_1h.parquet"))
    contracts = []
    for f in files:
        code = f.stem.split("_")[-2]
        D = parse_delivery(code)
        contracts.append({"code": code, "delivery": D, "file": f.name,
                          "contract": f"{coin}USD_{code}"})
    contracts.sort(key=lambda r: r["delivery"])

    # resample each contract onto the shared spot grid
    for c in contracts:
        q = load_cm_contract(coin, c["code"])
        c["F_grid"] = resample_f_to_spot(spot, q)

    trades: list[dict] = []
    skipped = 0
    incomplete = 0
    # entry-availability bookkeeping for look-ahead asserts
    for k, c in enumerate(contracts):
        D = c["delivery"]
        if k == 0:
            E = so[0]
        else:
            prev_D = contracts[k - 1]["delivery"]
            target = prev_D - pd.Timedelta(days=7)
            pos = int(np.searchsorted(so_ns, target.value, side="left"))
            if pos >= len(so):
                skipped += 1
                continue
            E = so[pos]
        both = np.isfinite(s_close) & np.isfinite(c["F_grid"])
        avail = np.where(both)[0]
        if len(avail) == 0:
            skipped += 1
            continue
        posE = int(np.searchsorted(so_ns, pd.Timestamp(E).value, side="left"))
        T = max(posE, int(avail[0]))
        if T >= len(so):
            skipped += 1
            continue
        S_entry = float(s_close[T])
        F_entry = float(c["F_grid"][T])
        tc = s_close_time.iloc[T]
        # look-ahead: entry uses closes <= entry close by construction
        assert pd.Timestamp(E) >= so[0]
        dte = (D - tc) / pd.Timedelta(days=1)
        if not np.isfinite(dte) or dte <= 0:
            skipped += 1
            continue
        ann = float(np.log(F_entry / S_entry) * 365.0 / dte)
        if ann < THRESH:
            skipped += 1
            continue
        # settlement: first spot bar with open <= D < close
        si = int(np.searchsorted(
            spot["close_time"].values.astype("datetime64[ns]").astype(np.int64),
            D.value, side="right"))
        # open_time <= D check
        while si < len(spot) and not (
                spot["open_time"].iloc[si] <= D < spot["close_time"].iloc[si]):
            # searchsorted on close_time gives first close > D; verify contain
            break
        if si >= len(spot) or not (
                spot["open_time"].iloc[si] <= D < spot["close_time"].iloc[si]):
            incomplete += 1
            continue
        S_del = float(s_close[si])
        ret = (S_del - S_entry) / S_entry + (F_entry - S_del) / F_entry - FEE_FULL
        # worst MtM over 4h closes in (T, D]
        seg = np.arange(T + 1, si + 1)
        seg = seg[seg < len(spot)]
        Fseg = c["F_grid"][seg]
        Sseg = s_close[seg]
        okm = np.isfinite(Fseg) & np.isfinite(Sseg)
        if okm.any():
            mtm = (Sseg[okm] / S_entry - 1.0) + ((F_entry - Fseg[okm]) / F_entry) \
                - FEE_ENTRY_PAID
            worst = float(np.min(mtm))
        else:
            worst = 0.0
        trades.append({
            "coin": coin, "contract": c["contract"], "delivery": D.date().isoformat(),
            "entry_open": str(so[T]), "entry_close": str(s_close_time.iloc[T]),
            "F_entry": F_entry, "S_entry": S_entry, "S_del": S_del,
            "DTE_days": round(float(dte), 3), "ann_basis": round(float(ann), 6),
            "ret_alloc": float(ret), "worst_mtm_alloc": float(worst),
        })
    info = {"n_contracts": len(contracts), "n_skipped": skipped,
            "n_incomplete": incomplete,
            "first_delivery": str(contracts[0]["delivery"].date()) if contracts else None,
            "last_delivery": str(contracts[-1]["delivery"].date()) if contracts else None}
    return trades, info


def year_of(entry_open: str) -> int:
    te = pd.Timestamp(entry_open)
    for y, a in enumerate(ANCH):
        a0 = pd.Timestamp(a, tz="UTC")
        if a0 <= te < a0 + YEAR:
            return y
    return -1


def last_close_before(times_ns: np.ndarray, closes: np.ndarray,
                       ts_ns: np.ndarray) -> np.ndarray:
    idx = np.searchsorted(times_ns, ts_ns, side="left") - 1
    out = np.full(len(ts_ns), np.nan)
    ok = idx >= 0
    out[ok] = closes[idx[ok]]
    return out


def run_overlay(trades_all: list[dict], coins: list[str], label: str) -> dict:
    """Compounding G2 overlay for a coin subset (method = oc_carrycompound)."""
    spec = importlib.util.spec_from_file_location(
        "v388_for_audit", RD / "v388/v388_bot_stop_distance.py")
    v388 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(v388)
    g1 = v388.Y1 + pd.Timedelta(hours=12)
    ANCH_TS = [pd.Timestamp(a, tz="UTC") for a in v388.ANCH]
    grid = pd.date_range(GRID0, g1, freq="1h")
    gn = grid.values.astype("datetime64[ns]").astype(np.int64)
    n = len(grid)

    runs = pickle.loads(V421.read_bytes())
    strat = "R2B1D17BFG2"

    h = pd.read_parquet(HOURLY, columns=["t", "close", "sym"])
    h["t"] = pd.to_datetime(h["t"], utc=True)
    spot: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    for coin in coins:
        d = h[h["sym"] == f"{coin}USDT"].sort_values("t")
        spot[coin] = (d["t"].values.astype("datetime64[ns]").astype(np.int64),
                      d["close"].to_numpy(dtype=float))

    # futures hourly marks from CM 1h files
    qmap: dict[tuple[str, str], tuple[np.ndarray, np.ndarray]] = {}
    for t in trades_all:
        key = (t["coin"], t["delivery"])
        if key in qmap:
            continue
        y, m, dd = t["delivery"].split("-")
        code = f"{y[2:]}{m}{dd}"
        (f,) = sorted(QDIR.glob(f"cm_{t['coin']}USD_{code}_1h.parquet"))
        q = pd.read_parquet(f, columns=["open_time", "close"])
        qo = pd.to_datetime(q["open_time"], utc=True).values.astype(
            "datetime64[ns]").astype(np.int64)
        o = np.argsort(qo)
        qmap[key] = (qo[o], q["close"].to_numpy(dtype=float)[o])

    s4 = pd.read_parquet(SDIR / "BTCUSDT_spot_4h.parquet",
                         columns=["open_time", "close_time"])
    s4c = pd.to_datetime(s4["close_time"], utc=True)
    trs = []
    for t in trades_all:
        te = pd.Timestamp(t["entry_open"], tz="UTC")
        tc = te + pd.Timedelta(hours=4)
        D = pd.Timestamp(t["delivery"] + " 08:00", tz="UTC")
        si = int(np.searchsorted(s4c.values.astype("datetime64[ns]").astype(np.int64),
                                 D.value, side="right"))
        ts = s4c.iloc[si]
        assert ts > tc, t
        trs.append({"coin": t["coin"], "delivery": t["delivery"],
                    "F_entry": float(t["F_entry"]), "S_entry": float(t["S_entry"]),
                    "ret_alloc": float(t["ret_alloc"]),
                    "tc_ns": tc.value, "ts_ns": ts.value})

    Es, Ms = [], []
    for s in range(4):
        e1, m1 = v388.hourly(runs[s][strat], GRID0, g1)
        assert (e1.index == grid).all()
        Es.append(e1.to_numpy(dtype=float))
        Ms.append(m1.to_numpy(dtype=float))
    Es = np.stack(Es)
    Ms = np.stack(Ms)

    for tr in trs:
        st, sc = spot[tr["coin"]]
        ft, fc = qmap[(tr["coin"], tr["delivery"])]
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
        st, sc = spot[tr["coin"]]
        ft, fc = qmap[(tr["coin"], tr["delivery"])]
        qa = np.array([a_ns])
        S = last_close_before(st, sc, qa)[0]
        F = last_close_before(ft, fc, qa)[0]
        if np.isfinite(S) and np.isfinite(F) and tr["F_entry"] and tr["S_entry"]:
            return float((S / tr["S_entry"] - 1.0)
                         + ((tr["F_entry"] - F) / tr["F_entry"]) - FEE_ENTRY_PAID)
        return 0.0

    a_ns_all = np.array([a.value for a in ANCH_TS])
    anchor_mtm = np.array([[mtm_at_anchor(tr, a) for tr in trs] for a in a_ns_all])

    rows: dict[float, dict] = {}
    for f in F_ROWS:
        years = []
        for y, a0 in enumerate(ANCH_TS):
            a1 = a0 + YEAR
            seg = (grid > a0) & (grid <= a1)
            idx = np.where(np.asarray(seg))[0]
            le = gn <= a0.value
            b = np.array([float(Es[s][le][-1]) if le.any() else 1.0 for s in range(4)])
            E4 = [Es[s][idx] / b[s] for s in range(4)]
            M4 = [Ms[s][idx] / b[s] for s in range(4)]
            es = np.mean(E4, axis=0)
            ms = np.mean(M4, axis=0)
            if f == 0.0:
                A_arr, M_arr = es, ms
            else:
                es_prev = np.concatenate([[1.0], es[:-1]])
                g = es / es_prev
                hh = ms / es_prev
                mtm_a = anchor_mtm[y]
                rel = [k for k, tr in enumerate(trs)
                       if tr["tc_ns"] < a1.value and tr["ts_ns"] > a0.value]
                span = {k for k in rel if trs[k]["tc_ns"] <= a0.value}
                mtm_seg = {k: trs[k]["mtm"][idx] - mtm_a[k] for k in rel}
                A_prev, U_prev = 1.0, 0.0
                A_arr = np.empty(len(idx))
                M_arr = np.empty(len(idx))
                tc_map: dict[int, list[int]] = {}
                for k in rel:
                    if k in span:
                        continue
                    pos = int(np.searchsorted(gn[idx], trs[k]["tc_ns"], side="right"))
                    if 0 <= pos < len(idx):
                        tc_map.setdefault(pos, []).append(k)
                U_open: dict[int, float] = {k: f * 1.0 for k in span}
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
        rows[f] = {"years": years, "R": R5, "W": min(yy["R"] for yy in years),
                   "DD": max(yy["DD"] for yy in years),
                   "losing": sum(yy["R"] < 0 for yy in years)}

    Etot = Es.mean(axis=0)
    Mtot = Ms.mean(axis=0)
    full: dict[float, dict] = {}
    peak_spot: dict[float, float] = {}
    for f in F_ROWS:
        if f == 0.0:
            A_c, M_c = Etot.copy(), Mtot.copy()
            peak_spot[f] = 0.0
        else:
            A_c = np.empty(n)
            M_c = np.empty(n)
            g0_mtm = np.array([mtm_at_anchor(tr, gn[0]) for tr in trs])
            rel_c = [k for k, tr in enumerate(trs) if tr["ts_ns"] > gn[0]]
            span_c = {k for k in rel_c if trs[k]["tc_ns"] <= gn[0]}
            N_c: dict[int, float] = {k: f * float(Etot[0]) for k in span_c}
            mtm_r = {k: trs[k]["mtm"] - g0_mtm[k] for k in rel_c}
            tc_pos: dict[int, list[int]] = {}
            for k in rel_c:
                if k in span_c:
                    continue
                pos = int(np.searchsorted(gn, trs[k]["tc_ns"], side="right"))
                if 0 <= pos < n:
                    tc_pos.setdefault(pos, []).append(k)
            A_c[0], M_c[0] = float(Etot[0]), float(Mtot[0])
            A_prev = float(Etot[0])
            U_prev = 0.0
            U_open_c: dict[int, float] = dict(N_c)
            peak = 0.0
            # entry/settlement hour positions for open-only notional
            tc_i = {k: int(np.searchsorted(gn, trs[k]["tc_ns"], side="right")) for k in rel_c}
            ts_i = {k: int(np.searchsorted(gn, trs[k]["ts_ns"], side="right")) for k in rel_c}
            for i in range(1, n):
                for k in tc_pos.get(i, []):
                    U_open_c[k] = f * A_prev
                U_i = 0.0
                for k, nk in U_open_c.items():
                    U_i += nk * mtm_r[k][i]
                dU = U_i - U_prev
                g = Etot[i] / Etot[i - 1]
                hh = Mtot[i] / Etot[i - 1]
                A_c[i] = A_prev * g + dU
                M_c[i] = A_prev * hh + dU
                A_prev, U_prev = A_c[i], U_i
                snot = sum(nk for k, nk in U_open_c.items()
                           if tc_i[k] <= i < ts_i[k])
                if A_c[i] > 0:
                    peak = max(peak, snot / A_c[i])
            peak_spot[f] = round(float(peak), 4)
        segf = np.asarray(grid > pd.Timestamp("2021-09-24", tz="UTC"))
        esf, msf = A_c[segf], M_c[segf]
        dd_m = round(100 * float(np.max(1 - msf / np.maximum.accumulate(esf))), 2)
        dd_c = round(100 * float(np.max(1 - esf / np.maximum.accumulate(esf))), 2)
        full[f] = {"marked": dd_m, "close": dd_c, "full": max(dd_m, dd_c)}
    return {"label": label, "coins": coins, "rows": rows, "full": full,
            "peak_spot_notional_vs_equity": peak_spot}


def main() -> None:
    all_trades: list[dict] = []
    per_coin: dict = {}
    for coin in COINS:
        trades, info = carry_trades_for_coin(coin)
        all_trades.extend(trades)
        n_e = len(trades)
        per_year: dict = {}
        for y, a in enumerate(ANCH):
            yt = [t for t in trades if year_of(t["entry_open"]) == y]
            per_year[a] = {"n_entered": len(yt),
                           "mean_ann_basis": round(float(np.mean([t["ann_basis"] for t in yt])), 6) if yt else None,
                           "mean_DTE": round(float(np.mean([t["DTE_days"] for t in yt])), 1) if yt else None,
                           "mean_ret_alloc": round(float(np.mean([t["ret_alloc"] for t in yt])), 6) if yt else None,
                           "sum_ret_alloc": round(float(sum(t["ret_alloc"] for t in yt)), 6),
                           "worst_mtm_alloc": round(float(min([t["worst_mtm_alloc"] for t in yt])), 6) if yt else None}
        per_coin[coin] = {"info": info, "n_entered": n_e, "per_year": per_year,
                          "trades": trades}

    # pooled year stats (grouped by entry open)
    pooled = {}
    for y, a in enumerate(ANCH):
        yt = [t for t in all_trades if year_of(t["entry_open"]) == y]
        pooled[a] = {"n_entered": len(yt),
                     "by_coin": {c: sum(1 for t in yt if t["coin"] == c) for c in COINS},
                     "sum_ret_alloc": round(float(sum(t["ret_alloc"] for t in yt)), 6),
                     "worst_mtm_alloc": round(float(min([t["worst_mtm_alloc"] for t in yt])), 6) if yt else None}

    ov_btceth = run_overlay([t for t in all_trades if t["coin"] in ("BTC", "ETH")],
                            ["BTC", "ETH"], "BTC+ETH")
    ov_all = run_overlay(list(all_trades), COINS, "all_majors")

    out = {
        "meta": {
            "rule": "oc_cashcarry PLAN.md unchanged (7d roll, 4%/yr, hold to delivery, fees 0.001/0.001/0.00055/0.0002)",
            "venue": "Binance COIN-M delivery quarterlies (cm_<COIN>USD 1h) + spot 4h majors",
            "window": ["2021-09-24", "2026-09-23"],
            "threshold_ann_basis": 0.04,
            "blind": True,
            "note": "independent replication; written before opening oc_carrymore REPORT/results",
        },
        "per_coin": {c: {"info": per_coin[c]["info"], "n_entered": per_coin[c]["n_entered"],
                         "per_year": per_coin[c]["per_year"]} for c in COINS},
        "trades": [
            {"coin": t["coin"], "contract": t["contract"], "delivery": t["delivery"],
             "entry_open": t["entry_open"], "entry_close": t["entry_close"],
             "F_entry": t["F_entry"], "S_entry": t["S_entry"], "S_del": t["S_del"],
             "DTE_days": t["DTE_days"], "ann_basis": t["ann_basis"],
             "ret_alloc": round(float(t["ret_alloc"]), 6),
             "worst_mtm_alloc": round(float(t["worst_mtm_alloc"]), 6)}
            for t in sorted(all_trades, key=lambda t: (t["entry_open"], t["coin"]))
        ],
        "n_entered_total": len(all_trades),
        "n_skipped_total": sum(per_coin[c]["info"]["n_skipped"] for c in COINS),
        "n_incomplete_total": sum(per_coin[c]["info"]["n_incomplete"] for c in COINS),
        "pooled_per_year": pooled,
        "overlay_BTC_ETH": {"rows": ov_btceth["rows"], "full": ov_btceth["full"],
                            "peak_spot_notional_vs_equity": ov_btceth["peak_spot_notional_vs_equity"]},
        "overlay_all_majors": {"rows": ov_all["rows"], "full": ov_all["full"],
                               "peak_spot_notional_vs_equity": ov_all["peak_spot_notional_vs_equity"]},
    }
    (HERE / "replication.json").write_text(json.dumps(out, indent=1))
    print(f"coins: {[(c, per_coin[c]['n_entered']) for c in COINS]} "
          f"total={len(all_trades)} skipped={out['n_skipped_total']} "
          f"incomplete={out['n_incomplete_total']}")
    for label, ov in (("BTC+ETH", ov_btceth), ("ALL", ov_all)):
        for f in F_ROWS:
            print(f"{label} f={f}: R={ov['rows'][f]['R']} W={ov['rows'][f]['W']} "
                  f"DD={ov['rows'][f]['DD']} full={ov['full'][f]['full']} "
                  f"peak_spot={ov['peak_spot_notional_vs_equity'][f]}")


if __name__ == "__main__":
    main()
