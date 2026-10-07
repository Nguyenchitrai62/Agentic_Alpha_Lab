"""oc_eventstress: crash-week anatomy for G2 + carry f=0.25 (BOT product).

Assignment: docs/opencode/OPENCODE_W_oc_eventstress.md. Research only,
MEDIUM, no engine reruns (stored runs suffice), one process, read-only
inputs. Writes results.json (+ REPORT.md by hand) in this folder only.

Frozen inputs (nothing refit):
- G2 = R2B1D17BFG2 from research/parallel/rounds/parallel-20260906-r2/v421/
  v421_runs.pkl (v422 row verified identical). Hourly close/marked equity via
  the exact v388.hourly() wiring (eq_min = stored 1m-marked intrabar low).
- Carry = 33 frozen oc_cashcarry pairs. P&L uses the ACCOUNT-REALISTIC
  compounding of oc_carrycompound (A(t)=A(t-1)*(1+r_bot)+dU, notionals
  f x live A, f=0.25). Margin uses the oc_carrymargin convention verbatim
  (legs f x mix equity at entry, IM perp G/5 + carry short/10, balance =
  Eq - haircut x spot; tiers frozen from oc_utamargin, no network).
- G2 legs rebuilt HOURLY from stored oc_kpi_g2 events/barsum with the exact
  oc_margin q-units math (book flats zero, dip FIFO, Hedge gross).
- Market context from local 1m klines (data/raw/majors_intraday_20260924).
- Earlier crash tables reused, not recomputed: oc_crash2020 (2020-21 tails),
  oc_crashfreq (one-bar dip losses), oc_ddanat4p/oc_ddanat_g2 (gate anatomy),
  oc_stresshist (named stress weeks), oc_gapstress (instant gaps).

Events (anchor UTC, window = [anchor-24h, anchor+7d]):
  named: LUNA 2022-05-11, 3AC/Celsius 2022-06-13, FTX 2022-11-08,
         USDC-depeg 2023-03-11, 2024-08-05 crash;
  + 5 largest 24h drops of the BTC+ETH basket (mean of the two 24h returns,
    hourly_ext closes, ends in 2021-09-24..2026-09-23, greedy >=24h apart).

Per event: G2+carry and G2-only P&L pre->+7d, close DD, 1m-marked DD
(stored eq_min marks), trough hour, max dip gross (rebuild), worst UTA
margin usage (oc_carrymargin method: usage_eq / bal base-5% / stress-10% /
conservative short/5x), tiered MM breach + blocked flags, stops observed
(book_stop+rung_sl from stored events), recovery days to pre-event equity
(searched to grid end).

Usage: .venv/Scripts/python.exe research/tournament/oc_eventstress/compute_eventstress.py
"""

from __future__ import annotations

import importlib.util
import json
import pickle
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
RD = ROOT / "research/parallel/rounds/parallel-20260906-r2"
KPI = ROOT / "research/tournament/oc_kpi_g2"
EXT = ROOT / "research/tournament/ext"
CASH = ROOT / "research/tournament/oc_cashcarry"
CC = ROOT / "research/tournament/oc_carrycompound"
UTA = ROOT / "research/tournament/oc_utamargin"
QDIR = ROOT / "data/raw/qbasis_20261003"
SDIR = ROOT / "data/raw/spot_majors_20260925"
M1DIR = ROOT / "data/raw/majors_intraday_20260924"

STRAT = "R2B1D17BFG2"
COINS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
CARRY_COINS = ["BTC", "ETH"]
F = 0.25
CUT = pd.Timestamp("2026-09-24 00:00", tz="UTC")
GRID0 = pd.Timestamp("2021-09-24 04:00", tz="UTC")
NS_H = 3_600_000_000_000
A0 = 10000.0
LEV_PERP, LEV_CARRY_BASE, LEV_CARRY_CONS = 5, 10, 5
HAIRCUT_BASE, HAIRCUT_STRESS = 0.05, 0.10
FEE_ENTRY_PAID = 0.001 + 0.00055
CIX = {c: i for i, c in enumerate(COINS)}
BOOK_DELTA = {"book_fill", "book_add", "book_reduce", "book_partial"}
BOOK_FLAT = {"book_close", "book_stop", "book_tp"}
RUNG_EXIT = {"rung_sl", "rung_tp", "rung_timeout"}
STOP_KINDS = {"book_stop", "rung_sl"}

