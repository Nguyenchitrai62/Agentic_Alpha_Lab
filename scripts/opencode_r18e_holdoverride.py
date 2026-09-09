"""Opencode v57 (R18-E-holdoverride): holding-override tren PF7 band2confirmed book.

Execution-override ONLY (khong re-selection vi can predictions):
- Base dong bang: artifacts/research/opencode_v49_band2conf/confirmed_band2_1x/signals.parquet
  (mission ghi 30 signals; VERIFY tai runtime — thuc te 50 signals / 30 fills normal).
- Ma tran co dinh trong configs/opencode_v57_holdoverride.json TRUOC khi chay:
    holding {h7 verbatim-control, h3 override 864, h14 override 4032}
    x sizing {1x, dd_guard} = 6 nhanh.
- h7_1x = VERBATIM (giua nguyen holding_bars goc 35x2016+15x864), cap 2016.
  Phai khop confirmed_band2_1x da xuat ban
  (total_return 1.2714637662525927 / max_drawdown -0.07248384849096634 / trades 30,
  sai so < 1e-6) neu khong thi STOP. Ly do: override-cung-2016 cho
  +137.23%/-10.55%/30 (do local), khong phai book PF7 goc.
- h3/h14 = execution-override: holding_bars = constant 864/4032, cap = holding
  (khop R1-A h7 execution-override). h14 cap 4032 vuot dataset max 2016 — bat buoc
  de engine chap nhan (VERIFY 1 <= holding <= max), disclose.
- Giu entry/stop/TP/entry_expiry identical. Khong refit, khong loc them.
- dd_guard: lev 0.5 khi equity mau cua h7_1x CUA CHINH EXPERIMENT NAY dang >10%
  duoi dinh truoc do (qua khu, cat 1-microsecond, moc 100.0), nguoc lai 1.0;
  ap dung tai thoi diem tin hieu cua tung nhanh. Quy uoc v11/v13/v18/v23/v49.
- Moi nhanh x 3 kich ban: normal / fee_stress (fee 0.00055) / execution_stress
  FillStress(5,5,5,0.00055,False), exposure<=1x. Monthly geometric theo duration
  cua configs/swing_v15_continuous_folds.json.
- Nhan exploratory: khoang 2023-2026 da mo, khong phai kiem dinh doc lap.
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

# Tham chieu control da xuat ban (confirmed_band2_1x, v49).
XUAT_BAN = {"total_return": 1.2714637662525927,
            "max_drawdown": -0.07248384849096634, "trades": 30}

HOLD = {"h7": 2016, "h3": 864, "h14": 4032}


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
    assert list(cfg["branches"]) == ["h7_1x", "h7_dd_guard", "h3_1x",
                                     "h3_dd_guard", "h14_1x", "h14_dd_guard"], \
        "ma tran phai la 3 holding x 2 sizing = 6 nhanh co dinh"
    assert list(cfg["sizings"]) == ["1x", "dd_guard"]
    assert cfg["holdings"]["h7"]["bars"] == 2016
    assert cfg["holdings"]["h3"]["bars"] == 864
    assert cfg["holdings"]["h14"]["bars"] == 4032
    assert cfg["control_reference"]["trades"] == XUAT_BAN["trades"]
    assert abs(cfg["control_reference"]["total_return"] - XUAT_BAN["total_return"]) < 1e-12
    assert abs(cfg["control_reference"]["max_drawdown"] - XUAT_BAN["max_drawdown"]) < 1e-12
    goc = Path(__file__).resolve().parents[1]
    base_path = goc / cfg["base_signals"]
    assert base_path.exists(), f"base signals khong ton tai: {base_path}"
    nen = pd.read_parquet(goc / cfg["candles"])
    goc_tin_hieu = pd.read_parquet(base_path)
    ds_cfg = json.loads((goc / cfg["dataset_config"]).read_text())
    me = json.loads((goc / cfg["parent_plan"]).read_text())
    # VERIFY: mission ghi 30 signals; ghi nhan thuc te (khong fail vi mission nham fills/signals).
    print(json.dumps({"base_exists": True, "n_signals_thuc_te": int(len(goc_tin_hieu)),
                      "mission_ghi": 30,
                      "holding_mix": {str(k): int((goc_tin_hieu['holding_bars'] == k).sum())
                                      for k in sorted(goc_tin_hieu['holding_bars'].unique().tolist())}}),
          flush=True)
    # Doc dataset max de VERIFY cap (mission yeu cau).
    ds_max = max(ds_cfg["holding_days"]) * 288
    assert ds_max == cfg["dataset_max_holding_bars"] == 2016, "dataset max phai la 7x288=2016"
    assert ds_cfg["entry_expiry_bars"] == cfg["execution"]["entry_expiry_bars"] == 12

    von = CostModel(**ds_cfg["costs"])
    von_fee = CostModel(**{**asdict(von), "fee_rate_per_fill": cfg["fee_stress_rate"]})
    nghiem = FillStress(cfg["stress"]["entry_penetration_bps"],
                        cfg["stress"]["target_penetration_bps"],
                        cfg["stress"]["market_exit_slippage_bps"],
                        cfg["stress"]["market_exit_fee_rate"],
                        cfg["stress"]["allow_limit_price_improvement"])

    def thuc_thi_cho(holding_bars, sizing):
        # VERIFY engine: 1 <= holding_bars <= max_holding_bars (cap = holding cua nhanh).
        cap = int(holding_bars)
        assert 1 <= holding_bars <= cap
        if sizing == "1x":
            return ExecutionConfig(entry_expiry_bars=ds_cfg["entry_expiry_bars"],
                                   max_holding_bars=cap, leverage=1.0, max_leverage=1.0)
        return ExecutionConfig(entry_expiry_bars=ds_cfg["entry_expiry_bars"],
                               max_holding_bars=cap, leverage=LEV_MIN, max_leverage=LEV_MAX)

    nam = ((pd.Timestamp(me["complete_evaluation_until"]) - pd.Timestamp(me["folds"][0][0]))
           .total_seconds() / (365.2425 * 86400))

    a.output.mkdir(parents=True)
    (a.output / "config.json").write_text(json.dumps(cfg, indent=2, ensure_ascii=False))
    (a.output / "driver_source.py").write_text(Path(__file__).read_text())

    ket_qua = {}
    # --- Control h7_1x VERBATIM truoc (cong tai hien) ---
    thu_muc_c = a.output / "h7_1x"
    thu_muc_c.mkdir()
    goc_c = goc_tin_hieu.copy().reset_index(drop=True)
    # VERIFY cap: moi holding goc <= 2016.
    assert bool((goc_c["holding_bars"] <= 2016).all()), "control verbatim vuot cap 2016"
    th_c = thuc_thi_cho(2016, "1x")
    kb_c = chay_nhanh(nen, goc_c, von, von_fee, th_c, nghiem, nam, thu_muc_c)
    goc_c.to_parquet(thu_muc_c / "signals.parquet", index=False)
    n = kb_c["normal"]
    dat = (abs(n["total_return"] - XUAT_BAN["total_return"]) < 1e-6
           and abs(n["max_drawdown"] - XUAT_BAN["max_drawdown"]) < 1e-6
           and n["trades"] == XUAT_BAN["trades"])
    print(json.dumps({"nhanh": "h7_1x", "n_signals": len(goc_c),
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
    ket_qua["h7_1x"] = {"scenarios": kb_c, "n_signals": len(goc_c),
                        "holding_bars": "verbatim(864/2016)", "sizing": "1x"}

    # Tham chieu guard = giao dich control cua chinh experiment nay (khong refit).
    _, gd_control = run_backtest(nen, goc_c, 100, von, th_c)
    bo_dem = {}

    def guard_cho(kh):
        khoa = tuple(pd.to_datetime(kh["signal_time"], utc=True).astype("int64"))
        if khoa not in bo_dem:
            bo_dem[khoa] = muc_dd_guard_tai(pd.to_datetime(kh["signal_time"], utc=True), gd_control)
        return bo_dem[khoa]

    ke_hoach = [("h7_dd_guard", "h7", "dd_guard"),
                ("h3_1x", "h3", "1x"),
                ("h3_dd_guard", "h3", "dd_guard"),
                ("h14_1x", "h14", "1x"),
                ("h14_dd_guard", "h14", "dd_guard")]
    for nhanh, hold_key, sizing in ke_hoach:
        thu_muc = a.output / nhanh
        thu_muc.mkdir()
        hb = HOLD[hold_key]
        if hold_key == "h7":
            # dd_guard tren nen verbatim (giua holding goc).
            co_ban = goc_tin_hieu.copy().reset_index(drop=True)
            mo_ta = "verbatim(864/2016)"
        else:
            # execution-override: holding_bars = constant, entry/stop/TP identical.
            co_ban = goc_tin_hieu.copy().reset_index(drop=True)
            co_ban["holding_bars"] = int(hb)
            mo_ta = f"override-{hb}"
        assert bool((co_ban["holding_bars"] <= hb).all())
        if sizing == "1x":
            kh = co_ban.drop(columns=["leverage"], errors="ignore")
            th = thuc_thi_cho(hb, "1x")
        else:
            kh = co_ban.drop(columns=["leverage"], errors="ignore").copy()
            kh["leverage"] = guard_cho(co_ban)
            th = thuc_thi_cho(hb, "dd_guard")
        kh.to_parquet(thu_muc / "signals.parquet", index=False)
        kb = chay_nhanh(nen, kh, von, von_fee, th, nghiem, nam, thu_muc)
        ket_qua[nhanh] = {"scenarios": kb, "n_signals": len(kh),
                          "holding_bars": mo_ta, "sizing": sizing}
        print(json.dumps({"nhanh": nhanh, "n_signals": len(kh), "holding": mo_ta,
                          "chi_tiet": {s: {kk: kb[s][kk] for kk in
                                           ["total_return", "max_drawdown", "trades",
                                            "monthly_geometric_net", "gross_pnl", "fees",
                                            "funding", "profit_factor", "win_rate",
                                            "long_trades", "short_trades"]}
                                      for s in ("normal", "fee_stress", "execution_stress")},
                          "gate": co_gate(kb, cfg["gate"])["overall_pass"]}), flush=True)

    danh_dau = {b: {"gate": co_gate(v["scenarios"], cfg["gate"]),
                    "n_signals": v["n_signals"], "holding_bars": v["holding_bars"],
                    "sizing": v["sizing"], "scenarios": v["scenarios"]}
                for b, v in ket_qua.items()}
    bao_cao = {"branches": danh_dau, "config": cfg,
               "kiem_tra_control": {"xuat_ban": XUAT_BAN,
                                    "tai_hien": {k: n[k] for k in
                                                 ("total_return", "max_drawdown", "trades",
                                                  "monthly_geometric_net")},
                                    "khop": True},
               "base_thuc_te": {"n_signals": int(len(goc_tin_hieu)),
                                "holding_mix": {str(k): int((goc_tin_hieu['holding_bars'] == k).sum())
                                                for k in sorted(goc_tin_hieu['holding_bars'].unique().tolist())},
                                "mission_ghi": 30,
                                "ghi_chu": "Mission nham fills(30) thanh signals; file goc 50 signals."},
               "cong_thuc": {"override": "h3/h14: holding_bars=constant causal; h7: verbatim",
                             "dd_trigger": DD_TRIGGER, "dd_guard_lev": DD_GUARD_LEV,
                             "dd_guard_tham_chieu": cfg["dd_guard"]["reference"],
                             "lev_min": LEV_MIN, "lev_max": LEV_MAX,
                             "fee_stress": "fee_rate_per_fill=0.00055",
                             "execution_stress": "FillStress(5,5,5,0.00055,False), exposure<=1x",
                             "monthly_geometric_net": "ty_le=final/100; monthly=ty_le^(1/(12*nam))-1"},
               "duration_years": nam, "independent_test": False, "live_approved": False,
               "exploratory": True,
               "canh_bao": ("CHI EXPLORATORY: khoang phat trien 2023-2026 da mo (den "
                            + me["complete_evaluation_until"] + "). Holding-override la quy tac "
                            "dong bang theo nhanh (khong fit, khong thich ung). "
                            "Tin hieu/diem khong refit. Khong de xuat nhanh nao, khong tuyen bo "
                            "kiem dinh. Drawdown lay mau theo gia dong nen trade, khong phai "
                            "drawdown mark-price/intrabar thuc. Exit stop/timeout dang market-like "
                            "theo fee kich ban, khong phai fill maker/limit dam bao. Khong suy doan "
                            "xac suat fill maker hay vi tri hang doi tu OHLC. "
                            "h14 cap 4032 vuot dataset max 2016 (disclose)."),
               "input_sha256": {str(q): sha256(goc / q) for q in
                                (cfg["candles"], cfg["base_signals"],
                                 cfg["dataset_config"], cfg["parent_plan"],
                                 "configs/opencode_v57_holdoverride.json")},
               "gate": {"monthly_min": cfg["gate"]["monthly_min"],
                        "dd_max": cfg["gate"]["dd_max"], "fills_min": cfg["gate"]["fills_min"]}}
    (a.output / "summary.json").write_text(json.dumps(bao_cao, indent=2, ensure_ascii=False, default=str))
    print("DA GHI", str(a.output / "summary.json"))
