"""oc_sleevealloc: cross-sleeve drawdown-budget allocator (G2-book / G2-dip / carry).

PLAN.md pre-registered (frozen before any outcome). CPU-only overlay on the hourly
grid (~44k rows, 4h+1h only, no 1m). Repro + allocator + controls + S5-approx.
"""
from __future__ import annotations

import importlib.util
import json
import pickle
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
RD = ROOT / "research/parallel/rounds/parallel-20260906-r2"
CC = ROOT / "research/tournament/oc_cashcarry"
QDIR = ROOT / "data/raw/qbasis_20261003"
SDIR = ROOT / "data/raw/spot_majors_20260925"
HOURLY = ROOT / "research/tournament/ext/hourly_ext.parquet"
V421 = RD / "v421/v421_runs.pkl"
V421_RES = RD / "v421/v421_result.json"
BOOKONLY = ROOT / "research/tournament/oc_bookattrib/tmp/bookonly_runs.pkl"
DIPONLY = HERE / "tmp/diponly_runs.pkl"
C2_S5 = ROOT / "research/tournament/oc_c2bybit/tmp/runs_S5.pkl"
C2_TAB = ROOT / "research/tournament/oc_c2bybit/tmp/c2bybit_table.json"
CC_RES = ROOT / "research/tournament/oc_carrycompound/results.json"

COINS = ["BTC", "ETH"]
FEE_ENTRY_PAID = 0.001 + 0.00055
GRID0 = pd.Timestamp("2021-09-24 04:00", tz="UTC")
CAP = pd.Timestamp("2026-09-24 00:00", tz="UTC")
YEAR = pd.Timedelta(days=365)
EMBARGO = pd.Timedelta(days=7)
TRAIL = pd.Timedelta(days=1460)
MIN_HIST = pd.Timedelta(days=180)
CARRY_CAP = 0.5
DD_FLOOR = 0.005
VOL_FLOOR = 1e-6
STRAT = "R2B1D17BFG2"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def last_close_before(times_ns: np.ndarray, closes: np.ndarray,
                       ts_ns: np.ndarray) -> np.ndarray:
    idx = np.searchsorted(times_ns, ts_ns, side="left") - 1
    out = np.full(len(ts_ns), np.nan)
    ok = idx >= 0
    out[ok] = closes[idx[ok]]
    return out


def dd_of(close: np.ndarray, marked: np.ndarray) -> float:
    pk = np.maximum.accumulate(close)
    return float(np.max(1 - marked / pk))


def monthly(end_factor: float) -> float:
    return 100 * (float(end_factor) ** (1 / 12) - 1)


print("[alloc] loading modules + runs ...", flush=True)
v388 = _load("v388_alloc", RD / "v388/v388_bot_stop_distance.py")
rm = _load("rm_alloc", ROOT / "research/diagnostics/r2_decompose5/reset_metric.py")
ANCH = [pd.Timestamp(a, tz="UTC") for a in v388.ANCH]
g1 = v388.Y1 + pd.Timedelta(hours=12)
grid = pd.date_range(GRID0, g1, freq="1h")
gn = grid.values.astype("datetime64[ns]").astype(np.int64)
n = len(grid)

runs = pickle.loads(V421.read_bytes())
book = pickle.loads(BOOKONLY.read_bytes())
dip = pickle.loads(DIPONLY.read_bytes())
assert set(runs) == {0, 1, 2, 3} and set(book) == {0, 1, 2, 3} and set(dip) == {0, 1, 2, 3}

# ---- 1. reproduction gate: REF == v421_result G2 to the digit ----
exp = json.loads(V421_RES.read_text())["rows"][STRAT]
got_years = [rm.year_reset(runs, STRAT, y) for y in range(5)]
assert [(m["R"], m["DD"]) for m in got_years] == [(r, d) for r, d in exp["years"]], got_years
assert round(float(np.prod([1 + m["R"] / 100 for m in got_years]) ** (1 / 5) - 1) * 100, 3) == exp["R"]
e_tot, m_tot = v388.mix(runs, STRAT, g1)
seg = e_tot.index > pd.Timestamp("2021-09-24", tz="UTC")
es, ms = e_tot[seg].to_numpy(), m_tot[seg].to_numpy()
full = round(100 * float(np.max(1 - ms / np.maximum.accumulate(es))), 2)
assert full == exp["full_path_dd"], (full, exp["full_path_dd"])
print(f"[alloc] G2 gate OK: 5.41 / 16.91 / 16.82 to the digit ({time.strftime('%H:%M:%S')})", flush=True)

