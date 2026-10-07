"""oc_tsmom_official: TSMOM sleeve on the OFFICIAL hourly+eq_min metric.

Pre-registered in PLAN.md before any outcome was computed. Post-hoc informed,
REPORTING ONLY. Rebuilds the oc_tsmom sleeve exactly, marks it HOURLY
(worst-case: long at hour low, short at hour high), and combines it with the
4-phase hourly eq/eq_min of R2B1D13BF / R2B1D14BFX5 (v424) / R2B1D17BFG2 (v421)
under reset_metric.year_reset conventions (overlay: sleeve sub-account = w of
capital, reset at each anchor; conservative DD from the combined eq_min).

Usage: .venv/Scripts/python.exe research/tournament/oc_tsmom_official/run_official.py
Reads: hourly_ext.parquet (t < 2026-09-24 UTC), v424/v424_runs.pkl,
  v421/v421_runs.pkl, v424/v421_result.json (official reference),
  oc_tsmom/results.json (sleeve cross-check). Imports (not copies)
  v388_bot_stop_distance.hourly/mix and reset_metric.year_reset.
Writes: research/tournament/oc_tsmom_official/results.json
One process, no 1m data, RAM < 1 GB (two hourly series + small grids).
"""
from __future__ import annotations

import importlib.util
import json
import pickle
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
RD = ROOT / "research/parallel/rounds/parallel-20260906-r2"
HOURLY = ROOT / "research/tournament/ext/hourly_ext.parquet"
TSMOM_RES = ROOT / "research/tournament/oc_tsmom/results.json"

COINS = ["BTCUSDT", "ETHUSDT"]
ANCHORS = ["2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24"]
CAP = pd.Timestamp("2026-09-24 00:00", tz="UTC")
VOL_TARGET = 0.10
POS_CAP = 1.0
TAKER = 0.00055
FUND_PER_DAY = 0.0003  # 0.0001 x 3 settlements on longs; shorts zero
ANN = 365.0
G0 = pd.Timestamp("2021-09-24 04:00", tz="UTC")

