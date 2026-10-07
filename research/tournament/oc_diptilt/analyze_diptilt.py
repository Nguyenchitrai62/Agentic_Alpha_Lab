"""oc_diptilt: regime-tilted dip size proxy (IDEA #39, PLAN pre-registered).

Fixed rule, ONE MAIN variant: dip rung size x1.2 in bull bars, x0.8 in bear
bars (v410 bear flag: BTC 4h open < 1200-bar mean, causal at the bar open).
Sensitivity x1.1/x0.9 reported only (NOT for selection).

Approximation on TRUE per-rung records of oc_kpi/events_s0..s3.parquet
(pairing = exact copy of oc_deepcheck pair_true): scale each rung's pnl by
its multiplier, rebuild each phase's equity path additively per bar, mix the
four phases 1/4 each with reset at anchors (reset_metric idea).

DOCUMENTED APPROXIMATION: additive (no compounding inside the year), no
budget/notional interaction (bigger rungs do not change admission/margin of
other rungs), no book leg (dip sleeve only), exit-time ordering inside the
fill year (dip rungs exit inside the same 4h holding bar, so fill-year ~=
exit-year up to boundary bars).

LIGHT: one process, RAM < 1 GB, no 1m data.
Usage: .venv/Scripts/python.exe research/tournament/oc_diptilt/analyze_diptilt.py
Writes results.json in this folder.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
KPI = HERE.parent / "oc_kpi"
EXT = HERE.parent / "ext"
REGIMETRUE = HERE.parent / "oc_regimetrue" / "results.json"
ANCH = [pd.Timestamp(f"{y}-09-24", tz="UTC") for y in (2021, 2022, 2023, 2024, 2025)]
ANCH_END = pd.Timestamp("2026-09-24", tz="UTC")
H4_HOURS = {0, 4, 8, 12, 16, 20}
EXITS = ("rung_sl", "rung_tp", "rung_timeout")
M_BULL, M_BEAR = 1.2, 0.8
S_BULL, S_BEAR = 1.1, 0.9


def year_of(t) -> int | None:
    t = pd.Timestamp(t)
    for k in range(5):
        end = ANCH[k + 1] if k < 4 else ANCH_END
        if ANCH[k] <= t < end:
            return k
    return None


def pair_true(ev: pd.DataFrame):
    """Positional pairing (exact copy of oc_deepcheck pair_true)."""
    rows, viol, maxwdiff = [], 0, 0.0
    for i in range(len(ev)):
        r = ev.iloc[i]
        if r["kind"] == "rung_fill":
            x = ev.iloc[i + 1]
            if x["kind"] not in EXITS or x["symbol"] != r["symbol"]:
                viol += 1
                continue
            maxwdiff = max(maxwdiff, abs(float(x["weight"]) - float(r["weight"])))
            rows.append(dict(
                fill_t=pd.Timestamp(r["t"]), exit_t=pd.Timestamp(x["t"]),
                symbol=r["symbol"], depth=float(r["rung"]),
                exit=x["kind"], weight=float(x["weight"]), ret=float(x["ret"]),
                pnl=float(x["weight"]) * float(x["ret"])))
    return rows, viol, maxwdiff


def floor_h4(ts: pd.Timestamp) -> pd.Timestamp:
    ts = pd.Timestamp(ts)
    h = (ts.hour // 4) * 4
    return pd.Timestamp(ts.year, ts.month, ts.day, h, tz="UTC")


def r_from_eq(eq_end: float) -> float:
    return (float(eq_end) ** (1.0 / 12.0) - 1.0) * 100.0


def dd_from_path(eq: np.ndarray) -> float:
    eq = np.asarray(eq, dtype=float)
    pk = np.maximum.accumulate(eq)
    return float(np.max(1.0 - eq / pk)) * 100.0


def mix_year_path(per_shift_eq: dict[int, tuple[np.ndarray, np.ndarray]]):
    """Time-union 1/4 mix of per-shift additive paths.

    per_shift_eq[s] = (exit_times_sorted, eq_values_incl_start1).
    Returns (times, mix_eq) with mix starting at 1.0.
    """
    times = np.sort(np.unique(np.concatenate(
        [np.asarray(t, dtype="datetime64[ns]") for t, _ in per_shift_eq.values()])))
    mix = np.zeros(len(times))
    for i, t in enumerate(times):
        tot = 0.0
        for s, (st, se) in per_shift_eq.items():
            j = int(np.searchsorted(st, t, side="right")) - 1
            tot += float(se[j + 1]) if j >= 0 else 1.0
        mix[i] = tot / 4.0
    return times, mix


def main():
    hourly = pd.read_parquet(EXT / "hourly_ext.parquet", columns=["t", "open", "sym"])
    hourly["t"] = pd.to_datetime(hourly["t"], utc=True)
    assert hourly["t"].max() < ANCH_END, hourly["t"].max()
    btc = (hourly[hourly["sym"] == "BTCUSDT"].sort_values("t"))
    btc = btc[(btc["t"].dt.hour.isin(H4_HOURS)) & (btc["t"].dt.minute == 0)]
    btc = btc[btc["t"] < ANCH_END].drop_duplicates("t").set_index("t").sort_index()
    btc_open = btc["open"].astype(float)
    ma1200 = btc_open.rolling(1200, min_periods=600).mean()

    all_rows, checks = [], dict(adjacency_violations=0, max_fill_exit_wdiff=0.0)
    for s in range(4):
        ev = pd.read_parquet(KPI / f"events_s{s}.parquet")
        rows, viol, maxwd = pair_true(ev)
        checks["adjacency_violations"] += int(viol)
        checks["max_fill_exit_wdiff"] = max(checks["max_fill_exit_wdiff"], float(maxwd))
        for d in rows:
            d["shift"] = s
            d["year"] = year_of(d["fill_t"])
            all_rows.append(d)
    checks["n_rungs"] = len(all_rows)
    assert len(all_rows) == 21389, len(all_rows)
    checks["outside_anchor_years"] = sum(1 for d in all_rows if d["year"] is None)
    rows = [d for d in all_rows if d["year"] is not None]

    for d in rows:
        t0 = floor_h4(d["fill_t"])
        d["T0"] = t0
        try:
            o = float(btc_open.loc[t0])
            m = float(ma1200.loc[t0])
            bear = bool(np.isfinite(o) and np.isfinite(m) and o < m)
        except KeyError:
            bear = False
        d["bear"] = "bear" if bear else "bull"
        d["m"] = M_BEAR if bear else M_BULL
        d["m_sens"] = S_BEAR if bear else S_BULL
        d["pnl_tilt"] = d["pnl"] * d["m"]
        d["pnl_sens"] = d["pnl"] * d["m_sens"]

    # per-shift per-year additive paths (sorted by exit_t), then 1/4 union mix
    years, bullbear = {}, {}
    for k in range(5):
        per_shift = {}
        for s in range(4):
            sel = sorted([d for d in rows if d["shift"] == s and d["year"] == k],
                         key=lambda r: r["exit_t"])
            st = np.array([r["exit_t"].to_datetime64() for r in sel], dtype="datetime64[ns]")
            base = np.concatenate([[1.0], 1.0 + np.cumsum([r["pnl"] for r in sel])])
            tilt = np.concatenate([[1.0], 1.0 + np.cumsum([r["pnl_tilt"] for r in sel])])
            sens = np.concatenate([[1.0], 1.0 + np.cumsum([r["pnl_sens"] for r in sel])])
            per_shift[s] = (st, base, tilt, sens)
        tb, mb = mix_year_path({s: (v[0], v[1]) for s, v in per_shift.items()})
        _, mt = mix_year_path({s: (v[0], v[2]) for s, v in per_shift.items()})
        _, ms = mix_year_path({s: (v[0], v[3]) for s, v in per_shift.items()})
        eb, et, es = float(mb[-1]), float(mt[-1]), float(ms[-1])
        years[str(k)] = dict(
            n=sum(1 for d in rows if d["year"] == k),
            base=dict(eq_end=round(eb, 6), R=round(r_from_eq(eb), 4),
                      DD=round(dd_from_path(mb), 4),
                      mix_pct=round((eb - 1) * 100, 3)),
            tilt=dict(eq_end=round(et, 6), R=round(r_from_eq(et), 4),
                      DD=round(dd_from_path(mt), 4),
                      mix_pct=round((et - 1) * 100, 3)),
            sens=dict(eq_end=round(es, 6), R=round(r_from_eq(es), 4),
                      DD=round(dd_from_path(ms), 4),
                      mix_pct=round((es - 1) * 100, 3)),
            pass_ret=bool(r_from_eq(et) > r_from_eq(eb)),
            pass_dd=bool(dd_from_path(mt) <= dd_from_path(mb)),
            pass_ret_sens=bool(r_from_eq(es) > r_from_eq(eb)),
            pass_dd_sens=bool(dd_from_path(ms) <= dd_from_path(mb)))
        bb = {}
        for regime in ("bear", "bull"):
            sel = [d for d in rows if d["year"] == k and d["bear"] == regime]
            pb = sum(d["pnl"] for d in sel) / 4 * 100
            pt = sum(d["pnl_tilt"] for d in sel) / 4 * 100
            bb[regime] = dict(n=len(sel), base_mix_pct=round(pb, 3),
                              tilt_mix_pct=round(pt, 3))
        bullbear[str(k)] = bb

    pooled = {}
    for regime in ("bear", "bull", "all"):
        sel = rows if regime == "all" else [d for d in rows if d["bear"] == regime]
        pooled[regime] = dict(
            n=len(sel), base_mix_pct=round(sum(d["pnl"] for d in sel) / 4 * 100, 3),
            tilt_mix_pct=round(sum(d["pnl_tilt"] for d in sel) / 4 * 100, 3),
            sens_mix_pct=round(sum(d["pnl_sens"] for d in sel) / 4 * 100, 3))

    # replication vs oc_regimetrue year totals (fill-year, all depths)
    reg = json.loads(REGIMETRUE.read_text())["totals"]
    repdiff = 0.0
    for k in range(5):
        a = years[str(k)]["base"]["mix_pct"]
        b = reg[str(k)]["all"]["pnl_mix_pct"]
        repdiff = max(repdiff, abs(a - b))
    checks["replication_max_abs_mixdiff_vs_regimetrue_all"] = round(repdiff, 4)
    assert repdiff < 0.002, repdiff

    n_ret = sum(1 for k in range(5) if years[str(k)]["pass_ret"])
    n_dd = sum(1 for k in range(5) if years[str(k)]["pass_dd"])
    promising = bool(n_ret >= 4 and n_dd >= 4)
    out = dict(
        variant="tilt x1.2 bull / x0.8 bear (v410 flag)",
        sensitivity="x1.1 / x0.9 (reported only, NOT for selection)",
        selection_rule=("PROMISING iff tilt R_proxy > base R_proxy in >= 4/5 years "
                        "AND tilt DD_proxy <= base DD_proxy in >= 4/5 years"),
        methods=("TRUE pairs = positional adjacency in engine append order "
                 "(fill row + its own exit row, same symbol). pnl = exit weight * "
                 "engine ret (net of rung fees), pnl_tilt = pnl * m(T0) with "
                 "m = 0.8 bear / 1.2 bull (sens 0.9/1.1). T0 = floor(fill_t to "
                 "standard 4h grid); bear = v410 BTC open4[T0] < MA1200[T0] incl "
                 "T0 min600, NaN->bull; known at the bar open. Year = FILL in "
                 "anchor year [A_k, A_k+365d). Per shift+year additive path "
                 "eq = 1 + cumsum(pnl_scaled) sorted by exit_t; mix path = "
                 "time-union mean of the 4 shift paths (1/4 each, reset to 1.0 "
                 "at every anchor; reset_metric idea). R_proxy = eq_end^(1/12)-1; "
                 "DD_proxy = max drawdown of the mix path. APPROXIMATION: "
                 "additive (no compounding), no budget/notional interaction, "
                 "no book leg (dip sleeve only). No 1m data read."),
        anchors=[a.strftime("%Y-%m-%d") for a in ANCH],
        multipliers=dict(main=dict(bull=M_BULL, bear=M_BEAR),
                         sens=dict(bull=S_BULL, bear=S_BEAR)),
        years=years, bullbear=bullbear, pooled=pooled,
        decision=dict(n_pass_ret=int(n_ret), n_pass_dd=int(n_dd),
                      promising=promising,
                      verdict=("PROMISING: leader runs a registered engine version"
                               if promising else "NOT PROMISING")),
        checks=checks)
    (HERE / "results.json").write_text(json.dumps(out, indent=1, default=str))
    print("n_rungs", len(rows), "viol", checks["adjacency_violations"], flush=True)
    for k in range(5):
        y = years[str(k)]
        print(k, "base R/ DD", y["base"]["R"], y["base"]["DD"],
              "tilt R/DD", y["tilt"]["R"], y["tilt"]["DD"],
              "ret?", y["pass_ret"], "dd?", y["pass_dd"], flush=True)
    print("PROMISING" if promising else "NOT PROMISING",
          f"(ret {n_ret}/5, dd {n_dd}/5)", flush=True)
    print("wrote results.json", flush=True)


if __name__ == "__main__":
    main()
