from dataclasses import dataclass
from typing import Optional
import time
from collections import deque

import numpy as np


@dataclass
class EMGConfig:
    baseline_window: float = 1.0      # seconds for baseline estimate
    rms_window: float = 0.2           # seconds for RMS computation
    max_range: float = 65535.0         # adjustable EMG max range (raw units)
    rms_method: str = "sliding_window"  # "sliding_window" or "ema" (Exponential Moving Average)
    ema_alpha: float = 0.1            # EMA smoothing factor (0-1), lower = more smoothing


class EMGProcessor:
    """
    EMG processor computing RMS using either sliding window or Exponential Moving Average (EMA).

    Steps:
    - Maintain fixed-time sample buffer
    - Estimate baseline over baseline_window (median)
    - Compute RMS using either:
      * Sliding window: RMS of baseline-subtracted samples over rms_window
      * EMA: Exponential moving average of RMS values
    - Normalize to 0..1 using max_range config
    """

    def __init__(self, cfg: Optional[EMGConfig] = None):
        self.cfg = cfg or EMGConfig()
        self._samples: deque[tuple[float, float]] = deque()  # (timestamp, raw)
        self._last_norm: float = 0.0
        self._last_rms: float = 0.0
        self._ema_rms: float = 0.0  # Current EMA RMS value

    def set_max_range(self, value: float):
        self.cfg.max_range = max(1.0, float(value))

    def update(self, raw_value: float) -> float:
        """Update with a single sample (legacy method, use update_batch for packet processing)."""
        return self.update_batch([raw_value])

    def update_batch(self, raw_samples: list[float]) -> float:
        """
        Update with a batch of samples (e.g., all samples from one packet).
        Computes RMS on the batch, then applies exponential moving average filtering.
        
        Args:
            raw_samples: List of raw EMG sample values from one packet
            
        Returns:
            Normalized EMG value (0..1)
        """
        now = time.time()
        
        # Add all samples to the buffer with the same timestamp (they're from the same packet)
        for raw_val in raw_samples:
            self._samples.append((now, float(raw_val)))
        
        # Evict old samples beyond baseline_window horizon
        horizon = max(self.cfg.baseline_window, self.cfg.rms_window)
        cutoff = now - horizon
        while self._samples and self._samples[0][0] < cutoff:
            self._samples.popleft()

        # Baseline from recent window
        base_cut = now - self.cfg.baseline_window
        baseline_vals = [v for t, v in self._samples if t >= base_cut]
        baseline = float(np.median(baseline_vals)) if baseline_vals else 0.0

        # Step 1: Compute RMS on the batch of samples
        if raw_samples:
            # Subtract baseline and compute RMS for this batch
            baseline_subtracted = np.array([max(0.0, float(v) - baseline) for v in raw_samples], dtype=np.float64)
            squares = np.square(baseline_subtracted)
            batch_rms = float(np.sqrt(np.mean(squares)))
        else:
            batch_rms = 0.0

        # Step 2: Apply exponential moving average filtering to the batch RMS
        alpha = max(0.0, min(1.0, self.cfg.ema_alpha))
        if self._ema_rms == 0.0:
            # Initialize EMA with first batch RMS
            self._ema_rms = batch_rms
        else:
            # EMA: EMA_new = alpha * current + (1 - alpha) * EMA_old
            self._ema_rms = alpha * batch_rms + (1.0 - alpha) * self._ema_rms
        
        rms = self._ema_rms
        self._last_rms = rms

        # Normalize to 0..1 against max_range
        norm = max(0.0, min(1.0, rms / max(1.0, self.cfg.max_range)))
        self._last_norm = norm
        return norm

    def last_value(self) -> float:
        return self._last_norm

    def last_rms(self) -> float:
        return self._last_rms