# ---- 2. sleeve hourly equities (book / dip) ----
Eb4, Mb4, Ed4, Md4 = [], [], [], []
for s in range(4):
    e1, m1 = v388.hourly(book[s]["BOOKONLY"], GRID0, g1)
    e2, m2 = v388.hourly(dip[s]["DIPONLY"], GRID0, g1)
    assert (e1.index == grid).all()
    Eb4.append(e1.to_numpy(float)); Mb4.append(m1.to_numpy(float))
    Ed4.append(e2.to_numpy(float)); Md4.append(m2.to_numpy(float))
Eb4, Mb4, Ed4, Md4 = map(np.stack, (Eb4, Mb4, Ed4, Md4))
E_book, M_book = Eb4.mean(axis=0), Mb4.mean(axis=0)
E_dip, M_dip = Ed4.mean(axis=0), Md4.mean(axis=0)

# ---- 3. carry per-trade hourly mtm (verbatim oc_carrycompound construction) ----
cc = json.loads((CC / "results.json").read_text())
assert cc["meta"]["threshold_ann_basis"] == 0.04
assert len(cc["trades"]) == 33 and cc["n_skipped"] == 13 and cc["n_incomplete"] == 2
h = pd.read_parquet(HOURLY, columns=["t", "close", "sym"])
h["t"] = pd.to_datetime(h["t"], utc=True)
assert bool((h["t"] < CAP).all())
spot: dict[str, tuple[np.ndarray, np.ndarray]] = {}
for coin in COINS:
    d = h[h["sym"] == f"{coin}USDT"].sort_values("t")
    spot[coin] = (d["t"].values.astype("datetime64[ns]").astype(np.int64),
                  d["close"].to_numpy(dtype=float))
qmap: dict[tuple[str, str], tuple[np.ndarray, np.ndarray]] = {}
for t in cc["trades"]:
    key = (t["coin"], t["delivery"])
    if key in qmap:
        continue
    y, m_, dd = t["delivery"].split("-")
    code = f"{y[2:]}{m_}{dd}"
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
    v[open_m & ~settled_m] = np.where(np.isfinite(mtm[open_m & ~settled_m]), mtm[open_m & ~settled_m], 0.0)
    v[settled_m] = tr["ret_alloc"]
    tr["mtm"] = v


def mtm_at_anchor(tr, a_ns: int) -> float:
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

# ---- 4. REF_CARRY validation: one-account f=0.25 == oc_carrycompound to digit ----
Es_list, Ms_list = [], []
for s in range(4):
    e1, m1 = v388.hourly(runs[s][STRAT], GRID0, g1)
    Es_list.append(e1.to_numpy(float)); Ms_list.append(m1.to_numpy(float))
Es, Ms = np.stack(Es_list), np.stack(Ms_list)
cc_exp = json.loads(CC_RES.read_text())["rows"]["G2_f0.25"]
ref_carry_years = []
for y, a0 in enumerate(ANCH):
    a1 = a0 + YEAR
    segm = (grid > a0) & (grid <= a1)
    idx = np.where(np.asarray(segm))[0]
    le = gn <= a0.value
    b = np.array([float(Es[s][le][-1]) if le.any() else 1.0 for s in range(4)])
    E4 = [Es[s][idx] / b[s] for s in range(4)]
    M4 = [Ms[s][idx] / b[s] for s in range(4)]
    es_y = np.mean(E4, axis=0)
    ms_y = np.mean(M4, axis=0)
    es_prev = np.concatenate([[1.0], es_y[:-1]])
    g = es_y / es_prev
    hh = ms_y / es_prev
    mtm_a = anchor_mtm[y]
    rel = [k for k, tr in enumerate(trades) if tr["tc_ns"] < a1.value and tr["ts_ns"] > a0.value]
    span = {k for k in rel if trades[k]["tc_ns"] <= a0.value}
    N = {k: 0.25 * 1.0 for k in span}
    mtm_seg = {k: trades[k]["mtm"][idx] - mtm_a[k] for k in rel}
    tc_map: dict[int, list[int]] = {}
    for k in rel:
        if k in span:
            continue
        pos = int(np.searchsorted(gn[idx], trades[k]["tc_ns"], side="right"))
        if 0 <= pos < len(idx):
            tc_map.setdefault(pos, []).append(k)
    A_prev, U_prev = 1.0, 0.0
    U_open: dict[int, float] = dict(N)
    A_arr = np.empty(len(idx)); M_arr = np.empty(len(idx))
    for i in range(len(idx)):
        for k in tc_map.get(i, []):
            U_open[k] = 0.25 * A_prev
        U_i = sum(nk * mtm_seg[k][i] for k, nk in U_open.items())
        dU = U_i - U_prev
        A_arr[i] = A_prev * g[i] + dU
        M_arr[i] = A_prev * hh[i] + dU
        A_prev, U_prev = A_arr[i], U_i
    pk = np.maximum.accumulate(A_arr)
    ref_carry_years.append((round(monthly(A_arr[-1]), 3), round(100 * float(np.max(1 - M_arr / pk)), 2)))
