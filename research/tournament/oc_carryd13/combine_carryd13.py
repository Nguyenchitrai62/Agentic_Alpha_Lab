"""oc_carryd13: overlay the frozen oc_cashcarry sleeve on low-DD stored rows.

Assignment (docs/opencode/OPENCODE_W_oc_carryd13.md): combine the stored
4-phase hourly equity of low-DD rows (v424 R2B1D13BF at 4.97 %/mo, max yearly
DD 14.98; plus any other v424/v425 row with max yearly DD < 15) with the
oc_cashcarry sleeve at f in {0.25, 0.5}.

Carry rule is reused UNCHANGED from research/tournament/oc_cashcarry
(pre-registered PLAN.md + analyze_cashcarry.py + results.json): one entry per
quarterly contract (next-quarter when front has <= 7 d left), ENTER iff
annualised basis >= 4 %/yr, equal-notional spot long + quarterly short, hold to
delivery, settlement = spot 4h close of the delivery bar, fees spot 0.1%/side
+ futures 0.055% entry / 0.02% delivery. This script reads the 33 entered
trades verbatim from oc_cashcarry/results.json (asserted equal) and only adds
an hourly mark for combination purposes.

Combination (equity-level, same reset metric):
- Base per anchor year = research/diagnostics/r2_decompose5/reset_metric.py
  year_reset exactly (4-phase mix, each phase reset to 1.0 at the anchor,
  v388.hourly grid G0=2021-09-24 04:00 .. g1=Y1+12h).
- Carry marked HOURLY: mtm_alloc(t) = (S(t)/S_entry-1) + ((F_entry-F(t))/F_entry)
  - 0.00155 (entry fees), with S(t)/F(t) = last CLOSED hourly bar strictly
  before t (causal); 0 before the entry-bar close; locked to the frozen
  ret_alloc (net of the full 0.00275 fee drag) from the settlement-bar close.
- Carry sized at f of year-start equity (yearly rebalance; labelled sizing
  assumption). Per-year carry curve is rebased to 0 at the anchor, so only
  intra-year accrual counts (spanning trades contribute from their anchor
  mark). Combined es/ms = base es/ms + carry curve (carry low = hourly-close
  mark, labelled: no intra-hour low, so combined DD is a close-marked lower
  bound on the carry leg).
- 5y mean / worst / max-DD / losing exactly as v424 (geometric mean of the
  yearly monthly factors). Full-path DD = chained-reset path (yearly combined
  segments chained multiplicatively; labelled). Base chained path + official
  v424 full-path DD shown for reference.
- These rows were already scored on all five years: this combination is
  POST-HOC, REPORTING ONLY. The carry rule itself was fixed before any
  combination (oc_cashcarry PLAN pre-registered).

Gap note: research/tournament/oc_carrycombo/ does not exist in this repo, so
"exactly as oc_carrycombo does" cannot be literal; the hourly-mark +
equity-level + reset-metric method above is defined here instead (same three
properties the assignment names).

Usage: .venv/Scripts/python.exe research/tournament/oc_carryd13/combine_carryd13.py
Reads: v424/v425/v421 *_result.json + v424_runs.pkl, oc_cashcarry/results.json,
  research/tournament/ext/hourly_ext.parquet (t < 2026-09-24, asserted),
  data/raw/qbasis_20261003/um_*_1h.parquet, one spot-4h file (delivery grid).
Writes: research/tournament/oc_carryd13/results.json
One process, 4h+1h data only (no 1m), RAM < 2 GB, no engine reruns.
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
CC = ROOT / "research/tournament/oc_cashcarry"
HOURLY = ROOT / "research/tournament/ext/hourly_ext.parquet"
QDIR = ROOT / "data/raw/qbasis_20261003"
SDIR = ROOT / "data/raw/spot_majors_20260925"

ANCHORS = [pd.Timestamp(f"{y}-09-24", tz="UTC") for y in (2021, 2022, 2023, 2024, 2025)]
YEAR_LEN = pd.Timedelta(days=365)
F_ROWS = [0.25, 0.5]
FEE_ENTRY_PAID = 0.001 + 0.00055  # in MtM while open (exit fees only in realized ret_alloc)
G0 = pd.Timestamp("2021-09-24 04:00", tz="UTC")
CAP = pd.Timestamp("2026-09-24 00:00", tz="UTC")


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def last_close_before(times_ns: np.ndarray, closes: np.ndarray, ts_ns: np.ndarray) -> np.ndarray:
    """Close of the last bar with bar_time strictly before each query time (causal)."""
    idx = np.searchsorted(times_ns, ts_ns, side="left") - 1
    out = np.full(len(ts_ns), np.nan)
    ok = idx >= 0
    out[ok] = closes[idx[ok]]
    return out


def main() -> None:
    v388 = _load("v388_for_carryd13", RD / "v388" / "v388_bot_stop_distance.py")
    rm = _load("reset_for_carryd13", ROOT / "research/diagnostics/r2_decompose5/reset_metric.py")
    g1 = v388.Y1 + pd.Timedelta(hours=12)
    grid = pd.date_range(G0, g1, freq="1h")
    grid_ns = grid.values.astype("datetime64[ns]").astype(np.int64)

    # ---- qualifying-row scan (v424 + v425 result jsons; v421 read for G2 reference) ----
    scanned: dict[str, dict] = {}
    for v in ("v424", "v425", "v421"):
        res = json.loads((RD / v / f"{v}_result.json").read_text())
        for row, m in res["rows"].items():
            scanned[f"{v}/{row}"] = {
                "R": float(m["R"]), "W": float(m["W"]), "DD": float(m["DD"]),
                "full_path_dd": float(m["full_path_dd"]), "losing": int(m["losing"]),
                "years": [[float(a), float(b)] for a, b in m["years"]],
            }
    qualifying = sorted([k for k, m in scanned.items()
                         if k.startswith(("v424/", "v425/")) and m["DD"] < 15.0])
    print("qualifying (max yearly DD < 15):", qualifying)

    # ---- frozen carry trades, reused unchanged ----
    cc = json.loads((CC / "results.json").read_text())
    assert cc["meta"]["threshold_ann_basis"] == 0.04
    assert len(cc["trades"]) == 33 and cc["n_skipped"] == 13 and cc["n_incomplete"] == 2
    assert cc["pooled"]["n_trades"] == 25

    # ---- hourly spot (causal last-closed-bar marks) ----
    h = pd.read_parquet(HOURLY, columns=["t", "close", "sym"])
    h["t"] = pd.to_datetime(h["t"], utc=True)
    assert bool((h["t"] < CAP).all()), "hourly data reaches beyond the cap"
    spot: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    for coin in ("BTC", "ETH"):
        d = h[h["sym"] == f"{coin}USDT"].sort_values("t")
        spot[coin] = (d["t"].values.astype("datetime64[ns]").astype(np.int64),
                      d["close"].to_numpy(dtype=float))

    # ---- quarterly hourly per traded contract ----
    qmap: dict[tuple[str, str], tuple[np.ndarray, np.ndarray]] = {}
    for t in cc["trades"]:
        key = (t["coin"], t["delivery"])
        if key in qmap:
            continue
        y, m, dd = t["delivery"].split("-")
        code = f"{y[2:]}{m}{dd}"
        (f,) = sorted(QDIR.glob(f"um_{t['coin']}USDT_{code}_1h.parquet"))
        q = pd.read_parquet(f, columns=["open_time", "close"])
        qo = pd.to_datetime(q["open_time"], utc=True).values.astype("datetime64[ns]").astype(np.int64)
        o = np.argsort(qo)
        qmap[key] = (qo[o], q["close"].to_numpy(dtype=float)[o])

    # ---- entry/settlement timestamps (spot-4h grid; shared BTC/ETH grid) ----
    s4 = pd.read_parquet(SDIR / "BTCUSDT_spot_4h.parquet",
                         columns=["open_time", "close_time"])
    s4o = pd.to_datetime(s4["open_time"], utc=True)
    s4c = pd.to_datetime(s4["close_time"], utc=True)
    trades = []
    for t in cc["trades"]:
        te = pd.Timestamp(t["entry_open"], tz="UTC")
        tc = te + pd.Timedelta(hours=4)
        assert (s4o == te).any(), t  # entry bar exists on the frozen 4h grid
        D = pd.Timestamp(t["delivery"] + " 08:00", tz="UTC")
        si = int(np.searchsorted(s4c.values.astype("datetime64[ns]").astype(np.int64),
                                 D.value, side="right"))
        assert si < len(s4), t  # complete trades only (incomplete already excluded)
        ts = s4c.iloc[si]
        assert ts > tc, t
        trades.append({"coin": t["coin"], "delivery": t["delivery"],
                       "F_entry": float(t["F_entry"]), "S_entry": float(t["S_entry"]),
                       "ret_alloc": float(t["ret_alloc"]),
                       "tc_ns": tc.value, "ts_ns": ts.value})

    # ---- raw hourly carry curve (indexed units, per f=1; sized later) ----
    G_ns = grid_ns
    raw = np.zeros(len(grid))
    per_trade_peak = {}
    for tr in trades:
        st, sc = spot[tr["coin"]]
        ft, fc = qmap[(tr["coin"], tr["delivery"])]
        S = last_close_before(st, sc, G_ns)
        F = last_close_before(ft, fc, G_ns)
        with np.errstate(divide="ignore", invalid="ignore"):
            mtm = (S / tr["S_entry"] - 1.0) + ((tr["F_entry"] - F) / tr["F_entry"]) - FEE_ENTRY_PAID
        mtm[~np.isfinite(mtm)] = np.nan
        # forward-fill hourly marks inside the holding window (like 4h ffill of closes)
        s = pd.Series(mtm, index=grid)
        s = s.ffill()
        mtm = s.to_numpy()
        v = np.zeros(len(grid))
        open_m = G_ns > tr["tc_ns"]
        settled_m = G_ns >= tr["ts_ns"]
        hold_m = open_m & ~settled_m
        v[hold_m] = mtm[hold_m]
        v[hold_m & ~np.isfinite(mtm)] = 0.0
        v[settled_m] = tr["ret_alloc"]
        raw += v
        per_trade_peak[tr["delivery"] + tr["coin"]] = float(np.nanmin(mtm[hold_m])) if hold_m.any() else 0.0
    # raw value exactly at each anchor (bars strictly before the anchor)
    a_ns = np.array([a.value for a in ANCHORS])
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
            if np.isfinite(S) and np.isfinite(F) and tr["F_entry"] and tr["S_entry"]:
                tot += (S / tr["S_entry"] - 1.0) + ((tr["F_entry"] - F) / tr["F_entry"]) - FEE_ENTRY_PAID
        raw_at_anchor.append(tot)
    raw_at_anchor = np.array(raw_at_anchor)

    # ---- base rows + combos ----
    runs = pickle.loads((RD / "v424" / "v424_runs.pkl").read_bytes())
    assert set(runs) == {0, 1, 2, 3}
    combos = []
    base_rows = {}
    for qual in qualifying:
        v, row = qual.split("/")
        assert v == "v424"  # only v424 rows qualified; v425 scanned and listed
        r424 = runs
        # base via the shared reset metric (exact function the assignment names)
        base_years = [rm.year_reset(r424, row, y) for y in range(5)]
        base_R = round(float(np.prod([1 + yy["R"] / 100 for yy in base_years]) ** (1 / 5) - 1) * 100, 3)
        base_rows[qual] = {"years": base_years, "R_5y": base_R,
                           "W": min(yy["R"] for yy in base_years),
                           "DD": max(yy["DD"] for yy in base_years)}
        # per-phase reset paths on the shared grid
        E, MN = [], []
        for s in range(4):
            e1, m1 = v388.hourly(r424[s][row], G0, g1)
            assert (e1.index == grid).all()
            E.append(e1)
            MN.append(m1)
        for f in F_ROWS:
            years = []
            chained_es, chained_ms = [], []
            level = 1.0
            for y, a0 in enumerate(ANCHORS):
                a1 = a0 + YEAR_LEN
                seg = (grid > a0) & (grid <= a1)
                b = np.array([float(e[e.index <= a0].iloc[-1]) if (e.index <= a0).any() else 1.0
                              for e in E])
                es = sum(e[seg] / bb for e, bb in zip(E, b)) / 4
                ms = sum(m[seg] / bb for m, bb in zip(MN, b)) / 4
                cy = f * (raw[seg] - raw_at_anchor[y])
                c = pd.Series(cy, index=es.index)
                es_c = es + c
                ms_c = ms + c
                pk = np.maximum.accumulate(es_c.to_numpy())
                R = round(100 * float(es_c.iloc[-1] ** (1 / 12) - 1), 3)
                DD = round(100 * float(np.max(1 - ms_c.to_numpy() / pk)), 2)
                years.append({"anchor": str(a0.date()), "R": R, "DD": DD,
                              "base_R": base_years[y]["R"], "base_DD": base_years[y]["DD"],
                              "carry_R_pp": round(R - base_years[y]["R"], 3),
                              "carry_DD_pp": round(DD - base_years[y]["DD"], 2),
                              "total_pct": round(float(es_c.iloc[-1] - 1) * 100, 4)})
                chained_es.append(es_c.to_numpy() * level)
                chained_ms.append(ms_c.to_numpy() * level)
                level *= float(es_c.iloc[-1])
            R5 = round(float(np.prod([1 + yy["R"] / 100 for yy in years]) ** (1 / 5) - 1) * 100, 3)
            W = min(yy["R"] for yy in years)
            DDmax = max(yy["DD"] for yy in years)
            fes = np.concatenate(chained_es)
            fms = np.concatenate(chained_ms)
            full_dd = round(100 * float(np.max(1 - fms / np.maximum.accumulate(fes))), 2)
            stretch = bool(R5 >= 5.0 and DDmax < 15.0 and full_dd < 15.0
                           and sum(yy["R"] < 0 for yy in years) == 0)
            combos.append({"row": qual, "f": f, "years": years,
                           "R_5y": R5, "W": W, "DD_maxyearly": DDmax,
                           "full_path_dd_chained": full_dd,
                           "losing_years": sum(yy["R"] < 0 for yy in years),
                           "stretch_all": stretch,
                           "win_rate_note": ("BOT all-trade win rate unchanged: equity-level overlay "
                                             "adds zero trades (v424_runs.pkl stores only t/eq/eq_min "
                                             "for these rows); carry pairs are 33/33 net positive on "
                                             "allocated capital per oc_cashcarry, reported separately, "
                                             "not mixed into a trade win rate.")})

    # ---- base chained full-path DD (same chaining, for an apples-to-apples delta) ----
    base_chained = {}
    for qual in qualifying:
        row = qual.split("/")[1]
        lv = 1.0
        fes, fms = [], []
        for y, a0 in enumerate(ANCHORS):
            a1 = a0 + YEAR_LEN
            parts_e, parts_m = [], []
            for s in range(4):
                e1, m1 = v388.hourly(runs[s][row], G0, g1)
                b = float(e1[e1.index <= a0].iloc[-1]) if (e1.index <= a0).any() else 1.0
                parts_e.append(e1[(e1.index > a0) & (e1.index <= a1)] / b)
                parts_m.append(m1[(m1.index > a0) & (m1.index <= a1)] / b)
            es = sum(parts_e) / 4
            ms = sum(parts_m) / 4
            fes.append(es.to_numpy() * lv)
            fms.append(ms.to_numpy() * lv)
            lv *= float(es.iloc[-1])
        fes, fms = np.concatenate(fes), np.concatenate(fms)
        base_chained[qual] = round(100 * float(np.max(1 - fms / np.maximum.accumulate(fes))), 2)

    # ---- checks ----
    off = scanned["v424/R2B1D13BF"]
    base = base_rows["v424/R2B1D13BF"]
    res = {"checks": {
        "base_R_gap_vs_official": round(abs(base["R_5y"] - off["R"]), 4),
        "base_W_gap_vs_official": round(abs(base["W"] - off["W"]), 4),
        "base_DD_gap_vs_official": round(abs(base["DD"] - off["DD"]), 4),
    }}
    res["checks"]["monthly_total_residual_pp"] = round(float(max(
        abs((1 + yy["total_pct"] / 100) ** (1 / 12) * 100 - 100 - yy["R"])
        for c in combos for yy in c["years"])), 6)

    out = {
        "meta": {
            "rows_scanned": {k: {"R": v["R"], "W": v["W"], "DD": v["DD"],
                                 "full_path_dd": v["full_path_dd"], "losing": v["losing"]}
                             for k, v in scanned.items()},
            "qualifying_max_yearly_DD_lt_15": qualifying,
            "carry_rule": ("frozen oc_cashcarry (PLAN pre-registered): roll next-quarter at <=7d, "
                           "enter iff ann basis >= 4%, equal-notional spot long + quarterly short, "
                           "hold to delivery, fees spot 0.001/side + fut 0.00055/0.0002; "
                           "33 entered / 13 skipped / 2 incomplete reused verbatim"),
            "combination": ("equity-level: per anchor year, 4-phase mix reset to 1.0 (reset_metric.year_reset) "
                            "+ carry sleeve at f of year-start equity, carry marked hourly causal "
                            "(last closed hourly bar strictly before t), rebased to 0 at anchor; "
                            "full-path DD = chained-reset path (labelled)"),
            "sizing_note": ("carry sized f of year-start equity (yearly rebalance); oc_carrycombo draft said "
                            "'rebalanced only at rolls' but that folder does not exist in this repo, so the "
                            "yearly-rebalance version is defined and labelled here"),
            "g1": str(g1), "data_cap": "2026-09-24T00:00:00Z",
            "post_hoc": True, "reporting_only": True,
        },
        "base_official_v424": off,
        "base_recomputed": {k: {"years": v["years"], "R_5y": v["R_5y"], "W": v["W"], "DD": v["DD"],
                                "full_path_dd_chained": base_chained[k]} for k, v in base_rows.items()},
        "combos": combos,
        "checks": res["checks"],
    }
    (HERE / "results.json").write_text(json.dumps(out, indent=1))
    print(f"qualifying={qualifying}")
    for c in combos:
        print(f"{c['row']} f={c['f']}: R5={c['R_5y']} W={c['W']} DDmax={c['DD_maxyearly']} "
              f"fullDD={c['full_path_dd_chained']} losing={c['losing_years']} stretch_all={c['stretch_all']}")
        for yy in c["years"]:
            print(f"   {yy['anchor']}: R={yy['R']} (base {yy['base_R']}) "
                  f"DD={yy['DD']} (base {yy['base_DD']})")
    print("checks:", json.dumps(res["checks"]))


if __name__ == "__main__":
    main()
