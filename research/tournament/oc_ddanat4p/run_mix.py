"""oc_ddanat4p task (1): mixed-path episodes from v411_runs.pkl (LIGHT, pkl-only).

Replicates v388.hourly/mix + reset_metric.year_reset exactly, confirms gate
numbers, finds the episode behind the 18.33 (year-2 reset path) and the four
deepest non-overlapping full-path continuous-mix episodes, with per-phase DDs.
Writes mix_episodes.json (consumed by results.json later).
"""
from __future__ import annotations

import json
import pickle
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
RD = ROOT / "research/parallel/rounds/parallel-20260906-r2"
PKL = RD / "v411" / "v411_runs.pkl"
STRAT = "R2B1D17BF"
ANCH = ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24", "2025-09-24")
Y1 = pd.Timestamp("2026-09-23", tz="UTC")
G0 = pd.Timestamp("2021-09-24 04:00", tz="UTC")
G1 = Y1 + pd.Timedelta(hours=12)


def hourly(run, g0=G0, g1=G1):
    t = pd.to_datetime(run["t"], utc=True)
    grid = pd.date_range(g0, g1, freq="1h")
    e = pd.Series(np.asarray(run["eq"], float), index=t).reindex(grid, method="ffill").fillna(1.0)
    lo = pd.Series(np.asarray(run["eq_min"], float), index=t - pd.Timedelta(hours=4)).reindex(grid, method="ffill").fillna(1.0)
    return e, np.minimum(lo, e)


