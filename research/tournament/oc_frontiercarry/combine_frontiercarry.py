"""oc_frontiercarry: POST-HOC carry overlay on every stored frontier row.

Assignment (docs/opencode/OPENCODE_W_oc_frontiercarry.md): for every frontier
row (oc_frontier v399-v423, 80 BOT rows, reset 5y metric) whose per-phase runs
are stored, add the frozen oc_cashcarry sleeve at f = 0.25 and report 5y mean,
worst year, max yearly DD, full-path DD, losing years, with and without carry,
sorted by max yearly DD; mark rows meeting (a) BOT base (>= 5 %/mo, DD < 20,
no losing year) and (b) stretch DD < 15.

Combination is equity-level, method reused UNCHANGED from
research/tournament/oc_carryd13/combine_carryd13.py (imported, not modified):
per anchor year, 4-phase mix reset to 1.0 (reset_metric.year_reset) + carry
sleeve at f of year-start equity (yearly rebalance, labelled), carry marked
HOURLY causal (last closed hourly bar strictly before t; 0 before entry-bar
close; locked to the frozen ret_alloc from settlement-bar close); combined
es/ms = base es/ms + carry curve; 5y mean = geometric mean of yearly monthly
factors (same as v424/frontier); full-path DD = chained-reset path (labelled).
Base chained path is recomputed with the same chaining for an apples-to-apples
delta; official frontier values (result.json rows + run.log full-path DD) are
kept for reference and cross-checked.

Margin note (oc_utamargin REPORT): additive overlay at f = 0.25 is margin-safe
on ONE Bybit UTA (0 blocked hours, no MM breach, no liquidation incl. -10%
gap); f = 0.50 needs split capital. Friction note (oc_carryfric REPORT):
frictions lower all returns by ~0.2-0.8 %/mo and breach DD even at f = 0.50.

POST-HOC, REPORTING ONLY: every base row here was already scored on all five
walk-forward years (anchors 2021-09-24 .. 2025-09-24, +365 d); the carry rule
was fixed before any combination (oc_cashcarry PLAN pre-registered). No
selection claim, no new predictive features (VF_COMMON feature-study rules:
not applicable, no compute/events).

Usage: .venv/Scripts/python.exe research/tournament/oc_frontiercarry/combine_frontiercarry.py
Reads: oc_frontier/results.json, vNNN/vNNN_result.json + vNNN_runs.pkl,
  oc_carryd13/combine_carryd13.py (imported, not modified),
  oc_cashcarry/results.json, research/tournament/ext/hourly_ext.parquet
  (t < 2026-09-24, asserted), data/raw/qbasis_20261003/um_*_1h.parquet, one
  spot-4h file (delivery grid).
Writes: research/tournament/oc_frontiercarry/results.json
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
FR = ROOT / "research/tournament/oc_frontier"
CC = ROOT / "research/tournament/oc_cashcarry"
HOURLY = ROOT / "research/tournament/ext/hourly_ext.parquet"
QDIR = ROOT / "data/raw/qbasis_20261003"
SDIR = ROOT / "data/raw/spot_majors_20260925"

F_CARRY = 0.25


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> None:
    c13 = _load("combine_carryd13_reuse",
                ROOT / "research/tournament/oc_carryd13/combine_carryd13.py")
    v388 = _load("v388_for_frontiercarry", RD / "v388" / "v388_bot_stop_distance.py")
    rm = _load("reset_for_frontiercarry",
               ROOT / "research/diagnostics/r2_decompose5/reset_metric.py")
    g1 = v388.Y1 + pd.Timedelta(hours=12)
    grid = pd.date_range(c13.G0, g1, freq="1h")
    grid_ns = grid.values.astype("datetime64[ns]").astype(np.int64)

    # ---- frontier rows (80, reset 5y metric) ----
    front = json.loads((FR / "results.json").read_text())
    assert front["meta"]["n_rows"] == 80, front["meta"]["n_rows"]
    frows: list[dict] = front["rows"]

    # ---- frozen carry trades, reused unchanged (same assertions as oc_carryd13) ----
    cc = json.loads((CC / "results.json").read_text())
    assert cc["meta"]["threshold_ann_basis"] == 0.04
    assert len(cc["trades"]) == 33 and cc["n_skipped"] == 13 and cc["n_incomplete"] == 2
    assert cc["pooled"]["n_trades"] == 25

    # ---- hourly spot (causal last-closed-bar marks; verbatim from oc_carryd13) ----
    h = pd.read_parquet(HOURLY, columns=["t", "close", "sym"])
    h["t"] = pd.to_datetime(h["t"], utc=True)
    assert bool((h["t"] < c13.CAP).all()), "hourly data reaches beyond the cap"
    spot: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    for coin in ("BTC", "ETH"):
        d = h[h["sym"] == f"{coin}USDT"].sort_values("t")
        spot[coin] = (d["t"].values.astype("datetime64[ns]").astype(np.int64),
                      d["close"].to_numpy(dtype=float))

    # ---- quarterly hourly per traded contract (verbatim from oc_carryd13) ----
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

    # ---- entry/settlement timestamps (spot-4h grid; verbatim from oc_carryd13) ----
    s4 = pd.read_parquet(SDIR / "BTCUSDT_spot_4h.parquet",
                         columns=["open_time", "close_time"])
    s4o = pd.to_datetime(s4["open_time"], utc=True)
    s4c = pd.to_datetime(s4["close_time"], utc=True)
    trades = []
    for t in cc["trades"]:
        te = pd.Timestamp(t["entry_open"], tz="UTC")
        tc = te + pd.Timedelta(hours=4)
        assert (s4o == te).any(), t
        D = pd.Timestamp(t["delivery"] + " 08:00", tz="UTC")
        si = int(np.searchsorted(s4c.values.astype("datetime64[ns]").astype(np.int64),
                                 D.value, side="right"))
        assert si < len(s4), t
        ts = s4c.iloc[si]
        assert ts > tc, t
        trades.append({"coin": t["coin"], "delivery": t["delivery"],
                       "F_entry": float(t["F_entry"]), "S_entry": float(t["S_entry"]),
                       "ret_alloc": float(t["ret_alloc"]),
                       "tc_ns": tc.value, "ts_ns": ts.value})

    # ---- raw hourly carry curve (indexed units at f=1; verbatim arithmetic) ----
    G_ns = grid_ns
    raw = np.zeros(len(grid))
    for tr in trades:
        st, sc = spot[tr["coin"]]
        ft, fc = qmap[(tr["coin"], tr["delivery"])]
        S = c13.last_close_before(st, sc, G_ns)
        F = c13.last_close_before(ft, fc, G_ns)
        with np.errstate(divide="ignore", invalid="ignore"):
            mtm = ((S / tr["S_entry"] - 1.0) + ((tr["F_entry"] - F) / tr["F_entry"])
                   - c13.FEE_ENTRY_PAID)
        mtm[~np.isfinite(mtm)] = np.nan
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
    a_ns = np.array([a.value for a in c13.ANCHORS])
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
            S = c13.last_close_before(st, sc, qa)[0]
            F = c13.last_close_before(ft, fc, qa)[0]
            if np.isfinite(S) and np.isfinite(F) and tr["F_entry"] and tr["S_entry"]:
                tot += ((S / tr["S_entry"] - 1.0) + ((tr["F_entry"] - F) / tr["F_entry"])
                        - c13.FEE_ENTRY_PAID)
        raw_at_anchor.append(tot)
    raw_at_anchor = np.array(raw_at_anchor)

    # ---- per-row base + carry (stored per-phase equity, no engine reruns) ----
    runs_cache: dict[str, dict] = {}
    combos = []
    max_R_gap = 0.0
    max_W_gap = 0.0
    max_DD_gap = 0.0
    max_resid = 0.0
    n_stored = 0
    missing: list[str] = []
    for fr in frows:
        v, row = fr["version"], fr["row"]
        key = f"{v}/{row}"
        if v not in runs_cache:
            runs_cache[v] = pickle.loads((RD / v / f"{v}_runs.pkl").read_bytes())
            assert set(runs_cache[v]) == {0, 1, 2, 3}, v
        runs = runs_cache[v]
        if row not in runs[0]:
            missing.append(key)
            continue
        n_stored += 1
        base_years = [rm.year_reset(runs, row, y) for y in range(5)]
        base_R5 = round(float(np.prod([1 + yy["R"] / 100 for yy in base_years]) ** (1 / 5) - 1) * 100, 3)
        base_W = min(yy["R"] for yy in base_years)
        base_DD = max(yy["DD"] for yy in base_years)
        max_R_gap = max(max_R_gap, abs(base_R5 - float(fr["R"])))
        max_W_gap = max(max_W_gap, abs(base_W - float(fr["W"])))
        max_DD_gap = max(max_DD_gap, abs(base_DD - float(fr["dd_yearly"])))
        E, MN = [], []
        for s in range(4):
            e1, m1 = v388.hourly(runs[s][row], c13.G0, g1)
            assert (e1.index == grid).all(), (v, row, s)
            E.append(e1)
            MN.append(m1)
        per_f = {}
        for f in (0.0, F_CARRY):
            years = []
            chained_es, chained_ms = [], []
            level = 1.0
            for y, a0 in enumerate(c13.ANCHORS):
                a1 = a0 + c13.YEAR_LEN
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
            for yy in years:
                resid = abs((1 + yy["total_pct"] / 100) ** (1 / 12) * 100 - 100 - yy["R"])
                max_resid = max(max_resid, resid)
            per_f[f] = {"years": years, "R_5y": R5, "W": W, "DD_maxyearly": DDmax,
                        "full_path_dd_chained": full_dd,
                        "losing_years": sum(yy["R"] < 0 for yy in years)}
        b, c = per_f[0.0], per_f[F_CARRY]
        off_full = fr["full_path_dd"]
        # BOT base: R>=5, max-yearly DD<20 AND chained full-path DD<20, no losing year.
        # Stretch: R>=5, max-yearly DD<15 AND chained full-path DD<15, no losing year.
        def bot_base(d):
            return bool(d["R_5y"] >= 5.0 and d["DD_maxyearly"] < 20.0
                        and d["full_path_dd_chained"] < 20.0 and d["losing_years"] == 0)

        def stretch(d):
            return bool(d["R_5y"] >= 5.0 and d["DD_maxyearly"] < 15.0
                        and d["full_path_dd_chained"] < 15.0 and d["losing_years"] == 0)

        combos.append({
            "key": key, "version": v, "row": row,
            "audited": bool(fr["audited"]), "recent_R": float(fr["recent_r"]),
            "official": {"R": float(fr["R"]), "W": float(fr["W"]),
                         "DD_maxyearly": float(fr["dd_yearly"]),
                         "full_path_dd": None if off_full is None else float(off_full),
                         "losing_years": int(sum(1 for y in fr["years"] if y[0] < 0))},
            "base": b, "carry_f": F_CARRY, "carry": c,
            "base_bot_base": bot_base(b), "carry_bot_base": bot_base(c),
            "carry_stretch": stretch(c),
            "win_rate_note": ("BOT all-trade win rate unchanged: equity-level overlay "
                              "adds zero trades (runs.pkl stores only t/eq/eq_min "
                              "for these rows); carry pairs are 33/33 net positive on "
                              "allocated capital per oc_cashcarry, reported separately, "
                              "not mixed into a trade win rate."),
        })

    combos.sort(key=lambda d: (d["carry"]["DD_maxyearly"], -d["carry"]["R_5y"]))

    checks = {
        "n_frontier_rows": len(frows),
        "n_with_stored_runs": n_stored,
        "missing_rows": missing,
        "base_R_gap_vs_official_max": round(float(max_R_gap), 4),
        "base_W_gap_vs_official_max": round(float(max_W_gap), 4),
        "base_DD_gap_vs_official_max": round(float(max_DD_gap), 4),
        "monthly_total_residual_pp_max": round(float(max_resid), 6),
        "carry_fee_entry_paid": float(c13.FEE_ENTRY_PAID),
        "sort": "combos sorted by carry max yearly DD ascending (ties: higher carry R first)",
        "bot_base_def": "R_5y >= 5.0, max yearly DD < 20, chained full-path DD < 20, losing years == 0",
        "stretch_def": "R_5y >= 5.0, max yearly DD < 15, chained full-path DD < 15, losing years == 0",
    }

    out = {
        "meta": {
            "frontier_src": "oc_frontier/results.json (80 BOT rows v399-v423, reset 5y metric)",
            "n_rows": len(combos),
            "carry_f": F_CARRY,
            "carry_rule": ("frozen oc_cashcarry (PLAN pre-registered): roll next-quarter at <=7d, "
                           "enter iff ann basis >= 4%, equal-notional spot long + quarterly short, "
                           "hold to delivery, fees spot 0.001/side + fut 0.00055/0.0002; "
                           "33 entered / 13 skipped / 2 incomplete reused verbatim"),
            "combination": ("equity-level, method reused UNCHANGED from "
                            "oc_carryd13/combine_carryd13.py (imported): per anchor year, "
                            "4-phase mix reset to 1.0 (reset_metric.year_reset) + carry sleeve "
                            "at f of year-start equity, carry marked hourly causal "
                            "(last closed hourly bar strictly before t), rebased to 0 at anchor; "
                            "full-path DD = chained-reset path (labelled)"),
            "sizing_note": ("carry sized f of year-start equity (yearly rebalance, same as "
                            "oc_carryd13); margin-safe at f = 0.25 on ONE Bybit UTA per oc_utamargin"),
            "margin_src": ("oc_utamargin REPORT: additive overlay at f = 0.25 margin-safe "
                           "(0 blocked hours, no MM breach, no liquidation incl. -10% gap)"),
            "friction_src": ("oc_carryfric REPORT: frictions lower all returns by ~0.2-0.8 %/mo; "
                             "D13BF+G2 friction tables in that report"),
            "g1": str(g1), "data_cap": "2026-09-24T00:00:00Z",
            "post_hoc": True, "reporting_only": True,
        },
        "combos": combos,
        "checks": checks,
    }
    (HERE / "results.json").write_text(json.dumps(out, indent=1))
    print(f"rows={len(combos)} stored={n_stored} missing={len(missing)} "
          f"Rgap={checks['base_R_gap_vs_official_max']} "
          f"Wgap={checks['base_W_gap_vs_official_max']} "
          f"DDgap={checks['base_DD_gap_vs_official_max']}")
    nb = sum(1 for d in combos if d["carry_bot_base"])
    ns = sum(1 for d in combos if d["carry_stretch"])
    print(f"carry_bot_base={nb} carry_stretch={ns}")
    for d in combos[:5]:
        print(f"{d['key']}: carry R5={d['carry']['R_5y']} W={d['carry']['W']} "
              f"DDmax={d['carry']['DD_maxyearly']} fullDD={d['carry']['full_path_dd_chained']} "
              f"losing={d['carry']['losing_years']} base_ok={d['base_bot_base']} "
              f"carry_ok={d['carry_bot_base']} stretch={d['carry_stretch']}")


if __name__ == "__main__":
    main()
