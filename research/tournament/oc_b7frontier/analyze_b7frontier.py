"""oc_b7frontier scoring (CPU-only): BOT legs + carry f=0.25 overlay + bootstrap.

Reads copied runs (D13BF_base/S5 from oc_c2frontier, G2B7_base/S5 from oc_cboostbybit)
plus new engine runs (D13B7_base/S5 in tmp/), scores BOT legs with
reset_metric.year_reset + v388.mix (verbatim oc_cboostbybit, g1 = Y1+12h), checks the
reproduction gates (G2==v421, D13BF==v424, G2B7==cascadeboost/cboostbybit, D13BF_S5==c2frontier
to the digit; f=0 carry short-circuit + G2+carry==oc_c2carry to the digit as a method check),
then overlays quarterly carry f=0/0.25 on all 6 BOT legs with the verbatim oc_c2carry /
oc_carrycompound ONE-account method and the oc_c2carry stationary bootstrap
(mean block 10 d, 4000 draws, seed 0). Writes tmp/b7frontier_table.json.
REPORT.md + results.json are written from that table only.
"""
from __future__ import annotations

import importlib.util
import json
import pickle
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
RD = ROOT / "research/parallel/rounds/parallel-20260906-r2"
TMP = HERE / "tmp"
CB = ROOT / "research/tournament/oc_cascadeboost"
C2F = ROOT / "research/tournament/oc_c2frontier"
CBB = ROOT / "research/tournament/oc_cboostbybit"
C2C = ROOT / "research/tournament/oc_c2carry"
CC = ROOT / "research/tournament/oc_cashcarry"
QDIR = ROOT / "data/raw/qbasis_20261003"
SDIR = ROOT / "data/raw/spot_majors_20260925"
HOURLY = ROOT / "research/tournament/ext/hourly_ext.parquet"
V421 = RD / "v421/v421_runs.pkl"
V421_RES = RD / "v421/v421_result.json"

COINS = ["BTC", "ETH"]
F_ROWS = [0.0, 0.25]
FEE_ENTRY_PAID = 0.001 + 0.00055
GRID0 = pd.Timestamp("2021-09-24 04:00", tz="UTC")
CAP = pd.Timestamp("2026-09-24 00:00", tz="UTC")
YEAR = pd.Timedelta(days=365)
S5_LIVE0 = pd.Timestamp("2021-11-15", tz="UTC")

BOOT_MEAN_BLOCK = 10.0
BOOT_N = 4000
BOOT_LEN = 365
BOOT_SEED = 0


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def geo(rs, nd=3):
    return round(100 * (float(np.prod([1 + r / 100 for r in rs])) ** (1 / len(rs)) - 1), nd)


def last_close_before(times_ns, closes, ts_ns):
    idx = np.searchsorted(times_ns, ts_ns, side="left") - 1
    out = np.full(len(ts_ns), np.nan)
    ok = idx >= 0
    out[ok] = closes[idx[ok]]
    return out


def stationary_indices(n, length, rng, p):
    out = np.empty(length, dtype=np.int64)
    k = 0
    while k < length:
        start = int(rng.integers(0, n))
        L = int(rng.geometric(p))
        L = min(L, length - k)
        idx = (start + np.arange(L)) % n
        out[k:k + L] = idx
        k += L
    return out


def bootstrap_row(r, l, seed=BOOT_SEED, n_paths=BOOT_N,
                  length=BOOT_LEN, mean_block=BOOT_MEAN_BLOCK):
    rng = np.random.default_rng(seed)
    n = len(r)
    p = 1.0 / mean_block
    I = np.empty((n_paths, length), dtype=np.int64)
    for b in range(n_paths):
        I[b] = stationary_indices(n, length, rng, p)
    R = r[I]
    L = l[I]
    P = np.cumprod(1.0 + R, axis=1)
    Pprev = np.concatenate([np.ones((n_paths, 1)), P[:, :-1]], axis=1)
    Mk = np.minimum(P, Pprev * L)
    peak = np.maximum.accumulate(
        np.concatenate([np.ones((n_paths, 1)), P], axis=1), axis=1)[:, 1:]
    dd_m = np.max(1.0 - Mk / peak, axis=1)
    R12 = P[:, -1] - 1.0
    m = (1.0 + np.clip(R12, -0.999999, None)) ** (1.0 / 12.0) - 1.0
    return {
        "m_med_pc": round(100 * float(np.median(m)), 3),
        "p_m_ge_5pc": round(100 * float(np.mean(m >= 0.05)), 2),
        "p_dd_gt_20pc": round(100 * float(np.mean(dd_m > 0.20)), 2),
        "p_losing_pc": round(100 * float(np.mean(R12 < 0)), 2),
    }