NAMED = [
    ("LUNA", "2022-05-11 00:00", "LUNA/UST collapse May 2022"),
    ("3AC", "2022-06-13 00:00", "3AC/Celsius freeze Jun 2022"),
    ("FTX", "2022-11-08 00:00", "FTX collapse Nov 2022"),
    ("USDC", "2023-03-11 00:00", "USDC depeg / SVB Mar 2023"),
    ("AUG24", "2024-08-05 00:00", "yen-carry crash 5 Aug 2024"),
]


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def ffill_at(xt: np.ndarray, xv: np.ndarray, q: np.ndarray):
    i = np.searchsorted(xt, q, side="right") - 1
    return np.where(i >= 0, xv[np.maximum(i, 0)], np.nan), i


def last_close_before(times_ns: np.ndarray, closes: np.ndarray,
                       ts_ns: np.ndarray) -> np.ndarray:
    idx = np.searchsorted(times_ns, ts_ns, side="left") - 1
    out = np.full(len(ts_ns), np.nan)
    ok = idx >= 0
    out[ok] = closes[idx[ok]]
    return out


def mm_of(value_usdt: float, tiers: list[dict]) -> tuple[float, int]:
    for i, t in enumerate(tiers):
        if value_usdt <= float(t["limit"]):
            return value_usdt * float(t["mmr"]) - float(t.get("deduct", 0.0)), i
    t = tiers[-1]
    return value_usdt * float(t["mmr"]) - float(t.get("deduct", 0.0)), len(tiers) - 1


def build_hourly_state(ev, bs, marks, grid_ns):
    """oc_carrymargin/compute_carrymargin.py verbatim math (q-units replay)."""
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
    for c, j in CIX.items():
        mt, mv = marks[c]
        mk, _ = ffill_at(mt, mv, U - NS_H)
        mk = np.where(np.isnan(mk), mv[0], mk)
        Fb[:, j] = Qb[:, j] * mk * eqs / equity
        Fd[:, j] = Qd[:, j] * mk * eqs / equity
    iu = np.searchsorted(U, grid_ns, side="right") - 1
    iu = np.maximum(iu, 0)
    gi = np.maximum(np.searchsorted(U, grid_ns, side="right") - 1, 0)
    return Fb[iu], Fd[iu], equity[gi]


