"""oc_deliverytrack: tracking error of the carry spot-leg sale around quarterly delivery.

Assignment: docs/opencode/OPENCODE_W_oc_deliverytrack.md
Writes ONLY: research/tournament/oc_deliverytrack/{results.json,REPORT.md}
Reads (read-only): research/tournament/oc_cashcarry/results.json (33 trades +
  delivery dates, F_entry/S_entry/S_del/ret_alloc), local 1m klines under
  data/raw/ (Binance USD-M perp 1m as spot proxy per the carry_audit precedent;
  Bybit linear perp 1m as second venue; see DATA NOTE below).

Delivery-price definition cited from the repo (no browsing):
  research/tournament/carry_audit/COMPARISON.md leader adjudication:
  "A delivery future settles at the delivery INDEX (an average of spot prices),
  so both legs converge by construction" and the operational rule "sell the
  spot leg at the delivery time (08:00 UTC, ideally spread across the index
  averaging window)". No more precise averaging-window definition (e.g. exact
  minutes) was found in the repo docs or research/data_fetch/bybitq; the
  30 minutes before 08:00 UTC (07:30-08:00) is this task's operationalisation
  of that window, stated here explicitly.

DATA NOTE (honest): no Binance spot 1m and no Bybit spot 1m exist locally.
  Binance spot is 4h/1h/1d only (data/raw/spot_majors_20260925); Bybit spot is
  1h only (data/raw/bybit_quarterly_20261006/spot_*_1h.parquet, from
  2021-07-05). The 1m price sources used are:
  (a) Binance USD-M perp 1m (data/raw/btc_intraday_20260924/klines_1m_*.parquet,
      data/raw/majors_intraday_20260924/<COIN>_1m_*.parquet) as the spot proxy
      -- the exact precedent of research/tournament/carry_audit/COMPARISON.md;
      perp tracks spot within a few bp and the quarterly basis converges into
      delivery morning;
  (b) Bybit linear perp 1m (data/raw/bybit_linear_1m_20261004/<COIN>_1m.parquet,
      from 2021-06-01) as the second venue;
  (c) Bybit spot 1h closes (07:00 bar) as a spot cross-check where available.
Per-delivery reference (index proxy) = 30-min TWAP of (a) closes 07:30-08:00.

Per (coin, delivery D = 08:00 UTC on code date):
  TWAP      = mean(close) of 30 bars with open_time in [D-30m, D)
  px_open08 = open of the D bar (sell at the 08:00 open)
  VWAP_5    = sum(typical*volume)/sum(volume), typical=(H+L+C)/3, bars D..D+4
  px_0815   = open of the D+15m bar (late bot)
  slices6   = mean(close) of the 07:34/07:39/07:44/07:49/07:54/07:59 bars
              (6 equal slices across 07:30-08:00)
  te_bp(x)  = (x - TWAP)/TWAP * 1e4
  dret_pp(x)= ret_alloc(exit=x) - ret_alloc(exit=TWAP), with the frozen
              oc_cashcarry formula ret = (S-S_entry)/S_entry + (F_entry-S)/F_entry
              - 0.00275, using the trade's stored F_entry/S_entry.
Also recorded: TWAP vs the modelled S_del (spot 4h close of delivery bar).

Run: .venv/Scripts/python.exe scripts/heavy_slot.py run --tag oc_deliverytrack \
       --min-free-gb 2.0 -- .venv/Scripts/python.exe \
       research/tournament/oc_deliverytrack/compute_deliverytrack.py
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
OUT_JSON = HERE / "results.json"

CC_JSON = ROOT / "research" / "tournament" / "oc_cashcarry" / "results.json"
BIN_BTC = ROOT / "data" / "raw" / "btc_intraday_20260924"
BIN_MAJ = ROOT / "data" / "raw" / "majors_intraday_20260924"
BYB_LIN = ROOT / "data" / "raw" / "bybit_linear_1m_20261004"
BYB_SPOT = ROOT / "data" / "raw" / "bybit_quarterly_20261006"

FEE_PAIR = 0.00275


def load_binance_1m(coin: str, year: int) -> pd.DataFrame:
    if coin == "BTC":
        p = BIN_BTC / f"klines_1m_{year}.parquet"
    else:
        p = BIN_MAJ / f"{coin}USDT_1m_{year}.parquet"
    df = pd.read_parquet(p, columns=["open_time", "open", "high", "low", "close", "volume"])
    df = df.copy()
    df["open_time"] = pd.to_datetime(df["open_time"], utc=True)
    return df.sort_values("open_time").reset_index(drop=True)


def load_bybit_linear_1m(coin: str) -> pd.DataFrame:
    df = pd.read_parquet(BYB_LIN / f"{coin}USDT_1m.parquet")
    df = df.copy()
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    return df.sort_values("open_time").reset_index(drop=True)


def window_stats(df: pd.DataFrame, d: pd.Timestamp) -> dict:
    """All sell-point prices from one coin's 1m frame around delivery D (08:00 UTC)."""
    t0 = d - pd.Timedelta(minutes=30)
    pre = df.loc[(df["open_time"] >= t0) & (df["open_time"] < d)].reset_index(drop=True)
    if len(pre) != 30:
        return {"coverage_error": f"pre-window bars={len(pre)} != 30"}
    twap = float(pre["close"].mean())
    row08 = df.loc[df["open_time"] == d]
    if len(row08) != 1:
        return {"coverage_error": "missing 08:00 bar"}
    px_open08 = float(row08["open"].iloc[0])
    post = df.loc[(df["open_time"] >= d) & (df["open_time"] < d + pd.Timedelta(minutes=5))]
    if len(post) != 5 or float(post["volume"].sum()) <= 0:
        return {"coverage_error": f"post-window bars={len(post)}"}
    typ = (post["high"] + post["low"] + post["close"]) / 3.0
    vwap5 = float((typ * post["volume"]).sum() / post["volume"].sum())
    row15 = df.loc[df["open_time"] == d + pd.Timedelta(minutes=15)]
    if len(row15) != 1:
        return {"coverage_error": "missing 08:15 bar"}
    px_0815 = float(row15["open"].iloc[0])
    want = [d - pd.Timedelta(minutes=26 - 5 * k) for k in range(6)]  # 07:34..07:59
    sl = df.loc[df["open_time"].isin(want)]
    if len(sl) != 6:
        return {"coverage_error": f"slice bars={len(sl)} != 6"}
    slices6 = float(sl["close"].mean())
    return {
        "twap": twap,
        "px_open08": px_open08,
        "vwap_0800_0805": vwap5,
        "px_0815": px_0815,
        "slices6": slices6,
        "n_pre": 30,
    }


