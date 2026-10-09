"""audit_c2 truncation check: recompute 200 random ch_q10 rows from bars truncated at T.

For each sampled (sym, shift, T): keep ONLY bars of that (sym, shift) with
bar-open <= T (every bar after the context deleted — no close after T and no
bar opening after T is touched), rebuild the 512-close log context + sigma
exactly like oc_chronos/run_chronos_4shift.py, run Chronos-Bolt-small, and
compare (q10 - log C0)/sigma to the stored ch_q10. Must match.

GPU via heavy_slot (one job at a time); torch imported BEFORE pandas.
"""
import sys
import time
from pathlib import Path

import torch  # before pandas (Windows DLL load order)

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PYLIB = ROOT / "research/tournament/oc_chronos/pylib"
sys.path.insert(0, str(PYLIB))

import numpy as np
import pandas as pd

from chronos import ChronosBoltPipeline

MODEL = "amazon/chronos-bolt-small"
FEATS = ROOT / "research/tournament/oc_chronos/chronos_features_4shift.parquet"
BARS = ROOT / "research/tournament/oc_kronoshidden/bars_4h_4shift.parquet"
P, H = 512, 1
N_SAMPLE = 200
SEED = 42
OUT = HERE / "tmp" / "truncation_check.json"


def main():
    import json
    t0 = time.time()
    torch.manual_seed(20261007)
    pipe = ChronosBoltPipeline.from_pretrained(MODEL)
    pipe.model.to("cuda:0").eval()
    print(f"model loaded in {time.time()-t0:.0f}s quantiles={pipe.quantiles}", flush=True)

    f = pd.read_parquet(FEATS)
    f["T"] = pd.to_datetime(f["T"], utc=True)
    rng = np.random.default_rng(SEED)
    samp = f.iloc[rng.choice(len(f), size=N_SAMPLE, replace=False)].reset_index(drop=True)

    bars = pd.read_parquet(BARS)
    bars["T"] = pd.to_datetime(bars["T"], utc=True)
    groups = {(s, sh): g.sort_values("T").reset_index(drop=True)
              for (s, sh), g in bars.groupby(["sym", "shift"], sort=True)}

    ctxs, meta = [], []
    for _, r in samp.iterrows():
        sym, sh, T = r["sym"], int(r["shift"]), r["T"]
        g = groups[(sym, sh)]
        # truncate: every bar after the context deleted (keep bar-open <= T only)
        trunc = g[g["T"] <= T].reset_index(drop=True)
        pos = trunc.index[trunc["T"] == T]
        assert len(pos) == 1, (sym, sh, T)
        E = int(pos[0])
        assert E >= P, (sym, sh, T, E)  # full 512-bar context available
        closes = trunc["close"].to_numpy(dtype=np.float64)
        lo = np.log(trunc["open"].to_numpy(dtype=np.float64))
        sig = pd.Series(np.r_[np.nan, np.diff(lo)]).rolling(360).std().to_numpy()
        assert np.isfinite(sig[E]), (sym, sh, T)
        logc = np.log(np.clip(closes, 1e-12, None))
        ctxs.append(np.ascontiguousarray(logc[E - P:E], dtype=np.float32))
        meta.append(dict(sym=sym, shift=sh, T=str(T), E=E, C0=float(closes[E - 1]),
                         sigma=float(sig[E]), stored=float(r["ch_q10"])))

    ctx = torch.from_numpy(np.stack(ctxs)).to("cuda:0")
    qs = []
    with torch.no_grad():
        for i in range(0, len(ctx), 128):
            pred = pipe.predict(ctx[i:i + 128], prediction_length=H)
            qs.append(pred[:, :, 0].float().cpu().numpy())
    q = np.concatenate(qs, axis=0)  # (n, 9); q10 = col 0
    assert q.shape == (N_SAMPLE, 9), q.shape

    diffs = []
    for m, q10 in zip(meta, q[:, 0]):
        recomp = (float(q10) - np.log(m["C0"])) / m["sigma"]
        m["recomputed"] = recomp
        m["abs_diff"] = abs(recomp - m["stored"])
        diffs.append(m["abs_diff"])
    diffs = np.array(diffs)
    res = dict(n=N_SAMPLE, seed=SEED,
               max_abs_diff=float(diffs.max()), mean_abs_diff=float(diffs.mean()),
               n_over_1e4=int((diffs > 1e-4).sum()), n_over_1e3=int((diffs > 1e-3).sum()),
               pass_1e3=bool((diffs <= 1e-3).all()))
    (HERE / "tmp").mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(res, indent=1))
    print(json.dumps(res, indent=1), flush=True)
    print(f"elapsed {time.time()-t0:.0f}s", flush=True)
    assert res["pass_1e3"], res


if __name__ == "__main__":
    main()
