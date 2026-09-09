"""Opencode v23 (R5-D1): funding rate lam FEATURE loc tin hieu majority dong bang.

Ghi chu tieng Viet (user doc):
- Nhiem vu huong du lieu moi: funding rate lam FEATURE (khac han v22-tranh-funding
  da chet vi K=6/12 khong loai duoc tin hieu nao).
- Dau vao dong bang (khong refit): tin hieu majority cua v15
  (artifacts/research/opencode_v15_mapensemble/majority_1x/signals.parquet, 94 tin hieu).
- Du lieu funding: data/raw/opencode_funding_20260907/funding_BTCUSDT.parquet
  (Binance fapi public, 2022-01-01 -> 2026-09-07, moi 8h, khong gap >9h).
- Nhan qua tuyet doi (causal): moi decision/signal chi dung cac ky funding co
  funding_time < signal_time (as-of join, searchsorted side=left tru 1).
  Dac trung qua khu: fund_rate hien tai, trung binh 7d/30d, do doc, z-score.
- Ma tran co dinh trong configs/opencode_v23_fundingfeat.json TRUOC khi chay:
  loc {control, band1, band2, dirconf} x sizing {1x, dd_guard} = 8 nhanh.
  BAND1/BAND2 chon sau khi xem phan phoi f7 (trung vi ~5.3e-05, P80 ~9.1e-05),
  ghi chet vao config truoc khi chay probe.
- Sizing dd_guard: tham chieu equity control_1x CUA CHINH NHANH NAY (qua khu,
  cat 1-microsecond, moc 100.0), ap dung tai thoi diem tin hieu DA LOC cua tung nhanh.
- Cong control: control_1x normal phai khop majority_1x da xuat ban
  (+165.17829563633006% / -20.086073993367803% / 63) neu khong thi STOP.
- Kich ban moi nhanh: normal / fee_stress (fee 0.00055) / execution_stress
  FillStress(5,5,5,0.00055,False), exposure<=1x. Monthly geometric theo duration
  cua configs/swing_v15_continuous_folds.json.
- Nhan exploratory: du lieu 2023-2026 da mo, khong phai kiem dinh doc lap.
  Chi backtest local, khong dat lenh live.
"""

import torch  # noqa: F401  (thu tu import: torch truoc pandas tren host nay)
import argparse
import json
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd
from agentic_alpha_lab.backtest.engine import CostModel, ExecutionConfig, run_backtest
from agentic_alpha_lab.backtest.execution_stress import FillStress, run_stress
from agentic_alpha_lab.data.training import sha256

DD_TRIGGER, DD_GUARD_LEV = 0.10, 0.5
LEV_MIN, LEV_MAX = 0.25, 1.0

# Tham chieu control da xuat ban (majority_1x, v15/B4).
XUAT_BAN = {"total_return": 1.6517829563633004,
            "max_drawdown": -0.20086073993367803, "trades": 63}


def tinh_feature_funding(df_tho):
    """Dac trung qua khu tu lich su funding (sap xep tang dan theo fundingTime).

    fund_7d: trung binh 21 ky; fund_30d/std30: 90 ky; fund_slope_7d: fund_7d
    hien tai tru fund_7d cach 21 ky; fund_z30: (fund_rate - fund_30d)/std30.
    Tat ca rolling min_periods day du -> cac dong dau la NaN (se bi as-of loai).
    """
    df = df_tho.sort_values("fundingTime").reset_index(drop=True).copy()
    r = df["fundingRate"].astype(float)
    df["fund_7d"] = r.rolling(21, min_periods=21).mean()
    df["fund_30d"] = r.rolling(90, min_periods=90).mean()
    df["fund_std30"] = r.rolling(90, min_periods=90).std()
    df["fund_slope_7d"] = df["fund_7d"] - df["fund_7d"].shift(21)
    df["fund_z30"] = (r - df["fund_30d"]) / df["fund_std30"]
    return df


def asof_join(signal_time, df_feat):
    """Chi so as-of: ky funding cuoi co funding_time < signal_time (tuyet doi qua khu)."""
    moc = df_feat["funding_time"].to_numpy()
    hoi = pd.to_datetime(signal_time, utc=True).to_numpy()
    return np.searchsorted(moc, hoi, side="left") - 1