assert [r for r, _ in ref_carry_years] == [yy["R"] for yy in cc_exp["years"]], (ref_carry_years, cc_exp["years"])
assert [d for _, d in ref_carry_years] == [yy["DD"] for yy in cc_exp["years"]]
print("[alloc] REF_CARRY mtm gate OK: reproduces oc_carrycompound f=0.25 to the digit", flush=True)

# ---- 5. carry UNIT sleeve (f_unit=1.0 per pair) hourly levels ----
a0_all = np.array([a.value for a in ANCH])
# per-year carry-unit segments (rebased at each anchor) + continuous unit path
carry_unit_close = np.zeros(n)   # dU-unit cumulative from grid start, rebased per year below
# Build per-trade unit mtm relative to grid start for continuous path:
g0_mtm = np.array([mtm_at_anchor(tr, gn[0]) for tr in trades])
rel_c = [k for k, tr in enumerate(trades) if tr["ts_ns"] > gn[0]]
unit_mtm_r = {k: trades[k]["mtm"] - g0_mtm[k] for k in rel_c}
# entry order for unit notionals (n=1.0 each, spanning rebased at grid start)
tc_pos: dict[int, list[int]] = {}
span_c = {k for k in rel_c if trades[k]["tc_ns"] <= gn[0]}
for k in rel_c:
    if k in span_c:
        continue
    pos = int(np.searchsorted(gn, trades[k]["tc_ns"], side="right"))
    if 0 <= pos < n:
        tc_pos.setdefault(pos, []).append(k)
U_path = np.zeros(n)
U_open_c: dict[int, float] = {k: 1.0 for k in span_c}
U_prev = 0.0
for i in range(1, n):
    for k in tc_pos.get(i, []):
        U_open_c[k] = 1.0
    U_i = sum(nk * unit_mtm_r[k][i] for k, nk in U_open_c.items())
    U_path[i] = U_i
E_carry_unit = 1.0 + U_path  # standalone carry-unit close (marked = same, lower bound)
M_carry_unit = E_carry_unit.copy()
peak_concurrent = max(
    sum(1 for k in rel_c if trades[k]["tc_ns"] < gn[i] and trades[k]["ts_ns"] > gn[i]) for i in range(0, n, 24)
)
print(f"[alloc] carry unit built; peak concurrent pairs (daily sample) = {peak_concurrent}", flush=True)

# ---- 6. trailing weights V1 (1/maxDD) / V2 (1/vol), cap 0.5, yearly ----
def sleeve_levels():
    return {"book": (E_book, M_book), "dip": (E_dip, M_dip), "carry": (E_carry_unit, M_carry_unit)}


LV = sleeve_levels()


def metric_dd(Ec: np.ndarray, Mm: np.ndarray, a: pd.Timestamp) -> float:
    w0, w1 = a - TRAIL, a - EMBARGO
    m = (grid >= w0) & (grid < w1)
    if m.sum() < 2:
        return np.nan
    c = Ec[m] / Ec[m][0]
    mk = Mm[m] / Ec[m][0]
    return max(dd_of(c, np.minimum(c, mk)), DD_FLOOR)


def metric_vol(Ec: np.ndarray, a: pd.Timestamp) -> float:
    w0, w1 = a - TRAIL, a - EMBARGO
    m = (grid >= w0) & (grid < w1)
    c = Ec[m]
    if m.sum() < 50:
        return np.nan
    r = c[1:] / c[:-1] - 1
    r = r[np.isfinite(r)]
    if len(r) < 50:
        return np.nan
    return max(float(np.std(r)), VOL_FLOOR)


