"""v193 Part B adversarial analysis (runs only after replication.json is saved).

Reads research v193 result for comparison and instruments a line-exact copy
of engine_user.simulate to collect: stop gap fills, per-bar book/sleeve
paths, worst 1m-marked intrabar bars, top-5% sleeve concentration, and a
causal re-derivation of the risk-budget predicate.
Run from the repository root so every data path below stays relative.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

AUD = Path("research/parallel/rounds/parallel-20260906-r2") / "v193_audit"
REP = AUD / "replication.json"
RES = Path("research/parallel/rounds/parallel-20260906-r2/v193/v193_result.json")
OUT = AUD / "analysis.json"
CACHE = Path("artifacts/research/engine_real")
OPENS_FILE = CACHE / "opens_v154.parquet"
BOOKS_FILE = CACHE / "books_v154.parquet"
MEMBERS_FILE = CACHE / "members_v154.parquet"

M_SL = 4.0
M_SLEEVE_SL = 5.0
D_LIMIT = 0.001
WIN_END = 239
GAP = 0.02


def _load_engine_user():
    spec = importlib.util.spec_from_file_location(
        "v193_analysis_engine_user",
        Path("research/parallel/rounds/parallel-20260906-r2/engine_user/engine_user.py"),
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def instrumented_run(eu, P2, opens, prep, X):
    """Line-exact copy of engine_user.simulate with diagnostics (no behavior change)."""
    from copy import deepcopy

    idx, cols = prep["idx"], prep["cols"]
    O, H, L, C = prep["O"], prep["H"], prep["L"], prep["C"]
    sig4, o1, o2, settle = prep["sig4"], prep["o1"], prep["o2"], prep["settle"]
    B = P2.to_numpy()
    na, n = len(cols), len(idx)
    o = opens.reindex(idx)[cols]
    v99, v110 = eu.er.v99, eu.er.v110
    realized = v99.W_BOOKS * (P2.shift(2) * (o / o.shift(1) - 1)).sum(axis=1)
    vol = (realized.rolling(60 * eu.PD, min_periods=20 * eu.PD).std() * np.sqrt(eu.PD * 365)).to_numpy()
    s = np.where(np.isnan(vol), 1.0, np.minimum(0.25 / np.where(np.isnan(vol), 1.0, vol), 2.0))
    live = np.asarray((idx >= v110.START) & (idx < v110.END))
    mins = np.array([eu.MIN_NOTIONAL.get(c, 5.0) for c in cols])
    net = np.zeros(n)
    g = np.ones(n)
    eq = np.ones(n)
    eq_min = np.ones(n)
    w = np.zeros(na)
    entry = np.full(na, np.nan)
    stats = dict(fills=0, unfilled=0, stops=0, tps=0, rungs=0, rung_stops=0, rung_tps=0, liq=0, fees=0.0, funding=0.0)

    book_gap_events = []    # (bar_pos, asset, side, SL, fill, gap_rel_entry)
    sleeve_gap_events = []  # (bar_pos, asset, rung, SL, fill_open, gap_rel_L)
    per_bar = []  # dicts per live bar
    budget_checks = {"candidates": 0, "mismatch": 0}

    for i in range(n):
        if i >= 2:
            j = i - 2
            peak = eq[max(0, j - 90 * eu.PD + 1): j + 1].max()
            g[i] = float(np.clip((0.20 - (1 - eq[j] / peak)) / 0.10, 0.0, 1.0))
        prev_eq = eq[i - 1] if i else 1.0
        if not live[i] or not np.all(np.isfinite(o1[i])) or not np.all(np.isfinite(o2[i])):
            eq[i] = prev_eq
            eq_min[i] = prev_eq
            continue
        tgt = v99.W_BOOKS * s[i] * B[i] * g[i]
        sd = sig4[i] * np.sqrt(6)
        cash = 0.0
        q = w / o1[i]
        start_val = float((q * o1[i]).sum())
        path = np.zeros(240)
        book_path = np.zeros(240)
        sleeve_path = np.zeros(240)
        for a in range(na):
            Oa, Ha, La, Ca = (X_[i, :, a].astype(float) for X_ in (O, H, L, C))
            if not np.isfinite(Oa[0]):
                continue
            qa, ea = q[a], entry[a]
            dw = tgt[a] - w[a]
            fill_min, fill_px = 999, np.nan
            if abs(dw) * prev_eq * eu.ACCOUNT >= mins[a] or (tgt[a] == 0 and w[a] != 0):
                lim = Oa[0] * (1 - D_LIMIT) if dw > 0 else Oa[0] * (1 + D_LIMIT)
                win = La[2:WIN_END] < lim if dw > 0 else Ha[2:WIN_END] > lim
                if win.any():
                    fill_min, fill_px = 2 + int(np.argmax(win)), lim
                    stats["fills"] += 1
                else:
                    stats["unfilled"] += 1
            dq = dw / o1[i][a] if fill_min < 999 else 0.0
            qarr = np.full(240, qa)
            carr = np.zeros(240)
            cur_q, cur_e = qa, ea
            side0 = int(np.sign(cur_q)) if cur_q != 0 else 0

            def levels(qq, ee):
                if qq == 0 or not np.isfinite(ee) or not np.isfinite(sd[a]):
                    return None, None
                if qq > 0:
                    return ee * (1 - M_SL * sd[a]), ee * (1 + 2 * M_SL * sd[a])
                return ee * (1 + M_SL * sd[a]), ee * (1 - 2 * M_SL * sd[a])

            def first_exit(qq, lo_m, hi_m):
                sl, tp = levels(qq, cur_e)
                if sl is None or hi_m <= lo_m:
                    return None
                Ls, Hs = La[lo_m:hi_m], Ha[lo_m:hi_m]
                hs = Ls <= sl if qq > 0 else Hs >= sl
                ht = Hs > tp if qq > 0 else Ls < tp
                hit = hs | ht
                if not hit.any():
                    return None
                k = int(np.argmax(hit))
                mm = lo_m + k
                if hs[k]:
                    px = min(sl, Oa[mm]) if qq > 0 else max(sl, Oa[mm])
                    return mm, px, eu.TAKER, "stops"
                return mm, tp, eu.MAKER, "tps"

            def apply_exit(ev):
                nonlocal cur_q, cur_e
                mm, px, fee, kind = ev
                # gap record for book stops: filled below the stop (long) / above (short)
                if kind == "stops":
                    sl, _ = levels(cur_q, cur_e)
                    if cur_q > 0 and px < sl - 1e-12:
                        book_gap_events.append((i, cols[a], "long", float(sl), float(px),
                                                float((sl - px) / cur_e), float(abs(cur_q) * (sl - px))))
                    elif cur_q < 0 and px > sl + 1e-12:
                        book_gap_events.append((i, cols[a], "short", float(sl), float(px),
                                                float((px - sl) / cur_e), float(abs(cur_q) * (px - sl))))
                carr[mm:] += cur_q * px - abs(cur_q) * px * fee
                stats["fees"] += abs(cur_q) * px * fee
                stats[kind] += 1
                qarr[mm:] = 0.0
                cur_q, cur_e = 0.0, np.nan

            seg_end = fill_min if fill_min < 240 else 240
            ev = first_exit(cur_q, 0, seg_end)
            if ev is not None:
                apply_exit(ev)
            elif fill_min < 240:
                new_q = cur_q + dq
                if cur_q == 0 or np.sign(new_q) != np.sign(cur_q):
                    cur_e = fill_px if new_q != 0 else np.nan
                elif abs(new_q) > abs(cur_q):
                    cur_e = (abs(cur_q) * cur_e + abs(dq) * fill_px) / abs(new_q)
                carr[fill_min:] -= dq * fill_px + abs(dq) * fill_px * eu.MAKER
                stats["fees"] += abs(dq) * fill_px * eu.MAKER
                qarr[fill_min:] = new_q
                cur_q = new_q
                ev = first_exit(cur_q, fill_min, 240)
                if ev is not None:
                    apply_exit(ev)
            val_path = carr + qarr * Ca - qa * o1[i][a]
            pnl_cash = carr[-1]
            end_val = pnl_cash + cur_q * o2[i][a]
            fund = eu.FUND_LONG * max(cur_q, 0.0) * o2[i][a] if settle[i] else 0.0
            stats["funding"] += fund
            path += val_path
            book_path += val_path
            cash += end_val - qa * o1[i][a] - fund
            q[a], entry[a] = cur_q, cur_e
        sleeve_pnl = 0.0
        # keep rung diagnostics for causal budget re-check
        rung_diag = []
        if True:
            rn = s[i] * g[i] * eu.SIZE / len(eu.RUNGS) / eu.S_REF
            fills = []
            for r, k in enumerate(eu.RUNGS):
                for a in range(na):
                    if not np.isfinite(sig4[i][a]):
                        continue
                    lv = o1[i][a] * (1 - k * sig4[i][a])
                    hit = L[i, 16:239, a].astype(float) < lv
                    if hit.any():
                        fills.append((16 + int(np.argmax(hit)), r, a, lv))
            fills.sort()
            taken = []
            for f, r, a, lv in fills:
                budget_checks["candidates"] += 1
                # engine predicate (full-scan exits of prior taken)
                risk_open = sum(rn * (M_SLEEVE_SL * sig4[i][t[2]] + GAP) for t in taken if t[4] > f)
                engine_take = risk_open + rn * (M_SLEEVE_SL * sig4[i][a] + GAP) <= X + 1e-12
                # causal re-derivation: prior rung still open iff no SL/TP hit in (f_prev+1 .. f)
                causal_open_risk = 0.0
                for (pf, pr, pa, plv, px, pret, psl, ptp) in rung_diag:
                    if pf > f:
                        continue
                    lo, hi = pf + 1, min(f + 1, 240)
                    if lo >= hi:
                        still_open = True
                    else:
                        La_, Ha_ = L[i, lo:hi, pa].astype(float), H[i, lo:hi, pa].astype(float)
                        hs_ = La_ <= psl
                        ht_ = Ha_ > ptp
                        still_open = not bool((hs_ | ht_).any())
                    engine_open = px > f
                    if still_open != engine_open:
                        budget_checks["mismatch"] += 1
                    if still_open:
                        causal_open_risk += rn * (M_SLEEVE_SL * sig4[i][pa] + GAP)
                if not engine_take:
                    continue
                Ha, La, Ca, Oa = (X_[i, :, a].astype(float) for X_ in (H, L, C, O))
                tp = lv * (1 + sig4[i][a])
                sl = lv * (1 - M_SLEEVE_SL * sig4[i][a])
                x, ret = 240, None
                if f + 1 < 240:
                    hs = La[f + 1:240] <= sl
                    ht = Ha[f + 1:240] > tp
                    hit = hs | ht
                    if hit.any():
                        k = int(np.argmax(hit))
                        x = f + 1 + k
                        if hs[k]:
                            ret = min(sl, Oa[x]) / lv - 1 - eu.MAKER - eu.TAKER
                            stats["rung_stops"] += 1
                            if Oa[x] < sl - 1e-12:
                                sleeve_gap_events.append((i, cols[a], r, float(sl), float(Oa[x]),
                                                          float((sl - Oa[x]) / lv),
                                                          float(rn * (sl - Oa[x]) / lv)))
                        else:
                            ret = tp / lv - 1 - 2 * eu.MAKER
                            stats["rung_tps"] += 1
                if ret is None:
                    ret = o2[i][a] / lv - 1 - eu.MAKER - eu.TAKER - (eu.FUND_LONG if settle[i] else 0.0)
                taken.append((f, r, a, lv, x, ret))
                rung_diag.append((f, r, a, lv, x, ret, sl, tp))
                sleeve_pnl += rn * ret
                seg = np.zeros(240)
                end = min(x, 240)
                seg[f:end] = Ca[f:end] / lv - 1
                if x < 240:
                    seg[x:] = ret
                path += rn * seg
                sleeve_path += rn * seg
            stats["rungs"] += len(taken)
        pnl = cash + sleeve_pnl
        eq[i] = prev_eq * (1 + pnl)
        eq_min[i] = prev_eq * (1 + min(0.0, float(path.min())))
        gross = float(np.abs(q * o2[i]).sum()) + (eu.N_MAX if True else 0.0)
        if 1 + float(path.min()) < eu.MMR * max(gross, 1e-9):
            stats["liq"] += 1
        end_eq_rel = 1 + pnl
        w = np.where(np.isfinite(o2[i]), q * o2[i] / end_eq_rel, 0.0)
        net[i] = pnl
        if live[i]:
            m = int(np.argmin(path))
            per_bar.append(dict(pos=i, date=str(idx[i]), net=float(pnl), book=float(cash),
                                sleeve=float(sleeve_pnl), path_min=float(path.min()),
                                path_min_minute=m, book_at_min=float(book_path[m]),
                                sleeve_at_min=float(sleeve_path[m]),
                                book_min=float(book_path.min()), sleeve_min=float(sleeve_path.min())))
    return dict(net=net, eq=eq, eq_min=eq_min, g=g, stats=stats, per_bar=per_bar,
                book_gaps=book_gap_events, sleeve_gaps=sleeve_gap_events,
                budget=deepcopy(budget_checks), live=int(np.asarray(
                    (idx >= v110.START) & (idx < v110.END)).sum()))


def main():
    assert REP.exists(), "save replication.json (Part A) first"
    eu = _load_engine_user()
    mem = pd.read_parquet(MEMBERS_FILE)
    books_cache = pd.read_parquet(BOOKS_FILE)
    opens = pd.read_parquet(OPENS_FILE).sort_index()
    cols = list(books_cache.columns)
    A_m, B_m = mem["A"], mem["B"]
    idx_union = A_m.index.union(B_m.index).sort_values()
    P2 = ((A_m.reindex(idx_union).reindex(columns=cols).fillna(0.0)
           + B_m.reindex(idx_union).reindex(columns=cols).fillna(0.0)) / 2).sort_index()
    prep = eu.prepare(P2, opens)

    # driver pipeline equivalence: v151 from books154 index + prepare(books154)
    books154, opens154 = eu.er.v154_books()
    mem2 = pd.read_parquet(eu.er.CACHE / "members_v154.parquet")
    A2 = mem2.xs("A", axis=1, level=0).reindex(books154.index).fillna(0.0)[cols]
    B2 = mem2.xs("B", axis=1, level=0).reindex(books154.index).fillna(0.0)[cols]
    v151 = (A2 + B2) / 2
    pipe_diff = float((v151 - P2).abs().max().max())
    prep2 = eu.prepare(books154, opens)
    arrays_same = all(
        bool(np.array_equal(np.asarray(prep[k], dtype=float), np.asarray(prep2[k], dtype=float), equal_nan=True))
        for k in ("O", "H", "L", "C", "sig4", "o1", "o2"))
    prep_same = bool(arrays_same and list(prep["idx"]) == list(prep2["idx"])
                     and bool((prep["settle"] == prep2["settle"]).all()))
    print(f"pipeline P2 vs driver v151 max abs diff = {pipe_diff}; prep identical = {prep_same}", flush=True)
    assert pipe_diff == 0.0 and prep_same

    res = json.loads(RES.read_text())
    out_runs = {}
    for X, key in ((0.03, "P2_X030"), (0.08, "P2_X080")):
        print(f"instrumented run X={X} ...", flush=True)
        r = instrumented_run(eu, P2, opens, prep, X)
        rep_row = json.loads(REP.read_text())["rows"][key]
        # exactness check vs blind replication
        assert r["stats"]["rungs"] == rep_row["stats"]["rungs"], (X, r["stats"]["rungs"])
        assert r["stats"]["rung_stops"] == rep_row["stats"]["rung_stops"], X
        assert r["stats"]["rung_tps"] == rep_row["stats"]["rung_tps"], X
        assert r["stats"]["fills"] == rep_row["stats"]["fills"], X
        out_runs[str(X)] = r
        print(f"X={X} rungs={r['stats']['rungs']} stops={r['stats']['rung_stops']} "
              f"tps={r['stats']['rung_tps']} liq={r['stats']['liq']} "
              f"book_gaps={len(r['book_gaps'])} sleeve_gaps={len(r['sleeve_gaps'])} "
              f"budget_candidates={r['budget']['candidates']} mismatch={r['budget']['mismatch']}", flush=True)

    # (3) worst intrabar bars for X=0.08
    bars = out_runs["0.08"]["per_bar"]
    worst = sorted(bars, key=lambda b: b["path_min"])[:10]
    # (4) top-5% sleeve concentration: rank live bars by X=0.08 sleeve pnl
    b08 = {b["pos"]: b for b in out_runs["0.08"]["per_bar"]}
    b03 = {b["pos"]: b for b in out_runs["0.03"]["per_bar"]}
    common = sorted(set(b08) & set(b03))
    n = len(common)
    k = max(1, int(round(0.05 * n)))
    ranked = sorted(common, key=lambda p: b08[p]["sleeve"], reverse=True)[:k]
    tot_diff = float(sum(b08[p]["net"] - b03[p]["net"] for p in common))
    top_diff = float(sum(b08[p]["net"] - b03[p]["net"] for p in ranked))
    sleeve_tot_diff = float(sum(b08[p]["sleeve"] - b03[p]["sleeve"] for p in common))
    sleeve_top_diff = float(sum(b08[p]["sleeve"] - b03[p]["sleeve"] for p in ranked))
    tot_sleeve08 = float(sum(b08[p]["sleeve"] for p in common))
    top_sleeve08 = float(sum(b08[p]["sleeve"] for p in ranked))

    def gap_stats(events):
        # events carry gap relative loss ([-2]) and equity drag ([-1])
        gaps = [e[-2] for e in events]
        drags = [e[-1] for e in events]
        return dict(n=len(events), total_gap_rel=float(sum(gaps)) if gaps else 0.0,
                    max_gap_rel=float(max(gaps)) if gaps else 0.0,
                    mean_gap_rel=float(sum(gaps) / len(gaps)) if gaps else 0.0,
                    total_equity_drag=float(sum(drags)) if drags else 0.0,
                    max_equity_drag=float(max(drags)) if drags else 0.0)

    analysis = {
        "pipeline_check": {"p2_vs_v151_max_abs_diff": pipe_diff, "prep_identical": prep_same},
        "budget_causality": {x: out_runs[x]["budget"] for x in ("0.03", "0.08")},
        "book_gaps": {x: gap_stats(out_runs[x]["book_gaps"]) for x in ("0.03", "0.08")},
        "sleeve_gaps": {x: gap_stats(out_runs[x]["sleeve_gaps"]) for x in ("0.03", "0.08")},
        "worst_intrabar_X008": [
            dict(date=w["date"], path_min=round(w["path_min"], 5), minute=w["path_min_minute"],
                 book_at_min=round(w["book_at_min"], 5), sleeve_at_min=round(w["sleeve_at_min"], 5),
                 net=round(w["net"], 5)) for w in worst],
        "concentration": dict(live_bars=n, top5_n=k,
                              total_net_diff=round(tot_diff, 5), top_net_diff=round(top_diff, 5),
                              share_net_diff=round(top_diff / tot_diff, 4) if tot_diff else None,
                              sleeve_total_diff=round(sleeve_tot_diff, 5),
                              sleeve_top_diff=round(sleeve_top_diff, 5),
                              share_sleeve_diff=round(sleeve_top_diff / sleeve_tot_diff, 4) if sleeve_tot_diff else None,
                              total_sleeve08=round(tot_sleeve08, 5), top_sleeve08=round(top_sleeve08, 5),
                              share_sleeve08=round(top_sleeve08 / tot_sleeve08, 4) if tot_sleeve08 else None),
        "stats_check": {x: out_runs[x]["stats"] for x in ("0.03", "0.08")},
    }
    OUT.write_text(json.dumps(analysis, indent=1, default=str))
    print(f"saved {OUT}", flush=True)
    print(json.dumps(analysis, indent=1, default=str)[:3000], flush=True)


if __name__ == "__main__":
    main()
