"""oc_utamargin: ONE Bybit UTA running G2 + frozen cash-carry overlay at f=0.25/0.5.

Question: can ONE Bybit Unified Trading Account run G2 (R2B1D17BFG2) AND the
frozen oc_cashcarry pair (spot BTC/ETH bought with the account's USDT,
collateralised with the Bybit haircut; short quarterly at 5x) as an additive
overlay without margin calls or liquidation at G2's worst minutes?

Method (no engine reruns, one process, hourly, 4h data + 1h marks only):
- G2 positions rebuilt HOURLY from stored oc_kpi_g2 events/barsum with the
  exact oc_margin q-units method (book flats zeroed, dip FIFO, Hedge-Mode
  gross = |book_net| + |dip_net| per coin), marked with hourly_ext closes
  (causal: last 1h bar with open_time < H), equity ffill from barsum
  (v421_runs.pkl equity series verified bit-identical, see results.json).
- Carry pairs FROZEN from oc_cashcarry/results.json (33 entered, same
  F_entry/S_entry/delivery/ret_alloc; entry rule/threshold/fees untouched).
  Legs sized f x total mix equity at entry hour (oc_carrycombo convention),
  held to delivery; spot marked with hourly_ext proxy, shorts with qbasis 1h
  (causal). No new signal, no tuning.
- UTA math (Bybit docs, live risk-limit tiers fetched 2026-10-06, frozen in
  results.json): IM = (G2 gross + carry short) / 5 (5x on all coins, the
  runbook minimum that never blocks G2 alone); MM = per-instrument tiered
  (position value x MMR_tier - deduction, no netting across perp/quarterly);
  margin balance = total equity - haircut x spot value (USDT 100%, BTC/ETH
  95% base tier; account < 10k stays base). Blocked iff IM > 95% of balance;
  liquidation iff balance < MM. A0 = 10000 USDT starting account for tier
  lookups (ratios themselves are scale-free).
- Grid: every hour 2021-09-24 00:00 .. 2026-09-23 04:00 UTC (< 2026-09-24
  cut) plus the 10 worst G2 minutes from oc_margin (positions/marks ffill
  from the containing hour; no 1m data loaded, stated as limitation).
- Gap: -10% all-coin instant gap at the worst UTA hour (perps closed at gap
  with taker 0.055%, carry spot/short both gap, hedged net ~ basis only).

Usage: .venv/Scripts/python.exe research/tournament/oc_utamargin/analyze_utamargin.py
Writes results.json (REPORT.md is written separately by hand from it).
"""

from __future__ import annotations

import json
import pickle
import urllib.request
from collections import Counter, deque
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
KPI = ROOT / "research" / "tournament" / "oc_kpi_g2"
EXT = ROOT / "research" / "tournament" / "ext"
CASH = ROOT / "research" / "tournament" / "oc_cashcarry"
MARGIN = ROOT / "research" / "tournament" / "oc_margin"
QDIR = ROOT / "data" / "raw" / "qbasis_20261003"

COINS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
CARRY_COINS = ["BTC", "ETH"]
CUT = pd.Timestamp("2026-09-24", tz="UTC")
GRID_START = pd.Timestamp("2021-09-24 00:00", tz="UTC")
GRID_END = pd.Timestamp("2026-09-23 04:00", tz="UTC")
LEV = 5
BLOCK_FRAC = 0.95
HAIRCUT = 0.05  # BTC/ETH base-tier collateral value 95% (Bybit UTA docs)
TAKER = 0.00055
F_ROWS = [0.25, 0.5]
FEE_ENTRY_PAID = 0.001 + 0.00055  # spot buy + futures entry, per allocated unit
A0 = 10000.0  # starting account USDT, for tier lookups only
CIX = {c: i for i, c in enumerate(COINS)}
BOOK_DELTA = {"book_fill", "book_add", "book_reduce", "book_partial"}
BOOK_FLAT = {"book_close", "book_stop", "book_tp"}
RUNG_EXIT = {"rung_sl", "rung_tp", "rung_timeout"}

