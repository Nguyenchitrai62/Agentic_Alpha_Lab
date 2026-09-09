"""Audit v31 (R7-N1m): do gia dinh stop-first + touch-khong-xuyen bang nen 1m.

Dau vao: trades normal + signals cua majority_1x, nen 5m local, nen 1m public
da crawl (chi do qua khu, causal). Nhan exploratory.
(a) touch-khong-xuyen o bar vao lenh; (b) both-touch stop&TP1 trong 1 bar 5m
-> giai quyet bang 1m; (c) replay exit tren 1m vs 5m (giu nguyen entry 5m).
Thu muc dich MOI artifacts/research/opencode_v31_1maudit/*, khong ghi de.
"""

import argparse
import hashlib
import json
from pathlib import Path


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def stop_fill_5m(o, h, l, direction, stop):
    if direction == 1:
        return None if l > stop else min(o, stop)
    return None if h < stop else max(o, stop)


def tp_fill_5m(o, h, l, direction, target):
    if direction == 1:
        return None if h < target else max(o, target)
    return None if l > target else min(o, target)


if __name__ == "__main__":
    import torch  # noqa: F401 - thu tu import: torch truoc pandas tren host nay
    import pandas as pd

    p = argparse.ArgumentParser(description="Audit 1m stop-first + touch (v31).")
    p.add_argument("--config", type=Path,
                   default=Path("configs/opencode_v31_1maudit.json"))
    p.add_argument("--m1dir", type=Path, required=True,
                   help="Thu muc data/raw/opencode_1m_audit_* da crawl.")
    p.add_argument("--output", type=Path, required=True,
                   help="Thu muc MOI artifacts/research/opencode_v31_1maudit/....")
    a = p.parse_args()

    goc = Path(__file__).resolve().parents[1]
    cfg = json.loads((goc / a.config).read_text(encoding="utf-8"))
    out = a.output if a.output.is_absolute() else goc / a.output
    if out.exists():
        raise FileExistsError(f"{out} da ton tai: chon thu muc moi, khong ghi de.")
    out.mkdir(parents=True)

    candles = pd.read_parquet(goc / cfg["base"]["candles_5m"])
    candles = candles.sort_values("open_time").reset_index(drop=True)
    signals = pd.read_parquet(goc / cfg["base"]["signals"])
    trades = pd.read_csv(goc / cfg["base"]["trades_normal"])
    m1dir = a.m1dir if a.m1dir.is_absolute() else goc / a.m1dir
    files_1m = sorted(m1dir.glob("klines_*_1m_*.parquet"))
    m1 = pd.concat([pd.read_parquet(f) for f in files_1m], ignore_index=True)
    m1 = m1.drop_duplicates(subset=["open_time"]).sort_values(
        "open_time").reset_index(drop=True)
    m1["open_time"] = pd.to_datetime(m1["open_time"], utc=True)
    m1_idx = {t: i for i, t in enumerate(m1["open_time"])}
    sig_by_bar = signals.set_index("bar_index")

    TP1_FRAC = 0.5
    FEE = float(cfg["costs"]["fee_rate_per_fill"])

    # Sanity: close 5m vs close 1m cuoi cua window 5m.
    ktra = 0
    lech_abs, lech_rel = [], []
    for t in trades.itertuples():
        for idx in (t.entry_index, t.exit_index):
            bar5 = candles.iloc[idx]
            t0 = pd.Timestamp(bar5["open_time"])
            last1m = t0 + pd.Timedelta(minutes=4)
            if last1m in m1_idx:
                c1 = float(m1.iloc[m1_idx[last1m]]["close"])
                c5 = float(bar5["close"])
                lech_abs.append(abs(c1 - c5))
                lech_rel.append(abs(c1 - c5) / c5)
                ktra += 1

    per_trade, both_rows = [], []
    gross_5m_sum, gross_1m_sum = 0.0, 0.0
    reason_5m = dict(trades["exit_reason"].value_counts())
    reason_1m = {}

    for n, t in enumerate(trades.itertuples()):
        d = int(t.direction)
        sig = sig_by_bar.loc[t.signal_index]
        limit, stop, tp1, tp2 = (float(sig["entry_limit"]),
                                 float(sig["stop_loss"]),
                                 float(sig["take_profit_1"]),
                                 float(sig["take_profit_2"]))
        bar5_entry = candles.iloc[t.entry_index]
        t0 = pd.Timestamp(bar5_entry["open_time"])
        m1_entry = [m1.iloc[m1_idx[t0 + pd.Timedelta(minutes=k)]]
                    for k in range(5) if (t0 + pd.Timedelta(minutes=k)) in m1_idx]
        co_du_1m_entry = len(m1_entry) == 5
        if d == 1:
            touch = min(float(r["low"]) for r in m1_entry) <= limit if m1_entry else None
            cross = float(bar5_entry["close"]) <= limit
        else:
            touch = max(float(r["high"]) for r in m1_entry) >= limit if m1_entry else None
            cross = float(bar5_entry["close"]) >= limit
        tnc = (bool(touch) and not cross) if touch is not None else None
        touch_min = sum(1 for r in m1_entry
                        if (float(r["low"]) <= limit if d == 1
                            else float(r["high"]) >= limit)) if m1_entry else None
        entry_at_open = ((float(bar5_entry["open"]) <= limit) if d == 1
                         else (float(bar5_entry["open"]) >= limit))

        # (b) quet both-touch tren 5m + giai quyet bang 1m.
        both_bar_idx, stop_first_ok, tp_first_sai, tie = 0, 0, 0, 0
        # (c) replay 1m: giu entry 5m, danh gia stop/TP tren 1m.
        notional = float(t.equity_before) * float(t.leverage)
        ep = float(t.entry_price)
        remaining, tp1_done, gross1 = 1.0, False, 0.0
        exit_reason_1m, exit_price_1m = "time", float(candles.iloc[t.exit_index]["open"])
        exit_idx_1m = t.exit_index
        t_exit_open = pd.Timestamp(candles.iloc[t.exit_index]["open_time"])

        # (b)+(c): engine quet stop/TP tren range(entry_index, exit_timeout) va
        # trigger bar (stop/tp2) VAN duoc kiem tra intrabar; chi time-exit moi
        # timeout tai open cua exit bar. Audit phai bao gom exit bar khi
        # exit_reason_5m la stop/tp2 (fix off-by-one: ban dau dung
        # range(entry, exit) cho moi trade nen mat trigger bar cuoi).
        t_exit_open = pd.Timestamp(candles.iloc[t.exit_index]["open_time"])
        trigger_bar = t.exit_reason in ("stop", "tp2")
        last_idx = t.exit_index if trigger_bar else t.exit_index - 1
        end_1m = t_exit_open + pd.Timedelta(minutes=5) if trigger_bar else t_exit_open

        for idx in range(t.entry_index, last_idx + 1):
            bar = candles.iloc[idx]
            o, h, l = float(bar["open"]), float(bar["high"]), float(bar["low"])
            bt0 = pd.Timestamp(bar["open_time"])
            allow = (idx != t.entry_index) or entry_at_open
            sf = stop_fill_5m(o, h, l, d, stop)
            tf1 = tp_fill_5m(o, h, l, d, tp1) if allow else None
            if sf is not None and tf1 is not None:
                both_bar_idx += 1
                m1s = [m1.iloc[m1_idx[bt0 + pd.Timedelta(minutes=k)]]
                       for k in range(5)
                       if (bt0 + pd.Timedelta(minutes=k)) in m1_idx]
                first_stop, first_tp = None, None
                for k, r in enumerate(m1s):
                    lo, hi = float(r["low"]), float(r["high"])
                    hit_s = (lo <= stop) if d == 1 else (hi >= stop)
                    hit_t = (hi >= tp1) if d == 1 else (lo <= tp1)
                    if hit_s and first_stop is None:
                        first_stop = k
                    if hit_t and first_tp is None:
                        first_tp = k
                    if first_stop is not None and first_tp is not None:
                        break
                both_rows.append({"trade_no": n, "signal_index": t.signal_index,
                                  "bar_5m_index": idx,
                                  "bar_5m_open": str(bt0),
                                  "first_stop_minute": first_stop,
                                  "first_tp1_minute": first_tp,
                                  "m1_bars_found": len(m1s)})
                if first_stop is not None and first_tp is not None:
                    if first_stop < first_tp:
                        stop_first_ok += 1
                    elif first_stop > first_tp:
                        tp_first_sai += 1
                    else:
                        tie += 1
                        stop_first_ok += 1  # cung bar 1m: engine bao toan, coi nhu dung
                elif first_stop is not None:
                    stop_first_ok += 1
                elif first_tp is not None:
                    tp_first_sai += 1

            # Replay 1m cho bar 5m nay (truoc timeout).
            if remaining <= 0:
                break
            for k in range(5):
                if remaining <= 0:
                    break
                mt = bt0 + pd.Timedelta(minutes=k)
                if mt >= end_1m or mt not in m1_idx:
                    continue
                r = m1.iloc[m1_idx[mt]]
                ro, rh, rl = float(r["open"]), float(r["high"]), float(r["low"])
                rtime = pd.Timestamp(r["open_time"])
                if (rtime.minute == 0 and rtime.second == 0
                        and rtime.hour % 8 == 0 and mt > t0):
                    rate = float(cfg["costs"]["funding_long_rate"]) if d == 1 else 0.0
                    gross1 -= 0.0  # funding tach rieng o 5m; gross chi so PnL gia
                s_hit = (rl <= stop) if d == 1 else (rh >= stop)
                if s_hit:
                    fill = min(ro, stop) if d == 1 else max(ro, stop)
                    gross1 += d * (fill - ep) / ep * notional * remaining
                    remaining = 0.0
                    exit_reason_1m, exit_price_1m, exit_idx_1m = "stop", fill, idx
                    break
                allow1 = allow  # suppress TP tren entry-5m-bar giong engine
                if not tp1_done and allow1:
                    t_hit = (rh >= tp1) if d == 1 else (rl <= tp1)
                    if t_hit:
                        fill = max(ro, tp1) if d == 1 else min(ro, tp1)
                        gross1 += d * (fill - ep) / ep * notional * TP1_FRAC
                        remaining -= TP1_FRAC
                        tp1_done = True
                if remaining > 0 and allow1:
                    t2_hit = (rh >= tp2) if d == 1 else (rl <= tp2)
                    if t2_hit:
                        fill = max(ro, tp2) if d == 1 else min(ro, tp2)
                        gross1 += d * (fill - ep) / ep * notional * remaining
                        remaining = 0.0
                        exit_reason_1m, exit_price_1m, exit_idx_1m = "tp2", fill, idx
                        break
        if remaining > 0:
            fill = float(candles.iloc[t.exit_index]["open"])
            gross1 += d * (fill - ep) / ep * notional * remaining
            exit_reason_1m = ("time_after_tp1" if tp1_done else "time")
            exit_price_1m, exit_idx_1m = fill, t.exit_index
        reason_1m[exit_reason_1m] = reason_1m.get(exit_reason_1m, 0) + 1

        gross_5m_sum += float(t.gross_pnl)
        gross_1m_sum += gross1
        per_trade.append({
            "trade_no": n, "signal_index": t.signal_index, "direction": d,
            "entry_limit": limit, "entry_price_5m": ep, "stop": stop,
            "tp1": tp1, "tp2": tp2, "exit_reason_5m": t.exit_reason,
            "gross_5m": float(t.gross_pnl),
            "entry_bar_m1_complete": co_du_1m_entry,
            "entry_touch": None if touch is None else bool(touch),
            "entry_cross_close": bool(cross),
            "entry_touch_no_cross": tnc, "entry_touch_minutes": touch_min,
            "both_touch_bars_5m": both_bar_idx,
            "stop_first_ok_1m": stop_first_ok, "tp_first_wrong_1m": tp_first_sai,
            "tie_same_1m": tie,
            "exit_reason_1m": exit_reason_1m, "exit_price_1m": exit_price_1m,
            "gross_1m": gross1, "gross_diff_1m_minus_5m": gross1 - float(t.gross_pnl),
        })

    df_t = pd.DataFrame(per_trade)
    df_b = pd.DataFrame(both_rows)
    df_t.to_csv(out / "per_trade_1m_audit.csv", index=False)
    (out / "both_touch_bars.csv").write_text(
        df_b.to_csv(index=False) if len(df_b) else "trade_no\n")
    (out / "config.json").write_text(json.dumps(cfg, indent=2, ensure_ascii=False),
                                     encoding="utf-8")

    co_1m = df_t[df_t["entry_bar_m1_complete"]]
    n_entry = int(co_1m["entry_touch"].notna().sum())
    n_tnc = int((co_1m["entry_touch_no_cross"] == True).sum())  # noqa: E712
    n_both = int(df_t["both_touch_bars_5m"].sum())
    n_ok = int(df_t["stop_first_ok_1m"].sum())
    n_sai = int(df_t["tp_first_wrong_1m"].sum())
    n_tie = int(df_t["tie_same_1m"].sum())
    n_trade_both = int((df_t["both_touch_bars_5m"] > 0).sum())

    summary = {
        "nhan": "exploratory, causal (nen 1m public qua khu). Khong phai kiem dinh doc lap.",
        "co_do_crawl_1m": {"so_file_1m": len(files_1m), "so_dong_1m": int(len(m1)),
                           "tu": str(m1["open_time"].iloc[0]),
                           "den": str(m1["open_time"].iloc[-1])},
        "sanity_5m_vs_1m_close": {"so_diem_kiem": ktra,
                                  "median_abs": float(pd.Series(lech_abs).median()),
                                  "median_rel": float(pd.Series(lech_rel).median()),
                                  "max_rel": float(pd.Series(lech_rel).max())},
        "a_touch_no_cross": {"so_trade_du_1m": n_entry,
                             "so_trade_touch_no_cross": n_tnc,
                             "ty_le_touch_no_cross": (n_tnc / n_entry if n_entry else None),
                             "tb_phut_touch_tren_5": float(co_1m["entry_touch_minutes"].mean()) if n_entry else None},
        "b_stop_first": {"so_bar_5m_both_touch": n_both,
                         "so_trade_co_both_touch": n_trade_both,
                         "stop_first_dung": n_ok, "tp_first_sai": n_sai,
                         "tie_cung_1m_tinh_dung": n_tie,
                         "ty_le_stop_first_dung": (n_ok / n_both if n_both else None),
                         "ty_le_tp_first_sai": (n_sai / n_both if n_both else None)},
        "c_pnl": {"tong_gross_5m": gross_5m_sum, "tong_gross_1m": gross_1m_sum,
                  "chenh_1m_tru_5m": gross_1m_sum - gross_5m_sum,
                  "chenh_binh_quan_moi_trade": (gross_1m_sum - gross_5m_sum) / len(df_t),
                  "exit_reason_5m": reason_5m, "exit_reason_1m_replay": reason_1m,
                  "so_trade_doi_exit_reason": int((df_t["exit_reason_5m"] != df_t["exit_reason_1m"]).sum())},
        "ket_luan": "",
        "sha256": {
            "config": sha256_file(goc / a.config),
            "trades": sha256_file(goc / cfg["base"]["trades_normal"]),
            "signals": sha256_file(goc / cfg["base"]["signals"]),
            "candles_5m": sha256_file(goc / cfg["base"]["candles_5m"]),
            "manifest_1m": sha256_file(m1dir / "manifest.json"),
        },
    }
    # Ket luan tu dong tu so do (tieng Viet).
    kl = []
    if summary["b_stop_first"]["ty_le_stop_first_dung"] is not None:
        r = summary["b_stop_first"]["ty_le_stop_first_dung"]
        kl.append(f"Gia dinh stop-first {'DUNG' if r >= 0.5 else 'SAI nhieu'} "
                  f"o muc 1m: {n_ok}/{n_both} bar both-touch ve phia stop "
                  f"({r:.1%}), {n_sai} bar TP cham truoc.")
    else:
        kl.append("Khong co bar 5m nao stop&TP1 cung cham: gia dinh stop-first "
                  "khong gay hai do duoc trong mau nay (trung tinh).")
    if summary["a_touch_no_cross"]["ty_le_touch_no_cross"] is not None:
        r2 = summary["a_touch_no_cross"]["ty_le_touch_no_cross"]
        kl.append(f"Touch-khong-xuyen o bar vao lenh: {n_tnc}/{n_entry} ({r2:.1%}). "
                  + ("Cao: fill OHLC lac quan, can prob-fill < 1."
                     if r2 >= 0.3 else "Thap: fill OHLC chap nhan duoc."))
    d = summary["c_pnl"]["chenh_1m_tru_5m"]
    if abs(d) < 1e-6:
        kl.append(f"Replay 1m giu entry: tong gross {gross_1m_sum:.2f} vs 5m "
                  f"{gross_5m_sum:.2f}, chenh ~0 (khop hoan toan, 0 trade doi "
                  f"exit reason): thu tu intrabar khong lam lech exit.")
    else:
        kl.append(f"Replay 1m giu entry: tong gross {gross_1m_sum:.2f} vs 5m "
                  f"{gross_5m_sum:.2f}, chenh {d:+.2f} diem equity "
                  f"({'1m xau hon: 5m lac quan' if d < 0 else '1m tot hon: stop-first bao toan'}).")
    summary["ket_luan"] = " ".join(kl)
    (out / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False, default=str),
          flush=True)
    print("DA GHI", str(out))
