"""Opencode v70 (R23-M-s0004band2): s0004 session x band2confirmed x sizing.

Micro-combo scope x scope cuoi cung chua test theo ledger (s0004 banked R1-C/E2,
band2confirmed banked R14-N PF 6.6-7.2 / WR 80% / DD<8%, never combined):
- Base dong bang: artifacts/research/opencode_v15_mapensemble/confirmed_1x/signals.parquet (94)
  VERIFY co cot signal_time + direction truoc khi chay, else STOP.
- Loc band2: fund_7d >= +5e-05 via decisions_funding_features.parquet — doc
  configs/opencode_v23_fundingfeat.json cho method exact, reuse verbatim
  (as-of funding_time < signal_time, fund_7d = mean 21 ky truoc, min_periods=21;
  v70 KHONG tinh lai, chi join fund_7d qua bar_index + check cheo signal_time).
  VERIFY files else STOP.
- Loc s0004: signal_time UTC hour 0<=h<4 (R1-C session probe, causal past-only).

Ma tran co dinh trong configs/opencode_v70_s0004band2.json TRUOC khi chay:
  scopes {all-control, s0004_only, band2_only, s0004_AND_band2}
  x sizing {1x, dd_guard} = 8 nhanh.
dd_guard: lev = 0.5 khi equity mau cua confirmed_all_1x CUA CHINH EXPERIMENT
  NAY dang >10% duoi dinh truoc do (qua khu, cat 1-microsecond, moc 100.0),
  nguoc lai 1.0; ap dung tai thoi diem tin hieu DA LOC scope cua tung nhanh.
  Quy uoc v11/v13/v18/v23/v49, disclose trong config.
Cong control: confirmed_all_1x normal phai khop confirmed_1x da xuat ban
  (total_return 1.5785811193475512 / max_drawdown -0.16094964732093653 /
  trades 60, sai so < 1e-6, trades exact) neu khong thi STOP.
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
SESSION_START, SESSION_END = 0, 4

# Tham chieu control da xuat ban (confirmed_1x, v15/B4; v49 tai hien).
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
    assert list(cfg["branches"]) == ["confirmed_all_1x", "confirmed_all_dd_guard",
                                     "confirmed_s0004_1x", "confirmed_s0004_dd_guard",
                                     "confirmed_band2_1x", "confirmed_band2_dd_guard",
                                     "confirmed_s0004_band2_1x",
                                     "confirmed_s0004_band2_dd_guard"], \
        "ma tran phai la 4 scope x 2 sizing = 8 nhanh co dinh"
    assert list(cfg["sizings"]) == ["1x", "dd_guard"]
    assert list(cfg["scopes"].keys()) == ["all", "s0004_only", "band2_only", "s0004_AND_band2"], \
        "scopes phai la all-control / s0004_only / band2_only / s0004_AND_band2"
    assert cfg["scopes"]["s0004_only"]["session_start_utc_hour_inclusive"] == 0
    assert cfg["scopes"]["s0004_only"]["session_end_utc_hour_exclusive"] == 4
    assert cfg["scopes"]["s0004_AND_band2"]["session_start_utc_hour_inclusive"] == 0
    assert cfg["scopes"]["s0004_AND_band2"]["session_end_utc_hour_exclusive"] == 4
    assert cfg["band2"]["fund_7d_min"] == 5e-05, "band2 phai tai su dung NGUYEN VAN tu D1"
    assert "fund_7d_max" not in cfg["band2"], "band2 mo (khong chan tren) theo D1"
    assert cfg["scopes"]["band2_only"]["fund_7d_min"] == 5e-05
    assert cfg["scopes"]["s0004_AND_band2"]["fund_7d_min"] == 5e-05
    assert cfg["control_reference"] == XUAT_BAN
    goc = Path(__file__).resolve().parents[1]
    # VERIFY files else STOP (mission).
    for khoa in ("candles", "dataset_config", "parent_plan", "funding_features"):
        assert (goc / cfg[khoa]).exists(), f"thieu file {khoa}={cfg[khoa]}; STOP"
    assert (goc / cfg["bases"]["confirmed"]).exists(), "thieu base confirmed; STOP"
    assert (goc / "configs/opencode_v23_fundingfeat.json").exists(), "thieu method funding v23; STOP"
    nen = pd.read_parquet(goc / cfg["candles"])
    goc_tin_hieu = pd.read_parquet(goc / cfg["bases"]["confirmed"])
    bang_funding = pd.read_parquet(goc / cfg["funding_features"])
    ds_cfg = json.loads((goc / cfg["dataset_config"]).read_text())
    me = json.loads((goc / cfg["parent_plan"]).read_text())
    # VERIFY signal_time + direction columns (mission).
    assert "signal_time" in goc_tin_hieu.columns and "direction" in goc_tin_hieu.columns, \
        "base confirmed thieu signal_time/direction; STOP"
    assert len(goc_tin_hieu) == 94, f"tin hieu confirmed dong bang phai la 94, got {len(goc_tin_hieu)}"

    # --- Tai su dung D1 verbatim: join fund_7d qua bar_index, KHONG tinh lai ---
    assert "fund_7d" in bang_funding.columns and "bar_index" in bang_funding.columns
    anh_xa = bang_funding.set_index("bar_index")["fund_7d"]
    tin_hieu = goc_tin_hieu.copy().reset_index(drop=True)
    tin_hieu["fund_7d"] = tin_hieu["bar_index"].map(anh_xa)
    assert int(tin_hieu["fund_7d"].isna().sum()) == 0, "join funding thieu (phai 94/94)"
    # Kiem tra cheo nhan qua signal_time: moi tin hieu phai co trong clock D1.
    clock_st = set(pd.to_datetime(bang_funding["signal_time"], utc=True).astype(str))
    sig_st = pd.to_datetime(tin_hieu["signal_time"], utc=True).astype(str)
    assert bool(sig_st.isin(clock_st).all()), "signal_time lech khoi clock D1"
    nguong = float(cfg["band2"]["fund_7d_min"])
    gio = pd.to_datetime(tin_hieu["signal_time"], utc=True).dt.hour.to_numpy()
    mat_s0004 = (gio >= SESSION_START) & (gio < SESSION_END)
    mat_band2 = (tin_hieu["fund_7d"].to_numpy() >= nguong)
    loc_all = tin_hieu.copy().reset_index(drop=True)
    loc_s0004 = tin_hieu[mat_s0004].copy().reset_index(drop=True)
    loc_band2 = tin_hieu[mat_band2].copy().reset_index(drop=True)
    loc_and = tin_hieu[mat_s0004 & mat_band2].copy().reset_index(drop=True)
    giu = {"all": len(loc_all), "s0004_only": len(loc_s0004),
           "band2_only": len(loc_band2), "s0004_AND_band2": len(loc_and)}
    print(json.dumps({"loc_kept": giu,
                      "and_long": int((loc_and["direction"] == 1).sum()),
                      "and_short": int((loc_and["direction"] == -1).sum()),
                      "s0004_long": int((loc_s0004["direction"] == 1).sum()),
                      "s0004_short": int((loc_s0004["direction"] == -1).sum()),
                      "band2_long": int((loc_band2["direction"] == 1).sum()),
                      "band2_short": int((loc_band2["direction"] == -1).sum())}), flush=True)

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
    thu_muc_c = a.output / "confirmed_all_1x"
    thu_muc_c.mkdir()
    goc_c = loc_all.drop(columns=["leverage", "fund_7d"], errors="ignore")
    goc_c.to_parquet(thu_muc_c / "signals.parquet", index=False)
    kb_c = chay_nhanh(nen, goc_c, von, von_fee, thuc_thi_1x, nghiem, nam, thu_muc_c)
    n = kb_c["normal"]
    dat = (abs(n["total_return"] - XUAT_BAN["total_return"]) < 1e-6
           and abs(n["max_drawdown"] - XUAT_BAN["max_drawdown"]) < 1e-6
           and n["trades"] == XUAT_BAN["trades"])
    print(json.dumps({"nhanh": "confirmed_all_1x", "n_signals": len(goc_c),
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
    ket_qua["confirmed_all_1x"] = {"scenarios": kb_c, "n_signals": len(goc_c),
                                  "scope": "all", "sizing": "1x",
                                  "n_kept": giu["all"]}

    # Tham chieu guard = giao dich control cua chinh experiment nay (khong refit).
    _, gd_control = run_backtest(nen, goc_c, 100, von, thuc_thi_1x)
    bo_dem = {}

    def guard_cho(kh):
        khoa = tuple(pd.to_datetime(kh["signal_time"], utc=True).astype("int64"))
        if khoa not in bo_dem:
            bo_dem[khoa] = muc_dd_guard_tai(pd.to_datetime(kh["signal_time"], utc=True), gd_control)
        return bo_dem[khoa]

    ke_hoach = [("confirmed_all_dd_guard", "all", "dd_guard"),
                ("confirmed_s0004_1x", "s0004_only", "1x"),
                ("confirmed_s0004_dd_guard", "s0004_only", "dd_guard"),
                ("confirmed_band2_1x", "band2_only", "1x"),
                ("confirmed_band2_dd_guard", "band2_only", "dd_guard"),
                ("confirmed_s0004_band2_1x", "s0004_AND_band2", "1x"),
                ("confirmed_s0004_band2_dd_guard", "s0004_AND_band2", "dd_guard")]
    nguon_loc = {"all": loc_all, "s0004_only": loc_s0004,
                 "band2_only": loc_band2, "s0004_AND_band2": loc_and}
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
        ket_qua[nhanh] = {"scenarios": kb, "n_signals": len(kh), "scope": loc,
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
                    "scope": v["scope"], "sizing": v["sizing"],
                    "scenarios": v["scenarios"]}
                for b, v in ket_qua.items()}
    bao_cao = {"branches": danh_dau, "config": cfg,
               "kiem_tra_control": {"xuat_ban": XUAT_BAN,
                                    "tai_hien": {k: n[k] for k in
                                                 ("total_return", "max_drawdown", "trades",
                                                  "monthly_geometric_net")},
                                    "khop": True},
               "loc_kept": giu,
               "scope_chi_tiet": {"nguong_fund_7d_min": nguong,
                                  "s0004": "signal_time UTC hour 0<=h<4 (R1-C, causal)",
                                  "band2": "fund_7d>=5e-05 verbatim D1 (mo, khong chan tren)",
                                  "giam_sat_fills": ("v49 band2 tren confirmed exec 28 fills (<30); "
                                                     "AND pre-loop 33 tin hieu — theo doi fills AND"),
                                  "s0004_long": int((loc_s0004["direction"] == 1).sum()),
                                  "s0004_short": int((loc_s0004["direction"] == -1).sum()),
                                  "band2_long": int((loc_band2["direction"] == 1).sum()),
                                  "band2_short": int((loc_band2["direction"] == -1).sum()),
                                  "and_long": int((loc_and["direction"] == 1).sum()),
                                  "and_short": int((loc_and["direction"] == -1).sum())},
               "cong_thuc": {"join": cfg["join"], "band2": cfg["band2"],
                             "funding_method_verbatim": cfg["funding_method_verbatim"],
                             "s0004": cfg["scopes"]["s0004_only"],
                             "dd_trigger": DD_TRIGGER, "dd_guard_lev": DD_GUARD_LEV,
                             "dd_guard_tham_chieu": cfg["dd_guard_reference"],
                             "lev_min": LEV_MIN, "lev_max": LEV_MAX,
                             "fee_stress": "fee_rate_per_fill=0.00055",
                             "execution_stress": "FillStress(5,5,5,0.00055,False), exposure<=1x",
                             "monthly_geometric_net": "ty_le=final/100; monthly=ty_le^(1/(12*nam))-1"},
               "duration_years": nam, "independent_test": False, "live_approved": False,
               "exploratory": True,
               "canh_bao": ("CHI EXPLORATORY: khoang phat trien 2023-2026 da mo (den "
                            + me["complete_evaluation_until"] + "). Loc scope la quy tac dong bang "
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
                                 "configs/opencode_v70_s0004band2.json")},
               "gate": {"monthly_min": cfg["gate"]["monthly_min"],
                        "dd_max": cfg["gate"]["dd_max"], "fills_min": cfg["gate"]["fills_min"]}}
    (a.output / "summary.json").write_text(json.dumps(bao_cao, indent=2, ensure_ascii=False, default=str))
    print("DA GHI", str(a.output / "summary.json"))