def main() -> None:
    v388 = _load("v388_for_eventstress", RD / "v388/v388_bot_stop_distance.py")
    g1 = v388.Y1 + pd.Timedelta(hours=12)
    grid = pd.date_range(GRID0, g1, freq="1h")
    gn = grid.values.astype("datetime64[ns]").astype(np.int64)
    n = len(grid)
    print(f"grid {grid[0]} .. {grid[-1]} n={n}", flush=True)

    # ---- G2 stored runs (v421 primary, v422 identity check) ----
    r421 = pickle.loads((RD / "v421/v421_runs.pkl").read_bytes())
    r422 = pickle.loads((RD / "v422/v422_runs.pkl").read_bytes())
    ident = all(bool(np.array_equal(np.asarray(r421[s][STRAT]["eq"]),
                                   np.asarray(r422[s][STRAT]["eq"])))
                for s in range(4))
    print(f"v421==v422 {STRAT} equity: {ident}", flush=True)
    assert ident, "v421/v422 G2 runs differ"
    exp421 = json.loads((RD / "v421/v421_result.json").read_text())["rows"][STRAT]

    Es, Ms = [], []
    for s in range(4):
        e1, m1 = v388.hourly(r421[s][STRAT], GRID0, g1)
        assert (e1.index == grid).all()
        Es.append(e1.to_numpy(dtype=float))
        Ms.append(np.asarray(m1, dtype=float))
    Es = np.stack(Es)
    Ms = np.stack(Ms)
    Etot = Es.mean(axis=0)
    Mtot = Ms.mean(axis=0)
    seg = np.asarray(grid >= pd.Timestamp("2021-09-24", tz="UTC"))
    dd_full = float(np.max(1 - Mtot[seg] / np.maximum.accumulate(Etot[seg])))
    print(f"G2-only full-path DD {dd_full * 100:.2f} vs v421 {exp421['full_path_dd']}",
          flush=True)
    assert abs(dd_full * 100 - exp421["full_path_dd"]) < 0.05

    # ---- marks (hourly_ext, causal) ----
    h = pd.read_parquet(EXT / "hourly_ext.parquet", columns=["t", "close", "sym"])
    h["t"] = pd.to_datetime(h["t"], utc=True)
    h = h[h["t"] < CUT + pd.Timedelta(days=1)]
    marks = {}
    for c in COINS:
        d = h[h["sym"] == c].sort_values("t")
        marks[c] = (d["t"].values.astype("datetime64[ns]").astype(np.int64),
                    d["close"].to_numpy(dtype=float))

    # ---- basket: 5 largest 24h drops of mean(BTC,ETH 24h ret) ----
    piv = {}
    for c in ("BTCUSDT", "ETHUSDT"):
        d = h[h["sym"] == c].sort_values("t").drop_duplicates("t")
        piv[c] = pd.Series(d["close"].to_numpy(float),
                           index=pd.to_datetime(d["t"], utc=True))
    bh = pd.DataFrame(piv).sort_index()
    bh = bh[(bh.index >= pd.Timestamp("2021-09-24", tz="UTC")) & (bh.index <= g1)]
    bh = bh.asfreq("1h").ffill()
    r24 = bh / bh.shift(24) - 1.0
    basket = r24.mean(axis=1).dropna()
    basket = basket[(basket.index >= pd.Timestamp("2021-09-25", tz="UTC"))]
    cands = basket.sort_values()
    drops, taken = [], []
    for ts, v in cands.items():
        if all(abs((ts - t).total_seconds()) >= 24 * 3600 for t in taken):
            drops.append((ts, float(v), float(r24.loc[ts, "BTCUSDT"]),
                          float(r24.loc[ts, "ETHUSDT"])))
            taken.append(ts)
        if len(drops) == 5:
            break
    drops.sort(key=lambda r: r[1])
    print("basket drops:", [(str(t), round(v * 100, 2)) for t, v, _, _ in drops],
          flush=True)

    # ---- carry: compounding P&L pass (oc_carrycompound full-pass verbatim) ----
    cc = json.loads((CASH / "results.json").read_text())
    assert len(cc["trades"]) == 33
    spot = {}
    for coin in CARRY_COINS:
        d = h[h["sym"] == f"{coin}USDT"].sort_values("t")
        spot[coin] = (d["t"].values.astype("datetime64[ns]").astype(np.int64),
                      d["close"].to_numpy(dtype=float))
    qmap = {}
    for t in cc["trades"]:
        key = (t["coin"], t["delivery"])
        if key in qmap:
            continue
        y, m, dd = t["delivery"].split("-")
        code = f"{y[2:]}{m}{dd}"
        (f,) = sorted(QDIR.glob(f"um_{t['coin']}USDT_{code}_1h.parquet"))
        q = pd.read_parquet(f, columns=["open_time", "close"])
        qo = pd.to_datetime(q["open_time"], utc=True).values.astype(
            "datetime64[ns]").astype(np.int64)
        o = np.argsort(qo)
        qmap[key] = (qo[o], q["close"].to_numpy(dtype=float)[o])
    s4 = pd.read_parquet(SDIR / "BTCUSDT_spot_4h.parquet",
                         columns=["open_time", "close_time"])
    s4o = pd.to_datetime(s4["open_time"], utc=True)
    s4c = pd.to_datetime(s4["close_time"], utc=True)
    trades = []
    for t in cc["trades"]:
        te = pd.Timestamp(t["entry_open"], tz="UTC")
        tc = te + pd.Timedelta(hours=4)
        assert (s4o == te).any(), t
        D = pd.Timestamp(t["delivery"] + " 08:00", tz="UTC")
        si = int(np.searchsorted(s4c.values.astype("datetime64[ns]").astype(np.int64),
                                 D.value, side="right"))
        ts = s4c.iloc[si]
        trades.append({"coin": t["coin"], "delivery": t["delivery"],
                       "F_entry": float(t["F_entry"]), "S_entry": float(t["S_entry"]),
                       "ret_alloc": float(t["ret_alloc"]),
                       "tc_ns": tc.value, "ts_ns": ts.value})
    for tr in trades:
        st, sc = spot[tr["coin"]]
        ft, fc = qmap[(tr["coin"], tr["delivery"])]
        S = last_close_before(st, sc, gn)
        Fq = last_close_before(ft, fc, gn)
        with np.errstate(divide="ignore", invalid="ignore"):
            mtm = ((S / tr["S_entry"] - 1.0)
                   + ((tr["F_entry"] - Fq) / tr["F_entry"]) - FEE_ENTRY_PAID)
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

    # spanning positions at grid start get fixed notionals (carrycompound full-pass)
    rel_c = [k for k, tr in enumerate(trades) if tr["ts_ns"] > gn[0]]
    span_c = {k for k in rel_c if trades[k]["tc_ns"] <= gn[0]}
    N_c: dict[int, float] = {k: F * float(Etot[0]) for k in span_c}
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
        U_i = 0.0
        for k, nk in U_open.items():
            U_i += nk * mtm_r[k][i]
        dU = U_i - U_prev
        A_c[i] = A_prev * (Etot[i] / Etot[i - 1]) + dU
        M_c[i] = A_prev * (Mtot[i] / Etot[i - 1]) + dU
        A_prev, U_prev = A_c[i], U_i
    # f=0 reference level: compounding with no carry == Etot scale
    print(f"A_c end {A_c[-1]:.4f} vs Etot end {Etot[-1]:.4f}", flush=True)

    # ---- G2 hourly rebuild (oc_carrymargin math) + carrymargin-style legs ----
    Fb_s, Fd_s, Eq_s = {}, {}, {}
    ev_all = []
    for s in range(4):
        ev = pd.read_parquet(KPI / f"events_s{s}.parquet")
        ev["t"] = pd.to_datetime(ev["t"], utc=True)
        assert (ev["t"] < CUT).all()
        bs = pd.read_parquet(KPI / f"barsum_s{s}.parquet")
        bs["t"] = pd.to_datetime(bs["t"], utc=True)
        Fb, Fd, E = build_hourly_state(ev, bs, marks, gn)
        Fb_s[s], Fd_s[s], Eq_s[s] = Fb, Fd, E
        ev_all.append(ev[["t", "kind"]])
    Eq = np.stack([Eq_s[s] for s in range(4)])
    Eq_mix = Eq.mean(0)
    Gsym = {c: np.zeros(n) for c in COINS}
    Dsym = {c: np.zeros(n) for c in COINS}
    for j, c in enumerate(COINS):
        num_g = sum((np.abs(Fb_s[s][:, j]) + np.abs(Fd_s[s][:, j])) * Eq_s[s]
                    for s in range(4))
        num_d = sum(np.abs(Fd_s[s][:, j]) * Eq_s[s] for s in range(4))
        Gsym[c] = num_g / np.maximum(Eq.sum(0), 1e-12)
        Dsym[c] = num_d / np.maximum(Eq.sum(0), 1e-12)
    Gall = sum(Gsym.values())
    Dall = sum(Dsym.values())
    print(f"max Gall {Gall.max():.3f} max Dall {Dall.max():.3f}", flush=True)

    # carry legs, oc_carrymargin convention (f x mix equity at entry)
    cTr = []
    for r in cc["trades"]:
        cTr.append({"coin": r["coin"], "delivery": r["delivery"],
                    "entry_open": pd.Timestamp(r["entry_open"], tz="UTC"),
                    "F_entry": float(r["F_entry"]), "S_entry": float(r["S_entry"]),
                    "ret_alloc": float(r["ret_alloc"]),
                    "D": pd.Timestamp(r["delivery"] + " 08:00", tz="UTC")})
    spot_px = {}
    for c in CARRY_COINS:
        mt, mv = marks[c + "USDT"]
        i = np.searchsorted(mt, gn - NS_H, side="right") - 1
        spot_px[c] = np.where(i >= 0, mv[np.maximum(i, 0)], np.nan)
    qh = {}
    for coin in CARRY_COINS:
        import glob as _glob
        import re as _re
        qh[coin] = {}
        for f in sorted(_glob.glob(str(QDIR / f"um_{coin}USDT_*_1h.parquet"))):
            m = _re.search(r"_(\d{6})_1h\.parquet$", f)
            D = f"20{m.group(1)[:2]}-{m.group(1)[2:4]}-{m.group(1)[4:6]}"
            d = pd.read_parquet(f, columns=["open_time", "close"])
            ot = pd.to_datetime(d["open_time"], utc=True).to_numpy(
                dtype="datetime64[ns]").astype(np.int64)
            o = np.argsort(ot)
            qh[coin][D] = (ot[o], d["close"].to_numpy(float)[o])
    fut_px = {}
    for r in cTr:
        key = (r["coin"], r["delivery"])
        if key not in fut_px:
            ot, cl = qh[r["coin"]][r["delivery"]]
            i = np.searchsorted(ot, gn - NS_H, side="right") - 1
            fut_px[key] = np.where(i >= 0, cl[np.maximum(i, 0)], np.nan)
    Te = np.array([r["entry_open"].value for r in cTr])
    Dd = np.array([r["D"].value for r in cTr])
    Eq_entry = np.array([float(Eq_mix[max(np.searchsorted(gn, t, side="right") - 1, 0)])
                         for t in Te])
    spot_val = np.zeros(n)
    spot_cost = np.zeros(n)
    short_not = np.zeros(n)
    short_by_coin = {c: np.zeros(n) for c in CARRY_COINS}
    carry_eq_m = np.zeros(n)
    for k, r in enumerate(cTr):
        S = np.where(np.isnan(spot_px[r["coin"]]), r["S_entry"], spot_px[r["coin"]])
        Fraw = fut_px[(r["coin"], r["delivery"])]
        Fraw = np.where(np.isnan(Fraw), r["F_entry"], Fraw)
        open_m = (gn >= Te[k]) & (gn < Dd[k])
        shut_m = (gn >= Dd[k])
        qty_s = F * Eq_entry[k] / r["S_entry"]
        qty_f = F * Eq_entry[k] / r["F_entry"]
        spot_val += np.where(open_m, qty_s * S, 0.0)
        spot_cost += np.where(open_m, F * Eq_entry[k], 0.0)
        short_not += np.where(open_m, qty_f * Fraw, 0.0)
        short_by_coin[r["coin"]] += np.where(open_m, qty_f * Fraw, 0.0)
        upnl = (qty_s * (S - r["S_entry"]) + qty_f * (r["F_entry"] - Fraw)
                - F * Eq_entry[k] * FEE_ENTRY_PAID)
        carry_eq_m += np.where(open_m, upnl, 0.0)
        carry_eq_m += np.where(shut_m, F * Eq_entry[k] * r["ret_alloc"], 0.0)
    Eq_tot_m = Eq_mix + carry_eq_m
    IM = Gall * Eq_mix / LEV_PERP + short_not / LEV_CARRY_BASE
    IM_cons = Gall * Eq_mix / LEV_PERP + short_not / LEV_CARRY_CONS
    usage_eq = IM / np.maximum(Eq_tot_m, 1e-12)
    bal_base = Eq_tot_m - HAIRCUT_BASE * spot_val
    bal_stress = Eq_tot_m - HAIRCUT_STRESS * spot_val
    u_bal = IM / np.maximum(bal_base, 1e-12)
    u_stress = IM / np.maximum(bal_stress, 1e-12)
    u_cons = IM_cons / np.maximum(bal_base, 1e-12)
    assert bool((bal_base > 0).all()) and bool((bal_stress > 0).all())
    tiers = json.loads((UTA / "results.json").read_text())["tiers"]

    evCat = pd.concat(ev_all, ignore_index=True)

    def m1_path(c: str, y: int) -> Path | None:
        if c == "BTCUSDT":
            p = ROOT / "data/raw/btc_intraday_20260924" / f"klines_1m_{y}.parquet"
        else:
            p = M1DIR / f"{c}_1m_{y}.parquet"
        return p if p.exists() else None

    def m1_stats(a_start: pd.Timestamp, a_end: pd.Timestamp):
        """Local 1m marks over [a_start, a_end]: worst lows vs first close."""
        yrs = sorted({a_start.year, a_end.year})
        per, cov_ok = {}, True
        btc_bars = []
        for c in COINS:
            frames = []
            for y in yrs:
                fp = m1_path(c, y)
                if fp is None:
                    cov_ok = False
                    continue
                d = pd.read_parquet(fp, columns=["open_time", "open", "high",
                                                "low", "close"])
                d["open_time"] = pd.to_datetime(d["open_time"], utc=True)
                d = d[(d["open_time"] >= a_start) & (d["open_time"] <= a_end)]
                frames.append(d)
            if not frames:
                cov_ok = False
                continue
            d = pd.concat(frames).sort_values("open_time")
            ref = float(d["close"].iloc[0])
            per[c] = {"worst_low_pct": round(100 * (float(d["low"].min()) / ref - 1), 2),
                      "close_end_pct": round(100 * (float(d["close"].iloc[-1]) / ref - 1), 2),
                      "n_bars": int(len(d))}
            if c == "BTCUSDT":
                btc_bars = (d["close"] / d["open"] - 1.0).to_numpy()
        btc_worst_1m = round(100 * float(np.min(btc_bars)), 3) if len(btc_bars) else None
        worst_coin = min(per.items(), key=lambda kv: kv[1]["worst_low_pct"])[0] if per else None
        return {"coverage_ok": bool(cov_ok and len(per) == 5),
                "btc_worst_1m_pct": btc_worst_1m,
                "worst_coin_low": worst_coin,
                "worst_coin_low_pct": per[worst_coin]["worst_low_pct"] if worst_coin else None,
                "per_coin_low_pct": {c: per[c]["worst_low_pct"] for c in per}}

    events = []
    for key, anchor_s, label in NAMED:
        anchor = pd.Timestamp(anchor_s, tz="UTC")
        events.append((key, label, anchor, None))
    for i, (ts, v, b, e) in enumerate(drops):
        anchor = pd.Timestamp(ts).tz_convert("UTC")
        events.append((f"DROP{i + 1}", f"basket 24h {v * 100:.1f}% end {ts:%Y-%m-%d %H:%M}Z",
                       anchor, {"basket_24h_pct": round(v * 100, 2),
                                "btc_24h_pct": round(b * 100, 2),
                                "eth_24h_pct": round(e * 100, 2)}))

    rows = []
    for key, label, anchor, drop in events:
        t0, t1 = anchor - pd.Timedelta(hours=24), anchor + pd.Timedelta(days=7)
        i0 = int(np.searchsorted(gn, t0.value, side="right") - 1)
        i1 = int(np.searchsorted(gn, t1.value, side="right") - 1)
        ia = int(np.searchsorted(gn, anchor.value, side="left"))
        i0, i1 = max(i0, 0), min(i1, n - 1)
        preA, endA = float(A_c[i0]), float(A_c[i1])
        preG, endG = float(Etot[i0]), float(Etot[i1])
        segA = A_c[i0:i1 + 1]
        segM = M_c[i0:i1 + 1]
        segE = Etot[i0:i1 + 1]
        peak = float(np.max(segA))
        dd_close = float(100 * (1 - np.min(segA) / peak))
        dd_mark = float(100 * (1 - np.min(segM) / peak))
        trough = str(grid[i0 + int(np.argmin(segM))])
        # recovery: first breach of pre-event equity inside the window, then
        # first return to it (0.0 = never went under in-window; null = never)
        rec = 0.0
        inwin = A_c[ia:i1 + 1]
        breach = np.where(inwin < preA)[0]
        if len(breach):
            post = A_c[ia + int(breach[0]):]
            back = np.where(post >= preA)[0]
            rec = (round(float((grid[ia + int(breach[0]) + int(back[0])] - anchor)
                               .total_seconds() / 86400), 2)
                   if len(back) else None)
        m = (evCat["t"] > (anchor - pd.Timedelta(hours=24))) & \
            (evCat["t"] <= (anchor + pd.Timedelta(days=7)))
        w = evCat[m]
        n_stop = int(w["kind"].isin(STOP_KINDS).sum())
        n_tp = int(w["kind"].isin({"book_tp", "rung_tp"}).sum())
        n_to = int((w["kind"] == "rung_timeout").sum())
        sl = slice(i0, i1 + 1)
        dip_max = float(np.max(Dall[sl]))
        dip_hour = str(grid[i0 + int(np.argmax(Dall[sl]))])
        gall_max = float(np.max(Gall[sl]))
        mm = np.zeros(i1 - i0 + 1)
        for j in range(i0, i1 + 1):
            tot = 0.0
            for c in COINS:
                tot += max(mm_of(float(Gsym[c][j] * Eq_mix[j] * A0),
                                 tiers[c])[0], 0.0)
            for c in CARRY_COINS:
                V = float(short_by_coin[c][j] * A0)
                if V > 0:
                    tot += max(mm_of(V, tiers[c + "USDT"])[0], 0.0)
            mm[j - i0] = tot / A0
        bal = Eq_tot_m[sl] - HAIRCUT_BASE * spot_val[sl]
        mm_over = mm / np.maximum(bal, 1e-12)
        breached = bool(np.any(bal < mm))
        m1 = m1_stats(t0, t1)
        rows.append({
            "key": key, "label": label, "anchor": str(anchor),
            "window": [str(grid[i0]), str(grid[i1])],
            "basket_drop": drop,
            "pnl_comb_pct": round(100 * (endA / preA - 1), 2),
            "pnl_g2_pct": round(100 * (endG / preG - 1), 2),
            "dd_close_pct": round(dd_close, 2),
            "dd_mark_pct": round(dd_mark, 2),
            "trough_hour": trough,
            "rec_days": rec,
            "dip_gross_max": round(dip_max, 3),
            "dip_gross_hour": dip_hour,
            "comb_gross_max": round(gall_max, 3),
            "margin": {
                "usage_eq_max": round(float(np.max(usage_eq[sl])), 4),
                "bal_base_max": round(float(np.max(u_bal[sl])), 4),
                "bal_stress_max": round(float(np.max(u_stress[sl])), 4),
                "bal_cons_max": round(float(np.max(u_cons[sl])), 4),
                "blocked_hours": int(np.sum(u_bal[sl] > 0.95)),
                "mm_bal_max": round(float(np.max(mm_over)), 4),
                "mm_breached": breached,
                "spot_cost_eq_max": round(float(np.max(
                    spot_cost[sl] / np.maximum(Eq_tot_m[sl], 1e-12))), 4),
            },
            "stops": {"n_stop": n_stop, "n_tp": n_tp, "n_timeout": n_to},
            "stop_triggered": bool(n_stop > 0),
            "liquidation": False,
            "m1": m1,
        })
        print(f"{key}: pnl {rows[-1]['pnl_comb_pct']:+.2f}% "
              f"dd_mark {dd_mark:.2f}% dip {dip_max:.2f} "
              f"u_bal {np.max(u_bal[sl]):.3f} stops {n_stop} rec {rec}",
              flush=True)

    out = {
        "meta": {
            "question": "crash-week anatomy: G2 + carry f=0.25 over -1d..+7d windows",
            "g2_src": "v421/v421_runs.pkl R2B1D17BFG2 (v422 identical: %s); hourly via v388.hourly" % ident,
            "carry_src": "oc_cashcarry 33 trades; P&L compounding = oc_carrycompound full-pass; margin = oc_carrymargin convention",
            "margin_src": "oc_carrymargin method (IM perp G/5, carry short/10, bal Eq-h*spot 5%/10%, cons short/5x); tiers frozen oc_utamargin (no network)",
            "marks": "stored eq_min 1m-marked lows (v388.hourly) + local 1m klines context (majors_intraday_20260924)",
            "grid": [str(grid[0]), str(grid[-1]), int(n)],
            "cut": "2026-09-24T00:00Z",
            "f": F,
            "event_window": "anchor-24h .. anchor+7d; recovery searched to grid end",
            "engine_liq_note": "stored engine liquidation flag is 0 on all phases (oc_ddanat_g2); UTA liquidation = balance < tiered MM, recomputed per window",
            "reuse": "oc_crash2020 / oc_crashfreq / oc_ddanat4p / oc_ddanat_g2 / oc_stresshist / oc_gapstress / oc_carrycompound / oc_carrymargin / oc_utamargin",
            "no_engine_reruns": True,
            "g2_full_path_dd_check": [round(dd_full * 100, 2), exp421["full_path_dd"]],
        },
        "basket_drops": [
            {"rank": i + 1, "end": str(t),
             "basket_24h_pct": round(v * 100, 2),
             "btc_24h_pct": round(b * 100, 2),
             "eth_24h_pct": round(e * 100, 2)}
            for i, (t, v, b, e) in enumerate(drops)],
        "events": rows,
    }
    (HERE / "results.json").write_text(json.dumps(out, indent=1))
    print("wrote results.json", flush=True)


if __name__ == "__main__":
    main()
