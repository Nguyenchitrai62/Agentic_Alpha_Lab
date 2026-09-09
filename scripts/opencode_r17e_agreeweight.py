"""Opencode v54 (R17-E-agreeweight): agreement-weighted sizing tren U1 dong bang.

Gia thuyet khac round16 (ledger): UNION filtering CHET vi no LOAI trade
(v52: monthly 2.935->2.724, trade them am rong + day mat winner do engine
don-vi-tri). Gia thuyet nay KHONG bao gio loai — vote chi dat SIZE:
key trong CA HAI tap -> leverage 1.0; key trong DUNG MOT tap -> 0.5.
Set membership biet tai thoi diem tin hieu (2 frame dong bang) -> causal.

Nguon dong bang (set ops only, never refit, causal past-only):
  majority  artifacts/research/opencode_v15_mapensemble/majority_1x/signals.parquet (94)
  confirmed artifacts/research/opencode_v15_mapensemble/confirmed_1x/signals.parquet (94)
U1 = majority UNION confirmed, dedup theo (bar_index, direction),
uu tien majority khi conflict (tu tinh overlap, khong tin tri nho).

4 nhanh co dinh (configs/opencode_v54_agreeweight.json viet TRUOC khi chay):
  majority_control_1x      majority verbatim 1x (control check + guard reference)
  U1_1x                    union all-1.0 (control, phai khop v52 U1_1x hoac STOP)
  U1_agreeweight           vote sizing 1.0/0.5 (floor 0.25/max 1.0 de 0.5 di qua)
  U1_agreeweight_dd_guard  vote * guard (guard tu majority-control experiment nay,
                           past-only 1-microsecond cutoff, seed 100.0):
                           both+noguard 1.0, both+guard 0.5,
                           single+noguard 0.5, single+guard 0.25.
Moi nhanh x 3 kich ban: normal / fee_stress (0.00055) /
execution_stress FillStress(5,5,5,0.00055,False). Monthly geometric tu
configs/swing_v15_continuous_folds.json duration.
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
LEV_BOTH, LEV_SINGLE = 1.0, 0.5

U1_PUB = {"total_return": 1.4742586857377251,
          "max_drawdown": -0.21751346157692608, "trades": 66}
MAJ_PUB = {"total_return": 1.6517829563633004,
           "max_drawdown": -0.20086073993367803, "trades": 63}

PRIORITY = ["majority", "confirmed"]


def muc_dd_guard_tai(diem_tin_hieu, giao_dich_tham_chieu):
    """Trang thai guard tu equity majority-control, tai diem tin hieu (chi qua khu)."""
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
                          "monthly_geometric_net": ty_le ** (1 / (12 * nam)) - 1,
                          "trade_leverage_hist": _hist([t.leverage for t in ds])}
        hang = [asdict(g) for g in ds]
        pd.DataFrame(hang).to_csv(thu_muc / f"{nhan}_trades.csv", index=False)
    kich_ban["execution_stress"]["diagnostics"] = chan_doan
    all_gd = {"normal": gd, "fee_stress": gd_phi, "execution_stress": gd_cang}
    return kich_ban, all_gd


def _hist(vals):
    h = {}
    for v in vals:
        k = str(float(v))
        h[k] = h.get(k, 0) + 1
    return dict(sorted(h.items()))


def _sig_hist(kh):
    if "leverage" in kh.columns:
        return _hist([float(v) for v in kh["leverage"].tolist()])
    return {"1.0": int(len(kh))}


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


def dedup_union(frames):
    """Dedup union theo (bar_index, direction), uu tien PRIORITY. Tra ve (df, conflicts, geo_diffs, nguon)."""
    gop = {}
    nguon = {}
    conflicts = 0
    geo_diffs = 0
    geo_cols = ["entry_limit", "stop_loss", "take_profit_1", "take_profit_2", "holding_bars"]
    for ten in PRIORITY:
        if ten not in frames:
            continue
        df = frames[ten]
        for _, row in df.iterrows():
            khoa = (int(row["bar_index"]), int(row["direction"]))
            if khoa not in gop:
                gop[khoa] = row
                nguon[khoa] = ten
            else:
                conflicts += 1
                try:
                    same = all(gop[khoa][c] == row[c] for c in geo_cols if c in df.columns)
                    if not same:
                        geo_diffs += 1
                except Exception:
                    pass
    out = pd.DataFrame(list(gop.values())).reset_index(drop=True)
    out = out.sort_values("signal_time").reset_index(drop=True)
    return out, conflicts, geo_diffs, nguon


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--config", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    if a.output.exists():
        raise FileExistsError("Chon output moi; khong ghi de bang chung lich su")
    cfg = json.loads(a.config.read_text())
    # Kiem tra ma tran co dinh (config viet TRUOC khi chay).
    assert list(cfg["branches"]) == ["majority_control_1x", "U1_1x",
                                     "U1_agreeweight", "U1_agreeweight_dd_guard"], \
        "ma tran phai la 4 nhanh co dinh"
    assert list(cfg["sizings"]) == ["1x", "agreeweight", "agreeweight_dd_guard"]
    assert cfg["vote_rule"]["both"].strip().endswith("1.0")
    assert cfg["vote_rule"]["single"].strip().endswith("0.5")
    assert cfg["union_rule"]["conflict_priority"].startswith("majority"), \
        "quy tac conflict phai uu tien majority"
    assert cfg["control_U1_reference"] == U1_PUB
    assert cfg["control_majority_reference"] == MAJ_PUB
    assert cfg["lev_min"] == LEV_MIN and cfg["lev_max"] == LEV_MAX
    goc = Path(__file__).resolve().parents[1]
    nen = pd.read_parquet(goc / cfg["candles"])
    ds_cfg = json.loads((goc / cfg["dataset_config"]).read_text())
    me = json.loads((goc / cfg["parent_plan"]).read_text())

    frames = {}
    for ten, rel in cfg["sources"].items():
        df = pd.read_parquet(goc / rel)
        assert int(len(df)) == int(cfg["source_n_signals"][ten]), \
            f"nguon {ten} phai co {cfg['source_n_signals'][ten]} tin hieu, got {len(df)}"
        assert set(["bar_index", "direction", "signal_time"]) <= set(df.columns), \
            f"nguon {ten} thieu cot khoa"
        assert int(df.duplicated(subset=["bar_index", "direction"]).sum()) == 0, \
            f"nguon {ten} co key trung noi bo"
        df = df.drop(columns=["action"], errors="ignore")
        df = df.drop(columns=["leverage"], errors="ignore")
        frames[ten] = df.reset_index(drop=True)
    print(json.dumps({"nguon_n": {k: len(v) for k, v in frames.items()}}), flush=True)

    # --- Overlap stats (tu tinh, truoc khi chay backtest) ---
    keys = {k: set(zip(v["bar_index"].astype(int), v["direction"].astype(int)))
            for k, v in frames.items()}
    inter = keys["majority"] & keys["confirmed"]
    uni = keys["majority"] | keys["confirmed"]
    mm = {k: r for k, r in zip(zip(frames["majority"]["bar_index"].astype(int),
                                   frames["majority"]["direction"].astype(int)),
                               frames["majority"].to_dict("records"))}
    cc = {k: r for k, r in zip(zip(frames["confirmed"]["bar_index"].astype(int),
                                   frames["confirmed"]["direction"].astype(int)),
                               frames["confirmed"].to_dict("records"))}
    geo_cols = ["entry_limit", "stop_loss", "take_profit_1", "take_profit_2", "holding_bars"]
    geo_diffs = sum(1 for k in inter if any(mm[k][c] != cc[k][c] for c in geo_cols))
    overlap = {
        "n_majority": len(keys["majority"]), "n_confirmed": len(keys["confirmed"]),
        "intersection_both": len(inter),
        "maj_only": len(keys["majority"] - keys["confirmed"]),
        "con_only": len(keys["confirmed"] - keys["majority"]),
        "U1_size": len(uni),
        "geo_diffs_on_intersection": int(geo_diffs),
    }
    print(json.dumps({"overlap": overlap}), flush=True)

    # --- Lap U1 + gan trong so vote (frozen, causal) ---
    u1_df, u1_conf, u1_geod, nguon_u1 = dedup_union(frames)
    assert len(u1_df) == overlap["U1_size"], "U1 size lech overlap"
    assert u1_geod == overlap["geo_diffs_on_intersection"], "geo diff lech"
    vote_w = np.array([LEV_BOTH if (int(r["bar_index"]), int(r["direction"])) in inter
                       else LEV_SINGLE for _, r in u1_df.iterrows()], dtype=float)
    u1_df["_vote"] = vote_w
    vote_stats = {
        "n_both_lev10": int((vote_w == LEV_BOTH).sum()),
        "n_single_lev05": int((vote_w == LEV_SINGLE).sum()),
        "signal_leverage_hist": _hist([float(v) for v in vote_w]),
        "U1_conflicts": int(u1_conf),
        "U1_geo_diffs": int(u1_geod),
        "member_counts": {t: sum(1 for v in nguon_u1.values() if v == t) for t in PRIORITY},
    }
    assert vote_stats["n_both_lev10"] == overlap["intersection_both"]
    assert vote_stats["n_single_lev05"] == overlap["maj_only"] + overlap["con_only"]
    print(json.dumps({"vote_stats": vote_stats}), flush=True)

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
    lev_proof = {}

    def ghi_nhanh(ten, kh, th):
        thu_muc = a.output / ten
        thu_muc.mkdir()
        kh.to_parquet(thu_muc / "signals.parquet", index=False)
        kb, gd_all = chay_nhanh(nen, kh, von, von_fee, th, nghiem, nam, thu_muc)
        ket_qua[ten] = {"scenarios": kb, "n_signals": len(kh),
                        "signal_leverage_hist": _sig_hist(kh)}
        lev_proof[ten] = {s: kb[s]["trade_leverage_hist"] for s in
                          ("normal", "fee_stress", "execution_stress")}
        print(json.dumps({"nhanh": ten, "n_signals": len(kh),
                          "sig_hist": ket_qua[ten]["signal_leverage_hist"],
                          "trade_hist_normal": lev_proof[ten]["normal"],
                          "chi_tiet": {s: {kk: kb[s][kk] for kk in
                                           ["total_return", "max_drawdown", "trades",
                                            "monthly_geometric_net", "gross_pnl", "fees",
                                            "funding", "profit_factor", "win_rate",
                                            "long_trades", "short_trades"]}
                                      for s in ("normal", "fee_stress", "execution_stress")},
                          "gate": co_gate(kb, cfg["gate"])["overall_pass"]}), flush=True)
        return kb, gd_all

    # --- 1) Majority control 1x truoc (CHECK khong fatal + lam guard reference) ---
    kb_m, gd_m_all = ghi_nhanh("majority_control_1x", frames["majority"].copy(), thuc_thi_1x)
    n = kb_m["normal"]
    maj_check = {
        "xuat_ban": MAJ_PUB,
        "tai_hien": {k: n[k] for k in ("total_return", "max_drawdown", "trades",
                                       "monthly_geometric_net")},
        "khop": bool(abs(n["total_return"] - MAJ_PUB["total_return"]) < 1e-6
                     and abs(n["max_drawdown"] - MAJ_PUB["max_drawdown"]) < 1e-6
                     and n["trades"] == MAJ_PUB["trades"])}
    print(json.dumps({"nhanh": "majority_control_1x",
                      "kiem_tra_control": "DAT" if maj_check["khop"] else "KHONG DAT",
                      "xuat_ban": MAJ_PUB}), flush=True)

    # --- 2) U1 1x control (FATAL: lech la STOP) ---
    u1_1x = u1_df.drop(columns=["_vote"]).copy()
    kb_u, _ = ghi_nhanh("U1_1x", u1_1x, thuc_thi_1x)
    u = kb_u["normal"]
    dat_u = (abs(u["total_return"] - U1_PUB["total_return"]) < 1e-6
             and abs(u["max_drawdown"] - U1_PUB["max_drawdown"]) < 1e-6
             and u["trades"] == U1_PUB["trades"])
    print(json.dumps({"nhanh": "U1_1x",
                      "kiem_tra_control": "DAT" if dat_u else "KHONG DAT",
                      "xuat_ban": U1_PUB}), flush=True)
    if not dat_u:
        (a.output / "CONTROL_MISMATCH.json").write_text(json.dumps(
            {"xuat_ban": U1_PUB,
             "tai_hien": {k: u[k] for k in ("total_return", "max_drawdown", "trades")}}, indent=2))
        raise SystemExit(f"CONTROL U1 KHONG KHOP: {u['total_return']=} {u['max_drawdown']=} "
                         f"{u['trades']=}; STOP")

    # Tham chieu guard = giao dich majority-control cua chinh experiment nay.
    _, gd_control = run_backtest(nen, frames["majority"].copy(), 100, von, thuc_thi_1x)
    bo_dem = {}

    def guard_cho(kh):
        khoa = tuple(pd.to_datetime(kh["signal_time"], utc=True).astype("int64"))
        if khoa not in bo_dem:
            bo_dem[khoa] = muc_dd_guard_tai(pd.to_datetime(kh["signal_time"], utc=True), gd_control)
        return bo_dem[khoa]

    # --- 3) U1 agreeweight (vote sizing thuan) ---
    kh_aw = u1_df.drop(columns=["_vote"]).copy()
    kh_aw["leverage"] = vote_w
    kb_aw, _ = ghi_nhanh("U1_agreeweight", kh_aw, thuc_thi_size)

    # --- 4) U1 agreeweight x dd_guard (vote * guard, cong khai) ---
    kh_awg = u1_df.drop(columns=["_vote"]).copy()
    kh_awg["leverage"] = vote_w * guard_cho(kh_awg)
    assert set(np.round(kh_awg["leverage"].unique(), 12)) <= {0.25, 0.5, 1.0}, \
        f"muc leverage guard lech: {sorted(kh_awg['leverage'].unique())}"
    kb_awg, _ = ghi_nhanh("U1_agreeweight_dd_guard", kh_awg, thuc_thi_size)

    # --- Bang chung leverage 0.5 di qua engine ---
    t05 = pd.read_csv(a.output / "U1_agreeweight" / "normal_trades.csv")
    proof_05 = bool(((t05["leverage"] - 0.5).abs() < 1e-12).any()) if len(t05) else False
    print(json.dumps({"bang_chung_leverage_05": proof_05,
                      "n_trade_05": int(((t05["leverage"] - 0.5).abs() < 1e-12).sum()) if len(t05) else 0,
                      "trade_hist": _hist(t05["leverage"].tolist()) if len(t05) else {}}), flush=True)

    danh_dau = {b: {"gate": co_gate(v["scenarios"], cfg["gate"]),
                    "n_signals": v["n_signals"],
                    "signal_leverage_hist": v["signal_leverage_hist"],
                    "trade_leverage_hist": lev_proof[b],
                    "scenarios": v["scenarios"]}
                for b, v in ket_qua.items()}
    bao_cao = {"branches": danh_dau, "config": cfg,
               "kiem_tra_control_U1": {
                   "xuat_ban": U1_PUB,
                   "tai_hien": {k: u[k] for k in ("total_return", "max_drawdown", "trades",
                                                  "monthly_geometric_net")},
                   "khop": True},
               "kiem_tra_control_majority": maj_check,
               "overlap": overlap, "vote_stats": vote_stats,
               "bang_chung_leverage": {
                   "U1_agreeweight_normal_co_trade_05": proof_05,
                   "chi_tiet": lev_proof},
               "cong_thuc": {"union": cfg["union_rule"], "vote": cfg["vote_rule"],
                             "sizing": cfg["sizing"],
                             "dd_trigger": DD_TRIGGER, "dd_guard_lev": DD_GUARD_LEV,
                             "dd_guard_tham_chieu": cfg["dd_guard_reference"],
                             "lev_min": LEV_MIN, "lev_max": LEV_MAX,
                             "clamp_engine": "min(max(requested, 0.25), 1.0)",
                             "fee_stress": "fee_rate_per_fill=0.00055",
                             "execution_stress": "FillStress(5,5,5,0.00055,False), exposure<=1x",
                             "monthly_geometric_net": "ty_le=final/100; monthly=ty_le^(1/(12*nam))-1"},
               "duration_years": nam, "independent_test": False, "live_approved": False,
               "exploratory": True,
               "canh_bao": ("CHI EXPLORATORY: khoang phat trien 2023-2026 da mo (den "
                            + me["complete_evaluation_until"] + "). Set ops + sizing tren tin hieu "
                            "dong bang (khong refit, khong tinh lai). Khong de xuat nhanh nao, "
                            "khong tuyen bo kiem dinh. Drawdown lay mau theo gia dong nen trade, "
                            "khong phai drawdown mark-price/intrabar thuc. Exit stop/timeout dang "
                            "market-like theo fee kich ban, khong phai fill maker/limit dam bao. "
                            "Khong suy doan xac suat fill maker hay vi tri hang doi tu OHLC."),
               "input_sha256": {str(q): sha256(goc / q) for q in
                                (cfg["candles"], cfg["sources"]["majority"],
                                 cfg["sources"]["confirmed"], cfg["dataset_config"],
                                 cfg["parent_plan"], "configs/opencode_v54_agreeweight.json")},
               "gate": {"monthly_min": cfg["gate"]["monthly_min"],
                        "dd_max": cfg["gate"]["dd_max"], "fills_min": cfg["gate"]["fills_min"]}}
    (a.output / "summary.json").write_text(json.dumps(bao_cao, indent=2, ensure_ascii=False, default=str))
    print("DA GHI", str(a.output / "summary.json"))
