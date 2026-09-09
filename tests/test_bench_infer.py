"""Tests for scripts/opencode_bench_infer.py (synthetic tiny model only).

Local inference harness test: no training, no cloud, no orders.
Loads the CLI module once and calls run_bench() on tmp ckpt dirs.
"""

import torch  # must precede pandas on Windows (c10.dll load order)

import importlib.util
import json
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def load_bench():
    spec = importlib.util.spec_from_file_location(
        "opencode_bench_infer", SCRIPTS / "opencode_bench_infer.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


BENCH = load_bench()

REQUIRED_KEYS = {"harness", "ckpt", "weights", "device", "cuda_available",
                 "torch_version", "arch", "in_features", "params",
                 "precision", "load_ms", "latency_ms", "throughput_wps",
                 "vram_peak_mb", "parity", "runs", "warmup", "timestamp_utc"}


def make_tiny_ckpt(d: Path, in_features=8, hidden=16, out=6) -> Path:
    from safetensors.torch import save_file
    d.mkdir(parents=True, exist_ok=True)
    torch.manual_seed(0)
    model = BENCH._TinyMLP(in_features, hidden, out)
    (d / "bench_config.json").write_text(json.dumps(
        {"arch": "tiny_mlp", "in_features": in_features,
         "hidden": hidden, "out": out}), encoding="utf-8")
    save_file(dict(model.state_dict()), str(d / "model.safetensors"))
    return d


def test_report_schema_and_reload_parity(tmp_path):
    ckpt = make_tiny_ckpt(tmp_path / "ckpt")
    out = tmp_path / "report.json"
    rep = BENCH.run_bench(ckpt, out, runs=10, warmup=2, device_name="cpu")
    assert REQUIRED_KEYS.issubset(rep.keys())
    assert rep["arch"] == "tiny_mlp"
    assert rep["params"] == 8 * 16 + 16 + 16 * 6 + 6
    assert rep["load_ms"] > 0
    for b in ("1", "8", "32"):
        assert rep["latency_ms"][b]["median_ms"] > 0
        assert rep["throughput_wps"][b] > 0
    assert rep["vram_peak_mb"] == 0.0  # cpu
    assert rep["parity"]["mode"] == "reload"
    assert rep["parity"]["max_abs_diff"] == pytest.approx(0.0, abs=1e-6)
    assert rep["parity"]["pass"] is True
    assert json.loads(out.read_text(encoding="utf-8"))["parity"]["pass"] is True


def test_reference_parity_pass_and_fail(tmp_path):
    import numpy as np
    ckpt = make_tiny_ckpt(tmp_path / "ckpt")
    device = torch.device("cpu")
    model, info, _ = BENCH.load_checkpoint(ckpt, device)
    g = torch.Generator(device="cpu").manual_seed(0)
    x = torch.randn(32, info["in_features"], generator=g, dtype=torch.float32)
    with torch.no_grad():
        good = BENCH._first_output(model(x)).float().cpu().numpy()
    ref_ok = tmp_path / "ref.npy"
    np.save(str(ref_ok), good)
    out = tmp_path / "r_ok.json"
    rep = BENCH.run_bench(ckpt, out, ref=str(ref_ok), runs=5, warmup=1, device_name="cpu")
    assert rep["parity"]["mode"] == "reference"
    assert rep["parity"]["pass"] is True

    ref_bad = tmp_path / "ref_bad.npy"
    np.save(str(ref_bad), good + 1.0)
    rep2 = BENCH.run_bench(ckpt, tmp_path / "r_bad.json", ref=str(ref_bad),
                           runs=5, warmup=1, device_name="cpu")
    assert rep2["parity"]["pass"] is False
    assert rep2["parity"]["max_abs_diff"] == pytest.approx(1.0, abs=1e-4)


def test_refuses_overwrite_and_rejects_unknown_layout(tmp_path):
    ckpt = make_tiny_ckpt(tmp_path / "ckpt")
    out = tmp_path / "report.json"
    BENCH.run_bench(ckpt, out, runs=2, warmup=1, device_name="cpu")
    with pytest.raises(FileExistsError):
        BENCH.run_bench(ckpt, out, runs=2, warmup=1, device_name="cpu")
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(FileNotFoundError):
        BENCH.run_bench(empty, tmp_path / "never.json", runs=2, warmup=1,
                        device_name="cpu")
