"""oc_tsmomcombo: overlay oc_tsmom 30d-TSMOM sleeve (exact reuse) on cached frontier rows.

Pre-registered in PLAN.md before any outcome was computed. Post-hoc informed
(sleeve + rows chosen after oc_tsmom/oc_frontier), REPORTING ONLY.
Usage: .venv/Scripts/python.exe research/tournament/oc_tsmomcombo/run_combo.py
Reads: hourly_ext.parquet (t < 2026-09-24 UTC), v411/v421/v422/v424 *_runs.pkl,
  vNNN_result.json (official reference), oc_tsmom/results.json (cross-check),
  oc_frontier/results.json (dominance set).
Writes: research/tournament/oc_tsmomcombo/results.json
One process, no 1m data, RAM < 1 GB.
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
FRONTIER_RES = ROOT / "research/tournament/oc_frontier/results.json"

COINS = ["BTCUSDT", "ETHUSDT"]
ANCHORS = ["2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24"]
CAP = pd.Timestamp("2026-09-24 00:00", tz="UTC")
VOL_TARGET = 0.10
POS_CAP = 1.0
TAKER = 0.00055
FUND_PER_DAY = 0.0003
ANN = 365.0
G0 = pd.Timestamp("2021-09-24 04:00", tz="UTC")

# (label, version dir, pkl name, row) — pkl dir == version dir per assignment
SPECS = [
    ("R2B1D13BF", "v424", "v424_runs.pkl", "R2B1D13BF"),
    ("R2B1D14BFX5", "v424", "v424_runs.pkl", "R2B1D14BFX5"),
    ("R2B1D17BFG2", "v421", "v421_runs.pkl", "R2B1D17BFG2"),
    ("R2B1D17BF", "v411", "v411_runs.pkl", "R2B1D17BF"),
    ("G2K20", "v422", "v422_runs.pkl", "G2K20"),
]
WEIGHTS = [0.10, 0.25]


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---- sleeve code copied EXACTLY from oc_tsmom/run_tsmom.py (constants above match) ----
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


# ---- base + stats helpers (same convention as oc_tsmom Variant B) ----
def max_dd(equity: np.ndarray) -> float:
    eq = np.asarray(equity, float)
    path = np.concatenate([[1.0], eq])
    pk = np.maximum.accumulate(path)
    return float(np.max(1.0 - path / pk))


def equity_from(r: np.ndarray) -> np.ndarray:
    return np.cumprod(1.0 + np.asarray(r, float))


def monthly_of(r: np.ndarray) -> float:
    eq = equity_from(np.asarray(r, float))
    return float(eq[-1] ** (1 / 12) - 1) * 100


def reset_F_for_row(runs: dict, row: str, v388, g1: pd.Timestamp) -> dict[int, pd.Series]:
    out = {}
    for y, a in enumerate(ANCHORS):
        a0 = pd.Timestamp(a, tz="UTC")
        parts = []
        for s in range(4):
            assert row in runs[s], (row, s, sorted(runs[s]))
            e1, _m1 = v388.hourly(runs[s][row], G0, g1)
            b = float(e1[e1.index <= a0].iloc[-1]) if (e1.index <= a0).any() else 1.0
            parts.append(e1 / b)
        out[y] = sum(parts) / 4
    return out


def reset_daily_returns(F: pd.Series, days: list[pd.Timestamp]) -> pd.Series:
    out = {}
    for day in days:
        b = day + pd.Timedelta(days=1)
        if day not in F.index or b not in F.index:
            continue
        out[day] = float(F.loc[b] / F.loc[day] - 1.0)
    return pd.Series(out).sort_index()


def main() -> None:
    hourly = pd.read_parquet(HOURLY)
    hourly["t"] = pd.to_datetime(hourly["t"], utc=True)
    assert bool((hourly["t"] < CAP).all()), "hourly data reaches beyond the cap"
    hourly = hourly[hourly["sym"].isin(COINS)].copy()

    opens, closes = build_daily(hourly)
    _signal, _vol, pos = compute_positions(closes)
    v388 = _load("v388_combo", RD / "v388" / "v388_bot_stop_distance.py")
    g1 = v388.Y1 + pd.Timedelta(hours=12)

    tsmom = json.loads(TSMOM_RES.read_text())
    tsmom_by_anchor = {y["anchor"]: y for y in tsmom["years"]}
    frontier = json.loads(FRONTIER_RES.read_text())
    official = {d["version"] + "/" + d["row"]: d for d in frontier["rows"]}
    frontier_yearly_set = set(frontier["frontier_yearly"])
    frontier_full_set = set(frontier["frontier_fullpath"])

    def year_days(a0: pd.Timestamp) -> list[pd.Timestamp]:
        cands = [a0 + pd.Timedelta(days=i) for i in range(365)]
        last_o = opens.index[-1]
        return [x for x in cands if x <= last_o - pd.Timedelta(days=1)]

    combos = []
    base_grid = []
    off_by_label: dict[str, dict] = {}
    # cache sleeve rs per year on the maximal day set (per-year common days are
    # row-independent since all F share the same hourly grid; recompute per row
    # intersection anyway for exactness)
    for label, vdir, pkl, row in SPECS:
        runs = pickle.loads((RD / vdir / pkl).read_bytes())
        assert set(runs) == {0, 1, 2, 3}, (label, sorted(runs))
        F = reset_F_for_row(runs, row, v388, g1)
        res_json = json.loads((RD / vdir / f"{vdir}_result.json").read_text())
        off = res_json["rows"][row]
        off_by_label[label] = {"src": f"{vdir}/{row}", "off": off}

        per_year = []  # per anchor year: days, rs, rb
        for k, a in enumerate(ANCHORS):
            a0 = pd.Timestamp(a, tz="UTC")
            sc = year_days(a0)
            sdf = sleeve_daily(opens, pos, sc)
            rb = reset_daily_returns(F[k], sc)
            common = sorted(set(sdf.index) & set(rb.index))
            assert len(common) >= 360, (label, a, len(common))
            sdf = sdf.loc[common]
            rs = sdf["r_s"].to_numpy(float)
            rbv = rb.loc[common].to_numpy(float)
            per_year.append({"days": common, "rs": rs, "rb": rbv})

        # base daily-grid stats per year (w=0)
        base_years = []
        for k, py in enumerate(per_year):
            eq_b = equity_from(py["rb"])
            base_years.append({
                "anchor": ANCHORS[k],
                "n_days": len(py["days"]),
                "monthly_pct": round(monthly_of(py["rb"]), 3),
                "maxDD_pct": round(max_dd(eq_b) * 100, 2),
                "total_pct": round(float(eq_b[-1] - 1) * 100, 3),
            })
        base_R = round(float(np.prod([1 + y["total_pct"] / 100 for y in base_years]) ** (1 / 60) - 1) * 100, 3)
        base_W = round(min(y["monthly_pct"] for y in base_years), 3)
        base_DD = round(max(y["maxDD_pct"] for y in base_years), 2)
        base_grid.append({"row": label, "src": f"{vdir}/{row}",
                          "years": base_years, "R_5y": base_R, "W": base_W,
                          "DD_maxyearly": base_DD})

        for w in WEIGHTS:
            years = []
            for k, py in enumerate(per_year):
                rc = py["rb"] + w * py["rs"]
                eq_c = equity_from(rc)
                eq_b = equity_from(py["rb"])
                m_c = monthly_of(rc)
                m_b = monthly_of(py["rb"])
                dd_c = max_dd(eq_c) * 100
                dd_b = max_dd(eq_b) * 100
                years.append({
                    "anchor": ANCHORS[k],
                    "n_days": len(py["days"]),
                    "monthly_pct": round(float(m_c), 3),
                    "maxDD_pct": round(float(dd_c), 2),
                    "total_pct": round(float(eq_c[-1] - 1) * 100, 3),
                    "base_monthly_pct": round(float(m_b), 3),
                    "base_maxDD_pct": round(float(dd_b), 2),
                    "excess_monthly_pp": round(float(m_c - m_b), 3),
                    "dd_delta_pp": round(float(dd_c - dd_b), 3),
                })
            R5 = round(float(np.prod([1 + y["total_pct"] / 100 for y in years]) ** (1 / 60) - 1) * 100, 3)
            W = round(min(y["monthly_pct"] for y in years), 3)
            DD = round(max(y["maxDD_pct"] for y in years), 2)
            # dominance vs official rows (R, dd_yearly), daily-grid vs official
            dominated = sorted([k for k, d in official.items()
                                if R5 >= d["R"] and DD <= d["dd_yearly"]
                                and (R5 > d["R"] or DD < d["dd_yearly"])])
            dom_frontier_y = sorted([k for k in dominated if k in frontier_yearly_set])
            dom_frontier_f = sorted([k for k in dominated if k in frontier_full_set])
            stretch = bool(R5 >= 5.0 and DD < 15.0)
            combos.append({
                "row": label, "src": f"{vdir}/{row}", "w": w,
                "R_5y": R5, "W": W, "DD_maxyearly": DD,
                "stretch": stretch,
                "dominated_official": dominated,
                "dominates_any_official": bool(dominated),
                "dominates_frontier_yearly": dom_frontier_y,
                "dominates_frontier_fullpath": dom_frontier_f,
                "dominates_any_frontier": bool(dom_frontier_y or dom_frontier_f),
                "years": years,
            })

    # ---- checks ----
    residuals = []
    for c in combos:
        for y in c["years"]:
            pass  # per-year totals recompound check done on stored daily below
    # sleeve exactness vs oc_tsmom r_sleeve (R2B1D17BF row shares the same days)
    sleeve_gap = []
    for k, a in enumerate(ANCHORS):
        ref = tsmom_by_anchor[a]
        # recompute rs on ref days to compare exactly
        a0 = pd.Timestamp(a, tz="UTC")
        sc = year_days(a0)
        sdf = sleeve_daily(opens, pos, sc)
        # oc_tsmom common-day subset: ref["days"]
        ref_days = [pd.Timestamp(d, tz="UTC") for d in ref["days"]]
        rs = sdf.loc[ref_days, "r_s"].to_numpy(float)
        arr = np.array(ref["r_sleeve"], float)
        sleeve_gap.append(float(np.max(np.abs(rs - arr))))
    # R2B1D17BF@0.25 vs oc_tsmom combined
    combo_ref = next(c for c in combos if c["row"] == "R2B1D17BF" and c["w"] == 0.25)
    combo_gap_m = max(abs(y["monthly_pct"] - tsmom_by_anchor[y["anchor"]]["combined"]["monthly_pct"]) for y in combo_ref["years"])
    combo_gap_dd = max(abs(y["maxDD_pct"] - tsmom_by_anchor[y["anchor"]]["combined"]["maxDD_pct"]) for y in combo_ref["years"])
    # compounding residual: totals vs monthly (monthly = (1+tot)^(1/12)-1)
    res = 0.0
    for c in combos:
        for y in c["years"]:
            m2 = (1 + y["total_pct"] / 100) ** (1 / 12) - 1
            res = max(res, abs(m2 * 100 - y["monthly_pct"]))
    # base w=0 equivalence: base_grid totals vs combo would-be base (stored base_monthly)
    out = {
        "meta": {
            "sleeve": "oc_tsmom exact reuse (BTC+ETH 30d TSMOM, 10% vol target, cap 1.0, next-open, taker 0.00055, longs fund 0.0003/d)",
            "base_convention": "daily-grid reset (per-shift F(a0)=1.0, r_b from F at 00:00; DD = daily-00:00 max peak-to-trough, no eq_min/1m marking — same as oc_tsmom Variant B)",
            "official_reference": "vNNN_result.json rows[row] (hourly grid + eq_min lows) + oc_frontier/results.json; reported side-by-side only",
            "anchors": ANCHORS,
            "weights": WEIGHTS,
            "data_cap": "2026-09-24T00:00:00Z",
            "g1": "2026-09-23 12:00:00+00:00",
            "reporting_only": True,
            "post_hoc_informed": True,
        },
        "official_rows": {
            label: {"src": v["src"],
                    "R": float(v["off"]["R"]), "W": float(v["off"]["W"]),
                    "DD_yearly": float(v["off"]["DD"]),
                    "full_path_dd": (None if v["off"].get("full_path_dd") is None
                                     else float(v["off"]["full_path_dd"])),
                    "years": [[float(a), float(b)] for a, b in v["off"]["years"]]}
            for label, v in off_by_label.items()
        },
        "base_daily_grid": base_grid,
        "combos": combos,
        "frontier_lists": {"yearly": sorted(frontier_yearly_set),
                           "fullpath": sorted(frontier_full_set)},
        "checks": {
            "hourly_cap_ok": True,
            "max_sleeve_abs_gap_vs_octsmom": round(float(max(sleeve_gap)), 10),
            "combo_vs_octsmom_monthly_gap": round(float(combo_gap_m), 6),
            "combo_vs_octsmom_dd_gap": round(float(combo_gap_dd), 6),
            "max_monthly_total_residual_pp": round(float(res), 6),
        },
    }
    (HERE / "results.json").write_text(json.dumps(out, indent=1))
    print(f"combos={len(combos)} sleeve_gap={max(sleeve_gap):.2e} combo_m_gap={combo_gap_m} combo_dd_gap={combo_gap_dd}", flush=True)
    for c in combos:
        print(f"{c['row']} w={c['w']}: R5={c['R_5y']} W={c['W']} DD={c['DD_maxyearly']} "
              f"dom_official={len(c['dominated_official'])} dom_frontier={c['dominates_any_frontier']} stretch={c['stretch']}", flush=True)


if __name__ == "__main__":
    main()
