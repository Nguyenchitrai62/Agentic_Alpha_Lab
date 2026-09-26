"""engine_real blind audit, part A: independent re-implementation.

Allowed imports only: v144/v144_deploy_v3.py (for v99 constants, v110 START/END/summarize,
v135 bar_stats) and scripts/carry_lab.py (for load, position, GRID, SYMS, ANCHORS, EMBARGO_DAYS).
Does NOT open engine_real/ (blind until replication.json is saved).
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parents[4]  # repo root: .../Agentic_Alpha_Lab
ROUND2 = ROOT / "research" / "parallel" / "rounds" / "parallel-20260906-r2"


def _load_v144():
    p = ROUND2 / "v144" / "v144_deploy_v3.py"
    spec = importlib.util.spec_from_file_location("audit_v144", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _load_carry_lab():
    p = ROOT / "scripts" / "carry_lab.py"
    spec = importlib.util.spec_from_file_location("audit_carry_lab", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


W_BOOKS, W_CARRY, CARRY_LEV, CAP = 0.8, 0.2, 3.0, 2.0
TARGET = 0.25
PD = 6
C_REAL = W_CARRY * CARRY_LEV  # 0.6
THRESH = {"BTCUSDT": 100.0, "ETHUSDT": 20.0}
DEFAULT_THRESH = 5.0


def build_real_carry(books_idx, carry_lab):
    """Real carry sleeve per assignment spec.

    rp/rs = po/so shift(-2)/shift(-1)-1, fund = rate.shift(-2),
    ret = (pos*(fund+rs-rp) - |diff(pos)|*0.0015)/1.2.
    Select per anchor argmax mean/std on [first+30d, anchor-EMBARGO_DAYS],
    forward [anchor, anchor+365d). Returns carry, expo aligned to books_idx.
    """
    SYMS = carry_lab.SYMS
    GRID = carry_lab.GRID
    ANCHORS = carry_lab.ANCHORS
    EMBARGO_DAYS = carry_lab.EMBARGO_DAYS
    per_sym_ret = {}
    per_sym_pos = {}
    for sym in SYMS:
        d = carry_lab.load(sym)
        po, so, rate = d["po"], d["so"], d["rate"]
        rp = po.shift(-2) / po.shift(-1) - 1
        rs = so.shift(-2) / so.shift(-1) - 1
        fund = rate.shift(-2)
        first = d["idx"][0]
        s0 = first + pd.Timedelta(days=30)
        cache = {}
        for q in GRID:
            key = json.dumps(q, sort_keys=True)
            pos = carry_lab.position(d, q)
            diff = pos.diff().abs()
            # initial entry cost from flat (matches carry_lab fillna(pos.iloc[0]))
            if len(pos):
                diff = diff.fillna(abs(float(pos.iloc[0])))
            gross = pos * (fund + rs - rp)
            cost = diff * (0.001 + 0.0005)
            ret = ((gross - cost) / 1.2).fillna(0.0)
            cache[key] = (pos.fillna(0.0), ret)
        fwd_rets, fwd_pos = [], []
        for anchor in ANCHORS:
            a = pd.Timestamp(anchor, tz="UTC")
            s1 = a - pd.Timedelta(days=EMBARGO_DAYS)
            best, best_score = None, -1e18
            for q in GRID:
                key = json.dumps(q, sort_keys=True)
                _, ret = cache[key]
                window = ret[(ret.index >= s0) & (ret.index <= s1)]
                mu = float(window.mean()) if len(window) else float("nan")
                sd = float(window.std()) if len(window) else float("nan")
                score = mu / sd if sd and sd > 0 and np.isfinite(mu) and np.isfinite(sd) else -9.0
                if score > best_score:
                    best_score, best = score, key
            pos_b, ret_b = cache[best]
            a1 = a + pd.Timedelta(days=365)
            fwd_rets.append(ret_b[(ret_b.index >= a) & (ret_b.index < a1)])
            fwd_pos.append(pos_b[(pos_b.index >= a) & (pos_b.index < a1)])
        per_sym_ret[sym] = pd.concat(fwd_rets).sort_index()
        per_sym_pos[sym] = pd.concat(fwd_pos).sort_index()
    ret_df = pd.DataFrame(per_sym_ret).sort_index()
    pos_df = pd.DataFrame(per_sym_pos).sort_index()
    carry = ret_df.mean(axis=1).reindex(books_idx).fillna(0.0)
    expo = pos_df.mean(axis=1).reindex(books_idx).fillna(0.0)
    return carry, expo


def load_funding_real(books_idx):
    out = {}
    for sym in books_idx_cols():
        f = pd.read_parquet(ROOT / "data" / "raw" / "xs_universe_20260924" / f"{sym}_funding.parquet")
        ft = pd.to_datetime(f["fundingTime"], utc=True)
        bucket = f.groupby(ft.dt.floor("4h"))["fundingRate"].sum()
        s = bucket.reindex(books_idx).fillna(0.0)
        out[sym] = s.shift(-2).fillna(0.0)
    return pd.DataFrame(out).reindex(columns=books_idx_cols())


def books_idx_cols():
    b = pd.read_parquet(ROOT / "artifacts" / "research" / "engine_real" / "books_v154.parquet")
    return list(b.columns)


def load_exec_stats(books_idx, v135):
    stats = {}
    for sym in books_idx_cols():
        raw = v135.bar_stats(sym)
        al = raw.reindex(books_idx + pd.Timedelta(hours=4))
        al = al.set_axis(books_idx)
        stats[sym] = al
    return stats


def exec_arrays(stats, cols):
    n = len(next(iter(stats.values())))
    fee_b = np.zeros((n, len(cols)))
    rel_b = np.zeros((n, len(cols)))
    fee_s = np.zeros((n, len(cols)))
    rel_s = np.zeros((n, len(cols)))
    D = 0.001
    for j, s in enumerate(cols):
        st = stats[s]
        p0 = st["p0"].to_numpy(dtype=float)
        lo = st["lo"].to_numpy(dtype=float)
        hi = st["hi"].to_numpy(dtype=float)
        p15 = st["p15"].to_numpy(dtype=float)
        have = ~np.isnan(p0)
        p15f = np.where(np.isnan(p15), p0, p15)
        with np.errstate(invalid="ignore", divide="ignore"):
            mv = np.where(have, p15f / np.where(have, p0, 1.0) - 1, 0.0)
        mv = np.nan_to_num(mv, nan=0.0, posinf=0.0, neginf=0.0)
        fb = have & (lo < p0 * (1 - D))
        fs = have & (hi > p0 * (1 + D))
        fee_b[:, j] = np.where(fb, 0.0002, 0.0005)
        rel_b[:, j] = np.where(fb, -D, mv + 0.0002)
        fee_s[:, j] = np.where(fs, 0.0002, 0.0005)
        rel_s[:, j] = np.where(fs, D, mv - 0.0002)
    return fee_b, rel_b, fee_s, rel_s


def load_low_high(books_idx, cols):
    lows, highs = {}, {}
    for sym in cols:
        df = pd.read_parquet(ROOT / "data" / "raw" / "xs_universe_20260924" / f"{sym}_4h.parquet")
        ot = pd.to_datetime(df["open_time"], utc=True)
        lo = pd.Series(df["low"].to_numpy(float), index=ot).reindex(books_idx)
        hi = pd.Series(df["high"].to_numpy(float), index=ot).reindex(books_idx)
        lows[sym] = lo.to_numpy(dtype=float)
        highs[sym] = hi.to_numpy(dtype=float)
    return np.column_stack([lows[c] for c in cols]), np.column_stack([highs[c] for c in cols])


def run_loop(books, o, carry, expo, fund_df_or_none, fee_b, rel_b, fee_s, rel_s,
             s_arr, r_next, live, mode):
    n, m = books.shape
    cols = list(books.columns)
    B = books.to_numpy(dtype=float)
    o_vals = o.to_numpy(dtype=float)
    carry_arr = carry.to_numpy(dtype=float)
    expo_arr = expo.to_numpy(dtype=float) if expo is not None else np.ones(n)
    fund_arr = fund_df_or_none.to_numpy(dtype=float) if fund_df_or_none is not None else None
    net = np.zeros(n)
    turn = np.zeros(n)
    g = np.ones(n)
    eq = np.ones(n)
    exec_c = np.zeros(n)
    fund_pnl = np.zeros(n)
    carry_pnl = np.zeros(n)
    carry_cost = np.zeros(n)
    gross = np.zeros(n)
    w_all = np.zeros((n, m))
    c_all = np.zeros(n)
    prev_w = np.zeros(m)
    prev_c = 0.0
    for i in range(n):
        if i >= 2:
            j = i - 2
            lo = max(0, j - 540 + 1)
            peak = eq[lo:j + 1].max()
            dd = 1 - eq[j] / peak if peak else 0.0
            g[i] = float(np.clip((0.20 - dd) / 0.10, 0.0, 1.0))
        if live[i]:
            w = W_BOOKS * s_arr[i] * B[i] * g[i]
            c = C_REAL * s_arr[i] * g[i]
        else:
            w = np.zeros(m)
            c = 0.0
        if mode == "real":
            ex = expo_arr[i]
            tot = c * ex + np.abs(w).sum() / 5.0
            if tot > 0.95:
                denom = max(ex, 1e-9)
                c_allow = (0.95 - np.abs(w).sum() / 5.0) / denom
                c = min(c, max(0.0, c_allow))
            if np.abs(w).sum() / 5.0 > 0.95:
                scale = (0.95 * 5.0) / np.abs(w).sum()
                w = w * scale
            equity = 10000.0 * (eq[i - 1] if i > 0 else 1.0)
            for jj, sym in enumerate(cols):
                th = THRESH.get(sym, DEFAULT_THRESH)
                if w[jj] != 0 and abs(w[jj] - prev_w[jj]) * equity < th:
                    w[jj] = prev_w[jj]
        dw = w - prev_w
        dc = c - prev_c
        buy = dw > 0
        fee = np.where(buy, fee_b[i], fee_s[i])
        rel = np.where(buy, rel_b[i], rel_s[i])
        ex_c = float(np.sum(np.abs(dw) * fee + dw * rel))
        if mode == "real":
            fp = float(-np.sum(w * fund_arr[i]))
            cp = float(c * carry_arr[i])
            cc = float(abs(dc) / 1.2 * expo_arr[i] * 0.0015)
        else:
            fp = float(-0.00005 * np.sum(np.clip(w, 0, None)))
            cp = float(c * carry_arr[i])
            cc = float(abs(dc) * 2 * 0.0004 / 1.2)
        gr = float(np.sum(w * r_next[i]))
        n_i = gr - ex_c + fp + cp - cc
        net[i] = n_i
        exec_c[i] = ex_c
        fund_pnl[i] = fp
        carry_pnl[i] = cp
        carry_cost[i] = cc
        gross[i] = gr
        turn[i] = float(np.abs(dw).sum())
        eq[i] = (eq[i - 1] if i > 0 else 1.0) * (1 + n_i)
        w_all[i] = w
        c_all[i] = c
        prev_w, prev_c = w.copy(), c
    return dict(net=net, turn=turn, g=g, eq=eq, exec=exec_c, funding=fund_pnl,
                carry_pnl=carry_pnl, carry_cost=carry_cost, gross=gross,
                w=w_all, c=c_all)


def intrabar_bound(eq, w_all, exec_c, fund_pnl, live, o_vals, low_arr, high_arr):
    n = len(eq)
    first = int(np.flatnonzero(live)[0]) if live.any() else 0
    base = eq[first - 1] if first > 0 else 1.0
    if base == 0:
        base = 1.0
    eq_lo = np.full(n, np.nan)
    for i in range(n):
        if not live[i]:
            continue
        if i + 1 >= n:
            continue
        if i == 0:
            prev_eq = 1.0
        else:
            prev_eq = eq[i - 1]
        w = w_all[i]
        oi1 = o_vals[i + 1]
        adv = 0.0
        for jj in range(w.shape[0]):
            oref = oi1[jj]
            if not np.isfinite(oref) or oref == 0:
                continue
            if w[jj] > 0:
                px = low_arr[i + 1, jj]
            else:
                px = high_arr[i + 1, jj]
            if not np.isfinite(px):
                continue
            adv += w[jj] * (px / oref - 1)
        eq_lo[i] = prev_eq * (1 + adv - exec_c[i] + min(fund_pnl[i], 0.0))
    eq_n = eq / base
    lo_n = eq_lo / base
    run = -np.inf
    worst = 0.0
    for i in range(n):
        if not live[i]:
            continue
        run = max(run, eq_n[i - 1] if i > 0 else eq_n[i])
        # include current eq in peak? spec: running max of eq; use max up to i-1 then current
        run = max(run, eq_n[i])
        if np.isfinite(lo_n[i]) and run > 0:
            dd = 1 - lo_n[i] / run
            worst = max(worst, dd)
    return float(worst), eq_lo


def main():
    v144 = _load_v144()
    carry_lab = _load_carry_lab()
    v110 = v144.v110
    v135 = v144.v135
    START, END = v110.START, v110.END

    books = pd.read_parquet(ROOT / "artifacts" / "research" / "engine_real" / "books_v154.parquet").sort_index()
    opens = pd.read_parquet(ROOT / "artifacts" / "research" / "engine_real" / "opens_v154.parquet").sort_index()
    idx = books.index
    cols = list(books.columns)
    o = opens.reindex(idx)
    n = len(idx)
    live = np.asarray((idx >= START) & (idx < END))

    o_vals = o.to_numpy(dtype=float)
    # r_next[i] = o[i+2]/o[i+1]-1, 0 if NaN
    with np.errstate(invalid="ignore", divide="ignore"):
        r_next = o.shift(-2).to_numpy(dtype=float) / o.shift(-1).to_numpy(dtype=float) - 1
    r_next = np.nan_to_num(r_next, nan=0.0, posinf=0.0, neginf=0.0)

    # carry sleeves
    carry_real, expo_real = build_real_carry(idx, carry_lab)
    carry_off_s = pd.read_parquet(ROOT / "artifacts" / "research" / "carry" / "carry_oos_fee0.0004.parquet")["carry"]
    carry_off = carry_off_s.reindex(idx).fillna(0.0)
    expo_off = pd.Series(1.0, index=idx)

    # vol/s shared? realized depends on carry -> compute separately per mode
    def vol_s(carry):
        c = carry.reindex(idx).fillna(0.0)
        oo = o.reindex(idx)
        books_s = books.reindex(idx)
        with np.errstate(invalid="ignore", divide="ignore"):
            ret1 = (oo / oo.shift(1) - 1)
        realized = W_BOOKS * (books_s.shift(2) * ret1).sum(axis=1) + C_REAL * c.shift(1)
        vol = realized.rolling(360, min_periods=120).std() * np.sqrt(6 * 365)
        s = np.minimum(TARGET / vol.to_numpy(dtype=float), CAP)
        s = np.where(np.isnan(s), 1.0, s)
        return s, realized

    s_off, _ = vol_s(carry_off)
    s_real, _ = vol_s(carry_real)

    fund_real = load_funding_real(idx)
    stats = load_exec_stats(idx, v135)
    fee_b, rel_b, fee_s, rel_s = exec_arrays(stats, cols)
    low_arr, high_arr = load_low_high(idx, cols)

    # realism-off loop (must match v154)
    out_off = run_loop(books, o, carry_off, expo_off, None, fee_b, rel_b, fee_s, rel_s,
                       s_off, r_next, live, mode="off")
    # real loop
    out_real = run_loop(books, o, carry_real, expo_real, fund_real, fee_b, rel_b, fee_s, rel_s,
                        s_real, r_next, live, mode="real")

    def pack(out, label):
        net_s = pd.Series(out["net"], index=idx)
        turn_s = pd.Series(out["turn"], index=idx)
        g_s = pd.Series(out["g"], index=idx)
        summ = v110.summarize(net_s, turn_s, g_s)
        wb, lo_a, hi_a = out["w"], low_arr, high_arr
        worst_ib, _ = intrabar_bound(out["eq"], wb, out["exec"], out["funding"], live,
                                     o_vals, lo_a, hi_a)
        comp = {k: float(np.sum(out[k][live])) for k in ("gross", "exec", "funding", "carry_pnl", "carry_cost", "net")}
        return dict(label=label, summary=summ, intrabar_bound=worst_ib, components=comp,
                    n_live=int(live.sum()), n=len(idx))

    rep_off = pack(out_off, "realism_off")
    rep_real = pack(out_real, "real")

    replication = {
        "target_v154": {"monthly_pct": 3.515, "full_path_dd": 19.15},
        "realism_off": {
            "monthly_pct": rep_off["summary"]["monthly_pct"],
            "yearly": rep_off["summary"]["yearly"],
            "full_path_dd": rep_off["summary"]["full_path_dd"],
            "worst_year_dd": rep_off["summary"]["worst_year_dd"],
            "intrabar_bound": rep_off["intrabar_bound"],
            "components": rep_off["components"],
        },
        "real": {
            "monthly_pct": rep_real["summary"]["monthly_pct"],
            "yearly": rep_real["summary"]["yearly"],
            "full_path_dd": rep_real["summary"]["full_path_dd"],
            "worst_year_dd": rep_real["summary"]["worst_year_dd"],
            "intrabar_bound": rep_real["intrabar_bound"],
            "components": rep_real["components"],
        },
        "params": {
            "target": TARGET, "cap": CAP, "w_books": W_BOOKS, "w_carry": W_CARRY,
            "carry_lev": CARRY_LEV, "start": str(START), "end": str(END),
            "budget": "0.95 cap with carry-first cut; w scaled to sum|w|=4.75",
            "min_notional_usdt": 10000, "thresholds": {"BTCUSDT": 100, "ETHUSDT": 20, "others": 5},
            "exec": "v135 10bps limit; maker fee 0.0002 rel ∓0.001 else taker 0.0005 rel p15/p0-1±0.0002",
            "funding": "xs fundingRate floored-4h sums reindexed shifted-2; pnl=-sum(w*f)",
            "carry_real": "per-symbols rp/rs shift(-2)/shift(-1), fund rate.shift(-2), ret=(pos*(fund+rs-rp)-|dd|*0.0015)/1.2; per-anchor argmax mean/std; fwd 365d; carry=mean ret, expo=mean pos",
            "carry_cost_real": "|dc|/1.2*expo*0.0015",
            "carry_off": "carry_oos_fee0.0004, expo=1, cost=|dc|*2*0.0004/1.2, funding=-0.00005*sum(max(w,0))",
            "vol": "rolling std 360 min 120 *sqrt(6*365); s=min(0.25/vol,2) else 1",
            "governor": "clip((0.20-(1-eq[j]/peak540))/0.10) j=i-2",
        },
    }
    (HERE / "replication.json").write_text(json.dumps(replication, indent=1, default=str))
    print(json.dumps({k: replication[k] for k in ("target_v154",)} , indent=1))
    print("OFF monthly", rep_off["summary"]["monthly_pct"], "DD", rep_off["summary"]["full_path_dd"],
          "IB", rep_off["intrabar_bound"])
    print("REAL monthly", rep_real["summary"]["monthly_pct"], "DD", rep_real["summary"]["full_path_dd"],
          "IB", rep_real["intrabar_bound"])


if __name__ == "__main__":
    main()
