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


class EMGProcessor:
    """
    EMG processor computing RMS over a sliding window.

    Steps:
    - Maintain fixed-time sample buffer
    - Estimate baseline over baseline_window (median)
    - Compute RMS of baseline-subtracted samples over rms_window
    - Normalize to 0..1 using max_range config
    """

    def __init__(self, cfg: Optional[EMGConfig] = None):
        self.cfg = cfg or EMGConfig()
        self._samples: deque[tuple[float, float]] = deque()  # (timestamp, raw)
        self._last_norm: float = 0.0

    def set_max_range(self, value: float):
        self.cfg.max_range = max(1.0, float(value))

    def update(self, raw_value: float) -> float:
        now = time.time()
        self._samples.append((now, float(raw_value)))
        # Evict old samples beyond baseline_window horizon
        horizon = max(self.cfg.baseline_window, self.cfg.rms_window)
        cutoff = now - horizon
        while self._samples and self._samples[0][0] < cutoff:
            self._samples.popleft()

        # Baseline from recent window
        base_cut = now - self.cfg.baseline_window
        baseline_vals = [v for t, v in self._samples if t >= base_cut]
        baseline = float(np.median(baseline_vals)) if baseline_vals else 0.0

        # RMS over rms_window of baseline-subtracted values
        rms_cut = now - self.cfg.rms_window
        rms_vals = [max(0.0, v - baseline) for t, v in self._samples if t >= rms_cut]
        if rms_vals:
            squares = np.square(np.array(rms_vals, dtype=np.float64))
            rms = float(np.sqrt(np.mean(squares)))
        else:
            rms = 0.0

        # Normalize to 0..1 against max_range
        norm = max(0.0, min(1.0, rms / max(1.0, self.cfg.max_range)))
        self._last_norm = norm
        return norm

    def last_value(self) -> float:
        return self._last_norm