def weights_for(a: pd.Timestamp, kind: str):
    hist_len = ((a - EMBARGO) - GRID0)
    if hist_len < MIN_HIST:
        return (1 / 3, 1 / 3, 1 / 3, True)  # fallback flag
    if kind == "V1":
        d_b = metric_dd(*LV["book"], a)
        d_d = metric_dd(*LV["dip"], a)
        d_c = metric_dd(*LV["carry"], a)
        inv = np.array([1 / d_b, 1 / d_d, 1 / d_c])
    else:
        v_b = metric_vol(LV["book"][0], a)
        v_d = metric_vol(LV["dip"][0], a)
        v_c = metric_vol(LV["carry"][0], a)
        inv = np.array([1 / v_b, 1 / v_d, 1 / v_c])
    raw = inv / inv.sum()
    wb, wd, wc = raw
    if wc > CARRY_CAP:
        wc = CARRY_CAP
        s = wb + wd
        wb, wd = 0.5 * wb / s, 0.5 * wd / s
    tot = wb + wd + wc
    return (wb / tot, wd / tot, wc / tot, False)


W_V1 = [weights_for(a, "V1") for a in ANCH]
W_V2 = [weights_for(a, "V2") for a in ANCH]
W_EQ = [(1 / 3, 1 / 3, 1 / 3, False) for _ in ANCH]
print("[alloc] weights:", flush=True)
for y, a in enumerate(ANCH):
    print(f"  {a.date()} V1 b/d/c={tuple(round(x,4) for x in W_V1[y][:3])} fb={W_V1[y][3]} | "
          f"V2 b/d/c={tuple(round(x,4) for x in W_V2[y][:3])} fb={W_V2[y][3]}", flush=True)

# ---- 7. capital-split scoring ----
def score_variant(Wlist, years):
    out = []
    for y in years:
        a0 = ANCH[y]
        a1 = a0 + YEAR
        segm = (grid > a0) & (grid <= a1)
        idx = np.where(np.asarray(segm))[0]
        wb, wd, wc, _ = Wlist[y]
        segs = []
        for key, w in (("book", wb), ("dip", wd), ("carry", wc)):
            Ec, Mm = LV[key]
            le = gn <= a0.value
            b = float(Ec[le][-1]) if le.any() else 1.0
            segs.append((w * Ec[idx] / b, w * Mm[idx] / b))
        A_arr = sum(s[0] for s in segs)
        M_arr = sum(s[1] for s in segs)
        pk = np.maximum.accumulate(A_arr)
        out.append({"anchor": str(a0.date()), "R": round(monthly(A_arr[-1]), 3),
                    "DD": round(100 * float(np.max(1 - M_arr / pk)), 2),
                    "end": round(float(A_arr[-1]), 6),
                    "w": [round(wb, 4), round(wd, 4), round(wc, 4)]})
    R5 = round(float(np.prod([1 + yy["R"] / 100 for yy in out]) ** (1 / len(out)) - 1) * 100, 3)
    return {"years": out, "R": R5, "W": min(yy["R"] for yy in out),
            "DD": max(yy["DD"] for yy in out), "losing": sum(yy["R"] < 0 for yy in out)}


def full_path_dd(Wlist):
    # continuous chained capital-split path from grid start
    A_vals, M_vals = [], []
    A_prev = 1.0
    for y, a0 in enumerate(ANCH):
        a1 = a0 + YEAR
        segm = (grid > a0) & (grid <= a1)
        idx = np.where(np.asarray(segm))[0]
        wb, wd, wc, _ = Wlist[y]
        A_seg, M_seg = 0, 0
        for key, w in (("book", wb), ("dip", wd), ("carry", wc)):
            Ec, Mm = LV[key]
            le = gn <= a0.value
            b = float(Ec[le][-1]) if le.any() else 1.0
            A_seg = A_seg + w * Ec[idx] / b
            M_seg = M_seg + w * Mm[idx] / b
        A_vals.append(A_prev * A_seg)
        Mv = A_prev * M_seg
        M_vals.append(Mv)
        A_prev = float(A_vals[-1][-1])
    A_c = np.concatenate(A_vals)
    M_c = np.concatenate(M_vals)
    segf = np.asarray(grid > pd.Timestamp("2021-09-24", tz="UTC"))[:len(A_c)]
    # align: segments already start after 2021-09-24; use full chained arrays
    dd_m = round(100 * float(np.max(1 - M_c / np.maximum.accumulate(A_c))), 2)
    dd_c = round(100 * float(np.max(1 - A_c / np.maximum.accumulate(A_c))), 2)
    return {"marked": dd_m, "close": dd_c, "full": max(dd_m, dd_c)}


