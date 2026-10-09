"""oc_shortmember: retrain the whale-flow book member on a SHORT-horizon label.

Per PLAN.md (pre-registered 2026-10-07, read it first). Steps:
  --check : rebuild deployed A/Aq exactly (v240 logic) and require
            Spearman(repro, cache) >= 0.999 per anchor year for both.
  --train : retrain annual+quarterly members with the label horizon replaced
            by hnew (6 or 18), same normalisation as y42 (v287 precedent:
            every return target replaced, filters/embargoes unchanged).
  --ic    : pooled member IC table (A vs AS6 vs AS18) at h={1,6,18,42}
            vs bookichorizon-style targets (descriptive, no selection).

HEAVY (HGB training): run via
  .venv/Scripts/python.exe scripts/heavy_slot.py run --tag oc_shortmember --min-free-gb 2.0 -- <this> ...
Writes ONLY inside research/tournament/oc_shortmatter (this folder).
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
RD = ROOT / "research/parallel/rounds/parallel-20260906-r2"
CACHE = ROOT / "artifacts/research/engine_real"
SYMS = ["BNBUSDT", "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]
ANCHORS = [pd.Timestamp(f"{y}-09-24", tz="UTC") for y in (2021, 2022, 2023, 2024, 2025)]
YEAR = pd.Timedelta(days=365)
YLABELS = [f"{y}-09-24" for y in (2021, 2022, 2023, 2024, 2025)]
H_IC = (1, 6, 18, 42)

_uid = [0]


def log(msg: str) -> None:
    print(f"[{datetime.now(timezone.utc):%H:%M:%S}] oc_shortmember: {msg}", flush=True)


def _load(name: str, path) -> object:
    _uid[0] += 1
    modname = f"{name}_{_uid[0]}"
    spec = importlib.util.spec_from_file_location(modname, str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[modname] = mod
    spec.loader.exec_module(mod)
    return mod


def relabel_y(panel: pd.DataFrame, hnew: int) -> pd.DataFrame:
    """Replace every return target (y, y6, y18, y42, y84) by y_hnew.

    y_hnew = clip(log(open[t+1+hnew]/open[t+1]) / (vol42*sqrt(hnew)), -4, +4),
    per symbol on time-sorted rows (v92/v94/v103 formula with H=hnew).
    """
    out = []
    for s, g in panel.groupby("sym", sort=False):
        g = g.sort_values("t").copy()
        o = g["open"].to_numpy(dtype=float)
        v = g["vol42"].to_numpy(dtype=float)
        n = len(g)
        fwd = np.full(n, np.nan)
        if n - 1 - hnew > 0:
            with np.errstate(divide="ignore", invalid="ignore"):
                fwd[: n - 1 - hnew] = np.log(o[1 + hnew:] / o[1: n - hnew])
        with np.errstate(divide="ignore", invalid="ignore"):
            ynew = np.clip(fwd / (v * np.sqrt(hnew)), -4, 4)
        ynew[~np.isfinite(ynew)] = np.nan
        g["y"] = ynew
        for col in ("y6", "y18", "y42", "y84"):
            if col in g.columns:
                g[col] = ynew
        out.append(g)
    return pd.concat(out, ignore_index=True)


def build_member(quarterly: bool, hnew: int | None):
    """Reproduce v240.build_member(quarterly, keep_fills=False); if hnew is
    not None, replace every return target by y_hnew (v287 precedent)."""
    tag = f"{'q' if quarterly else 'a'}_{hnew if hnew is not None else 'orig'}"
    v202 = _load(f"v202_shm_{tag}", RD / "v202/v202_quarterly_retrain.py")
    v144 = _load(f"v144_shm_{tag}", RD / "v144/v144_deploy_v3.py")
    if quarterly:
        v202.quarterly(v144)
    ext, v103 = v144.v115.v114.v113, v144.v103
    ext.cb_bars = v144.v115.v114.cb_bars_ext
    v144.v115.v114.v113.cb_bars = v144.v115.v114.cb_bars_ext
    ext.v92.load_asset = ext.load_asset_ext
    v240 = _load(f"v240_shm_{tag}", RD / "v240/v240_order_level_flow.py")
    b92, b103, orig_vp = ext.v92.build, v103.build, v144.v129.vol_predict
    log(f"building base92 panel ({tag}) ...")
    base92 = b92()
    log(f"base92 ({tag}): {base92.shape}")
    xf = v240.feature_frame(ext.v92.load_asset, False)
    log(f"order-flow xf ({tag}): {xf.shape}")
    drop = {c for c in xf.columns if c not in ("t", "sym")}
    v144.v129.vol_predict = (
        lambda panel, fs, anchors, emb: orig_vp(panel, [c for c in fs if c not in drop], anchors, emb)
    )
    if hnew is None:
        ext.v92.build = lambda: base92.merge(xf, on=["t", "sym"], how="left")
        v103.build = lambda: b103().merge(xf, on=["t", "sym"], how="left")
    else:
        add94 = ext.v94.add_targets
        ext.v92.build = lambda: relabel_y(base92.merge(xf, on=["t", "sym"], how="left"), hnew)
        ext.v94.add_targets = lambda p: relabel_y(add94(p), hnew)
        v103.build = lambda: relabel_y(b103().merge(xf, on=["t", "sym"], how="left"), hnew)
    log(f"training books_v142 ({tag}; quarterly={quarterly}, hnew={hnew}) ...")
    t0 = time.time()
    books = v144.books_v142()[1]
    log(f"books ({tag}) done: {books.shape} in {time.time() - t0:.0f}s")
    return books


def spearman_per_year(repro: pd.DataFrame, ref: pd.DataFrame, grid: pd.DatetimeIndex) -> dict:
    a = repro.reindex(grid).fillna(0.0)
    b = ref.reindex(grid).fillna(0.0)
    out = {}
    for ylab, a0 in zip(YLABELS, ANCHORS):
        m = (grid >= a0) & (grid < a0 + YEAR)
        x = a.loc[m].stack()
        yy = b.loc[m].stack()
        c = float(pd.DataFrame({"x": x, "y": yy}).corr(method="spearman").iloc[0, 1])
        out[ylab] = round(c, 6)
    return out


def cmd_check() -> None:
    eu = _load("eu_shm_check", RD / "engine_user/engine_user.py")
    books154, _ = eu.er.v154_books()
    grid = books154.index
    ok = True
    for name, q, cache_f in (("A", False, "member_A_O1_orders.parquet"),
                             ("Aq", True, "member_Aq_O1_orders.parquet")):
        repro = build_member(q, None)
        ref = pd.read_parquet(CACHE / cache_f)
        per = spearman_per_year(repro, ref, grid)
        for ylab, c in per.items():
            flag = "OK" if c >= 0.999 else "FAIL"
            if c < 0.999:
                ok = False
            log(f"builder check {name} year {ylab}: Spearman={c:.6f} [{flag}]")
        (HERE / "tmp" / f"repro_{name}.parquet").unlink(missing_ok=True)
    res = {"builder_check": "pass" if ok else "FAIL"}
    (HERE / "tmp" / "builder_check.json").write_text(json.dumps(res, indent=1))
    if not ok:
        log("BUILDER CHECK FAILED: stop and report (no training, no engine).")
        raise SystemExit(1)
    log("builder check PASS (>= 0.999 every anchor year for A and Aq).")


def cmd_train(hnew: int) -> None:
    chk = json.loads((HERE / "tmp" / "builder_check.json").read_text())
    assert chk.get("builder_check") == "pass", "run --check (pass) before --train"
    for name, q in ((f"AS{hnew}", False), (f"AS{hnew}q", True)):
        out = HERE / f"member_{name}.parquet"
        if out.exists():
            log(f"{name} exists, skip ({out})")
            continue
        books = build_member(q, hnew)
        books.index.name = "t"
        books.to_parquet(out)
        log(f"wrote {out} {books.shape}")


def cmd_ic() -> None:
    members = {}
    eu = _load("eu_shm_ic", RD / "engine_user/engine_user.py")
    books154, _ = eu.er.v154_books()
    grid = books154.index.sort_values()
    members["A"] = pd.read_parquet(CACHE / "member_A_O1_orders.parquet").reindex(grid).fillna(0.0)
    for hnew in (6, 18):
        f = HERE / f"member_AS{hnew}.parquet"
        assert f.exists(), f"missing {f}; run --train {hnew} first"
        members[f"AS{hnew}"] = pd.read_parquet(f).reindex(grid).fillna(0.0)
    opens_full = pd.read_parquet(CACHE / "opens_v154.parquet")[SYMS].sort_index()
    r1 = opens_full / opens_full.shift(1) - 1.0
    sigma_full = r1.rolling(360, min_periods=120).std(ddof=1)
    sigma = sigma_full.reindex(grid)
    rows = []
    for h in H_IC:
        ahead = grid + pd.Timedelta(hours=4 * h)
        fh = (opens_full.reindex(ahead).to_numpy() / opens_full.reindex(grid).to_numpy() - 1.0)
        with np.errstate(divide="ignore", invalid="ignore"):
            yh = fh / sigma.to_numpy()
        yh = pd.DataFrame(yh, index=grid, columns=SYMS)
        yh[(sigma.isna()) | (sigma <= 0) | (~np.isfinite(fh))] = np.nan
        for ylab, a0 in zip(YLABELS, ANCHORS):
            m = (grid >= a0) & (grid < a0 + YEAR)
            for sname, P in members.items():
                pv = P.loc[m].to_numpy(dtype=float).ravel()
                yv = yh.loc[m].to_numpy(dtype=float).ravel()
                mm = np.isfinite(pv) & np.isfinite(yv)
                pv, yv = pv[mm], yv[mm]
                if len(pv) < 3 or np.std(pv) == 0 or np.std(yv) == 0:
                    ic = None
                else:
                    ic = round(float(pd.Series(pv).corr(pd.Series(yv), method="spearman")), 4)
                rows.append({"member": sname, "year": ylab, "h": h, "pooled_ic": ic, "n": int(mm.sum())})
            log(f"ic h={h} year={ylab} done")
    (HERE / "tmp" / "member_ic.json").write_text(json.dumps(rows, indent=1))
    log(f"wrote tmp/member_ic.json rows={len(rows)}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--train", type=int, default=None)
    ap.add_argument("--ic", action="store_true")
    a = ap.parse_args()
    (HERE / "tmp").mkdir(exist_ok=True)
    if a.check:
        cmd_check()
    elif a.train is not None:
        assert a.train in (6, 18)
        cmd_train(a.train)
    elif a.ic:
        cmd_ic()
    else:
        raise SystemExit("pass --check, --train 6|18, or --ic")


if __name__ == "__main__":
    main()
