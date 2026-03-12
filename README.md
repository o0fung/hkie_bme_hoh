# HKIE BME HOH Game

Cross-platform Python game for the HKIE BME booth. It uses two EMG channels (flexor/extensor) to control one exo hand over BLE and guides users through repeatable flexion/extension cycles to earn stars.

The app runs on macOS, Ubuntu, and Windows, defaults to full-screen, and supports simulation mode when hardware is not connected.

## Highlights

- One-hand control loop using two EMG channels: `emg_flexor` and `emg_extensor`
- BLE device scan/bind flow for EMGS + exo-hand devices
- Real-time EMG bars, raw EMG charts, circular hand-position gauge, and star progress
- Start/Stop output safety control and quick Reset
- Optional mirrored layout for left/right operator preference
- Simulation mode for testing without BLE hardware

## Project Layout

- `app/__main__.py` - app entrypoint and runtime wiring
- `app/game/scenes.py` - gameplay + settings scenes and UI behavior
- `app/ble/ble_manager.py` - BLE orchestration and scanning/binding
- `app/ble/emgs_client.py` - EMGS UART command/notification helpers
- `app/ble/exo_client.py` - exo-hand client command/feedback handling
- `app/io/input_manager.py` - EMG processing and normalization
- `app/ui/widgets.py` - reusable Pygame widgets
- `config/devices.sample.json` - sample device/config template

## EMG Porting Guide

For colleagues implementing the same control behavior in another language, see:

- `docs/emg_control_reference.md`

It focuses on:

- channel-specific EMG callbacks (`_on_flexor_emg`, `_on_extensor_emg`)
- signal processing (`EMGProcessor.update_batch`, dynamic MVC update)
- game control mapping (`_choose_active_muscle`, `GameScene.update`)

## Install

### Option 1 (from Git)

```bash
pip install git+https://github.com/o0fung/hkie_bme_hoh.git
```

Run:

```bash
run_hoh_game
```

### Option 2 (local source)

```bash
git clone https://github.com/o0fung/hkie_bme_hoh.git
cd hkie_bme_hoh
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -e .
```

Run:

```bash
run_hoh_game
```

## Run Modes

Full-screen (default):

```bash
python -m app
```

Windowed:

```bash
GAME_FULLSCREEN=0 python -m app
# Windows PowerShell:
# $env:GAME_FULLSCREEN=0; python -m app
```

## Configuration

At startup, the app expects `config/devices.json` in the current working directory. If it does not exist, it attempts to create it from `config/devices.sample.json` (or built-in defaults as fallback).

### Config schema (current)

```json
{
  "simulation": false,
  "settings": {
    "emg_max_range_flexor": 5000,
    "emg_max_range_extensor": 5000,
    "hand_start_percent": 70,
    "threshold_percent": 10,
    "countdown_seconds": 3,
    "target_flexion_percent": 90,
    "target_extension_percent": 30,
    "grip_step_percent": 5,
    "command_rate_hz": 10,
    "activation_hysteresis_percent": 2,
    "deactivation_hysteresis_percent": 5
  },
  "emg_flexor": {
    "name": "EMGS",
    "mac_address": "",
    "service_uuid": "",
    "write_characteristic_uuid": "6e400002-b5a3-f393-e0a9-e50e24dcca9e",
    "notify_characteristic_uuid": "6e400003-b5a3-f393-e0a9-e50e24dcca9e"
  },
  "emg_extensor": {
    "name": "EMGS",
    "mac_address": "",
    "service_uuid": "",
    "write_characteristic_uuid": "6e400002-b5a3-f393-e0a9-e50e24dcca9e",
    "notify_characteristic_uuid": "6e400003-b5a3-f393-e0a9-e50e24dcca9e"
  },
  "exo_hand": {
    "name": "Exo-Hand",
    "mac_address": "",
    "service_uuid": "",
    "write_characteristic_uuid": "",
    "feedback_characteristic_uuid": ""
  }
}
```

Notes:

- Backward compatibility exists for legacy `settings.target_close_percent`.
- `simulation` accepts boolean or string values like `"true"` / `"false"`.

## Controls

- `ESC` - quit
- `F11` - toggle full-screen
- On-screen buttons - `Settings`, `Reset`, `Start/Stop`, `Mirror`, `Exit`
- Simulation keyboard input:
  - Hold `F` for flexor activation
  - Hold `E` for extensor activation

## Gameplay Cycle

Each star requires a two-phase cycle on one exo hand:

1. **Flexion phase**: reach and hold at/above `target_flexion_percent`.
2. **Extension phase**: reach and hold at/below `target_extension_percent`.
3. Complete both phases to earn one star.
4. Earn 3 stars to complete the session.

## BLE Tips

- macOS: allow Bluetooth access for Terminal/app in Privacy settings.
- Ubuntu: ensure BlueZ is installed and adapter is enabled.
- Windows: ensure Bluetooth is enabled and adapter drivers are working.
- If scan results are empty, move closer, power-cycle devices, and scan again.

## Troubleshooting

- No window or blank display: try windowed mode (`GAME_FULLSCREEN=0`).
- Import/runtime errors: verify active venv and reinstall (`pip install -e .`).
- No simulation response: click the game window to focus, then use `F` / `E`.
- No BLE data: verify MAC/UUID config and system Bluetooth permissions.

## License

MIT
