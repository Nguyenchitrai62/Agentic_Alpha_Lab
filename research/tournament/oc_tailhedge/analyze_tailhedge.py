"""oc_tailhedge: long-BTC-put tail hedge so the dip sleeve can run larger at same DD.

Assignment: docs/opencode/OPENCODE_W_oc_tailhedge.md + PLAN.md (pre-registered).
Read-only inputs, no engine reruns, one process, streams one yearly 1m file at a
time (low RAM), no GPU.

  python research/tournament/oc_tailhedge/analyze_tailhedge.py
"""

from __future__ import annotations

import importlib.util
import json
import math
import pickle
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
RD = ROOT / "research/parallel/rounds/parallel-20260906-r2"
V421 = RD / "v421/v421_runs.pkl"
V422 = RD / "v422/v422_runs.pkl"
V421_RES = RD / "v421/v421_result.json"
V422_RES = RD / "v422/v422_result.json"
IVP = ROOT / "data/raw/deribit_opt_20260926/BTC_options_4h.parquet"
BTC1M = ROOT / "data/raw/btc_intraday_20260924"

STRAT_G2 = "R2B1D17BFG2"
STRAT_K20 = "G2K20"
GRID0 = pd.Timestamp("2021-09-24 04:00", tz="UTC")
CAP = pd.Timestamp("2026-09-24 00:00", tz="UTC")
YEAR = pd.Timedelta(days=365)
SEC_YR = 365.0 * 86400.0
M_ROWS = (0.15, 0.25)
H_ROWS = (1.0, 2.0)
SKEW = {0.15: 0.05, 0.25: 0.10}
SQRT2 = math.sqrt(2.0)


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def ncdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / SQRT2))


def bs_put(S: float, K: float, T: float, sigma: float) -> float:
    """European put, r=q=0. Intrinsic when T<=0 or sigma<=0."""
    if not (np.isfinite(S) and np.isfinite(K)) or S <= 0 or K <= 0:
        return 0.0
    if T <= 0 or sigma <= 0 or not np.isfinite(sigma):
        return max(K - S, 0.0)
    sT = sigma * math.sqrt(T)
    d1 = (math.log(S / K) + 0.5 * sigma * sigma * T) / sT
    d2 = d1 - sT
    return K * ncdf(-d2) - S * ncdf(-d1)


def fee_buy_side(S: float, opt: float) -> float:
    return min(0.0003 * S, 0.125 * opt)


def fee_settle_side(Ss: float, intr: float) -> float:
    return min(0.00015 * Ss, 0.125 * intr)


def last_friday(y: int, m: int) -> int:
    last = pd.Timestamp(y, m, 1) + pd.offsets.MonthEnd(0)
    wd = last.weekday()  # Monday=0 .. Friday=4
    return last.day - ((wd - 4) % 7)


def monthly_expiries() -> list[pd.Timestamp]:
    out = []
    for y in range(2021, 2027):
        for m in range(1, 13):
            d = last_friday(y, m)
            e = pd.Timestamp(y, m, d, 8, 0, tz="UTC")
            if pd.Timestamp("2021-09-01", tz="UTC") <= e <= pd.Timestamp("2026-09-30", tz="UTC"):
                out.append(e)
    return sorted(out)


