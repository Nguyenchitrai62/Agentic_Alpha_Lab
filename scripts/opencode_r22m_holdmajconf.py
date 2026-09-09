"""Opencode v67 (R22-M-holdmajconf): holding-override tren ensemble bases majority+confirmed.

Execution-override ONLY (khong re-selection vi can predictions):
- Base dong bang: artifacts/research/opencode_v15_mapensemble/majority_1x/signals.parquet (94)
  + confirmed_1x/signals.parquet (94). VERIFY tai runtime (holding_mix).
- Ma tran co dinh trong configs/opencode_v67_holdmajconf.json TRUOC khi chay:
    holdings {h7 verbatim-control, h3 override 864, h14 override 4032}
    x bases {majority, confirmed} x sizing {1x} = 6 nhanh.
- Hai control VERBATIM chay truoc nhu cong tai hien:
    maj_h7_1x phai khop majority_1x da xuat ban
      (total_return 1.6517829563633004 / max_drawdown -0.20086073993367803 / trades 63,
       sai so < 1e-6);
    conf_h7_1x phai khop confirmed_1x da xuat ban
      (total_return 1.5785811193475512 / max_drawdown -0.16094964732093653 / trades 60,
       sai so < 1e-6);
    mot trong hai KHONG DAT thi STOP. Ly do verbatim (tien le v57): base co holding
    hon hop (majority 61x2016+33x864; confirmed 64x2016+30x864) nen override-cung-2016
    se cho ket qua khac book goc; chi verbatim moi la control trung thuc.
- h3/h14 = execution-override: holding_bars = constant 864/4032, cap = holding
  (khop R1-A h7 execution-override + v57). h14 cap 4032 vuot dataset max 2016 (7x288)
  — bat buoc de engine chap nhan (VERIFY 1 <= holding <= max), disclose.
- Giu entry/stop/TP/entry_expiry identical. Khong refit, khong loc them.
- Nhanh thu 7 co dieu kien (neu re): best-holding branch duy nhat (best normal monthly
  trong 6 nhanh) duoc chay them bien the dd_guard x 3 kich ban; tham chieu guard la
  equity control CUNG BASE cua chinh experiment nay (fresh, qua khu, cat 1-microsecond,
  moc 100.0). Neu khong re thi skip+record ly do. Quy uoc v11/v13/v18/v23/v49/v57.
- Moi nhanh x 3 kich ban: normal / fee_stress (fee 0.00055) / execution_stress
  FillStress(5,5,5,0.00055,False), exposure<=1x. Monthly geometric theo duration
  cua configs/swing_v15_continuous_folds.json.
- Nhan exploratory: khoang 2023-2026 da mo, khong phai kiem dinh doc lap.
  Chi backtest local, khong dat lenh live.
"""
import torch  # noqa: F401  (thu tu import: torch truoc pandas tren host nay)
import argparse
import json
import traceback
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd
from agentic_alpha_lab.backtest.engine import CostModel, ExecutionConfig, run_backtest
from agentic_alpha_lab.backtest.execution_stress import FillStress, run_stress
from agentic_alpha_lab.data.training import sha256

DD_TRIGGER, DD_GUARD_LEV = 0.10, 0.5
LEV_MIN, LEV_MAX = 0.25, 1.0

