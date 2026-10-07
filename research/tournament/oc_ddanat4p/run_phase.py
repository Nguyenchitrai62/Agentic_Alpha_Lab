"""oc_ddanat4p run_phase: EXACT oc_ddanat17 replica for phase s=SHIFT.

Same v411 worker settings (dips x1.7 inv-rule, budget 0.26*1.7, bear-book
filter, R2 agents r2_table_sN, v216 grid trade, win_start=5) with
events/attrib/path_out/bars collected (ONE process). Only `shift` differs
(argv[1], 1..3). Adds fixed-window attribution of the 2024-01-03 crash window
(mixed-clock bar-ends in (2024-01-03 11:00, 2024-01-03 16:00]) alongside the
standard five-episode decomposition (replica validation).

Usage: .venv/Scripts/python.exe research/tournament/oc_ddanat4p/run_phase.py 1
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
TABLES = RD / "v376" / "tables_hidden"
RUNGS = (2.5, 3.0, 3.5, 4.0)


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    sys.path.insert(0, str(ROOT / "research/diagnostics/phase_offset_full"))
    import phase_offset_full as pof

    v388 = _load("v388_for_dd4p", RD / "v388" / "v388_bot_stop_distance.py")
    Y1 = v388.Y1
    shift = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    tag = f"dd4p_s{shift}"
    pod = pof._load(f"pod_{tag}", ROOT / "research/diagnostics/phase_offset_dips/phase_offset_dips.py")
    hist = pof._load(f"hist_{tag}", ROOT / "backend/history_tm.py")
    v221 = pof._load(f"v221_{tag}", pof.RD / "v221/v221_grid_hysteresis.py")
    fw = pof._load(f"fw_{tag}", ROOT / "scripts/forward_v205.py")
    eu, v216 = v221.eu, v221.v216

    cap = {}
    eu.summarize = lambda idx, net, eq, eq_min, g, stats, eq_max=None: cap.update(
        idx=idx, eq=eq.copy(), eq_min=eq_min.copy(),
        eq_max=(eq if eq_max is None else eq_max).copy(), stats=dict(stats)) or {}

    shift = int(sys.argv[1]) if len(sys.argv) > 1 else 0
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

    events, attrib, path_out, bars = [], [], {}, []
    cache_raw = HERE / f"raw_s{shift}.pkl"
    if cache_raw.exists() and "--rerun" not in sys.argv:
        raw = pickle.loads(cache_raw.read_bytes())
        events, attrib = raw["events"], raw["attrib"]
        path_out = dict(t=raw["t"], eq=raw["eq"], eq_min=raw["eq_min"], eq_max=raw["eq_max"])
        cap.update(idx=raw["t"], eq=raw["eq"], eq_min=raw["eq_min"], eq_max=raw["eq_max"], stats=raw["stats"])
        print(f"reused raw_s{shift}.pkl", flush=True)
    else:
        eu.simulate(books_bear, opens, prep, trade=trade, win_start=5,
                    events=events, attrib=attrib, path_out=path_out, bars=bars, **kw)
        cache_raw.write_bytes(pickle.dumps(dict(
            events=events, attrib=[(str(t), np.asarray(b).tolist(), float(s)) for t, b, s in attrib],
            t=path_out["t"], eq=path_out["eq"], eq_min=path_out["eq_min"], eq_max=path_out["eq_max"],
            stats=cap["stats"])))
    attrib = [(pd.Timestamp(t), np.asarray(b, float), float(s)) for t, b, s in attrib]
    print("simulate done", flush=True)
    print("stats", {k: (round(v, 4) if isinstance(v, float) else v) for k, v in cap["stats"].items()}, flush=True)

    # --- equity on live window (bar-end times idx+8h, as v411) ---
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

    # --- five largest non-overlapping peak-to-trough episodes (4h close) ---
    peak = np.maximum.accumulate(e_live)
    dd = 1 - e_live / peak
    cand = []
    for q in range(len(e_live)):
        p = int(np.argmax(e_live[: q + 1]))
        if e_live[q] < e_live[p]:
            cand.append((float(1 - e_live[q] / e_live[p]), p, q))
    cand.sort(key=lambda t: -t[0])
    chosen = []
    used = np.zeros(len(e_live), bool)
    for depth, p, q in cand:
        if not used[p: q + 1].any():
            chosen.append((depth, p, q))
            used[p: q + 1] = True
        if len(chosen) == 5:
            break
    chosen.sort(key=lambda t: t[1])
    print("episodes", [(round(d, 4), str(t_end[p]), str(t_end[q])) for d, p, q in chosen], flush=True)

    # --- attribution arrays ---
    at = np.array([a[0] for a in attrib])  # bar-start times
    abook = np.stack([np.asarray(a[1], float) for a in attrib])  # (n, na) fractions of bar-start eq
    asleep = np.array([float(a[2]) for a in attrib])
    bmat = books_bear[cols].reindex(pidx).to_numpy()  # aligned to path_out rows
    # map attrib time (bar-start = pidx + 4h) -> row position in pidx
    pos_of = {pd.Timestamp(t).value: k for k, t in enumerate(pidx)}
    a_pos = np.array([pos_of.get((pd.Timestamp(t) - pd.Timedelta(hours=4)).value, -1) for t in at])
    assert (a_pos >= 0).all(), (a_pos < 0).sum()

    ev = pd.DataFrame(events)
    ev["t"] = pd.to_datetime(ev["t"], utc=True)
    # pair rung fills -> exits (FIFO per symbol; engine appends fill then exit adjacently)
    from collections import deque
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
                                  ret=float(r.ret), loss=loss, fill_price=float(f0.price),
                                  exit_price=float(r.price)))
    # n of the B1 rule at each fill (same formula as corr_size, m = f-1)
    sym2a = {s: a for a, s in enumerate(cols)}
    for d in rungs:
        ft = pd.Timestamp(d["fill_t"])
        # holding-bar start = fill_t floored to minute minus f; recover via bar-start lookup:
        ts = t_start
        j = int(np.searchsorted(ts.asi8, ft.value, side="right")) - 1
        if 0 <= j < len(pidx):
            k = int(a_pos[j]) if j < len(a_pos) else None
        # a_pos[j] is position of attrib bar j in pidx; attrib/live share the full idx so a_pos[j]==j_global
        # recompute directly: row = index of bar-start t_start[j] in pidx
        if k is not None:
            a = sym2a[d["symbol"]]
            f = int(round((ft - ts[j]).total_seconds() / 60))
            m = f - 1
            n = 0
            if 0 <= m < 240:
                for b in range(len(cols)):
                    if b == a or not (np.isfinite(O[k, 0, b]) and np.isfinite(C[k, m, b]) and np.isfinite(sg[k][b])):
                        continue
                    n += float(C[k, m, b]) <= float(O[k, 0, b]) * (1 - 2.5 * float(sg[k][b]))
            d["n"] = int(n)
            d["fill_min"] = int(f)
            d["bar_start"] = str(ts[j])
        else:
            d["n"] = None
            d["fill_min"] = None
            d["bar_start"] = None
    rungs.sort(key=lambda d: d["loss"])
    worst20 = rungs[:20]

    # --- per-episode decomposition ---
    episodes = []
    for depth, p, q in chosen:
        # attrib bars j with (peak_end, trough_end] on the attrib clock: t_start in (t_end[p]-4h, t_end[q]-4h]
        lo, hi = t_end[p] - pd.Timedelta(hours=4), t_end[q] - pd.Timedelta(hours=4)
        m = (t_start > lo) & (t_start <= hi)
        jj = np.where(m)[0]
        bl = bs = dp = 0.0
        per_coin = {}
        for j in jj:
            k = int(a_pos[j])
            for a, s in enumerate(cols):
                v = float(abook[j, a])
                tgt = float(bmat[k, a])
                per_coin.setdefault(s, dict(book=0.0, dip=0.0))
                per_coin[s]["book"] += v
                if tgt > 0:
                    bl += v
                elif tgt < 0:
                    bs += v
        ds = float(asleep[jj].sum()) if len(jj) else 0.0
        # dip per coin from exit events in (peak_end, trough_end]
        for d in rungs:
            te = pd.Timestamp(d["exit_t"])
            if te > t_end[p] and te <= t_end[q]:
                per_coin.setdefault(d["symbol"], dict(book=0.0, dip=0.0))
                per_coin[d["symbol"]]["dip"] += d["loss"]
        tot_attr = bl + bs + ds
        tot_eq = float(e_live[q] / e_live[p] - 1)
        # 1m-marked depth of the same window
        pk1 = float(e_live[p])
        wmn = float(np.minimum(e_live[p: q + 1], em_live[p: q + 1]).min())
        dd1m = float(1 - wmn / pk1)
        # exit-kind split of dip loss in window
        kinds = {}
        for d in rungs:
            te = pd.Timestamp(d["exit_t"])
            if te > t_end[p] and te <= t_end[q]:
                kinds[d["exit"]] = kinds.get(d["exit"], 0.0) + d["loss"]
        episodes.append(dict(
            peak_end=str(t_end[p]), trough_end=str(t_end[q]),
            dd_4h_pct=round(100 * depth, 2), dd_1m_pct=round(100 * dd1m, 2),
            eq_change_pct=round(100 * tot_eq, 2),
            book_long=round(bl * 100, 3), book_short=round(bs * 100, 3),
            dip=round(ds * 100, 3), attrib_sum=round(tot_attr * 100, 3),
            dip_exit_kinds={k: round(v * 100, 3) for k, v in kinds.items()},
            per_coin={s: dict(book=round(v["book"] * 100, 3), dip=round(v["dip"] * 100, 3)) for s, v in per_coin.items()},
            n_bars=int(len(jj))))
    # --- checks (vs v411 same-shift reference) ---
    cache = RD / "v411" / "v411_runs.pkl"
    check = {}
    if cache.exists():
        runs = pickle.loads(cache.read_bytes())
        ref = runs[shift]["R2B1D17BF"]
        check[f"v411_s{shift}_eq_end"] = ref["eq"][-1]
        check["rerun_eq_end"] = float(e_live[-1])
        check["rel_diff"] = float(e_live[-1] / ref["eq"][-1] - 1)
    check["stats"] = {k: (round(v, 4) if isinstance(v, float) else v) for k, v in cap["stats"].items()}
    check["n_events"] = int(len(ev))
    check["n_rungs"] = int(len(rungs))
    check["n_attrib"] = int(len(attrib))

    # --- fixed crash-window attribution: mixed-clock bar-ends in (WIN_LO, WIN_HI] ---
    # (post-hoc extension logged in REPORT: the pre-registered 1-hour mark window
    # contains no crash-bar close; this uses the close-trough extension).
    WIN_LO = pd.Timestamp("2024-01-03 11:00", tz="UTC")
    WIN_HI = pd.Timestamp("2024-01-03 16:00", tz="UTC")
    wmask = (t_end > WIN_LO) & (t_end <= WIN_HI)
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
        if te > WIN_LO and te <= WIN_HI:
            wcoin.setdefault(d["symbol"], dict(book=0.0, dip=0.0))
            wcoin[d["symbol"]]["dip"] += d["loss"]
    wkinds = {}
    for d in rungs:
        te = pd.Timestamp(d["exit_t"])
        if te > WIN_LO and te <= WIN_HI:
            wkinds[d["exit"]] = wkinds.get(d["exit"], 0.0) + d["loss"]
    weq0 = float(e_live[wmask][0] / e_live[wmask][0]) if len(wj) else 1.0
    crash = dict(window=[str(WIN_LO), str(WIN_HI)],
                 bars=[str(t) for t in t_end[wmask]],
                 n_bars=int(len(wj)),
                 book_long=round(wbl * 100, 3), book_short=round(wbs * 100, 3),
                 dip=round(wds * 100, 3),
                 attrib_sum=round((wbl + wbs + wds) * 100, 3),
                 dip_exit_kinds={k: round(v * 100, 3) for k, v in wkinds.items()},
                 per_coin={s: dict(book=round(v["book"] * 100, 3), dip=round(v["dip"] * 100, 3)) for s, v in wcoin.items()})

    out = dict(
        variant="R2B1D17BF", phase=shift, live=[str(live0), str(live1)],
        episodes=episodes, worst20=[
            dict(exit_t=d["exit_t"], fill_t=d["fill_t"], symbol=d["symbol"], n=d["n"],
                 depth=d["depth"], exit=d["exit"], loss_pct=round(100 * d["loss"], 4),
                 ret=round(d["ret"], 5), weight=round(d["weight"], 5)) for d in worst20],
        worst20_note="loss_pct = weight*ret in percent of bar-start equity; n = B1 inv-rule count; depth = rung k sigma",
        crash_window=crash,
        checks=check)
    (HERE / f"attrib_s{shift}.json").write_text(json.dumps(out, indent=1))
    ev.to_parquet(HERE / f"events_s{shift}.parquet")
    pd.DataFrame(rungs).to_parquet(HERE / f"rungs_s{shift}.parquet")
    print(f"wrote attrib_s{shift}.json", flush=True)
    for e in episodes:
        tot = e["book_long"] + e["book_short"] + e["dip"]
        print(e["peak_end"], "->", e["trough_end"], "DD", e["dd_4h_pct"],
              "bookL", e["book_long"], "bookS", e["book_short"], "dip", e["dip"], "sum", round(tot, 3), flush=True)


if __name__ == "__main__":
    main()
