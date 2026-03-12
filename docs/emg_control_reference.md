# EMG Control Reference (Flexor/Extensor)

This guide focuses on three parts of the runtime pipeline:

1. Channel-specific EMG callbacks
2. Signal processing (raw samples -> normalized activation)
3. Game control mapping (activation -> grip command)

It is intended for engineers porting logic to another language.

## 1) Channel-specific EMG processing

Primary functions:

- `app/__main__.py` -> `_on_flexor_emg(payload)`
- `app/__main__.py` -> `_on_extensor_emg(payload)`
- `app/ble/emgs_client.py` -> `parse_notification(payload)`

Flow:

- Receive one BLE notification (`payload`) per channel.
- Parse notification to structured packet.
- Keep only EMG packets (`type == "E"`).
- Extract `emg_samples` (list of raw u16 values, typically ~100 samples/packet).
- Save raw samples for chart display.
- Send sample batch to EMG processor to obtain one normalized control value.

Pseudocode:

```text
function on_channel_emg(payload, processor, raw_buffer, update_dynamic_mvc):
    parsed = parse_notification(payload)
    if parsed is None:
        return

    if parsed.type != "E":
        return

    if "emg_samples" not in parsed:
        return

    samples = parsed.emg_samples
    if samples is empty:
        return

    raw_buffer = float_copy(samples)                  # for waveform chart only
    normalized_value = processor.update_batch(samples) # 0..1 control value
    update_dynamic_mvc(processor.last_rms())           # optional in-session auto-range adaptation

    return normalized_value
```

Notes:

- Flexor and extensor are processed independently but with identical logic.
- Parser robustness is important because firmware framing can vary.

## 2) Signal processing

Primary functions:

- `app/io/input_manager.py` -> `EMGProcessor.update_batch(raw_samples)`
- `app/io/input_manager.py` -> `EMGProcessor.set_max_range(value)`
- `app/io/input_manager.py` -> `EMGProcessor.reset()`
- `app/__main__.py` -> `_update_dynamic_mvc(rms, current_max, set_max)`

Processing sequence per packet:

1. Add all packet samples to a time buffer.
2. Compute baseline as median over recent baseline window.
3. Rectify: `x = max(0, raw - baseline)`.
4. Compute packet RMS: `sqrt(mean(x^2))`.
5. Apply EMA to RMS.
6. Normalize by `max_range`.
7. Clamp to `[0, 1]`.

Pseudocode:

```text
function update_batch(raw_samples):
    now = current_time()

    for sample in raw_samples:
        sample_buffer.append((now, float(sample)))

    # Keep only recent history needed for baseline and RMS windows
    horizon = max(baseline_window_size, rms_window_size)
    drop entries older than now - horizon

    # Use the data within the baseline_window_size to compute median and output the offset that move ADC to around zero.
    baseline_values = values from sample_buffer newer than now - baseline_window
    baseline = median(baseline_values) if exists else 0

    # Apply Root-Mean-Square on all current sample after the offset removal.
    rectified = [max(0, s - baseline) for s in raw_samples]
    batch_rms = sqrt(mean(square(rectified))) if raw_samples not empty else 0

    # Use Exponential Moving Average to smooth emg data (alpha~0.1; max_range=65535.0).
    if ema_rms is uninitialized:
        ema_rms = batch_rms
    else:
        ema_rms = alpha * batch_rms + (1 - alpha) * ema_rms

    normalized = clamp(ema_rms / max_range, 0, 1)

    last_rms = ema_rms
    last_norm = normalized
    return normalized
```

Dynamic MVC auto-range pseudocode:

```text
function update_dynamic_mvc(rms, current_max, floor, last_strong_ts, now):
    alpha_up = 0.2
    alpha_down = 0.01
    up_margin_ratio = 0.03
    hold_activity_ratio = 0.85
    decay_trigger_ratio = 0.60
    decay_grace_s = 2.0

    up_trigger = current_max * (1 + up_margin_ratio)
    hold_trigger = current_max * hold_activity_ratio
    decay_trigger = current_max * decay_trigger_ratio

    if rms >= up_trigger:
        # Fast growth when user reaches a clearly stronger contraction
        current_max = current_max + alpha_up * (rms - current_max)
        last_strong_ts = now
        return max(floor, current_max), last_strong_ts

    if rms >= hold_trigger:
        # Keep scale stable during moderate/high activity
        last_strong_ts = now
        return current_max, last_strong_ts

    if rms >= decay_trigger:
        return current_max, last_strong_ts

    if (now - last_strong_ts) < decay_grace_s:
        return current_max, last_strong_ts

    # Slow decay after sustained low activity/fatigue; never below floor
    current_max = current_max * (1 - alpha_down)
    return max(floor, current_max), last_strong_ts
```

