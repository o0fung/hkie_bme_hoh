# HKIE BME Grip & Catch

A kid-friendly, full-screen Python game for the HKIE BME Inno-Carnival. Kids squeeze using EMG sensors to control an exoskeleton hand (open/close) and catch falling balls on screen. Supports a settings overlay to scan and connect BLE devices (EMG sensors and the exo-hand). Includes a simulation mode for demos without hardware.

## Features

- Cross-platform: macOS, Ubuntu, Windows
- Full-screen Pygame display with large, touch-friendly buttons
- BLE integration via bleak (scan/connect/notify/write)
- EMG processing (smoothing + threshold) to derive a 0..1 grip value
- Mini-game: Grip & Catch — close the hand to catch falling balls and score points
- Simulation mode (no hardware) — hold left mouse button to “squeeze”

## Project layout

- `src/main.py` — app entry point
- `src/ble/ble_manager.py` — BLE manager (async bleak in background thread)
- `src/io/input_manager.py` — EMG signal processing (normalize, smooth)
- `src/ui/widgets.py` — simple UI components (Button, Label, Panel)
- `src/game/scene_manager.py` — scene base and manager
- `src/game/scenes.py` — Game and Settings scenes
- `config/devices.sample.json` — example config to fill with MAC addresses and UUIDs

## Setup

1) Create a Python environment and install dependencies

```bash
python -m venv .venv
source .venv/bin/activate  # macOS/Linux
# .venv\\Scripts\\activate  # Windows PowerShell
pip install -r requirements.txt
```

2) First run (simulation mode by default)

```bash
python -m src.main
```

- Full screen is enabled by default; press F11 to toggle.
- Press ESC to quit.
- In simulation mode, hold left mouse button to “squeeze” (hand closes).

## Add your devices

Copy the sample and fill in addresses and UUIDs when you have them:

```bash
cp config/devices.sample.json config/devices.json
```

Then edit `config/devices.json` and set:

- EMG sensor(s): `mac_address`, `service_uuid`, `characteristic_uuid`
- Exo-hand: `mac_address`, `service_uuid`, `characteristic_uuid`

In `src/main.py`, wire your EMG notification characteristic in `_bind_emg` by calling `self.ble.start_notifications(...)` with your characteristic UUID, and set `self.exo_characteristic_uuid` in `_bind_exo` for write commands.

## Game concept ideas

- Grip & Catch (included): Catch falling balls by closing your hand; time-limited rounds, score display.
- Squeeze Meter: Maintain a target grip zone that moves up/down — great for biofeedback and pacing.
- Rhythm Grip: Close/open to the beat (simple visual metronome) — stars for timing accuracy.

Props like a rubber/sponge ball can make the experience tangible while the screen reflects their action.

## Troubleshooting

- If `pygame` or `bleak` fails to install on macOS, ensure Command Line Tools are installed and try Python 3.10–3.12.
- Some platforms require Bluetooth permissions. On macOS, grant Bluetooth access to the terminal/VS Code.
- No hardware? Keep `"simulation": true` in `config/devices.json`.

## License

MIT
