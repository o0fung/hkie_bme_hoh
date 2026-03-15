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
    noise_floor_window_seconds: float = 3.0  # rolling window length for RMS noise floor
    noise_floor_percentile: float = 20.0     # low percentile used as noise floor estimate
    noise_floor_alpha: float = 0.05          # EMA smoothing factor for noise floor tracking
    noise_floor_margin_percent: float = 5.0  # extra safety margin above floor in % of max_range


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

    Porting notes:
    - Input: one BLE packet normally carries ~100 raw EMG ADC samples (u16).
    - Processing unit: this class treats each packet as one batch and emits one control value.
    - Output: one normalized activation in [0, 1] per packet, suitable for game control.
    """

    def __init__(self, cfg: Optional[EMGConfig] = None):
        self.cfg = cfg or EMGConfig()
        self._samples: deque[tuple[float, float]] = deque()  # (timestamp, raw)
        self._rms_history: deque[tuple[float, float]] = deque()  # (timestamp, smoothed_rms)
        self._last_norm: float = 0.0
        self._last_rms: float = 0.0
        self._ema_rms: float = 0.0  # Current EMA RMS value
        self._noise_floor_rms: float = 0.0  # Smoothed RMS noise-floor estimate

    def set_max_range(self, value: float):
        self.cfg.max_range = max(1.0, float(value))

    def set_noise_floor_window_seconds(self, value: float):
        self.cfg.noise_floor_window_seconds = max(0.5, float(value))

    def set_noise_floor_percentile(self, value: float):
        self.cfg.noise_floor_percentile = max(1.0, min(50.0, float(value)))

    def set_noise_floor_alpha(self, value: float):
        self.cfg.noise_floor_alpha = max(0.0, min(1.0, float(value)))

    def set_noise_floor_margin_percent(self, value: float):
        self.cfg.noise_floor_margin_percent = max(0.0, min(50.0, float(value)))

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

        Porting notes:
        1) Estimate baseline from recent history (median over baseline_window).
        2) Rectify by subtracting baseline and clamping to zero.
        3) Compute RMS over this packet's samples.
        4) Smooth RMS using EMA (alpha = cfg.ema_alpha).
        5) Normalize RMS by max_range, clamp to [0, 1].
        """
        now = time.time()
        
        # Keep incoming packet samples in the rolling history so baseline
        # estimation can include recent packets, not just the current one.
        # Packet-level timestamping: all samples in one BLE packet share one arrival time.
        for raw_val in raw_samples:
            self._samples.append((now, float(raw_val)))
        
        # Retain enough history to satisfy both baseline and RMS windows.
        # (Current RMS is packet-based, but this keeps window semantics explicit.)
        # Evict old samples beyond baseline_window horizon
        # baseline_window size -> 1 second; rms_window size -> 0.2 second
        horizon = max(self.cfg.baseline_window, self.cfg.rms_window)
        cutoff = now - horizon
        while self._samples and self._samples[0][0] < cutoff:
            self._samples.popleft()

        # Baseline tracks slow drift (electrode offset / skin-contact changes).
        base_cut = now - self.cfg.baseline_window
        baseline_vals = [v for t, v in self._samples if t >= base_cut]
        baseline = float(np.median(baseline_vals)) if baseline_vals else 0.0

        # Step 1: Compute RMS on the batch of samples
        if raw_samples:
            # Half-wave rectification after baseline removal.
            baseline_subtracted = np.array([max(0.0, float(v) - baseline) for v in raw_samples], dtype=np.float64)
            squares = np.square(baseline_subtracted)
            batch_rms = float(np.sqrt(np.mean(squares)))
        else:
            # Empty packet (or dropped payload): treat as no instantaneous activity.
            batch_rms = 0.0

        # EMA converts noisy per-packet RMS into a stable control signal.
        alpha = max(0.0, min(1.0, self.cfg.ema_alpha))
        if self._ema_rms == 0.0:
            # First usable observation seeds EMA to avoid startup bias from zero.
            self._ema_rms = batch_rms
        else:
            # Steady-state smoothing:
            # larger alpha reacts faster; smaller alpha favors stability.
            # EMA_new = alpha * current + (1 - alpha) * EMA_old
            self._ema_rms = alpha * batch_rms + (1.0 - alpha) * self._ema_rms
        
        rms = self._ema_rms

        # Dynamic RMS noise-floor compensation:
        # 1) Estimate floor from a low percentile over recent RMS history.
        # 2) Smooth floor with EMA to avoid twitchy threshold movement.
        # 3) Subtract floor + safety margin to suppress interference-driven baseline rise.
        self._rms_history.append((now, rms))
        floor_window = max(0.5, float(self.cfg.noise_floor_window_seconds))
        floor_cutoff = now - floor_window
        while self._rms_history and self._rms_history[0][0] < floor_cutoff:
            self._rms_history.popleft()

        floor_vals = [v for _, v in self._rms_history]
        floor_percentile = max(1.0, min(50.0, float(self.cfg.noise_floor_percentile)))
        floor_target = float(np.percentile(floor_vals, floor_percentile)) if floor_vals else 0.0
        floor_alpha = max(0.0, min(1.0, float(self.cfg.noise_floor_alpha)))
        if self._noise_floor_rms == 0.0:
            self._noise_floor_rms = floor_target
        else:
            self._noise_floor_rms = (
                floor_alpha * floor_target + (1.0 - floor_alpha) * self._noise_floor_rms
            )

        margin_ratio = max(0.0, min(50.0, float(self.cfg.noise_floor_margin_percent))) / 100.0
        margin_rms = margin_ratio * max(1.0, float(self.cfg.max_range))
        effective_rms = max(0.0, rms - self._noise_floor_rms - margin_rms)
        self._last_rms = effective_rms

        # Normalize by configured dynamic range and clamp for downstream control.
        norm = max(0.0, min(1.0, effective_rms / max(1.0, self.cfg.max_range)))
        self._last_norm = norm
        return norm

    def last_value(self) -> float:
        return self._last_norm

    def last_rms(self) -> float:
        return self._last_rms

    def reset(self) -> None:
        """Clear buffered state so processing restarts from a clean baseline."""
        self._samples.clear()
        self._rms_history.clear()
        self._last_norm = 0.0
        self._last_rms = 0.0
        self._ema_rms = 0.0
        self._noise_floor_rms = 0.0
