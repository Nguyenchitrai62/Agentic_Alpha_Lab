"""oc_dip1h run: 1h-grid dip sleeve replay + G2 overlay (PLAN.md frozen 2026-10-08).

Usage:
  python research/tournament/oc_dip1h/run_dip1h.py --step g2
  python research/tournament/oc_dip1h/run_dip1h.py --step pass1 --coin BTCUSDT
  python research/tournament/oc_dip1h/run_dip1h.py --step pass2   # accounting+report
  (full: --step all runs g2 + all coins + pass2; heavy 1m work belongs under
   heavy_slot --tag oc_dip1h --min-free-gb 2.0)

One process, one coin's 1m H/L in RAM at a time (float32). Progress every 10 min.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import pickle
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
import dip1h_core as C

RD = ROOT / "research/parallel/rounds/parallel-20260906-r2"
V421 = RD / "v421/v421_runs.pkl"
V421_RES = RD / "v421/v421_result.json"
TMP = HERE / "tmp"

MAJORS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
STRAT = "R2B1D17BFG2"
GRID0 = pd.Timestamp("2021-09-24 04:00", tz="UTC")
G1 = pd.Timestamp("2026-09-23 12:00", tz="UTC")
TRADE0 = pd.Timestamp("2021-09-24 00:00", tz="UTC")
M1_START = pd.Timestamp("2020-08-01 00:00", tz="UTC")
M1_END = G1 + pd.Timedelta(hours=1)  # next-open of the last traded bar
ANCH = [pd.Timestamp(a, tz="UTC") for a in
        ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")]
YEAR = pd.Timedelta(days=365)
VARIANTS = ["H05", "H025"]


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def files_1m(sym: str):
    if sym == "BTCUSDT":
        return sorted((ROOT / "data/raw/btc_intraday_20260924").glob("klines_1m_20*.parquet"))
    return sorted((ROOT / f"data/raw/majors_intraday_20260924").glob(f"{sym}_1m_20*.parquet"))


# ---------------- step g2: baseline hourly equity + validation ----------------
def step_g2() -> None:
    v388 = _load("v388_for_dip1h", RD / "v388/v388_bot_stop_distance.py")
    runs = pickle.loads(V421.read_bytes())
    assert set(runs) == {0, 1, 2, 3}
    grid = pd.date_range(GRID0, G1, freq="1h")
    Es, Ms = [], []
    for s in range(4):
        e1, m1 = v388.hourly(runs[s][STRAT], GRID0, G1)
        assert (e1.index == grid).all()
        Es.append(e1.to_numpy(dtype=float))
        Ms.append(m1.to_numpy(dtype=float))
    Es, Ms = np.stack(Es), np.stack(Ms)
    E, M = Es.mean(axis=0), Ms.mean(axis=0)
    # per-year reset validation vs v421_result.json (to the digit)
    exp = json.loads(V421_RES.read_text())["rows"][STRAT]
    gn = grid.values.astype("datetime64[ns]").astype(np.int64)
    gotR, gotD = [], []
    for y, a0 in enumerate(ANCH):
        a1 = a0 + YEAR
        seg = (grid > a0) & (grid <= a1)
        idx = np.where(np.asarray(seg))[0]
        le = gn <= a0.value
        b = np.array([float(Es[s][le][-1]) if le.any() else 1.0 for s in range(4)])
        es = np.mean([Es[s][idx] / b[s] for s in range(4)], axis=0)
        ms = np.mean([Ms[s][idx] / b[s] for s in range(4)], axis=0)
        pk = np.maximum.accumulate(es)
        gotR.append(round(100 * float(es[-1] ** (1 / 12) - 1), 3))
        gotD.append(round(100 * float(np.max(1 - ms / pk)), 2))
    assert gotR == [r for r, _ in exp["years"]], (gotR, exp["years"])
    assert gotD == [d for _, d in exp["years"]], (gotD, exp["years"])
    segf = np.asarray(grid > pd.Timestamp("2021-09-24", tz="UTC"))
    esf, msf = E[segf], M[segf]
    dd_m = round(100 * float(np.max(1 - msf / np.maximum.accumulate(esf))), 2)
    dd_c = round(100 * float(np.max(1 - esf / np.maximum.accumulate(esf))), 2)
    full = max(dd_m, dd_c)
    assert full == exp["full_path_dd"], (full, exp)
    geo5 = round(float(np.prod([1 + r / 100 for r in gotR]) ** (1 / 5) - 1) * 100, 3)
    assert geo5 == exp["R"] and min(gotR) == exp["W"] and max(gotD) == exp["DD"]
    print(f"g2 validation OK: reproduces v421_result {STRAT} to the digit", flush=True)
    TMP.mkdir(exist_ok=True)
    np.savez_compressed(TMP / "g2_hourly.npz",
                        grid=gn, Es=Es, Ms=Ms, E=E, M=M,
                        anchors=np.array([a.value for a in ANCH]))


# ---------------- step pass1: per-coin 1m -> rung records ----------------
def step_pass1(coin: str) -> None:
    t0 = time.time()
    last_print = t0
    cols = ["open_time", "open", "high", "low", "close"]
    parts = [pd.read_parquet(f, columns=cols) for f in files_1m(coin)]
    m = pd.concat(parts, ignore_index=True)
    del parts
    m["open_time"] = pd.to_datetime(m["open_time"], utc=True)
    m = m.drop_duplicates("open_time").sort_values("open_time")
    m = m[(m["open_time"] >= M1_START) & (m["open_time"] < M1_END)]
    full_idx = pd.date_range(M1_START, M1_END - pd.Timedelta(minutes=1), freq="1min")
    m = m.set_index("open_time").reindex(full_idx)
    O = m["open"].to_numpy(dtype=np.float32)
    H = m["high"].to_numpy(dtype=np.float32)
    Lw = m["low"].to_numpy(dtype=np.float32)
    Cc = m["close"].to_numpy(dtype=np.float32)
    del m
    n_min = len(full_idx)
    assert n_min % 60 == 0, n_min
    nb = n_min // 60
    T = full_idx[:n_min:60]  # hourly bar opens
    O1 = O[::60].astype(float)
    sg = C.sigma1h_causal(O1)
    Ob = O.reshape(nb, 60)
    Hb = H.reshape(nb, 60)
    Lb = Lw.reshape(nb, 60)
    del O, H, Lw, Cc
    recs = []
    n_traded = 0
    for j in range(nb):
        tj = T[j]
        if not (TRADE0 <= tj < G1):
            continue
        n_traded += 1
        s = float(sg[j])
        if not (np.isfinite(s) and s > 0):
            continue
        o0 = float(O1[j])
        o_next = float(O1[j + 1]) if j + 1 < nb else np.nan
        settle = (tj + pd.Timedelta(hours=1)).hour in C.SETTLE_HOURS
        for r in C.bar_outcomes(o0, Ob[j], Hb[j], Lb[j], s, o_next, settle):
            exit_bar = tj if r["x"] < 60 else tj + pd.Timedelta(hours=1)
            recs.append((int(tj.value), int(exit_bar.value), r["k"], r["f"],
                         r["x"], r["fill"], r["exit"], r["ret"], r["how"]))
        now = time.time()
        if now - last_print >= 600:
            print(f"pass1 {coin}: bar {tj} ({n_traded} traded) "
                  f"{now - t0:.0f}s", flush=True)
            last_print = now
    df = pd.DataFrame(recs, columns=["bar_ns", "exit_ns", "k", "f", "x",
                                     "fill", "exit", "ret", "how"])
    df["coin"] = coin
    TMP.mkdir(exist_ok=True)
    df.to_parquet(TMP / f"rec_{coin}.parquet", index=False)
    print(f"pass1 {coin}: DONE {n_traded} bars, {len(df)} rungs, "
          f"{time.time() - t0:.0f}s", flush=True)


# ---------------- step pass2: accounting, overlay, report ----------------
def _year_of(tns: int) -> int | None:
    for i in range(5):
        lo = ANCH[i].value
        hi = (ANCH[i] + YEAR).value
        if lo <= tns < hi:
            return i
    return None


def step_pass2() -> None:
    z = np.load(TMP / "g2_hourly.npz")
    grid = pd.to_datetime(z["grid"], utc=True)
    Es, Ms, E, M = z["Es"], z["Ms"], z["E"], z["M"]
    gn = z["grid"]
    dfs = [pd.read_parquet(TMP / f"rec_{c}.parquet") for c in MAJORS]
    rec = pd.concat(dfs, ignore_index=True)
    del dfs
    print(f"pass2: {len(rec)} rung records", flush=True)
    rec = rec[np.isfinite(rec["ret"].to_numpy())].copy()
    n_nan = None
    rec["bar_i"] = rec["bar_ns"]  # sort key
    rec = rec.sort_values(["bar_ns", "coin", "k"]).reset_index(drop=True)

    # ---- standalone: per-year reset + continuous (for correlation) ----
    out_sa, cont = {}, {}
    for v in VARIANTS:
        size = C.SIZE[v]
        # per-year reset
        years = []
        for y in range(5):
            a0, a1 = ANCH[y].value, (ANCH[y] + YEAR).value
            sub = rec[(rec["bar_ns"] >= a0) & (rec["bar_ns"] < a1)]
            bars = np.sort(sub["bar_ns"].unique())
            Eb = {b: 0.0 for b in bars}
            Eq = 1.0
            Epath = []
            # group exits by exit_ns for stepping
            sub = sub.copy()
            for b in bars:
                Eb[b] = Eq
                # exits attributed to the hour containing the exit minute
                m = (sub["exit_ns"] >= b) & (sub["exit_ns"] < b + 3_600_000_000_000)
                grp = sub[m]
                if len(grp):
                    N = size * np.array([Eb.get(bb, Eq) for bb in grp["bar_ns"]])
                    Eq = Eq + float(np.sum(N * grp["ret"].to_numpy()))
                Epath.append(Eq)
            Epath = np.array(Epath)
            # fees / gross
            N_all = size * np.array([Eb[bb] for bb in sub["bar_ns"]]) if len(sub) else np.array([])
            fee_leg = np.where(sub["how"].to_numpy() == "tp", 2 * C.MAKER,
                               C.MAKER + C.TAKER) if len(sub) else np.array([])
            fees = float(np.sum(fee_leg * N_all)) if len(sub) else 0.0
            # funding: timeout exits at settling hour (exit minute 0 of exit bar)
            ex_hr = (pd.to_datetime(sub["exit_ns"]).dt.hour.to_numpy()
                     if len(sub) else np.array([]))
            fund = float(np.sum(np.where(
                (sub["how"].to_numpy() == "time") & np.isin(ex_hr, list(C.SETTLE_HOURS)),
                C.FUND * N_all, 0.0))) if len(sub) else 0.0
            ratio = (sub["exit"].to_numpy() / sub["fill"].to_numpy()
                     if len(sub) else np.array([]))
            gross_pos = float(np.sum(np.where(ratio > 1, (ratio - 1) * N_all, 0.0))) \
                if len(sub) else 0.0
            R = round(C.pct_per_month(Eq), 3)
            DD = round(C.max_dd(Epath), 2)
            n = int(len(sub))
            wr = round(float(np.mean(sub["ret"].to_numpy() > 0)), 4) if n else None
            years.append({"anchor": str(ANCH[y].date()), "R": R, "DD": DD,
                          "end": round(float(Eq), 6), "trades": n,
                          "win": wr, "fees": round(fees, 6),
                          "funding": round(fund, 6),
                          "fee_share": round(fees / max(gross_pos, 1e-12), 4)
                          if n else None})
        R4 = round(float(np.prod([1 + years[y]["R"] / 100 for y in range(4)])
                         ** (1 / 4) - 1) * 100, 3)
        R5 = round(float(np.prod([1 + y["R"] / 100 for y in years])
                         ** (1 / 5) - 1) * 100, 3)
        out_sa[v] = {"years": years,
                     "dev4": {"R": R4, "W": min(y["R"] for y in years[:4]),
                              "DD": max(y["DD"] for y in years[:4]),
                              "losing": sum(y["R"] < 0 for y in years[:4])},
                     "R5": R5, "W5": min(y["R"] for y in years),
                     "DD5": max(y["DD"] for y in years),
                     "losing5": sum(y["R"] < 0 for y in years)}
        # continuous (no reset) for daily correlation
        bars = np.sort(rec["bar_ns"].unique())
        Eq = 1.0
        Eb = {}
        Eser = []
        for b in bars:
            Eb[b] = Eq
            m = (rec["exit_ns"] >= b) & (rec["exit_ns"] < b + 3_600_000_000_000)
            grp = rec[m]
            if len(grp):
                N = size * np.array([Eb.get(bb, Eq) for bb in grp["bar_ns"]])
                Eq = Eq + float(np.sum(N * grp["ret"].to_numpy()))
            Eser.append(Eq)
        cont[v] = (bars, np.array(Eser))

    # ---- combined overlay on TOTAL equity (frozen UTA method) ----
    def run_comb(v: str | None):
        an = np.array([a.value for a in ANCH])
        rows = []
        for y, a0 in enumerate(ANCH):
            a1 = a0 + YEAR
            seg = (grid > a0) & (grid <= a1)
            idx = np.where(np.asarray(seg))[0]
            le = gn <= a0.value
            b = np.array([float(Es[s][le][-1]) if le.any() else 1.0 for s in range(4)])
            E4 = [Es[s][idx] / b[s] for s in range(4)]
            M4 = [Ms[s][idx] / b[s] for s in range(4)]
            es = np.mean(E4, axis=0)
            ms = np.mean(M4, axis=0)
            if v is None:
                A_arr, M_arr = es, ms
                skips = 0
            else:
                size = C.SIZE[v]
                sub = rec[(rec["bar_ns"] > a0.value)
                          & (rec["bar_ns"] <= (a0 + YEAR).value)]
                es_prev = np.concatenate([[1.0], es[:-1]])
                g = es / es_prev
                hh = ms / es_prev
                gh = grid[idx]
                A_prev = 1.0
                A_arr = np.empty(len(idx))
                M_arr = np.empty(len(idx))
                A_at: dict = {}  # entry bar_ns -> combined A at that bar
                skipped: set = set()  # record indices cut by the 2x cap
                skips = 0
                for i, t in enumerate(gh):
                    tns = t.value
                    A_at_bar = A_prev
                    if len(sub):
                        m_entry = (sub["bar_ns"] == tns)
                        if m_entry.any():
                            grp = sub[m_entry].sort_values(["f", "coin", "k"])
                            new_open: list = []  # (exit_offset, N)
                            for rix, r in grp.iterrows():
                                N = size * A_at_bar
                                open_now = sum(N0 for xo, N0 in new_open
                                               if xo > r["f"])
                                if (open_now + N) / A_prev + 1.0 > 2.0:
                                    skipped.add(rix)
                                    skips += 1
                                    continue
                                new_open.append((r["x"], N))
                    dU = 0.0
                    if len(sub):
                        m_exit = ((sub["exit_ns"] >= tns)
                                  & (sub["exit_ns"] < tns + 3_600_000_000_000))
                        if m_exit.any():
                            for rix, r in sub[m_exit].iterrows():
                                if rix in skipped:
                                    continue
                                eb = r["bar_ns"]
                                NA = size * A_at.get(eb, A_at_bar)
                                dU += NA * r["ret"]
                    A_arr[i] = A_prev * g[i] + dU
                    M_arr[i] = A_prev * hh[i] + dU
                    A_at[tns] = A_prev
                    A_prev = A_arr[i]
            pk = np.maximum.accumulate(A_arr)
            R = round(100 * float(A_arr[-1] ** (1 / 12) - 1), 3)
            DD = round(100 * float(np.max(1 - M_arr / pk)), 2)
            rows.append({"anchor": str(a0.date()), "R": R, "DD": DD,
                         "end": round(float(A_arr[-1]), 6),
                         "skips": skips if v else 0})
        R4 = round(float(np.prod([1 + r["R"] / 100 for r in rows[:4]])
                         ** (1 / 4) - 1) * 100, 3)
        R5 = round(float(np.prod([1 + r["R"] / 100 for r in rows])
                         ** (1 / 5) - 1) * 100, 3)
        return {"years": rows,
                "dev4": {"R": R4, "W": min(r["R"] for r in rows[:4]),
                         "DD": max(r["DD"] for r in rows[:4]),
                         "losing": sum(r["R"] < 0 for r in rows[:4])},
                "R5": R5, "W5": min(r["R"] for r in rows),
                "DD5": max(r["DD"] for r in rows),
                "losing5": sum(r["R"] < 0 for r in rows)}

    comb = {"G2": run_comb(None)}
    for v in VARIANTS:
        comb[f"G2+{v}"] = run_comb(v)

    # full-path DD (v421 continuous convention)
    Etot, Mtot = E, M
    full = {}
    for key in ["G2"] + [f"G2+{v}" for v in VARIANTS]:
        if key == "G2":
            A_c, M_c = Etot.copy(), Mtot.copy()
        else:
            v = key.split("+")[1]
            size = C.SIZE[v]
            # continuous overlay from GRID0
            A_c = np.empty(len(grid))
            M_c = np.empty(len(grid))
            A_prev = float(Etot[0])
            A_c[0], M_c[0] = float(Etot[0]), float(Mtot[0])
            A_at = {int(grid[0].value): A_prev}
            rec_c = rec[rec["bar_ns"] >= int(grid[0].value)].copy()
            skipped_c: set = set()
            for i in range(1, len(grid)):
                tns = int(grid[i].value)
                A_at_bar = A_prev
                m_entry = (rec_c["bar_ns"] == tns)
                if m_entry.any():
                    grp = rec_c[m_entry].sort_values(["f", "coin", "k"])
                    new_open = []
                    for rix, r in grp.iterrows():
                        N = size * A_at_bar
                        open_now = sum(N0 for xo, N0 in new_open if xo > r["f"])
                        if (open_now + N) / A_prev + 1.0 > 2.0:
                            skipped_c.add(rix)
                            continue
                        new_open.append((r["x"], N))
                m_exit = ((rec_c["exit_ns"] >= tns - 3_600_000_000_000)
                          & (rec_c["exit_ns"] < tns))
                dU = 0.0
                if m_exit.any():
                    for rix, r in rec_c[m_exit].iterrows():
                        if rix in skipped_c:
                            continue
                        NA = size * A_at.get(r["bar_ns"], A_at_bar)
                        dU += NA * r["ret"]
                g = Etot[i] / Etot[i - 1]
                hh = Mtot[i] / Etot[i - 1]
                A_c[i] = A_prev * g + dU
                M_c[i] = A_prev * hh + dU
                A_prev = A_c[i]
                A_at[tns] = A_prev
        segf = np.asarray(grid > pd.Timestamp("2021-09-24", tz="UTC"))
        esf, msf = A_c[segf], M_c[segf]
        dd_m = round(100 * float(np.max(1 - msf / np.maximum.accumulate(esf))), 2)
        dd_c = round(100 * float(np.max(1 - esf / np.maximum.accumulate(esf))), 2)
        full[key] = {"marked": dd_m, "close": dd_c, "full": max(dd_m, dd_c)}
    for key in comb:
        comb[key]["full_path_dd"] = full[key]

    # daily-return correlation sleeve vs G2 (dev4 + post, labelled)
    def daily_ret(bars_ns, Eser):
        idx = pd.to_datetime(bars_ns, utc=True)
        s = pd.Series(Eser, index=idx)
        d = s.resample("1D", origin=pd.Timestamp("2021-09-24", tz="UTC")).last().ffill()
        return d.pct_change().dropna()
    g2d = pd.Series(E, index=grid).resample(
        "1D", origin=pd.Timestamp("2021-09-24", tz="UTC")).last().ffill().pct_change().dropna()
    corr = {}
    for v in VARIANTS:
        sd = daily_ret(*cont[v])
        for tag, lo, hi in (("dev4", "2021-09-24", "2025-09-24"),
                            ("post", "2025-09-24", "2026-09-24")):
            a = g2d.loc[lo:hi]
            b = sd.loc[lo:hi]
            ix = a.index.intersection(b.index)
            c = round(float(a.loc[ix].corr(b.loc[ix])), 4) if len(ix) > 10 else None
            corr[f"{v}_vs_G2_{tag}"] = {"n": int(len(ix)), "pearson": c}

    res = {
        "meta": {
            "g2_src": "research/parallel/rounds/parallel-20260906-r2/v421/v421_runs.pkl strat R2B1D17BFG2",
            "grid": [str(grid[0]), str(grid[-1])],
            "metric": "reset per anchor year (fresh 1.0) + v421 continuous full-path DD; f=0 reproduces v421_result to the digit",
            "sizing": "rung notional = size_frac x equity at entry bar (H05=0.0320656, H025=0.0160328); combined: off TOTAL A + 2x cap (G2 gross proxied 1.0x)",
            "rungs": list(C.RUNGS), "tp": "1.0 sigma", "stop": "4.0 sigma touch, stop-first",
            "costs": "maker 0.0002, taker 0.00055, funding 0.0001 timeout-at-settle",
            "n_records": int(len(rec)),
        },
        "standalone": out_sa,
        "combined": comb,
        "corr_daily": corr,
    }
    (HERE / "results.json").write_text(json.dumps(res, indent=1))
    for v in VARIANTS:
        print(v, out_sa[v]["dev4"], "R5", out_sa[v]["R5"], flush=True)
    for k in comb:
        print(k, comb[k]["dev4"], "R5", comb[k]["R5"],
              "fullDD", comb[k]["full_path_dd"], flush=True)
    print(corr, flush=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--step", choices=["g2", "pass1", "pass2", "all"], required=True)
    ap.add_argument("--coin", default=None)
    a = ap.parse_args()
    if a.step in ("g2", "all"):
        step_g2()
    if a.step == "pass1":
        assert a.coin in MAJORS, a.coin
        step_pass1(a.coin)
    if a.step == "all":
        for c in MAJORS:
            step_pass1(c)
    if a.step in ("pass2", "all"):
        step_pass2()


if __name__ == "__main__":
    main()
