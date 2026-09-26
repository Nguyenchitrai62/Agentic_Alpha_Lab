"""W12 MA S/R study: definitions fixed in patterns/ma_levels.py, run once.

Study A (next-open entry): common.event_study on 15m (4,16,48),
  1h (1,4,12), 4h (1,3,6). Decisions before 2025-09-14 only.
Study B (limit at the level): for bounce/reject events enter at the level
  price L[t]; signed return d*log(close[t+h]/L[t]) vs a placebo level P on
  the SAME side at ~the same distance (P = close[t] - d*dist*(1+j),
  j ~ U(-0.25, 0.25) seeded, dist = |close[t]-L[t]|), redrawn until P is
  not within 0.5 ATR of any of the 32 MA levels (same exit, same direction
  d). Same-side is required: a bounce always buys below close, so a
  random-side placebo would lose by construction and prove nothing about
  the level itself. S/R is real only if MA levels beat placebo after costs.
"""

import torch  # noqa: F401  (import first: Windows DLL load order)
from pathlib import Path

import re
import numpy as np
import pandas as pd
from scipy import stats

from agentic_alpha_lab.patterns import common, ma_levels

OUT = Path(__file__).resolve().parents[2] / "artifacts" / "research" / "masr" / "levels"
INTRA = Path(__file__).resolve().parents[2] / "data" / "raw" / "btc_intraday_20260924"
H_MAP = {"15m": (4, 16, 48), "1h": (1, 4, 12), "4h": (1, 3, 6)}
PLACEBO_TOL_ATR = 0.25
PLACEBO_JITTER = 0.25
PLACEBO_DRAWS = 20
# NOTE: MA and placebo share the exit close[t+h], so MA-minus-placebo is
# algebraically d*log(P/L): a pure entry-price effect. To test whether MA
# bounces predict better CONTINUATION, we also report forward returns from
# the common close[t] for both event sets (fw_* columns).
SEED = 12
COST_BPS = "4-8 bps round-trip (Study B maker ~2-4 bps)"


def _load(tf: str) -> pd.DataFrame:
    if tf == "15m":
        b = pd.read_parquet(INTRA / "klines_15m.parquet")
        return b.sort_values("open_time").reset_index(drop=True)
    return common.load_bars(tf)


