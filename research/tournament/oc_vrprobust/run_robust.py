"""oc_vrprobust runner: robustness of the G2 + weekly short-straddle overlay.

Copied engine from research/tournament/oc_vrpstraddle/run_vrp.py (V2 only,
parameterised by sell multiplier k, fee caps, 15-min SL) + new stages.
PLAN.md pre-registered 2026-10-07 BEFORE any outcome.

Stages (heavy ones via heavy_slot; B is light):
  A       k-sweep dev4 (standalone + G2 overlay f=0.25) + assert k=0.97
          reproduces oc_vrpstraddle to the digit; then recent year ONCE.
  C       C1 (Bybit fees) + C2 (15-min SL) + C3 (1m-marked DD), dev4.
  C4      gap stress at the worst minute (needs A paths).
  D       sizing on G2 / G2+carry + MANUAL overlay (needs carry_base).
  B       term structure from traded strike prices (light, direct run).
  collect assemble results.json from stage outputs (light).

Usage: python run_robust.py <stage>
"""
from __future__ import annotations

import importlib.util
import json
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
import vrprobust as V

RD = ROOT / "research/parallel/rounds/parallel-20260906-r2"
V421 = RD / "v421/v421_runs.pkl"
V421_RES = RD / "research/parallel/rounds/parallel-20260906-r2/v421/v421_result.json"
V421_RES = RD / "v421/v421_result.json"
DVDIR = ROOT / "data/raw/deribit_dvol_20261005"
BTC1M = ROOT / "data/raw/btc_intraday_20260924"
ETH1M = ROOT / "data/raw/majors_intraday_20260924"
VRP_RES = ROOT / "research/tournament/oc_vrpstraddle/results.json"
STK = ROOT / "data/raw/deribit_strike_20261007"

STRAT = "R2B1D17BFG2"
GRID0 = pd.Timestamp("2021-09-24 04:00", tz="UTC")
ANCH_S = ["2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24"]
ANCH = [pd.Timestamp(a, tz="UTC") for a in ANCH_S]
YEAR = pd.Timedelta(days=365)
COINS = ["BTC", "ETH"]
YK = {"BTC": 1000.0, "ETH": 50.0}
YNS = int(365 * 86400 * 1_000_000_000)
K_GRID = [0.97, 0.92, 0.88, 0.85, 0.80]

MAKER = 0.0002
TAKER = 0.00055
FUND = 0.0001
SL_MULT = 1.05


