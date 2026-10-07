"""oc_manualtsmom: M5_human MANUAL + oc_tsmom 30d-TSMOM sleeve combos.

Pre-registered in PLAN.md before any outcome was computed. Fixed rule, one run.
Usage: .venv/Scripts/python.exe research/tournament/oc_manualtsmom/run_manualtsmom.py
Reads: research/tournament/ext/hourly_ext.parquet (BTC+ETH, t < 2026-09-24 UTC),
  research/diagnostics/oc_manualcap/oc_manualcap_runs.pkl (M5_human 4-phase runs),
  research/diagnostics/oc_manualcap/results.json (base proof reference),
  research/tournament/oc_tsmom/results.json (sleeve cross-check).
Imports (not copies): v388_bot_stop_distance.hourly/mix, reset_metric.year_reset.
Writes: research/tournament/oc_manualtsmom/results.json
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
MCAP_PKL = ROOT / "research/diagnostics/oc_manualcap/oc_manualcap_runs.pkl"
MCAP_RES = ROOT / "research/diagnostics/oc_manualcap/results.json"
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
ROW = "M5_human"
WEIGHTS = [0.25, 0.50, 1.00]


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


# ---- hourly marking copied EXACTLY from oc_tsmom_official/run_official.py ----
def build_sleeve_hourly(hourly: pd.DataFrame, opens: pd.DataFrame, pos: pd.DataFrame,
                         year_days: dict[int, list[pd.Timestamp]],
                         sdf_by_year: dict[int, pd.DataFrame]) -> tuple[pd.Series, pd.Series, dict]:
    v388 = _load("v388_grid", RD / "v388" / "v388_bot_stop_distance.py")
    g1 = v388.Y1 + pd.Timedelta(hours=12)
    grid = pd.date_range(G0, g1, freq="1h")
    px = {}
    for sym in COINS:
        d = hourly[hourly["sym"] == sym].set_index("t").sort_index()
        px[sym] = {k: d[k] for k in ("open", "high", "low", "close")}
    S_day: dict = {}
    rs_map = {}
    for y in range(5):
        sdf = sdf_by_year[y]
        for e, r in zip(sdf.index, sdf["r_s"].to_numpy(float)):
            rs_map[e] = float(r)

    def fallback_r(d: pd.Timestamp) -> float:
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
    last_ebar = (v388.Y1 + pd.Timedelta(hours=12)).floor("D")
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
            pp = pd.Series(0.0, index=COINS)
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

    v388 = _load("v388_mtm", RD / "v388" / "v388_bot_stop_distance.py")
    rm = _load("reset_mtm", ROOT / "research/diagnostics/r2_decompose5/reset_metric.py")
    g1 = v388.Y1 + pd.Timedelta(hours=12)

    allres = pickle.loads(MCAP_PKL.read_bytes())
    assert set(allres) == {0, 1, 2, 3}, sorted(allres)
    runs = {s: {ROW: allres[s][ROW]["run"]} for s in allres}

    opens, closes = build_daily(hourly)
    _signal, _vol, pos = compute_positions(closes)

    def year_days(a0: pd.Timestamp) -> list[pd.Timestamp]:
        cands = [a0 + pd.Timedelta(days=i) for i in range(365)]
        last_o = opens.index[-1]
        return [x for x in cands if x <= last_o - pd.Timedelta(days=1)]

    yd = {y: year_days(pd.Timestamp(a, tz="UTC")) for y, a in enumerate(ANCHORS)}
    sdf_by_year = {y: sleeve_daily(opens, pos, yd[y]) for y in range(5)}
    S_eq, S_min, S_day = build_sleeve_hourly(hourly, opens, pos, yd, sdf_by_year)

    # ---- checks ----
    tsmom = json.loads(TSMOM_RES.read_text())
    tsmom_by_anchor = {y["anchor"]: y for y in tsmom["years"]}
    sleeve_gap = []
    for y, a in enumerate(ANCHORS):
        ref = tsmom_by_anchor[a]
        ref_days = [pd.Timestamp(d, tz="UTC") for d in ref["days"]]
        rs = sdf_by_year[y].loc[ref_days, "r_s"].to_numpy(float)
        arr = np.array(ref["r_sleeve"], float)
        sleeve_gap.append(float(np.max(np.abs(rs - arr))))
    bnd_gap = []
    for e, lvl in S_day.items():
        if e in S_eq.index and e > S_eq.index[0]:
            bnd_gap.append(abs(float(S_eq.loc[e]) - float(lvl)))
    viol = float(np.max(np.asarray(S_min) - np.asarray(S_eq)))

    mcap_ref = json.loads(MCAP_RES.read_text())["rows"][ROW]
    recomp = [rm.year_reset(runs, ROW, y) for y in range(5)]
    base_R = [r["R"] for r in recomp]
    base_DD = [r["DD"] for r in recomp]

    # book trades pooled over phases (PLAN.md win metric)
    book_nb, book_wb = [], []
    for y in range(5):
        nb = sum(allres[s][ROW]["wins"][y]["nb"] for s in range(4))
        wb = sum(allres[s][ROW]["wins"][y]["wb"] for s in range(4))
        book_nb.append(int(nb))
        book_wb.append(int(wb))
    pool_nb = int(sum(book_nb))
    pool_wb = int(sum(book_wb))

    # sleeve trades per year (PLAN.md: holding day with non-zero position; win iff r_s > 0)
    sl_n, sl_w = [], []
    for y in range(5):
        sdf = sdf_by_year[y]
        days = sdf.index.tolist()
        pday = [pos.loc[e - pd.Timedelta(days=1)].fillna(0.0)
                if (e - pd.Timedelta(days=1)) in pos.index
                else pd.Series(0.0, index=COINS) for e in days]
        n = sum(1 for p in pday if (abs(float(p["BTCUSDT"])) + abs(float(p["ETHUSDT"])) > 0))
        w = sum(1 for e, p in zip(days, pday)
                if (abs(float(p["BTCUSDT"])) + abs(float(p["ETHUSDT"])) > 0)
                and float(sdf.loc[e, "r_s"]) > 0)
        sl_n.append(int(n))
        sl_w.append(int(w))

    # ---- official-metric combinations ----
    e_full, mn_full = v388.mix(runs, ROW, g1)
    s0 = float(S_eq.iloc[0])
    sleeve_cont = S_eq / s0
    sleeve_low_cont = S_min / s0

    combos = []
    for conv in ("overlay", "split"):
        for w in WEIGHTS:
            years = []
            for y, a in enumerate(ANCHORS):
                a0 = pd.Timestamp(a, tz="UTC")
                parts_e, parts_m = [], []
                for s in range(4):
                    e1, m1 = v388.hourly(runs[s][ROW], G0, g1)
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
                idx = base_es.index.intersection(F.index)
                assert len(idx) >= 8600, (conv, w, a, len(idx))
                be = base_es.loc[idx].to_numpy(float)
                bm = base_ms.loc[idx].to_numpy(float)
                fe = F.loc[idx].to_numpy(float)
                fm = FM.loc[idx].to_numpy(float)
                if conv == "overlay":
                    ce = be + w * (fe - 1.0)
                    cm = bm + w * (fm - 1.0)
                else:
                    ce = (1 - w) * be + w * fe
                    cm = (1 - w) * bm + w * fm
                tot_b = float(be[-1] - 1)
                tot_c = float(ce[-1] - 1)
                m_b = monthly_of_total(tot_b)
                m_c = monthly_of_total(tot_c)
                dd_b = max_dd_from(be, bm) * 100
                dd_c = max_dd_from(ce, cm) * 100
                nb, wb = book_nb[y], book_wb[y]
                ns, ws = sl_n[y], sl_w[y]
                win = (wb + ws) / (nb + ns) if (nb + ns) else None
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
                    "book_nb": nb, "book_wb": wb,
                    "book_win": round(wb / nb, 4) if nb else None,
                    "sleeve_n": ns, "sleeve_w": ws,
                    "sleeve_win": round(ws / ns, 4) if ns else None,
                    "win": round(win, 4) if win is not None else None,
                })
            R5 = round(float(np.prod([1 + y["total_pct"] / 100 for y in years]) ** (1 / 60) - 1) * 100, 3)
            W = round(min(y["monthly_pct"] for y in years), 3)
            DD = round(max(y["maxDD_pct"] for y in years), 2)
            pool_win = (sum(y["book_wb"] for y in years) + sum(y["sleeve_w"] for y in years)) / \
                (sum(y["book_nb"] for y in years) + sum(y["sleeve_n"] for y in years))
            # full-path (mix-style, no reset)
            segf = e_full.index > pd.Timestamp("2021-09-24", tz="UTC")
            ef = e_full[segf].to_numpy(float)
            mf = mn_full[segf].to_numpy(float)
            sc = sleeve_cont[e_full.index[segf]].to_numpy(float)
            sl = sleeve_low_cont[e_full.index[segf]].to_numpy(float)
            if conv == "overlay":
                ce_f = ef + w * (sc - 1.0)
                cm_f = mf + w * (sl - 1.0)
            else:
                ce_f = (1 - w) * ef + w * sc
                cm_f = (1 - w) * mf + w * sl
            fp_dd = round(float(np.max(1 - cm_f / np.maximum.accumulate(ce_f))) * 100, 2)
            fp_tot = round(float(ce_f[-1] - 1) * 100, 3)
            # default rule on the excess
            ex = np.array([y["excess_monthly_pp"] for y in years])
            full = float(np.mean(ex))
            n_pos = int((ex > 0).sum())
            loyo = []
            for h in range(5):
                pool = float(np.mean([ex[k] for k in range(5) if k != h]))
                loyo.append(bool(np.sign(pool) == np.sign(full)) if full != 0 else False)
            promising = bool(n_pos >= 4 and sum(loyo) >= 4)
            base_hit = bool(R5 >= 5.0 and DD < 20.0 and fp_dd < 20.0 and pool_win >= 0.55)
            combos.append({
                "conv": conv, "w": w,
                "R_5y": R5, "W": W, "DD_maxyearly": DD,
                "full_path_dd": fp_dd, "full_path_total_pct": fp_tot,
                "pool_win": round(float(pool_win), 4),
                "promising_default": promising,
                "excess_pos_years": f"{n_pos}/5",
                "loyo_sign_hold": f"{sum(loyo)}/5",
                "base_hit": base_hit,
                "years": years,
            })

    res = 0.0
    for c in combos:
        for y in c["years"]:
            for tot, m in ((y["total_pct"], y["monthly_pct"]), (y["base_total_pct"], y["base_monthly_pct"])):
                m2 = (1 + tot / 100) ** (1 / 12) - 1
                res = max(res, abs(m2 * 100 - m))

    out = {
        "meta": {
            "base": "M5_human honest MANUAL (15-min reaction, night bar skipped, agents ON) from oc_manualcap_runs.pkl; reset_metric.year_reset per year + v388.mix full-path",
            "sleeve": "oc_tsmom exact reuse (BTC+ETH 30d TSMOM, 10% vol target, cap 1.0, next-open, taker 0.00055, longs fund 0.0003/d) + oc_tsmom_official hourly worst-case marking",
            "conventions": "(a) overlay: base_es + w*(F-1); (b) split: (1-w)*base_es + w*F (same for eq_min legs)",
            "weights": WEIGHTS,
            "anchors": ANCHORS,
            "data_cap": "2026-09-24T00:00:00Z",
            "g1": "2026-09-23 12:00:00+00:00",
            "win_metric": "per year (book_wb+sleeve_w)/(book_nb+sleeve_n); sleeve trade = holding day with non-zero position, win iff r_s>0 strict",
        },
        "base_proof": {
            "recomputed_R": base_R,
            "recomputed_DD": base_DD,
            "reference_R": mcap_ref["years_R"],
            "reference_DD": mcap_ref["years_DD"],
            "match_R": base_R == mcap_ref["years_R"],
            "match_DD": base_DD == mcap_ref["years_DD"],
        },
        "book": {"per_year_nb": book_nb, "per_year_wb": book_wb,
                 "pool_nb": pool_nb, "pool_wb": pool_wb,
                 "pool_win": round(pool_wb / pool_nb, 4),
                 "reference_pool_nb": mcap_ref["book_trades"],
                 "reference_pool_win": mcap_ref["book_win"]},
        "sleeve_trades": {"per_year_n": sl_n, "per_year_w": sl_w,
                          "pool_n": int(sum(sl_n)), "pool_w": int(sum(sl_w)),
                          "pool_win": round(sum(sl_w) / sum(sl_n), 4)},
        "checks": {
            "hourly_cap_ok": True,
            "max_sleeve_abs_gap_vs_octsmom": round(float(max(sleeve_gap)), 10),
            "max_day_boundary_gap": round(float(max(bnd_gap)) if bnd_gap else 0.0, 10),
            "max_eqmin_above_eq": round(viol, 10),
            "max_monthly_total_residual_pp": round(float(res), 6),
        },
        "combos": combos,
    }
    (HERE / "results.json").write_text(json.dumps(out, indent=1))
    print(f"sleeve_gap={max(sleeve_gap):.2e} bnd_gap={max(bnd_gap) if bnd_gap else 0:.2e} eqmin_viol={viol:.2e} "
          f"base_match_R={out['base_proof']['match_R']} match_DD={out['base_proof']['match_DD']}", flush=True)
    print(f"book pool {pool_nb} win {pool_wb / pool_nb:.4f} | sleeve pool {sum(sl_n)} win {sum(sl_w) / sum(sl_n):.4f}", flush=True)
    for c in combos:
        print(f"{c['conv']} w={c['w']}: R5={c['R_5y']} W={c['W']} DD={c['DD_maxyearly']} "
              f"fullDD={c['full_path_dd']} win={c['pool_win']} promising={c['promising_default']} base_hit={c['base_hit']}", flush=True)


if __name__ == "__main__":
    main()
