import math
import random
import time
from typing import Dict, List


def update_sim_emg_channel(state: Dict[str, float], pressed: bool):
    """
    Update one channel's synthetic EMG envelope and oscillator state.
    """
    now = time.perf_counter()
    dt = max(0.0, min(0.1, now - state["last_update"]))
    state["last_update"] = now

    if pressed:
        state["press_duration"] = min(2.0, state["press_duration"] + dt)
    else:
        state["press_duration"] = max(0.0, state["press_duration"] - (dt * 2.5))

    target_intensity = min(1.0, state["press_duration"] / 1.4)
    lerp_rate = 8.0
    state["intensity"] += (target_intensity - state["intensity"]) * min(1.0, dt * lerp_rate)
    intensity = state["intensity"]

    rest_freq = 8.0
    max_freq = 95.0
    rest_amp = 0.015
    max_amp = 0.42
    state["freq_hz"] = rest_freq + (max_freq - rest_freq) * intensity
    state["amp"] = rest_amp + (max_amp - rest_amp) * intensity
    state["phase"] = (state["phase"] + (math.tau * state["freq_hz"] * dt)) % math.tau

    level_noise = random.uniform(-0.02, 0.02)
    state["level"] = max(0.0, min(1.0, 0.03 + (0.92 * intensity) + level_noise))


def sim_emg_raw_samples(state: Dict[str, float], count: int = 100) -> List[float]:
    """Generate high-rate synthetic ADC-like EMG samples around midpoint."""
    sample_rate_hz = 1000.0
    phase = state["phase"]
    freq_hz = state["freq_hz"]
    amp = state["amp"]
    intensity = state["intensity"]
    noise_std = 0.006 + (0.014 * intensity)
    phase_step = math.tau * freq_hz / sample_rate_hz

    samples: List[float] = []
    for _ in range(count):
        phase = (phase + phase_step) % math.tau
        sample_norm = 0.5 + (amp * math.sin(phase)) + random.gauss(0.0, noise_std)
        sample_norm = max(0.0, min(1.0, sample_norm))
        samples.append(sample_norm * 65535.0)

    state["phase"] = phase
    return samples
