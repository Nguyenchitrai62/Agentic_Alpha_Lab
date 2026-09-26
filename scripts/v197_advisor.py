"""Live advisory for the current best pipeline (v197) - RESEARCH OUTPUT ONLY, no orders are placed.

v197 (research/parallel/rounds/parallel-20260906-r2/v197, audited): v151 books (0.5 v144 + 0.5 options-flow model set,
frozen models in models/frozen/) at portfolio vol target 0.25 (cap 2), plus the dip-sleeve ladder, traded like the
user's rules (AGENTS.md): limit entries, stop-loss (market) and take-profit (limit) on every position.
Walk-forward (engine_user): first four years 5.56%/month, 5-year mean 5.00%/month, most recent year 2.76%/month,
DD 19.7%; the 5%/month gate is NOT passed. Not financial advice.

What it prints for the CURRENT 4h bar (the bar that opened after the last closed 4h candle):
1. Books: per major the target position (fraction of equity, + long / - short), a limit entry 0.10% better than the
   bar open, stop-loss entry -/+ 4 daily sigma (market) and take-profit entry +/- 8 daily sigma (limit); the order
   rests until the bar closes and is cancelled if unfilled (then re-run at the next bar).
2. Dip sleeve: for each major, four resting buy limits at open * (1 - k sigma_4h), k = 2.5/3/3.5/4, live from 16
   minutes after the bar open until 2 minutes before it closes; each filled rung gets a take-profit sell limit at
   L (1 + sigma_4h) and a stop at L (1 - 5 sigma_4h); if neither is hit, close it at the next 4h open.
   Rung size = s * g * 1.5 * 0.25/4 / 1.657 of equity; keep sum over OPEN rungs of size * (5 sigma_4h + 2%) <= 12%.
3. Confidence per asset: whether the two member models agree on the direction and how large the signal is relative to
   the pipeline's maximum per-asset weight.

The drawdown governor g needs the account's equity history: pass --dd <current drawdown from the 90-day peak, e.g.
0.08>; default 0 (g = 1). g = clip((0.20 - dd) / 0.10, 0, 1) scales every size.

  python scripts/v197_advisor.py [--dd 0.0] [--equity 10000]
"""

from __future__ import annotations