def score_bot(v388, rm, runs, key):
    rr = {s: {key: runs[s][key]["run"]} for s in range(4)}
    yrs = [rm.year_reset(rr, key, y) for y in range(5)]
    Rs = [y["R"] for y in yrs]
    DDs = [y["DD"] for y in yrs]
    dev = Rs[:4]
    g1 = v388.Y1 + pd.Timedelta(hours=12)
    e, mn = v388.mix(rr, key, g1)
    seg = e.index > pd.Timestamp("2021-09-24", tz="UTC")
    es, ms = e[seg].to_numpy(float), mn[seg].to_numpy(float)
    idx = e.index[seg]
    pk = np.maximum.accumulate(es)
    dd = 1 - ms / pk
    fulldd = round(100 * float(np.max(dd)), 2)
    dd_c = round(100 * float(np.max(1 - es / pk)), 2)
    i_dd = int(np.argmax(dd))
    i_pk = int(np.argmax(es[:i_dd + 1])) if i_dd > 0 else 0
    ep = {"peak": str(idx[i_pk]), "trough": str(idx[i_dd]),
          "depth_pct": round(100 * float(dd[i_dd]), 2)}
    wins = []
    for y in range(5):
        nb = sum(runs[s][key]["wins"][y]["nb"] for s in range(4))
        wb = sum(runs[s][key]["wins"][y]["wb"] for s in range(4))
        nr = sum(runs[s][key]["wins"][y]["nr"] for s in range(4))
        wr = sum(runs[s][key]["wins"][y]["wr"] for s in range(4))
        wins.append(dict(nb=nb, wb=wb, nr=nr, wr=wr,
                         book_win=round(wb / nb, 4) if nb else None,
                         rung_win=round(wr / nr, 4) if nr else None,
                         all_win=round((wb + wr) / (nb + nr), 4) if (nb + nr) else None))
    sms = None
    try:
        sms = [runs[s][key]["mult"] for s in range(4)]
        n_sz = sum(m[str(y)]["n_sized"] for m in sms for y in range(5))
        sm = (sum(m[str(y)]["sized_mean"] * m[str(y)]["n_sized"]
                     for m in sms for y in range(5)) / n_sz) if n_sz else None
        sized_mean = round(sm, 6) if sm is not None else None
    except Exception:
        sized_mean = None
    return dict(years_R=Rs, years_DD=DDs,
                Rdev4=geo(dev), Wdev4=round(min(dev), 3),
                DDdev4=round(max(DDs[:4]), 2),
                losing_dev4=sum(r < 0 for r in dev),
                R5y=geo(Rs), W5y=round(min(Rs), 3),
                DD5y=round(max(DDs), 2),
                losing_5y=sum(r < 0 for r in Rs),
                full_path_dd=fulldd,
                DDmax_full=round(max(max(DDs), fulldd), 2),
                dd_marked=fulldd, dd_close=dd_c,
                worst_marked_episode=ep,
                sized_mean=sized_mean,
                wins=wins)