def _load_v388():
    spec = importlib.util.spec_from_file_location("v388_vrprobust", RD / "v388/v388_bot_stop_distance.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------- data ----------------

def load_dvol(coin):
    ms, cl = [], []
    for f in sorted(DVDIR.glob(f"{coin}_*.json")):
        d = json.loads(f.read_text())
        for c in d["candles"]:
            ms.append(int(c[0]))
            cl.append(float(c[4]))
    ms = np.array(ms, dtype=np.int64)
    cl = np.array(cl, dtype=float)
    o = np.argsort(ms)
    ms, cl = ms[o], cl[o]
    keep = np.ones(len(ms), dtype=bool)
    keep[1:] = ms[1:] != ms[:-1]
    return ms[keep] * 1_000_000, cl[keep]


def load_1m(coin):
    if coin == "BTC":
        files = [BTC1M / f"klines_1m_{y}.parquet" for y in (2021, 2022, 2023, 2024, 2025, 2026)]
    else:
        files = [ETH1M / f"{coin}USDT_1m_{y}.parquet" for y in (2021, 2022, 2023, 2024, 2025, 2026)]
    ts, cl = [], []
    for f in files:
        df = pd.read_parquet(f, columns=["open_time", "close"])
        ts.append(pd.to_datetime(df["open_time"], utc=True).values.astype("datetime64[ns]").astype(np.int64))
        cl.append(df["close"].to_numpy(dtype=float))
    ts = np.concatenate(ts)
    cl = np.concatenate(cl)
    o = np.argsort(ts)
    ts, cl = ts[o], cl[o]
    keep = np.ones(len(ts), dtype=bool)
    keep[1:] = ts[1:] != ts[:-1]
    return ts[keep], cl[keep]


def px_at(ts, cl, q_ns):
    i = int(np.searchsorted(ts, q_ns, side="left"))
    if i < len(ts) and ts[i] == q_ns:
        return float(cl[i]), True
    if i > 0:
        return float(cl[i - 1]), False
    return float("nan"), False


def dvol_known(d_ms, d_cl, t_ns):
    i = int(np.searchsorted(d_ms + 3600_000_000_000, t_ns, side="right")) - 1
    if i < 0:
        return float("nan")
    return float(d_cl[i])


def fridays(a0, a1):
    days = pd.date_range(a0.normalize(), a1.normalize() + pd.Timedelta(days=8), freq="D")
    return [d for d in days if d.weekday() == 4]


# ---------------- positions (V2 + parameters) ----------------

def build_positions(grid, gh, data, sell_mult=0.97, cap_rate=0.0003,
                    settle_rate=0.00015, cap_frac=0.125, sl_15m=False):
    """V2 (1-week naked) per-(cycle,coin) economics. Marks at 1.0x/1.05x DVOL
    unchanged for all k; only sigma_sell = sell_mult x DVOL varies."""
    gn = grid.values.astype("datetime64[ns]").astype(np.int64)
    positions = []
    n_inexact = 0
    fris = fridays(grid[0], grid[-1])
    for fi, fri in enumerate(fris):
        entry_t = (fri + pd.Timedelta(hours=8, minutes=5)).value
        expiry_t = (fri + pd.Timedelta(days=7, hours=8)).value
        if entry_t < gn[0] or expiry_t > gn[-1]:
            continue
        settle_lo = (fri + pd.Timedelta(days=7, hours=7, minutes=30)).value
        for coin in COINS:
            d = data[coin]
            dv = dvol_known(d["d_ms"], d["d_cl"], entry_t)
            if not np.isfinite(dv) or dv <= 0:
                positions.append({"coin": coin, "fri": str(fri.date()),
                                  "skip": "no-vol", "entry_step": -1})
                continue
            sigma_sell = sell_mult * dv / 100.0
            s_min = (fri + pd.Timedelta(hours=8, minutes=4)).value
            S, exact = px_at(d["m_ts"], d["m_cl"], s_min)
            n_inexact += (not exact)
            if not np.isfinite(S) or S <= 0:
                positions.append({"coin": coin, "fri": str(fri.date()),
                                  "skip": "no-price", "entry_step": -1})
                continue
            K = V.strike_round(S, YK[coin])
            if not np.isfinite(K) or K <= 0:
                positions.append({"coin": coin, "fri": str(fri.date()),
                                  "skip": "bad-strike", "entry_step": -1})
                continue
            T_entry = (expiry_t - entry_t) / YNS
            prem_c = V.bs_call(S, K, T_entry, sigma_sell)
            prem_p = V.bs_put(S, K, T_entry, sigma_sell)
            gross = prem_c + prem_p
            fee_c = V.fee_per_side(S, prem_c, cap_rate, cap_frac)
            fee_p = V.fee_per_side(S, prem_p, cap_rate, cap_frac)
            opt_cash = gross - fee_c - fee_p
            e_step = int(np.searchsorted(gn, entry_t, side="right"))
            x_step = int(np.searchsorted(gn, expiry_t, side="left"))
            sl = slice(e_step, x_step + 1)
            L = x_step - e_step + 1
            gseg = gn[sl]
            h = gh[coin]
            px = h["px"][sl]
            sigv = h["dv"][sl] / 100.0
            if not np.all(np.isfinite(sigv)):
                positions.append({"coin": coin, "fri": str(fri.date()),
                                  "skip": "no-vol-path", "entry_step": -1})
                continue
            T = (expiry_t - gseg) / YNS
            sig_m = sigv
            sig_sl = SL_MULT * sigv
            m10 = V.bs_straddle_vec(px, K, T, sig_m)
            # hourly walk (base)
            exit_kind, exit_j = "expiry", L - 1
            for j in range(L - 1):
                s = e_step + j
                is_4h = pd.Timestamp(gn[s], tz="UTC").hour % 4 == 0
                if is_4h and m10[j] <= 0.3 * gross:
                    exit_kind, exit_j = "tp", j
                    break
                m105 = V.bs_straddle(px[j], K, T[j], sig_sl[j])
                if opt_cash - m105 <= -gross:
                    exit_kind, exit_j = "sl", j
                    break
            done15 = False
            if sl_15m:
                # unified quarter-hour SL walk (TP still 4h closes first).
                # First check quarter = 09:00 (same embargo as base).
                q0 = (fri + pd.Timedelta(hours=9)).value
                q1 = gn[e_step + exit_j]  # never later than the hourly exit
                qq = np.arange((q0 // 900_000_000_000) * 900_000_000_000,
                               q1, 900_000_000_000)
                hk = {int(t): (e_step + k) for k, t in enumerate(gn[sl])}
                for q in qq:
                    if q < q0 or q >= q1:
                        continue
                    if q in hk:
                        j = hk[q] - e_step
                        s = hk[q]
                        if pd.Timestamp(gn[s], tz="UTC").hour % 4 == 0 and m10[j] <= 0.3 * gross:
                            exit_kind, exit_j = "tp", j
                            break
                    pxq, ex = px_at(d["m_ts"], d["m_cl"], int(q) - 60_000_000_000)
                    n_inexact += (not ex)
                    sigq = dvol_known(d["d_ms"], d["d_cl"], int(q))
                    if not (np.isfinite(pxq) and pxq > 0 and np.isfinite(sigq) and sigq > 0):
                        continue
                    Tq = (expiry_t - int(q)) / YNS
                    if Tq <= 0:
                        continue
                    sigq_sl = SL_MULT * sigq / 100.0
                    markq = V.bs_straddle(pxq, K, Tq, sigq_sl)
                    if opt_cash - markq <= -gross:
                        j = int(np.searchsorted(gn, int(q), side="right")) - e_step
                        j = max(0, min(j, L - 1))
                        exit_kind, exit_j = "sl15", j
                        leg_c = V.bs_call(pxq, K, Tq, sigq_sl)
                        leg_p = V.bs_put(pxq, K, Tq, sigq_sl)
                        fc = V.fee_per_side(pxq, leg_c, cap_rate, cap_frac)
                        fp = V.fee_per_side(pxq, leg_p, cap_rate, cap_frac)
                        buy = leg_c + leg_p
                        p15 = {
                            "coin": coin, "fri": str(fri.date()), "skip": None,
                            "S": S, "K": K, "sig_raw": float(dv), "gross": float(gross),
                            "opt_cash": float(opt_cash), "entry_t": int(entry_t),
                            "expiry_t": int(expiry_t), "entry_step": e_step,
                            "expiry_step": x_step, "exit_kind": exit_kind,
                            "exit_step": e_step + exit_j, "exit_j": exit_j,
                            "cf_exit": float(-(buy + fc + fp)),
                            "pnl_u": float(opt_cash - (buy + fc + fp)),
                            "S_settle": float("nan"), "rv": float("nan"),
                            "m10": m10.astype(float), "pos": np.zeros(L), "hc": np.zeros(L),
                        }
                        record_rv(p15, d, s_min, fri, 1)
                        positions.append(p15)
                        done15 = True
                        break
                # NOTE: if the quarter walk re-finds the base hourly exit
                # (:00 quarters carry identical px/sigma), exit_kind/exit_j
                # keep base values and the position is built by the shared
                # block below with identical economics.
            if done15:
                continue
            pnl_u, cf_exit, S_set = None, None, float("nan")
            px_x = float(px[exit_j])
            if exit_kind in ("tp", "sl"):
                sigx = float(sig_sl[exit_j]) if exit_kind == "sl" else float(sig_m[exit_j])
                Tx = float(T[exit_j])
                leg_c = V.bs_call(px_x, K, Tx, sigx)
                leg_p = V.bs_put(px_x, K, Tx, sigx)
                fc = V.fee_per_side(px_x, leg_c, cap_rate, cap_frac)
                fp = V.fee_per_side(px_x, leg_p, cap_rate, cap_frac)
                buy = leg_c + leg_p
                cf_exit = -(buy + fc + fp)
                pnl_u = opt_cash + cf_exit
            else:
                s_vals = []
                for k in range(30):
                    q = settle_lo + k * 60_000_000_000
                    pxq, ex = px_at(d["m_ts"], d["m_cl"], q)
                    n_inexact += (not ex)
                    s_vals.append(pxq)
                S_set = float(np.mean(s_vals))
                intr_c = max(S_set - K, 0.0)
                intr_p = max(K - S_set, 0.0)
                stl = V.settle_fee(S_set, intr_c, settle_rate, cap_frac) + V.settle_fee(S_set, intr_p, settle_rate, cap_frac)
                cf_exit = -((intr_c + intr_p) + stl)
                pnl_u = opt_cash + cf_exit
            p = {"coin": coin, "fri": str(fri.date()), "skip": None,
                 "S": S, "K": K, "sig_raw": float(dv), "gross": float(gross),
                 "opt_cash": float(opt_cash), "entry_t": int(entry_t),
                 "expiry_t": int(expiry_t), "entry_step": e_step,
                 "expiry_step": x_step, "exit_kind": exit_kind,
                 "exit_step": e_step + exit_j, "exit_j": exit_j,
                 "cf_exit": float(cf_exit), "pnl_u": float(pnl_u),
                 "S_settle": float(S_set), "rv": float("nan"),
                 "m10": m10.astype(float), "pos": np.zeros(L), "hc": np.zeros(L)}
            record_rv(p, d, s_min, fri, 1)
            positions.append(p)
    print(f"[k={sell_mult}/sl15={sl_15m}] positions={len(positions)} "
          f"skipped={sum(1 for p in positions if p.get('skip'))} inexact_px={n_inexact}")
    return positions


def record_rv(p, d, s_min, fri, weeks):
    lo = int(np.searchsorted(d["m_ts"], s_min, side="left"))
    hi = int(np.searchsorted(d["m_ts"], (fri + pd.Timedelta(days=7 * weeks, hours=8)).value, side="left"))
    seg = d["m_cl"][lo:hi + 1]
    if len(seg) > 10 and np.all(seg > 0) and np.all(np.isfinite(seg)):
        r = np.diff(np.log(seg))
        p["rv"] = float(np.std(r, ddof=1) * np.sqrt(365 * 24 * 60))


# ---------------- account simulation (copy of run_vrp V2 path) ----------------

def year_slices(grid):
    gn = grid.values.astype("datetime64[ns]").astype(np.int64)
    out = []
    for a0 in ANCH:
        a1 = a0 + YEAR
        idx = np.where((grid > a0) & (grid <= a1))[0]
        out.append((str(a0.date()), idx))
    return out


def simulate_year(grid, idx, positions, g=None, hh=None, f=1.0, standalone=True,
                  pxmap=None, tag="", entry_acct=None, track=False):
    n = len(idx)
    gn = grid.values.astype("datetime64[ns]").astype(np.int64)
    year_end_ns = (grid[idx[-1]] + pd.Timedelta(hours=1)).value
    ev_entry: dict[int, list] = {}
    ev_exit: dict[int, list] = {}
    n_skip = 0
    for p in positions:
        if p.get("skip") or p["entry_step"] < 0:
            continue
        e = p["entry_step"] - idx[0]
        if not (0 <= e < n):
            continue
        if p["expiry_t"] > year_end_ns:
            n_skip += 1
            continue
        ev_entry.setdefault(e, []).append(p)
        x = p["exit_step"] - idx[0]
        if 0 <= x < n:
            ev_exit.setdefault(x, []).append(p)
    E = np.empty(n)
    Mc = np.empty(n)
    dU_arr = np.zeros(n)
    g2_arr = np.zeros(n)
    cash = 1.0
    A_prev = 1.0
    cash_prev, U_prev = 1.0, 0.0
    open_p = []
    qmap = {}
    trades = []
    opt_leg = 0.0
    track_cash = np.empty(n) if track else None
    track_U = np.empty(n) if track else None
    track_open = [] if track else None
    for i in range(n):
        gi = 1.0 if g is None else float(g[i])
        hhi = 1.0 if hh is None else float(hh[i])
        for p in ev_entry.get(i, []):
            acct = (cash + U_prev) if standalone else A_prev
            ff = 1.0 if standalone else f
            q = V.size_q(acct, p["S"], ff)
            qmap[id(p)] = q
            if entry_acct is not None:
                entry_acct[(p["fri"], p["coin"])] = acct
            open_p.append(p)
            cash += q * p["opt_cash"]
        for p in ev_exit.get(i, []):
            q = qmap.pop(id(p), 0.0)
            if p in open_p:
                open_p.remove(p)
            j = p["exit_j"]
            cash += q * p["cf_exit"]
            opt_leg += q * (p["opt_cash"] + p["cf_exit"])
            trades.append({"fri": p["fri"], "coin": p["coin"], "exit": p["exit_kind"],
                           "q": q, "K": p["K"], "gross": p["gross"], "pnl": q * p["pnl_u"],
                           "win": bool(p["pnl_u"] > 0), "iv": p["sig_raw"], "rv": p["rv"]})
        U = 0.0
        for o in open_p:
            j = idx[i] - o["entry_step"]
            assert 0 <= j < len(o["m10"]), (tag, i, j)
            q = qmap.get(id(o), 0.0)
            pxs = pxmap[o["coin"]][idx[i]]
            U += q * (-float(o["m10"][j]))
        acct_now = cash + U
        if standalone:
            A_i, M_i = acct_now, acct_now
            dU = 0.0
            g2l = 0.0
        else:
            dU = acct_now - (cash_prev + U_prev)
            A_i = A_prev * gi + dU
            M_i = A_prev * hhi + dU
            g2l = A_prev * (gi - 1.0)
        E[i] = A_i
        Mc[i] = M_i
        dU_arr[i] = dU
        g2_arr[i] = g2l
        if track:
            track_cash[i] = cash
            track_U[i] = U
            track_open.append([(o["fri"], o["coin"], qmap.get(id(o), 0.0)) for o in open_p])
        cash_prev, U_prev, A_prev = cash, U, A_i
    pk = np.maximum.accumulate(E)
    dd = float(np.max(1 - Mc / pk)) if np.all(pk > 0) else float("nan")
    R = float(E[-1] ** (1 / 12) - 1) * 100 if E[-1] > 0 else float("-inf")
    worst = None
    worst_dt = None
    for k in range(168, n):
        r = E[k] / E[k - 168] - 1 if E[k - 168] > 0 else float("nan")
        if np.isfinite(r) and (worst is None or r < worst):
            worst, worst_dt = r, str(grid[idx[k]].date())
    n_tr = len(trades)
    wins = sum(t["win"] for t in trades)
    kinds = {k: sum(1 for t in trades if t["exit"] == k) for k in ("tp", "sl", "sl15", "expiry")}
    gaps = [(t["iv"] / 100.0 - t["rv"]) for t in trades
            if np.isfinite(t["iv"]) and np.isfinite(t["rv"])]
    ivs = [t["iv"] for t in trades if np.isfinite(t["iv"])]
    rvs = [t["rv"] for t in trades if np.isfinite(t["rv"])]
    total = float(E[-1] - 1.0)
    out = {"E": E, "M": Mc, "R": round(R, 3), "DD": round(dd * 100, 2),
           "end": round(float(E[-1]), 6), "trades": trades, "n": n_tr,
           "win": round(wins / n_tr, 4) if n_tr else 0.0,
           "tp": kinds["tp"], "sl": kinds["sl"] + kinds["sl15"], "expiry": kinds["expiry"],
           "worst_week": None if worst is None else [worst_dt, round(worst * 100, 2)],
           "gap": round(float(np.mean(gaps)), 4) if gaps else None,
           "iv_mean": round(float(np.mean(ivs)), 2) if ivs else None,
           "rv_mean": round(float(np.mean(rvs)), 4) if rvs else None,
           "opt_leg": round(opt_leg, 6), "hedge_leg": round(total - opt_leg, 6),
           "n_skip": n_skip, "dU": dU_arr, "g2": g2_arr}
    if track:
        out["track_cash"] = track_cash
        out["track_U"] = track_U
        out["track_open"] = track_open
    return out


# ---------------- shared loading ----------------

def load_all():
    v388 = _load_v388()
    g1 = v388.Y1 + pd.Timedelta(hours=12)
    grid = pd.date_range(GRID0, g1, freq="1h")
    gn = grid.values.astype("datetime64[ns]").astype(np.int64)
    print("grid", grid[0], "->", grid[-1], len(grid), flush=True)
    runs = pickle.loads(V421.read_bytes())
    Es, Ms = [], []
    for s in range(4):
        e1, m1 = v388.hourly(runs[s][STRAT], GRID0, g1)
        assert (e1.index == grid).all()
        Es.append(e1.to_numpy(dtype=float))
        Ms.append(m1.to_numpy(dtype=float))
    Es = np.stack(Es)
    Ms = np.stack(Ms)
    sys.path.insert(0, str(ROOT / "research/diagnostics/r2_decompose5"))
    from reset_metric import year_reset
    exp = json.loads(V421_RES.read_text())["rows"][STRAT]
    got_years = [year_reset(runs, STRAT, y) for y in range(5)]
    assert [r["R"] for r in got_years] == [rr for rr, _ in exp["years"]], got_years
    assert [r["DD"] for r in got_years] == [dd for _, dd in exp["years"]], got_years
    print("G2 baseline validation OK", flush=True)
    data = {}
    for coin in COINS:
        d_ms, d_cl = load_dvol(coin)
        m_ts, m_cl = load_1m(coin)
        data[coin] = {"d_ms": d_ms, "d_cl": d_cl, "m_ts": m_ts, "m_cl": m_cl}
    gh = {}
    pxmap = {}
    for coin in COINS:
        d = data[coin]
        px = np.array([px_at(d["m_ts"], d["m_cl"], int(t) - 60_000_000_000)[0] for t in gn])
        assert np.isfinite(px).all(), coin
        dv = np.array([dvol_known(d["d_ms"], d["d_cl"], int(t)) for t in gn])
        gh[coin] = {"px": px, "dv": dv}
        pxmap[coin] = px
    return v388, grid, gn, gh, data, pxmap, Es, Ms, exp


def g2_year(Es, Ms, grid, y, idx):
    gn = grid.values.astype("datetime64[ns]").astype(np.int64)
    le = gn <= ANCH[y].value
    b = np.array([float(Es[s][le][-1]) if le.any() else 1.0 for s in range(4)])
    es = np.mean([Es[s][idx] / b[s] for s in range(4)], axis=0)
    ms = np.mean([Ms[s][idx] / b[s] for s in range(4)], axis=0)
    es_prev = np.concatenate([[1.0], es[:-1]])
    return es / es_prev, ms / es_prev


def overlay_full_dd(grid, Es, Ms, positions, f, pxmap, tag=""):
    mask = grid > pd.Timestamp("2021-09-24", tz="UTC")
    fidx = np.where(mask)[0]
    Etot_p = Es.mean(axis=0)[mask]
    Mtot_p = Ms.mean(axis=0)[mask]
    Eprev = np.concatenate([[Etot_p[0]], Etot_p[:-1]])
    r = simulate_year(grid, fidx, positions, g=Etot_p / Eprev, hh=Mtot_p / Eprev,
                      f=f, standalone=False, pxmap=pxmap, tag=tag)
    Ec, Mc = r["E"], r["M"]
    pk = np.maximum.accumulate(Ec)
    dd_m = round(100 * float(np.max(1 - Mc / pk)), 2)
    dd_c = round(100 * float(np.max(1 - Ec / pk)), 2)
    return max(dd_m, dd_c), dd_m, dd_c


# ---------------- stages ----------------

def stage_A():
    v388, grid, gn, gh, data, pxmap, Es, Ms, exp = load_all()
    (HERE / "tmp").mkdir(exist_ok=True)
    dev_idx = year_slices(grid)[:4]
    all_idx = year_slices(grid)
    vrp = json.loads(VRP_RES.read_text())
    out = {"standalone": {}, "overlay_f025": {}, "recent": {}}
    for k in K_GRID:
        positions = build_positions(grid, gh, data, sell_mult=k)
        sa = {}
        for ay, idx in dev_idx:
            r = simulate_year(grid, idx, positions, standalone=True, pxmap=pxmap, tag=f"k{k}")
            sa[ay] = {"R": r["R"], "DD": r["DD"], "end": r["end"], "trades": r["n"],
                       "win": r["win"], "tp": r["tp"], "sl": r["sl"], "expiry": r["expiry"]}
        R4 = float(np.prod([1 + sa[ay]["R"] / 100 for ay, _ in dev_idx]) ** (1 / 4) - 1) * 100
        out["standalone"][str(k)] = {
            "years": sa, "dev4_mean": round(R4, 3),
            "dev4_worst": min(sa[ay]["R"] for ay, _ in dev_idx),
            "dev4_DD": max(sa[ay]["DD"] for ay, _ in dev_idx),
            "dev4_losing": sum(sa[ay]["R"] < 0 for ay, _ in dev_idx)}
        print("standalone k=", k, out["standalone"][str(k)], flush=True)
        if k == 0.97:
            for ay, _ in dev_idx:
                ref = vrp["standalone"][ay]
                got = sa[ay]
                assert got["R"] == ref["R"] and got["DD"] == ref["DD"] and \
                    got["trades"] == ref["trades"] and got["win"] == ref["win"] and \
                    got["tp"] == ref["tp"] and got["sl"] == ref["sl"] and \
                    got["expiry"] == ref["expiry"], (ay, got, ref)
            print("k=0.97 standalone reproduces oc_vrpstraddle V2 dev4 to the digit", flush=True)
        ov = {}
        for y, (ay, idx) in enumerate(dev_idx):
            g, hh = g2_year(Es, Ms, grid, y, idx)
            r = simulate_year(grid, idx, positions, g=g, hh=hh, f=0.25,
                              standalone=False, pxmap=pxmap, tag=f"k{k}")
            ov[ay] = {"R": r["R"], "DD": r["DD"], "end": r["end"]}
        R4o = float(np.prod([1 + ov[ay]["R"] / 100 for ay, _ in dev_idx]) ** (1 / 4) - 1) * 100
        dd_full, dd_m, dd_c = overlay_full_dd(grid, Es, Ms, positions, 0.25, pxmap, tag=f"k{k}")
        out["overlay_f025"][str(k)] = {
            "years": ov, "dev4_mean": round(R4o, 3),
            "dev4_worst": min(ov[ay]["R"] for ay, _ in dev_idx),
            "dev4_DD": max(ov[ay]["DD"] for ay, _ in dev_idx),
            "dev4_losing": sum(ov[ay]["R"] < 0 for ay, _ in dev_idx),
            "full_path_DD": dd_full}
        print("overlay k=", k, out["overlay_f025"][str(k)], flush=True)
        if k == 0.97:
            ref = vrp["overlay"]["G2_f0.25"]
            for (ay, _), rr in zip(dev_idx, ref["years"]):
                assert ov[ay]["R"] == rr["R"] and ov[ay]["DD"] == rr["DD"], (ay, ov[ay], rr)
            print("k=0.97 overlay reproduces oc_vrpstraddle G2+0.25 dev4 to the digit", flush=True)
    # save base (k=0.97) yearly-reset overlay paths + entry accounts for C3/C4
    positions = build_positions(grid, gh, data, sell_mult=0.97)
    paths = {}
    entry_acct = {}
    for y, (ay, idx) in enumerate(dev_idx):
        g, hh = g2_year(Es, Ms, grid, y, idx)
        ea: dict = {}
        r = simulate_year(grid, idx, positions, g=g, hh=hh, f=0.25,
                          standalone=False, pxmap=pxmap, tag="base097",
                          entry_acct=ea, track=True)
        paths[ay] = {"E": r["E"], "M": r["M"], "dU": r["dU"], "g2": r["g2"],
                      "cash": r["track_cash"], "U": r["track_U"]}
        np.save(HERE / "tmp" / f"a_path_{ay}.npy",
                np.stack([r["E"], r["M"], r["dU"], r["g2"], r["track_cash"], r["track_U"]]))
        for (fri, coin), acct in ea.items():
            entry_acct[f"{ay}|{fri}|{coin}"] = acct
    (HERE / "tmp" / "a_entry_acct.json").write_text(json.dumps(entry_acct))
    (HERE / "tmp" / "a_idx.json").write_text(json.dumps(
        {ay: [int(idx[0]), int(idx[-1])] for ay, idx in dev_idx}))
    # recent year ONCE for all k rows + G2 ref (descriptive, pre-registered)
    ay, idx = all_idx[4]
    for k in K_GRID:
        positions = build_positions(grid, gh, data, sell_mult=k)
        rs = simulate_year(grid, idx, positions, standalone=True, pxmap=pxmap, tag=f"recent{k}")
        g, hh = g2_year(Es, Ms, grid, 4, idx)
        ro = simulate_year(grid, idx, positions, g=g, hh=hh, f=0.25,
                           standalone=False, pxmap=pxmap, tag=f"recent{k}")
        out["recent"][str(k)] = {
            "standalone": {"R": rs["R"], "DD": rs["DD"], "end": rs["end"], "trades": rs["n"], "win": rs["win"]},
            "overlay": {"R": ro["R"], "DD": ro["DD"], "end": ro["end"]}}
        print("recent k=", k, out["recent"][str(k)], flush=True)
    out["recent"]["G2"] = {"R": exp["years"][4][0], "DD": exp["years"][4][1]}
    (HERE / "tmp" / "A.json").write_text(json.dumps(out, indent=1))
    print("stage A done", flush=True)


def stage_C():
    v388, grid, gn, gh, data, pxmap, Es, Ms, exp = load_all()
    dev_idx = year_slices(grid)[:4]
    out = {}
    # C1: Bybit fees (0.07 cap legs + 0.0003-rate settlement, same formula)
    positions = build_positions(grid, gh, data, sell_mult=0.97, cap_rate=0.0003,
                                settle_rate=0.0003, cap_frac=0.07)
    sa, ov = {}, {}
    for ay, idx in dev_idx:
        r = simulate_year(grid, idx, positions, standalone=True, pxmap=pxmap, tag="C1")
        sa[ay] = {"R": r["R"], "DD": r["DD"], "end": r["end"], "trades": r["n"], "win": r["win"]}
    for y, (ay, idx) in enumerate(dev_idx):
        g, hh = g2_year(Es, Ms, grid, y, idx)
        r = simulate_year(grid, idx, positions, g=g, hh=hh, f=0.25,
                          standalone=False, pxmap=pxmap, tag="C1")
        ov[ay] = {"R": r["R"], "DD": r["DD"], "end": r["end"]}
    out["C1_bybit_fees"] = {"standalone": sa, "overlay_f025": ov}
    print("C1", json.dumps(out["C1_bybit_fees"])[:600], flush=True)
    # C2: 15-min SL
    positions = build_positions(grid, gh, data, sell_mult=0.97, sl_15m=True)
    # sanity: 15-min checks can only accelerate the SL, never delay it.
    # Non-sl15 positions must match the hourly twin exactly; sl15 exits must
    # occur at or before the twin's exit step.
    twin = build_positions(grid, gh, data, sell_mult=0.97, sl_15m=False)
    assert len(twin) == len(positions)
    n_early = 0
    for a, b in zip(twin, positions):
        assert (a.get("skip") is not None) == (b.get("skip") is not None)
        if a.get("skip") is None:
            assert (a["fri"], a["coin"]) == (b["fri"], b["coin"])
            if b["exit_kind"] == "sl15":
                assert b["exit_step"] <= a["exit_step"], (a["fri"], a["coin"])
                n_early += 1
            else:
                assert a["exit_kind"] == b["exit_kind"] and a["exit_j"] == b["exit_j"] and \
                    abs(a["pnl_u"] - b["pnl_u"]) < 1e-9, (a["fri"], a["coin"], a["exit_kind"], b["exit_kind"])
    print(f"C2 nesting check OK: {n_early} accelerated SLs, rest identical to hourly",
          flush=True)
    sa, ov = {}, {}
    n_sl15 = sum(1 for p in positions if not p.get("skip") and p.get("exit_kind") == "sl15")
    for ay, idx in dev_idx:
        r = simulate_year(grid, idx, positions, standalone=True, pxmap=pxmap, tag="C2")
        sa[ay] = {"R": r["R"], "DD": r["DD"], "end": r["end"], "trades": r["n"],
                   "win": r["win"], "sl": r["sl"]}
    for y, (ay, idx) in enumerate(dev_idx):
        g, hh = g2_year(Es, Ms, grid, y, idx)
        r = simulate_year(grid, idx, positions, g=g, hh=hh, f=0.25,
                          standalone=False, pxmap=pxmap, tag="C2")
        ov[ay] = {"R": r["R"], "DD": r["DD"], "end": r["end"]}
    out["C2_sl15m"] = {"standalone": sa, "overlay_f025": ov, "n_sl15_dev4": n_sl15}
    print("C2", json.dumps(out["C2_sl15m"])[:600], flush=True)
    # C3: 1m-marked combined DD at G2 top-20 DD minutes + sleeve worst 10 hours
    positions = build_positions(grid, gh, data, sell_mult=0.97)
    mask = grid > pd.Timestamp("2021-09-24", tz="UTC")
    Etot = Es.mean(axis=0)
    Mtot = Ms.mean(axis=0)
    pk = np.maximum.accumulate(Etot[mask])
    ddr = 1 - Mtot[mask] / pk
    fidx = np.where(mask)[0]
    top20 = fidx[np.argsort(-ddr)[:20]]
    # sleeve worst 10 hours: continuous standalone dev4, most negative hourly dE
    dev4mask = (grid > pd.Timestamp("2021-09-24", tz="UTC")) & (grid <= pd.Timestamp("2025-09-24", tz="UTC"))
    didx = np.where(dev4mask)[0]
    rs = simulate_year(grid, didx, positions, standalone=True, pxmap=pxmap, tag="C3sleeve")
    dE = np.diff(np.concatenate([[1.0], rs["E"]]))
    w10 = didx[np.argsort(dE)[:10]]
    targets = sorted(set(int(t) for t in list(top20) + list(w10)))
    # continuous overlay dev4 with tracking for q per open position
    # NOTE: overlay needs base g/hh; build from Etot/Mtot (continuous, no reset)
    Eprev = np.concatenate([[Etot[didx[0]]], Etot[didx[:-1]]])
    gfull = Etot[didx] / Eprev
    hfull = Mtot[didx] / Eprev
    ro = simulate_year(grid, didx, positions, g=gfull, hh=hfull, f=0.25,
                       standalone=False, pxmap=pxmap, tag="C3ov", track=True)
    by_pos = {(p["fri"], p["coin"]): p for p in positions if not p.get("skip")}
    # 1m marking at targets
    rows = []
    worst_1m = 0.0
    for t in targets:
        step = int(t)
        rel = step - didx[0]
        if not (0 <= rel < len(didx)):
            continue
        px1 = {c: px_at(data[c]["m_ts"], data[c]["m_cl"], int(gn[step]) - 60_000_000_000)[0]
               for c in COINS}
        U_1m = 0.0
        det = []
        for (fri, coin, q) in ro["track_open"][rel]:
            p = by_pos[(fri, coin)]
            j = step - p["entry_step"]
            if not (0 <= j < len(p["m10"])):
                continue
            sig = dvol_known(data[coin]["d_ms"], data[coin]["d_cl"], int(gn[step]))
            Tleft = (p["expiry_t"] - int(gn[step])) / YNS
            m1 = V.bs_straddle(px1[coin], p["K"], Tleft, sig / 100.0)
            U_1m += q * (-m1)
            det.append({"fri": fri, "coin": coin, "px_h": float(pxmap[coin][step]),
                         "px_1m": float(px1[coin]), "m_h": float(p["m10"][j]), "m_1m": float(m1)})
        dU_1m = U_1m - ro["track_U"][rel]
        M_1m = ro["M"][rel] + dU_1m
        peak = float(np.max(ro["E"][:rel + 1]))
        dd_1m = 1 - M_1m / peak if peak > 0 else float("nan")
        worst_1m = max(worst_1m, float(dd_1m))
        rows.append({"t": str(grid[step]), "M_h": round(float(ro["M"][rel]), 6),
                      "M_1m": round(float(M_1m), 6), "dd_1m_pct": round(float(dd_1m) * 100, 2),
                      "n_open": len(det)})
    out["C3_1m_marked"] = {"n_targets": len(targets), "worst_1m_dd_pct": round(worst_1m * 100, 2),
                            "hourly_overlay_maxDD_dev4cont": round(
                                float(np.max(1 - ro["M"] / np.maximum.accumulate(ro["E"]))) * 100, 2),
                            "rows": rows}
    print("C3 worst 1m dd%", out["C3_1m_marked"]["worst_1m_dd_pct"], flush=True)
    (HERE / "tmp" / "C.json").write_text(json.dumps(out, indent=1, default=str))
    print("stage C done", flush=True)


def stage_C4():
    v388, grid, gn, gh, data, pxmap, Es, Ms, exp = load_all()
    dev_idx = year_slices(grid)[:4]
    # worst minute from saved base overlay paths (yearly-reset, f=0.25, k=0.97)
    worst = None
    for ay, idx in dev_idx:
        arr = np.load(HERE / "tmp" / f"a_path_{ay}.npy")  # E,M,dU,g2,cash,U
        E = arr[0]
        prev = np.concatenate([[1.0], E[:-1]])
        ret = E / prev - 1
        i = int(np.argmin(ret))
        if worst is None or ret[i] < worst[0]:
            worst = (float(ret[i]), ay, idx, i, arr)
    ret_w, ay_w, idx_w, i_w, arr_w = worst
    step_w = int(idx_w[i_w])
    T_w = pd.Timestamp(int(gn[step_w]), tz="UTC")
    A_w = float(arr_w[0][i_w])
    A_prev = float(arr_w[0][i_w - 1]) if i_w > 0 else 1.0
    print(f"worst combined minute: {T_w} ret={ret_w * 100:.2f}% acct={A_w:.4f}", flush=True)
    # G2 exposure via oc_gapstress method (read-only import, cap 2.0 on dip)
    spec = importlib.util.spec_from_file_location(
        "gapstress_mod", ROOT / "research/tournament/oc_gapstress/compute_gapstress.py")
    gs = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gs)
    marks = gs.load_marks()
    S_num, G_num, Eq_sum = 0.0, 0.0, 0.0
    per_phase = []
    for s in range(4):
        ev, bt, eq, gb, live0, live1 = gs.load_phase(s)
        U, Fb, Fd, equity, info, _ = gs.build_state(ev, bt, eq, marks)
        ii = int(np.searchsorted(U, int(gn[step_w]), side="right")) - 1
        assert ii >= 0
        bn = float(Fb[ii].sum())
        bg = float(np.abs(Fb[ii]).sum())
        dn = float(Fd[ii].sum())
        dg = float(np.abs(Fd[ii]).sum())
        sc = 1.0 if dg < 1e-12 else min(1.0, 2.0 / dg)
        S_ph = bn + dn * sc
        G_ph = bg + dg * sc
        Eq = float(equity[ii])
        S_num += S_ph * Eq
        G_num += G_ph * Eq
        Eq_sum += Eq
        per_phase.append({"s": s, "S": round(S_ph, 4), "G": round(G_ph, 4),
                           "dip_gross": round(dg, 4), "book_gross": round(bg, 4),
                           "eq": round(Eq, 4)})
    S_mix = S_num / Eq_sum
    G_mix = G_num / Eq_sum
    # open straddles at the worst step (base k=0.97 positions + saved entry accts)
    positions = build_positions(grid, gh, data, sell_mult=0.97)
    ea = json.loads((HERE / "tmp" / "a_entry_acct.json").read_text())
    by_pos = {(p["fri"], p["coin"]): p for p in positions if not p.get("skip")}
    open_now = []
    for (fri, coin), p in by_pos.items():
        if p["entry_step"] <= step_w < p["exit_step"]:
            acct = ea.get(f"{ay_w}|{fri}|{coin}")
            if acct is None:
                continue
            q = V.size_q(acct, p["S"], 0.25)
            j = step_w - p["entry_step"]
            open_now.append((p, q, j))
    out = {"worst_minute": str(T_w), "worst_hourly_ret_pct": round(ret_w * 100, 2),
            "acct": round(A_w, 6), "G2_mix_S": round(S_mix, 4), "G2_mix_G": round(G_mix, 4),
            "per_phase": per_phase, "n_open_straddles": len(open_now)}
    for g, u in (("-10%", -0.10), ("-15%", -0.15), ("+10%", 0.10), ("+15%", 0.15)):
        m = abs(u)
        if u < 0:  # down gap: longs lose S*m (+fee to close)
            Lg2 = 100.0 * (S_mix * m + TAKER * G_mix * (1 - m))
        else:  # up gap: longs gain S*m (-fee to close)
            Lg2 = 100.0 * (-S_mix * m + TAKER * G_mix * (1 - m))
        Lslv = 0.0
        for (p, q, j) in open_now:
            coin = p["coin"]
            Spx = float(pxmap[coin][step_w])
            sig = float(gh[coin]["dv"][step_w]) / 100.0
            Tleft = (p["expiry_t"] - int(gn[step_w])) / YNS
            cur = float(p["m10"][j])
            sh = V.bs_straddle(Spx * (1 + u), p["K"], Tleft, 1.5 * sig)
            Lslv += q * (sh - cur)
        Lcmb = (Lg2 / 100.0 * A_prev + Lslv) / A_w * 100.0
        out[f"g_{g}"] = {"G2_alone_pct": round(Lg2, 2),
                               "overlay_combined_pct": round(float(Lcmb), 2),
                               "diff_pp": round(float(Lcmb) - Lg2, 2)}
    print(json.dumps(out, indent=1), flush=True)
    (HERE / "tmp" / "C4.json").write_text(json.dumps(out, indent=1))
    print("stage C4 done", flush=True)


def stage_D():
    import carry_base as CB
    v388, grid, gn, gh, data, pxmap, Es, Ms, exp = load_all()
    dev_idx = year_slices(grid)[:4]
    all_idx = year_slices(grid)
    trades = CB.load_carry_trades(grid)
    # validate G2+carry f=0.25 reproduces oc_carrycompound to the digit
    cc_exp = json.loads((ROOT / "research/tournament/oc_carrycompound/results.json").read_text())
    for y, (ay, idx) in enumerate(all_idx):
        a0 = ANCH[y]
        _, gb, hb, A_arr, M_arr = CB.year_base_g_hh(Es, Ms, grid, trades, 0.25, a0)
        pk = np.maximum.accumulate(A_arr)
        R = round(100 * float(A_arr[-1] ** (1 / 12) - 1), 3)
        DD = round(100 * float(np.max(1 - M_arr / pk)), 2)
        ref = cc_exp["rows"]["G2_f0.25"]["years"][y]
        assert R == ref["R"] and DD == ref["DD"], (ay, R, DD, ref)
    print("G2+carry f=0.25 validation OK (reproduces oc_carrycompound yearly R/DD)", flush=True)
    positions = build_positions(grid, gh, data, sell_mult=0.97)
    out = {"sizing": {}, "manual": {}}
    # D1: f grid on G2 and on G2+carry
    for base in ("G2", "G2carry"):
        for f in (0.10, 0.25, 0.50):
            yrs = []
            for y, (ay, idx) in enumerate(dev_idx):
                if base == "G2":
                    g, hh = g2_year(Es, Ms, grid, y, idx)
                else:
                    _, g, hh, _, _ = CB.year_base_g_hh(Es, Ms, grid, trades, 0.25, ANCH[y])
                r = simulate_year(grid, idx, positions, g=g, hh=hh, f=f,
                                  standalone=False, pxmap=pxmap, tag=f"D1{base}{f}")
                yrs.append({"anchor": ay, "R": r["R"], "DD": r["DD"], "end": r["end"]})
            R4 = float(np.prod([1 + yy["R"] / 100 for yy in yrs]) ** (1 / 4) - 1) * 100
            out["sizing"][f"{base}_f{f}"] = {
                "years": yrs, "dev4_mean": round(R4, 3),
                "dev4_worst": min(yy["R"] for yy in yrs),
                "dev4_DD": max(yy["DD"] for yy in yrs),
                "dev4_losing": sum(yy["R"] < 0 for yy in yrs)}
            print(base, f, out["sizing"][f"{base}_f{f}"], flush=True)
    # robust pick per base
    picks = {}
    for base in ("G2", "G2carry"):
        rows = {k: v for k, v in out["sizing"].items() if k.startswith(base)}
        elig = {k: v for k, v in rows.items() if v["dev4_DD"] <= 20 and v["dev4_losing"] == 0}
        pool = elig or rows
        hi = {k: v for k, v in pool.items() if v["dev4_mean"] >= 5}
        pool2 = hi or pool
        picks[base] = max(pool2, key=lambda k: (pool2[k]["dev4_worst"], pool2[k]["dev4_mean"]))
    out["picks"] = picks
    print("D1 picks:", picks, flush=True)
    # recent year ONCE for the 2 picks + 2 references
    ay, idx = all_idx[4]
    out["recent"] = {}
    for base in ("G2", "G2carry"):
        if base == "G2":
            g, hh = g2_year(Es, Ms, grid, 4, idx)
        else:
            _, g, hh, _, _ = CB.year_base_g_hh(Es, Ms, grid, trades, 0.25, ANCH[4])
        f = float(picks[base].split("_f")[1])
        r = simulate_year(grid, idx, positions, g=g, hh=hh, f=f,
                          standalone=False, pxmap=pxmap, tag="Drecent")
        out["recent"][picks[base]] = {"R": r["R"], "DD": r["DD"], "end": r["end"]}
    # references: G2 and G2+carry alone recent year
    out["recent"]["G2_f0"] = {"R": exp["years"][4][0], "DD": exp["years"][4][1]}
    _, _, _, A_arr, M_arr = CB.year_base_g_hh(Es, Ms, grid, trades, 0.25, ANCH[4])
    pk = np.maximum.accumulate(A_arr)
    out["recent"]["G2carry_f0"] = {
        "R": round(100 * float(A_arr[-1] ** (1 / 12) - 1), 3),
        "DD": round(100 * float(np.max(1 - M_arr / pk)), 2)}
    print("D1 recent:", out["recent"], flush=True)
    # D2 MANUAL
    mcap = pickle.loads((ROOT / "research/diagnostics/oc_manualcap/oc_manualcap_runs.pkl").read_bytes())
    MEs, MMs = [], []
    for s in range(4):
        e1, m1 = v388.hourly(mcap[s]["M5_human"]["run"], GRID0, grid[-1])
        assert (e1.index == grid).all()
        MEs.append(e1.to_numpy(dtype=float))
        MMs.append(m1.to_numpy(dtype=float))
    MEs = np.stack(MEs)
    MMs = np.stack(MMs)
    for f in (0.25, 0.50):
        yrs = []
        for y, (ay, idx) in enumerate(dev_idx):
            le = gn <= ANCH[y].value
            b = np.array([float(MEs[s][le][-1]) if le.any() else 1.0 for s in range(4)])
            es = np.mean([MEs[s][idx] / b[s] for s in range(4)], axis=0)
            ms = np.mean([MMs[s][idx] / b[s] for s in range(4)], axis=0)
            es_prev = np.concatenate([[1.0], es[:-1]])
            r = simulate_year(grid, idx, positions, g=es / es_prev, hh=ms / es_prev, f=f,
                              standalone=False, pxmap=pxmap, tag=f"MAN{f}")
            yrs.append({"anchor": ay, "R": r["R"], "DD": r["DD"], "end": r["end"]})
        R4 = float(np.prod([1 + yy["R"] / 100 for yy in yrs]) ** (1 / 4) - 1) * 100
        out["manual"][f"MANUAL_f{f}"] = {
            "years": yrs, "dev4_mean": round(R4, 3),
            "dev4_worst": min(yy["R"] for yy in yrs),
            "dev4_DD": max(yy["DD"] for yy in yrs),
            "dev4_losing": sum(yy["R"] < 0 for yy in yrs)}
        print("MANUAL", f, out["manual"][f"MANUAL_f{f}"], flush=True)
    # MANUAL reference dev4 (f=0)
    refy = []
    for y, (ay, idx) in enumerate(dev_idx):
        le = gn <= ANCH[y].value
        b = np.array([float(MEs[s][le][-1]) if le.any() else 1.0 for s in range(4)])
        es = np.mean([MEs[s][idx] / b[s] for s in range(4)], axis=0)
        ms = np.mean([MMs[s][idx] / b[s] for s in range(4)], axis=0)
        pk = np.maximum.accumulate(es)
        refy.append({"anchor": ay,
                      "R": round(100 * float(es[-1] ** (1 / 12) - 1), 3),
                      "DD": round(100 * float(np.max(1 - ms / pk)), 2)})
    out["manual"]["MANUAL_f0"] = {"years": refy}
    # recent year ONCE for best MANUAL row + reference
    cand = {k: v for k, v in out["manual"].items() if k != "MANUAL_f0"}
    bestM = max(cand, key=lambda k: (cand[k]["dev4_worst"], cand[k]["dev4_mean"]))
    out["manual_pick"] = bestM
    ay, idx = all_idx[4]
    le = gn <= ANCH[4].value
    b = np.array([float(MEs[s][le][-1]) if le.any() else 1.0 for s in range(4)])
    es = np.mean([MEs[s][idx] / b[s] for s in range(4)], axis=0)
    ms = np.mean([MMs[s][idx] / b[s] for s in range(4)], axis=0)
    es_prev = np.concatenate([[1.0], es[:-1]])
    f = float(bestM.split("_f")[1])
    r = simulate_year(grid, idx, positions, g=es / es_prev, hh=ms / es_prev, f=f,
                      standalone=False, pxmap=pxmap, tag="MANrecent")
    pk = np.maximum.accumulate(es)
    out["manual_recent"] = {
        bestM: {"R": r["R"], "DD": r["DD"], "end": r["end"]},
        "MANUAL_f0": {"R": round(100 * float(es[-1] ** (1 / 12) - 1), 3),
                       "DD": round(100 * float(np.max(1 - ms / pk)), 2)}}
    print("MANUAL pick:", bestM, out["manual_recent"], flush=True)
    (HERE / "tmp" / "D.json").write_text(json.dumps(out, indent=1))
    print("stage D done", flush=True)


STRIKE_MONTHS = {
    "BTC": ["2021-01", "2021-02", "2021-03", "2021-04", "2021-05", "2021-06",
            "2021-07", "2023-03", "2025-06"],
    "ETH": ["2021-01", "2021-02", "2021-03", "2021-04", "2021-05", "2021-06",
            "2021-07", "2021-08", "2021-09", "2023-03", "2025-06"],
}


def stage_B():
    """Term structure from traded strike prices (light, read-only)."""
    out = {"months": STRIKE_MONTHS, "fridays": []}
    dvol = {c: load_dvol(c) for c in COINS}
    for coin in COINS:
        for mon in STRIKE_MONTHS[coin]:
            f = STK / coin / f"{coin}_{mon}.parquet"
            df = pd.read_parquet(f)
            df["hour"] = pd.to_datetime(df["hour"], utc=True)
            df["expiry"] = pd.to_datetime(df["expiry"], utc=True)
            y, m = int(mon[:4]), int(mon[5:7])
            first = pd.Timestamp(y, m, 1, tz="UTC")
            last = (first + pd.offsets.MonthEnd(0)).normalize()
            days = pd.date_range(first, last, freq="D")
            fris = [d for d in days if d.weekday() == 4]
            for fri in fris:
                nxt = (fri + pd.Timedelta(days=7)).date()
                win = df[(df["hour"] >= fri + pd.Timedelta(hours=8)) &
                         (df["hour"] < fri + pd.Timedelta(hours=12)) &
                         (df["expiry"].dt.date == nxt) &
                         (df["cp"].isin(["C", "P"]))]
                if len(win) == 0:
                    continue
                win = win[np.isfinite(win["vwap_index"]) & (win["vwap_index"] > 0) &
                          np.isfinite(win["vwap_iv"]) & (win["vwap_iv"] > 0) &
                          (win["sum_amount"] > 0)]
                if len(win) == 0:
                    continue
                win = win[(win["strike"] / win["vwap_index"] - 1).abs() <= 0.02]
                if len(win) == 0:
                    continue
                w = win["sum_amount"].to_numpy(dtype=float)
                iv = float(np.sum(win["vwap_iv"].to_numpy(dtype=float) * w) / w.sum())
                dv = dvol_known(dvol[coin][0], dvol[coin][1],
                                int((fri + pd.Timedelta(hours=8)).value))
                sell = win[win["taker_sell_amount"] > win["taker_buy_amount"]]
                buy = win[win["taker_buy_amount"] > win["taker_sell_amount"]]
                iv_s = iv_b = float("nan")
                if len(sell):
                    ws = sell["sum_amount"].to_numpy(dtype=float)
                    iv_s = float(np.sum(sell["vwap_iv"].to_numpy(dtype=float) * ws) / ws.sum())
                if len(buy):
                    wb = buy["sum_amount"].to_numpy(dtype=float)
                    iv_b = float(np.sum(buy["vwap_iv"].to_numpy(dtype=float) * wb) / wb.sum())
                out["fridays"].append(
                    {"coin": coin, "fri": str(fri.date()), "n_rows": int(len(win)),
                     "amount": round(float(w.sum()), 2), "IV_7d": round(iv, 2),
                     "DVOL_0800": round(float(dv), 2) if np.isfinite(dv) else None,
                     "r": round(iv / float(dv), 4) if np.isfinite(dv) and dv > 0 else None,
                     "IV_sell": round(iv_s, 2) if np.isfinite(iv_s) else None,
                     "IV_buy": round(iv_b, 2) if np.isfinite(iv_b) else None})
    def dist(rs):
        xs = sorted(r["r"] for r in rs if r["r"] is not None)
        n = len(xs)
        if not n:
            return {"n": 0}
        return {"n": n, "mean": round(float(np.mean(xs)), 4),
                "median": round(float(np.median(xs)), 4),
                "p10": round(float(np.quantile(xs, 0.10)), 4),
                "p90": round(float(np.quantile(xs, 0.90)), 4)}
    summ = {"pooled": dist(out["fridays"])}
    for coin in COINS:
        summ[coin] = dist([r for r in out["fridays"] if r["coin"] == coin])
        for mon in STRIKE_MONTHS[coin]:
            summ[f"{coin}_{mon}"] = dist(
                [r for r in out["fridays"] if r["coin"] == coin and r["fri"][:7] == mon])
    out["dist"] = summ
    (HERE / "tmp" / "B.json").write_text(json.dumps(out, indent=1, default=str))
    print("B pooled:", summ["pooled"], "BTC:", summ["BTC"], "ETH:", summ["ETH"], flush=True)
    print("stage B done", flush=True)


def stage_collect():
    A = json.loads((HERE / "tmp" / "A.json").read_text())
    C = json.loads((HERE / "tmp" / "C.json").read_text())
    C4 = json.loads((HERE / "tmp" / "C4.json").read_text())
    D = json.loads((HERE / "tmp" / "D.json").read_text())
    B = json.loads((HERE / "tmp" / "B.json").read_text())
    exp = json.loads(V421_RES.read_text())["rows"][STRAT]
    g2_mean = exp["R"]
    ks = sorted(float(k) for k in A["overlay_f025"])
    gains = [A["overlay_f025"][str(k)]["dev4_mean"] - g2_mean for k in ks]
    k_gain_star = None
    bracket = None
    for i in range(len(ks) - 1):
        if gains[i] > 0 and gains[i + 1] <= 0:
            k_gain_star = ks[i + 1] - gains[i + 1] * (ks[i] - ks[i + 1]) / (gains[i] - gains[i + 1])
            bracket = [ks[i], ks[i + 1]]
            break
    k_dd_star = None
    for k in sorted(ks, reverse=True):
        if A["overlay_f025"][str(k)]["dev4_DD"] > 16.91:
            k_dd_star = k
            break
    out = {"meta": {"rule": "V2 weekly naked ATM straddle BTC+ETH overlay; robustness study",
                     "k_grid": K_GRID, "G2_R": g2_mean, "G2_DD": 16.91},
            "A": A, "B": B, "C": C, "C4": C4, "D": D,
            "k_star": {"k_gain_interp": k_gain_star, "gain_bracket": bracket,
                        "k_dd_first_exceed": k_dd_star,
                        "gains_over_G2": {str(k): round(g, 3) for k, g in zip(ks, gains)}}}
    (HERE / "results.json").write_text(json.dumps(out, indent=1, default=str))
    print("k_star:", out["k_star"], flush=True)
    print("stage collect done", flush=True)


def main():
    stage = sys.argv[1] if len(sys.argv) > 1 else "A"
    if stage == "A":
        stage_A()
    elif stage == "C":
        stage_C()
    elif stage == "C4":
        stage_C4()
    elif stage == "D":
        stage_D()
    elif stage == "B":
        stage_B()
    elif stage == "collect":
        stage_collect()
    else:
        raise SystemExit(f"unknown stage {stage}")


if __name__ == "__main__":
    main()
