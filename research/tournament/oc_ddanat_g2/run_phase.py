"""oc_ddanat_g2 run_phase: EXACT oc_kpi_g2 replica for phase s=SHIFT + attrib.

Same v421 R2B1D17BFG2 worker settings (dips x1.7 inv-rule, budget 0.26*1.7,
bear-book filter, R2 agents r2_table_sN, v216 grid trade, win_start=5,
sleeve_gross_cap 2.0) with events/attrib/path_out/bars collected (ONE process).
Only `shift` differs (argv[1], 0..3). Attributes the four reset-chained episode
windows from mix_episodes.json (same convention as oc_ddanat4p run_phase.py).

Usage: .venv/Scripts/python.exe research/tournament/oc_ddanat_g2/run_phase.py 0
Writes attrib_s{shift}.json (+ checks vs v421_runs.pkl and oc_kpi_g2 events).
"""
from __future__ import annotations

import importlib.util
import json
import pickle
import sys
from collections import deque
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
RD = ROOT / "research/parallel/rounds/parallel-20260906-r2"
TABLES = RD / "v376" / "tables_hidden"
KPI = ROOT / "research/tournament/oc_kpi_g2"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    sys.path.insert(0, str(ROOT / "research/diagnostics/phase_offset_full"))
    import phase_offset_full as pof

    v388 = _load("v388_for_ddg2", RD / "v388" / "v388_bot_stop_distance.py")
    Y1 = v388.Y1
    shift = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    tag = f"ddg2_s{shift}"
    pod = pof._load(f"pod_{tag}", ROOT / "research/diagnostics/phase_offset_dips/phase_offset_dips.py")
    hist = pof._load(f"hist_{tag}", ROOT / "backend/history_tm.py")
    v221 = pof._load(f"v221_{tag}", pof.RD / "v221/v221_grid_hysteresis.py")
    fw = pof._load(f"fw_{tag}", ROOT / "scripts/forward_v205.py")
    eu, v216 = v221.eu, v221.v216

    cap = {}
    eu.summarize = lambda idx, net, eq, eq_min, g, stats, eq_max=None: cap.update(
        idx=idx, eq=eq.copy(), eq_min=eq_min.copy(),
        eq_max=(eq if eq_max is None else eq_max).copy(), stats=dict(stats)) or {}

    sh = pd.Timedelta(hours=shift)
    live0, live1 = pof.DEV0 + sh, Y1 + sh
    eu.v110.START, eu.v110.END = live0, live1
    books154, _opens_std = eu.er.v154_books()
    M = pod.minutes()
    opens, prep = pof.prep_idx(M, books154.index + sh, shift, list(books154.columns))
    del M
    idx, cols = prep["idx"], list(prep["cols"])
    std_books = fw.research_books_d2(eu).reindex(books154.index).fillna(0.0)[cols]
    books = std_books.reindex(idx, method="ffill").fillna(0.0)
    btc = _opens_std["BTCUSDT"].reindex(books154.index)
    bear = (btc < btc.rolling(1200, min_periods=600).mean()).to_numpy()
    sb = std_books.copy()
    sb.loc[bear] = sb.loc[bear].where(sb.loc[bear] <= 0, sb.loc[bear] * 0.5)
    books_bear = sb.reindex(idx, method="ffill").fillna(0.0)

    hist.R2_TABLE = TABLES / f"r2_table_s{shift}.parquet"
    kw, trade = pof.pipe_setup("v321", hist, v221, v216, idx, cols, True)
    O, C, sg = prep["O"], prep["C"], prep["sig4"]
    base_size, rule, kd = kw["sleeve_fill_size"], "inv", 1.7

    def corr_size(i, a, r, f, base_size=base_size, rule=rule, kd=kd):
        m = f - 1
        n = 0
        for b in range(len(cols)):
            if b == a or not (np.isfinite(O[i, 0, b]) and np.isfinite(C[i, m, b]) and np.isfinite(sg[i][b])):
                continue
            n += float(C[i, m, b]) <= float(O[i, 0, b]) * (1 - 2.5 * float(sg[i][b]))
        mult = 1.0 / (1 + n) if rule == "inv" else (0.5 if n >= 2 else 1.0)
        return mult * kd * base_size(i, a, r, f)

    kw["sleeve_fill_size"] = corr_size
    kw["risk_mult"] = lambda i, e: 1.0
    kw["sleeve_risk_budget"] = kw.get("sleeve_risk_budget", 0.26) * 1.0 * kd
    kw["sleeve_gross_cap"] = 2.0

    events, attrib, path_out, bars = [], [], {}, []
    eu.simulate(books_bear, opens, prep, trade=trade, win_start=5,
                events=events, attrib=attrib, path_out=path_out, bars=bars, **kw)
    print("simulate done", flush=True)
    print("stats", {k: (round(v, 4) if isinstance(v, float) else v) for k, v in cap["stats"].items()}, flush=True)
    attrib = [(pd.Timestamp(t), np.asarray(b, float), float(s)) for t, b, s in attrib]

    # --- equity on live window (bar-end times idx+8h, as v411/v421) ---
    pidx = path_out["t"]
    eq = np.asarray(path_out["eq"], float)
    eq_min = np.asarray(path_out["eq_min"], float)
    lv = np.asarray((pidx >= live0) & (pidx < live1))
    first = int(np.argmax(lv))
    base = float(eq[first - 1]) if first > 0 else 1.0
    li = np.where(lv)[0]
    e_live = eq[li] / base
    em_live = eq_min[li] / base
    t_end = pidx[li] + pd.Timedelta(hours=8)  # holding-bar end
    t_start = pidx[li] + pd.Timedelta(hours=4)  # attrib clock

    # --- checks vs v421 pkl + oc_kpi_g2 events ---
    runs = pickle.loads((RD / "v421" / "v421_runs.pkl").read_bytes())
    ref = runs[shift]["R2B1D17BFG2"]
    check = dict(v421_eq_end=float(ref["eq"][-1]), rerun_eq_end=float(e_live[-1]),
                 rel_diff=float(e_live[-1] / ref["eq"][-1] - 1))
    check["stats"] = {k: (round(v, 4) if isinstance(v, float) else v) for k, v in cap["stats"].items()}
    ev = pd.DataFrame(events)
    ev["t"] = pd.to_datetime(ev["t"], utc=True)
    check["n_events"] = int(len(ev))
    kpi_ev = pd.read_parquet(KPI / f"events_s{shift}.parquet")
    check["kpi_n_events"] = int(len(kpi_ev))
    check["kpi_n_rung_fill"] = int((kpi_ev["kind"] == "rung_fill").sum())
    check["rerun_n_rung_fill"] = int((ev["kind"] == "rung_fill").sum())
    check["n_attrib"] = int(len(attrib))
    check["n_bars"] = int(len(bars))

    # --- attribution arrays ---
    at = np.array([a[0] for a in attrib])
    abook = np.stack([np.asarray(a[1], float) for a in attrib])
    asleep = np.array([float(a[2]) for a in attrib])
    bmat = books_bear[cols].reindex(pidx).to_numpy()
    pos_of = {pd.Timestamp(t).value: k for k, t in enumerate(pidx)}
    a_pos = np.array([pos_of.get((pd.Timestamp(t) - pd.Timedelta(hours=4)).value, -1) for t in at])
    assert (a_pos >= 0).all(), (a_pos < 0).sum()

    # pair rung fills -> exits (FIFO per symbol)
    pend = {}
    rungs = []
    for r in ev.itertuples():
        if r.kind == "rung_fill":
            pend.setdefault(r.symbol, deque()).append(r)
        elif r.kind in ("rung_sl", "rung_tp", "rung_timeout"):
            q0 = pend.get(r.symbol)
            if q0:
                f0 = q0.popleft()
                loss = float(r.weight) * float(r.ret)
                rungs.append(dict(fill_t=str(f0.t), exit_t=str(r.t), symbol=r.symbol,
                                  depth=float(f0.rung), exit=r.kind, weight=float(r.weight),
                                  ret=float(r.ret), loss=loss))
    rungs.sort(key=lambda d: d["loss"])
    check["n_rungs"] = int(len(rungs))
    kpi_rungs = int((kpi_ev["kind"] == "rung_fill").sum())
    check["kpi_n_rungs"] = kpi_rungs

    def attribute_window(lo, hi):
        # attrib bars j with bar-end in (lo, hi]: t_end in (lo, hi]
        wmask = (t_end > lo) & (t_end <= hi)
        wj = np.where(wmask)[0]
        wbl = wbs = 0.0
        wcoin = {}
        for j in wj:
            k = int(a_pos[j])
            for a, s in enumerate(cols):
                v = float(abook[j, a])
                tgt = float(bmat[k, a])
                wcoin.setdefault(s, dict(book=0.0, dip=0.0))
                wcoin[s]["book"] += v
                if tgt > 0:
                    wbl += v
                elif tgt < 0:
                    wbs += v
        wds = float(asleep[wj].sum()) if len(wj) else 0.0
        for d in rungs:
            te = pd.Timestamp(d["exit_t"])
            if te > lo and te <= hi:
                wcoin.setdefault(d["symbol"], dict(book=0.0, dip=0.0))
                wcoin[d["symbol"]]["dip"] += d["loss"]
        wkinds = {}
        for d in rungs:
            te = pd.Timestamp(d["exit_t"])
            if te > lo and te <= hi:
                wkinds[d["exit"]] = wkinds.get(d["exit"], 0.0) + d["loss"]
        # eq move over window on this phase's own live series
        if len(wj):
            p0 = int(wj[0])
            q0 = int(wj[-1])
            base0 = float(e_live[p0 - 1]) if p0 > 0 else base / base
            # window start equity = e_live just before first bar; use e_live[p0-1]
            eq0 = float(e_live[p0 - 1]) if p0 > 0 else float(e_live[p0] / (1 + 0))
            eq1 = float(e_live[q0])
            eq_chg = float(eq1 / e_live[p0 - 1] - 1) if p0 > 0 else float(eq1 - 1)
        else:
            eq_chg = 0.0
        return dict(bars=[str(t) for t in t_end[wmask]], n_bars=int(len(wj)),
                    book_long=round(wbl * 100, 3), book_short=round(wbs * 100, 3),
                    dip=round(wds * 100, 3),
                    attrib_sum=round((wbl + wbs + wds) * 100, 3),
                    eq_change_pct=round(eq_chg * 100, 3),
                    dip_exit_kinds={k: round(v * 100, 3) for k, v in wkinds.items()},
                    per_coin={s: dict(book=round(v["book"] * 100, 3),
                                       dip=round(v["dip"] * 100, 3)) for s, v in wcoin.items()})

    mix = json.loads((HERE / "mix_episodes.json").read_text())
    episodes = []
    for ep in mix["reset_episodes"]:
        lo = pd.Timestamp(ep["peak"], tz="UTC")
        hi = pd.Timestamp(ep["trough"], tz="UTC")
        a = attribute_window(lo, hi)
        a["window"] = [str(lo), str(hi)]
        a["mixed_dd_4h"] = ep["dd_4h_pct"]
        a["mixed_dd_1m"] = ep["dd_1m_pct"]
        episodes.append(a)

    out = dict(variant="R2B1D17BFG2", phase=shift, live=[str(live0), str(live1)],
               episodes=episodes,
               worst20=[dict(exit_t=d["exit_t"], fill_t=d["fill_t"], symbol=d["symbol"],
                             exit=d["exit"], loss_pct=round(100 * d["loss"], 4),
                             ret=round(d["ret"], 5), weight=round(d["weight"], 5))
                        for d in rungs[:20]],
               checks=check)
    (HERE / f"attrib_s{shift}.json").write_text(json.dumps(out, indent=1))
    print(f"wrote attrib_s{shift}.json rel_diff {check['rel_diff']:.3e} "
          f"events {check['n_events']}/{check['kpi_n_events']}", flush=True)
    for e in episodes:
        tot = e["book_long"] + e["book_short"] + e["dip"]
        print(e["window"][0], "->", e["window"][1], "bookL", e["book_long"],
              "bookS", e["book_short"], "dip", e["dip"], "sum", round(tot, 3),
              "eq_chg", e["eq_change_pct"], flush=True)
    if abs(check["rel_diff"]) > 1e-9:
        raise SystemExit(f"shift {shift}: equity mismatch rel_diff {check['rel_diff']:.3e}")


if __name__ == "__main__":
    main()
