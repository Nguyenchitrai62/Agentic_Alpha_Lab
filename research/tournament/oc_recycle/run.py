"""oc_recycle run: committed-budget base vs winner-recycle V1/V2 (heavy 1m job).

Frozen definitions in PLAN.md (IDEAS6 idea #8). One process, one coin H/L at a
time, all-five-coins 1m opens/closes held as float32 arrays, RAM < 3 GB.
Run ONLY via the shared semaphore:
  .venv/Scripts/python.exe scripts/heavy_slot.py run --tag oc_recycle --min-free-gb 2.0 -- \
    .venv/Scripts/python.exe research/tournament/oc_recycle/run.py
Long job: heartbeat via progress prints every 10 minutes. Log to tmp/run.log
when launched with nohup.

Outputs: tmp/ledger.npz + results.json (this folder).
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import recycle as R

START = pd.Timestamp("2020-08-01", tz="UTC")
END = pd.Timestamp("2026-09-24 00:00", tz="UTC")
TRADE_START = pd.Timestamp("2021-09-24 00:00", tz="UTC")
YEAR_END = pd.Timestamp("2026-09-24 00:00", tz="UTC")
MAJORS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
ANCHORS = [pd.Timestamp(a, tz="UTC") for a in
           ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")]
SETTLE_HOURS = (0, 8, 16)
SHIFTS = (0, 1, 2, 3)
EPOCH = pd.Timestamp("1970-01-01", tz="UTC")
W = R.LIVE_B - R.LIVE_A + 1  # 223 live minutes
DSUM_GATE = 0.273
DD_TOL = 0.01
REF_M4 = [0.911, 0.833, 2.100, 3.197, 0.677]  # oc_placebo_dip 4-phase means


def load_oc(sym: str):
    """Full-length 1m open + close as float32 (+ minute index)."""
    if sym == "BTCUSDT":
        files = sorted(Path("data/raw/btc_intraday_20260924").glob("klines_1m_20*.parquet"))
    else:
        files = sorted(Path("data/raw/majors_intraday_20260924").glob(f"{sym}_1m_20*.parquet"))
    parts = [pd.read_parquet(f, columns=["open_time", "open", "close"]) for f in files]
    m = pd.concat(parts, ignore_index=True)
    m["open_time"] = pd.to_datetime(m["open_time"], utc=True)
    m = m.drop_duplicates("open_time").sort_values("open_time")
    m = m[(m["open_time"] >= START) & (m["open_time"] <= END)]
    idx = pd.date_range(START, END, freq="1min")
    m = m.set_index("open_time").reindex(idx)
    O = m["open"].to_numpy(dtype=np.float32)
    C = m["close"].to_numpy(dtype=np.float32)
    del m, parts
    return idx, O, C


def load_hl(sym: str, idx):
    if sym == "BTCUSDT":
        files = sorted(Path("data/raw/btc_intraday_20260924").glob("klines_1m_20*.parquet"))
    else:
        files = sorted(Path("data/raw/majors_intraday_20260924").glob(f"{sym}_1m_20*.parquet"))
    parts = [pd.read_parquet(f, columns=["open_time", "high", "low"]) for f in files]
    m = pd.concat(parts, ignore_index=True)
    m["open_time"] = pd.to_datetime(m["open_time"], utc=True)
    m = m.drop_duplicates("open_time").sort_values("open_time")
    m = m[(m["open_time"] >= START) & (m["open_time"] <= END)]
    m = m.set_index("open_time").reindex(idx)
    H = m["high"].to_numpy(dtype=np.float32)
    L = m["low"].to_numpy(dtype=np.float32)
    del m, parts
    return H, L


def year_of(t0):
    for i in range(5):
        lo = ANCHORS[i]
        hi = ANCHORS[i + 1] if i < 4 else YEAR_END
        if lo <= t0 < hi:
            return i
    return None


def exit_day_ordinal(bt: pd.Timestamp, x: int) -> int:
    d = (bt + pd.Timedelta(minutes=int(x))).date()
    return int((pd.Timestamp(d, tz="UTC") - EPOCH).days)


def cell_stats(dates: np.ndarray, wy: np.ndarray):
    if wy.size == 0:
        return 0.0, 0.0, 0.0
    order = np.argsort(dates, kind="stable")
    d = dates[order]
    v = wy[order]
    uniq, idx = np.unique(d, return_index=True)
    bounds = np.append(idx[1:], v.size)
    daily = np.array([v[s:e].sum() for s, e in zip(idx, bounds)])
    cum = np.cumsum(daily)
    peak = np.maximum.accumulate(cum)
    dd = float(np.min(cum - peak))
    return float(daily.sum()), float(daily.min()), float(-dd)


def main():
    t_start = time.time()
    O, C, base_idx = {}, {}, None
    for sym in MAJORS:
        ii, o, c = load_oc(sym)
        base_idx = ii if base_idx is None else base_idx
        O[sym], C[sym] = o, c
        print(f"loaded OC {sym}", flush=True)
    n_all = len(base_idx)

    grids = {}
    for s in SHIFTS:
        off = s * 60
        nb = (n_all - off) // 240
        t0 = base_idx[off:off + nb * 240:240]
        opens_bar, sig_bar = {}, {}
        for sym in MAJORS:
            ob = O[sym][off:off + nb * 240:240].astype(float)
            sg = pd.Series(ob).pct_change().rolling(360, min_periods=120).std(ddof=1).shift(1).to_numpy()
            opens_bar[sym], sig_bar[sym] = ob, sg
        js = [j for j in range(nb)
              if TRADE_START <= t0[j] < YEAR_END and (off + j * 240 + 240) < n_all]
        grids[s] = dict(off=off, nb=nb, t0=t0, opens=opens_bar, sig=sig_bar, js=js)
        print(f"shift {s}: nb={nb} traded={len(js)}", flush=True)
    del opens_bar, sig_bar

    # ---- candidate signals: one base fill per (phase, bar, coin, k) ----
    pool = []  # signals with finite nets (paired across arms)
    n_drop_nf = 0
    for sym in MAJORS:
        H, L = load_hl(sym, base_idx)
        La, Ha = L, H
        others = [b for b in MAJORS if b != sym]
        n_sig = 0
        for s in SHIFTS:
            g = grids[s]
            off, t0 = g["off"], g["t0"]
            opens_bar, sig_bar = g["opens"], g["sig"]
            Oa, Ca = O[sym], C[sym]
            for j in g["js"]:
                bt = t0[j]
                o1, sg = float(opens_bar[sym][j]), float(sig_bar[sym][j])
                if not (np.isfinite(o1) and np.isfinite(sg)) or o1 <= 0 or sg <= 0:
                    continue
                base = off + j * 240
                o2m = Oa[base + 240]
                o2 = float(o2m) if np.isfinite(o2m) else np.nan
                settle = (bt + pd.Timedelta(hours=4)).hour in SETTLE_HOURS
                yi = year_of(bt)
                low_win = La[base + R.LIVE_A:base + R.LIVE_B + 1].astype(float)
                cmat = np.stack([C[b][base + R.LIVE_A - 1:base + R.LIVE_B].astype(float)
                                 for b in others])
                oo = np.array([opens_bar[b][j] for b in others], dtype=float)
                ss = np.array([sig_bar[b][j] for b in others], dtype=float)
                nvec = R.n_vector(cmat, oo, ss)
                Ha_b = Ha[base:base + 240].astype(float)
                La_b = La[base:base + 240].astype(float)
                Ca_b = Ca[base:base + 240].astype(float)
                Oa_b = Oa[base:base + 240].astype(float)
                for k in R.RUNGS:
                    lv = o1 * (1 - k * sg)
                    if not np.isfinite(lv) or lv <= 0:
                        continue
                    ib = R.find_fill(low_win, np.full(W, lv))
                    if ib is None:
                        continue
                    f = R.LIVE_A + ib
                    nf = int(nvec[ib])
                    ret, x, how = R.outcome_from_fill(Ha_b, La_b, Ca_b, Oa_b, f, lv, sg, o2, settle)
                    if not np.isfinite(ret):
                        n_drop_nf += 1
                        continue
                    pool.append(dict(s=s, j=j, sym=sym, k=k, f=int(f), x=int(x), how=how,
                                     w=float(R.size_mult(nf)), n=int(nf), ret=float(ret),
                                     lv=float(lv), t_bar=bt, y=yi))
                    n_sig += 1
        print(f"{sym}: signals={n_sig}", flush=True)
        del H, L, Ha, La
    print(f"pool={len(pool)} drop_nonfinite={n_drop_nf} elapsed={time.time()-t_start:.0f}s", flush=True)

    # ---- per-(phase, bar) budget walks: base committed, V1 same-coin, V2 any-coin ----
    groups: dict = {}
    for i, r in enumerate(pool):
        groups.setdefault((r["s"], r["j"]), []).append(i)
    base_rows, v1_rows, v2_rows = [], [], []
    stat = dict(base_skip=0, base_cut=0, v1_skip=0, v1_cut=0, v1_rec=0,
                 v2_skip=0, v2_cut=0, v2_rec=0)
    for (s, j), idxs in groups.items():
        order = sorted(idxs, key=lambda i: (pool[i]["f"], pool[i]["k"], pool[i]["sym"]))
        pos = list(range(len(order)))
        F = [pool[i]["f"] for i in order]
        X = [pool[i]["x"] for i in order]
        W8 = [pool[i]["w"] for i in order]
        HW = [pool[i]["how"] for i in order]
        SY = [pool[i]["sym"] for i in order]
        kb = R.committed_walk(F, X, W8, pos, G=R.GROSS_CAP)
        k1, kind1 = R.recycle_walk(F, X, W8, HW, SY, pos, G=R.GROSS_CAP, same_coin=True)
        k2, kind2 = R.recycle_walk(F, X, W8, HW, SY, pos, G=R.GROSS_CAP, same_coin=False)
        for q, i in enumerate(order):
            r = pool[i]
            wb = kb[q]
            if wb <= 0:
                stat["base_skip"] += 1
            else:
                if wb < r["w"] - 1e-12:
                    stat["base_cut"] += 1
                base_rows.append(dict(s=s, y=r["y"], sym=r["sym"], k=r["k"], f=r["f"],
                                      x=r["x"], how=r["how"], w=wb, ret=r["ret"],
                                      t_bar=r["t_bar"]))
            w1 = k1[q]
            if w1 <= 0:
                stat["v1_skip"] += 1
            else:
                if w1 < r["w"] - 1e-12:
                    stat["v1_cut"] += 1
                if kind1[q] == 1:
                    stat["v1_rec"] += 1
                v1_rows.append(dict(s=s, y=r["y"], sym=r["sym"], k=r["k"], f=r["f"],
                                    x=r["x"], how=r["how"], w=w1, ret=r["ret"],
                                    t_bar=r["t_bar"], kind=int(kind1[q])))
            w2 = k2[q]
            if w2 <= 0:
                stat["v2_skip"] += 1
            else:
                if w2 < r["w"] - 1e-12:
                    stat["v2_cut"] += 1
                if kind2[q] == 1:
                    stat["v2_rec"] += 1
                v2_rows.append(dict(s=s, y=r["y"], sym=r["sym"], k=r["k"], f=r["f"],
                                    x=r["x"], how=r["how"], w=w2, ret=r["ret"],
                                    t_bar=r["t_bar"], kind=int(kind2[q])))
    df_b = pd.DataFrame(base_rows)
    df_1 = pd.DataFrame(v1_rows)
    df_2 = pd.DataFrame(v2_rows)
    print(f"kept base={len(df_b)} v1={len(df_1)} v2={len(df_2)} stat={stat}", flush=True)

    # ---- fidelity: uncapped sums (no budget) vs placebo refs ----
    df_pool = pd.DataFrame(pool)
    nocap_means = []
    for yi in range(5):
        sub = df_pool[df_pool["y"] == yi]
        per_s = []
        for s in SHIFTS:
            ss = sub[sub["s"] == s]
            if len(ss):
                wy = ss["w"].to_numpy(float) * ss["ret"].to_numpy(float)
                dd = [exit_day_ordinal(t, x) for t, x in zip(ss["t_bar"], ss["x"])]
                S, _, _ = cell_stats(np.array(dd), wy)
            else:
                S = 0.0
            per_s.append(S)
        nocap_means.append(float(np.mean(per_s)))

    def arm_year(s, yi, df):
        sub = df[(df["s"] == s) & (df["y"] == yi)]
        if len(sub):
            wy = sub["w"].to_numpy(float) * sub["ret"].to_numpy(float)
            dd = np.array([exit_day_ordinal(t, x) for t, x in zip(sub["t_bar"], sub["x"])])
            S, Wd, DD = cell_stats(dd, wy)
        else:
            S, Wd, DD = 0.0, 0.0, 0.0
        return {"n": int(len(sub)), "sum": S, "worst_day": Wd, "max_dd": DD}

    arms = {"base": df_b, "v1": df_1, "v2": df_2}
    per_year = []
    for yi in range(5):
        row = {"year": ANCHORS[yi].date().isoformat()}
        for name, df in arms.items():
            stats = [arm_year(s, yi, df) for s in SHIFTS]
            row[name] = {"sum_mean": float(np.mean([t["sum"] for t in stats])),
                         "n_mean": float(np.mean([t["n"] for t in stats])),
                         "worst_mean": float(np.mean([t["worst_day"] for t in stats])),
                         "dd_mean": float(np.mean([t["max_dd"] for t in stats]))}
        for v in ("v1", "v2"):
            row[v]["dSum"] = row[v]["sum_mean"] - row["base"]["sum_mean"]
            row[v]["pass_sum"] = bool(row[v]["sum_mean"] >= row["base"]["sum_mean"] - 1e-12)
            row[v]["pass_dd"] = bool(row[v]["dd_mean"] <= row["base"]["dd_mean"] + DD_TOL)
        # pooled win rates + recycled diagnostics
        for name, df in arms.items():
            sub = df[df["y"] == yi]
            row[f"win_{name}"] = float((sub["ret"].to_numpy(float) > 0).mean()) if len(sub) else 0.0
        for name, df in (("v1", df_1), ("v2", df_2)):
            sub = df[df["y"] == yi]
            rec = sub[sub["kind"] == 1]
            row[f"n_rec_{name}"] = int(len(rec))
            row[f"win_rec_{name}"] = float((rec["ret"].to_numpy(float) > 0).mean()) if len(rec) else 0.0
            wy_tot = float((sub["w"].to_numpy(float) * sub["ret"].to_numpy(float)).sum()) if len(sub) else 0.0
            wy_re = float((rec["w"].to_numpy(float) * rec["ret"].to_numpy(float)).sum()) if len(rec) else 0.0
            row[f"rec_share_{name}"] = float(wy_re / wy_tot) if wy_tot != 0 else 0.0
        per_year.append(row)

    gate = {}
    for v in ("v1", "v2"):
        sh = sum(1 for r in per_year if r[v]["pass_sum"])
        dh = sum(1 for r in per_year if r[v]["pass_dd"])
        dsum = float(sum(r[v]["sum_mean"] for r in per_year) - sum(r["base"]["sum_mean"] for r in per_year))
        gate[v] = {"sum_half": int(sh), "dd_half": int(dh), "dSum5y": round(dsum, 6),
                   "pass": bool(sh >= 4 and dh >= 4 and dsum >= DSUM_GATE)}

    # fee/funding/leg split per arm (counts; nets already include costs)
    def leg_split(df):
        if not len(df):
            return {}
        h = df["how"].value_counts().to_dict()
        return {k: int(v) for k, v in h.items()}

    chk_src = np.round(pd.DataFrame(pool)[["f", "x", "w", "ret"]].to_numpy(), 9).tobytes() \
        if len(pool) else b"empty"
    chk = hashlib.sha256(chk_src).hexdigest()[:16]
    out = {"config": {"coins": list(MAJORS), "rungs": list(R.RUNGS),
                       "bars": "per-phase opens in [2021-09-24, 2026-09-24)",
                       "grid": "4h from 2020-08-01 00:00 UTC + shift s in {0,1,2,3}h",
                       "live": [R.LIVE_A, R.LIVE_B],
                       "maker": R.MAKER, "taker": R.TAKER, "fund_long": 0.0001,
                       "base": "committed-budget: kept fills count against G=2.0 all window (idle-capital baseline)",
                       "rule": "winner-recycle: realised kind==0 TP (x<=f) frees kept notional; V1 same-coin pool, V2 cross-coin pool; one recycle per unit (pool-depleting), no compounding (kind==1 never frees); frozen lv/w; D0 exits incl. market-taker stops",
                       "cap": "per (phase,bar) time-order (f,k,coin) walk: skip when room<=1e-12 else cut to room",
                       "scoring": "exit-date daily sums, 4-phase means; gate sum_half>=4/5 + dd_half>=4/5 (tol 0.01) + dSum5y>=+0.273",
                       "note": "signals with non-finite exit nets dropped identically in all arms; market data to 2026-09-24 = research data"},
           "n_pool": int(len(pool)), "n_drop_nonfinite": int(n_drop_nf),
           "cap_stat": stat, "ledger_checksum": chk,
           "fidelity_nocap_4phase_means": [round(v, 6) for v in nocap_means],
           "fidelity_ref_placebo": REF_M4,
           "per_year": per_year, "gate": gate,
           "legs": {name: leg_split(df) for name, df in arms.items()},
           "n_kept": {name: int(len(df)) for name, df in arms.items()}}
    (HERE / "results.json").write_text(json.dumps(out, indent=1, default=str))
    # light ledger for audit (per-fill rows per arm)
    np.savez_compressed(HERE / "tmp" / "ledger.npz",
                        base=df_b.to_records(index=False) if len(df_b) else np.array([]),
                        v1=df_1.to_records(index=False) if len(df_1) else np.array([]),
                        v2=df_2.to_records(index=False) if len(df_2) else np.array([]))
    print(json.dumps({"gate": gate, "n_kept": out["n_kept"], "checksum": chk}, indent=1))
    print(f"done elapsed={time.time()-t_start:.0f}s", flush=True)


if __name__ == "__main__":
    main()
