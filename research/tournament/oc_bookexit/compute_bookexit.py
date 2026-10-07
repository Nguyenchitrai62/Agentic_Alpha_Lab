"""oc_bookexit: learned exit levels for BOOK trades (idea #31, PLAN pre-registered).

Walk-forward HistGradientBoostingClassifier(max_depth=3, max_iter=200,
min_samples_leaf=200) of "episode reaches +1.5x ATR4h before -1.0x ATR4h"
from 7 entry-time features; flagged (p<0.45) episodes that touch +1.0x ATR
bank the small win at entry size, else default exits. Vectorised 4h only,
one process, no 1m data:

  python research/tournament/oc_bookexit/compute_bookexit.py
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
CACHE = ROOT / "artifacts/research/engine_real"
HEXTP = ROOT / "research/tournament/ext/hourly_ext.parquet"
SYMS = ["BNBUSDT", "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]
COIN_ID = {s: i for i, s in enumerate(SYMS)}
BOUND = pd.Timestamp("2026-09-24 00:00", tz="UTC")
ANCHORS = [pd.Timestamp(f"{y}-09-24", tz="UTC") for y in (2021, 2022, 2023, 2024, 2025)]
YEAR_LEN = pd.Timedelta(days=365)
EMBARGO = pd.Timedelta(days=7)
FLAT_TOL = 1e-12
FEE = 0.0005
ATR_N = 14
VOL_N = 360
VOL_MIN = 120
TREND_N = 180
P_THRESH = 0.45
FEATS = ["wgt", "abs_w", "vol4h", "trend30d", "btc_trend30d", "hour", "coin_id"]


def research_books_d2() -> pd.DataFrame:
    """Mirror of scripts/forward_v205.py::research_books_d2 (same files, same math)."""
    m = lambda f: pd.read_parquet(CACHE / f)[SYMS]  # noqa: E731
    A, Aq = m("member_A_O1_orders.parquet"), m("member_Aq_O1_orders.parquet")
    B, Bq = m("member_B_tv.parquet"), m("member_Bq_tv.parquet")
    idx = A.index.union(Aq.index)
    f = lambda X: X.reindex(idx).fillna(0.0)  # noqa: E731
    o1 = 0.5 * (f(A) + f(B)) / 2 + 0.5 * (f(Aq) + f(Bq)) / 2
    D = pd.read_parquet(CACHE / "members_v154.parquet").xs("D", axis=1, level=0)[SYMS]
    Dq = pd.read_parquet(CACHE / "members_quarterly_D.parquet")[SYMS]
    idx2 = o1.index.union(D.index).union(Dq.index)
    g = lambda X: X.reindex(idx2).fillna(0.0)  # noqa: E731
    return 0.8 * g(o1) + 0.2 * (g(D) + g(Dq)) / 2


def load_grid() -> tuple[pd.DataFrame, pd.DataFrame]:
    books = research_books_d2()
    opens_full = pd.read_parquet(CACHE / "opens_v154.parquet")
    grid = books.index.intersection(opens_full.dropna(how="all").index).sort_values()
    step = grid[1:] - grid[:-1]
    assert bool((step == pd.Timedelta(hours=4)).all()), "grid is not a regular 4h grid"
    w = books.reindex(grid)
    nxt = grid + pd.Timedelta(hours=4)
    scored = (grid < BOUND) & (nxt <= BOUND) & nxt.isin(opens_full.index)
    grid = grid[scored]
    assert bool((((grid[1:] - grid[:-1]) == pd.Timedelta(hours=4)).all())), "scored grid not contiguous"
    w = w.reindex(grid)
    o = opens_full.reindex(grid)
    o1 = opens_full.reindex(nxt[scored])
    o1.index = grid
    r = o1 / o - 1.0
    assert bool(r.notna().all().all()), "unexpected NaN forward return inside bound"
    return w, r[SYMS]


def load_hlc(grid: pd.DatetimeIndex) -> dict[str, pd.DataFrame]:
    """Aggregate hourly_ext majors to the 4h grid (hours T..T+3 per bar T)."""
    h = pd.read_parquet(HEXTP, filters=[("sym", "in", SYMS)])
    h["t"] = pd.to_datetime(h["t"], utc=True)
    h = h[(h["t"] >= grid[0]) & (h["t"] < BOUND)].sort_values("t")
    h["bar"] = (h["t"].astype("int64") // 14_400_000_000_000) * 14_400_000_000_000
    h["bar"] = pd.to_datetime(h["bar"], utc=True)
    out: dict[str, pd.DataFrame] = {}
    for s in SYMS:
        g = h[h["sym"] == s].groupby("bar")
        agg = pd.DataFrame({"high": g["high"].max(), "low": g["low"].min(),
                            "close": g["close"].last(), "n": g["high"].size()})
        agg = agg[agg["n"] == 4].drop(columns="n").reindex(grid)
        out[s] = agg
    return out


def atr_series(hlc: pd.DataFrame) -> pd.Series:
    hi, lo, cl = hlc["high"], hlc["low"], hlc["close"]
    prev = cl.shift(1)
    tr = pd.concat([hi - lo, (hi - prev).abs(), (lo - prev).abs()], axis=1).max(axis=1)
    return tr.rolling(ATR_N, min_periods=ATR_N).mean()


def build_episodes(w: pd.DataFrame, r: pd.DataFrame, hlc: dict[str, pd.DataFrame],
                   atr: dict[str, pd.Series], opens: pd.DataFrame) -> pd.DataFrame:
    grid = w.index
    pos = {t: i for i, t in enumerate(grid)}
    btc_o = opens["BTCUSDT"].to_numpy()
    rows: list[dict] = []
    excl = {"no_close": 0, "nan_atr_hlc": 0, "nan_feat": 0}
    for s in SYMS:
        wv = w[s].to_numpy()
        rv = r[s].to_numpy()
        hi = hlc[s]["high"].to_numpy()
        lo = hlc[s]["low"].to_numpy()
        av = atr[s].to_numpy()
        eo = opens[s].to_numpy()
        ov = opens[s].to_numpy()
        ret = rv
        vol = pd.Series(ret).rolling(VOL_N, min_periods=VOL_MIN).std().to_numpy()
        sgn = np.where(np.abs(wv) < FLAT_TOL, 0, np.sign(wv)).astype(int)
        i, n = 0, len(grid)
        while i < n:
            if sgn[i] == 0:
                i += 1
                continue
            a = i
            while i + 1 < n and sgn[i + 1] == sgn[a]:
                i += 1
            b = i
            side = sgn[a]
            if b + 1 >= n:
                excl["no_close"] += 1
                i += 1
                continue
            seg_hi, seg_lo = hi[a:b + 1], lo[a:b + 1]
            A = av[a - 1] if a - 1 >= 0 else np.nan
            if not np.isfinite(A) or A <= 0 or np.isnan(seg_hi).any() or np.isnan(seg_lo).any() \
                    or not np.isfinite(eo[a]):
                excl["nan_atr_hlc"] += 1
                i += 1
                continue
            E = float(eo[a])
            if side > 0:
                up = np.nonzero(seg_hi >= E + 1.5 * A)[0]
                dn = np.nonzero(seg_lo <= E - 1.0 * A)[0]
                tp = np.nonzero(seg_hi >= E + 1.0 * A)[0]
            else:
                up = np.nonzero(seg_lo <= E - 1.5 * A)[0]
                dn = np.nonzero(seg_hi >= E + 1.0 * A)[0]
                tp = np.nonzero(seg_lo <= E - 1.0 * A)[0]
            iu = int(up[0]) if len(up) else None
            idn = int(dn[0]) if len(dn) else None
            label = 1 if (iu is not None and (idn is None or iu < idn)) else 0
            tp_hit = bool(len(tp))
            gross = float((wv[a:b + 1] * rv[a:b + 1]).sum())
            entry = abs(float(wv[a]))
            intra = float(np.abs(np.diff(wv[a:b + 1])).sum()) if b > a else 0.0
            flatleg = abs(float(wv[b]))
            net = gross - FEE * (entry + intra + flatleg)
            if tp_hit:
                rule_net = 1.0 * (A / E) * entry - 2.0 * FEE * entry
            else:
                rule_net = net
            v = vol[a - 1] if a - 1 >= 0 else np.nan
            t30 = eo[a - 1] / eo[a - 1 - TREND_N] - 1.0 if a - 1 - TREND_N >= 0 else np.nan
            bt30 = btc_o[a - 1] / btc_o[a - 1 - TREND_N] - 1.0 if a - 1 - TREND_N >= 0 else np.nan
            if not (np.isfinite(v) and np.isfinite(t30) and np.isfinite(bt30)):
                excl["nan_feat"] += 1
                i += 1
                continue
            rows.append(dict(coin=s, coin_id=COIN_ID[s], a=int(a), b=int(b),
                             entry_t=grid[a], close_t=grid[b + 1],
                             side=int(side), wgt=float(wv[a]), abs_w=entry,
                             vol4h=float(v), trend30d=float(t30), btc_trend30d=float(bt30),
                             hour=int(grid[a].hour), atr=float(A), entry_open=E,
                             label=int(label), tp_hit=tp_hit,
                             gross=round(gross, 8), net=round(net, 8),
                             rule_net_full=round(rule_net, 8)))
            i += 1
    ep = pd.DataFrame(rows).sort_values("close_t").reset_index(drop=True)
    return ep, excl


def year_masks(entry_t: pd.Series) -> list[np.ndarray]:
    bounds = ANCHORS + [ANCHORS[-1] + YEAR_LEN]
    return [np.asarray((entry_t >= bounds[k]) & (entry_t < bounds[k + 1])) for k in range(5)]


def path_stats(ep: pd.DataFrame, key: str) -> dict:
    """Close-ordered trade-equity path, year-rebased; daily-ffill worst week."""
    if len(ep) == 0:
        return dict(n=0, pnl_sum=None, pnl_comp=None, win=None, maxdd=None, worst_week=None)
    x = ep.sort_values("close_t")[key].to_numpy(float)
    ct = pd.to_datetime(ep.sort_values("close_t")["close_t"])
    per_t = pd.Series(1.0 + x, index=ct).groupby(level=0).prod()  # simultaneous closes compound
    eq = per_t.cumprod().to_numpy()
    peak = np.maximum.accumulate(eq)
    dd = 1.0 - eq / peak
    days = pd.date_range(ep["entry_t"].min().floor("D"), ep["close_t"].max().ceil("D"), freq="D")
    df = pd.DataFrame({"eq": eq}, index=per_t.index)
    daily = df["eq"].reindex(days, method="ffill").fillna(1.0).to_numpy()
    ww = None
    if len(daily) >= 8:
        win = daily[7:] / daily[:-7] - 1.0
        ww = round(float(np.min(win)), 6)
    return dict(n=int(len(x)), pnl_sum=round(float(x.sum()), 6),
                pnl_comp=round(float(eq[-1] - 1.0), 6),
                win=round(float((x > 0).mean()), 4),
                maxdd=round(float(np.max(dd)), 6), worst_week=ww)


def main() -> None:
    w, r = load_grid()
    grid = w.index
    opens_full = pd.read_parquet(CACHE / "opens_v154.parquet").reindex(grid)
    hlc = load_hlc(grid)
    atr = {s: atr_series(hlc[s]) for s in SYMS}
    ep, excl = build_episodes(w, r, hlc, atr, opens_full)
    ep["entry_t"] = pd.to_datetime(ep["entry_t"], utc=True)
    ep["close_t"] = pd.to_datetime(ep["close_t"], utc=True)
    masks = year_masks(ep["entry_t"])
    X = ep[FEATS].to_numpy(float)
    y = ep["label"].to_numpy(int)
    years = []
    ep["p"] = np.nan
    ep["flag"] = False
    ep["rule_net"] = ep["net"]
    for k, A in enumerate(ANCHORS):
        tr = np.asarray(ep["close_t"] < A - EMBARGO)
        te = masks[k]
        if int(tr.sum()) == 0:
            # No causal training data (books start exactly at the 2021-09-24
            # anchor): no model, no flags, rule == default. Logged post-hoc.
            d = dict(year=str(A.date()), n_train=0, train_rate=None,
                     n_test=int(te.sum()),
                     test_rate=round(float(y[te].mean()), 4) if te.sum() else None,
                     flagged=0, flagged_share=0.0 if te.sum() else None, no_train_data=True)
        else:
            clf = HistGradientBoostingClassifier(max_depth=3, max_iter=200, min_samples_leaf=200)
            clf.fit(X[tr], y[tr])
            p = clf.predict_proba(X[te])[:, 1]
            ep.loc[te, "p"] = p
            flag = p < P_THRESH
            ep.loc[te, "flag"] = flag
            rn = ep.loc[te, "net"].to_numpy(float).copy()
            fidx = np.nonzero(flag)[0]
            tp = ep.loc[te, "tp_hit"].to_numpy(bool)[fidx]
            rn[fidx[tp]] = ep.loc[te, "rule_net_full"].to_numpy(float)[fidx[tp]]
            ep.loc[te, "rule_net"] = rn
            d = dict(year=str(A.date()), n_train=int(tr.sum()),
                     train_rate=round(float(y[tr].mean()), 4),
                     n_test=int(te.sum()),
                     test_rate=round(float(y[te].mean()), 4) if te.sum() else None,
                     flagged=int(flag.sum()),
                     flagged_share=round(float(flag.mean()), 4) if te.sum() else None)
        st_d = path_stats(ep[te], "net")
        st_r = path_stats(ep[te], "rule_net")
        d["default"] = st_d
        d["rule"] = st_r
        d["d_pnl"] = round(st_r["pnl_sum"] - st_d["pnl_sum"], 6)
        d["d_win"] = round(st_r["win"] - st_d["win"], 4)
        years.append(d)
        print(f"{d['year']} train={d['n_train']} (rate {d['train_rate']}) test={d['n_test']} "
              f"(rate {d['test_rate']}) flagged={d['flagged']} "
              f"P&L {st_d['pnl_sum']} -> {st_r['pnl_sum']} win {st_d['win']} -> {st_r['win']}", flush=True)
    d_all = np.array([yy["d_pnl"] for yy in years])
    loo = [round(float(np.delete(d_all, i).mean()), 6) for i in range(5)]
    pnl_ok = sum(1 for yy in years if yy["rule"]["pnl_sum"] >= yy["default"]["pnl_sum"])
    win_ok = sum(1 for yy in years if yy["rule"]["win"] > yy["default"]["win"])
    out = dict(version="oc_bookexit", idea=31, grid=[str(grid[0]), str(grid[-1])], n_bars=len(grid),
               n_episodes=len(ep), excluded=excl,
               label_rate=round(float(y.mean()), 4),
               per_coin={s: dict(n=int((ep["coin"] == s).sum()),
                                 rate=round(float(ep.loc[ep["coin"] == s, "label"].mean()), 4))
                         for s in SYMS},
               years=years, loo_d_pnl=loo,
               pnl_years_not_lower=int(pnl_ok), win_years_up=int(win_ok),
               promising=bool(pnl_ok >= 4 and win_ok >= 4))
    (HERE / "results.json").write_text(json.dumps(out, indent=1))
    print("P&L years not lower:", pnl_ok, "| win years up:", win_ok, "| PROMISING:", out["promising"], flush=True)


if __name__ == "__main__":
    main()
