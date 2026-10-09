"""oc_coinattrib: per-coin and per-side attribution of G2 (book timing + dip).

Pre-registered PLAN.md (no tuning, single method). Reuses
research/tournament/oc_bookattrib/analyze_bookattrib.py read-only for the
book vectorised gross (deployed book rows, bear filter, 4 clocks) and
research/tournament/oc_stoptf/fills.parquet D0 leg for the dip replica
(validated against oc_placebo_dip base 7.718304 before use).

Run (1m opens for shifted clocks -> use the shared semaphore):
  .venv/Scripts/python.exe scripts/heavy_slot.py run --tag oc_coinattrib \
    --min-free-gb 2.0 -- .venv/Scripts/python.exe \
    research/tournament/oc_coinattrib/analyze_coinattrib.py
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
BOOKATTRIB = ROOT / "research/tournament/oc_bookattrib/analyze_bookattrib.py"
FILLS = ROOT / "research/tournament/oc_stoptf/fills.parquet"
PLACEBO_RES = ROOT / "research/tournament/oc_placebo_dip/results.json"

ANCH = [pd.Timestamp(f"{y}-09-24", tz="UTC") for y in (2021, 2022, 2023, 2024, 2025)]
YEAR = pd.Timedelta(days=365)
BLOCK = 42
NPERM = 500
BASE_SEED = 7


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def monthly_geometric(end_factor: float) -> float:
    return 100 * (float(end_factor) ** (1 / 12) - 1)


def herfindahl(shares) -> float:
    s = np.asarray(shares, dtype=float)
    return float(np.sum(s ** 2))


def main():
    BA = _load("ba_coinattrib", BOOKATTRIB)
    SYMS = BA.SYMS
    ncoins = len(SYMS)

    print("validating G2 baseline ...", flush=True)
    BA.validate_g2()

    print("validating dip ledger against oc_placebo_dip base ...", flush=True)
    df = pd.read_parquet(FILLS)
    assert len(df) == 22312, len(df)
    assert set(df["sym"].unique()) == set(SYMS), df["sym"].unique()
    pb = json.loads(PLACEBO_RES.read_text())
    assert abs(float(pb["base_sum5y"]) - 7.718304) < 1e-4, pb["base_sum5y"]
    exp_s = [r["S"] for r in pb["base_mean4"]]
    df["wy"] = df["w"].to_numpy(float) * df["d0"].to_numpy(float)
    got_s = []
    for y in range(5):
        sub = df[df["y"] == y]
        m = float(np.mean([sub[sub["phase"] == p]["wy"].sum() for p in (0, 1, 2, 3)]))
        got_s.append(m)
    for g, e in zip(got_s, exp_s):
        assert abs(g - e) < 1e-6, (got_s, exp_s)
    print(f"dip ledger OK: n=22312 base_sum5y={sum(got_s):.6f}", flush=True)

    print("loading standard books ...", flush=True)
    books154, opens_std, std_nobear, sb_std, bear_std = BA.load_books_standard()
    print("loading shifted opens (1m open column only) ...", flush=True)
    shifted = BA.load_shifted_opens()

    # ---------------- BOOK per-coin ----------------
    per_phase_book = {}  # shift -> list per year dict
    for shift in range(4):
        idx, opens = shifted[shift]
        cols = list(books154.columns)
        assert cols == SYMS, cols
        books_bear = sb_std.reindex(idx, method="ffill").fillna(0.0)
        o = opens[cols].to_numpy(float)
        r = o[1:] / o[:-1] - 1
        w = books_bear.to_numpy(float)[:-1]
        t_idx = idx[:-1]
        valid = np.isfinite(o[:-1]).all(axis=1) & np.isfinite(o[1:]).all(axis=1)
        print(f"shift {shift}: bars {len(t_idx)}, valid {int(valid.sum())}", flush=True)
        years_out = []
        for yi, a0 in enumerate(ANCH):
            a1 = a0 + YEAR
            m = (t_idx >= a0) & (t_idx < a1) & valid
            wy = w[m]
            ry = r[m]
            n = int(m.sum())
            # totals
            b = (wy * ry).sum(axis=1)
            E = float(np.prod(1 + b))
            R = monthly_geometric(E)
            wbar = wy.mean(axis=0)
            beta_b = (wbar[None, :] * ry).sum(axis=1)
            tim = b - beta_b
            T_total = float(tim.sum())
            Et = float(np.prod(1 + tim))
            Rt = monthly_geometric(Et)
            assert np.allclose(b, beta_b + tim, atol=1e-12)
            # pooled sides
            wl = np.where(wy > 0, wy, 0.0)
            ws = np.where(wy < 0, wy, 0.0)
            Rl = monthly_geometric(float(np.prod(1 + (wl * ry).sum(axis=1))))
            Rs = monthly_geometric(float(np.prod(1 + (ws * ry).sum(axis=1))))
            # per coin
            coins_out = []
            for ci, sym in enumerate(SYMS):
                bc = wy[:, ci] * ry[:, ci]
                Ec = float(np.prod(1 + bc))
                Rc = monthly_geometric(Ec)
                betac = wbar[ci] * ry[:, ci]
                Ebc = float(np.prod(1 + betac))
                Rbc = monthly_geometric(Ebc)
                timc = bc - betac
                Etc = float(np.prod(1 + timc))
                Rtc = monthly_geometric(Etc)
                Tc = float(timc.sum())
                lc = np.where(wy[:, ci] > 0, wy[:, ci], 0.0) * ry[:, ci]
                sc = np.where(wy[:, ci] < 0, wy[:, ci], 0.0) * ry[:, ci]
                Rlc = monthly_geometric(float(np.prod(1 + lc)))
                Rsc = monthly_geometric(float(np.prod(1 + sc)))
                # per-coin placebo: shuffle w_c blocks, seed 7+ci
                rng = np.random.default_rng(BASE_SEED + ci + 1000 * (shift * 5 + yi))
                nrows = wy.shape[0]
                nb = (nrows + BLOCK - 1) // BLOCK
                blocks = [np.arange(i * BLOCK, min((i + 1) * BLOCK, nrows)) for i in range(nb)]
                full_blocks = [bl for bl in blocks if len(bl) == BLOCK]
                partial = [bl for bl in blocks if len(bl) != BLOCK]
                wc = wy[:, ci]
                rc = ry[:, ci]
                T_actual_c = Tc
                T_perms = np.empty(NPERM)
                for p in range(NPERM):
                    wp = np.empty_like(wc)
                    order = rng.permutation(len(full_blocks))
                    pos = 0
                    for oi in order:
                        bl = full_blocks[oi]
                        wp[pos:pos + BLOCK] = wc[bl]
                        pos += BLOCK
                    for bl in partial:
                        wp[bl] = wc[bl]
                    bp = wp * rc
                    betap = wp.mean() * rc
                    T_perms[p] = float((bp - betap).sum())
                pct = float((T_perms <= T_actual_c).mean())
                pval = float((1 + (T_perms >= T_actual_c).sum()) / (1 + NPERM))
                coins_out.append({
                    "sym": sym, "B_R": round(Rc, 3), "BETA_R": round(Rbc, 3),
                    "TIMING_R": round(Rtc, 3), "timing_sum": round(Tc, 4),
                    "long_R": round(Rlc, 3), "short_R": round(Rsc, 3),
                    "mean_w": round(float(wy[:, ci].mean()), 6),
                    "placebo_pct": round(100 * pct, 1), "placebo_p": round(pval, 4),
                })
            # LOCO timing (vectorised): recompute without each coin
            loco = []
            for ci, sym in enumerate(SYMS):
                keep = [k for k in range(ncoins) if k != ci]
                b_nc = (wy[:, keep] * ry[:, keep]).sum(axis=1)
                wb_nc = wy[:, keep].mean(axis=0)
                beta_nc = (wb_nc[None, :] * ry[:, keep]).sum(axis=1)
                tim_nc = b_nc - beta_nc
                R_nc = monthly_geometric(float(np.prod(1 + tim_nc)))
                loco.append({"drop_sym": sym, "TIMING_R_wo": round(R_nc, 3),
                             "tim_sum_wo": round(float(tim_nc.sum()), 4)})
            # identity: sum of coin timing == total timing (rounded outputs: looser tol)
            assert abs(sum(c["timing_sum"] for c in coins_out) - T_total) < 1e-3
            years_out.append({
                "anchor": str(a0.date()), "n_bars": n,
                "B_R": round(R, 3), "TIMING_R": round(Rt, 3),
                "timing_sum": round(T_total, 4),
                "long_R": round(Rl, 3), "short_R": round(Rs, 3),
                "coins": coins_out, "loco": loco,
            })
            print(f"s{shift} Y{yi} {a0.date()}: B={R:.3f} tim={Rt:.3f} " +
                  " ".join(f"{c['sym']}={c['TIMING_R']:.2f}" for c in coins_out), flush=True)
        per_phase_book[str(shift)] = years_out

    # 4-phase means per coin-year
    mean_book = []
    for yi, a0 in enumerate(ANCH):
        Tm = [float(np.mean([per_phase_book[str(s)][yi]["coins"][ci]["timing_sum"]
                             for s in range(4)])) for ci in range(ncoins)]
        tot = float(sum(Tm))
        shares = [(t / tot) if tot != 0 else 0.0 for t in Tm]
        H = herfindahl(shares)
        maxc = SYMS[int(np.argmax(shares))] if tot != 0 else None
        mean_book.append({
            "anchor": str(a0.date()),
            "timing_sum_mean": [round(t, 4) for t in Tm],
            "timing_sum_total": round(tot, 4),
            "timing_share": [round(s, 4) for s in shares],
            "herfindahl": round(H, 4),
            "max_coin": maxc,
            "max_share": round(float(max(shares)) if shares else 0.0, 4),
            "B_R": round(float(np.mean([per_phase_book[str(s)][yi]["B_R"] for s in range(4)])), 3),
            "TIMING_R": round(float(np.mean([per_phase_book[str(s)][yi]["TIMING_R"] for s in range(4)])), 3),
            "long_R": round(float(np.mean([per_phase_book[str(s)][yi]["long_R"] for s in range(4)])), 3),
            "short_R": round(float(np.mean([per_phase_book[str(s)][yi]["short_R"] for s in range(4)])), 3),
            "per_coin_TIMING_R": [
                round(float(np.mean([per_phase_book[str(s)][yi]["coins"][ci]["TIMING_R"]
                                            for s in range(4)])), 3)
                for ci in range(ncoins)],
            "per_coin_placebo_pct": [
                round(float(np.mean([per_phase_book[str(s)][yi]["coins"][ci]["placebo_pct"]
                                            for s in range(4)])), 1)
                for ci in range(ncoins)],
            "loco_TIMING_R_wo": [
                round(float(np.mean([next(d["TIMING_R_wo"] for d in per_phase_book[str(s)][yi]["loco"]
                                             if d["drop_sym"] == SYMS[ci]) for s in range(4)])), 3)
                for ci in range(ncoins)],
        })

    # ---------------- DIP per-coin ----------------
    # per coin-year 4-phase-mean sums + pooled win/stop
    dip_years = []
    for yi, a0 in enumerate(ANCH):
        per_phase_sums = {}
        row = {"anchor": str(a0.date())}
        Scoins = []
        for sym in SYMS:
            ss = [float(df[(df["y"] == yi) & (df["phase"] == p) & (df["sym"] == sym)]["wy"].sum())
                  for p in (0, 1, 2, 3)]
            Scoins.append(float(np.mean(ss)))
            per_phase_sums[sym] = [round(s, 6) for s in ss]
        tot = float(sum(Scoins))
        shares = [(s / tot) if tot != 0 else 0.0 for s in Scoins]
        H = herfindahl(shares)
        # pooled win / stop per coin-year
        wins, stops, ns, means = [], [], [], []
        for sym in SYMS:
            sub = df[(df["y"] == yi) & (df["sym"] == sym)]
            yv = sub["d0"].to_numpy(float)
            hh = sub["h0"].tolist()
            n = len(sub)
            win = float((yv > 0).mean()) if n else 0.0
            stop = float(sum(1 for h in hh if h in ("stop", "backstop")) / n) if n else 0.0
            wins.append(round(win, 4))
            stops.append(round(stop, 4))
            ns.append(int(round(n / 4, 2)) if False else round(float(n) / 4, 2))
            means.append(round(float(yv.mean()) if n else 0.0, 6))
        row.update({
            "S_mean": [round(s, 6) for s in Scoins],
            "S_total": round(tot, 6),
            "share": [round(s, 4) for s in shares],
            "herfindahl": round(H, 4),
            "max_coin": SYMS[int(np.argmax(shares))],
            "max_share": round(float(max(shares)), 4),
            "n_mean4": ns,
            "win_pooled": wins,
            "stop_rate_pooled": stops,
            "mean_ret": means,
            "per_phase_sums": per_phase_sums,
            "loco_S_wo": [round(tot - s, 6) for s in Scoins],
        })
        dip_years.append(row)
        print(f"dip Y{yi} {a0.date()}: S={tot:.4f} " +
              " ".join(f"{s}={v:.3f}" for s, v in zip(SYMS, Scoins)), flush=True)

    # dip DD episodes: pooled-across-phases daily exit-day sums
    daily = {}
    coin_daily = {s: {} for s in SYMS}
    for _, r in df.iterrows():
        d = str(r["xd0"])
        v = float(r["wy"])
        daily[d] = daily.get(d, 0.0) + v
        cd = coin_daily[str(r["sym"])]
        cd[d] = cd.get(d, 0.0) + v
    days = sorted(daily)
    dvals = np.array([daily[d] for d in days], float)
    cum = np.cumsum(dvals)
    # top-5 non-overlapping peak-to-trough episodes
    episodes = []
    used = np.zeros(len(days), dtype=bool)
    for _ in range(5):
        best = None
        for i in range(len(days)):
            if used[i]:
                continue
            for j in range(i + 1, len(days)):
                if used[i:j + 1].any():
                    continue
                dd = float(cum[j] - np.max(cum[i:j + 1])) if j > i else 0.0
                if dd < 0 and (best is None or dd < best[0]):
                    best = (dd, i, j)
        if best is None:
            break
        dd, i, j = best
        peak_idx = int(i + np.argmax(cum[i:j + 1]))
        episodes.append({"peak_day": days[peak_idx], "trough_day": days[j],
                         "dd": round(dd, 4)})
        used[peak_idx:j + 1] = True
    episodes.sort(key=lambda e: e["dd"])
    # per-coin contribution in episode windows (peak_day, trough_day]
    ep_coin = []
    for e in episodes:
        pk, tr = e["peak_day"], e["trough_day"]
        per = {}
        for sym in SYMS:
            cd = coin_daily[sym]
            per[sym] = round(float(sum(v for d, v in cd.items() if pk < d <= tr)), 6)
        tot = round(float(sum(per.values())), 6)
        e2 = dict(e)
        e2["per_coin"] = per
        e2["window_sum"] = tot
        ep_coin.append(e2)
    # totals across 5 episodes per coin
    tot5 = {s: round(float(sum(e["per_coin"][s] for e in ep_coin)), 6) for s in SYMS}
    grand5 = float(sum(tot5.values()))
    share5 = {s: round(tot5[s] / grand5, 4) if grand5 != 0 else 0.0 for s in SYMS}

    out = {
        "meta": {
            "strat": "R2B1D17BFG2",
            "book": "oc_bookattrib replica: research_books_d2 + v421 x0.5 bear filter, "
                    "ffill to 4 shifted clocks; r = next-bar open-to-open; "
                    "BLOCK=42 NPERM=500 per coin-year, seed=7+coin_idx+1000*(shift*5+yi)",
            "dip_src": "research/tournament/oc_stoptf/fills.parquet D0 leg only "
                       "(validated n=22312, 5y sum 7.718304 vs oc_placebo_dip)",
            "dip_dd": "pooled-across-phases daily (xd0, w*d0) path, top-5 "
                      "non-overlapping peak-to-trough episodes (exit dates)",
            "shares": "book timing_share from 4-phase-mean timing sums; "
                      "dip share from 4-phase-mean S sums; H = sum share^2",
            "g2_validation": "BA.validate_g2() asserts to the digit in-script",
        },
        "per_phase_book": per_phase_book,
        "mean_book": mean_book,
        "dip_years": dip_years,
        "dip_dd_episodes": ep_coin,
        "dip_dd_5ep_totals": {"per_coin": tot5, "grand": round(grand5, 6), "share": share5},
        "syms": SYMS,
    }
    (HERE / "tmp" / "coinattrib_raw.json").write_text(json.dumps(out, indent=1, default=str))
    print("wrote tmp/coinattrib_raw.json", flush=True)

    # ---- compact results.json ----
    def dev_count(shares_list):
        return int(sum(1 for s in shares_list[:4] if s > 0.40))

    book_max = [m["max_share"] for m in mean_book]
    dip_max = [d["max_share"] for d in dip_years]
    res = {
        "g2_validation": {"reproduced_exactly": True, "rows": {"R": 5.41, "W": 2.588, "DD": 16.91,
                                                               "full_path_dd": 16.82}},
        "dip_validation": {"n": 22312, "base_sum5y": round(float(sum(got_s)), 6),
                           "matches_placebo_dip": True},
        "book_timing_share": [
            {"anchor": m["anchor"], "shares": dict(zip(SYMS, m["timing_share"])),
             "H": m["herfindahl"], "max_coin": m["max_coin"], "max_share": m["max_share"],
             "timing_sums": dict(zip(SYMS, m["timing_sum_mean"])),
             "TIMING_R_per_coin": dict(zip(SYMS, m["per_coin_TIMING_R"])),
             "placebo_pct_per_coin": dict(zip(SYMS, m["per_coin_placebo_pct"])),
             "loco_TIMING_R_wo": dict(zip(SYMS, m["loco_TIMING_R_wo"]))}
            for m in mean_book],
        "dip_share": [
            {"anchor": d["anchor"], "S": dict(zip(SYMS, d["S_mean"])),
             "shares": dict(zip(SYMS, d["share"])), "H": d["herfindahl"],
             "max_coin": d["max_coin"], "max_share": d["max_share"],
             "win": dict(zip(SYMS, d["win_pooled"])),
             "stop_rate": dict(zip(SYMS, d["stop_rate_pooled"])),
             "loco_S_wo": dict(zip(SYMS, d["loco_S_wo"]))}
            for d in dip_years],
        "dip_dd_5ep": {"episodes": ep_coin, "totals": tot5, "grand": round(grand5, 6),
                       "share": share5},
        "key_counts": {
            "book_years_gt40_dev4": dev_count(book_max),
            "book_years_gt40_5y": int(sum(1 for s in book_max if s > 0.40)),
            "dip_years_gt40_dev4": dev_count(dip_max),
            "dip_years_gt40_5y": int(sum(1 for s in dip_max if s > 0.40)),
            "book_max_shares": book_max, "dip_max_shares": dip_max,
        },
    }
    (HERE / "results.json").write_text(json.dumps(res, indent=1, default=str))
    print(json.dumps(res["key_counts"], indent=1), flush=True)


if __name__ == "__main__":
    main()
