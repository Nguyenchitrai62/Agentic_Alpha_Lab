"""v143 audit 4: independent recompute of v143_evaluate.py numbers from saved NN predictions.

Method (no leader v143 code imported; audit helpers reused from the audited
v132_v133_audit replication, attributed):
- Build 5-asset panels from raw (v114 extended for v92/v94 books, standard v103).
- Retrain HGB legs deterministically (v92 LO x5, v94 LS x15, v103 x10).
- Retrain v129 vol forecasts (x10) and replace vol42 with pvol before weights.
- Load saved NN parquets (artifacts/kaggle/v143/local_out), nn=mean(p6,p18).
- Per-anchor ICs (HGB/NN vs y6/y18) + causal scale ratio (prev-year std ratio, 1 first).
- Tranched books (mean over 6 phases, own 20%-cap-2 scales, 0.25/0.25/0.5,
  15% target ungoverned v110 sequential engine with carry) for
  primary_blend (0.5*HGB+0.5*ratio*NN) and secondary_nn_only (ratio*NN).
- Compare ICs/ratios/monthly/DD/yearly with v143/v143_result.json.
Writes eval_report.json.
"""
import importlib.util
import json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[5]
AUD = Path(__file__).resolve().parent
LEAD = json.loads((ROOT / "research/parallel/rounds/parallel-20260906-r2/v143/v143_result.json").read_text())
PRED = ROOT / "artifacts/kaggle/v143/local_out"

spec = importlib.util.spec_from_file_location(
    "rep132", ROOT / "research/parallel/rounds/parallel-20260906-r2/v132_v133_audit/replicate_v132_v133.py")
R = importlib.util.module_from_spec(spec)
spec.loader.exec_module(R)

SYMS5 = list(R.SYMS5)
ANCHORS = list(R.ANCHORS)