DEV = [0, 1, 2, 3]
res_V1 = score_variant(W_V1, DEV)
res_V2 = score_variant(W_V2, DEV)
res_EQ = score_variant(W_EQ, DEV)
res_V1["full_path_dd"] = full_path_dd(W_V1)
res_V2["full_path_dd"] = full_path_dd(W_V2)
res_EQ["full_path_dd"] = full_path_dd(W_EQ)
for k, r in (("V1", res_V1), ("V2", res_V2), ("CTRL-EQ", res_EQ)):
    print(f"[alloc] dev4 {k}: R={r['R']} W={r['W']} DD={r['DD']} losing={r['losing']} full={r['full_path_dd']}", flush=True)

# ---- 8. robust pick on dev4 ONLY ----
cands = {"V1": res_V1, "V2": res_V2}
qual = {k: v for k, v in cands.items() if v["DD"] <= 20 and v["losing"] == 0}
if qual:
    over5 = {k: v for k, v in qual.items() if v["R"] >= 5}
    pool = over5 if over5 else qual
    pick = max(pool, key=lambda k: (pool[k]["W"], pool[k]["R"]))
else:
    pick = max(cands, key=lambda k: (cands[k]["W"], cands[k]["R"]))
print(f"[alloc] dev4 robust pick = {pick}", flush=True)

# ---- 9. most-recent year scored ONCE for pick + REF (+refs, labelled) ----
Y4 = [4]
Wpick = W_V1 if pick == "V1" else W_V2
res_pick_y4 = score_variant(Wpick, Y4)
res_ref_y4 = score_variant(W_EQ, Y4)  # placeholder replaced below (REF total, not EQ)
# REF total Y4 from gate (v421, labelled re-score of frozen numbers, no recompute selection)
ref_y4 = {"anchor": "2025-09-24", "R": got_years[4]["R"], "DD": got_years[4]["DD"]}
refcarry_y4 = {"anchor": "2025-09-24", "R": cc_exp["years"][4]["R"], "DD": cc_exp["years"][4]["DD"]}
# full 5y rows for pick + refs (5y reported, never selected)
res_pick_5y = score_variant(Wpick, [0, 1, 2, 3, 4])
res_pick_5y["full_path_dd"] = full_path_dd(Wpick)
res_eq_5y = score_variant(W_EQ, [0, 1, 2, 3, 4])
res_eq_5y["full_path_dd"] = full_path_dd(W_EQ)

# sleeve standalone year Rs (gross=net: legs already net; report for cost transparency)
def sleeve_year(key, y):
    a0 = ANCH[y]
    a1 = a0 + YEAR
    segm = (grid > a0) & (grid <= a1)
    idx = np.where(np.asarray(segm))[0]
    Ec, Mm = LV[key]
    le = gn <= a0.value
    b = float(Ec[le][-1]) if le.any() else 1.0
    A_arr = Ec[idx] / b
    M_arr = Mm[idx] / b
    pk = np.maximum.accumulate(A_arr)
    return {"R": round(monthly(A_arr[-1]), 3), "DD": round(100 * float(np.max(1 - M_arr / pk)), 2)}


sleeves = {k: [sleeve_year(k, y) for y in range(5)] for k in ("book", "dip", "carry")}

# ---- 10. S5-approx (Bybit BOT leg + same carry marks, frozen pick weights) ----
s5 = pickle.loads(C2_S5.read_bytes())
assert set(s5) == {0, 1, 2, 3}
Eb5 = []
for sh in range(4):
    e1, m1 = v388.hourly(s5[sh]["REF"]["run"], GRID0, g1)
    Eb5.append((e1.to_numpy(float), m1.to_numpy(float)))
