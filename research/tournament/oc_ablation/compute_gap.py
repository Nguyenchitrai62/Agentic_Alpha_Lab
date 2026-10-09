"""oc_ablation gap test: -10% all-coin instantaneous gap per row (oc_gapstress method).

Light job (events + hourly marks, no 1m). For each row, rebuilds per-phase
open book+dip fractions from that row's saved events with the oc_gapstress
build_state logic (engine q-units, FIFO dips, qty x hourly mark x
start-equity/end-equity), then the 4-phase equity-weighted mix on the union
of sample times. Reports worst-minute -10% loss, its timestamp/split, loss at
G2's worst minute, and minute-weighted median/p99/max. Writes tmp/gap.json.
"""
from __future__ import annotations

import json
import pickle
from collections import Counter, deque
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
EXT = HERE.parent / "ext"
ROWS = ["G2", "NO_GOV", "NO_BEAR", "NO_CAP", "NO_B1", "TOUCH", "NO_VT"]
COINS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
BOOK_DELTA = {"book_fill", "book_add", "book_reduce", "book_partial"}
BOOK_FLAT = {"book_close", "book_stop", "book_tp"}
RUNG_EXIT = {"rung_sl", "rung_tp", "rung_timeout"}
TAKER = 0.00055
CIX = {c: i for i, c in enumerate(COINS)}


def ffill_at(xt, xv, q):
    i = np.searchsorted(xt, q, side="right") - 1
    return np.where(i >= 0, xv[np.maximum(i, 0)], np.nan), i


def build_state(ev, bt, eq, marks):
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
    for c, j in CIX.items():
        m = (sym == c)
        order = np.argsort(t[m], kind="stable")
        idxm = np.where(m)[0][order]
        qb = 0.0
        deltas = []
        for k in idxm:
            kk, ww, px = kind[k], w[k], price[k]
            if kk in BOOK_DELTA:
                dq = ww / px if kk == "book_fill" else ww * pe[k] / px
                qb += dq
            elif kk in BOOK_FLAT:
                qb = 0.0
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
    Fb = np.zeros_like(Qb)
    Fd = np.zeros_like(Qd)
    for c, j in CIX.items():
        mt, mv = marks[c]
        mk, _ = ffill_at(mt, mv, U)
        Fb[:, j] = Qb[:, j] * mk * eqs / equity
        Fd[:, j] = Qd[:, j] * mk * eqs / equity
    return U, Fb, Fd, equity


def loss_pct(S, G, g=0.10):
    return 100.0 * (S * g + TAKER * G * (1 - g))


