"""oc_vrpgate runner: V2 at consistent r=0.87, gated by ex-ante vol premium.

POST-HOC INFORMED (see PLAN.md): gate idea + thresholds picked after seeing
V2 yearly IV-RV gaps. Engine copied from research/tournament/oc_vrpconsistent/
run_consistent.py (+ oc_vrpstraddle/run_vrp.py); originals never edited.

Pricing (frozen): sigma_sell = 0.97*r*DVOL/100, TP/mark = 1.0*r*DVOL/100,
SL = 1.05*r*DVOL/100, r = 0.87. Everything else = V2.

Gate (per coin per Friday, info <= 08:05):
  t_gate = Friday 08:00 UTC. DVOL_0800 = dvol_known(t_gate).
  RV7  = std of 1m log-returns over [t_gate-7d, t_gate) * sqrt(525600).
  RV30 = std of 1m log-returns over [t_gate-30d, t_gate) * sqrt(525600).
  Coverage: >=9000 finite-positive closes for RV7, >=38000 for RV30,
  else NaN => gate FAILS (no sale).
  gap7 = r*DVOL_0800/100 - RV7. ratio30 = (r*DVOL_0800/100)/RV30.
  R087: ungated. G1: gap7 >= 0.05. G2: ratio30 >= 1.15.

Stages (heavy via heavy_slot):
  python run_gate.py dev          -> dev4 standalone + overlay f=0.25 for
                                     R087/G1/G2; asserts R087 reproduces
                                     oc_vrpconsistent tmp/dev.json to the
                                     digit; tmp/dev.json
  python run_gate.py recent <ROW> -> asserts <ROW> is the robust winner on
                                     dev4 overlay f=0.25, scores recent year
                                     ONCE for <ROW> + G2 ref; tmp/recent.json
  python run_gate.py collect      -> results.json (light)
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
import vrp as V

RD = ROOT / "research/parallel/rounds/parallel-20260906-r2"
V421 = RD / "v421/v421_runs.pkl"
V421_RES = RD / "v421/v421_result.json"
DVDIR = ROOT / "data/raw/deribit_dvol_20261005"
BTC1M = ROOT / "data/raw/btc_intraday_20260924"
ETH1M = ROOT / "data/raw/majors_intraday_20260924"
CONS_DEV = ROOT / "research/tournament/oc_vrpconsistent/tmp/dev.json"

STRAT = "R2B1D17BFG2"
GRID0 = pd.Timestamp("2021-09-24 04:00", tz="UTC")
ANCH_S = ["2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24"]
ANCH = [pd.Timestamp(a, tz="UTC") for a in ANCH_S]
YEAR = pd.Timedelta(days=365)
COINS = ["BTC", "ETH"]
YK = {"BTC": 1000.0, "ETH": 50.0}
YNS = int(365 * 86400 * 1_000_000_000)
R = 0.87
SELL_MULT = 0.97
SL_MULT = 1.05
TP_FRAC = 0.30
MAKER = 0.0002
TAKER = 0.00055
F_OVERLAY = 0.25
G1_MIN_GAP = 0.05
G2_MIN_RATIO = 1.15
MIN_BARS_7 = 9000
MIN_BARS_30 = 38000
SQRT_MIN_PER_YEAR = float(np.sqrt(365 * 24 * 60))  # sqrt(525600)


def _load_v388():
    spec = importlib.util.spec_from_file_location("v388_gate", RD / "v388/v388_bot_stop_distance.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


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


def rv_before(t_gate_ns, m_ts, m_cl, days, min_bars):
    """Annualised realised vol over [t_gate-days, t_gate). NaN if short data.

    Causal: uses only 1m bars with open_time < t_gate.
    """
    lo_ns = t_gate_ns - days * 86400 * 1_000_000_000
    lo = int(np.searchsorted(m_ts, lo_ns, side="left"))
    hi = int(np.searchsorted(m_ts, t_gate_ns, side="left"))
    seg = m_cl[lo:hi]
    if len(seg) < min_bars:
        return float("nan")
    if not np.all(np.isfinite(seg)) or not np.all(seg > 0):
        return float("nan")
    r = np.diff(np.log(seg))
    if len(r) < 2 or not np.all(np.isfinite(r)):
        return float("nan")
    return float(np.std(r, ddof=1) * SQRT_MIN_PER_YEAR)


def fridays(a0, a1):
    days = pd.date_range(a0.normalize(), a1.normalize() + pd.Timedelta(days=8), freq="D")
    return [d for d in days if d.weekday() == 4]


def gate_decision(row, dv0800, rv7, rv30):
    """Return (trade: bool, gap7, ratio30). NaN inputs => no trade."""
    iv = R * dv0800 / 100.0 if (np.isfinite(dv0800) and dv0800 > 0) else float("nan")
    gap7 = iv - rv7 if (np.isfinite(iv) and np.isfinite(rv7)) else float("nan")
    ratio30 = iv / rv30 if (np.isfinite(iv) and np.isfinite(rv30) and rv30 > 0) else float("nan")
    if row == "R087":
        return True, gap7, ratio30
    if row == "G1":
        return (np.isfinite(gap7) and gap7 >= G1_MIN_GAP), gap7, ratio30
    if row == "G2":
        return (np.isfinite(ratio30) and ratio30 >= G2_MIN_RATIO), gap7, ratio30
    raise ValueError(row)


def build_positions(grid, gh, data, row):
    """V2 r=0.87 with per-coin Friday gate. Gated-out weeks are skipped."""
    gn = grid.values.astype("datetime64[ns]").astype(np.int64)
    positions = []
    n_inexact = 0
    n_gated_out = 0
    fris = fridays(grid[0], grid[-1])
    for fi, fri in enumerate(fris):
        entry_t = (fri + pd.Timedelta(hours=8, minutes=5)).value
        expiry_t = (fri + pd.Timedelta(days=7, hours=8)).value
        t_gate = (fri + pd.Timedelta(hours=8)).value
        if entry_t < gn[0] or expiry_t > gn[-1]:
            continue
        settle_lo = (fri + pd.Timedelta(days=7, hours=7, minutes=30)).value
        for coin in COINS:
            d = data[coin]
            dv = dvol_known(d["d_ms"], d["d_cl"], entry_t)
            dv0800 = dvol_known(d["d_ms"], d["d_cl"], t_gate)
            rv7 = rv_before(t_gate, d["m_ts"], d["m_cl"], 7, MIN_BARS_7)
            rv30 = rv_before(t_gate, d["m_ts"], d["m_cl"], 30, MIN_BARS_30)
            trade, gap7, ratio30 = gate_decision(row, dv0800, rv7, rv30)
            base = {"coin": coin, "fri": str(fri.date()), "dv0800": float(dv0800),
                    "rv7": float(rv7), "rv30": float(rv30),
                    "gap7": float(gap7), "ratio30": float(ratio30)}
            if not np.isfinite(dv) or dv <= 0:
                positions.append({**base, "skip": "no-vol", "entry_step": -1})
                continue
            if not trade:
                n_gated_out += 1
                positions.append({**base, "skip": "gated", "entry_step": -1,
                                  "entry_t": int(entry_t), "expiry_t": int(expiry_t)})
                continue
            sigma_sell = SELL_MULT * R * dv / 100.0
            s_min = (fri + pd.Timedelta(hours=8, minutes=4)).value
            S, exact = px_at(d["m_ts"], d["m_cl"], s_min)
            n_inexact += (not exact)
            if not np.isfinite(S) or S <= 0:
                positions.append({**base, "skip": "no-price", "entry_step": -1})
                continue
            K = V.strike_round(S, YK[coin])
            if not np.isfinite(K) or K <= 0:
                positions.append({**base, "skip": "bad-strike", "entry_step": -1})
                continue
            T_entry = (expiry_t - entry_t) / YNS
            prem_c = V.bs_call(S, K, T_entry, sigma_sell)
            prem_p = V.bs_put(S, K, T_entry, sigma_sell)
            gross = prem_c + prem_p
            fee_c = V.fee_per_side(S, prem_c)
            fee_p = V.fee_per_side(S, prem_p)
            opt_cash = gross - fee_c - fee_p
            e_step = int(np.searchsorted(gn, entry_t, side="right"))
            x_step = int(np.searchsorted(gn, expiry_t, side="left"))
            sl = slice(e_step, x_step + 1)
            L = x_step - e_step + 1
            gseg = gn[sl]
            h = gh[coin]
            px = h["px"][sl]
            sigv = h["dv"][sl] / 100.0 * R
            if not np.all(np.isfinite(sigv)):
                positions.append({**base, "skip": "no-vol-path", "entry_step": -1})
                continue
            T = (expiry_t - gseg) / YNS
            sig_m = sigv
            sig_sl = SL_MULT * sigv
            m10 = V.bs_straddle_vec(px, K, T, sig_m)
            exit_kind, exit_j = "expiry", L - 1
            for j in range(L - 1):
                s = e_step + j
                is_4h = pd.Timestamp(gn[s], tz="UTC").hour % 4 == 0
                if is_4h and m10[j] <= TP_FRAC * gross:
                    exit_kind, exit_j = "tp", j
                    break
                m105 = V.bs_straddle(px[j], K, T[j], sig_sl[j])
                if opt_cash - m105 <= -gross:
                    exit_kind, exit_j = "sl", j
                    break
            pnl_u, cf_exit, S_set = None, None, float("nan")
            px_x = float(px[exit_j])
            if exit_kind in ("tp", "sl"):
                sigx = float(sig_sl[exit_j]) if exit_kind == "sl" else float(sig_m[exit_j])
                Tx = float(T[exit_j])
                leg_c = V.bs_call(px_x, K, Tx, sigx)
                leg_p = V.bs_put(px_x, K, Tx, sigx)
                fc = V.fee_per_side(px_x, leg_c)
                fp = V.fee_per_side(px_x, leg_p)
                cf_exit = -((leg_c + leg_p) + fc + fp)
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
                stl = V.settle_fee(S_set, intr_c) + V.settle_fee(S_set, intr_p)
                cf_exit = -((intr_c + intr_p) + stl)
                pnl_u = opt_cash + cf_exit
            p = {**base, "skip": None,
                 "S": S, "K": K, "sig_raw": float(R * dv), "dv": float(dv),
                 "gross": float(gross),
                 "opt_cash": float(opt_cash), "entry_t": int(entry_t),
                 "expiry_t": int(expiry_t), "entry_step": e_step,
                 "expiry_step": x_step, "exit_kind": exit_kind,
                 "exit_step": e_step + exit_j, "exit_j": exit_j,
                 "cf_exit": float(cf_exit), "pnl_u": float(pnl_u),
                 "S_settle": float(S_set), "rv": float("nan"),
                 "m10": m10.astype(float),
                 "pos": np.zeros(L), "hc": np.zeros(L)}
            lo = int(np.searchsorted(d["m_ts"], s_min, side="left"))
            hi = int(np.searchsorted(d["m_ts"], (fri + pd.Timedelta(days=7, hours=8)).value, side="left"))
            seg = d["m_cl"][lo:hi + 1]
            if len(seg) > 10 and np.all(seg > 0) and np.all(np.isfinite(seg)):
                rr = np.diff(np.log(seg))
                p["rv"] = float(np.std(rr, ddof=1) * np.sqrt(365 * 24 * 60))
            positions.append(p)
    print(f"[{row}] positions={len(positions)} "
          f"skipped={sum(1 for p in positions if p.get('skip'))} "
          f"gated_out={n_gated_out} inexact_px={n_inexact}", flush=True)
    return positions


def year_slices(grid):
    out = []
    for a0 in ANCH:
        a1 = a0 + YEAR
        idx = np.where((grid > a0) & (grid <= a1))[0]
        out.append((str(a0.date()), idx))
    return out


def simulate_year(grid, idx, positions, g=None, hh=None, f=1.0, standalone=True,
                   pxmap=None, tag=""):
    n = len(idx)
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
    for i in range(n):
        gi = 1.0 if g is None else float(g[i])
        hhi = 1.0 if hh is None else float(hh[i])
        for p in ev_entry.get(i, []):
            acct = (cash + U_prev) if standalone else A_prev
            ff = 1.0 if standalone else f
            q = V.size_q(acct, p["S"], ff)
            qmap[id(p)] = q
            open_p.append(p)
            cash += q * p["opt_cash"]
        for p in ev_exit.get(i, []):
            q = qmap.pop(id(p), 0.0)
            if p in open_p:
                open_p.remove(p)
            cash += q * p["cf_exit"]
            opt_leg += q * (p["opt_cash"] + p["cf_exit"])
            trades.append({"fri": p["fri"], "coin": p["coin"], "exit": p["exit_kind"],
                           "q": q, "K": p["K"], "gross": p["gross"], "pnl": q * p["pnl_u"],
                           "win": bool(p["pnl_u"] > 0), "iv": p["sig_raw"], "rv": p["rv"],
                           "gap7": p.get("gap7"), "ratio30": p.get("ratio30")})
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
        cash_prev, U_prev, A_prev = cash, U, A_i
    pk = np.maximum.accumulate(E)
    dd = float(np.max(1 - Mc / pk)) if np.all(pk > 0) else float("nan")
    Rr = float(E[-1] ** (1 / 12) - 1) * 100 if E[-1] > 0 else float("-inf")
    worst, worst_dt = None, None
    for k in range(168, n):
        r_ = E[k] / E[k - 168] - 1 if E[k - 168] > 0 else float("nan")
        if np.isfinite(r_) and (worst is None or r_ < worst):
            worst, worst_dt = r_, str(grid[idx[k]].date())
    n_tr = len(trades)
    wins = sum(t["win"] for t in trades)
    kinds = {k: sum(1 for t in trades if t["exit"] == k) for k in ("tp", "sl", "expiry")}
    gaps = [(t["iv"] / 100.0 - t["rv"]) for t in trades
            if np.isfinite(t["iv"]) and np.isfinite(t["rv"])]
    ivs = [t["iv"] for t in trades if np.isfinite(t["iv"])]
    rvs = [t["rv"] for t in trades if np.isfinite(t["rv"])]
    total = float(E[-1] - 1.0)
    return {"E": E, "M": Mc, "R": round(Rr, 3), "DD": round(dd * 100, 2),
            "end": round(float(E[-1]), 6), "trades": trades, "n": n_tr,
            "win": round(wins / n_tr, 4) if n_tr else 0.0,
            "tp": kinds["tp"], "sl": kinds["sl"], "expiry": kinds["expiry"],
            "worst_week": None if worst is None else [worst_dt, round(worst * 100, 2)],
            "gap": round(float(np.mean(gaps)), 4) if gaps else None,
            "iv_mean": round(float(np.mean(ivs)), 2) if ivs else None,
            "rv_mean": round(float(np.mean(rvs)), 4) if rvs else None,
            "opt_leg": round(opt_leg, 6), "hedge_leg": round(total - opt_leg, 6),
            "n_skip": n_skip, "dU": dU_arr, "g2": g2_arr}


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


def gate_share_stats(grid, positions, anch_idx):
    """Share sold + mean gap7/ratio30 sold vs skipped over counted weeks.

    Universe = coin-weeks counted in the year sim (entry in year, expiry in
    year, valid price+vol). R087 universe == all counted; G1/G2 sold subset.
    """
    n = len(anch_idx)
    gn = grid.values.astype("datetime64[ns]").astype(np.int64)
    idx0 = anch_idx[0]
    year_end_ns = (grid[anch_idx[-1]] + pd.Timedelta(hours=1)).value
    uni, sold = [], []
    for p in positions:
        if p.get("skip") not in (None, "gated"):
            continue
        et = p.get("entry_t", None)
        xt = p.get("expiry_t", None)
        if et is None or xt is None:
            # traded positions carry entry_t/expiry_t; gated ones too (see build)
            continue
        e_step = int(np.searchsorted(gn, et, side="right"))
        e_rel = e_step - idx0
        if not (0 <= e_rel < n):
            continue
        if xt > year_end_ns:
            continue
        uni.append(p)
        if p.get("skip") is None:
            sold.append(p)
    def _mean(key, rows):
        v = [x[key] for x in rows if np.isfinite(x.get(key, float("nan")))]
        return round(float(np.mean(v)), 4) if v else None
    skipped = [u for u in uni if u not in sold]
    return {"universe": len(uni), "sold": len(sold),
            "share": round(len(sold) / len(uni), 4) if uni else 0.0,
            "gap_sold": _mean("gap7", sold), "gap_skipped": _mean("gap7", skipped),
            "ratio_sold": _mean("ratio30", sold), "ratio_skipped": _mean("ratio30", skipped)}


def stage_dev():
    v388, grid, gn, gh, data, pxmap, Es, Ms, exp = load_all()
    (HERE / "tmp").mkdir(exist_ok=True)
    dev_idx = year_slices(grid)[:4]
    ref = json.loads(CONS_DEV.read_text())
    out = {"rows": {}, "G2": {}, "meta": {
        "r": R, "label": "POST-HOC INFORMED",
        "G1": f"gap7 >= {G1_MIN_GAP}", "G2": f"ratio30 >= {G2_MIN_RATIO}"}}
    for row in ("R087", "G1", "G2"):
        positions = build_positions(grid, gh, data, row)
        sa = {}
        for ay, idx in dev_idx:
            s = simulate_year(grid, idx, positions, standalone=True, pxmap=pxmap, tag=row)
            gs = gate_share_stats(grid, positions, idx)
            sa[ay] = {"R": s["R"], "DD": s["DD"], "end": s["end"], "trades": s["n"],
                       "win": s["win"], "tp": s["tp"], "sl": s["sl"], "expiry": s["expiry"],
                       "worst_week": s["worst_week"], "gap": s["gap"],
                       "iv_mean": s["iv_mean"], "rv_mean": s["rv_mean"],
                       "share": gs["share"], "universe": gs["universe"], "sold": gs["sold"],
                       "gap_sold": gs["gap_sold"], "gap_skipped": gs["gap_skipped"],
                       "ratio_sold": gs["ratio_sold"], "ratio_skipped": gs["ratio_skipped"],
                       "n_skip": s["n_skip"]}
        R4 = float(np.prod([1 + sa[ay]["R"] / 100 for ay, _ in dev_idx]) ** (1 / 4) - 1) * 100
        ov = {}
        for y, (ay, idx) in enumerate(dev_idx):
            g, hh = g2_year(Es, Ms, grid, y, idx)
            s = simulate_year(grid, idx, positions, g=g, hh=hh, f=F_OVERLAY,
                              standalone=False, pxmap=pxmap, tag=f"{row}f{F_OVERLAY}")
            ov[ay] = {"R": s["R"], "DD": s["DD"], "end": s["end"]}
        R4o = float(np.prod([1 + ov[ay]["R"] / 100 for ay, _ in dev_idx]) ** (1 / 4) - 1) * 100
        dd_full, _, _ = overlay_full_dd(grid, Es, Ms, positions, F_OVERLAY, pxmap, tag=row)
        # pooled gate stats over dev4 counted weeks
        uni4 = sum(sa[ay]["universe"] for ay, _ in dev_idx)
        sold4 = sum(sa[ay]["sold"] for ay, _ in dev_idx)
        out["rows"][row] = {
            "standalone": {"years": sa, "dev4_mean": round(R4, 3),
                           "dev4_worst": min(sa[ay]["R"] for ay, _ in dev_idx),
                           "dev4_DD": max(sa[ay]["DD"] for ay, _ in dev_idx),
                           "dev4_losing": sum(sa[ay]["R"] < 0 for ay, _ in dev_idx)},
            "overlay_f0.25": {"years": ov, "dev4_mean": round(R4o, 3),
                              "dev4_worst": min(ov[ay]["R"] for ay, _ in dev_idx),
                              "dev4_DD": max(ov[ay]["DD"] for ay, _ in dev_idx),
                              "dev4_losing": sum(ov[ay]["R"] < 0 for ay, _ in dev_idx),
                              "full_path_DD": dd_full},
            "dev4_share": round(sold4 / uni4, 4) if uni4 else 0.0,
            "dev4_universe": uni4, "dev4_sold": sold4}
        print("row", row, out["rows"][row], flush=True)
    # R087 must reproduce oc_vrpconsistent R087 to the digit
    got_sa = out["rows"]["R087"]["standalone"]
    ref_sa = ref["standalone"]["R087"]
    for ay, _ in dev_idx:
        a, b = got_sa["years"][ay], ref_sa["years"][ay]
        assert a["R"] == b["R"] and a["DD"] == b["DD"] and a["trades"] == b["trades"] \
            and a["win"] == b["win"] and a["tp"] == b["tp"] and a["sl"] == b["sl"] \
            and a["expiry"] == b["expiry"], (ay, a, b)
    assert got_sa["dev4_mean"] == ref_sa["dev4_mean"] and got_sa["dev4_worst"] == ref_sa["dev4_worst"] \
        and got_sa["dev4_DD"] == ref_sa["dev4_DD"], (got_sa, ref_sa)
    got_ov = out["rows"]["R087"]["overlay_f0.25"]
    ref_ov = ref["overlay"]["R087_f0.25"]
    for ay, _ in dev_idx:
        assert got_ov["years"][ay]["R"] == ref_ov["years"][ay]["R"] and \
            got_ov["years"][ay]["DD"] == ref_ov["years"][ay]["DD"], (ay, got_ov["years"][ay])
    assert got_ov["dev4_mean"] == ref_ov["dev4_mean"] and got_ov["dev4_worst"] == ref_ov["dev4_worst"] \
        and got_ov["dev4_DD"] == ref_ov["dev4_DD"], (got_ov, ref_ov)
    print("R087 reproduces oc_vrpconsistent R087 standalone+overlay to the digit", flush=True)
    # f=0 overlay reproduces G2 dev4
    out["G2"]["dev4"] = {
        "years": {ay: {"R": exp["years"][y][0], "DD": exp["years"][y][1]}
                  for y, (ay, _) in enumerate(dev_idx)},
        "dev4_mean": round(float(np.prod([1 + exp["years"][y][0] / 100 for y in range(4)]) ** (1 / 4) - 1) * 100, 3),
        "dev4_worst": min(exp["years"][y][0] for y in range(4)),
        "dev4_DD": max(exp["years"][y][1] for y in range(4))}
    (HERE / "tmp" / "dev.json").write_text(json.dumps(out, indent=1, default=str))
    print("stage dev done", flush=True)


def pick_winner(dev):
    rows = {r: dev["rows"][r]["overlay_f0.25"] for r in ("R087", "G1", "G2")}
    elig = {r: d for r, d in rows.items() if d["dev4_DD"] <= 20 and d["dev4_losing"] == 0}
    pool = elig or rows
    hi = [r for r, d in pool.items() if d["dev4_mean"] >= 5]
    pool2 = {r: pool[r] for r in (hi or list(pool))}
    return max(pool2, key=lambda r: (pool2[r]["dev4_worst"], pool2[r]["dev4_mean"]))


def stage_recent(row):
    v388, grid, gn, gh, data, pxmap, Es, Ms, exp = load_all()
    dev = json.loads((HERE / "tmp" / "dev.json").read_text())
    best = pick_winner(dev)
    assert row == best, f"requested {row} but robust overlay winner is {best}"
    print(f"robust overlay winner confirmed: {row}", flush=True)
    all_idx = year_slices(grid)
    ay, idx = all_idx[4]
    positions = build_positions(grid, gh, data, row)
    g, hh = g2_year(Es, Ms, grid, 4, idx)
    ro = simulate_year(grid, idx, positions, g=g, hh=hh, f=F_OVERLAY,
                       standalone=False, pxmap=pxmap, tag=f"recent{row}")
    sa = simulate_year(grid, idx, positions, standalone=True, pxmap=pxmap, tag=f"recent{row}sa")
    gs = gate_share_stats(grid, positions, idx)
    dd_full, dd_m, dd_c = overlay_full_dd(grid, Es, Ms, positions, F_OVERLAY, pxmap, tag="recent")
    out = {"row": row, "label": "most-recent year scored ONCE for the frozen winner only",
           "overlay_f0.25": {"R": ro["R"], "DD": ro["DD"], "end": ro["end"]},
           "standalone": {"R": sa["R"], "DD": sa["DD"], "end": sa["end"],
                          "trades": sa["n"], "win": sa["win"], "tp": sa["tp"],
                          "sl": sa["sl"], "expiry": sa["expiry"],
                          "worst_week": sa["worst_week"], "gap": sa["gap"],
                          "iv_mean": sa["iv_mean"], "rv_mean": sa["rv_mean"]},
           "gate": gs,
           "G2": {"R": exp["years"][4][0], "DD": exp["years"][4][1]},
           "full_path_DD_note": "full-path DD is computed over the whole span, not recent-only"}
    print("recent", out, flush=True)
    (HERE / "tmp" / "recent.json").write_text(json.dumps(out, indent=1, default=str))


def stage_collect():
    dev = json.loads((HERE / "tmp" / "dev.json").read_text())
    recent = json.loads((HERE / "tmp" / "recent.json").read_text())
    exp = json.loads(V421_RES.read_text())["rows"][STRAT]
    out = {"meta": {"label": "POST-HOC INFORMED", "r": R,
                    "rule": "V2 weekly naked ATM straddle BTC+ETH r=0.87 "
                            "(sell 0.97r, TP 1.0r, SL 1.05r); gates G1 gap7>=0.05, "
                            "G2 ratio30>=1.15; overlay UTA f=0.25 of TOTAL equity",
                    "G2_R5": exp["R"], "G2_W": exp["W"], "G2_DD": exp["DD"],
                    "G2_dev4_mean": dev["G2"]["dev4"]["dev4_mean"],
                    "G2_dev4_worst": dev["G2"]["dev4"]["dev4_worst"],
                    "G2_dev4_DD": dev["G2"]["dev4"]["dev4_DD"]},
           "dev": dev, "recent": recent}
    (HERE / "results.json").write_text(json.dumps(out, indent=1, default=str))
    print("collect done", flush=True)


def main():
    stage = sys.argv[1] if len(sys.argv) > 1 else "dev"
    if stage == "dev":
        stage_dev()
    elif stage == "recent":
        stage_recent(sys.argv[2])
    elif stage == "collect":
        stage_collect()
    else:
        raise SystemExit(f"unknown stage {stage}")


if __name__ == "__main__":
    main()
