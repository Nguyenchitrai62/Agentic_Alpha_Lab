"""oc_vipfees: reprice G2 (R2B1D17BFG2) fees under Bybit VIP1/VIP2.

Reads ONLY research/tournament/oc_kpi_g2/{events,barsum}_s{0..3}.parquet and
results_equity.json. No 1m data, one process. See PLAN.md (pre-registered).
Usage: .venv/Scripts/python.exe research/tournament/oc_vipfees/compute_vipfees.py
"""
from __future__ import annotations

import json
from collections import deque
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
G2 = HERE.parent / "oc_kpi_g2"

# Gate (VIP0) + assumed VIP schedules (fraction of notional). No repo doc lists
# Bybit VIP tiers; values cross-checked vs Bybit public derivatives schedule.
VIP0 = {"maker": 0.0002, "taker": 0.00055}
VIP1 = {"maker": 0.00018, "taker": 0.0004}
VIP2 = {"maker": 0.00016, "taker": 0.000375}
TIERS = {"VIP0": VIP0, "VIP1": VIP1, "VIP2": VIP2}
# Public Bybit derivatives 30d-volume thresholds (assumed, stated in REPORT).
THRESH = {"VIP1": 10_000_000.0, "VIP2": 25_000_000.0}

MAKER_LEGS = {"book_fill", "book_add", "book_reduce", "book_partial",
              "book_tp", "book_close", "rung_fill", "rung_tp"}
TAKER_LEGS = {"book_stop", "rung_sl", "rung_timeout"}

ANCH = [pd.Timestamp(f"{y}-09-24", tz="UTC") for y in (2021, 2022, 2023, 2024, 2025)]
ANCH_END = pd.Timestamp("2026-09-24", tz="UTC")
FULL_MONTHS = [f"{y:04d}-{m:02d}" for y in (2021, 2022, 2023, 2024, 2025, 2026)
               for m in range(1, 13)]
FULL_MONTHS = [m for m in FULL_MONTHS if "2021-10" <= m <= "2026-09"]  # 60


def month_of(t) -> str:
    t = pd.Timestamp(t)
    return f"{t.year:04d}-{t.month:02d}"


def year_of(t):
    t = pd.Timestamp(t)
    for k in range(5):
        end = ANCH[k + 1] if k < 4 else ANCH_END
        if ANCH[k] <= t < end:
            return k
    return None