# Tham chieu control da xuat ban (v15 ensemble).
XUAT_BAN = {
    "majority": {"total_return": 1.6517829563633004,
                 "max_drawdown": -0.20086073993367803, "trades": 63},
    "confirmed": {"total_return": 1.5785811193475512,
                  "max_drawdown": -0.16094964732093653, "trades": 60},
}

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
    assert list(cfg["branches"]) == ["maj_h7_1x", "conf_h7_1x", "maj_h3_1x",
                                     "conf_h3_1x", "maj_h14_1x", "conf_h14_1x"], \
        "ma tran phai la 2 bases x 3 holdings x 1x = 6 nhanh co dinh"
    assert list(cfg["sizings"]) == ["1x"]
    assert cfg["holdings"]["h7"]["bars"] == 2016
    assert cfg["holdings"]["h3"]["bars"] == 864
    assert cfg["holdings"]["h14"]["bars"] == 4032
    for base in ("majority", "confirmed"):
        assert cfg["control_reference"][base]["trades"] == XUAT_BAN[base]["trades"]
        assert abs(cfg["control_reference"][base]["total_return"] - XUAT_BAN[base]["total_return"]) < 1e-12
        assert abs(cfg["control_reference"][base]["max_drawdown"] - XUAT_BAN[base]["max_drawdown"]) < 1e-12
    goc = Path(__file__).resolve().parents[1]
    base_maj_path = goc / cfg["base_signals"]["majority"]
    base_conf_path = goc / cfg["base_signals"]["confirmed"]
    assert base_maj_path.exists(), f"base majority khong ton tai: {base_maj_path}"
    assert base_conf_path.exists(), f"base confirmed khong ton tai: {base_conf_path}"
    nen = pd.read_parquet(goc / cfg["candles"])
    goc_maj = pd.read_parquet(base_maj_path)
    goc_conf = pd.read_parquet(base_conf_path)
    ds_cfg = json.loads((goc / cfg["dataset_config"]).read_text())
    me = json.loads((goc / cfg["parent_plan"]).read_text())

    def mix(df):
        return {str(k): int((df["holding_bars"] == k).sum())
                for k in sorted(df["holding_bars"].unique().tolist())}

    # VERIFY base thuc te.
    print(json.dumps({"base_exists": True,
                      "majority_n": int(len(goc_maj)), "majority_mix": mix(goc_maj),
                      "confirmed_n": int(len(goc_conf)), "confirmed_mix": mix(goc_conf)}),
          flush=True)
    # Doc dataset max de VERIFY cap (mission yeu cau + tien le v57).
    ds_max = max(ds_cfg["holding_days"]) * 288
    assert ds_max == cfg["dataset_max_holding_bars"] == 2016, "dataset max phai la 7x288=2016"
    assert ds_cfg["holding_days"] == [3, 7]
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
    gd_control = {}

    # --- Hai control VERBATIM truoc (cong tai hien) ---
    for nhanh, base, goc_tin_hieu in (("maj_h7_1x", "majority", goc_maj),
                                      ("conf_h7_1x", "confirmed", goc_conf)):
        thu_muc_c = a.output / nhanh
        thu_muc_c.mkdir()
        goc_c = goc_tin_hieu.copy().reset_index(drop=True)
        # VERIFY cap: moi holding goc <= 2016.
        assert bool((goc_c["holding_bars"] <= 2016).all()), f"{nhanh} verbatim vuot cap 2016"
        th_c = thuc_thi_cho(2016, "1x")
        kb_c = chay_nhanh(nen, goc_c, von, von_fee, th_c, nghiem, nam, thu_muc_c)
        goc_c.to_parquet(thu_muc_c / "signals.parquet", index=False)
        n = kb_c["normal"]
        xb = XUAT_BAN[base]
        dat = (abs(n["total_return"] - xb["total_return"]) < 1e-6
               and abs(n["max_drawdown"] - xb["max_drawdown"]) < 1e-6
               and n["trades"] == xb["trades"])
        print(json.dumps({"nhanh": nhanh, "base": base, "n_signals": len(goc_c),
                          "normal": {k: n[k] for k in ("total_return", "max_drawdown", "trades",
                                                       "monthly_geometric_net")},
                          "kiem_tra_control": "DAT" if dat else "KHONG DAT",
                          "xuat_ban": xb}), flush=True)
        if not dat:
            (a.output / "CONTROL_MISMATCH.json").write_text(json.dumps(
                {"nhanh": nhanh, "base": base, "xuat_ban": xb,
                 "tai_hien": {k: n[k] for k in ("total_return", "max_drawdown", "trades")}}, indent=2))
            raise SystemExit(f"CONTROL KHONG KHOP ({nhanh}): {n['total_return']=} "
                             f"{n['max_drawdown']=} {n['trades']=}; STOP")
        ket_qua[nhanh] = {"scenarios": kb_c, "n_signals": len(goc_c),
                          "holding_bars": "verbatim(mix-864/2016)", "sizing": "1x",
                          "base": base}
        # Tham chieu guard = giao dich control cua chinh experiment nay.
        _, gd_c = run_backtest(nen, goc_c, 100, von, th_c)
        gd_control[base] = gd_c

    bo_dem = {}

    def guard_cho(base, kh):
        khoa = (base, tuple(pd.to_datetime(kh["signal_time"], utc=True).astype("int64")))
        if khoa not in bo_dem:
            bo_dem[khoa] = muc_dd_guard_tai(pd.to_datetime(kh["signal_time"], utc=True),
                                            gd_control[base])
        return bo_dem[khoa]

    ke_hoach = [("maj_h3_1x", "majority", "h3", "1x"),
                ("conf_h3_1x", "confirmed", "h3", "1x"),
                ("maj_h14_1x", "majority", "h14", "1x"),
                ("conf_h14_1x", "confirmed", "h14", "1x")]
    base_map = {"majority": goc_maj, "confirmed": goc_conf}
    for nhanh, base, hold_key, sizing in ke_hoach:
        thu_muc = a.output / nhanh
        thu_muc.mkdir()
        hb = HOLD[hold_key]
        # execution-override: holding_bars = constant, entry/stop/TP identical.
        co_ban = base_map[base].copy().reset_index(drop=True)
        co_ban["holding_bars"] = int(hb)
        mo_ta = f"override-{hb}"
        assert bool((co_ban["holding_bars"] <= hb).all())
        kh = co_ban.drop(columns=["leverage"], errors="ignore")
        th = thuc_thi_cho(hb, "1x")
        kh.to_parquet(thu_muc / "signals.parquet", index=False)
        kb = chay_nhanh(nen, kh, von, von_fee, th, nghiem, nam, thu_muc)
        ket_qua[nhanh] = {"scenarios": kb, "n_signals": len(kh),
                          "holding_bars": mo_ta, "sizing": sizing, "base": base}
        print(json.dumps({"nhanh": nhanh, "base": base, "n_signals": len(kh), "holding": mo_ta,
                          "chi_tiet": {s: {kk: kb[s][kk] for kk in
                                           ["total_return", "max_drawdown", "trades",
                                            "monthly_geometric_net", "gross_pnl", "fees",
                                            "funding", "profit_factor", "win_rate",
                                            "long_trades", "short_trades"]}
                                      for s in ("normal", "fee_stress", "execution_stress")},
                          "gate": co_gate(kb, cfg["gate"])["overall_pass"]}), flush=True)

    # --- Nhanh thu 7 co dieu kien: dd_guard tren best-holding (best normal monthly) ---
    dieu_kien = {"ran": False, "best_branch": None, "dd_branch": None,
                 "skipped_reason": None, "base": None, "holding": None}
    try:
        best = max(ket_qua.keys(),
                   key=lambda b: ket_qua[b]["scenarios"]["normal"]["monthly_geometric_net"])
        best_base = ket_qua[best]["base"]
        best_hold_desc = ket_qua[best]["holding_bars"]
        if best_hold_desc.startswith("override-"):
            hb_best = int(best_hold_desc.split("-")[1])
            hold_key_best = {864: "h3", 2016: "h7", 4032: "h14"}[hb_best]
        else:
            hb_best, hold_key_best = 2016, "h7"
        dd_ten = f"{best}_dd_guard" if not best.endswith("_1x") else best[:-3] + "_dd_guard"
        # tranh trung ten (luon moi vi 6 nhanh goc deu _1x)
        thu_muc7 = a.output / dd_ten
        thu_muc7.mkdir()
        if hold_key_best == "h7":
            co_ban7 = base_map[best_base].copy().reset_index(drop=True)
            mo_ta7 = "verbatim(mix-864/2016)"
        else:
            co_ban7 = base_map[best_base].copy().reset_index(drop=True)
            co_ban7["holding_bars"] = int(hb_best)
            mo_ta7 = f"override-{hb_best}"
        kh7 = co_ban7.drop(columns=["leverage"], errors="ignore").copy()
        kh7["leverage"] = guard_cho(best_base, co_ban7)
        th7 = thuc_thi_cho(hb_best, "dd_guard")
        kh7.to_parquet(thu_muc7 / "signals.parquet", index=False)
        kb7 = chay_nhanh(nen, kh7, von, von_fee, th7, nghiem, nam, thu_muc7)
        ket_qua[dd_ten] = {"scenarios": kb7, "n_signals": len(kh7),
                           "holding_bars": mo_ta7, "sizing": "dd_guard",
                           "base": best_base}
        dieu_kien.update({"ran": True, "best_branch": best, "dd_branch": dd_ten,
                          "base": best_base,
                          "holding": mo_ta7,
                          "guard_reference": f"control cung base {best_base}_h7_1x cua chinh experiment nay"})
        print(json.dumps({"nhanh_thu_7": dd_ten, "best": best, "base": best_base,
                          "holding": mo_ta7,
                          "chi_tiet": {s: {kk: kb7[s][kk] for kk in
                                           ["total_return", "max_drawdown", "trades",
                                            "monthly_geometric_net"]}
                                      for s in ("normal", "fee_stress", "execution_stress")},
                          "gate": co_gate(kb7, cfg["gate"])["overall_pass"]}), flush=True)
    except Exception as e:  # noqa: BLE001 — skip+record theo mission
        dieu_kien["skipped_reason"] = f"{type(e).__name__}: {e}\n{traceback.format_exc(limit=3)}"
        print(json.dumps({"nhanh_thu_7": "SKIP", "ly_do": dieu_kien["skipped_reason"]}), flush=True)

    danh_dau = {b: {"gate": co_gate(v["scenarios"], cfg["gate"]),
                    "n_signals": v["n_signals"], "holding_bars": v["holding_bars"],
                    "sizing": v["sizing"], "base": v["base"], "scenarios": v["scenarios"]}
                for b, v in ket_qua.items()}
    bao_cao = {"branches": danh_dau, "config": cfg,
               "kiem_tra_control": {
                   "majority": {"xuat_ban": XUAT_BAN["majority"],
                                "tai_hien": {k: ket_qua["maj_h7_1x"]["scenarios"]["normal"][k]
                                             for k in ("total_return", "max_drawdown", "trades",
                                                       "monthly_geometric_net")},
                                "khop": True},
                   "confirmed": {"xuat_ban": XUAT_BAN["confirmed"],
                                 "tai_hien": {k: ket_qua["conf_h7_1x"]["scenarios"]["normal"][k]
                                              for k in ("total_return", "max_drawdown", "trades",
                                                        "monthly_geometric_net")},
                                 "khop": True}},
               "conditional_7th": dieu_kien,
               "base_thuc_te": {"majority_n": int(len(goc_maj)), "majority_mix": mix(goc_maj),
                                "confirmed_n": int(len(goc_conf)), "confirmed_mix": mix(goc_conf)},
               "cong_thuc": {"override": "h3/h14: holding_bars=constant causal; h7: verbatim",
                             "dd_trigger": DD_TRIGGER, "dd_guard_lev": DD_GUARD_LEV,
                             "dd_guard_tham_chieu": cfg["conditional_7th"]["dd_guard"]["reference"],
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
                                (cfg["candles"], cfg["base_signals"]["majority"],
                                 cfg["base_signals"]["confirmed"], cfg["dataset_config"],
                                 cfg["parent_plan"], "configs/opencode_v67_holdmajconf.json")},
               "gate": {"monthly_min": cfg["gate"]["monthly_min"],
                        "dd_max": cfg["gate"]["dd_max"], "fills_min": cfg["gate"]["fills_min"]}}
    (a.output / "summary.json").write_text(json.dumps(bao_cao, indent=2, ensure_ascii=False, default=str))
    print("DA GHI", str(a.output / "summary.json"))