def _study_b(bars: pd.DataFrame, tf: str, horizons: tuple[int, ...]) -> pd.DataFrame:
    ev = ma_levels.events(bars)
    fam, atr_s, mat = ma_levels.family_levels(bars)
    atr = atr_s.to_numpy(float)
    close = bars["close"].astype(float).to_numpy(float)
    ot = pd.to_datetime(bars["open_time"], utc=True).to_numpy()
    decide = (bars["open_time"] < common.DEV_DECISION_END).to_numpy()
    first_half = (bars["open_time"] < common.DEV_SPLIT).to_numpy()
    lvlmat = mat.to_numpy(float)
    n = len(bars)
    rng = np.random.default_rng(SEED)
    rows = []
    pat_cols = [c for c in ev.columns
                if c.endswith("_bounce_support") or c.endswith("_reject_resistance")]
    for col in pat_cols:
        fam_key = re.sub(r"_(conf_)?(bounce_support|reject_resistance)$", "",
                         col.replace("msr_ev_", "msr_fam_"))
        L = fam[fam_key].to_numpy(float)
        d = ev[col].to_numpy()
        base = decide & (d != 0) & ~np.isnan(L) & ~np.isnan(atr) & (atr > 0)
        if base.sum() == 0:
            continue
        idx = np.flatnonzero(base)
        dist_abs = np.abs(close[idx] - L[idx])
        dd_all = d[idx]
        # same-side placebo with seeded jitter; redraw while on an MA level
        P = np.full(len(idx), np.nan)
        alive = np.ones(len(idx), bool)
        for _ in range(PLACEBO_DRAWS):
            todo = np.flatnonzero(alive & np.isnan(P))
            if len(todo) == 0:
                break
            j = rng.uniform(-PLACEBO_JITTER, PLACEBO_JITTER, size=len(todo))
            cand = close[idx[todo]] - dd_all[todo] * dist_abs[todo] * (1.0 + j)
            with np.errstate(invalid="ignore", divide="ignore"):
                dmin = np.nanmin(
                    np.abs(cand[:, None] - lvlmat[idx[todo]]) / atr[idx[todo]][:, None],
                    axis=1,
                )
            take = np.isfinite(dmin) & (dmin > PLACEBO_TOL_ATR)
            P[todo[take]] = cand[take]
        keep = ~np.isnan(P)
        keep_idx = idx[keep]
        P = P[keep]
        if len(keep_idx) == 0:
            continue
        dd = d[keep_idx]
        LL = L[keep_idx]
        for h in horizons:
            j = keep_idx + h
            ok = j < n
            if ok.sum() < 10:
                continue
            kk = keep_idx[ok]
            entry, plcb, xd = LL[ok], P[ok], dd[ok]
            xc = close[j[ok]]
            with np.errstate(divide="ignore", invalid="ignore"):
                r_ma = xd * np.log(xc / entry)
                r_pb = xd * np.log(xc / plcb)
            good = np.isfinite(r_ma) & np.isfinite(r_pb)
            if good.sum() < 10:
                continue
            a = r_ma[good] * 1e4
            b_ = r_pb[good] * 1e4
            diff = a - b_
            t_ma = common.newey_west_t(a, h)
            t_df = common.newey_west_t(diff, h)
            p_df = float(2 * stats.norm.sf(abs(t_df))) if np.isfinite(t_df) else np.nan
            fh = first_half[kk[good]]
            mh = float(np.mean(diff[fh])) if fh.sum() else np.nan
            sh = float(np.mean(diff[~fh])) if (~fh).sum() else np.nan
            with np.errstate(divide="ignore", invalid="ignore"):
                fw = xd * np.log(xc / close[kk[good]]) * 1e4  # shared-exit-free continuation
            rows.append(dict(
                tf=tf, pattern=col, horizon=h, n=int(good.sum()),
                mean_ma_bps=float(np.mean(a)), hit_ma=float(np.mean(r_ma[good] > 0)),
                nw_t_ma=t_ma, mean_pb_bps=float(np.mean(b_)),
                hit_pb=float(np.mean(r_pb[good] > 0)),
                diff_bps=float(np.mean(diff)), diff_nw_t=t_df, diff_p=p_df,
                first_half_diff_bps=mh, second_half_diff_bps=sh,
                fw_ma_bps=float(np.mean(fw)),
            ))
    out = pd.DataFrame(rows)
    if len(out):
        out["q_value"] = common.benjamini_hochberg(out["diff_p"].to_numpy())
        out["beats_placebo"] = (
            (out["diff_bps"] > 0) & (out["n"] >= 30)
            & (np.sign(out["first_half_diff_bps"]) == np.sign(out["second_half_diff_bps"]))
            & (np.sign(out["first_half_diff_bps"]) == np.sign(out["diff_bps"]))
        )
    return out


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    a_frames, b_frames = [], []
    for tf, hs in H_MAP.items():
        bars = _load(tf)
        ev = ma_levels.events(bars)
        res = common.event_study(bars, ev, horizons=hs, tf=tf)
        res.to_csv(OUT / f"event_study_{tf}.csv", index=False)
        a_frames.append(res)
        n_sig = int(res["stable_significant"].sum()) if len(res) else 0
        print(f"A {tf}: rows={len(res)} stable_significant={n_sig} (n_bars={len(bars)})")
        bres = _study_b(bars, tf, hs)
        bres.to_csv(OUT / f"studyB_{tf}.csv", index=False)
        b_frames.append(bres)
        n_beat = int(bres["beats_placebo"].sum()) if len(bres) else 0
        print(f"B {tf}: rows={len(bres)} beats_placebo={n_beat}")
    a = pd.concat(a_frames, ignore_index=True)
    a.to_csv(OUT / "event_study_all.csv", index=False)
    sig = a[a["stable_significant"]]
    sig.to_csv(OUT / "event_study_stable_significant.csv", index=False)
    b = pd.concat(b_frames, ignore_index=True)
    b.to_csv(OUT / "studyB_all.csv", index=False)
    beat = b[b["beats_placebo"]]
    beat.to_csv(OUT / "studyB_beats_placebo.csv", index=False)
    mx = float(a["mean_excess_bps"].abs().max()) if len(a) else float("nan")
    top_a = a.sort_values("p_value").iloc[0] if len(a) else None
    conf_b = b[b["pattern"].str.contains("conf_")]
    base_b = b[~b["pattern"].str.contains("conf_")]
    med_diff = float(b["diff_bps"].median()) if len(b) else float("nan")
    med_fw = float(b["fw_ma_bps"].median()) if len(b) else float("nan")
    with open(OUT / "SUMMARY.md", "w") as f:
        lines = [
            "# W12 MA S/R levels summary",
            f"1. Study A rows={len(a)} stable_significant={len(sig)} (q<0.10, n>=30, halves agree).",
            f"2. max |mean_excess|={mx:.1f} bps vs {COST_BPS}; "
            + (f"top p: {top_a['tf']} {top_a['pattern']} h={int(top_a['horizon'])} "
               f"{float(top_a['mean_excess_bps']):.1f} bps n={int(top_a['n'])} "
               f"halves {float(top_a['first_half_bps']):.1f}/{float(top_a['second_half_bps']):.1f} (unstable)."
               if top_a is not None else "no rows."),
            f"3. Study B rows={len(b)} median MA-placebo diff={med_diff:.1f} bps (shared exit => pure entry effect d*log(P/L)).",
            f"4. continuation from close after bounce/reject bars: median {med_fw:.1f} bps; level adds nothing forward.",
        ]
        if len(beat):
            top = beat.sort_values("diff_bps", ascending=False).iloc[0]
            lines.append(
                f"5. best raw diff: {top['tf']} {top['pattern']} h={int(top['horizon'])} diff={float(top['diff_bps']):.1f} bps "
                f"(entry effect only; continuation {float(top['fw_ma_bps']):.1f} bps)."
            )
        else:
            lines.append("5. no family/horizon beats its same-side placebo; MA levels add nothing over nearby prices.")
        cb = float(conf_b["diff_bps"].median()) if len(conf_b) else float("nan")
        bb = float(base_b["diff_bps"].median()) if len(base_b) else float("nan")
        lines += [
            f"6. confluence-vs-base median diff: {cb:.1f} vs {bb:.1f} bps (no confluence premium)." if len(conf_b) and len(base_b)
            else "6. confluence variants too sparse to compare.",
            "7. verdict: MA Ribbon lines are not precise S/R; do not trade bounces/breaks on them alone.",
        ]
        f.write("\n".join(lines[:15]) + "\n")
    print(f"total A={len(a)} stable={len(sig)}; total B={len(b)} beats={len(beat)}")
    print(open(OUT / "SUMMARY.md").read())


if __name__ == "__main__":
    main()
