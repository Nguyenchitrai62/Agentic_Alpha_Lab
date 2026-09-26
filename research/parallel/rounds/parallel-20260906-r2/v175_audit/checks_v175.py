"""v175 Part B adversarial checks (runs AFTER replication.json was saved).

Reads v175/v175_result.json and recomputes from raw parquet (no v175
imports except the result JSON):
 (1) look-ahead review (code + numeric alignment);
 (2) marketable bids: fills where the price is ALREADY below L at the
     first live minute (open of minute 16 < L) + reprice effect at the
     minute-16 open with taker fee 0.0005;
 (3) gap fills: trigger-minute low below L by more than 2%%;
 (4) share of each year's sleeve sum from the top 5%% of events;
 (5) exit at T+4h+15min sensitivity;
 (6) 2021 drawdown dates: sleeve vs books joint loss.
Also diagnoses the k-selection flips (2024/2025) under v175 conventions
(grid-seeded sigma, <= selection boundary).
"""

from __future__ import annotations

import glob
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parents[4]
ROUND2 = ROOT / "research" / "parallel" / "rounds" / "parallel-20260906-r2"
V175 = ROUND2 / "v175"

SYMS = ["BNBUSDT", "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]
KS = (2, 2.5, 3, 3.5, 4)
GRID_START = pd.Timestamp("2020-02-01 00:00:00+00:00")
SEL_START = GRID_START + pd.Timedelta(days=30)
ENTRY_FEE = 0.0002
EXIT_FEE = 0.0005


def _load_engine_real():
    spec = importlib.util.spec_from_file_location(
        "v175B_engine_real", ROUND2 / "engine_real" / "engine_real.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _ffill_rows(a: np.ndarray) -> np.ndarray:
    out = a.copy()
    for i in range(out.shape[0]):
        last = np.nan
        row = out[i]
        for k in range(row.shape[0]):
            if np.isnan(row[k]):
                row[k] = last
            else:
                last = row[k]
    return out


def main():
    rep = json.loads((HERE / "replication.json").read_text())
    res = json.loads((V175 / "v175_result.json").read_text())
    er = _load_engine_real()
    ANCHORS = list(er.v144.v110.v92.ANCHORS)
    anchors_ts = [pd.Timestamp(a, tz="UTC") for a in ANCHORS]

    print("=== comparison replication vs v175_result ===")
    for a_row, v_row in zip(rep["per_anchor"], res["sleeve_alone"]):
        print(a_row["anchor"], "k", a_row["k"], v_row["k"],
              "net", a_row["sleeve_net_pct"], v_row["net_pct"],
              "dd", a_row["sleeve_dd_pct"], v_row["dd_pct"],
              "ev", a_row["events"], v_row["events"])
    for key in ("primary_size025", "sensitivity_size015"):
        c = rep["combined_by_size"][key.split("_size")[1].replace("025", "0.25").replace("015", "0.15")]
        v = res[key]
        print(key, "monthly", c["monthly_pct"], v["monthly_pct"],
              "DD", c["full_path_dd"], v["full_path_dd"])
        for cy, vy in zip(c["yearly"], v["yearly"]):
            print("  ", cy["anchor"], cy["net_pct"], vy["net_pct"],
                  cy["max_drawdown_percent"], vy["max_drawdown_percent"],
                  cy["mean_g"], vy["mean_g"], cy["fills"], vy["fills"])
    print("v175 chosen:", json.dumps(res["chosen"]))
    print("audit k:", {r["anchor"]: r["k"] for r in rep["per_anchor"]})
    print("v175 reference_v172:", res["reference_v172"])

    books, _ = er.v154_books()
    books = books.sort_index()
    grid = pd.date_range(GRID_START, books.index.max(), freq="4h", tz="UTC")
    n = len(grid)
    T_all = grid + pd.Timedelta(hours=4)
    T2_all = grid + pd.Timedelta(hours=8)

    openT = np.zeros((n, len(SYMS)))
    exitOpen4h = np.zeros((n, len(SYMS)))
    fundT2 = np.zeros((n, len(SYMS)))
    sigma_full = np.zeros((n, len(SYMS)))
    for j, sym in enumerate(SYMS):
        k = pd.read_parquet(ROOT / "data/raw/xs_universe_20260924" / f"{sym}_4h.parquet")
        ot = pd.to_datetime(k["open_time"], utc=True)
        o = pd.Series(k["open"].to_numpy(dtype=float), index=ot).sort_index()
        o = o[~o.index.duplicated(keep="last")]
        ret = o / o.shift(1) - 1
        sigma_full[:, j] = ret.rolling(360, min_periods=120).std().reindex(grid).to_numpy(dtype=float)
        openT[:, j] = o.reindex(T_all).to_numpy(dtype=float)
        exitOpen4h[:, j] = o.reindex(T2_all).to_numpy(dtype=float)
        f = pd.read_parquet(ROOT / "data/raw/xs_universe_20260924" / f"{sym}_funding.parquet")
        ft = pd.to_datetime(f["fundingTime"], utc=True).dt.floor("4h")
        fundT2[:, j] = f.groupby(ft)["fundingRate"].sum().reindex(T2_all).fillna(0.0).to_numpy(dtype=float)

    # v175-convention sigma: rolling seeded at the grid start, on G-indexed
    # opens (returns ending at G[i] itself — causal, exactly as v175 builds
    # `opens` reindexed to G before pct_change/rolling).
    sigma_grid = np.zeros((n, len(SYMS)))
    for j, sym in enumerate(SYMS):
        k = pd.read_parquet(ROOT / "data/raw/xs_universe_20260924" / f"{sym}_4h.parquet")
        ot = pd.to_datetime(k["open_time"], utc=True)
        o = pd.Series(k["open"].to_numpy(dtype=float), index=ot).sort_index()
        o = o[~o.index.duplicated(keep="last")]
        s_G = o.reindex(grid)
        sigma_grid[:, j] = s_G.pct_change().rolling(360, min_periods=120).std().to_numpy(dtype=float)

    n_min = n * 240
    mgrid = pd.date_range(T_all.min(), T_all.min() + pd.Timedelta(minutes=n_min - 1),
                          freq="1min", tz="UTC")
    O = np.zeros((n, 240, len(SYMS)))
    H = np.zeros((n, 240, len(SYMS)))
    L = np.zeros((n, 240, len(SYMS)))
    for j, sym in enumerate(SYMS):
        if sym == "BTCUSDT":
            files = sorted(glob.glob(str(ROOT / "data/raw/btc_intraday_20260924/klines_1m_20*.parquet")))
        else:
            files = sorted(glob.glob(str(ROOT / f"data/raw/majors_intraday_20260924/{sym}_1m_20*.parquet")))
        parts = [pd.read_parquet(f, columns=["open_time", "open", "high", "low"]) for f in files]
        d = pd.concat(parts, ignore_index=True)
        d["open_time"] = pd.to_datetime(d["open_time"], utc=True)
        d = d.sort_values("open_time").drop_duplicates("open_time", keep="last").set_index("open_time")
        O[:, :, j] = _ffill_rows(d["open"].astype(float).reindex(mgrid).to_numpy(dtype=float).reshape(n, 240))
        H[:, :, j] = _ffill_rows(d["high"].astype(float).reindex(mgrid).to_numpy(dtype=float).reshape(n, 240))
        L[:, :, j] = _ffill_rows(d["low"].astype(float).reindex(mgrid).to_numpy(dtype=float).reshape(n, 240))

    MO = np.arange(16, 239)
    idx = np.arange(n)
    s_out = np.zeros((n, len(SYMS)))
    for j in range(len(SYMS)):
        nxt = np.clip(idx + 1, 0, n - 1)
        o0, h0, l0 = O[nxt, 0, j], H[nxt, 0, j], L[nxt, 0, j]
        with np.errstate(invalid="ignore", divide="ignore"):
            rng = (h0 - l0) / o0
        ok = (np.isfinite(rng) & np.isfinite(o0) & (o0 > 0)
              & np.isfinite(h0) & np.isfinite(l0) & (h0 >= l0))
        s_raw = np.maximum(0.0002, 0.25 * rng)
        s_out[:, j] = np.where(ok, np.where(np.isfinite(s_raw), s_raw, 0.0002), 0.0002)

    def sleeve_for_sigma(sig):
        r_sym_k = {}
        for j in range(len(SYMS)):
            per_k = {}
            for k in KS:
                with np.errstate(invalid="ignore", divide="ignore"):
                    lim = openT[:, j] * (1 - k * sig[:, j])
                valid = (np.isfinite(sig[:, j]) & (sig[:, j] > 0) & np.isfinite(openT[:, j])
                         & (openT[:, j] > 0) & np.isfinite(lim) & (lim > 0))
                with np.errstate(invalid="ignore"):
                    hit = valid[:, None] & np.isfinite(L[:, MO, j]) & (L[:, MO, j] < lim[:, None])
                has = hit.any(axis=1)
                ok = has & valid & np.isfinite(exitOpen4h[:, j]) & (exitOpen4h[:, j] > 0) & (idx + 1 < n)
                r = np.zeros(n)
                with np.errstate(invalid="ignore", divide="ignore"):
                    r[ok] = exitOpen4h[ok, j] * (1 - s_out[ok, j]) / lim[ok] - 1 - ENTRY_FEE - EXIT_FEE - fundT2[ok, j]
                r[~np.isfinite(r)] = 0.0
                r[idx + 1 >= n] = 0.0
                per_k[k] = r
            r_sym_k[j] = per_k
        return {k: 0.25 * sum(r_sym_k[j][k] for j in range(len(SYMS))) for k in KS}, r_sym_k

    sleeve_k, r_sym_k = sleeve_for_sigma(sigma_full)
    sleeve_k_grid, _ = sleeve_for_sigma(sigma_grid)

    # ---- k-selection under both conventions ----
    print("=== k-selection: audit (< bound, full-history sigma) vs v175 (<= bound, grid-seeded sigma) ===")
    for a, a_ts in zip(ANCHORS, anchors_ts):
        for tag, sk, win in (
            ("audit", sleeve_k,
             (grid >= SEL_START) & (grid < a_ts - pd.Timedelta(days=1))),
            ("v175 ", sleeve_k_grid,
             (grid >= SEL_START) & (grid <= a_ts - pd.Timedelta(days=1))),
        ):
            scores = {}
            for k in KS:
                s = sk[k][win]
                mu, sd = float(s.mean()), float(s.std())
                scores[k] = mu / sd if (np.isfinite(mu) and np.isfinite(sd) and sd > 0) else -np.inf
            bk = max(KS, key=lambda k: scores[k])
            print(f"{a} {tag}: best={bk} " + " ".join(f"{k}:{round(scores[k], 4)}" for k in KS)
                  + f" v175={res['chosen'][a]['k']}({res['chosen'][a]['train_sharpe_per_bar']})")
    ndiff = int((np.isfinite(sigma_full) & np.isfinite(sigma_grid)
                 & (np.abs(sigma_full - sigma_grid) > 1e-12)).sum())
    print(f"sigma cells differing full-history vs grid-seeded: {ndiff} "
          f"(expect only the first ~240 grid bars)")

    # ---- event details under audit applied-k ----
    best_k = {r["anchor"]: r["k"] for r in rep["per_anchor"]}
    events = []
    for j, sym in enumerate(SYMS):
        for k in KS:
            with np.errstate(invalid="ignore", divide="ignore"):
                lim = openT[:, j] * (1 - k * sigma_full[:, j])
            valid = (np.isfinite(sigma_full[:, j]) & (sigma_full[:, j] > 0) & np.isfinite(openT[:, j])
                     & (openT[:, j] > 0) & np.isfinite(lim) & (lim > 0))
            with np.errstate(invalid="ignore"):
                hit = valid[:, None] & np.isfinite(L[:, MO, j]) & (L[:, MO, j] < lim[:, None])
            has = hit.any(axis=1)
            first = hit.argmax(axis=1)
            for i in np.nonzero(has)[0]:
                t = grid[i]
                a_use = next((a for a, at in zip(ANCHORS, anchors_ts)
                              if at <= t < at + pd.Timedelta(days=365)), None)
                if a_use is None or best_k[a_use] != k:
                    continue
                if not (np.isfinite(exitOpen4h[i, j]) and exitOpen4h[i, j] > 0 and i + 1 < n):
                    continue
                m = int(MO[first[i]])
                r = exitOpen4h[i, j] * (1 - s_out[i, j]) / lim[i] - 1 - ENTRY_FEE - EXIT_FEE - fundT2[i, j]
                if not np.isfinite(r):
                    continue
                events.append({"t": t, "anchor": a_use, "sym": sym, "k": k, "L": float(lim[i]),
                               "m": m, "low_m": float(L[i, m, j]), "open16": float(O[i, 16, j]),
                               "open15next": float(O[i + 1, 15, j]),
                               "h15next": float(H[i + 1, 15, j]), "l15next": float(L[i + 1, 15, j]),
                               "o15next": float(O[i + 1, 15, j]),
                               "s_out": float(s_out[i, j]), "exit": float(exitOpen4h[i, j]),
                               "fund": float(fundT2[i, j]), "r": float(r)})
    ev = pd.DataFrame(events)
    print(f"applied-k fill events in anchor windows: {len(ev)} "
          f"(audit sleeve_totals events={rep['sleeve_totals']['events']})")
    for a in ANCHORS:
        sub = ev[ev["anchor"] == a]
        ra = next(r for r in rep["per_anchor"] if r["anchor"] == a)
        print(f"{a}: k={ra['k']} events={len(sub)} (rep {ra['events']}) "
              f"sleeve_sum={0.25 * sub['r'].sum():.4f} (rep {ra['sleeve_sum']:.4f})")

    # ---- (1) look-ahead ----
    print("=== check1 look-ahead ===")
    print("code: L=open(T)*(1-k*sigma(t)) with sigma from 4h opens<=t; "
          "fill minutes 16..238 strictly inside T=t+4h; exit/funding at T+4h only. "
          "No signal/weight/k uses post-decision data beyond executed prices.")
    print(f"fill minute range in rebuilt events: [{ev['m'].min()}, {ev['m'].max()}] "
          f"(must lie in 16..238)")
    assert ev["m"].min() >= 16 and ev["m"].max() <= 238

    # ---- (2) marketable bids ----
    print("=== check2 already-below-L at minute 16 ===")
    for a in ANCHORS:
        sub = ev[ev["anchor"] == a]
        mk = sub["open16"] < sub["L"]
        n_mk = int(mk.sum())
        # reprice: entry at minute-16 open, taker fee 0.0005 on entry (exit taker 0.0005 as before)
        r_alt = sub["exit"] * (1 - sub["s_out"]) / sub["open16"] - 1 - 0.0005 - 0.0005 - sub["fund"]
        r_alt = r_alt.where(np.isfinite(sub["open16"]) & (sub["open16"] > 0), sub["r"])
        base_sum = 0.25 * sub["r"].sum()
        alt = sub["r"].copy()
        alt[mk] = r_alt[mk]
        alt_sum = 0.25 * alt.sum()
        ra = next(r for r in rep["per_anchor"] if r["anchor"] == a)
        s = sleeve_k[ra["k"]][(grid >= pd.Timestamp(a, tz="UTC"))
                              & (grid < pd.Timestamp(a, tz="UTC") + pd.Timedelta(days=365))]
        eq = np.cumprod(1 + s)
        base_net = 100 * (float(eq[-1]) - 1)
        print(f"{a}: marketable {n_mk}/{len(sub)} ({100 * n_mk / max(len(sub), 1):.1f}%%); "
              f"sleeve_sum {base_sum:.4f} -> {alt_sum:.4f} (delta {alt_sum - base_sum:+.4f}); "
              f"implied net {base_net:.2f}%% -> {100 * ((1 + base_net / 100) * (1 + alt_sum) / (1 + base_sum) - 1):.2f}%%")
    n_mk_all = int((ev["open16"] < ev["L"]).sum())
    print(f"ALL: marketable {n_mk_all}/{len(ev)} ({100 * n_mk_all / len(ev):.1f}%%). "
          f"Model fills these at L (maker fee); reality would fill at/near the minute-16 open "
          f"(better price for a buy) — L is conservative there.")

    # ---- (3) gaps ----
    print("=== check3 gap fills (trigger-minute low >2%% below L) ===")
    ev["gap"] = (ev["L"] - ev["low_m"]) / ev["L"]
    for a in ANCHORS:
        sub = ev[ev["anchor"] == a]
        g = sub[sub["gap"] > 0.02]
        print(f"{a}: gaps {len(g)}/{len(sub)}; max gap {100 * sub['gap'].max():.2f}%%; "
              f"mean r of gaps {1e4 * g['r'].mean():.1f}bps vs all {1e4 * sub['r'].mean():.1f}bps")
    print(f"ALL: gaps {int((ev['gap'] > 0.02).sum())}/{len(ev)}. "
          f"A resting buy bid filled at L as the price trades through L — including gaps and "
          f"gap-opens below L (filled at the open, better than L). The model price L is "
          f"conservative in every gap case, never optimistic.")

    # ---- (4) top-5%% concentration ----
    print("=== check4 top-5pct concentration ===")
    for a in ANCHORS:
        sub = ev[ev["anchor"] == a].sort_values("r", ascending=False).reset_index(drop=True)
        ntop = max(1, int(np.ceil(0.05 * len(sub))))
        top_sum = 0.25 * sub["r"].iloc[:ntop].sum()
        tot = 0.25 * sub["r"].sum()
        rest_net = 100 * (float(np.cumprod(1 + 0.25 * sub["r"].sort_index(kind="stable").to_numpy())[-1]) - 1) \
            if len(sub) else 0.0
        print(f"{a}: n={len(sub)} top5pct n={ntop} share={100 * top_sum / tot:.1f}%% "
              f"(top {top_sum:.4f} of {tot:.4f})")
    print("note: sleeve_sum is fee/funding-loaded; share computed on 0.25*sum(r) per bar, "
          "order-free (sums commute), so the share is exact.")

    # ---- (5) exit at T+4h+15min ----
    print("=== check5 exit T+4h+15m ===")
    with np.errstate(invalid="ignore", divide="ignore"):
        rng15 = (ev["h15next"] - ev["l15next"]) / ev["o15next"]
    s15 = np.where(np.isfinite(rng15) & np.isfinite(ev["o15next"]) & (ev["o15next"] > 0),
                   np.maximum(0.0002, 0.25 * rng15), 0.0002)
    exit15 = ev["o15next"] * (1 - s15)
    r15 = np.where(np.isfinite(exit15) & (exit15 > 0),
                   exit15 / ev["L"] - 1 - ENTRY_FEE - EXIT_FEE - ev["fund"], ev["r"])
    ev["r15"] = np.where(np.isfinite(r15), r15, ev["r"])
    n_fallback = int((~np.isfinite(exit15) | (exit15 <= 0)).sum())
    print(f"minute-15 opens missing/nonpositive: {n_fallback}/{len(ev)} (kept original exit there)")
    for a in ANCHORS:
        sub = ev[ev["anchor"] == a]
        ra = next(r for r in rep["per_anchor"] if r["anchor"] == a)
        s = sleeve_k[ra["k"]][(grid >= pd.Timestamp(a, tz="UTC"))
                              & (grid < pd.Timestamp(a, tz="UTC") + pd.Timedelta(days=365))]
        base_net = 100 * (float(np.cumprod(1 + s)[-1]) - 1)
        alt_sum = 0.25 * sub["r15"].sum()
        base_sum = 0.25 * sub["r"].sum()
        alt_net = 100 * ((1 + base_net / 100) * (1 + alt_sum) / (1 + base_sum) - 1)
        print(f"{a}: k={ra['k']} sleeve_net exit4h={base_net:.2f}%% exit+15m={alt_net:.2f}%% "
              f"delta={alt_net - base_net:+.2f}pp")

    # ---- (6) 2021 drawdown: sleeve vs books ----
    print("=== check6 2021 drawdown ===")
    a = "2021-09-24"
    a0 = pd.Timestamp(a, tz="UTC")
    win2021 = (grid >= a0) & (grid < a0 + pd.Timedelta(days=365))
    g2021 = grid[win2021]
    s = sleeve_k[best_k[a]][win2021]
    eq_s = np.cumprod(1 + s)
    peak_s = np.maximum.accumulate(eq_s)
    dd_s = 1 - eq_s / peak_s
    i_trough = int(np.argmax(dd_s))
    i_peak = int(np.argmax(eq_s[:i_trough + 1]))
    print(f"sleeve-alone 2021: peak {g2021[i_peak].date()}, trough {g2021[i_trough].date()} "
          f"DD={100 * dd_s[i_trough]:.2f}%% (rep {next(r for r in rep['per_anchor'] if r['anchor'] == a)['sleeve_dd_pct']}%%)")
    # books-alone net series in 2021 (light mirror of the audit combined loop, sleeve=0)
    v135 = er.v144.v135
    v99 = er.v144.v99
    v110 = er.v144.v110
    PD = er.v144.PD
    books2, opens_full2 = er.v154_books()
    books2 = books2.sort_index()
    bidx = books2.index
    cols = list(books2.columns)
    ctx = er.context(books2, opens_full2)
    fee_b = np.zeros((len(bidx), len(cols)))
    rel_b = np.zeros((len(bidx), len(cols)))
    fee_s = np.zeros((len(bidx), len(cols)))
    rel_s = np.zeros((len(bidx), len(cols)))

    def _bar_stats_W(m_1m, W):
        T = m_1m["open_time"].dt.floor("4h")
        off = ((m_1m["open_time"] - T).dt.total_seconds() // 60).astype(int)
        p0 = m_1m[off == 0].set_index(T[off == 0])["open"]
        wmask = (off >= 2) & (off <= W - 1)
        lo = m_1m[wmask].groupby(T[wmask])["low"].min()
        hi = m_1m[wmask].groupby(T[wmask])["high"].max()
        pW = m_1m[off == W].set_index(T[off == W])["open"]
        return pd.DataFrame({"p0": p0, "lo": lo, "hi": hi, "pW": pW})

    for j, col in enumerate(cols):
        m = v135.load_1m(col)
        st = _bar_stats_W(m, 60).reindex(bidx + pd.Timedelta(hours=4)).set_axis(bidx)
        p0 = st["p0"].to_numpy(dtype=float)
        lo = st["lo"].to_numpy(dtype=float)
        hi = st["hi"].to_numpy(dtype=float)
        pW = st["pW"].to_numpy(dtype=float)
        have = ~np.isnan(p0)
        pWf = np.where(np.isnan(pW), p0, pW)
        with np.errstate(invalid="ignore", divide="ignore"):
            mv = np.where(have, pWf / np.where(have, p0, 1.0) - 1, 0.0)
        mv = np.nan_to_num(mv, nan=0.0, posinf=0.0, neginf=0.0)
        fb = have & (lo < p0 * (1 - 0.001))
        fs = have & (hi > p0 * (1 + 0.001))
        fee_b[:, j] = np.where(fb, 0.0002, 0.0005)
        rel_b[:, j] = np.where(fb, -0.001, mv + 0.0002)
        fee_s[:, j] = np.where(fs, 0.0002, 0.0005)
        rel_s[:, j] = np.where(fs, 0.001, mv - 0.0002)
    o = ctx["opens"].reindex(bidx)[cols]
    r_next, _, _, fund = ctx["mkt"]
    carry, expo = ctx["carry_real"]
    B = books2.to_numpy(dtype=float)
    live = np.asarray((bidx >= v110.START) & (bidx < v110.END))
    nB = len(bidx)
    realized = (v99.W_BOOKS * (books2.shift(2) * (o / o.shift(1) - 1)).sum(axis=1)
                + v99.W_CARRY * v99.CARRY_LEV * pd.Series(carry, index=bidx).shift(1))
    vol = (realized.rolling(60 * PD, min_periods=20 * PD).std() * np.sqrt(PD * 365)).to_numpy(dtype=float)
    s_arr = np.where(np.isnan(vol), 1.0, np.minimum(0.25 / np.where(np.isnan(vol), 1.0, vol), v99.CAP))
    mins = np.array([er.MIN_NOTIONAL.get(c, 5.0) for c in cols])
    net_b = np.zeros(nB)
    eq_b = np.ones(nB)
    prev_w = np.zeros(len(cols))
    prev_c = 0.0
    for i in range(nB):
        if live[i]:
            w = v99.W_BOOKS * s_arr[i] * B[i]
            c = v99.W_CARRY * v99.CARRY_LEV * s_arr[i]
        else:
            w = np.zeros(len(cols))
            c = 0.0
        ex = expo[i]
        if c * ex + np.abs(w).sum() / er.MARGIN > er.BUFFER:
            c = min(c, max(0.0, (er.BUFFER - np.abs(w).sum() / er.MARGIN) / max(ex, 1e-9)))
            if np.abs(w).sum() / er.MARGIN > er.BUFFER:
                w = w * er.BUFFER * er.MARGIN / np.abs(w).sum()
        eq_usdt = er.ACCOUNT_USDT * (eq_b[i - 1] if i else 1.0)
        w = np.where((np.abs(w - prev_w) * eq_usdt < mins) & (w != 0), prev_w, w)
        dw = w - prev_w
        buy = dw > 0
        exec_c = float(np.sum(np.abs(dw) * np.where(buy, fee_b[i], fee_s[i])
                              + dw * np.where(buy, rel_b[i], rel_s[i])))
        dc = c - prev_c
        carry_c = float(abs(dc) / er.CARRY_CAPITAL * ex * (er.SPOT_FEE + er.PERP_TAKER))
        net_b[i] = float(np.sum(w * r_next[i])) - exec_c + float(-np.sum(w * fund[i])) \
            + float(c * carry[i]) - carry_c
        eq_b[i] = (eq_b[i - 1] if i else 1.0) * (1 + net_b[i])
        prev_w, prev_c = w.copy(), c
    bwin = (bidx >= a0) & (bidx < a0 + pd.Timedelta(days=365))
    idx2021 = bidx[bwin]
    nb2021 = net_b[bwin]
    eq_b2021 = np.cumprod(1 + nb2021)
    pk_b = np.maximum.accumulate(eq_b2021)
    dd_b = 1 - eq_b2021 / pk_b
    j_tr = int(np.argmax(dd_b))
    j_pk = int(np.argmax(eq_b2021[:j_tr + 1]))
    print(f"books-alone 2021: peak {idx2021[j_pk].date()}, trough {idx2021[j_tr].date()} "
          f"DD={100 * dd_b[j_tr]:.2f}%% (rep {rep['books_alone_W60']['yearly'][0]['max_drawdown_percent']}%%)")
    # joint loss: daily aggregation + correlation in 2021
    sl_d = pd.Series(s, index=g2021).resample("1D").sum()
    bk_d = pd.Series(nb2021, index=idx2021).resample("1D").sum()
    both = pd.concat([sl_d, bk_d], axis=1, join="inner").dropna()
    both.columns = ["sleeve", "books"]
    ov_start = max(g2021[i_peak].date(), idx2021[j_pk].date())
    ov_end = min(g2021[i_trough].date(), idx2021[j_tr].date())
    print(f"DD-window overlap: sleeve {g2021[i_peak].date()}->{g2021[i_trough].date()} vs "
          f"books {idx2021[j_pk].date()}->{idx2021[j_tr].date()} "
          f"(overlap {ov_start}->{ov_end} "
          f"{'YES' if ov_start <= ov_end else 'none'})")
    print(f"2021 daily corr(sleeve, books)={both['sleeve'].corr(both['books']):.3f}; "
          f"sleeve daily mean {1e4 * both['sleeve'].mean():.2f}bps, books daily mean {1e4 * both['books'].mean():.2f}bps")
    neg = both[(both["sleeve"] < 0) & (both["books"] < 0)]
    print(f"days both negative in 2021: {len(neg)}/{len(both)}; "
          f"sleeve loss on those days {both.loc[neg.index, 'sleeve'].sum():.4f}, "
          f"books loss {both.loc[neg.index, 'books'].sum():.4f}")
    print("books engine rows 2021 (audit books_alone_W60 yearly[0] / v175 primary yearly[0]):")
    print("  audit:", json.dumps(rep["books_alone_W60"]["yearly"][0]))
    print("  v175 primary size025:", json.dumps(res["primary_size025"]["yearly"][0]))
    print("  v175 sleeve 2021:", json.dumps(res["sleeve_alone"][0]))


if __name__ == "__main__":
    main()
