# HKIE BME Dual Grip Game

A kid-friendly, cross‑platform Python game for the HKIE BME Inno‑Carnival booth. Players wear two EMG sensors and control two exoskeleton hand braces. The goal is to hold both hands closed simultaneously long enough to earn three stars.

Runs on macOS, Ubuntu, and Windows in full screen with touch‑friendly UI. Bluetooth LE is used to connect to devices; a simulation mode lets you demo without hardware.

## Features

- Dual‑hand gameplay with RMS EMG processing (adjustable max range)
- Threshold‑based control: each hand closes when its EMG exceeds a percentage threshold
- Position feedback: waits until both braces reach target close before starting a countdown
- Countdown reward: hold both closed for N seconds to earn a star; collect 3 stars to win
- **Circular position gauges**: Visual indicators showing current finger position percentage (0–100%) with target markers (90% threshold)
- **EMG charts**: Real-time visualization of raw EMG signals with mirrored left/right charts
- **Hand labels**: Clear "Left Hand" and "Right Hand" labels positioned under respective EMG bars
- Settings overlay: scan/bind BLE devices, adjust EMG max range, threshold %, countdown seconds, target close %
- Touch‑friendly buttons: Settings, Reset, and Exit (top‑left); 3 stars (top‑right); two vertical EMG bar gauges with threshold markers
- **Touch scrolling**: Scrollable device list with touch-enabled scrollbar support
- Simulation mode: demo without hardware (see Controls)

## Project layout

- `app/__main__.py` — alternative entry point (module mode)
- `app/ble/ble_manager.py` — BLE manager (async bleak in background thread)
- `app/ble/emgs_client.py` — EMGS (Nordic UART) command helpers and notify parser
- `app/io/input_manager.py` — EMG RMS processing and normalization
- `app/ui/widgets.py` — UI components (Button, Label, Panel, BarGauge, NumericStepper, CircularGauge, EMGChart)
- `app/game/scene_manager.py` — scene base and manager
- `app/game/scenes.py` — Game and Settings scenes
- `config/devices.sample.json` — example config for MAC addresses and UUIDs

## Install

### Option 1: Install from Git (Recommended)

```bash
pip install git+https://github.com/o0fung/hkie_bme_hoh.git
```

After installation, run the game with:
```bash
run_hoh_game
```

### Option 2: Install from Local Source

```bash
# Clone the repository
git clone https://github.com/o0fung/hkie_bme_hoh.git
cd hkie_bme_hoh

# Create virtual environment (recommended)
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\\Scripts\\activate

# Install dependencies
pip install -r requirements.txt
# Or install as editable package:
pip install -e .
```

After installing as editable package, you can also run with:
```bash
run_hoh_game
```

## Run

Full‑screen (default):

```bash
python -m app
```

Windowed (dev/testing):

```bash
GAME_FULLSCREEN=0 python -m app     # Windows PowerShell: $env:GAME_FULLSCREEN=0; python -m app
```

You can also run as a module:

```bash
python -m app
```

## Configure devices

Copy the sample and edit values:

```bash
cp config/devices.sample.json config/devices.json
```

Fill in the MAC addresses and UUIDs for each device. Example fields:

```json
{
	"simulation": true,
	"settings": {
		"emg_max_range": 1024,
		"threshold_percent": 60,
		"countdown_seconds": 3,
		"target_close_percent": 90
	},
	"emg_left": {
		"name": "EMG Left Forearm",
		"mac_address": "AA:BB:CC:DD:EE:FF",
		"service_uuid": "<service-uuid>",
		"write_characteristic_uuid": "6e400002-b5a3-f393-e0a9-e50e24dcca9e",
		"notify_characteristic_uuid": "6e400003-b5a3-f393-e0a9-e50e24dcca9e"
	},
	"emg_right": {
		"name": "EMG Right Forearm",
		"mac_address": "11:22:33:44:55:66",
		"service_uuid": "<service-uuid>",
		"write_characteristic_uuid": "6e400002-b5a3-f393-e0a9-e50e24dcca9e",
		"notify_characteristic_uuid": "6e400003-b5a3-f393-e0a9-e50e24dcca9e"
	},
	"exo_left": {
		"name": "Exo-Hand Left",
		"mac_address": "77:88:99:AA:BB:CC",
		"service_uuid": "<service-uuid>",
		"write_characteristic_uuid": "<write-uuid>",
		"feedback_characteristic_uuid": "<feedback-uuid>"
	},
	"exo_right": {
		"name": "Exo-Hand Right",
		"mac_address": "CC:BB:AA:99:88:77",
		"service_uuid": "<service-uuid>",
		"write_characteristic_uuid": "<write-uuid>",
		"feedback_characteristic_uuid": "<feedback-uuid>"
	}
}
```

Notes:
- EMG devices use Nordic UART Service (NUS). On bind, the app sends commands to set EMG mode to RMS and start streaming.
- EMG notifications are framed like `S<E...>`; we heuristically read the first u16 value as the EMG magnitude until a full spec is provided.
- Exo feedback is assumed to be a single byte 0–100 for position; adjust if different.

## Controls

- ESC: Quit
- F11: Toggle full screen
- **Exit button** (top‑left): Safely quit the application
- Settings (top‑left): open settings overlay
- Reset (top‑left): reset stars and countdown
- Simulation (no hardware):
	- Default: hold keyboard 'L' for Left EMG and 'R' for Right EMG
	- (You can easily switch to mouse buttons in code if preferred.)

## Gameplay logic

1. The app continuously computes RMS EMG for left and right arms over a short window and normalizes by EMG Max Range.
2. If a side’s EMG ≥ Threshold %, it commands that hand to close (grip 100%). Otherwise, it commands open (grip 0%).
3. The app monitors exo position feedback (0–1). When both hands reach ≥ Target Close %, a center countdown begins.
4. If both stay closed until the countdown reaches 0, you earn a star. Earn 3 stars to win.

## Settings overlay

- **Scan BLE**: search for all nearby BLE devices (filters devices with non-None names), sorted with "RR_HOH" and "EMGS" prefixes at the top
- **Scrollable device list**: Touch-enabled scrollbar for long device lists
- **Device binding**: Bind per‑side (EMG L/R, Exo L/R) with separate device name and MAC address display
- **Simulation toggle**: switch between simulated and real BLE mode
- **Numeric steppers** (aligned buttons for better UI):
	- EMG Max Range: normalization maximum for EMG RMS
	- Threshold %: level above which a hand is considered "closing"
	- Countdown s: time required holding both closed to earn a star
	- Target Close %: required exo position (feedback) to count as closed

## BLE tips

- macOS: grant Bluetooth permission to the Terminal/app. If scanning returns empty, check System Settings → Privacy & Security → Bluetooth.
- Ubuntu: ensure user is in the `bluetooth` group; BlueZ must be installed and the adapter enabled.
- Windows: ensure Bluetooth is on; some dongles require vendor drivers.
- If devices don’t appear, move closer, power cycle devices, and scan again.

## Troubleshooting

- Black screen or no window: verify SDL can create a display (try windowed mode: `GAME_FULLSCREEN=0`).
- Import errors: re‑activate your venv and `pip install -r requirements.txt`.
- No input in simulation: click into the window to focus; use mouse buttons (or switch to keyboard polling in code).
- BLE permissions: see BLE tips; reboot Bluetooth service if needed.

## License

MIT