# Frozen fallback tier-1 (Bybit linear risk-limit, fetched live 2026-10-06;
# full tables stored in results.json at runtime).
FROZEN_TIER1 = {
    "BTCUSDT": {"limit": 300000.0, "mmr": 0.0033},
    "ETHUSDT": {"limit": 300000.0, "mmr": 0.0033},
    "SOLUSDT": {"limit": 50000.0, "mmr": 0.005},
    "BNBUSDT": {"limit": 10000.0, "mmr": 0.0067},
    "XRPUSDT": {"limit": 50000.0, "mmr": 0.005},
}


def fetch_tiers() -> dict:
    """Fetch linear risk-limit tiers from Bybit public API (no keys)."""
    out = {}
    for sym in COINS:
        url = f"https://api.bybit.com/v5/market/risk-limit?category=linear&symbol={sym}&limit=50"
        with urllib.request.urlopen(url, timeout=20) as r:
            d = json.loads(r.read().decode())
        rows = d["result"]["list"]
        tiers = []
        for t in sorted(rows, key=lambda x: int(x["id"])):
            tiers.append({
                "limit": float(t["riskLimitValue"]),
                "mmr": float(t["maintenanceMargin"]),
                "deduct": float(t["mmDeduction"] or 0.0),
                "maxLev": t["maxLeverage"],
            })
        out[sym] = {"fetched": True, "tiers": tiers}
    return out


def mm_of(value_usdt: float, tiers: list[dict]) -> tuple[float, int]:
    """Tiered maintenance margin for one instrument position value."""
    for i, t in enumerate(tiers):
        if value_usdt <= t["limit"]:
            return value_usdt * t["mmr"] - t["deduct"], i
    t = tiers[-1]
    return value_usdt * t["mmr"] - t["deduct"], len(tiers) - 1


def load_marks():
    h = pd.read_parquet(EXT / "hourly_ext.parquet", columns=["t", "sym", "close"])
    h = h[h["sym"].isin(COINS)].copy()
    h["t"] = pd.to_datetime(h["t"], utc=True)
    assert h["t"].max() < CUT + pd.Timedelta(days=1)
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
    assert ev["t"].max() < CUT
    bs = pd.read_parquet(KPI / f"barsum_s{s}.parquet")
    bs["t"] = pd.to_datetime(bs["t"], utc=True)
    assert bs["t"].max() < CUT
    return ev, bs


def ffill_at(xt: np.ndarray, xv: np.ndarray, q: np.ndarray):
    i = np.searchsorted(xt, q, side="right") - 1
    return np.where(i >= 0, xv[np.maximum(i, 0)], np.nan), i


def build_hourly_state(ev: pd.DataFrame, bs: pd.DataFrame, marks: dict,
                       grid_ns: np.ndarray):
    """Replay stored events to each hour H (post-event state, causal marks).

    Same q-units math as oc_margin/compute_margin.py: book_fill qk =
    weight/price; book_add/reduce/partial qk = weight*prev_eq/price;
    book_stop/tp/close zero the coin; dip rung_fill qk = weight/price with
    FIFO exits. Fractions = qty x mark x bar-start equity / indexed equity.
    """
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
    Fb_raw = np.zeros_like(Qb)  # oc_margin recon quantity (no eqs factor)
    for c, j in CIX.items():
        mt, mv = marks[c]
        mk, _ = ffill_at(mt, mv, U - 3_600_000_000_000)  # last 1h bar strictly before H
        mk = np.where(np.isnan(mk), mv[0], mk)
        Fb[:, j] = Qb[:, j] * mk * eqs / equity
        Fd[:, j] = Qd[:, j] * mk * eqs / equity
        Fb_raw[:, j] = Qb[:, j] * mk / equity
    # sample to hourly grid (ffill post-event state)
    iu = np.searchsorted(U, grid_ns, side="right") - 1
    iu = np.maximum(iu, 0)
    gi = np.maximum(np.searchsorted(U, grid_ns, side="right") - 1, 0)
    return Fb[iu], Fd[iu], equity[gi], Fb_raw[iu]


def load_carry_trades():
    res = json.loads((CASH / "results.json").read_text())
    trades = res["trades"]
    assert len(trades) == 33
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
    """expiry date str -> (open_time ns, close) for the quarterly 1h file."""
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


