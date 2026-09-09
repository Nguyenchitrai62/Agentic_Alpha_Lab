"""Opencode v52 (R16-E-unionbook): dedup UNION of frozen quality legs.

Mirror hypothesis (ledger round15_synthesis): every filter on selective bases
kills coverage; UNION of quality legs ADDS coverage and may add monthly.
Genuinely untested direction.

Frozen sources (set ops only, never refit, causal past-only):
  majority       artifacts/research/opencode_v15_mapensemble/majority_1x/signals.parquet (94)
  confirmed      artifacts/research/opencode_v15_mapensemble/confirmed_1x/signals.parquet (94)
  band2confirmed artifacts/research/opencode_v49_band2conf/confirmed_band2_1x/signals.parquet (50, subset of confirmed)
  s0004_t050     artifacts/research/opencode_v13_megacombo/s0004_t050_1x/signals.parquet (47)

Union rule (pre-specified in configs/opencode_v52_unionbook.json BEFORE running):
  dedup by (bar_index, direction); on (bar,direction) conflict keep majority's
  row (priority majority > confirmed > band2confirmed > s0004_t050); each member
  keeps its own geometry. Conflict count recorded.
Sets: majority_control, confirmed_control, U1 = maj|con,
      U2 = maj|con|band2|s0004. x sizing {1x, dd_guard} = 8 branches.
dd_guard reference = majority_control_1x equity of THIS experiment (fresh run,
past-only 1-microsecond cutoff, 100.0 seed), applied at each branch's own
signal times. Same formula as scripts/opencode_r1a_holding_probe.py.
Control gate: majority_control_1x normal must match published majority_1x
(+165.178%/−20.086%/63, tol 1e-6) or STOP. confirmed_control_1x checked
(not fatal) vs published confirmed_1x (+157.86%/−16.09%/60).
Each branch x 3 scenarios: normal / fee_stress (0.00055) / execution_stress
FillStress(5,5,5,0.00055,False), exposure<=1x. Monthly geometric from
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

MAJ_PUB = {"total_return": 1.6517829563633004,
           "max_drawdown": -0.20086073993367803, "trades": 63}
CON_PUB = {"total_return": 1.5785811193475512,
           "max_drawdown": -0.16094964732093653, "trades": 60}

PRIORITY = ["majority", "confirmed", "band2confirmed", "s0004_t050"]


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


def dedup_union(frames):
    """Dedup union theo (bar_index, direction), uu tien PRIORITY. Tra ve (df, conflicts, geo_diffs)."""
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
    assert list(cfg["branches"]) == ["majority_control_1x", "majority_control_dd_guard",
                                     "confirmed_control_1x", "confirmed_control_dd_guard",
                                     "U1_1x", "U1_dd_guard", "U2_1x", "U2_dd_guard"], \
        "ma tran phai la 4 sets x 2 sizing = 8 nhanh co dinh"
    assert list(cfg["sizings"]) == ["1x", "dd_guard"]
    assert cfg["union_rule"]["conflict_priority"].startswith("majority"), \
        "quy tac conflict phai uu tien majority"
    assert cfg["control_majority_reference"] == MAJ_PUB
    assert cfg["control_confirmed_reference"] == CON_PUB
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

    # --- Overlap stats (trung thuc, truoc khi chay backtest) ---
    keys = {k: set(zip(v["bar_index"].astype(int), v["direction"].astype(int)))
            for k, v in frames.items()}
    u1k = keys["majority"] | keys["confirmed"]
    u2k = u1k | keys["band2confirmed"] | keys["s0004_t050"]
    overlap = {
        "n_majority": len(keys["majority"]), "n_confirmed": len(keys["confirmed"]),
        "n_band2confirmed": len(keys["band2confirmed"]), "n_s0004_t050": len(keys["s0004_t050"]),
        "maj_inter_con": len(keys["majority"] & keys["confirmed"]),
        "U1_size": len(u1k),
        "band2_subset_of_confirmed": bool(keys["band2confirmed"] <= keys["confirmed"]),
        "band2_minus_majority": len(keys["band2confirmed"] - keys["majority"]),
        "s0004_in_maj": len(keys["s0004_t050"] & keys["majority"]),
        "s0004_in_con": len(keys["s0004_t050"] & keys["confirmed"]),
        "s0004_in_band2": len(keys["s0004_t050"] & keys["band2confirmed"]),
        "s0004_new_vs_U1": len(keys["s0004_t050"] - u1k),
        "U2_size": len(u2k),
        "U2_minus_U1": len(u2k - u1k),
    }
    print(json.dumps({"overlap": overlap}), flush=True)

    # --- Lap cac tap hop ---
    u1_df, u1_conf, u1_geod, _ = dedup_union(
        {k: frames[k] for k in ("majority", "confirmed")})
    u2_df, u2_conf, u2_geod, nguon_u2 = dedup_union(frames)
    assert len(u1_df) == overlap["U1_size"], "U1 size lech overlap"
    assert len(u2_df) == overlap["U2_size"], "U2 size lech overlap"
    tap = {"majority_control": frames["majority"].copy(),
           "confirmed_control": frames["confirmed"].copy(),
           "U1": u1_df, "U2": u2_df}
    union_stats = {
        "U1": {"n_signals": len(u1_df), "conflicts": u1_conf, "geo_diffs_on_conflict": u1_geod},
        "U2": {"n_signals": len(u2_df), "conflicts": u2_conf, "geo_diffs_on_conflict": u2_geod,
               "member_counts": {t: sum(1 for v in nguon_u2.values() if v == t) for t in PRIORITY}},
    }
    print(json.dumps({"union_stats": union_stats}), flush=True)

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
    # --- Majority control 1x truoc (cong tai hien, STOP neu lech) ---
    thu_muc_m = a.output / "majority_control_1x"
    thu_muc_m.mkdir()
    goc_m = tap["majority_control"]
    goc_m.to_parquet(thu_muc_m / "signals.parquet", index=False)
    kb_m = chay_nhanh(nen, goc_m, von, von_fee, thuc_thi_1x, nghiem, nam, thu_muc_m)
    n = kb_m["normal"]
    dat = (abs(n["total_return"] - MAJ_PUB["total_return"]) < 1e-6
           and abs(n["max_drawdown"] - MAJ_PUB["max_drawdown"]) < 1e-6
           and n["trades"] == MAJ_PUB["trades"])
    print(json.dumps({"nhanh": "majority_control_1x", "n_signals": len(goc_m),
                      "normal": {k: n[k] for k in ("total_return", "max_drawdown", "trades",
                                                   "monthly_geometric_net")},
                      "kiem_tra_control": "DAT" if dat else "KHONG DAT",
                      "xuat_ban": MAJ_PUB}), flush=True)
    if not dat:
        (a.output / "CONTROL_MISMATCH.json").write_text(json.dumps(
            {"xuat_ban": MAJ_PUB,
             "tai_hien": {k: n[k] for k in ("total_return", "max_drawdown", "trades")}}, indent=2))
        raise SystemExit(f"CONTROL KHONG KHOP: {n['total_return']=} {n['max_drawdown']=} "
                         f"{n['trades']=}; STOP")
    ket_qua["majority_control_1x"] = {"scenarios": kb_m, "n_signals": len(goc_m),
                                      "tap": "majority_control", "sizing": "1x"}

    # Tham chieu guard = giao dich majority-control cua chinh experiment nay.
    _, gd_control = run_backtest(nen, goc_m, 100, von, thuc_thi_1x)
    bo_dem = {}

    def guard_cho(kh):
        khoa = tuple(pd.to_datetime(kh["signal_time"], utc=True).astype("int64"))
        if khoa not in bo_dem:
            bo_dem[khoa] = muc_dd_guard_tai(pd.to_datetime(kh["signal_time"], utc=True), gd_control)
        return bo_dem[khoa]

    ke_hoach = [("majority_control_dd_guard", "majority_control", "dd_guard"),
                ("confirmed_control_1x", "confirmed_control", "1x"),
                ("confirmed_control_dd_guard", "confirmed_control", "dd_guard"),
                ("U1_1x", "U1", "1x"),
                ("U1_dd_guard", "U1", "dd_guard"),
                ("U2_1x", "U2", "1x"),
                ("U2_dd_guard", "U2", "dd_guard")]
    confirmed_check = None
    for nhanh, t, sizing in ke_hoach:
        thu_muc = a.output / nhanh
        thu_muc.mkdir()
        co_ban = tap[t]
        if sizing == "1x":
            kh = co_ban.copy()
            th = thuc_thi_1x
        else:
            kh = co_ban.copy()
            kh["leverage"] = guard_cho(co_ban)
            th = thuc_thi_size
        kh.to_parquet(thu_muc / "signals.parquet", index=False)
        kb = chay_nhanh(nen, kh, von, von_fee, th, nghiem, nam, thu_muc)
        ket_qua[nhanh] = {"scenarios": kb, "n_signals": len(kh), "tap": t, "sizing": sizing}
        if nhanh == "confirmed_control_1x":
            cn = kb["normal"]
            confirmed_check = {
                "xuat_ban": CON_PUB,
                "tai_hien": {k: cn[k] for k in ("total_return", "max_drawdown", "trades",
                                                "monthly_geometric_net")},
                "khop": bool(abs(cn["total_return"] - CON_PUB["total_return"]) < 1e-6
                             and abs(cn["max_drawdown"] - CON_PUB["max_drawdown"]) < 1e-6
                             and cn["trades"] == CON_PUB["trades"])}
            print(json.dumps({"nhanh": nhanh, "confirmed_check": confirmed_check}), flush=True)
        print(json.dumps({"nhanh": nhanh, "n_signals": len(kh),
                          "chi_tiet": {s: {kk: kb[s][kk] for kk in
                                           ["total_return", "max_drawdown", "trades",
                                            "monthly_geometric_net", "gross_pnl", "fees",
                                            "funding", "profit_factor", "win_rate",
                                            "long_trades", "short_trades"]}
                                      for s in ("normal", "fee_stress", "execution_stress")},
                          "gate": co_gate(kb, cfg["gate"])["overall_pass"]}), flush=True)

    danh_dau = {b: {"gate": co_gate(v["scenarios"], cfg["gate"]),
                    "n_signals": v["n_signals"], "tap": v["tap"],
                    "sizing": v["sizing"], "scenarios": v["scenarios"]}
                for b, v in ket_qua.items()}
    bao_cao = {"branches": danh_dau, "config": cfg,
               "kiem_tra_control_majority": {
                   "xuat_ban": MAJ_PUB,
                   "tai_hien": {k: n[k] for k in ("total_return", "max_drawdown", "trades",
                                                  "monthly_geometric_net")},
                   "khop": True},
               "kiem_tra_control_confirmed": confirmed_check,
               "overlap": overlap, "union_stats": union_stats,
               "cong_thuc": {"union": cfg["union_rule"],
                             "dd_trigger": DD_TRIGGER, "dd_guard_lev": DD_GUARD_LEV,
                             "dd_guard_tham_chieu": cfg["dd_guard_reference"],
                             "lev_min": LEV_MIN, "lev_max": LEV_MAX,
                             "fee_stress": "fee_rate_per_fill=0.00055",
                             "execution_stress": "FillStress(5,5,5,0.00055,False), exposure<=1x",
                             "monthly_geometric_net": "ty_le=final/100; monthly=ty_le^(1/(12*nam))-1"},
               "duration_years": nam, "independent_test": False, "live_approved": False,
               "exploratory": True,
               "canh_bao": ("CHI EXPLORATORY: khoang phat trien 2023-2026 da mo (den "
                            + me["complete_evaluation_until"] + "). Set ops tren tin hieu "
                            "dong bang (khong refit, khong tinh lai). Khong de xuat nhanh nao, "
                            "khong tuyen bo kiem dinh. Drawdown lay mau theo gia dong nen trade, "
                            "khong phai drawdown mark-price/intrabar thuc. Exit stop/timeout dang "
                            "market-like theo fee kich ban, khong phai fill maker/limit dam bao. "
                            "Khong suy doan xac suat fill maker hay vi tri hang doi tu OHLC."),
               "input_sha256": {str(q): sha256(goc / q) for q in
                                (cfg["candles"], cfg["sources"]["majority"],
                                 cfg["sources"]["confirmed"], cfg["sources"]["band2confirmed"],
                                 cfg["sources"]["s0004_t050"], cfg["dataset_config"],
                                 cfg["parent_plan"], "configs/opencode_v52_unionbook.json")},
               "gate": {"monthly_min": cfg["gate"]["monthly_min"],
                        "dd_max": cfg["gate"]["dd_max"], "fills_min": cfg["gate"]["fills_min"]}}
    (a.output / "summary.json").write_text(json.dumps(bao_cao, indent=2, ensure_ascii=False, default=str))
    print("DA GHI", str(a.output / "summary.json"))