E5 = sum(e for e, _ in Eb5) / 4
M5 = sum(m for _, m in Eb5) / 4
s5_rows_pick, s5_rows_ref = [], []
for y in DEV:
    a0 = ANCH[y]
    a1 = a0 + YEAR
    segm = (grid > a0) & (grid <= a1)
    idx = np.where(np.asarray(segm))[0]
    le = gn <= a0.value
    b5 = float(E5[le][-1]) if le.any() else 1.0
    E5s, M5s = E5[idx] / b5, M5[idx] / b5
    # REF_S5 baseline on this grid (should match c2bybit table approx; short 2021 labelled)
    pk5 = np.maximum.accumulate(E5s)
    s5_rows_ref.append({"anchor": str(a0.date()), "R": round(monthly(E5s[-1]), 3),
                        "DD": round(100 * float(np.max(1 - M5s / pk5)), 2)})
    wb, wd, wc, _ = Wpick[y]
    # capital-split approx: (1-wc) on Bybit BOT total + wc on carry unit
    Ec, Mm = LV["carry"]
    b = float(Ec[le][-1]) if le.any() else 1.0
    Ecs, Mcs = Ec[idx] / b, Mm[idx] / b
    A_arr = (1 - wc) * E5s + wc * Ecs
    M_arr = (1 - wc) * M5s + wc * Mcs
    pk = np.maximum.accumulate(A_arr)
    s5_rows_pick.append({"anchor": str(a0.date()), "R": round(monthly(A_arr[-1]), 3),
                         "DD": round(100 * float(np.max(1 - M_arr / pk)), 2),
                         "w_carry": round(wc, 4)})
c2tab = json.loads(C2_TAB.read_text())

out = {
    "meta": {
        "ref": "v421 R2B1D17BFG2 (5.41/16.91/16.82); book=oc_bookattrib/bookonly_runs.pkl BOOKONLY; "
               "dip=oc_sleevealloc/tmp/diponly_runs.pkl DIPONLY (mirror runner); carry=oc_cashcarry 33 frozen + "
               "oc_carrycompound mtm (f_unit=1.0 per pair, fees spot 0.001/side + fut 0.00055/0.0002)",
        "accounting": "capital-split, exposure 1.0: A(t)=wb*Eb+wd*Ed+wc*Ec rebalanced yearly at anchors, "
                      "no transfer cost; carry marks causal hourly closes (lower bound); spanning rebased at resets",
        "weights": "trailing min(1460d, avail) ending anchor-7d; V1 1/maxDD (floor 0.5%), V2 1/vol (floor 1e-6); "
                   "carry capped 0.5 (rescale book/dip); <180d avail -> equal 1/3",
        "metric": "reset_metric arithmetic per year (fresh 1.0) + chained continuous full-path DD (max marked/close)",
        "s5": "diagnostic approx: BOT leg=Bybit G2 total (runs_S5.pkl REF), carry leg=same hourly marks, "
              "pick yearly w_carry frozen (no refit); book/dip split NOT re-estimated on Bybit (stated limit); "
              "2021 S5 is a SHORT window (Bybit from 2021-11-15)",
    },
    "weights": {"V1": [list(W_V1[y][:3]) + [W_V1[y][3]] for y in range(5)],
                "V2": [list(W_V2[y][:3]) + [W_V2[y][3]] for y in range(5)]},
    "dev4": {"V1": res_V1, "V2": res_V2, "CTRL-EQ": res_EQ},
    "pick": pick,
    "y4_once": {"pick": res_pick_y4, "REF_total": ref_y4, "REF_CARRY_f025": refcarry_y4,
                "CTRL-EQ": res_ref_y4},
    "five_y": {"pick": res_pick_5y, "CTRL-EQ": res_eq_5y,
               "REF_total": {"R": exp["R"], "W": exp["W"], "DD": exp["DD"],
                             "losing": 0, "full_path_dd": exp["full_path_dd"]},
               "REF_CARRY_f025": dict(cc_exp, full_path_dd=json.loads(CC_RES.read_text())["rows"]["G2_f0.25"]["full_path_dd"])},
    "sleeves_standalone": sleeves,
    "s5_approx": {"pick": s5_rows_pick, "REF_S5_grid": s5_rows_ref,
                  "c2bybit_table_ref": c2tab.get("table", c2tab)},
    "carry_peak_concurrent_daily_sample": peak_concurrent,
}
(HERE / "tmp" / "sleeve_table.json").write_text(json.dumps(out, indent=1, default=str))
(HERE / "results.json").write_text(json.dumps(out, indent=1, default=str))
print(f"[alloc] wrote tmp/sleeve_table.json + results.json; pick={pick} ({time.strftime('%H:%M:%S')})", flush=True)
