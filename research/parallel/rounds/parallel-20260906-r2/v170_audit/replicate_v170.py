"""v170 blind audit Part A replication.

Blind rule: does NOT read research/.../v170/* nor v170_result.json
nor v170_exec_window.py until replication.json is saved.
Base: audited engine_real replication (engine_real_audit/audit_engine.py),
imported for books/carry/funding/vol/loop; ONLY the execution arrays are
replaced with the W-parameterized 1m window from the assignment:

Per symbol, 1m klines (v135.load_1m), holding bar T = t + 4h, minute offsets
inside T: p0 = open at offset 0, lo/hi = min low / max high over offsets
2..W-1, pW = open at offset W (NaN -> p0).
Buy: maker if lo < p0*(1-0.001): fee 0.0002, rel -0.001;
  else fee 0.0005, rel pW/p0 - 1 + 0.0002.
Sell symmetric (hi > p0*1.001: fee 0.0002, rel +0.001;
  else fee 0.0005, rel pW/p0 - 1 - 0.0002).
No p0 -> taker with rel +/-0.0002.
W in (15, 60, 120); W=15 must equal engine_real (3.708 / 18.87).
Target 0.25, governor on, all realism on.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parents[4]
ROUND2 = ROOT / "research" / "parallel" / "rounds" / "parallel-20260906-r2"
OUT = HERE / "replication.json"

WS = (15, 60, 120)
D = 0.001
TARGET_MONTHLY_W15 = 3.708
TARGET_DD_W15 = 18.87


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def bar_stats_W(m_1m, W):
    """Per 4h bar T: p0 (open at offset 0), lo/hi over offsets 2..W-1, pW (open at W)."""
    T = m_1m["open_time"].dt.floor("4h")
    off = ((m_1m["open_time"] - T).dt.total_seconds() // 60).astype(int)
    p0 = m_1m[off == 0].set_index(T[off == 0])["open"]
    wmask = (off >= 2) & (off <= W - 1)
    lo = m_1m[wmask].groupby(T[wmask])["low"].min()
    hi = m_1m[wmask].groupby(T[wmask])["high"].max()
    pW = m_1m[off == W].set_index(T[off == W])["open"]
    return pd.DataFrame({"p0": p0, "lo": lo, "hi": hi, "pW": pW})


def exec_arrays_W(idx, cols, v135, W):
    n = len(idx)
    fee_b = np.zeros((n, len(cols)))
    rel_b = np.zeros((n, len(cols)))
    fee_s = np.zeros((n, len(cols)))
    rel_s = np.zeros((n, len(cols)))
    # keep aligned stats for diagnostics (pW/p0 drift on taker branch)
    drift = np.zeros((n, len(cols)))
    have_m = np.zeros((n, len(cols)), dtype=bool)
    maker_b_m = np.zeros((n, len(cols)), dtype=bool)
    maker_s_m = np.zeros((n, len(cols)), dtype=bool)
    for j, s in enumerate(cols):
        m = v135.load_1m(s)
        st = bar_stats_W(m, W).reindex(idx + pd.Timedelta(hours=4)).set_axis(idx)
        p0 = st["p0"].to_numpy(dtype=float)
        lo = st["lo"].to_numpy(dtype=float)
        hi = st["hi"].to_numpy(dtype=float)
        pW = st["pW"].to_numpy(dtype=float)
        have = ~np.isnan(p0)
        pWf = np.where(np.isnan(pW), p0, pW)
        with np.errstate(invalid="ignore", divide="ignore"):
            mv = np.where(have, pWf / np.where(have, p0, 1.0) - 1, 0.0)
        mv = np.nan_to_num(mv, nan=0.0, posinf=0.0, neginf=0.0)
        fb = have & (lo < p0 * (1 - D))
        fs = have & (hi > p0 * (1 + D))
        fee_b[:, j] = np.where(fb, 0.0002, 0.0005)
        rel_b[:, j] = np.where(fb, -D, mv + 0.0002)
        fee_s[:, j] = np.where(fs, 0.0002, 0.0005)
        rel_s[:, j] = np.where(fs, D, mv - 0.0002)
        drift[:, j] = mv
        have_m[:, j] = have
        maker_b_m[:, j] = fb
        maker_s_m[:, j] = fs
    return fee_b, rel_b, fee_s, rel_s, drift, have_m, maker_b_m, maker_s_m


def maker_shares(w_all, fee_b, fee_s, live):
    dw = np.diff(w_all, axis=0, prepend=np.zeros((1, w_all.shape[1])))
    buys = (dw > 0) & live[:, None]
    sells = (dw < 0) & live[:, None]
    b_tot = int(buys.sum())
    s_tot = int(sells.sum())
    b_mk = int(((fee_b == 0.0002) & buys).sum())
    s_mk = int(((fee_s == 0.0002) & sells).sum())
    return {
        "buy_orders_live": b_tot,
        "buy_maker": b_mk,
        "buy_maker_share": round(b_mk / b_tot, 4) if b_tot else None,
        "sell_orders_live": s_tot,
        "sell_maker": s_mk,
        "sell_maker_share": round(s_mk / s_tot, 4) if s_tot else None,
        "all_orders_live": b_tot + s_tot,
        "all_maker": b_mk + s_mk,
        "all_maker_share": round((b_mk + s_mk) / (b_tot + s_tot), 4) if (b_tot + s_tot) else None,
    }


def main():
    v144 = _load("audit_v144_w170", ROUND2 / "v144" / "v144_deploy_v3.py")
    carry_lab = _load("audit_carry_lab_w170", ROOT / "scripts" / "carry_lab.py")
    audit = _load("audit_engine_w170", ROUND2 / "engine_real_audit" / "audit_engine.py")
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

    with np.errstate(invalid="ignore", divide="ignore"):
        r_next = o.shift(-2).to_numpy(dtype=float) / o.shift(-1).to_numpy(dtype=float) - 1
    r_next = np.nan_to_num(r_next, nan=0.0, posinf=0.0, neginf=0.0)

    carry_real, expo_real = audit.build_real_carry(idx, carry_lab)

    def vol_s(carry):
        c = carry.reindex(idx).fillna(0.0)
        oo = o.reindex(idx)
        books_s = books.reindex(idx)
        with np.errstate(invalid="ignore", divide="ignore"):
            ret1 = oo / oo.shift(1) - 1
        realized = audit.W_BOOKS * (books_s.shift(2) * ret1).sum(axis=1) + audit.C_REAL * c.shift(1)
        vol = realized.rolling(360, min_periods=120).std() * np.sqrt(6 * 365)
        s = np.minimum(audit.TARGET / vol.to_numpy(dtype=float), audit.CAP)
        return np.where(np.isnan(s), 1.0, s)

    s_real = vol_s(carry_real)
    fund_real = audit.load_funding_real(idx)

    results = {}
    for W in WS:
        fee_b, rel_b, fee_s, rel_s, drift, have_m, fb_m, fs_m = exec_arrays_W(idx, cols, v135, W)
        out = audit.run_loop(books, o, carry_real, expo_real, fund_real,
                             fee_b, rel_b, fee_s, rel_s, s_real, r_next, live, mode="real")
        net_s = pd.Series(out["net"], index=idx)
        turn_s = pd.Series(out["turn"], index=idx)
        g_s = pd.Series(out["g"], index=idx)
        summ = v110.summarize(net_s, turn_s, g_s)
        comp = {k: float(np.sum(out[k][live])) for k in ("gross", "exec", "funding", "carry_pnl", "carry_cost", "net")}
        comp_pct = {k: round(100 * float(v), 2) for k, v in comp.items()}
        ms = maker_shares(out["w"], fee_b, fee_s, live)
        # diagnostics: yearly concentration + taker drift
        yearly_net = [float(y["net_pct"]) for y in summ["yearly"]]
        net_sum_live = float(np.sum(out["net"][live]))
        per_year_net_sum = []
        for y in summ["yearly"]:
            a0 = pd.Timestamp(y["anchor"], tz="UTC")
            mk = (idx >= a0) & (idx < a0 + pd.Timedelta(days=365))
            per_year_net_sum.append(float(np.sum(out["net"][mk])))
        max_share = (max(per_year_net_sum) / net_sum_live) if net_sum_live else None
        # taker drift check: for taker & have, rel_b - 0.0002 must equal drift
        dw = np.diff(out["w"], axis=0, prepend=np.zeros((1, out["w"].shape[1])))
        taker_b = (~fb_m) & have_m & (dw > 0) & live[:, None]
        taker_s = (~fs_m) & have_m & (dw < 0) & live[:, None]
        dev_b = np.abs((rel_b - 0.0002 - drift)[taker_b]).max() if taker_b.any() else 0.0
        dev_s = np.abs((rel_s + 0.0002 - drift)[taker_s]).max() if taker_s.any() else 0.0
        taker_diag = {
            "taker_buy_orders_live": int(taker_b.sum()),
            "taker_sell_orders_live": int(taker_s.sum()),
            "max_abs_dev_buy_rel_minus_drift": float(dev_b),
            "max_abs_dev_sell_rel_minus_drift": float(dev_s),
            "mean_drift_taker_buy": float(drift[taker_b].mean()) if taker_b.any() else None,
            "mean_drift_taker_sell": float(drift[taker_s].mean()) if taker_s.any() else None,
            "share_taker_buy_nonzero_drift": float(np.mean(np.abs(drift[taker_b]) > 1e-9)) if taker_b.any() else None,
        }
        results[f"W{W}"] = {
            "monthly_pct": summ["monthly_pct"],
            "yearly": summ["yearly"],
            "full_path_dd": summ["full_path_dd"],
            "worst_year_dd": summ["worst_year_dd"],
            "maker": ms,
            "components_sum": comp,
            "components_pct_of_start_equity_sum": comp_pct,
            "diagnostic": {
                "yearly_net_pct": yearly_net,
                "per_year_net_sum": per_year_net_sum,
                "total_net_sum_live": net_sum_live,
                "max_year_share_of_net_sum": max_share,
                "taker_drift": taker_diag,
            },
        }
        print(f"W={W} monthly={summ['monthly_pct']} DD={summ['full_path_dd']} "
              f"maker={ms['all_maker_share']} (buy {ms['buy_maker_share']}, sell {ms['sell_maker_share']}) "
              f"comp={comp_pct}", flush=True)

    w15 = results["W15"]
    assert w15["monthly_pct"] == TARGET_MONTHLY_W15, (w15["monthly_pct"], TARGET_MONTHLY_W15)
    assert w15["full_path_dd"] == TARGET_DD_W15, (w15["full_path_dd"], TARGET_DD_W15)

    # gain-concentration diagnostic (not a pass/fail gate, reported)
    for key, r in results.items():
        ys = r["diagnostic"]["yearly_net_pct"]
        print(key, "yearly_net_pct", ys, "max_share", round(r["diagnostic"]["max_year_share_of_net_sum"], 3),
              flush=True)

    replication = {
        "version": "v170_audit_replication",
        "blind": "did_not_open_research_v170_until_this_file_saved",
        "books": "v154 (A+B+D)/3 cached",
        "target": 0.25,
        "governor": True,
        "realism": "all on (funding, carry_real, budget, min_notional)",
        "exec_spec": ("per symbol 1m klines v135.load_1m, T=t+4h, p0=open@0, lo/hi=min/max over 2..W-1, "
                      "pW=open@W NaN->p0; buy maker lo<p0*0.999 fee 0.0002 rel -0.001 else fee 0.0005 "
                      "rel pW/p0-1+0.0002; sell hi>p0*1.001 fee 0.0002 rel +0.001 else fee 0.0005 "
                      "rel pW/p0-1-0.0002; no p0 -> taker rel +/-0.0002"),
        "W": list(WS),
        "engine_real_reference": {"monthly_pct": 3.708, "full_path_dd": 18.87},
        "results": results,
        "params": {
            "D": D, "start": str(START), "end": str(END),
            "vol": "rolling std 360 min 120 *sqrt(6*365); s=min(0.25/vol,2) else 1",
            "governor": "clip((0.20-(1-eq[j]/peak540))/0.10) j=i-2",
            "budget": "0.95 cap with carry-first cut; w scaled to sum|w|=4.75",
            "min_notional_usdt": 10000,
        },
    }
    OUT.write_text(json.dumps(replication, indent=1, default=str))
    print("saved", OUT)


if __name__ == "__main__":
    main()
