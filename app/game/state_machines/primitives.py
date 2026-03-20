import math
from typing import Iterable, Optional


def snap_grip_target(grip_target: float, grip_step: float) -> float:
    """Quantize grip target to configured command step."""
    step = max(0.01, float(grip_step))
    return max(0.0, min(1.0, round(float(grip_target) / step) * step))


def stabilize_grip_target(
    candidate_target: float,
    hold_target: float,
    last_direction: int,
    forward_deadband: float,
    reversal_deadband: float,
) -> tuple[float, int]:
    """
    Stabilize command output around crossover boundaries.

    A direction flip is accepted only after the candidate moves beyond the
    configured reversal gate. This suppresses one-step oscillation when flexor
    and extensor are near-equal around threshold.
    """
    delta = float(candidate_target) - float(hold_target)
    if abs(delta) < 1e-9:
        return hold_target, last_direction

    direction = 1 if delta > 0.0 else -1
    forward_gate = max(0.0, float(forward_deadband))
    reversal_gate = max(0.0, float(reversal_deadband))
    if last_direction != 0 and direction != last_direction:
        if reversal_gate > 0.0 and abs(delta) < reversal_gate:
            return hold_target, last_direction
    elif forward_gate > 0.0 and abs(delta) < forward_gate:
        return hold_target, last_direction

    return candidate_target, direction


def percentile(values: Iterable[float], p: float) -> float:
    """Compute a linear-interpolated percentile over values."""
    ordered = sorted(float(v) for v in values)
    if not ordered:
        return 0.0
    p = max(0.0, min(100.0, float(p)))
    if len(ordered) == 1:
        return ordered[0]
    pos = (len(ordered) - 1) * (p / 100.0)
    low = int(math.floor(pos))
    high = int(math.ceil(pos))
    if low == high:
        return ordered[low]
    weight = pos - low
    return ordered[low] * (1.0 - weight) + ordered[high] * weight


def compute_effective_thresholds(
    base_thr: float,
    flexor_noise_history: Iterable[float],
    extensor_noise_history: Iterable[float],
    noise_floor_percentile: float,
    noise_floor_guard: float,
) -> tuple[float, float, float, float, float, float]:
    """
    Raise per-channel thresholds when baseline noise drifts upward.

    The guard keeps spontaneous baseline bursts from immediately activating
    control while still allowing voluntary contraction to win.
    """
    flexor_floor = percentile(flexor_noise_history, noise_floor_percentile)
    extensor_floor = percentile(extensor_noise_history, noise_floor_percentile)
    flexor_guard_thr = flexor_floor + float(noise_floor_guard)
    extensor_guard_thr = extensor_floor + float(noise_floor_guard)
    flexor_thr = max(float(base_thr), flexor_guard_thr)
    extensor_thr = max(float(base_thr), extensor_guard_thr)
    return (
        max(0.0, min(0.99, flexor_floor)),
        max(0.0, min(0.99, extensor_floor)),
        max(0.0, min(0.99, flexor_guard_thr)),
        max(0.0, min(0.99, extensor_guard_thr)),
        max(0.0, min(0.99, flexor_thr)),
        max(0.0, min(0.99, extensor_thr)),
    )


def choose_active_muscle(
    current_active_muscle: Optional[str],
    emg_flexor: float,
    emg_extensor: float,
    flexor_thr: float,
    extensor_thr: float,
    activation_hysteresis: float,
    deactivation_hysteresis: float,
) -> Optional[str]:
    """
    Decide control ownership ("flexor", "extensor", or None) with hysteresis.
    """
    deactivate_flexor_thr = max(0.0, float(flexor_thr) - float(deactivation_hysteresis))
    deactivate_extensor_thr = max(0.0, float(extensor_thr) - float(deactivation_hysteresis))
    activate_flexor_thr = min(1.0, float(flexor_thr) + float(activation_hysteresis))
    activate_extensor_thr = min(1.0, float(extensor_thr) + float(activation_hysteresis))
    dominance_margin = max(float(activation_hysteresis), float(deactivation_hysteresis))

    if current_active_muscle == "flexor":
        if emg_extensor >= activate_extensor_thr and (emg_extensor - emg_flexor) >= dominance_margin:
            return "extensor"
        if emg_flexor >= deactivate_flexor_thr:
            return "flexor"

    if current_active_muscle == "extensor":
        if emg_flexor >= activate_flexor_thr and (emg_flexor - emg_extensor) >= dominance_margin:
            return "flexor"
        if emg_extensor >= deactivate_extensor_thr:
            return "extensor"

    if emg_flexor >= activate_flexor_thr:
        return "flexor"
    if emg_extensor >= activate_extensor_thr:
        return "extensor"
    if emg_flexor >= flexor_thr and emg_extensor >= extensor_thr:
        return "flexor"
    return None
