# EMG Controller Reference (Flexor/Extensor -> Motor Output)

This document explains how EMG input becomes exo-hand motor output in runtime.
It focuses on:

1. Packet-level EMG input handling
2. Signal conditioning and normalization
3. Muscle arbitration and motor command generation
4. Conditions and guards that prevent unstable output

It is intended for implementation, review, and porting.

## 1) End-to-end pipeline

Primary code locations:

- `app/__main__.py` -> `_on_flexor_emg(payload)`, `_on_extensor_emg(payload)`, `_process_emg_payload(...)`
- `app/io/input_manager.py` -> `EMGProcessor.update_batch(raw_samples)`
- `app/__main__.py` -> `_update_dynamic_mvc(...)`
- `app/game/scenes.py` -> `_choose_active_muscle(...)`, `_stabilize_grip_target(...)`, `update(dt)`
- `app/__main__.py` -> `_send_grip(grip)`

One control cycle:

```text
BLE payload
  -> parse + validate packet
  -> channel processor (baseline -> full-wave rectify -> RMS -> EMA -> normalize)
  -> dynamic MVC max-range adaptation
  -> flexor/extensor arbitration with hysteresis + latch
  -> target mapping + quantization + deadband stabilization
  -> rate-limited send_grip() command to exo hand
```

## 2) Input and output contracts

### 2.1 EMG packet input (per channel)

Input:

- `payload: bytes` from BLE notification.

Accepted conditions:

- `parse_notification(payload)` returns a packet object.
- `packet["type"] == "E"` (EMG packet).
- `packet["emg_samples"]` exists and is non-empty.
- Samples are numeric-convertible.

Output (channel-local state):

- `raw samples` (float list) for waveform chart.
- `normalized EMG activation` in `[0, 1]` for control.
- `effective RMS` to dynamic MVC adaptation.

Rejected packets are ignored safely (no control update).

### 2.2 Motor command output

Input:

- `grip: float` normalized target in `[0, 1]`.

Output:

- Exo command level `int(0..100)` via `move_uniform(level)`.

Conditions and guards:

- Clamp input to `[0, 1]`.
- Command is only sent when level changed from previous send.
- Command sending is also rate-limited in scene update (`command_rate_hz`).

## 3) Signal processing logic (EMGProcessor)

Primary function:

- `app/io/input_manager.py` -> `EMGProcessor.update_batch(raw_samples)`

Per-packet algorithm:

1. Append packet samples to rolling time buffer.
2. Estimate baseline as median over `baseline_window`.
3. Full-wave rectify with baseline subtraction:
   - `rectified_i = abs(sample_i - baseline)`.
4. Compute packet RMS:
   - `batch_rms = sqrt(mean(rectified^2))`.
5. Smooth RMS with EMA:
   - `ema = alpha * batch_rms + (1-alpha) * ema_prev`.
6. Normalize:
   - `norm = clamp(ema_rms / max_range, 0, 1)`.

Important note:

- Dynamic MVC uses `last_rms()` from processor, which is the smoothed
  per-packet RMS (`ema_rms`), not raw packet RMS.

## 4) Dynamic MVC range adaptation

Primary function:

- `app/__main__.py` -> `_update_dynamic_mvc(rms, current_max, set_max, floor, last_strong_attr)`

Purpose:

- Keep normalization usable across stronger effort and fatigue in-session.

Decision logic:

```text
up_trigger    = current_max * (1 + up_margin_ratio)
hold_trigger  = current_max * hold_activity_ratio
decay_trigger = current_max * decay_trigger_ratio

if rms >= up_trigger:
    # Fast growth
    current_max <- current_max + alpha_up * (rms - current_max)
    last_strong_ts <- now
    apply max(floor, current_max)
    return

if rms >= hold_trigger:
    # Maintain scale and refresh grace
    last_strong_ts <- now
    return

if rms >= decay_trigger:
    return

if (now - last_strong_ts) < decay_grace_seconds:
    return

# Sustained low activity only: slow decay
current_max <- max(floor, current_max * (1 - alpha_down))
```

Guarantees:

- Fast upward adaptation.
- Slow downward adaptation.
- Never below configured floor (`settings emg_max_range_*`).

## 5) Active-muscle arbitration conditions

Primary function:

- `app/game/scenes.py` -> `_choose_active_muscle(emg_flexor, emg_extensor, thr)`

Inputs:

- `emg_flexor`, `emg_extensor` in `[0, 1]`.
- `thr` in `[0, 0.99]`.
- Hysteresis parameters:
  - `activation_hysteresis`
  - `deactivation_hysteresis`

Derived thresholds:

- `activate_thr = thr + activation_hysteresis`
- `deactivate_thr = thr - deactivation_hysteresis`
- `dominance_margin = max(activation_hysteresis, deactivation_hysteresis)`

Arbitration rules:

1. If flexor is latched:
   - switch to extensor only if extensor clears activate threshold and leads by dominance margin.
   - otherwise keep flexor while flexor >= deactivate threshold.
2. If extensor is latched: symmetric rule.
3. If no latch remains:
   - choose flexor if flexor >= activate threshold.
   - else choose extensor if extensor >= activate threshold.
   - if both are near base threshold, flexor wins deterministic tie-break.
4. Else no active muscle.

This creates a stable latch and avoids chatter near threshold crossings.

## 6) Active muscle -> grip target -> command

Primary function:

- `app/game/scenes.py` -> `update(dt)`

### 6.1 Target mapping

- If active muscle is flexor:
  - map above-threshold flexor activity to closing direction
  - `raw_target` in `[hand_start .. 1.0]`
- If active muscle is extensor:
  - map above-threshold extensor activity to opening direction
  - `raw_target` in `[hand_start .. 0.0]`
- If no active muscle:
  - hold previous target.

### 6.2 Output conditioning

1. Snap to step size (`grip_step_percent`).
2. Stabilize with deadbands:
   - `forward_deadband_percent`: suppress tiny same-direction updates.
   - `reversal_deadband_percent`: require larger movement before direction flip.
3. Save stabilized target as hold target.

### 6.3 Send conditions

Motor command is sent only if all are true:

- Motor output is enabled (`Start` active).
- Current time exceeds command interval (`1 / command_rate_hz`).
- Quantized exo level changed since last send.

## 7) Settings that control behavior

Runtime-critical control settings (`config/devices.json` -> `settings`):

- `threshold_percent`
- `activation_hysteresis_percent`
- `deactivation_hysteresis_percent`
- `hand_start_percent`
- `grip_step_percent`
- `command_rate_hz`
- `forward_deadband_percent`
- `reversal_deadband_percent`

Dynamic MVC settings:

- `dynamic_mvc_alpha_up`
- `dynamic_mvc_alpha_down`
- `dynamic_mvc_up_margin_ratio`
- `dynamic_mvc_hold_activity_ratio`
- `dynamic_mvc_decay_trigger_ratio`
- `dynamic_mvc_decay_grace_seconds`

## 8) Porting checklist

- Keep one independent processor per channel (flexor/extensor).
- Preserve order: baseline -> full-wave rectify -> RMS -> EMA -> normalize.
- Preserve latch+hysteresis arbitration logic and tie-break behavior.
- Preserve snap/deadband/rate-limit send chain.
- Preserve dynamic MVC floor clamp and grace-timed decay.