def main() -> None:
    v388 = _load("v388_for_tail", RD / "v388/v388_bot_stop_distance.py")
    ANCH = [pd.Timestamp(a, tz="UTC") for a in v388.ANCH]
    assert [str(a.date()) for a in ANCH] == ["2021-09-24", "2022-09-24", "2023-09-24",
                                             "2024-09-24", "2025-09-24"]
    g1 = v388.Y1 + pd.Timedelta(hours=12)
    grid = pd.date_range(GRID0, g1, freq="1h")
    assert (grid < CAP).all(), "grid must stay strictly under the cap"
    gn = grid.values.astype("datetime64[ns]").astype(np.int64)
    n = len(grid)

    runs21 = pickle.loads(V421.read_bytes())
    runs22 = pickle.loads(V422.read_bytes())
    assert set(runs21) == {0, 1, 2, 3} and set(runs22) == {0, 1, 2, 3}

    Es_g2 = np.stack([v388.hourly(runs21[s][STRAT_G2], GRID0, g1)[0].to_numpy(dtype=float)
                      for s in range(4)])
    Ms_g2 = np.stack([v388.hourly(runs21[s][STRAT_G2], GRID0, g1)[1].to_numpy(dtype=float)
                      for s in range(4)])
    Es_k = np.stack([v388.hourly(runs22[s][STRAT_K20], GRID0, g1)[0].to_numpy(dtype=float)
                     for s in range(4)])
    Ms_k = np.stack([v388.hourly(runs22[s][STRAT_K20], GRID0, g1)[1].to_numpy(dtype=float)
                     for s in range(4)])
    for arr, nm in ((Es_g2, "Es_g2"), (Ms_g2, "Ms_g2"), (Es_k, "Es_k"), (Ms_k, "Ms_k")):
        assert arr.shape == (4, n), (nm, arr.shape)
        assert np.isfinite(arr).all(), nm

    # ---- Deribit aggregated OTM-put IV (primary; DVOL fallback unused) ----
    iv = pd.read_parquet(IVP, columns=["bar", "iv_otm_put"])
    iv["bar"] = pd.to_datetime(iv["bar"], utc=True)
    iv = iv.drop_duplicates("bar").sort_values("bar")
    iv_close_ns = (iv["bar"] + pd.Timedelta(hours=4)).values.astype(
        "datetime64[ns]").astype(np.int64)
    iv_vals = iv["iv_otm_put"].to_numpy(dtype=float)
    nan0 = int(np.isnan(iv_vals).sum())
    iv_vals = pd.Series(iv_vals).ffill().to_numpy()
    assert np.isfinite(iv_vals).all(), "IV has leading NaNs even after ffill"
    assert iv_close_ns[0] <= gn[0], "IV history must start before the grid"

    def iv_known(t_ns: int) -> float:
        """Last 4h bar with close <= t (strictly causal)."""
        j = int(np.searchsorted(iv_close_ns, t_ns, side="right")) - 1
        assert j >= 0
        return float(iv_vals[j])

    sig_mark_grid = np.array([0.95 * iv_known(int(t)) / 100.0 for t in gn])
    assert np.isfinite(sig_mark_grid).all()

    # ---- BTC 1m klines -> hourly close/low on grid + event-minute lookups ----
    need_min = pd.date_range(GRID0 - pd.Timedelta(hours=1), g1, freq="1min")
    need_set = set(need_min.values.astype("datetime64[ns]").astype(np.int64))
    cmin: dict[int, float] = {}
    lmin: dict[int, float] = {}
    for fp in sorted(BTC1M.glob("klines_1m_20*.parquet")):
        df = pd.read_parquet(fp, columns=["open_time", "high", "low", "close"])
        ot = pd.to_datetime(df["open_time"], utc=True).values.astype(
            "datetime64[ns]").astype(np.int64)
        hi = df["high"].to_numpy(dtype=float)
        lo = df["low"].to_numpy(dtype=float)
        cl = df["close"].to_numpy(dtype=float)
        for t_, h_, l_, c_ in zip(ot.tolist(), hi.tolist(), lo.tolist(), cl.tolist()):
            if t_ in need_set and t_ not in cmin:
                cmin[t_] = c_
                lmin[t_] = l_
    assert len(cmin) == len(need_min), f"1m coverage {len(cmin)}/{len(need_min)}"
    c_all = np.array([cmin[t_] for t_ in
                      need_min.values.astype("datetime64[ns]").astype(np.int64)])
    l_all = np.array([lmin[t_] for t_ in
                      need_min.values.astype("datetime64[ns]").astype(np.int64)])
    assert np.isfinite(c_all).all() and np.isfinite(l_all).all()
    c_by_min = dict(zip(need_min.values.astype("datetime64[ns]").astype(np.int64).tolist(),
                        c_all.tolist()))

    Sc = np.empty(n)  # 1m close of minute t-1 (known at t)
    Sl = np.empty(n)  # min 1m low over [t-60m, t-1m]
    for i, t_ in enumerate(gn.tolist()):
        Sc[i] = c_by_min[t_ - 60_000_000_000]
    lser = pd.Series(l_all, index=need_min).rolling(60, min_periods=60).min()
    rmin = lser.reindex(need_min).to_numpy()
    gmin_idx = {t_: k for k, t_ in enumerate(
        need_min.values.astype("datetime64[ns]").astype(np.int64).tolist())}
    for i, t_ in enumerate(gn.tolist()):
        Sl[i] = rmin[gmin_idx[t_ - 60_000_000_000]]
    assert np.isfinite(Sc).all() and np.isfinite(Sl).all() and bool((Sl <= Sc + 1e-9).all())

    # ---- expiry calendar + per-expiry causal inputs ----
    # Selection calendar runs to Oct-2026 (a position bought at the last in-grid
    # roll may expire after the grid end; it is marked to cap = truncation).
    CAL = monthly_expiries() + [pd.Timestamp(2026, 10, last_friday(2026, 10), 8, 0, tz="UTC")]
    EXPS = [e for e in CAL if GRID0.date() <= e.date() <= g1.date()]
    assert EXPS[0] == pd.Timestamp("2021-09-24 08:00", tz="UTC"), EXPS[:3]
    roll_idx: dict[int, pd.Timestamp] = {}
    S_entry: dict[pd.Timestamp, float] = {}
    S_settle: dict[pd.Timestamp, float] = {}
    for e in EXPS:
        entry_ns = (e.normalize() + pd.Timedelta(hours=8, minutes=5)).value
        pos = int(np.searchsorted(gn, entry_ns, side="right"))
        assert pos < n and grid[pos] > e.normalize() + pd.Timedelta(hours=8, minutes=5)
        roll_idx[pos] = e
        m0804 = (e.normalize() + pd.Timedelta(hours=8, minutes=4)).value
        assert m0804 in c_by_min, e
        S_entry[e] = c_by_min[m0804]
        closes = []
        for mm in range(30, 60):
            mk = (e.normalize() + pd.Timedelta(hours=7, minutes=mm)).value
            assert mk in c_by_min, (e, mm)
            closes.append(c_by_min[mk])
        S_settle[e] = float(np.mean(closes))
    iv_entry = {e: iv_known(int((e.normalize() + pd.Timedelta(hours=8, minutes=5)).value))
                for e in EXPS}

    def next_expiry(t_ns: int) -> pd.Timestamp:
        for e in CAL:
            if (e.value - t_ns) / 1e9 >= 21 * 86400:
                return e
        raise AssertionError("no expiry >= 21d away (position runs past cap)")

    # ---------------- hedge simulation core ----------------
    def simulate(es: np.ndarray, ms: np.ndarray, idx: np.ndarray,
                 m: float, h: float, pin_first: bool,
                 ledger: list | None = None, tag: str = ""):
        """Overlay one put series. idx = grid positions simulated (ascending).
        pin_first: A/M at idx[0] pinned to base (continuous pass); else grow from 1.0."""
        A = np.empty(len(idx))
        Mc = np.empty(len(idx))
        Mo = np.empty(len(idx))
        dH = np.zeros(len(idx))
        if pin_first:
            A_prev = float(es[idx[0]])
            Mc[0] = A[0] = float(es[idx[0]])
            Mo[0] = float(ms[idx[0]])
            start = 1
        else:
            A_prev = 1.0
            start = 0
        pos = None  # dict(units,K,exp,buy,mpc,mpo)
        paid = 0.0
        received = 0.0
        n_buy = 0
        n_tp = 0
        n_set = 0
        prev_i = idx[0] if pin_first else None
        for k in range(start, len(idx)):
            i = int(idx[k])
            es_prev = float(es[int(prev_i)]) if prev_i is not None else 1.0
            g = float(es[i]) / es_prev
            hh = float(ms[i]) / es_prev
            A_g = A_prev * g
            dh_c = 0.0
            dh_o = 0.0
            sm = float(sig_mark_grid[i]) + SKEW[m]
            if pos is not None:
                T = max((pos["exp"].value - gn[i]) / 1e9, 0.0) / SEC_YR
                mc = bs_put(float(Sc[i]), pos["K"], T, sm)
                mo = bs_put(float(Sl[i]), pos["K"], T, sm)
                dh_c += pos["units"] * (mc - pos["mpc"])
                dh_o += pos["units"] * (mo - pos["mpo"])
                pos["mpc"], pos["mpo"] = mc, mo
            if i in roll_idx:
                e_today = roll_idx[i]
                if pos is not None and pos["exp"] == e_today:
                    intr = max(pos["K"] - S_settle[e_today], 0.0)
                    fs = fee_settle_side(S_settle[e_today], intr)
                    cash = pos["units"] * (intr - fs)
                    dh_c += cash - pos["units"] * pos["mpc"]
                    dh_o += cash - pos["units"] * pos["mpo"]
                    received += cash
                    if ledger is not None:
                        ledger.append({"row": tag, "type": "settle",
                                       "t": str(grid[i]), "expiry": str(pos["exp"].date()),
                                       "K": pos["K"], "units": round(pos["units"], 9),
                                       "intr": round(intr, 2), "fee": round(fs, 4),
                                       "cash": round(cash, 6)})
                    pos = None
                    n_set += 1
                if pos is None:
                    S_e = S_entry[e_today]
                    E_new = next_expiry(int((e_today.normalize()
                                             + pd.Timedelta(hours=8, minutes=5)).value))
                    K = math.floor(S_e * (1.0 - m) / 1000.0) * 1000
                    T_e = ((E_new.value - (e_today.normalize()
                                           + pd.Timedelta(hours=8, minutes=5)).value) / 1e9) / SEC_YR
                    sb = 1.05 * float(iv_entry[e_today]) / 100.0 + SKEW[m]
                    buy = bs_put(S_e, K, T_e, sb)
                    fb = fee_buy_side(S_e, buy)
                    A_cur = A_g + dh_c
                    units = h * A_cur / S_e
                    T_m = max((E_new.value - gn[i]) / 1e9, 0.0) / SEC_YR
                    me_c = bs_put(float(Sc[i]), K, T_m, sm)
                    me_o = bs_put(float(Sl[i]), K, T_m, sm)
                    dh_c += units * (me_c - buy - fb)
                    dh_o += units * (me_o - buy - fb)
                    paid += units * (buy + fb)
                    if ledger is not None:
                        ledger.append({"row": tag, "type": "buy",
                                       "t": str(grid[i]),
                                       "expiry": str(E_new.date()), "K": K,
                                       "S": round(S_e, 1), "units": round(units, 9),
                                       "buy": round(buy, 2), "fee": round(fb, 4),
                                       "sigma_buy": round(sb, 4)})
                    pos = {"units": units, "K": K, "exp": E_new, "buy": buy,
                           "mpc": me_c, "mpo": me_o}
                    n_buy += 1
            elif pos is not None and pos["mpc"] >= 5.0 * pos["buy"] and pos["buy"] > 0:
                fs = fee_buy_side(float(Sc[i]), pos["mpc"])
                cash = pos["units"] * (pos["mpc"] - fs)
                dh_c += cash - pos["units"] * pos["mpc"]
                dh_o += cash - pos["units"] * pos["mpo"]
                received += cash
                if ledger is not None:
                    ledger.append({"row": tag, "type": "tp",
                                       "t": str(grid[i]),
                                       "expiry": str(pos["exp"].date()), "K": pos["K"],
                                       "units": round(pos["units"], 9),
                                       "mark": round(pos["mpc"], 2),
                                       "buy": round(pos["buy"], 2),
                                       "mult": round(pos["mpc"] / pos["buy"], 2),
                                       "cash": round(cash, 6)})
                n_tp += 1
                S_n = float(Sc[i])
                E_new = next_expiry(int(gn[i]))
                K = math.floor(S_n * (1.0 - m) / 1000.0) * 1000
                T_e = ((E_new.value - gn[i]) / 1e9) / SEC_YR
                sb = 1.05 * iv_known(int(gn[i])) / 100.0 + SKEW[m]
                buy = bs_put(S_n, K, T_e, sb)
                fb = fee_buy_side(S_n, buy)
                A_cur = A_g + dh_c
                units = h * A_cur / S_n
                T_m = max((E_new.value - gn[i]) / 1e9, 0.0) / SEC_YR
                me_c = bs_put(S_n, K, T_m, sm)
                me_o = bs_put(float(Sl[i]), K, T_m, sm)
                dh_c += units * (me_c - buy - fb)
                dh_o += units * (me_o - buy - fb)
                paid += units * (buy + fb)
                pos = {"units": units, "K": K, "exp": E_new, "buy": buy,
                       "mpc": me_c, "mpo": me_o}
                n_buy += 1
            A_i = A_g + dh_c
            A[k] = A_i
            Mc[k] = A_prev * hh + dh_c
            Mo[k] = A_prev * hh + dh_o
            dH[k] = dh_c
            A_prev = A_i
            prev_i = i
        info = {"paid": paid, "received": received, "cost": paid - received,
                "n_buy": n_buy, "n_tp": n_tp, "n_set": n_set,
                "open": pos is not None}
        return A, Mc, Mo, dH, info

    def year_stats(A: np.ndarray, Mc: np.ndarray, Mo: np.ndarray):
        pk = np.maximum.accumulate(A)
        R = round(100 * float(A[-1] ** (1 / 12) - 1), 3)
        DDc = round(100 * float(np.max(1 - Mc / pk)), 2)
        DDo = round(100 * float(np.max(1 - Mo / pk)), 2)
        return R, DDc, DDo, round(float(A[-1]), 6)

    # ---------------- validation: base rows reproduce published results ----
    base_defs = {"G2": (Es_g2, Ms_g2, STRAT_G2, V421_RES),
                 "G2K20": (Es_k, Ms_k, STRAT_K20, V422_RES)}
    base_years: dict[str, list] = {}
    for bname, (EsB, MsB, _s, _r) in base_defs.items():
        ys = []
        for y, a0 in enumerate(ANCH):
            seg = np.where((grid > a0) & (grid <= a0 + YEAR))[0]
            le = gn <= a0.value
            b = np.array([float(EsB[s][le][-1]) if le.any() else 1.0 for s in range(4)])
            es = np.mean([EsB[s][seg] / b[s] for s in range(4)], axis=0)
            ms = np.mean([MsB[s][seg] / b[s] for s in range(4)], axis=0)
            pk = np.maximum.accumulate(es)
            R = round(100 * float(es[-1] ** (1 / 12) - 1), 3)
            DD = round(100 * float(np.max(1 - ms / pk)), 2)
            ys.append((R, DD, round(float(es[-1]), 6)))
        base_years[bname] = ys
    exp21 = json.loads(V421_RES.read_text())["rows"][STRAT_G2]
    exp22 = json.loads(V422_RES.read_text())["rows"][STRAT_K20]
    assert [(r, d) for r, d, _ in base_years["G2"]] == [
        tuple(x) for x in exp21["years"]], base_years["G2"]
    assert [(r, d) for r, d, _ in base_years["G2K20"]] == [
        tuple(x) for x in exp22["years"]], base_years["G2K20"]

    Etot = {"G2": Es_g2.mean(axis=0), "G2K20": Es_k.mean(axis=0)}
    Mtot = {"G2": Ms_g2.mean(axis=0), "G2K20": Ms_k.mean(axis=0)}
    full_base = {}
    for bname in ("G2", "G2K20"):
        es, ms = Etot[bname], Mtot[bname]
        pk = np.maximum.accumulate(es)
        dd_m = round(100 * float(np.max(1 - ms / pk)), 2)
        dd_c = round(100 * float(np.max(1 - es / pk)), 2)
        full_base[bname] = {"marked": dd_m, "close": dd_c, "full": max(dd_m, dd_c)}
    assert full_base["G2"]["full"] == exp21["full_path_dd"], full_base["G2"]
    assert full_base["G2K20"]["full"] == exp22["full_path_dd"], full_base["G2K20"]
    R5 = {b: round(float(np.prod([1 + r / 100 for r, _, _ in base_years[b]]) ** (1 / 5) - 1) * 100, 3)
          for b in ("G2", "G2K20")}
    assert (R5["G2"], R5["G2K20"]) == (exp21["R"], exp22["R"]), (R5, exp21["R"], exp22["R"])
    print(f"baseline OK: G2 {R5['G2']}/{exp21['DD']}/{full_base['G2']['full']} "
          f"G2K20 {R5['G2K20']}/{exp22['DD']}/{full_base['G2K20']['full']}")

    # ---------------- PHASE 1: dev4 for all 10 rows ----------------
    seg_idx = [np.where((grid > a0) & (grid <= a0 + YEAR))[0] for a0 in ANCH]
    rows: dict[str, dict] = {}
    for bname in ("G2", "G2K20"):
        EsB = Es_g2 if bname == "G2" else Es_k
        MsB = Ms_g2 if bname == "G2" else Ms_k
        rows[bname] = {"base": bname, "m": None, "h": None,
                       "years": [{"anchor": str(ANCH[y].date()), "R": r, "DDc": d,
                                  "DDopt": d, "end": e,
                                  "cost": 0.0, "n_buy": 0, "n_tp": 0}
                                 for y, (r, d, e) in enumerate(base_years[bname])],
                       "full": full_base[bname]}
        for m in M_ROWS:
            for h in H_ROWS:
                key = f"{bname}+H(m{m},h{h})"
                years = []
                for y in range(4):
                    seg = seg_idx[y]
                    le = gn <= ANCH[y].value
                    b = np.array([float(EsB[s][le][-1]) if le.any() else 1.0
                                  for s in range(4)])
                    es = np.mean([EsB[s][seg] / b[s] for s in range(4)], axis=0)
                    ms = np.mean([MsB[s][seg] / b[s] for s in range(4)], axis=0)
                    A, Mc, Mo, _, info = simulate(es, ms, np.arange(len(seg)),
                                                  m, h, False)
                    R, DDc, DDo, end = year_stats(A, Mc, Mo)
                    years.append({"anchor": str(ANCH[y].date()), "R": R, "DDc": DDc,
                                  "DDopt": DDo, "end": end, "cost": round(info["cost"], 6),
                                  "n_buy": info["n_buy"], "n_tp": info["n_tp"]})
                Rs = [yy["R"] for yy in years]
                R4 = round(float(np.prod([1 + r / 100 for r in Rs]) ** (1 / 4) - 1) * 100, 3)
                rows[key] = {"base": bname, "m": m, "h": h, "years": years,
                             "R4": R4, "W4": min(Rs),
                             "DD4": max(yy["DDc"] for yy in years),
                             "DD4opt": max(yy["DDopt"] for yy in years),
                             "losing4": sum(r < 0 for r in Rs)}
    for bname in ("G2", "G2K20"):
        Rs = [yy["R"] for yy in rows[bname]["years"][:4]]
        rows[bname].update({"R4": round(float(np.prod([1 + r / 100 for r in Rs]) ** (1 / 4) - 1) * 100, 3),
                            "W4": min(Rs),
                            "DD4": max(yy["DDc"] for yy in rows[bname]["years"][:4]),
                            "DD4opt": max(yy["DDopt"] for yy in rows[bname]["years"][:4]),
                            "losing4": sum(r < 0 for r in Rs)})

    # robust selection on dev4
    hedge_keys = [k for k in rows if "+H(" in k]
    elig = [k for k in hedge_keys if rows[k]["DD4"] <= 20 and rows[k]["losing4"] == 0]
    pool = [k for k in elig if rows[k]["R4"] >= 5.0] or elig
    if pool:
        sub = [k for k in pool if rows[k]["R4"] >= 5.0] or pool
        chosen = max(sub, key=lambda k: (rows[k]["W4"], rows[k]["R4"]))
    else:
        chosen = max(hedge_keys, key=lambda k: (rows[k]["W4"], rows[k]["R4"]))
    print(f"dev4 choice: {chosen} R4={rows[chosen]['R4']} W4={rows[chosen]['W4']} "
          f"DD4={rows[chosen]['DD4']}")

    # ---------------- PHASE 2: most-recent year ONCE (chosen + G2) ----------------
    last: dict[str, dict] = {}
    for key in (chosen, "G2"):
        r = rows[key]
        y = 4
        seg = seg_idx[y]
        if r["m"] is None:
            yy = r["years"][y]
            last[key] = {"R": yy["R"], "DDc": yy["DDc"], "DDopt": yy["DDopt"],
                         "end": yy["end"], "cost": 0.0, "n_buy": 0, "n_tp": 0}
        else:
            EsB = Es_g2 if r["base"] == "G2" else Es_k
            MsB = Ms_g2 if r["base"] == "G2" else Ms_k
            le = gn <= ANCH[y].value
            b = np.array([float(EsB[s][le][-1]) if le.any() else 1.0 for s in range(4)])
            es = np.mean([EsB[s][seg] / b[s] for s in range(4)], axis=0)
            ms = np.mean([MsB[s][seg] / b[s] for s in range(4)], axis=0)
            A, Mc, Mo, _, info = simulate(es, ms, np.arange(len(seg)),
                                          r["m"], r["h"], False)
            R, DDc, DDo, end = year_stats(A, Mc, Mo)
            last[key] = {"R": R, "DDc": DDc, "DDopt": DDo, "end": end,
                         "cost": round(info["cost"], 6), "n_buy": info["n_buy"],
                         "n_tp": info["n_tp"]}

    # ---------------- full-path passes (all rows) + top-5 G2 DD episodes ----
    full_idx = np.arange(n)
    full_paths: dict[str, dict] = {}
    ledger: list[dict] = []
    for key, r in rows.items():
        if r["m"] is None:
            es, ms = Etot[r["base"]], Mtot[r["base"]]
            full_paths[key] = {"A": es, "dH": np.zeros(n)}
            pk = np.maximum.accumulate(es)
            dd_m = round(100 * float(np.max(1 - ms / pk)), 2)
            dd_c = round(100 * float(np.max(1 - es / pk)), 2)
            r["full"] = {"marked": dd_m, "close": dd_c, "full": max(dd_m, dd_c),
                         "marked_opt": dd_m}
        else:
            es, ms = Etot[r["base"]], Mtot[r["base"]]
            A, Mc, Mo, dH, _ = simulate(es, ms, full_idx, r["m"], r["h"], True,
                                        ledger, key)
            pk = np.maximum.accumulate(A)
            dd_c = round(100 * float(np.max(1 - Mc / pk)), 2)
            dd_o = round(100 * float(np.max(1 - Mo / pk)), 2)
            dd_a = round(100 * float(np.max(1 - A / pk)), 2)
            i_dd = int(np.argmax(1 - Mc / pk))
            i_pk = int(np.argmax(A[:i_dd + 1])) if i_dd > 0 else 0
            r["full"] = {"marked": dd_c, "close": dd_a,
                         "full": max(dd_c, dd_a), "marked_opt": dd_o,
                         "full_opt": max(dd_o, dd_a),
                         "maxdd_peak": str(grid[i_pk]), "maxdd_trough": str(grid[i_dd])}
            full_paths[key] = {"A": A, "dH": dH}
    pd.DataFrame(ledger).to_csv(HERE / "hedge_ledger.csv", index=False)

    # top-5 non-overlapping DD episodes on the GATE DD series of G2:
    # dd(t) = 1 - ms(t)/peak(es)(t); episode trough = local dd maxima.
    mg = Mtot["G2"]
    eg = Etot["G2"]
    pk_es = np.maximum.accumulate(eg)
    dd = 1 - mg / pk_es
    order = np.argsort(-dd, kind="stable")
    picked = []
    for t in order:
        if len(picked) == 5 or dd[t] <= 0:
            break
        t = int(t)
        p = int(np.argmax(eg[:t + 1]))
        lo, hi = min(p, t), max(p, t)
        if any(not (hi < plo or lo > phi) for plo, phi, _ in picked):
            continue
        picked.append((lo, hi, float(dd[t])))
    picked.sort(key=lambda e: -e[2])
    episodes = []
    for p, t, dv in picked:
        gdd = round(100 * dv, 2)
        A_ch = full_paths[chosen]["A"]
        lo, hi = min(p, t), max(p, t)
        pnl = float(full_paths[chosen]["dH"][lo + 1:hi + 1].sum())
        episodes.append({"peak": str(grid[lo]), "trough": str(grid[hi]),
                         "g2_dd_pct": gdd,
                         "hedge_pnl_chosen": round(pnl, 6),
                         "hedge_pnl_pct_of_peak": round(100 * pnl / float(A_ch[lo]), 3)})
    episodes.sort(key=lambda e: -e["g2_dd_pct"])

    key_q = "does any G2K20+H row beat G2 on dev4 mean AND have yearly/full DD <= G2's (conservative)?"
    g2r4, g2dd4, g2full = rows["G2"]["R4"], rows["G2"]["DD4"], rows["G2"]["full"]["full"]
    k20h = [k for k in hedge_keys if rows[k]["base"] == "G2K20"]
    beat = [k for k in k20h if rows[k]["R4"] > g2r4
            and rows[k]["DD4"] <= g2dd4 and rows[k]["full"]["full"] <= g2full]
    answer = bool(beat)

    out = {
        "meta": {
            "g2_src": "research/parallel/rounds/parallel-20260906-r2/v421/v421_runs.pkl strat R2B1D17BFG2",
            "g2k20_src": "research/parallel/rounds/parallel-20260906-r2/v422/v422_runs.pkl strat G2K20",
            "iv_src": "data/raw/deribit_opt_20260926/BTC_options_4h.parquet (iv_otm_put; DVOL fallback unused)",
            "iv_nan_bars_prefill": nan0,
            "spot_src": "data/raw/btc_intraday_20260924/klines_1m_20*.parquet",
            "grid": [str(grid[0]), str(grid[-1])],
            "metric": "reset_metric.year_reset per anchor year (fresh 1.0, flat hedge at reset) + v421 continuous full-path DD",
            "assumption": ("ONE account: A(t)=A(t-1)*(1+r_bot(t))+dH(t), r_bot from stored 4-phase base mean "
                           "(UTA: BOT sizes on TOTAL equity); long BTC monthly puts, BS(r=q=0) priced/marked, "
                           "fees min(0.0003*S,0.125*price)/side, settle fee min(0.00015*S,0.125*intrinsic); "
                           "rolls/settles at first grid hour after 08:05 on last-Friday-08:00UTC expiries; "
                           "TP 5x with same-m rebuy; conservative DD on hourly-close marks, optimistic on hourly-low marks"),
            "dev_years": [str(ANCH[y].date()) for y in range(4)],
            "last_year": str(ANCH[4].date()),
            "chosen": chosen,
            "key_question": key_q,
            "key_answer": answer,
            "key_beating_rows": beat,
        },
        "rows": rows,
        "last_year_once": last,
        "top5_g2_dd_episodes": episodes,
    }
    (HERE / "results.json").write_text(json.dumps(out, indent=1))
    for k, r in rows.items():
        print(f"{k}: R4={r['R4']} W4={r['W4']} DD4={r['DD4']}/{r['DD4opt']} "
              f"full={r['full']['full']}/{r['full'].get('full_opt')} losing4={r['losing4']}")
    print("last-year-once:", {k: last[k] for k in last})
    print("key Q:", key_q, "->", answer, beat)


if __name__ == "__main__":
    main()
