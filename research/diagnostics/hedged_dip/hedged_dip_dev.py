"""Dev-only event study (holding bars 2021-09-24 .. 2025-09-17): are the M3-style dip limits an IDIOSYNCRATIC or a MARKET reversal?
Dip limit on ETH / SOL / BNB / XRP at k sigma_4h below the 4h open (k = 3, 4), fill on a 1m trade-through from minute 16, TP 1 sigma, native touch
stop 8 sigma, else exit at the next 4h open (maker entry / maker TP / taker exit, long funding at a settlement held). HEDGED variant: at the fill
minute's close a BTC short of equal notional is opened (taker), closed at the dip's exit minute (taker; next 4h open for a time exit); BTC short
earns no funding. Reports per dev year: fills, win, mean net per fill (%), 5% quantile, for unhedged and hedged.
  python research/diagnostics/hedged_dip/hedged_dip_dev.py
"""
import importlib.util, json
from pathlib import Path
import numpy as np, pandas as pd
RD = Path("research/parallel/rounds/parallel-20260906-r2")
def L(n, p):
    s = importlib.util.spec_from_file_location(n, p); m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
v293 = L("v293_hd", RD / "v293/v293_pooled_exit_agent.py")
MAKER, TAKER, FUND = 0.0002, 0.00055, 0.0001
ANCH = [pd.Timestamp(a, tz="UTC") for a in ("2021-09-24", "2022-09-24", "2023-09-24", "2024-09-24")]
STOP_DEV = pd.Timestamp("2025-09-17", tz="UTC")
btc = v293.Asset("BTCUSDT")
rows = []
for s in ("ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"):
    A = v293.Asset(s)
    assert len(A.t0) == len(btc.t0) and A.t0[0] == btc.t0[0]
    for j in range(1, A.nb - 1):
        T = A.t0[j]
        if T < ANCH[0] or T >= STOP_DEV:
            continue
        sg, o1, o2 = A.sig[j], A.o[j], A.o[j + 1]
        if not (np.isfinite(sg) and np.isfinite(o1) and np.isfinite(o2)):
            continue
        b0 = j * 240
        H, Lw, O = A.H[b0:b0 + 240], A.L[b0:b0 + 240], A.O[b0:b0 + 240]
        BC, BO = btc.C[b0:b0 + 240], btc.O[b0:b0 + 240]
        bo2 = btc.o[j + 1]
        settle = (T + pd.Timedelta(hours=4)).hour in (0, 8, 16)
        for k in (3.0, 4.0):
            lv = o1 * (1 - k * sg)
            hit = Lw[16:239] < lv
            if not hit.any():
                continue
            f = 16 + int(np.argmax(hit))
            tp, st = lv * (1 + sg), lv * (1 - 8 * sg)
            hs = Lw[f + 1:240] <= st; ht = H[f + 1:240] > tp
            ks = int(np.argmax(hs)) if hs.any() else None; kt = int(np.argmax(ht)) if ht.any() else None
            if ks is not None and (kt is None or ks <= kt):
                x = f + 1 + ks; ret = min(st, O[x]) / lv - 1 - MAKER - TAKER; bx = BC[x]
            elif kt is not None:
                x = f + 1 + kt; ret = tp / lv - 1 - 2 * MAKER; bx = BC[x]
            else:
                x = 240; ret = o2 / lv - 1 - MAKER - TAKER - (FUND if settle else 0.0); bx = bo2
            be = BC[f]
            if not (np.isfinite(be) and np.isfinite(bx)):
                continue
            hedge = 1 - bx / be - 2 * TAKER
            y = max(q for q, a in enumerate(ANCH) if T >= a)
            rows.append(dict(sym=s, k=k, y=y, ret=ret, hedged=ret + hedge, btc_move=bx / be - 1))
    print(s, flush=True)
d = pd.DataFrame(rows)
out = {}
for col in ("ret", "hedged"):
    g = d.groupby(["k", "y"])[col].agg(n="size", win=lambda x: round(float((x > 0).mean()), 3), mean=lambda x: round(float(100 * x.mean()), 3),
                                       q05=lambda x: round(float(100 * x.quantile(0.05)), 2))
    out[col] = g.reset_index().to_dict("records")
    print(col); print(g.unstack("y").to_string())
print("corr(ret, btc_move)", round(float(d[["ret", "btc_move"]].corr().iloc[0, 1]), 3))
Path("research/diagnostics/hedged_dip/hedged_dip_dev.json").write_text(json.dumps(out, indent=1))
