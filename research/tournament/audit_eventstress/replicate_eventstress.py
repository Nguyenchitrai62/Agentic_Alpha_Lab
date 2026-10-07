"""Blind audit replication for oc_eventstress (crash-week anatomy G2+carry f=0.25).

Independent re-implementation from header spec in
research/tournament/oc_eventstress/compute_eventstress.py (inputs only) +
frozen inputs:
  G2 = v421/v421_runs.pkl R2B1D17BFG2 (v422 identity check), hourly via
  v388/v388_bot_stop_distance.hourly (eq_min = stored 1m-marked low);
  carry = oc_cashcarry/results.json 33 trades, compounding = oc_carrycompound
  full-pass A(t)=A(t-1)*(E(t)/E(t-1))+dU, N=f*A at entry, f=0.25, causal
  last-CLOSED hourly marks, fee entry-paid 0.00155, settled=ret_alloc;
  dip gross = oc_kpi_g2 events/barsum q-units rebuild (book flats zero,
  dip FIFO, Hedge gross) with hourly_ext marks;
  1m context = data/raw/majors_intraday_20260924 (+ btc_intraday for BTC).
Does NOT import oc_eventstress/compute_eventstress.py and does NOT open
oc_eventstress/REPORT.md or results.json until replication.json is written.

Events replicated (3 of the 5 named): LUNA 2022-05-11, FTX 2022-11-08,
AUG24 2024-08-05. Window anchor-24h..anchor+7d. Metrics per event:
pnl_comb_pct, pnl_g2_pct, dd_close_pct, dd_mark_pct, dip_gross_max,
rec_days (to grid end), trough_hour.

Usage:
  .venv/Scripts/python.exe scripts/heavy_slot.py run --tag audit_eventstress \
    --min-free-gb 2.0 -- .venv/Scripts/python.exe \
    research/tournament/audit_eventstress/replicate_eventstress.py
"""

from __future__ import annotations

import importlib.util
import json
import pickle
from collections import Counter, deque
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
RD = ROOT / "research/parallel/rounds/parallel-20260906-r2"
KPI = ROOT / "research/tournament/oc_kpi_g2"
EXT = ROOT / "research/tournament/ext"
CASH = ROOT / "research/tournament/oc_cashcarry"
QDIR = ROOT / "data/raw/qbasis_20261003"
SDIR = ROOT / "data/raw/spot_majors_20260925"
M1DIR = ROOT / "data/raw/majors_intraday_20260924"

STRAT = "R2B1D17BFG2"
COINS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
F = 0.25
CUT = pd.Timestamp("2026-09-24 00:00", tz="UTC")
GRID0 = pd.Timestamp("2021-09-24 04:00", tz="UTC")
NS_H = 3_600_000_000_000
FEE_PAID = 0.001 + 0.00055
CIX = {c: i for i, c in enumerate(COINS)}
BDELTA = {"book_fill", "book_add", "book_reduce", "book_partial"}
BFLAT = {"book_close", "book_stop", "book_tp"}
REXIT = {"rung_sl", "rung_tp", "rung_timeout"}

EVENTS = [
    ("LUNA", "2022-05-11 00:00"),
    ("FTX", "2022-11-08 00:00"),
    ("AUG24", "2024-08-05 00:00"),
]


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def ffill_before(xt: np.ndarray, xv: np.ndarray, q: np.ndarray):
    # last value with xt < q (strictly before): searchsorted left - 1
    i = np.searchsorted(xt, q, side="left") - 1
    return np.where(i >= 0, xv[np.maximum(i, 0)], np.nan)


