"""oc_putwrite runner: weekly cash-secured put-write sleeve (BTC+ETH).

Implements PLAN.md exactly. One process, 1m+4h data only, small RAM.
Outputs: results.json, trades_<variant>.parquet in this folder.
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
import putwrite as P

RD = ROOT / "research/parallel/rounds/parallel-20260906-r2"
V421 = RD / "v421/v421_runs.pkl"
V421_RES = RD / "v421/v421_result.json"
IVDIR = ROOT / "data/raw/deribit_opt_20260926"
DVDIR = ROOT / "data/raw/deribit_dvol_20261005"
BTC1M = ROOT / "data/raw/btc_intraday_20260924"
ETH1M = ROOT / "data/raw/majors_intraday_20260924"

STRAT = "R2B1D17BFG2"
GRID0 = pd.Timestamp("2021-09-24 04:00", tz="UTC")
ANCH_S = ["2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24"]
ANCH = [pd.Timestamp(a, tz="UTC") for a in ANCH_S]
YEAR = pd.Timedelta(days=365)
GRID_LIST = ["BTC", "ETH"]
YK = {c: (1000.0 if c == "BTC" else 50.0) for c in GRID_LIST}

VARIANTS = {
    "P1": {"z": 1.0, "spread": False},
    "P2": {"z": 1.5, "spread": False},
    "P3": {"z": 2.0, "spread": False},
    "P4": {"z": 1.5, "spread": True, "z_long": 3.0},
}
F_OVERLAY = [0.25, 0.5]


def _load_v388():
    spec = importlib.util.spec_from_file_location("v388_pw", RD / "v388/v388_bot_stop_distance.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------- data ----------------

def load_iv(coin):
    df = pd.read_parquet(IVDIR / f"{coin}_options_4h.parquet", columns=["bar", "iv_otm_put"])
    df = df.sort_values("bar").reset_index(drop=True)
    t0 = pd.to_datetime(df["bar"], utc=True).values.astype("datetime64[ns]").astype(np.int64)
    return t0, df["iv_otm_put"].to_numpy(dtype=float)


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
    return ms[keep] * 1_000_000, cl[keep]  # ns, vol points


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
    return ts[o], cl[o]


def px_at(ts, cl, q_ns):
    """1m close of bar open exactly q; else last bar open strictly before q (causal)."""
    i = int(np.searchsorted(ts, q_ns, side="left"))
    if i < len(ts) and ts[i] == q_ns:
        return float(cl[i]), True
    if i > 0:
        return float(cl[i - 1]), False
    return float("nan"), False


def iv_known(iv_t0, iv_put, t_ns):
    """iv_otm_put of last 4h bar with close (start+4h) <= t; NaN if none/NaN."""
    i = int(np.searchsorted(iv_t0 + 4 * 3600_000_000_000, t_ns, side="right")) - 1
    if i < 0:
        return float("nan")
    return float(iv_put[i])


def dvol_known(d_ms, d_cl, t_ns):
    """DVOL close of last hourly candle with candle-close <= t; NaN if none."""
    i = int(np.searchsorted(d_ms + 3600_000_000_000, t_ns, side="right")) - 1
    if i < 0:
        return float("nan")
    return float(d_cl[i])


# ---------------- weekly precompute (per-unit, account-independent) ----------------

def fridays(a0: pd.Timestamp, a1: pd.Timestamp):
    days = pd.date_range(a0.normalize(), a1.normalize() + pd.Timedelta(days=8), freq="D")
    return [d for d in days if d.weekday() == 4]


def build_positions(grid, gh, data, variant, sigma_sell_mult=1.0, fee_mult=1.0):
    """Walk every Friday cycle; return list of per-unit position dicts.

    grid: hourly grid (UTC, hourly). gh: dict coin -> dict of hourly arrays.
    data: dict coin -> raw arrays. Entry applied at first grid step >= 08:05.
    """
    cap_rate = 0.0003 * fee_mult
    settle_rate = 0.00015 * fee_mult
    v = VARIANTS[variant]
    z, spread = v["z"], v["spread"]
    z_long = v.get("z_long", 3.0)
    gn = grid.values.astype("datetime64[ns]").astype(np.int64)
    positions = []
    n_inexact = 0
    for fri in fridays(grid[0], grid[-1]):
        entry_t = (fri + pd.Timedelta(hours=8, minutes=5)).value
        expiry_t = (fri + pd.Timedelta(days=7, hours=8)).value
        if entry_t < gn[0] or expiry_t > gn[-1]:
            continue
        settle_lo = (fri + pd.Timedelta(days=7, hours=7, minutes=30)).value
        for coin in GRID_LIST:
            d = data[coin]
            iv = iv_known(d["iv_t0"], d["iv_put"], entry_t)
            if not np.isfinite(iv):
                dv = dvol_known(d["d_ms"], d["d_cl"], entry_t)
                iv = dv if np.isfinite(dv) else float("nan")
            if not np.isfinite(iv) or iv <= 0:
                positions.append({"variant": variant, "coin": coin, "fri": str(fri.date()),
                                  "skip": "no-vol", "entry_step": -1})
                continue
            sigma_e = iv / 100.0
            s_min = (fri + pd.Timedelta(hours=8, minutes=4)).value
            S, exact = px_at(d["m_ts"], d["m_cl"], s_min)
            n_inexact += (not exact)
            if not np.isfinite(S) or S <= 0:
                positions.append({"variant": variant, "coin": coin, "fri": str(fri.date()),
                                  "skip": "no-price", "entry_step": -1})
                continue
            K = P.strike_from_spot(S, z, sigma_e, YK[coin])
            if not np.isfinite(K) or K <= 0:
                positions.append({"variant": variant, "coin": coin, "fri": str(fri.date()),
                                  "skip": "bad-strike", "entry_step": -1})
                continue
            prem = P.bs_put(S, K, 7.0 / 365.0, sigma_sell_mult * 0.95 * sigma_e)
            fee_in = min(cap_rate * S, 0.125 * prem)
            pos = {"variant": variant, "coin": coin, "fri": str(fri.date()), "skip": None,
                   "S": S, "K": K, "sigma_e": sigma_e, "premium": prem, "fee_in": fee_in,
                   "denom": K, "entry_t": int(entry_t), "expiry_t": int(expiry_t)}
            if spread:
                Kl = P.strike_from_spot(S, z_long, sigma_e, YK[coin])
                if not np.isfinite(Kl) or Kl <= 0 or Kl >= K:
                    # disclosed fallback: naked P2 leg for this coin/week
                    pos["spread_fallback_naked"] = True
                else:
                    sig_buy = 1.05 * sigma_e + 0.05
                    lc = P.bs_put(S, Kl, 7.0 / 365.0, sig_buy)
                    lf = min(cap_rate * S, 0.125 * lc)
                    pos["K_long"] = Kl
                    pos["long_cost"] = lc
                    pos["long_fee_in"] = lf
                    pos["denom"] = K - Kl
            # hourly slice
            e_step = int(np.searchsorted(gn, entry_t, side="right"))
            x_step = int(np.searchsorted(gn, expiry_t, side="left"))
            noon = ((fri + pd.Timedelta(hours=12)).value)
            c0 = max(e_step, int(np.searchsorted(gn, noon, side="left")))
            sl = slice(e_step, x_step)
            gseg = gn[sl]
            h = gh[coin]
            px = h["px"][sl]
            ivs = h["ivsrc"][sl]
            sig_m = 1.05 * ivs / 100.0
            T = (expiry_t - gseg) / (365.0 * 86400 * 1_000_000_000)
            marks = P.bs_put_vec(px, K, T, sig_m)
            exit_kind, exit_step, exit_mark, exit_px = "expiry", x_step, 0.0, float("nan")
            lmarks = None
            if spread and "K_long" in pos:
                sig_l = 0.95 * ivs / 100.0 + 0.05
                lmarks = P.bs_put_vec(px, pos["K_long"], T, sig_l)
            for j in range(c0 - e_step, len(gseg)):
                t = gseg[j]
                hh = pd.Timestamp(t, tz="UTC")
                is_4h = hh.hour % 4 == 0 and hh.minute == 0
                m = float(marks[j])
                if is_4h and m <= 0.2 * prem:
                    exit_kind, exit_step, exit_mark, exit_px = "tp", e_step + j, m, float(px[j])
                    break
                if m >= 3.0 * prem:
                    exit_kind, exit_step, exit_mark, exit_px = "sl", e_step + j, m, float(px[j])
                    break
            fee_out = 0.0
            lexit = 0.0
            lfee_out = 0.0
            if exit_kind in ("tp", "sl"):
                fee_out = min(cap_rate * exit_px, 0.125 * exit_mark)
                if lmarks is not None:
                    lexit = float(lmarks[exit_step - e_step])
                    lfee_out = min(cap_rate * exit_px, 0.125 * lexit)
            else:
                s_vals = []
                for k in range(30):
                    q = settle_lo + k * 60_000_000_000
                    pxq, _ = px_at(d["m_ts"], d["m_cl"], q)
                    s_vals.append(pxq)
                S_set = float(np.mean(s_vals))
                intr = max(K - S_set, 0.0)
                stl = min(settle_rate * S_set, 0.125 * intr) if intr > 0 else 0.0
                exit_mark, exit_px = intr, S_set
                fee_out = stl
                pos["S_settle"] = S_set
                if "K_long" in pos:
                    pos["long_intrinsic"] = max(pos["K_long"] - S_set, 0.0) if np.isfinite(S_set) else 0.0
            pos.update({"entry_step": e_step, "expiry_step": x_step, "exit_kind": exit_kind,
                        "exit_step": exit_step, "exit_mark": exit_mark, "exit_px": exit_px,
                        "fee_out": fee_out, "marks": marks,
                        "long_exit": lexit, "long_fee_out": lfee_out, "long_marks": lmarks})
            positions.append(pos)
    print(f"[{variant}] positions={len(positions)} inexact_px={n_inexact}")
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


def simulate_year(grid, idx, positions, g=None, hh=None, f=1.0, standalone=True):
    """Hourly account loop. g/hh: base growth arrays (overlay); standalone g=1.

    Entries/exits are grid steps; boundary weeks (expiry past year end) skipped.
    Standalone: E[i] = cash + unrealized. Overlay: A = A_prev*g + dU sleeve,
    M = M_prev*hh + dU sleeve; close path uses the same sleeve dU (disclosed).
    Returns dict with equity path, per-cycle stats, trade rows.
    """
    n = len(idx)
    year_end_ns = (grid[idx[-1]] + pd.Timedelta(hours=1)).value
    gpos = {s: [] for s in range(n)}
    for p in positions:
        if p.get("skip") or p["entry_step"] < 0:
            continue
        e = p["entry_step"] - idx[0]
        if not (0 <= e < n):
            continue
        if p["expiry_t"] > year_end_ns:
            p.setdefault("skipped_years", []).append(str(grid[idx[0]].date()))
            continue
        gpos[e].append(("entry", p))
        x = p["exit_step"] - idx[0]
        if 0 <= x < n:
            gpos[x].append(("exit", p))
    E = np.empty(n)
    Mc = np.empty(n)
    cash = 1.0
    A_prev = 1.0
    cash_prev, U_prev = 1.0, 0.0
    open_p = []
    qmap = {}
    trades = []
    cyc = {}
    leg_sleeve = np.zeros(n) if not standalone else None
    leg_g2 = np.zeros(n) if not standalone else None
    for i in range(n):
        gi = 1.0 if g is None else float(g[i])
        hhi = 1.0 if hh is None else float(hh[i])
        prev_acct = cash + U_prev if standalone else A_prev
        for kind, p in gpos.get(i, []):
            if kind == "entry":
                acct = (cash + U_prev) if standalone else A_prev
                if "K_long" in p:
                    q = P.size_spread(acct, p["K"], p["K_long"], 1.0 if standalone else f)
                else:
                    q = P.size_naked(acct, p["K"], 1.0 if standalone else f)
                qmap[id(p)] = q
                open_p.append(p)
                cf = q * (p["premium"] - p["fee_in"])
                if "K_long" in p:
                    cf -= q * (p["long_cost"] + p["long_fee_in"])
                cash += cf
                c = cyc.setdefault(p["fri"], {"E_base": prev_acct, "prem": 0.0, "pnl": 0.0})
                c["prem"] += q * p["premium"]
            else:
                if p in open_p:
                    open_p.remove(p)
                q = qmap.pop(id(p), 0.0)
                if p["exit_kind"] in ("tp", "sl"):
                    cash -= q * (p["exit_mark"] + p["fee_out"])
                    if "K_long" in p:
                        cash += q * (p["long_exit"] - p["long_fee_out"])
                    pnl_u = P.weekly_pnl_per_unit(p["premium"], p["fee_in"], p["exit_kind"],
                                                  p["exit_mark"], p["fee_out"])
                    if "K_long" in p:
                        pnl_u += (p["long_exit"] - p["long_fee_out"]) - (p["long_cost"] + p["long_fee_in"])
                else:
                    cash -= q * (p["exit_mark"] + p["fee_out"])
                    if "K_long" in p:
                        cash += q * p.get("long_intrinsic", 0.0)
                    pnl_u = P.weekly_pnl_per_unit(p["premium"], p["fee_in"], "expiry",
                                                  intrinsic=p["exit_mark"], settle=p["fee_out"])
                    if "K_long" in p:
                        pnl_u += p.get("long_intrinsic", 0.0) - (p["long_cost"] + p["long_fee_in"])
                cyc[p["fri"]]["pnl"] += q * pnl_u
                trades.append({"fri": p["fri"], "coin": p["coin"], "variant": p["variant"],
                               "exit": p["exit_kind"], "q": q, "K": p["K"],
                               "premium": p["premium"], "pnl": q * pnl_u,
                               "win": bool(q * pnl_u > 0)})
        U = 0.0
        for o in open_p:
            j = idx[i] - o["entry_step"]
            if 0 <= j < len(o["marks"]):
                U -= qmap.get(id(o), 0.0) * float(o["marks"][j])
                if o.get("long_marks") is not None:
                    U += qmap.get(id(o), 0.0) * float(o["long_marks"][j])
        acct_now = cash + U
        if standalone:
            A_i, M_i = acct_now, acct_now
        else:
            dU = acct_now - (cash_prev + U_prev)
            A_i = A_prev * gi + dU
            M_i = A_prev * hhi + dU  # marked level off pre-step account (NOT cumprod)
            leg_sleeve[i] = dU
            leg_g2[i] = A_prev * (gi - 1.0)
        E[i] = A_i
        Mc[i] = M_i
        cash_prev, U_prev, A_prev = cash, U, A_i
    pk = np.maximum.accumulate(E)
    dd = float(np.max(1 - Mc / pk)) if np.all(pk > 0) else float("nan")
    R = float(E[-1] ** (1 / 12) - 1) * 100 if E[-1] > 0 else float("-inf")
    worst = None
    for fri, c in cyc.items():
        base = c.get("E_base", 0) or 0
        if base <= 0:
            continue
        r = c["pnl"] / base * 100
        if worst is None or r < worst[1]:
            worst = (fri, round(r, 3))
    n_tr = len(trades)
    wins = sum(t["win"] for t in trades)
    kinds = {k: sum(1 for t in trades if t["exit"] == k) for k in ("tp", "sl", "expiry")}
    ybases = [c["prem"] / c["E_base"] for c in cyc.values() if (c.get("E_base", 0) or 0) > 0]
    prem_yield = float(np.mean(ybases)) if ybases else 0.0
    return {"E": E, "M": Mc, "R": round(R, 3), "DD": round(dd * 100, 2),
            "end": round(float(E[-1]), 6), "trades": trades, "n": n_tr,
            "win": round(wins / n_tr, 4) if n_tr else 0.0,
            "tp": kinds["tp"], "sl": kinds["sl"], "expiry": kinds["expiry"],
            "worst_week": worst, "prem_yield": round(prem_yield * 100, 3),
            "cycles": cyc, "leg_sleeve": leg_sleeve, "leg_g2": leg_g2}


def main():
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

    # G2 baseline validation via reset_metric
    sys.path.insert(0, str(ROOT / "research/diagnostics/r2_decompose5"))
    from reset_metric import year_reset
    exp = json.loads(V421_RES.read_text())["rows"][STRAT]
    got_years = []
    for y in range(5):
        r = year_reset(runs, STRAT, y)
        got_years.append(r)
    assert [r["R"] for r in got_years] == [rr for rr, _ in exp["years"]], got_years
    assert [r["DD"] for r in got_years] == [dd for _, dd in exp["years"]], got_years
    print("G2 baseline validation OK (yearly R/DD reproduce v421_result to the digit)")

    # ---- market data ----
    data = {}
    for coin in GRID_LIST:
        iv_t0, iv_put = load_iv(coin)
        d_ms, d_cl = load_dvol(coin)
        m_ts, m_cl = load_1m(coin)
        data[coin] = {"iv_t0": iv_t0, "iv_put": iv_put, "d_ms": d_ms, "d_cl": d_cl,
                      "m_ts": m_ts, "m_cl": m_cl}
    # hourly price + ivsrc arrays on grid (causal: last 1m close <= t; last closed 4h bar)
    gh = {}
    for coin in GRID_LIST:
        d = data[coin]
        px = np.array([px_at(d["m_ts"], d["m_cl"], t)[0] for t in gn])
        ivs = np.array([iv_known(d["iv_t0"], d["iv_put"], t) for t in gn])
        need_fb = ~np.isfinite(ivs)
        if need_fb.any():
            fb = np.array([dvol_known(d["d_ms"], d["d_cl"], t) if nf else np.nan
                           for t, nf in zip(gn, need_fb)])
            ivs[need_fb] = fb[need_fb]
        assert np.isfinite(px).all(), coin
        print(coin, "hourly iv fallback bars:", int(np.isnan(
            np.array([iv_known(d['iv_t0'], d['iv_put'], t) for t in gn])).sum()))
        gh[coin] = {"px": px, "ivsrc": ivs}

    dev_idx = year_slices(grid)[:4]
    all_idx = year_slices(grid)

    results = {"variants": {}, "meta": {
        "grid": [str(grid[0]), str(grid[-1])],
        "strat": STRAT,
        "note": "entries applied at first hourly step >= 08:05 (09:00); no exit checks before Fri 12:00; TP before SL at 4h closes; boundary weeks skipped per year; long-expiry = intrinsic, no fee (disclosed)",
    }}
    for variant in VARIANTS:
        positions = build_positions(grid, gh, data, variant)
        yrs = []
        all_trades = []
        for ay, idx in dev_idx:
            out = simulate_year(grid, idx, positions, standalone=True)
            yrs.append({"anchor": ay, "R": out["R"], "DD": out["DD"], "end": out["end"],
                        "trades": out["n"], "win": out["win"], "tp": out["tp"],
                        "sl": out["sl"], "expiry": out["expiry"],
                        "worst_week": out["worst_week"], "prem_yield_pct": out["prem_yield"]})
            all_trades.extend([{**t, "anchor": ay} for t in out["trades"]])
        R5 = float(np.prod([1 + y["R"] / 100 for y in yrs]) ** (1 / 4) - 1) * 100
        results["variants"][variant] = {
            "years": yrs,
            "dev4_mean": round(R5, 3),
            "dev4_worst": min(y["R"] for y in yrs),
            "dev4_DD": max(y["DD"] for y in yrs),
            "dev4_losing": sum(y["R"] < 0 for y in yrs),
        }
        pd.DataFrame(all_trades).to_parquet(HERE / f"trades_{variant}_dev4.parquet")
        print(variant, results["variants"][variant])
    (HERE / "tmp" / "dev4.json").write_text(json.dumps(results, indent=1, default=str))
    print("dev4 done ->", HERE / "tmp/dev4.json")


if __name__ == "__main__":
    main()
