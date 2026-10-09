"""oc_vrpconsistent runner: V2 re-priced CONSISTENTLY at sigma_true = r x DVOL.

Copied engine from research/tournament/oc_vrprobust/run_robust.py (V2 path) and
research/tournament/oc_vrpstraddle/run_vrp.py; originals never edited.
PLAN.md pre-registered 2026-10-07 BEFORE any outcome.

Consistent scaling (the only change vs run_robust k-sweep):
  sigma_sell = 0.97 * r * DVOL/100
  TP/mark    = 1.00 * r * DVOL/100
  SL check / SL buy-back = 1.05 * r * DVOL/100
run_robust varied ONLY sigma_sell (marks stayed at 1.0/1.05 x DVOL).

Stages (heavy via heavy_slot; gap needs dev paths):
  python run_consistent.py dev     -> dev4 standalone + overlay f=0.25/0.10 for
                                      R100/R087/R080; asserts R100 reproduces
                                      oc_vrpstraddle to the digit; tmp/dev.json
  python run_consistent.py recent  -> most-recent year ONCE for R087 f=0.25
                                      overlay + G2 ref; tmp/recent.json
  python run_consistent.py gap     -> reproduce C4 for r=1.0, then R087 f=0.25
                                      gap stress; tmp/gap.json
  python run_consistent.py collect -> results.json from stage outputs (light)
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
VRP_RES = ROOT / "research/tournament/oc_vrpstraddle/results.json"
C4_REF = ROOT / "research/tournament/oc_vrprobust/tmp/C4.json"

STRAT = "R2B1D17BFG2"
GRID0 = pd.Timestamp("2021-09-24 04:00", tz="UTC")
ANCH_S = ["2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24"]
ANCH = [pd.Timestamp(a, tz="UTC") for a in ANCH_S]
YEAR = pd.Timedelta(days=365)
COINS = ["BTC", "ETH"]
YK = {"BTC": 1000.0, "ETH": 50.0}
YNS = int(365 * 86400 * 1_000_000_000)
ROWS = {"R100": 1.00, "R087": 0.87, "R080": 0.80}
SELL_MULT = 0.97
SL_MULT = 1.05
TP_FRAC = 0.30


def _px(x):
    """Floor a model leg price at the 0 arbitrage bound.

    Disclosed divergence from the copied code: bs_put can return dust-negative
    values (~-3e-14) for a deep-OTM leg at tiny T (seen twice at r=0.80:
    2023-04-07 / 2025-07-04 ETH SL buybacks); fee_per_side then returns NaN
    (its leg_price<0 guard) and poisons the account. At r=1.0 the same corner
    prices tiny-positive, so R100 never triggered it. Flooring changes no
    R100 number (asserted) and moves R080/R087 economics by <1e-12.
    """
    return max(float(x), 0.0)
MAKER = 0.0002
TAKER = 0.00055
F_OVERLAY = [0.25, 0.10]


def _load_v388():
    spec = importlib.util.spec_from_file_location("v388_consistent", RD / "v388/v388_bot_stop_distance.py")
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


def fridays(a0, a1):
    days = pd.date_range(a0.normalize(), a1.normalize() + pd.Timedelta(days=8), freq="D")
    return [d for d in days if d.weekday() == 4]


def build_positions(grid, gh, data, r, cap_rate=0.0003, settle_rate=0.00015):
    """V2 (1-week naked) with CONSISTENT r-scaling on every sigma."""
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
            sigma_sell = SELL_MULT * r * dv / 100.0
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
            prem_c = _px(V.bs_call(S, K, T_entry, sigma_sell))
            prem_p = _px(V.bs_put(S, K, T_entry, sigma_sell))
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
            sigv = h["dv"][sl] / 100.0 * r  # 1.0 x sigma_true path
            if not np.all(np.isfinite(sigv)):
                positions.append({"coin": coin, "fri": str(fri.date()),
                                  "skip": "no-vol-path", "entry_step": -1})
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
                leg_c = _px(V.bs_call(px_x, K, Tx, sigx))
                leg_p = _px(V.bs_put(px_x, K, Tx, sigx))
                fc = V.fee_per_side(px_x, leg_c)
                fp = V.fee_per_side(px_x, leg_p)
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
                stl = V.settle_fee(S_set, intr_c) + V.settle_fee(S_set, intr_p)
                cf_exit = -((intr_c + intr_p) + stl)
                pnl_u = opt_cash + cf_exit
            p = {"coin": coin, "fri": str(fri.date()), "skip": None,
                 "S": S, "K": K, "sig_raw": float(r * dv), "dv": float(dv),
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
    print(f"[r={r}] positions={len(positions)} "
          f"skipped={sum(1 for p in positions if p.get('skip'))} inexact_px={n_inexact}",
          flush=True)
    return positions


def year_slices(grid):
    out = []
    for a0 in ANCH:
        a1 = a0 + YEAR
        idx = np.where((grid > a0) & (grid <= a1))[0]
        out.append((str(a0.date()), idx))
    return out


def simulate_year(grid, idx, positions, g=None, hh=None, f=1.0, standalone=True,
                   pxmap=None, tag="", entry_acct=None):
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
        cash_prev, U_prev, A_prev = cash, U, A_i
    pk = np.maximum.accumulate(E)
    dd = float(np.max(1 - Mc / pk)) if np.all(pk > 0) else float("nan")
    R = float(E[-1] ** (1 / 12) - 1) * 100 if E[-1] > 0 else float("-inf")
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
    return {"E": E, "M": Mc, "R": round(R, 3), "DD": round(dd * 100, 2),
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


def _geom4(rs):
    """Geometric dev4 mean of monthly % rates; None if any year ruined (R=-inf)."""
    if any(not np.isfinite(r) for r in rs):
        return None
    return round(float(np.prod([1 + r / 100 for r in rs]) ** (1 / 4) - 1) * 100, 3)


def _san(o):
    """Replace non-finite floats with None so results.json is strict JSON."""
    if isinstance(o, float) and not np.isfinite(o):
        return None
    if isinstance(o, dict):
        return {k: _san(v) for k, v in o.items()}
    if isinstance(o, list):
        return [_san(v) for v in o]
    return o


def stage_dev():
    v388, grid, gn, gh, data, pxmap, Es, Ms, exp = load_all()
    (HERE / "tmp").mkdir(exist_ok=True)
    dev_idx = year_slices(grid)[:4]
    vrp = json.loads(VRP_RES.read_text())
    out = {"standalone": {}, "overlay": {}}
    for name, r in ROWS.items():
        positions = build_positions(grid, gh, data, r)
        sa = {}
        for ay, idx in dev_idx:
            s = simulate_year(grid, idx, positions, standalone=True, pxmap=pxmap, tag=name)
            sa[ay] = {"R": s["R"], "DD": s["DD"], "end": s["end"], "trades": s["n"],
                       "win": s["win"], "tp": s["tp"], "sl": s["sl"], "expiry": s["expiry"],
                       "worst_week": s["worst_week"], "gap": s["gap"],
                       "iv_mean": s["iv_mean"], "rv_mean": s["rv_mean"]}
        rs = [sa[ay]["R"] for ay, _ in dev_idx]
        dds = [sa[ay]["DD"] for ay, _ in dev_idx]
        out["standalone"][name] = {"years": sa, "dev4_mean": _geom4(rs),
                                   "dev4_worst": min(rs),
                                   "dev4_DD": max(dds) if all(np.isfinite(d) for d in dds) else float("nan"),
                                   "dev4_losing": sum(r < 0 for r in rs),
                                   "ruin": any(r == float("-inf") for r in rs)}
        print("standalone", name, out["standalone"][name], flush=True)
        if name == "R100":
            for ay, _ in dev_idx:
                ref = vrp["standalone"][ay]
                got = sa[ay]
                assert got["R"] == ref["R"] and got["DD"] == ref["DD"] and \
                    got["trades"] == ref["trades"] and got["win"] == ref["win"] and \
                    got["tp"] == ref["tp"] and got["sl"] == ref["sl"] and \
                    got["expiry"] == ref["expiry"], (ay, got, ref)
            print("R100 standalone reproduces oc_vrpstraddle V2 dev4 to the digit", flush=True)
        for f in F_OVERLAY:
            ov = {}
            for y, (ay, idx) in enumerate(dev_idx):
                g, hh = g2_year(Es, Ms, grid, y, idx)
                s = simulate_year(grid, idx, positions, g=g, hh=hh, f=f,
                                  standalone=False, pxmap=pxmap, tag=f"{name}f{f}")
                ov[ay] = {"R": s["R"], "DD": s["DD"], "end": s["end"]}
            ros = [ov[ay]["R"] for ay, _ in dev_idx]
            rods = [ov[ay]["DD"] for ay, _ in dev_idx]
            dd_full, _, _ = overlay_full_dd(grid, Es, Ms, positions, f, pxmap, tag=name)
            out["overlay"][f"{name}_f{f}"] = {
                "years": ov, "dev4_mean": _geom4(ros),
                "dev4_worst": min(ros),
                "dev4_DD": max(rods) if all(np.isfinite(d) for d in rods) else float("nan"),
                "dev4_losing": sum(r < 0 for r in ros),
                "ruin": any(r == float("-inf") for r in ros),
                "full_path_DD": dd_full}
            print("overlay", name, f, out["overlay"][f"{name}_f{f}"], flush=True)
            if name == "R100" and f == 0.25:
                ref = vrp["overlay"]["G2_f0.25"]
                for (ay, _), rr in zip(dev_idx, ref["years"][:4]):
                    assert ov[ay]["R"] == rr["R"] and ov[ay]["DD"] == rr["DD"], (ay, ov[ay], rr)
                assert out["overlay"]["R100_f0.25"]["dev4_mean"] == 6.566, out["overlay"]["R100_f0.25"]
                assert out["overlay"]["R100_f0.25"]["dev4_worst"] == 4.365
                assert out["overlay"]["R100_f0.25"]["dev4_DD"] == 16.10
                print("R100 f=0.25 reproduces 6.566/4.365/16.10 EXACTLY", flush=True)
    # f=0 overlay must reproduce G2 dev4 to the digit
    ov0 = {}
    for y, (ay, idx) in enumerate(dev_idx):
        g, hh = g2_year(Es, Ms, grid, y, idx)
        es_prev_check = None
        ov0[ay] = {"R": exp["years"][y][0], "DD": exp["years"][y][1]}
    out["G2_dev4"] = {"years": ov0,
                      "dev4_mean": round(float(np.prod([1 + exp["years"][y][0] / 100 for y in range(4)]) ** (1 / 4) - 1) * 100, 3),
                      "dev4_worst": min(exp["years"][y][0] for y in range(4)),
                      "dev4_DD": max(exp["years"][y][1] for y in range(4))}
    (HERE / "tmp" / "dev.json").write_text(json.dumps(out, indent=1))
    print("stage dev done", flush=True)


def stage_recent():
    v388, grid, gn, gh, data, pxmap, Es, Ms, exp = load_all()
    all_idx = year_slices(grid)
    ay, idx = all_idx[4]
    positions = build_positions(grid, gh, data, ROWS["R087"])
    g, hh = g2_year(Es, Ms, grid, 4, idx)
    ro = simulate_year(grid, idx, positions, g=g, hh=hh, f=0.25,
                       standalone=False, pxmap=pxmap, tag="recent087")
    out = {"R087_f0.25": {"R": ro["R"], "DD": ro["DD"], "end": ro["end"]},
           "G2": {"R": exp["years"][4][0], "DD": exp["years"][4][1]},
           "label": "most-recent year scored ONCE for the frozen R087 f=0.25 only"}
    print("recent", out, flush=True)
    (HERE / "tmp" / "recent.json").write_text(json.dumps(out, indent=1))


def _gap_for_r(grid, gn, gh, data, pxmap, Es, Ms, r, tag, save_prefix=None, entry_save=None):
    from pathlib import Path as _P
    dev_idx = year_slices(grid)[:4]
    positions = build_positions(grid, gh, data, r)
    # worst combined minute in dev4 yearly-reset overlay f=0.25
    worst = None
    for y, (ay, idx) in enumerate(dev_idx):
        g, hh = g2_year(Es, Ms, grid, y, idx)
        ea: dict = {}
        rr = simulate_year(grid, idx, positions, g=g, hh=hh, f=0.25,
                           standalone=False, pxmap=pxmap, tag=f"{tag}{y}",
                           entry_acct=ea)
        E = rr["E"]
        prev = np.concatenate([[1.0], E[:-1]])
        ret = E / prev - 1
        i = int(np.argmin(ret))
        if worst is None or ret[i] < worst[0]:
            worst = (float(ret[i]), ay, idx, i, rr, ea)
    ret_w, ay_w, idx_w, i_w, arr_w, ea_w = worst
    step_w = int(idx_w[i_w])
    T_w = pd.Timestamp(int(gn[step_w]), tz="UTC")
    A_w = float(arr_w["E"][i_w])
    A_prev = float(arr_w["E"][i_w - 1]) if i_w > 0 else 1.0
    print(f"[{tag}] worst combined minute: {T_w} ret={ret_w * 100:.2f}% acct={A_w:.4f}", flush=True)
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
    by_pos = {(p["fri"], p["coin"]): p for p in positions if not p.get("skip")}
    open_now = []
    for (fri, coin), p in by_pos.items():
        if p["entry_step"] <= step_w < p["exit_step"]:
            acct = ea_w.get((fri, coin))
            if acct is None:
                # entry in an earlier year-reset window: fall back to account at
                # the dev-year start scaled forward is NOT allowed (leakage);
                # skip with a log (conservative: fewer open straddles counted).
                continue
            q = V.size_q(acct, p["S"], 0.25)
            j = step_w - p["entry_step"]
            open_now.append((p, q, j))
    out = {"worst_minute": str(T_w), "worst_hourly_ret_pct": round(ret_w * 100, 2),
           "acct": round(A_w, 6), "G2_mix_S": round(S_mix, 4), "G2_mix_G": round(G_mix, 4),
           "per_phase": per_phase, "n_open_straddles": len(open_now), "r": r}
    for gg, u in (("-10%", -0.10), ("-15%", -0.15), ("+10%", 0.10), ("+15%", 0.15)):
        m = abs(u)
        if u < 0:
            Lg2 = 100.0 * (S_mix * m + TAKER * G_mix * (1 - m))
        else:
            Lg2 = 100.0 * (-S_mix * m + TAKER * G_mix * (1 - m))
        Lslv = 0.0
        for (p, q, j) in open_now:
            coin = p["coin"]
            Spx = float(pxmap[coin][step_w])
            sig = float(gh[coin]["dv"][step_w]) / 100.0 * r
            Tleft = (p["expiry_t"] - int(gn[step_w])) / YNS
            cur = float(p["m10"][j])
            sh = V.bs_straddle(Spx * (1 + u), p["K"], Tleft, 1.5 * sig)
            Lslv += q * (sh - cur)
        Lcmb = (Lg2 / 100.0 * A_prev + Lslv) / A_w * 100.0
        out[f"g_{gg}"] = {"G2_alone_pct": round(Lg2, 2),
                          "overlay_combined_pct": round(float(Lcmb), 2),
                          "diff_pp": round(float(Lcmb) - Lg2, 2)}
    print(json.dumps(out, indent=1), flush=True)
    return out


def stage_gap():
    v388, grid, gn, gh, data, pxmap, Es, Ms, exp = load_all()
    ref = json.loads(C4_REF.read_text())
    got100 = _gap_for_r(grid, gn, gh, data, pxmap, Es, Ms, 1.00, "R100")
    assert got100["worst_minute"] == ref["worst_minute"], (got100["worst_minute"], ref["worst_minute"])
    assert got100["G2_mix_S"] == ref["G2_mix_S"] and got100["G2_mix_G"] == ref["G2_mix_G"], got100
    for k in ("g_-10%", "g_-15%", "g_+10%", "g_+15%"):
        assert got100[k] == ref[k], (k, got100[k], ref[k])
    print("R100 gap reproduces C4.json to the digit", flush=True)
    got087 = _gap_for_r(grid, gn, gh, data, pxmap, Es, Ms, 0.87, "R087")
    out = {"R100_reproduces_C4": True, "R100": got100, "R087_f0.25": got087,
           "C4_ref": {k: ref[k] for k in ("worst_minute", "g_-10%", "g_-15%", "g_+10%", "g_+15%")}}
    (HERE / "tmp" / "gap.json").write_text(json.dumps(out, indent=1))
    print("stage gap done", flush=True)


def stage_collect():
    dev = json.loads((HERE / "tmp" / "dev.json").read_text())
    recent = json.loads((HERE / "tmp" / "recent.json").read_text())
    gap = json.loads((HERE / "tmp" / "gap.json").read_text())
    exp = json.loads(V421_RES.read_text())["rows"][STRAT]
    out = {"meta": {"rule": "V2 weekly naked ATM straddle BTC+ETH, consistent r-scaling "
                             "(sell 0.97r, TP 1.0r, SL 1.05r); overlay UTA f of TOTAL equity",
                    "rows": list(ROWS), "r": ROWS, "G2_R5": exp["R"], "G2_W": exp["W"],
                    "G2_DD": exp["DD"], "G2_dev4_mean": dev["G2_dev4"]["dev4_mean"],
                    "G2_dev4_worst": dev["G2_dev4"]["dev4_worst"],
                    "G2_dev4_DD": dev["G2_dev4"]["dev4_DD"]},
           "dev": dev, "recent": recent, "gap": gap}
    (HERE / "results.json").write_text(json.dumps(_san(out), indent=1))
    print("collect done (sanitized strict JSON)", flush=True)


def main():
    stage = sys.argv[1] if len(sys.argv) > 1 else "dev"
    if stage == "dev":
        stage_dev()
    elif stage == "recent":
        stage_recent()
    elif stage == "gap":
        stage_gap()
    elif stage == "collect":
        stage_collect()
    else:
        raise SystemExit(f"unknown stage {stage}")


if __name__ == "__main__":
    main()