def rebuild_gross(ev, bs, marks, grid_ns):
    """Independent q-units rebuild (book flats zero, dip FIFO), vectorized."""
    t = ev["t"].to_numpy(dtype="datetime64[ns]").astype(np.int64)
    sym = ev["symbol"].to_numpy()
    kind = ev["kind"].to_numpy()
    price = ev["price"].to_numpy(float)
    w = ev["weight"].to_numpy(float)
    bt = bs["t"].to_numpy(dtype="datetime64[ns]").astype(np.int64)
    eq = bs["equity"].to_numpy(float)
    ii = np.searchsorted(bt, t, side="right") - 1
    pe = np.where(ii >= 0, eq[np.maximum(ii, 0)], 1.0)
    Qb_grid = np.zeros((len(grid_ns), len(COINS)))
    Qd_grid = np.zeros((len(grid_ns), len(COINS)))
    for c, j in CIX.items():
        m = sym == c
        order = np.argsort(t[m], kind="stable")
        idxm = np.where(m)[0][order]
        qb = 0.0
        tus, qus = [], []
        for k in idxm:
            kk = kind[k]
            if kk in BDELTA:
                dq = w[k] / price[k] if kk == "book_fill" else w[k] * pe[k] / price[k]
                qb += dq
            elif kk in BFLAT:
                qb = 0.0
            else:
                continue
            tus.append(t[k])
            qus.append(qb)
        if tus:
            tu = np.array(tus)
            qu = np.array(qus)
            # keep last per timestamp
            keep = np.ones(len(tu), bool)
            # last occurrence wins: mark all but last of equal run as drop
            for a in range(len(tu) - 1):
                if tu[a] == tu[a + 1]:
                    keep[a] = False
            tu, qu = tu[keep], qu[keep]
            pos = np.searchsorted(tu, grid_ns, side="right") - 1
            Qb_grid[:, j] = np.where(pos >= 0, qu[np.maximum(pos, 0)], 0.0)
        fills, exits = [], []
        for k in idxm:
            if kind[k] == "rung_fill":
                fills.append((t[k], w[k] / price[k]))
            elif kind[k] in REXIT:
                exits.append(t[k])
        fills.sort()
        exits.sort()
        nx = Counter(exits)
        pts = sorted(set([f[0] for f in fills]) | set(nx))
        q = deque()
        fi = 0
        ptt, qtt = [], []
        for x in pts:
            while fi < len(fills) and fills[fi][0] <= x:
                q.append(fills[fi][1])
                fi += 1
            for _ in range(nx[x]):
                if q:
                    q.popleft()
            ptt.append(x)
            qtt.append(float(sum(q)))
        if ptt:
            ptt = np.array(ptt)
            qtt = np.array(qtt)
            pos = np.searchsorted(ptt, grid_ns, side="right") - 1
            Qd_grid[:, j] = np.where(pos >= 0, qtt[np.maximum(pos, 0)], 0.0)
    iu2 = np.searchsorted(bt, grid_ns, side="right") - 1
    equity_g = np.where(iu2 >= 0, eq[np.maximum(iu2, 0)], 1.0)
    bi = np.maximum(iu2, 0)
    eqs = np.where(bi > 0, eq[bi - 1], 1.0)
    Fb = np.zeros_like(Qb_grid)
    Fd = np.zeros_like(Qd_grid)
    for c, j in CIX.items():
        mt, mv = marks[c]
        mk = ffill_before(mt, mv, grid_ns - NS_H)
        mk = np.where(np.isnan(mk), mv[0], mk)
        Fb[:, j] = Qb_grid[:, j] * mk * eqs / np.maximum(equity_g, 1e-12)
        Fd[:, j] = Qd_grid[:, j] * mk * eqs / np.maximum(equity_g, 1e-12)
    return Fb, Fd, equity_g