def main():
    print("building panels...", flush=True)
    panel114, panel103, bars114, bars103 = R.build_panels(SYMS5)
    f92 = [c for c in panel114.columns if c not in ("y", "t", "open", "sym", "bar") and not c.startswith("y")]
    # v94 feats: panel114 + y18/y42/y84 targets exist; feats exclude all y*
    f94 = [c for c in panel114.columns if c not in ("y", "t", "open", "sym", "bar") and not c.startswith("y")]
    f103 = [c for c in panel103.columns if c not in ("y", "t", "open", "sym", "bar") and not c.startswith("y")]
    print(f"feats {len(f92)}/{len(f94)}/{len(f103)}", flush=True)
    lo_parts, ls_parts, fl_parts = [], [], []
    for a in ANCHORS:
        te, n = R.train_v92(panel114, f92, a)
        lo_parts.append(te)
        print(f"lo {a} tr={n}", flush=True)
    for a in ANCHORS:
        te, ntrs = R.train_v94(panel114, f94, a)
        ls_parts.append(te)
        print(f"ls {a} tr={ntrs}", flush=True)
    for a in ANCHORS:
        te, ntrs = R.train_v103(panel103, f103, a)
        fl_parts.append(te)
        print(f"fl {a} tr={ntrs}", flush=True)
    lo = pd.concat(lo_parts, ignore_index=True)
    ls = pd.concat(ls_parts, ignore_index=True)
    fl = pd.concat(fl_parts, ignore_index=True)
    # NN
    nn = pd.concat([pd.read_parquet(PRED / f"pred_{a}.parquet") for a in ANCHORS], ignore_index=True)
    nn["t"] = pd.to_datetime(nn["t"], utc=True)
    nn["nn_raw"] = 0.5 * (nn["p6"] + nn["p18"])
    fl = fl.merge(nn[["t", "sym", "nn_raw"]], on=["t", "sym"], how="left")
    # ICs + ratios
    ic, ratio, prev = {}, {}, None
    for a in ANCHORS:
        m = (fl.t >= pd.Timestamp(a, tz="UTC")) & (fl.t < pd.Timestamp(a, tz="UTC") + pd.Timedelta(days=365))
        g = fl[m]
        ratio[a] = 1.0 if prev is None else float(prev["pred"].std() / prev["nn_raw"].std())
        prev = g
        ic[a] = {
            "hgb_y6": round(float(g[["pred", "y6"]].corr(method="spearman").iloc[0, 1]), 4),
            "nn_y6": round(float(g[["nn_raw", "y6"]].corr(method="spearman").iloc[0, 1]), 4),
            "hgb_y18": round(float(g[["pred", "y18"]].corr(method="spearman").iloc[0, 1]), 4),
            "nn_y18": round(float(g[["nn_raw", "y18"]].corr(method="spearman").iloc[0, 1]), 4),
        }
        print(a, ic[a], "scale", round(ratio[a], 3), flush=True)
    fl["scale"] = fl["t"].apply(lambda t: ratio[max(a for a in ANCHORS if t >= pd.Timestamp(a, tz="UTC"))])
    # vol forecasts
    print("vol forecasts...", flush=True)
    pv92, q92 = R.train_pvol(panel114, f92, bars114)
    pv103, q103 = R.train_pvol(panel103, f103, bars103)

    def swap(df, pv):
        d = df.merge(pv[["t", "sym", "pvol"]], on=["t", "sym"], how="left")
        d["vol42"] = d["pvol"].fillna(d["vol42"])
        return d.drop(columns="pvol")

    lo_s, ls_s = swap(lo, pv92), swap(ls, pv92)
    # books use o for vol_scale; carry/engine need o_103
    o_lo = lo_s.pivot_table(index="t", columns="sym", values="open")
    o_lo = o_lo[list(SYMS5)]
    carry = pd.read_parquet(R.CARRY_FILE)
    carry.index = pd.to_datetime(carry.index, utc=True)
    out = {"ic": ic, "nn_scale_ratio": ratio}
    for key, sig in (("primary_blend", lambda d: 0.5 * d["pred"] + 0.5 * d["scale"] * d["nn_raw"].fillna(0.0)),
                     ("secondary_nn_only", lambda d: d["scale"] * d["nn_raw"].fillna(0.0))):
        f2 = fl.assign(pred=sig(fl))
        fl_s = swap(f2, pv103)
        o_103 = fl_s.pivot_table(index="t", columns="sym", values="open")[list(SYMS5)]
        Wlo_raw = R.weights_lo_from_oos(lo_s, 5)
        W94_raw = R.weights_ls_from_oos(ls_s, 5)
        W103_raw = R.weights_ls_from_oos(fl_s, 5)
        Wlo, _ = R.tranche_mean(Wlo_raw)
        W94, _ = R.tranche_mean(W94_raw)
        W103, _ = R.tranche_mean(W103_raw)
        idx = Wlo.index.union(W94.index).union(W103.index).sort_values()
        idx = idx[idx >= o_103.index.min()]
        s_lo = R.vol_scale(o_lo.reindex(idx).ffill(), Wlo.reindex(idx).fillna(0.0))
        s94 = R.vol_scale(o_lo.reindex(idx).ffill(), W94.reindex(idx).fillna(0.0))
        s103 = R.vol_scale(o_103.reindex(idx), W103.reindex(idx).fillna(0.0))
        b_lo = Wlo.reindex(idx).fillna(0.0).mul(s_lo.reindex(idx).fillna(1.0), axis=0)
        b94 = W94.reindex(idx).fillna(0.0).mul(s94.reindex(idx).fillna(1.0), axis=0)
        b103 = W103.reindex(idx).fillna(0.0).mul(s103.reindex(idx).fillna(1.0), axis=0)
        books = 0.25 * b_lo + 0.25 * b94 + 0.5 * b103
        o = o_103.reindex(idx).sort_index()
        books = books[o.columns]
        carry_s = carry.reindex(idx)["carry"].astype(float).fillna(0.0)
        ret1 = o / o.shift(1) - 1
        realized = R.W_BOOKS * (books.shift(2) * ret1).sum(axis=1) + R.W_CARRY * R.CARRY_LEV * carry_s.shift(1)
        vol = realized.rolling(R.ROLL, min_periods=R.ROLL_MIN).std(ddof=1) * np.sqrt(R.PD * 365)
        s15 = (0.15 / vol).clip(upper=R.CAP).fillna(1.0).replace([np.inf, -np.inf], R.CAP).fillna(1.0)
        live = np.asarray((idx >= R.START) & (idx < R.END))
        res = {}
        for sc, (fee, slip) in R.SCEN.items():
            net, turn = R.run_seq(o.to_numpy(float), books.to_numpy(float), carry_s.to_numpy(float),
                                  s15.to_numpy(float), live, fee, slip)
            res[sc] = R.summarize_seq(pd.Series(net, index=idx), pd.Series(turn, index=idx))
            print(key, sc, res[sc]["monthly_pct"], "fullDD", res[sc]["full_path_dd"],
                  [(y["anchor"][:4], y["net_pct"], y["max_drawdown_percent"]) for y in res[sc]["yearly"]], flush=True)
        out[key] = res
    # compare
    cmp = {"ic_match": out["ic"] == LEAD["ic"],
           "ratio_match": all(abs(out["nn_scale_ratio"][a] - LEAD["nn_scale_ratio"][a]) < 1e-9 for a in ANCHORS)}
    for key in ("primary_blend", "secondary_nn_only"):
        for sc in ("normal", "fee_stress", "execution_stress"):
            b, l = out[key][sc], LEAD[key][sc]
            cmp[f"{key}.{sc}.monthly"] = {"blind": b["monthly_pct"], "leader": l["monthly_pct"],
                                          "diff": round(b["monthly_pct"] - l["monthly_pct"], 4)}
            cmp[f"{key}.{sc}.fullDD"] = {"blind": b["full_path_dd"], "leader": l["full_path_dd"],
                                         "diff": round(b["full_path_dd"] - l["full_path_dd"], 4)}
            for yb, yl in zip(b["yearly"], l["yearly"]):
                k = f"{key}.{sc}.{yb['anchor']}"
                cmp[k] = {"net_b": yb["net_pct"], "net_l": yl["net_pct"], "dd_b": yb["max_drawdown_percent"],
                          "dd_l": yl["max_drawdown_percent"], "fills_b": yb["fills"], "fills_l": yl.get("fills")}
    rep = {"recomputed": out, "leader": {"ic": LEAD["ic"], "nn_scale_ratio": LEAD["nn_scale_ratio"],
           "monthly": {k: {s: LEAD[k][s]["monthly_pct"] for s in ("normal", "fee_stress", "execution_stress")} for k in ("primary_blend", "secondary_nn_only")}},
           "comparison": cmp}
    (AUD / "eval_report.json").write_text(json.dumps(rep, indent=1, default=str))
    print(json.dumps(cmp, indent=1, default=str))


if __name__ == "__main__":
    main()
