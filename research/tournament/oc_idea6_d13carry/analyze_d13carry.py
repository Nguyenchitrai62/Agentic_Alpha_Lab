"""oc_idea6_d13carry: DD<15 stretch — D13BF + concentrated (max-coin) carry f=0.50.

Assignment: docs/opencode/OPENCODE_W_oc_idea6_d13carry.md + IDEAS_20261007 §6.
Pre-registered (REPORT.md, frozen BEFORE this ran — no other variants):
  S1 D13BF + max-coin carry f=0.50 (split capital per oc_utamargin).
  S2 S1 with idea-#1 K1 dip sizing (ENGINE-REQUIRED, NOT scored here).

Method (reused UNCHANGED from audited blocks, nothing refit):
- Base: v424 R2B1D13BF stored 4-phase runs via reset_metric.year_reset
  exactly (research/diagnostics/r2_decompose5/reset_metric.py).
- Carry rule: frozen oc_cashcarry (PLAN pre-registered): roll next-quarter at
  <=7d, enter iff ann basis >= 4 %, equal-notional spot long + quarterly
  short, hold to delivery, fees spot 0.001/side + fut 0.00055/0.0002
  (drag 0.00275). 33 trades reused verbatim (asserted).
- Max-coin filter (idea #4 M1): per delivery, when BOTH BTC and ETH pass,
  keep ONLY the higher ann_basis coin (basis from entry-bar closes only —
  causal; single-coin deliveries unchanged). No fitting, no test-year stat.
- Combination (equity-level, oc_carryd13 convention, imported not modified):
  per anchor year, 4-phase mix reset to 1.0 + carry at f of YEAR-START equity
  (yearly rebalance, labelled), carry marked HOURLY causal (last CLOSED
  hourly bar strictly before t; 0 before entry-bar close; locked to frozen
  ret_alloc from settlement-bar close); combined es/ms = base es/ms + carry
  curve; 5y/dev means = geometric mean of yearly monthly factors;
  full-path DD = chained-reset path (labelled). Sizing differs from the
  oc_carrycompound compounding convention (f x live A) — both baselines are
  reproduced below for the comparison, S1 uses the oc_carryd13 convention so
  it is directly comparable to the 5.104/14.85 + 5.234/14.71 map.
- Selection ONLY on dev years 2021-2024 (robust criterion). Recent year
  2025-09-24..2026-09-23 scored ONCE, for the winner only. Baseline
  reproductions below re-check already-published numbers (validation, not
  selection) and are labelled POST-HOC.

Reads: v421/v424 result JSONs + runs.pkl, oc_cashcarry/carrycompound/
  carryd13 results.json, ext/hourly_ext.parquet (t < 2026-09-24, asserted),
  data/raw/qbasis_20261003/um_*_1h.parquet, one spot-4h file (delivery grid).
Writes: research/tournament/oc_idea6_d13carry/results.json
One process, 4h+1h data only (no 1m), no engine reruns.

Usage: .venv/Scripts/python.exe research/tournament/oc_idea6_d13carry/analyze_d13carry.py
"""

from __future__ import annotations

import importlib.util
import json
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
RD = ROOT / "research/parallel/rounds/parallel-20260906-r2"
CC = ROOT / "research/tournament/oc_cashcarry"
CCMP = ROOT / "research/tournament/oc_carrycompound"
CD13 = ROOT / "research/tournament/oc_carryd13"
HOURLY = ROOT / "research/tournament/ext/hourly_ext.parquet"
QDIR = ROOT / "data/raw/qbasis_20261003"
SDIR = ROOT / "data/raw/spot_majors_20260925"

F_S1 = 0.50
DEV_YEARS = (0, 1, 2, 3)  # anchors 2021..2024 — selection ONLY here
RECENT_YEAR = 4  # anchor 2025-09-24 — scored once, winner only
CAP = pd.Timestamp("2026-09-24 00:00", tz="UTC")


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def geo_mean_pct(monthlies) -> float:
    m = np.asarray(monthlies, dtype=float)
    return float((np.prod(1 + m / 100) ** (1 / len(m)) - 1) * 100)


