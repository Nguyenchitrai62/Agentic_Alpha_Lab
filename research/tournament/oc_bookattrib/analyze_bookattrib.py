"""oc_bookattrib: where does the deployed G2 BOOK's return come from?

Vectorised attribution (read-only replica of v421 worker for w; 4h opens per
shifted clock for r). See PLAN.md (pre-registered). Run:
  .venv/Scripts/python.exe research/tournament/oc_bookattrib/analyze_bookattrib.py
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
V421 = RD / "v421/v421_runs.pkl"
V421_RES = RD / "v421/v421_result.json"
SYMS = ["BNBUSDT", "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]
ANCH = [pd.Timestamp(f"{y}-09-24", tz="UTC") for y in (2021, 2022, 2023, 2024, 2025)]
YEAR = pd.Timedelta(days=365)
BLOCK = 42
NPERM = 500
SEED = 7
STRAT = "R2B1D17BFG2"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def monthly_geometric(end_factor: float) -> float:
    return 100 * (float(end_factor) ** (1 / 12) - 1)


def validate_g2():
    runs = pickle.loads(V421.read_bytes())
    exp = json.loads(V421_RES.read_text())["rows"][STRAT]
    rm = _load("reset_for_attrib", ROOT / "research/diagnostics/r2_decompose5/reset_metric.py")
    v388 = _load("v388_for_attrib", RD / "v388/v388_bot_stop_distance.py")
    got_years = []
    for y in range(5):
        m = rm.year_reset(runs, STRAT, y)
        got_years.append((m["R"], m["DD"]))
    assert got_years == [(r, d) for r, d in exp["years"]], (got_years, exp["years"])
    got = {"R": round(float(np.prod([1 + r / 100 for r, _ in got_years]) ** (1 / 5) - 1) * 100, 3)}
    assert got["R"] == exp["R"], (got, exp["R"])
    g1 = v388.Y1 + pd.Timedelta(hours=12)
    e, mn = v388.mix(runs, STRAT, g1)
    seg = e.index > pd.Timestamp("2021-09-24", tz="UTC")
    es, ms = e[seg].to_numpy(), mn[seg].to_numpy()
    full = round(100 * float(np.max(1 - ms / np.maximum.accumulate(es))), 2)
    assert full == exp["full_path_dd"], (full, exp["full_path_dd"])
    print(f"G2 validation OK: R={exp['R']} W={exp['W']} DD={exp['DD']} full={full}", flush=True)
    return runs


def load_books_standard():
    eu = _load("eu_attrib", RD / "engine_user/engine_user.py")
    fw = _load("fw_attrib", ROOT / "scripts/forward_v205.py")
    books154, opens_std = eu.er.v154_books()
    cols = list(books154.columns)
    assert cols == SYMS, cols
    std = fw.research_books_d2(eu).reindex(books154.index).fillna(0.0)[cols]
    btc = opens_std["BTCUSDT"].reindex(books154.index)
    bear = (btc < btc.rolling(1200, min_periods=600).mean()).to_numpy()
    sb = std.copy()
    sb.loc[bear] = sb.loc[bear].where(sb.loc[bear] <= 0, sb.loc[bear] * 0.5)
    return books154, opens_std, std, sb, bear


def load_shifted_opens():
    """Per-shift 4h opens using the same first-minute-open logic as prep_idx (open column only)."""
    eu = _load("eu_attrib2", RD / "engine_user/engine_user.py")
    books154, _ = eu.er.v154_books()
    cols = list(books154.columns)
    # load 1m opens only (lighter than full minutes())
    opens_1m = {}
    for s in SYMS:
        d = ROOT / ("data/raw/btc_intraday_20260924" if s == "BTCUSDT" else "data/raw/majors_intraday_20260924")
        pat = "klines_1m_20*.parquet" if s == "BTCUSDT" else f"{s}_1m_20*.parquet"
        parts = []
        for f in sorted(d.glob(pat)):
            parts.append(pd.read_parquet(f, columns=["open_time", "open"]))
        m = pd.concat(parts)
        m["open_time"] = pd.to_datetime(m["open_time"], utc=True)
        m = m.drop_duplicates("open_time").set_index("open_time").sort_index()["open"].astype(float)
        opens_1m[s] = m
        print(f"loaded 1m open {s}: {len(m)} rows", flush=True)
    out = {}
    for shift in range(4):
        sh = pd.Timedelta(hours=shift)
        idx = books154.index + sh
        opens = pd.DataFrame(index=idx, columns=cols, dtype=float)
        hold = pd.Index(idx + pd.Timedelta(hours=4))
        for j, s in enumerate(cols):
            m = opens_1m[s]
            m = m[(m.index >= idx[0]) & (m.index < idx[-1] + pd.Timedelta(hours=8))]
            start = (m.index - sh).floor("4h") + sh
            row = hold.get_indexer(start)
            # first open of each holding bar: minute exactly at bar start
            at_start = m.index == start
            first = m[at_start]
            # first.index are minute times == bar starts; map bar start -> idx (bar start - 4h)
            # holding bar H = idx+4h; bar start S == H - 4h + ... actually S == H - 4h? check:
            # prep_idx: hold=idx+4h; row=hold.get_indexer(start); first=m[m.index==start]["open"]; opens=reindex(idx)
            # first.index are starts; reindex to idx needs start==idx+? At s=0, idx are 00/04.. and starts are same grid,
            # first.index==start values are holding-bar starts? m.index==start means minute at its own bar start.
            # The bar whose holding interval starts at S has decision idx S-4h. hold.get_indexer maps S->row.
            # Simplest: replicate prep_idx exactly via indexer.
            ok = row >= 0
            # build series start->open then map to idx via hold
            ser = pd.Series(m.to_numpy()[ok], index=pd.Index(start[ok]))
            # keep first occurrence per start (there is exactly one minute at start)
            ser = ser[~ser.index.duplicated(keep="first")]
            # hold[i] is the holding-bar end? No: hold=idx+4h = bar END? Actually decision idx, holding [idx,idx+4h)?
            # prep opens[s] = first minute open reindexed to idx: first.index are bar STARTS == idx values on standard grid.
            # So map: opens at idx t = minute open at time t.
            opens[s] = ser.reindex(idx)
        out[shift] = (idx, opens)
        print(f"shift {shift}: opens {opens.shape}, NaN frac {float(opens.isna().mean().mean()):.4f}", flush=True)
    return out


def ols_nw5(y, x):
    """OLS y=alpha+beta*x with Newey-West(5) SE (Bartlett). Returns dict."""
    y = np.asarray(y, float)
    x = np.asarray(x, float)
    n = len(y)
    X = np.column_stack([np.ones(n), x])
    XtX_inv = np.linalg.inv(X.T @ X)
    beta = XtX_inv @ (X.T @ y)
    e = y - X @ beta
    S = np.zeros((2, 2))
    for i in range(n):
        xe = X[i][:, None] * e[i]
        S += xe @ xe.T
    for L in range(1, 6):
        w = 1 - L / 6
        G = np.zeros((2, 2))
        for i in range(L, n):
            a = X[i][:, None] * e[i]
            b = X[i - L][:, None] * e[i - L]
            G += a @ b.T + b @ a.T
        S += w * G
    V = XtX_inv @ S @ XtX_inv
    se = np.sqrt(np.diag(V))
    t = beta / np.where(se > 0, se, np.nan)
    return {"alpha_d": float(beta[0]), "beta": float(beta[1]),
            "se_alpha": float(se[0]), "se_beta": float(se[1]),
            "t_alpha": float(t[0]), "t_beta": float(t[1]), "n": int(n)}


def main():
    print("validating G2 baseline ...", flush=True)
    validate_g2()
    print("loading standard books ...", flush=True)
    books154, opens_std, std_nobear, sb_std, bear_std = load_books_standard()
    print("loading shifted opens (1m open column only) ...", flush=True)
    shifted = load_shifted_opens()

    rng = np.random.default_rng(SEED)
    per_phase = {}
    for shift in range(4):
        idx, opens = shifted[shift]
        cols = list(books154.columns)
        # books_bear ffill to shifted clock (exact v421 logic)
        books_bear = sb_std.reindex(idx, method="ffill").fillna(0.0)
        books_nobear = std_nobear.reindex(idx, method="ffill").fillna(0.0)
        assert (books_bear.index == idx).all()
        o = opens[cols].to_numpy(float)
        r = o[1:] / o[:-1] - 1  # r(t) uses opens t -> t+1; aligns with w(t) at idx[:-1]
        w = books_bear.to_numpy(float)[:-1]
        w_nb = books_nobear.to_numpy(float)[:-1]
        t_idx = idx[:-1]
        valid = np.isfinite(o[:-1]).all(axis=1) & np.isfinite(o[1:]).all(axis=1)
        print(f"shift {shift}: bars {len(t_idx)}, valid {int(valid.sum())}", flush=True)
        years_out = []
        for yi, a0 in enumerate(ANCH):
            a1 = a0 + YEAR
            # wall-clock window (same market for all phases)
            m = (t_idx >= a0) & (t_idx < a1) & valid
            wy = w[m]
            ry = r[m]
            ty = t_idx[m]
            n = int(m.sum())
            b = (wy * ry).sum(axis=1)
            E = float(np.prod(1 + b))
            R = monthly_geometric(E)
            # beta/timing
            wbar = wy.mean(axis=0)
            beta_b = (wbar[None, :] * ry).sum(axis=1)
            Eb = float(np.prod(1 + beta_b))
            Rb = monthly_geometric(Eb)
            tim = b - beta_b
            Et = float(np.prod(1 + tim))
            Rt = monthly_geometric(Et)
            assert abs((1 + b).prod() - (1 + beta_b).prod() * 0 + (1 + b).prod()) >= 0
            # identity check B vs cumprod split is NOT multiplicative; check additive per-bar
            assert np.allclose(b, beta_b + tim, atol=1e-12)
            # long/short
            wl = np.where(wy > 0, wy, 0.0)
            ws = np.where(wy < 0, wy, 0.0)
            bl = (wl * ry).sum(axis=1)
            bs = (ws * ry).sum(axis=1)
            Rl = monthly_geometric(float(np.prod(1 + bl)))
            Rs = monthly_geometric(float(np.prod(1 + bs)))
            assert np.allclose(b, bl + bs, atol=1e-12)
            # no-bear counterfactual
            wy_nb = w_nb[m]
            b_nb = (wy_nb * ry).sum(axis=1)
            R_nb = monthly_geometric(float(np.prod(1 + b_nb)))
            # daily regression
            days = pd.DatetimeIndex(ty).floor("D")
            uniq = pd.unique(days)
            rd, rm = [], []
            for d in uniq:
                mm = days == d
                rd.append(float(np.prod(1 + b[mm]) - 1))
                cd = np.prod(1 + ry[mm], axis=0) - 1
                rm.append(float(np.mean(cd)) if mm.sum() else np.nan)
            rd = np.array(rd, float)
            rm = np.array(rm, float)
            okd = np.isfinite(rd) & np.isfinite(rm)
            reg = ols_nw5(rd[okd], rm[okd]) if okd.sum() > 10 else None
            if reg is not None:
                reg["alpha_ann_pct"] = round(100 * ((1 + reg["alpha_d"]) ** 365 - 1), 3)
            # placebo on TIMING level: permute w blocks within coin-year
            nrows = wy.shape[0]
            nb = (nrows + BLOCK - 1) // BLOCK
            blocks = [np.arange(i * BLOCK, min((i + 1) * BLOCK, nrows)) for i in range(nb)]
            full_blocks = [bl for bl in blocks if len(bl) == BLOCK]
            partial = [bl for bl in blocks if len(bl) != BLOCK]
            T_actual = float(tim.sum())
            T_perms = np.empty(NPERM)
            for p in range(NPERM):
                wp = np.empty_like(wy)
                for c in range(wy.shape[1]):
                    order = rng.permutation(len(full_blocks))
                    pos = 0
                    for oi in order:
                        bl = full_blocks[oi]
                        wp[pos:pos + BLOCK, c] = wy[bl, c]
                        pos += BLOCK
                    for bl in partial:
                        wp[bl, c] = wy[bl, c]
                bp_ = (wp * ry).sum(axis=1)
                wb_p = wp.mean(axis=0)
                betap = (wb_p[None, :] * ry).sum(axis=1)
                T_perms[p] = float((bp_ - betap).sum())
            pct = float((T_perms <= T_actual).mean())
            pval = float((1 + (T_perms >= T_actual).sum()) / (1 + NPERM))
            years_out.append({
                "anchor": str(a0.date()), "n_bars": n,
                "B_R": round(R, 3), "B_total_pct": round(100 * (E - 1), 2),
                "BETA_R": round(Rb, 3), "TIMING_R": round(Rt, 3),
                "timing_sum": round(T_actual, 4),
                "placebo_pct": round(100 * pct, 1), "placebo_p": round(pval, 4),
                "perm_mean": round(float(T_perms.mean()), 4),
                "perm_sd": round(float(T_perms.std()), 4),
                "long_R": round(Rl, 3), "short_R": round(Rs, 3),
                "nobear_R": round(R_nb, 3),
                "bear_gain_pp": round(R - R_nb, 3),
                "mean_w": round(float(wy.mean()), 5),
                "mean_abs_w": round(float(np.abs(wy).mean()), 5),
                "reg": reg, "n_days": int(okd.sum()),
            })
            print(f"s{shift} Y{yi} {a0.date()}: B={R:.3f} beta={Rb:.3f} tim={Rt:.3f} "
                  f"long={Rl:.3f} short={Rs:.3f} nobear={R_nb:.3f} placebo={100*pct:.1f}%", flush=True)
        per_phase[str(shift)] = years_out

    # 4-phase means of monthly R
    mean_rows = []
    for yi, a0 in enumerate(ANCH):
        def avg(key):
            return round(float(np.mean([per_phase[str(s)][yi][key] for s in range(4)])), 3)
        mean_rows.append({
            "anchor": str(a0.date()),
            "B_R": avg("B_R"), "BETA_R": avg("BETA_R"), "TIMING_R": avg("TIMING_R"),
            "long_R": avg("long_R"), "short_R": avg("short_R"),
            "nobear_R": avg("nobear_R"), "bear_gain_pp": avg("bear_gain_pp"),
            "placebo_pct": round(float(np.mean([per_phase[str(s)][yi]["placebo_pct"] for s in range(4)])), 1),
            "beta": round(float(np.mean([per_phase[str(s)][yi]["reg"]["beta"] for s in range(4) if per_phase[str(s)][yi]["reg"]])), 3),
        })
    out = {
        "meta": {
            "strat": STRAT, "src": "v421_runs.pkl (t/eq/eq_min only) + regen w via v421 worker logic",
            "w": "research_books_d2 + v421 x0.5 bear filter on longs, ffill to shifted clocks",
            "r": "next-bar open-to-open on that shift's prep opens (first-1m-open logic)",
            "B": "sum w r per bar, cumprod per [A,A+365d) wall-clock year",
            "placebo": f"{NPERM} block-{BLOCK} shuffles of w within coin-year, seed {SEED}",
            "reg": "daily book on equal-weight 5-coin daily, OLS + Newey-West(5d)",
            "g2_validation": "reset_metric per-year + v388 full-path DD reproduce v421_result to the digit",
        },
        "per_phase": per_phase,
        "mean4": mean_rows,
    }
    (HERE / "tmp" / "attrib_raw.json").write_text(json.dumps(out, indent=1, default=str))
    print("wrote tmp/attrib_raw.json", flush=True)


if __name__ == "__main__":
    main()