def gan_feature(tin_hieu, df_feat):
    """Gan 5 cot funding qua khu vao bang tin hieu; kiem tra nhan qua."""
    idx = asof_join(tin_hieu["signal_time"], df_feat)
    assert bool((idx >= 89).all()), "thieu lich su 30d cho mot so tin hieu"
    lay = df_feat.iloc[idx].reset_index(drop=True)
    # Kiem tra thu cong: funding_time phai TRUOC signal_time (ng hiem ngat).
    assert bool((pd.to_datetime(lay["funding_time"], utc=True).to_numpy()
                 < pd.to_datetime(tin_hieu["signal_time"], utc=True).to_numpy()).all()), \
        "vi pham nhan qua: funding_time khong truoc signal_time"
    ra = tin_hieu.copy().reset_index(drop=True)
    ra["fund_rate"] = lay["fundingRate"].to_numpy()
    ra["fund_7d"] = lay["fund_7d"].to_numpy()
    ra["fund_30d"] = lay["fund_30d"].to_numpy()
    ra["fund_slope_7d"] = lay["fund_slope_7d"].to_numpy()
    ra["fund_z30"] = lay["fund_z30"].to_numpy()
    assert bool(ra[["fund_rate", "fund_7d", "fund_30d", "fund_slope_7d", "fund_z30"]].notna().all().all())
    return ra


def loc_theo_nhanh(df, loc, cfg):
    """Loc tin hieu dong bang theo dac trung funding qua khu (khong fit)."""
    if loc == "control":
        return df.copy().reset_index(drop=True)
    if loc == "band1":
        b = cfg["ban_b1_trung_tinh"]
        return df[(df["fund_7d"] >= b["fund_7d_min"]) & (df["fund_7d"] <= b["fund_7d_max"])].copy().reset_index(drop=True)
    if loc == "band2":
        b = cfg["ban_b2_am"]
        return df[df["fund_7d"] >= b["fund_7d_min"]].copy().reset_index(drop=True)
    if loc == "dirconf":
        giu_long = (df["direction"] == 1) & (df["fund_rate"] > 0)
        giu_short = (df["direction"] == -1) & (df["fund_rate"] < 0)
        return df[giu_long | giu_short].copy().reset_index(drop=True)
    raise ValueError(f"loc la {loc}")


def muc_dd_guard_tai(diem_tin_hieu, giao_dich_tham_chieu):
    """Trang thai guard tu equity control, tai cac diem tin hieu (chi qua khu)."""
    von = [(pd.Timestamp(g.exit_time), g.equity_after) for g in giao_dich_tham_chieu]
    von.sort()
    eq = pd.Series({ts: v for ts, v in von})
    ra = []
    for ts in pd.to_datetime(diem_tin_hieu, utc=True):
        qua_khu = eq.loc[:ts - pd.Timedelta(microseconds=1)] if len(eq) else pd.Series(dtype=float)
        if len(qua_khu) == 0:
            ra.append(1.0)
            continue
        duong = pd.concat([pd.Series({pd.Timestamp.min.tz_localize("UTC"): 100.0}), qua_khu]).sort_index()
        dinh = float(duong.cummax().iloc[-1])
        muc = float(duong.iloc[-1])
        ra.append(DD_GUARD_LEV if muc / dinh < 1.0 - DD_TRIGGER else 1.0)
    return np.array(ra, dtype=float)


def chay_nhanh(nen, tin_hieu, von, von_fee, thuc_thi, nghiem, nam, thu_muc):
    kich_ban = {}
    thuong, gd = run_backtest(nen, tin_hieu, 100, von, thuc_thi)
    phi, gd_phi = run_backtest(nen, tin_hieu, 100, von_fee, thuc_thi)
    cang, gd_cang, chan_doan = run_stress(nen, tin_hieu, 100, von, thuc_thi, nghiem)
    for nhan, ket_qua, ds in (("normal", thuong, gd), ("fee_stress", phi, gd_phi),
                              ("execution_stress", cang, gd_cang)):
        ty_le = ket_qua.final_equity / 100
        kich_ban[nhan] = {**asdict(ket_qua),
                          "annual_geometric_net": ty_le ** (1 / nam) - 1,
                          "monthly_geometric_net": ty_le ** (1 / (12 * nam)) - 1}
        hang = [asdict(g) for g in ds]
        pd.DataFrame(hang).to_csv(thu_muc / f"{nhan}_trades.csv", index=False)
    kich_ban["execution_stress"]["diagnostics"] = chan_doan
    return kich_ban


