"""oc_utamargin2: POST-HOC sensitivity on oc_utamargin (ONE Bybit UTA).

Reuses oc_utamargin/analyze_utamargin.py VERBATIM except for the single
named change: the carry-short leg's IM leverage is varied (5x reproduce,
10x, 20x) while the G2 perp legs stay at 5x:

    IM = G2_gross / 5 + carry_short / LEV_CARRY        (oc_utamargin: /5 on both)

MM tiers are UNCHANGED (tiered per-instrument, no netting). Everything
else (hourly grid 2021-09-24..2026-09-23, causal marks, frozen 33
oc_cashcarry pairs sized f x mix equity at entry, balance = Eq_tot -
haircut x spot_val, blocked iff IM > 95% balance, liq iff balance < MM)
is identical to oc_utamargin.

Grid: f in {0.25, 0.375, 0.5} x LEV_CARRY in {5, 10, 20} = 9 cells.
Per cell (at its own worst hour = min free margin):
- min free margin, blocked hours, MM breaches, -10% all-coin gap loss.
- haircut stress: balance recomputed with haircut 10% and 20% (base 5%);
  min free / blocked / gap-loss-% under each.
- squeeze stress: +30% on BTC/ETH (carry spot AND quarterly short, plus
  G2 BTC/ETH perp notionals directionally): isolated-short check
  (loss_short vs IM_short — fails before the hedge helps) vs UTA-cross
  pooled outcome (balance_after vs MM_after, IM_after vs balance_after).
  Account mode matters: ISOLATED would liquidate the short; CROSS pools
  the spot gain, so the cell survives iff the pooled account survives.

Bybit leverage evidence (public, no keys, fetched live 2026-10-06 at
runtime; frozen fallback recorded visibly in results.json):
- inverse quarterly: BTCUSDH27/BTCUSDZ26 max 100x, ETHUSDH27/ETHUSDZ26
  max 50x (GET /v5/market/instruments-info?category=inverse).
- linear dated (LinearFutures) BTC/ETH: max 50x
  (GET /v5/market/instruments-info?category=linear).
- Hence 10x/20x on the USDT-margined quarterly short is within venue
  limits. Anything not verifiable is marked ASSUMPTION below / in REPORT.

Usage: .venv/Scripts/python.exe scripts/heavy_slot.py run --tag oc_utamargin2 --min-free-gb 2.0 -- .venv/Scripts/python.exe research/tournament/oc_utamargin2/analyze_utamargin2.py
Writes results.json (REPORT.md is written separately by hand from it).
RAM: hourly arrays only (43805 x handful of float64), well under 2.5 GB.
"""

from __future__ import annotations

import json
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
PREV = ROOT / "research" / "tournament" / "oc_utamargin"

COINS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
CARRY_COINS = ["BTC", "ETH"]
CUT = pd.Timestamp("2026-09-24", tz="UTC")
GRID_START = pd.Timestamp("2021-09-24 00:00", tz="UTC")
GRID_END = pd.Timestamp("2026-09-23 04:00", tz="UTC")
LEV_G2 = 5  # unchanged from oc_utamargin
LEV_CARRY_GRID = [5, 10, 20]
BLOCK_FRAC = 0.95
HAIRCUT_BASE = 0.05
HAIRCUT_STRESS = [0.10, 0.20]
TAKER = 0.00055
F_ROWS = [0.25, 0.375, 0.5]
FEE_ENTRY_PAID = 0.001 + 0.00055
A0 = 10000.0
CIX = {c: i for i, c in enumerate(COINS)}
BOOK_DELTA = {"book_fill", "book_add", "book_reduce", "book_partial"}
BOOK_FLAT = {"book_close", "book_stop", "book_tp"}
RUNG_EXIT = {"rung_sl", "rung_tp", "rung_timeout"}
SQUEEZE = 0.30  # +30% on BTC/ETH