import argparse
import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts/research/advisor_shadow/v197_advice_latest.json"
RUNGS = (2.5, 3.0, 3.5, 4.0)
M_SL_BOOK, M_TP_BOOK = 4.0, 8.0
M_SL_RUNG, M_TP_RUNG = 5.0, 1.0
D_LIMIT = 0.001
RUNG_SIZE = 1.5 * 0.25 / 4 / 1.657
RISK_BUDGET, GAP = 0.12, 0.02


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def market_state(sess, sym):
    """Current 4h bar open (the bar in progress) and sigma_4h / sigma_d from the last 360 closed 4h bars."""
    from agentic_alpha_lab.data.binance_usdm import BASE_URL
    r = sess.get(f"{BASE_URL}/fapi/v1/klines", params={"symbol": sym, "interval": "4h", "limit": 400}, timeout=60)
    r.raise_for_status()
    k = pd.DataFrame(r.json()).iloc[:, :5]
    k.columns = ["open_time", "open", "high", "low", "close"]
    k["open_time"] = pd.to_datetime(k["open_time"], unit="ms", utc=True)
    for c in ("open", "high", "low", "close"):
        k[c] = k[c].astype(float)
    cur = k.iloc[-1]
    closed_opens = k["open"].iloc[:-1]
    sig4 = float(closed_opens.pct_change().tail(360).std())
    p = sess.get(f"{BASE_URL}/fapi/v1/ticker/price", params={"symbol": sym}, timeout=30).json()
    return dict(bar_open_time=cur["open_time"], bar_open=float(cur["open"]), last=float(p["price"]), sig4=sig4,
                sig_d=sig4 * np.sqrt(6))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dd", type=float, default=0.0, help="current drawdown of the account from its 90-day peak (0.08 = 8%)")
    ap.add_argument("--equity", type=float, default=10_000.0, help="account equity in USDT (for sizes in USDT)")
    args = ap.parse_args()
    g = float(np.clip((0.20 - args.dd) / 0.10, 0.0, 1.0))
    v151 = _load("v151_advisor_v197", ROOT / "scripts/v151_advisor.py")
    adv = v151.advise()
    scale = float(adv["portfolio_scale"])
    sess = requests.Session()
    now = datetime.now(timezone.utc)
    books, sleeve = [], []
    wmax = 0.8 * scale * 0.5  # reference size: a strong single-asset book weight at the current scale
    for sym in sorted(adv["perp_weight"]):
        w = (adv["perp_weight"][sym] + adv["spot_weight"].get(sym, 0.0)) * g  # directional part (carry leg removed)
        m = market_state(sess, sym)
        a, b = adv["members"]["v144"].get(sym, 0.0), adv["members"]["options_model"].get(sym, 0.0)
        agree = np.sign(a) == np.sign(b) and a != 0
        strength = min(abs(w) / wmax, 1.0) if wmax > 0 else 0.0
        conf = "CAO" if agree and strength >= 0.5 else ("TRUNG BINH" if agree and strength >= 0.2 else "THAP")
        side = "LONG" if w > 0.005 else ("SHORT" if w < -0.005 else "DUNG NGOAI (flat)")
        row = dict(symbol=sym, side=side, weight=round(w, 4), notional_usdt=round(abs(w) * args.equity, 2), confidence=conf,
                   members_agree=bool(agree), strength=round(strength, 2))
        if side.startswith(("LONG", "SHORT")):
            if w > 0:
                entry = m["bar_open"] * (1 - D_LIMIT)
                sl, tp = entry * (1 - M_SL_BOOK * m["sig_d"]), entry * (1 + M_TP_BOOK * m["sig_d"])
            else:
                entry = m["bar_open"] * (1 + D_LIMIT)
                sl, tp = entry * (1 + M_SL_BOOK * m["sig_d"]), entry * (1 - M_TP_BOOK * m["sig_d"])
            row.update(sl_pct=round(100 * abs(sl / entry - 1), 1), tp_pct=round(100 * abs(tp / entry - 1), 1))
            row.update(limit_entry=round(entry, 6), stop_loss_market=round(sl, 6), take_profit_limit=round(tp, 6),
                       last_price=m["last"], valid_until=str(m["bar_open_time"] + pd.Timedelta(hours=4)))
        books.append(row)
        rn = scale * g * RUNG_SIZE
        for k in RUNGS:
            L = m["bar_open"] * (1 - k * m["sig4"])
            sleeve.append(dict(symbol=sym, rung_sigma=k, buy_limit=round(L, 6), take_profit_limit=round(L * (1 + M_TP_RUNG * m["sig4"]), 6),
                               stop_loss_market=round(L * (1 - M_SL_RUNG * m["sig4"]), 6), size_frac=round(rn, 4),
                               size_usdt=round(rn * args.equity, 2), risk_frac=round(rn * (M_SL_RUNG * m["sig4"] + GAP), 4),
                               live_from=str(m["bar_open_time"] + pd.Timedelta(minutes=16)),
                               live_until=str(m["bar_open_time"] + pd.Timedelta(minutes=238)),
                               exit_if_open_at=str(m["bar_open_time"] + pd.Timedelta(hours=4)), last_price=m["last"]))
    out = dict(pipeline="v197", generated_at=now.isoformat(), decision_bar_close=adv["decision_bar_close"], governor_g=round(g, 3),
               portfolio_scale=scale, books=books, dip_sleeve=sleeve, sleeve_risk_budget=RISK_BUDGET,
               note=("RESEARCH OUTPUT, not financial advice; walk-forward: first four years 5.56%/month, 5-year mean 5.00%/month, "
                     "most recent year 2.76%/month, DD 19.7%; the 5%/month gate is NOT passed; models frozen "
                     + str(adv.get("models_cutoff"))))
    OUT.write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
    print(f"PIPELINE v197 | nen 4h quyet dinh: {adv['decision_bar_close']} | scale {scale} | governor g {g:.2f}")
    print("\n1) SACH GIAO DICH (vao lenh limit, SL market, TP limit; lenh chua khop se huy khi nen 4h ket thuc):")
    for r in books:
        if "limit_entry" in r:
            print(f"  {r['symbol']:8s} {r['side']:5s} {r['weight']*100:6.2f}% von (~{r['notional_usdt']} USDT)  "
                  f"entry {r['limit_entry']}  SL {r['stop_loss_market']} (-{r['sl_pct']}%)  TP {r['take_profit_limit']} (+{r['tp_pct']}%)  "
                  f"tin cay: {r['confidence']} (2 mo hinh {'cung' if r['members_agree'] else 'khac'} huong, do manh {r['strength']})")
        else:
            print(f"  {r['symbol']:8s} {r['side']}  (trong so {r['weight']*100:.2f}%)")
    gross = sum(abs(r["weight"]) for r in books)
    print(f"  => Tong vi the sach: {gross * 100:.1f}% von (don bay {gross:.2f} lan). Lich su: trung binh ~48% von, cao nhat ~230% von.")
    print("  => SL/TP xa la luoi an toan: mo hinh thuong tu dong/giam vi the sau ~2 ngay (trung vi), khong can cho cham TP/SL.")
    print(f"\n2) MUA DAY TRONG NEN (dat san tu phut 16 den phut 238 cua nen 4h hien tai; tong rui ro lenh dang mo <= {RISK_BUDGET*100:.0f}% von):")
    for r in sleeve:
        print(f"  {r['symbol']:8s} {r['rung_sigma']}sigma: BUY LIMIT {r['buy_limit']}  TP {r['take_profit_limit']}  SL {r['stop_loss_market']}  "
              f"size {r['size_frac']*100:.2f}% (~{r['size_usdt']} USDT)")
    print(f"\nDa luu: {OUT}")
    print("Luu y: day la ket qua nghien cuu, KHONG phai loi khuyen dau tu; pipeline chua dat cong 5%/thang (nam gan nhat 2.76%/thang).")


if __name__ == "__main__":
    main()