def co_gate(kich_ban, gate):
    co = {}
    for s in ("normal", "fee_stress", "execution_stress"):
        m = kich_ban[s]
        co[s] = {"monthly_pass": bool(m["monthly_geometric_net"] >= gate["monthly_min"]),
                 "dd_pass": bool(abs(m["max_drawdown"]) <= gate["dd_max"]),
                 "fills_pass": bool(m["trades"] >= gate["fills_min"])}
        co[s]["scenario_pass"] = all(co[s].values())
    co["overall_pass"] = all(co[s]["scenario_pass"] for s in
                             ("normal", "fee_stress", "execution_stress"))
    return co


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--config", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    if a.output.exists():
        raise FileExistsError("Chon output moi; khong ghi de bang chung lich su")
    cfg = json.loads(a.config.read_text())
    # Kiem tra ma tran co dinh (config viet TRUOC khi chay).
    assert list(cfg["branches"]) == ["control_1x", "control_dd_guard", "band1_1x", "band1_dd_guard",
                                     "band2_1x", "band2_dd_guard", "dirconf_1x", "dirconf_dd_guard"], \
        "ma tran phai la 4 loc x 2 sizing = 8 nhanh co dinh"
    assert cfg["ban_b1_trung_tinh"]["fund_7d_min"] == -5e-05
    assert cfg["ban_b1_trung_tinh"]["fund_7d_max"] == 0.0001
    assert cfg["ban_b2_am"]["fund_7d_min"] == 5e-05
    assert cfg["control_reference"] == XUAT_BAN
    goc = Path(__file__).resolve().parents[1]
    nen = pd.read_parquet(goc / cfg["candles"])
    goc_tin_hieu = pd.read_parquet(goc / cfg["base_majority"])
    quyet_dinh = pd.read_parquet(goc / "data/processed/swing_regime_research_v4/decisions.parquet")
    tho_btc = pd.read_parquet(goc / cfg["du_lieu_funding"]["file_btc"])
    assert cfg["du_lieu_funding"]["symbol_dung_cho_probe"] == "BTCUSDT"
    ds_cfg = json.loads((goc / cfg["dataset_config"]).read_text())
    me = json.loads((goc / cfg["parent_plan"]).read_text())

    feat = tinh_feature_funding(tho_btc)
    # Bao phu causal tren toan decision clock (5628 quyet dinh).
    idx_d = asof_join(quyet_dinh["signal_time"], feat)
    bao_phu = {"so_quyet_dinh": int(len(quyet_dinh)),
               "idx_asof_min": int(idx_d.min()),
               "du_lich_su_30d": bool((idx_d >= 89).all()),
               "nhan_qua": bool((pd.to_datetime(feat.iloc[idx_d]["funding_time"], utc=True).to_numpy()
                                 < pd.to_datetime(quyet_dinh["signal_time"], utc=True).to_numpy()).all())}

    tin_hieu = gan_feature(goc_tin_hieu, feat)
    assert len(tin_hieu) == 94, f"tin hieu majority dong bang phai la 94, got {len(tin_hieu)}"

    von = CostModel(**ds_cfg["costs"])
    von_fee = CostModel(**{**asdict(von), "fee_rate_per_fill": cfg["fee_stress_rate"]})
    nghiem = FillStress(cfg["stress"]["entry_penetration_bps"],
                        cfg["stress"]["target_penetration_bps"],
                        cfg["stress"]["market_exit_slippage_bps"],
                        cfg["stress"]["market_exit_fee_rate"],
                        cfg["stress"]["allow_limit_price_improvement"])
    thuc_thi_1x = ExecutionConfig(entry_expiry_bars=ds_cfg["entry_expiry_bars"],
                                  max_holding_bars=max(ds_cfg["holding_days"]) * 288,
                                  leverage=1.0, max_leverage=1.0)
    thuc_thi_size = ExecutionConfig(entry_expiry_bars=ds_cfg["entry_expiry_bars"],
                                    max_holding_bars=max(ds_cfg["holding_days"]) * 288,
                                    leverage=LEV_MIN, max_leverage=LEV_MAX)
    nam = ((pd.Timestamp(me["complete_evaluation_until"]) - pd.Timestamp(me["folds"][0][0]))
           .total_seconds() / (365.2425 * 86400))

    a.output.mkdir(parents=True)
    (a.output / "config.json").write_text(json.dumps(cfg, indent=2, ensure_ascii=False))
    (a.output / "driver_source.py").write_text(Path(__file__).read_text())
    # Luu feature funding cho toan decision clock (nhan qua, tai su dung lai).
    lay_d = feat.iloc[idx_d].reset_index(drop=True)
    bang_clock = pd.DataFrame({
        "bar_index": quyet_dinh["bar_index"].to_numpy(),
        "signal_time": pd.to_datetime(quyet_dinh["signal_time"], utc=True).astype(str),
        "funding_time_dung": pd.to_datetime(lay_d["funding_time"], utc=True).astype(str),
        "fund_rate": lay_d["fundingRate"].to_numpy(dtype=float),
        "fund_7d": lay_d["fund_7d"].to_numpy(dtype=float),
        "fund_30d": lay_d["fund_30d"].to_numpy(dtype=float),
        "fund_slope_7d": lay_d["fund_slope_7d"].to_numpy(dtype=float),
        "fund_z30": lay_d["fund_z30"].to_numpy(dtype=float),
    })
    bang_clock.to_parquet(a.output / "decisions_funding_features.parquet", index=False)

    ket_qua = {}
    # --- Control 1x truoc (cong tai hien) ---
    thu_muc_c = a.output / "control_1x"
    thu_muc_c.mkdir()
    goc_c = loc_theo_nhanh(tin_hieu, "control", cfg)
    if "leverage" in goc_c.columns:
        goc_c = goc_c.drop(columns=["leverage"])
    goc_c.to_parquet(thu_muc_c / "signals.parquet", index=False)
    kb_c = chay_nhanh(nen, goc_c, von, von_fee, thuc_thi_1x, nghiem, nam, thu_muc_c)
    n = kb_c["normal"]
    dat = (abs(n["total_return"] - XUAT_BAN["total_return"]) < 1e-6
           and abs(n["max_drawdown"] - XUAT_BAN["max_drawdown"]) < 1e-6
           and n["trades"] == XUAT_BAN["trades"])
    print(json.dumps({"nhanh": "control_1x", "n_signals": len(goc_c),
                      "normal": {k: n[k] for k in ("total_return", "max_drawdown", "trades",
                                                   "monthly_geometric_net")},
                      "kiem_tra_control": "DAT" if dat else "KHONG DAT",
                      "xuat_ban": XUAT_BAN}), flush=True)
    if not dat:
        (a.output / "CONTROL_MISMATCH.json").write_text(json.dumps(
            {"xuat_ban": XUAT_BAN,
             "tai_hien": {k: n[k] for k in ("total_return", "max_drawdown", "trades")}}, indent=2))
        raise SystemExit(f"CONTROL KHONG KHOP: {n['total_return']=} {n['max_drawdown']=} "
                         f"{n['trades']=}; STOP")
    ket_qua["control_1x"] = {"scenarios": kb_c, "n_signals": len(goc_c),
                             "loc": "control", "sizing": "1x"}

    # Tham chieu guard = giao dich control cua chinh nhanh nay (khong refit).
    _, gd_control = run_backtest(nen, goc_c, 100, von, thuc_thi_1x)
    bo_dem = {}

    def guard_cho(kh):
        khoa = tuple(pd.to_datetime(kh["signal_time"], utc=True).astype("int64"))
        if khoa not in bo_dem:
            bo_dem[khoa] = muc_dd_guard_tai(pd.to_datetime(kh["signal_time"], utc=True), gd_control)
        return bo_dem[khoa]

    ke_hoach = [("control_dd_guard", "control", "dd_guard"),
                ("band1_1x", "band1", "1x"), ("band1_dd_guard", "band1", "dd_guard"),
                ("band2_1x", "band2", "1x"), ("band2_dd_guard", "band2", "dd_guard"),
                ("dirconf_1x", "dirconf", "1x"), ("dirconf_dd_guard", "dirconf", "dd_guard")]
    for nhanh, loc, sizing in ke_hoach:
        thu_muc = a.output / nhanh
        thu_muc.mkdir()
        co_ban = loc_theo_nhanh(tin_hieu, loc, cfg)
        if sizing == "1x":
            kh = co_ban.drop(columns=["leverage"]) if "leverage" in co_ban.columns else co_ban.copy()
            th = thuc_thi_1x
        else:
            kh = co_ban.copy()
            kh["leverage"] = guard_cho(co_ban)
            th = thuc_thi_size
        kh.to_parquet(thu_muc / "signals.parquet", index=False)
        kb = chay_nhanh(nen, kh, von, von_fee, th, nghiem, nam, thu_muc)
        ket_qua[nhanh] = {"scenarios": kb, "n_signals": len(kh), "loc": loc, "sizing": sizing}
        print(json.dumps({"nhanh": nhanh, "n_signals": len(kh),
                          "chi_tiet": {s: {kk: kb[s][kk] for kk in
                                           ["total_return", "max_drawdown", "trades",
                                            "monthly_geometric_net", "gross_pnl", "fees",
                                            "funding", "profit_factor", "win_rate",
                                            "long_trades", "short_trades"]}
                                      for s in ("normal", "fee_stress", "execution_stress")},
                          "gate": co_gate(kb, cfg["gate"])["overall_pass"]}), flush=True)

    danh_dau = {b: {"gate": co_gate(v["scenarios"], cfg["gate"]),
                    "n_signals": v["n_signals"], "loc": v["loc"],
                    "sizing": v["sizing"], "scenarios": v["scenarios"]}
                for b, v in ket_qua.items()}
    bao_cao = {"branches": danh_dau, "config": cfg,
               "kiem_tra_control": {"xuat_ban": XUAT_BAN,
                                    "tai_hien": {k: n[k] for k in
                                                 ("total_return", "max_drawdown", "trades",
                                                  "monthly_geometric_net")},
                                    "khop": True},
               "bao_phu_funding": bao_phu,
               "phan_phoi_funding_btc": {
                   "so_ky": int(len(feat)),
                   "tu": str(feat["funding_time"].iloc[0]),
                   "den": str(feat["funding_time"].iloc[-1]),
                   "trung_vi_fund_rate": float(feat["fundingRate"].median()),
                   "trung_vi_fund_7d": float(feat["fund_7d"].median()),
                   "ty_le_fund_rate_am": float((feat["fundingRate"] <= 0).mean()),
                   "ty_le_fund_7d_am": float((feat["fund_7d"] < 0).mean())},
               "cong_thuc": {"dac_trung": cfg["dinh_nghia_feature"],
                             "band1": cfg["ban_b1_trung_tinh"], "band2": cfg["ban_b2_am"],
                             "dirconf": cfg["loc_dirconf_xac_nhan_huong"],
                             "dd_trigger": DD_TRIGGER, "dd_guard_lev": DD_GUARD_LEV,
                             "dd_guard_tham_chieu": cfg["sizing"]["dd_guard"],
                             "lev_min": LEV_MIN, "lev_max": LEV_MAX,
                             "fee_stress": "fee_rate_per_fill=0.00055",
                             "execution_stress": "FillStress(5,5,5,0.00055,False), exposure<=1x",
                             "monthly_geometric_net": "ty_le=final/100; monthly=ty_le^(1/(12*nam))-1"},
               "duration_years": nam, "independent_test": False, "live_approved": False,
               "exploratory": True,
               "canh_bao": ("CHI EXPLORATORY: khoang phat trien 2023-2026 da mo (den "
                            + me["complete_evaluation_until"] + "). Loc funding la quy tac dong bang "
                            "theo nhanh (khong fit, khong thich ung). Tin hieu/diem khong refit. "
                            "Khong de xuat nhanh nao, khong tuyen bo kiem dinh. "
                            "Drawdown lay mau theo gia dong nen trade, khong phai drawdown "
                            "mark-price/intrabar thuc. Exit stop/timeout dang market-like theo fee "
                            "kich ban, khong phai fill maker/limit dam bao. Khong suy doan xac suat "
                            "fill maker hay vi tri hang doi tu OHLC."),
               "input_sha256": {str(q): sha256(goc / q) for q in
                                (cfg["candles"], cfg["base_majority"], cfg["dataset_config"],
                                 cfg["parent_plan"], cfg["du_lieu_funding"]["file_btc"],
                                 cfg["du_lieu_funding"]["manifest"],
                                 "configs/opencode_v23_fundingfeat.json")},
               "gate": {"monthly_min": cfg["gate"]["monthly_min"],
                        "dd_max": cfg["gate"]["dd_max"], "fills_min": cfg["gate"]["fills_min"]}}
    (a.output / "summary.json").write_text(json.dumps(bao_cao, indent=2, ensure_ascii=False, default=str))
    print("DA GHI", str(a.output / "summary.json"))
