"""kpack: run the evolutionary searches (v306+) on Kaggle CPU kernels with the SAME audited engine and inputs (no new data, no new fits).

build(out): writes a self-contained pack
  prep.npz            engine_user.prepare(v154 books, opens) arrays (O/H/L/C 1m cubes float32 as produced locally, sig4, o1, o2, settle, sig1h)
  books154.parquet, opens.parquet, consts.json (v99.W_BOOKS, v110.START / END, PD, ANCHORS, v216.GRID, v221.KW, fees)
  cache/              every artifacts/research/engine_real/*.parquet (walk-forward member books, v306 gene tables)
  engine_standalone.py = engine_user.py with the module loads replaced by the pack constants (simulate / summarize unchanged)
fake_v221(pack): a namespace with the attributes v306 / v307 read from v221 (eu.simulate, eu.prepare -> loaded prep, eu.er.v154_books,
  eu.er.CACHE, eu.ANCHORS, eu.MAKER / TAKER / FUND_LONG, v216.GRID, KW). The runs assert the local reference rows (G2 6.504, manual 2.502),
  so any difference of the Kaggle environment stops the run.
  python research/parallel/rounds/parallel-20260906-r2/kpack/kpack.py build <out_dir>
"""
from __future__ import annotations

import importlib.util
import json
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
RD = HERE.parent
HEADER_OLD = '''er = _load("engine_real_u", HERE.parent / "engine_real/engine_real.py")
v172 = _load("v172_u", HERE.parent / "v172/v172_sleeve_realistic.py")
v99, v110, PD = er.v99, er.v110, er.PD
ANCHORS = er.v92.ANCHORS
'''
HEADER_NEW = '''import json as _json
import os as _os
from types import SimpleNamespace as _NS
_C = _json.loads((Path(_os.environ["KPACK"]) / "consts.json").read_text())
v99 = _NS(W_BOOKS=_C["W_BOOKS"])
v110 = _NS(START=pd.Timestamp(_C["START"]), END=pd.Timestamp(_C["END"]))
PD = _C["PD"]
ANCHORS = tuple(_C["ANCHORS"])
'''


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def build(out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    v221 = _load("v221", RD / "v221/v221_grid_hysteresis.py")
    eu = v221.eu
    books154, opens = eu.er.v154_books()
    prep = eu.prepare(books154, opens)
    np.savez(out / "prep.npz", **{k: prep[k] for k in ("O", "H", "L", "C", "sig4", "o1", "o2", "settle", "sig1h")})
    books154.to_parquet(out / "books154.parquet")
    opens.to_parquet(out / "opens.parquet")
    consts = dict(W_BOOKS=float(eu.v99.W_BOOKS), START=str(eu.v110.START), END=str(eu.v110.END), PD=int(eu.PD), ANCHORS=list(eu.ANCHORS),
                  GRID=v221.v216.GRID, KW={k: (list(v) if isinstance(v, tuple) else v) for k, v in v221.KW.items()},
                  MAKER=eu.MAKER, TAKER=eu.TAKER, FUND_LONG=eu.FUND_LONG)
    (out / "consts.json").write_text(json.dumps(consts, indent=1))
    (out / "cache").mkdir(exist_ok=True)
    for f in sorted(eu.er.CACHE.glob("*.parquet")):
        shutil.copy2(f, out / "cache" / f.name)
    src = (RD / "engine_user/engine_user.py").read_text()
    assert HEADER_OLD in src
    (out / "engine_standalone.py").write_text(src.replace(HEADER_OLD, HEADER_NEW))
    print("pack written", out, sum(p.stat().st_size for p in out.rglob("*") if p.is_file()) / 1e6, "MB")


def fake_v221(pack):
    pack = Path(pack)
    import os
    os.environ["KPACK"] = str(pack)
    eng = _load("engine_standalone", pack / "engine_standalone.py")
    C = json.loads((pack / "consts.json").read_text())
    books154, opens = pd.read_parquet(pack / "books154.parquet"), pd.read_parquet(pack / "opens.parquet")
    z = np.load(pack / "prep.npz")
    prep = dict(idx=books154.index, cols=list(books154.columns), **{k: z[k] for k in z.files})
    er = SimpleNamespace(CACHE=pack / "cache", v154_books=lambda: (books154, opens))
    eu = SimpleNamespace(simulate=eng.simulate, summarize=eng.summarize, prepare=lambda b, o: prep, er=er, ANCHORS=tuple(C["ANCHORS"]),
                         MAKER=C["MAKER"], TAKER=C["TAKER"], FUND_LONG=C["FUND_LONG"])
    kw = {k: (tuple(v) if isinstance(v, list) else v) for k, v in C["KW"].items()}
    return SimpleNamespace(eu=eu, v216=SimpleNamespace(GRID=C["GRID"]), KW=kw)


if __name__ == "__main__":
    if sys.argv[1] == "build":
        build(sys.argv[2])
