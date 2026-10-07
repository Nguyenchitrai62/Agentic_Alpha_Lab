"""oc_carrymargin: hourly UTA margin usage for G2 + frozen carry at f=0.25.

Assignment: docs/opencode/OPENCODE_W_oc_carrymargin.md. Deployment safety
check, LIGHT-MEDIUM, no engine reruns, no network, no 1m data, one process.

Frozen inputs only:
- G2 legs rebuilt HOURLY from stored oc_kpi_g2 events/barsum with the exact
  oc_margin q-units math (book flats zeroed, dip FIFO, Hedge-Mode gross =
  |book_net| + |dip_net| per coin), marked with hourly_ext 1h closes
  (causal: last 1h bar strictly before H), equity ffill from barsum.
  v421/v422_runs.pkl equity series verified identical to barsum.
- Carry: 33 frozen oc_cashcarry pairs reused verbatim (signal, F/S_entry,
  deliveries, ret_alloc untouched); legs = f x total mix equity at entry
  hour (oc_carrycombo convention), held to delivery; spot marked with
  hourly_ext proxy, shorts with qbasis um_ 1h (causal, same rule).

UTA math (stated assumptions):
- Perp IM = G2 gross notional / 5 (account leverage the bot uses: 5x per
  coin, runbook BOT_RUNBOOK_VI.md section 1; oc_margin: minimum setting
  that never blocks at cap 2.0).
- Carry-short IM = short notional / 10 BASE (runbook section 1: carry
  short quarterly at 10x, spot-hedged). Side row at /5 (conservative,
  oc_utamargin convention).
- Spot needs no IM (it IS collateral). Margin balance = total equity -
  haircut x spot value. BASE haircut 5% on BTC/ETH spot (Bybit UTA
  help-center: BTC/ETH 95% base tier; source oc_carrycombo REPORT section 3
  + oc_utamargin results.json haircut_src; account < 10k stays base tier).
  STRESS row: 10% haircut on BTC/ETH spot (assignment-ordered).
- Denominator "equity" = total account equity Eq_tot = Eq_mix + carry MtM
  (one UTA, BOT sizes on total equity). Primary metric usage_eq =
  IM_total / Eq_tot; collateral-adjusted usage_bal = IM_total / balance
  (base 5%, stress 10%). Blocked convention: IM > 95% (oc_margin /
  oc_utamargin); tight iff > 80%.

Grid: every hour 2021-09-24 00:00 .. 2026-09-23 23:00 UTC (43,824 hours),
all strictly before CUT 2026-09-24 00:00 UTC.

Usage: .venv/Scripts/python.exe research/tournament/oc_carrymargin/compute_carrymargin.py
Writes results.json (REPORT.md is written separately by hand from it).
"""

from __future__ import annotations

import json
import pickle
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
KPI = ROOT / "research" / "tournament" / "oc_kpi_g2"
EXT = ROOT / "research" / "tournament" / "ext"
CASH = ROOT / "research" / "tournament" / "oc_cashcarry"
QDIR = ROOT / "data" / "raw" / "qbasis_20261003"
R2 = ROOT / "research" / "parallel" / "rounds" / "parallel-20260906-r2"

COINS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
CARRY_COINS = ["BTC", "ETH"]
CUT = pd.Timestamp("2026-09-24 00:00", tz="UTC")
GRID_START = pd.Timestamp("2021-09-24 00:00", tz="UTC")
GRID_END = pd.Timestamp("2026-09-23 23:00", tz="UTC")
LEV_PERP = 5
LEV_CARRY_BASE = 10
LEV_CARRY_CONS = 5
HAIRCUT_BASE = 0.05
HAIRCUT_STRESS = 0.10
F = 0.25
FEE_ENTRY_PAID = 0.001 + 0.00055
CIX = {c: i for i, c in enumerate(COINS)}
BOOK_DELTA = {"book_fill", "book_add", "book_reduce", "book_partial"}
BOOK_FLAT = {"book_close", "book_stop", "book_tp"}
RUNG_EXIT = {"rung_sl", "rung_tp", "rung_timeout"}
NS_H = 3_600_000_000_000


