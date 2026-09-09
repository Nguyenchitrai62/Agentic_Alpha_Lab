"""Opencode v65 (R21-E-band1conf): funding neutral-band1 x confirmed x sizing.

Micro-combo chua test (mission E-EXPLOIT worker):
- D1 leg: band1 TRUNG TINH (fund_7d trong [-5e-05, +1e-04]) — giu 82/94 tin hieu
  majority, monthly pha loang 2.42% tren majority. NGUYEN VAN dinh nghia tu
  configs/opencode_v23_fundingfeat.json:ban_b1_trung_tinh; KHONG tinh lai funding.
- B4 leg: tin hieu confirmed dong bang (map-ensemble iso4 xac nhan boi isoall)
  artifacts/research/opencode_v15_mapensemble/confirmed_1x/signals.parquet (94).

Tai su dung verbatim: join fund_7d tu D1 artifact
  artifacts/research/opencode_v23_fundingfeat/decisions_funding_features.parquet
  qua bar_index (kiem tra cheo signal_time), loc band1 hai phia.
  Khong doc funding raw, khong rolling, khong refit.

Ma tran co dinh trong configs/opencode_v65_band1conf.json TRUOC khi chay:
  loc {control, band1} x sizing {1x, dd_guard} = 4 nhanh.
dd_guard: lev = 0.5 khi equity mau cua confirmed_control_1x CUA CHINH
  EXPERIMENT NAY dang >10% duoi dinh truoc do (qua khu, cat 1-microsecond,
  moc 100.0), nguoc lai 1.0; ap dung tai thoi diem tin hieu DA LOC cua tung
  nhanh. Quy uoc v11/v13/v18/v23, da disclose trong config.
Cong control: confirmed_control_1x normal phai khop confirmed_1x da xuat ban
  (total_return 1.5785811193475512 / max_drawdown -0.16094964732093653 /
  trades 60, sai so < 1e-6) neu khong thi STOP.
Moi nhanh x 3 kich ban: normal / fee_stress (fee 0.00055) / execution_stress
  FillStress(5,5,5,0.00055,False), exposure<=1x. Monthly geometric theo duration
  cua configs/swing_v15_continuous_folds.json.
Nhan exploratory: khoang 2023-2026 da mo, khong phai kiem dinh doc lap.
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

# Tham chieu control da xuat ban (confirmed_1x, v15/B4).
XUAT_BAN = {"total_return": 1.5785811193475512,
            "max_drawdown": -0.16094964732093653, "trades": 60}


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
    assert list(cfg["branches"]) == ["confirmed_control_1x", "confirmed_control_dd_guard",
                                     "confirmed_band1_1x", "confirmed_band1_dd_guard"], \
        "ma tran phai la 2 loc x 2 sizing = 4 nhanh co dinh"
    assert list(cfg["sizings"]) == ["1x", "dd_guard"]
    assert cfg["band1"]["fund_7d_min"] == -5e-05, "band1 phai tai su dung NGUYEN VAN tu D1"
    assert cfg["band1"]["fund_7d_max"] == 0.0001, "band1 phai tai su dung NGUYEN VAN tu D1"
    assert cfg["control_reference"] == XUAT_BAN
    goc = Path(__file__).resolve().parents[1]
    nen = pd.read_parquet(goc / cfg["candles"])
    goc_tin_hieu = pd.read_parquet(goc / cfg["bases"]["confirmed"])
    bang_funding = pd.read_parquet(goc / cfg["funding_features"])
    ds_cfg = json.loads((goc / cfg["dataset_config"]).read_text())
    me = json.loads((goc / cfg["parent_plan"]).read_text())
    assert len(goc_tin_hieu) == 94, f"tin hieu confirmed dong bang phai la 94, got {len(goc_tin_hieu)}"

    # --- Tai su dung D1 verbatim: join fund_7d qua bar_index, KHONG tinh lai ---
    assert "fund_7d" in bang_funding.columns and "bar_index" in bang_funding.columns
    anh_xa = bang_funding.set_index("bar_index")["fund_7d"]
    tin_hieu = goc_tin_hieu.copy().reset_index(drop=True)
    tin_hieu["fund_7d"] = tin_hieu["bar_index"].map(anh_xa)
    assert int(tin_hieu["fund_7d"].isna().sum()) == 0, "join funding thieu (phai 94/94)"
    # Kiem tra cheo nhan qua qua signal_time: moi tin hieu phai co trong clock D1.
    clock_st = set(pd.to_datetime(bang_funding["signal_time"], utc=True).astype(str))
    sig_st = pd.to_datetime(tin_hieu["signal_time"], utc=True).astype(str)
    assert bool(sig_st.isin(clock_st).all()), "signal_time lech khoi clock D1"
    fmin = float(cfg["band1"]["fund_7d_min"])
    fmax = float(cfg["band1"]["fund_7d_max"])
    loc_band1 = tin_hieu[(tin_hieu["fund_7d"] >= fmin) & (tin_hieu["fund_7d"] <= fmax)].copy().reset_index(drop=True)
    loc_control = tin_hieu.copy().reset_index(drop=True)
    giu = {"control": len(loc_control), "band1": len(loc_band1)}
    print(json.dumps({"loc_kept": giu,
                      "band1_long": int((loc_band1["direction"] == 1).sum()),
                      "band1_short": int((loc_band1["direction"] == -1).sum())}), flush=True)

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

    ket_qua = {}
    # --- Control 1x truoc (cong tai hien) ---
    thu_muc_c = a.output / "confirmed_control_1x"
    thu_muc_c.mkdir()
    goc_c = loc_control.drop(columns=["leverage", "fund_7d"],
                             errors="ignore")
    goc_c.to_parquet(thu_muc_c / "signals.parquet", index=False)
    kb_c = chay_nhanh(nen, goc_c, von, von_fee, thuc_thi_1x, nghiem, nam, thu_muc_c)
    n = kb_c["normal"]
    dat = (abs(n["total_return"] - XUAT_BAN["total_return"]) < 1e-6
           and abs(n["max_drawdown"] - XUAT_BAN["max_drawdown"]) < 1e-6
           and n["trades"] == XUAT_BAN["trades"])
    print(json.dumps({"nhanh": "confirmed_control_1x", "n_signals": len(goc_c),
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
    ket_qua["confirmed_control_1x"] = {"scenarios": kb_c, "n_signals": len(goc_c),
                                      "loc": "control", "sizing": "1x",
                                      "n_kept": giu["control"]}

    # Tham chieu guard = giao dich control cua chinh experiment nay (khong refit).
    _, gd_control = run_backtest(nen, goc_c, 100, von, thuc_thi_1x)
    bo_dem = {}

    def guard_cho(kh):
        khoa = tuple(pd.to_datetime(kh["signal_time"], utc=True).astype("int64"))
        if khoa not in bo_dem:
            bo_dem[khoa] = muc_dd_guard_tai(pd.to_datetime(kh["signal_time"], utc=True), gd_control)
        return bo_dem[khoa]

    ke_hoach = [("confirmed_control_dd_guard", "control", "dd_guard"),
                ("confirmed_band1_1x", "band1", "1x"),
                ("confirmed_band1_dd_guard", "band1", "dd_guard")]
    nguon_loc = {"control": loc_control, "band1": loc_band1}
    for nhanh, loc, sizing in ke_hoach:
        thu_muc = a.output / nhanh
        thu_muc.mkdir()
        co_ban = nguon_loc[loc]
        if sizing == "1x":
            kh = co_ban.drop(columns=["leverage", "fund_7d"], errors="ignore")
            th = thuc_thi_1x
        else:
            kh = co_ban.drop(columns=["leverage", "fund_7d"], errors="ignore").copy()
            kh["leverage"] = guard_cho(co_ban)
            th = thuc_thi_size
        kh.to_parquet(thu_muc / "signals.parquet", index=False)
        kb = chay_nhanh(nen, kh, von, von_fee, th, nghiem, nam, thu_muc)
        ket_qua[nhanh] = {"scenarios": kb, "n_signals": len(kh), "loc": loc,
                          "sizing": sizing, "n_kept": giu[loc]}
        print(json.dumps({"nhanh": nhanh, "n_signals": len(kh),
                          "chi_tiet": {s: {kk: kb[s][kk] for kk in
                                           ["total_return", "max_drawdown", "trades",
                                            "monthly_geometric_net", "gross_pnl", "fees",
                                            "funding", "profit_factor", "win_rate",
                                            "long_trades", "short_trades"]}
                                      for s in ("normal", "fee_stress", "execution_stress")},
                          "gate": co_gate(kb, cfg["gate"])["overall_pass"]}), flush=True)

    danh_dau = {b: {"gate": co_gate(v["scenarios"], cfg["gate"]),
                    "n_signals": v["n_signals"], "n_kept": v["n_kept"],
                    "loc": v["loc"], "sizing": v["sizing"],
                    "scenarios": v["scenarios"]}
                for b, v in ket_qua.items()}
    bao_cao = {"branches": danh_dau, "config": cfg,
               "kiem_tra_control": {"xuat_ban": XUAT_BAN,
                                    "tai_hien": {k: n[k] for k in
                                                 ("total_return", "max_drawdown", "trades",
                                                  "monthly_geometric_net")},
                                    "khop": True},
               "loc_kept": giu,
               "band1_chi_tiet": {"nguong_fund_7d_min": fmin,
                                  "nguong_fund_7d_max": fmax,
                                  "nguon": "configs/opencode_v23_fundingfeat.json:ban_b1_trung_tinh (verbatim, khong tinh lai)",
                                  "d1_majority_tham_chieu": "D1 band1 giu 82/94 majority, pha loang monthly ve 2.42% tren majority",
                                  "band1_long": int((loc_band1["direction"] == 1).sum()),
                                  "band1_short": int((loc_band1["direction"] == -1).sum())},
               "cong_thuc": {"join": cfg["join"], "band1": cfg["band1"],
                             "dd_trigger": DD_TRIGGER, "dd_guard_lev": DD_GUARD_LEV,
                             "dd_guard_tham_chieu": cfg["dd_guard_reference"],
                             "lev_min": LEV_MIN, "lev_max": LEV_MAX,
                             "fee_stress": "fee_rate_per_fill=0.00055",
                             "execution_stress": "FillStress(5,5,5,0.00055,False), exposure<=1x",
                             "monthly_geometric_net": "ty_le=final/100; monthly=ty_le^(1/(12*nam))-1"},
               "duration_years": nam, "independent_test": False, "live_approved": False,
               "exploratory": True,
               "canh_bao": ("CHI EXPLORATORY: khoang phat trien 2023-2026 da mo (den "
                            + me["complete_evaluation_until"] + "). Loc band1 la quy tac dong bang "
                            "theo nhanh (khong fit, khong thich ung, khong tinh lai funding). "
                            "Tin hieu/diem khong refit. Khong de xuat nhanh nao, khong tuyen bo "
                            "kiem dinh. Drawdown lay mau theo gia dong nen trade, khong phai "
                            "drawdown mark-price/intrabar thuc. Exit stop/timeout dang market-like "
                            "theo fee kich ban, khong phai fill maker/limit dam bao. Khong suy doan "
                            "xac suat fill maker hay vi tri hang doi tu OHLC."),
               "input_sha256": {str(q): sha256(goc / q) for q in
                                (cfg["candles"], cfg["bases"]["confirmed"],
                                 cfg["dataset_config"], cfg["parent_plan"],
                                 cfg["funding_features"],
                                 "configs/opencode_v23_fundingfeat.json",
                                 "configs/opencode_v65_band1conf.json")},
               "gate": {"monthly_min": cfg["gate"]["monthly_min"],
                        "dd_max": cfg["gate"]["dd_max"], "fills_min": cfg["gate"]["fills_min"]}}
    (a.output / "summary.json").write_text(json.dumps(bao_cao, indent=2, ensure_ascii=False, default=str))
    print("DA GHI", str(a.output / "summary.json"))
