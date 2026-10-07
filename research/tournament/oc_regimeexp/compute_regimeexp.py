"""oc_regimeexp: month-start market states vs R2B1D17BF monthly returns.

REPORTING only. Light job: hourly_ext.parquet + oc_kpi/results_equity.json.
One process, small RAM (BTC hourly only, float64 series).
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "research" / "tournament" / "oc_regimeexp"
HOURLY = ROOT / "research" / "tournament" / "ext" / "hourly_ext.parquet"
KPI = ROOT / "research" / "tournament" / "oc_kpi" / "results_equity.json"
CUTOFF = pd.Timestamp("2026-09-24 00:00", tz="UTC")


def load_btc_4h_open():
    h = pd.read_parquet(HOURLY, columns=["t", "open", "close", "sym"])
    h = h[h["sym"] == "BTCUSDT"].sort_values("t").reset_index(drop=True)
    assert h["t"].max() <= CUTOFF, h["t"].max()
    h["t"] = pd.to_datetime(h["t"], utc=True)
    # 4h boundaries: hour % 4 == 0
    b = h[h["t"].dt.hour % 4 == 0][["t", "open", "close"]].reset_index(drop=True)
    b = b.rename(columns={"t": "T", "open": "o", "close": "c"})
    return b


def month_starts():
    ms = pd.date_range("2021-03-01", "2026-09-01", freq="MS", tz="UTC")
    report_months = pd.date_range("2021-09-01", "2026-09-01", freq="MS", tz="UTC")
    return ms, report_months


def vol30_at(btc_hourly, m0):
    # hourly bars with t < m0, last 720 log returns ending with bar closing at m0
    # bar with open time t closes at t+1h; bar closing at m0 has t = m0-1h
    h = btc_hourly[btc_hourly["t"] < m0].tail(721)
    assert len(h) == 721, (m0, len(h))
    cl = h["close"].to_numpy(dtype=float)
    r = np.log(cl[1:] / cl[:-1])
    assert len(r) == 720
    return float(np.std(r, ddof=1))


def states(b4, btc_hourly, times):
    o = b4.set_index("T")["o"]
    rows = []
    vol_hist = {}  # time -> vol, in order
    for m0 in times:
        p0 = float(o[m0])
        prev = o.loc[m0 - pd.Timedelta(hours=4 * 1200): m0 - pd.Timedelta(hours=4)]
        assert len(prev) == 1200, (m0, len(prev))
        mu = float(prev.mean())
        bear = int(p0 < mu)
        v = vol30_at(btc_hourly, m0)
        hist = np.array([vol_hist[t] for t in sorted(vol_hist)], dtype=float)
        if len(hist) >= 1:
            lo, hi = np.percentile(hist, [100 / 3, 200 / 3])
            lab = "low" if v <= lo else ("high" if v >= hi else "mid")
        else:
            lo, hi, lab = float("nan"), float("nan"), "warmup"
        past = o[m0 - pd.Timedelta(days=90)]
        s90 = float(np.log(p0 / float(past)))
        trend = "up" if s90 >= 0 else "down"
        rows.append(
            dict(
                month_start=str(m0.date()), bear=bear, mu1200=mu, p0=p0,
                vol30=v, vol_lo=float(lo) if len(hist) else None,
                vol_hi=float(hi) if len(hist) else None, vol=lab,
                s90=s90, trend=trend, n_prior_vol=len(hist),
            )
        )
        vol_hist[m0] = v
    return rows


def dist(rets):
    a = np.array(rets, dtype=float)
    return dict(
        n=int(len(a)), mean=float(np.mean(a)), median=float(np.median(a)),
        share_ge5=float(np.mean(a >= 5.0)), share_lt0=float(np.mean(a < 0.0)),
        worst=float(np.min(a)),
    )


def main():
    b4 = load_btc_4h_open()
    h = pd.read_parquet(HOURLY, columns=["t", "open", "close", "sym"])
    h = h[h["sym"] == "BTCUSDT"].sort_values("t").reset_index(drop=True)
    h["t"] = pd.to_datetime(h["t"], utc=True)

    ms_all, ms_rep = month_starts()
    all_rows = states(b4, h, list(ms_all))
    by_m0 = {r["month_start"]: r for r in all_rows}

    kpi = json.loads(KPI.read_text())
    monthly = kpi["monthly"]  # [ [YYYY-MM, pct], ... ] 61 rows
    assert len(monthly) == 61, len(monthly)
    months = []
    for ym, pct in monthly:
        m0 = pd.Timestamp(ym + "-01", tz="UTC")
        st = by_m0[str(m0.date())]
        assert st["vol"] in ("low", "mid", "high"), (ym, st["vol"])
        months.append(
            dict(month=ym, ret=float(pct), bear=st["bear"], vol=st["vol"],
                 trend=st["trend"], partial=ym in ("2021-09", "2026-09"))
        )

    out_states = [
        dict(month=m["month"], ret=m["ret"], bear=m["bear"], vol=m["vol"],
             trend=m["trend"], partial=m["partial"]) for m in months
    ]

    single = {}
    for col in ("bear", "vol", "trend"):
        dd = {}
        for m in months:
            dd.setdefault(m[col], []).append(m["ret"])
        tab = {}
        for k, rs in sorted(dd.items(), key=lambda kv: str(kv[0])):
            ms_ = [m["month"] for m in months if m[col] == k]
            d = dist(rs)
            d["months"] = ms_
            w = min(range(len(rs)), key=lambda i: rs[i])
            d["worst_month"] = ms_[w]
            tab[str(k)] = d
        single[col] = tab

    combos = {}
    thin = {}
    dd = {}
    for m in months:
        dd.setdefault((m["bear"], m["vol"], m["trend"]), []).append(m)
    for k in sorted(dd):
        name = f"bear{k[0]}_vol{k[1]}_trend{k[2]}"
        ms_ = [m["month"] for m in dd[k]]
        if len(dd[k]) >= 5:
            d = dist([m["ret"] for m in dd[k]])
            d["months"] = ms_
            rs = [m["ret"] for m in dd[k]]
            d["worst_month"] = ms_[int(np.argmin(rs))]
            combos[name] = d
        else:
            thin[name] = {"n": len(dd[k]), "months": ms_}

    # CURRENT states
    cur = {}
    oidx = b4.set_index("T")["o"]
    t_last = b4["T"].max()  # last 4h open in data (2026-09-23 20:00 UTC)
    assert t_last < CUTOFF
    for label, t, use_last in (
        ("month_start_2026-09-01", pd.Timestamp("2026-09-01", tz="UTC"), False),
        ("asof_last_data", CUTOFF, True),
    ):
        tp = t_last if use_last else t
        cp = CUTOFF if use_last else t  # vol window end: all bars t < cp
        p0 = float(oidx[tp])
        mu = float(oidx.loc[tp - pd.Timedelta(hours=4 * 1200): tp - pd.Timedelta(hours=4)].mean())
        v = vol30_at(h, cp)
        hist = np.array([r["vol30"] for r in all_rows if pd.Timestamp(r["month_start"], tz="UTC") < cp
                         and r["month_start"] >= "2021-03-01"], dtype=float)
        lo, hi = [float(x) for x in np.percentile(hist, [100 / 3, 200 / 3])]
        lab = "low" if v <= lo else ("high" if v >= hi else "mid")
        s90 = float(np.log(p0 / float(oidx[tp - pd.Timedelta(days=90)])))
        cur[label] = dict(T=str(tp), vol_end=str(cp), p0=p0, mu1200=mu, bear=int(p0 < mu),
                          vol30=v, vol_lo=lo, vol_hi=hi, vol=lab, s90=s90,
                          trend="up" if s90 >= 0 else "down",
                          n_prior_vol=int(len(hist)))

    results = {
        "meta": {
            "variant": "R2B1D17BF",
            "monthly_source": "research/tournament/oc_kpi/results_equity.json",
            "monthly_note": "61 calendar months 2021-09..2026-09, values in %; "
                            "2021-09 partial from 2021-09-24, 2026-09 partial to g1.",
            "market_source": "research/tournament/ext/hourly_ext.parquet",
            "cutoff": "2026-09-24 00:00 UTC",
            "definitions": {
                "bear": "o(M0) < mean of prior 1200 4h opens (strictly before M0)",
                "vol": "std of 720 hourly log returns ending at M0; expanding causal tercile vs prior month starts back to 2021-03-01",
                "trend": "sign of log(o(M0)/o(M0-90d)); zero -> up",
            },
            "n_months": 61,
        },
        "months": out_states,
        "by_single": single,
        "combos_n_ge5": combos,
        "combos_thin_n_lt5": thin,
        "current": cur,
    }
    (OUT / "results.json").write_text(json.dumps(results, indent=1))
    print(json.dumps({k: {kk: {kkk: round(v, 3) if isinstance(v, float) else v
                               for kkk, v in vv.items() if kkk != "months"}
                          for kk, vv in d.items()} for k, d in single.items()}, indent=1))
    print("combos:", {k: v["n"] for k, v in combos.items()})
    print("thin:", thin)
    print("current:", json.dumps(cur, indent=1))


if __name__ == "__main__":
    main()