def fetch_venue_leverage() -> tuple[dict, str]:
    """Live Bybit public evidence for dated-futures max leverage (no keys)."""
    out: dict = {}
    try:
        d = json.loads(urllib.request.urlopen(
            "https://api.bybit.com/v5/market/instruments-info?category=linear&limit=1000",
            timeout=30).read().decode())
        dated = [x for x in d["result"]["list"]
                 if x.get("contractType") == "LinearFutures"
                 and x.get("baseCoin") in ("BTC", "ETH")]
        out["linear_dated_BTC_ETH"] = {
            "n": len(dated),
            "maxLev": sorted({x["leverageFilter"]["maxLeverage"] for x in dated}),
            "examples": [x["symbol"] for x in dated[:4]],
        }
        d2 = json.loads(urllib.request.urlopen(
            "https://api.bybit.com/v5/market/instruments-info?category=inverse&limit=1000",
            timeout=30).read().decode())
        inv = [x for x in d2["result"]["list"] if "Futures" in str(x.get("contractType"))]
        out["inverse_dated"] = {
            sym: lev for sym, lev in
            ((x["symbol"], x["leverageFilter"]["maxLeverage"]) for x in inv
             if x["symbol"].startswith(("BTCUSD", "ETHUSD")))}
        d3 = json.loads(urllib.request.urlopen(
            "https://api.bybit.com/v5/market/risk-limit?category=inverse&symbol=BTCUSD&limit=3",
            timeout=20).read().decode())
        out["inverse_BTCUSD_tier1"] = d3["result"]["list"][0]
        src = ("Bybit public GET /v5/market/instruments-info (linear+inverse) + "
               "GET /v5/market/risk-limit?category=inverse, 2026-10-06")
        return out, src
    except Exception as e:  # never silent
        return {"fetch_failed": f"{type(e).__name__}: {e}",
                "fallback_ASSUMPTION": "linear dated BTC/ETH max 50x; "
                "inverse quarterly BTC max 100x / ETH max 50x (verified "
                "2026-10-06, frozen here because fetch failed)"}, \
            "fetch failed; frozen fallback (ASSUMPTION — re-verify before live)"


