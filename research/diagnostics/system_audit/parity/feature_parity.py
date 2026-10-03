"""Train/serve-skew audit, items 1-3: live advisor features / predictions / book rows vs the research builders and cached members.

Live side = the deployed advisor code (scripts/v240_advisor.py A set = v104_advisor + v233_advisor.live_tv + flow_frame(aggflow_live),
scripts/v233_advisor.py B set, scripts/v154_advisor.py Coinbase set used by scripts/v285_cb_advisor.py), run AS OF each 4h decision bar
(ADVISOR_ASOF) with its REST inputs served from one cached public REST download (klines 4h / 1d, funding) so every as-of run sees exactly
the bars a prospective run at that bar would have seen (4h: open >= asof-500d and close <= asof; 1d: 800d; last 1000 funding prints <=
asof; TradingView: the last 1499 closed 4h klines, as live_tv's limit=1500 call minus the forming bar). No data-update calls are made
(no Deribit / Coinbase / aggTrades writes). Two as-of panels are also built with the real REST code path to validate the emulation.

Research side = the research builders exactly as v240_order_level_flow.build_member / v286 (D) assemble the panels before training
(v144 books_v142 inputs: ext.v92.build with load_asset_ext, v103.build, v240.feature_frame (TV + order-level flow), v111.add_cb, v142.add_xs),
and the cached walk-forward members in artifacts/research/engine_real (research_books_d2 etc. from scripts/forward_v205.py).

Output: parity/feature_parity.json. Research/paper only; nothing outside research/diagnostics/system_audit/parity is written.

  .venv/Scripts/python.exe research/diagnostics/system_audit/parity/feature_parity.py
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import time
import types
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
os.chdir(ROOT)
sys.path.insert(0, str(HERE))
import rest_cache as rc  # noqa: E402

RD = ROOT / "research/parallel/rounds/parallel-20260906-r2"
OUT = HERE / "feature_parity.json"
SYMS = list(rc.SYMS)
COLS = ["BNBUSDT", "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]
WIN = pd.date_range("2026-09-01", "2026-09-23 20:00", freq="4h", tz="UTC")  # research archives end 2026-09-24 08:00


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def cmp_cols(a: pd.DataFrame, b: pd.DataFrame, cols) -> dict:
    """a, b aligned on the same index; per column: max abs diff, correlation, fraction equal within 1e-6 (NaN == NaN counts equal)."""
    out = {}
    for c in cols:
        x, y = a[c].astype(float).to_numpy(), b[c].astype(float).to_numpy()
        both = np.isfinite(x) & np.isfinite(y)
        nan_eq = np.isnan(x) & np.isnan(y)
        eq = (both & (np.abs(x - y) <= 1e-6)) | nan_eq
        d = np.abs(x - y)[both]
        corr = float(np.corrcoef(x[both], y[both])[0, 1]) if both.sum() > 2 and np.std(x[both]) > 0 and np.std(y[both]) > 0 else None
        out[c] = {"n": int(len(x)), "n_both_finite": int(both.sum()), "nan_mismatch": int((np.isnan(x) ^ np.isnan(y)).sum()),
                  "max_abs_diff": float(d.max()) if len(d) else None, "corr": None if corr is None else round(corr, 6),
                  "frac_eq_1e-6": round(float(eq.mean()), 4)}
    return out


def main():
    t0 = time.time()
    end = pd.Timestamp.now(tz="UTC").floor("4h")
    K4, K1D, FR = rc.market_data(end)
    print("REST cache ready", end, flush=True)

    # ---------------- live modules (deployed code) ----------------
    v240 = _load("par_v240_advisor", ROOT / "scripts/v240_advisor.py")
    v233a = v240.v233a
    v154 = _load("par_v154_advisor", ROOT / "scripts/v154_advisor.py")
    seta, setb, cbm = v240.seta, v233a.setb, v154.cbm
    models_a = __import__("pickle").loads(seta.MODELS.read_bytes())
    models_d = __import__("pickle").loads(cbm.MODELS.read_bytes())

    # (a) validation: real REST live_panel for two as-of bars (before patching)
    import requests
    val_T = [pd.Timestamp("2026-09-10 11:59:59.999", tz="UTC"), pd.Timestamp("2026-09-23 23:59:59.999", tz="UTC")]
    real_panels = {}
    for T in val_T:
        os.environ["ADVISOR_ASOF"] = str(T)
        real_panels[T] = seta.live_panel(requests.Session(), T.to_pydatetime())
        time.sleep(2)
    os.environ.pop("ADVISOR_ASOF", None)

    # (b) patch the REST inputs with the cached download (as-of slicing identical to the endpoints' semantics)
    import agentic_alpha_lab.data.binance_usdm as bu

    def fake_fetch(symbol, interval, start, end=None, session=None):
        src = K4 if interval == "4h" else K1D
        d = src[symbol]
        st, en = pd.Timestamp(start), pd.Timestamp(end)
        return d[(d.open_time >= st) & (d.open_time <= en)].reset_index(drop=True).copy()

    def fake_funding(session, sym):
        t = pd.Timestamp(os.environ["ADVISOR_ASOF"]) if os.environ.get("ADVISOR_ASOF") else None
        f = FR[sym]
        f = f[f.fundingTime <= t] if t is not None else f
        return f.tail(1000).reset_index(drop=True).copy()

    bu.fetch_klines = fake_fetch
    for m in (seta, setb, cbm):
        m.funding_asof = fake_funding
    orig_lp = seta.live_panel
    PC: dict = {}

    def cached_lp(session, now):
        k = str(now)
        if k not in PC:
            PC.clear()
            PC[k] = orig_lp(session, now)
        return PC[k].copy()

    for m in (seta, setb, cbm):
        m.live_panel = cached_lp
    TVC: dict = {}

    def fake_live_tv():
        T = pd.Timestamp(os.environ["ADVISOR_ASOF"])
        if T not in TVC:
            rows = []
            for sym in v233a.SYMS:
                b = K4[sym]
                b = b[b.close_time <= T].tail(1499).reset_index(drop=True)
                rows.append(pd.concat([pd.DataFrame({"t": b["open_time"], "sym": sym}), v233a.tvm.tv_features(b)], axis=1))
            TVC.clear()
            TVC[T] = pd.concat(rows, ignore_index=True)
        return TVC[T]

    v233a.live_tv = fake_live_tv
    STASH: dict = {}
    aug_a, aug_d = seta._augment, cbm._augment
    seta._augment = lambda r: STASH.__setitem__("A", aug_a(r)) or STASH["A"]
    cbm._augment = lambda r: STASH.__setitem__("D", aug_d(r)) or STASH["D"]

    # validation of the emulation against the real REST panels
    val = {}
    for T in val_T:
        os.environ["ADVISOR_ASOF"] = str(T)
        em = orig_lp(None, T.to_pydatetime())
        rp = real_panels[T]
        fe = [c for c in em.columns if c not in ("sym", "t", "bar")]
        j = rp.merge(em, on=["t", "sym"], suffixes=("_r", "_e"))
        md = max(float(np.nanmax(np.abs(j[f + "_r"].astype(float) - j[f + "_e"].astype(float)))) if j[f + "_r"].notna().any() else 0.0
                 for f in fe if f + "_r" in j)
        val[str(T)] = {"rows_real": len(rp), "rows_emulated": len(em), "rows_joined": len(j), "first_t_real": str(rp.t.min()),
                        "first_t_emulated": str(em.t.min()), "max_abs_diff_all_features": md}
    os.environ.pop("ADVISOR_ASOF", None)
    print("emulation check", val, flush=True)

    # ---------------- as-of loop ----------------
    shadow = [json.loads(x) for x in open(ROOT / "artifacts/research/advisor_shadow/shadow.jsonl", encoding="utf-8") if x.strip().startswith("{")]
    logged = sorted({pd.Timestamp(r["decision_bar_close"]) for r in shadow if r.get("candidate") in ("v240_O1", "v285_CB")
                     and not r.get("error") and "perp_weight" in r})
    bars_T = [t + pd.Timedelta(hours=4) - pd.Timedelta(milliseconds=1) for t in WIN] + [T for T in logged if T < end]
    featA, featD, recs = [], [], []
    fa_cols = sorted(set(models_a["feats92"]) | set(models_a["feats103"]))
    fd_cols = [c for c in sorted(set(models_d["feats92"]) | set(models_d["feats103"])) if c.startswith("cb_")]
    for k, T in enumerate(bars_T):
        os.environ["ADVISOR_ASOF"] = str(T)
        STASH.clear()
        a, b, d = seta.advise(), setb.advise(), cbm.advise()
        t = T + pd.Timedelta(milliseconds=1) - pd.Timedelta(hours=4)
        assert pd.Timestamp(a["decision_bar_close"]) == T, (a["decision_bar_close"], T)
        ra, rd_ = STASH["A"], STASH["D"]
        featA.append(ra[ra.t == t][["t", "sym"] + fa_cols])
        featD.append(rd_[rd_.t == t][["t", "sym"] + fd_cols])
        perp = {s: round(0.5 * a["perp_weight"].get(s, 0.0) + 0.5 * b["perp_weight"].get(s, 0.0), 4) for s in COLS}
        spot = {s: round(0.5 * a["spot_weight"].get(s, 0.0) + 0.5 * b["spot_weight"].get(s, 0.0), 4) for s in COLS}
        sc = round(0.5 * a["portfolio_scale"] + 0.5 * b["portfolio_scale"], 3)
        rec = {"t": t, "scale_a": a["portfolio_scale"], "scale_b": b["portfolio_scale"], "scale_d": d["portfolio_scale"]}
        for s in COLS:
            rec[f"o1_{s}"] = (perp[s] + spot[s]) / (0.8 * sc)
            rec[f"A_{s}"] = (a["perp_weight"][s] + a["spot_weight"][s]) / (0.8 * a["portfolio_scale"])
            rec[f"B_{s}"] = (b["perp_weight"][s] + b["spot_weight"][s]) / (0.8 * b["portfolio_scale"])
            rec[f"D_{s}"] = (d["perp_weight"][s] + d["spot_weight"][s]) / (0.8 * d["portfolio_scale"])
            rec[f"Aperp_{s}"], rec[f"Bperp_{s}"] = a["perp_weight"][s], b["perp_weight"][s]
            for key, src in (("pa", a), ("pb", b), ("pd", d)):
                for mk, mv in src["predictions"].items():
                    rec[f"{key}_{mk}_{s}"] = mv.get(s)
        recs.append(rec)
        if k % 10 == 0:
            print(k, len(bars_T), T, f"{time.time() - t0:.0f}s", flush=True)
    os.environ.pop("ADVISOR_ASOF", None)
    live = pd.DataFrame(recs).set_index("t").sort_index()
    featA = pd.concat(featA, ignore_index=True).set_index(["t", "sym"]).sort_index()
    featD = pd.concat(featD, ignore_index=True).drop_duplicates("t").set_index("t")[fd_cols].sort_index()
    live.to_parquet(HERE / "cache/live_asof_rows.parquet")
    featA.to_parquet(HERE / "cache/live_asof_featA.parquet")

    # ---------------- research panels (builders, no training) ----------------
    v144r = _load("par_v144r", RD / "v144/v144_deploy_v3.py")
    v240r = _load("par_v240r", RD / "v240/v240_order_level_flow.py")
    v111r = _load("par_v111r", RD / "v111/v111_coinbase_premium.py")
    ext, v103r, v142r = v144r.v115.v114.v113, v144r.v103, v144r.v142
    ext.cb_bars = v144r.v115.v114.cb_bars_ext
    v144r.v115.v114.v113.cb_bars = v144r.v115.v114.cb_bars_ext
    ext.v92.load_asset = ext.load_asset_ext
    base92 = ext.v92.build()
    xf = v240r.feature_frame(ext.v92.load_asset, False)
    p92x = v142r.add_xs(base92.merge(xf, on=["t", "sym"], how="left"), v142r.BASE)
    p103 = v103r.build()
    p103x = v142r.add_xs(p103.merge(xf, on=["t", "sym"], how="left"), v142r.BASE + v142r.FLOWX)
    cbf = v111r.add_cb(p103[["t", "sym"]]).drop(columns="sym").drop_duplicates("t").set_index("t")
    print("research panels built", f"{time.time() - t0:.0f}s", flush=True)

    win_idx = featA.index[featA.index.get_level_values(0).isin(WIN)]
    LA = featA.loc[win_idx]
    R92 = p92x.set_index(["t", "sym"]).reindex(win_idx)
    R103 = p103x.set_index(["t", "sym"]).reindex(win_idx)
    f92, f103 = models_a["feats92"], models_a["feats103"]
    res: dict = {"window": [str(WIN[0]), str(WIN[-1])], "emulation_check_vs_real_rest": val, "rows_compared": int(len(win_idx))}
    res["A_features_vs_research_p92"] = cmp_cols(LA, R92, f92)
    res["A_features_vs_research_p103"] = cmp_cols(LA, R103, [c for c in f103 if c not in f92])
    LDw = featD.reindex(WIN)
    res["D_cb_features_vs_research"] = cmp_cols(LDw, cbf.reindex(WIN), fd_cols)

    # TV-only: live 1499-bar window vs research full history, and data source: REST 4h klines vs research 4h archive
    tvc = [c for c in f92 if c.startswith("tv_")]
    res["tv_summary"] = {c: res["A_features_vs_research_p92"][c] for c in tvc}
    src = {}
    for s in SYMS:
        b, _, _ = ext.v92.load_asset(s)
        b = b.set_index("open_time")
        r = K4[s].set_index("open_time").reindex(WIN)
        a_ = b.reindex(WIN)
        src[s] = {c: float(np.nanmax(np.abs(r[c].astype(float) / a_[c].astype(float) - 1)))
                  for c in ("open", "high", "low", "close", "volume", "quote_volume", "num_trades", "taker_buy_quote_volume") if c in a_}
    res["kline_source_rest_vs_archive_max_rel_diff"] = src

    # ---------------- item 3: predictions / books vs cached research members ----------------
    fw = _load("par_forward_v205", ROOT / "scripts/forward_v205.py")
    eu = types.SimpleNamespace(er=types.SimpleNamespace(CACHE=ROOT / "artifacts/research/engine_real"))
    C = eu.er.CACHE
    mem = {k: pd.read_parquet(C / f)[COLS] for k, f in (("A", "member_A_O1_orders.parquet"), ("Aq", "member_Aq_O1_orders.parquet"),
                                                        ("B", "member_B_tv.parquet"), ("Bq", "member_Bq_tv.parquet"),
                                                        ("Dq", "members_quarterly_D.parquet"))}
    mem["D"] = pd.read_parquet(C / "members_v154.parquet").xs("D", axis=1, level=0)[COLS]
    rd2 = fw.research_books_d2(eu).reindex(WIN)
    ro1 = fw.research_books_o1(eu).reindex(WIN)
    lw = live.reindex(WIN)

    def corr_block(Lx, Rx):
        x, y = Lx.to_numpy().ravel(), Rx.to_numpy().ravel()
        ok = np.isfinite(x) & np.isfinite(y)
        per = {s: round(float(np.corrcoef(Lx[s], Rx[s])[0, 1]), 4) if Lx[s].std() > 0 and Rx[s].std() > 0 else None for s in COLS}
        return {"pooled_corr": round(float(np.corrcoef(x[ok], y[ok])[0, 1]), 4), "per_symbol_corr": per,
                "sign_agree": round(float((np.sign(x[ok]) == np.sign(y[ok])).mean()), 4),
                "mean_abs_diff": round(float(np.abs(x[ok] - y[ok]).mean()), 5), "max_abs_diff": round(float(np.abs(x[ok] - y[ok]).max()), 5),
                "mean_abs_live": round(float(np.abs(x[ok]).mean()), 5), "mean_abs_research": round(float(np.abs(y[ok]).mean()), 5)}

    L = {k: lw[[f"{k}_{s}" for s in COLS]].set_axis(COLS, axis=1) for k in ("A", "B", "D", "o1")}
    R = {k: v.reindex(WIN) for k, v in mem.items()}
    res["books_member_corr"] = {
        "A_live_vs_A_annual": corr_block(L["A"], R["A"]), "A_live_vs_Aq_quarterly": corr_block(L["A"], R["Aq"]),
        "A_live_vs_mean(A,Aq)": corr_block(L["A"], (R["A"] + R["Aq"]) / 2),
        "B_live_vs_mean(B,Bq)": corr_block(L["B"], (R["B"] + R["Bq"]) / 2),
        "D_live_vs_mean(D,Dq)": corr_block(L["D"], (R["D"] + R["Dq"]) / 2),
        "research_A_vs_Aq (model-vintage noise floor)": corr_block(R["A"], R["Aq"]),
        "research_D_vs_Dq (model-vintage noise floor)": corr_block(R["D"], R["Dq"]),
        "O1_row_live_vs_research_books_o1": corr_block(L["o1"], ro1),
        "D2_row_live_formula_vs_research_books_d2": corr_block(0.8 * L["o1"] + 0.2 * L["D"], rd2)}
    # combination skew: the logged O1 row = (perp_a+perp_b+spot_a+spot_b)/(0.8 x mean scale) = scale-weighted mean of A and B books
    eqw = (L["A"] + L["B"]) / 2
    sw = (L["A"].mul(lw["scale_a"], axis=0) + L["B"].mul(lw["scale_b"], axis=0)).div(lw["scale_a"] + lw["scale_b"], axis=0)
    res["O1_combination_skew"] = {
        "logged_row_vs_equal_weight_mean(A,B)": corr_block(L["o1"], eqw),
        "logged_row_vs_scale_weighted_mean": corr_block(L["o1"], sw),
        "scale_a_minus_scale_b": {"mean": round(float((lw.scale_a - lw.scale_b).mean()), 4), "max_abs": round(float((lw.scale_a - lw.scale_b).abs().max()), 4)},
        "weight_on_A_range": [round(float((lw.scale_a / (lw.scale_a + lw.scale_b)).min()), 4), round(float((lw.scale_a / (lw.scale_a + lw.scale_b)).max()), 4)]}
    # model prediction correlation is not available per model in the research caches (members store books); the live per-model
    # predictions are kept in cache/live_asof_rows.parquet

    # ---------------- replay of the logged live rows (Sep 28 .. Oct 3) ----------------
    lb_o1, lb_cb = fw.live_books("v240_O1"), fw.live_books("v285_CB")
    rep = live[live.index > WIN[-1]]
    o1r, dr = rep[[f"o1_{s}" for s in COLS]].set_axis(COLS, axis=1), rep[[f"D_{s}" for s in COLS]].set_axis(COLS, axis=1)
    ci, cd = o1r.index.intersection(lb_o1.index), dr.index.intersection(lb_cb.index)
    res["replay_vs_logged"] = {"O1_rows": corr_block(o1r.loc[ci], lb_o1.loc[ci][COLS]) | {"n_bars": len(ci)},
                               "CB_rows": corr_block(dr.loc[cd], lb_cb.loc[cd][COLS]) | {"n_bars": len(cd)}}
    per_bar = (o1r.loc[ci] - lb_o1.loc[ci][COLS]).abs().max(axis=1)
    res["replay_vs_logged"]["O1_max_abs_diff_per_bar"] = {str(k): round(float(v), 4) for k, v in per_bar.items()}
    mode = {}
    for r in shadow:
        if r.get("candidate") == "v240_O1" and not r.get("error") and "perp_weight" in r:
            mode[pd.Timestamp(r["decision_bar_close"]) + pd.Timedelta(milliseconds=1) - pd.Timedelta(hours=4)] = (r.get("mode"), bool(r.get("asof")))
    res["replay_vs_logged"]["O1_row_mode"] = {str(k): mode.get(k) for k in ci}
    # live features of the replayed bars: flow rows now come from the refreshed archive (<= 2026-10-01 20:00) or the live buckets after it
    res["runtime_s"] = round(time.time() - t0)
    OUT.write_text(json.dumps(res, indent=1, default=str))
    print("wrote", OUT, flush=True)


if __name__ == "__main__":
    main()