def main() -> None:
    v388 = _load("v388_for_d13carry", RD / "v388" / "v388_bot_stop_distance.py")
    rm = _load("reset_for_d13carry",
               ROOT / "research/diagnostics/r2_decompose5/reset_metric.py")
    d13mod = _load("combine_carryd13_reuse", CD13 / "combine_carryd13.py")
    last_close_before = d13mod.last_close_before
    FEE_ENTRY_PAID = d13mod.FEE_ENTRY_PAID
    assert FEE_ENTRY_PAID == 0.001 + 0.00055
    G0 = d13mod.G0
    g1 = v388.Y1 + pd.Timedelta(hours=12)
    ANCH = [pd.Timestamp(a, tz="UTC") for a in v388.ANCH]
    assert [str(a.date()) for a in ANCH] == [
        "2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24",
        "2025-09-24"], ANCH
    YEAR = pd.Timedelta(days=365)
    grid = pd.date_range(G0, g1, freq="1h")
    gn = grid.values.astype("datetime64[ns]").astype(np.int64)

    # ---- 1. baseline gate: reproduce published numbers exactly, else STOP ----
    v421 = json.loads((RD / "v421" / "v421_result.json").read_text())
    g2off = v421["rows"]["R2B1D17BFG2"]
    assert (g2off["R"], g2off["W"], g2off["DD"]) == (5.41, 2.588, 16.91), g2off
    assert g2off["full_path_dd"] == 16.82, g2off
    v424 = json.loads((RD / "v424" / "v424_result.json").read_text())
    d13off = v424["rows"]["R2B1D13BF"]
    assert (d13off["R"], d13off["W"], d13off["DD"]) == (4.971, 2.485, 14.98)
    assert d13off["full_path_dd"] == 14.86, d13off
    ccmp = json.loads((CCMP / "results.json").read_text())
    cmp25 = ccmp["rows"]["G2_f0.25"]
    assert (cmp25["R"], cmp25["W"], cmp25["DD"]) == (5.634, 2.778, 16.75)
    assert cmp25["full_path_dd"]["full"] == 16.66, cmp25
    assert ccmp["carry_add_pp_per_month"] == 0.224
    cmp0 = ccmp["rows"]["G2_f0.0"]
    assert cmp0["R"] == g2off["R"] and cmp0["W"] == g2off["W"]
    assert cmp0["DD"] == g2off["DD"]
    assert cmp0["full_path_dd"]["full"] == g2off["full_path_dd"]
    cd13 = json.loads((CD13 / "results.json").read_text())
    by_f = {c["f"]: c for c in cd13["combos"]}
    assert (by_f[0.25]["R_5y"], by_f[0.25]["DD_maxyearly"]) == (5.104, 14.85)
    assert (by_f[0.5]["R_5y"], by_f[0.5]["DD_maxyearly"]) == (5.234, 14.71)
    print("baseline gate OK: G2 5.41 + compound 5.634/16.75/16.66 + "
          "d13 maps 5.104/14.85 + 5.234/14.71")

    # base D13BF via the shared reset metric (exact function) — validation
    runs = pickle.loads((RD / "v424" / "v424_runs.pkl").read_bytes())
    assert set(runs) == {0, 1, 2, 3}
    base5 = [rm.year_reset(runs, "R2B1D13BF", y) for y in range(5)]
    assert [b["R"] for b in base5] == [r for r, _ in d13off["years"]], base5
    assert [b["DD"] for b in base5] == [d for _, d in d13off["years"]], base5
    print("D13BF base reproduces v424_result to the digit")

    # ---- 2. frozen carry trades + max-coin filter (idea #4 M1, causal) ----
    cc = json.loads((CC / "results.json").read_text())
    assert cc["meta"]["threshold_ann_basis"] == 0.04
    assert len(cc["trades"]) == 33 and cc["n_skipped"] == 13
    assert cc["n_incomplete"] == 2
    for t in cc["trades"]:
        assert t["ann_basis"] >= 0.04 - 1e-9
        assert t["ret_alloc"] > 0
    by_del: dict[str, list[dict]] = {}
    for t in cc["trades"]:
        by_del.setdefault(t["delivery"], []).append(t)
    kept, excluded = [], []
    for dl, ts in sorted(by_del.items()):
        coins = {t["coin"] for t in ts}
        if coins == {"BTC", "ETH"} and len(ts) == 2:
            ts = sorted(ts, key=lambda t: t["ann_basis"], reverse=True)
            # tie-break frozen: higher ret_alloc (entry-known locked gross)
            if ts[0]["ann_basis"] == ts[1]["ann_basis"]:
                ts = sorted(ts, key=lambda t: t["ret_alloc"], reverse=True)
            kept.append(ts[0])
            excluded.append(ts[1])
        else:
            assert len(ts) == 1, (dl, ts)
            kept.append(ts[0])
    assert len(kept) + len(excluded) == 33
    assert len(kept) == len(by_del) == 18 and len(excluded) == 15
    # causality: pick uses ONLY entry-bar-known frozen basis (no future info)
    for k in kept:
        assert k["ann_basis"] >= 0.04 - 1e-9 and k["ret_alloc"] > 0
    print(f"max-coin: 33 -> {len(kept)} kept / {len(excluded)} excluded "
          f"({len(by_del)} deliveries)")

    # ---- 3. hourly marks (causal, same as combine_carryd13) ----
    h = pd.read_parquet(HOURLY, columns=["t", "close", "sym"])
    h["t"] = pd.to_datetime(h["t"], utc=True)
    assert bool((h["t"] < CAP).all()), "hourly data reaches beyond the cap"
    spot: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    for coin in ("BTC", "ETH"):
        d = h[h["sym"] == f"{coin}USDT"].sort_values("t")
        spot[coin] = (d["t"].values.astype("datetime64[ns]").astype(np.int64),
                      d["close"].to_numpy(dtype=float))
    qmap: dict[tuple[str, str], tuple[np.ndarray, np.ndarray]] = {}
    for t in kept:
        key = (t["coin"], t["delivery"])
        if key in qmap:
            continue
        y, m, dd = t["delivery"].split("-")
        code = f"{y[2:]}{m}{dd}"
        (f,) = sorted(QDIR.glob(f"um_{t['coin']}USDT_{code}_1h.parquet"))
        q = pd.read_parquet(f, columns=["open_time", "close"])
        qo = pd.to_datetime(q["open_time"], utc=True).values.astype(
            "datetime64[ns]").astype(np.int64)
        o = np.argsort(qo)
        qmap[key] = (qo[o], q["close"].to_numpy(dtype=float)[o])
    s4 = pd.read_parquet(SDIR / "BTCUSDT_spot_4h.parquet",
                         columns=["open_time", "close_time"])
    s4o = pd.to_datetime(s4["open_time"], utc=True)
    s4c = pd.to_datetime(s4["close_time"], utc=True)
    trades = []
    for t in kept:
        te = pd.Timestamp(t["entry_open"], tz="UTC")
        tc = te + pd.Timedelta(hours=4)
        assert (s4o == te).any(), t
        D = pd.Timestamp(t["delivery"] + " 08:00", tz="UTC")
        si = int(np.searchsorted(
            s4c.values.astype("datetime64[ns]").astype(np.int64),
            D.value, side="right"))
        assert si < len(s4), t
        ts = s4c.iloc[si]
        assert ts > tc, t
        trades.append({"coin": t["coin"], "delivery": t["delivery"],
                       "ann_basis": float(t["ann_basis"]),
                       "F_entry": float(t["F_entry"]),
                       "S_entry": float(t["S_entry"]),
                       "ret_alloc": float(t["ret_alloc"]),
                       "tc_ns": tc.value, "ts_ns": ts.value})
    raw = np.zeros(len(grid))
    for tr in trades:
        st, sc = spot[tr["coin"]]
        ft, fc = qmap[(tr["coin"], tr["delivery"])]
        S = last_close_before(st, sc, gn)
        F = last_close_before(ft, fc, gn)
        with np.errstate(divide="ignore", invalid="ignore"):
            mtm = ((S / tr["S_entry"] - 1.0)
                   + ((tr["F_entry"] - F) / tr["F_entry"]) - FEE_ENTRY_PAID)
        mtm[~np.isfinite(mtm)] = np.nan
        mtm = pd.Series(mtm, index=grid).ffill().to_numpy()
        v = np.zeros(len(grid))
        open_m = gn > tr["tc_ns"]
        settled_m = gn >= tr["ts_ns"]
        hold_m = open_m & ~settled_m
        v[hold_m] = mtm[hold_m]
        v[hold_m & ~np.isfinite(mtm)] = 0.0
        v[settled_m] = tr["ret_alloc"]
        tr["mtm"] = v
        raw += v
    a_ns = np.array([a.value for a in ANCH])
    raw_at_anchor = []
    for a in a_ns:
        tot = 0.0
        qa = np.array([a])
        for tr in trades:
            if a <= tr["tc_ns"]:
                continue
            if a >= tr["ts_ns"]:
                tot += tr["ret_alloc"]
                continue
            st, sc = spot[tr["coin"]]
            ft, fc = qmap[(tr["coin"], tr["delivery"])]
            S = last_close_before(st, sc, qa)[0]
            F = last_close_before(ft, fc, qa)[0]
            if np.isfinite(S) and np.isfinite(F):
                tot += ((S / tr["S_entry"] - 1.0)
                        + ((tr["F_entry"] - F) / tr["F_entry"])
                        - FEE_ENTRY_PAID)
        raw_at_anchor.append(tot)
    raw_at_anchor = np.array(raw_at_anchor)

    # ---- 4. D13BF base paths on the shared grid ----
    E, MN = [], []
    for s in range(4):
        e1, m1 = v388.hourly(runs[s]["R2B1D13BF"], G0, g1)
        assert (e1.index == grid).all()
        E.append(e1)
        MN.append(m1)

    def combine_year(y: int, f: float):
        a0 = ANCH[y]
        a1 = a0 + YEAR
        seg = (grid > a0) & (grid <= a1)
        b = np.array([float(e[e.index <= a0].iloc[-1])
                      if (e.index <= a0).any() else 1.0 for e in E])
        es = sum(e[seg] / bb for e, bb in zip(E, b)) / 4
        ms = sum(m[seg] / bb for m, bb in zip(MN, b)) / 4
        cy = f * (raw[seg] - raw_at_anchor[y])
        c = pd.Series(cy, index=es.index)
        es_c = es + c
        ms_c = ms + c
        pk = np.maximum.accumulate(es_c.to_numpy())
        R = round(100 * float(es_c.iloc[-1] ** (1 / 12) - 1), 3)
        DD = round(100 * float(np.max(1 - ms_c.to_numpy() / pk)), 2)
        return {"R": R, "DD": DD, "total_pct": round(
            float(es_c.iloc[-1] - 1) * 100, 4),
            "es_end": float(es_c.iloc[-1]),
            "es": es_c.to_numpy(), "ms": ms_c.to_numpy()}

    # ---- 5. DEV-ONLY selection (2021-2024); S2 unscored by design ----
    s1_dev = [combine_year(y, F_S1) for y in DEV_YEARS]
    s1_dev_R = [d["R"] for d in s1_dev]
    s1_dev_DD = [d["DD"] for d in s1_dev]
    dev4 = {"R": round(geo_mean_pct(s1_dev_R), 3),
            "W": min(s1_dev_R),
            "DD": max(s1_dev_DD),
            "losing": sum(r < 0 for r in s1_dev_R)}
    base_dev = [base5[y] for y in DEV_YEARS]
    base_dev4 = {"R": round(geo_mean_pct([b["R"] for b in base_dev]), 3),
                 "W": min(b["R"] for b in base_dev),
                 "DD": max(b["DD"] for b in base_dev)}
    # S2: pre-registered but NOT scored — K1 dip sizing needs a full 4-phase
    # engine rerun with 1m data; book legs are judged ONLY in that engine,
    # never a vectorised proxy. No S2 numbers are computed here.
    s2_status = ("ENGINE-REQUIRED: K1 dip sizing (budget-normalised "
                 "1/(1+n)-prior x 0.25) needs a full 4-phase engine rerun; "
                 "not scored, no proxy used for selection.")
    # robust criterion on dev only; S1 is the sole scored variant
    s1_ok = dev4["DD"] <= 20 and dev4["losing"] == 0
    winner = "S1" if s1_ok else "NONE"
    print(f"S1 dev4: {dev4} base dev4: {base_dev4} winner={winner}")

    # ---- 6. recent year ONCE, winner only ----
    recent = None
    chained_full_dev = None
    if winner == "S1":
        r = combine_year(RECENT_YEAR, F_S1)
        recent = {"anchor": str(ANCH[RECENT_YEAR].date()), "R": r["R"],
                  "DD": r["DD"], "total_pct": r["total_pct"]}
        # chained-reset full path: dev segments + recent, chained (labelled)
        lvl, fes, fms = 1.0, [], []
        for y in list(DEV_YEARS) + [RECENT_YEAR]:
            d = combine_year(y, F_S1)
            fes.append(d["es"] * lvl)
            fms.append(d["ms"] * lvl)
            lvl *= d["es_end"]
        fes, fms = np.concatenate(fes), np.concatenate(fms)
        full_chained = round(
            100 * float(np.max(1 - fms / np.maximum.accumulate(fes))), 2)
        # dev-only chained path (selection context)
        lvl, des, dms = 1.0, [], []
        for d in s1_dev:
            des.append(d["es"] * lvl)
            dms.append(d["ms"] * lvl)
            lvl *= d["es_end"]
        des, dms = np.concatenate(des), np.concatenate(dms)
        chained_full_dev = round(
            100 * float(np.max(1 - dms / np.maximum.accumulate(des))), 2)
    five = None
    if winner == "S1":
        allR = s1_dev_R + [recent["R"]]
        five = {"R": round(geo_mean_pct(allR), 3), "W": min(allR),
                "DD": max(s1_dev_DD + [recent["DD"]]),
                "losing": sum(x < 0 for x in allR)}

    # ---- 7. UTA bound (max-coin overlap; inherits oc_utamargin verdict) ----
    open_mat = np.zeros((len(grid), len(trades)))
    for j, tr in enumerate(trades):
        open_mat[:, j] = ((gn > tr["tc_ns"]) & (gn < tr["ts_ns"])).astype(float)
    overlap = open_mat.sum(axis=1)
    max_overlap = int(overlap.max())
    peak_spot_cost = round(max_overlap * F_S1, 4)  # fraction of year-start Eq
    uta = {"max_overlap_pairs": max_overlap,
           "peak_spot_cost_per_yearstart_eq": peak_spot_cost,
           "bothcoin_ref_peak_per_eq": 1.799,
           "verdict": ("SPLIT CAPITAL ONLY at f=0.50: oc_utamargin finds "
                       "1 blocked hour + spot cost 179.9% Eq additive; "
                       "oc_utamargin2 finds f=0.50 blocked under haircut "
                       "stress at EVERY leverage (5x/10x/20x). Max-coin "
                       "lightens overlap "
                       f"({max_overlap} vs 3 pairs) but peak indexed cost "
                       f"({peak_spot_cost} of year-start Eq) still needs a "
                       "separate USDT wallet / borrow; NOT cleared additive "
                       "on one UTA.")}

    out = {
        "meta": {
            "pre_reg": ["S1 D13BF+maxcoin-carry f0.50 split-capital",
                        "S2 S1 with idea-#1 K1 sizing (ENGINE-REQUIRED)"],
            "base": "v424/R2B1D13BF frozen 4-phase runs via reset_metric"
                    ".year_reset exactly",
            "carry_rule": "frozen oc_cashcarry (4% filter, 33 trades reused "
                          "verbatim); max-coin M1: per delivery keep higher "
                          "ann_basis (entry-known only), 18 kept / 15 out",
            "combination": "equity-level oc_carryd13 convention: f of "
                           "year-start equity, hourly causal marks, "
                           "chained-reset full-path DD (labelled); NOT the "
                           "oc_carrycompound live-A compounding convention",
            "sizing": "f=0.50 of year-start equity (yearly rebalance); "
                      "split-capital deployment per oc_utamargin/2",
            "gate_costs": "BOT base = stored 4-phase equities (research "
                          "engine maker 0.02% / taker 0.055% + gate funding "
                          "longs 0.01%/8h); carry = frozen spot 0.001/side "
                          "+ fut 0.00055/0.0002, delivery future pays NO "
                          "funding",
            "selection": "dev years 2021-2024 ONLY, robust criterion "
                         "(DD<=20, no losing dev year; prefer dev4>=5 then "
                         "highest dev4 WORST); recent scored once for winner",
            "post_hoc": True,
            "data_cap": "2026-09-24T00:00:00Z",
        },
        "baseline_checks": {
            "G2_official": {"R": g2off["R"], "W": g2off["W"],
                            "DD": g2off["DD"],
                            "full_path_dd": g2off["full_path_dd"]},
            "D13BF_official": {"R": d13off["R"], "W": d13off["W"],
                               "DD": d13off["DD"],
                               "full_path_dd": d13off["full_path_dd"]},
            "G2_carrycompound_f0.25": {"R": cmp25["R"], "W": cmp25["W"],
                                      "DD": cmp25["DD"],
                                      "full": cmp25["full_path_dd"]["full"],
                                      "add_pp": ccmp["carry_add_pp_per_month"]},
            "bothcoin_d13_f0.25": {"R": by_f[0.25]["R_5y"],
                                   "DD": by_f[0.25]["DD_maxyearly"]},
            "bothcoin_d13_f0.50": {"R": by_f[0.5]["R_5y"],
                                   "DD": by_f[0.5]["DD_maxyearly"]},
        },
        "maxcoin": {
            "kept": [{"coin": t["coin"], "delivery": t["delivery"],
                      "ann_basis": round(t["ann_basis"], 6),
                      "ret_alloc": t["ret_alloc"]} for t in trades],
            "n_kept": len(kept), "n_excluded": len(excluded),
            "excluded_deliveries": sorted({t["delivery"] for t in excluded}),
        },
        "S1_dev_years": [
            {"anchor": str(ANCH[y].date()), "R": s1_dev[i]["R"],
             "DD": s1_dev[i]["DD"], "base_R": base5[y]["R"],
             "base_DD": base5[y]["DD"],
             "carry_R_pp": round(s1_dev[i]["R"] - base5[y]["R"], 3)}
            for i, y in enumerate(DEV_YEARS)],
        "S1_dev4": dev4,
        "S1_chained_full_dev": chained_full_dev,
        "S2_status": s2_status,
        "winner": winner,
        "S1_recent_once": recent,
        "S1_five_posthoc": five,
        "S1_full_chained_posthoc": full_chained if winner == "S1" else None,
        "uta": uta,
        "friction_bound": ("Stored S1-S5 robustness runs (oc_d13robust / "
                           "v421_audit) are absent in this tree, so no new "
                           "friction run here. Published bound oc_carryfric: "
                           "both-coin D13BF+carry f0.50 keeps stretch only "
                           "at base (5.234/14.71) and S2-f0.50 (5.062/14.80)"
                           "; fails S1/S3/S4/S5. Max-coin lift is SMALLER "
                           "(18 vs 33 pairs), so it cannot pass where "
                           "both-coin fails."),
        "win_rate_note": ("BOT all-trade win rate UNCHANGED — equity-level "
                          "overlay adds zero trades; max-coin kept pairs are "
                          "18/18 net positive on allocated capital "
                          "per frozen oc_cashcarry, reported separately."),
    }
    (HERE / "results.json").write_text(json.dumps(out, indent=1))
    print(f"S1 dev4={dev4} chained_dev={chained_full_dev} winner={winner}")
    if recent:
        print(f"S1 recent once: {recent} five_posthoc={five} "
              f"full_chained={full_chained}")
    print("peak overlap:", max_overlap, "peak spot cost:", peak_spot_cost)


if __name__ == "__main__":
    sys.exit(main())
