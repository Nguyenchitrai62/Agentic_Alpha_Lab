"""oc_i2_tapecancel run: dip replica (oc_bidttl-exact) + C1/C2 tape-cancel screen.

Two stages for selection-protocol compliance:
  Stage A (dev4): bars with open in [2021-09-24, 2025-09-24). Replica fills +
    C1/C2 cancel flags, G-cap walks, dev4 legs, robust choice on dev4 ONLY.
  Stage B (2025, POST-HOC): bars with open in [2025-09-24, 2026-09-24), base +
    CHOSEN variant only. Skipped entirely if no variant is dev-eligible.
4-phase engine runs ONLY if the screen is PROMISING (not expected).

  .venv/Scripts/python.exe scripts/heavy_slot.py run --tag oc_i2_tapecancel --min-free-gb 2.0 -- .venv/Scripts/python.exe research/tournament/oc_i2_tapecancel/run_tapecancel.py [--smoke]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import numpy as np
import pandas as pd

import tapecancel as T

START = pd.Timestamp("2020-08-01", tz="UTC")
END = pd.Timestamp("2026-09-24 00:00", tz="UTC")
TRADE_START = pd.Timestamp("2021-09-24 00:00", tz="UTC")
SPLIT = pd.Timestamp("2025-09-24 00:00", tz="UTC")  # dev4 | 2025 split (bar open)
YEAR_END = pd.Timestamp("2026-09-24 00:00", tz="UTC")
MAJORS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
ANCHORS = [pd.Timestamp(a, tz="UTC") for a in
           ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")]
PHASES = (0, 1, 2, 3)
SETTLE_HOURS = (0, 8, 16)
TAPE_DIR = Path("data/raw/aggflow_20260929_orders_1m")
TAPE_HIST_START = pd.Timestamp("2021-08-20", tz="UTC")  # trailing-30d cover
PLACEBO_GATE = 0.273
PLACEBO_REF_P0 = [2.388052, 0.182865, 3.809764, 2.579274, 0.711509]


def check_baseline() -> dict:
    """Step 0: reproduce G2+carry / G2 exactly, else raise (stop)."""
    cc = json.loads(Path("research/tournament/oc_carrycompound/results.json").read_text())
    v = json.loads(Path("research/parallel/rounds/parallel-20260906-r2/v421/v421_result.json").read_text())["rows"]["R2B1D17BFG2"]
    g0, g25 = cc["rows"]["G2_f0.0"], cc["rows"]["G2_f0.25"]
    assert (g25["R"], g25["DD"], g25["full_path_dd"]["full"]) == (5.634, 16.75, 16.66), g25
    assert (g0["R"], g0["W"], g0["DD"]) == (v["R"], v["W"], v["DD"]), (g0, v)
    assert [y["R"] for y in g0["years"]] == [r for r, _ in v["years"]]
    assert [y["DD"] for y in g0["years"]] == [d for _, d in v["years"]]
    assert g0["full_path_dd"]["full"] == v["full_path_dd"]
    print("baseline OK: G2+carry 5.634/16.75/full16.66; f=0==v421 G2 to the digit", flush=True)
    return {"G2": {"R": g0["R"], "W": g0["W"], "DD": g0["DD"], "full": g0["full_path_dd"]["full"]},
            "G2_carry": {"R": g25["R"], "W": g25["W"], "DD": g25["DD"], "full": g25["full_path_dd"]["full"]},
            "carry_add_pp": cc["carry_add_pp_per_month"]}


def load_oc(sym: str):
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


def load_tape(sym: str, idx, first_month: str, last_month: str):
    """Per-minute taker buy/sell notional (float32, NaN = missing).

    first/last_month: 'YYYY-MM' file bounds (monthly files named
    SYM-aggTrades-YYYY-MM.parquet plus a few daily/weekly stragglers, which
    are included when they fall in range by filename comparison).
    """
    d = TAPE_DIR / sym
    files = sorted(d.glob("*.parquet"))
    keep = [f for f in files if first_month <= f.name[len(sym) + 11:len(sym) + 18] <= last_month]
    if not keep:
        raise SystemExit(f"no tape files for {sym} in [{first_month},{last_month}]")
    b_all, s_all, t_all = [], [], []
    for f in keep:
        df = pd.read_parquet(f)
        if not isinstance(df.index, pd.DatetimeIndex):
            raise SystemExit(f"tape index not time: {f}")
        if df.index.tz is None:
            df.index = df.index.tz_localize("UTC")
        else:
            df.index = df.index.tz_convert("UTC")
        bcols = [c for c in df.columns if c.startswith("buy_")]
        scols = [c for c in df.columns if c.startswith("sell_")]
        b_all.append(df[bcols].sum(axis=1))
        s_all.append(df[scols].sum(axis=1))
    b = pd.concat(b_all).sort_index()
    s = pd.concat(s_all).sort_index()
    b = b[~b.index.duplicated(keep="last")].reindex(idx)
    s = s[~s.index.duplicated(keep="last")].reindex(idx)
    return (b.to_numpy(dtype=np.float32), s.to_numpy(dtype=np.float32))


def year_of(t0):
    for i in range(5):
        lo = ANCHORS[i]
        hi = ANCHORS[i + 1] if i < 4 else YEAR_END
        if lo <= t0 < hi:
            return i
    return None


def build_grids(O, C, base_idx, n_all, phases, lo_time, hi_time, max_bars=None):
    grids = {}
    for p in phases:
        off = p * 60
        nb = (n_all - off) // 240
        t0 = base_idx[off:off + nb * 240:240]
        opens_bar, sig_bar = {}, {}
        for sym in MAJORS:
            ob = O[sym][off:off + nb * 240:240].astype(float)
            sg = pd.Series(ob).pct_change().rolling(360, min_periods=120).std(ddof=1).shift(1).to_numpy()
            opens_bar[sym], sig_bar[sym] = ob, sg
        js = [j for j in range(nb)
              if lo_time <= t0[j] < hi_time and (off + j * 240 + 240) < n_all]
        if max_bars is not None:
            js = js[:max_bars]
        grids[p] = dict(off=off, nb=nb, t0=t0, opens=opens_bar, sig=sig_bar, js=js)
    return grids


def sample_stats(buy, sell, base_idx, n_all, phases, hist_lo: pd.Timestamp, hist_hi: pd.Timestamp):
    """s30/s60 for all phase-grid opens in [hist_lo, hist_hi).

    Returns dict coin-agnostic: (opens_ns_sorted, s30_sorted, s60_sorted) for
    the caller coin (call per coin). Windows: offsets 17..46 / 17..76.
    """
    a1, b1 = T.WIN1
    a2, b2 = T.WIN2
    opens, ss30, ss60 = [], [], []
    for p in phases:
        off = p * 60
        nb = (n_all - off) // 240
        t0 = base_idx[off:off + nb * 240:240]
        for j in range(nb):
            bt = t0[j]
            if not (hist_lo <= bt < hist_hi):
                continue
            base = off + j * 240
            if base + b2 >= n_all:
                continue
            s30 = T.tape_sell_share(buy[base + a1:base + b1 + 1], sell[base + a1:base + b1 + 1])
            s60 = T.tape_sell_share(buy[base + a2:base + b2 + 1], sell[base + a2:base + b2 + 1])
            opens.append(bt.value)
            ss30.append(s30)
            ss60.append(s60)
    o = np.array(opens, dtype=np.int64)
    order = np.argsort(o, kind="stable")
    return o[order], np.array(ss30, dtype=float)[order], np.array(ss60, dtype=float)[order]


def process_stage(O, C, base_idx, n_all, coins, phases, lo_time, hi_time,
                  variants, tape_months, max_bars=None):
    """Replica fills + tape-cancel flags for bars with open in [lo, hi).

    variants: subset of {"C1","C2"} (stage B passes only the chosen one).
    Returns list of fill dicts (base fields + s30/q80/s60/q90/toxic flags).
    """
    grids = build_grids(O, C, base_idx, n_all, phases, lo_time, hi_time, max_bars)
    coin_ix = {s: i for i, s in enumerate(MAJORS)}
    rows = []
    for sym in coins:
        buy, sell = load_tape(sym, base_idx, *tape_months)
        # sample history must cover trailing-30d of the earliest bar here
        samp_o, samp30, samp60 = sample_stats(
            buy, sell, base_idx, n_all, phases,
            max(TAPE_HIST_START, lo_time - pd.Timedelta(days=35)), hi_time)
        H, L = load_hl(sym, base_idx)
        La, Ha = L, H
        Oa, Ca = O[sym], C[sym]
        others = [s for s in MAJORS if s != sym]
        for p in phases:
            g = grids[p]
            off, t0 = g["off"], g["t0"]
            opens_bar, sig_bar = g["opens"], g["sig"]
            n_fill = 0
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
                if yi is None:
                    continue
                a1, b1 = T.WIN1
                a2, b2 = T.WIN2
                s30 = T.tape_sell_share(buy[base + a1:base + b1 + 1], sell[base + a1:base + b1 + 1])
                s60 = T.tape_sell_share(buy[base + a2:base + b2 + 1], sell[base + a2:base + b2 + 1])
                q80 = T.trailing_quantile(samp_o, samp30, bt.value, 0.80)
                q90 = T.trailing_quantile(samp_o, samp60, bt.value, 0.90)
                tox1 = bool(np.isfinite(s30) and np.isfinite(q80) and s30 > q80)
                tox2 = bool(np.isfinite(s60) and np.isfinite(q90) and s60 > q90)
                low_win = La[base + T.LIVE_A:base + T.LIVE_B + 1].astype(float)
                cmat = np.stack([C[b][base + T.LIVE_A - 1:base + T.LIVE_B].astype(float)
                                 for b in others])
                oo = np.array([opens_bar[b][j] for b in others], dtype=float)
                ss = np.array([sig_bar[b][j] for b in others], dtype=float)
                nvec = T.n_vector(cmat, oo, ss)
                Ha_b = Ha[base:base + 240].astype(float)
                La_b = La[base:base + 240].astype(float)
                Ca_b = Ca[base:base + 240].astype(float)
                Oa_b = Oa[base:base + 240].astype(float)
                for ri, k in enumerate(T.RUNGS):
                    lv = o1 * (1 - k * sg)
                    if not np.isfinite(lv) or lv <= 0:
                        continue
                    ib = T.find_fill(low_win, lv)
                    if ib is None:
                        continue
                    f = T.LIVE_A + ib
                    nf = int(nvec[ib])
                    ret, x, how = T.outcome_from_fill(Ha_b, La_b, Ca_b, Oa_b, f, lv, sg, o2, settle)
                    if not np.isfinite(ret):
                        continue
                    n_fill += 1
                    xd = T.exit_day_iso(bt, int(x))
                    row = dict(phase=p, coin=coin_ix[sym], year=yi,
                               bar=off + j * 240, k_ix=ri, k=float(k),
                               f=int(f), x=int(x), w=float(T.size_mult(nf)),
                               ret=float(ret), how=how, xd=xd, t_bar=bt,
                               s30=float(s30), q80=float(q80),
                               s60=float(s60), q90=float(q90))
                    if "C1" in variants:
                        row["cancel_C1"] = bool("C1" in variants and tox1 and f > T.CANCEL1_MIN)
                    if "C2" in variants:
                        row["cancel_C2"] = bool("C2" in variants and tox2 and f > T.CANCEL2_MIN)
                    rows.append(row)
            print(f"{sym} p{p}: fills={n_fill} [{lo_time.date()},{hi_time.date()})", flush=True)
        del H, L, La, Ha, buy, sell
    return rows


def apply_cap(df, arms):
    """G-cap walks per (phase,bar) for base + variant subset pools."""
    df["key"] = (df["phase"].astype(str) + "|" + df["bar"].astype(str) + "|" +
                 df["coin"].astype(str) + "|" + df["k_ix"].astype(str))
    for arm in arms:
        df[f"wk_{arm}"] = 0.0
    for (p, b), g in df.groupby(["phase", "bar"], sort=False):
        idx = g.index.to_numpy()
        f = g["f"].to_numpy()
        x = g["x"].to_numpy()
        w = g["w"].to_numpy()
        kk = g["k_ix"].to_numpy()
        cc = g["coin"].to_numpy()
        order = sorted(range(len(g)), key=lambda t: (int(f[t]), int(kk[t]), int(cc[t])))
        kept = T.gross_cap_weights(f, x, w, order)
        for t, pos in enumerate(idx):
            df.at[pos, f"wk_base"] = float(kept[t])
        for arm, ccol, kmin in (("C1", "cancel_C1", T.CANCEL1_MIN),
                                ("C2", "cancel_C2", T.CANCEL2_MIN)):
            if arm not in arms:
                continue
            sub = [t for t in range(len(g)) if not bool(g.iloc[t][ccol])]
            if sub:
                sub_order = sorted(sub, key=lambda t: (int(f[t]), int(kk[t]), int(cc[t])))
                kept_v = T.gross_cap_weights(f, x, w, sub_order)
                for t in sub:
                    df.at[idx[t], f"wk_{arm}"] = float(kept_v[t])
    return df


def score_cells(df, arms, phases, years):
    cells = {}
    for arm in arms:
        for p in phases:
            for y in years:
                m = (df["phase"] == p) & (df["year"] == y) & (df[f"wk_{arm}"] > 0)
                sub = df[m]
                n = int(len(sub))
                if n:
                    wy = sub[f"wk_{arm}"].to_numpy(float) * sub["ret"].to_numpy(float)
                    S, Wd, DD, nd = T.cell_stats_dict(sub["xd"].to_numpy(), wy)
                    win = float((sub["ret"].to_numpy(float) > 0).mean())
                else:
                    S, Wd, DD, nd, win = 0.0, 0.0, 0.0, 0, 0.0
                cells[(arm, p, y)] = dict(n=n, S=S, W=Wd, DD=DD, ndays=nd, win=win)
    return cells


def summarize_years(df, cells, arms, years, phases):
    per_year = {arm: [] for arm in arms}
    for arm in arms:
        for y in years:
            Sb = [cells[("base", p, y)]["S"] for p in phases]
            Db = [cells[("base", p, y)]["DD"] for p in phases]
            Wb = [cells[("base", p, y)]["W"] for p in phases]
            rec = {"year": ANCHORS[y].date().isoformat(),
                   "S_bar_base": round(float(np.mean(Sb)), 6),
                   "DD_bar_base": round(float(np.mean(Db)), 6),
                   "W_bar_base": round(float(np.mean(Wb)), 6),
                   "n_bar_base": round(float(np.mean([cells[('base', p, y)]["n"] for p in phases])), 2),
                   "win_bar_base": round(float(np.mean([cells[('base', p, y)]["win"] for p in phases])), 6),
                   "per_phase_S_base": [round(v, 6) for v in Sb],
                   "per_phase_DD_base": [round(v, 6) for v in Db]}
            for v in arms:
                if v == "base":
                    continue
                Sv = [cells[(v, p, y)]["S"] for p in phases]
                Dv = [cells[(v, p, y)]["DD"] for p in phases]
                Wv = [cells[(v, p, y)]["W"] for p in phases]
                rec[f"S_bar_{v}"] = round(float(np.mean(Sv)), 6)
                rec[f"DD_bar_{v}"] = round(float(np.mean(Dv)), 6)
                rec[f"W_bar_{v}"] = round(float(np.mean(Wv)), 6)
                rec[f"n_bar_{v}"] = round(float(np.mean([cells[(v, p, y)]["n"] for p in phases])), 2)
                rec[f"win_bar_{v}"] = round(float(np.mean([cells[(v, p, y)]["win"] for p in phases])), 6)
                rec[f"per_phase_S_{v}"] = [round(x, 6) for x in Sv]
                rec[f"per_phase_DD_{v}"] = [round(x, 6) for x in Dv]
                rec[f"delta_S_bar_{v}"] = round(float(np.mean(Sv) - np.mean(Sb)), 6)
                rec[f"dDD_bar_{v}"] = round(float(np.mean(Dv) - np.mean(Db)), 6)
                rec[f"pass_sum_{v}"] = bool(np.mean(Sv) >= np.mean(Sb))
                rec[f"pass_dd_{v}"] = bool(np.mean(Dv) <= np.mean(Db) + 0.01)
            per_year[arm].append(rec)
    # NOTE per_year keyed by arm but each rec holds all arms; return base list
    return per_year["base"]


def lost_extra(df, arm, ccol, years, phases):
    out = {}
    base_keys = set(df[df["wk_base"] > 0]["key"].tolist())
    for y in years:
        ln, lrets, lw = [], [], []
        for p in phases:
            m = (df["phase"] == p) & (df["year"] == y) & (df["wk_base"] > 0) & (df[ccol])
            s = df[m]
            ln.append(int(len(s)))
            lw.append(float((s["wk_base"] * s["ret"]).sum()) if len(s) else 0.0)
            lrets.extend(s["ret"].tolist())
        me = (df["year"] == y) & (df[f"wk_{arm}"] > 0)
        exn, exs = [], []
        for p in phases:
            s = df[me & (df["phase"] == p)]
            new = s[~s["key"].isin(base_keys)]
            exn.append(int(len(new)))
            exs.append(float((new[f"wk_{arm}"] * new["ret"]).sum()) if len(new) else 0.0)
        out[y] = {"lost_n_total": int(sum(ln)),
                  "lost_win": round(float(np.mean([r > 0 for r in lrets])) if lrets else 0.0, 6),
                  "lost_sum_total": round(float(sum(lw)), 6),
                  "extra_n_total": int(sum(exn)),
                  "extra_sum_total": round(float(sum(exs)), 6)}
    return out


def pooled(df, wcol):
    sub = df[df[wcol] > 0]
    wy = sub[wcol].to_numpy(float) * sub["ret"].to_numpy(float)
    S, Wd, DD, nd = T.cell_stats_dict(sub["xd"].to_numpy(), wy)
    return {"n": int(len(sub)), "sum": round(float(S), 6),
            "worst_day": round(float(Wd), 6), "max_dd": round(float(DD), 6),
            "ndays": int(nd),
            "win": round(float((sub["ret"].to_numpy(float) > 0).mean()) if len(sub) else 0.0, 6)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    args = ap.parse_args()

    baseline = check_baseline()
    coins = ("BTCUSDT",) if args.smoke else MAJORS
    phases = (0,) if args.smoke else PHASES

    O, C, base_idx = {}, {}, None
    for sym in MAJORS:
        ii, o, c = load_oc(sym)
        base_idx = ii if base_idx is None else base_idx
        O[sym], C[sym] = o, c
        print(f"loaded OC {sym}", flush=True)
    n_all = len(base_idx)

    # ---------------- Stage A: dev4 ----------------
    rowsA = process_stage(O, C, base_idx, n_all, coins, phases,
                          TRADE_START, SPLIT, ("C1", "C2"),
                          ("2020-01", "2025-09"),
                          max_bars=300 if args.smoke else None)
    dfA = pd.DataFrame(rowsA)
    if len(dfA) == 0:
        raise SystemExit("empty stage-A ledger")
    arms = ["base", "C1", "C2"]
    dfA = apply_cap(dfA, arms)
    dev_years = [0, 1, 2, 3]
    cellsA = score_cells(dfA, arms, phases, dev_years)
    perA = summarize_years(dfA, cellsA, arms, dev_years, phases)

    # uncapped side row (raw w*y 4-phase means, dev4)
    uncA = {}
    for y in dev_years:
        for arm, m in (("base", dfA["w"] > 0), ("C1", ~dfA["cancel_C1"]), ("C2", ~dfA["cancel_C2"])):
            sub = dfA[(dfA["year"] == y) & m]
            ss = [float(((sub[sub["phase"] == p])["w"] * (sub[sub["phase"] == p])["ret"]).sum())
                  if len(sub[sub["phase"] == p]) else 0.0 for p in phases]
            uncA[(arm, y)] = (float(np.mean(ss)), [float(v) for v in ss])

    # fidelity: phase-0 uncapped base raw sums vs oc_placebo_dip ref (dev4)
    if not args.smoke:
        got_p0 = [uncA[("base", y)][1][0] for y in dev_years]
        ref_p0 = PLACEBO_REF_P0[:4]
        assert all(abs(g - r) < 1e-6 for g, r in zip(got_p0, ref_p0)), (got_p0, ref_p0)
        print(f"fidelity OK: phase0 dev4 uncapped base = {[round(v,6) for v in got_p0]}", flush=True)
    n_cand_A = int(len(dfA))

    # dev4 selection (pre-registered robust rule on dev4 ONLY)
    stats = {}
    for v in ("C1", "C2"):
        dsum = sum(r[f"delta_S_bar_{v}"] for r in perA)
        wdeltas = [r[f"delta_S_bar_{v}"] for r in perA]
        n_sum = sum(1 for r in perA if r[f"pass_sum_{v}"])
        n_dd = sum(1 for r in perA if r[f"pass_dd_{v}"])
        stats[v] = {"dSum_dev4": round(float(dsum), 6),
                    "worst_delta_dev4": round(float(min(wdeltas)), 6),
                    "years_sum_ge": int(n_sum), "years_dd_ok": int(n_dd),
                    "eligible": bool(n_dd == 4 and n_sum >= 3)}
    elig = [v for v in ("C1", "C2") if stats[v]["eligible"]]
    chosen = T.choose_variant({v: {"years_sum_ge": stats[v]["years_sum_ge"],
                                    "years_dd_ok": stats[v]["years_dd_ok"],
                                    "worst_delta_dev4": stats[v]["worst_delta_dev4"],
                                    "dSum_dev4": stats[v]["dSum_dev4"]}
                               for v in ("C1", "C2")})
    assert (chosen in elig) if elig else (chosen is None)
    print(json.dumps({"dev4_stats": stats, "chosen": chosen}, indent=1), flush=True)

    result = {"config": {
        "idea": "IDEAS2_20261007 §3 tape-contingent dip-bid cancel",
        "variants": {"C1": "cancel unfilled at +30m (f>46) iff s30>q80 trailing-30d",
                     "C2": "cancel unfilled at +60m (f>76) iff s60>q90 trailing-30d"},
        "replica": "oc_bidttl-exact (majors x R2, B1 sizes, D0 exits, live 16..238, maker 0.0002/taker 0.00055, v293 settle funding)",
        "cap": "v421-style G=2.0 walk per (phase,bar), order (f,k,coin)",
        "tape": "data/raw/aggflow_20260929_orders_1m (Binance aggTrades taker buy/sell notional, no re-download)",
        "gate": "PROMISING iff 5y sum>=base 4/5 AND DD<=base+0.01 4/5 AND dSum5y>=+0.273; engine only if PROMISING",
        "selection": "dev4-only robust: eligible iff dd-ok 4/4 and sum-pass >=3/4; pick highest dev4 WORST-year delta, tie -> higher dev4 mean delta; 2025 scored once for chosen only, POST-HOC"},
        "baseline": baseline,
        "n_candidates_dev4": n_cand_A,
        "ledger_checksum_dev4": hashlib.sha256(
            np.round(dfA[["w", "ret", "wk_base", "wk_C1", "wk_C2"]].to_numpy(), 9).tobytes()).hexdigest()[:16],
        "phase0_uncapped_fidelity_dev4": {
            "got_raw_sums": [round(v, 6) for v in ([uncA[('base', y)][1][0] for y in dev_years] if not args.smoke else [])],
            "oc_placebo_dip_ref": PLACEBO_REF_P0[:4]},
        "dev4_per_year": perA,
        "dev4_stats": stats,
        "chosen": chosen}

    for v, ccol in (("C1", "cancel_C1"), ("C2", "cancel_C2")):
        le = lost_extra(dfA, v, ccol, dev_years, phases)
        for r in perA:
            y = ANCHORS.index(pd.Timestamp(r["year"], tz="UTC"))
            r[f"lost_{v}"] = le[y]
        result[f"dev4_full_C1" if v == "C1" else f"dev4_full_C2"] = pooled(dfA, f"wk_{v}")
    result["dev4_full_base"] = pooled(dfA, "wk_base")

    if args.smoke:
        print(json.dumps({"n": len(dfA), "stats": stats, "chosen": chosen}, indent=1))
        return

    dfA.to_parquet(HERE / "fills_dev4.parquet", index=False)

    # ---------------- Stage B: 2025 once for the chosen variant only ----------------
    if chosen is None:
        result["stage_B_2025"] = None
        result["decision"] = {"promising": False, "reason": "no dev-eligible variant (need dd-ok 4/4 and sum-pass >=3/4 on 2021-2024); both rejected on dev4; 2025 unscored; no engine"}
        result["engine"] = None
    else:
        ccol = "cancel_C1" if chosen == "C1" else "cancel_C2"
        rowsB = process_stage(O, C, base_idx, n_all, MAJORS, PHASES,
                              SPLIT, YEAR_END, (chosen,),
                              ("2025-08", "2026-09"))
        dfB = pd.DataFrame(rowsB)
        dfB["key"] = (dfB["phase"].astype(str) + "|" + dfB["bar"].astype(str) + "|" +
                      dfB["coin"].astype(str) + "|" + dfB["k_ix"].astype(str))
        armsB = ["base", chosen]
        dfB = apply_cap(dfB, armsB)
        cellsB = score_cells(dfB, armsB, PHASES, [4])
        perB = summarize_years(dfB, cellsB, armsB, [4], PHASES)
        le = lost_extra(dfB, chosen, ccol, [4], PHASES)
        perB[0][f"lost_{chosen}"] = le[4]
        # fidelity on 2025 phase-0
        sub = dfB[(dfB["year"] == 4)]
        ss = [float(((sub[sub["phase"] == p])["w"] * (sub[sub["phase"] == p])["ret"]).sum())
              if len(sub[sub["phase"] == p]) else 0.0 for p in PHASES]
        assert abs(ss[0] - PLACEBO_REF_P0[4]) < 1e-6, (ss[0], PLACEBO_REF_P0[4])
        print(f"fidelity OK: phase0 2025 uncapped base = {ss[0]:.6f}", flush=True)
        dfB.to_parquet(HERE / "fills_2025.parquet", index=False)
        assert int(len(dfA)) + int(len(dfB)) == 22312, (len(dfA), len(dfB))

        # 5y joint legs for the chosen variant (2025 labelled POST-HOC)
        all_per = perA + perB
        # rebuild rec with both arms for year 4: summarize_years already did
        n_sum5 = sum(1 for r in perA if r[f"pass_sum_{chosen}"]) + (1 if perB[0][f"pass_sum_{chosen}"] else 0)
        n_dd5 = sum(1 for r in perA if r[f"pass_dd_{chosen}"]) + (1 if perB[0][f"pass_dd_{chosen}"] else 0)
        dsum5 = round(sum(r[f"delta_S_bar_{chosen}"] for r in perA) + perB[0][f"delta_S_bar_{chosen}"], 6)
        promising = bool(n_sum5 >= 4 and n_dd5 >= 4 and dsum5 >= PLACEBO_GATE)
        result["stage_B_2025"] = {"note": "POST-HOC: 2025-09-24..2026-09-23 scored once, chosen variant only",
                                  "per_year": perB,
                                  "full_base_2025": pooled(dfB, "wk_base"),
                                  f"full_{chosen}_2025": pooled(dfB, f"wk_{chosen}")}
        result["five_year_chosen"] = {"years_sum_ge": int(n_sum5), "years_dd_ok": int(n_dd5),
                                      "dSum5y": float(dsum5), "gate": PLACEBO_GATE,
                                      "promising": promising}
        result["decision"] = {"promising": promising,
                              "reason": f"chosen={chosen} 5y sum {n_sum5}/5, dd {n_dd5}/5, dSum5y {dsum5:+.4f} vs +0.273"}
        result["engine"] = None  # filled only if promising (not expected)

    (HERE / "results.json").write_text(json.dumps(result, indent=1))
    print(json.dumps({"chosen": chosen, "decision": result["decision"]}, indent=1))


if __name__ == "__main__":
    main()
