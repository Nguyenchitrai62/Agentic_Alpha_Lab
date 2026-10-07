"""oc_outage compute: outage overlay on the validated 4-phase D0+B1 ledger.

Base ledger: research/tournament/oc_usdtdip/panel.parquet (D0 exits + B1 sizes,
4 clock phases; see PLAN.md). Outage intervals per PLAN.md (seeded weekly 2h,
monthly 6h, quarterly 24h; adversarial 10 worst market hours per year).
Deferred exits recomputed with exact 1m slices ONLY for fills whose base exit
falls inside an outage -- one coin's 1m O/H/L/C in RAM at a time (float32).
Peak < 0.4 GB by design (no heavy_slot). See PLAN.md for frozen definitions.

Usage:
  .venv/Scripts/python.exe research/tournament/oc_outage/compute_outage.py [--smoke]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import outage_core as K

ROOT = HERE.parents[2]
PANEL = ROOT / "research/tournament/oc_usdtdip/panel.parquet"

START = pd.Timestamp("2020-08-01", tz="UTC")
END = pd.Timestamp("2026-09-24 00:00", tz="UTC")
MAJORS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
ANCHORS = [pd.Timestamp(a, tz="UTC") for a in
           ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")]
YEAR_END = pd.Timestamp("2026-09-24 00:00", tz="UTC")
PHASES = (0, 1, 2, 3)
MIN_PER_YEAR = 525600  # 365d
EPOCH_DAY_MIN = 1440


def abs_min(ts: pd.Timestamp) -> int:
    return int((ts - START).total_seconds() // 60)


def abs_to_iso(m: int) -> str:
    return (START + pd.Timedelta(minutes=int(m))).isoformat()


ANCHOR_ABS = [abs_min(a) for a in ANCHORS]
YEAR_OF = {a.date().isoformat(): i for i, a in enumerate(ANCHORS)}


def load_1m(sym: str, cols):
    if sym == "BTCUSDT":
        files = sorted(Path("data/raw/btc_intraday_20260924").glob("klines_1m_20*.parquet"))
    else:
        files = sorted(Path("data/raw/majors_intraday_20260924").glob(f"{sym}_1m_20*.parquet"))
    parts = [pd.read_parquet(f, columns=["open_time"] + list(cols)) for f in files]
    m = pd.concat(parts, ignore_index=True)
    m["open_time"] = pd.to_datetime(m["open_time"], utc=True)
    m = m.drop_duplicates("open_time").sort_values("open_time")
    m = m[(m["open_time"] >= START) & (m["open_time"] <= END)]
    idx = pd.date_range(START, END, freq="1min")
    m = m.set_index("open_time").reindex(idx)
    out = {c: m[c].to_numpy(dtype=np.float32) for c in cols}
    del m, parts
    return idx, out


def cell_stats_days(day_ord: np.ndarray, wy: np.ndarray):
    return K.cell_stats(np.asarray(day_ord), np.asarray(wy, dtype=float))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true",
                    help="test-only: phase 0, first 500 fills; no files")
    args = ap.parse_args()

    panel = pd.read_parquet(PANEL)
    panel["yi"] = panel["year"].map(YEAR_OF)
    assert panel["yi"].notna().all()
    panel["yi"] = panel["yi"].astype(int)
    # absolute minutes
    panel["t_abs"] = panel["bar_ord"].astype(int)
    panel["te_abs"] = panel["t_abs"] + panel["x"].astype(int)
    panel["p_abs"] = panel["t_abs"] + K.LIVE_A
    # base exit day ordinal (days since START)
    bx = panel["x"].to_numpy(dtype=np.int64)
    ta = panel["t_abs"].to_numpy(dtype=np.int64)
    panel["d0_day"] = np.where(bx < 240, (ta + bx) // 1440, (ta + 240) // 1440)
    if args.smoke:
        panel = panel[panel["phase"] == 0].head(500).copy()
        print(f"smoke: {len(panel)} fills", flush=True)

    coins = sorted(panel["sym"].unique().tolist())
    coin_ix = {s: i for i, s in enumerate(MAJORS)}

    # ---- base stats per (year, phase) ----
    base_cell = {}
    for y in range(5):
        for p in PHASES:
            m = (panel["yi"] == y) & (panel["phase"] == p)
            wy = (panel.loc[m, "w_base"].to_numpy(float) *
                  panel.loc[m, "y"].to_numpy(float))
            s, wday, dd = cell_stats_days(panel.loc[m, "d0_day"].to_numpy(), wy)
            base_cell[(y, p)] = dict(S=s, W=wday, DD=dd, n=int(m.sum()),
                                    win=float((panel.loc[m, "y"].to_numpy(float) > 0).mean()) if m.any() else 0.0)

    # ---- seeded intervals (a/b/c), absolute minutes ----
    scenarios = {}
    scenarios["weekly_2h"] = sorted(
        sum((K.gen_block_outages(aa, 10080, 120, 101) for aa in ANCHOR_ABS), []))
    scenarios["monthly_6h"] = sorted(
        sum((K.gen_block_outages(aa, 43800, 360, 102) for aa in ANCHOR_ABS), []))
    scenarios["quarterly_24h"] = sorted(
        sum((K.gen_block_outages(aa, 131400, 1440, 103) for aa in ANCHOR_ABS), []))

    # ---- (d) worst market hours: hourly closes per coin, UTC-midnight grid ----
    # hour starts (abs) covering [A, A+365d) per year
    hadv = []
    if not args.smoke:
        hourly_close = {}
        for sym in MAJORS:
            _, d = load_1m(sym, ["close"])
            C = d["close"].astype(float)
            del d
            hourly_close[sym] = C
            print(f"loaded close {sym}", flush=True)
        n_all = len(next(iter(hourly_close.values())))
        for y, aa in enumerate(ANCHOR_ABS):
            hs = list(range(aa, aa + MIN_PER_YEAR, 60))
            rets = np.full(len(hs), np.nan)
            for i, h in enumerate(hs):
                if h + 60 >= n_all:
                    continue
                rs = []
                ok = True
                for sym in MAJORS:
                    c0 = hourly_close[sym][h]
                    c1 = hourly_close[sym][h + 60]
                    if not (np.isfinite(c0) and np.isfinite(c1)) or c0 <= 0:
                        ok = False
                        break
                    rs.append(c1 / c0 - 1)
                if ok:
                    rets[i] = float(np.mean(rs))
            pick = K.rank_worst_hours(np.array(hs), rets, 10)
            for i in pick:
                hadv.append((hs[i], hs[i] + 60))
            print(f"year {y}: worst-hour mean rets "
                  f"{sorted([round(float(rets[i]), 5) for i in pick])}", flush=True)
        del hourly_close
    scenarios["adversarial_10h"] = sorted(hadv)
    for k, v in scenarios.items():
        print(f"{k}: {len(v)} intervals", flush=True)

    if args.smoke:
        # light check: interval counts + a placement probe, no files
        print(json.dumps({k: len(v) for k, v in scenarios.items()}, indent=1))
        return

    # ---- per-fill outage flags (vectorised per scenario via searchsorted) ----
    panel_idx = panel.reset_index(drop=True)
    p_abs = panel_idx["p_abs"].to_numpy(dtype=np.int64)
    te_abs = panel_idx["te_abs"].to_numpy(dtype=np.int64)
    # NOTE: the panel carries no exit-kind column; for fills whose base exit
    # minute is offline we recompute the base outcome from exact 1m slices
    # (and validate it against the panel row) to recover the kind, then
    # apply_outage_to_fill leaves native TP/backstop exits unchanged.
    scen_data = {}
    for sname, ivs in scenarios.items():
        starts = np.array([s for s, _ in ivs], dtype=np.int64)
        ends = np.array([e for _, e in ivs], dtype=np.int64)
        # offline(m) <-> starts[j] <= m < ends[j], j = searchsorted(starts, m)-1
        def flag(arr):
            j = np.searchsorted(starts, arr, side="right") - 1
            ok = (j >= 0) & (arr < ends[np.clip(j, 0, len(ends) - 1)])
            return ok
        missed = flag(p_abs)
        te_off = flag(te_abs)
        scen_data[sname] = dict(intervals=ivs, missed=missed, te_off=te_off)
        print(f"{sname}: missed={int(missed.sum())} te_off={int(te_off.sum())}",
              flush=True)

    # ---- recompute deferred exits per coin (exact 1m slices, candidates only) ----
    # bar opens/sigmas per (phase, coin) for lv/sg/o2/settle
    n_all = None
    O_all = {}
    for sym in MAJORS:
        _, d = load_1m(sym, ["open"])
        O_all[sym] = d["open"]
        if n_all is None:
            n_all = len(d["open"])
        print(f"loaded open {sym}", flush=True)
    grids = {}
    for p in PHASES:
        off = p * 60
        nb = (n_all - off) // 240
        grids[p] = dict(off=off, nb=nb)
    sig_lookup = {}  # (sym, phase) -> (opens float array, sig array)
    for sym in MAJORS:
        O = O_all[sym].astype(float)
        for p in PHASES:
            off, nb = grids[p]["off"], grids[p]["nb"]
            ob = O[off:off + nb * 240:240].astype(float)
            sg = pd.Series(ob).pct_change().rolling(360, min_periods=120).std(ddof=1).shift(1).to_numpy()
            sig_lookup[(sym, p)] = (ob, sg)
        print(f"sigma {sym}", flush=True)

    # candidate rows needing 1m slices: any scenario te_off and not missed
    need = np.zeros(len(panel_idx), dtype=bool)
    for sname in scenarios:
        need |= (scen_data[sname]["te_off"] & ~scen_data[sname]["missed"])
    print(f"fills needing recompute: {int(need.sum())}/{len(panel_idx)}", flush=True)

    # y_scen / day_scen per scenario; init with base (missed -> NaN weight 0)
    y_base = panel_idx["y"].to_numpy(float)
    w_base = panel_idx["w_base"].to_numpy(float)
    d_base = panel_idx["d0_day"].to_numpy(dtype=np.int64)
    res = {}
    for sname in scenarios:
        res[sname] = dict(y=np.array(y_base), day=np.array(d_base),
                          kept=~scen_data[sname]["missed"])

    # process per coin
    for sym in MAJORS:
        _, d = load_1m(sym, ["open", "high", "low", "close"])
        O = d["open"].astype(float)
        H = d["high"].astype(float)
        L = d["low"].astype(float)
        C = d["close"].astype(float)
        del d
        rows = np.where((panel_idx["sym"] == sym).to_numpy() & need)[0]
        print(f"{sym}: recompute rows={len(rows)}", flush=True)
        for r in rows:
            prow = panel_idx.iloc[r]
            p = int(prow["phase"])
            t_abs = int(prow["t_abs"])
            f = int(prow["f"])
            k = float(prow["rung_k"])
            off = grids[p]["off"]
            j = (t_abs - off) // 240
            ob, sgarr = sig_lookup[(sym, p)]
            if j < 0 or j >= len(ob):
                continue
            o1, sg = float(ob[j]), float(sgarr[j])
            if not (np.isfinite(o1) and np.isfinite(sg)) or o1 <= 0 or sg <= 0:
                continue
            lv = o1 * (1 - k * sg)
            o2m = O[t_abs + 240] if 0 <= t_abs + 240 < len(O) else np.nan
            o2 = float(o2m) if np.isfinite(o2m) else np.nan
            settle = (((t_abs + 240) // 60) % 24) in (0, 8, 16)
            Ha_b = H[t_abs:t_abs + 240]
            La_b = L[t_abs:t_abs + 240]
            Ca_b = C[t_abs:t_abs + 240]
            Oa_b = O[t_abs:t_abs + 240]
            if len(Ha_b) < 240:
                continue
            # recover base outcome from slices (validates the panel row)
            bret, bx, bhow = K.outcome_mu(Ha_b, La_b, Ca_b, Oa_b, f, lv, sg,
                                          1.0, o2, settle)
            if not np.isfinite(bret):
                continue
            if abs(bret - float(prow["y"])) > 1e-6 or int(bx) != int(prow["x"]):
                # panel/base mismatch (e.g. Y2 leap-day grid edge): keep base
                continue
            for sname, ivs in scenarios.items():
                if scen_data[sname]["missed"][r]:
                    continue
                if not scen_data[sname]["te_off"][r]:
                    continue
                ret, xo, how, delayed, rescued = K.apply_outage_to_fill(
                    f, lv, sg, bret, int(bx), bhow, t_abs, o2, settle,
                    H, L, O, ivs)
                if not np.isfinite(ret):
                    res[sname]["kept"][r] = False
                    continue
                res[sname]["y"][r] = float(ret)
                ce_day = (t_abs + int(xo)) // 1440
                res[sname]["day"][r] = int(ce_day)
        del O, H, L, C

    # ---- scoring ----
    def score_arm(yv, dv, kept):
        cells = {}
        for yy in range(5):
            per_p = {}
            for p in PHASES:
                m = ((panel_idx["yi"] == yy) & (panel_idx["phase"] == p)
                     & kept).to_numpy()
                wy = (w_base[m] * yv[m]) if m.any() else np.array([])
                dd = dv[m] if m.any() else np.array([], dtype=np.int64)
                s, wday, ddraw = cell_stats_days(dd, wy)
                n = int(m.sum())
                win = float((yv[m] > 0).mean()) if n else 0.0
                per_p[p] = dict(S=s, W=wday, DD=ddraw, n=n, win=win)
            cells[yy] = per_p
        return cells

    base_cells = score_arm(y_base, d_base, np.ones(len(panel_idx), bool))
    scen_cells = {s: score_arm(res[s]["y"], res[s]["day"], res[s]["kept"])
                  for s in scenarios}

    def four_phase_mean(cells, yy, key):
        return float(np.mean([cells[yy][p][key] for p in PHASES]))

    years = []
    for yy in range(5):
        row = {"year": ANCHORS[yy].date().isoformat(),
               "base": {k: round(four_phase_mean(base_cells, yy, k), 6)
                        for k in ("S", "W", "DD", "n", "win")},
               "per_phase_base_S": [round(base_cells[yy][p]["S"], 6) for p in PHASES],
               "scenarios": {}}
        for sname in scenarios:
            sc = scen_cells[sname]
            S = four_phase_mean(sc, yy, "S")
            Sb = four_phase_mean(base_cells, yy, "S")
            # missed vs late (year, 4-phase-mean units: mean over phases)
            missed_ph, late_ph = [], []
            for p in PHASES:
                m = ((panel_idx["yi"] == yy) & (panel_idx["phase"] == p)).to_numpy()
                miss = scen_data[sname]["missed"] & m
                kept = (~scen_data[sname]["missed"]) & m
                missed_ph.append(float((w_base[miss] * y_base[miss]).sum()))
                late_ph.append(float((w_base[kept] *
                                      (y_base[kept] - res[sname]["y"][kept])).sum()))
            missed_m = float(np.mean(missed_ph))
            late_m = float(np.mean(late_ph))
            loss = float(Sb - S)
            if abs(loss) > 1e-12:
                sh_m, sh_l = missed_m / loss, late_m / loss
            else:
                sh_m, sh_l = None, None
            row["scenarios"][sname] = {
                "S": round(S, 6), "W": round(four_phase_mean(sc, yy, "W"), 6),
                "DD": round(four_phase_mean(sc, yy, "DD"), 6),
                "n": round(four_phase_mean(sc, yy, "n"), 6),
                "win": round(four_phase_mean(sc, yy, "win"), 6),
                "dS_vs_base": round(S - Sb, 6),
                "missed": round(missed_m, 6), "late": round(late_m, 6),
                "share_missed": (round(sh_m, 4) if sh_m is not None else None),
                "share_late": (round(sh_l, 4) if sh_l is not None else None),
                "per_phase_S": [round(sc[yy][p]["S"], 6) for p in PHASES],
                "per_phase_DD": [round(sc[yy][p]["DD"], 6) for p in PHASES],
            }
        years.append(row)

    # 5y rollups + worst episodes
    summary = {}
    for sname in scenarios:
        base5 = float(sum(four_phase_mean(base_cells, yy, "S") for yy in range(5)))
        scen5 = float(sum(four_phase_mean(scen_cells[sname], yy, "S") for yy in range(5)))
        # pooled full path (all phases, exit-date order)
        kept = res[sname]["kept"]
        s_full, _, dd_full = K.cell_stats(res[sname]["day"][kept],
                                          (w_base[kept] * res[sname]["y"][kept]))
        bkept = np.ones(len(panel_idx), bool)
        bs_full, _, bdd_full = K.cell_stats(d_base, w_base * y_base)
        # episode losses
        ivs = scenarios[sname]
        ep = []
        for (s_, e_) in ivs:
            m_miss = scen_data[sname]["missed"] & (p_abs >= s_) & (p_abs < e_)
            m_delay = (~scen_data[sname]["missed"]) & scen_data[sname]["te_off"] \
                & (te_abs >= s_) & (te_abs < e_)
            loss_miss = float((w_base[m_miss] * y_base[m_miss]).sum())
            loss_late = float((w_base[m_delay] *
                               (y_base[m_delay] - res[sname]["y"][m_delay])).sum())
            ep.append(dict(start=abs_to_iso(s_), end=abs_to_iso(e_),
                           loss=loss_miss + loss_late, missed=loss_miss,
                           late=loss_late, n_missed=int(m_miss.sum()),
                           n_delayed=int(m_delay.sum())))
        ep_sorted = sorted(ep, key=lambda d: d["loss"], reverse=True)
        worst = ep_sorted[0] if ep_sorted else None
        summary[sname] = {
            "base_5y_4pmean_sum": round(base5, 6),
            "scen_5y_4pmean_sum": round(scen5, 6),
            "loss_5y": round(base5 - scen5, 6),
            "base_full_pooled": {"sum": round(bs_full, 6), "dd": round(bdd_full, 6)},
            "scen_full_pooled": {"sum": round(s_full, 6), "dd": round(dd_full, 6)},
            "n_intervals": len(ivs),
            "n_missed_fills": int(scen_data[sname]["missed"].sum()),
            "worst_episode": ({k: (round(v, 6) if isinstance(v, float) else v)
                                for k, v in worst.items()} if worst else None),
            "top5_episodes": [{k: (round(v, 6) if isinstance(v, float) else v)
                               for k, v in d.items()} for d in ep_sorted[:5]],
        }
        # 5y shares
        tot_miss = tot_late = 0.0
        for yy in range(5):
            tot_miss += years[yy]["scenarios"][sname]["missed"]
            tot_late += years[yy]["scenarios"][sname]["late"]
        loss5 = base5 - scen5
        summary[sname]["missed_5y"] = round(tot_miss, 6)
        summary[sname]["late_5y"] = round(tot_late, 6)
        if abs(loss5) > 1e-12:
            summary[sname]["share_missed_5y"] = round(tot_miss / loss5, 4)
            summary[sname]["share_late_5y"] = round(tot_late / loss5, 4)
        else:
            summary[sname]["share_missed_5y"] = None
            summary[sname]["share_late_5y"] = None

    # cross-checks: phase-0 raw sums vs refs
    ref_p0 = [2.388052, 0.182865, 3.809764, 2.579274, 0.711509]
    got_p0 = []
    for yy in range(5):
        m = ((panel_idx["yi"] == yy) & (panel_idx["phase"] == 0)).to_numpy()
        got_p0.append(float((w_base[m] * y_base[m]).sum()))
    chk = hashlib.sha256(np.round(np.stack([w_base, y_base]), 9).tobytes()).hexdigest()[:16]

    out = {
        "config": {
            "base": "oc_usdtdip panel.parquet base arm (D0 + B1, 4 phases)",
            "bars": "open in [2021-09-24, 2026-09-24)",
            "grid": "4h from 2020-08-01 00:00 UTC + 0/1/2/3h; phase 0 == oc_dipexit grid",
            "live": [K.LIVE_A, K.LIVE_B], "maker": K.MAKER, "taker": K.TAKER,
            "fund_long": K.FUND, "settle_hours": list(K.SETTLE_HOURS),
            "placement": "bar missed iff T+16 in an outage interval",
            "exits": "native TP/backstop always; close5/time deferred to first online minute open",
            "scenarios": {
                "weekly_2h": "52x120m/week, seed 101",
                "monthly_6h": "12x360m/30.44d-month, seed 102",
                "quarterly_24h": "4x1440m/quarter, seed 103",
                "adversarial_10h": "10 lowest mean-majors 1h returns per 365d year (UTC-midnight grid)",
            },
            "daily": "scenario-exit-date UTC sums; maxDD of cumulative daily-sum path from 0",
            "resources": "one process, one-coin 1m slices for candidates only; peak < 0.4 GB",
        },
        "n_fills_base": int(len(panel_idx)),
        "ledger_checksum": chk,
        "phase0_fidelity": {"got_raw_sums": [round(s, 6) for s in got_p0],
                            "ref_raw_sums": ref_p0},
        "intervals": {s: [{"start": abs_to_iso(a), "end": abs_to_iso(b)}
                          for a, b in scenarios[s]] for s in scenarios},
        "years": years,
        "summary": summary,
    }
    (HERE / "results.json").write_text(json.dumps(out, indent=1))
    print("n_fills", len(panel_idx), "checksum", chk, flush=True)
    for sname in scenarios:
        print(sname, json.dumps(summary[sname], indent=1)[:800], flush=True)


if __name__ == "__main__":
    main()
