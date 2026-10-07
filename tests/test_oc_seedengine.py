"""Light audit for oc_seedengine (no engine replay here)."""
import json
import pickle
from pathlib import Path

import pandas as pd

HERE = Path("research/diagnostics/oc_seedengine")
SEEDS = (0, 101, 202, 303, 404)


def test_build_gate():
    info = json.loads((HERE / "build_info.json").read_text())
    assert info["repro_ok"] is True
    for s in ("0", "1", "2", "3"):
        r = info["repro_per_phase"][s]
        assert r["ref_rows"] == 273850 and r["mine_rows"] == 273850
        assert r["overlap"] == 273850 and r["ref_only"] == 0 and r["mine_only"] == 0
        assert r["size_match"] >= 0.999 and r["tp_match"] >= 0.999


def test_table_schema():
    for s in SEEDS:
        for p in range(4):
            t = pd.read_parquet(HERE / f"seed_table_s{s}_p{p}.parquet")
            assert list(t.columns) == ["T", "sym", "rung", "size", "tp"]
            assert len(t) == 273850
            assert set(t["size"].unique()) <= {0.5, 1.0, 1.5}
            assert set(t["tp"].unique()) <= {0.5, 1.0, 1.5}
            assert set(t["sym"].unique()) == {"BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"}
            assert set(t["rung"].unique()) == {0, 1, 2, 3, 4}


def test_runs_present():
    for s in (101, 202, 303, 404):
        runs = pickle.loads((HERE / f"seed_runs_s{s}.pkl").read_bytes())
        assert sorted(runs) == [0, 1, 2, 3]
        for sh, r in runs.items():
            assert len(r["eq"]) > 10000
            assert all(v == v and v > 0 for v in r["eq"])


def test_results_consistency():
    res = json.loads((HERE / "results.json").read_text())
    assert res["row"] == "R2B1D17BFG2" and res["build_repro_ok"] is True
    assert sorted(int(k) for k in res["per_seed"]) == [0, 101, 202, 303, 404]
    for s in ("0", "101", "202", "303", "404"):
        m = res["per_seed"][s]
        assert len(m["years"]) == 5 and m["losing"] == 0
        assert m["W"] == min(y["R"] for y in m["years"])
    # 2021 zero dispersion (deterministic jj=0 fits)
    r2021 = {res["per_seed"][s]["years"][0]["R"] for s in res["per_seed"]}
    assert len(r2021) == 1
    # deployed matches v421 cache row
    v421 = json.load(open("research/parallel/rounds/parallel-20260906-r2/v421/v421_result.json"))
    dep = v421["rows"]["R2B1D17BFG2"]
    assert abs(res["per_seed"]["0"]["R"] - dep["R"]) < 1e-9
    assert [y["R"] for y in res["per_seed"]["0"]["years"]] == [y[0] for y in dep["years"]]
    # distribution: tight seed noise, deployed near mean
    d = res["distribution_5_seeds"]["R"]
    assert abs(d["mean"] - 5.387) < 0.01 and d["std"] < 0.1
    assert d["deployed_rank"] == 2 and abs(d["deployed_minus_mean"] - 0.023) < 0.01
