"""oc_gapstress: instantaneous-gap stress on R2B1D17BF open exposure.

Rebuilds per-phase open book + dip positions as FRACTIONS of phase equity from
oc_kpi events/barsum (+ hourly marks), then applies instantaneous down gaps
with no stop protection (close at gapped price, taker fee). See PLAN.md.

Usage: .venv/Scripts/python.exe research/tournament/oc_gapstress/compute_gapstress.py
Writes results.json (numbers) — REPORT.md is written separately by hand from it.
LIGHT job: one process, no 1m data, peak RAM well under 1 GB.
"""
from __future__ import annotations

import json
from collections import deque
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
KPI = HERE.parent / "oc_kpi"
EXT = HERE.parent / "ext"
TAKER = 0.00055
GAPS = (0.05, 0.10, 0.20)
CAPS = {"uncapped": None, "cap3": 3.0, "cap2": 2.0}
COINS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
BOOK_DELTA = {"book_fill", "book_add", "book_reduce", "book_partial"}
BOOK_FLAT = {"book_close", "book_stop", "book_tp"}
RUNG_EXIT = {"rung_sl", "rung_tp", "rung_timeout"}
CUT = pd.Timestamp("2026-09-24", tz="UTC").value

CIX = {c: i for i, c in enumerate(COINS)}


def load_marks():
    h = pd.read_parquet(EXT / "hourly_ext.parquet")
    h["t"] = pd.to_datetime(h["t"], utc=True).astype("int64").to_numpy()
    out = {}
    for c in COINS:
        m = h[h["sym"] == c].sort_values("t")
        out[c] = (m["t"].to_numpy(), m["close"].to_numpy(float))
    return out


def load_phase(s):
    ev = pd.read_parquet(KPI / f"events_s{s}.parquet",
                         columns=["t", "symbol", "kind", "price", "weight"])
    ev["t"] = pd.to_datetime(ev["t"], utc=True).astype("int64")
    bs = pd.read_parquet(KPI / f"barsum_s{s}.parquet")
    bt = pd.to_datetime(bs["t"], utc=True).astype("int64").to_numpy()
    chk = json.loads((KPI / f"check_s{s}.json").read_text())
    live0 = pd.Timestamp(chk["live"][0]).value
    live1 = pd.Timestamp(chk["live"][1]).value
    return ev, bt, bs["equity"].to_numpy(float), bs["gross_book"].to_numpy(float), live0, live1


def ffill_at(xt, xv, q):
    i = np.searchsorted(xt, q, side="right") - 1
    return np.where(i >= 0, xv[np.maximum(i, 0)], np.nan), i


