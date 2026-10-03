"""v372 building block: SEQUENCE dataset for a CNN dip size agent (no selection input by itself).

Training rows = the pooled survivorship-free dip fills of v306 fit "U" (5 majors + 30 U2020 alts, all seven depths 2.0 .. 5.0, BOT labels: close5
4-sigma stop + 8-sigma backstop, TP 1 sigma -> y = y1.0, clipped to [-0.10, 0.08]; fill bar j, exit time t_exit, cross-fit half j % 2).
Inputs known at the OPEN of the holding bar (the deployable bar-open form, as the v306 tables): the seven v293 state features evaluated at minute 0
(x1 = the rung depth) plus two sequences over the PREVIOUS (closed) 4h bar: the coin's 240 one-minute log returns / sigma_4h and BTC's 240 one-minute
log returns / BTC sigma_4h (NaN -> 0).
Table rows = every major x holding bar from the first anchor on x the seven depths (the same bar-open inputs).
Output: artifacts/research/engine_real/v372_seq/{train.npz, table.npz} (float32), meta in manifest.json.
  python research/parallel/rounds/parallel-20260906-r2/v372/v372_seq_data.py
"""
import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

RD = Path("research/parallel/rounds/parallel-20260906-r2")
OUT = Path("artifacts/research/engine_real/v372_seq")
U = (2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0)


def L(n, p):
    s = importlib.util.spec_from_file_location(n, p); m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m


def seq(A, j):
    if j < 1:
        return np.zeros(240, np.float32)
    c = A.C[(j - 1) * 240: j * 240]
    prev = A.C[(j - 1) * 240 - 1] if (j - 1) * 240 - 1 >= 0 else np.nan
    lr = np.diff(np.log(np.r_[prev, c]))
    sg = A.sig[j]
    out = lr / sg if sg > 0 else lr * 0
    return np.nan_to_num(out, nan=0.0, posinf=0.0, neginf=0.0).astype(np.float32)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    v294 = L("v294_sq", RD / "v294/v294_wide_pool_exit_agent.py"); v293 = v294.v293
    eu = L("engine_user_sq", RD / "engine_user/engine_user.py")
    v293.RUNGS = U
    anchors = [pd.Timestamp(a, tz="UTC") for a in eu.ANCHORS]
    assets = {s: v293.Asset(s) for s in v293.MAJORS}
    btc = assets["BTCUSDT"]
    X, S, B, Y, J, TX, SYM = [], [], [], [], [], [], []
    for s in v293.MAJORS + v294.universe():
        A = assets[s] if s in assets else v293.Asset(s)
        d = v293.fills_of(A, eu.MAKER, eu.TAKER, eu.FUND_LONG, btc)
        if len(d):
            for j, row in zip(d["j"].astype(int), d.itertuples(index=False)):
                kk = j * 240
                st = [A.sp30(kk), getattr(row, "x1"), A.volreg[j], A.trend[j], btc.sp30(kk),
                      np.log(A.C[kk] / A.hmax24[kk]) / A.sig[j] if A.hmax24[kk] > 0 else np.nan, A.t0[j].hour]
                X.append(st); S.append(seq(A, j)); B.append(seq(btc, j))
            Y.append(np.clip(d["y1.0"].to_numpy(float), -0.10, 0.08)); J.append(d["j"].to_numpy(int)); TX.append(pd.to_datetime(d["t_exit"], utc=True).astype("int64").to_numpy())
            SYM += [s] * len(d)
        print("fills", s, len(d), flush=True)
        if s not in assets:
            del A
    np.savez_compressed(OUT / "train.npz", X=np.array(X, np.float32), S=np.array(S), B=np.array(B), y=np.concatenate(Y).astype(np.float32),
                        j=np.concatenate(J), t_exit=np.concatenate(TX), sym=np.array(SYM))
    TX_, TS_, TB_, meta = [], [], [], []
    for s, A in assets.items():
        for j, T in enumerate(A.t0):
            if T < anchors[0] or not np.isfinite(A.sig[j]):
                continue
            jj = max(q for q, a0 in enumerate(anchors) if T >= a0)
            kk = j * 240
            base = [A.sp30(kk), 0.0, A.volreg[j], A.trend[j], btc.sp30(kk),
                    np.log(A.C[kk] / A.hmax24[kk]) / A.sig[j] if A.hmax24[kk] > 0 else np.nan, T.hour]
            TX_.append(base); TS_.append(seq(A, j)); TB_.append(seq(btc, j)); meta.append((int(T.value), s, jj))
    np.savez_compressed(OUT / "table.npz", X=np.array(TX_, np.float32), S=np.array(TS_), B=np.array(TB_), T=np.array([m[0] for m in meta]),
                        sym=np.array([m[1] for m in meta]), anchor=np.array([m[2] for m in meta]),
                        anchors=np.array([int(a.value) for a in anchors]))
    man = {f: hashlib.sha256((OUT / f).read_bytes()).hexdigest() for f in ("train.npz", "table.npz")}
    (OUT / "manifest.json").write_text(json.dumps(dict(sha256=man, depths=U, embargo_days=7, note="bar-open inputs; y = y1.0 BOT labels"), indent=1))
    print("saved", man)


if __name__ == "__main__":
    main()
