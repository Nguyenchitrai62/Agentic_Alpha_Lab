"""v290: information-satellite screen on CB - every audited "different information" set as a 20% satellite (registry v290).

Why: the only recent foundation gains came from members carrying DIFFERENT information at a small weight (v285: the Coinbase-premium
member D at 20% on C4 -> first gate pass); making D more similar to A/B hurt (v286). Five other information sets were rejected in
2026-09 only as EQUAL-weight members of the old v154 ensemble (v156 DVOL, v157 macro, v159 Fear & Greed, v160 CFTC COT) or as
replacements / 1/3 members in the D2 trade mode (v230 Korean premium) - never as a small satellite on the C4/CB foundation, which is
exactly how D failed first (v206) and then passed (v285). New data (fetched once, scripts/fetch_coinbase_alts.py): Coinbase SOL-USD /
XRP-USD 1h candles -> a PER-COIN Coinbase premium member Dc (D uses only the BTC / ETH market-wide premium).
Members (each annual + v202 quarterly, v144 builder, features merged into the v92 and v103 panels, excluded from the vol models; the
feature code and its publication lags are the audited modules' own):
  K  Korean premium (v230.korea_features, on t)            E  DVOL (v156.dvol_features, on t)
  F  US macro (v157: agentic_alpha_lab.patterns.macro, t)  G  Fear & Greed (v159.fng_features, on t)
  H  CFTC COT (v160.cot_features, on t)
  Dc per-coin Coinbase premium on (t, sym): for BTC / ETH / SOL / XRP, p = 1e4 log(Coinbase close / Binance spot close) at the 4h bar
     close exactly as v111.premium (Coinbase hour [t+3h, t+4h) close vs the Binance spot 4h close, tolerance 2h -> NaN in listing gaps);
     features cbc_dev = mean6 - mean540, cbc_z = cbc_dev / std540, cbc_chg = mean6 - mean42, cbc_relz = z540 of (mean6_c - mean6_btc);
     BNB rows NaN (not listed on Coinbase).
Fixed before running (everything else = CB / C4 rules: G2 grid trader, close5 dip stops 4 sigma + 8-sigma backstop, budget 0.18,
v221.KW, minute-5 rule, limit entries, SL market / TP limit, Bybit fees, adverse funding):
  CB_X     books = 0.8 x CB + 0.2 x (X + Xq)/2 for each X        (screen rows; dev years only)
  SAT      books = 0.8 x CB + 0.2 x mean over ACCEPTED X of (X + Xq)/2
ACCEPTANCE (dev only): X is accepted iff v286.dev_select({CB_ref, CB_X}) picks CB_X (robust criterion, DD filter on 2021-2024).
SAT exists only if >= 1 satellite is accepted; its most recent year is scored once. No other row is scored on the most recent year.
Reference: CB_ref must reproduce dev4 5.864. Builder check: annual K must reproduce member_K_annual exactly.
Known risk (disclosed before running): six comparisons -> a lucky acceptance is possible; SAT must also pass a robustness report
(stress rows vs CB, as p1_robustness) before any deployment.

  python research/parallel/rounds/parallel-20260906-r2/v290/v290_satellite_screen.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
RD = HERE.parent
C4R = dict(sleeve_stop_mode="close5", sleeve_backstop=8.0, m_sleeve_sl=4.0, sleeve_risk_budget=0.18)
SP = Path("data/raw/spot_majors_20260925")
CBDIR = {"BTC": Path("data/raw/coinbase_20260925"), "ETH": Path("data/raw/coinbase_20260925"),
         "SOL": Path("data/raw/coinbase_alts_20260930"), "XRP": Path("data/raw/coinbase_alts_20260930")}
DC = ("cbc_dev", "cbc_z", "cbc_chg", "cbc_relz")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def premium_series(coin: str) -> pd.DataFrame:
    """v111.premium for one coin: 6-bar mean and the rolling stats of the Coinbase-vs-Binance-spot premium at each 4h bar close."""
    cb = pd.read_parquet(CBDIR[coin] / f"{coin}-USD_1h.parquet")[["open_time", "close"]].rename(columns={"close": "cb"})
    cb["open_time"] = pd.to_datetime(cb["open_time"], utc=True)
    parts = [pd.read_parquet(f) for f in (SP / f"{coin}USDT_spot_4h_2017.parquet", SP / f"{coin}USDT_spot_4h.parquet") if f.exists()]
    bn = pd.concat([p[["open_time", "close"]] for p in parts], ignore_index=True)
    bn["open_time"] = pd.to_datetime(bn["open_time"], utc=True)
    bn = bn.drop_duplicates("open_time").sort_values("open_time").reset_index(drop=True)
    bn["key"] = bn["open_time"] + pd.Timedelta(hours=3)
    j = pd.merge_asof(bn, cb.sort_values("open_time"), left_on="key", right_on="open_time", direction="backward",
                      tolerance=pd.Timedelta(hours=2), suffixes=("", "_cb"))
    p = pd.Series(1e4 * np.log(j["cb"].astype(float) / j["close"].astype(float)).to_numpy(), index=bn["open_time"])
    return pd.DataFrame({"p6": p.rolling(6, min_periods=4).mean(), "p42": p.rolling(42, min_periods=30).mean(),
                         "m540": p.rolling(540, min_periods=270).mean(), "s540": p.rolling(540, min_periods=270).std()})


def percoin_features() -> pd.DataFrame:
    ps = {c: premium_series(c) for c in CBDIR}
    btc6 = ps["BTC"]["p6"]
    rows = []
    for c, d in ps.items():
        rel = d["p6"] - btc6.reindex(d.index)
        rz = (rel - rel.rolling(540, min_periods=270).mean()) / rel.rolling(540, min_periods=270).std()
        rows.append(pd.DataFrame({"t": d.index, "sym": f"{c}USDT", "cbc_dev": (d["p6"] - d["m540"]).to_numpy(),
                                  "cbc_z": ((d["p6"] - d["m540"]) / d["s540"]).to_numpy(), "cbc_chg": (d["p6"] - d["p42"]).to_numpy(),
                                  "cbc_relz": rz.to_numpy()}))
    return pd.concat(rows, ignore_index=True)


def feature_source(key):
    """-> (callable(b92) -> frame, merge keys, feature names)."""
    if key == "K":
        v230 = _load("v230_s", RD / "v230/v230_korea_premium_member.py")
        return (lambda b92: v230.korea_features()), ["t"], list(v230.KR)
    if key == "E":
        v156 = _load("v156_s", RD / "v156/v156_ensemble_dvol.py")
        return (lambda b92: v156.dvol_features(b92())), ["t"], list(v156.DV)
    if key == "G":
        v159 = _load("v159_s", RD / "v159/v159_ensemble_fng.py")
        return (lambda b92: v159.fng_features(pd.Series(b92()["t"].unique()))), ["t"], list(v159.FNG)
    if key == "H":
        v160 = _load("v160_s", RD / "v160/v160_ensemble_cot.py")
        return (lambda b92: v160.cot_features(pd.Series(b92()["t"].unique()))), ["t"], list(v160.COT)
    if key == "F":
        def fmac(b92):
            from agentic_alpha_lab.patterns import macro
            ts = pd.Series(sorted(b92()["t"].unique()))
            bars = pd.DataFrame({"t": ts, "close_time": ts + pd.Timedelta(hours=4) - pd.Timedelta(milliseconds=1)})
            mf = macro.compute(bars).reset_index(drop=True)
            cols = [c for c in mf.columns if c not in ("t", "close_time", "open_time")]
            return pd.concat([bars[["t"]], mf[cols]], axis=1)
        return fmac, ["t"], None  # names = every non-key column
    if key == "Dc":
        return (lambda b92: percoin_features()), ["t", "sym"], list(DC)
    raise KeyError(key)


def build_member(key: str, quarterly: bool):
    tag = f"{key}{'q' if quarterly else 'a'}"
    v144 = _load(f"v144_s{tag}", RD / "v144/v144_deploy_v3.py")
    if quarterly:
        _load(f"v202_s{tag}", RD / "v202/v202_quarterly_retrain.py").quarterly(v144)
    ext, v103 = v144.v115.v114.v113, v144.v103
    v144.v115.v114.v113.cb_bars = v144.v115.v114.cb_bars_ext
    ext.v92.load_asset = ext.load_asset_ext
    b92, b103, orig_vp = ext.v92.build, v103.build, v144.v129.vol_predict
    fn, on, names = feature_source(key)
    feats = fn(b92)
    names = names or [c for c in feats.columns if c not in on]
    v144.v129.vol_predict = lambda panel, fs, anchors, emb: orig_vp(panel, [c for c in fs if c not in names], anchors, emb)
    ext.v92.build = lambda: b92().merge(feats, on=on, how="left")
    v103.build = lambda: b103().merge(feats, on=on, how="left")
    return v144.books_v142()[1]


def main():
    v221 = _load("v221", RD / "v221/v221_grid_hysteresis.py")
    v286 = _load("v286_s", RD / "v286/v286_coinbase_member_upgrade.py")
    eu, v216, v204, v213 = v221.eu, v221.v216, v221.v204, v221.v216.v213
    books154, opens = eu.er.v154_books()
    cols, idx, C = list(books154.columns), books154.index, eu.er.CACHE
    k_ann = pd.read_parquet(C / "member_K_annual.parquet")
    chk = build_member("K", False).reindex(k_ann.index)[list(k_ann.columns)]
    diff = float((chk - k_ann).abs().max().max())
    assert diff < 1e-12, f"builder does not reproduce member_K_annual (max diff {diff})"
    print("builder check: member_K_annual reproduced exactly", flush=True)
    m = {k: pd.read_parquet(C / f).reindex(idx).fillna(0.0)[cols] for k, f in (
        ("A", "member_A_O1_orders.parquet"), ("Aq", "member_Aq_O1_orders.parquet"), ("B", "member_B_tv.parquet"), ("Bq", "member_Bq_tv.parquet"))}
    m["D"] = pd.read_parquet(C / "members_v154.parquet").xs("D", axis=1, level=0).reindex(idx).fillna(0.0)[cols]
    m["Dq"] = pd.read_parquet(C / "members_quarterly_D.parquet").reindex(idx).fillna(0.0)[cols]
    cb = 0.8 * (0.5 * (m["A"] + m["B"]) / 2 + 0.5 * (m["Aq"] + m["Bq"]) / 2) + 0.2 * (m["D"] + m["Dq"]) / 2
    sats = {}
    for key in ("K", "E", "F", "G", "H", "Dc"):
        pair = []
        for q in (False, True):
            cache = C / f"member_sat_{key}{'q' if q else ''}.parquet"
            if not cache.exists():
                build_member(key, q).to_parquet(cache)
            pair.append(pd.read_parquet(cache).reindex(idx).fillna(0.0)[cols])
        sats[key] = (pair[0] + pair[1]) / 2
        c = pd.concat([sats[key].stack(), cb.stack()], axis=1).corr().iloc[0, 1]
        print("satellite", key, "cached; book-weight corr with CB", round(float(c), 3), flush=True)
    prep = eu.prepare(books154, opens)
    trade = dict(v216.GRID, policy=v216.grid_policy(v221.B_ABS, v221.B_REL))
    out = {"version": "v290", "rows": {}, "trades": {}, "accepted": []}

    def run(key, bk):
        ev = []
        r = eu.simulate(bk, opens, prep, trade=trade, win_start=5, events=ev, **dict(v221.KW, **C4R))
        r["worst_dev_month_pct"] = round(v204.worst_month(r), 3)
        r["dev_dd"] = v286.dev_dd(r)
        out["rows"][key], out["trades"][key] = r, v213.trade_stats(ev)
        print(key, "dev4", r["monthly_dev4"], "worst", r["worst_dev_month_pct"], "devDD", r["dev_dd"],
              "dev years (net, dd1m)", [(y["anchor"][:4], y["net_pct"], y["dd_1m_pct"]) for y in r["yearly"][:4]],
              "dev win", out["trades"][key]["dev"]["win_rate"], flush=True)
        return r
    ref = run("CB_ref", cb)
    assert abs(ref["monthly_dev4"] - 5.864) < 0.002
    for key, sb in sats.items():
        run(f"CB_{key}", 0.8 * cb + 0.2 * sb)
        if v286.dev_select({k: out["rows"][k] for k in ("CB_ref", f"CB_{key}")}, v204.worst_month) == f"CB_{key}":
            out["accepted"].append(key)
    print("accepted satellites:", out["accepted"], flush=True)
    sel = None
    if out["accepted"]:
        run("SAT", 0.8 * cb + 0.2 * sum(sats[k] for k in out["accepted"]) / len(out["accepted"]))
        sel = "SAT"
        s_ = out["rows"]["SAT"]
        out["final_score_selected"] = {"monthly_5y": s_["monthly_5y"], "monthly_last_year": s_["monthly_last_year"],
                                       "losing_years": s_["losing_years"], "gate_dd": s_["gate_dd"], "gate_pass": s_["gate_pass"],
                                       "yearly": [(y["anchor"][:4], y["net_pct"], y["dd_1m_pct"]) for y in s_["yearly"]],
                                       "hidden_year_trades": out["trades"]["SAT"]["_hidden"],
                                       "sat_vs_cb_dev": dev_select_note(v286, v204, out)}
    else:
        out["final_score_selected"] = "no satellite accepted - CB stays; nothing scored on the most recent year"
    out["selected"] = sel
    for k in out["trades"]:
        if k != sel:
            out["trades"][k].pop("_hidden", None)
    for k in out["rows"]:
        if k != sel:
            for fld in ("monthly_last_year", "monthly_5y", "gate_dd", "gate_pass", "dd_4h", "dd_1m", "losing_years"):
                out["rows"][k].pop(fld, None)
            out["rows"][k]["yearly"] = out["rows"][k]["yearly"][:4]
    print("FINAL", sel, out["final_score_selected"], flush=True)
    raw = json.dumps(out, indent=1, default=str)
    (HERE / "v290_result.json").write_text(raw)
    print("sha256", hashlib.sha256(raw.encode()).hexdigest())


def dev_select_note(v286, v204, out):
    return "SAT preferred over CB_ref by dev_select" if v286.dev_select(
        {k: out["rows"][k] for k in ("CB_ref", "SAT")}, v204.worst_month) == "SAT" else "CB_ref preferred over SAT by dev_select"


if __name__ == "__main__":
    main()