def main():
    dm1 = VIP0["maker"] - VIP1["maker"]
    dt1 = VIP0["taker"] - VIP1["taker"]
    dm2 = VIP0["maker"] - VIP2["maker"]
    dt2 = VIP0["taker"] - VIP2["taker"]

    # --- load bars + events per shift; attribute legs to holding bars ---
    n_months = {}
    # per-shift monthly accumulators (sub-equity-fraction units); mix = mean
    # over shifts at the end (shift bar grids are phase-offset, so keys differ)
    mS1, mS2, mV = {}, {}, {}
    tot_maker_w = 0.0                 # sum |w| over maker legs (sub-fraction units)
    tot_taker_w = 0.0
    side_counts = {}
    max_t = pd.Timestamp("2021-01-01", tz="UTC")
    n_fee_legs = 0
    # per-shift structures for flip counts
    flip = {"VIP1": {"rung": 0, "rung_n": 0, "book": 0, "book_n": 0},
            "VIP2": {"rung": 0, "rung_n": 0, "book": 0, "book_n": 0}}
    for s in range(4):
        bs = pd.read_parquet(G2 / f"barsum_s{s}.parquet")
        bs["t"] = pd.to_datetime(bs["t"], utc=True)
        bs = bs.sort_values("t").reset_index(drop=True)
        bts = bs["t"].to_numpy()
        eq = bs["equity"].to_numpy(float)
        # per-bar accumulators for this shift (sub-equity USD with base 1.0 start)
        save1, save2, voleq = {}, {}, {}
        for i, t in enumerate(bs["t"]):
            k = str(pd.Timestamp(t))
            save1[k] = 0.0
            save2[k] = 0.0
            voleq[k] = 0.0
        bar_eq = {str(pd.Timestamp(t)): float(e) for t, e in zip(bs["t"], eq)}
        ev = pd.read_parquet(G2 / f"events_s{s}.parquet")
        ev["t"] = pd.to_datetime(ev["t"], utc=True)
        if (ev["t"] >= ANCH_END).any():
            raise RuntimeError(f"shift {s}: event at/after 2026-09-24")
        max_t = max(max_t, ev["t"].max())
        side_counts[s] = ev[ev["kind"] == "book_fill"]["side"].value_counts().to_dict()
        ev = ev.sort_values("t").reset_index(drop=True)
        bidx = (pd.to_datetime(ev["t"]) - pd.Timedelta(hours=4)).values  # bar start <= t
        # holding-bar start for each event: last barsum t <= event t
        pos = np.searchsorted(bts, ev["t"].to_numpy()) - 1
        pos = np.clip(pos, 0, len(bs) - 1)
        for j, r in enumerate(ev.itertuples()):
            k = r.kind
            if k not in MAKER_LEGS and k not in TAKER_LEGS:
                continue
            w = abs(float(r.weight))
            bk = str(pd.Timestamp(bts[pos[j]]))
            eqb = float(eq[pos[j]])
            is_maker = k in MAKER_LEGS
            d1 = dm1 if is_maker else dt1
            d2 = dm2 if is_maker else dt2
            save1[bk] += w * d1 * eqb
            save2[bk] += w * d2 * eqb
            voleq[bk] += w * eqb
            n_fee_legs += 1
            if is_maker:
                tot_maker_w += w
            else:
                tot_taker_w += w
        # --- flip counts: rungs FIFO per symbol; book episodes (v213 loop) ---
        evs = ev.sort_values("t").reset_index(drop=True)
        pend = {}
        for r in evs.itertuples():
            if r.kind == "rung_fill":
                pend.setdefault(r.symbol, deque()).append(r)
            elif r.kind in ("rung_sl", "rung_tp", "rung_timeout"):
                q0 = pend.get(r.symbol)
                if q0:
                    f0 = q0.popleft()
                    wf, wx = abs(float(f0.weight)), abs(float(r.weight))
                    ret = float(r.ret)
                    base = wf * ret
                    ex_m = dm1 if r.kind == "rung_tp" else dt1
                    ex_m2 = dm2 if r.kind == "rung_tp" else dt2
                    s1 = wf * dm1 + wx * ex_m
                    s2 = wf * dm2 + wx * ex_m2
                    for tn, sv in (("VIP1", s1), ("VIP2", s2)):
                        flip[tn]["rung_n"] += 1
                        if base < 0 <= base + sv:
                            flip[tn]["rung"] += 1
        posd, nbook = {}, 0
        for e in evs.itertuples():
            kk, sym = e.kind, e.symbol
            if kk == "book_fill":
                q = abs(e.weight) / e.price
                posd[sym] = dict(side=1 if e.side == "buy" else -1, qty=q,
                                 cost=q * e.price, proceeds=0.0,
                                 f0=q * e.price * VIP0["maker"],
                                 s1=q * e.price * dm1, s2=q * e.price * dm2)
                continue
            o = posd.get(sym)
            if o is None:
                continue
            if kk == "book_add":
                q = abs(e.weight) / e.price
                o["qty"] += q
                o["cost"] += q * e.price
                o["f0"] += q * e.price * VIP0["maker"]
                o["s1"] += q * e.price * dm1
                o["s2"] += q * e.price * dm2
            elif kk in ("book_reduce", "book_partial"):
                q = min(abs(e.weight) / e.price, o["qty"])
                o["qty"] -= q
                o["proceeds"] += q * e.price
                o["f0"] += q * e.price * VIP0["maker"]
                o["s1"] += q * e.price * dm1
                o["s2"] += q * e.price * dm2
            elif kk in ("book_stop", "book_tp", "book_close"):
                o["proceeds"] += o["qty"] * e.price
                is_t = kk == "book_stop"
                o["f0"] += o["qty"] * e.price * (VIP0["taker"] if is_t else VIP0["maker"])
                o["s1"] += o["qty"] * e.price * (dt1 if is_t else dm1)
                o["s2"] += o["qty"] * e.price * (dt2 if is_t else dm2)
                net = (o["side"] * (o["proceeds"] - o["cost"]) - o["f0"]) / o["cost"]
                for tn, sv in (("VIP1", o["s1"]), ("VIP2", o["s2"])):
                    flip[tn]["book_n"] += 1
                    if net < 0 <= net + sv / o["cost"]:
                        flip[tn]["book"] += 1
                posd.pop(sym, None)
        # per-shift calendar-month fractions (divide USD by contemporary equity)
        for k in save1:
            e = bar_eq[k]
            m = month_of(pd.Timestamp(k))
            d = mS1.setdefault(s, {})
            d[m] = d.get(m, 0.0) + (save1[k] / e if e else 0.0)
            d = mS2.setdefault(s, {})
            d[m] = d.get(m, 0.0) + (save2[k] / e if e else 0.0)
            d = mV.setdefault(s, {})
            d[m] = d.get(m, 0.0) + (voleq[k] / e if e else 0.0)

    # --- mix = mean over the 4 phase sub-accounts (1/4 capital each) ---
    S1, S2, V = {}, {}, {}
    for s in range(4):
        for m, v in mS1[s].items():
            S1[m] = S1.get(m, 0.0) + v / 4
        for m, v in mS2[s].items():
            S2[m] = S2.get(m, 0.0) + v / 4
        for m, v in mV[s].items():
            V[m] = V.get(m, 0.0) + v / 4
    for m in list(S1):
        assert S1[m] >= 0 and S2[m] >= 0, m

    # --- old monthly table -> new tables ---
    eqj = json.loads((G2 / "results_equity.json").read_text())
    old = {m: r for m, r in eqj["monthly"]}
    months = [m for m, _ in eqj["monthly"]]
    assert months[0] == "2021-09" and months[-1] == "2026-09" and len(months) == 61
    new1 = {m: (1 + old[m] / 100) + S1.get(m, 0.0) - 1 for m in months}
    new2 = {m: (1 + old[m] / 100) + S2.get(m, 0.0) - 1 for m in months}

    def geomean(rmap, ms):
        p = 1.0
        for m in ms:
            p *= 1 + rmap[m]
        return p ** (1 / len(ms)) - 1

    full = [m for m in months if m in FULL_MONTHS]
    assert len(full) == 60
    years_ms = [[m for m in full if m[0:4] == str(y) and m in full] for y in range(2022, 2027)]
    # anchor years: y0 = 2021-10..2022-09, ... y4 = 2025-10..2026-09
    anch_ms = []
    for a in range(5):
        y0, y1 = 2021 + a, 2022 + a
        ms = [m for m in full
              if (m[0:4] == str(y0) and m >= f"{y0}-10") or (m[0:4] == str(y1) and m <= f"{y1}-09")]
        assert len(ms) == 12, (a, ms)
        anch_ms.append(ms)
    oldf = {m: old[m] / 100 for m in months}
    g_old_5y = geomean(oldf, full)
    g1_5y = geomean(new1, full)
    g2_5y = geomean(new2, full)
    net_old = float(np.prod([1 + oldf[m] for m in months]) - 1)
    net1 = float(np.prod([1 + new1[m] for m in months]) - 1)
    net2 = float(np.prod([1 + new2[m] for m in months]) - 1)
    per_year = []
    for i, ms in enumerate(anch_ms):
        ro = geomean(oldf, ms)
        r1 = geomean(new1, ms)
        r2 = geomean(new2, ms)
        per_year.append({
            "year": i, "anchor": ANCH[i].strftime("%Y-%m-%d"),
            "months": ms[0] + ".." + ms[-1],
            "R_old_pct": round(ro * 100, 4),
            "R_VIP1_pct": round(r1 * 100, 4),
            "R_VIP2_pct": round(r2 * 100, 4),
            "gain_VIP1_pp": round((r1 - ro) * 100, 4),
            "gain_VIP2_pp": round((r2 - ro) * 100, 4),
            "mean_save_VIP1_pp": round(float(np.mean([S1.get(m, 0.0) for m in ms])) * 100, 4),
            "mean_save_VIP2_pp": round(float(np.mean([S2.get(m, 0.0) for m in ms])) * 100, 4),
        })
    tau = float(np.mean([V.get(m, 0.0) for m in full]))  # turnover / month
    sbar1 = float(np.mean([S1.get(m, 0.0) for m in full]))
    sbar2 = float(np.mean([S2.get(m, 0.0) for m in full]))
    out = {
        "variant": "R2B1D17BFG2",
        "fee_schedules": {k: {"maker": v["maker"], "taker": v["taker"]} for k, v in TIERS.items()},
        "fee_schedule_note": "VIP0 = gate (Bybit VIP0 derivatives). No repo doc lists "
                             "Bybit VIP tiers; VIP1/VIP2 rates + 10M/25M 30d-volume thresholds are "
                             "ASSUMED values cross-checked vs Bybit public derivatives schedule 2026-10-06.",
        "tier_volume_threshold_30d_usdt": THRESH,
        "method": ("additive per-bar: leg fee=|weight|xrate (weight=fraction of phase sub equity); "
                   "per-shift monthly saving = sum of bar savings / contemporary bar equity; "
                   "mix S(M) = mean over the 4 phase sub-accounts; "
                   "1+R_new=1+R_old+S(M); exit-vs-fill price drift ignored; funding identical, excluded."),
        "leg_types": {"maker": sorted(MAKER_LEGS), "taker": sorted(TAKER_LEGS),
                      "ignored": ["order_issue", "order_expire", "order_cancel", "sl_move"]},
        "fee_legs_total": int(n_fee_legs),
        "sum_abs_weight_sub_units": {"maker_legs": round(tot_maker_w, 2),
                                     "taker_legs": round(tot_taker_w, 2)},
        "book_fill_side_counts_per_shift": {str(k): v for k, v in side_counts.items()},
        "max_event_t": str(max_t),
        "data_end": "2026-09-24 00:00:00+00:00",
        "monthly_saving_pct": {
            m: {"VIP1": round(S1.get(m, 0.0) * 100, 4),
                "VIP2": round(S2.get(m, 0.0) * 100, 4)} for m in months},
        "monthly_volume_pct_of_equity": {m: round(V.get(m, 0.0) * 100, 3) for m in months},
        "turnover_per_month": round(tau, 5),
        "mean_monthly_saving": {"VIP1_pct": round(sbar1 * 100, 4),
                                "VIP2_pct": round(sbar2 * 100, 4)},
        "five_year": {
            "net_old_pct": round(net_old * 100, 2),
            "net_VIP1_pct": round(net1 * 100, 2),
            "net_VIP2_pct": round(net2 * 100, 2),
            "monthly_geomean_old_pct": round(g_old_5y * 100, 4),
            "monthly_geomean_VIP1_pct": round(g1_5y * 100, 4),
            "monthly_geomean_VIP2_pct": round(g2_5y * 100, 4),
            "gain_VIP1_pp_per_month": round((g1_5y - g_old_5y) * 100, 4),
            "gain_VIP2_pp_per_month": round((g2_5y - g_old_5y) * 100, 4),
        },
        "per_anchor_year": per_year,
        "volume_at_equity_usdt": {
            str(int(E)): {
                "monthly_volume_usdt": round(tau * E, 0),
                "VIP1_threshold_share": round(tau * E / THRESH["VIP1"], 4),
                "VIP2_threshold_share": round(tau * E / THRESH["VIP2"], 4),
            } for E in (5_000, 10_000, 50_000)},
        "equity_required_usdt": {
            "VIP1": round(THRESH["VIP1"] / tau, 0),
            "VIP2": round(THRESH["VIP2"] / tau, 0)},
        "fee_usd_saved_per_month": {
            str(int(E)): {"VIP1": round(sbar1 * E, 2), "VIP2": round(sbar2 * E, 2)}
            for E in (5_000, 10_000, 50_000)},
        "sign_flips": {k: dict(v) for k, v in flip.items()},
        "drawdown_note": "fee saving is non-negative on every bar, so the VIP1/VIP2 equity "
                         "path lies pointwise >= the VIP0 path; DD unchanged (not recomputed).",
        "checks": {
            "all_monthly_savings_nonneg": bool(all(S1.get(m, 0) >= 0 and S2.get(m, 0) >= 0
                                                    for m in months)),
            "net_old_reproduces_oc_kpi_g2": round(net_old * 100, 2),
            "n_months": len(months),
            "n_full_months": len(full),
        },
    }
    (HERE / "results.json").write_text(json.dumps(out, indent=1))
    print("turnover/month", round(tau, 5), flush=True)
    print("gain VIP1/VIP2 pp/mo", round((g1_5y - g_old_5y) * 100, 4),
          round((g2_5y - g_old_5y) * 100, 4), flush=True)
    print("E_req VIP1/VIP2", round(THRESH["VIP1"] / tau), round(THRESH["VIP2"] / tau), flush=True)
    print("flips", flip, flush=True)


if __name__ == "__main__":
    main()