def ffill_at(xt: np.ndarray, xv: np.ndarray, q: np.ndarray):
    i = np.searchsorted(xt, q, side="right") - 1
    return np.where(i >= 0, xv[np.maximum(i, 0)], np.nan), i


def load_marks():
    h = pd.read_parquet(EXT / "hourly_ext.parquet", columns=["t", "sym", "close"])
    h = h[h["sym"].isin(COINS)].copy()
    h["t"] = pd.to_datetime(h["t"], utc=True)
    assert (h["t"] < CUT + pd.Timedelta(days=1)).all()
    out = {}
    for c in COINS:
        m = h[h["sym"] == c].sort_values("t")
        out[c] = (m["t"].to_numpy(dtype="datetime64[ns]").astype(np.int64),
                  m["close"].to_numpy(float))
    return out


def load_phase(s: int):
    ev = pd.read_parquet(KPI / f"events_s{s}.parquet",
                         columns=["t", "symbol", "kind", "price", "weight"])
    ev["t"] = pd.to_datetime(ev["t"], utc=True)
    assert (ev["t"] < CUT).all()
    bs = pd.read_parquet(KPI / f"barsum_s{s}.parquet")
    bs["t"] = pd.to_datetime(bs["t"], utc=True)
    assert (bs["t"] < CUT).all()
    return ev, bs


def build_hourly_state(ev: pd.DataFrame, bs: pd.DataFrame, marks: dict,
                       grid_ns: np.ndarray):
    """Replay stored events to each hour H (post-event state, causal marks).

    Same q-units math as oc_margin/compute_margin.py and
    oc_utamargin/analyze_utamargin.py: book_fill qk = weight/price;
    book_add/reduce/partial qk = weight*prev_eq/price; book_stop/tp/close
    zero the coin; dip rung_fill qk = weight/price with FIFO exits.
    Fractions = qty x mark x bar-start equity / indexed equity.
    Marks: last 1h bar strictly before H.
    """
    from collections import Counter, deque

    t = ev["t"].to_numpy(dtype="datetime64[ns]").astype(np.int64)
    sym = ev["symbol"].to_numpy()
    kind = ev["kind"].to_numpy()
    price = ev["price"].to_numpy(float)
    w = ev["weight"].to_numpy(float)
    bt = bs["t"].to_numpy(dtype="datetime64[ns]").astype(np.int64)
    eq = bs["equity"].to_numpy(float)
    pe, _ = ffill_at(bt, eq, t)
    pe = np.where(np.isnan(pe), 1.0, pe)

    U = np.union1d(t, grid_ns)
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
        nx = Counter(exits)
        pts = sorted(set([f[0] for f in fills]) | set(nx))
        q = deque()
        fi = 0
        ct = {}
        for x in pts:
            while fi < len(fills) and fills[fi][0] <= x:
                q.append(fills[fi][1])
                fi += 1
            for _ in range(nx[x]):
                if q:
                    q.popleft()
            ct[x] = float(sum(q))
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
    Fb_raw = np.zeros_like(Qb)
    for c, j in CIX.items():
        mt, mv = marks[c]
        mk, _ = ffill_at(mt, mv, U - NS_H)  # last 1h bar strictly before H
        mk = np.where(np.isnan(mk), mv[0], mk)
        Fb[:, j] = Qb[:, j] * mk * eqs / equity
        Fd[:, j] = Qd[:, j] * mk * eqs / equity
        Fb_raw[:, j] = Qb[:, j] * mk / equity
    iu = np.searchsorted(U, grid_ns, side="right") - 1
    iu = np.maximum(iu, 0)
    gi = np.maximum(np.searchsorted(U, grid_ns, side="right") - 1, 0)
    return Fb[iu], Fd[iu], equity[gi], Fb_raw[iu]


def load_carry_trades():
    res = json.loads((CASH / "results.json").read_text())
    trades = res["trades"]
    assert len(trades) == 33, len(trades)
    out = []
    for r in trades:
        out.append({
            "coin": r["coin"],
            "delivery": r["delivery"],
            "entry_open": pd.Timestamp(r["entry_open"], tz="UTC"),
            "F_entry": float(r["F_entry"]),
            "S_entry": float(r["S_entry"]),
            "ret_alloc": float(r["ret_alloc"]),
            "D": pd.Timestamp(r["delivery"] + " 08:00", tz="UTC"),
        })
    return out