def build_state(ev, bt, eq, marks):
    """Per-coin open FRACTIONS of equity at union(event times, bar ends)."""
    t = ev["t"].to_numpy()
    sym = ev["symbol"].to_numpy()
    kind = ev["kind"].to_numpy()
    price = ev["price"].to_numpy(float)
    w = ev["weight"].to_numpy(float)
    # engine prev_eq per event = indexed end equity of the previous bar
    # (add/reduce/partial weights carry a /prev_eq factor; fills do not)
    pe, _ = ffill_at(bt, eq, t)
    pe = np.where(np.isnan(pe), 1.0, pe)
    U = np.union1d(t, bt)
    U.sort()
    nu = len(U)
    Qb = np.zeros((nu, len(COINS)))  # book qty in engine q-units (start-base fraction / price)
    Qd = np.zeros((nu, len(COINS)))  # dip qty in the same units
    fills_from_open = 0
    reduce_viol = 0.0
    unpaired_exit = 0
    for c, j in CIX.items():
        m = (sym == c)
        order = np.argsort(t[m], kind="stable")
        idxm = np.where(m)[0][order]
        # --- book: delta cumsum with hard flats (engine q-units: fill qk =
        # weight/price; add/reduce/partial qk = weight*prev_eq/price because
        # those event weights carry a /prev_eq factor; see engine_user.py) ---
        qb = 0.0
        deltas = []
        for n, k in enumerate(idxm):
            kk, ww, px = kind[k], w[k], price[k]
            if kk in BOOK_DELTA:
                if kk == "book_fill" and abs(qb) > 1e-9:
                    fills_from_open += 1
                dq = ww / px if kk == "book_fill" else ww * pe[k] / px
                if kk in ("book_reduce", "book_partial") and abs(dq) > abs(qb) * 1.05 + 1e-12:
                    reduce_viol = max(reduce_viol, abs(abs(dq) - abs(qb)))
                qb += dq
            elif kk in BOOK_FLAT:
                qb = 0.0
            deltas.append((t[k], qb))
        if deltas:
            tu = np.array([d[0] for d in deltas])
            qu = np.array([d[1] for d in deltas])
            # last qb wins per timestamp, then ffill over U
            keep_t, keep_q = [], []
            for a in range(len(tu)):
                if a + 1 < len(tu) and tu[a + 1] == tu[a]:
                    continue
                keep_t.append(tu[a])
                keep_q.append(qu[a])
            ii = np.searchsorted(U, np.array(keep_t))
            has = np.zeros(nu, bool)
            has[ii] = True
            val = np.zeros(nu)
            val[ii] = np.array(keep_q)
            cur, out = 0.0, np.zeros(nu)
            for a in range(nu):
                if has[a]:
                    cur = val[a]
                out[a] = cur
            Qb[:, j] = out
        # --- dip: FIFO fill qty (qk = weight / limit price, no equity factor) ---
        fills, exits = [], []
        for k in idxm:
            if kind[k] == "rung_fill":
                fills.append((t[k], w[k] / price[k]))
            elif kind[k] in RUNG_EXIT:
                exits.append(t[k])
        fills.sort()
        exits.sort()
        # sweep post-event state at every fill/exit minute (fills first at same
        # minute, so fill-minute-stop rungs net to zero)
        from collections import Counter
        nx = Counter(exits)
        pts = sorted(set([f[0] for f in fills]) | set(nx))
        q = deque()
        fi = 0
        evts = []
        for x in pts:
            while fi < len(fills) and fills[fi][0] <= x:
                q.append(fills[fi][1])
                fi += 1
            for _ in range(nx[x]):
                if q:
                    q.popleft()
                else:
                    unpaired_exit += 1
            evts.append((x, float(sum(q))))
        # collapse to last value per timestamp, ffill over U
        ct = {}
        for a, b_ in evts:
            ct[a] = b_
        if ct:
            kt = np.array(sorted(ct))
            kv = np.array([ct[a] for a in kt])
            ii = np.searchsorted(U, kt)
            has = np.zeros(nu, bool)
            has[ii] = True
            val = np.zeros(nu)
            val[ii] = kv
            cur, out = 0.0, np.zeros(nu)
            for a in range(nu):
                if has[a]:
                    cur = val[a]
                out[a] = cur
            Qd[:, j] = out
    # equities + marks at U (equity = indexed end equity of the containing bar;
    # eqs = indexed START equity of the containing bar).
    # True fraction of current equity = Q*mark*eqs/equity (engine q-units are
    # fractions-of-bar-start per price; eq compounds multiplicatively).
    # barsum's gross_book = |qty*open|/equity omits the *eqs factor, so the
    # recon check below compares Q*mark/equity against barsum.
    equity, bi = ffill_at(bt, eq, U)
    equity = np.where(np.isnan(equity), 1.0, equity)
    bi = np.maximum(bi, 0)
    eqs = np.where(bi > 0, eq[bi - 1], 1.0)
    eqs = np.where(np.isnan(ffill_at(bt, eq, U)[0]), 1.0, eqs)
    Fb = np.zeros_like(Qb)
    Fd = np.zeros_like(Qd)
    Fb_raw = np.zeros_like(Qb)
    for c, j in CIX.items():
        mt, mv = marks[c]
        mk, _ = ffill_at(mt, mv, U)
        Fb[:, j] = Qb[:, j] * mk * eqs / equity
        Fd[:, j] = Qd[:, j] * mk * eqs / equity
        Fb_raw[:, j] = Qb[:, j] * mk / equity
    info = {"fills_from_open": int(fills_from_open),
            "reduce_overrun_max": round(float(reduce_viol), 6),
            "unpaired_rung_exits": int(unpaired_exit)}
    return U, Fb, Fd, equity, info, Fb_raw