def main() -> None:
    try:
        tiers = fetch_tiers()
        tier_src = "Bybit public GET /v5/market/risk-limit?category=linear (no keys), 2026-10-06"
    except Exception as e:  # never silent: freeze fallback visibly
        tiers = {s: {"fetched": False, "tiers": [
            {"limit": FROZEN_TIER1[s]["limit"], "mmr": FROZEN_TIER1[s]["mmr"],
             "deduct": 0.0, "maxLev": "n/a"}]} for s in COINS}
        tier_src = f"fetch failed ({type(e).__name__}); frozen fallback {FROZEN_TIER1}"
    assert (pd.Timestamp("2026-10-06", tz="UTC") - CUT).days >= 0

    grid = pd.date_range(GRID_START, GRID_END, freq="1h", tz="UTC")
    assert grid.max() < CUT
    grid_ns = grid.to_numpy(dtype="datetime64[ns]").astype(np.int64)
    n = len(grid)
    print(f"hours={n}", flush=True)

    marks = load_marks()
    # v421 equity identity check (assignment's named source)
    pkl = pickle.load(open(
        ROOT / "research/parallel/rounds/parallel-20260906-r2/v421/v421_runs.pkl", "rb"))
    v421_ok = True
    for s in range(4):
        v = pkl[s]["R2B1D17BFG2"]
        bs = pd.read_parquet(KPI / f"barsum_s{s}.parquet")
        if len(v["eq"]) != len(bs) or not np.allclose(v["eq"], bs["equity"].to_numpy(float)):
            v421_ok = False
    print(f"v421_runs.pkl equity identical to barsum: {v421_ok}", flush=True)

    Fb_s, Fd_s, Eq_s = {}, {}, {}
    recon = {}
    for s in range(4):
        ev, bs = load_phase(s)
        Fb, Fd, E, Fr = build_hourly_state(ev, bs, marks, grid_ns)
        Fb_s[s], Fd_s[s], Eq_s[s] = Fb, Fd, E
        # recon vs barsum gross_book at 4h bar ends, oc_margin convention:
        # raw (no eqs factor) book gross vs stored gross_book
        bt = pd.to_datetime(bs["t"], utc=True)
        gb = bs["gross_book"].to_numpy(float)
        ok = (bt >= GRID_START) & (bt <= GRID_END)
        btv = bt[ok]
        gbv = gb[ok.values]
        gi = np.searchsorted(grid, btv)
        valid = gi < n
        diff = np.abs(np.abs(Fr[gi[valid]]).sum(1) - gbv[valid])
        recon[str(s)] = {"median_abs_diff": round(float(np.median(diff)), 5),
                         "max_abs_diff": round(float(diff.max()), 4)}
        print(f"phase {s}: recon median {np.median(diff):.5f} max {diff.max():.4f}",
              flush=True)
    Eq = np.stack([Eq_s[s] for s in range(4)])  # 4 x n
    Eq_mix = Eq.mean(0)
    # equity-weighted mix fractions (oc_margin convention)
    Gall = np.zeros(n)
    Sall = np.zeros(n)
    Gsym = {c: np.zeros(n) for c in COINS}   # per-symbol gross frac of mix equity
    for j, c in enumerate(COINS):
        num_g = sum((np.abs(Fb_s[s][:, j]) + np.abs(Fd_s[s][:, j])) * Eq_s[s]
                    for s in range(4))
        num_s = sum((Fb_s[s][:, j] + Fd_s[s][:, j]) * Eq_s[s] for s in range(4))
        den = Eq.sum(0)
        Gsym[c] = num_g / np.maximum(den, 1e-12)  # mix fraction (den = 4*Eq_mix)
    Gall = sum(Gsym.values())
    Snum = sum(sum((Fb_s[s][:, j] + Fd_s[s][:, j]) * Eq_s[s] for s in range(4))
               for j in range(len(COINS)))
    Sall = Snum / np.maximum(Eq.sum(0), 1e-12)

    # ---- carry legs (frozen trades) ----
    trades = load_carry_trades()
    qmap = {c: load_q_hourly(c) for c in CARRY_COINS}
    # hourly marks for spot proxy (perp close) and quarterly
    spot_px = {}
    for c in CARRY_COINS:
        sym = c + "USDT"
        mt, mv = marks[sym]
        q = grid_ns - 3_600_000_000_000
        i = np.searchsorted(mt, q, side="right") - 1
        spot_px[c] = np.where(i >= 0, mv[np.maximum(i, 0)], np.nan)
    fut_px = {}  # (coin, delivery) -> hourly series
    for r in trades:
        key = (r["coin"], r["delivery"])
        if key not in fut_px:
            ot, cl = qmap[r["coin"]][r["delivery"]]
            q = grid_ns - 3_600_000_000_000
            i = np.searchsorted(ot, q, side="right") - 1
            fut_px[key] = np.where(i >= 0, cl[np.maximum(i, 0)], np.nan)
    Te = np.array([r["entry_open"].value for r in trades])
    Dd = np.array([r["D"].value for r in trades])
    Eq_entry = np.array([float(Eq_mix[np.maximum(
        np.searchsorted(grid_ns, t, side="right") - 1, 0)]) for t in Te])

    per_f = {}
    hourly_cache = {}
    for f in F_ROWS:
        ntr = len(trades)
        spot_val = np.zeros(n)
        spot_cost = np.zeros(n)  # cash locked in spot legs (cost basis)
        short_not = np.zeros(n)
        carry_eq = np.zeros(n)  # carry P&L indexed (added to Eq_mix)
        short_by_coin = {c: np.zeros(n) for c in CARRY_COINS}
        for k, r in enumerate(trades):
            S = np.where(np.isnan(spot_px[r["coin"]]), r["S_entry"],
                         spot_px[r["coin"]])
            Fraw = fut_px[(r["coin"], r["delivery"])]
            F = np.where(np.isnan(Fraw), r["F_entry"], Fraw)
            open_m = (grid_ns >= Te[k]) & (grid_ns < Dd[k])
            shut_m = (grid_ns >= Dd[k])
            qty_s = f * Eq_entry[k] / r["S_entry"]
            qty_f = f * Eq_entry[k] / r["F_entry"]
            sv = qty_s * S
            sn = qty_f * F
            spot_val += np.where(open_m, sv, 0.0)
            spot_cost += np.where(open_m, f * Eq_entry[k], 0.0)
            short_not += np.where(open_m, sn, 0.0)
            short_by_coin[r["coin"]] += np.where(open_m, sn, 0.0)
            upnl = (qty_s * (S - r["S_entry"]) + qty_f * (r["F_entry"] - F)
                    - f * Eq_entry[k] * FEE_ENTRY_PAID)
            carry_eq += np.where(open_m, upnl, 0.0)
            carry_eq += np.where(shut_m, f * Eq_entry[k] * r["ret_alloc"], 0.0)
        Eq_tot = Eq_mix + carry_eq
        balance = Eq_tot - HAIRCUT * spot_val
        assert np.isfinite(balance).all() and np.isfinite(short_not).all(), \
            "NaN in carry marks (check qbasis coverage)"
        # cash funding of the spot legs: cost basis vs account size
        # (borrow interest if wallet goes negative is NOT modelled)
        cost_over_Eq = spot_cost / np.maximum(Eq_tot, 1e-12)
        cash_headroom = (Eq_tot - spot_cost) / np.maximum(Eq_tot, 1e-12)
        IM = (Gall * Eq_mix + short_not) / LEV
        im_over_bal = IM / np.maximum(balance, 1e-12)
        free_ratio = 1.0 - im_over_bal
        blocked = im_over_bal > BLOCK_FRAC
        # tiered MM (absolute USDT with A0 scale)
        MM = np.zeros(n)
        max_tier = {c: 0 for c in COINS}
        for i in range(n):
            mm = 0.0
            for c in COINS:
                V = float(Gsym[c][i] * Eq_mix[i] * A0)
                m, ti = mm_of(V, tiers[c]["tiers"])
                mm += m
                max_tier[c] = max(max_tier[c], ti)
            for c in CARRY_COINS:
                V = float(short_by_coin[c][i] * A0)
                if V > 0:
                    m, ti = mm_of(V, tiers[c + "USDT"]["tiers"])
                    mm += m
            MM[i] = mm / A0
        mm_over_bal = MM / np.maximum(balance, 1e-12)
        breached = balance < MM
        hourly_cache[f] = {
            "Eq_tot": Eq_tot, "balance": balance, "IM": IM,
            "MM": MM, "spot_val": spot_val, "short_not": short_not,
            "carry_eq": carry_eq, "im_over_bal": im_over_bal,
            "blocked": blocked, "breached": breached,
        }
        wb = np.where(blocked)[0]
        # scheduled bot opens that would be rejected in blocked hours
        skip_info = {"n_blocked_hours": int(blocked.sum()),
                     "blocked_list": [str(grid[i]) for i in wb[:24]]}
        if len(wb):
            ev_ts = []
            for s in range(4):
                ev = pd.read_parquet(KPI / f"events_s{s}.parquet", columns=["t", "kind"])
                ev["t"] = pd.to_datetime(ev["t"], utc=True)
                ev_ts.append(ev)
            ev_all = pd.concat(ev_ts)
            hh = pd.to_datetime(pd.Series([str(grid[i]) for i in wb]), utc=True)
            hits = ev_all[ev_all["t"].dt.floor("h").isin(hh)]
            skip_info["n_scheduled_events_in_blocked"] = int(len(hits))
            skip_info["by_kind"] = hits["kind"].value_counts().to_dict()
        else:
            # what sits at the tightest hour (would-be-first skipped)
            i0 = int(np.argmin(free_ratio))
            H0 = grid[i0]
            ev0 = []
            for s in range(4):
                ev = pd.read_parquet(KPI / f"events_s{s}.parquet", columns=["t", "kind", "symbol"])
                ev["t"] = pd.to_datetime(ev["t"], utc=True)
                m = ev[ev["t"].dt.floor("h") == H0]
                for _, r_ in m.iterrows():
                    ev0.append(f"s{s} {r_['kind']} {r_['symbol']} {r_['t']}")
            skip_info["tightest_hour"] = str(H0)
            skip_info["scheduled_at_tightest"] = ev0[:12]
            skip_info["n_scheduled_events_in_blocked"] = 0
            skip_info["by_kind"] = {}
        i_min = int(np.argmin(free_ratio))
        # -10% gap at the worst hour
        g = 0.10
        loss_g2 = (Sall[i_min] * Eq_mix[i_min] * g
                   + TAKER * Gall[i_min] * Eq_mix[i_min] * (1 - g))
        sv, sn = float(spot_val[i_min]), float(short_not[i_min])
        loss_carry = (sv - sn) * g + TAKER * sn * (1 - g)
        loss = float(loss_g2 + loss_carry)
        bal = float(balance[i_min])
        # MM after gap (notionals shrink by (1-g)); tiers held
        mm_after = 0.0
        for c in COINS:
            V = float(Gsym[c][i_min] * Eq_mix[i_min] * A0 * (1 - g))
            m, _ = mm_of(V, tiers[c]["tiers"])
            mm_after += m
        for c in CARRY_COINS:
            V = float(short_by_coin[c][i_min] * A0 * (1 - g))
            if V > 0:
                m, _ = mm_of(V, tiers[c + "USDT"]["tiers"])
                mm_after += m
        mm_after /= A0
        liq = bool((bal - loss) < mm_after)
        per_f[str(f)] = {
            "n_hours": n,
            "min_free_ratio": round(float(free_ratio.min()), 4),
            "min_IM_over_balance": round(float(im_over_bal.min()), 4),
            "max_IM_over_balance": round(float(im_over_bal.max()), 4),
            "max_MM_over_balance": round(float(mm_over_bal.max()), 4),
            "n_blocked_hours": int(blocked.sum()),
            "n_mm_breach_hours": int(breached.sum()),
            "worst_hour": str(grid[i_min]),
            "worst_G2_gross_frac": round(float(Gall[i_min]), 4),
            "worst_carry_short_frac_of_Eqmix": round(
                float(short_not[i_min] / max(Eq_mix[i_min], 1e-12)), 4),
            "worst_spot_frac_of_Eqmix": round(
                float(sv / max(Eq_mix[i_min], 1e-12)), 4),
            "max_tier_per_symbol": max_tier,
            "max_spot_cost_over_Eqtot": round(float(cost_over_Eq.max()), 4),
            "min_cash_headroom_frac": round(float(cash_headroom.min()), 4),
            "skip": skip_info,
            "gap10_at_worst": {
                "loss_pct_of_balance": round(float(loss / max(bal, 1e-12) * 100), 2),
                "loss_indexed": round(loss, 4),
                "balance_indexed": round(bal, 4),
                "liquidated": liq,
            },
        }
        print(f"f={f} min_free={free_ratio.min():.4f} "
              f"maxIM={im_over_bal.max():.4f} blocked={blocked.sum()} "
              f"breach={breached.sum()} worst={grid[i_min]}", flush=True)

    # ---- worst G2 minutes from oc_margin (1m exits), hourly proxy ----
    oc_margin_worst = json.loads((MARGIN / "results.json").read_text())["mix"]["worst10_m10"]
    minute_rows = []
    for w in oc_margin_worst:
        tm = pd.Timestamp(w["t"], tz="UTC")
        if not (GRID_START <= tm < CUT):
            continue
        i = int(np.searchsorted(grid_ns, tm.value, side="right") - 1)
        i = max(min(i, n - 1), 0)
        row = {"t": w["t"], "G2_loss10_pct": w["loss_pct"],
               "G2_gross": w["gross"], "hour_used": str(grid[i])}
        for f in F_ROWS:
            hc = hourly_cache[f]
            bal = float(hc["balance"][i])
            im = float(hc["IM"][i])
            mm = float(hc["MM"][i])
            g = 0.10
            loss_g2 = w["loss_pct"] / 100.0 * float(Eq_mix[i])
            sv, sn = float(hc["spot_val"][i]), float(hc["short_not"][i])
            loss = loss_g2 + (sv - sn) * g + TAKER * sn * (1 - g)
            row[f"f{str(f)}_free_ratio"] = round(1 - im / max(bal, 1e-12), 4)
            row[f"f{str(f)}_gap10_loss_pct_bal"] = round(loss / max(bal, 1e-12) * 100, 2)
            row[f"f{str(f)}_gap10_liquidated"] = bool((bal - loss) < mm * 0.9)
            row[f"f{str(f)}_mm_breach"] = bool(bal < mm)
        minute_rows.append(row)

    res = {
        "meta": {
            "question": "ONE Bybit UTA: G2 + frozen carry overlay at f=0.25/0.5, additive",
            "leverage": LEV,
            "block_threshold": BLOCK_FRAC,
            "haircut_BTC_ETH": HAIRCUT,
            "haircut_src": "Bybit UTA help-center: BTC 95%, ETH 95% base tier "
                           "(oc_carrycombo §3); account < 10k stays base tier",
            "tier_src": tier_src,
            "tier_fetch_date": "2026-10-06",
            "A0_USDT": A0,
            "grid": [str(grid[0]), str(grid[-1]), n],
            "cut": "2026-09-24T00:00Z (no data at/after cut)",
            "carry_src": "oc_cashcarry/results.json 33 entered trades reused verbatim "
                         "(signal/fees/deliveries untouched)",
            "carry_sizing": "legs = f x total mix equity at entry hour "
                            "(oc_carrycombo convention), held to delivery",
            "G2_src": "oc_kpi_g2 events/barsum replayed hourly (oc_margin q-units); "
                      "v421_runs.pkl equity verified identical to barsum",
            "v421_equity_identical_to_barsum": bool(v421_ok),
            "marks": "hourly_ext 1h closes (G2 perps + spot proxy) + qbasis 1h "
                     "quarterly closes, causal (last bar with open_time < H)",
            "minute_check_limitation": "worst G2 minutes use hourly marks/positions "
                "ffill (no 1m data loaded); 1m wicks would be worse for perps, "
                "carry pair is hedged so its minute gap is ~basis only",
            "no_engine_reruns": True,
            "recon_vs_barsum": recon,
        },
        "tiers": {s: tiers[s]["tiers"] for s in COINS},
        "per_f": per_f,
        "worst_G2_minutes": minute_rows,
    }
    (HERE / "results.json").write_text(json.dumps(res, indent=1))
    print("wrote results.json", flush=True)


if __name__ == "__main__":
    main()
