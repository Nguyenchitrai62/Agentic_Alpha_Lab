"""oc_rearm run: B1 base vs re-arm rule, oc_b1deeper-exact, 4 clock phases.

One process, one coin's H/L in RAM at a time; all-five-coins 1m opens/closes
held as float32 arrays; bar opens/sigmas precomputed per coin per phase.
See PLAN.md (idea #67, frozen before any outcome computation).
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import numpy as np
import pandas as pd

import rearm as R

START = pd.Timestamp("2020-08-01", tz="UTC")
END = pd.Timestamp("2026-09-24 00:00", tz="UTC")
TRADE_START = pd.Timestamp("2021-09-24 00:00", tz="UTC")
YEAR_END = pd.Timestamp("2026-09-24 00:00", tz="UTC")
MAJORS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
ANCHORS = [pd.Timestamp(a, tz="UTC") for a in
           ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")]
SETTLE_HOURS = (0, 8, 16)
SHIFTS = (0, 1, 2, 3)
W = R.LIVE_B - R.LIVE_A + 1  # 223 live minutes


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


def daily_path(recs):
    """recs: list of (exit_date_iso, w_y). Returns (S, worst_day, maxDD, ndays)."""
    if not recs:
        return 0.0, 0.0, 0.0, 0
    daily = {}
    for d, v in recs:
        daily[d] = daily.get(d, 0.0) + v
    days = sorted(daily)
    cum, peak, dd = 0.0, 0.0, 0.0
    for d in days:
        cum += daily[d]
        peak = max(peak, cum)
        dd = min(dd, cum - peak)
    return float(sum(daily.values())), float(min(daily.values())), float(-dd), len(days)


def main():
    O, C, base_idx = {}, {}, None
    for sym in MAJORS:
        ii, o, c = load_oc(sym)
        base_idx = ii if base_idx is None else base_idx
        O[sym], C[sym] = o, c
        print(f"loaded OC {sym}", flush=True)
    n_all = len(base_idx)

    # Per-phase shifted 4h grids: opens/sigmas per coin + traded bar list.
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

    candidates = []  # base (kind 0) + re-arm (kind 1) candidates, cap applied later
    for sym in MAJORS:
        H, L = load_hl(sym, base_idx)
        La, Ha = L, H
        others = [b for b in MAJORS if b != sym]
        n_base = n_re = 0
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
                                 for b in others])  # (4, W) closes at T+m-1
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
                        continue
                    xd = (bt + pd.Timedelta(minutes=int(x))).date().isoformat() if int(x) < 240 else \
                        (bt + pd.Timedelta(hours=4)).date().isoformat()
                    cid = len(candidates)
                    candidates.append(dict(s=s, j=j, sym=sym, k=k, kind=0, parent=-1,
                                             f=int(f), x=int(x), how=how,
                                             w=float(R.size_mult(nf)), n=int(nf),
                                             ret=float(ret), xd=xd, fill=float(lv),
                                             t_bar=bt, y=yi))
                    n_base += 1
                    if how == "tp":
                        rel = R.find_refill(low_win, lv, (int(x) + 1) - R.LIVE_A)
                        if rel is None:
                            continue
                        f2 = R.LIVE_A + rel
                        n2 = int(nvec[rel])
                        ret2, x2, how2 = R.outcome_from_fill(
                            Ha_b, La_b, Ca_b, Oa_b, f2, lv, sg, o2, settle)
                        if not np.isfinite(ret2):
                            continue
                        xd2 = (bt + pd.Timedelta(minutes=int(x2))).date().isoformat() if int(x2) < 240 else \
                            (bt + pd.Timedelta(hours=4)).date().isoformat()
                        candidates.append(dict(s=s, j=j, sym=sym, k=k, kind=1, parent=cid,
                                                 f=int(f2), x=int(x2), how=how2,
                                                 w=float(R.size_mult(n2)), n=int(n2),
                                                 ret=float(ret2), xd=xd2, fill=float(lv),
                                                 t_bar=bt, y=yi))
                        n_re += 1
        print(f"{sym}: base_cands={n_base} rearm_cands={n_re}", flush=True)
        del H, L, Ha, La

    # Per-(phase, bar) G=2.0 cap walk, separately per arm (PLAN.md item 6).
    groups: dict = {}
    for i, r in enumerate(candidates):
        groups.setdefault((r["s"], r["j"]), []).append(i)
    base_rows, rule_rows = [], []
    n_skip_base = n_skip_rule = n_cut_rule = n_cut_base = n_noparent = 0
    for (s, j), idxs in groups.items():
        order = sorted(idxs, key=lambda i: (candidates[i]["f"], candidates[i]["k"], candidates[i]["sym"]))
        pos_of = {i: p for p, i in enumerate(order)}
        F = [candidates[i]["f"] for i in order]
        X = [candidates[i]["x"] for i in order]
        W8 = [candidates[i]["w"] for i in order]
        # Base arm: base fills only.
        bord = [p for p in range(len(order)) if candidates[order[p]]["kind"] == 0]
        kb = R.gross_cap_weights([F[p] for p in bord], [X[p] for p in bord],
                                 [W8[p] for p in bord], list(range(len(bord))), G=R.GROSS_CAP)
        for bp, p in enumerate(bord):
            wk = kb[bp]
            r = candidates[order[p]]
            r["w_base"] = wk
            if wk <= 0:
                n_skip_base += 1
            else:
                if wk < r["w"] - 1e-12:
                    n_cut_base += 1
                base_rows.append(dict(s=s, y=r["y"], sym=r["sym"], k=r["k"], f=r["f"],
                                      x=r["x"], how=r["how"], w=wk, ret=r["ret"], xd=r["xd"]))
        # Rule arm: base + re-armed, parent-aware.
        P = [pos_of[candidates[order[p]]["parent"]] if candidates[order[p]]["kind"] == 1 else -1
             for p in range(len(order))]
        kr = R.gross_cap_weights(F, X, W8, list(range(len(order))), G=R.GROSS_CAP, parent=P)
        for p in range(len(order)):
            wk = kr[p]
            r = candidates[order[p]]
            r["w_rule"] = wk
            if wk <= 0:
                n_skip_rule += 1
                if r["kind"] == 1 and P[p] >= 0 and kr.get(P[p], 0.0) <= 0.0:
                    n_noparent += 1
            else:
                if wk < r["w"] - 1e-12:
                    n_cut_rule += 1
                rule_rows.append(dict(s=s, y=r["y"], sym=r["sym"], k=r["k"], kind=r["kind"],
                                      f=r["f"], x=r["x"], how=r["how"], w=wk, ret=r["ret"], xd=r["xd"]))

    df_b = pd.DataFrame(base_rows)
    df_r = pd.DataFrame(rule_rows)

    def arm_year(s, yi, df):
        sub = df[(df["s"] == s) & (df["y"] == yi)]
        n = len(sub)
        if n:
            wy = sub["w"].to_numpy(float) * sub["ret"].to_numpy(float)
            S, Wd, DD, nd = daily_path(list(zip(sub["xd"].tolist(), wy.tolist())))
            s_raw = float(wy.sum())
        else:
            S, Wd, DD, nd, s_raw = 0.0, 0.0, 0.0, 0, 0.0
        return {"n": int(n), "sum": S, "worst_day": Wd, "max_dd": DD, "ndays": nd, "wy": s_raw}

    def renorm_year(s, yi, df):
        sub = df[(df["s"] == s) & (df["y"] == yi)]
        if len(sub):
            w = sub["w"].to_numpy(float)
            wy = w / w.mean() * sub["ret"].to_numpy(float)
            S, _, _, _ = daily_path(list(zip(sub["xd"].tolist(), wy.tolist())))
        else:
            S = 0.0
        return S

    per_year, per_shift = [], {a: {s: [] for s in SHIFTS} for a in ("base", "rule")}
    for yi in range(5):
        row = {"year": ANCHORS[yi].date().isoformat()}
        for arm, df in (("base", df_b), ("rule", df_r)):
            stats = [arm_year(s, yi, df) for s in SHIFTS]
            for s in SHIFTS:
                per_shift[arm][s].append({"year": row["year"], **{kk: stats[s][kk]
                                          for kk in ("n", "sum", "worst_day", "max_dd")}})
            row[arm] = {"sum_mean": float(np.mean([t["sum"] for t in stats])),
                        "n_mean": float(np.mean([t["n"] for t in stats])),
                        "worst_mean": float(np.mean([t["worst_day"] for t in stats])),
                        "dd_mean": float(np.mean([t["max_dd"] for t in stats])),
                        "sum_renorm_mean": float(np.mean([renorm_year(s, yi, df) for s in SHIFTS]))}
        # pooled win rates / re-armed share across phases
        pb = df_b[df_b["y"] == yi]
        pr = df_r[df_r["y"] == yi]
        pr_re = pr[pr["kind"] == 1]
        row["win_base"] = float((pb["ret"].to_numpy(float) > 0).mean()) if len(pb) else 0.0
        row["win_rule"] = float((pr["ret"].to_numpy(float) > 0).mean()) if len(pr) else 0.0
        row["win_rearm"] = float((pr_re["ret"].to_numpy(float) > 0).mean()) if len(pr_re) else 0.0
        row["n_rearm"] = int(len(pr_re))
        wy_tot = float((pr["w"].to_numpy(float) * pr["ret"].to_numpy(float)).sum()) if len(pr) else 0.0
        wy_re = float((pr_re["w"].to_numpy(float) * pr_re["ret"].to_numpy(float)).sum()) if len(pr_re) else 0.0
        row["rearm_share"] = float(wy_re / wy_tot) if wy_tot != 0 else 0.0
        row["rearm_wy"] = wy_re
        row["rule_wy"] = wy_tot
        row["pass_sum"] = bool(np.isfinite(row["rule"]["sum_mean"]) and np.isfinite(row["base"]["sum_mean"])
                               and row["rule"]["sum_mean"] > row["base"]["sum_mean"])
        row["pass_dd"] = bool(np.isfinite(row["rule"]["dd_mean"]) and np.isfinite(row["base"]["dd_mean"])
                              and row["rule"]["dd_mean"] <= row["base"]["dd_mean"] + 0.01)
        per_year.append(row)

    pr_all_re = df_r[df_r["kind"] == 1]
    rw_all = float((pr_all_re["ret"].to_numpy(float) > 0).mean()) if len(pr_all_re) else 0.0
    n_sum = sum(1 for r in per_year if r["pass_sum"])
    n_dd = sum(1 for r in per_year if r["pass_dd"])
    decision = {"years_sum_higher": int(n_sum), "years_dd_not_worse_1pp": int(n_dd),
                "rearm_win_all": rw_all,
                "promising": bool(n_sum >= 4 and n_dd >= 4 and rw_all >= 0.60)}

    full = {}
    for arm, df in (("base", df_b), ("rule", df_r)):
        full[arm] = {"n": int(len(df)),
                     "win_rate": float((df["ret"].to_numpy(float) > 0).mean()) if len(df) else 0.0,
                     "wy_sum_pooled": float((df["w"].to_numpy(float) * df["ret"].to_numpy(float)).sum())
                     if len(df) else 0.0}

    chk_src = np.round(pd.DataFrame(candidates)[["ret", "w"]].to_numpy(), 9).tobytes() \
        if len(candidates) else b"empty"
    chk = hashlib.sha256(chk_src).hexdigest()[:16]
    out = {"config": {"coins": list(MAJORS), "rungs": list(R.RUNGS),
                       "bars": "per-phase opens in [2021-09-24, 2026-09-24)",
                       "grid": "4h from 2020-08-01 00:00 UTC + shift s in {0,1,2,3}h",
                       "live": [R.LIVE_A, R.LIVE_B],
                       "maker": R.MAKER, "taker": R.TAKER, "fund_long": 0.0001,
                       "settle_hours": list(SETTLE_HOURS),
                       "n": "other majors C(T+m-1) <= O(T)*(1-2.5*sg(T)), oc_b1deeper-exact, per-phase grid",
                       "base": "B1 static bid at lv, strict low<lv fill, size 1/(1+n), D0 exits from lv, G=2.0 cap",
                       "rule": "base + re-arm: after an inside-bar TP, same bid at same lv from x+1, one refill max, w2=1/(1+n(f2)), D0 exit, counts to G=2.0",
                       "cap": "per (phase,bar) time-order (f,k,coin) walk: skip when room<=1e-12 else cut to room; re-arm dropped when parent kept 0",
                       "scoring": "PRIMARY raw w_kept*y daily sums by exit date UTC, 4-phase means; wins/shares pooled; renorm side row",
                       "dd_rule": "DD_rule <= DD_base + 0.01 (1pp = 0.01 w*y units); sum strictly higher; rearm pooled win >= 0.60",
                       "note": "fills with non-finite exit nets dropped identically in base and rule; market data to 2026-09-24 = research data"},
           "n_candidates": int(len(candidates)),
           "n_base_cands": int(sum(1 for r in candidates if r["kind"] == 0)),
           "n_rearm_cands": int(sum(1 for r in candidates if r["kind"] == 1)),
           "cap": {"base_skipped": int(n_skip_base), "base_cut": int(n_cut_base),
                   "rule_skipped": int(n_skip_rule), "rule_cut": int(n_cut_rule),
                   "rearm_parent_skipped": int(n_noparent)},
           "n_fills_base": int(len(df_b)), "n_fills_rule": int(len(df_r)),
           "n_fills_rearm": int(len(pr_all_re)),
           "ledger_checksum": chk,
           "per_year": per_year, "per_shift": per_shift, "full": full, "decision": decision}
    (HERE / "results.json").write_text(json.dumps(out, indent=1, default=str))
    pd.DataFrame(candidates).to_parquet(HERE / "fills_candidates.parquet", index=False)
    print("n_cands", len(candidates), "n_base", len(df_b), "n_rule", len(df_r),
          "n_rearm", len(pr_all_re), "checksum", chk, flush=True)
    print(json.dumps(decision, indent=1))


if __name__ == "__main__":
    main()
