"""Equal-risk portfolio of out-of-sample books; one leverage scalar reported on a grid (disclosed as chosen on the OOS years)."""
import numpy as np, pandas as pd
from agentic_alpha_lab.oos_streams import family_stream, metrics
START = pd.Timestamp("2021-09-24", tz="UTC")
books = {"regime_btc": family_stream("BTCUSDT", "4h", "regime_scaled")}
for s in ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"):
    books[f"slow_{s[:3]}"] = family_stream(s, "4h", "tsmom")
    books[f"fast_{s[:3]}"] = family_stream(s, "1h", "tsmom_fast")
c = pd.read_parquet("artifacts/research/carry/carry_oos_fee0.0004.parquet")["carry"]
books["carry"] = c.groupby(c.index.floor("D")).apply(lambda x: float(np.prod(1 + x) - 1))
df = pd.DataFrame(books).fillna(0.0)
df = df[df.index >= START]
corr = df.corr()
print("mean pairwise correlation:", round(float(corr.values[np.triu_indices(len(corr), 1)].mean()), 2))
print(corr.round(2).loc[["regime_btc", "slow_BTC", "fast_BTC", "carry"], :].to_string())
# equal risk weights using the vol of the first OOS year only (known after 2022-09) would peek little; use trailing 180d vol instead (causal)
vol = df.rolling(180, min_periods=60).std().shift(1)
w = (1 / vol).div((1 / vol).sum(axis=1), axis=0).fillna(1 / df.shape[1])
port = (w * df).sum(axis=1)
print("\nlev | CAGR | monthly | maxDD | sharpe | hidden-year | yearly")
for lev in (1, 2, 3, 4, 5, 6, 8):
    r = port * lev
    m = metrics(r)
    yearly = [round(100 * float(np.prod(1 + g) - 1), 1) for _, g in r.groupby(((r.index - START).days // 365))]
    print(f"{lev:>3} | {100*m['cagr']:5.1f}% | {100*m['monthly']:4.2f}% | {100*m['dd']:4.1f}% | {m['sharpe']:.2f} | {100*m['hidden']:5.1f}% | {yearly}")
# gross leverage actually required per unit of capital (sum of |book exposure| is ~book gross, so report the book-weight sum times lev)
print("\nnote: each book is itself scaled to <=1x per asset; portfolio lev L means L x capital spread over the books")

print("\n== Two sleeves: trend group (equal risk inside, causal 180d vol) with gross multiplier L; carry sleeve at 3x")
trend_cols = [c for c in df.columns if c != "carry"]
tv = df[trend_cols].rolling(180, min_periods=60).std().shift(1)
tw = (1 / tv).div((1 / tv).sum(axis=1), axis=0).fillna(1 / len(trend_cols))
trend = (tw * df[trend_cols]).sum(axis=1)
# normalise the trend group to the average risk of a single book so L is comparable to "L x one book"
single_vol = df[trend_cols].std().mean()
trend_n = trend * (single_vol / trend.std())
print("trend group alone: sharpe", round(float(trend.mean() / trend.std() * np.sqrt(365)), 2), "vol ratio vs single book", round(float(trend.std() / single_vol), 2))
print("split(trend,carry) | L | CAGR | monthly | maxDD | hidden | yearly")
for split in ((1.0, 0.0), (0.7, 0.3), (0.5, 0.5)):
    for L in (1.0, 1.5, 2.0, 2.5, 3.0):
        r = split[0] * trend_n * L + split[1] * df["carry"] * 3.0
        m = metrics(r)
        yearly = [round(100 * float(np.prod(1 + g) - 1), 1) for _, g in r.groupby(((r.index - START).days // 365))][:5]
        print(f"{split} | {L} | {100*m['cagr']:5.1f}% | {100*m['monthly']:4.2f}% | {100*m['dd']:4.1f}% | {100*m['hidden']:5.1f}% | {yearly}")

print("\n== Continuous drawdown control on the combined book (exposure m = clip(1 - dd/cap, floor, 1) from yesterday's equity)")
def dd_control(r, cap, floor):
    eq, peak, out = 1.0, 1.0, []
    for x in r.to_numpy():
        dd = 1 - eq / peak
        m = min(1.0, max(floor, 1 - dd / cap))
        y = m * x
        eq *= 1 + y
        peak = max(peak, eq)
        out.append(y)
    return pd.Series(out, index=r.index)
for split in ((0.7, 0.3), (0.5, 0.5)):
    for L in (2.0, 2.5, 3.0, 4.0):
        base = split[0] * trend_n * L + split[1] * df["carry"] * 3.0
        for cap, floor in ((0.15, 0.25), (0.2, 0.25), (0.25, 0.1)):
            r = dd_control(base, cap, floor)
            m = metrics(r)
            if m["dd"] <= 0.22:
                print(f"{split} L={L} cap={cap} floor={floor} | CAGR {100*m['cagr']:5.1f}% monthly {100*m['monthly']:4.2f}% maxDD {100*m['dd']:4.1f}% hidden {100*m['hidden']:5.1f}%")
