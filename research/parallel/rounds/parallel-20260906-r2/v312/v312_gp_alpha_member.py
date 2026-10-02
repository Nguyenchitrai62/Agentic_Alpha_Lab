"""v312: GENETIC-PROGRAMMING alpha mining -> a new walk-forward book member G (registry v312, part 1 = features + member books).

Why: every MANUAL / BOT search so far recombines the same information; the book signal (IC ~0.07 at 7 days) is the long-run limit and the only
past step changes came from NEW information (TV indicators v231, whale flow v236 / v240, Coinbase premium v285). Genetic programming searches
formulaic transformations of the raw 4h bar data (price, range, volume, taker flow, trade count, funding) that the hand-made features do not
contain.
NO LOOK-AHEAD BY CONSTRUCTION: the GP sees ONLY rows whose 7-day label window ends before MINE_END = 2021-09-24 - 17 days (the first anchor
minus the v92 embargo of 102 bars); the formulas are frozen once and then used unchanged for every anchor 2021-2025, where the member models are
fitted walk-forward exactly like the audited members (before each anchor - embargo). Every operator is causal (rolling windows end at the bar's
close; cross-sectional ops use the five majors at the same bar).
GP: terminals per symbol (wide frames, 4h bars): r (log close return), lc (log close), hl ((high - low) / close), lv (log quote volume), tb (taker-buy
share - 0.5), nt (log trade count), fr (last settled funding rate x 1e4, as v92 f7 timing); operators delta / lag / ts_mean / ts_std / ts_z /
ts_max / ts_min / ema (windows 3, 6, 12, 18, 42, 84, 180 bars), cs_rank / cs_demean, add / sub / mul / safe-div / max / min, abs / sign / neg /
slog. Fitness on two mining blocks by label end (B1 2017-09-01 .. 2019-08-31, B2 2019-09-01 .. MINE_END): pooled Spearman IC of the feature with
the v92 target y (7-day vol-normalised forward return from the next open); fit = min(|IC_B1|, |IC_B2|) if both ICs have the same sign else 0,
minus 0.001 per node; population 400, 25 generations, tournament 5, subtree crossover 0.7 / mutation 0.3, depth <= 4, GA seed 312.
Selection: hall of fame by fit, greedily keep formulas with fit >= 0.02 and |Spearman| < 0.6 to every base92 / O1 feature and to the kept GP
features (on the mining rows), at most K = 10. Output: artifacts/research/engine_real/v312_gp_features.parquet (t, sym, gp0..), the formulas in
v312/gp_formulas.json.
MEMBER G = the audited O1 member A (v240 TV + order-level flow features, v144 builder: v92 7d + v94 18/42/84 + v103 6/18 targets, annual fits) with
the GP features added to every component; Gq = the v202 quarterly-retrained twin. Builder check: without the GP features the builder must reproduce
member_A_O1_orders exactly (as v287). Output: member_G_gp.parquet / member_Gq_gp.parquet.
Part 2 (scored separately, registered with its own selection rule): the member enters the walk-forward GA pool of the MANUAL / BOT products.

  python research/parallel/rounds/parallel-20260906-r2/v312/v312_gp_alpha_member.py
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import random
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
RD = HERE.parent
MINE_END = pd.Timestamp("2021-09-24", tz="UTC") - pd.Timedelta(days=17)
B1 = (pd.Timestamp("2017-09-01", tz="UTC"), pd.Timestamp("2019-09-01", tz="UTC"))
B2 = (pd.Timestamp("2019-09-01", tz="UTC"), MINE_END)
WINS = (3, 6, 12, 18, 42, 84, 180)
TERMS = ("r", "lc", "hl", "lv", "tb", "nt", "fr")
UN_TS = ("delta", "lag", "ts_mean", "ts_std", "ts_z", "ts_max", "ts_min", "ema")
UN = ("abs", "sign", "neg", "slog", "cs_rank", "cs_demean")
BIN = ("add", "sub", "mul", "div", "max", "min")
POP, GENS, TOUR, MAXD, K = 400, 25, 5, 4, 10
SEED = 312


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ------------------------------------------------------------------ expression trees
def rand_tree(rng, d=0):
    if d >= MAXD or (d > 0 and rng.random() < 0.3):
        return ("T", rng.choice(TERMS))
    u = rng.random()
    if u < 0.45:
        return (rng.choice(UN_TS), rng.choice(WINS), rand_tree(rng, d + 1))
    if u < 0.65:
        return (rng.choice(UN), rand_tree(rng, d + 1))
    return (rng.choice(BIN), rand_tree(rng, d + 1), rand_tree(rng, d + 1))


def size(t):
    return 1 if t[0] == "T" else 1 + sum(size(c) for c in t[1:] if isinstance(c, tuple))


def depth(t):
    return 0 if t[0] == "T" else 1 + max(depth(c) for c in t[1:] if isinstance(c, tuple))


def key(t):
    return json.dumps(t)


def nodes(t, path=()):
    yield path, t
    if t[0] != "T":
        for i, c in enumerate(t[1:], 1):
            if isinstance(c, tuple):
                yield from nodes(c, path + (i,))


def replace(t, path, new):
    if not path:
        return new
    lst = list(t)
    lst[path[0]] = replace(t[path[0]], path[1:], new)
    return tuple(lst)


class Evaluator:
    """Evaluates trees on wide frames (index = 4h bar open time, columns = the five majors); subtree cache by key."""

    def __init__(self, terms):
        self.T, self.cache = terms, {}

    def __call__(self, t):
        k = key(t)
        if k in self.cache:
            return self.cache[k]
        op = t[0]
        if op == "T":
            v = self.T[t[1]]
        elif op in UN_TS:
            w, x = t[1], self(t[2])
            if op == "delta":
                v = x - x.shift(w)
            elif op == "lag":
                v = x.shift(w)
            elif op == "ts_mean":
                v = x.rolling(w, min_periods=max(2, w // 2)).mean()
            elif op == "ts_std":
                v = x.rolling(w, min_periods=max(2, w // 2)).std()
            elif op == "ts_z":
                v = (x - x.rolling(w, min_periods=max(2, w // 2)).mean()) / x.rolling(w, min_periods=max(2, w // 2)).std()
            elif op == "ts_max":
                v = x.rolling(w, min_periods=max(2, w // 2)).max()
            elif op == "ts_min":
                v = x.rolling(w, min_periods=max(2, w // 2)).min()
            else:
                v = x.ewm(span=w, adjust=False, min_periods=w).mean()
        elif op in UN:
            x = self(t[1])
            v = {"abs": np.abs, "sign": np.sign, "neg": lambda z: -z}.get(op, None)
            if v is not None:
                v = v(x)
            elif op == "slog":
                v = np.sign(x) * np.log1p(np.abs(x))
            elif op == "cs_rank":
                v = x.rank(axis=1, pct=True)
            else:
                v = x.sub(x.mean(axis=1), axis=0)
        else:
            a, b = self(t[1]), self(t[2])
            if op == "add":
                v = a + b
            elif op == "sub":
                v = a - b
            elif op == "mul":
                v = a * b
            elif op == "div":
                v = a / b.where(b.abs() > 1e-9)
            elif op == "max":
                v = np.maximum(a, b)
            else:
                v = np.minimum(a, b)
        v = v.replace([np.inf, -np.inf], np.nan)
        if len(self.cache) < 20000:
            self.cache[k] = v
        return v


def spearman(a, b):
    m = np.isfinite(a) & np.isfinite(b)
    if m.sum() < 500:
        return np.nan
    ra, rb = pd.Series(a[m]).rank().to_numpy(), pd.Series(b[m]).rank().to_numpy()
    return float(np.corrcoef(ra, rb)[0, 1])


def terminals(load_asset, syms):
    cols = {}
    for s in syms:
        b, d, f = load_asset(s)
        b = b.drop_duplicates("open_time").set_index("open_time").sort_index()
        c = b["close"].astype(float)
        fr = f.set_index("fundingTime")["fundingRate"].sort_index() if len(f) else pd.Series(dtype=float)
        # funding known at the bar close: last settlement at or before the bar's close time (as v92 merge_asof on close_time)
        frb = pd.merge_asof(pd.DataFrame({"t": b["close_time"].to_numpy()}), pd.DataFrame({"t": fr.index, "f": fr.to_numpy()}),
                            on="t", direction="backward")["f"].to_numpy() if len(fr) else np.full(len(b), np.nan)
        qv = b["quote_volume"].astype(float)
        cols[s] = dict(r=np.log(c).diff(), lc=np.log(c), hl=(b["high"] - b["low"]) / c, lv=np.log(qv.clip(lower=1)),
                       tb=b["taker_buy_quote_volume"].astype(float) / qv.where(qv > 0) - 0.5, nt=np.log(b["num_trades"].astype(float).clip(lower=1)),
                       fr=pd.Series(frb * 1e4, index=b.index))
    T = {}
    for term in TERMS:
        T[term] = pd.DataFrame({s: cols[s][term] for s in syms}).sort_index()
    return T


def mine(T, panel, base_cols, log):
    ev = Evaluator(T)
    syms = list(T["r"].columns)
    lab_end = panel["t"] + pd.Timedelta(hours=4 * 43)
    rows = {}
    for nm, (a, b) in (("B1", B1), ("B2", B2)):
        sel = panel[(lab_end >= a) & (lab_end < b) & np.isfinite(panel["y"])]
        rows[nm] = sel
    pos = {nm: [(T["r"].index.get_indexer(g["t"]), syms.index(s)) for s, g in r.groupby("sym") if s in syms] for nm, r in rows.items()}
    ys = {nm: np.concatenate([r[r.sym == s]["y"].to_numpy(float) for s, _ in r.groupby("sym") if s in syms]) for nm, r in rows.items()}

    def vec(frame, nm):
        A = frame.to_numpy(float)
        return np.concatenate([A[ii, j] if (ii >= 0).all() else np.where(ii >= 0, A[np.clip(ii, 0, None), j], np.nan) for ii, j in pos[nm]])

    def fit(t):
        try:
            f = ev(t)
        except Exception:
            return -1.0, None
        ic = [spearman(vec(f, nm), ys[nm]) for nm in ("B1", "B2")]
        if not all(np.isfinite(ic)) or np.sign(ic[0]) != np.sign(ic[1]):
            return -0.001 * size(t), ic
        return float(min(abs(ic[0]), abs(ic[1])) - 0.001 * size(t)), ic

    rng = random.Random(SEED)
    pop = [rand_tree(rng) for _ in range(POP)]
    hof = {}
    for gen in range(GENS):
        sc = []
        for t in pop:
            k = key(t)
            if k not in hof:
                hof[k] = (t,) + fit(t)
            sc.append(hof[k][1])
        best = sorted(hof.values(), key=lambda z: -z[1])[:5]
        log(f"gen {gen} best {[round(b[1], 4) for b in best]} hof {len(hof)} cache {len(ev.cache)}")
        new = sorted(zip(sc, range(len(pop))), reverse=True)[: POP // 10]
        nxt = [pop[i] for _, i in new]
        while len(nxt) < POP:
            p1 = max(rng.sample(range(len(pop)), TOUR), key=lambda i: sc[i])
            if rng.random() < 0.7:
                p2 = max(rng.sample(range(len(pop)), TOUR), key=lambda i: sc[i])
                a, b = pop[p1], pop[p2]
                pa, _ = rng.choice(list(nodes(a)))
                _, sb = rng.choice(list(nodes(b)))
                c = replace(a, pa, sb)
            else:
                a = pop[p1]
                pa, _ = rng.choice(list(nodes(a)))
                c = replace(a, pa, rand_tree(rng, MAXD - 2))
            if depth(c) <= MAXD + 1:
                nxt.append(c)
        pop = nxt
    # greedy diverse selection on the mining rows
    allrows = pd.concat([rows["B1"], rows["B2"]])
    pos_all = [(T["r"].index.get_indexer(g["t"]), syms.index(s)) for s, g in allrows.groupby("sym") if s in syms]
    base_mat = np.concatenate([g[base_cols].to_numpy(float) for s, g in allrows.groupby("sym") if s in syms])

    def vec_all(frame):
        A = frame.to_numpy(float)
        return np.concatenate([np.where(ii >= 0, A[np.clip(ii, 0, None), j], np.nan) for ii, j in pos_all])

    kept, kept_v = [], []
    for t, f_, ic in sorted(hof.values(), key=lambda z: -z[1]):
        if f_ < 0.02 or len(kept) >= K:
            break
        v = vec_all(ev(t))
        cmax = max([abs(spearman(v, base_mat[:, q])) for q in range(base_mat.shape[1])] + [abs(spearman(v, u)) for u in kept_v] + [0])
        if cmax < 0.6:
            kept.append((t, f_, ic, cmax))
            kept_v.append(v)
            log(f"kept gp{len(kept) - 1} fit {f_:.4f} ic {ic} max|corr| {cmax:.2f} size {size(t)}: {key(t)}")
    return kept, ev


def build_member(quarterly, xg, v240, v287):
    tag = f"g{'q' if quarterly else 'a'}{int(xg is not None)}"
    v202 = _load(f"v202_{tag}", RD / "v202/v202_quarterly_retrain.py")
    v144 = _load(f"v144_{tag}", RD / "v144/v144_deploy_v3.py")
    if quarterly:
        v202.quarterly(v144)
    ext, v103 = v144.v115.v114.v113, v144.v103
    ext.cb_bars = v144.v115.v114.cb_bars_ext
    v144.v115.v114.v113.cb_bars = v144.v115.v114.cb_bars_ext
    ext.v92.load_asset = ext.load_asset_ext
    b92, b103, orig_vp = ext.v92.build, v103.build, v144.v129.vol_predict
    base92 = b92()
    xf = v240.feature_frame(ext.v92.load_asset, False)
    if xg is not None:
        xf = xf.merge(xg, on=["t", "sym"], how="left")
    drop = {c for c in xf.columns if c not in ("t", "sym")}
    v144.v129.vol_predict = lambda panel, fs, anchors, emb: orig_vp(panel, [c for c in fs if c not in drop], anchors, emb)
    ext.v92.build = lambda: base92.merge(xf, on=["t", "sym"], how="left")
    v103.build = lambda: b103().merge(xf, on=["t", "sym"], how="left")
    return v144.books_v142()[1]


def main():
    logf = (HERE / "gp.log").open("a")

    def log(s):
        print(s, flush=True)
        logf.write(s + "\n"); logf.flush()

    v240 = _load("v240_g", RD / "v240/v240_order_level_flow.py")
    v287 = _load("v287_g", RD / "v287/v287_path_label_member.py")
    C = Path("artifacts/research/engine_real")
    # builder check FIRST in a clean state (as v287): without GP features the builder must reproduce member_A_O1_orders
    a_o1 = pd.read_parquet(C / "member_A_O1_orders.parquet")
    chk = build_member(False, None, v240, v287).reindex(a_o1.index)[list(a_o1.columns)]
    # exact before 2026-09-01: the order-flow store was appended / corrected by the live backend for the last three weeks after the audited
    # member was cached (the ORIGINAL v240 builder shows the same 138 differing bars 2026-09-01 .. 2026-09-23 and none before)
    early = a_o1.index < pd.Timestamp("2026-09-01", tz="UTC")
    diff = float((chk - a_o1)[early].abs().max().max())
    late = float((chk - a_o1)[~early].abs().max().max())
    assert diff < 1e-12, f"builder does not reproduce member_A_O1_orders (max diff {diff})"
    log(f"builder check: member_A_O1_orders reproduced exactly before 2026-09-01 (late-period diff {late:.4f}, live store update)")
    fp = C / "v312_gp_features.parquet"
    if not fp.exists():
        v144 = _load("v144_g0", RD / "v144/v144_deploy_v3.py")
        ext = v144.v115.v114.v113
        ext.cb_bars = v144.v115.v114.cb_bars_ext
        ext.v92.load_asset = ext.load_asset_ext
        panel = ext.v92.build()
        xf = v240.feature_frame(ext.v92.load_asset, False)
        syms = list(v240.SYMS)
        T = terminals(ext.load_asset_ext, syms)
        base_cols = [c for c in panel.columns if c not in ("asset", "y", "t", "open", "sym", "bar")]
        pm = panel.merge(xf, on=["t", "sym"], how="left")
        base_cols += [c for c in xf.columns if c not in ("t", "sym")]
        kept, ev = mine(T, pm, base_cols, log)
        (HERE / "gp_formulas.json").write_text(json.dumps([dict(name=f"gp{i}", tree=t, fit=f_, ic=ic, max_corr=c) for i, (t, f_, ic, c) in enumerate(kept)],
                                                          indent=1))
        feats = []
        for i, (t, *_rest) in enumerate(kept):
            F = ev(t).stack().rename(f"gp{i}").reset_index()
            F.columns = ["t", "sym", f"gp{i}"]
            feats.append(F.set_index(["t", "sym"]))
        xg = pd.concat(feats, axis=1).reset_index()
        xg["t"] = pd.to_datetime(xg["t"], utc=True)
        xg.to_parquet(fp)
    xg = pd.read_parquet(fp)
    log(f"features {xg.shape}")
    for name, q in (("G", False), ("Gq", True)):
        build_member(q, xg, v240, v287).to_parquet(C / f"member_{name}_gp.parquet")
        log(f"member {name} written")
    raw = (HERE / "gp_formulas.json").read_text()
    log("sha256 formulas " + hashlib.sha256(raw.encode()).hexdigest())


if __name__ == "__main__":
    main()