Notes:

- Current implementation is bidirectional in-session:
  - Grows quickly on stronger contractions.
  - Shrinks slowly only after sustained low activity.
- Decay is gated by both activity threshold and grace time to avoid jitter.
- Runtime range is clamped to the Settings baseline floor (never below configured max range).

Dynamic MVC config keys (`config/devices.json` -> `settings`):

- `dynamic_mvc_alpha_up` (default `0.2`)
- `dynamic_mvc_alpha_down` (default `0.01`)
- `dynamic_mvc_up_margin_ratio` (default `0.03`)
- `dynamic_mvc_hold_activity_ratio` (default `0.85`)
- `dynamic_mvc_decay_trigger_ratio` (default `0.60`)
- `dynamic_mvc_decay_grace_seconds` (default `2.0`)

## 3) Game control mapping

Primary functions:

- `app/game/scenes.py` -> `_choose_active_muscle(emg_flexor, emg_extensor, thr)`
- `app/game/scenes.py` -> `update(dt)`

Concept:

- Inputs are normalized activations (`0..1`) for flexor/extensor.
- A shared threshold and hysteresis decide which muscle currently owns control.
- Active muscle maps to grip target:
  - Flexor drives hand toward closed.
  - Extensor drives hand toward open.
- Output command is quantized and rate-limited before sending to exo hand.

### 3.1 Active-muscle arbitration

Pseudocode:

```text
function choose_active_muscle(flex, ext, thr):
    activate_thr   = min(1.0, thr + activation_hysteresis)
    deactivate_thr = max(0.0, thr - deactivation_hysteresis)
    dominance_margin = max(activation_hysteresis, deactivation_hysteresis)

    if active == FLEXOR:
        if ext >= activate_thr and (ext - flex) >= dominance_margin:
            return EXTENSOR
        if flex >= deactivate_thr:
            return FLEXOR

    if active == EXTENSOR:
        if flex >= activate_thr and (flex - ext) >= dominance_margin:
            return FLEXOR
        if ext >= deactivate_thr:
            return EXTENSOR

    # New selection (flexor priority)
    if flex >= activate_thr:
        return FLEXOR
    if ext >= activate_thr:
        return EXTENSOR
    if flex >= thr and ext >= thr:
        return FLEXOR
    return NONE
```

### 3.2 EMG -> grip target mapping

Pseudocode:

```text
function control_tick():
    flex = emg_flexor_provider()    # normalized 0..1
    ext  = emg_extensor_provider()  # normalized 0..1

    thr = clamp(threshold_percent / 100, 0, 0.99)
    hand_start = clamp(hand_start_percent / 100, 0, 1)

    active = choose_active_muscle(flex, ext, thr)

    if active == FLEXOR:
        flex_norm = clamp((flex - thr) / max(0.01, 1 - thr), 0, 1)
        raw_target = hand_start + (1 - hand_start) * flex_norm
    else if active == EXTENSOR:
        ext_norm = clamp((ext - thr) / max(0.01, 1 - thr), 0, 1)
        raw_target = hand_start * (1 - ext_norm)
    else:
        raw_target = previous_hold_target

    snapped_target = quantize_to_step(raw_target, grip_step_percent)
    grip_target = stabilize_output_direction(snapped_target, previous_hold_target)
    previous_hold_target = grip_target

    if motor_enabled and time_since_last_command >= command_interval:
        send_grip(grip_target)
        last_command_time = now
```

Notes:

- `grip_step_percent` provides output quantization.
- `forward_deadband_percent` suppresses small same-direction output changes
  (set to `0` to disable).
- Direction reversal is guarded by an output deadband so small opposite-side
  fluctuations do not immediately flip motor polarity
  (`reversal_deadband_percent`, set to `0` to disable).
- `command_rate_hz` limits command frequency to protect BLE and actuator stability.
- If neither muscle is active, last target is held (no oscillation back to neutral).

## Port checklist (for another language)

- Parse EMG notifications and expose `emg_samples`.
- Keep one independent processor instance per channel.
- Preserve baseline -> RMS -> EMA -> normalize order.
- Preserve hysteresis/latching arbitration logic exactly.
- Preserve target quantization, output deadbands, and command rate limiting.