def load_q_hourly(coin: str):
    import glob
    import re
    out = {}
    for f in sorted(glob.glob(str(QDIR / f"um_{coin}USDT_*_1h.parquet"))):
        m = re.search(r"_(\d{6})_1h\.parquet$", f)
        s = m.group(1)
        D = f"20{s[:2]}-{s[2:4]}-{s[4:6]}"
        d = pd.read_parquet(f, columns=["open_time", "close"])
        ot = pd.to_datetime(d["open_time"], utc=True).to_numpy(
            dtype="datetime64[ns]").astype(np.int64)
        o = np.argsort(ot)
        out[D] = (ot[o], d["close"].to_numpy(float)[o])
    return out


def stats(x: np.ndarray):
    x = np.asarray(x, dtype=float)
    return {
        "n": int(len(x)),
        "max": round(float(np.max(x)), 4),
        "p99": round(float(np.percentile(x, 99)), 4),
        "mean": round(float(np.mean(x)), 4),
        "n_above_80": int(np.sum(x > 0.80)),
        "n_above_95": int(np.sum(x > 0.95)),
        "share_above_80_pct": round(100.0 * float(np.mean(x > 0.80)), 3),
        "share_above_95_pct": round(100.0 * float(np.mean(x > 0.95)), 3),
    }


