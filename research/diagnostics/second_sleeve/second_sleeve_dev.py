"""Study B: a second, independent dip stream with a learned filter (dev years only).

Dev window ONLY: 2021-09-24 .. 2025-09-24 (exclusive of the end).
Training-only: 2020-08-01 .. 2021-09-24. Never loads or computes on >= 2025-09-24
(END is set to 2025-09-24 00:00 UTC and every load is sliced before any use).

Structure (fixed before running, executable under the user trade rules):
  periods P in (720, 1440) min, aligned at 00:00/12:00 UTC (START is midnight).
  sigma_P = std of last 30 CLOSED period close-to-close log returns (min 20, shift 1).
  resting limit bids at L = O * exp(-k sigma_P), k in (2.5,3,3.5,4), O = minute-0 open,
  placed at minute 5, valid until minute P-16, fill only on 1m trade-through (low < L),
  maker 0.0002.
  stop: bot closes when a clock 5-min block closes <= L*exp(-4 sigma) -> market exit
    at the next minute open (taker 0.00055), plus native touch stop at L*exp(-8 sigma)
    (gap fills at that minute open, fill minute checked, stop-first).
  take-profit limit at L*exp(+1 sigma) (maker, never in the fill minute).
  otherwise exit at the next period open (taker). Funding 0.0001 per 00/08/16 UTC
  settlement held (exit at the settlement minute pays). Stop-first when one minute
  touches both stop and take-profit (backstop checked before TP; a close-stop signal
  in the same minute suppresses the TP, i.e. the stop wins).
  E1: pooled rung table (all 35 coins), features = seven v293 state features with the
    period's own windows + hour (see FEATURES below), label = net return per notional.
    Walk-forward HGB (depth 3, lr 0.05, 200 iter, min leaf 200), cross-fitted even/odd
    periods. Fits for anchor Y use only fills with t_exit < Y - 7 days.
  E2: policy per P: x1.5 if both halves predict > 2*mu, x0 if both < -mu (skip),
    else x0.5 if both < 0, else x1 (skip checked first; mu = train-label mean for Y).
    Majors-only sub-account risking 1% per rung at the 4-sigma stop
    (notional = mult * 0.01 * E / (4*sigma)), baseline (mult=1) vs policy.
  E3: daily-PnL correlation of the policy sub-account with the 4h G2 pipeline
    (v301 build_hooks, budget 0.26), plus blend (1-x) G2 + x sub-account monthly
    rebalanced for x in (0.15,0.25,0.35), dev-only (indicative).

FEATURES (all known strictly before the fill minute f; kk = f-1 global minute):
  x0 sp30  = log(C[kk]/C[kk-30]) / (sig1[kk]*sqrt(30)), sig1 = std of 1m log returns
            over the previous 1440 minutes ending at kk (NaN when short/degenerate).
  x1 rung depth k.
  x2 volreg = sigma_P[p] / trailing 540-period median (min 180).
  x3 trend  = (log(open_p)-log(open_{p-42})) / (sigma_P[p]*sqrt(42)).
  x4 btc_sp30 at the same minute kk (same formula on BTC).
  x5 dd = log(C[kk]/hmax[kk]) / sigma_P[p], hmax = max high over previous 1440 min.
  x6 hour of the fill (0-23 UTC).
HGB handles NaNs natively. No post-hoc changes (any change would be logged here).
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

HERE = Path(__file__).parent
RD = Path("research/parallel/rounds/parallel-20260906-r2")
D_MAJ = Path("data/raw/majors_intraday_20260924")
D_BTC = Path("data/raw/btc_intraday_20260924")
D_ALTS = (Path("data/raw/alts_intraday_20260926"), Path("data/raw/alts2020_intraday_20260930"))

START = pd.Timestamp("2020-08-01", tz="UTC")
END = pd.Timestamp("2025-09-24", tz="UTC")  # exclusive; never touch >= this
ANCHORS = [pd.Timestamp(a, tz="UTC") for a in ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24")]
EMBARGO = pd.Timedelta(days=7)
MAJORS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
PS = (720, 1440)
KS = (2.5, 3.0, 3.5, 4.0)
WIN0 = 5
M_STOP, BACKSTOP, M_TP = 4.0, 8.0, 1.0
MAKER, TAKER, FUND = 0.0002, 0.00055, 0.0001
R_RISK, RISK_AT = 0.01, 4.0


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def universe_35():
    v294 = _load("v294_u", RD / "v294/v294_wide_pool_exit_agent.py")
    U = tuple(v294.universe())
    return MAJORS + U, list(U)


def load_1m_arrays(sym, grid):
    if sym == "BTCUSDT":
        pat = "klines_1m_*.parquet"
        files = sorted(D_BTC.glob(pat))
    elif sym in MAJORS:
        files = sorted(D_MAJ.glob(f"{sym}_1m_*.parquet"))
    else:
        files = sorted(f for d in D_ALTS for f in d.glob(f"{sym}_1m_*.parquet"))
    parts = []
    for f in files:
        try:
            y = int(f.stem.split("_")[-1])
        except Exception:
            continue
        if y < 2020 or y > 2025:
            continue
        parts.append(pd.read_parquet(f, columns=["open_time", "open", "high", "low", "close"]))
    if not parts:
        return None
    m = pd.concat(parts)
    m["open_time"] = pd.to_datetime(m["open_time"], utc=True)
    m = m.drop_duplicates("open_time")
    m = m[(m.open_time >= START) & (m.open_time < END)].set_index("open_time").sort_index()
    m = m.reindex(grid)
    m["close"] = m["close"].ffill()
    for c in ("open", "high", "low"):
        m[c] = m[c].fillna(m["close"])
    if m["close"].isna().all():
        return None
    return {k: m[k].to_numpy(float) for k in ("open", "high", "low", "close")}


def period_stats(O, C, P):
    nm = len(O)
    npd = nm // P
    assert nm % P == 0
    po = O[0: npd * P: P].copy()
    pc = C[P - 1: npd * P: P].copy()
    with np.errstate(divide="ignore", invalid="ignore"):
        r = np.log(pc[1:] / pc[:-1])
    r = np.concatenate([[np.nan], r])
    sig = pd.Series(r).rolling(30, min_periods=20).std().shift(1).to_numpy()
    volreg = (pd.Series(sig) / pd.Series(sig).rolling(540, min_periods=180).median()).to_numpy()
    with np.errstate(divide="ignore", invalid="ignore"):
        trend = (np.log(pd.Series(po)) - np.log(pd.Series(po).shift(42))).to_numpy() / (sig * np.sqrt(42))
    return po, pc, sig, volreg, trend, npd


def sp30_at(C, kk):
    if kk < 1440 or kk < 30:
        return np.nan
    w = C[kk - 1439: kk + 1]
    if not np.all(np.isfinite(w)):
        return np.nan
    with np.errstate(divide="ignore", invalid="ignore"):
        lr = np.log(w[1:] / w[:-1])
    s = float(np.std(lr, ddof=1)) if np.all(np.isfinite(lr)) else np.nan
    if not (s > 0):
        return np.nan
    return float(np.log(C[kk] / C[kk - 30]) / (s * np.sqrt(30)))


def hmax_at(H, kk):
    if kk < 1440:
        return np.nan
    w = H[kk - 1439: kk + 1]
    if not np.all(np.isfinite(w)):
        return np.nan
    return float(w.max())


def exit_rung(O, H, L, C, s0, f, P, lim, sg, fund_cum, block_end, nm):
    stop = lim * np.exp(-M_STOP * sg)
    bstop = lim * np.exp(-BACKSTOP * sg)
    tp = lim * np.exp(M_TP * sg)
    fg = s0 + f
    end = s0 + P
    n = P - f
    Og, Hg, Lg, Cg = O[fg: end], H[fg: end], L[fg: end], C[fg: end]
    be = block_end[fg: end]
    jb = jtp = jsg = None
    for j in range(n):
        if j > 0 and Og[j] <= bstop:
            if jb is None:
                jb = j
                break  # gap stop is immediate; lowest possible for backstop search
        if Lg[j] <= bstop:
            if jb is None:
                jb = j
            break
    # TP search (j > 0 only)
    hit_tp = np.flatnonzero(Hg[1:] > tp)
    if len(hit_tp):
        jtp = int(hit_tp[0]) + 1
    # close-stop signal search
    sig = np.flatnonzero(be & (Cg <= stop))
    if len(sig):
        jsg = int(sig[0])
    # decide with stop-first: backstop > close-stop > TP on ties
    if jb is not None:
        # does a close-stop exit strictly before the backstop minute?
        if jsg is not None and jsg + 1 < jb and (jtp is None or jsg <= jtp):
            ex = fg + jsg + 1
            return min(ex, end), (O[min(ex, nm - 1)] if min(ex, nm - 1) < nm else C[nm - 1]), "stop"
        if jtp is not None and jtp < jb and (jsg is None or jtp < jsg):
            return fg + jtp, tp, "tp"
        px = Og[jb] if (jb > 0 and Og[jb] <= bstop) else bstop
        return fg + jb, float(px), "stop"
    if jsg is not None and (jtp is None or jsg <= jtp):
        ex = fg + jsg + 1
        ex = min(ex, end)
        px = O[min(ex, nm - 1)] if ex < nm else C[nm - 1]
        return ex, float(px), "stop"
    if jtp is not None:
        return fg + jtp, float(tp), "tp"
    px = O[end] if end < nm else C[nm - 1]
    return end, float(px), "time"


def build_rungs(sym, arr, btcC, grid, P, fund_cum, block_end):
    O, H, L, C = arr["open"], arr["high"], arr["low"], arr["close"]
    nm = len(grid)
    po, pc, sig, volreg, trend, npd = period_stats(O, C, P)
    win1 = P - 16
    rows = []
    for p in range(npd):
        sg = sig[p]
        o0 = po[p]
        if not (np.isfinite(sg) and sg > 0 and np.isfinite(o0)):
            continue
        s0 = p * P
        t0 = grid[s0]
        if t0 >= END:
            continue
        Lw = L[s0 + WIN0: s0 + win1]
        if not np.all(np.isfinite(Lw)):
            continue
        for k in KS:
            lim = o0 * np.exp(-k * sg)
            hit = np.flatnonzero(Lw < lim)
            if not len(hit):
                continue
            f = WIN0 + int(hit[0])
            fg = s0 + f
            ex, px, kind = exit_rung(O, H, L, C, s0, f, P, lim, sg, fund_cum, block_end, nm)
            q_rel = px / lim
            fee_exit = MAKER if kind == "tp" else TAKER
            nf = int(fund_cum[min(ex, nm - 1)] - fund_cum[fg])
            ret = q_rel - 1 - MAKER - q_rel * fee_exit - FUND * nf
            t_fill = grid[fg]
            t_exit = grid[min(ex, nm - 1)] if ex < nm else grid[nm - 1]
            kk = fg - 1
            x0 = sp30_at(C, kk)
            x4 = sp30_at(btcC, kk)
            hm = hmax_at(H, kk)
            x5 = float(np.log(C[kk] / hm) / sg) if (np.isfinite(hm) and hm > 0 and np.isfinite(C[kk])) else np.nan
            rows.append(dict(sym=sym, p=p, t_fill=t_fill, t_exit=t_exit, k=k, f=f, fg=fg,
                             ex=int(min(ex, nm)), lim=float(lim), sg=float(sg), ret=float(ret),
                             kind=kind, t0=t0,
                             x0=x0, x1=float(k), x2=float(volreg[p]), x3=float(trend[p]),
                             x4=x4, x5=x5, x6=float(t_fill.hour)))
    return pd.DataFrame(rows)


def hgb():
    return HistGradientBoostingRegressor(max_depth=3, learning_rate=0.05, max_iter=200,
                                        min_samples_leaf=200)


def year_masks(t_fill):
    t = pd.to_datetime(t_fill, utc=True)
    out = {}
    for i, a0 in enumerate(ANCHORS):
        a1 = a0 + pd.Timedelta(days=365)
        out[str(a0.year)] = np.asarray((t >= a0) & (t < a1))
    out["dev"] = np.asarray((t >= ANCHORS[0]) & (t < ANCHORS[0] + pd.Timedelta(days=4 * 365 + 1)))
    # exact dev: t < 2025-09-24
    out["dev"] = np.asarray((t >= ANCHORS[0]) & (t < END))
    return out


def simulate_subaccount(rungs, Ldict, Cdict, grid, P, mult_key):
    nm = len(grid)
    realized = np.zeros(nm + 1)
    u_low = np.zeros(nm)
    u_close = np.zeros(nm)
    notional = np.zeros(nm)
    by_p = {}
    for r in rungs.itertuples():
        by_p.setdefault(r.p, []).append(r)
    npd = nm // P
    cash = 1.0
    trades = []
    skipped = 0
    liquidated = None
    for p in range(npd):
        s0 = p * P
        if p > 0:
            cash += realized[s0 - P + 1: s0 + 1].sum()
        if cash <= 0 or liquidated is not None:
            break
        E = cash
        for r in by_p.get(p, []):
            mult = float(getattr(r, mult_key))
            if not (mult > 0):
                skipped += 1
                continue
            N = mult * R_RISK * E / (RISK_AT * r.sg)
            pnl = N * r.ret
            realized[min(r.ex, nm)] += pnl
            seg = slice(r.fg, min(r.ex, nm))
            Ls = Ldict[r.sym][seg]
            Cs = Cdict[r.sym][seg]
            with np.errstate(divide="ignore", invalid="ignore"):
                u_low[seg] += N * (Ls / r.lim - 1) - N * MAKER
                u_close[seg] += N * (Cs / r.lim - 1) - N * MAKER
            notional[seg] += N
            trades.append(dict(t=r.t_fill, sym=r.sym, k=r.k, kind=r.kind, ret=r.ret,
                               mult=mult, pnl_frac=pnl / E))
        seg = slice(s0, min(s0 + P, nm))
        run_cash = cash + np.concatenate([[0.0], np.cumsum(realized[s0 + 1: min(s0 + P, nm)])])
        eq_low = run_cash + u_low[seg]
        bad = np.flatnonzero(eq_low <= 0.01 * notional[seg])
        if len(bad) and notional[seg][bad[0]] > 0:
            liquidated = str(grid[s0 + int(bad[0])])
            break
    cash_path = 1.0 + np.cumsum(realized[:nm])
    return dict(cash=cash_path, u_low=u_low, u_close=u_close, notional=notional,
                trades=pd.DataFrame(trades), skipped=int(skipped), liquidated=liquidated)


def yearly_stats(eq_close, eq_low, grid):
    years = []
    for a0 in ANCHORS:
        a1 = a0 + pd.Timedelta(days=365)
        mk = np.asarray((grid >= a0) & (grid < a1))
        if not mk.any():
            years.append(dict(anchor=str(a0.date()), net_pct=0.0, dd_1m_pct=0.0))
            continue
        idx = np.flatnonzero(mk)
        base = eq_close[idx[0] - 1] if idx[0] > 0 else 1.0
        e = eq_close[idx] / base
        em = eq_low[idx] / base
        net = float(e[-1] - 1)
        peak = np.maximum.accumulate(np.concatenate([[1.0], e]))[1:]
        dd = float(np.max(1 - np.minimum(e, em) / peak)) if len(e) else 0.0
        years.append(dict(anchor=str(a0.date()), net_pct=round(100 * net, 2),
                          dd_1m_pct=round(100 * dd, 2)))
    e, em = eq_close / eq_close[0], eq_low / eq_close[0]
    peak = np.maximum.accumulate(np.concatenate([[1.0], e]))[1:]
    dd_full = float(np.max(1 - np.minimum(e, em) / peak))
    geo = float(np.prod([1 + y["net_pct"] / 100 for y in years]) ** (1 / 4) - 1)
    dev4 = float((1 + geo) ** (1 / 12) - 1)
    return years, round(100 * dev4, 3), round(100 * dd_full, 2)


def main():
    names, U = universe_35()
    print("universe", len(names), "majors", MAJORS, "alts", len(U), flush=True)
    grid = pd.date_range(START, END - pd.Timedelta(minutes=1), freq="1min")
    nm = len(grid)
    hours = grid.hour.to_numpy()
    mins = grid.minute.to_numpy()
    fund_cum = np.cumsum((mins == 0) & np.isin(hours, (0, 8, 16))).astype(int)
    block_end = ((mins % 5) == 4)
    out = {"version": "second_sleeve", "dev_window": ["2021-09-24", "2025-09-24"],
           "embargo": "7d", "periods": {}, "post_hoc_changes": [],
           "leakage_checks": [
               "END=2025-09-24 exclusive; every 1m load sliced to < END before use",
               "sigma_P uses only closed periods (rolling std shift 1, min 20)",
               "features at minute f-1 only; fills from minute 5 on trade-through",
               "fits per anchor use only fills with t_exit < anchor - 7 days",
               "no statistic computed on >= 2025-09-24 (asserted max t_exit < END)",
           ]}
    maj_rungs = {}
    for P in PS:
        print(f"== P={P} building rungs ==", flush=True)
        btc_arr = load_1m_arrays("BTCUSDT", grid)
        assert btc_arr is not None
        btcC = btc_arr["close"]
        pooled = []
        maj_list = []
        keepLC = {}
        for sym in names:
            arr = btc_arr if sym == "BTCUSDT" else load_1m_arrays(sym, grid)
            if arr is None:
                print("missing", sym, flush=True)
                continue
            d = build_rungs(sym, arr, btcC, grid, P, fund_cum, block_end)
            if len(d):
                pooled.append(d)
                if sym in MAJORS:
                    maj_list.append(d)
            if sym in MAJORS and sym != "BTCUSDT":
                keepLC[sym] = (arr["low"], arr["close"])
            del arr
        keepLC["BTCUSDT"] = (btc_arr["low"], btc_arr["close"])
        del btc_arr
        allf = pd.concat(pooled, ignore_index=True)
        maj = pd.concat(maj_list, ignore_index=True) if maj_list else pd.DataFrame()
        assert allf["t_exit"].max() < END and maj["t_fill"].max() < END
        X = allf[[f"x{q}" for q in range(7)]].to_numpy(float)
        y = allf["ret"].to_numpy(float)
        half = (allf["p"].to_numpy() % 2)
        t_exit = pd.to_datetime(allf["t_exit"], utc=True)
        models, mus, ntrain = {}, {}, {}
        for jj, a0 in enumerate(ANCHORS):
            keep = (t_exit < (a0 - EMBARGO)).to_numpy()
            mus[str(a0.date())] = float(y[keep].mean()) if keep.sum() else float("nan")
            ntrain[str(a0.date())] = int(keep.sum())
            pair = []
            for h in (0, 1):
                sel = keep & (half == h)
                pair.append(hgb().fit(X[sel], y[sel]))
            models[jj] = pair
        # predict majors rungs
        maj = maj.copy()
        maj["anchor_jj"] = maj["t_fill"].apply(
            lambda t: max([q for q, a0 in enumerate(ANCHORS) if t >= a0], default=-1))
        pas, pbs, mults = [], [], []
        for r in maj.itertuples():
            jj = int(r.anchor_jj)
            if jj < 0:
                pas.append(np.nan)
                pbs.append(np.nan)
                mults.append(1.0)
                continue
            x = np.array([[r.x0, r.x1, r.x2, r.x3, r.x4, r.x5, r.x6]], float)
            pa = float(models[jj][0].predict(x)[0])
            pb = float(models[jj][1].predict(x)[0])
            mu = mus[str(ANCHORS[jj].date())]
            pas.append(pa)
            pbs.append(pb)
            if pa < -mu and pb < -mu:
                mults.append(0.0)
            elif pa > 2 * mu and pb > 2 * mu:
                mults.append(1.5)
            elif pa < 0 and pb < 0:
                mults.append(0.5)
            else:
                mults.append(1.0)
        maj["pa"] = pas
        maj["pb"] = pbs
        maj["mult"] = mults
        maj["mult_base"] = 1.0
        Ldict = {s: keepLC[s][0] for s in keepLC}
        Cdict = {s: keepLC[s][1] for s in keepLC}
        dev = maj[(maj.t_fill >= ANCHORS[0]) & (maj.t_fill < END)]
        per_year_base, per_year_pol = {}, {}
        for yy in [str(a.year) for a in ANCHORS]:
            a0 = pd.Timestamp(yy + "-09-24", tz="UTC")
            # dev-year slice by fill time
            g = dev[(dev.t_fill >= a0) & (dev.t_fill < a0 + pd.Timedelta(days=365))]
            gb = g  # baseline uses all filled
            gp = g[g.mult > 0]  # policy filled (non-skipped)
            def sstats(gg):
                r = gg["ret"].to_numpy(float) if len(gg) else np.array([])
                return dict(n=int(len(gg)),
                            win_rate=round(float((r > 0).mean()), 3) if len(r) else None,
                            mean_net_bps=round(10000 * float(r.mean()), 1) if len(r) else None,
                            stopped=int((gg.kind == "stop").sum()),
                            timeouts=int((gg.kind == "time").sum()))
            per_year_base[yy] = sstats(gb)
            per_year_pol[yy] = sstats(gp)
        acc_b = simulate_subaccount(dev, Ldict, Cdict, grid, P, "mult_base")
        acc_p = simulate_subaccount(dev, Ldict, Cdict, grid, P, "mult")
        for acc in (acc_b, acc_p):
            eqc = acc["cash"] + acc["u_close"]
            eql = acc["cash"] + acc["u_low"]
            devmk = np.asarray((grid >= ANCHORS[0]) & (grid < END))
            acc["years"], acc["dev4"], acc["dd_full"] = yearly_stats(eqc[devmk], eql[devmk], grid[devmk])
        # skipped share over dev
        skipped_share = float((maj[(maj.t_fill >= ANCHORS[0]) & (maj.t_fill < END)].mult == 0).mean())
        res = {"P": P, "pooled_rungs": int(len(allf)),
               "pooled_by_sym": {s: int((allf.sym == s).sum()) for s in names if (allf.sym == s).any()},
               "train_rows": ntrain, "mu": mus,
               "majors_dev_rungs": int(len(dev)),
               "skipped_share": round(skipped_share, 4),
               "stopped_dev": int((dev.mult > 0).sum() and (dev[dev.mult > 0].kind == "stop").sum()),
               "per_year_baseline": per_year_base, "per_year_policy": per_year_pol,
               "baseline": {"years": acc_b["years"], "dev4_monthly_pct": acc_b["dev4"],
                            "dd_1m_full_pct": acc_b["dd_full"], "liquidated": acc_b["liquidated"],
                            "skipped": acc_b["skipped"]},
               "policy": {"years": acc_p["years"], "dev4_monthly_pct": acc_p["dev4"],
                          "dd_1m_full_pct": acc_p["dd_full"], "liquidated": acc_p["liquidated"],
                          "skipped": acc_p["skipped"]}}
        out["periods"][str(P)] = res
        maj_rungs[P] = (maj, Ldict, Cdict)
        print(P, "pooled", len(allf), "majdev", len(dev), "skip", skipped_share,
              "base", acc_b["dev4"], acc_b["dd_full"], "pol", acc_p["dev4"], acc_p["dd_full"], flush=True)
    # E3: G2 reproduction dev-only
    print("== E3 G2 ==", flush=True)
    v293 = _load("v293_e3", RD / "v293/v293_pooled_exit_agent.py")
    v293.END = END
    v301 = _load("v301_e3", RD / "v301/v301_return_first_budget.py")
    v221 = _load("v221_e3", RD / "v221/v221_grid_hysteresis.py")
    v216, eu = v221.v216, v221.eu
    books154, opens = eu.er.v154_books()
    cols, idx = list(books154.columns), books154.index
    C = eu.er.CACHE
    m = {k: pd.read_parquet(C / f).reindex(idx).fillna(0.0)[cols] for k, f in (
        ("A", "member_A_O1_orders.parquet"), ("Aq", "member_Aq_O1_orders.parquet"),
        ("B", "member_B_tv.parquet"), ("Bq", "member_Bq_tv.parquet"))}
    m["D"] = pd.read_parquet(C / "members_v154.parquet").xs("D", axis=1, level=0).reindex(idx).fillna(0.0)[cols]
    m["Dq"] = pd.read_parquet(C / "members_quarterly_D.parquet").reindex(idx).fillna(0.0)[cols]
    cb = 0.8 * (0.5 * (m["A"] + m["B"]) / 2 + 0.5 * (m["Aq"] + m["Bq"]) / 2) + 0.2 * (m["D"] + m["Dq"]) / 2
    prep = eu.prepare(books154, opens)
    trade = dict(v216.GRID, policy=v216.grid_policy(v221.B_ABS, v221.B_REL))
    size_s1, size_s5, tp = v301.build_hooks(eu, idx, cols)
    ev = []
    path = {}
    kw = dict(v221.KW, **dict(v293.C4R, sleeve_risk_budget=0.26))
    r = eu.simulate(cb, opens, prep, trade=trade, win_start=5, events=ev, path_out=path,
                    sleeve_fill_size=size_s1, sleeve_tp=tp, **kw)
    t = pd.DatetimeIndex(path["t"])
    devmk = (t >= ANCHORS[0]) & (t < END)
    assert t[devmk].max() < END
    eq, emin = np.asarray(path["eq"], float)[devmk], np.asarray(path["eq_min"], float)[devmk]
    td = t[devmk]
    # dev4 / DD from dev slice only (no hidden statistic)
    eyears = []
    for a0 in ANCHORS:
        a1 = a0 + pd.Timedelta(days=365)
        mk = np.asarray((td >= a0) & (td < a1))
        base = eq[np.flatnonzero(mk)[0] - 1] if np.flatnonzero(mk)[0] > 0 else 1.0
        e, em = eq[mk] / base, emin[mk] / base
        eyears.append(dict(anchor=str(a0.date()), net_pct=round(100 * float(e[-1] - 1), 2),
                           dd_1m_pct=round(100 * float(np.max(1 - np.minimum(e, em) / np.maximum.accumulate(np.concatenate([[1.0], np.maximum(e, em)]))[1:])), 2)))
    geo = float(np.prod([1 + y["net_pct"] / 100 for y in eyears]) ** (1 / 4) - 1)
    g2dev4 = round(100 * float((1 + geo) ** (1 / 12) - 1), 3)
    g2dd = round(float(max(y["dd_1m_pct"] for y in eyears)), 2)
    out["g2"] = {"dev_years": eyears, "dev4_monthly_pct": g2dev4, "dev_dd_max_yearly": g2dd,
                 "ref_expect": "monthly_dev4 6.527 and dev DD 17.33"}
    print("G2 dev4", g2dev4, "devDD", g2dd, eyears, flush=True)
    # daily correlation + blends per P (dev only)
    e3 = {}
    # G2 daily returns from dev 4h equity (last bar per day)
    g2s = pd.Series(eq, index=td)
    g2d_eq = g2s.resample("1D").last().ffill()
    g2d_eq = g2d_eq[(g2d_eq.index >= ANCHORS[0]) & (g2d_eq.index < END)]
    g2d = g2d_eq.pct_change().fillna(0.0)
    for P in PS:
        maj, Ldict, Cdict = maj_rungs[P]
        # rebuild policy sub-account daily equity on dev grid (reuse simulation arrays)
        # re-simulate to get arrays on full grid then slice to dev daily closes
        dev = maj[(maj.t_fill >= ANCHORS[0]) & (maj.t_fill < END)]
        acc = simulate_subaccount(dev, Ldict, Cdict, grid, P, "mult")
        eqc = acc["cash"] + acc["u_close"]
        eql = acc["cash"] + acc["u_low"]
        s = pd.Series(eqc, index=grid)
        smin = pd.Series(np.minimum(eqc, eql), index=grid)
        sd_eq = s.resample("1D").last().ffill()
        sd_eq = sd_eq[(sd_eq.index >= ANCHORS[0]) & (sd_eq.index < END)]
        sd_min = smin.resample("1D").last().ffill()
        sd_min = sd_min[(sd_min.index >= ANCHORS[0]) & (sd_min.index < END)]
        common = g2d.index.intersection(sd_eq.index)
        subd = sd_eq.pct_change().fillna(0.0).reindex(common).fillna(0.0)
        g2c = g2d.reindex(common).fillna(0.0)
        corr = round(float(np.corrcoef(subd.to_numpy(), g2c.to_numpy())[0, 1]), 3) if len(common) > 2 else None
        # blends with monthly rebalancing on 4h bars (indicative)
        # map sub-account minute equity to G2 4h bars
        pos = grid.get_indexer(td)
        eq_s = np.full(len(td), np.nan)
        min_s = np.full(len(td), np.nan)
        for i, a in enumerate(pos):
            if a < 0 or a + 240 > len(grid):
                continue
            eq_s[i] = eqc[a + 239]
            min_s[i] = min(eql[a: a + 240].min(), eqc[a: a + 240].min())
        eq_s = pd.Series(eq_s, td).ffill().fillna(1.0).to_numpy()
        min_s = pd.Series(min_s, td).ffill().fillna(1.0).to_numpy()
        blends = {}
        for x in (0.15, 0.25, 0.35):
            n = len(td)
            beq, bemin = np.ones(n), np.ones(n)
            month = pd.DatetimeIndex(td).to_period("M")
            V = 1.0
            a = b = 0.0
            for i in range(n):
                if i == 0 or month[i] != month[i - 1]:
                    V = beq[i - 1] if i > 0 else 1.0
                    ref_cb = eq[i - 1] if i > 0 else eq[0]
                    ref_s = eq_s[i - 1] if i > 0 else eq_s[0]
                    a, b = (1 - x) * V / ref_cb, x * V / ref_s
                beq[i] = a * eq[i] + b * eq_s[i]
                bemin[i] = a * emin[i] + b * min_s[i]
            by = []
            for a0 in ANCHORS:
                a1 = a0 + pd.Timedelta(days=365)
                mk = np.asarray((td >= a0) & (td < a1))
                f0 = int(np.argmax(mk))
                base = beq[f0 - 1] if f0 > 0 else 1.0
                e_, em_ = beq[mk] / base, bemin[mk] / base
                by.append(dict(anchor=str(a0.date()), net_pct=round(100 * float(e_[-1] - 1), 2),
                               dd_1m_pct=round(100 * float(np.max(1 - np.minimum(e_, em_) / np.maximum.accumulate(np.concatenate([[1.0], np.maximum(e_, em_)]))[1:])), 2)))
            geo_b = float(np.prod([1 + y["net_pct"] / 100 for y in by]) ** (1 / 4) - 1)
            blends[str(x)] = {"years": by, "dev4_monthly_pct": round(100 * float((1 + geo_b) ** (1 / 12) - 1), 3),
                              "dev_dd_max_yearly": round(float(max(y["dd_1m_pct"] for y in by)), 2)}
        e3[str(P)] = {"daily_corr_dev": corr, "blends": blends,
                      "sub_policy_dev4": out["periods"][str(P)]["policy"]["dev4_monthly_pct"],
                      "sub_policy_dd": out["periods"][str(P)]["policy"]["dd_1m_full_pct"]}
        print(P, "corr", corr, blends, flush=True)
    out["e3"] = e3
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "second_sleeve_dev.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
