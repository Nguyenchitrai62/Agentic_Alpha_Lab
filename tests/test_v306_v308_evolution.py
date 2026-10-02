"""Light checks of the v306-v308 evolutionary searches (no data needed): genome encoding, seeds, kpack header, engine gov hook default."""
import importlib.util
from pathlib import Path

import pytest

RD = Path("research/parallel/rounds/parallel-20260906-r2")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.parametrize("path", ["v306/v306_walkforward_evolution.py", "v307/v307_manual_book_evolution.py",
                                  "v308/v308_manual_book_leverage_evolution.py", "v309/v309_manual_book_management_evolution.py",
                                  "v310/v310_manual_book_robust_evolution.py",
                                  "v313/v313_manual_book_gp_member_evolution.py"])
def test_genome_roundtrip_and_seeds(path):
    m = _load("evo_" + Path(path).stem, RD / path)
    for name, d in m.SEEDS.items():
        g = m.encode(d)
        assert m.valid(g), name
        assert m.encode(m.decode(g)) == g
        assert len(g) == len(m.GENES)
    assert len(set(m.encode(d) for d in m.SEEDS.values())) == len(m.SEEDS)  # seeds are distinct genomes


def test_v308_reference_seed_in_range():
    m = _load("evo_v308", RD / "v308/v308_manual_book_leverage_evolution.py")
    d = m.decode(m.encode(m.SEEDS["G2_manual"]))
    assert d["target"] == 0.25 and d["cap"] == 2.0 and d["gov"] == (0.20, 0.10) and d["short"] == 1.0 and d["be_off"] == 0.001


def test_kpack_header_and_gov_default():
    kp = _load("kpack_t", RD / "kpack/kpack.py")
    src = (RD / "engine_user/engine_user.py").read_text()
    assert kp.HEADER_OLD in src
    assert "gov=None" in src and "gz, gw = (0.20, 0.10) if gov is None else gov" in src
    assert "g[i] = float(np.clip((gz - (1 - eq[j] / peak)) / gw, 0.0, 1.0))" in src