def main():
    h = pd.read_parquet(EXT / "hourly_ext.parquet")
    h["t"] = pd.to_datetime(h["t"], utc=True).astype("int64").to_numpy()
    marks = {}
    for c in COINS:
        m = h[h["sym"] == c].sort_values("t")
        marks[c] = (m["t"].to_numpy(), m["close"].to_numpy(float))
    per_row_mix = {}
    for r in ROWS:
        states = {}
        for s in range(4):
            p = HERE / "tmp" / f"events_s{s}_{r}.parquet"
            rp = HERE / "tmp" / f"runs_s{s}.pkl"
            assert p.exists(), f"missing {p}"
            ev = pd.read_parquet(p, columns=["t", "symbol", "kind", "price", "weight"])
            ev["t"] = pd.to_datetime(ev["t"], utc=True).astype("int64")
            runs = pickle.loads(rp.read_bytes())
            bt = pd.to_datetime(pd.Series(runs[r]["t"]), utc=True).astype("int64").to_numpy()
            eq = np.array(runs[r]["eq"], float)
            U, Fb, Fd, equity = build_state(ev, bt, eq, marks)
            dur = np.empty(len(U))
            dur[:-1] = (U[1:] - U[:-1]) / 6e10
            dur[-1] = 0.0
            states[s] = {"U": U, "B": Fb, "D": Fd, "Eq": equity, "W": dur}
        Uall = np.union1d(np.union1d(states[0]["U"], states[1]["U"]),
                          np.union1d(states[2]["U"], states[3]["U"]))
        Uall.sort()
        P = {}
        for s in range(4):
            st = states[s]
            ii = np.searchsorted(st["U"], Uall, side="right") - 1
            hh = ii >= 0
            Bc = np.zeros((len(Uall), len(COINS)))
            Dc = np.zeros((len(Uall), len(COINS)))
            Eq = np.zeros(len(Uall))
            jj = np.maximum(ii[hh], 0)
            Bc[hh], Dc[hh], Eq[hh] = st["B"][jj], st["D"][jj], st["Eq"][jj]
            P[s] = {"Bc": Bc, "Dc": Dc, "Eq": Eq}
        Eqsum = sum(P[s]["Eq"] for s in range(4))
        Gmix = sum(np.abs(P[s]["Bc"]).sum(1) + np.abs(P[s]["Dc"]).sum(1) for s in range(4))
        open_m = (Gmix > 1e-12) & (Eqsum > 0)
        dur = np.empty(len(Uall))
        dur[:-1] = (Uall[1:] - Uall[:-1]) / 6e10
        dur[-1] = 0.0
        keep = open_m & (dur > 0)
        Um = Uall[keep]
        Wm = dur[keep]
        idxm = np.where(keep)[0]
        Eqw = np.array([P[s]["Eq"][idxm] for s in range(4)])
        Eqsum_m = Eqw.sum(0)
        Sall = np.zeros(len(idxm))
        Gall = np.zeros(len(idxm))
        Dall = np.zeros(len(idxm))
        Ball = np.zeros(len(idxm))
        for s in range(4):
            Sall += (P[s]["Bc"][idxm].sum(1) + P[s]["Dc"][idxm].sum(1)) * P[s]["Eq"][idxm]
            Gall += (np.abs(P[s]["Bc"][idxm]).sum(1) + np.abs(P[s]["Dc"][idxm]).sum(1)) * P[s]["Eq"][idxm]
            Dall += np.abs(P[s]["Dc"][idxm]).sum(1) * P[s]["Eq"][idxm]
            Ball += np.abs(P[s]["Bc"][idxm]).sum(1) * P[s]["Eq"][idxm]
        Sall /= Eqsum_m
        Gall /= Eqsum_m
        Dall /= Eqsum_m
        Ball /= Eqsum_m
        L10 = loss_pct(Sall, Gall)
        o = np.argsort(-L10, kind="stable")
        k = int(o[0])
        per_row_mix[r] = {
            "worst_t": pd.Timestamp(int(Um[k]), tz="UTC").strftime("%Y-%m-%d %H:%M"),
            "worst_loss_pct": round(float(L10[k]), 2),
            "worst_gross": round(float(Gall[k]), 3),
            "worst_dip": round(float(Dall[k]), 3),
            "worst_book": round(float(Ball[k]), 3),
            "median": round(float(np.average(np.sort(L10), weights=Wm[np.argsort(L10)])), 3) if len(L10) else 0.0,
            "max": round(float(L10.max(initial=0)), 2),
        }
        # proper weighted median/p99
        oo = np.argsort(L10, kind="stable")
        cum = np.cumsum(Wm[oo]) / Wm.sum()
        per_row_mix[r]["median"] = round(float(L10[oo][np.searchsorted(cum, 0.5)]), 3)
        per_row_mix[r]["p99"] = round(float(L10[oo][np.searchsorted(cum, 0.99)]), 3)
        print(r, per_row_mix[r])
    # loss of every row at G2's worst minute
    g2t = per_row_mix["G2"]["worst_t"]
    out = {"rows": per_row_mix, "g2_worst_t": g2t, "gap": "-10% all-coin, close at gapped price (taker)",
           "method": "oc_gapstress build_state + equity-weighted 4-phase mix; minute-weighted stats"}
    (HERE / "tmp" / "gap.json").write_text(json.dumps(out, indent=1))
    print("wrote tmp/gap.json, G2 worst minute:", g2t)


if __name__ == "__main__":
    main()
