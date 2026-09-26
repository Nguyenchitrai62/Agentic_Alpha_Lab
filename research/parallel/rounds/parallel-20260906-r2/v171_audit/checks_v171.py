"""v171 Part B adversarial checks (runs AFTER replication.json was saved).

Reads v171/v171_result.json + v171/v171_robustness.json and recomputes from
raw parquet (no v169/v171 imports):
 (1) causality review of trigger/sigma (numeric support);
 (2) 1m offset alignment vs 4h open + missing/duplicate diagnostics;
 (3) 20 largest event returns with timestamps vs raw 1m rows;
 (4) entry tradability (volume m+1 > 0, entry inside minute high/low);
 (5) sensitivity: exit at T+4h+15min instead of the 4h open.
Also verifies the <= vs < selection-boundary hypothesis for train Sharpe.
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
V171 = ROUND2 / "v171"

SYMS = ["BNBUSDT", "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]
KS = (2, 2.5, 3, 3.5, 4)
GRID_START = pd.Timestamp("2020-02-01 00:00:00+00:00")


def _load_engine_real():
    spec = importlib.util.spec_from_file_location(
        "v171B_engine_real", ROUND2 / "engine_real" / "engine_real.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    rep = json.loads((HERE / "replication.json").read_text())
    res = json.loads((V171 / "v171_result.json").read_text())
    rob = json.loads((V171 / "v171_robustness.json").read_text())
    er = _load_engine_real()
    ANCHORS = list(er.v144.v110.v92.ANCHORS)
    anchors_ts = [pd.Timestamp(a, tz="UTC") for a in ANCHORS]

    # ---- exact-match comparison ----
    print("=== comparison replication vs v171_result ===")
    for a_row, v_row in zip(rep["per_anchor"], res["sleeve_alone"]):
        print(a_row["anchor"], "k", a_row["k"], v_row["k"],
              "net", a_row["sleeve_net_pct"], v_row["net_pct"],
              "dd", a_row["sleeve_dd_pct"], v_row["dd_pct"],
              "ev", a_row["events"], v_row["events"])
    c, v = rep["combined"], res["primary_v154_plus_sleeve"]
    print("combined monthly", c["monthly_pct"], v["monthly_pct"],
          "DD", c["full_path_dd"], v["full_path_dd"])
    for cy, vy in zip(c["yearly"], v["yearly"]):
        print(cy["anchor"], cy["net_pct"], vy["net_pct"], cy["max_drawdown_percent"],
              vy["max_drawdown_percent"], cy["mean_g"], vy["mean_g"], cy["fills"], vy["fills"])

    books, _ = er.v154_books()
    books = books.sort_index()
    grid = pd.date_range(GRID_START, books.index.max(), freq="4h", tz="UTC")
    n = len(grid)
    T_all = grid + pd.Timedelta(hours=4)
    T2_all = grid + pd.Timedelta(hours=8)

    openT = np.zeros((n, len(SYMS)))
    exitOpen = np.zeros((n, len(SYMS)))
    fundT2 = np.zeros((n, len(SYMS)))
    sigma = np.zeros((n, len(SYMS)))
    for j, sym in enumerate(SYMS):
        k = pd.read_parquet(ROOT / "data/raw/xs_universe_20260924" / f"{sym}_4h.parquet")
        ot = pd.to_datetime(k["open_time"], utc=True)
        o = pd.Series(k["open"].to_numpy(dtype=float), index=ot).sort_index()
        o = o[~o.index.duplicated(keep="last")]
        ret = o / o.shift(1) - 1
        sigma[:, j] = ret.rolling(360, min_periods=120).std().reindex(grid).to_numpy(dtype=float)
        openT[:, j] = o.reindex(T_all).to_numpy(dtype=float)
        exitOpen[:, j] = o.reindex(T2_all).to_numpy(dtype=float)
        f = pd.read_parquet(ROOT / "data/raw/xs_universe_20260924" / f"{sym}_funding.parquet")
        ft = pd.to_datetime(f["fundingTime"], utc=True).dt.floor("4h")
        fundT2[:, j] = f.groupby(ft)["fundingRate"].sum().reindex(T2_all).fillna(0.0).to_numpy(dtype=float)

    # ---- 1m grids with OHLCV ----
    n_min = n * 240
    mgrid = pd.date_range(T_all.min(), T_all.min() + pd.Timedelta(minutes=n_min - 1),
                          freq="1min", tz="UTC")
    O = np.full((n, 240, len(SYMS)), np.nan)
    C = np.full((n, 240, len(SYMS)), np.nan)
    H = np.full((n, 240, len(SYMS)), np.nan)
    L = np.full((n, 240, len(SYMS)), np.nan)
    V = np.full((n, 240, len(SYMS)), np.nan)
    Craw = np.full((n, 240, len(SYMS)), np.nan)  # pre-ffill close
    dup_info = {}
    for j, sym in enumerate(SYMS):
        if sym == "BTCUSDT":
            files = sorted(glob.glob(str(ROOT / "data/raw/btc_intraday_20260924/klines_1m_20*.parquet")))
        else:
            files = sorted(glob.glob(str(ROOT / f"data/raw/majors_intraday_20260924/{sym}_1m_20*.parquet")))
        parts = [pd.read_parquet(f, columns=["open_time", "open", "high", "low", "close", "volume"]) for f in files]
        d = pd.concat(parts, ignore_index=True)
        d["open_time"] = pd.to_datetime(d["open_time"], utc=True)
        d = d.sort_values("open_time")
        dup = int(d.duplicated("open_time").sum())
        # first-vs-last duplicate difference
        dd = d.drop_duplicates("open_time", keep="first").set_index("open_time").sort_index()
        dl = d.drop_duplicates("open_time", keep="last").set_index("open_time").sort_index()
        common = dd.index.intersection(dl.index)
        ndiff = int((((dd.loc[common, ["open", "high", "low", "close", "volume"]]
                            - dl.loc[common, ["open", "high", "low", "close", "volume"]]).abs().sum(axis=1)) > 0).sum())
        d = d.drop_duplicates("open_time", keep="last").set_index("open_time")
        dup_info[sym] = {"rows": len(d), "dups": dup, "first_vs_last_diff": ndiff}
        for arr, col in ((O, "open"), (C, "close"), (H, "high"), (L, "low"), (V, "volume")):
            s = d[col].astype(float).reindex(mgrid).to_numpy(dtype=float).reshape(n, 240)
            if col == "close":
                Craw[:, :, j] = s
            # within-bar ffill
            for i in range(n):
                last = np.nan
                row = s[i]
                for m_ in range(240):
                    if np.isnan(row[m_]):
                        row[m_] = last
                    else:
                        last = row[m_]
            arr[:, :, j] = s
    print("dup_info", json.dumps(dup_info, indent=1))

    # ---- (2) alignment: 1m minute-0 open vs 4h open(T) ----
    print("=== check2 alignment ===")
    for j, sym in enumerate(SYMS):
        a, b = O[:, 0, j], openT[:, j]
        ok = np.isfinite(a) & np.isfinite(b) & (b != 0)
        rel = np.abs(a[ok] / b[ok] - 1)
        print(f"{sym}: coverage={ok.mean():.4f} median_rel_bps={np.median(rel) * 1e4:.4f} "
              f"max_rel_bps={rel.max() * 1e4:.3f} share_gt1bps={(rel > 1e-4).mean():.5f} "
              f"share_gt10bps={(rel > 1e-3).mean():.5f}")
        miss = np.isnan(C[:, :, j]).mean(axis=1)
        print(f"  1m missing-inside-bar: bars fully missing={(miss == 1).sum()}, "
              f"mean missing share={np.nanmean(miss):.5f}")

    # ---- rebuild applied-k events with details ----
    best_k = {r["anchor"]: r["k"] for r in rep["per_anchor"]}
    MO = np.arange(16, 239)
    events = []  # (t, sym, m, dip, entry, exit, fund, r)
    for j, sym in enumerate(SYMS):
        dip = C[:, MO, j] / openT[:, j:j + 1] - 1
        for i in range(n):
            t = grid[i]
            a_use = next((a for a, at in zip(ANCHORS, anchors_ts)
                          if at <= t < at + pd.Timedelta(days=365)), None)
            if a_use is None:
                continue
            kk = best_k[a_use]
            s = sigma[i, j]
            if not (np.isfinite(s) and s > 0):
                continue
            if not (np.isfinite(openT[i, j]) and openT[i, j] > 0 and np.isfinite(exitOpen[i, j])):
                continue
            row = dip[i]
            thr = -kk * s
            hit = np.nonzero(np.isfinite(row) & (row <= thr))[0]
            if not len(hit):
                continue
            m_ = int(MO[hit[0]])
            entry = O[i, m_ + 1, j]
            if not (np.isfinite(entry) and entry > 0):
                continue
            r = exitOpen[i, j] * 0.9998 / (entry * 1.0002) - 1 - 0.001 - fundT2[i, j]
            if not np.isfinite(r):
                continue
            events.append({"t": str(t), "sym": sym, "m": m_, "dip_bps": round(float(row[hit[0]]) * 1e4, 1),
                           "entry": float(entry), "exit": float(exitOpen[i, j]),
                           "r_bps": round(float(r) * 1e4, 1),
                           "trig_raw_missing": bool(np.isnan(Craw[i, m_, j])),
                           "entry_vol": float(V[i, m_ + 1, j]),
                           "entry_lo": float(L[i, m_ + 1, j]),
                           "entry_hi": float(H[i, m_ + 1, j])})
    ev = pd.DataFrame(events)
    print(f"total applied-k events in anchor windows: {len(ev)}")
    # live-span events per anchor should match sleeve_alone counts
    for a, at in zip(ANCHORS, anchors_ts):
        mk = (pd.to_datetime(ev["t"], utc=True) >= at) & (pd.to_datetime(ev["t"], utc=True) < at + pd.Timedelta(days=365))
        print(a, "events", int(mk.sum()), "audit", rep["per_anchor"][ANCHORS.index(a)]["events"])

    # ---- (3) top-20 events ----
    top20 = ev.sort_values("r_bps", ascending=False).head(20)
    print("=== check3 top-20 events ===")
    for _, e in top20.iterrows():
        print(e["t"], e["sym"], "m=", e["m"], "dip_bps=", e["dip_bps"], "r_bps=", e["r_bps"],
              "entry=", e["entry"], "exit4h=", e["exit"], "raw_missing=", e["trig_raw_missing"])
    # verify trigger dips exist in RAW (pre-ffill) 1m rows
    raw_ok = int((~ev["trig_raw_missing"]).sum())
    print(f"events with trigger minute present in raw 1m: {raw_ok}/{len(ev)}")
    # dump raw minute bars around each top-20 trigger
    for _, e in top20.iterrows():
        t = pd.Timestamp(e["t"])
        T = t + pd.Timedelta(hours=4)
        sym = e["sym"]
        if sym == "BTCUSDT":
            files = sorted(glob.glob(str(ROOT / "data/raw/btc_intraday_20260924/klines_1m_20*.parquet")))
        else:
            files = sorted(glob.glob(str(ROOT / f"data/raw/majors_intraday_20260924/{sym}_1m_20*.parquet")))
        raw = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
        raw["open_time"] = pd.to_datetime(raw["open_time"], utc=True)
        raw = raw.sort_values("open_time").drop_duplicates("open_time", keep="last").set_index("open_time")
        want = pd.date_range(T + pd.Timedelta(minutes=int(e["m"]) - 2),
                             T + pd.Timedelta(minutes=int(e["m"]) + 2), freq="1min", tz="UTC")
        print(f"--- {e['t']} {sym} m={e['m']} raw bars ---")
        print(raw.reindex(want)[["open", "high", "low", "close", "volume"]].to_string())

    # ---- (4) tradability ----
    print("=== check4 tradability ===")
    for sym in SYMS:
        sub = ev[ev["sym"] == sym]
        v = sub["entry_vol"].to_numpy(dtype=float)
        lo = sub["entry_lo"].to_numpy(dtype=float)
        hi = sub["entry_hi"].to_numpy(dtype=float)
        px = sub["entry"].to_numpy(dtype=float)
        print(f"{sym}: n={len(sub)} vol>0 share={np.mean(v > 0):.4f} "
              f"entry_in_[lo,hi] share={np.mean((px >= lo) & (px <= hi)):.4f} "
              f"median_vol={np.median(v):.1f}")

    # ---- (5) exit at T+4h+15min ----
    print("=== check5 exit T+4h+15m ===")
    # 1m open at offset 15 of bar T+4h == open_g[i+1, 15]
    r2_sum = {}
    for a, at in zip(ANCHORS, anchors_ts):
        mk = (grid >= at) & (grid < at + pd.Timedelta(days=365))
        s2 = np.zeros(n)
        kk = best_k[a]
        for j in range(len(SYMS)):
            dip = C[:, MO, j] / openT[:, j:j + 1] - 1
            sig = sigma[:, j]
            for i in np.nonzero(mk)[0]:
                if i + 1 >= n:
                    continue
                if not (np.isfinite(sig[i]) and sig[i] > 0):
                    continue
                if not (np.isfinite(openT[i, j]) and openT[i, j] > 0):
                    continue
                row = dip[i]
                hit = np.nonzero(np.isfinite(row) & (row <= -kk * sig[i]))[0]
                if not len(hit):
                    continue
                m_ = int(MO[hit[0]])
                entry = O[i, m_ + 1, j]
                exit2 = O[i + 1, 15, j]
                if not (np.isfinite(entry) and entry > 0 and np.isfinite(exit2) and exit2 > 0):
                    continue
                r2 = exit2 * 0.9998 / (entry * 1.0002) - 1 - 0.001 - fundT2[i, j]
                s2[i] += 0.25 * r2
        x = s2[mk]
        eq = np.cumprod(1 + x)
        net_pct = 100 * (float(eq[-1]) - 1)
        base_net = next(r["sleeve_net_pct"] for r in rep["per_anchor"] if r["anchor"] == a)
        print(f"{a}: k={kk} sleeve_net_exit4h={base_net} sleeve_net_exit+15m={round(net_pct, 2)} "
              f"delta={round(net_pct - base_net, 2)}pp")

    # ---- selection boundary hypothesis (<= vs <) ----
    print("=== train sharpe boundary ===")
    SEL0 = GRID_START + pd.Timedelta(days=30)
    sleeve_k = {}
    for kk in KS:
        acc = np.zeros(n)
        for j in range(len(SYMS)):
            dip = C[:, MO, j] / openT[:, j:j + 1] - 1
            sig = sigma[:, j]
            with np.errstate(invalid="ignore"):
                mask = (np.isfinite(sig) & (sig > 0))[:, None] & np.isfinite(dip) & (dip <= (-kk * sig)[:, None])
            has = mask.any(axis=1)
            first = mask.argmax(axis=1)
            entry = np.where(has, O[np.arange(n), np.clip(MO[first] + 1, 0, 239), j], np.nan)
            ok = has & np.isfinite(entry) & (entry > 0) & np.isfinite(exitOpen[:, j])
            r = np.zeros(n)
            r[ok] = exitOpen[ok, j] * 0.9998 / (entry[ok] * 1.0002) - 1 - 0.001 - fundT2[ok, j]
            r[~np.isfinite(r)] = 0.0
            acc += 0.25 * r
        sleeve_k[kk] = acc
    for a, at in zip(ANCHORS, anchors_ts):
        for op, tag in (("lt", "t<anchor-1d"), ("le", "t<=anchor-1d")):
            win = ((grid >= SEL0) & (grid < at - pd.Timedelta(days=1)) if op == "lt"
                   else (grid >= SEL0) & (grid <= at - pd.Timedelta(days=1)))
            scores = {}
            for kk in KS:
                s = sleeve_k[kk][win]
                scores[kk] = float(s.mean() / s.std()) if s.std() > 0 else -9
            bk = max(KS, key=lambda kk: scores[kk])
            rep_sh = next(iter([c["train_sharpe_per_bar"] for c in [res["chosen"][a]]]))
            print(f"{a} {tag}: best={bk} scores=" +
                  " ".join(f"{kk}:{round(scores[kk], 4)}" for kk in KS) + f" v171={rep_sh}")

    # ---- robustness cross-check (mean/median bps) ----
    print("=== robustness cross-check ===")
    for a, at in zip(ANCHORS, anchors_ts):
        sub = ev[(pd.to_datetime(ev["t"], utc=True) >= at)
                 & (pd.to_datetime(ev["t"], utc=True) < at + pd.Timedelta(days=365))]
        vrow = rob["rows"]["v171"][ANCHORS.index(a)]
        print(f"{a}: audit mean_bps={sub['r_bps'].mean():.1f} vs {vrow['mean_bps']} | "
              f"median_bps={sub['r_bps'].median():.1f} vs {vrow['median_bps']} | n={len(sub)} vs {vrow['events']}")


if __name__ == "__main__":
    main()
