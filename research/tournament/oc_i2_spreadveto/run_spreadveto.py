"""oc_i2_spreadveto: spread/depth-state dip veto (IDEAS2_20261007 section 4).

Binary VETO (not sizing): skip new dip bids when trailing-7d median spread
> p90 (S1) or top-5 depth < p10 (S2 = spread-p90 OR depth-p10).

Pre-registered variants: S1, S2 (see REPORT.md pre-registration, written
BEFORE any outcome). Dip replica + placebo gate (+0.273); 4-phase engine
only on the 2023-2024 overlap and only if the screen passes.

Method (frozen in REPORT.md):
  Replica ledger: research/tournament/oc_depthtilt/fills.parquet (22312
  fills, audited D0+B1 replica; phase-0 sums = placebo ref to 1e-6,
  asserted in-script). Fills identical across arms; veto drops candidates.
  Spread state: UNAVAILABLE — data/raw/bookdepth_20261004 stores ONLY
  1%/2%/5% cumulative notionals (bid/ask_n1/n2/n5, see
  scripts/fetch_bookdepth.py); no bid/ask prices, no spread column.
  Asserted in-script -> S1 infeasible (no-op, disclosed).
  Depth state per (coin, bar open T): med7 = median of tot5 = bid_n5+ask_n5
  over snapshots with ts in [T-7d, T) (ts strictly before T; >=1000
  snapshots else NaN -> no veto). Rows with ts >= 2026-09-24 never used.
  Thresholds per (anchor A, coin): p10 of med7 bar-states over calibration
  window [2023-01-08, A-7d) (expanding from depth start, 7d embargo; min 60
  bars else NaN -> no veto). 2021-2022 anchors: empty window -> no veto
  (size 1, no imputation, per spec).
  S2 (spread leg missing, disclosed) = depth-only veto: drop fills whose
  (phase, bar, coin) has med7 < p10. Holds/exits unchanged (ledger exits
  kept for survivors); G-cap walk re-run on the vetoed candidate set.
  Scoring: placebo convention on 4-phase means per dev year (2021-2024):
  PASS_sum iff S_rule >= S_base; PASS_dd iff DD_rule <= DD_base + 0.01;
  PROMISING iff both in >= 4/5 years (dev4: >= 4/4? reported both ways,
  see results) AND dSum >= +0.273 (pooled placebo p95). PRIMARY = uncapped
  w*y (gate-compatible); capped G=2.0 wk*y side row. Year 2025-09-24..
  2026-09-23 is NEVER scored for a variant here (only the dev screen
  decides; engine/2025 runs only if it passes).

Writes ONLY research/tournament/oc_i2_spreadveto/results.json.
Light process (ledger 22k rows + one depth symbol at a time, < 0.4 GB).
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
LEDGER = ROOT / "research/tournament/oc_depthtilt/fills.parquet"
DEPTH = ROOT / "data/raw/bookdepth_20261004"
V421_RES = ROOT / "research/parallel/rounds/parallel-20260906-r2/v421/v421_result.json"
CC_RES = ROOT / "research/tournament/oc_carrycompound/results.json"

MAJORS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
ANCHORS = [pd.Timestamp(a, tz="UTC") for a in
           ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")]
YEAR_END = pd.Timestamp("2026-09-24 00:00", tz="UTC")
CAP = pd.Timestamp("2026-09-24 00:00", tz="UTC")
DD_TOL = 0.01
GATE_DSUM = 0.273  # pooled placebo p95 (oc_placebo_dip)
MIN_SNAP = 1000
MIN_CAL = 60
CAL_START = pd.Timestamp("2023-01-08", tz="UTC")
EMBARGO = pd.Timedelta(days=7)
WIN7 = pd.Timedelta(days=7)
PLACEBO_REF_P0 = [2.388052, 0.182865, 3.809764, 2.579274, 0.711509]


def cell_stats(dates, wy):
    """(S, worst_day, maxDD, ndays) of exit-day sums. DD >= 0 in w*y units."""
    dates = np.asarray(dates)
    wy = np.asarray(wy, dtype=float)
    if wy.size == 0:
        return 0.0, 0.0, 0.0, 0
    daily: dict = {}
    for d, v in zip(dates.tolist(), wy.tolist()):
        daily[d] = daily.get(d, 0.0) + v
    days = sorted(daily)
    cum, peak, dd = 0.0, 0.0, 0.0
    for d in days:
        cum += daily[d]
        peak = max(peak, cum)
        dd = min(dd, cum - peak)
    return float(sum(daily.values())), float(min(daily.values())), float(-dd), len(days)


def gross_cap_weights(f, x, w, order, G=2.0, eps=1e-12):
    """v421-style sleeve_gross_cap walk (oc_depthtilt-exact)."""
    kept = {}
    open_fills = []
    for p in order:
        fi, xi, wi = int(f[p]), int(x[p]), float(w[p])
        open_w = sum(wk for (xk, wk) in open_fills if xk > fi)
        room = float(G) - open_w
        if room <= eps:
            kept[p] = 0.0
        else:
            wk = wi if wi <= room else room
            kept[p] = wk
            open_fills.append((xi, wk))
    return kept


def main() -> None:
    # ---- 0. baseline gate: reproduce G2 / G2+carry exactly, else stop ----
    v = json.loads(V421_RES.read_text())["rows"]["R2B1D17BFG2"]
    assert v["R"] == 5.41 and v["W"] == 2.588 and v["DD"] == 16.91, v
    assert v["full_path_dd"] == 16.82, v
    assert [list(y) for y in v["years"]] == [
        [2.588, 10.86], [3.282, 16.91], [6.045, 15.81],
        [10.677, 8.27], [4.648, 12.9]], v["years"]
    cc = json.loads(CC_RES.read_text())["rows"]["G2_f0.25"]
    assert cc["R"] == 5.634 and cc["W"] == 2.778 and cc["DD"] == 16.75, cc
    assert cc["full_path_dd"]["full"] == 16.66, cc["full_path_dd"]
    print("baseline gate OK: G2 5.41/16.91/full16.82; G2+carry 5.634/16.75/full16.66",
          flush=True)

    # ---- 1. replica ledger + fidelity ----
    df = pd.read_parquet(LEDGER)
    assert len(df) == 22312, len(df)
    assert sorted(df["phase"].unique().tolist()) == [0, 1, 2, 3]
    got_p0 = []
    for y in range(5):
        s = df[(df["year"] == y) & (df["phase"] == 0)]
        got_p0.append(round(float((s["w_base"] * s["ret"]).sum()), 6))
    assert all(abs(g - r) < 1e-6 for g, r in zip(got_p0, PLACEBO_REF_P0)), got_p0
    print("ledger fidelity OK: phase-0 sums", got_p0, flush=True)
    df["t_bar"] = pd.to_datetime(df["t_bar"], utc=True)
    coin_of = dict(enumerate(MAJORS))

    # ---- 2. spread-availability proof (S1 feasibility) ----
    depth_cols = {}
    for sym in MAJORS:
        d = pd.read_parquet(DEPTH / f"{sym}_bookdepth_1m.parquet",
                            columns=["minute", "ts", "bid_n1", "ask_n1",
                                     "bid_n2", "ask_n2", "bid_n5", "ask_n5"])
        depth_cols[sym] = list(d.columns)
        del d
    has_spread = any("spread" in c or c in ("bid", "ask", "bid_px", "ask_px")
                     for cols in depth_cols.values() for c in cols)
    s1_feasible = bool(has_spread)
    print("spread columns present:", has_spread, "-> S1 feasible:", s1_feasible,
          flush=True)

    # ---- 3. depth state med7 per (coin, dev bar) ----
    df["Tns"] = df["t_bar"].to_numpy(dtype="datetime64[ns]").astype(np.int64)
    dev = df[df["year"] <= 3].copy()  # dev years 2021-2024 only; 2025 never scored
    # unique (coin, T) needing states: dev bars + calibration bars (subset)
    need = dev[["coin", "Tns"]].drop_duplicates()
    need = need[need["Tns"] >= pd.Timestamp("2023-01-01", tz="UTC").value]
    med7_map: dict[tuple[int, int], float] = {}
    cal_states: dict[tuple[int, int], list[float]] = {}  # (anchor_y, coin) -> states
    thresholds: dict[tuple[int, int], float | None] = {}
    veto_counts: dict = {}
    for ci, sym in enumerate(MAJORS):
        d = pd.read_parquet(DEPTH / f"{sym}_bookdepth_1m.parquet",
                            columns=["ts", "bid_n5", "ask_n5"])
        d["ts"] = pd.to_datetime(d["ts"], utc=True)
        d = d[d["ts"] < CAP].sort_values("ts").reset_index(drop=True)
        ts = d["ts"].to_numpy(dtype="datetime64[ns]").astype(np.int64)
        tot = (d["bid_n5"].to_numpy(float) + d["ask_n5"].to_numpy(float))
        del d
        Tn = need[need["coin"] == ci]["Tns"].to_numpy()
        Tn = np.sort(np.unique(Tn))
        win = WIN7.value
        states = np.full(len(Tn), np.nan)
        for i, T in enumerate(Tn):
            lo = int(np.searchsorted(ts, T - win, side="left"))
            hi = int(np.searchsorted(ts, T, side="left"))  # strictly before T
            n = hi - lo
            if n >= MIN_SNAP:
                states[i] = float(np.median(tot[lo:hi]))
        for T, s in zip(Tn, states):
            med7_map[(ci, int(T))] = float(s) if np.isfinite(s) else float("nan")
        # calibration per dev anchor: bars with t_bar in [CAL_START, A-7d)
        cal0 = CAL_START.value
        for ay in range(4):
            a_ns = ANCHORS[ay].value
            m = (Tn >= cal0) & (Tn < a_ns - EMBARGO.value)
            vals = states[m]
            vals = vals[np.isfinite(vals)]
            if len(vals) >= MIN_CAL:
                thresholds[(ay, ci)] = float(np.quantile(vals, 0.10))
            else:
                thresholds[(ay, ci)] = None
        n_nan = int(np.isnan(states).sum())
        print(f"{sym}: bars={len(Tn)} nan_med7={n_nan} "
              f"thr={[thresholds.get((ay, ci)) for ay in range(4)]}", flush=True)
        del ts, tot
    n_thr_none = sum(1 for v in thresholds.values() if v is None)
    n_thr_all = len(thresholds)
    print(f"threshold cells None: {n_thr_none}/{n_thr_all} (expect 10: anchors 2021+2022 x 5 coins)",
          flush=True)
    assert n_thr_none == 10 and n_thr_all == 20, (n_thr_none, n_thr_all)

    # ---- 4. veto flags (dev bars only) ----
    def is_veto_depth(row) -> bool:
        key = (int(row["coin"]), int(row["Tns"]))
        s = med7_map.get(key, float("nan"))
        thr = thresholds.get((int(row["year"]), int(row["coin"])))
        if thr is None or not np.isfinite(s):
            return False
        return bool(s < thr)

    dev = dev.copy()
    dev["veto_s2"] = dev.apply(is_veto_depth, axis=1)
    # S1: infeasible -> no veto anywhere
    n_veto_s2 = int(dev["veto_s2"].sum())
    n_dev = len(dev)
    print(f"dev fills={n_dev} vetoed_S2={n_veto_s2} "
          f"({n_veto_s2 / max(n_dev, 1):.3%})", flush=True)
    veto_by_year = {str(y): int(dev[(dev["year"] == y)]["veto_s2"].sum())
                    for y in range(4)}
    print("vetoed fills by dev year:", veto_by_year, flush=True)

    # ---- 5. scoring helper (4-phase means per year, uncapped + capped) ----
    PHASES = (0, 1, 2, 3)

    def score_set(keep_mask: np.ndarray, wcol: str, cap_walk: bool) -> dict:
        """Score dev years 0..3 on kept fills. cap_walk: re-run G-cap walk."""
        sub = dev[keep_mask].copy()
        wk_col = "_wk"
        if cap_walk:
            sub[wk_col] = 0.0
            for (p, b), g in sub.groupby(["phase", "bar"], sort=False):
                idx = g.index.to_numpy()
                f = g["f"].to_numpy()
                x = g["x"].to_numpy()
                kk = g["k_ix"].to_numpy()
                cc = g["coin"].to_numpy()
                order = sorted(range(len(g)),
                               key=lambda t: (int(f[t]), int(kk[t]), int(cc[t])))
                kept = gross_cap_weights(f, x, g[wcol].to_numpy(), order)
                for t, pos in enumerate(idx):
                    sub.at[pos, wk_col] = float(kept[t])
            w = wk_col
        else:
            w = wcol
        per_year = []
        for y in range(4):
            Ss, DDs, ns, wins = [], [], [], []
            for p in PHASES:
                m = (sub["phase"] == p) & (sub["year"] == y)
                if cap_walk:
                    m = m & (sub[wk_col] > 0)
                s = sub[m]
                n = int(len(s))
                ns.append(n)
                if n:
                    wv = s[w].to_numpy(float)
                    wy = wv * s["ret"].to_numpy(float)
                    S, _, DD, _ = cell_stats(s["xd"].to_numpy(), wy)
                    wins.append(float((s["ret"].to_numpy(float) > 0).mean()))
                else:
                    S, DD = 0.0, 0.0
                    wins.append(0.0)
                Ss.append(S)
                DDs.append(DD)
            per_year.append({"S_bar": float(np.mean(Ss)),
                             "DD_bar": float(np.mean(DDs)),
                             "n_bar": float(np.mean(ns)),
                             "win_bar": float(np.mean(wins)),
                             "per_phase_S": [float(v) for v in Ss],
                             "per_phase_DD": [float(v) for v in DDs]})
        # pooled dev4 path (all phases) context
        if cap_walk:
            s4 = sub[sub[wk_col] > 0]
            wv = s4[wk_col].to_numpy(float)
        else:
            s4 = sub
            wv = s4[wcol].to_numpy(float)
        wy = wv * s4["ret"].to_numpy(float)
        S4, _, DD4, _ = cell_stats(s4["xd"].to_numpy(), wy)
        return {"per_year": per_year,
                "d4_sum": float(sum(r["S_bar"] for r in per_year)),
                "pooled": {"sum": float(S4), "dd": float(DD4),
                           "n": int(len(s4)),
                           "win": float((s4["ret"].to_numpy(float) > 0).mean())
                           if len(s4) else 0.0}}

    base_unc = score_set(np.ones(len(dev), bool), "w_base", cap_walk=False)
    s2_unc = score_set(~dev["veto_s2"].to_numpy(), "w_base", cap_walk=False)
    base_cap = score_set(np.ones(len(dev), bool), "w_base", cap_walk=True)
    s2_cap = score_set(~dev["veto_s2"].to_numpy(), "w_base", cap_walk=True)
    # S1 = no-op (infeasible): rule == base
    s1_unc, s1_cap = base_unc, base_cap

    def decide(rule: dict, base: dict, label: str) -> dict:
        ps = sum(1 for y in range(4)
                 if rule["per_year"][y]["S_bar"] >= base["per_year"][y]["S_bar"])
        pd_ = sum(1 for y in range(4)
                  if rule["per_year"][y]["DD_bar"] <= base["per_year"][y]["DD_bar"] + DD_TOL)
        dsum = float(rule["d4_sum"] - base["d4_sum"])
        overlap = [2, 3]  # 2023-2024 depth-overlap years
        ps_o = sum(1 for y in overlap
                   if rule["per_year"][y]["S_bar"] >= base["per_year"][y]["S_bar"])
        pd_o = sum(1 for y in overlap
                   if rule["per_year"][y]["DD_bar"] <= base["per_year"][y]["DD_bar"] + DD_TOL)
        dsum_o = float(sum(rule["per_year"][y]["S_bar"] - base["per_year"][y]["S_bar"]
                           for y in overlap))
        return {"variant": label, "years_sum_ge_dev4": int(ps),
                "years_dd_ok_dev4": int(pd_), "dSum_dev4": round(dsum, 6),
                "years_sum_ge_overlap": int(ps_o), "years_dd_ok_overlap": int(pd_o),
                "dSum_overlap": round(dsum_o, 6),
                "promising_dev4": bool(ps >= 4 and pd_ >= 4 and dsum >= GATE_DSUM),
                "promising_overlap": bool(ps_o >= 2 and pd_o >= 2 and dsum_o >= GATE_DSUM)}

    dec_s1 = decide(s1_unc, base_unc, "S1")
    dec_s2 = decide(s2_unc, base_unc, "S2")
    dec_s2_cap = decide(s2_cap, base_cap, "S2_capped_siderow")
    print("S1:", dec_s1, flush=True)
    print("S2:", dec_s2, flush=True)
    print("S2 capped:", dec_s2_cap, flush=True)

    # ---- 6. engine gate: only if a variant passes the dev screen ----
    chosen = None
    for dec in (dec_s2, dec_s1):
        if dec["promising_dev4"]:
            chosen = dec["variant"]
            break
    engine_run = False  # screen decides; reset_metric/engine only if chosen
    print("chosen:", chosen, "engine_run:", engine_run, flush=True)

    out = {
        "meta": {
            "idea": "IDEAS2_20261007 section 4: spread/depth-state dip veto",
            "variants": ["S1 skip on spread-p90",
                         "S2 skip on spread-p90 OR depth-p10"],
            "baseline_gate": "v421 R2B1D17BFG2 5.41/2.588/16.91/full16.82 + "
                             "oc_carrycompound G2_f0.25 5.634/2.778/16.75/full16.66 "
                             "(asserted in-script)",
            "replica": "oc_depthtilt fills.parquet 22312 fills; phase-0 sums "
                       "match placebo ref to 1e-6 (asserted)",
            "spread": {"columns": depth_cols,
                       "feasible": s1_feasible,
                       "note": "archive stores ONLY 1/2/5% notionals; no "
                               "bid/ask prices -> spread uncomputable -> S1 "
                               "infeasible no-op (rule==base, disclosed)"},
            "depth_state": "med7 = median(bid_n5+ask_n5) over ts in [T-7d,T), "
                           "ts strictly before bar open, >=1000 snapshots; "
                           "rows ts>=2026-09-24 excluded",
            "threshold": "per (anchor, coin) p10 of med7 bar-states over "
                         "[2023-01-08, A-7d), min 60 bars; 2021/2022 anchors "
                         "empty -> no veto (size 1, no imputation)",
            "veto_scope": "per (phase, bar, coin); holds/exits unchanged; "
                          "G-cap walk re-run on vetoed set (capped side row)",
            "scoring": "placebo convention on 4-phase means, dev years "
                       "2021-2024: PASS_sum S>=base, PASS_dd DD<=base+0.01, "
                       "PROMISING iff both 4/4 + dSum>=+0.273; PRIMARY uncapped "
                       "w*y; year 2025 never scored for a variant",
            "costs": "maker 0.0002 / taker 0.00055 + v293 settle funding "
                     "(ledger-identical across arms)",
            "selection": "dev 2021-2024 only (robust criterion); 2023-2024 "
                         "overlap reported (depth starts 2023-01); 2025 scored "
                         "once for the chosen variant only (none chosen -> not scored)",
        },
        "baseline": {"v421_G2": v, "carry_G2_f0.25": {
            "R": cc["R"], "W": cc["W"], "DD": cc["DD"],
            "full_path_dd": cc["full_path_dd"]}},
        "ledger": {"n": int(len(df)), "phase0_sums": got_p0,
                   "dev_fills": int(n_dev)},
        "thresholds_p10": {f"{ay}/{MAJORS[ci]}": thresholds[(ay, ci)]
                           for ay in range(4) for ci in range(5)},
        "veto": {"S2_vetoed_dev_fills": int(n_veto_s2),
                 "vetoed_by_dev_year": veto_by_year},
        "base_unc": base_unc, "s1_unc": s1_unc, "s2_unc": s2_unc,
        "base_cap": base_cap, "s2_cap": s2_cap,
        "decision": {"S1": dec_s1, "S2": dec_s2,
                     "S2_capped_siderow": dec_s2_cap,
                     "chosen": chosen, "engine_run": engine_run,
                     "engine_note": "not run: no variant passed the dip "
                                    "screen (per assignment: engine only if "
                                    "the screen passes); no reset_metric / "
                                    "full-path DD beyond the reproduced "
                                    "baselines above"},
    }
    (HERE / "results.json").write_text(json.dumps(out, indent=1))
    print("wrote results.json", flush=True)


if __name__ == "__main__":
    main()
