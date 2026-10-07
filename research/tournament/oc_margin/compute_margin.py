"""oc_margin: Bybit cross-margin / leverage + liquidation-distance report for R2B1D17BFG2.

Rebuilds per-phase open book + dip positions as FRACTIONS of phase equity from
oc_kpi_g2 events/barsum (+ hourly marks) with the exact oc_gapstress q-units
method, then applies Bybit USDT-perp cross-margin math (Hedge Mode).
See PLAN.md. LIGHT job: one process, no 1m data, peak RAM well under 1 GB.

Usage: .venv/Scripts/python.exe research/tournament/oc_margin/compute_margin.py
Writes results.json (numbers) — REPORT.md is written separately by hand from it.
"""
from __future__ import annotations

import json
from collections import deque
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
KPI = HERE.parent / "oc_kpi_g2"
EXT = HERE.parent / "ext"
TAKER = 0.00055
MMR = 0.005  # Bybit majors tier-1 assumption (see PLAN.md)
LEVS = (3, 5, 10, 20)
GAPS = (0.10, 0.20)
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
    pe, _ = ffill_at(bt, eq, t)
    pe = np.where(np.isnan(pe), 1.0, pe)
    U = np.union1d(t, bt)
    U.sort()
    nu = len(U)
    Qb = np.zeros((nu, len(COINS)))
    Qd = np.zeros((nu, len(COINS)))
    fills_from_open = 0
    reduce_viol = 0.0
    unpaired_exit = 0
    for c, j in CIX.items():
        m = (sym == c)
        order = np.argsort(t[m], kind="stable")
        idxm = np.where(m)[0][order]
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
            else:
                continue
            deltas.append((t[k], qb))
        if deltas:
            tu = np.array([d[0] for d in deltas])
            qu = np.array([d[1] for d in deltas])
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
        fills, exits = [], []
        for k in idxm:
            if kind[k] == "rung_fill":
                fills.append((t[k], w[k] / price[k]))
            elif kind[k] in RUNG_EXIT:
                exits.append(t[k])
        fills.sort()
        exits.sort()
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


def d_liq_of(G):
    """Adverse all-long-weighted move (fraction) triggering liquidation."""
    with np.errstate(divide="ignore", invalid="ignore"):
        d = (1.0 - MMR * G) / (G * (1.0 - MMR))
    return np.where(G > 1e-12, d, np.inf)


def gap_loss_frac(S, G, g):
    return S * g + TAKER * G * (1 - g)


def wquant(x, w, q):
    x = np.asarray(x, float)
    w = np.asarray(w, float)
    o = np.argsort(x, kind="stable")
    cum = np.cumsum(w[o]) / w[o].sum()
    return float(x[o][np.searchsorted(cum, q)])


def wpct(x, w, q):
    return round(wquant(x, w, q), 4)


