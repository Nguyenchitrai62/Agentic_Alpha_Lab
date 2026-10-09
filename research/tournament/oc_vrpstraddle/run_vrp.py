"""oc_vrpstraddle runner: delta-hedged short ATM straddle sleeve (BTC+ETH).

Implements PLAN.md exactly. Stages:
  python run_vrp.py dev4            -> builds positions for V1/V2/V3, yearly
                                     standalone sim on dev4 anchors, writes
                                     tmp/dev4.json + trades_<v>_dev4.parquet
  python run_vrp.py final <VARIANT> -> asserts <VARIANT> is the robust-criterion
                                     winner on dev4, scores the most recent year
                                     once, runs sensitivities (dev4), G2 overlay
                                     (f=0.25/0.5), correlations; writes
                                     tmp/final.json

One process, 1m + hourly/DVOL/IV data only. Run heavy steps via heavy_slot.
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
IVDIR = ROOT / "data/raw/deribit_opt_20260926"
BTC1M = ROOT / "data/raw/btc_intraday_20260924"
ETH1M = ROOT / "data/raw/majors_intraday_20260924"

STRAT = "R2B1D17BFG2"
GRID0 = pd.Timestamp("2021-09-24 04:00", tz="UTC")
ANCH_S = ["2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24"]
ANCH = [pd.Timestamp(a, tz="UTC") for a in ANCH_S]
YEAR = pd.Timedelta(days=365)
COINS = ["BTC", "ETH"]
YK = {"BTC": 1000.0, "ETH": 50.0}
YNS = int(365 * 86400 * 1_000_000_000)

VARIANTS = {
    "V1": {"weeks": 1, "hedge": True, "every4": False},
    "V2": {"weeks": 1, "hedge": False, "every4": False},
    "V3": {"weeks": 4, "hedge": True, "every4": True},
}
F_OVERLAY = [0.25, 0.5]

MAKER = 0.0002
TAKER = 0.00055
FUND = 0.0001
SLIP = 0.0002  # hedge adverse slippage (base); sens 0.0005
SELL_MULT = 0.97
SL_MULT = 1.05


def _load_v388():
    spec = importlib.util.spec_from_file_location("v388_vrp", RD / "v388/v388_bot_stop_distance.py")
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
    return ms[keep] * 1_000_000, cl[keep]  # candle-start ns, vol points


def load_iv(coin):
    df = pd.read_parquet(IVDIR / f"{coin}_options_4h.parquet",
                         columns=["bar", "iv_otm_put", "iv_otm_call"])
    df = df.sort_values("bar").reset_index(drop=True)
    t0 = pd.to_datetime(df["bar"], utc=True).values.astype("datetime64[ns]").astype(np.int64)
    return t0, df["iv_otm_put"].to_numpy(dtype=float), df["iv_otm_call"].to_numpy(dtype=float)


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
    """1m close of bar open exactly q; else last bar open strictly before q."""
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


def iv_known(iv_t0, iv_put, iv_call, t_ns):
    i = int(np.searchsorted(iv_t0 + 4 * 3600_000_000_000, t_ns, side="right")) - 1
    if i < 0:
        return float("nan"), float("nan")
    return float(iv_put[i]), float(iv_call[i])


# ---------------- Fridays ----------------

def fridays(a0: pd.Timestamp, a1: pd.Timestamp):
    days = pd.date_range(a0.normalize(), a1.normalize() + pd.Timedelta(days=8), freq="D")
    return [d for d in days if d.weekday() == 4]


# ---------------- position precompute (per-unit, account-independent) ----------------

def build_positions(grid, gh, data, variant, sigma_src="dvol", cap_rate=0.0003,
                    settle_rate=0.00015, hedge_slip=SLIP):
    """Per-(cycle,coin) per-unit economics + hourly path. Scale-free triggers."""
    spec = VARIANTS[variant]
    weeks, hedge, every4 = spec["weeks"], spec["hedge"], spec["every4"]
    gn = grid.values.astype("datetime64[ns]").astype(np.int64)
    positions = []
    n_inexact = 0
    fris = fridays(grid[0], grid[-1])
    for fi, fri in enumerate(fris):
        if every4 and (fi % 4 != 0):
            continue
        entry_t = (fri + pd.Timedelta(hours=8, minutes=5)).value
        expiry_t = (fri + pd.Timedelta(days=7 * weeks, hours=8)).value
        if entry_t < gn[0] or expiry_t > gn[-1]:
            continue
        settle_lo = (fri + pd.Timedelta(days=7 * weeks, hours=7, minutes=30)).value
        for coin in COINS:
            d = data[coin]
            dv = dvol_known(d["d_ms"], d["d_cl"], entry_t)
            ivp, ivc = iv_known(d["iv_t0"], d["iv_put"], d["iv_call"], entry_t)
            otm = 0.5 * (ivp + ivc) if (np.isfinite(ivp) and np.isfinite(ivc)) else float("nan")
            sig_raw = otm if (sigma_src == "otmiv" and np.isfinite(otm)) else dv
            if sigma_src == "otmiv" and not np.isfinite(otm):
                sig_raw = dv  # disclosed DVOL fallback
            if not np.isfinite(sig_raw) or sig_raw <= 0:
                positions.append({"variant": variant, "coin": coin, "fri": str(fri.date()),
                                  "skip": "no-vol", "entry_step": -1})
                continue
            sigma_sell = SELL_MULT * sig_raw / 100.0
            s_min = (fri + pd.Timedelta(hours=8, minutes=4)).value
            S, exact = px_at(d["m_ts"], d["m_cl"], s_min)
            n_inexact += (not exact)
            if not np.isfinite(S) or S <= 0:
                positions.append({"variant": variant, "coin": coin, "fri": str(fri.date()),
                                  "skip": "no-price", "entry_step": -1})
                continue
            K = V.strike_round(S, YK[coin])
            if not np.isfinite(K) or K <= 0:
                positions.append({"variant": variant, "coin": coin, "fri": str(fri.date()),
                                  "skip": "bad-strike", "entry_step": -1})
                continue
            T_entry = (expiry_t - entry_t) / YNS
            prem_c = V.bs_call(S, K, T_entry, sigma_sell)
            prem_p = V.bs_put(S, K, T_entry, sigma_sell)
            gross = prem_c + prem_p
            fee_c = V.fee_per_side(S, prem_c, cap_rate)
            fee_p = V.fee_per_side(S, prem_p, cap_rate)
            opt_cash = gross - fee_c - fee_p
            e_step = int(np.searchsorted(gn, entry_t, side="right"))
            x_step = int(np.searchsorted(gn, expiry_t, side="left"))
            sl = slice(e_step, x_step + 1)
            L = x_step - e_step + 1
            gseg = gn[sl]
            h = gh[coin]
            px = h["px"][sl]
            if sigma_src == "otmiv":
                sigpts = h["otm"][sl].copy()
                need = ~np.isfinite(sigpts)
                sigpts[need] = h["dv"][sl][need]  # disclosed DVOL fallback (points)
                sigv = sigpts / 100.0
            else:
                sigv = h["dv"][sl] / 100.0
            if not np.all(np.isfinite(sigv)):
                positions.append({"variant": variant, "coin": coin, "fri": str(fri.date()),
                                  "skip": "no-vol-path", "entry_step": -1})
                continue
            T = (expiry_t - gseg) / YNS
            sig_m = sigv
            sig_sl = SL_MULT * sigv
            m10 = V.bs_straddle_vec(px, K, T, sig_m)
            m105 = V.bs_straddle_vec(px, K, T, sig_sl)
            pos = np.zeros(L)
            hc = np.zeros(L)
            if hedge:
                delta = V.bs_straddle_delta_vec(px, K, T, sig_m)
                cur_hc, cur_pos = 0.0, 0.0
                for j in range(L):
                    s = e_step + j
                    if s < x_step and (pd.Timestamp(gn[s], tz="UTC").hour % 4 == 0):
                        tgt = -float(delta[j])
                        dn = tgt - cur_pos
                        if dn != 0.0:
                            cur_hc += -dn * px[j] - abs(dn) * px[j] * (hedge_slip + MAKER)
                            cur_pos = tgt
                    if pd.Timestamp(gn[s], tz="UTC").hour in (0, 8, 16) and cur_pos > 0:
                        cur_hc -= cur_pos * px[j] * FUND
                    hc[j] = cur_hc
                    pos[j] = cur_pos
            # walk exits
            exit_kind, exit_j = "expiry", L - 1
            for j in range(L - 1):  # no SL/TP at the expiry step itself
                s = e_step + j
                is_4h = pd.Timestamp(gn[s], tz="UTC").hour % 4 == 0
                if is_4h and m10[j] <= 0.3 * gross:
                    exit_kind, exit_j = "tp", j
                    break
                pnl = hc[j] + pos[j] * px[j] - m105[j] + opt_cash
                if pnl <= -gross:
                    exit_kind, exit_j = "sl", j
                    break
            pnl_u, cf_exit, S_set = None, None, float("nan")
            px_x = float(px[exit_j])
            if exit_kind in ("tp", "sl"):
                sigx = float(sig_sl[exit_j]) if exit_kind == "sl" else float(sig_m[exit_j])
                Tx = float(T[exit_j])
                leg_c = V.bs_call(px_x, K, Tx, sigx)
                leg_p = V.bs_put(px_x, K, Tx, sigx)
                fc = V.fee_per_side(px_x, leg_c, cap_rate)
                fp = V.fee_per_side(px_x, leg_p, cap_rate)
                buy = leg_c + leg_p
                hclose = abs(float(pos[exit_j])) * px_x * TAKER
                cf_exit = -(buy + fc + fp) + float(pos[exit_j]) * px_x - hclose
                pnl_u = opt_cash + float(hc[exit_j]) + cf_exit
            else:
                s_vals = []
                for k in range(30):
                    q = settle_lo + k * 60_000_000_000
                    pxq, ex = px_at(d["m_ts"], d["m_cl"], q)
                    n_inexact += (not ex)
                    s_vals.append(pxq)
                S_set = float(np.mean(s_vals))
                intr_c = max(px_x * 0 + S_set - K, 0.0)  # call intrinsic vs settle
                intr_p = max(K - S_set, 0.0)
                stl = V.settle_fee(S_set, intr_c, settle_rate) + V.settle_fee(S_set, intr_p, settle_rate)
                payoff = intr_c + intr_p
                hclose = abs(float(pos[L - 1])) * float(px[L - 1]) * TAKER
                cf_exit = -(payoff + stl) + float(pos[L - 1]) * float(px[L - 1]) - hclose
                pnl_u = opt_cash + float(hc[L - 1]) + cf_exit
            # realised vol entry->expiry (1m log rets, annualised)
            lo = int(np.searchsorted(d["m_ts"], s_min, side="left"))
            hi = int(np.searchsorted(d["m_ts"], (fri + pd.Timedelta(days=7 * weeks, hours=8)).value, side="left"))
            seg = d["m_cl"][lo:hi + 1]
            rv = float("nan")
            if len(seg) > 10 and np.all(seg > 0) and np.all(np.isfinite(seg)):
                r = np.diff(np.log(seg))
                rv = float(np.std(r, ddof=1) * np.sqrt(365 * 24 * 60))
            positions.append({
                "variant": variant, "coin": coin, "fri": str(fri.date()), "skip": None,
                "S": S, "K": K, "sig_raw": float(sig_raw), "gross": float(gross),
                "opt_cash": float(opt_cash), "entry_t": int(entry_t), "expiry_t": int(expiry_t),
                "entry_step": e_step, "expiry_step": x_step, "exit_kind": exit_kind,
                "exit_step": e_step + exit_j, "exit_j": exit_j,
                "cf_exit": float(cf_exit), "pnl_u": float(pnl_u), "S_settle": float(S_set),
                "rv": float(rv), "m10": m10.astype(float), "pos": pos.astype(float),
                "hc": hc.astype(float),
            })
    print(f"[{variant}/{sigma_src}] positions={len(positions)} "
          f"skipped={sum(1 for p in positions if p.get('skip'))} inexact_px={n_inexact}")
    return positions


# ---------------- account simulation ----------------

def year_slices(grid):
    gn = grid.values.astype("datetime64[ns]").astype(np.int64)
    out = []
    for a0 in ANCH:
        a1 = a0 + YEAR
        idx = np.where((grid > a0) & (grid <= a1))[0]
        out.append((str(a0.date()), idx))
    return out


def simulate_year(grid, idx, positions, g=None, hh=None, f=1.0, standalone=True,
                  pxmap=None, tag=""):
    """Hourly account loop over one anchor year.

    g/hh: base growth arrays (overlay) or None (standalone). pxmap: coin -> full-grid px.
    Boundary weeks (expiry past year end) are skipped. Returns stats + equity + legs.
    """
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
    A_prev, M_prev = 1.0, 1.0
    cash_prev, U_prev = 1.0, 0.0
    open_p = []
    qmap = {}
    trades = []
    cyc = {}
    opt_leg, worst_dates = 0.0, None
    for i in range(n):
        gi = 1.0 if g is None else float(g[i])
        hhi = 1.0 if hh is None else float(hh[i])
        prev_acct = cash + U_prev if standalone else A_prev
        for p in ev_entry.get(i, []):
            acct = (cash + U_prev) if standalone else A_prev
            ff = 1.0 if standalone else f
            q = V.size_q(acct, p["S"], ff)
            qmap[id(p)] = q
            open_p.append(p)
            cash += q * p["opt_cash"]
            c = cyc.setdefault((p["fri"], p["coin"]), {"E_base": prev_acct, "prem": 0.0, "pnl": 0.0})
            c["prem"] += q * p["gross"]
        for p in ev_exit.get(i, []):
            q = qmap.pop(id(p), 0.0)
            if p in open_p:
                open_p.remove(p)
            j = p["exit_j"]
            s = idx[i]
            pxs = pxmap[p["coin"]][s]
            # hedge cashflow delta already applied below via hc; apply exit leg here
            cash += q * (float(p["hc"][j]) - float(p.get("_hc_applied", 0.0)))  # remainder to exit
            p["_hc_applied"] = float(p["hc"][j])
            cash += q * p["cf_exit"]
            # NOTE cf_exit includes hedge close (pos*px - taker fee) but NOT hc remainder
            # above; combined with per-step hc deltas the full hedge leg is realised.
            # For trade attribution recompute full per-unit pnl:
            opt_u = p["opt_cash"] + (p["cf_exit"] - (float(p["pos"][j]) * pxs
                                                     - abs(float(p["pos"][j])) * pxs * TAKER))
            opt_leg += q * opt_u
            trades.append({"fri": p["fri"], "coin": p["coin"], "exit": p["exit_kind"],
                           "q": q, "K": p["K"], "gross": p["gross"], "pnl": q * p["pnl_u"],
                           "win": bool(p["pnl_u"] > 0), "iv": p["sig_raw"], "rv": p["rv"]})
            cyc[(p["fri"], p["coin"])]["pnl"] += q * p["pnl_u"]
        U = 0.0
        for o in open_p:
            j = idx[i] - o["entry_step"]
            assert 0 <= j < len(o["m10"]), (tag, i, j)
            q = qmap.get(id(o), 0.0)
            # apply hedge cashflow delta for this step
            prev_hc = float(o.get("_hc_applied", 0.0))
            cur_hc = float(o["hc"][j])
            if cur_hc != prev_hc:
                cash += q * (cur_hc - prev_hc)
                o["_hc_applied"] = cur_hc
            pxs = pxmap[o["coin"]][idx[i]]
            U += q * (-float(o["m10"][j]) + float(o["pos"][j]) * pxs)
        # reset per-position applied markers each year run (fresh dicts per call)
        acct_now = cash + U
        if standalone:
            A_i, M_i = acct_now, acct_now
            dU = 0.0
            g2l = 0.0
        else:
            # v421/carrycompound convention: the marked path is anchored on the
            # CLOSE path (A_prev), not compounded on itself (M_prev would decay
            # the base by Π(ms/es) over every dip).
            dU = acct_now - (cash_prev + U_prev)
            A_i = A_prev * gi + dU
            M_i = A_prev * hhi + dU
            g2l = A_prev * (gi - 1.0)
        E[i] = A_i
        Mc[i] = M_i
        dU_arr[i] = dU
        g2_arr[i] = g2l
        cash_prev, U_prev, A_prev, M_prev = cash, U, A_i, M_i
    # clear transient markers (positions reused across years)
    for p in positions:
        p.pop("_hc_applied", None)
    pk = np.maximum.accumulate(E)
    dd = float(np.max(1 - Mc / pk)) if np.all(pk > 0) else float("nan")
    R = float(E[-1] ** (1 / 12) - 1) * 100 if E[-1] > 0 else float("-inf")
    worst, worst_dt = None, None
    for k in range(168, n):
        r = E[k] / E[k - 168] - 1 if E[k - 168] > 0 else float("nan")
        if np.isfinite(r) and (worst is None or r < worst):
            worst, worst_dt = r, str(grid[idx[k]].date())
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


def main():
    stage = sys.argv[1] if len(sys.argv) > 1 else "dev4"
    v388 = _load_v388()
    g1 = v388.Y1 + pd.Timedelta(hours=12)
    grid = pd.date_range(GRID0, g1, freq="1h")
    gn = grid.values.astype("datetime64[ns]").astype(np.int64)
    print("grid", grid[0], "->", grid[-1], len(grid))

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
    print("G2 baseline validation OK (yearly R/DD reproduce v421_result to the digit)")

    data = {}
    for coin in COINS:
        iv_t0, iv_put, iv_call = load_iv(coin)
        d_ms, d_cl = load_dvol(coin)
        m_ts, m_cl = load_1m(coin)
        data[coin] = {"iv_t0": iv_t0, "iv_put": iv_put, "iv_call": iv_call,
                      "d_ms": d_ms, "d_cl": d_cl, "m_ts": m_ts, "m_cl": m_cl}
    gh = {}
    pxmap = {}
    for coin in COINS:
        d = data[coin]
        px = np.array([px_at(d["m_ts"], d["m_cl"], int(t) - 60_000_000_000)[0] for t in gn])
        assert np.isfinite(px).all(), coin
        dv = np.array([dvol_known(d["d_ms"], d["d_cl"], int(t)) for t in gn])
        ivs = np.array([iv_known(d["iv_t0"], d["iv_put"], d["iv_call"], int(t)) for t in gn])
        otm = np.array([(0.5 * (a + b) if (np.isfinite(a) and np.isfinite(b)) else np.nan)
                        for a, b in ivs])
        gh[coin] = {"px": px, "dv": dv, "otm": otm}
        pxmap[coin] = px
    print("hourly DVOL NaN:", {c: int(np.isnan(gh[c]['dv']).sum()) for c in COINS})

    (HERE / "tmp").mkdir(exist_ok=True)
    dev_idx = year_slices(grid)[:4]
    all_idx = year_slices(grid)

    if stage == "dev4":
        results = {"variants": {}, "meta": {
            "grid": [str(grid[0]), str(grid[-1])], "strat": STRAT,
            "note": ("entries at first hourly step >= 08:05 (09:00); hedge set at 4h closes only "
                     "(first 12:00 Fri); TP before SL at 4h closes; hourly px = 1m close of prior "
                     "minute (:59); boundary weeks skipped per year; hedge close as taker; "
                     "marks close-marked (DD lower bound)")}}
        for variant in VARIANTS:
            positions = build_positions(grid, gh, data, variant)
            yrs = []
            all_trades = []
            for ay, idx in dev_idx:
                out = simulate_year(grid, idx, positions, standalone=True, pxmap=pxmap, tag=variant)
                yrs.append({"anchor": ay, "R": out["R"], "DD": out["DD"], "end": out["end"],
                            "trades": out["n"], "win": out["win"], "tp": out["tp"],
                            "sl": out["sl"], "expiry": out["expiry"],
                            "worst_week": out["worst_week"], "gap": out["gap"],
                            "iv_mean": out["iv_mean"], "rv_mean": out["rv_mean"],
                            "opt_leg": out["opt_leg"], "hedge_leg": out["hedge_leg"],
                            "n_skip": out["n_skip"]})
                all_trades.extend([{**t, "anchor": ay} for t in out["trades"]])
            R4 = float(np.prod([1 + y["R"] / 100 for y in yrs]) ** (1 / 4) - 1) * 100
            results["variants"][variant] = {
                "years": yrs, "dev4_mean": round(R4, 3),
                "dev4_worst": min(y["R"] for y in yrs),
                "dev4_DD": max(y["DD"] for y in yrs),
                "dev4_losing": sum(y["R"] < 0 for y in yrs)}
            if all_trades:
                pd.DataFrame(all_trades).to_parquet(HERE / f"trades_{variant}_dev4.parquet")
            print(variant, results["variants"][variant])
        (HERE / "tmp" / "dev4.json").write_text(json.dumps(results, indent=1, default=str))
        print("dev4 done ->", HERE / "tmp/dev4.json")

    elif stage == "final":
        variant = sys.argv[2]
        dev4 = json.loads((HERE / "tmp" / "dev4.json").read_text())
        # robust criterion recomputed here; assert the requested variant wins
        rows = {v: d for v, d in dev4["variants"].items()}
        elig = {v: d for v, d in rows.items() if d["dev4_DD"] <= 20 and d["dev4_losing"] == 0}
        pool = elig or rows
        hi = [v for v, d in pool.items() if d["dev4_mean"] >= 5]
        pool2 = {v: pool[v] for v in (hi or list(pool))}
        best = max(pool2, key=lambda v: (pool2[v]["dev4_worst"], pool2[v]["dev4_mean"]))
        assert variant == best, f"requested {variant} but robust winner is {best}"
        print(f"robust winner confirmed: {variant} (eligible={[k for k in elig]})")

        out = {"variant": variant, "standalone": {}, "sens": {}, "overlay": {},
               "corr": {}, "full": {}, "meta": {
                   "grid": [str(grid[0]), str(grid[-1])], "strat": STRAT,
                   "rule": ("short ATM straddle Fri 08:05, K nearest grid, sell 0.97xDVOL, "
                            "hedge -q*delta at 4h closes (+2bps/maker), SL -1x prem hourly "
                            "(buyback 1.05xDVOL, hedge taker), TP 0.3x prem at 4h (maker), "
                            "settle mean 07:30..07:59; funding longs 0.0001/8h")}}

        positions = build_positions(grid, gh, data, variant)
        # standalone: dev4 years (recomputed) + most recent year ONCE
        for ay, idx in all_idx:
            r = simulate_year(grid, idx, positions, standalone=True, pxmap=pxmap, tag=variant)
            out["standalone"][ay] = {
                "R": r["R"], "DD": r["DD"], "end": r["end"], "trades": r["n"],
                "win": r["win"], "tp": r["tp"], "sl": r["sl"], "expiry": r["expiry"],
                "worst_week": r["worst_week"], "gap": r["gap"],
                "iv_mean": r["iv_mean"], "rv_mean": r["rv_mean"],
                "opt_leg": r["opt_leg"], "hedge_leg": r["hedge_leg"], "n_skip": r["n_skip"]}
            print("standalone", ay, out["standalone"][ay])
        recent_trades = simulate_year(grid, all_idx[4][1], positions,
                                      standalone=True, pxmap=pxmap, tag=variant)["trades"]
        pd.DataFrame([{**t, "anchor": all_idx[4][0]} for t in recent_trades]).to_parquet(
            HERE / f"trades_{variant}_recent.parquet")

        # sensitivities (dev4 only, labelled)
        for sname, kw in {"sigma_otmiv": {"sigma_src": "otmiv"},
                          "fees_x2": {"cap_rate": 0.0006, "settle_rate": 0.0003},
                          "hedge_slip_5bps": {"hedge_slip": 0.0005}}.items():
            sp = build_positions(grid, gh, data, variant, **kw)
            yrs = []
            for ay, idx in dev_idx:
                r = simulate_year(grid, idx, sp, standalone=True, pxmap=pxmap, tag=variant + sname)
                yrs.append({"anchor": ay, "R": r["R"], "DD": r["DD"], "end": r["end"],
                            "trades": r["n"], "win": r["win"], "tp": r["tp"],
                            "sl": r["sl"], "expiry": r["expiry"]})
            R4 = float(np.prod([1 + y["R"] / 100 for y in yrs]) ** (1 / 4) - 1) * 100
            out["sens"][sname] = {"years": yrs, "dev4_mean": round(R4, 3),
                                  "dev4_worst": min(y["R"] for y in yrs),
                                  "dev4_DD": max(y["DD"] for y in yrs),
                                  "dev4_losing": sum(y["R"] < 0 for y in yrs)}
            print("sens", sname, out["sens"][sname])

        # overlay on G2 (yearly reset + full path), f=0 must reproduce G2
        ov = {}
        for f in [0.0] + F_OVERLAY:
            years = []
            for y, (ay, idx) in enumerate(all_idx):
                le = gn <= ANCH[y].value
                b = np.array([float(Es[s][le][-1]) if le.any() else 1.0 for s in range(4)])
                E4 = [Es[s][idx] / b[s] for s in range(4)]
                M4 = [Ms[s][idx] / b[s] for s in range(4)]
                es = np.mean(E4, axis=0)
                ms = np.mean(M4, axis=0)
                if f == 0.0:
                    A_arr, M_arr = es, ms
                    dU = np.zeros(len(idx))
                    g2l = np.zeros(len(idx))
                else:
                    es_prev = np.concatenate([[1.0], es[:-1]])
                    g = es / es_prev
                    hh = ms / es_prev
                    r = simulate_year(grid, idx, positions, g=g, hh=hh, f=f,
                                      standalone=False, pxmap=pxmap, tag=f"{variant}f{f}")
                    A_arr, M_arr, dU, g2l = r["E"], r["M"], r["dU"], r["g2"]
                pk = np.maximum.accumulate(A_arr)
                R = round(100 * float(A_arr[-1] ** (1 / 12) - 1), 3)
                DD = round(100 * float(np.max(1 - M_arr / pk)), 2)
                years.append({"anchor": ay, "R": R, "DD": DD, "end": round(float(A_arr[-1]), 6)})
                if f == F_OVERLAY[0]:
                    ov_years_legs = (ay, idx, dU, g2l, A_arr)
            R5 = round(float(np.prod([1 + yy["R"] / 100 for yy in years]) ** (1 / 5) - 1) * 100, 3)
            ov[f"G2_f{f}"] = {"years": years, "R": R5,
                              "W": min(yy["R"] for yy in years),
                              "DD": max(yy["DD"] for yy in years),
                              "losing": sum(yy["R"] < 0 for yy in years)}
        got0 = ov["G2_f0.0"]
        assert [yy["R"] for yy in got0["years"]] == [rr for rr, _ in exp["years"]], got0
        assert [yy["DD"] for yy in got0["years"]] == [dd for _, dd in exp["years"]], got0
        assert got0["R"] == exp["R"] and got0["W"] == exp["W"] and got0["DD"] == exp["DD"]
        print("f=0 overlay validation OK: reproduces v421_result G2 to the digit")
        out["overlay"] = ov

        # full-path DD (continuous account from grid start; sleeve close-marked)
        mask = grid > pd.Timestamp("2021-09-24", tz="UTC")
        fidx = np.where(mask)[0]
        for key, f in (("sleeve_only", 1.0), (f"G2_f{F_OVERLAY[0]}", F_OVERLAY[0]),
                       ((f"G2_f{F_OVERLAY[1]}", F_OVERLAY[1]))):
            if key == "sleeve_only":
                r = simulate_year(grid, fidx, positions, standalone=True, pxmap=pxmap, tag="full")
                Ec, Mc = r["E"], r["M"]
            else:
                Etot_p = Es.mean(axis=0)[mask]
                Mtot_p = Ms.mean(axis=0)[mask]
                Eprev = np.concatenate([[Etot_p[0]], Etot_p[:-1]])
                g = Etot_p / Eprev
                hhm = Mtot_p / Eprev
                r = simulate_year(grid, fidx, positions, g=g, hh=hhm, f=f,
                                  standalone=False, pxmap=pxmap, tag="full" + key)
                Ec, Mc = r["E"], r["M"]
            pk = np.maximum.accumulate(Ec)
            dd_m = round(100 * float(np.max(1 - Mc / pk)), 2)
            dd_c = round(100 * float(np.max(1 - Ec / pk)), 2)
            out["full"][key] = {"DD": max(dd_m, dd_c), "DD_marked": dd_m,
                                "DD_close": dd_c, "end": round(float(Ec[-1]), 6)}
        out["full"]["G2_alone"] = {"DD": exp["full_path_dd"]}
        print("full-path:", out["full"])

        # daily-P&L correlation (sleeve leg vs G2 leg, yearly-reset combo f=0.25 concat)
        dall, gall = [], []
        for y, (ay, idx) in enumerate(all_idx):
            le = gn <= ANCH[y].value
            b = np.array([float(Es[s][le][-1]) if le.any() else 1.0 for s in range(4)])
            es = np.mean([Es[s][idx] / b[s] for s in range(4)], axis=0)
            ms = np.mean([Ms[s][idx] / b[s] for s in range(4)], axis=0)
            es_prev = np.concatenate([[1.0], es[:-1]])
            g = es / es_prev
            hh = ms / es_prev
            r = simulate_year(grid, idx, positions, g=g, hh=hh, f=F_OVERLAY[0],
                              standalone=False, pxmap=pxmap, tag="corr")
            df = pd.DataFrame({"d": grid[idx].date, "sleeve": r["dU"], "g2": r["g2"]})
            dall.append(df)
        dall = pd.concat(dall).groupby("d")[["sleeve", "g2"]].sum()
        c_all = float(dall["sleeve"].corr(dall["g2"])) if len(dall) > 2 else float("nan")
        worst20 = set(dall.nsmallest(20, "g2").index)
        sub = dall.loc[dall.index.isin(worst20)]
        c_w = float(sub["sleeve"].corr(sub["g2"])) if len(sub) > 2 else float("nan")
        # worst 5 combo weeks (yearly-reset f=0.25 paths, 168h returns)
        weeks = []
        for y, (ay, idx) in enumerate(all_idx):
            le = gn <= ANCH[y].value
            b = np.array([float(Es[s][le][-1]) if le.any() else 1.0 for s in range(4)])
            es = np.mean([Es[s][idx] / b[s] for s in range(4)], axis=0)
            ms = np.mean([Ms[s][idx] / b[s] for s in range(4)], axis=0)
            es_prev = np.concatenate([[1.0], es[:-1]])
            r = simulate_year(grid, idx, positions, g=es / es_prev, hh=ms / es_prev,
                              f=F_OVERLAY[0], standalone=False, pxmap=pxmap, tag="weeks")
            E = r["E"]
            for k in range(168, len(E)):
                if E[k - 168] > 0:
                    weeks.append((str(grid[idx[k]].date()), float(E[k] / E[k - 168] - 1)))
        weeks.sort(key=lambda t: t[1])
        seen, worst5 = set(), []
        for d, v in weeks:
            if d not in seen:
                seen.add(d)
                worst5.append([d, round(v * 100, 2)])
            if len(worst5) == 5:
                break
        out["corr"] = {"daily_corr_all": round(c_all, 3),
                       "daily_corr_g2worst20": round(c_w, 3),
                       "worst5_weeks": worst5}
        print("corr:", out["corr"])

        (HERE / "tmp" / "final.json").write_text(json.dumps(out, indent=1, default=str))
        (HERE / "results.json").write_text(json.dumps(out, indent=1, default=str))
        print("final done ->", HERE / "tmp/final.json", " + results.json")

    else:
        raise SystemExit(f"unknown stage {stage}")


if __name__ == "__main__":
    main()