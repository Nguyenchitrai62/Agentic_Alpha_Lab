"""oc_bidttl run: base (live 16..238) vs TTL (live 16..135) dip replica + B1 + G-cap.

One process; all-five-coins 1m O/C float32 + one-coin H/L at a time.
See PLAN.md for frozen definitions. RAM < 3 GB.
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

import bidttl as B

START = pd.Timestamp("2020-08-01", tz="UTC")
END = pd.Timestamp("2026-09-24 00:00", tz="UTC")
TRADE_START = pd.Timestamp("2021-09-24 00:00", tz="UTC")
YEAR_END = pd.Timestamp("2026-09-24 00:00", tz="UTC")
MAJORS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
ANCHORS = [pd.Timestamp(a, tz="UTC") for a in
           ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")]
PHASES = (0, 1, 2, 3)
SETTLE_HOURS = (0, 8, 16)
W = B.LIVE_B - B.LIVE_A + 1  # 223
W_TTL = B.TTL_B - B.LIVE_A + 1  # 120


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


def year_of(t0):
    for i in range(5):
        lo = ANCHORS[i]
        hi = ANCHORS[i + 1] if i < 4 else YEAR_END
        if lo <= t0 < hi:
            return i
    return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true",
                    help="test-only: 1 coin, phase 0, first 300 traded bars")
    args = ap.parse_args()

    coins = ("BTCUSDT",) if args.smoke else MAJORS
    phases = (0,) if args.smoke else PHASES

    O, C, base_idx = {}, {}, None
    for sym in MAJORS:
        ii, o, c = load_oc(sym)
        base_idx = ii if base_idx is None else base_idx
        O[sym], C[sym] = o, c
        print(f"loaded OC {sym}", flush=True)
    n_all = len(base_idx)

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
              if TRADE_START <= t0[j] < YEAR_END and (off + j * 240 + 240) < n_all]
        if args.smoke:
            js = js[:300]
        grids[p] = dict(off=off, nb=nb, t0=t0, opens=opens_bar, sig=sig_bar, js=js)
        print(f"phase {p}: nb={nb} traded={len(js)}", flush=True)

    coin_ix = {s: i for i, s in enumerate(MAJORS)}
    rows = []
    for sym in coins:
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
                low_win = La[base + B.LIVE_A:base + B.LIVE_B + 1].astype(float)
                cmat = np.stack([C[b][base + B.LIVE_A - 1:base + B.LIVE_B].astype(float)
                                 for b in others])
                oo = np.array([opens_bar[b][j] for b in others], dtype=float)
                ss = np.array([sig_bar[b][j] for b in others], dtype=float)
                nvec = B.n_vector(cmat, oo, ss)
                Ha_b = Ha[base:base + 240].astype(float)
                La_b = La[base:base + 240].astype(float)
                Ca_b = Ca[base:base + 240].astype(float)
                Oa_b = Oa[base:base + 240].astype(float)
                for ri, k in enumerate(B.RUNGS):
                    lv = o1 * (1 - k * sg)
                    if not np.isfinite(lv) or lv <= 0:
                        continue
                    ib = B.find_fill(low_win, lv)
                    if ib is None:
                        continue
                    f = B.LIVE_A + ib
                    nf = int(nvec[ib])
                    ret, x, how = B.outcome_from_fill(Ha_b, La_b, Ca_b, Oa_b, f, lv, sg, o2, settle)
                    if not np.isfinite(ret):
                        continue
                    n_fill += 1
                    xd = B.exit_day_iso(bt, int(x))
                    rows.append(dict(phase=p, coin=coin_ix[sym], year=yi,
                                     bar=off + j * 240, k_ix=ri, k=float(k),
                                     f=int(f), x=int(x), w=float(B.size_mult(nf)),
                                     ret=float(ret), how=how, xd=xd,
                                     t_bar=bt))
            print(f"{sym} p{p}: fills={n_fill}", flush=True)
        del H, L, La, Ha
    # free 1m OC arrays before scoring
    del O, C

    df = pd.DataFrame(rows)
    if len(df) == 0:
        raise SystemExit("empty ledger")
    df["ttl_cand"] = df["f"] <= B.TTL_B
    df["key"] = (df["phase"].astype(str) + "|" + df["bar"].astype(str) + "|" +
                 df["coin"].astype(str) + "|" + df["k_ix"].astype(str))

    # --- G-cap walks per (phase, bar): base pool + TTL pool (subset) ---
    df["wk_base"] = 0.0
    df["wk_ttl"] = 0.0
    for (p, b), g in df.groupby(["phase", "bar"], sort=False):
        idx = g.index.to_numpy()
        f = g["f"].to_numpy()
        x = g["x"].to_numpy()
        w = g["w"].to_numpy()
        kk = g["k_ix"].to_numpy()
        cc = g["coin"].to_numpy()
        order = sorted(range(len(g)), key=lambda t: (int(f[t]), int(kk[t]), int(cc[t])))
        kept = B.gross_cap_weights(f, x, w, order)
        for t, pos in enumerate(idx):
            df.at[pos, "wk_base"] = float(kept[t])
        sub = [t for t in range(len(g)) if int(f[t]) <= B.TTL_B]
        if sub:
            sub_order = sorted(sub, key=lambda t: (int(f[t]), int(kk[t]), int(cc[t])))
            kept_t = B.gross_cap_weights(f, x, w, sub_order)
            for t in sub:
                df.at[idx[t], "wk_ttl"] = float(kept_t[t])

    def score_cells(frame, wcol):
        # per (phase, year) cells + pooled path
        cells = {}
        for p in phases:
            for y in range(5):
                m = (frame["phase"] == p) & (frame["year"] == y) & (frame[wcol] > 0)
                sub = frame[m]
                n = int(len(sub))
                if n:
                    wy = sub[wcol].to_numpy(float) * sub["ret"].to_numpy(float)
                    S, Wd, DD, nd = B.cell_stats_dict(sub["xd"].to_numpy(), wy)
                    win = float((sub["ret"].to_numpy(float) > 0).mean())
                else:
                    S, Wd, DD, nd, win = 0.0, 0.0, 0.0, 0, 0.0
                cells[(p, y)] = dict(n=n, S=S, W=Wd, DD=DD, ndays=nd, win=win)
        return cells

    cells_base = score_cells(df, "wk_base")
    cells_ttl = score_cells(df, "wk_ttl")

    # uncapped side row (raw w*y, TTL subset)
    def score_uncapped():
        out = {}
        for y in range(5):
            for arm, m in (("base", df["w"] > 0),
                           ("ttl", df["ttl_cand"])):
                sub = df[(df["year"] == y) & m]
                ss = []
                for p in phases:
                    s = sub[sub["phase"] == p]
                    ss.append(float((s["w"] * s["ret"]).sum()) if len(s) else 0.0)
                out[(arm, y)] = (float(np.mean(ss)), [float(v) for v in ss])
        return out

    unc = score_uncapped()

    per_year = []
    dsum5y = 0.0
    for y in range(5):
        Sb = [cells_base[(p, y)]["S"] for p in phases]
        St = [cells_ttl[(p, y)]["S"] for p in phases]
        Db = [cells_base[(p, y)]["DD"] for p in phases]
        Dt = [cells_ttl[(p, y)]["DD"] for p in phases]
        Wb = [cells_base[(p, y)]["W"] for p in phases]
        Wt = [cells_ttl[(p, y)]["W"] for p in phases]
        S_bar_b, S_bar_t = float(np.mean(Sb)), float(np.mean(St))
        DD_bar_b, DD_bar_t = float(np.mean(Db)), float(np.mean(Dt))
        W_bar_b, W_bar_t = float(np.mean(Wb)), float(np.mean(Wt))
        dsum5y += S_bar_t - S_bar_b
        # lost: base-kept late fills (f>=136), per-phase then mean
        lost_n, lost_wsum, lost_wy = [], [], []
        lost_rets = []
        for p in phases:
            m = (df["phase"] == p) & (df["year"] == y) & (df["wk_base"] > 0) & (df["f"] > B.TTL_B)
            s = df[m]
            lost_n.append(int(len(s)))
            lost_wsum.append(float((s["wk_base"] * s["ret"]).sum()) if len(s) else 0.0)
            lost_rets.extend(s["ret"].tolist())
        # extra: TTL-kept fills whose key not in base-kept set
        base_keys = set(df[(df["year"] == y) & (df["wk_base"] > 0)]["key"].tolist())
        me = (df["year"] == y) & (df["wk_ttl"] > 0)
        ex_sum_by_p, ex_n_by_p = [], []
        for p in phases:
            s = df[me & (df["phase"] == p)]
            new = s[~s["key"].isin(base_keys)]
            ex_n_by_p.append(int(len(new)))
            ex_sum_by_p.append(float((new["wk_ttl"] * new["ret"]).sum()) if len(new) else 0.0)
        per_year.append({
            "year": ANCHORS[y].date().isoformat(),
            "S_bar_base": round(S_bar_b, 6), "S_bar_ttl": round(S_bar_t, 6),
            "delta_S_bar": round(S_bar_t - S_bar_b, 6),
            "DD_bar_base": round(DD_bar_b, 6), "DD_bar_ttl": round(DD_bar_t, 6),
            "dDD_bar": round(DD_bar_t - DD_bar_b, 6),
            "W_bar_base": round(W_bar_b, 6), "W_bar_ttl": round(W_bar_t, 6),
            "n_bar_base": round(float(np.mean([cells_base[(p, y)]["n"] for p in phases])), 2),
            "n_bar_ttl": round(float(np.mean([cells_ttl[(p, y)]["n"] for p in phases])), 2),
            "win_bar_base": round(float(np.mean([cells_base[(p, y)]["win"] for p in phases])), 6),
            "win_bar_ttl": round(float(np.mean([cells_ttl[(p, y)]["win"] for p in phases])), 6),
            "per_phase_S_base": [round(v, 6) for v in Sb],
            "per_phase_S_ttl": [round(v, 6) for v in St],
            "per_phase_DD_base": [round(v, 6) for v in Db],
            "per_phase_DD_ttl": [round(v, 6) for v in Dt],
            "lost_n_bar": round(float(np.mean(lost_n)), 2),
            "lost_n_total": int(sum(lost_n)),
            "lost_win": round(float(np.mean([r > 0 for r in lost_rets])) if lost_rets else 0.0, 6),
            "lost_sum_bar": round(float(np.mean(lost_wsum)), 6),
            "lost_sum_total": round(float(sum(lost_wsum)), 6),
            "extra_n_bar": round(float(np.mean(ex_n_by_p)), 2),
            "extra_n_total": int(sum(ex_n_by_p)),
            "extra_sum_bar": round(float(np.mean(ex_sum_by_p)), 6),
            "extra_sum_total": round(float(sum(ex_sum_by_p)), 6),
            "uncapped_S_bar_base": round(unc[("base", y)][0], 6),
            "uncapped_S_bar_ttl": round(unc[("ttl", y)][0], 6),
            "pass_sum": bool(S_bar_t >= S_bar_b),
            "pass_dd": bool(DD_bar_t <= DD_bar_b + 0.01),
        })

    # pooled full paths (all phases together, cap-adjusted)
    def pooled(wcol):
        sub = df[df[wcol] > 0]
        wy = (sub[wcol].to_numpy(float) * sub["ret"].to_numpy(float))
        S, Wd, DD, nd = B.cell_stats_dict(sub["xd"].to_numpy(), wy)
        return {"n": int(len(sub)), "sum": round(float(S), 6),
                "worst_day": round(float(Wd), 6), "max_dd": round(float(DD), 6),
                "ndays": int(nd),
                "win": round(float((sub["ret"].to_numpy(float) > 0).mean()) if len(sub) else 0.0, 6)}

    full = {"base": pooled("wk_base"), "ttl": pooled("wk_ttl")}
    n_sum = sum(1 for r in per_year if r["pass_sum"])
    n_dd = sum(1 for r in per_year if r["pass_dd"])
    decision = {"years_sum_ge": int(n_sum), "years_dd_ok": int(n_dd),
                "dSum5y": round(float(dsum5y), 6),
                "dSum5y_gate": 0.273,
                "promising": bool(n_sum >= 4 and n_dd >= 4 and dsum5y >= 0.273)}

    # fidelity: phase-0 uncapped base raw sums vs placebo ref
    ref = [2.388052, 0.182865, 3.809764, 2.579274, 0.711509]
    got = [unc[("base", y)][1][0] for y in range(5)] if not args.smoke else []
    chk = hashlib.sha256(
        np.round(df[["w", "ret", "wk_base", "wk_ttl"]].to_numpy(), 9).tobytes()).hexdigest()[:16]
    out = {"config": {
        "coins": list(coins), "rungs": list(B.RUNGS),
        "bars": "open in [2021-09-24, 2026-09-24)",
        "grid": "4h from 2020-08-01 00:00 UTC + 0/1/2/3h",
        "live_base": [B.LIVE_A, B.LIVE_B], "live_ttl": [B.LIVE_A, B.TTL_B],
        "ttl_rule": "bid still unfilled at minute 136 (120 min after window opens at 16) cancelled, no replacement same bar; fills unchanged",
        "maker": B.MAKER, "taker": B.TAKER, "fund_long": 0.0001,
        "settle_hours": list(SETTLE_HOURS),
        "sizes": "B1 w=1/(1+n_fill), v399-exact n",
        "exits": "D0 replica from lv (TP=lv*(1+sg), sl 4sg close5, bl 8sg, timeout next open)",
        "cap": "v421-style G=2.0 walk per (phase,bar), order (f,k,coin), cut to room, skip when full; equity=1 constant; open+new<=G; D0 exits<=240 so per-bar pools independent",
        "pairing": "kept only if single D0 leg finite (base and TTL identically)",
        "scoring": "PRIMARY cap-adjusted wk*y daily sums by exit date UTC; 4-phase means; DD of cumsum path from 0 (>=0)",
        "criterion": "PROMISING iff sum>=base in >=4/5y AND DD<=base+0.01 in >=4/5y AND 5y sum delta>=+0.273",
        "resources": "one process, majors 1m O/C float32 + one-coin H/L"},
        "n_candidates": int(len(df)),
        "n_base_kept": int((df["wk_base"] > 0).sum()),
        "n_ttl_kept": int((df["wk_ttl"] > 0).sum()),
        "ledger_checksum": chk,
        "phase0_uncapped_fidelity": {
            "got_raw_sums": [round(v, 6) for v in got],
            "oc_placebo_dip_ref": ref,
            "note": "same replica+B1 sizes; pairing differs (here single D0 leg vs placebo 3 TP legs)"},
        "per_year": per_year, "full": full, "decision": decision}
    if args.smoke:
        print(json.dumps({"n": len(df), "decision": decision,
                          "per_year": [(r["year"], r["S_bar_base"], r["S_bar_ttl"]) for r in per_year]}, indent=1))
        return
    (HERE / "results.json").write_text(json.dumps(out, indent=1))
    df.to_parquet(HERE / "fills.parquet", index=False)
    print("n_candidates", len(df), "base_kept", int((df["wk_base"] > 0).sum()),
          "ttl_kept", int((df["wk_ttl"] > 0).sum()), "checksum", chk, flush=True)
    print(json.dumps(decision, indent=1))


if __name__ == "__main__":
    main()
