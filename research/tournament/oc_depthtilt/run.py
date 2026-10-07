"""oc_depthtilt run: base B1 vs depth-tilted dip sizing + G-cap (idea #78).

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

import depthtilt as D

START = pd.Timestamp("2020-08-01", tz="UTC")
END = pd.Timestamp("2026-09-24 00:00", tz="UTC")
TRADE_START = pd.Timestamp("2021-09-24 00:00", tz="UTC")
YEAR_END = pd.Timestamp("2026-09-24 00:00", tz="UTC")
MAJORS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
ANCHORS = [pd.Timestamp(a, tz="UTC") for a in
           ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")]
PHASES = (0, 1, 2, 3)
SETTLE_HOURS = (0, 8, 16)
DD_TOL = 0.01
GATE_DSUM = 0.273


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
                low_win = La[base + D.LIVE_A:base + D.LIVE_B + 1].astype(float)
                cmat = np.stack([C[b][base + D.LIVE_A - 1:base + D.LIVE_B].astype(float)
                                 for b in others])
                oo = np.array([opens_bar[b][j] for b in others], dtype=float)
                ss = np.array([sig_bar[b][j] for b in others], dtype=float)
                nvec = D.n_vector(cmat, oo, ss)
                Ha_b = Ha[base:base + 240].astype(float)
                La_b = La[base:base + 240].astype(float)
                Ca_b = Ca[base:base + 240].astype(float)
                Oa_b = Oa[base:base + 240].astype(float)
                for ri, k in enumerate(D.RUNGS):
                    lv = o1 * (1 - k * sg)
                    if not np.isfinite(lv) or lv <= 0:
                        continue
                    ib = D.find_fill(low_win, lv)
                    if ib is None:
                        continue
                    f = D.LIVE_A + ib
                    nf = int(nvec[ib])
                    ret, x, how = D.outcome_from_fill(Ha_b, La_b, Ca_b, Oa_b, f, lv, sg, o2, settle)
                    if not np.isfinite(ret):
                        continue
                    n_fill += 1
                    xd = D.exit_day_iso(bt, int(x))
                    wb = float(D.size_mult(nf))
                    wr = float(D.rule_weight(nf, float(k)))
                    rows.append(dict(phase=p, coin=coin_ix[sym], year=yi,
                                     bar=off + j * 240, k_ix=ri, k=float(k),
                                     f=int(f), x=int(x), n_fill=nf,
                                     w_base=wb, w_rule=wr,
                                     ret=float(ret), how=how, xd=xd,
                                     t_bar=bt))
            print(f"{sym} p{p}: fills={n_fill}", flush=True)
        del H, L, La, Ha
    del O, C

    df = pd.DataFrame(rows)
    if len(df) == 0:
        raise SystemExit("empty ledger")
    df["key"] = (df["phase"].astype(str) + "|" + df["bar"].astype(str) + "|" +
                 df["coin"].astype(str) + "|" + df["k_ix"].astype(str))

    # --- G-cap walks per (phase, bar): base pool (w_base) + rule pool (w_rule) ---
    df["wk_base"] = 0.0
    df["wk_rule"] = 0.0
    for (p, b), g in df.groupby(["phase", "bar"], sort=False):
        idx = g.index.to_numpy()
        f = g["f"].to_numpy()
        x = g["x"].to_numpy()
        kk = g["k_ix"].to_numpy()
        cc = g["coin"].to_numpy()
        order = sorted(range(len(g)), key=lambda t: (int(f[t]), int(kk[t]), int(cc[t])))
        kept_b = D.gross_cap_weights(f, x, g["w_base"].to_numpy(), order)
        kept_r = D.gross_cap_weights(f, x, g["w_rule"].to_numpy(), order)
        for t, pos in enumerate(idx):
            df.at[pos, "wk_base"] = float(kept_b[t])
            df.at[pos, "wk_rule"] = float(kept_r[t])

    def score_cells(wcol):
        cells = {}
        for p in phases:
            for y in range(5):
                m = (df["phase"] == p) & (df["year"] == y) & (df[wcol] > 0)
                sub = df[m]
                n = int(len(sub))
                if n:
                    wv = sub[wcol].to_numpy(float)
                    N = float(wv.sum())
                    wy = wv * sub["ret"].to_numpy(float)
                    S, Wd, DD, nd = D.cell_stats_dict(sub["xd"].to_numpy(), wy)
                    win = float((sub["ret"].to_numpy(float) > 0).mean())
                    ppf = float(S / N) if N > 0 else float("nan")
                else:
                    N, S, Wd, DD, nd, win, ppf = 0.0, 0.0, 0.0, 0.0, 0, 0.0, float("nan")
                cells[(p, y)] = dict(n=n, N=N, S=S, W=Wd, DD=DD, ndays=nd, win=win, ppf=ppf)
        return cells

    cells_cb = score_cells("wk_base")
    cells_cr = score_cells("wk_rule")
    cells_ub = score_cells("w_base")
    cells_ur = score_cells("w_rule")

    per_year = []
    dsum5y_cap, dsum5y_unc = 0.0, 0.0
    for y in range(5):
        Sb = [cells_cb[(p, y)]["S"] for p in phases]
        Sr = [cells_cr[(p, y)]["S"] for p in phases]
        Db = [cells_cb[(p, y)]["DD"] for p in phases]
        Dr = [cells_cr[(p, y)]["DD"] for p in phases]
        Wb = [cells_cb[(p, y)]["W"] for p in phases]
        Wr = [cells_cr[(p, y)]["W"] for p in phases]
        Nb = [cells_cb[(p, y)]["N"] for p in phases]
        Nr = [cells_cr[(p, y)]["N"] for p in phases]
        S_bar_b, S_bar_r = float(np.mean(Sb)), float(np.mean(Sr))
        DD_bar_b, DD_bar_r = float(np.mean(Db)), float(np.mean(Dr))
        W_bar_b, W_bar_r = float(np.mean(Wb)), float(np.mean(Wr))
        N_bar_b, N_bar_r = float(np.mean(Nb)), float(np.mean(Nr))
        ppf_bar_b = float(S_bar_b / N_bar_b) if N_bar_b > 0 else float("nan")
        ppf_bar_r = float(S_bar_r / N_bar_r) if N_bar_r > 0 else float("nan")
        dsum5y_cap += S_bar_r - S_bar_b
        # uncapped 4-phase means
        SUb = [cells_ub[(p, y)]["S"] for p in phases]
        SUr = [cells_ur[(p, y)]["S"] for p in phases]
        DDb = [cells_ub[(p, y)]["DD"] for p in phases]
        DDr = [cells_ur[(p, y)]["DD"] for p in phases]
        WUb = [cells_ub[(p, y)]["W"] for p in phases]
        WUr = [cells_ur[(p, y)]["W"] for p in phases]
        NUb = [cells_ub[(p, y)]["N"] for p in phases]
        NUr = [cells_ur[(p, y)]["N"] for p in phases]
        SU_bar_b, SU_bar_r = float(np.mean(SUb)), float(np.mean(SUr))
        DDU_bar_b, DDU_bar_r = float(np.mean(DDb)), float(np.mean(DDr))
        WU_bar_b, WU_bar_r = float(np.mean(WUb)), float(np.mean(WUr))
        NU_bar_b, NU_bar_r = float(np.mean(NUb)), float(np.mean(NUr))
        dsum5y_unc += SU_bar_r - SU_bar_b
        # exposure-matched control: pooled realised ratio that year
        Ntot_b = float(sum(Nb))
        Ntot_r = float(sum(Nr))
        R_cap = float(Ntot_r / Ntot_b) if Ntot_b > 0 else 1.0
        S_ctrl_bar = float(R_cap * S_bar_b)
        NUtot_b = float(sum(NUb))
        NUtot_r = float(sum(NUr))
        R_unc = float(NUtot_r / NUtot_b) if NUtot_b > 0 else 1.0
        SU_ctrl_bar = float(R_unc * SU_bar_b)
        # per-rung uncapped diagnostics (pooled phases, this year)
        rung = []
        for ri, k in enumerate(D.RUNGS):
            m = (df["year"] == y) & (df["k_ix"] == ri)
            s = df[m]
            n_r = int(len(s))
            Nb_k = float(s["w_base"].sum()) if n_r else 0.0
            Nr_k = float(s["w_rule"].sum()) if n_r else 0.0
            Sb_k = float((s["w_base"] * s["ret"]).sum()) if n_r else 0.0
            Sr_k = float((s["w_rule"] * s["ret"]).sum()) if n_r else 0.0
            rung.append({"k": float(k), "tilt": round(D.tilt_mult(float(k)), 8),
                         "n": n_r,
                         "N_base": round(Nb_k, 6), "N_rule": round(Nr_k, 6),
                         "S_base": round(Sb_k, 6), "S_rule": round(Sr_k, 6),
                         "ppf_base": round(Sb_k / Nb_k, 8) if Nb_k > 0 else None,
                         "ppf_rule": round(Sr_k / Nr_k, 8) if Nr_k > 0 else None})
        per_year.append({
            "year": ANCHORS[y].date().isoformat(),
            "cap": {
                "S_bar_base": round(S_bar_b, 6), "S_bar_rule": round(S_bar_r, 6),
                "delta_S_bar": round(S_bar_r - S_bar_b, 6),
                "N_bar_base": round(N_bar_b, 6), "N_bar_rule": round(N_bar_r, 6),
                "realised_ratio": round(R_cap, 6),
                "ppf_bar_base": round(ppf_bar_b, 8), "ppf_bar_rule": round(ppf_bar_r, 8),
                "DD_bar_base": round(DD_bar_b, 6), "DD_bar_rule": round(DD_bar_r, 6),
                "dDD_bar": round(DD_bar_r - DD_bar_b, 6),
                "W_bar_base": round(W_bar_b, 6), "W_bar_rule": round(W_bar_r, 6),
                "n_bar_base": round(float(np.mean([cells_cb[(p, y)]["n"] for p in phases])), 2),
                "n_bar_rule": round(float(np.mean([cells_cr[(p, y)]["n"] for p in phases])), 2),
                "win_bar_base": round(float(np.mean([cells_cb[(p, y)]["win"] for p in phases])), 6),
                "win_bar_rule": round(float(np.mean([cells_cr[(p, y)]["win"] for p in phases])), 6),
                "per_phase_S_base": [round(v, 6) for v in Sb],
                "per_phase_S_rule": [round(v, 6) for v in Sr],
                "per_phase_DD_base": [round(v, 6) for v in Db],
                "per_phase_DD_rule": [round(v, 6) for v in Dr],
                "per_phase_ppf_base": [round(cells_cb[(p, y)]["ppf"], 8) for p in phases],
                "per_phase_ppf_rule": [round(cells_cr[(p, y)]["ppf"], 8) for p in phases],
                "S_ctrl_bar": round(S_ctrl_bar, 6),
                "gain_over_ctrl": round(S_bar_r - S_ctrl_bar, 6),
                "pass_sum": bool(S_bar_r >= S_bar_b),
                "pass_dd": bool(DD_bar_r <= DD_bar_b + DD_TOL),
                "pass_ctrl": bool(S_bar_r > S_ctrl_bar),
            },
            "uncapped": {
                "S_bar_base": round(SU_bar_b, 6), "S_bar_rule": round(SU_bar_r, 6),
                "delta_S_bar": round(SU_bar_r - SU_bar_b, 6),
                "N_bar_base": round(NU_bar_b, 6), "N_bar_rule": round(NU_bar_r, 6),
                "realised_ratio": round(R_unc, 6),
                "ppf_bar_base": round(SU_bar_b / NU_bar_b, 8) if NU_bar_b > 0 else None,
                "ppf_bar_rule": round(SU_bar_r / NU_bar_r, 8) if NU_bar_r > 0 else None,
                "DD_bar_base": round(DDU_bar_b, 6), "DD_bar_rule": round(DDU_bar_r, 6),
                "dDD_bar": round(DDU_bar_r - DDU_bar_b, 6),
                "W_bar_base": round(WU_bar_b, 6), "W_bar_rule": round(WU_bar_r, 6),
                "S_ctrl_bar": round(SU_ctrl_bar, 6),
                "gain_over_ctrl": round(SU_bar_r - SU_ctrl_bar, 6),
                "pass_sum": bool(SU_bar_r >= SU_bar_b),
                "pass_dd": bool(DDU_bar_r <= DDU_bar_b + DD_TOL),
                "pass_ctrl": bool(SU_bar_r > SU_ctrl_bar),
            },
            "per_rung_uncapped": rung,
        })

    def pooled(wcol):
        sub = df[df[wcol] > 0]
        wv = sub[wcol].to_numpy(float)
        wy = wv * sub["ret"].to_numpy(float)
        S, Wd, DD, nd = D.cell_stats_dict(sub["xd"].to_numpy(), wy)
        N = float(wv.sum())
        return {"n": int(len(sub)), "realised": round(N, 6),
                "sum": round(float(S), 6),
                "ppf": round(float(S / N), 8) if N > 0 else None,
                "worst_day": round(float(Wd), 6), "max_dd": round(float(DD), 6),
                "ndays": int(nd),
                "win": round(float((sub["ret"].to_numpy(float) > 0).mean()) if len(sub) else 0.0, 6)}

    full = {"cap_base": pooled("wk_base"), "cap_rule": pooled("wk_rule"),
            "uncapped_base": pooled("w_base"), "uncapped_rule": pooled("w_rule")}
    n_sum = sum(1 for r in per_year if r["cap"]["pass_sum"])
    n_dd = sum(1 for r in per_year if r["cap"]["pass_dd"])
    n_ctrl = sum(1 for r in per_year if r["cap"]["pass_ctrl"])
    decision = {"years_sum_ge": int(n_sum), "years_dd_ok": int(n_dd),
                "years_ctrl": int(n_ctrl),
                "dSum5y_cap": round(float(dsum5y_cap), 6),
                "dSum5y_unc": round(float(dsum5y_unc), 6),
                "dSum5y_gate": GATE_DSUM,
                "promising": bool(n_sum >= 4 and n_dd >= 4 and n_ctrl >= 4
                                  and dsum5y_cap >= GATE_DSUM)}

    ref = [2.388052, 0.182865, 3.809764, 2.579274, 0.711509]
    got = []
    for y in range(5):
        s = df[(df["year"] == y) & (df["phase"] == 0)]
        got.append(float((s["w_base"] * s["ret"]).sum()) if len(s) else 0.0)
    chk = hashlib.sha256(
        np.round(df[["w_base", "w_rule", "ret", "wk_base", "wk_rule"]].to_numpy(), 9).tobytes()).hexdigest()[:16]
    out = {"config": {
        "coins": list(coins), "rungs": list(D.RUNGS),
        "bars": "open in [2021-09-24, 2026-09-24)",
        "grid": "4h from 2020-08-01 00:00 UTC + 0/1/2/3h",
        "live": [D.LIVE_A, D.LIVE_B],
        "tilt": "w_raw(k)=k/2.5 renormalised per coin-bar to sum 5.0; " +
                ", ".join(f"{k}->{D.tilt_mult(float(k)):.8f}" for k in D.RUNGS),
        "sizes": "base w=1/(1+n_fill); rule w=tilt(k)/(1+n_fill); v399-exact n",
        "exits": "D0 replica from lv (TP=lv*(1+sg), sl 4sg close5, bl 8sg, timeout next open)",
        "maker": D.MAKER, "taker": D.TAKER, "fund_long": 0.0001,
        "settle_hours": list(SETTLE_HOURS),
        "cap": "v421-style G=2.0 walk per (phase,bar), order (f,k,coin), cut to room, skip when full; equity=1 constant; open+new<=G; D0 exits<=240 so per-bar pools independent",
        "pairing": "kept only if single D0 leg finite (base and rule identically; same fills)",
        "scoring": "PRIMARY cap-adjusted wk*y daily sums by exit date UTC; 4-phase means; DD of cumsum path from 0 (>=0); ppf_bar=S_bar/N_bar",
        "control": "per-year pooled realised ratio R(Y)=N_rule(Y)/N_base(Y); S_ctrl_bar(Y)=R(Y)*S_base_bar(Y)",
        "criterion": "PROMISING iff (capped) sum>=base in >=4/5y AND DD<=base+0.01 in >=4/5y AND dSum5y>=+0.273 AND rule>ctrl in >=4/5y",
        "post_hoc": "motivated by oc_saturation edge/unit-notional 0.19% at 2.5sg vs 0.51-0.58% at 5sg; fixed tilt, no fit",
        "resources": "one process, majors 1m O/C float32 + one-coin H/L"},
        "n_candidates": int(len(df)),
        "n_cap_base_kept": int((df["wk_base"] > 0).sum()),
        "n_cap_rule_kept": int((df["wk_rule"] > 0).sum()),
        "ledger_checksum": chk,
        "phase0_uncapped_fidelity": {
            "got_raw_sums": [round(v, 6) for v in got],
            "oc_placebo_dip_ref": ref,
            "note": "same replica+B1 sizes; pairing differs (here single D0 leg vs placebo 3 TP legs)"},
        "per_year": per_year, "full": full, "decision": decision}
    if args.smoke:
        print(json.dumps({"n": len(df), "decision": decision,
                           "per_year": [(r["year"], r["cap"]["S_bar_base"],
                                         r["cap"]["S_bar_rule"]) for r in per_year]}, indent=1))
        return
    (HERE / "results.json").write_text(json.dumps(out, indent=1))
    df.to_parquet(HERE / "fills.parquet", index=False)
    print("n_candidates", len(df), "cap_base_kept", int((df["wk_base"] > 0).sum()),
          "cap_rule_kept", int((df["wk_rule"] > 0).sum()), "checksum", chk, flush=True)
    print(json.dumps(decision, indent=1))


if __name__ == "__main__":
    main()
