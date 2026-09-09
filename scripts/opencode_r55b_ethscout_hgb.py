"""R55b ETH scout (3/3): cheap CPU HGBClassifier walk-forward + GO/NO-GO diagnostics.

- Pattern B1 purged monthly folds (trailing 730d, embargo 8d >= 7d horizon),
  seed co dinh duy nhat; predict 3-class direction (class7).
- Metrics OOS pooled DIAGNOSTIC ONLY (no portfolio): rank Spearman P(up)~fwd7,
  top-decile hit P(fwd7>0|top10% P(up)), calibration-in-the-large.
- GO/NO-GO rule doc trong configs/opencode_v142_ethscout.json TRUOC khi fit;
  script assert ban copy khop config goc (frozen rule), roi moi chot verdict.
- Ghi thu muc MOI artifacts/research/opencode_v142_ethscout/... (khong ghi de).
"""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import torch  # noqa: F401 - torch truoc pandas (DLL load-order Windows host)
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from threadpoolctl import threadpool_limits

CFG_PATH = "configs/opencode_v142_ethscout.json"
SEED = 1729


def spearman(a: np.ndarray, b: np.ndarray) -> float:
    ra = pd.Series(a).rank().to_numpy()
    rb = pd.Series(b).rank().to_numpy()
    ra -= ra.mean()
    rb -= rb.mean()
    den = float(np.sqrt((ra * ra).sum() * (rb * rb).sum()))
    if den == 0:
        return float("nan")
    return float((ra * rb).sum() / den)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", type=str, required=True)
    ap.add_argument("--output", type=str, default=None)
    a = ap.parse_args()
    root = Path(__file__).resolve().parents[1]
    cfg = json.loads((root / CFG_PATH).read_text())
    ds = root / a.dataset
    dec = pd.read_parquet(ds / "decisions.parquet")
    dec["signal_time"] = pd.to_datetime(dec["signal_time"], utc=True)
    dec["label_end"] = pd.to_datetime(dec["label_end"], utc=True)
    with np.load(ds / "features.npz") as z:
        X = z["features"].astype(np.float64)
        fnames = [str(s) for s in z["feature_names"]]
    assert len(dec) == len(X) and np.isfinite(X).all()
    y = dec["class7"].to_numpy(dtype=int)  # 0 down / 1 flat / 2 up
    fwd7 = dec["fwd7"].to_numpy(float)

    # Frozen GO rule (pre-spec truoc fit).
    rule = cfg["go_nogo_rule_prespecified"]
    rank_min, hit_min = 0.05, 0.55
    assert f"OOS rank_primary > {rank_min}" in rule["GO_iff"] or "rank_primary > 0.05" in rule["GO_iff"]
    assert "topdecile_hit_primary > 0.55" in rule["GO_iff"]

    hp = cfg["model"]
    clf_kw = dict(max_iter=hp["max_iter"], max_leaf_nodes=hp["max_leaf_nodes"],
                  min_samples_leaf=hp["min_samples_leaf"], learning_rate=hp["learning_rate"],
                  l2_regularization=hp["l2_regularization"], max_bins=hp["max_bins"],
                  early_stopping=hp["early_stopping"], random_state=hp["random_state"])
    months = pd.date_range(dec["signal_time"].min().strftime("%Y-%m-01"),
                           "2026-03-01", freq="MS", tz="UTC")
    proba = np.full((len(dec), 3), np.nan)
    folds, skipped = [], []
    with threadpool_limits(limits=2):
        for fit_at in months:
            label = fit_at.strftime("%Y-%m")
            train = ((dec["label_end"] < fit_at - pd.Timedelta(days=8))
                     & (dec["signal_time"] >= fit_at - pd.Timedelta(days=730))).to_numpy()
            sel = (dec["signal_time"].dt.strftime("%Y-%m").to_numpy() == label)
            if sel.sum() == 0:
                continue
            if train.sum() < 200:
                skipped.append({"month": label, "train": int(train.sum()),
                                "eval": int(sel.sum()), "reason": "min_train_decisions=200"})
                continue
            if bool((dec["signal_time"][sel] < fit_at).any()):
                raise ValueError("Predictions before fitting clock")
            clf = HistGradientBoostingClassifier(**clf_kw).fit(X[train], y[train])
            proba[sel] = clf.predict_proba(X[sel])
            folds.append({"fit_at": str(fit_at), "train": int(train.sum()),
                          "eval": int(sel.sum()),
                          "train_balance": {str(k): int((y[train] == k).sum()) for k in (0, 1, 2)}})
            print({"month": label, "train": int(train.sum()), "eval": int(sel.sum())}, flush=True)
    oos = np.isfinite(proba).all(axis=1)
    assert oos.sum() > 0, "khong co OOS predictions"
    P = proba[oos]
    yo, fo = y[oos], fwd7[oos]
    p_up, p_flat, p_down = P[:, 2], P[:, 1], P[:, 0]

    rank_primary = spearman(p_up, fo)
    rank_secondary = spearman(p_up - p_down, fo)
    k = max(10, len(fo) // 10)
    order = np.argsort(p_up, kind="stable")
    top = order[-k:]
    bot = order[:k]
    hit_primary = float((fo[top] > 0).mean())
    hit_up_class = float((yo[top] == 2).mean())
    bot_pos = float((fo[bot] > 0).mean())
    cal = {
        "mean_p_down": float(p_down.mean()), "obs_freq_down": float((yo == 0).mean()),
        "mean_p_flat": float(p_flat.mean()), "obs_freq_flat": float((yo == 1).mean()),
        "mean_p_up": float(p_up.mean()), "obs_freq_up": float((yo == 2).mean()),
        "bias_up": float(p_up.mean() - (yo == 2).mean()),
        "bias_down": float(p_down.mean() - (yo == 0).mean()),
    }
    acc = float(((P.argmax(axis=1)) == yo).mean())
    ll = float(-np.log(np.clip(P[np.arange(len(yo)), yo], 1e-12, 1.0)).mean())
    # Per-fold rank (context only).
    dec_oos = dec[oos].reset_index(drop=True)
    Po = pd.DataFrame({"m": dec_oos["signal_time"].dt.strftime("%Y-%m"), "p": p_up, "f": fo})
    fold_rank = [{"month": m, "n": int(len(g)),
                  "rank": spearman(g["p"].to_numpy(), g["f"].to_numpy())}
                 for m, g in Po.groupby("m")]
    pos_months = sum(1 for r in fold_rank if (r["rank"] or 0) > 0)

    go = bool(rank_primary > rank_min and hit_primary > hit_min)
    verdict = "GO" if go else "NO-GO"
    rule_outcome = (f"rank_primary={rank_primary:.4f} {'>' if rank_primary > rank_min else '<='} {rank_min} "
                    f"AND hit_primary={hit_primary:.4f} {'>' if hit_primary > hit_min else '<='} {hit_min} "
                    f"=> {verdict} (BTC best: rank 0.074 v29 / hit ~0.49)")

    if a.output is None:
        hom_nay = datetime.now(timezone.utc).strftime("%Y%m%d")
        out = root / "artifacts" / "research" / "opencode_v142_ethscout" / f"hgb_{hom_nay}"
    else:
        out = Path(a.output)
        out = out if out.is_absolute() else root / out
    if out.exists():
        raise FileExistsError(f"{out} da ton tai: chon thu muc moi, khong ghi de.")
    out.mkdir(parents=True)
    (out / "config.json").write_text(json.dumps(cfg, indent=2, ensure_ascii=False))
    (out / "driver_source.py").write_text(Path(__file__).read_text())
    pd.DataFrame({"signal_time": dec["signal_time"][oos].to_numpy(),
                  "fwd7": fo, "class7": yo,
                  "p_down": p_down, "p_flat": p_flat, "p_up": p_up}
                 ).to_parquet(out / "predictions_oos.parquet", index=False)
    pd.DataFrame(folds).to_csv(out / "folds.csv", index=False)
    pd.DataFrame(fold_rank).to_csv(out / "fold_rank.csv", index=False)
    summary = {
        "experiment": "opencode-v142-ethscout-hgb",
        "dataset": str(a.dataset),
        "n_decisions": int(len(dec)),
        "n_oos": int(oos.sum()),
        "n_folds": len(folds),
        "skipped_folds": skipped,
        "model": {**clf_kw, "kind": "HistGradientBoostingClassifier"},
        "seed": SEED,
        "metrics_oos_pooled": {
            "rank_primary_spearman_pup_fwd7": rank_primary,
            "rank_secondary_spearman_pupdown_fwd7": rank_secondary,
            "topdecile_k": int(k),
            "topdecile_hit_primary_Pfwd7pos": hit_primary,
            "topdecile_hit_upclass": hit_up_class,
            "bottomdecile_Pfwd7pos": bot_pos,
            "calibration_in_the_large": cal,
            "accuracy": acc,
            "log_loss": ll,
            "fold_rank_pos_months": f"{pos_months}/{len(fold_rank)}",
        },
        "go_rule": rule["GO_iff"],
        "rule_outcome": rule_outcome,
        "verdict": verdict,
        "reference_btc": rule["reference"],
        "causality": "past-only features (bars <= t), labels strictly after t, purged monthly WF embargo 8d; exploratory labels; diagnostic only, no portfolio",
        "independent_test": False,
        "exploratory": True,
        "live_approved": False,
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    print(json.dumps(summary["metrics_oos_pooled"], indent=2), flush=True)
    print(rule_outcome, flush=True)
    print(f"DA GHI {out}", flush=True)


if __name__ == "__main__":
    main()
