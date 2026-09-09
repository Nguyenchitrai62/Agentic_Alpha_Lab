"""Opencode v50 (R15-E-band2tp075): funding-band2 x confirmed x tp075 exit x sizing.

Combo hai chan dep nhat (mission E-EXPLOIT):
- N-band2conf leg: band2 (fund_7d >= +5e-05) tren confirmed dong bang — PF 6.6-7.2,
  WR 80%, DD<8%, nhung monthly ~2.45% + exec fills 28. NGUYEN VAN dinh nghia tu
  configs/opencode_v23_fundingfeat.json:ban_b2_am; phuong phap verbatim tu
  artifacts/research/opencode_v49_band2conf/ (join qua bar_index, cross-check
  signal_time). KHONG tinh lai funding.
- N3 leg: tp075 exit fraction (share of notional closed at TP1, remainder to
  TP2/timeout) robust o stress. tp1_fraction la hang so ExecutionConfig dong bang
  theo nhanh (0<f<1, causal, biet tai signal_time; assert tai runtime).

Ma tran co dinh trong configs/opencode_v50_band2tp075.json TRUOC khi chay:
  band2 x tp1 {tp050=0.5 control, tp075=0.75} x sizing {1x, dd_guard} = 4 nhanh.
  Tat ca 4 nhanh tren CUNG tap 50 tin hieu band2 (94 confirmed -> band2 filter).
dd_guard: lev = 0.5 khi equity mau cua confirmed_band2_tp050_1x CONTROL CUA CHINH
  EXPERIMENT NAY dang >10% duoi dinh truoc do (qua khu, cat 1-microsecond,
  moc 100.0), nguoc lai 1.0; ap dung tai thoi diem tin hieu DA LOC band2 cua tung
  nhanh (via cot leverage, geometry giu nguyen). Quy uoc v11/v13/v18/v23.
  DISCLOSE: v49 dung control KHONG LOC lam tham chieu guard; v50 dung control DA
  LOC band2_tp050_1x vi tat ca nhanh deu tren tap band2 (cross-book se nhiem).
Cong control: confirmed_band2_tp050_1x normal phai khop N-band2conf band2_1x da
  xuat ban (total_return 1.2714637662525927 / max_drawdown -0.07248384849096634 /
  trades 30, sai so < 1e-6) neu khong thi STOP.
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

# Tham chieu control da xuat ban (v49 confirmed_band2_1x normal, tp1=0.5 mac dinh).
XUAT_BAN = {"total_return": 1.2714637662525927,
            "max_drawdown": -0.07248384849096634, "trades": 30}


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
    assert list(cfg["branches"]) == ["confirmed_band2_tp050_1x", "confirmed_band2_tp050_dd_guard",
                                     "confirmed_band2_tp075_1x", "confirmed_band2_tp075_dd_guard"], \
        "ma tran phai la band2 x tp1 x sizing = 4 nhanh co dinh"
    assert list(cfg["sizings"]) == ["1x", "dd_guard"]
    assert list(cfg["tp1_fractions"].keys()) == ["tp050", "tp075"]
    assert cfg["tp1_fractions"]["tp050"] == 0.5 and cfg["tp1_fractions"]["tp075"] == 0.75
    assert cfg["band2"]["fund_7d_min"] == 5e-05, "band2 phai tai su dung NGUYEN VAN tu D1"
    assert "fund_7d_max" not in cfg["band2"], "band2 mo (khong chan tren) theo D1"
    assert cfg["control_reference"] == XUAT_BAN
    goc = Path(__file__).resolve().parents[1]

    # VERIFY runtime: stress path honors tp1_fraction (N3 precedent, re-assert).
    stress_src = (goc / "src/agentic_alpha_lab/backtest/execution_stress.py").read_text()
    assert "execution.tp1_fraction" in stress_src, "stress path khong tham chieu tp1_fraction"
    assert "0 < execution.tp1_fraction < 1" in stress_src, "stress path thieu validation tp1"

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
    nguong = float(cfg["band2"]["fund_7d_min"])
    loc_band2 = tin_hieu[tin_hieu["fund_7d"] >= nguong].copy().reset_index(drop=True)
    giu = {"band2": len(loc_band2)}
    print(json.dumps({"loc_kept": giu,
                      "band2_long": int((loc_band2["direction"] == 1).sum()),
                      "band2_short": int((loc_band2["direction"] == -1).sum())}), flush=True)

    von = CostModel(**ds_cfg["costs"])
    von_fee = CostModel(**{**asdict(von), "fee_rate_per_fill": cfg["fee_stress_rate"]})
    nghiem = FillStress(cfg["stress"]["entry_penetration_bps"],
                        cfg["stress"]["target_penetration_bps"],
                        cfg["stress"]["market_exit_slippage_bps"],
                        cfg["stress"]["market_exit_fee_rate"],
                        cfg["stress"]["allow_limit_price_improvement"])

    def thuc_thi_cho(tp1, sizing):
        assert 0 < tp1 < 1, f"tp1_fraction phai 0<f<1, got {tp1}"
        if sizing == "1x":
            return ExecutionConfig(entry_expiry_bars=ds_cfg["entry_expiry_bars"],
                                   max_holding_bars=max(ds_cfg["holding_days"]) * 288,
                                   tp1_fraction=tp1, leverage=1.0, max_leverage=1.0)
        return ExecutionConfig(entry_expiry_bars=ds_cfg["entry_expiry_bars"],
                               max_holding_bars=max(ds_cfg["holding_days"]) * 288,
                               tp1_fraction=tp1, leverage=LEV_MIN, max_leverage=LEV_MAX)

    nam = ((pd.Timestamp(me["complete_evaluation_until"]) - pd.Timestamp(me["folds"][0][0]))
           .total_seconds() / (365.2425 * 86400))

    a.output.mkdir(parents=True)
    (a.output / "config.json").write_text(json.dumps(cfg, indent=2, ensure_ascii=False))
    (a.output / "driver_source.py").write_text(Path(__file__).read_text())

    def chuan_bi(khung_band2, tp1, sizing, guard_vec=None):
        # Provenance only: engine doc ExecutionConfig.tp1_fraction, khong doc cot nay.
        kh = khung_band2.drop(columns=["leverage", "fund_7d"], errors="ignore").copy()
        kh["tp1_fraction"] = tp1
        if sizing == "dd_guard":
            assert guard_vec is not None
            kh["leverage"] = guard_vec
        return kh.reset_index(drop=True)

    ket_qua = {}
    # --- Control band2_tp050_1x truoc (cong tai hien) ---
    tp_c = float(cfg["tp1_fractions"]["tp050"])
    thu_muc_c = a.output / "confirmed_band2_tp050_1x"
    thu_muc_c.mkdir()
    goc_c = chuan_bi(loc_band2, tp_c, "1x")
    goc_c.to_parquet(thu_muc_c / "signals.parquet", index=False)
    kb_c = chay_nhanh(nen, goc_c, von, von_fee, thuc_thi_cho(tp_c, "1x"), nghiem, nam, thu_muc_c)
    n = kb_c["normal"]
    dat = (abs(n["total_return"] - XUAT_BAN["total_return"]) < 1e-6
           and abs(n["max_drawdown"] - XUAT_BAN["max_drawdown"]) < 1e-6
           and n["trades"] == XUAT_BAN["trades"])
    print(json.dumps({"nhanh": "confirmed_band2_tp050_1x", "n_signals": len(goc_c),
                      "normal": {k: n[k] for k in ("total_return", "max_drawdown", "trades",
                                                   "monthly_geometric_net")},
                      "kiem_tra_control": "DAT" if dat else "KHONG DAT",
                      "xuat_ban": XUAT_BAN,
                      "stress_tp1_verified": True}), flush=True)
    if not dat:
        (a.output / "CONTROL_MISMATCH.json").write_text(json.dumps(
            {"xuat_ban": XUAT_BAN,
             "tai_hien": {k: n[k] for k in ("total_return", "max_drawdown", "trades")}}, indent=2))
        raise SystemExit(f"CONTROL KHONG KHOP: {n['total_return']=} {n['max_drawdown']=} "
                         f"{n['trades']=}; STOP")
    ket_qua["confirmed_band2_tp050_1x"] = {"scenarios": kb_c, "n_signals": len(goc_c),
                                          "loc": "band2", "tp1_fraction": tp_c,
                                          "sizing": "1x", "n_kept": giu["band2"]}

    # Tham chieu guard = giao dich control band2_tp050_1x cua chinh experiment nay.
    _, gd_control = run_backtest(nen, goc_c, 100, von, thuc_thi_cho(tp_c, "1x"))
    bo_dem = {}

    def guard_cho(kh):
        khoa = tuple(pd.to_datetime(kh["signal_time"], utc=True).astype("int64"))
        if khoa not in bo_dem:
            bo_dem[khoa] = muc_dd_guard_tai(pd.to_datetime(kh["signal_time"], utc=True), gd_control)
        return bo_dem[khoa]

    ke_hoach = [("confirmed_band2_tp050_dd_guard", "tp050", "dd_guard"),
                ("confirmed_band2_tp075_1x", "tp075", "1x"),
                ("confirmed_band2_tp075_dd_guard", "tp075", "dd_guard")]
    for nhanh, tp_key, sizing in ke_hoach:
        thu_muc = a.output / nhanh
        thu_muc.mkdir()
        tp1 = float(cfg["tp1_fractions"][tp_key])
        if sizing == "1x":
            kh = chuan_bi(loc_band2, tp1, "1x")
            th = thuc_thi_cho(tp1, "1x")
        else:
            tham_chieu = chuan_bi(loc_band2, tp1, "1x")
            kh = chuan_bi(loc_band2, tp1, "dd_guard", guard_cho(tham_chieu))
            th = thuc_thi_cho(tp1, "dd_guard")
        kh.to_parquet(thu_muc / "signals.parquet", index=False)
        kb = chay_nhanh(nen, kh, von, von_fee, th, nghiem, nam, thu_muc)
        ket_qua[nhanh] = {"scenarios": kb, "n_signals": len(kh), "loc": "band2",
                          "tp1_fraction": tp1, "sizing": sizing, "n_kept": giu["band2"]}
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
                    "loc": v["loc"], "tp1_fraction": v["tp1_fraction"],
                    "sizing": v["sizing"],
                    "scenarios": v["scenarios"]}
                for b, v in ket_qua.items()}
    bao_cao = {"branches": danh_dau, "config": cfg,
               "kiem_tra_control": {"xuat_ban": XUAT_BAN,
                                    "tai_hien": {k: n[k] for k in
                                                 ("total_return", "max_drawdown", "trades",
                                                  "monthly_geometric_net")},
                                    "khop": True},
               "stress_tp1_verified": {"honored": True,
                                       "chi_tiet": "run_stress close_fraction(fill, execution.tp1_fraction, ...) + validation 0<tp1<1 (N3 precedent, re-assert tai runtime)"},
               "loc_kept": giu,
               "band2_chi_tiet": {"nguong_fund_7d_min": nguong,
                                  "band2_long": int((loc_band2["direction"] == 1).sum()),
                                  "band2_short": int((loc_band2["direction"] == -1).sum())},
               "cong_thuc": {"join": cfg["join"], "band2": cfg["band2"],
                             "tp1_fractions": cfg["tp1_fractions"],
                             "dd_trigger": DD_TRIGGER, "dd_guard_lev": DD_GUARD_LEV,
                             "dd_guard_tham_chieu": cfg["dd_guard_reference"],
                             "lev_min": LEV_MIN, "lev_max": LEV_MAX,
                             "fee_stress": "fee_rate_per_fill=0.00055",
                             "execution_stress": "FillStress(5,5,5,0.00055,False), exposure<=1x",
                             "monthly_geometric_net": "ty_le=final/100; monthly=ty_le^(1/(12*nam))-1"},
               "duration_years": nam, "independent_test": False, "live_approved": False,
               "exploratory": True,
               "canh_bao": ("CHI EXPLORATORY: khoang phat trien 2023-2026 da mo (den "
                            + me["complete_evaluation_until"] + "). Loc band2 la quy tac dong bang "
                            "theo nhanh (khong fit, khong thich ung, khong tinh lai funding). "
                            "tp1_fraction la hang so dong bang theo nhanh (khong fit). "
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
                                 "configs/opencode_v49_band2conf.json",
                                 "configs/opencode_v50_band2tp075.json")},
               "gate": {"monthly_min": cfg["gate"]["monthly_min"],
                        "dd_max": cfg["gate"]["dd_max"], "fills_min": cfg["gate"]["fills_min"]}}
    (a.output / "summary.json").write_text(json.dumps(bao_cao, indent=2, ensure_ascii=False, default=str))
    print("DA GHI", str(a.output / "summary.json"))