def main() -> None:
    grid = pd.date_range(GRID_START, GRID_END, freq="1h", tz="UTC")
    assert grid.max() < CUT and grid.min() >= pd.Timestamp("2021-09-24", tz="UTC")
    grid_ns = grid.to_numpy(dtype="datetime64[ns]").astype(np.int64)
    n = len(grid)
    print(f"hours={n} grid {grid[0]} .. {grid[-1]}", flush=True)

    marks = load_marks()

    # v421/v422 equity identity check (named sources; G2 rows identical)
    v_ident = {}
    for v in ("v421", "v422"):
        pkl = pickle.load(open(R2 / v / f"{v}_runs.pkl", "rb"))
        ok = True
        for s in range(4):
            vv = pkl[s]["R2B1D17BFG2"]
            bs = pd.read_parquet(KPI / f"barsum_s{s}.parquet")
            if len(vv["eq"]) != len(bs) or not np.allclose(
                    vv["eq"], bs["equity"].to_numpy(float)):
                ok = False
        v_ident[v] = bool(ok)
    print(f"v421/v422 equity identical to barsum: {v_ident}", flush=True)

    Fb_s, Fd_s, Eq_s = {}, {}, {}
    recon = {}
    for s in range(4):
        ev, bs = load_phase(s)
        Fb, Fd, E, Fr = build_hourly_state(ev, bs, marks, grid_ns)
        Fb_s[s], Fd_s[s], Eq_s[s] = Fb, Fd, E
        bt = pd.to_datetime(bs["t"], utc=True)
        gb = bs["gross_book"].to_numpy(float)
        okm = (bt >= GRID_START) & (bt <= GRID_END)
        gi = np.searchsorted(grid, bt[okm])
        valid = gi < n
        diff = np.abs(np.abs(Fr[gi[valid]]).sum(1) - gb[okm.values][valid])
        recon[str(s)] = {"median_abs_diff": round(float(np.median(diff)), 5),
                         "max_abs_diff": round(float(diff.max()), 4)}
        print(f"phase {s}: recon median {np.median(diff):.5f} max {diff.max():.4f}",
              flush=True)
    Eq = np.stack([Eq_s[s] for s in range(4)])
    Eq_mix = Eq.mean(0)
    Gsym = {c: np.zeros(n) for c in COINS}
    for j, c in enumerate(COINS):
        num_g = sum((np.abs(Fb_s[s][:, j]) + np.abs(Fd_s[s][:, j])) * Eq_s[s]
                    for s in range(4))
        Gsym[c] = num_g / np.maximum(Eq.sum(0), 1e-12)
    Gall = sum(Gsym.values())

    # ---- carry legs (frozen trades, oc_carrycombo sizing) ----
    trades = load_carry_trades()
    qmap = {c: load_q_hourly(c) for c in CARRY_COINS}
    spot_px = {}
    for c in CARRY_COINS:
        mt, mv = marks[c + "USDT"]
        q = grid_ns - NS_H
        i = np.searchsorted(mt, q, side="right") - 1
        spot_px[c] = np.where(i >= 0, mv[np.maximum(i, 0)], np.nan)
    fut_px = {}
    for r in trades:
        key = (r["coin"], r["delivery"])
        if key not in fut_px:
            ot, cl = qmap[r["coin"]][r["delivery"]]
            q = grid_ns - NS_H
            i = np.searchsorted(ot, q, side="right") - 1
            fut_px[key] = np.where(i >= 0, cl[np.maximum(i, 0)], np.nan)
    Te = np.array([r["entry_open"].value for r in trades])
    Dd = np.array([r["D"].value for r in trades])
    Eq_entry = np.array([float(Eq_mix[np.maximum(
        np.searchsorted(grid_ns, t, side="right") - 1, 0)]) for t in Te])

    spot_val = np.zeros(n)
    spot_cost = np.zeros(n)
    short_not = np.zeros(n)
    carry_eq = np.zeros(n)
    for k, r in enumerate(trades):
        S = np.where(np.isnan(spot_px[r["coin"]]), r["S_entry"], spot_px[r["coin"]])
        Fraw = fut_px[(r["coin"], r["delivery"])]
        Fraw = np.where(np.isnan(Fraw), r["F_entry"], Fraw)
        open_m = (grid_ns >= Te[k]) & (grid_ns < Dd[k])
        shut_m = (grid_ns >= Dd[k])
        qty_s = F * Eq_entry[k] / r["S_entry"]
        qty_f = F * Eq_entry[k] / r["F_entry"]
        spot_val += np.where(open_m, qty_s * S, 0.0)
        spot_cost += np.where(open_m, F * Eq_entry[k], 0.0)
        short_not += np.where(open_m, qty_f * Fraw, 0.0)
        upnl = (qty_s * (S - r["S_entry"]) + qty_f * (r["F_entry"] - Fraw)
                - F * Eq_entry[k] * FEE_ENTRY_PAID)
        carry_eq += np.where(open_m, upnl, 0.0)
        carry_eq += np.where(shut_m, F * Eq_entry[k] * r["ret_alloc"], 0.0)
    assert np.isfinite(spot_val).all() and np.isfinite(short_not).all()

    Eq_tot = Eq_mix + carry_eq
    IM_perp = Gall * Eq_mix / LEV_PERP
    IM_carry_base = short_not / LEV_CARRY_BASE
    IM_carry_cons = short_not / LEV_CARRY_CONS
    IM_tot = IM_perp + IM_carry_base
    IM_tot_cons = IM_perp + IM_carry_cons
    usage_eq = IM_tot / np.maximum(Eq_tot, 1e-12)
    bal_base = Eq_tot - HAIRCUT_BASE * spot_val
    bal_stress = Eq_tot - HAIRCUT_STRESS * spot_val
    usage_bal_base = IM_tot / np.maximum(bal_base, 1e-12)
    usage_bal_stress = IM_tot / np.maximum(bal_stress, 1e-12)
    usage_bal_cons = IM_tot_cons / np.maximum(bal_base, 1e-12)
    IM0 = Gall * Eq_mix / LEV_PERP
    usage0 = IM0 / np.maximum(Eq_mix, 1e-12)
    cost_over = spot_cost / np.maximum(Eq_tot, 1e-12)

    assert bool((bal_base > 0).all()), "base balance must stay positive hourly"
    assert bool((bal_stress > 0).all()), "stress balance must stay positive hourly"

    def pack(u: np.ndarray, extra: dict | None = None):
        d = stats(u)
        if extra:
            d.update(extra)
        return d

    order = np.argsort(-usage_bal_base, kind="stable")[:5]
    worst5 = []
    for i in order:
        i = int(i)
        worst5.append({
            "hour": str(grid[i]),
            "usage_eq": round(float(usage_eq[i]), 4),
            "usage_bal_base": round(float(usage_bal_base[i]), 4),
            "usage_bal_stress": round(float(usage_bal_stress[i]), 4),
            "G2_gross_frac": round(float(Gall[i]), 4),
            "carry_short_frac": round(float(short_not[i] / max(Eq_tot[i], 1e-12)), 4),
            "spot_val_frac": round(float(spot_val[i] / max(Eq_tot[i], 1e-12)), 4),
            "Eq_tot": round(float(Eq_tot[i]), 4),
        })

    out = {
        "meta": {
            "question": "UTA margin usage: G2 (book+dip)/5 + carry short/10, "
                        "spot as collateral; f=0.25 fits one UTA without borrow?",
            "grid": [str(grid[0]), str(grid[-1]), int(n)],
            "cut": "2026-09-24T00:00Z (no data at/after cut)",
            "G2_src": "oc_kpi_g2 events/barsum s=0..3 replayed hourly "
                      "(oc_margin q-units; Hedge gross=|book|+|dip| per coin)",
            "v421_v422_equity_identical_to_barsum": v_ident,
            "carry_src": "oc_cashcarry/results.json 33 entered trades reused "
                         "verbatim (signal/fees/deliveries untouched)",
            "carry_sizing": "legs = f x total mix equity at entry hour "
                            "(oc_carrycombo convention), held to delivery",
            "leverage_perp": LEV_PERP,
            "leverage_perp_src": "docs/BOT_RUNBOOK_VI.md s1 (5x per coin) + "
                                 "oc_margin (minimum never-blocking at cap 2.0)",
            "leverage_carry_base": LEV_CARRY_BASE,
            "leverage_carry_base_src": "docs/BOT_RUNBOOK_VI.md s1 (carry short "
                                       "quarterly 10x, spot-hedged)",
            "leverage_carry_conservative_row": LEV_CARRY_CONS,
            "haircut_base": HAIRCUT_BASE,
            "haircut_base_src": "Bybit UTA help-center BTC/ETH 95% base tier "
                                "via oc_carrycombo REPORT s3 + oc_utamargin "
                                "results.json haircut_src; <10k stays base",
            "haircut_stress": HAIRCUT_STRESS,
            "haircut_stress_src": "assignment-ordered stress: 10% on BTC/ETH spot",
            "blocked_convention": "IM > 95% (oc_margin/oc_utamargin); tight > 80%",
            "denominator": "Eq_tot = Eq_mix + carry MtM (one UTA); "
                           "usage_eq = IM/Eq_tot; usage_bal = IM/(Eq_tot - h*spot)",
            "marks": "hourly_ext 1h closes (G2 perps + spot proxy) + qbasis um_ "
                     "1h quarterly closes, causal (last bar strictly before H)",
            "recon_vs_barsum_gross_book": recon,
            "no_engine_reruns": True,
            "no_network": True,
            "definitions_fixed_before_results": True,
            "post_hoc_changes": "none",
            "f": F,
        },
        "G2_alone_f0": pack(usage0),
        "G2_carry_f0.25_usage_eq": pack(usage_eq),
        "G2_carry_f0.25_bal_base5": pack(usage_bal_base),
        "G2_carry_f0.25_bal_stress10": pack(usage_bal_stress),
        "G2_carry_f0.25_bal_cons5x_carry": pack(usage_bal_cons),
        "spot_cash": {
            "max_spot_cost_over_Eq": round(float(np.max(cost_over)), 4),
            "min_cash_headroom_frac": round(float(np.min(1.0 - cost_over)), 4),
            "n_hours_spot_cost_above_Eq": int(np.sum(cost_over > 1.0)),
        },
        "worst5_hours_by_bal_base": worst5,
    }
    (HERE / "results.json").write_text(json.dumps(out, indent=1))
    for k in ("G2_alone_f0", "G2_carry_f0.25_usage_eq",
              "G2_carry_f0.25_bal_base5", "G2_carry_f0.25_bal_stress10",
              "G2_carry_f0.25_bal_cons5x_carry"):
        print(k, out[k], flush=True)
    print("spot_cash", out["spot_cash"], flush=True)
    print("worst5", worst5, flush=True)


if __name__ == "__main__":
    main()
