"""oc_carrycombo: BOT/MANUAL account + locked cash-and-carry sleeve (hourly-marked).

Assignment: docs/opencode/OPENCODE_W_oc_carrycombo.md. Read-only inputs, no
engine reruns, one process, small RAM (hourly grid ~44k rows, 4h/1h data only).

Combined path (task 1): total account = G2 4-phase mix (each phase 1/4 of
capital at each anchor, reset metric) + carry sleeve overlay at f in
{0.25, 0.50} of equity. Carry trades are FROZEN from
research/tournament/oc_cashcarry/results.json (same entry/exit rule, same
fees: spot 0.001/side, futures 0.00055 entry + 0.0002 delivery). The sleeve is
marked HOURLY (Binance spot 1h closes + quarterly 1h closes, causal: value at
grid hour H uses only bars with 1h open_time < H) and sized/rebalanced ONLY at
rolls: each entered pair's legs = f x total combined equity at its entry hour,
held to delivery. Per anchor year metrics use EXACTLY
research/diagnostics/r2_decompose5/reset_metric.py year_reset on per-phase
combined runs; full-path DD uses the v421 formula. f=0 rows must reproduce
v421_result.json (G2) and oc_manualcap results.json (M5_human) to the digit.

  python research/tournament/oc_carrycombo/analyze_carrycombo.py
"""

from __future__ import annotations

import importlib.util
import json
import os
import pickle
import tempfile
import time
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parents[2]

# frozen carry-trade source (entries/exits/fees all defined there)
CC = ROOT / "research/tournament/oc_cashcarry"
V421 = ROOT / "research/parallel/rounds/parallel-20260906-r2/v421/v421_runs.pkl"
V421_RES = ROOT / "research/parallel/rounds/parallel-20260906-r2/v421/v421_result.json"
MANRUNS = ROOT / "research/diagnostics/oc_manualcap/oc_manualcap_runs.pkl"
MANRES = ROOT / "research/diagnostics/oc_manualcap/results.json"
QDIR = ROOT / "data/raw/qbasis_20261003"
SDIR = ROOT / "data/raw/spot_majors_20260925"

COINS = ["BTC", "ETH"]
F_ROWS = [0.25, 0.5]
FEE_ENTRY_PAID = 0.001 + 0.00055  # spot buy + futures short entry (exit fees at delivery)

CACHE = Path(os.environ.get("OCC_SPOT1H_DIR",
             str(Path(tempfile.gettempdir()) / "opencode" / "oc_carrycombo")))


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


v388 = _load("v388_for_combo",
             ROOT / "research/parallel/rounds/parallel-20260906-r2/v388/v388_bot_stop_distance.py")
cc = _load("oc_cashcarry_mod", CC / "analyze_cashcarry.py")

GRID0 = pd.Timestamp("2021-09-24 04:00", tz="UTC")
G1 = v388.Y1 + pd.Timedelta(hours=12)  # same g1 as reset_metric.year_reset default
ANCH = [pd.Timestamp(a, tz="UTC") for a in v388.ANCH]
YEAR = pd.Timedelta(days=365)


