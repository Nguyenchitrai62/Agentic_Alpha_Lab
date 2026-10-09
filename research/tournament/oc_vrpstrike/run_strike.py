"""oc_vrpstrike runner: weekly short ATM straddle priced from REAL Deribit traded IV.

Implements PLAN.md exactly (STRIKE-V2, single frozen variant; no selection).
Stages:
  python run_strike.py inventory  -> complete-month inventory + overlap check
                                    (manifests only + sha/row compare)
                                    -> tmp/inventory.json
  python run_strike.py dev        -> build Friday coin-weeks, standalone f=1
                                    yearly sim on dev4 anchors (PARTIAL-aware)
                                    -> tmp/dev.json + trades_strike_dev4.parquet
  python run_strike.py final     -> G2 f=0 reproduction assert, overlay f=0.25
                                    (dev4 + recent ONCE), full-path DD,
                                    diagnostics, STATUS.md + results.json

One process, strike + 1m + hourly DVOL data only. Run via heavy_slot.
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
import vrpstrike as S

RD = ROOT / "research/parallel/rounds/parallel-20260906-r2"
V421 = RD / "v421/v421_runs.pkl"
V421_RES = RD / "v421/v421_result.json"
DVDIR = ROOT / "data/raw/deribit_dvol_20261005"
BTC1M = ROOT / "data/raw/btc_intraday_20260924"
ETH1M = ROOT / "data/raw/majors_intraday_20260924"
SDIR = ROOT / "data/raw/deribit_strike_20261007"
SDIR_B = ROOT / "data/raw/deribit_strike_20261007_b"

STRAT = "R2B1D17BFG2"
GRID0 = pd.Timestamp("2021-09-24 04:00", tz="UTC")
ANCH_S = ["2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24"]
ANCH = [pd.Timestamp(a, tz="UTC") for a in ANCH_S]
YEAR = pd.Timedelta(days=365)
COINS = ["BTC", "ETH"]
YNS = int(365 * 86400 * 1_000_000_000)
F_OVERLAY = 0.25
H24 = 24 * 3600 * 1_000_000_000


def _load_v388():
    spec = importlib.util.spec_from_file_location("v388_strike", RD / "v388/v388_bot_stop_distance.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------- manifests / inventory ----------------

def _manifest_complete(coin: str, folder: Path) -> list[str]:
    m = json.loads((folder / coin / "manifest.json").read_text())
    ml = m.get("months", [])
    if ml and isinstance(ml[0], str):
        # ["BTC_2021-01.parquet", ...] or ["BTC_2026-02.parquet", ...]
        out = []
        for f in ml:
            stem = f.replace(".parquet", "")
            parts = stem.split("_", 1)
            out.append(parts[1] if len(parts) == 2 else stem)
        return sorted(out)
    out = []
    for e in ml:
        if isinstance(e, dict) and e.get("month"):
            if e.get("complete", True):
                out.append(e["month"])
    return sorted(out)


def inventory() -> dict:
    inv: dict = {"coins": {}, "overlap": {}}
    for coin in COINS:
        fwd = _manifest_complete(coin, SDIR)
        bwd = _manifest_complete(coin, SDIR_B)
        fwd_files = sorted((SDIR / coin).glob(f"{coin}_*.parquet"))
        bwd_files = sorted((SDIR_B / coin).glob(f"{coin}_*.parquet"))
        inv["coins"][coin] = {
            "forward_complete": fwd,
            "backward_complete": bwd,
            "union_complete": sorted(set(fwd) | set(bwd)),
            "disk_forward": [p.name for p in fwd_files],
            "disk_backward": [p.name for p in bwd_files],
        }
        both = sorted(set(fwd) & set(bwd))
        inv["overlap"][coin] = {"months": both, "identical": {}}
        for mm in both:
            a = SDIR / coin / f"{coin}_{mm}.parquet"
            b = SDIR_B / coin / f"{coin}_{mm}.parquet"
            dfa = pd.read_parquet(a)
            dfb = pd.read_parquet(b)
            same = dfa.shape == dfb.shape and bool(
                (dfa.sort_values(list(dfa.columns)).reset_index(drop=True)
                 == dfb.sort_values(list(dfb.columns)).reset_index(drop=True)).all().all())
            if not same:
                raise SystemExit(f"OVERLAP MISMATCH {coin} {mm}: shapes {dfa.shape} vs {dfb.shape}")
            inv["overlap"][coin]["identical"][mm] = {"rows": int(dfa.shape[0]), "identical": True}
    (HERE / "tmp").mkdir(exist_ok=True)
    (HERE / "tmp" / "inventory.json").write_text(json.dumps(inv, indent=1))
    print(json.dumps({c: {k: (v if not isinstance(v, list) or len(v) < 12 else f"{len(v)} months: {v[0]}..{v[-1]}")
                         for k, v in d.items()} for c, d in inv["coins"].items()}, indent=1))
    print("overlap:", json.dumps(inv["overlap"], indent=1))
    return inv


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


def load_strike(inv: dict) -> dict:
    """Load ONLY complete-month files. Returns per-coin lookup structures."""
    out = {}
    for coin in COINS:
        months = set(inv["coins"][coin]["union_complete"])
        frames = []
        for folder in (SDIR / coin, SDIR_B / coin):
            for p in sorted(folder.glob(f"{coin}_*.parquet")):
                mm = p.name.replace(".parquet", "").split("_", 1)[1]
                if mm not in months:
                    continue
                df = pd.read_parquet(p)
                frames.append(df)
        if not frames:
            out[coin] = None
            continue
        df = pd.concat(frames, ignore_index=True)
        # normalise
        df["hour_ns"] = pd.to_datetime(df["hour"], utc=True).values.astype("datetime64[ns]").astype(np.int64)
        df["expiry_date"] = pd.to_datetime(df["expiry"], utc=True).dt.normalize()
        df["close_ns"] = df["hour_ns"] + 3600_000_000_000
        # dedupe (hour, instrument): identical rows -> keep first (overlap months)
        dup = df.duplicated(subset=["hour_ns", "instrument_name"], keep=False)
        if bool(dup.any()):
            g = df[dup].sort_values(["hour_ns", "instrument_name"])
            # verify identical across all data columns within each key
            nunq = g.groupby(["hour_ns", "instrument_name"]).agg(
                {c: "nunique" for c in df.columns if c not in ("hour_ns", "instrument_name")})
            if bool((nunq > 1).any().any()):
                raise SystemExit(f"CONFLICTING dup rows for {coin}")
            print(f"[{coin}] deduped {(dup).sum()} identical overlap rows")
            df = df.drop_duplicates(subset=["hour_ns", "instrument_name"], keep="first")
        df = df.sort_values("hour_ns").reset_index(drop=True)
        # median index per hour
        med = df.groupby("hour_ns")["vwap_index"].median()
        hours = med.index.to_numpy(dtype=np.int64)
        medv = med.to_numpy(dtype=float)
        # per-instrument series
        inst: dict[str, tuple] = {}
        for name, gd in df.groupby("instrument_name"):
            gd = gd.sort_values("hour_ns")
            inst[name] = (gd["close_ns"].to_numpy(dtype=np.int64),
                          gd["vwap_iv"].to_numpy(dtype=float))
        # entry cell lookup
        cell = {}
        for _, r in df[["instrument_name", "hour_ns", "vwap_iv", "sum_amount"]].iterrows():
            cell[(r["instrument_name"], int(r["hour_ns"]))] = (float(r["vwap_iv"]), float(r["sum_amount"]))
        # (expiry_date, strike, cp) -> instrument
        key2inst = {}
        for (ed, k, cp), gd in df.groupby(["expiry_date", "strike", "cp"]):
            key2inst[(str(pd.Timestamp(ed).date()), float(k), str(cp))] = str(gd["instrument_name"].iloc[0])
        exp_strikes: dict[str, np.ndarray] = {}
        for ed, gd in df.groupby("expiry_date"):
            exp_strikes[str(pd.Timestamp(ed).date())] = gd["strike"].to_numpy(dtype=float)
        out[coin] = {"df": df, "hours": hours, "medv": medv,
                     "inst": inst, "cell": cell, "key2inst": key2inst,
                     "exp_strikes": exp_strikes,
                     "months": sorted(months)}
    return out


# ---------------- Fridays ----------------

def fridays(a0: pd.Timestamp, a1: pd.Timestamp):
    days = pd.date_range(a0.normalize(), a1.normalize() + pd.Timedelta(days=8), freq="D")
    return [d for d in days if d.weekday() == 4]


# ---------------- position precompute (per-unit, account-independent) ----------------

def build_positions(grid, gh, mkt, strike, inv):
    gn = grid.values.astype("datetime64[ns]").astype(np.int64)
    positions = []
    n_inexact = 0
    counts = {"data-gap": 0, "low-volume": 0, "no-pair": 0, "no-vol": 0, "no-price": 0}
    fris = fridays(grid[0], grid[-1])
    for fri in fris:
        entry_ts = (fri + pd.Timedelta(hours=11)).value
        expiry_ts = (fri + pd.Timedelta(days=7, hours=8)).value
        if entry_ts < gn[0] or expiry_ts > gn[-1]:
            continue
        entry_month = fri.strftime("%Y-%m")
        expiry_month = (fri + pd.Timedelta(days=7)).strftime("%Y-%m")
        settle_lo = (fri + pd.Timedelta(days=7, hours=7, minutes=30)).value
        for coin in COINS:
            st = strike[coin]
            complete = set(inv["coins"][coin]["union_complete"])
            if st is None or entry_month not in complete or expiry_month not in complete:
                positions.append({"variant": "STRIKE-V2", "coin": coin, "fri": str(fri.date()),
                                  "skip": "data-gap", "entry_step": -1})
                counts["data-gap"] += 1
                continue
            d = mkt[coin]
            h = S.HAIRCUIT[coin]
            # index08
            h08 = (fri + pd.Timedelta(hours=8)).value
            j = int(np.searchsorted(st["hours"], h08))
            if j < len(st["hours"]) and st["hours"][j] == h08:
                index08 = float(st["medv"][j])
            else:
                lo = st["hours"][j - 1] if j > 0 else None
                hi = st["hours"][j] if j < len(st["hours"]) else None
                cands = [x for x in (lo, hi) if x is not None]
                if not cands:
                    positions.append({"variant": "STRIKE-V2", "coin": coin, "fri": str(fri.date()),
                                      "skip": "no-vol", "entry_step": -1})
                    counts["no-vol"] += 1
                    continue
                best = min(cands, key=lambda x: (abs(x - h08), x))
                index08 = float(st["medv"][int(np.searchsorted(st["hours"], best))])
            # strike nearest to index among this expiry's strikes
            expd = str((fri + pd.Timedelta(days=7)).date())
            arr = st["exp_strikes"].get(expd, np.array([]))
            K = S.select_strike(arr, index08)
            if not np.isfinite(K):
                positions.append({"variant": "STRIKE-V2", "coin": coin, "fri": str(fri.date()),
                                  "skip": "no-pair", "entry_step": -1})
                counts["no-pair"] += 1
                continue
            ci = st["key2inst"].get((expd, float(K), "C"))
            pi = st["key2inst"].get((expd, float(K), "P"))
            if ci is None or pi is None:
                positions.append({"variant": "STRIKE-V2", "coin": coin, "fri": str(fri.date()),
                                  "skip": "no-pair", "entry_step": -1})
                counts["no-pair"] += 1
                continue
            # entry IV over Fri 08/09/10 buckets
            legs = {}
            ok = True
            for leg, inst in (("C", ci), ("P", pi)):
                ivs, amts = [], []
                for hh in (8, 9, 10):
                    hb = (fri + pd.Timedelta(hours=hh)).value
                    v = st["cell"].get((inst, hb))
                    if v is not None:
                        ivs.append(v[0])
                        amts.append(v[1])
                iv_aw, tot = S.amount_weighted_iv(np.array(ivs), np.array(amts))
                legs[leg] = (iv_aw, tot)
                if not np.isfinite(iv_aw) or tot < S.MIN_ENTRY_AMOUNT:
                    ok = False
            if not ok:
                positions.append({"variant": "STRIKE-V2", "coin": coin, "fri": str(fri.date()),
                                  "skip": "low-volume", "entry_step": -1,
                                  "K": float(K), "index08": float(index08)})
                counts["low-volume"] += 1
                continue
            iv_c, amt_c = legs["C"]
            iv_p, amt_p = legs["P"]
            s_min = (fri + pd.Timedelta(hours=10, minutes=59)).value
            S_entry, exact = px_at(d["m_ts"], d["m_cl"], s_min)
            n_inexact += (not exact)
            if not np.isfinite(S_entry) or S_entry <= 0:
                positions.append({"variant": "STRIKE-V2", "coin": coin, "fri": str(fri.date()),
                                  "skip": "no-price", "entry_step": -1})
                counts["no-price"] += 1
                continue
            dv_entry = dvol_known(d["d_ms"], d["d_cl"], entry_ts)
            if not np.isfinite(dv_entry) or dv_entry <= 0:
                positions.append({"variant": "STRIKE-V2", "coin": coin, "fri": str(fri.date()),
                                  "skip": "no-vol", "entry_step": -1})
                counts["no-vol"] += 1
                continue
            r_c = float(iv_c) / float(dv_entry)
            r_p = float(iv_p) / float(dv_entry)
            T_entry = (expiry_ts - entry_ts) / YNS
            sig_c = S.sell_sigma(iv_c, coin)
            sig_p = S.sell_sigma(iv_p, coin)
            prem_c = S.bs_call(S_entry, K, T_entry, sig_c)
            prem_p = S.bs_put(S_entry, K, T_entry, sig_p)
            gross = float(prem_c + prem_p)
            fee_c = S.fee_per_side(S_entry, prem_c)
            fee_p = S.fee_per_side(S_entry, prem_p)
            opt_cash = float(gross - fee_c - fee_p)
            e_step = int(np.searchsorted(gn, entry_ts, side="right"))
            x_step = int(np.searchsorted(gn, expiry_ts, side="left"))
            sl = slice(e_step, x_step + 1)
            L = x_step - e_step + 1
            gseg = gn[sl]
            px = gh[coin]["px"][sl]
            dv = gh[coin]["dv"][sl]
            if not np.all(np.isfinite(dv)):
                positions.append({"variant": "STRIKE-V2", "coin": coin, "fri": str(fri.date()),
                                  "skip": "no-vol", "entry_step": -1})
                counts["no-vol"] += 1
                continue
            T = (expiry_ts - gseg) / YNS
            cc, ic = st["inst"][ci]
            cp_, ip_ = st["inst"][pi]
            mid = np.empty(L)
            ask = np.empty(L)
            for k in range(L):
                t = int(gseg[k])
                # call leg
                ivt, fresh = S.last_traded_iv(cc, ic, t)
                if fresh:
                    sm_c, sa_c = ivt / 100.0, (ivt + h) / 100.0
                else:
                    sm_c = r_c * float(dv[k]) / 100.0
                    sa_c = sm_c + h / 100.0
                ivt, fresh = S.last_traded_iv(cp_, ip_, t)
                if fresh:
                    sm_p, sa_p = ivt / 100.0, (ivt + h) / 100.0
                else:
                    sm_p = r_p * float(dv[k]) / 100.0
                    sa_p = sm_p + h / 100.0
                mid[k] = S.bs_call(px[k], K, T[k], sm_c) + S.bs_put(px[k], K, T[k], sm_p)
                ask[k] = S.bs_call(px[k], K, T[k], sa_c) + S.bs_put(px[k], K, T[k], sa_p)
            exit_kind, exit_j = "expiry", L - 1
            for k in range(L - 1):
                is_4h = pd.Timestamp(gn[e_step + k], tz="UTC").hour % 4 == 0
                if is_4h and mid[k] <= 0.3 * gross:
                    exit_kind, exit_j = "tp", k
                    break
                if opt_cash - ask[k] <= -gross:
                    exit_kind, exit_j = "sl", k
                    break
            px_x = float(px[exit_j])
            if exit_kind in ("tp", "sl"):
                Tx = float(T[exit_j])
                t = int(gseg[exit_j])
                ivcx, fcx = S.last_traded_iv(cc, ic, t)
                ivpx, fpx = S.last_traded_iv(cp_, ip_, t)
                if exit_kind == "sl":
                    scx = (ivcx + h) / 100.0 if fcx else r_c * float(dv[exit_j]) / 100.0 + h / 100.0
                    spx = (ivpx + h) / 100.0 if fpx else r_p * float(dv[exit_j]) / 100.0 + h / 100.0
                else:
                    scx = ivcx / 100.0 if fcx else r_c * float(dv[exit_j]) / 100.0
                    spx = ivpx / 100.0 if fpx else r_p * float(dv[exit_j]) / 100.0
                leg_c = S.bs_call(px_x, K, Tx, scx)
                leg_p = S.bs_put(px_x, K, Tx, spx)
                fc = S.fee_per_side(px_x, leg_c)
                fp = S.fee_per_side(px_x, leg_p)
                cf_exit = -(leg_c + leg_p + fc + fp)
                pnl_u = opt_cash + cf_exit
                S_set = float("nan")
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
                stl = S.settle_fee(S_set, intr_c) + S.settle_fee(S_set, intr_p)
                cf_exit = -((intr_c + intr_p) + stl)
                pnl_u = opt_cash + cf_exit
            lo = int(np.searchsorted(d["m_ts"], s_min, side="left"))
            hi = int(np.searchsorted(d["m_ts"], expiry_ts, side="left"))
            seg = d["m_cl"][lo:hi + 1]
            rv = float("nan")
            if len(seg) > 10 and np.all(seg > 0) and np.all(np.isfinite(seg)):
                r = np.diff(np.log(seg))
                rv = float(np.std(r, ddof=1) * np.sqrt(365 * 24 * 60))
            positions.append({
                "variant": "STRIKE-V2", "coin": coin, "fri": str(fri.date()), "skip": None,
                "S": S_entry, "K": float(K), "index08": float(index08),
                "call": ci, "put": pi, "iv_c": float(iv_c), "iv_p": float(iv_p),
                "amt_c": float(amt_c), "amt_p": float(amt_p),
                "r_c": float(r_c), "r_p": float(r_p), "dvol_entry": float(dv_entry),
                "gross": float(gross), "opt_cash": float(opt_cash),
                "entry_t": int(entry_ts), "expiry_t": int(expiry_ts),
                "entry_step": e_step, "expiry_step": x_step, "exit_kind": exit_kind,
                "exit_step": e_step + exit_j, "exit_j": exit_j,
                "cf_exit": float(cf_exit), "pnl_u": float(pnl_u), "S_settle": float(S_set),
                "rv": float(rv), "m10": mid.astype(float),
            })
    print(f"[STRIKE-V2] positions={len(positions)} skips={counts} inexact_px={n_inexact}")
    return positions


# ---------------- account simulation (V2-unhedged: no hedge leg) ----------------

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
    for i in range(n):
        gi = 1.0 if g is None else float(g[i])
        hhi = 1.0 if hh is None else float(hh[i])
        for p in ev_entry.get(i, []):
            acct = (cash + U_prev) if standalone else A_prev
            ff = 1.0 if standalone else f
            q = S.size_q(acct, p["S"], ff)
            qmap[id(p)] = q
            open_p.append(p)
            cash += q * p["opt_cash"]
        for p in ev_exit.get(i, []):
            q = qmap.pop(id(p), 0.0)
            if p in open_p:
                open_p.remove(p)
            cash += q * p["cf_exit"]
            trades.append({"fri": p["fri"], "coin": p["coin"], "exit": p["exit_kind"],
                           "q": q, "K": p["K"], "gross": p["gross"], "pnl": q * p["pnl_u"],
                           "win": bool(p["pnl_u"] > 0), "iv_c": p["iv_c"], "iv_p": p["iv_p"],
                           "r_c": p["r_c"], "r_p": p["r_p"], "rv": p["rv"],
                           "S": p["S"], "dvol": p["dvol_entry"],
                           "amt_c": p["amt_c"], "amt_p": p["amt_p"]})
        U = 0.0
        for o in open_p:
            j = idx[i] - o["entry_step"]
            assert 0 <= j < len(o["m10"]), (tag, i, j)
            U += qmap.get(id(o), 0.0) * (-float(o["m10"][j]))
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
        r = E[k] / E[k - 168] - 1 if E[k - 168] > 0 else float("nan")
        if np.isfinite(r) and (worst is None or r < worst):
            worst, worst_dt = r, str(grid[idx[k]].date())
    n_tr = len(trades)
    wins = sum(t["win"] for t in trades)
    kinds = {k: sum(1 for t in trades if t["exit"] == k) for k in ("tp", "sl", "expiry")}
    ivs = [(t["iv_c"] + t["iv_p"]) / 2 for t in trades]
    gaps = [(t["iv_c"] + t["iv_p"]) / 2 / 100.0 - t["rv"] for t in trades
            if np.isfinite(t["rv"])]
    rrs = [(t["r_c"] + t["r_p"]) / 2 for t in trades]
    prems = [t["gross"] / t["S"] * 100 for t in trades if np.isfinite(t["S"]) and t["S"] > 0]
    return {"E": E, "M": Mc, "R": round(R, 3), "DD": round(dd * 100, 2),
            "end": round(float(E[-1]), 6), "trades": trades, "n": n_tr,
            "win": round(wins / n_tr, 4) if n_tr else 0.0,
            "tp": kinds["tp"], "sl": kinds["sl"], "expiry": kinds["expiry"],
            "worst_week": None if worst is None else [worst_dt, round(worst * 100, 2)],
            "gap": round(float(np.mean(gaps)), 4) if gaps else None,
            "iv_mean": round(float(np.mean(ivs)), 2) if ivs else None,
            "r_mean": round(float(np.mean(rrs)), 4) if rrs else None,
            "r_med": round(float(np.median(rrs)), 4) if rrs else None,
            "r_p10": round(float(np.quantile(rrs, 0.1)), 4) if rrs else None,
            "r_p90": round(float(np.quantile(rrs, 0.9)), 4) if rrs else None,
            "prem_med": round(float(np.median(prems)), 4) if prems else None,
            "prem_mean": round(float(np.mean(prems)), 4) if prems else None,
            "n_skip": n_skip, "dU": dU_arr, "g2": g2_arr}


def diagnostics_for_year(out) -> dict:
    t = out["trades"]
    by_coin: dict = {}
    for c in COINS:
        tc = [x for x in t if x["coin"] == c]
        rr = [(x["r_c"] + x["r_p"]) / 2 for x in tc]
        by_coin[c] = {"n": len(tc),
                      "r_med": round(float(np.median(rr)), 4) if rr else None,
                      "r_mean": round(float(np.mean(rr)), 4) if rr else None}
    return {"n": out["n"], "by_coin": by_coin, "r_med": out["r_med"],
            "r_mean": out["r_mean"], "prem_med": out["prem_med"],
            "gap": out["gap"]}


# ---------------- main ----------------

def build_all():
    v388 = _load_v388()
    g1 = v388.Y1 + pd.Timedelta(hours=12)
    grid = pd.date_range(GRID0, g1, freq="1h")
    gn = grid.values.astype("datetime64[ns]").astype(np.int64)
    print("grid", grid[0], "->", grid[-1], len(grid))
    inv = json.loads((HERE / "tmp" / "inventory.json").read_text())
    mkt = {}
    for coin in COINS:
        d_ms, d_cl = load_dvol(coin)
        m_ts, m_cl = load_1m(coin)
        mkt[coin] = {"d_ms": d_ms, "d_cl": d_cl, "m_ts": m_ts, "m_cl": m_cl}
    gh, pxmap = {}, {}
    for coin in COINS:
        d = mkt[coin]
        px = np.array([px_at(d["m_ts"], d["m_cl"], int(t) - 60_000_000_000)[0] for t in gn])
        assert np.isfinite(px).all(), coin
        dv = np.array([dvol_known(d["d_ms"], d["d_cl"], int(t)) for t in gn])
        gh[coin] = {"px": px, "dv": dv}
        pxmap[coin] = px
    print("hourly DVOL NaN:", {c: int(np.isnan(gh[c]["dv"]).sum()) for c in COINS})
    strike = load_strike(inv)
    for coin in COINS:
        st = strike[coin]
        print(f"[{coin}] months={inv['coins'][coin]['union_complete']} "
              f"rows={0 if st is None else len(st['df'])} inst={0 if st is None else len(st['inst'])}")
    positions = build_positions(grid, gh, mkt, strike, inv)
    return v388, grid, gn, mkt, gh, pxmap, strike, positions


def g2_paths(v388, grid):
    runs = pickle.loads(V421.read_bytes())
    Es, Ms = [], []
    for s in range(4):
        e1, m1 = v388.hourly(runs[s][STRAT], GRID0, v388.Y1 + pd.Timedelta(hours=12))
        assert (e1.index == grid).all()
        Es.append(e1.to_numpy(dtype=float))
        Ms.append(m1.to_numpy(dtype=float))
    return np.stack(Es), np.stack(Ms)


def main():
    stage = sys.argv[1] if len(sys.argv) > 1 else "inventory"
    (HERE / "tmp").mkdir(exist_ok=True)
    if stage == "inventory":
        inventory()
        return
    if stage == "dev":
        v388, grid, gn, mkt, gh, pxmap, strike, positions = build_all()
        dev_idx = year_slices(grid)[:4]
        results: dict = {"variant": "STRIKE-V2", "years": {}, "meta": {
            "grid": [str(grid[0]), str(grid[-1])], "strat": STRAT,
            "note": ("V2-unhedged, traded-IV pricing; entry Fri 11:00 "
                      "(S=10:59 1m close); first exit check 12:00 Fri; "
                      "marks close-marked (DD lower bound); PARTIAL years use "
                      "tradeable coin-weeks only (entry+expiry months complete)")}}
        all_trades = []
        for ay, idx in dev_idx:
            out = simulate_year(grid, idx, positions, standalone=True, pxmap=pxmap, tag="dev")
            results["years"][ay] = {
                "R": out["R"], "DD": out["DD"], "end": out["end"], "trades": out["n"],
                "win": out["win"], "tp": out["tp"], "sl": out["sl"], "expiry": out["expiry"],
                "worst_week": out["worst_week"], "gap": out["gap"], "iv_mean": out["iv_mean"],
                "diag": diagnostics_for_year(out), "n_skip": out["n_skip"], "PARTIAL": True}
            all_trades.extend([{**t, "anchor": ay} for t in out["trades"]])
            print("standalone", ay, results["years"][ay])
        Rs = [results["years"][ay]["R"] for ay, _ in dev_idx]
        R4 = float(np.prod([1 + r / 100 for r in Rs]) ** (1 / 4) - 1) * 100
        results["dev4_mean"] = round(R4, 3)
        results["dev4_worst"] = min(Rs)
        results["dev4_DD"] = max(results["years"][ay]["DD"] for ay, _ in dev_idx)
        results["dev4_losing"] = sum(r < 0 for r in Rs)
        if all_trades:
            pd.DataFrame(all_trades).to_parquet(HERE / "trades_strike_dev4.parquet")
        (HERE / "tmp" / "dev.json").write_text(json.dumps(results, indent=1, default=str))
        print("dev done ->", HERE / "tmp/dev.json", results["dev4_mean"], results["dev4_worst"])
        return
    if stage == "final":
        v388, grid, gn, mkt, gh, pxmap, strike, positions = build_all()
        sys.path.insert(0, str(ROOT / "research/diagnostics/r2_decompose5"))
        from reset_metric import year_reset
        exp = json.loads(V421_RES.read_text())["rows"][STRAT]
        got_years = [year_reset(pickle.loads(V421.read_bytes()), STRAT, y) for y in range(5)]
        assert [r["R"] for r in got_years] == [rr for rr, _ in exp["years"]], got_years
        assert [r["DD"] for r in got_years] == [dd for _, dd in exp["years"]], got_years
        print("G2 baseline validation OK (v421_result yearly R/DD reproduce)")
        Es, Ms = g2_paths(v388, grid)
        all_idx = year_slices(grid)
        out: dict = {"variant": "STRIKE-V2", "standalone": {}, "overlay": {},
                     "corr": {}, "full": {}, "meta": {
                         "grid": [str(grid[0]), str(grid[-1])], "strat": STRAT,
                         "rule": ("short ATM straddle Fri 11:00, K nearest traded "
                                  "strike to 08:00 index, sell (iv-h) BTC h=0.5 "
                                  "ETH h=1.0, SL -1x hourly ask, TP 0.3x 4h mid, "
                                  "settle mean 07:30..07:59; Deribit-style fees; "
                                  "q=0.5fE/S; no hedge; fallback r x DVOL"),
                         "overlay": "UTA A(t)=A(t-1)(1+r_bot)+dSleeve, f=0.25",
                         "partial": ("PARTIAL years: tradeable coin-weeks only "
                                     "(entry+expiry months complete)")}}
        for ay, idx in all_idx:
            r = simulate_year(grid, idx, positions, standalone=True, pxmap=pxmap, tag="sa")
            out["standalone"][ay] = {
                "R": r["R"], "DD": r["DD"], "end": r["end"], "trades": r["n"],
                "win": r["win"], "tp": r["tp"], "sl": r["sl"], "expiry": r["expiry"],
                "worst_week": r["worst_week"], "gap": r["gap"], "iv_mean": r["iv_mean"],
                "diag": diagnostics_for_year(r), "n_skip": r["n_skip"], "PARTIAL": True}
            print("standalone", ay, out["standalone"][ay])
        recent_trades = simulate_year(grid, all_idx[4][1], positions,
                                      standalone=True, pxmap=pxmap, tag="rec")["trades"]
        if recent_trades:
            pd.DataFrame([{**t, "anchor": all_idx[4][0]} for t in recent_trades]).to_parquet(
                HERE / "trades_strike_recent.parquet")
        ov = {}
        for f in [0.0, F_OVERLAY]:
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
                else:
                    es_prev = np.concatenate([[1.0], es[:-1]])
                    g = es / es_prev
                    hh = ms / es_prev
                    r = simulate_year(grid, idx, positions, g=g, hh=hh, f=f,
                                      standalone=False, pxmap=pxmap, tag=f"ov{f}")
                    A_arr, M_arr = r["E"], r["M"]
                pk = np.maximum.accumulate(A_arr)
                R = round(100 * float(A_arr[-1] ** (1 / 12) - 1), 3)
                DD = round(100 * float(np.max(1 - M_arr / pk)), 2)
                years.append({"anchor": ay, "R": R, "DD": DD,
                              "end": round(float(A_arr[-1]), 6), "PARTIAL": True})
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
        mask = grid > pd.Timestamp("2021-09-24", tz="UTC")
        fidx = np.where(mask)[0]
        for key, f in (("sleeve_only", 1.0), ("G2_f0.25", F_OVERLAY)):
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
        dall, gall = [], []
        for y, (ay, idx) in enumerate(all_idx):
            le = gn <= ANCH[y].value
            b = np.array([float(Es[s][le][-1]) if le.any() else 1.0 for s in range(4)])
            es = np.mean([Es[s][idx] / b[s] for s in range(4)], axis=0)
            ms = np.mean([Ms[s][idx] / b[s] for s in range(4)], axis=0)
            es_prev = np.concatenate([[1.0], es[:-1]])
            r = simulate_year(grid, idx, positions, g=es / es_prev, hh=ms / es_prev,
                              f=F_OVERLAY, standalone=False, pxmap=pxmap, tag="corr")
            df = pd.DataFrame({"d": grid[idx].date, "sleeve": r["dU"], "g2": r["g2"]})
            dall.append(df)
        dall = pd.concat(dall).groupby("d")[["sleeve", "g2"]].sum()
        c_all = float(dall["sleeve"].corr(dall["g2"])) if len(dall) > 2 else float("nan")
        worst20 = set(dall.nsmallest(20, "g2").index)
        sub = dall.loc[dall.index.isin(worst20)]
        c_w = float(sub["sleeve"].corr(sub["g2"])) if len(sub) > 2 else float("nan")
        out["corr"] = {"daily_corr_all": round(c_all, 3),
                       "daily_corr_g2worst20": round(c_w, 3)}
        print("corr:", out["corr"])
        dev = json.loads((HERE / "tmp" / "dev.json").read_text())
        out["dev4"] = {k: dev[k] for k in ("dev4_mean", "dev4_worst", "dev4_DD", "dev4_losing")}
        (HERE / "tmp" / "final.json").write_text(json.dumps(out, indent=1, default=str))
        (HERE / "results.json").write_text(json.dumps(out, indent=1, default=str))
        print("final done ->", HERE / "tmp/final.json", " + results.json")
        return
    raise SystemExit(f"unknown stage {stage}")


if __name__ == "__main__":
    main()