def mm_of(value_usdt: float, tiers: list[dict]) -> tuple[float, int]:
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
    """VERBATIM q-units replay from oc_utamargin (book flats zeroed, dip FIFO)."""
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
        mk, _ = ffill_at(mt, mv, U - 3_600_000_000_000)
        mk = np.where(np.isnan(mk), mv[0], mk)
        Fb[:, j] = Qb[:, j] * mk * eqs / equity
        Fd[:, j] = Qd[:, j] * mk * eqs / equity
    iu = np.searchsorted(U, grid_ns, side="right") - 1
    iu = np.maximum(iu, 0)
    gi = np.maximum(np.searchsorted(U, grid_ns, side="right") - 1, 0)
    return Fb[iu], Fd[iu], equity[gi]


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
    venue, venue_src = fetch_venue_leverage()
    # Linear-perp MM tiers: reuse oc_utamargin frozen snapshot (same date).
    prev_res = json.loads((PREV / "results.json").read_text())
    tiers = {s: {"tiers": prev_res["tiers"][s]} for s in COINS}

    grid = pd.date_range(GRID_START, GRID_END, freq="1h", tz="UTC")
    assert grid.max() < CUT
    grid_ns = grid.to_numpy(dtype="datetime64[ns]").astype(np.int64)
    n = len(grid)
    print(f"hours={n}", flush=True)

    marks = load_marks()
    Fb_s, Fd_s, Eq_s = {}, {}, {}
    for s in range(4):
        ev, bs = load_phase(s)
        Fb, Fd, E = build_hourly_state(ev, bs, marks, grid_ns)
        Fb_s[s], Fd_s[s], Eq_s[s] = Fb, Fd, E
    Eq = np.stack([Eq_s[s] for s in range(4)])
    Eq_mix = Eq.mean(0)
    Gsym = {c: np.zeros(n) for c in COINS}
    Ssym = {c: np.zeros(n) for c in COINS}  # signed net frac of mix equity
    for j, c in enumerate(COINS):
        num_g = sum((np.abs(Fb_s[s][:, j]) + np.abs(Fd_s[s][:, j])) * Eq_s[s]
                    for s in range(4))
        num_s = sum((Fb_s[s][:, j] + Fd_s[s][:, j]) * Eq_s[s] for s in range(4))
        den = Eq.sum(0)
        Gsym[c] = num_g / np.maximum(den, 1e-12)
        Ssym[c] = num_s / np.maximum(den, 1e-12)
    Gall = sum(Gsym.values())
    Sall = sum(Ssym.values())

    trades = load_carry_trades()
    qmap = {c: load_q_hourly(c) for c in CARRY_COINS}
    spot_px = {}
    for c in CARRY_COINS:
        sym = c + "USDT"
        mt, mv = marks[sym]
        q = grid_ns - 3_600_000_000_000
        i = np.searchsorted(mt, q, side="right") - 1
        spot_px[c] = np.where(i >= 0, mv[np.maximum(i, 0)], np.nan)
    fut_px = {}
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

    # carry legs depend on f only (not on LEV_CARRY) — build once per f
    carry_by_f = {}
    for f in F_ROWS:
        spot_val = np.zeros(n)
        spot_cost = np.zeros(n)
        short_not = np.zeros(n)
        carry_eq = np.zeros(n)
        short_by_coin = {c: np.zeros(n) for c in CARRY_COINS}
        spot_by_coin = {c: np.zeros(n) for c in CARRY_COINS}
        for k, r in enumerate(trades):
            S = np.where(np.isnan(spot_px[r["coin"]]), r["S_entry"], spot_px[r["coin"]])
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
            spot_by_coin[r["coin"]] += np.where(open_m, sv, 0.0)
            upnl = (qty_s * (S - r["S_entry"]) + qty_f * (r["F_entry"] - F)
                    - f * Eq_entry[k] * FEE_ENTRY_PAID)
            carry_eq += np.where(open_m, upnl, 0.0)
            carry_eq += np.where(shut_m, f * Eq_entry[k] * r["ret_alloc"], 0.0)
        Eq_tot = Eq_mix + carry_eq
        assert np.isfinite(Eq_tot).all() and np.isfinite(short_not).all()
        carry_by_f[f] = {
            "spot_val": spot_val, "spot_cost": spot_cost, "short_not": short_not,
            "carry_eq": carry_eq, "Eq_tot": Eq_tot,
            "short_by_coin": short_by_coin, "spot_by_coin": spot_by_coin,
        }

    def mm_path(Gsym_, Eq_mix_, short_by_coin_, A0_=A0):
        MM = np.zeros(n)
        max_tier = {c: 0 for c in COINS}
        for i in range(n):
            mm = 0.0
            for c in COINS:
                V = float(Gsym_[c][i] * Eq_mix_[i] * A0_)
                m, ti = mm_of(V, tiers[c]["tiers"])
                mm += m
                max_tier[c] = max(max_tier[c], ti)
            for c in CARRY_COINS:
                V = float(short_by_coin_[c][i] * A0_)
                if V > 0:
                    m, _ti = mm_of(V, tiers[c + "USDT"]["tiers"])
                    mm += m
            MM[i] = mm / A0_
        return MM, max_tier

    cells: dict = {}
    for f in F_ROWS:
        cb = carry_by_f[f]
        spot_val, short_not, Eq_tot = cb["spot_val"], cb["short_not"], cb["Eq_tot"]
        MM, max_tier = mm_path(Gsym, Eq_mix, cb["short_by_coin"])
        cost_over_Eq = spot_cost_safe = cb["spot_cost"] / np.maximum(Eq_tot, 1e-12)
        for lev in LEV_CARRY_GRID:
            balance = Eq_tot - HAIRCUT_BASE * spot_val
            IM = Gall * Eq_mix / LEV_G2 + short_not / lev
            im_over_bal = IM / np.maximum(balance, 1e-12)
            free_ratio = 1.0 - im_over_bal
            blocked = im_over_bal > BLOCK_FRAC
            mm_over_bal = MM / np.maximum(balance, 1e-12)
            breached = balance < MM
            i_min = int(np.argmin(free_ratio))
            # -10% all-coin gap at worst hour (oc_utamargin method)
            g = 0.10
            loss_g2 = (Sall[i_min] * Eq_mix[i_min] * g
                       + TAKER * Gall[i_min] * Eq_mix[i_min] * (1 - g))
            sv, sn = float(spot_val[i_min]), float(short_not[i_min])
            loss_carry = (sv - sn) * g + TAKER * sn * (1 - g)
            loss = float(loss_g2 + loss_carry)
            bal = float(balance[i_min])
            mm_after = 0.0
            for c in COINS:
                V = float(Gsym[c][i_min] * Eq_mix[i_min] * A0 * (1 - g))
                m, _ = mm_of(V, tiers[c]["tiers"])
                mm_after += m
            for c in CARRY_COINS:
                V = float(cb["short_by_coin"][c][i_min] * A0 * (1 - g))
                if V > 0:
                    m, _ = mm_of(V, tiers[c + "USDT"]["tiers"])
                    mm_after += m
            mm_after /= A0
            liq = bool((bal - loss) < mm_after)
            # haircut stresses at ALL hours + gap % under stressed balance
            hc: dict = {}
            for hcut in HAIRCUT_STRESS:
                b = Eq_tot - hcut * spot_val
                iob = IM / np.maximum(b, 1e-12)
                fr = 1.0 - iob
                bl = iob > BLOCK_FRAC
                br = b < MM
                bmin = float(b[i_min])
                hc[str(hcut)] = {
                    "min_free_ratio": round(float(fr.min()), 4),
                    "n_blocked_hours": int(bl.sum()),
                    "n_mm_breach_hours": int(br.sum()),
                    "gap10_loss_pct_of_stressed_balance": round(
                        float(loss / max(bmin, 1e-12) * 100), 2),
                    "gap10_liquidated_under_stress": bool((bmin - loss) < mm_after),
                }
            # +30% BTC/ETH squeeze at worst hour
            sq = SQUEEZE
            g2_gross_bt = float((Gsym["BTCUSDT"][i_min] + Gsym["ETHUSDT"][i_min])
                                * Eq_mix[i_min])
            g2_net_bt = float((Ssym["BTCUSDT"][i_min] + Ssym["ETHUSDT"][i_min])
                              * Eq_mix[i_min])
            sv_bt = float(cb["spot_by_coin"]["BTC"][i_min]
                          + cb["spot_by_coin"]["ETH"][i_min])
            sn_bt = float(cb["short_by_coin"]["BTC"][i_min]
                          + cb["short_by_coin"]["ETH"][i_min])
            # ISOLATED short leg alone: 30% loss vs its own IM
            iso_im_short = sn_bt / lev if sn_bt > 0 else 0.0
            iso_loss_short = sq * sn_bt
            iso_ratio = float(iso_loss_short / max(iso_im_short, 1e-12)) \
                if sn_bt > 0 else 0.0
            isolated_survives = bool(iso_ratio <= 1.0) if sn_bt > 0 else True
            # CROSS pooled: spot gain + short loss + G2 BTC/ETH net move;
            # collateral haircut drag on the (risen) spot value
            d_carry_net = sq * (sv_bt - sn_bt)
            d_g2_net = sq * g2_net_bt
            bal_after = bal + d_carry_net + d_g2_net - HAIRCUT_BASE * sq * sv_bt
            g2_gross_after = float(Gall[i_min] * Eq_mix[i_min] + sq * g2_gross_bt)
            sn_after = sn_bt * (1 + sq) + (sn - sn_bt)
            IM_after = g2_gross_after / LEV_G2 + (
                (sn - sn_bt) / lev + sn_bt * (1 + sq) / lev)
            MM_after = 0.0
            for c in COINS:
                scale = (1 + sq) if c in ("BTCUSDT", "ETHUSDT") else 1.0
                V = float(Gsym[c][i_min] * Eq_mix[i_min] * A0 * scale)
                m, _ = mm_of(V, tiers[c]["tiers"])
                MM_after += m
            for c in CARRY_COINS:
                V = float(cb["short_by_coin"][c][i_min] * A0 * (1 + sq))
                if V > 0:
                    m, _ = mm_of(V, tiers[c + "USDT"]["tiers"])
                    MM_after += m
            MM_after /= A0
            cross_liq = bool(bal_after < MM_after)
            cross_blocked = bool(IM_after / max(bal_after, 1e-12) > BLOCK_FRAC)
            key = f"f{f}_lev{lev}"
            cells[key] = {
                "f": f, "lev_carry": lev,
                "n_hours": n,
                "max_tier_per_symbol": {c: int(max_tier[c]) for c in COINS},
                "min_free_ratio": round(float(free_ratio.min()), 4),
                "max_IM_over_balance": round(float(im_over_bal.max()), 4),
                "max_MM_over_balance": round(float(mm_over_bal.max()), 4),
                "n_blocked_hours": int(blocked.sum()),
                "blocked_list": [str(grid[i]) for i in np.where(blocked)[0][:24]],
                "n_mm_breach_hours": int(breached.sum()),
                "worst_hour": str(grid[i_min]),
                "worst_G2_gross_frac": round(float(Gall[i_min]), 4),
                "worst_carry_short_frac_of_Eqmix": round(
                    float(short_not[i_min] / max(Eq_mix[i_min], 1e-12)), 4),
                "worst_spot_frac_of_Eqmix": round(
                    float(sv / max(Eq_mix[i_min], 1e-12)), 4),
                "max_spot_cost_over_Eqtot": round(float(cost_over_Eq.max()), 4),
                "min_cash_headroom_frac": round(
                    float(((Eq_tot - cb["spot_cost"]) / np.maximum(Eq_tot, 1e-12)).min()), 4),
                "gap10_at_worst": {
                    "loss_pct_of_balance": round(float(loss / max(bal, 1e-12) * 100), 2),
                    "loss_indexed": round(loss, 4),
                    "balance_indexed": round(bal, 4),
                    "liquidated": liq,
                },
                "haircut_stress": hc,
                "squeeze30_BTCETH_at_worst": {
                    "G2_net_BTCETH_frac": round(
                        float(g2_net_bt / max(Eq_mix[i_min], 1e-12)), 4),
                    "isolated_short_IM_indexed": round(float(iso_im_short), 4),
                    "isolated_short_loss_indexed": round(float(iso_loss_short), 4),
                    "isolated_loss_over_IM": round(float(iso_ratio), 2),
                    "isolated_short_survives": isolated_survives,
                    "cross_balance_after_indexed": round(float(bal_after), 4),
                    "cross_IM_over_balance_after": round(
                        float(IM_after / max(bal_after, 1e-12)), 4),
                    "cross_MM_over_balance_after": round(
                        float(MM_after / max(bal_after, 1e-12)), 4),
                    "cross_liquidated": cross_liq,
                    "cross_blocked": cross_blocked,
                    "account_mode_matters": True,
                    "note": "ISOLATED: 30% loss vs IM_short=notional/lev "
                            f"(loss/IM={iso_ratio:.2f} at {lev}x) -> short "
                            "liquidated before the spot hedge helps. CROSS "
                            "(Bybit UTA default): spot gain + short loss + "
                            "G2 BTC/ETH net are pooled, survives iff pooled "
                            "balance > MM.",
                },
            }
            print(f"f={f} lev={lev} min_free={free_ratio.min():.4f} "
                  f"maxIM={im_over_bal.max():.4f} blocked={blocked.sum()} "
                  f"breach={breached.sum()} worst={grid[i_min]}", flush=True)

    overall_tier = {c: 0 for c in COINS}
    for cell in cells.values():
        for c in COINS:
            overall_tier[c] = max(overall_tier[c], cell["max_tier_per_symbol"][c])
    res = {
        "meta": {
            "question": "POST-HOC sensitivity on oc_utamargin: carry-short "
                        "leverage 5x/10x/20x (G2 legs stay 5x), f=0.25/0.375/0.5",
            "post_hoc": True,
            "lev_G2": LEV_G2,
            "lev_carry_grid": LEV_CARRY_GRID,
            "f_grid": F_ROWS,
            "IM_formula": "IM = G2_gross/5 + carry_short/LEV_CARRY "
                          "(oc_utamargin had /5 on both; MM tiers unchanged)",
            "block_threshold": BLOCK_FRAC,
            "haircut_base": HAIRCUT_BASE,
            "haircut_stress": HAIRCUT_STRESS,
            "haircut_src": "base 5% = oc_utamargin (Bybit UTA BTC/ETH 95% "
                           "base tier); 10%/20% are extra stresses "
                           "(ASSUMPTION: doubled/quadrupled haircut)",
            "venue_leverage": venue,
            "venue_leverage_src": venue_src,
            "venue_leverage_fetch_date": "2026-10-06",
            "carry_short_venue_mapping": "um_BTC/ETHUSDT quarterly "
                "(Binance USDT-margined) proxies Bybit linear dated "
                "(LinearFutures BTC/ETH, verified max 50x) — venue mapping "
                "is an ASSUMPTION; inverse quarterly (BTC max 100x / ETH max "
                "50x) documented as the alternative listing",
            "A0_USDT": A0,
            "grid": [str(grid[0]), str(grid[-1]), n],
            "cut": "2026-09-24T00:00Z (no data at/after cut)",
            "carry_src": "oc_cashcarry/results.json 33 entered trades reused "
                         "verbatim (signal/fees/deliveries untouched)",
            "carry_sizing": "legs = f x total mix equity at entry hour "
                            "(oc_carrycombo convention), held to delivery",
            "G2_src": "oc_kpi_g2 events/barsum replayed hourly (oc_margin "
                      "q-units, functions verbatim from oc_utamargin)",
            "MM": "per-instrument tiered (oc_utamargin frozen linear tiers, "
                  "no netting perp vs quarterly) — UNCHANGED",
            "max_tier_per_symbol": overall_tier,
            "squeeze": "+30% on BTC/ETH within 24h; G2 BTC/ETH net included "
                       "directionally; uniform-mark ASSUMPTION",
            "no_engine_reruns": True,
            "no_1m": True,
        },
        "cells": cells,
    }
    (HERE / "results.json").write_text(json.dumps(res, indent=1))
    print("wrote results.json", flush=True)


if __name__ == "__main__":
    main()