def main():
    runs = pickle.loads(PKL.read_bytes())
    assert set(runs) == {0, 1, 2, 3}
    hs = [hourly(runs[s][STRAT]) for s in range(4)]
    es = sum(h[0] for h in hs) / 4
    ms = sum(h[1] for h in hs) / 4

    # --- confirm yearly reset DDs (reset_metric.year_reset logic inlined) ---
    yearly = []
    for y in range(5):
        a0 = pd.Timestamp(ANCH[y], tz="UTC")
        E, MN = [], []
        for s in range(4):
            e1, m1 = hs[s][0], hs[s][1]
            b = float(e1[e1.index <= a0].iloc[-1]) if (e1.index <= a0).any() else 1.0
            seg = (e1.index > a0) & (e1.index <= a0 + pd.Timedelta(days=365))
            E.append(e1[seg] / b)
            MN.append(m1[seg] / b)
        ey, my = sum(E) / 4, sum(MN) / 4
        pk = np.maximum.accumulate(ey.to_numpy())
        dd = round(100 * float(np.max(1 - my.to_numpy() / pk)), 2)
        r = round(100 * float(ey.iloc[-1] ** (1 / 12) - 1), 3)
        yearly.append(dict(R=r, DD=dd))
    ref_years = [(2.831, 12.42), (3.505, 16.23), (4.669, 18.33), (11.27, 8.26), (5.06, 12.81)]
    for y, (rr, dd) in enumerate(ref_years):
        assert abs(yearly[y]["R"] - rr) < 0.05, (y, yearly[y])
        assert abs(yearly[y]["DD"] - dd) < 0.05, (y, yearly[y])

    # --- full-path continuous mix DD (v411 logic) ---
    seg = es.index > pd.Timestamp("2021-09-24", tz="UTC")
    esf, msf = es[seg], ms[seg]
    full_dd = round(100 * float(np.max(1 - msf.to_numpy() / np.maximum.accumulate(esf.to_numpy()))), 2)
    assert abs(full_dd - 16.9) < 0.05, full_dd

    # --- (a) year-2 reset path episode behind the 18.33 ---
    y = 2
    a0 = pd.Timestamp(ANCH[y], tz="UTC")
    E, MN = [], []
    for s in range(4):
        e1, m1 = hs[s][0], hs[s][1]
        b = float(e1[e1.index <= a0].iloc[-1])
        segy = (e1.index > a0) & (e1.index <= a0 + pd.Timedelta(days=365))
        E.append(e1[segy] / b)
        MN.append(m1[segy] / b)
    ey, my = sum(E) / 4, sum(MN) / 4
    pk = np.maximum.accumulate(ey.to_numpy())
    dd_curve = 1 - my.to_numpy() / pk
    q = int(np.argmax(dd_curve))
    dd_max = float(dd_curve[q])
    p = int(np.argmax(ey.to_numpy()[: q + 1]))
    ep1833 = dict(peak=str(ey.index[p]), trough=str(ey.index[q]),
                  dd_4h_pct=round(100 * float(1 - ey.to_numpy()[q] / ey.to_numpy()[p]), 2),
                  dd_1m_pct=round(100 * dd_max, 2))
    # POST-HOC extension (logged): the max-DD pair above is a 1-hour mark
    # artifact (mixed closes barely move 11:00->12:00 because phase bar-ends are
    # staggered; the marked collapse prints first, closes follow). For
    # attribution, extend to the subsequent close trough: argmin of ey closes
    # after p before recovery to ey[p] (or year end).
    tev = ey.to_numpy()
    rec = np.where(tev[p + 1:] >= tev[p])[0]
    end = p + 1 + int(rec[0]) if len(rec) else len(tev) - 1
    qc = p + int(np.argmin(tev[p:end + 1]))
    ep1833["close_trough"] = str(ey.index[qc])
    ep1833["close_dd_pct"] = round(100 * float(1 - tev[qc] / tev[p]), 2)
    # reset-chained full path (yearly-reset segments chained multiplicatively)
    # for the "three next-largest" ranking on the reset basis.
    chained_e, chained_m = [], []
    lvl = 1.0
    for y in range(5):
        a0 = pd.Timestamp(ANCH[y], tz="UTC")
        E2, MN2 = [], []
        for s in range(4):
            e1, m1 = hs[s][0], hs[s][1]
            b = float(e1[e1.index <= a0].iloc[-1]) if (e1.index <= a0).any() else 1.0
            segy = (e1.index > a0) & (e1.index <= a0 + pd.Timedelta(days=365))
            E2.append(e1[segy] / b)
            MN2.append(m1[segy] / b)
        ey2, my2 = sum(E2) / 4, sum(MN2) / 4
        chained_e.append(ey2 * lvl)
        chained_m.append(my2 * lvl)
        lvl = float(chained_e[-1].iloc[-1])
    ce = pd.concat(chained_e)
    cm = pd.concat(chained_m)
    ce_close = ce.to_numpy()
    cand2 = []
    for qq in range(len(ce_close)):
        pp = int(np.argmax(ce_close[: qq + 1]))
        if ce_close[qq] < ce_close[pp]:
            cand2.append((float(1 - ce_close[qq] / ce_close[pp]), pp, qq))
    cand2.sort(key=lambda t: -t[0])
    chosen2, used2 = [], np.zeros(len(ce_close), bool)
    for depth, pp, qq in cand2:
        if not used2[pp: qq + 1].any():
            chosen2.append((depth, pp, qq))
            used2[pp: qq + 1] = True
        if len(chosen2) == 4:
            break
    chosen2.sort(key=lambda t: t[1])
    reset_episodes = []
    for depth, pp, qq in chosen2:
        pkv = float(ce_close[pp])
        wmn = float(np.minimum(ce_close[pp: qq + 1], cm.to_numpy()[pp: qq + 1]).min())
        reset_episodes.append(dict(
            peak=str(ce.index[pp]), trough=str(ce.index[qq]),
            dd_4h_pct=round(100 * depth, 2),
            dd_1m_pct=round(100 * float(1 - wmn / pkv), 2)))

    # --- (b) four deepest non-overlapping full-path episodes (close-based candidates) ---
    e = esf.to_numpy()
    peak_acc = np.maximum.accumulate(e)
    cand = []
    for qq in range(len(e)):
        pp = int(np.argmax(e[: qq + 1]))
        if e[qq] < e[pp]:
            cand.append((float(1 - e[qq] / e[pp]), pp, qq))
    cand.sort(key=lambda t: -t[0])
    chosen = []
    used = np.zeros(len(e), bool)
    for depth, pp, qq in cand:
        if not used[pp: qq + 1].any():
            chosen.append((depth, pp, qq))
            used[pp: qq + 1] = True
        if len(chosen) == 4:
            break
    chosen.sort(key=lambda t: t[1])
    idx = esf.index
    episodes = []
    for depth, pp, qq in chosen:
        pkv = float(e[pp])
        wmn = float(np.minimum(esf.to_numpy()[pp: qq + 1], msf.to_numpy()[pp: qq + 1]).min())
        episodes.append(dict(
            peak=str(idx[pp]), trough=str(idx[qq]),
            dd_4h_pct=round(100 * depth, 2),
            dd_1m_pct=round(100 * float(1 - wmn / pkv), 2)))

    # --- per-phase DDs per episode (phase's own hourly series, same grid hours) ---
    def phase_dd(peak_ts, trough_ts):
        out = []
        for s in range(4):
            e_s, m_s = hs[s][0], hs[s][1]
            window = (e_s.index >= peak_ts) & (e_s.index <= trough_ts)
            base = float(e_s[e_s.index <= peak_ts].iloc[-1])
            wmn = float(np.minimum(e_s[window].to_numpy(), m_s[window].to_numpy()).min())
            tr = str(e_s[window][np.minimum(e_s[window].to_numpy(), m_s[window].to_numpy()).argmin():][:1].index[0]) \
                if window.any() else None
            out.append(dict(phase=s, dd_pct=round(100 * float(1 - wmn / base), 2), trough=str(tr)))
        return out

    ep1833["phases"] = phase_dd(pd.Timestamp(ep1833["peak"]), pd.Timestamp(ep1833["trough"]))
    for ep in episodes:
        ep["phases"] = phase_dd(pd.Timestamp(ep["peak"]), pd.Timestamp(ep["trough"]))

    out = dict(variant=STRAT, yearly=yearly, full_path_dd=full_dd,
               ep_1833=ep1833, full_episodes=episodes,
               reset_episodes=reset_episodes)
    for ep in reset_episodes:
        ep["phases"] = [dict(phase=p["phase"], dd_pct=p["dd_pct"], trough=p["trough"])
                        for p in phase_dd(pd.Timestamp(ep["peak"]), pd.Timestamp(ep["trough"]))]
        print("reset-ep", ep["peak"], "->", ep["trough"], ep["dd_4h_pct"], ep["dd_1m_pct"],
              [p["dd_pct"] for p in ep["phases"]], flush=True)
    (HERE / "mix_episodes.json").write_text(json.dumps(out, indent=1))
    print("yearly", yearly, flush=True)
    print("full DD", full_dd, flush=True)
    print("ep1833", ep1833, flush=True)
    for ep in episodes:
        print("full-ep", ep["peak"], "->", ep["trough"], ep["dd_4h_pct"], ep["dd_1m_pct"],
              [p["dd_pct"] for p in ep["phases"]], flush=True)


if __name__ == "__main__":
    main()