# ---------- spot 1h download (Binance public klines, no keys) ----------
def ensure_spot_1h():
    CACHE.mkdir(parents=True, exist_ok=True)
    out = {}
    ok = True
    for coin in COINS:
        p = CACHE / f"{coin}USDT_spot_1h_202109_202609.parquet"
        if p.exists():
            d = pd.read_parquet(p)
            d["open_time"] = pd.to_datetime(d["open_time"], utc=True)
            out[coin] = d
            continue
        try:
            rows = []
            cur = int(pd.Timestamp("2021-09-01", tz="UTC").value // 10 ** 6)
            end = int(pd.Timestamp("2026-09-24", tz="UTC").value // 10 ** 6)
            sym = f"{coin}USDT"
            while True:
                url = (f"https://api.binance.com/api/v3/klines?symbol={sym}"
                       f"&interval=1h&limit=1000&startTime={cur}")
                for attempt in range(4):
                    try:
                        req = urllib.request.Request(url, headers={"User-Agent": "oc_carrycombo"})
                        raw = urllib.request.urlopen(req, timeout=30).read()
                        break
                    except Exception:
                        if attempt == 3:
                            raise
                        time.sleep(2 * (attempt + 1))
                batch = json.loads(raw)
                if not batch:
                    break
                rows.extend(batch)
                cur = batch[-1][0] + 3600_000
                if batch[-1][0] >= end:
                    break
                time.sleep(0.05)
            d = pd.DataFrame({"open_time": pd.to_datetime([r[0] for r in rows], utc=True, unit="ms"),
                              "close": [float(r[4]) for r in rows]})
            d = d.drop_duplicates("open_time").sort_values("open_time").reset_index(drop=True)
            d.to_parquet(p, index=False)
            out[coin] = d
        except Exception as e:  # offline fallback recorded, never silent
            print(f"spot-1h download failed for {coin}: {type(e).__name__}; fallback ffill-4h")
            out[coin] = None
            ok = False
    return out, ok


# ---------- hourly marks on the grid ----------
def hourly_marks(grid_ns, bars_ns, closes):
    """Last bar close with bar open_time < grid hour (causal). NaN if none."""
    idx = np.searchsorted(bars_ns, grid_ns, side="left") - 1
    out = np.full(len(grid_ns), np.nan)
    ok = idx >= 0
    out[ok] = closes[idx[ok]]
    return out


def main():
    t_start = time.time()
    grid = pd.date_range(GRID0, G1, freq="1h", tz="UTC")
    gn = grid.to_numpy(dtype="datetime64[ns]").astype(np.int64)

    v421runs = pickle.loads(V421.read_bytes())
    manruns = pickle.loads(MANRUNS.read_bytes())
    manruns = {s: {"M5_human": manruns[s]["M5_human"]["run"]} for s in manruns}
    ccres = json.loads((CC / "results.json").read_text())

    # ---- base phase paths (exact v388.hourly per phase) ----
    base = {}
    for label, runs, strat in (("G2", v421runs, "R2B1D17BFG2"), ("MAN", manruns, "M5_human")):
        Es, Ms = [], []
        for s in range(4):
            e1, m1 = v388.hourly(runs[s][strat], GRID0, G1)
            e1 = e1.reindex(grid).ffill().fillna(1.0).to_numpy(dtype=float)
            m1 = m1.reindex(grid).ffill().fillna(1.0).to_numpy(dtype=float)
            Es.append(e1)
            Ms.append(m1)
        base[label] = (np.stack(Es), np.stack(Ms))

    # ---- frozen carry entries, re-derived delivery/settle times ----
    spot4 = {}
    for coin in COINS:
        s = cc.load_spot(coin)
        spot4[coin] = s
    # cross-check: my um entry set must equal results.json entered set
    qmap_all = {c: cc.load_q_1h(c) for c in COINS}
    rederived = []
    for coin in COINS:
        s = spot4[coin]
        expiries = sorted(qmap_all[coin])
        for k, D in enumerate(expiries):
            F = cc.resample_to_spot(qmap_all[coin][D], s)
            if k > 0:
                cand = expiries[k - 1] - pd.Timedelta(days=cc.ROLL_DAYS)
                pos = int(np.searchsorted(
                    s["open_time"].to_numpy(dtype="datetime64[ns]").astype(np.int64),
                    cand.value, side="left"))
            else:
                pos = 0
            sc = s["close"].to_numpy(dtype=float)
            both = np.where(~np.isnan(F))[0]
            both = both[both >= pos]
            if len(both) == 0:
                continue
            ti = int(both[0])
            T_close = s["close_time"].iloc[ti]
            dte = (D - T_close).total_seconds() / 86400.0
            if dte <= 0:
                continue
            basis = float(np.log(float(F[ti]) / float(sc[ti])) * 365.0 / dte)
            if basis >= cc.THRESHOLD:
                # same incomplete rule as oc_cashcarry: D beyond last spot bar -> excluded
                sct = s["close_time"].to_numpy(dtype="datetime64[ns]").astype(np.int64)
                si = int(np.searchsorted(sct, D.value, side="right"))
                if si >= len(s):
                    continue
                rederived.append((coin, str(D.date())))
    frozen = sorted((t["coin"], t["delivery"]) for t in ccres["trades"])
    assert sorted(rederived) == frozen, (
        f"entry re-derivation diverged: {len(rederived)} vs {len(frozen)} frozen")
    print(f"entry cross-check OK: {len(frozen)} entered = oc_cashcarry trades")

    trades = []
    for t in ccres["trades"]:
        coin = t["coin"]
        s = spot4[coin]
        entry_close = pd.to_datetime(t["entry_open"], utc=True) + pd.Timedelta(hours=4)
        D = pd.to_datetime(t["delivery"] + " 08:00", utc=True)
        sct = s["close_time"].to_numpy(dtype="datetime64[ns]").astype(np.int64)
        si = int(np.searchsorted(sct, D.value, side="right"))
        assert si < len(s), t["delivery"]
        settle_close = pd.to_datetime(s["close_time"].iloc[si], utc=True)
        # hand-check frozen settlement value = delivery-bar spot close
        assert abs(float(s["close"].iloc[si]) - t["S_del"]) < 1e-9, t["delivery"]
        trades.append(dict(coin=coin, entry_close=entry_close, settle_close=settle_close,
                           F_entry=t["F_entry"], S_entry=t["S_entry"],
                           ret_alloc=t["ret_alloc"], delivery=t["delivery"]))

    # ---- hourly spot marks (downloaded) + hourly futures marks ----
    spot1h, spot_hourly_ok = ensure_spot_1h()
    S_grid = {}
    for coin in COINS:
        if spot1h[coin] is not None:
            b = spot1h[coin]
            bn = b["open_time"].to_numpy(dtype="datetime64[ns]").astype(np.int64)
            S_grid[coin] = hourly_marks(gn, bn, b["close"].to_numpy(dtype=float))
        else:  # fallback: 4h spot closes forward-filled (recorded in results.json)
            s = spot4[coin]
            sn = s["open_time"].to_numpy(dtype="datetime64[ns]").astype(np.int64)
            S_grid[coin] = hourly_marks(gn, sn, s["close"].to_numpy(dtype=float))
    F_grid = {}
    for tr in trades:
        coin = tr["coin"]
        D = pd.Timestamp(tr["delivery"] + " 08:00", tz="UTC")
        q = qmap_all[coin][D]
        qn = q["open_time"].to_numpy(dtype="datetime64[ns]").astype(np.int64)
        F_grid[(coin, tr["delivery"])] = hourly_marks(gn, qn, q["close"].to_numpy(dtype=float))

    # ---- per-trade hourly mtm (alloc units), ffilled from entry values ----
    n = len(grid)
    for tr in trades:
        i0 = int(np.searchsorted(gn, tr["entry_close"].value, side="right"))
        i1 = int(np.searchsorted(gn, tr["settle_close"].value, side="right"))
        tr["i0"], tr["i1"] = min(i0, n), min(i1, n)
        S = S_grid[tr["coin"]].copy()
        F = F_grid[(tr["coin"], tr["delivery"])].copy()
        lo, hi = tr["i0"], tr["i1"]
        if hi > lo:
            Sw = S[lo:hi]
            Fw = F[lo:hi]
            # causal ffill from entry values (before first hourly mark: entry price)
            mask_s = np.isnan(Sw)
            mask_f = np.isnan(Fw)
            if mask_s.all() or mask_f.all():
                mtm = np.full(hi - lo, -FEE_ENTRY_PAID)
            else:
                Sv = Sw.copy()
                Fv = Fw.copy()
                Sv[mask_s] = tr["S_entry"]
                Fv[mask_f] = tr["F_entry"]
                # forward-fill interior gaps
                Sv = pd.Series(Sv).ffill().to_numpy()
                Fv = pd.Series(Fv).ffill().to_numpy()
                mtm = (Sv / tr["S_entry"] - 1.0) + ((tr["F_entry"] - Fv) / tr["F_entry"]) - FEE_ENTRY_PAID
            m = np.full(n, np.nan)
            m[lo:hi] = mtm
            tr["mtm"] = m
        else:
            tr["mtm"] = np.full(n, np.nan)

    # ---- combined forward pass per (base, f); rebalanced only at rolls ----
    out_rows, full_dd = {}, {}
    for label in ("G2", "MAN"):
        Es, Ms = base[label]
        Etot = Es.mean(axis=0)
        Mtot = Ms.mean(axis=0)
        for f in [0.0] + F_ROWS:
            C = Etot.copy()
            R = np.zeros(n)
            U = np.zeros(n)
            if f > 0:
                active = {}
                settle_at = {}
                n_pregrid_excluded = 0
                for k, tr in enumerate(trades):
                    if tr["i1"] <= 0:
                        # delivered before the study grid starts: pre-window P&L,
                        # excluded like oc_cashcarry's pre_window set (no P&L imputed)
                        n_pregrid_excluded += 1
                        continue
                    if tr["i0"] < n:
                        active.setdefault(max(tr["i0"], 0), []).append(k)
                    if tr["i1"] < n:
                        settle_at.setdefault(tr["i1"], []).append(k)
                    elif tr["i1"] >= n:
                        pass  # open past grid end: never settles in-window
                open_k = {}
                settled = 0.0
                Cseq = Etot.copy()
                for i in range(n):
                    for k in active.get(i, []):
                        open_k[k] = f * Cseq[i - 1] if i > 0 else f * 1.0
                    for k in settle_at.get(i, []):
                        if k in open_k:
                            settled += open_k.pop(k) * trades[k]["ret_alloc"]
                    u = 0.0
                    for k, sc in open_k.items():
                        v = trades[k]["mtm"][i]
                        if np.isfinite(v):
                            u += sc * v
                    R[i] = settled
                    U[i] = u
                    Cseq[i] = Etot[i] + settled + u
                C = Cseq
            Cs = Es + (R + U)[None, :] / 4.0
            Mks = Ms + (R + U)[None, :] / 4.0
            M = Mtot + R + U
            # reset metric, inline (identical arithmetic to
            # research/diagnostics/r2_decompose5/reset_metric.py year_reset,
            # applied directly on the hourly series to avoid a second
            # v388.hourly ffill pass, which would shift eq_min by 4h)
            yy = []
            for y in range(5):
                a0 = ANCH[y]
                a1 = a0 + YEAR
                E4, M4 = [], []
                for s in range(4):
                    le = np.where(gn <= a0.value)[0]
                    b = float(Cs[s][le[-1]]) if len(le) else 1.0
                    seg = (gn > a0.value) & (gn <= a1.value)
                    E4.append(Cs[s][seg] / b)
                    M4.append(Mks[s][seg] / b)
                es = np.mean(E4, axis=0)
                ms = np.mean(M4, axis=0)
                pk = np.maximum.accumulate(es)
                yy.append(dict(R=round(100 * float(es[-1] ** (1 / 12) - 1), 3),
                               DD=round(100 * float(np.max(1 - ms / pk)), 2)))
            geo = 100 * (float(np.prod([1 + v["R"] / 100 for v in yy])) ** (1 / 5) - 1)
            row = dict(R=round(geo, 3), W=min(v["R"] for v in yy),
                       DD=max(v["DD"] for v in yy),
                       losing=sum(v["R"] < 0 for v in yy),
                       years=[(v["R"], v["DD"]) for v in yy])
            out_rows[(label, f)] = row
            seg = grid > pd.Timestamp("2021-09-24", tz="UTC")
            es, ms = C[seg], M[seg]
            dd_mark = round(100 * float(np.max(1 - ms / np.maximum.accumulate(es))), 2)
            dd_close = round(100 * float(np.max(1 - es / np.maximum.accumulate(es))), 2)
            full_dd[(label, f)] = dict(marked=dd_mark, close=dd_close,
                                       full=max(dd_mark, dd_close))

    # ---- validation: f=0 must reproduce the frozen rows to the digit ----
    exp_g2 = json.loads(V421_RES.read_text())["rows"]["R2B1D17BFG2"]
    got_g2 = out_rows[("G2", 0.0)]
    assert got_g2["years"] == [tuple(x) for x in exp_g2["years"]], (got_g2, exp_g2)
    assert got_g2["R"] == exp_g2["R"] and got_g2["DD"] == exp_g2["DD"], (got_g2, exp_g2)
    assert full_dd[("G2", 0.0)]["full"] == exp_g2["full_path_dd"], full_dd[("G2", 0.0)]
    exp_man = json.loads(MANRES.read_text())["rows"]["M5_human"]
    got_man = out_rows[("MAN", 0.0)]
    assert [r for r, _ in got_man["years"]] == exp_man["years_R"], (got_man, exp_man)
    assert [d for _, d in got_man["years"]] == exp_man["years_DD"], (got_man, exp_man)
    assert got_man["R"] == exp_man["R5"] and got_man["DD"] == exp_man["maxDD"], (got_man, exp_man)
    assert full_dd[("MAN", 0.0)]["full"] == exp_man["fullDD"], full_dd[("MAN", 0.0)]
    print("f=0 validation OK: G2 reproduces v421_result, MAN reproduces oc_manualcap")

    # ---- task 2: USDT-margined (um_) vs COIN-M (cm_) basis at same entry bars ----
    cm_files = {c: sorted(QDIR.glob(f"cm_{c}USD_*_1h.parquet")) for c in COINS}
    cm_by_date = {}
    for coin in COINS:
        for p in cm_files[coin]:
            cm_by_date[(coin, cc.parse_expiry(p.name).date().isoformat())] = p
    cm_cmp = []
    for tr in trades:
        key = (tr["coin"], tr["delivery"])
        p = cm_by_date.get(key)
        if p is None:
            cm_cmp.append(dict(coin=tr["coin"], delivery=tr["delivery"], cm_available=False))
            continue
        q = pd.read_parquet(p, columns=["open_time", "close"])
        q["open_time"] = pd.to_datetime(q["open_time"], utc=True)
        Fcm = cc.resample_to_spot(q, spot4[tr["coin"]])
        s = spot4[tr["coin"]]
        ti = int(np.searchsorted(s["close_time"].to_numpy(dtype="datetime64[ns]").astype(np.int64),
                                tr["entry_close"].value, side="left") - 1)
        F_val = float(Fcm[ti])
        dte = (pd.Timestamp(tr["delivery"] + " 08:00", tz="UTC") - tr["entry_close"]).total_seconds() / 86400.0
        cm_basis = float(np.log(F_val / tr["S_entry"]) * 365.0 / dte)
        um_basis = float(np.log(tr["F_entry"] / tr["S_entry"]) * 365.0 / dte)
        cm_cmp.append(dict(coin=tr["coin"], delivery=tr["delivery"], cm_available=True,
                           um_basis=round(um_basis, 6), cm_basis=round(cm_basis, 6),
                           diff_bps=round((cm_basis - um_basis) * 10000, 1),
                           um_enter=True, cm_enter=bool(cm_basis >= cc.THRESHOLD)))
    # skipped um contracts: same-bar cm basis (do decisions agree?)
    entered_keys = set((t["coin"], t["delivery"]) for t in trades)
    skip_cmp = []
    for coin in COINS:
        s = spot4[coin]
        sc = s["close"].to_numpy(dtype=float)
        for D in sorted(qmap_all[coin]):
            dk = (coin, str(D.date()))
            if dk in entered_keys or dk not in cm_by_date:
                continue
            F = cc.resample_to_spot(qmap_all[coin][D], s)
            if len(s) == 0:
                continue
            prev = sorted(qmap_all[coin])[sorted(qmap_all[coin]).index(D) - 1] \
                if sorted(qmap_all[coin]).index(D) > 0 else None
            if prev is None:
                pos = 0
            else:
                cand = prev - pd.Timedelta(days=cc.ROLL_DAYS)
                pos = int(np.searchsorted(
                    s["open_time"].to_numpy(dtype="datetime64[ns]").astype(np.int64),
                    cand.value, side="left"))
            both = np.where(~np.isnan(F))[0]
            both = both[both >= pos]
            if len(both) == 0:
                continue
            ti = int(both[0])
            T_close = s["close_time"].iloc[ti]
            dte = (D - T_close).total_seconds() / 86400.0
            if dte <= 0 or not np.isfinite(F[ti]):
                continue
            um_basis = float(np.log(float(F[ti]) / float(sc[ti])) * 365.0 / dte)
            q = pd.read_parquet(cm_by_date[dk], columns=["open_time", "close"])
            q["open_time"] = pd.to_datetime(q["open_time"], utc=True)
            Fcm = cc.resample_to_spot(q, s)
            if not np.isfinite(Fcm[ti]):
                continue
            cm_basis = float(np.log(float(Fcm[ti]) / float(sc[ti])) * 365.0 / dte)
            skip_cmp.append(dict(coin=coin, delivery=str(D.date()),
                                 um_basis=round(um_basis, 6), cm_basis=round(cm_basis, 6),
                                 um_enter=bool(um_basis >= cc.THRESHOLD),
                                 cm_enter=bool(cm_basis >= cc.THRESHOLD)))

    pregrid = sum(1 for tr in trades if tr["i1"] <= 0)
    spanning = sum(1 for tr in trades if tr["i0"] <= 0 < tr["i1"])
    assert pregrid == 4, pregrid  # BTC/ETH 2021-03 + 2021-06 deliveries
    print(f"pre-grid delivered (excluded): {pregrid}; spanning at grid start: {spanning}")
    res = dict(
        meta=dict(
            grid=[str(grid[0]), str(grid[-1])], grid_freq="1h", n_hours=n,
            pregrid_excluded=pregrid, spanning_at_start=spanning,
            g2_src="research/parallel/rounds/parallel-20260906-r2/v421/v421_runs.pkl strat R2B1D17BFG2",
            man_src="research/diagnostics/oc_manualcap/oc_manualcap_runs.pkl row M5_human",
            carry_src="research/tournament/oc_cashcarry/results.json (33 entered trades frozen; entries/exits/fees identical)",
            metric="reset_metric.year_reset per phase + v421 full-path DD formula; f=0 reproduces v421_result + oc_manualcap to the digit",
            sizing="overlay: pair legs = f x total combined equity at entry hour, held to delivery, rebalanced only at rolls; return denominator = base account equity (extra spot-cash funding NOT in denominator; see funded_capital_note)",
            funded_capital_note=("sleeve needs up to 2f extra cash for spot legs when both coins open "
                                 "(f=0.25 -> up to 1.5x funded; f=0.5 -> up to 2x funded); "
                                 "return on total funded capital ~= reported R/(1+utilised extra cash)"),
            marking=("hourly: spot leg = Binance spot 1h closes (downloaded public klines, causal last-open<H); "
                     "futures leg = quarterly 1h closes; G2/MAN legs = 4h equities ffilled (v388.hourly); "
                     "no 1m data, no engine rerun" if spot_hourly_ok else
                     "FALLBACK: spot leg = 4h closes ffilled (spot-1h download failed); futures hourly"),
            spot_hourly_ok=spot_hourly_ok,
            bybit_note="Bybit facts fetched 2026-10-06 from public instruments-info (no keys) + help-center docs; see REPORT.md",
            seconds=round(time.time() - t_start, 1)),
        g2_alone=dict(R=exp_g2["R"], W=exp_g2["W"], DD=exp_g2["DD"],
                      full_path_dd=exp_g2["full_path_dd"], years=exp_g2["years"]),
        rows={f"{label}_f{f}": dict(row, full_path_dd=full_dd[(label, f)])
              for (label, f), row in out_rows.items()},
        cm_vs_um=dict(entered=cm_cmp, skipped_with_cm=skip_cmp,
                      note=("same entry bars, same spot S_entry, same DTE; basis differs only via F. "
                            "cm_* are inverse coin-margined (settle BTC/ETH); um_* are USDT-margined. "
                            "Comparison is signal-only; live venue per task 3 is Bybit USDT-margined.")),
        bybit=dict(
            fetched="2026-10-06 (public endpoints, no keys)",
            linear_url=("https://api.bybit.com/v5/market/instruments-info"
                        "?category=linear&limit=1000"),
            inverse_url=("https://api.bybit.com/v5/market/instruments-info"
                         "?category=inverse&limit=1000"),
            linear_quarterlies=["BTCUSDT-25DEC26", "BTCUSDT-26MAR27", "BTCUSDT-25JUN27",
                                 "ETHUSDT-25DEC26", "ETHUSDT-26MAR27", "ETHUSDT-25JUN27"],
            linear_other=["BTC/ETH weeklies 09/16/23/30OCT26 + 27NOV26"],
            linear_status="Trading", linear_settle="USDT", linear_delivery_fee="0",
            linear_funding_interval=0, linear_max_leverage=50,
            linear_unified_margin=True,
            inverse_quarterlies=["BTCUSDZ26", "BTCUSDH27", "ETHUSDZ26", "ETHUSDH27"],
            inverse_status="Trading", inverse_settle="BTC/ETH (coin)",
            fees_vip0=dict(futures_taker=0.00055, futures_maker=0.0002,
                           spot_taker=0.001, spot_maker=0.001,
                           src="Bybit help-center Trading-Fee-Structure 2026-09-02; matches gate + carry fee assumptions"),
            uta_collateral=dict(btc="95% (5% haircut, base tier)",
                                eth="95% (5% haircut, base tier)",
                                src="Bybit help-center UTA intro article",
                                tier_note=("ASSUMPTION: tier breakpoints above base sizes not pulled; "
                                           "small-size carry (account < 10k USDT) stays in base tier")),
            gaps=("ASSUMPTIONS: (a) Bybit delivery-index methodology vs modelled "
                  "spot-4h-close settlement - difference bounded by delivery-bar spot range, "
                  "nets to first order in the hedged pair; (b) historical Bybit quarterly "
                  "prices not used - Binance delivery data is a proxy; (c) Bybit expiries "
                  "are Fridays like Binance quarterlies; tickers differ "
                  "(BTCUSDT-25DEC26 vs BTCUSDT_241227)")),
    )
    (HERE / "results.json").write_text(json.dumps(res, indent=1))
    for k in sorted(out_rows):
        r = out_rows[k]
        print(k, r, full_dd[k])
    print("cm entered pairs:", len([c for c in cm_cmp if c.get("cm_available")]),
          "skipped um with cm:", len(skip_cmp))
    print("wrote results.json")


if __name__ == "__main__":
    main()
