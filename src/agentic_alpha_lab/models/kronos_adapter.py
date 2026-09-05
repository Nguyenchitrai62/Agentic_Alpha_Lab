from __future__ import annotations

import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Sequence

import torch
import numpy as np
import pandas as pd


MODEL_SPECS = {
    "mini": {
        "model_id": "NeoQuasar/Kronos-mini",
        "tokenizer_id": "NeoQuasar/Kronos-Tokenizer-2k",
        "model_dir": "Kronos-mini",
        "tokenizer_dir": "Kronos-Tokenizer-2k",
        "max_context": 2048,
    },
    "small": {
        "model_id": "NeoQuasar/Kronos-small",
        "tokenizer_id": "NeoQuasar/Kronos-Tokenizer-base",
        "model_dir": "Kronos-small",
        "tokenizer_dir": "Kronos-Tokenizer-base",
        "max_context": 512,
    },
    "base": {
        "model_id": "NeoQuasar/Kronos-base",
        "tokenizer_id": "NeoQuasar/Kronos-Tokenizer-base",
        "model_dir": "Kronos-base",
        "tokenizer_dir": "Kronos-Tokenizer-base",
        "max_context": 512,
    },
}


@dataclass(frozen=True)
class ForecastSummary:
    variant: str
    as_of: str
    horizon_bars: int
    current_close: float
    predicted_close: float
    predicted_return: float
    predicted_path_low: float
    predicted_path_high: float
    direction: str
    elapsed_seconds: float
    peak_cuda_memory_mb: float


def _import_kronos(repo_path: Path):
    resolved = repo_path.resolve()
    if not (resolved / "model" / "kronos.py").exists():
        raise FileNotFoundError(f"Kronos repo not found at {resolved}")
    path = str(resolved)
    if path not in sys.path:
        sys.path.insert(0, path)
    from model import Kronos, KronosPredictor, KronosTokenizer

    return Kronos, KronosPredictor, KronosTokenizer


class KronosAdapter:
    def __init__(
        self,
        variant: str,
        repo_path: Path,
        device: str = "cuda:0",
        model_root: Path | None = Path("artifacts/models"),
    ) -> None:
        if variant not in MODEL_SPECS:
            raise ValueError(f"Unknown Kronos variant {variant!r}; choose {sorted(MODEL_SPECS)}")
        if device.startswith("cuda") and not torch.cuda.is_available():
            raise RuntimeError("CUDA requested but torch.cuda.is_available() is False")

        Kronos, KronosPredictor, KronosTokenizer = _import_kronos(repo_path)
        spec = MODEL_SPECS[variant]
        local_model = model_root / str(spec["model_dir"]) if model_root else None
        local_tokenizer = model_root / str(spec["tokenizer_dir"]) if model_root else None
        model_source = str(local_model.resolve()) if local_model and (local_model / "config.json").exists() else str(spec["model_id"])
        tokenizer_source = str(local_tokenizer.resolve()) if local_tokenizer and (local_tokenizer / "config.json").exists() else str(spec["tokenizer_id"])
        self.variant = variant
        self.device = device
        self.max_context = int(spec["max_context"])
        self.tokenizer = KronosTokenizer.from_pretrained(tokenizer_source)
        self.model = Kronos.from_pretrained(model_source)
        self.tokenizer.eval()
        self.model.eval()
        self.predictor = KronosPredictor(
            self.model,
            self.tokenizer,
            device=device,
            max_context=self.max_context,
        )

    @staticmethod
    def _features(frame: pd.DataFrame) -> pd.DataFrame:
        required = ["open", "high", "low", "close", "volume", "quote_volume"]
        missing = [column for column in required if column not in frame.columns]
        if missing:
            raise ValueError(f"Kline data is missing {missing}")
        result = frame[["open", "high", "low", "close", "volume", "quote_volume"]].copy()
        return result.rename(columns={"quote_volume": "amount"})

    def forecast(
        self,
        context: pd.DataFrame,
        future_timestamps: pd.Series | pd.DatetimeIndex,
        temperature: float = 0.6,
        top_k: int = 1,
        top_p: float = 1.0,
        sample_count: int = 1,
    ) -> tuple[pd.DataFrame, ForecastSummary]:
        horizon = len(future_timestamps)
        if horizon <= 0:
            raise ValueError("future_timestamps must not be empty")
        context = context.tail(self.max_context).copy()
        x_timestamp = context["open_time"].reset_index(drop=True)
        y_timestamp = pd.Series(future_timestamps).reset_index(drop=True)
        features = self._features(context).reset_index(drop=True)

        if self.device.startswith("cuda"):
            torch.cuda.empty_cache()
            torch.cuda.reset_peak_memory_stats()
        started = time.perf_counter()
        with torch.inference_mode():
            prediction = self.predictor.predict(
                df=features,
                x_timestamp=x_timestamp,
                y_timestamp=y_timestamp,
                pred_len=horizon,
                T=temperature,
                top_k=top_k,
                top_p=top_p,
                sample_count=sample_count,
                verbose=False,
            )
        if self.device.startswith("cuda"):
            torch.cuda.synchronize()
        elapsed = time.perf_counter() - started
        peak_mb = (
            torch.cuda.max_memory_allocated() / 1024**2
            if self.device.startswith("cuda")
            else 0.0
        )
        current_close = float(context["close"].iloc[-1])
        predicted_close = float(prediction["close"].iloc[-1])
        predicted_return = predicted_close / current_close - 1.0
        direction = "UP" if predicted_return > 0 else "DOWN" if predicted_return < 0 else "SIDEWAYS"
        summary = ForecastSummary(
            variant=self.variant,
            as_of=pd.Timestamp(context["close_time"].iloc[-1]).isoformat(),
            horizon_bars=horizon,
            current_close=current_close,
            predicted_close=predicted_close,
            predicted_return=predicted_return,
            predicted_path_low=float(prediction["low"].min()),
            predicted_path_high=float(prediction["high"].max()),
            direction=direction,
            elapsed_seconds=elapsed,
            peak_cuda_memory_mb=peak_mb,
        )
        return prediction, summary

    def forecast_batch(
        self,
        contexts: Sequence[pd.DataFrame],
        future_timestamps: Sequence[pd.Series | pd.DatetimeIndex],
        temperature: float = 0.6,
        top_k: int = 1,
        top_p: float = 1.0,
        sample_count: int = 1,
    ) -> list[pd.DataFrame]:
        if not contexts:
            return []
        trimmed = [context.tail(self.max_context).copy() for context in contexts]
        lengths = {len(context) for context in trimmed}
        if len(lengths) != 1:
            raise ValueError("All batch contexts must have equal length")
        pred_len = len(future_timestamps[0])
        if any(len(timestamps) != pred_len for timestamps in future_timestamps):
            raise ValueError("All future timestamp sequences must have equal length")

        with torch.inference_mode():
            return self.predictor.predict_batch(
                df_list=[self._features(context).reset_index(drop=True) for context in trimmed],
                x_timestamp_list=[context["open_time"].reset_index(drop=True) for context in trimmed],
                y_timestamp_list=[pd.Series(values).reset_index(drop=True) for values in future_timestamps],
                pred_len=pred_len,
                T=temperature,
                top_k=top_k,
                top_p=top_p,
                sample_count=sample_count,
                verbose=False,
            )


def summary_dict(summary: ForecastSummary) -> dict[str, object]:
    return asdict(summary)
