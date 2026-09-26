"""v154 error analysis (DESCRIPTIVE diagnostics only).

Rebuilds v154 exactly from the leader modules (no copied modelling logic):

  research/parallel/rounds/parallel-20260906-r2/v144/v144_deploy_v3.py
    (books_v142 + the simulate engine pieces)
  v151/v151_info_ensemble.py  (books_with_options -> member B, options flow)
  v154/v154_ensemble_coinbase.py (books_coinbase -> member D, Coinbase premium)

Member A = v144 books. Books = (A + B + D) / 3, then the v144 sequential
engine for target 0.25 with the 20% drawdown governor. The engine loop is
copied from v144_deploy_v3.simulate (as the assignment instructs) and
extended to also return per-bar arrays: portfolio scale s, governor g, the
final weights w per asset, per-asset gross return contribution w_i * r_i,
cost per asset, funding per asset, and carry terms.

Book components per member (v92 LO / v94 LS / v103 LS) are rebuilt from the
books_v142 internals: the three phased weight frames and their vol-target
scales are captured during the official build calls, then combined with the
official 0.25 / 0.25 / 0.50 weighting. Identity
member_book == b_lo + b94 + b103 is asserted.

DESCRIPTIVE ONLY on the already-seen OOS span 2021-09-24..2026-09-23. This
script fits nothing and tunes nothing. Any idea the report suggests needs a
pre-registered test (and prospective confirmation) before any use.

Usage (from the repository root):
  .venv/Scripts/python.exe research/diagnostics/v154_error_analysis/analyze.py

Runtime: three member-book rebuilds (tens of minutes). Writes summary.json
and REPORT.md next to this file. Exits non-zero if the reconstruction does
not match v154's primary row (3.515 %/month, 19.15 % full-path DD) within
0.01.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

import torch  # noqa: F401  (import before pandas: Windows DLL load-order rule)

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

ROUND = ROOT / "research" / "parallel" / "rounds" / "parallel-20260906-r2"

DISCLAIMER = (
    "DESCRIPTIVE ONLY: this analysis replays the already-seen OOS span "
    "2021-09-24..2026-09-23 (including the former hidden year). It fits nothing "
    "and tunes nothing. Any idea it suggests needs a pre-registered test "
    "(and prospective confirmation) before any use."
)

REF_MONTHLY = 3.515
REF_DD = 19.15
TOL = 0.01


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, ROUND / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def build_member(kind):
    """Build one member book set via the official leader-module code.

    kind A: v144.books_v142() with no augmentation.
    kind B: the v151 augmentation (Deribit options-flow features from the
      imported v150 module) applied to a fresh v144 copy, then books_v142().
      The augmentation statements match v151_info_ensemble.books_with_options.
    kind D: the v154 augmentation (Coinbase-premium features from the
      imported v111 module) applied to a fresh v144 copy, then books_v142().
      The augmentation statements match v154_ensemble_coinbase.books_coinbase.

    Returns (p103, member_books, components dict, v144-module copy used).
    Components are captured (not retrained twice): the three phased frames
    and their vol-target scales are recorded with wrappers, then combined
    with the official 0.25/0.25/0.50 weighting from books_v142.
    """
    tag = {"A": "v144A", "B": "v144B", "D": "v144D"}[kind]
    v144x = _load(tag, "v144/v144_deploy_v3.py")
    if kind == "B":
        v150 = _load("v150feat", "v150/v150_options_flow.py")
        feats, OPT = v150.opt_features(), v150.OPT
        ext, v103m = v144x.v115.v114.v113, v144x.v103
        b92, b103 = ext.v92.build, v103m.build
        orig_vp = v144x.v129.vol_predict
        v144x.v129.vol_predict = (
            lambda panel, fs, anchors, emb: orig_vp(panel, [c for c in fs if c not in OPT], anchors, emb)
        )
        v144x.v115.v114.v113.cb_bars = v144x.v115.v114.cb_bars_ext
        ext.v92.load_asset = ext.load_asset_ext
        ext.v92.build = lambda: b92().merge(feats, on="t", how="left")
        v103m.build = lambda: b103().merge(feats, on="t", how="left")
    elif kind == "D":
        v111 = _load("v111feat", "v111/v111_coinbase_premium.py")
        v144cb = v144x
        cbf = v111.add_cb(v144cb.v103.build()[["t", "sym"]]).drop(columns="sym").drop_duplicates("t")
        ext, v103m = v144cb.v115.v114.v113, v144cb.v103
        b92, b103 = ext.v92.build, v103m.build
        orig_vp = v144cb.v129.vol_predict
        v144cb.v129.vol_predict = (
            lambda panel, fs, anchors, emb: orig_vp(panel, [c for c in fs if c not in v111.CB], anchors, emb)
        )
        v144cb.v115.v114.v113.cb_bars = v144cb.v115.v114.cb_bars_ext
        ext.v92.load_asset = ext.load_asset_ext
        ext.v92.build = lambda: b92().merge(cbf, on="t", how="left")
        v103m.build = lambda: b103().merge(cbf, on="t", how="left")

    # Capture wrappers for the books_v142 internals (official 0.25/0.25/0.50
    # weighting is reused below to form the three book components).
    v125m = v144x.v125
    phased_calls, scale_calls = [], []
    orig_phased = v125m.phased

    def phased_cap(W, phases):
        out = orig_phased(W, phases)
        phased_calls.append(out)
        return out

    v125m.phased = phased_cap
    ext = v144x.v115.v114.v113
    orig_s92, orig_s94 = ext.v92.vol_target_scale, ext.v94.vol_target_scale

    def s92_cap(panel, W, *a, **k):
        out = orig_s92(panel, W, *a, **k)
        scale_calls.append(("s92", out))
        return out

    def s94_cap(panel, W, *a, **k):
        out = orig_s94(panel, W, *a, **k)
        scale_calls.append(("s94", out))
        return out

    ext.v92.vol_target_scale = s92_cap
    ext.v94.vol_target_scale = s94_cap

    p103, books = v144x.books_v142()

    assert len(phased_calls) == 3, f"expected 3 phased calls, got {len(phased_calls)}"
    assert [k for k, _ in scale_calls] == ["s92", "s94", "s94"], scale_calls
    W_lo, W94, W103 = phased_calls
    s92, s94a, s94b = [s for _, s in scale_calls]
    idx = W_lo.index.union(W94.index).union(W103.index)
    idx = idx[idx >= p103.t.min()]
    b_lo = 0.25 * W_lo.reindex(idx).fillna(0.0).mul(s92.reindex(idx).fillna(1.0), axis=0)
    b94 = 0.25 * W94.reindex(idx).fillna(0.0).mul(s94a.reindex(idx).fillna(1.0), axis=0)
    b103 = 0.5 * W103.reindex(idx).fillna(0.0).mul(s94b.reindex(idx).fillna(1.0), axis=0)
    comp = {"b_lo": b_lo, "b94": b94, "b103": b103}
    resid = (b_lo + b94 + b103 - books.reindex(idx).fillna(0.0)).abs().to_numpy().max()
    assert resid < 1e-12, f"book-component identity failed for member {kind}: {resid}"
    return p103, books, comp, v144x


def run_engine_t25(p103, books, v144x):
    """v144 sequential engine for target 0.25 with the 20% governor.

    Loop copied from v144_deploy_v3.simulate (single primary row),
    extended with per-bar arrays. All engine pieces (v99 constants,
    v135 1m bar stats, v110 window/governor/summarize) come from the
    imported leader modules.
    """
    v99, v135, v110 = v144x.v99, v144x.v135, v144x.v110
    PD, D = v144x.PD, v144x.D
    target, gov = 0.25, True
    idx = books.index
    carry = (
        pd.read_parquet("artifacts/research/carry/carry_oos_fee0.0004.parquet")["carry"]
        .reindex(idx)
        .fillna(0.0)
        .to_numpy()
    )
    o = p103.pivot_table(index="t", columns="sym", values="open").reindex(idx)
    realized = v99.W_BOOKS * (books.shift(2) * (o / o.shift(1) - 1)).sum(axis=1) + v99.W_CARRY * v99.CARRY_LEV * pd.Series(
        carry, index=idx
    ).shift(1)
    vol = (realized.rolling(60 * PD, min_periods=20 * PD).std() * np.sqrt(PD * 365)).to_numpy()
    r_next = (o.shift(-2) / o.shift(-1) - 1).fillna(0.0).to_numpy()
    B, cols = books.to_numpy(), list(books.columns)
    st = {s: v135.bar_stats(s).reindex(idx + pd.Timedelta(hours=4)).set_axis(idx) for s in cols}
    fee_b, rel_b, fee_s, rel_s = (np.zeros(B.shape) for _ in range(4))
    for j, s in enumerate(cols):
        p0 = st[s]["p0"].to_numpy()
        lo_, hi_, p15 = st[s]["lo"].to_numpy(), st[s]["hi"].to_numpy(), st[s]["p15"].to_numpy()
        have = ~np.isnan(p0)
        p15 = np.where(np.isnan(p15), p0, p15)
        mv = np.where(have, p15 / np.where(have, p0, 1.0) - 1, 0.0)
        fb, fs = have & (lo_ < p0 * (1 - D)), have & (hi_ > p0 * (1 + D))
        fee_b[:, j], rel_b[:, j] = np.where(fb, 0.0002, 0.0005), np.where(fb, -D, mv + 0.0002)
        fee_s[:, j], rel_s[:, j] = np.where(fs, 0.0002, 0.0005), np.where(fs, D, mv - 0.0002)
    live = np.asarray((idx >= v110.START) & (idx < v110.END))
    s = np.where(np.isnan(vol), 1.0, np.minimum(target / np.where(np.isnan(vol), 1.0, vol), v99.CAP))
    n, k = len(idx), B.shape[1]
    net, turn, g = np.zeros(n), np.zeros(n), np.ones(n)
    W = np.zeros((n, k))
    grossA = np.zeros((n, k))
    costA = np.zeros((n, k))
    fundA = np.zeros((n, k))
    carry_gross = np.zeros(n)
    carry_cost = np.zeros(n)
    # Sequential loop (identical economics to v144_deploy_v3.simulate).
    eq = np.ones(n)
    prev_w, prev_c = np.zeros(k), 0.0
    for i in range(n):
        if gov and i >= 2:
            j = i - 2
            peak = eq[max(0, j - 90 * PD + 1) : j + 1].max()
            g[i] = float(np.clip((0.20 - (1 - eq[j] / peak)) / 0.10, 0.0, 1.0))
        w = v99.W_BOOKS * s[i] * B[i] * g[i] if live[i] else np.zeros(k)
        c = v99.W_CARRY * v99.CARRY_LEV * s[i] * g[i] if live[i] else 0.0
        dw = w - prev_w
        buy = dw > 0
        fee = np.where(buy, fee_b[i], fee_s[i])
        rel = np.where(buy, rel_b[i], rel_s[i])
        cost = np.abs(dw) * fee + dw * rel
        turn[i] = np.abs(dw).sum()
        fund = np.clip(w, 0, None) * 0.00005
        cg = c * carry[i]
        cc = abs(c - prev_c) * 2 * 0.0004 / 1.2
        net[i] = (w * r_next[i]).sum() - cost.sum() - fund.sum() + cg - cc
        eq[i] = (eq[i - 1] if i else 1.0) * (1 + net[i])
        W[i], grossA[i], costA[i], fundA[i] = w, w * r_next[i], cost, fund
        carry_gross[i], carry_cost[i] = cg, cc
        prev_w, prev_c = w, c
    summ = v110.summarize(pd.Series(net, index=idx), pd.Series(turn, index=idx), pd.Series(g, index=idx))
    return {
        "idx": idx, "cols": cols, "s": s, "g": g, "W": W, "grossA": grossA, "costA": costA,
        "fundA": fundA, "carry_gross": carry_gross, "carry_cost": carry_cost,
        "net": net, "turn": turn, "eq": eq, "r_next": r_next,
        "fee_b": fee_b, "rel_b": rel_b, "fee_s": fee_s, "rel_s": rel_s,
        "live": live, "summ": summ, "o": o,
    }


def main():
    print("proving provenance imports ...", flush=True)
    v151 = _load("v151prov", "v151/v151_info_ensemble.py")
    v154 = _load("v154prov", "v154/v154_ensemble_coinbase.py")
    assert hasattr(v151, "books_with_options") and hasattr(v154, "books_coinbase")

    members, comps, mods = {}, {}, {}
    p103A = None
    for kind in ("A", "B", "D"):
        print(f"building member {kind} ...", flush=True)
        p103, books, comp, mod = build_member(kind)
        members[kind] = books
        comps[kind] = comp
        mods[kind] = mod
        if kind == "A":
            p103A = p103
    v144x = mods["A"]
    v99, v110 = v144x.v99, v144x.v110
    PD = v144x.PD
    anchors = [pd.Timestamp(a, tz="UTC") for a in v144x.v115.v114.v113.v92.ANCHORS]
    anchors_np = np.array(anchors)

    idx = members["A"].index.union(members["B"].index).union(members["D"].index)
    A = members["A"].reindex(idx).fillna(0.0)
    Bm = members["B"].reindex(idx).fillna(0.0)
    Dm = members["D"].reindex(idx).fillna(0.0)
    books = (A + Bm + Dm) / 3

    print("running t25 governed engine ...", flush=True)
    eng = run_engine_t25(p103A, books, v144x)
    eidx = eng["idx"]
    assert eidx.equals(idx), "engine index must equal the (A+B+D)/3 union index"
    summ = eng["summ"]
    dm = abs(summ["monthly_pct"] - REF_MONTHLY)
    dd = abs(summ["full_path_dd"] - REF_DD)
    print(f"reconstruction: monthly={summ['monthly_pct']} (ref {REF_MONTHLY}, d={dm:.4f}) "
          f"fullDD={summ['full_path_dd']} (ref {REF_DD}, d={dd:.4f})", flush=True)
    if dm > TOL or dd > TOL:
        raise SystemExit(f"reconstruction check FAILED: d_monthly={dm:.4f} d_dd={dd:.4f} (tol {TOL})")

    lv = eng["live"]
    lidx = eidx[lv]
    n = len(eidx)
    W, G, C, F = eng["W"], eng["grossA"], eng["costA"], eng["fundA"]
    CG, CC, NET = eng["carry_gross"], eng["carry_cost"], eng["net"]
    s, g = eng["s"], eng["g"]
    r_next = eng["r_next"]
    # Accounting identity on every live bar.
    chk = G[lv].sum(axis=1) - C[lv].sum(axis=1) - F[lv].sum(axis=1) + CG[lv] - CC[lv] - NET[lv]
    assert np.abs(chk).max() < 1e-12, np.abs(chk).max()

    G_live = G[lv]
    C_live = C[lv]
    F_live = F[lv]
    CG_live = CG[lv]
    CC_live = CC[lv]
    NET_live = NET[lv]
    CY_net = float(CG_live.sum() - CC_live.sum())
    tot = {
        "gross": float(G_live.sum()), "cost": float(C_live.sum()), "funding": float(F_live.sum()),
        "carry_gross": float(CG_live.sum()), "carry_cost": float(CC_live.sum()),
        "carry_net": CY_net, "net": float(NET_live.sum()),
    }
    assert abs(tot["gross"] - tot["cost"] - tot["funding"] + tot["carry_net"] - tot["net"]) < 1e-9

    cols = eng["cols"]
    # 1. by asset (carry is portfolio-level; asset nets sum to net - carry_net).
    by_asset = []
    for j, sym in enumerate(cols):
        gg, cc_, ff = float(G_live[:, j].sum()), float(C_live[:, j].sum()), float(F_live[:, j].sum())
        by_asset.append({"asset": sym, "gross": gg, "cost": cc_, "funding": ff, "net_ex_carry": gg - cc_ - ff})

    # 2. by member: w_member = 0.8*s*g*member_book/3 (standalone costs + netting residuals).
    scale = (v99.W_BOOKS * s[lv] * g[lv] / 3)[:, None]
    by_member, member_frames = [], {}
    for m, M in (("A", A), ("B", Bm), ("D", Dm)):
        Wm = scale * M.reindex(eidx).fillna(0.0).to_numpy()[lv]
        member_frames[m] = Wm
        Gm = float((Wm * r_next[lv]).sum())
        dWm = Wm - np.vstack([np.zeros((1, Wm.shape[1])), Wm[:-1]])
        buy = dWm > 0
        fee = np.where(buy, eng["fee_b"][lv], eng["fee_s"][lv])
        rel = np.where(buy, eng["rel_b"][lv], eng["rel_s"][lv])
        Cm = float((np.abs(dWm) * fee + dWm * rel).sum())
        Fm = float(np.clip(Wm, 0, None).sum() * 0.00005)
        cym = CY_net / 3
        by_member.append({"member": m, "gross": Gm, "cost_standalone": Cm, "funding_standalone": Fm,
                          "carry_share": cym, "net_standalone": Gm - Cm - Fm + cym})
    assert abs(sum(m["gross"] for m in by_member) - tot["gross"]) < 1e-9
    res_cost = tot["cost"] - sum(m["cost_standalone"] for m in by_member)
    res_fund = tot["funding"] - sum(m["funding_standalone"] for m in by_member)
    assert abs(sum(m["net_standalone"] for m in by_member) - res_cost - res_fund - tot["net"]) < 1e-9

    # 3. by book inside members (gross only; execution is shared at member level).
    by_book = []
    for m in ("A", "B", "D"):
        for bname in ("b_lo", "b94", "b103"):
            Cb = comps[m][bname].reindex(eidx).fillna(0.0).to_numpy()[lv]
            Wb = scale * Cb
            Gb = float((Wb * r_next[lv]).sum())
            by_book.append({"member": m, "book": bname, "gross": Gb})
    for m in ("A", "B", "D"):
        part = sum(r["gross"] for r in by_book if r["member"] == m)
        ref = next(x["gross"] for x in by_member if x["member"] == m)
        assert abs(part - ref) < 1e-9, (m, part, ref)

    # 4. long vs short legs (buys->long, sells->short; funding+carry attach to long).
    WL = np.clip(W[lv], 0, None)
    WS = np.minimum(W[lv], 0.0)
    dW = W[lv] - np.vstack([np.zeros((1, W.shape[1])), W[lv][:-1]])
    buy = dW > 0
    fee = np.where(buy, eng["fee_b"][lv], eng["fee_s"][lv])
    rel = np.where(buy, eng["rel_b"][lv], eng["rel_s"][lv])
    Cbuy = np.abs(dW) * fee + dW * rel
    long_cost = float(Cbuy[buy].sum())
    short_cost = float(Cbuy[~buy].sum())
    long_short = {
        "long": {"gross": float((WL * r_next[lv]).sum()), "cost": long_cost,
                 "funding": float(F_live.sum()), "carry_net": CY_net},
        "short": {"gross": float((WS * r_next[lv]).sum()), "cost": short_cost,
                  "funding": 0.0, "carry_net": 0.0},
    }
    for leg in ("long", "short"):
        long_short[leg]["net"] = (long_short[leg]["gross"] - long_short[leg]["cost"]
                                  - long_short[leg]["funding"] + long_short[leg]["carry_net"])
    assert abs(long_short["long"]["gross"] + long_short["short"]["gross"] - tot["gross"]) < 1e-9
    assert abs(long_short["long"]["cost"] + long_short["short"]["cost"] - tot["cost"]) < 1e-9
    assert abs(long_short["long"]["net"] + long_short["short"]["net"] - tot["net"]) < 1e-9

    # 5/6. BTC ribbon state + realised-vol tercile at t (from the member-A v103 panel).
    btc = p103A[p103A["sym"] == "BTCUSDT"][["t", "btc_rib", "vol42"]].drop_duplicates("t").set_index("t").sort_index()
    rib = btc["btc_rib"].reindex(eidx).ffill().to_numpy()[lv]
    bvol = btc["vol42"].reindex(eidx).ffill().to_numpy()[lv]
    rib_lab = np.where(rib > 0, "bull(+1)", np.where(rib < 0, "bear(-1)", "flat(0)"))
    cuts = list(pd.qcut(bvol, 3, labels=False, duplicates="drop"))
    terc = np.array(cuts)
    tlab = np.where(terc == 0, "low", np.where(terc == 1, "mid", "high"))
    qvals = [float(np.quantile(bvol, q)) for q in (0.0, 1 / 3, 2 / 3, 1.0)]

    def group_sum(labels):
        rows = []
        for lab in sorted(set(labels.tolist())):
            mk = labels == lab
            gg = float(G_live[mk].sum())
            cc_ = float(C_live[mk].sum())
            ff = float(F_live[mk].sum())
            cyg = float(CG_live[mk].sum())
            cyc = float(CC_live[mk].sum())
            rows.append({"group": lab, "bars": int(mk.sum()), "gross": gg, "cost": cc_,
                         "funding": ff, "carry_net": cyg - cyc,
                         "net": gg - cc_ - ff + cyg - cyc})
        return rows

    by_ribbon = group_sum(rib_lab)
    by_vol = group_sum(tlab)
    for tbl in (by_ribbon, by_vol):
        assert abs(sum(r["net"] for r in tbl) - tot["net"]) < 1e-9

    # 7. by anchor year.
    aid = np.searchsorted(anchors_np, lidx.to_numpy(), side="right") - 1
    aid = np.clip(aid, 0, len(anchors) - 1)
    by_year = []
    for k, a in enumerate(anchors):
        mk = aid == k
        gg = float(G_live[mk].sum())
        cc_ = float(C_live[mk].sum())
        ff = float(F_live[mk].sum())
        cyg = float(CG_live[mk].sum())
        cyc = float(CC_live[mk].sum())
        by_year.append({"anchor": pd.Timestamp(a).strftime("%Y-%m-%d"), "bars": int(mk.sum()),
                        "gross": gg, "cost": cc_, "funding": ff, "carry_net": cyg - cyc,
                        "net": gg - cc_ - ff + cyg - cyc})
    assert abs(sum(r["net"] for r in by_year) - tot["net"]) < 1e-9

    # 8. five largest non-overlapping drawdown episodes on the live equity path.
    eq_live = np.cumprod(1 + NET_live)
    episodes, taken = [], []
    order = np.argsort(eq_live / np.maximum.accumulate(eq_live) - 1.0)
    for t in order:
        if len(episodes) == 5:
            break
        p = int(np.argmax(eq_live[: t + 1]))
        if eq_live[t] >= eq_live[p]:
            continue
        if any(not (t < p0 or p > t0) for (p0, t0) in taken):
            continue
        taken.append((p, int(t)))
        depth = float(1 - eq_live[int(t)] / eq_live[p])
        win = slice(p + 1, int(t) + 1)  # bars in (peak, trough]
        ep = {"peak": str(lidx[p].date()), "trough": str(lidx[int(t)].date()), "depth_pct": depth * 100,
              "window_net": float(NET_live[win].sum()), "window_gross": float(G_live[win].sum()),
              "window_cost": float(C_live[win].sum()), "window_funding": float(F_live[win].sum()),
              "window_carry_net": float(CG_live[win].sum() - CC_live[win].sum())}
        ep["by_asset_gross"] = {sym: float(G_live[win][:, j].sum()) for j, sym in enumerate(cols)}
        ep["by_member_gross"] = {
            m: float((member_frames[m][win] * r_next[lv][win]).sum()) for m in ("A", "B", "D")}
        ep["by_book_gross"] = {
            f"{m}/{bname}": float(((scale * comps[m][bname].reindex(eidx).fillna(0.0).to_numpy()[lv])[win]
                                   * r_next[lv][win]).sum())
            for m in ("A", "B", "D") for bname in ("b_lo", "b94", "b103")}
        ep["long_gross"] = float((np.clip(W[lv][win], 0, None) * r_next[lv][win]).sum())
        ep["short_gross"] = float((np.minimum(W[lv][win], 0.0) * r_next[lv][win]).sum())
        assert abs(sum(ep["by_asset_gross"].values()) - ep["window_gross"]) < 1e-9
        assert abs(sum(ep["by_member_gross"].values()) - ep["window_gross"]) < 1e-9
        assert abs(sum(ep["by_book_gross"].values()) - ep["window_gross"]) < 1e-9
        assert abs(ep["long_gross"] + ep["short_gross"] - ep["window_gross"]) < 1e-9
        episodes.append(ep)
    episodes.sort(key=lambda e: -e["depth_pct"])
    assert len(episodes) == 5, len(episodes)

    # 9. daily hit rate + payoff ratio per anchor year.
    days = lidx.floor("D")
    day_net = pd.Series(NET_live).groupby(days).sum()
    day_year = pd.Series(aid).groupby(days).first()
    daily_years = []
    for k, a in enumerate(anchors):
        d = day_net[day_year == k].to_numpy()
        up, dn = d[d > 0], d[d < 0]
        daily_years.append({"anchor": pd.Timestamp(a).strftime("%Y-%m-%d"), "days": int(len(d)),
                            "hit_rate": float(len(up) / len(d)) if len(d) else float("nan"),
                            "payoff_ratio": float(up.mean() / -dn.mean()) if len(up) and len(dn) else float("nan"),
                            "mean_daily_bps": float(1e4 * d.mean()) if len(d) else float("nan")})
    up, dn = day_net[day_net > 0], day_net[day_net < 0]
    daily_overall = {"days": int(len(day_net)), "hit_rate": float(len(up) / len(day_net)),
                     "payoff_ratio": float(up.mean() / -dn.mean()) if len(up) and len(dn) else float("nan")}

    summary = {
        "version": "v154_error_analysis",
        "disclaimer": DISCLAIMER,
        "provenance": {
            "live_span": ["2021-09-24", "2026-09-23"],
            "bars_4h": "closed Binance USD-M majors 4h bars (v103 panel opens)",
            "engine": "v144 sequential realistic engine: 10bps limit execution on 1m data, "
                      "v110 20% drawdown governor (90-day peak, 2-bar lag)",
            "portfolio": "books=(A+B+D)/3; final w=0.8*s*g*books; carry=0.2*3*s*g",
            "target": 0.25, "governor": True, "cap": float(v99.CAP),
            "fee": "0.0002 maker / 0.0005 taker + 0.0002 slippage (scenario-dependent fills)",
            "funding": "long 0.0001/8h -> 0.00005 per 4h bar on clipped long weights; short zero",
            "capital": "compounded from equity, indexed to 100; decomposition sums are additive sums of per-bar net",
            "reference_v154_primary": {"monthly_pct": REF_MONTHLY, "full_path_dd": REF_DD},
            "anchors": [pd.Timestamp(a).strftime("%Y-%m-%d") for a in anchors],
        },
        "reconstruction": {
            "monthly_pct": summ["monthly_pct"], "full_path_dd": summ["full_path_dd"],
            "ref_monthly_pct": REF_MONTHLY, "ref_full_path_dd": REF_DD,
            "d_monthly": dm, "d_dd": dd, "tol": TOL, "passed": bool(dm <= TOL and dd <= TOL),
            "yearly": summ["yearly"],
        },
        "totals": tot,
        "compounded_net_pct": float((np.prod(1 + NET_live) - 1) * 100),
        "by_asset": by_asset,
        "by_member": by_member,
        "member_cost_netting_residual": res_cost,
        "member_funding_netting_residual": res_fund,
        "by_book": by_book,
        "long_short": long_short,
        "by_ribbon": by_ribbon,
        "by_vol_tercile": {"cuts": qvals, "rows": by_vol},
        "by_year": by_year,
        "episodes": episodes,
        "daily": {"per_year": daily_years, "overall": daily_overall},
    }
    (HERE / "summary.json").write_text(json.dumps(summary, indent=1, default=str))
    print("wrote summary.json", flush=True)
    write_report(summary)
    print("wrote REPORT.md", flush=True)


def _t(rows, cols, fmt):
    out = ["| " + " | ".join(cols) + " |", "|" + "|".join(["---"] * len(cols)) + "|"]
    for r in rows:
        out.append("| " + " | ".join(fmt(c, r.get(c)) for c in cols) + " |")
    return "\n".join(out)


def write_report(s):
    f2 = lambda c, v: f"{v:.2f}" if isinstance(v, float) else str(v)
    f4 = lambda c, v: f"{v:.4f}" if isinstance(v, float) else str(v)
    L = ["# v154 error analysis (descriptive diagnostics)", "",
         "> " + DISCLAIMER, "",
         "## Reconstruction check",
         f"Rebuilt v154 (A+B+D)/3 through the v144 t25 governed engine: "
         f"**monthly {s['reconstruction']['monthly_pct']}%** (ref {REF_MONTHLY}, "
         f"d={s['reconstruction']['d_monthly']:.4f}), **full-path DD "
         f"{s['reconstruction']['full_path_dd']}%** (ref {REF_DD}, "
         f"d={s['reconstruction']['d_dd']:.4f}). Tolerance 0.01: "
         f"{'PASSED' if s['reconstruction']['passed'] else 'FAILED'}.",
         f"Live span 2021-09-24..2026-09-23. Additive net sum "
         f"{s['totals']['net']:.4f} vs compounded {(s['compounded_net_pct'] / 100):.4f} "
         f"(capital fraction; the gap is compounding).", "",
         "## Totals (capital fractions, additive sums over live 4h bars)",
         _t([{**s["totals"]}], list(s["totals"].keys()), f4), "",
         "## 1. By asset (asset nets exclude portfolio carry; add carry_net for the total)",
         _t(s["by_asset"], ["asset", "gross", "cost", "funding", "net_ex_carry"], f4), "",
         "## 2. By member (standalone costs; netting residuals reconcile to the total)",
         _t(s["by_member"], ["member", "gross", "cost_standalone", "funding_standalone",
                             "carry_share", "net_standalone"], f4),
         f"cost netting residual {s['member_cost_netting_residual']:.4f}; "
         f"funding netting residual {s['member_funding_netting_residual']:.4f}.", "",
         "## 3. By book inside members (gross only; execution is shared at member level)",
         _t(s["by_book"], ["member", "book", "gross"], f4), "",
         "## 4. Long vs short legs (buys attach cost to long; funding+carry attach to long)",
         _t([{"leg": k, **v} for k, v in s["long_short"].items()],
            ["leg", "gross", "cost", "funding", "carry_net", "net"], f4), "",
         "## 5. By BTC daily ribbon state at t",
         _t(s["by_ribbon"], ["group", "bars", "gross", "cost", "funding", "carry_net", "net"], f4), "",
         "## 6. By BTC realised-vol tercile at t "
         f"(cut points {', '.join(f'{c:.4f}' for c in s['by_vol_tercile']['cuts'])})",
         _t(s["by_vol_tercile"]["rows"],
            ["group", "bars", "gross", "cost", "funding", "carry_net", "net"], f4), "",
         "## 7. By anchor year",
         _t(s["by_year"], ["anchor", "bars", "gross", "cost", "funding", "carry_net", "net"], f4), "",
         "## 8. Five largest non-overlapping drawdown episodes (peak -> trough)",
         _t([{k: e[k] for k in ("peak", "trough", "depth_pct", "window_net", "window_gross",
                                "window_cost", "window_funding", "window_carry_net")} for e in s["episodes"]],
            ["peak", "trough", "depth_pct", "window_net", "window_gross", "window_cost",
             "window_funding", "window_carry_net"], f2)]
    for i, e in enumerate(s["episodes"], 1):
        L += ["",
              f"### Episode {i}: {e['peak']} -> {e['trough']} (depth {e['depth_pct']:.2f}%)",
              "gross by asset: " + ", ".join(f"{k} {v:.4f}" for k, v in e["by_asset_gross"].items()),
              "gross by member: " + ", ".join(f"{k} {v:.4f}" for k, v in e["by_member_gross"].items()),
              "gross by book: " + ", ".join(f"{k} {v:.4f}" for k, v in e["by_book_gross"].items()),
              f"gross long {e['long_gross']:.4f} / short {e['short_gross']:.4f}."]
    L += ["", "## 9. Daily hit rate and payoff ratio per anchor year",
          _t(s["daily"]["per_year"],
             ["anchor", "days", "hit_rate", "payoff_ratio", "mean_daily_bps"], f4),
          f"overall: {s['daily']['overall']}", "", "## Observations (plain, descriptive; not validated findings)"]
    L += observations(s)
    L += ["",
          "Any idea above needs a pre-registered test (and prospective confirmation) before any use."]
    (HERE / "REPORT.md").write_text("\n".join(L) + "\n")


def observations(s):
    t, obs = s["totals"], []
    mb = sorted(s["by_member"], key=lambda r: -r["gross"])
    obs.append("1. Member gross ranking: "
               + ", ".join("%s %.3f" % (m["member"], m["gross"]) for m in mb)
               + " (total gross %.3f); costs+funding take %.3f off the gross path."
               % (t["gross"], t["cost"] + t["funding"] - t["carry_net"]))
    ba = sorted(s["by_asset"], key=lambda r: -r["gross"])
    obs.append("2. Asset gross ranking: "
               + ", ".join("%s %.3f" % (r["asset"], r["gross"]) for r in ba) + ".")
    ls = s["long_short"]
    obs.append("3. Long-leg gross %.3f vs short-leg gross %.3f; long net %.3f vs short net %.3f "
               "(funding and carry attach to the long leg)."
               % (ls["long"]["gross"], ls["short"]["gross"], ls["long"]["net"], ls["short"]["net"]))
    by = sorted(s["by_year"], key=lambda r: -r["net"])
    obs.append("4. Anchor-year net ranking: "
               + ", ".join("%s %.3f" % (r["anchor"][:4], r["net"]) for r in by) + ".")
    rb = sorted(s["by_ribbon"], key=lambda r: -r["net"])
    obs.append("5. Ribbon-regime net ranking: "
               + ", ".join("%s %.3f" % (r["group"], r["net"]) for r in rb)
               + " (bars: " + ", ".join("%s=%d" % (r["group"], r["bars"]) for r in rb) + ").")
    vt = sorted(s["by_vol_tercile"]["rows"], key=lambda r: -r["net"])
    obs.append("6. Vol-tercile net ranking: "
               + ", ".join("%s %.3f" % (r["group"], r["net"]) for r in vt) + ".")
    e = s["episodes"][0]
    dom_a = min(e["by_asset_gross"], key=e["by_asset_gross"].get)
    dom_m = min(e["by_member_gross"], key=e["by_member_gross"].get)
    obs.append("7. Deepest drawdown episode %s -> %s (%.2f%%); largest gross-loss asset %s (%.3f), "
               "member %s (%.3f)."
               % (e["peak"], e["trough"], e["depth_pct"], dom_a, e["by_asset_gross"][dom_a],
                  dom_m, e["by_member_gross"][dom_m]))
    dy = s["daily"]["per_year"]
    hr = ", ".join("%s %.3f" % (r["anchor"][:4], r["hit_rate"]) for r in dy)
    obs.append("8. Daily hit rate by anchor year: %s (overall %.3f)." % (hr, s["daily"]["overall"]["hit_rate"]))
    obs.append("9. Member standalone costs exceed realised costs by %.3f "
               "(netting benefit of averaging members before trading)."
               % (-s["member_cost_netting_residual"],))
    bk = {}
    for r in s["by_book"]:
        bk[r["book"]] = bk.get(r["book"], 0.0) + r["gross"]
    obs.append("10. Book gross across members: "
               + ", ".join("%s %.3f" % kv for kv in sorted(bk.items(), key=lambda kv: -kv[1])) + ".")
    return obs


if __name__ == "__main__":
    main()