def te_bp(px: float, ref: float) -> float:
    return (px - ref) / ref * 1e4


def ret_alloc(exit_s: float, f_entry: float, s_entry: float) -> float:
    return (exit_s - s_entry) / s_entry + (f_entry - exit_s) / f_entry - FEE_PAIR


def main() -> None:
    cc = json.loads(CC_JSON.read_text(encoding="utf-8"))
    trades = cc["trades"]
    assert len(trades) == 33, f"expected 33 oc_cashcarry trades, got {len(trades)}"

    byb_cache: dict[str, pd.DataFrame | None] = {}
    byb_spot_cache: dict[str, pd.DataFrame | None] = {}

    def get_byb(coin: str):
        if coin not in byb_cache:
            try:
                byb_cache[coin] = load_bybit_linear_1m(coin)
            except FileNotFoundError:
                byb_cache[coin] = None
        return byb_cache[coin]

    def get_byb_spot(coin: str):
        if coin not in byb_spot_cache:
            p = BYB_SPOT / f"spot_{coin}USDT_1h.parquet"
            if p.exists():
                df = pd.read_parquet(p)
                df = df.copy()
                df["open_time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
                byb_spot_cache[coin] = df.sort_values("open_time").reset_index(drop=True)
            else:
                byb_spot_cache[coin] = None
        return byb_spot_cache[coin]

    rows = []
    for t in trades:
        coin, delivery = t["coin"], t["delivery"]
        d = pd.Timestamp(delivery, tz="UTC") + pd.Timedelta(hours=8)
        f_entry, s_entry, s_del = t["F_entry"], t["S_entry"], t["S_del"]
        rec: dict = {
            "coin": coin, "delivery": delivery,
            "F_entry": f_entry, "S_entry": s_entry, "S_del_model": s_del,
            "ret_alloc_model": t["ret_alloc"],
        }
        # --- primary venue: Binance perp 1m as spot proxy ---
        dfs = []
        for yr in sorted({d.year, (d - pd.Timedelta(hours=2)).year}):
            dfs.append(load_binance_1m(coin, yr))
        bdf = pd.concat(dfs, ignore_index=True).sort_values("open_time").reset_index(drop=True)
        ws = window_stats(bdf, d)
        if "coverage_error" in ws:
            rec["binance_error"] = ws["coverage_error"]
        else:
            tw = ws["twap"]
            rec["binance"] = {
                **{k: ws[k] for k in ("twap", "px_open08", "vwap_0800_0805", "px_0815", "slices6")},
                "te_bp": {k: te_bp(ws[k], tw) for k in ("px_open08", "vwap_0800_0805", "px_0815", "slices6")},
            }
            r_tw = ret_alloc(tw, f_entry, s_entry)
            rec["binance"]["ret_exit_twap"] = r_tw
            rec["binance"]["dret_pp_vs_twap"] = {
                k: (ret_alloc(ws[k], f_entry, s_entry) - r_tw) * 100.0
                for k in ("px_open08", "vwap_0800_0805", "px_0815", "slices6")
            }
            rec["binance"]["ret_exit"] = {
                k: ret_alloc(ws[k], f_entry, s_entry)
                for k in ("px_open08", "vwap_0800_0805", "px_0815", "slices6")
            }
            rec["binance"]["twap_vs_model_bp"] = te_bp(tw, s_del)
            rec["binance"]["dret_model_vs_twap_pp"] = (ret_alloc(s_del, f_entry, s_entry) - r_tw) * 100.0
        # --- second venue: Bybit linear perp 1m ---
        byb = get_byb(coin)
        if byb is None or d < byb["open_time"].iloc[0]:
            rec["bybit"] = {"unavailable": "linear 1m starts 2021-06-01" if byb is not None else "file missing"}
        else:
            wb = window_stats(byb, d)
            if "coverage_error" in wb:
                rec["bybit"] = {"unavailable": wb["coverage_error"]}
            else:
                rec["bybit"] = {
                    "twap": wb["twap"],
                    "te_bp": {k: te_bp(wb[k], wb["twap"]) for k in ("px_open08", "vwap_0800_0805", "px_0815", "slices6")},
                }
                if "binance" in rec:
                    rec["bybit"]["twap_vs_binance_bp"] = te_bp(wb["twap"], rec["binance"]["twap"])
        # --- spot cross-check: Bybit spot 1h 07:00 close ---
        bs = get_byb_spot(coin)
        if bs is not None:
            r7 = bs.loc[bs["open_time"] == d - pd.Timedelta(hours=1)]
            if len(r7) == 1 and "binance" in rec:
                c7 = float(r7["close"].iloc[0])
                rec["bybit_spot_1h_07close"] = c7
                rec["bybit_spot_07close_vs_twap_bp"] = te_bp(c7, rec["binance"]["twap"])
        rows.append(rec)

    ok = [r for r in rows if "binance" in r]
    assert len(ok) == 33, f"binance coverage {len(ok)}/33"
    methods = ("px_open08", "vwap_0800_0805", "px_0815", "slices6")
    summary = {}
    for m in methods:
        tes = np.array([r["binance"]["te_bp"][m] for r in ok])
        des = np.array([r["binance"]["dret_pp_vs_twap"][m] for r in ok])
        summary[m] = {
            "te_bp_mean": float(tes.mean()),
            "te_bp_std": float(tes.std(ddof=1)),
            "te_bp_worst_abs": float(np.abs(tes).max()),
            "te_bp_max": float(tes.max()),
            "te_bp_min": float(tes.min()),
            "dret_pp_mean": float(des.mean()),
            "dret_pp_worst_abs": float(np.abs(des).max()),
            "dret_pp_min": float(des.min()),
            "dret_pp_max": float(des.max()),
        }
        for coin in ("BTC", "ETH"):
            tes_c = np.array([r["binance"]["te_bp"][m] for r in ok if r["coin"] == coin])
            summary[m][f"te_bp_worst_abs_{coin}"] = float(np.abs(tes_c).max())
    tw_model = np.array([r["binance"]["twap_vs_model_bp"] for r in ok])
    dm_model = np.array([r["binance"]["dret_model_vs_twap_pp"] for r in ok])
    both = [r for r in ok if "bybit" in r and "twap" in r.get("bybit", {})]
    agree = np.array([r["bybit"]["twap_vs_binance_bp"] for r in both])
    spotx = np.array([r["bybit_spot_07close_vs_twap_bp"] for r in ok if "bybit_spot_07close_vs_twap_bp" in r])

    out = {
        "meta": {
            "n_trades": 33,
            "n_binance_ok": len(ok),
            "n_bybit_ok": len(both),
            "n_spotx_ok": len(spotx),
            "delivery_rule": "08:00 UTC on code date (oc_cashcarry)",
            "index_proxy": "30-min TWAP of Binance USD-M perp 1m closes 07:30-08:00 (spot proxy per carry_audit precedent)",
            "delivery_definition_cited": "research/tournament/carry_audit/COMPARISON.md leader adjudication: 'A delivery future settles at the delivery INDEX (an average of spot prices), so both legs converge by construction'; op rule 'sell the spot leg at the delivery time (08:00 UTC, ideally spread across the index averaging window)'. No exact minute-window definition found in repo/bybitq; 07:30-08:00 is this task's operationalisation.",
            "data": {
                "binance": "data/raw/btc_intraday_20260924/klines_1m_*.parquet + data/raw/majors_intraday_20260924/<COIN>USDT_1m_*.parquet (USD-M perp 1m, spot proxy)",
                "bybit": "data/raw/bybit_linear_1m_20261004/<COIN>USDT_1m.parquet (linear perp 1m, from 2021-06-01)",
                "bybit_spot_1h": "data/raw/bybit_quarterly_20261006/spot_<COIN>USDT_1h.parquet (spot cross-check)",
            },
            "ret_formula": "ret_alloc(S) = (S-S_entry)/S_entry + (F_entry-S)/F_entry - 0.00275 (frozen oc_cashcarry)",
            "slices6": "mean close of 07:34/07:39/07:44/07:49/07:54/07:59 bars (6 equal slices across 07:30-08:00)",
        },
        "summary": summary,
        "twap_vs_model": {
            "te_bp_mean": float(tw_model.mean()),
            "te_bp_worst_abs": float(np.abs(tw_model).max()),
            "dret_pp_mean": float(dm_model.mean()),
            "dret_pp_worst_abs": float(np.abs(dm_model).max()),
        },
        "venue_agreement": {
            "bybit_twap_vs_binance_twap_bp_mean": float(agree.mean()) if len(agree) else None,
            "bybit_twap_vs_binance_twap_bp_worst_abs": float(np.abs(agree).max()) if len(agree) else None,
            "bybit_spot07_vs_twap_bp_worst_abs": float(np.abs(spotx).max()) if len(spotx) else None,
        },
        "deliveries": rows,
    }
    OUT_JSON.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(f"wrote {OUT_JSON} n_ok={len(ok)}/33 n_bybit={len(both)}")
    for m, s in summary.items():
        print(f"{m}: te mean {s['te_bp_mean']:+.2f}bp std {s['te_bp_std']:.2f} worst {s['te_bp_worst_abs']:.2f} | "
              f"dret mean {s['dret_pp_mean']:+.4f}pp worst {s['dret_pp_worst_abs']:.4f}")


if __name__ == "__main__":
    main()