def main():
    v388 = _load("v388_b7f", RD / "v388/v388_bot_stop_distance.py")
    rm = _load("reset_b7f", ROOT / "research/diagnostics/r2_decompose5/reset_metric.py")
    g1 = v388.Y1 + pd.Timedelta(hours=12)
    ANCH = [pd.Timestamp(a, tz="UTC") for a in v388.ANCH]
    grid = pd.date_range(GRID0, g1, freq="1h")
    gn = grid.values.astype("datetime64[ns]").astype(np.int64)
    n = len(grid)

    # ---- gate 1: G2 reproduced from stored runs (CPU, no engine) ----
    v421_runs = pickle.loads(V421.read_bytes())
    exp_g2 = json.loads(V421_RES.read_text())["rows"]["R2B1D17BFG2"]
    rr_g2 = {s: {"G2": v421_runs[s]["R2B1D17BFG2"]} for s in range(4)}
    got_g2 = [rm.year_reset(rr_g2, "G2", y) for y in range(5)]
    for y in range(5):
        er, ed = exp_g2["years"][y]
        assert (got_g2[y]["R"], got_g2[y]["DD"]) == (er, ed), (y, got_g2[y], exp_g2["years"][y])
    print("G2 reproduces v421 R2B1D17BFG2 EXACTLY:", [(g["R"], g["DD"]) for g in got_g2], flush=True)

    # ---- load BOT legs (copied + new) ----
    f_d13_base = pickle.loads((C2F / "tmp/runs_D13BF_base.pkl").read_bytes())
    f_d13_s5 = pickle.loads((C2F / "tmp/runs_D13BF_S5.pkl").read_bytes())
    cbb_base = pickle.loads((CBB / "tmp/runs_base.pkl").read_bytes())
    cbb_s5 = pickle.loads((CBB / "tmp/runs_S5.pkl").read_bytes())
    p_new_base = TMP / "runs_D13B7_base.pkl"
    p_new_s5 = TMP / "runs_D13B7_S5.pkl"
    assert p_new_base.exists(), f"missing {p_new_base} — run compute_b7frontier_engine.py first"
    assert p_new_s5.exists(), f"missing {p_new_s5} — run compute_b7frontier_engine.py first"
    f_d13b7_base = pickle.loads(p_new_base.read_bytes())
    f_d13b7_s5 = pickle.loads(p_new_s5.read_bytes())
    for d, nm in ((f_d13_base, "D13BF_base"), (f_d13_s5, "D13BF_S5"),
                  (f_d13b7_base, "D13B7_base"), (f_d13b7_s5, "D13B7_S5")):
        assert set(d) == {0, 1, 2, 3}, (nm, sorted(d))
    for d, nm in ((cbb_base, "cbb_base"), (cbb_s5, "cbb_s5")):
        assert set(d) == {0, 1, 2, 3}, (nm, sorted(d))
        for s in range(4):
            assert set(d[s]) == {"REF", "B7"}, (nm, s, sorted(d[s]))

    bot_runs = {
        "D13BF_base": {s: {"D13BF_base": f_d13_base[s]["D13BF"]} for s in range(4)},
        "D13BF_S5": {s: {"D13BF_S5": f_d13_s5[s]["D13BF"]} for s in range(4)},
        "D13B7_base": {s: {"D13B7_base": f_d13b7_base[s]["D13B7"]} for s in range(4)},
        "D13B7_S5": {s: {"D13B7_S5": f_d13b7_s5[s]["D13B7"]} for s in range(4)},
        "G2B7_base": {s: {"G2B7_base": cbb_base[s]["B7"]} for s in range(4)},
        "G2B7_S5": {s: {"G2B7_S5": cbb_s5[s]["B7"]} for s in range(4)},
        "G2_base": {s: {"G2_base": cbb_base[s]["REF"]} for s in range(4)},
        "G2_S5": {s: {"G2_S5": cbb_s5[s]["REF"]} for s in range(4)},
    }
    bot_table = {k: score_bot(v388, rm, bot_runs[k], k) for k in bot_runs}
    print("BOT scored:", {k: (v["R5y"], v["full_path_dd"]) for k, v in bot_table.items()}, flush=True)

    # ---- gates 2-5: copied rows reproduce frozen numbers to the digit ----
    exp_d13 = json.loads((RD / "v424/v424_result.json").read_text())["rows"]["R2B1D13BF"]
    for y in range(5):
        er, ed = exp_d13["years"][y]
        assert bot_table["D13BF_base"]["years_R"][y] == er, (y, bot_table["D13BF_base"]["years_R"][y], er)
        assert bot_table["D13BF_base"]["years_DD"][y] == ed, (y, bot_table["D13BF_base"]["years_DD"][y], ed)
    assert bot_table["D13BF_base"]["R5y"] == exp_d13["R"]
    assert bot_table["D13BF_base"]["full_path_dd"] == exp_d13["full_path_dd"]
    print("D13BF_base reproduces v424 R2B1D13BF EXACTLY", flush=True)

    cb_res = json.loads((CB / "results.json").read_text())
    cb_dev_R = cb_res["dev4_engine"]["B7"]["years_R"]
    cb_dev_DD = cb_res["dev4_engine"]["B7"]["years_DD"]
    cb_last = cb_res["engine_last_once_REF_pick"]["B7"]
    for y in range(4):
        assert bot_table["G2B7_base"]["years_R"][y] == cb_dev_R[y], (y, bot_table["G2B7_base"]["years_R"][y], cb_dev_R[y])
        assert bot_table["G2B7_base"]["years_DD"][y] == cb_dev_DD[y], (y, bot_table["G2B7_base"]["years_DD"][y], cb_dev_DD[y])
    assert bot_table["G2B7_base"]["years_R"][4] == cb_last["Rlast_diag"]
    assert bot_table["G2B7_base"]["years_DD"][4] == cb_last["DDlast_diag"]
    assert bot_table["G2B7_base"]["R5y"] == cb_last["R5y"]
    assert bot_table["G2B7_base"]["full_path_dd"] == cb_last["full_path_dd"]
    print("G2B7_base reproduces oc_cascadeboost/cboostbybit B7_base EXACTLY", flush=True)

    cbb_tab = json.loads((CBB / "tmp/cboostbybit_table.json").read_text())["table"]
    for key in ("G2B7_S5", "G2_S5", "G2_base"):
        src = {"G2B7_S5": "B7_S5", "G2_S5": "REF_S5", "G2_base": "REF_base"}[key]
        assert bot_table[key]["years_R"] == cbb_tab[src]["years_R"], (key, bot_table[key]["years_R"])
        assert bot_table[key]["years_DD"] == cbb_tab[src]["years_DD"], key
        assert bot_table[key]["R5y"] == cbb_tab[src]["R5y"], key
        assert bot_table[key]["full_path_dd"] == cbb_tab[src]["full_path_dd"], key
    print("G2B7_S5/G2_S5/G2_base reproduce oc_cboostbybit table EXACTLY", flush=True)

    c2f_tab = json.loads((C2F / "tmp/frontier_table.json").read_text())["new_rows"]
    for key in ("D13BF_S5",):
        assert bot_table[key]["years_R"] == c2f_tab[key]["years_R"], (key, bot_table[key]["years_R"])
        assert bot_table[key]["years_DD"] == c2f_tab[key]["years_DD"], key
        assert bot_table[key]["R5y"] == c2f_tab[key]["R5y"], key
        assert bot_table[key]["full_path_dd"] == c2f_tab[key]["full_path_dd"], key
    print("D13BF_S5 reproduces oc_c2frontier table EXACTLY", flush=True)

    # ---- carry overlay (verbatim oc_c2carry method) on all BOT legs + G2 gates ----
    legs_for_carry = {
        "D13BF_bin": bot_runs["D13BF_base"],
        "D13B7_bin": bot_runs["D13B7_base"],
        "G2B7_bin": bot_runs["G2B7_base"],
        "G2_bin": bot_runs["G2_base"],
        "D13BF_by": bot_runs["D13BF_S5"],
        "D13B7_by": bot_runs["D13B7_S5"],
        "G2B7_by": bot_runs["G2B7_S5"],
        "G2_by": bot_runs["G2_S5"],
    }
    # per-leg base hourly equities on the grid
    base = {}
    for leg, runs in legs_for_carry.items():
        key = list(runs[0])[0]
        Es, Ms = [], []
        for s in range(4):
            e1, m1 = v388.hourly(runs[s][key]["run"], GRID0, g1)
            assert (e1.index == grid).all()
            Es.append(e1.to_numpy(dtype=float))
            Ms.append(m1.to_numpy(dtype=float))
        base[leg] = (np.stack(Es), np.stack(Ms))

    cc = json.loads((CC / "results.json").read_text())
    assert cc["meta"]["threshold_ann_basis"] == 0.04
    assert len(cc["trades"]) == 33 and cc["n_skipped"] == 13
    assert cc["n_incomplete"] == 2
    h = pd.read_parquet(HOURLY, columns=["t", "close", "sym"])
    h["t"] = pd.to_datetime(h["t"], utc=True)
    assert bool((h["t"] < CAP).all())
    spot = {}
    for coin in COINS:
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
        qo = pd.to_datetime(q["open_time"], utc=True).values.astype("datetime64[ns]").astype(np.int64)
        o = np.argsort(qo)
        qmap[key] = (qo[o], q["close"].to_numpy(dtype=float)[o])
    s4 = pd.read_parquet(SDIR / "BTCUSDT_spot_4h.parquet", columns=["open_time", "close_time"])
    s4o = pd.to_datetime(s4["open_time"], utc=True)
    s4c = pd.to_datetime(s4["close_time"], utc=True)
    trades = []
    for t in cc["trades"]:
        te = pd.Timestamp(t["entry_open"], tz="UTC")
        tc = te + pd.Timedelta(hours=4)
        assert (s4o == te).any(), t
        D = pd.Timestamp(t["delivery"] + " 08:00", tz="UTC")
        si = int(np.searchsorted(s4c.values.astype("datetime64[ns]").astype(np.int64), D.value, side="right"))
        assert si < len(s4), t
        ts = s4c.iloc[si]
        assert ts > tc, t
        trades.append({"coin": t["coin"], "delivery": t["delivery"],
                       "F_entry": float(t["F_entry"]), "S_entry": float(t["S_entry"]),
                       "ret_alloc": float(t["ret_alloc"]), "tc_ns": tc.value, "ts_ns": ts.value})
    for tr in trades:
        st, sc = spot[tr["coin"]]
        ft, fc = qmap[(tr["coin"], tr["delivery"])]
        S = last_close_before(st, sc, gn)
        F = last_close_before(ft, fc, gn)
        with np.errstate(divide="ignore", invalid="ignore"):
            mtm = ((S / tr["S_entry"] - 1.0) + ((tr["F_entry"] - F) / tr["F_entry"]) - FEE_ENTRY_PAID)
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

    def mtm_at_anchor(tr, a_ns):
        if a_ns <= tr["tc_ns"]:
            return 0.0
        if a_ns >= tr["ts_ns"]:
            return float(tr["ret_alloc"])
        st, sc = spot[tr["coin"]]
        ft, fc = qmap[(tr["coin"], tr["delivery"])]
        qa = np.array([a_ns])
        S = last_close_before(st, sc, qa)[0]
        F = last_close_before(ft, fc, qa)[0]
        if np.isfinite(S) and np.isfinite(F) and tr["F_entry"] and tr["S_entry"]:
            return float((S / tr["S_entry"] - 1.0) + ((tr["F_entry"] - F) / tr["F_entry"]) - FEE_ENTRY_PAID)
        return 0.0

    a_ns_all = np.array([a.value for a in ANCH])
    anchor_mtm = np.array([[mtm_at_anchor(tr, a) for tr in trades] for a in a_ns_all])

    def year_pass(Es, Ms, f):
        years = []
        for y, a0 in enumerate(ANCH):
            a1 = a0 + YEAR
            seg = (grid > a0) & (grid <= a1)
            idx = np.where(np.asarray(seg))[0]
            le = gn <= a0.value
            b = np.array([float(Es[s][le][-1]) if le.any() else 1.0 for s in range(4)])
            E4 = [Es[s][idx] / b[s] for s in range(4)]
            M4 = [Ms[s][idx] / b[s] for s in range(4)]
            es = np.mean(E4, axis=0)
            ms = np.mean(M4, axis=0)
            if f == 0.0:
                A_arr, M_arr = es, ms
            else:
                es_prev = np.concatenate([[1.0], es[:-1]])
                g = es / es_prev
                hh = ms / es_prev
                mtm_a = anchor_mtm[y]
                rel = [k for k, tr in enumerate(trades) if tr["tc_ns"] < a1.value and tr["ts_ns"] > a0.value]
                span = {k for k in rel if trades[k]["tc_ns"] <= a0.value}
                N = {k: f * 1.0 for k in span}
                mtm_seg = {k: trades[k]["mtm"][idx] - mtm_a[k] for k in rel}
                A_prev, U_prev = 1.0, 0.0
                A_arr = np.empty(len(idx))
                M_arr = np.empty(len(idx))
                tc_map = {}
                for k in rel:
                    if k in span:
                        continue
                    pos = int(np.searchsorted(gn[idx], trades[k]["tc_ns"], side="right"))
                    if 0 <= pos < len(idx):
                        tc_map.setdefault(pos, []).append(k)
                U_open = dict(N)
                for i in range(len(idx)):
                    for k in tc_map.get(i, []):
                        U_open[k] = f * A_prev
                    U_i = 0.0
                    for k, nk in U_open.items():
                        U_i += nk * mtm_seg[k][i]
                    dU = U_i - U_prev
                    A_i = A_prev * g[i] + dU
                    M_i = A_prev * hh[i] + dU
                    A_arr[i] = A_i
                    M_arr[i] = M_i
                    A_prev, U_prev = A_i, U_i
            pk = np.maximum.accumulate(A_arr)
            R = round(100 * float(A_arr[-1] ** (1 / 12) - 1), 3)
            DD = round(100 * float(np.max(1 - M_arr / pk)), 2)
            years.append({"anchor": str(a0.date()), "R": R, "DD": DD, "end": round(float(A_arr[-1]), 6)})
        R5 = round(float(np.prod([1 + yy["R"] / 100 for yy in years]) ** (1 / 5) - 1) * 100, 3)
        return years, R5

    def full_pass(Es, Ms, f):
        Etot = Es.mean(axis=0)
        Mtot = Ms.mean(axis=0)
        if f == 0.0:
            A_c, M_c = Etot.copy(), Mtot.copy()
        else:
            A_c = np.empty(n)
            M_c = np.empty(n)
            g0_mtm = np.array([mtm_at_anchor(tr, gn[0]) for tr in trades])
            rel_c = [k for k, tr in enumerate(trades) if tr["ts_ns"] > gn[0]]
            span_c = {k for k in rel_c if trades[k]["tc_ns"] <= gn[0]}
            N_c = {k: f * float(Etot[0]) for k in span_c}
            mtm_r = {k: trades[k]["mtm"] - g0_mtm[k] for k in rel_c}
            tc_pos = {}
            for k in rel_c:
                if k in span_c:
                    continue
                pos = int(np.searchsorted(gn, trades[k]["tc_ns"], side="right"))
                if 0 <= pos < n:
                    tc_pos.setdefault(pos, []).append(k)
            A_c[0], M_c[0] = float(Etot[0]), float(Mtot[0])
            A_prev = float(Etot[0])
            U_prev = 0.0
            U_open_c = dict(N_c)
            for i in range(1, n):
                for k in tc_pos.get(i, []):
                    U_open_c[k] = f * A_prev
                U_i = 0.0
                for k, nk in U_open_c.items():
                    U_i += nk * mtm_r[k][i]
                dU = U_i - U_prev
                g = Etot[i] / Etot[i - 1]
                hh = Mtot[i] / Etot[i - 1]
                A_c[i] = A_prev * g + dU
                M_c[i] = A_prev * hh + dU
                A_prev, U_prev = A_c[i], U_i
        segf = np.asarray(grid > pd.Timestamp("2021-09-24", tz="UTC"))
        esf, msf = A_c[segf], M_c[segf]
        dd_m = round(100 * float(np.max(1 - msf / np.maximum.accumulate(esf))), 2)
        dd_c = round(100 * float(np.max(1 - esf / np.maximum.accumulate(esf))), 2)
        return A_c, M_c, {"marked": dd_m, "close": dd_c, "full": max(dd_m, dd_c)}

    carry_rows = {}
    for leg in ("D13BF_bin", "D13B7_bin", "G2B7_bin", "G2_bin",
                "D13BF_by", "D13B7_by", "G2B7_by", "G2_by"):
        Es, Ms = base[leg]
        for f in F_ROWS:
            years, R5 = year_pass(Es, Ms, f)
            A_c, M_c, full = full_pass(Es, Ms, f)
            e_s = pd.Series(A_c, index=grid)
            m_s = pd.Series(M_c, index=grid)
            D0 = S5_LIVE0 if leg.endswith("_by") else pd.Timestamp("2021-09-24", tz="UTC")
            D = pd.date_range(D0, pd.Timestamp("2026-09-23", tz="UTC"), freq="1D")
            E = e_s.reindex(D, method="ffill").fillna(1.0).to_numpy(float)
            M = pd.Series(index=D, dtype=float)
            M.iloc[0] = float(E[0])
            mh = pd.concat([m_s, e_s], axis=1).min(axis=1)
            for d in range(1, len(D)):
                seg = mh[(mh.index > D[d - 1]) & (mh.index <= D[d])]
                M.iloc[d] = float(seg.min()) if len(seg) else float(E[d])
            M = M.fillna(pd.Series(E, index=D)).to_numpy(float)
            r = E[1:] / E[:-1] - 1.0
            l = M[1:] / E[:-1]
            boot = bootstrap_row(r, l)
            tag = {"D13BF_bin": "D13BF", "D13B7_bin": "D13B7", "G2B7_bin": "G2B7", "G2_bin": "G2",
                   "D13BF_by": "D13BF", "D13B7_by": "D13B7", "G2B7_by": "G2B7", "G2_by": "G2"}[leg]
            venue = "binance" if leg.endswith("_bin") else "bybit_S5"
            key = f"{tag}{'_carry' if f else ''}_{venue}"
            carry_rows[key] = {"bot": tag, "venue": venue, "f": f, "years": years, "R5y": R5,
                               "W5y": min(yy["R"] for yy in years),
                               "DDmax": max(yy["DD"] for yy in years),
                               "losing": sum(yy["R"] < 0 for yy in years),
                               "full_path_dd": full, "recent": years[-1], "bootstrap": boot}
            print(f"{key}: 5y={R5} W={carry_rows[key]['W5y']} DD={carry_rows[key]['DDmax']} "
                  f"full={full['full']} boot={boot}", flush=True)

    # ---- gate 6: G2+carry reproduces oc_c2carry to the digit (method check) ----
    c2c_res = json.loads((C2C / "results.json").read_text())["rows"]
    for key in ("G2_binance", "G2_carry_binance", "G2_bybit_S5", "G2_carry_bybit_S5"):
        er = [yy["R"] for yy in c2c_res[key]["years"]]
        ed = [yy["DD"] for yy in c2c_res[key]["years"]]
        got = carry_rows[key]
        assert [yy["R"] for yy in got["years"]] == er, (key, got)
        assert [yy["DD"] for yy in got["years"]] == ed, (key, got)
        assert got["R5y"] == c2c_res[key]["R5y"], (key, got["R5y"])
        assert got["full_path_dd"] == c2c_res[key]["full_path_dd"], (key, got)
    print("gate G2/G2+carry x Binance/Bybit reproduces oc_c2carry EXACTLY", flush=True)
    # f=0 carry short-circuit == BOT table
    for bkey, ckey in (("D13BF_base", "D13BF_binance"), ("D13B7_base", "D13B7_binance"),
                       ("G2B7_base", "G2B7_binance"), ("D13BF_S5", "D13BF_bybit_S5"),
                       ("D13B7_S5", "D13B7_bybit_S5"), ("G2B7_S5", "G2B7_bybit_S5")):
        assert carry_rows[ckey]["years"] is not None
        assert [yy["R"] for yy in carry_rows[ckey]["years"]] == bot_table[bkey]["years_R"], (bkey, ckey)
        assert [yy["DD"] for yy in carry_rows[ckey]["years"]] == bot_table[bkey]["years_DD"], (bkey, ckey)

    out = {"bot": bot_table, "carry": carry_rows,
           "gates": {"G2_v421": True, "D13BF_v424": True, "G2B7_cascadeboost": True,
                     "G2B7_S5_cboostbybit": True, "D13BF_S5_c2frontier": True,
                     "G2carry_c2carry": True}}
    (TMP / "b7frontier_table.json").write_text(json.dumps(out, indent=1))
    print("saved tmp/b7frontier_table.json", flush=True)


if __name__ == "__main__":
    main()
