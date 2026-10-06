"""Audit test for the delivery-track replication (blind audit, tolerance checks)."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUD = ROOT / "research" / "tournament" / "audit_deliverytrack"
REP = AUD / "replication.json"
CMP = AUD / "comparison.json"
EVL = ROOT / "research" / "tournament" / "oc_deliverytrack" / "results.json"


def _load(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def test_replication_exists_and_covers_33():
    rep = _load(REP)
    assert rep["meta"]["n_trades"] == 33
    assert len(rep["rows"]) == 33
    keys = {(r["coin"], r["delivery"]) for r in rep["rows"]}
    assert len(keys) == 33
    for r in rep["rows"]:
        for k in ("spot_twap_0730_0800", "spot_sched_6slice", "fut_twap_0730_0800",
                  "fut_sched_6slice"):
            assert r[k] > 0, (r["coin"], r["delivery"], k)
        assert abs(r["te_bp_sched"]) < 100.0


def test_same_venue_matches_within_tolerance():
    rep = _load(REP)
    evl = _load(EVL)
    rmap = {(r["coin"], r["delivery"]): r for r in rep["rows"]}
    emap = {(r["coin"], r["delivery"]): r for r in evl["deliveries"]}
    assert set(rmap) == set(emap)
    tw_d, sl_d = [], []
    for k, v in rmap.items():
        b = emap[k]["binance"]
        tw_d.append((v["fut_twap_0730_0800"] - b["twap"]) / b["twap"] * 1e4)
        sl_d.append((v["fut_sched_6slice"] - b["slices6"]) / b["slices6"] * 1e4)
    import statistics

    assert abs(statistics.mean(tw_d)) <= 1.0, statistics.mean(tw_d)
    assert max(abs(x) for x in tw_d) <= 3.0
    assert abs(statistics.mean(sl_d)) <= 1.0, statistics.mean(sl_d)
    assert max(abs(x) for x in sl_d) <= 3.0


def test_sched_tracking_error_is_small_and_venue_robust():
    rep = _load(REP)
    evl = _load(EVL)
    assert abs(rep["summary"]["te_sched_bp_mean"]) < 3.0
    assert rep["summary"]["te_sched_bp_worst_abs"] < 25.0
    assert abs(evl["summary"]["slices6"]["te_bp_mean"]) < 3.0
    assert evl["summary"]["slices6"]["te_bp_worst_abs"] < 25.0
    assert evl["summary"]["slices6"]["dret_pp_worst_abs"] < 0.02


def test_bot_bucket_schedule_shape():
    from bot.carry import SLICE_BUCKET_MS, SLICE_N, SLICE_WINDOW_MS, _slice_bucket

    assert SLICE_N == 6
    assert SLICE_WINDOW_MS == 30 * 60 * 1000
    assert SLICE_BUCKET_MS == 5 * 60 * 1000
    dlv = 8 * 3600 * 1000
    start = dlv - SLICE_WINDOW_MS
    # one slice per 5-minute bucket starting delivery-30min, first cycle inside
    assert _slice_bucket(start, dlv) == 0
    assert _slice_bucket(start + 5 * 60 * 1000, dlv) == 1
    assert _slice_bucket(dlv - 1, dlv) == 5
    assert _slice_bucket(dlv, dlv) is None
    assert _slice_bucket(start - 1, dlv) is None


def test_comparison_verdict_pass():
    cmp_ = _load(CMP)
    assert cmp_["verdict"] == "PASS"
    for k, v in cmp_["comparison_same_venue_exact_defs_bp"].items():
        assert abs(v["mean"]) <= 1.0, (k, v)
        assert v["worst_abs"] <= 3.0, (k, v)