# (label, version dir, pkl name, row) — pkl dir == version dir per assignment
SPECS = [
    ("R2B1D13BF", "v424", "v424_runs.pkl", "R2B1D13BF"),
    ("R2B1D14BFX5", "v424", "v424_runs.pkl", "R2B1D14BFX5"),
    ("R2B1D17BFG2", "v421", "v421_runs.pkl", "R2B1D17BFG2"),
]
WEIGHTS = [0.10, 0.25]


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---- sleeve code copied EXACTLY from oc_tsmom/run_tsmom.py ----
def build_daily(hourly: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    days = pd.date_range("2020-08-01", "2026-09-23", freq="D", tz="UTC")
    opens = pd.DataFrame(index=days, columns=COINS, dtype=float)
    closes = pd.DataFrame(index=days, columns=COINS, dtype=float)
    for sym in COINS:
        d = hourly[hourly["sym"] == sym].set_index("t").sort_index()
        o = d["open"]
        c = d["close"]
        opens[sym] = [o.get(x, np.nan) for x in days]
        closes[sym] = [c.get(x + pd.Timedelta(hours=23), np.nan) for x in days]
    return opens, closes


def compute_positions(closes: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    signal = pd.DataFrame(0, index=closes.index, columns=closes.columns, dtype=int)
    vol = pd.DataFrame(np.nan, index=closes.index, columns=closes.columns)
    pos = pd.DataFrame(0.0, index=closes.index, columns=closes.columns)
    logc = np.log(closes.astype(float))
    ret30 = closes.astype(float) / closes.astype(float).shift(30) - 1.0
    lr = logc.diff()
    for sym in closes.columns:
        r30 = ret30[sym]
        ok_ret = closes[sym].rolling(31).count() == 31
        s = pd.Series(0, index=closes.index, dtype=int)
        s[r30 > 0] = 1
        s[r30 < 0] = -1
        s[~ok_ret] = 0
        signal[sym] = s
        v = lr[sym].rolling(30).std(ddof=1) * np.sqrt(ANN)
        ok_vol = lr[sym].rolling(30).count() == 30
        v[~ok_vol] = np.nan
        v[~(v > 0)] = np.nan
        vol[sym] = v
        raw = VOL_TARGET / v
        p = s.astype(float) * raw.clip(upper=POS_CAP)
        p[v.isna() | (s == 0)] = 0.0
        pos[sym] = p.fillna(0.0)
    return signal, vol, pos


def sleeve_daily(opens: pd.DataFrame, pos: pd.DataFrame, days: list[pd.Timestamp]) -> pd.DataFrame:
    out = []
    prev = pd.Series(0.0, index=COINS)
    for e in days:
        e_next = e + pd.Timedelta(days=1)
        p = pos.loc[e - pd.Timedelta(days=1)] if (e - pd.Timedelta(days=1)) in pos.index else pd.Series(0.0, index=COINS)
        p = p.fillna(0.0)
        gross = 0.0
        for sym in COINS:
            try:
                o0 = opens.loc[e, sym]
                o1 = opens.loc[e_next, sym]
            except KeyError:
                continue
            if pd.isna(o0) or pd.isna(o1) or o0 == 0:
                continue
            gross += float(p[sym]) * (float(o1) / float(o0) - 1.0)
        cost = TAKER * float((p - prev).abs().sum())
        fund = FUND_PER_DAY * float(p.clip(lower=0).sum())
        out.append((e, gross, cost, fund, gross - cost - fund))
        prev = p
    df = pd.DataFrame(out, columns=["day", "gross", "cost", "fund", "r_s"]).set_index("day")
    return df


# ---- hourly marking (PLAN.md §NEW; day-boundary eq == daily sleeve) ----
def build_sleeve_hourly(hourly: pd.DataFrame, opens: pd.DataFrame, pos: pd.DataFrame,
                         year_days: dict[int, list[pd.Timestamp]],
                         sdf_by_year: dict[int, pd.DataFrame]) -> tuple[pd.Series, pd.Series, dict]:
    """Continuous hourly sleeve eq / eq_min on the v388 grid.

    Day-open levels S_day are stitched from the yearly-convention daily r_s
    (prev = 0 at each anchor, exactly as oc_tsmom), so day-boundary eq
    reproduces the daily sleeve exactly. Intraday: eq via hourly closes,
    eq_min worst-case (long -> low, short -> high); at exact 00:00 marks eq
    uses O(next day) (execution price), eq_min keeps the closing hour's worst.
    Returns (S_eq, S_min, S_day).
    """
    v388 = _load("v388_grid", RD / "v388" / "v388_bot_stop_distance.py")
    g1 = v388.Y1 + pd.Timedelta(hours=12)
    grid = pd.date_range(G0, g1, freq="1h")
    px = {}
    for sym in COINS:
        d = hourly[hourly["sym"] == sym].set_index("t").sort_index()
        px[sym] = {k: d[k] for k in ("open", "high", "low", "close")}
    # stitched day-open levels (continuous in level, yearly-convention returns)
    S_day: dict = {}
    rs_map = {}
    for y in range(5):
        sdf = sdf_by_year[y]
        for e, r in zip(sdf.index, sdf["r_s"].to_numpy(float)):
            rs_map[e] = float(r)

    def fallback_r(d: pd.Timestamp) -> float:
        # continuous-convention daily return for days covered by no anchor
        # year (leap-year gap, e.g. 2024-09-23): prev = actual previous pos.
        p = pos.loc[d - pd.Timedelta(days=1)].fillna(0.0) if (d - pd.Timedelta(days=1)) in pos.index else pd.Series(0.0, index=COINS)
        pp = pos.loc[d - pd.Timedelta(days=2)].fillna(0.0) if (d - pd.Timedelta(days=2)) in pos.index else pd.Series(0.0, index=COINS)
        gross = 0.0
        for sym in COINS:
            try:
                o0 = opens.loc[d, sym]
                o1 = opens.loc[d + pd.Timedelta(days=1), sym]
            except KeyError:
                continue
            if pd.isna(o0) or pd.isna(o1) or o0 == 0:
                continue
            gross += float(p[sym]) * (float(o1) / float(o0) - 1.0)
        return float(gross - TAKER * float((p - pp).abs().sum())
                     - FUND_PER_DAY * float(p.clip(lower=0).sum()))

    first_day = min(rs_map)
    last_ebar = (v388.Y1 + pd.Timedelta(hours=12)).floor("D")  # grid-end day needs a base level
    all_days = pd.date_range(first_day, last_ebar, freq="D", tz="UTC").tolist()
    S_day[all_days[0]] = 1.0
    for e in all_days[1:]:
        prev_day = e - pd.Timedelta(days=1)
        r = rs_map.get(prev_day, fallback_r(prev_day))
        S_day[e] = S_day[prev_day] * (1.0 + r)
    anchor_set = {pd.Timestamp(a, tz="UTC") for a in ANCHORS}
    o_day = {s: opens[s] for s in COINS}
    eq = np.empty(len(grid))
    mn = np.empty(len(grid))
    for i, h in enumerate(grid):
        bar = h - pd.Timedelta(hours=1)
        ebar = bar.floor("D")
        p = pos.loc[ebar - pd.Timedelta(days=1)].fillna(0.0) if (ebar - pd.Timedelta(days=1)) in pos.index else pd.Series(0.0, index=COINS)
        if ebar in anchor_set:
            pp = pd.Series(0.0, index=COINS)  # yearly convention: entry from 0
        else:
            pp = pos.loc[ebar - pd.Timedelta(days=2)].fillna(0.0) if (ebar - pd.Timedelta(days=2)) in pos.index else pd.Series(0.0, index=COINS)
        cost = TAKER * float((pd.Series(p).astype(float) - pp.astype(float)).abs().sum())
        fund = FUND_PER_DAY * float(pd.Series(p).astype(float).clip(lower=0).sum())
        base = S_day.get(ebar, np.nan)
        is_midnight = (h.hour == 0 and h.minute == 0)
        g = 0.0
        w = 0.0
        for sym in COINS:
            ps = float(p[sym])
            if ps == 0.0:
                continue
            try:
                o0 = float(o_day[sym].loc[ebar])
            except KeyError:
                continue
            if not np.isfinite(o0) or o0 == 0:
                continue
            if is_midnight:
                # execution price at the day boundary (exact daily sleeve)
                try:
                    o1 = float(o_day[sym].loc[ebar + pd.Timedelta(days=1)])
                except KeyError:
                    o1 = np.nan
                if np.isfinite(o1):
                    g += ps * (o1 / o0 - 1.0)
            else:
                c = px[sym]["close"].get(bar, np.nan)
                if np.isfinite(c):
                    g += ps * (float(c) / o0 - 1.0)
            # worst-case mark from the same hour bar in both cases
            if ps > 0:
                v = px[sym]["low"].get(bar, np.nan)
            else:
                v = px[sym]["high"].get(bar, np.nan)
            if np.isfinite(v):
                w += ps * (float(v) / o0 - 1.0)
        eq[i] = base * (1.0 - cost - fund + g)
        mn[i] = base * (1.0 - cost - fund + w)
    S_eq = pd.Series(eq, index=grid)
    S_min = pd.Series(mn, index=grid)
    return S_eq, S_min, S_day


def max_dd_from(es: np.ndarray, ms: np.ndarray) -> float:
    """year_reset DD: peak from eq path only, trough from eq_min (fraction)."""
    pk = np.maximum.accumulate(np.asarray(es, float))
    return float(np.max(1.0 - np.asarray(ms, float) / pk))


def monthly_of_total(total: float) -> float:
    return float((1.0 + total) ** (1.0 / 12) - 1) * 100


def main() -> None:
    hourly = pd.read_parquet(HOURLY)
    hourly["t"] = pd.to_datetime(hourly["t"], utc=True)
    assert bool((hourly["t"] < CAP).all()), "hourly data reaches beyond the cap"
    hourly = hourly[hourly["sym"].isin(COINS)].copy()
    assert set(hourly["sym"].unique()) == set(COINS)

    v388 = _load("v388_off", RD / "v388" / "v388_bot_stop_distance.py")
    rm = _load("reset_off", ROOT / "research/diagnostics/r2_decompose5/reset_metric.py")
    g1 = v388.Y1 + pd.Timedelta(hours=12)

    opens, closes = build_daily(hourly)
    _signal, _vol, pos = compute_positions(closes)

    def year_days(a0: pd.Timestamp) -> list[pd.Timestamp]:
        cands = [a0 + pd.Timedelta(days=i) for i in range(365)]
        last_o = opens.index[-1]
        return [x for x in cands if x <= last_o - pd.Timedelta(days=1)]

    yd = {y: year_days(pd.Timestamp(a, tz="UTC")) for y, a in enumerate(ANCHORS)}
    sdf_by_year = {y: sleeve_daily(opens, pos, yd[y]) for y in range(5)}

    S_eq, S_min, S_day = build_sleeve_hourly(hourly, opens, pos, yd, sdf_by_year)

    tsmom = json.loads(TSMOM_RES.read_text())
    tsmom_by_anchor = {y["anchor"]: y for y in tsmom["years"]}
    sleeve_gap = []
    for y, a in enumerate(ANCHORS):
        ref = tsmom_by_anchor[a]
        ref_days = [pd.Timestamp(d, tz="UTC") for d in ref["days"]]
        rs = sdf_by_year[y].loc[ref_days, "r_s"].to_numpy(float)
        arr = np.array(ref["r_sleeve"], float)
        sleeve_gap.append(float(np.max(np.abs(rs - arr))))
    # day-boundary exactness: grid midnight eq vs stitched day levels
    bnd_gap = []
    for e, lvl in S_day.items():
        if e in S_eq.index and e > S_eq.index[0]:
            bnd_gap.append(abs(float(S_eq.loc[e]) - float(lvl)))
    # intraday conservatism: eq_min <= eq + tiny tolerance
    viol = float(np.max(np.asarray(S_min) - np.asarray(S_eq)))

    # ---- base proof: year_reset must reproduce official numbers ----
    base_proof = []
    runs_by_label = {}
    for label, vdir, pkl, row in SPECS:
        runs = pickle.loads((RD / vdir / pkl).read_bytes())
        assert set(runs) == {0, 1, 2, 3}, (label, sorted(runs))
        for s in runs:
            assert set(runs[s][row]) == {"t", "eq", "eq_min"}, (label, s)
        runs_by_label[label] = runs
        official = json.loads((RD / vdir / f"{vdir}_result.json").read_text())["rows"][row]
        recomp = [rm.year_reset(runs, row, y) for y in range(5)]
        e, mn = v388.mix(runs, row, g1)
        seg = e.index > pd.Timestamp("2021-09-24", tz="UTC")
        fp = round(100 * float(np.max(1 - mn[seg].to_numpy() / np.maximum.accumulate(e[seg].to_numpy()))), 2)
        base_proof.append({
            "row": label, "src": f"{vdir}/{row}",
            "official": {"R": official["R"], "W": official["W"], "DD": official["DD"],
                         "full_path_dd": official["full_path_dd"], "years": official["years"]},
            "recomputed": [{"R": r["R"], "DD": r["DD"]} for r in recomp],
            "recomputed_full_path_dd": fp,
            "match_R": all(r["R"] == o for r, o in zip(recomp, [x[0] for x in official["years"]])),
            "match_DD": all(r["DD"] == o for r, o in zip(recomp, [x[1] for x in official["years"]])),
            "match_full": fp == official["full_path_dd"],
        })

    # ---- official-metric combinations ----
    combos = []
    for label, vdir, pkl, row in SPECS:
        runs = runs_by_label[label]
        # continuous base for the full-path leg
        e_full, mn_full = v388.mix(runs, row, g1)
        s0 = float(S_eq.iloc[0])
        sleeve_cont = S_eq / s0
        sleeve_low_cont = S_min / s0
        for w in WEIGHTS:
            years = []
            for y, a in enumerate(ANCHORS):
                a0 = pd.Timestamp(a, tz="UTC")
                parts_e, parts_m = [], []
                for s in range(4):
                    e1, m1 = v388.hourly(runs[s][row], G0, g1)
                    b = float(e1[e1.index <= a0].iloc[-1]) if (e1.index <= a0).any() else 1.0
                    segm = (e1.index > a0) & (e1.index <= a0 + pd.Timedelta(days=365))
                    parts_e.append(e1[segm] / b)
                    parts_m.append(m1[segm] / b)
                base_es = sum(parts_e) / 4
                base_ms = sum(parts_m) / 4
                bS = float(S_day[a0])
                segS = (S_eq.index > a0) & (S_eq.index <= a0 + pd.Timedelta(days=365))
                F = S_eq[segS] / bS
                FM = S_min[segS] / bS
                # shared hourly index (identical grids by construction)
                idx = base_es.index.intersection(F.index)
                assert len(idx) >= 8600, (label, a, len(idx))
                be = base_es.loc[idx].to_numpy(float)
                bm = base_ms.loc[idx].to_numpy(float)
                fe = F.loc[idx].to_numpy(float)
                fm = FM.loc[idx].to_numpy(float)
                ce = be + w * (fe - 1.0)
                cm = bm + w * (fm - 1.0)
                tot_b = float(be[-1] - 1)
                tot_c = float(ce[-1] - 1)
                m_b = monthly_of_total(tot_b)
                m_c = monthly_of_total(tot_c)
                dd_b = max_dd_from(be, bm) * 100
                dd_c = max_dd_from(ce, cm) * 100
                years.append({
                    "anchor": a,
                    "n_hours": len(idx),
                    "base_monthly_pct": round(m_b, 3),
                    "base_maxDD_pct": round(dd_b, 2),
                    "base_total_pct": round(tot_b * 100, 3),
                    "monthly_pct": round(m_c, 3),
                    "maxDD_pct": round(dd_c, 2),
                    "total_pct": round(tot_c * 100, 3),
                    "excess_monthly_pp": round(m_c - m_b, 3),
                    "dd_delta_pp": round(dd_c - dd_b, 3),
                })
            R5 = round(float(np.prod([1 + y["total_pct"] / 100 for y in years]) ** (1 / 60) - 1) * 100, 3)
            W = round(min(y["monthly_pct"] for y in years), 3)
            DD = round(max(y["maxDD_pct"] for y in years), 2)
            # full-path (mix-style, no reset)
            segf = e_full.index > pd.Timestamp("2021-09-24", tz="UTC")
            ef = e_full[segf].to_numpy(float)
            mf = mn_full[segf].to_numpy(float)
            sc = sleeve_cont[e_full.index[segf]].to_numpy(float)
            sl = sleeve_low_cont[e_full.index[segf]].to_numpy(float)
            ce_f = ef + w * (sc - 1.0)
            cm_f = mf + w * (sl - 1.0)
            fp_dd = round(float(np.max(1 - cm_f / np.maximum.accumulate(ce_f))) * 100, 2)
            fp_tot = round(float(ce_f[-1] - 1) * 100, 3)
            stretch = bool(R5 >= 5.0 and DD < 15.0)
            combos.append({
                "row": label, "src": f"{vdir}/{row}", "w": w,
                "R_5y": R5, "W": W, "DD_maxyearly": DD,
                "full_path_dd": fp_dd, "full_path_total_pct": fp_tot,
                "stretch": stretch,
                "years": years,
            })

    # ---- descriptive header-default checks on the excess (no gate) ----
    desc = {}
    for c in combos:
        ex = np.array([y["excess_monthly_pp"] for y in c["years"]])
        sgn = np.sign(ex)
        full = float(np.mean(ex))
        loyo = []
        for h in range(5):
            pool = float(np.mean([ex[k] for k in range(5) if k != h]))
            loyo.append(bool(np.sign(pool) == np.sign(full)) if full != 0 else False)
        key = f"{c['row']}@{c['w']}"
        desc[key] = {
            "same_sign_years": f"{int(np.max([(sgn == 1).sum(), (sgn == -1).sum()]))}/5",
            "all_positive": bool((ex > 0).all()),
            "loyo_sign_hold": f"{sum(loyo)}/5",
        }

    # compounding residuals: totals vs monthly
    res = 0.0
    for c in combos:
        for y in c["years"]:
            for tot, m in ((y["total_pct"], y["monthly_pct"]), (y["base_total_pct"], y["base_monthly_pct"])):
                m2 = (1 + tot / 100) ** (1 / 12) - 1
                res = max(res, abs(m2 * 100 - m))

    out = {
        "meta": {
            "sleeve": "oc_tsmom exact reuse (BTC+ETH 30d TSMOM, 10% vol target, cap 1.0, next-open, taker 0.00055, longs fund 0.0003/d) + NEW hourly worst-case marking (long->hour low, short->hour high)",
            "base_convention": "official metric: v388.hourly 1h grid + eq_min lows, reset_metric.year_reset per year (sleeve sub-account = w of capital, overlay, reset at each anchor; conservative DD from combined eq_min); full-path DD v388.mix-style continuous",
            "official_reference": "v424_result.json / v421_result.json rows (R, W, DD, full_path_dd, years)",
            "anchors": ANCHORS,
            "weights": WEIGHTS,
            "data_cap": "2026-09-24T00:00:00Z",
            "g1": "2026-09-23 12:00:00+00:00",
            "reporting_only": True,
            "post_hoc_informed": True,
        },
        "base_proof": base_proof,
        "checks": {
            "hourly_cap_ok": True,
            "max_sleeve_abs_gap_vs_octsmom": round(float(max(sleeve_gap)), 10),
            "max_day_boundary_gap": round(float(max(bnd_gap)) if bnd_gap else 0.0, 10),
            "max_eqmin_above_eq": round(viol, 10),
            "max_monthly_total_residual_pp": round(float(res), 6),
        },
        "combos": combos,
        "descriptive_default_rule": desc,
    }
    (HERE / "results.json").write_text(json.dumps(out, indent=1))
    print(f"sleeve_gap={max(sleeve_gap):.2e} bnd_gap={max(bnd_gap) if bnd_gap else 0:.2e} eqmin_viol={viol:.2e}", flush=True)
    for b in base_proof:
        print(f"BASE {b['row']}: official R={b['official']['R']} DD={b['official']['DD']} "
              f"match_R={b['match_R']} match_DD={b['match_DD']} match_full={b['match_full']}", flush=True)
    for c in combos:
        print(f"{c['row']} w={c['w']}: R5={c['R_5y']} W={c['W']} DD={c['DD_maxyearly']} "
              f"fullDD={c['full_path_dd']} stretch={c['stretch']}", flush=True)


if __name__ == "__main__":
    main()