def loss_pct(S, G, g):
    """Instant loss in % of equity for a DOWN gap of magnitude g (positive = loss).
    S = signed open fraction (longs lose), G = gross; close at gapped price (taker)."""
    return 100.0 * (S * g + TAKER * G * (1 - g))


def wquant(x, w, q):
    o = np.argsort(x, kind="stable")
    cum = np.cumsum(w[o]) / w[o].sum()
    return float(x[o][np.searchsorted(cum, q)])


def dist(x, w):
    return {"n": int(len(x)), "median": round(wquant(x, w, 0.5), 3),
            "p99": round(wquant(x, w, 0.99), 3), "max": round(float(np.max(x)), 3)}


def worst10(U, L, G, Dg, Bg, Eq):
    o = np.argsort(-L, kind="stable")[:10]
    return [{"t": pd.Timestamp(int(U[i]), tz="UTC").strftime("%Y-%m-%d %H:%M"),
             "loss_pct": round(float(L[i]), 2), "gross": round(float(G[i]), 3),
             "dip_gross": round(float(Dg[i]), 3), "book_gross": round(float(Bg[i]), 3),
             "equity": round(float(Eq[i]), 3)} for i in o]


def main():
    marks = load_marks()
    phases, states = {}, {}
    for s in range(4):
        ev, bt, eq, gb, live0, live1 = load_phase(s)
        assert ev["t"].to_numpy().max() < CUT
        U, Fb, Fd, equity, info, Fb_raw = build_state(ev, bt, eq, marks)
        bn, bg = Fb.sum(1), np.abs(Fb).sum(1)
        dn, dg = Fd.sum(1), np.abs(Fd).sum(1)
        gross = bg + dg
        live_min = (live1 - live0) / 6e10
        nxt = np.empty(len(U))
        nxt[:-1] = (U[1:] - U[:-1]) / 6e10
        nxt[-1] = max(0.0, (live1 - U[-1]) / 6e10)
        w0 = np.where((U >= live0) & (U < live1), nxt, 0.0)
        open_m = (gross > 1e-12) & (w0 > 0)
        Uc, B, D, Eq, W = U[open_m], Fb[open_m], Fd[open_m], equity[open_m], w0[open_m]
        bn, bg = B.sum(1), np.abs(B).sum(1)
        dn, dg = D.sum(1), np.abs(D).sum(1)
        states[s] = {"U": Uc, "B": B, "D": D, "Eq": Eq, "W": W,
                     "live0": live0, "live1": live1, "live_min": live_min,
                     "open_min": float(W.sum())}
        # recon: barsum row bt[k] holds the holding bar [bt[k],bt[k]+4h)'s END
        # state; compare with our post-event state at U == bt[k+1]
        j = np.searchsorted(U, bt[1:])
        j = np.clip(j, 0, len(U) - 1)
        ref = gb[:-1]
        diff = np.abs(np.abs(Fb_raw).sum(1)[j] - ref)
        out = {"n_open_samples": int(open_m.sum()),
               "open_minutes": round(float(W.sum()), 1),
               "live_minutes": round(float(live_min), 1),
               "coverage": round(float(W.sum() / live_min), 4),
               "book_gross_max": round(float(bg.max(initial=0)), 4),
               "dip_gross_max": round(float(dg.max(initial=0)), 4),
               "combined_gross_max": round(float((bg + dg).max(initial=0)), 4),
               "recon_vs_barsum": {"median_abs_diff": round(float(np.median(diff)), 5),
                                   "max_abs_diff": round(float(np.max(diff)), 4),
                                   "n_bars": int(len(ref))},
               "build_info": info,
               "gaps": {}, "single_m10": {}, "shares_m10": {}}
        for capname, cap in CAPS.items():
            sc = np.ones_like(dg) if cap is None else np.minimum(1.0, cap / np.maximum(dg, 1e-12))
            Sn, Gg = bn + dn * sc, bg + dg * sc
            for g in GAPS:
                out["gaps"][f"all_m{int(g*100)}_{capname}"] = dist(loss_pct(Sn, Gg, g), W)
            L10 = loss_pct(Sn, Gg, 0.10)
            out["shares_m10"][capname] = {
                "gt20": round(float(W[L10 > 20].sum() / W.sum()), 5),
                "gt50": round(float(W[L10 > 50].sum() / W.sum()), 5),
                "gt20_of_live": round(float(W[L10 > 20].sum() / live_min), 6),
                "gt50_of_live": round(float(W[L10 > 50].sum() / live_min), 6)}
            out[f"worst10_all_m10_{capname}"] = worst10(Uc, L10, Gg, dg * sc, bg, Eq)
        out["single_m5"], out["single_m20"] = {}, {}
        for c, j in CIX.items():
            out["single_m10"][c] = dist(
                loss_pct(B[:, j] + D[:, j], np.abs(B[:, j]) + np.abs(D[:, j]), 0.10), W)
            out["single_m5"][c] = dist(
                loss_pct(B[:, j] + D[:, j], np.abs(B[:, j]) + np.abs(D[:, j]), 0.05), W)
            out["single_m20"][c] = dist(
                loss_pct(B[:, j] + D[:, j], np.abs(B[:, j]) + np.abs(D[:, j]), 0.20), W)
        phases[str(s)] = out

    # ---- 4-phase mix on union of sample times ----
    Uall = np.union1d(np.union1d(states[0]["U"], states[1]["U"]),
                      np.union1d(states[2]["U"], states[3]["U"]))
    Uall.sort()
    P = {}
    for s in range(4):
        st = states[s]
        ii = np.searchsorted(st["U"], Uall, side="right") - 1
        hh = (ii >= 0) & (Uall >= st["live0"]) & (Uall < st["live1"])
        Bc = np.zeros((len(Uall), len(COINS)))
        Dc = np.zeros((len(Uall), len(COINS)))
        Eq = np.zeros(len(Uall))
        jj = np.maximum(ii[hh], 0)
        Bc[hh], Dc[hh], Eq[hh] = st["B"][jj], st["D"][jj], st["Eq"][jj]
        P[s] = {"Bc": Bc, "Dc": Dc, "Eq": Eq}
    Eqsum = sum(P[s]["Eq"] for s in range(4))
    Gmix = sum(np.abs(P[s]["Bc"]).sum(1) + np.abs(P[s]["Dc"]).sum(1) for s in range(4))
    open_m = (Gmix > 1e-12) & (Eqsum > 0)
    Um = Uall[open_m]
    dur = np.empty(len(Uall))
    dur[:-1] = (Uall[1:] - Uall[:-1]) / 6e10
    dur[-1] = 0.0
    Wm = dur[open_m]
    keep = Wm > 0
    Um, Wm = Um[keep], Wm[keep]
    idxm = np.where(open_m)[0][keep]
    Eqw = np.array([P[s]["Eq"][idxm] for s in range(4)])
    Eqsum_m = Eqw.sum(0)
    mix = {"n_open_samples": int(keep.sum()),
           "open_minutes": round(float(Wm.sum()), 1),
           "live_minutes": round(float(np.mean([states[s]["live_min"] for s in range(4)])), 1),
           "gaps": {}, "single_m10": {}, "single_m5": {}, "single_m20": {}, "shares_m10": {}}
    mix["coverage"] = round(float(Wm.sum() / mix["live_minutes"]), 4)
    for capname, cap in CAPS.items():
        Sall = np.zeros(len(idxm))
        Gall = np.zeros(len(idxm))
        Dall = np.zeros(len(idxm))
        Ball = np.zeros(len(idxm))
        for s in range(4):
            dg = np.abs(P[s]["Dc"][idxm]).sum(1)
            sc = np.ones(len(idxm)) if cap is None else np.minimum(1.0, cap / np.maximum(dg, 1e-12))
            Sall += (P[s]["Bc"][idxm].sum(1) + (P[s]["Dc"][idxm] * sc[:, None]).sum(1)) * P[s]["Eq"][idxm]
            Gall += (np.abs(P[s]["Bc"][idxm]).sum(1) + (np.abs(P[s]["Dc"][idxm]) * sc[:, None]).sum(1)) * P[s]["Eq"][idxm]
            Dall += ((np.abs(P[s]["Dc"][idxm]) * sc[:, None]).sum(1)) * P[s]["Eq"][idxm]
            Ball += np.abs(P[s]["Bc"][idxm]).sum(1) * P[s]["Eq"][idxm]
        Sall /= Eqsum_m
        Gall /= Eqsum_m
        Dall /= Eqsum_m
        Ball /= Eqsum_m
        for g in GAPS:
            L = loss_pct(Sall, Gall, g)
            mix["gaps"][f"all_m{int(g*100)}_{capname}"] = dist(L, Wm)
        L10 = loss_pct(Sall, Gall, 0.10)
        mix["shares_m10"][capname] = {
            "gt20": round(float(Wm[L10 > 20].sum() / Wm.sum()), 5),
            "gt50": round(float(Wm[L10 > 50].sum() / Wm.sum()), 5),
            "gt20_of_live": round(float(Wm[L10 > 20].sum() / mix["live_minutes"]), 6),
            "gt50_of_live": round(float(Wm[L10 > 50].sum() / mix["live_minutes"]), 6)}
        mix[f"worst10_all_m10_{capname}"] = worst10(Um, L10, Gall, Dall, Ball, Eqsum_m / 4)
    for c, j in CIX.items():
        Sc = sum((P[s]["Bc"][idxm][:, j] + P[s]["Dc"][idxm][:, j]) * P[s]["Eq"][idxm]
                 for s in range(4)) / Eqsum_m
        Gc = sum((np.abs(P[s]["Bc"][idxm][:, j]) + np.abs(P[s]["Dc"][idxm][:, j]))
                 * P[s]["Eq"][idxm] for s in range(4)) / Eqsum_m
        mix["single_m10"][c] = dist(loss_pct(Sc, Gc, 0.10), Wm)
        mix["single_m5"][c] = dist(loss_pct(Sc, Gc, 0.05), Wm)
        mix["single_m20"][c] = dist(loss_pct(Sc, Gc, 0.20), Wm)

    res = {"variant": "R2B1D17BF",
           "method": ("book/dip qty in engine q-units (weight/price; book flats zeroed; dip FIFO); "
                       "fractions = qty x hourly mark x bar-start equity / indexed end equity; "
                       "DOWN-gap loss% = (S*g + 0.00055*G*(1-g))*100; samples tile time "
                       "(event minutes + 4h bar ends); minute-weighted stats; mix = equity-weighted mean "
                       "of phase losses; caps scale dip proportionally per phase"),
           "taker": TAKER, "gaps": list(GAPS), "caps": list(CAPS),
           "phases": phases, "mix": mix,
           "checks": {"cut": "2026-09-24T00:00Z",
                      "oc_kpi_combined_gross_max": 6.4007, "oc_kpi_book_gross_max": 1.3131}}
    (HERE / "results.json").write_text(json.dumps(res, indent=1))
    for s, o in phases.items():
        print(f"phase {s}: open_min {o['open_minutes']:.0f} cov {o['coverage']} "
              f"m10 {o['gaps']['all_m10_uncapped']} gt20 {o['shares_m10']['uncapped']['gt20']} "
              f"recon {o['recon_vs_barsum']} info {o['build_info']}", flush=True)
    print("mix:", mix["gaps"]["all_m10_uncapped"], mix["shares_m10"]["uncapped"], flush=True)


if __name__ == "__main__":
    main()
