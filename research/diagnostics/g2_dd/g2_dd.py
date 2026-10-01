"""Study G2 drawdown anatomy (dev years ONLY: 2021-09-24 .. 2025-09-24).

Reproduces v301 G2 (CB books + J1 size-S1/TP agents, dip budget 0.26) with the
leader engine, then answers (dev-only):
  Q1  every >7% drawdown episode on the 4h-close path (peak/trough/depth/days,
      book vs sleeve sums, per-coin splits, worst 1d/3d, BTC move, rung counts,
      top-3-bar loss shares).
  Q2  dip-loss clustering: rung_sl grouped by 4h bar; bars with >=3 stopped
      rungs of distinct coins (systemic flush); share of stop losses they carry
      and sleeve net on other bars; same grouping for rung_tp wins.
  Q3  book concentration: gross/net exposure and #long/#short in each episode
      vs outside; pre-episode exposure; daily-PnL distribution when |net| is in
      its top decile.
  Q4  three mechanical counterfactuals (same agents, causal data only):
      (a) governor x0.5 when BTC 4h realised vol (std of last 42 4h returns) is
          above its trailing 540-bar 80th percentile (risk_mult hook);
      (b) dip sleeve skips a rung once >=3 rungs of other coins in the same bar
          already stopped with exit minute < fill minute (engine copy under this
          folder, sleeve_flush_skip=3);
      (c) sleeve risk budget 0.26 -> 0.13 while lagged equity (2-bar lag, as the
          governor) is >6% below its trailing 540-bar (90-day) peak (engine
          copy, sleeve_budget_dd).
      Each reports dev4, worst dev year, dev DD, dev book win rate.

Definitions were fixed BEFORE looking at results (see META). Any post-hoc
change is appended to META["post_hoc_changes"].
Never touches dates >= 2025-09-24: every series/event is sliced to dev before
any statistic or print.

  .venv/Scripts/python.exe research/diagnostics/g2_dd/g2_dd.py
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
ROOT = Path(__file__).resolve().parents[3]
RD = ROOT / "research/parallel/rounds/parallel-20260906-r2"
OUT = HERE / "g2_dd.json"

DEV_START = pd.Timestamp("2021-09-24", tz="UTC")
HIDDEN = pd.Timestamp("2025-09-24", tz="UTC")

META = {
    "dev_window": ["2021-09-24", "2025-09-24"],
    "reference": "v301 G2_b26 must give monthly_dev4 6.527 and dev DD 17.33",
    "episode_def": "4h-close equity (path_out eq, indexed by bar close T) sliced "
                   "to dev; running peak/cummax; dd=1-eq/peak; scan for dd>0.07; "
                   "extend while dd>0; trough=argmax dd in segment; "
                   "peak=argmax eq up to trough; window=(peak,trough] for sums.",
    "book_sleeve_def": "attrib (t, per-asset book array, sleeve) as fractions of "
                       "bar-start equity; sums over window bars (t>peak & t<=trough).",
    "sleeve_coin_def": "per-coin sleeve = sum(ret*weight) of rung_tp/sl/timeout "
                       "exits with peak<t_exit<=trough.",
    "top3_def": "book: 3 worst single-bar total-book attrib sums in the window, "
                "share of book_sum; rungs: rung exits grouped by exit 4h bar, 3 "
                "worst bars' share of sleeve_sum; combined: 3 worst total-bar "
                "(book+sleeve attrib) share of total loss. Shares reported only "
                "when the denominator is negative.",
    "flush_def": "rung_sl grouped by floor-4h bar of exit time; systemic flush = "
                 "bar with >=3 stopped rungs of >=3 distinct coins.",
    "exposure_def": "bars[i].target per coin (fraction of equity, governor "
                    "included); gross=sum|tgt|, net=sum(tgt); top decile = 90th "
                    "percentile of |net| over dev bars; daily eod net = last bar.",
    "a_def": "BTC 4h vol = rolling std(42) of BTC 4h-open returns on the decision "
             "grid; threshold = 80th percentile of the past 540 vols excluding "
             "the current bar; risk_mult 0.5/1.0 (governor; scales book targets "
             "and sleeve sizes).",
    "b_def": "skip a rung fill at minute f when >=3 rungs of other coins "
             "(symbol != current) in the same holding bar already stopped with "
             "exit minute < f (causal; engine copy).",
    "c_def": "per-bar sleeve budget 0.26, cut to 0.13 when eq[i-2] is >6% below "
              "its trailing 540-bar peak (2-bar lag like the governor; engine copy).",
    "definitions_fixed_before_results": True,
    "post_hoc_changes": [],
}


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _r(x):
    if x is None or (isinstance(x, float) and (not np.isfinite(x))):
        return None
    if isinstance(x, (np.floating,)):
        return round(float(x), 4)
    if isinstance(x, (np.integer,)):
        return int(x)
    return x


def main():
    v221 = _load("v221", RD / "v221/v221_grid_hysteresis.py")
    eu, v216, v204 = v221.eu, v221.v216, v221.v204
    v213 = v216.v213
    v286 = _load("v286", RD / "v286/v286_coinbase_member_upgrade.py")
    v301 = _load("v301", RD / "v301/v301_return_first_budget.py")
    v293 = v301.v297.v293
    eg = _load("engine_g2dd", HERE / "engine_g2dd.py")

    books154, opens = eu.er.v154_books()
    cols, idx = list(books154.columns), books154.index
    C = eu.er.CACHE
    m = {k: pd.read_parquet(C / f).reindex(idx).fillna(0.0)[cols] for k, f in (
        ("A", "member_A_O1_orders.parquet"), ("Aq", "member_Aq_O1_orders.parquet"),
        ("B", "member_B_tv.parquet"), ("Bq", "member_Bq_tv.parquet"))}
    m["D"] = pd.read_parquet(C / "members_v154.parquet").xs("D", axis=1, level=0).reindex(idx).fillna(0.0)[cols]
    m["Dq"] = pd.read_parquet(C / "members_quarterly_D.parquet").reindex(idx).fillna(0.0)[cols]
    cb = 0.8 * (0.5 * (m["A"] + m["B"]) / 2 + 0.5 * (m["Aq"] + m["Bq"]) / 2) + 0.2 * (m["D"] + m["Dq"]) / 2
    prep = eu.prepare(books154, opens)
    trade = dict(v216.GRID, policy=v216.grid_policy(v221.B_ABS, v221.B_REL))
    KW = dict(v221.KW, **dict(v293.C4R, sleeve_risk_budget=0.26))

    print("training J1 hooks (v301 build_hooks) ...", flush=True)
    size_s1, _size_s5, tp = v301.build_hooks(eu, idx, cols)

    # ---- base G2 run (leader engine) ----
    att, path, ev, bars = [], {}, [], []
    r = eu.simulate(cb, opens, prep, trade=trade, win_start=5, events=ev, attrib=att,
                    path_out=path, bars=bars, sleeve_fill_size=size_s1, sleeve_tp=tp, **KW)
    dev_dd = v286.dev_dd(r)
    print("base monthly_dev4", r["monthly_dev4"], "devDD", dev_dd, flush=True)
    assert abs(r["monthly_dev4"] - 6.527) < 0.002, r["monthly_dev4"]
    assert abs(dev_dd - 17.33) < 0.02, dev_dd

    # ---- slice to dev BEFORE any use ----
    T = pd.DatetimeIndex(path["t"]) + pd.Timedelta(hours=4)
    eq = pd.Series(np.asarray(path["eq"], float), index=T)
    eq = eq[(eq.index >= DEV_START) & (eq.index < HIDDEN)].sort_index()
    eq = eq[~eq.index.duplicated(keep="last")]
    att_t = pd.DatetimeIndex([a[0] for a in att])
    book_arr = np.array([np.asarray(a[1], float) for a in att])
    slv_arr = np.array([float(a[2]) for a in att])
    amask = (att_t >= DEV_START) & (att_t < HIDDEN)
    att_t, book_arr, slv_arr = att_t[amask], book_arr[amask], slv_arr[amask]
    order = np.argsort(att_t)
    att_t, book_arr, slv_arr = att_t[order], book_arr[order], slv_arr[order]
    evd = [e for e in ev if e["t"] >= DEV_START and e["t"] < HIDDEN]
    barsd = [b for b in bars if b["t"] >= DEV_START and b["t"] < HIDDEN]
    btc_o = opens["BTCUSDT"].reindex(eq.index, method="ffill")
    ts_dev = v213.trade_stats(evd)
    dev_win = ts_dev["dev"].get("win_rate")
    dev_yearly = [(y["anchor"][:4], y["net_pct"], y["dd_1m_pct"]) for y in r["yearly"][:4]]
    print("dev years (net, dd1m):", dev_yearly, "dev book win:", dev_win, flush=True)
    assert all(pd.Timestamp(a, tz="UTC") < HIDDEN for a, _, _ in dev_yearly for _ in [0])

    # ================= Q1: episodes >7% on 4h close =================
    peak = eq.cummax()
    dd = 1 - eq / peak
    ddv, eqv = dd.to_numpy(), eq.to_numpy()
    eidx = eq.index
    episodes = []
    i = 0
    n = len(ddv)
    while i < n:
        if ddv[i] > 0.07:
            j = i
            while j < n and ddv[j] > 0:
                j += 1
            seg = slice(i, j)
            tr = i + int(np.argmax(ddv[seg]))
            pk = int(np.argmax(eqv[:tr + 1]))
            episodes.append((pk, tr, j))
            i = j
        else:
            i += 1
    q1 = []
    in_ep = np.zeros(n, bool)
    META["post_hoc_changes"].append(
        "after the first run: attribute peak->recovery as well as peak->trough. "
        "Reason: the 2024-08-05 systemic flush (-12.6% sleeve exits in 2 bars, "
        "4h-close dd 10.6% on 2024-08-05) and the 2024-09-20 8.6% local trough sit "
        "in ep9's recovery leg (dd never reset to 0 between 2024-07-16 and Oct), so "
        "peak->trough-only windows orphan the largest flush. Added recovery_date, "
        "peak->recovery book/sleeve sums, and recovery-leg max dd per episode. "
        "Episode peak/trough/depth/days definitions unchanged.")
    for k, (pk, tr, j) in enumerate(episodes):
        t_pk, t_tr = eidx[pk], eidx[tr]
        t_rec = eidx[j - 1] if j < n else eidx[n - 1]
        in_ep[pk:tr + 1] = True
        win = (att_t > t_pk) & (att_t <= t_tr)
        win_rec = (att_t > t_pk) & (att_t <= t_rec)
        bsum = float(book_arr[win].sum())
        ssum = float(slv_arr[win].sum())
        bsum_rec = float(book_arr[win_rec].sum())
        ssum_rec = float(slv_arr[win_rec].sum())
        # recovery-leg max dd (local peak reset at the trough)
        rseg = slice(tr, j)
        rpeak = np.maximum.accumulate(eqv[rseg])
        rdd = 1 - eqv[rseg] / rpeak
        rtr = tr + int(np.argmax(rdd))
        rec_leg_max_dd = round(float(rdd.max()) * 100, 2)
        rec_leg_max_dd_date = str(eidx[rtr])
        book_coin = {c: round(float(book_arr[win][:, ci].sum() * 100), 2) for ci, c in enumerate(cols)}
        rex = [e for e in evd if e["kind"] in ("rung_tp", "rung_sl", "rung_timeout")
               and e["t"] > t_pk and e["t"] <= t_tr]
        slv_coin, fills, stops = {}, 0, 0
        for e in evd:
            if e["t"] > t_pk and e["t"] <= t_tr:
                if e["kind"] == "rung_fill":
                    fills += 1
                elif e["kind"] == "rung_sl":
                    stops += 1
        for e in rex:
            slv_coin[e["symbol"]] = slv_coin.get(e["symbol"], 0.0) + float(e["ret"]) * float(e["weight"])
        slv_coin = {s: round(v * 100, 2) for s, v in slv_coin.items()}
        sub = eq[(eq.index >= t_pk) & (eq.index <= t_tr)]
        dly = sub.resample("1D").last().pct_change()
        worst_1d = float(dly.min()) if len(dly.dropna()) else None
        d3 = sub.resample("1D").last().pct_change(3)
        worst_3d = float(d3.min()) if len(d3.dropna()) else None
        btc_move = float(btc_o[t_tr] / btc_o[t_pk] - 1) if btc_o[t_pk] else None
        # top-3 shares
        per_bar_book = book_arr[win].sum(axis=1)
        per_bar_tot = book_arr[win].sum(axis=1) + slv_arr[win]
        b3 = np.sort(per_bar_book)[:3].sum() if win.sum() >= 3 else per_bar_book.sum()
        t3 = np.sort(per_bar_tot)[:3].sum() if win.sum() >= 3 else per_bar_tot.sum()
        exit_bar = {}
        for e in rex:
            k2 = pd.Timestamp(e["t"]).floor("4h")
            exit_bar[k2] = exit_bar.get(k2, 0.0) + float(e["ret"]) * float(e["weight"])
        r3 = sum(sorted(exit_bar.values())[:3]) if len(exit_bar) >= 3 else sum(exit_bar.values())
        tot = bsum + ssum
        rec = {
            "id": k, "peak": str(t_pk), "trough": str(t_tr), "recovery": str(t_rec),
            "depth_pct": round(float(ddv[tr]) * 100, 2),
            "days": round((t_tr - t_pk).total_seconds() / 86400, 1),
            "bars": int(tr - pk),
            "book_sum_pct": round(bsum * 100, 2), "sleeve_sum_pct": round(ssum * 100, 2),
            "total_pct": round(tot * 100, 2),
            "book_sum_peak_to_recovery_pct": round(bsum_rec * 100, 2),
            "sleeve_sum_peak_to_recovery_pct": round(ssum_rec * 100, 2),
            "recovery_leg_max_dd_pct": rec_leg_max_dd,
            "recovery_leg_max_dd_date": rec_leg_max_dd_date,
            "book_by_coin_pct": book_coin, "sleeve_by_coin_pct": slv_coin,
            "worst_day_pct": round(worst_1d * 100, 2) if worst_1d is not None else None,
            "worst_3d_pct": round(worst_3d * 100, 2) if worst_3d is not None else None,
            "btc_move_pct": round(btc_move * 100, 2) if btc_move is not None else None,
            "rungs_filled": fills, "rungs_stopped": stops,
            "worst3_book_bar_share": round(float(b3 / bsum), 3) if bsum < 0 else None,
            "worst3_rung_bar_share": round(float(r3 / ssum), 3) if ssum < 0 and ssum != 0 else None,
            "worst3_total_bar_share": round(float(t3 / tot), 3) if tot < 0 else None,
        }
        q1.append(rec)
        print(f"ep{k} {rec['peak'][:10]}->{rec['trough'][:10]} depth {rec['depth_pct']} "
              f"book {rec['book_sum_pct']} sleeve {rec['sleeve_sum_pct']} btc {rec['btc_move_pct']} "
              f"fills {fills} stops {stops}", flush=True)
    print("episodes>7%:", len(q1), flush=True)

    # ================= Q2: dip-loss clustering =================
    sl = [e for e in evd if e["kind"] == "rung_sl"]
    tp_e = [e for e in evd if e["kind"] == "rung_tp"]
    allx = [e for e in evd if e["kind"] in ("rung_tp", "rung_sl", "rung_timeout")]

    def bar_groups(events):
        g = {}
        for e in events:
            k2 = pd.Timestamp(e["t"]).floor("4h")
            d = g.setdefault(k2, {"n": 0, "syms": set(), "pnl": 0.0})
            d["n"] += 1
            d["syms"].add(e["symbol"])
            d["pnl"] += float(e["ret"]) * float(e["weight"])
        return g

    gsl, gtp = bar_groups(sl), bar_groups(tp_e)
    flush = {k2: d for k2, d in gsl.items() if d["n"] >= 3 and len(d["syms"]) >= 3}
    tot_sl = -sum(float(e["ret"]) * float(e["weight"]) for e in sl)
    flush_sl = -sum(d["pnl"] for d in flush.values())
    other_net = sum(float(e["ret"]) * float(e["weight"]) for e in allx
                    if pd.Timestamp(e["t"]).floor("4h") not in flush)
    flush_net = sum(float(e["ret"]) * float(e["weight"]) for e in allx
                    if pd.Timestamp(e["t"]).floor("4h") in flush)
    tot_tp_win = sum(max(0.0, float(e["ret"]) * float(e["weight"])) for e in tp_e)
    tpc = {k2: d for k2, d in gtp.items() if d["n"] >= 3 and len(d["syms"]) >= 3}
    tpc_win = sum(max(0.0, d["pnl"]) for d in tpc.values())
    tp_in_flush = sum(max(0.0, float(e["ret"]) * float(e["weight"])) for e in tp_e
                       if pd.Timestamp(e["t"]).floor("4h") in flush)
    q2 = {
        "n_rung_sl": len(sl), "n_rung_tp": len(tp_e),
        "flush_bars": [{"bar": str(k2), "stops": d["n"], "coins": sorted(d["syms"]),
                        "pnl_pct": round(d["pnl"] * 100, 3)} for k2, d in sorted(flush.items())],
        "n_flush_bars": len(flush),
        "total_stop_loss_pct": round(tot_sl * 100, 3),
        "flush_stop_loss_pct": round(flush_sl * 100, 3),
        "flush_share_of_stop_loss": round(flush_sl / tot_sl, 3) if tot_sl else None,
        "sleeve_net_other_bars_pct": round(other_net * 100, 3),
        "sleeve_net_flush_bars_pct": round(flush_net * 100, 3),
        "tp_cluster_bars": [{"bar": str(k2), "tps": d["n"], "coins": sorted(d["syms"]),
                             "pnl_pct": round(d["pnl"] * 100, 3)} for k2, d in sorted(tpc.items())],
        "n_tp_cluster_bars": len(tpc),
        "total_tp_win_pct": round(tot_tp_win * 100, 3),
        "tp_cluster_share_of_tp_win": round(tpc_win / tot_tp_win, 3) if tot_tp_win else None,
        "tp_win_inside_sl_flush_bars_pct": round(tp_in_flush * 100, 3),
    }
    print("flush bars:", len(flush), "share of stop loss:", q2["flush_share_of_stop_loss"],
          "other-bar net %:", q2["sleeve_net_other_bars_pct"], flush=True)

    # ================= Q3: book concentration =================
    tgt = np.array([b["target"] for b in barsd])
    bt = pd.DatetimeIndex([b["t"] for b in barsd])
    gross = np.abs(tgt).sum(axis=1)
    net = tgt.sum(axis=1)
    nlong = (tgt > 1e-12).sum(axis=1)
    nshort = (tgt < -1e-12).sum(axis=1)
    bar_in_ep = np.zeros(len(bt), bool)
    for e in q1:
        bar_in_ep |= (bt > pd.Timestamp(e["peak"])) & (bt <= pd.Timestamp(e["trough"]))

    def _m(x):
        return round(float(np.mean(x)), 4) if len(x) else None

    q3 = {
        "outside": {"bars": int((~bar_in_ep).sum()), "mean_gross": _m(gross[~bar_in_ep]),
                    "mean_net": _m(net[~bar_in_ep]), "mean_abs_net": _m(np.abs(net[~bar_in_ep])),
                    "mean_nlong": _m(nlong[~bar_in_ep]), "mean_nshort": _m(nshort[~bar_in_ep])},
        "episodes": [],
    }
    for e in q1:
        msk = (bt > pd.Timestamp(e["peak"])) & (bt <= pd.Timestamp(e["trough"]))
        pre = (bt > pd.Timestamp(e["peak"]) - pd.Timedelta(days=5)) & (bt <= pd.Timestamp(e["peak"]))
        q3["episodes"].append({
            "id": e["id"], "bars": int(msk.sum()),
            "mean_gross": _m(gross[msk]), "max_gross": round(float(gross[msk].max()), 4) if msk.any() else None,
            "mean_net": _m(net[msk]), "max_abs_net": round(float(np.abs(net[msk]).max()), 4) if msk.any() else None,
            "mean_nlong": _m(nlong[msk]), "mean_nshort": _m(nshort[msk]),
            "pre5d_mean_abs_net": _m(np.abs(net[pre])), "pre5d_max_abs_net": round(float(np.abs(net[pre]).max()), 4) if pre.any() else None,
        })
    thr = float(np.quantile(np.abs(net), 0.9))
    eod = pd.Series(net, index=bt).resample("1D").last()
    edly = eq.resample("1D").last().pct_change()
    sel = eod[np.abs(eod) >= thr].index
    spd = edly.reindex(sel).dropna().to_numpy() * 100
    alld = edly.dropna().to_numpy() * 100
    q3["top_decile"] = {
        "abs_net_threshold": round(thr, 4), "n_days": int(len(spd)),
        "mean_daily_pct": round(float(spd.mean()), 3) if len(spd) else None,
        "median_daily_pct": round(float(np.median(spd)), 3) if len(spd) else None,
        "win_rate": round(float((spd > 0).mean()), 3) if len(spd) else None,
        "worst_day_pct": round(float(spd.min()), 2) if len(spd) else None,
        "best_day_pct": round(float(spd.max()), 2) if len(spd) else None,
        "dev_all_days": {"n": int(len(alld)), "mean_daily_pct": round(float(alld.mean()), 3) if len(alld) else None,
                         "win_rate": round(float((alld > 0).mean()), 3) if len(alld) else None},
    }
    print("top-decile |net| thr:", round(thr, 4), "days:", len(spd), flush=True)

    # ================= Q4: counterfactuals =================
    btc_idx = opens["BTCUSDT"].reindex(idx).ffill()
    ret4 = btc_idx.pct_change()
    vol42 = ret4.rolling(42).std()
    thr42 = vol42.shift(1).rolling(540, min_periods=180).quantile(0.8)
    hivol = (vol42 > thr42).fillna(False).to_numpy()

    def risk_mult_a(i, eq_hist):
        return 0.5 if hivol[i] else 1.0

    def run_counterfactual(engine, label, **extra):
        evc = []
        rc = engine.simulate(cb, opens, prep, trade=trade, win_start=5, events=evc,
                             sleeve_fill_size=size_s1, sleeve_tp=tp, **KW, **extra)
        # keep the engine's full result but use ONLY dev years below
        dev = {k: rc[k] for k in ("monthly_dev4",)}
        dev["worst_dev_month_pct"] = round(v204.worst_month(rc), 3)
        dev["dev_dd"] = v286.dev_dd(rc)
        dev["dev_years"] = [(y["anchor"][:4], y["net_pct"], y["dd_1m_pct"]) for y in rc["yearly"][:4]]
        tsc = v213.trade_stats([e for e in evc if e["t"] < HIDDEN])
        dev["dev_book_win_rate"] = tsc["dev"].get("win_rate")
        dev["dev_book_trades"] = tsc["dev"].get("trades")
        for k in ("flush_skipped", "dd_budget_bars"):
            if k in rc.get("stats", {}):
                dev[k] = rc["stats"][k]
        assert all(pd.Timestamp(a, tz="UTC") < HIDDEN for a, _, _ in dev["dev_years"])
        print(label, dev, flush=True)
        return dev

    # copy-engine fidelity (defaults off must reproduce the base)
    evf = []
    rf = eg.simulate(cb, opens, prep, trade=trade, win_start=5, events=evf,
                     sleeve_fill_size=size_s1, sleeve_tp=tp, **KW)
    print("copy-engine fidelity dev4:", rf["monthly_dev4"], "devDD:", v286.dev_dd(rf), flush=True)
    assert abs(rf["monthly_dev4"] - r["monthly_dev4"]) < 1e-9
    assert abs(v286.dev_dd(rf) - dev_dd) < 1e-9

    q4 = {}
    q4["a_vol_target"] = run_counterfactual(eu, "A", risk_mult=risk_mult_a)
    q4["b_flush_skip"] = run_counterfactual(eg, "B", sleeve_flush_skip=3)
    q4["c_dd_budget"] = run_counterfactual(
        eg, "C", sleeve_budget_dd=dict(dd=0.06, low=0.13, lookback=540))

    base = {"monthly_dev4": r["monthly_dev4"],
            "worst_dev_month_pct": round(v204.worst_month(r), 3),
            "dev_dd": dev_dd, "dev_book_win_rate": dev_win,
            "dev_years": dev_yearly}
    ranking = []
    for key, label in (("a_vol_target", "a_vol_x0.5"), ("b_flush_skip", "b_flush_skip3"),
                       ("c_dd_budget", "c_budget_0.13")):
        d = q4[key]
        dd_red = round(base["dev_dd"] - d["dev_dd"], 2)
        dev4_loss = round(base["monthly_dev4"] - d["monthly_dev4"], 3)
        ratio = None
        if dev4_loss > 0:
            ratio = round(dd_red / dev4_loss, 2)
        elif dd_red > 0:
            ratio = "free (no dev4 loss)"
        ranking.append({"rule": label, "dd_reduction": dd_red, "dev4_loss": dev4_loss,
                        "dd_per_dev4": ratio, "dev_dd": d["dev_dd"],
                        "dev4": d["monthly_dev4"], "worst": d["worst_dev_month_pct"],
                        "dev_win": d["dev_book_win_rate"]})
    ranking.sort(key=lambda d: (d["dd_per_dev4"] == "free (no dev4 loss)",
                                d["dd_per_dev4"] if isinstance(d["dd_per_dev4"], (int, float)) else -1e9),
                 reverse=True)

    out = {"meta": META,
           "reference": base,
           "copy_fidelity": {"monthly_dev4": rf["monthly_dev4"], "dev_dd": v286.dev_dd(rf)},
           "q1_episodes": q1, "q2_dip_clusters": q2, "q3_book_concentration": q3,
           "q4_counterfactuals": q4, "ranking": ranking}
    OUT.write_text(json.dumps(out, indent=1, default=str))
    print("wrote", str(OUT), "ranking:", ranking, flush=True)


if __name__ == "__main__":
    main()