def main():
    marks = load_marks()
    phases, states = {}, {}
    for s in range(4):
        ev, bt, eq, gb, live0, live1 = load_phase(s)
        assert ev["t"].to_numpy().max() < CUT
        U, Fb, Fd, equity, info, Fb_raw = build_state(ev, bt, eq, marks)
        bn, bg = Fb.sum(1), np.abs(Fb).sum(1)
        dn, dg = Fd.sum(1), np.abs(Fd).sum(1)
        S, G = bn + dn, bg + dg
        live_min = (live1 - live0) / 6e10
        nxt = np.empty(len(U))
        nxt[:-1] = (U[1:] - U[:-1]) / 6e10
        nxt[-1] = max(0.0, (live1 - U[-1]) / 6e10)
        w0 = np.where((U >= live0) & (U < live1), nxt, 0.0)
        open_m = (G > 1e-12) & (w0 > 0)
        Uc, Bc, Dc, Eq, W = U[open_m], Fb[open_m], Fd[open_m], equity[open_m], w0[open_m]
        Sc, Gc = S[open_m], G[open_m]
        Bg = np.abs(Bc).sum(1)
        Dg = np.abs(Dc).sum(1)
        states[s] = {"U": Uc, "B": Bc, "D": Dc, "Eq": Eq, "W": W,
                      "live0": live0, "live1": live1, "live_min": live_min,
                      "open_min": float(W.sum())}
        j = np.searchsorted(U, bt[1:])
        j = np.clip(j, 0, len(U) - 1)
        ref = gb[:-1]
        diff = np.abs(np.abs(Fb_raw).sum(1)[j] - ref)
        DL = d_liq_of(Gc)
        MM = MMR * Gc
        lev_info = {}
        min_lev = None
        for L in LEVS:
            IM = Gc / L
            blocked = IM > 0.95
            lev_info[str(L)] = {
                "max_IM": round(float(IM.max(initial=0)), 4),
                "max_G": round(float(Gc.max(initial=0)), 4),
                "share_blocked_open": round(float(W[blocked].sum() / W.sum()), 6),
                "share_blocked_live": round(float(W[blocked].sum() / live_min), 6),
                "n_blocked_samples": int(blocked.sum()),
            }
            if blocked.sum() == 0 and min_lev is None:
                min_lev = L
        if min_lev is None:
            min_lev = 20
        free_min = 1.0 - Gc / min_lev
        gaps = {}
        for g in GAPS:
            lf = gap_loss_frac(Sc, Gc, g)
            liq_thr = 1.0 - MMR * Gc * (1 - g)
            liqd = lf >= liq_thr
            gaps[f"m{int(g*100)}"] = {
                "loss_median": round(wquant(lf * 100, W, 0.5), 3),
                "loss_p99": round(wquant(lf * 100, W, 0.99), 3),
                "loss_max": round(float(np.max(lf * 100)), 3),
                "share_liquidated_open": round(float(W[liqd].sum() / W.sum()), 6),
                "share_liquidated_live": round(float(W[liqd].sum() / live_min), 6),
                "n_liquidated_samples": int(liqd.sum()),
            }
        # worst-10 by -10% gap loss
        lf10 = gap_loss_frac(Sc, Gc, 0.10)
        o = np.argsort(-lf10, kind="stable")[:10]
        worst10 = [{"t": pd.Timestamp(int(Uc[i]), tz="UTC").strftime("%Y-%m-%d %H:%M"),
                    "loss_pct": round(float(lf10[i] * 100), 2),
                    "gross": round(float(Gc[i]), 3),
                    "dip_gross": round(float(Dg[i]), 3),
                    "book_gross": round(float(Bg[i]), 3),
                    "d_liq": round(float(DL[i]), 4),
                    "liquidated": bool(lf10[i] >= 1.0 - MMR * Gc[i] * 0.9),
                    "equity": round(float(Eq[i]), 3)} for i in o]
        out = {"n_open_samples": int(open_m.sum()),
               "open_minutes": round(float(W.sum()), 1),
               "live_minutes": round(float(live_min), 1),
               "coverage": round(float(W.sum() / live_min), 4),
               "G_median": wpct(Gc, W, 0.5), "G_p99": wpct(Gc, W, 0.99),
               "G_max": round(float(Gc.max(initial=0)), 4),
               "S_max_long": round(float(Sc.max(initial=0)), 4),
               "S_min_short": round(float(Sc.min()), 4),
               "book_gross_max": round(float(Bg.max(initial=0)), 4),
               "dip_gross_max": round(float(Dg.max(initial=0)), 4),
               "MM_median": wpct(MM, W, 0.5), "MM_p99": wpct(MM, W, 0.99),
               "MM_max": round(float(MM.max(initial=0)), 4),
               "recon_vs_barsum": {"median_abs_diff": round(float(np.median(diff)), 5),
                                   "max_abs_diff": round(float(np.max(diff)), 4),
                                   "n_bars": int(len(ref))},
               "build_info": info,
               "leverage": lev_info,
               "min_leverage_never_blocked": int(min_lev),
               "at_min_leverage": {
                   "L": int(min_lev),
                   "free_median": wpct(free_min, W, 0.5),
                   "free_p1": wpct(free_min, W, 0.01),
                   "free_min": round(float(free_min.min()), 4),
                   "dliq_median": wpct(DL[np.isfinite(DL)], W[np.isfinite(DL)], 0.5)
                   if np.isfinite(DL).any() else None,
                   "dliq_p1": wpct(DL[np.isfinite(DL)], W[np.isfinite(DL)], 0.01)
                   if np.isfinite(DL).any() else None,
                   "dliq_min": round(float(DL.min(initial=np.inf)), 4),
               },
               "gaps": gaps,
               "worst10_m10": worst10}
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
    Sall = sum((P[s]["Bc"][idxm].sum(1) + P[s]["Dc"][idxm].sum(1)) * P[s]["Eq"][idxm]
               for s in range(4)) / Eqsum_m
    Gall = sum((np.abs(P[s]["Bc"][idxm]).sum(1) + np.abs(P[s]["Dc"][idxm]).sum(1))
               * P[s]["Eq"][idxm] for s in range(4)) / Eqsum_m
    Ball = sum(np.abs(P[s]["Bc"][idxm]).sum(1) * P[s]["Eq"][idxm]
               for s in range(4)) / Eqsum_m
    Dall = sum((np.abs(P[s]["Dc"][idxm]).sum(1)) * P[s]["Eq"][idxm]
               for s in range(4)) / Eqsum_m
    live_mean = float(np.mean([states[s]["live_min"] for s in range(4)]))
    DLm = d_liq_of(Gall)
    MMm = MMR * Gall
    lev_info = {}
    min_lev = None
    for L in LEVS:
        IM = Gall / L
        blocked = IM > 0.95
        lev_info[str(L)] = {
            "max_IM": round(float(IM.max(initial=0)), 4),
            "share_blocked_open": round(float(Wm[blocked].sum() / Wm.sum()), 6),
            "share_blocked_live": round(float(Wm[blocked].sum() / live_mean), 6),
            "n_blocked_samples": int(blocked.sum()),
        }
        if blocked.sum() == 0 and min_lev is None:
            min_lev = L
    if min_lev is None:
        min_lev = 20
    free_min = 1.0 - Gall / min_lev
    gaps = {}
    for g in GAPS:
        lf = gap_loss_frac(Sall, Gall, g)
        liq_thr = 1.0 - MMR * Gall * (1 - g)
        liqd = lf >= liq_thr
        gaps[f"m{int(g*100)}"] = {
            "loss_median": round(wquant(lf * 100, Wm, 0.5), 3),
            "loss_p99": round(wquant(lf * 100, Wm, 0.99), 3),
            "loss_max": round(float(np.max(lf * 100)), 3),
            "share_liquidated_open": round(float(Wm[liqd].sum() / Wm.sum()), 6),
            "share_liquidated_live": round(float(Wm[liqd].sum() / live_mean), 6),
            "n_liquidated_samples": int(liqd.sum()),
        }
    lf10 = gap_loss_frac(Sall, Gall, 0.10)
    o = np.argsort(-lf10, kind="stable")[:10]
    Eqmean = Eqsum_m / 4
    worst10 = [{"t": pd.Timestamp(int(Um[i]), tz="UTC").strftime("%Y-%m-%d %H:%M"),
                "loss_pct": round(float(lf10[i] * 100), 2),
                "gross": round(float(Gall[i]), 3),
                "dip_gross": round(float(Dall[i]), 3),
                "book_gross": round(float(Ball[i]), 3),
                "d_liq": round(float(DLm[i]), 4),
                "liquidated": bool(lf10[i] >= 1.0 - MMR * Gall[i] * 0.9),
                "equity": round(float(Eqmean[i]), 3)} for i in o]
    mix = {"n_open_samples": int(keep.sum()),
           "open_minutes": round(float(Wm.sum()), 1),
           "live_minutes": round(float(live_mean), 1),
           "coverage": round(float(Wm.sum() / live_mean), 4),
           "G_median": wpct(Gall, Wm, 0.5), "G_p99": wpct(Gall, Wm, 0.99),
           "G_max": round(float(Gall.max(initial=0)), 4),
           "MM_median": wpct(MMm, Wm, 0.5), "MM_p99": wpct(MMm, Wm, 0.99),
           "MM_max": round(float(MMm.max(initial=0)), 4),
           "leverage": lev_info,
           "min_leverage_never_blocked": int(min_lev),
           "at_min_leverage": {
               "L": int(min_lev),
               "free_median": wpct(free_min, Wm, 0.5),
               "free_p1": wpct(free_min, Wm, 0.01),
               "free_min": round(float(free_min.min()), 4),
               "dliq_median": wpct(DLm[np.isfinite(DLm)], Wm[np.isfinite(DLm)], 0.5),
               "dliq_p1": wpct(DLm[np.isfinite(DLm)], Wm[np.isfinite(DLm)], 0.01),
               "dliq_min": round(float(DLm.min(initial=np.inf)), 4),
           },
           "gaps": gaps,
           "worst10_m10": worst10}

    res = {"variant": "R2B1D17BFG2",
           "venue": "Bybit USDT perps, cross margin, Hedge Mode",
           "method": ("book/dip qty in engine q-units (weight/price; book flats zeroed; dip FIFO); "
                       "fractions = qty x hourly mark x bar-start equity / indexed end equity; "
                       "Hedge-Mode gross = |book_net|+|dip_net| per coin; "
                       "Bybit IM = G/L, MM = 0.005*G, free = 1-G/L, blocked iff IM>0.95; "
                       "d_liq = (1-0.005*G)/(G*0.995) all-long-weighted; "
                       "gap loss = S*g+0.00055*G*(1-g); liquidated iff loss >= 1-0.005*G*(1-g)"),
           "tier_assumption": ("No Bybit tier table found in the repo; assume all five majors inside "
                               "tier-1 for an account < 10k USDT (max notional ~3-4x equity, far below "
                               "tier-1 value limits); flat MMR = 0.005 (0.5%). Engine's 1% MM check is "
                               "the conservative side row."),
           "leverage_settings": list(LEVS), "MMR": MMR, "taker": TAKER,
           "gaps": list(GAPS), "block_threshold": 0.95,
           "phases": phases, "mix": mix,
           "checks": {"cut": "2026-09-24T00:00Z"}}
    (HERE / "results.json").write_text(json.dumps(res, indent=1))
    for s, out in phases.items():
        print(f"phase {s}: Gmax {out['G_max']} minLev {out['min_leverage_never_blocked']} "
              f"dliq {out['at_min_leverage']} gaps {out['gaps']} recon {out['recon_vs_barsum']}",
              flush=True)
    print("mix:", mix["G_max"], mix["min_leverage_never_blocked"],
          mix["at_min_leverage"], mix["gaps"], flush=True)


if __name__ == "__main__":
    main()