def main() -> None:
    v388 = _load("v388_for_rep", RD / "v388/v388_bot_stop_distance.py")
    g1 = v388.Y1 + pd.Timedelta(hours=12)
    grid = pd.date_range(GRID0, g1, freq="1h")
    gn = grid.values.astype("datetime64[ns]").astype(np.int64)
    n = len(grid)
    print(f"grid {grid[0]}..{grid[-1]} n={n}", flush=True)

    r421 = pickle.loads((RD / "v421/v421_runs.pkl").read_bytes())
    r422 = pickle.loads((RD / "v422/v422_runs.pkl").read_bytes())
    ident = all(
        bool(np.array_equal(np.asarray(r421[s][STRAT]["eq"]), np.asarray(r422[s][STRAT]["eq"])))
        for s in range(4)
    )
    print(f"v421==v422 {ident}", flush=True)
    assert ident

    Es, Ms = [], []
    for s in range(4):
        e1, m1 = v388.hourly(r421[s][STRAT], GRID0, g1)
        assert (e1.index == grid).all()
        Es.append(e1.to_numpy(float))
        Ms.append(np.asarray(m1, float))
    Es = np.stack(Es)
    Ms = np.stack(Ms)
    Etot = Es.mean(0)
    Mtot = Ms.mean(0)

    h = pd.read_parquet(EXT / "hourly_ext.parquet", columns=["t", "close", "sym"])
    h["t"] = pd.to_datetime(h["t"], utc=True)
    h = h[h["t"] < CUT + pd.Timedelta(days=1)]
    marks = {}
    for c in COINS:
        d = h[h["sym"] == c].sort_values("t")
        marks[c] = (
            d["t"].values.astype("datetime64[ns]").astype(np.int64),
            d["close"].to_numpy(float),
        )

    cc = json.loads((CASH / "results.json").read_text())
    assert len(cc["trades"]) == 33, len(cc["trades"])
    spot = {}
    for coin in ("BTC", "ETH"):
        d = h[h["sym"] == f"{coin}USDT"].sort_values("t")
        spot[coin] = (
            d["t"].values.astype("datetime64[ns]").astype(np.int64),
            d["close"].to_numpy(float),
        )
    qmap = {}
    for tr in cc["trades"]:
        key = (tr["coin"], tr["delivery"])
        if key in qmap:
            continue
        y, m, dd = tr["delivery"].split("-")
        code = f"{y[2:]}{m}{dd}"
        (f,) = sorted(QDIR.glob(f"um_{tr['coin']}USDT_{code}_1h.parquet"))
        q = pd.read_parquet(f, columns=["open_time", "close"])
        qo = pd.to_datetime(q["open_time"], utc=True).values.astype("datetime64[ns]").astype(np.int64)
        o = np.argsort(qo)
        qmap[key] = (qo[o], q["close"].to_numpy(float)[o])
    s4 = pd.read_parquet(SDIR / "BTCUSDT_spot_4h.parquet", columns=["open_time", "close_time"])
    s4c = pd.to_datetime(s4["close_time"], utc=True)
    trades = []
    for tr in cc["trades"]:
        te = pd.Timestamp(tr["entry_open"], tz="UTC")
        tc = te + pd.Timedelta(hours=4)
        D = pd.Timestamp(tr["delivery"] + " 08:00", tz="UTC")
        si = int(np.searchsorted(s4c.values.astype("datetime64[ns]").astype(np.int64), D.value, side="right"))
        ts = s4c.iloc[si]
        trades.append(
            {
                "coin": tr["coin"],
                "delivery": tr["delivery"],
                "F_entry": float(tr["F_entry"]),
                "S_entry": float(tr["S_entry"]),
                "ret_alloc": float(tr["ret_alloc"]),
                "tc_ns": tc.value,
                "ts_ns": ts.value,
            }
        )
    for tr in trades:
        st, sc = spot[tr["coin"]]
        ft, fc = qmap[(tr["coin"], tr["delivery"])]
        S = ffill_before(st, sc, gn)
        Fq = ffill_before(ft, fc, gn)
        with np.errstate(divide="ignore", invalid="ignore"):
            mtm = (S / tr["S_entry"] - 1.0) + ((tr["F_entry"] - Fq) / tr["F_entry"]) - FEE_PAID
        mtm[~np.isfinite(mtm)] = np.nan
        mtm = pd.Series(mtm, index=grid).ffill().to_numpy()
        v = np.zeros(n)
        open_m = gn > tr["tc_ns"]
        settled_m = gn >= tr["ts_ns"]
        hold_m = open_m & ~settled_m
        v[hold_m] = mtm[hold_m]
        v[hold_m & ~np.isfinite(mtm)] = 0.0
        v[settled_m] = tr["ret_alloc"]
        tr["mtm"] = v

    rel_c = [k for k, tr in enumerate(trades) if tr["ts_ns"] > gn[0]]
    span_c = {k for k in rel_c if trades[k]["tc_ns"] <= gn[0]}
    N_c = {k: F * float(Etot[0]) for k in span_c}
    mtm_r = {k: trades[k]["mtm"] - trades[k]["mtm"][0] for k in rel_c}
    tc_pos: dict[int, list[int]] = {}
    for k in rel_c:
        if k in span_c:
            continue
        pos = int(np.searchsorted(gn, trades[k]["tc_ns"], side="right"))
        if 0 <= pos < n:
            tc_pos.setdefault(pos, []).append(k)
    A_c = np.empty(n)
    M_c = np.empty(n)
    A_c[0], M_c[0] = float(Etot[0]), float(Mtot[0])
    A_prev, U_prev = float(Etot[0]), 0.0
    U_open: dict[int, float] = dict(N_c)
    for i in range(1, n):
        for k in tc_pos.get(i, []):
            U_open[k] = F * A_prev
        U_i = sum(nk * mtm_r[k][i] for k, nk in U_open.items())
        dU = U_i - U_prev
        A_c[i] = A_prev * (Etot[i] / Etot[i - 1]) + dU
        M_c[i] = A_prev * (Mtot[i] / Etot[i - 1]) + dU
        A_prev, U_prev = A_c[i], U_i

    # dip-gross rebuild per phase
    Fb_s, Fd_s, Eq_s = {}, {}, {}
    for s in range(4):
        ev = pd.read_parquet(KPI / f"events_s{s}.parquet")
        ev["t"] = pd.to_datetime(ev["t"], utc=True)
        assert bool((ev["t"] < CUT).all())
        bs = pd.read_parquet(KPI / f"barsum_s{s}.parquet")
        bs["t"] = pd.to_datetime(bs["t"], utc=True)
        Fb, Fd, E = rebuild_gross(ev, bs, marks, gn)
        Fb_s[s], Fd_s[s], Eq_s[s] = Fb, Fd, E
    Eq = np.stack([Eq_s[s] for s in range(4)])
    Gsym = {c: np.zeros(n) for c in COINS}
    Dsym = {c: np.zeros(n) for c in COINS}
    for j, c in enumerate(COINS):
        num_g = sum((np.abs(Fb_s[s][:, j]) + np.abs(Fd_s[s][:, j])) * Eq_s[s] for s in range(4))
        num_d = sum(np.abs(Fd_s[s][:, j]) * Eq_s[s] for s in range(4))
        Gsym[c] = num_g / np.maximum(Eq.sum(0), 1e-12)
        Dsym[c] = num_d / np.maximum(Eq.sum(0), 1e-12)
    Dall = sum(Dsym.values())
    print(f"max Dall {Dall.max():.3f}", flush=True)

    # 1m coverage check (no values used for P&L)
    def m1_exists(a0, a1):
        yrs = sorted({a0.year, a1.year})
        ok = True
        for c in COINS:
            for y in yrs:
                if c == "BTCUSDT":
                    p = ROOT / "data/raw/btc_intraday_20260924" / f"klines_1m_{y}.parquet"
                    if not p.exists():
                        p = M1DIR / f"{c}_1m_{y}.parquet"
                else:
                    p = M1DIR / f"{c}_1m_{y}.parquet"
                if not p.exists():
                    ok = False
        return ok

    out_events = []
    for key, anchor_s in EVENTS:
        anchor = pd.Timestamp(anchor_s, tz="UTC")
        t0, t1 = anchor - pd.Timedelta(hours=24), anchor + pd.Timedelta(days=7)
        i0 = max(int(np.searchsorted(gn, t0.value, side="right") - 1), 0)
        i1 = min(int(np.searchsorted(gn, t1.value, side="right") - 1), n - 1)
        ia = int(np.searchsorted(gn, anchor.value, side="left"))
        preA, endA = float(A_c[i0]), float(A_c[i1])
        preG, endG = float(Etot[i0]), float(Etot[i1])
        segA = A_c[i0 : i1 + 1]
        segM = M_c[i0 : i1 + 1]
        peak = float(np.max(segA))
        dd_close = round(float(100 * (1 - np.min(segA) / peak)), 2)
        dd_mark = round(float(100 * (1 - np.min(segM) / peak)), 2)
        trough = str(grid[i0 + int(np.argmin(segM))])
        rec = 0.0
        inwin = A_c[ia : i1 + 1]
        breach = np.where(inwin < preA)[0]
        if len(breach):
            post = A_c[ia + int(breach[0]) :]
            back = np.where(post >= preA)[0]
            rec = (
                round(float((grid[ia + int(breach[0]) + int(back[0])] - anchor).total_seconds() / 86400), 2)
                if len(back)
                else None
            )
        sl = slice(i0, i1 + 1)
        dip_max = round(float(np.max(Dall[sl])), 3)
        dip_hour = str(grid[i0 + int(np.argmax(Dall[sl]))])
        out_events.append(
            {
                "key": key,
                "anchor": str(anchor),
                "window": [str(grid[i0]), str(grid[i1])],
                "pnl_comb_pct": round(100 * (endA / preA - 1), 2),
                "pnl_g2_pct": round(100 * (endG / preG - 1), 2),
                "dd_close_pct": dd_close,
                "dd_mark_pct": dd_mark,
                "trough_hour": trough,
                "rec_days": rec,
                "dip_gross_max": dip_max,
                "dip_gross_hour": dip_hour,
                "m1_coverage_ok": bool(m1_exists(t0, t1)),
            }
        )
        print(f"{key}: pnl {out_events[-1]['pnl_comb_pct']:+.2f}% dd_mark {dd_mark:.2f}% dip {dip_max:.3f} rec {rec}", flush=True)

    out = {
        "meta": {
            "blind": True,
            "note": "independent replication; written before opening oc_eventstress REPORT/results",
            "grid": [str(grid[0]), str(grid[-1]), int(n)],
            "f": F,
            "v421_v422_identical": bool(ident),
            "event_window": "anchor-24h..anchor+7d; recovery searched to grid end",
            "inputs": "v421_runs.pkl R2B1D17BFG2 via v388.hourly; oc_cashcarry 33 trades; hourly_ext+qbasis um_*; oc_kpi_g2 events/barsum",
        },
        "events": out_events,
    }
    (HERE / "replication.json").write_text(json.dumps(out, indent=1))
    print("wrote replication.json", flush=True)


if __name__ == "__main__":
    main()
