from __future__ import annotations

import argparse
import gc
import json
from datetime import datetime, timezone
from pathlib import Path

import torch  # Import before pandas on Windows to avoid a DLL load-order conflict.
import numpy as np
import pandas as pd

from agentic_alpha_lab.data.timeframes import resample_closed_ohlcv
from agentic_alpha_lab.models.kronos_adapter import KronosAdapter
from agentic_alpha_lab.signals.forecast_signal import forecast_to_signal, signal_dict


TIMEFRAMES = {
    "5m": {"rule": None, "lookback": 512, "horizon": 12, "horizon_label": "1 giờ"},
    "15m": {"rule": "15min", "lookback": 512, "horizon": 16, "horizon_label": "4 giờ"},
    "1h": {"rule": "1h", "lookback": 360, "horizon": 24, "horizon_label": "24 giờ"},
    "4h": {"rule": "4h", "lookback": 168, "horizon": 18, "horizon_label": "72 giờ"},
}


def _json_number(value: float) -> float:
    return float(np.asarray(value).item())


def _timeframe_frame(base: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    rule = TIMEFRAMES[timeframe]["rule"]
    if rule is None:
        return base.copy()
    return resample_closed_ohlcv(base, str(rule))


def _load_backtests(project_root: Path) -> list[dict[str, object]]:
    paths = [
        project_root / "reports/smoke/kronos_mini_256w_h12_s3_summary.json",
        project_root / "reports/smoke/kronos_small_256w_h12_s3_summary.json",
        project_root / "reports/smoke/kronos_base_256w_h12_s3_summary.json",
        project_root / "reports/mini_h12/kronos_mini_2706w_h12_s3_summary.json",
        project_root / "reports/mini_h48/validation_locked_test.json",
    ]
    rows: list[dict[str, object]] = []
    for path in paths:
        if not path.exists():
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        if path.name == "validation_locked_test.json":
            result = payload["locked_test"]
            rows.append(
                {
                    "label": "Mini · 4h locked test",
                    "return": result["total_return"],
                    "gross_pnl": result["gross_pnl"],
                    "fees": result["fees"],
                    "funding": result["funding"],
                    "trades": result["trades"],
                    "profit_factor": result["profit_factor"],
                    "status": "out_of_sample",
                }
            )
        else:
            result = payload["backtest"]
            horizon = payload["model"]["horizon"]
            rows.append(
                {
                    "label": f"{payload['variant'].title()} · {horizon * 5}m",
                    "return": result["total_return"],
                    "gross_pnl": result["gross_pnl"],
                    "fees": result["fees"],
                    "funding": result["funding"],
                    "trades": result["trades"],
                    "profit_factor": result["profit_factor"],
                    "status": "smoke" if payload["windows"] <= 256 else "research",
                }
            )
    return rows


def _load_leverage_experiment(project_root: Path) -> dict[str, object] | None:
    path = project_root / "reports/mini_h48/confidence_leverage.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate static multi-timeframe Kronos dashboard data")
    parser.add_argument("--variant", default="mini", choices=["mini", "small", "base"])
    parser.add_argument("--paths", type=int, default=16)
    parser.add_argument("--threshold-bps", type=float, default=12.0)
    parser.add_argument("--temperature", type=float, default=0.7)
    parser.add_argument("--top-p", type=float, default=0.9)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument(
        "--data",
        type=Path,
        default=Path("data/raw/binance_usdm/BTCUSDT/5m/klines.parquet"),
    )
    parser.add_argument("--kronos-repo", type=Path, default=Path("../Kronos"))
    parser.add_argument("--model-root", type=Path, default=Path("artifacts/models"))
    parser.add_argument("--output", type=Path, default=Path("web/app/dashboard-data.json"))
    parser.add_argument("--public-output", type=Path, default=Path("web/public/data/dashboard.json"))
    parser.add_argument("--artifact", type=Path, default=Path("artifacts/multitimeframe_forecast.json"))
    args = parser.parse_args()

    project_root = Path.cwd()
    base = pd.read_parquet(args.data).sort_values("open_time").reset_index(drop=True)
    base["open_time"] = pd.to_datetime(base["open_time"], utc=True)
    base["close_time"] = pd.to_datetime(base["close_time"], utc=True)
    adapter = KronosAdapter(args.variant, args.kronos_repo, args.device, args.model_root)
    results: list[dict[str, object]] = []

    for timeframe, spec in TIMEFRAMES.items():
        candles = _timeframe_frame(base, timeframe)
        lookback = min(int(spec["lookback"]), len(candles))
        if lookback < 64:
            raise ValueError(f"Not enough complete {timeframe} candles: {len(candles)}")
        context = candles.tail(lookback).copy()
        step = pd.Timedelta("5min" if timeframe == "5m" else str(spec["rule"]))
        first_future = pd.Timestamp(context["open_time"].iloc[-1]) + step
        future_times = pd.date_range(first_future, periods=int(spec["horizon"]), freq=step)
        predictions: list[pd.DataFrame] = []
        elapsed = 0.0

        for path_index in range(args.paths):
            seed = 17_000 + path_index
            torch.manual_seed(seed)
            if torch.cuda.is_available():
                torch.cuda.manual_seed_all(seed)
            prediction, summary = adapter.forecast(
                context,
                future_times,
                temperature=args.temperature,
                top_k=0,
                top_p=args.top_p,
                sample_count=1,
            )
            elapsed += summary.elapsed_seconds
            predictions.append(prediction.reset_index(drop=True))

        close_paths = np.stack([item["close"].to_numpy(float) for item in predictions])
        mean_prediction = pd.DataFrame(
            {
                column: np.mean(np.stack([item[column].to_numpy(float) for item in predictions]), axis=0)
                for column in ["open", "high", "low", "close", "volume", "amount"]
            },
            index=future_times,
        )
        signal = forecast_to_signal(
            candles,
            len(candles) - 1,
            mean_prediction,
            threshold_bps=args.threshold_bps,
        )
        current_close = float(context["close"].iloc[-1])
        final_closes = close_paths[:, -1]
        historical_closes = context["close"].tail(int(spec["horizon"]) + 1).to_numpy(float)
        recent_vol = float(np.std(np.diff(np.log(historical_closes))))
        path_vols = np.std(np.diff(np.log(np.maximum(close_paths, 1e-9)), axis=1), axis=1)

        history = [
            {
                "timestamp": pd.Timestamp(row.open_time).isoformat(),
                "close": _json_number(row.close),
                "high": _json_number(row.high),
                "low": _json_number(row.low),
                "volume": _json_number(row.volume),
            }
            for row in context.tail(120).itertuples(index=False)
        ]
        forecast = [
            {
                "timestamp": pd.Timestamp(timestamp).isoformat(),
                "mean": _json_number(np.mean(close_paths[:, index])),
                "p10": _json_number(np.quantile(close_paths[:, index], 0.10)),
                "p90": _json_number(np.quantile(close_paths[:, index], 0.90)),
            }
            for index, timestamp in enumerate(future_times)
        ]
        results.append(
            {
                "timeframe": timeframe,
                "horizon_label": spec["horizon_label"],
                "lookback_bars": lookback,
                "horizon_bars": int(spec["horizon"]),
                "as_of": pd.Timestamp(context["close_time"].iloc[-1]).isoformat(),
                "current_close": current_close,
                "upside_probability": _json_number(np.mean(final_closes > current_close)),
                "volatility_amplification_probability": _json_number(np.mean(path_vols > recent_vol)),
                "median_return": _json_number(np.median(final_closes) / current_close - 1.0),
                "mean_return": _json_number(np.mean(final_closes) / current_close - 1.0),
                "inference_seconds": elapsed,
                "signal": signal_dict(signal),
                "history": history,
                "forecast": forecast,
                "sample_paths": [
                    [_json_number(value) for value in path]
                    for path in close_paths[: min(5, len(close_paths))]
                ],
            }
        )
        print(
            f"{timeframe}: {signal.label}, upside={results[-1]['upside_probability']:.1%}, "
            f"mean_return={results[-1]['mean_return']:.2%}"
        )

    weights = {"5m": 0.10, "15m": 0.20, "1h": 0.30, "4h": 0.40}
    weighted_upside = sum(
        weights[str(item["timeframe"])] * float(item["upside_probability"]) for item in results
    )
    active_directions = [int(item["signal"]["direction"]) for item in results]
    agreement = max(active_directions.count(-1), active_directions.count(0), active_directions.count(1)) / len(results)
    consensus = "LONG" if weighted_upside >= 0.60 else "SHORT" if weighted_upside <= 0.40 else "MIXED"
    payload = {
        "research_only": True,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "market": "BTCUSDT Binance USD-M perpetual",
        "model": f"Kronos-{args.variant}",
        "sampling": {
            "paths": args.paths,
            "temperature": args.temperature,
            "top_p": args.top_p,
            "threshold_bps": args.threshold_bps,
        },
        "costs": {
            "entry_fee": 0.0002,
            "exit_fee": 0.0002,
            "long_funding_per_8h": 0.0001,
            "short_funding": 0.0,
        },
        "consensus": {
            "label": consensus,
            "weighted_upside_probability": weighted_upside,
            "agreement": agreement,
            "weights": weights,
            "warning": "Multi-timeframe zero-shot view; not validated as a combined trading strategy.",
        },
        "timeframes": results,
        "backtests": _load_backtests(project_root),
        "leverage_experiment": _load_leverage_experiment(project_root),
    }
    for output in [args.output, args.public_output, args.artifact]:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    del adapter
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()


if __name__ == "__main__":
    main()
