# Settings Button Click Flow

## Overview
When the Settings button is clicked on the Game scene, it triggers a chain of UI scene transitions and initializations. Here's the complete code flow:

---

## 1. Button Definition (Game Scene)
**File:** `src/game/scenes.py` (Line 52)

```python
self.settings_button = Button(
    pygame.Rect(20, 20, 140, 44), 
    "Settings", 
    self.font_small, 
    on_click=self.open_settings  # <-- This is the callback
)
```

The Settings button's **on_click callback** is set to `self.open_settings`, which comes from the `open_settings()` function defined in `main.py`.

---

## 2. Event Handling (Game Scene)
**File:** `src/game/scenes.py` (Line 78)

```python
def handle_event(self, event: pygame.event.Event):
    self.settings_button.handle_event(event)  # Passes event to button
    self.reset_button.handle_event(event)
```

When a pygame event occurs (like a mouse click), it's passed to the button's `handle_event()` method.

---

## 3. Button Widget Handler
**File:** `src/ui/widgets.py` (Button class)

The Button class checks if the event is a click within its rectangular area, and if so, calls the `on_click` callback.

---

## 4. Scene Manager Routing
**File:** `src/game/scene_manager.py`

```python
class SceneManager:
    def handle_event(self, event: pygame.event.Event):
        if self._scene:
            self._scene.handle_event(event)  # Routes events to current scene
```

The main game loop in `main.py` calls `self.scenes.handle_event(event)`, which delegates to the current scene's `handle_event()` method.

---

## 5. Open Settings Callback (App.__init__ → _build_scenes)
**File:** `main.py` (Lines 95–116)

```python
def _build_scenes(self):
    def open_settings():
        """Create and switch to SettingsScene"""
        init = {
            "emg_max_range": self.emg_max_range,
            "threshold_percent": self.threshold_percent,
            "countdown_seconds": self.countdown_seconds,
            "target_close_percent": self.target_close_percent,
        }
        settings_scene = SettingsScene(
            self.screen_rect,
            self.ble,                                    # BLE manager (for scanning)
            on_close=lambda: self.scenes.set_scene(self.game_scene),
            set_emg_max=self._set_emg_max,              # Callbacks for settings changes
            set_threshold_percent=self._set_threshold_percent,
            set_countdown_seconds=self._set_countdown_seconds,
            set_target_close_percent=self._set_target_close_percent,
            on_bind_left_emg=self._bind_left_emg,       # Device binding callbacks
            on_bind_right_emg=self._bind_right_emg,
            on_bind_left_exo=self._bind_left_exo,
            on_bind_right_exo=self._bind_right_exo,
            init_values=init,
        )
        self.scenes.set_scene(settings_scene)  # <-- Switch to Settings scene
    
    # ... (other scene setup code)
    
    self.game_scene = GameScene(
        # ...
        open_settings=open_settings,  # Pass the callback to GameScene
        # ...
    )
    self.scenes.set_scene(self.game_scene)  # Start with GameScene
```

### Key Actions:
1. **Collects current settings** into the `init` dictionary
2. **Creates SettingsScene** with:
   - Reference to the BLE manager for scanning
   - All the callback functions for closing, changing settings, and binding devices
3. **Switches to SettingsScene** via `self.scenes.set_scene(settings_scene)`

---

## 6. Settings Scene Initialization
**File:** `src/game/scenes.py` (Lines 181–220)

```python
class SettingsScene(Scene):
    def __init__(
        self,
        screen_rect: pygame.Rect,
        ble: BLEManager,
        on_close: Callable[[], None],
        set_emg_max: Callable[[float], None],
        set_threshold_percent: Callable[[float], None],
        set_countdown_seconds: Callable[[float], None],
        set_target_close_percent: Callable[[float], None],
        on_bind_left_emg: Callable[[Optional[BLEDeviceInfo]], None],
        on_bind_right_emg: Callable[[Optional[BLEDeviceInfo]], None],
        on_bind_left_exo: Callable[[Optional[BLEDeviceInfo]], None],
        on_bind_right_exo: Callable[[Optional[BLEDeviceInfo]], None],
        init_values: dict,
    ):
        self.ble = ble
        self.on_close = on_close
        
        # Create UI controls
        self.panel = Panel(...)                    # Dark overlay panel
        self.close_btn = Button(...)               # "Close" button
        self.scan_btn = Button(
            pygame.Rect(120, 150, 180, 40), 
            "Scan BLE", 
            self.font, 
            on_click=self._scan                    # <-- Scan button handler
        )
        self.sim_toggle = Button(
            pygame.Rect(120, 200, 180, 40), 
            f"Simulation: {'ON' if ble.simulation else 'OFF'}", 
            self.font, 
            on_click=self._toggle_sim              # <-- Simulation toggle
        )
        
        # Numeric steppers for settings
        self.step_emg_max = NumericStepper(
            "EMG Max Range", 
            ..., 
            on_change=set_emg_max
        )
        self.step_threshold = NumericStepper(
            "Threshold %", 
            ..., 
            on_change=set_threshold_percent
        )
        self.step_countdown = NumericStepper(
            "Countdown s", 
            ..., 
            on_change=set_countdown_seconds
        )
        self.step_target_close = NumericStepper(
            "Target Close %", 
            ..., 
            on_change=set_target_close_percent
        )
        
        # Store device binding callbacks
        self.on_bind_left_emg = on_bind_left_emg
        self.on_bind_right_emg = on_bind_right_emg
        self.on_bind_left_exo = on_bind_left_exo
        self.on_bind_right_exo = on_bind_right_exo
```

---

## 7. Settings Scene UI Controls

### Close Button
**File:** `src/game/scenes.py` (Line 204)
- Callback: `on_close` → switches back to GameScene via `self.scenes.set_scene(self.game_scene)`

### Scan BLE Button
**File:** `src/game/scenes.py` (Lines 205, 227–248)
- Callback: `self._scan()`
- **Does:**
  1. Calls `self.ble.scan(timeout=4.0)` to discover BLE devices
  2. Creates device buttons for each discovered device
  3. Each device has 4 bind buttons: "Bind EMG L", "Bind EMG R", "Bind Exo L", "Bind Exo R"
  4. Each bind button calls `ble.connect(device_address)` then invokes the appropriate binding callback

### Simulation Toggle Button
**File:** `src/game/scenes.py` (Lines 206, 222–225)
- Callback: `self._toggle_sim()`
- **Does:**
  1. Flips `self.ble.simulation` between True/False
  2. Updates button text to show current state

### Numeric Steppers
**File:** `src/game/scenes.py` (Lines 212–218)
- Four adjustable parameters with live callbacks:
  - **EMG Max Range:** min=100, max=5000, default=1024
  - **Threshold %:** min=5, max=100, default=60
  - **Countdown s:** min=1, max=10, default=3
  - **Target Close %:** min=50, max=100, default=90
- Each stepper calls its `on_change` callback with the new value

---

## 8. Settings Scene Event Handling
**File:** `src/game/scenes.py` (Lines 249–260)

```python
def handle_event(self, event: pygame.event.Event):
    self.close_btn.handle_event(event)           # Handle Close button
    self.scan_btn.handle_event(event)            # Handle Scan button
    self.sim_toggle.handle_event(event)          # Handle Simulation toggle
    self.step_emg_max.handle_event(event)        # Handle EMG Max Range stepper
    self.step_threshold.handle_event(event)      # Handle Threshold stepper
    self.step_countdown.handle_event(event)      # Handle Countdown stepper
    self.step_target_close.handle_event(event)   # Handle Target Close stepper
    for b, _, _ in self._device_buttons:         # Handle discovered device buttons
        b.handle_event(event)
```

---

## 9. Settings Scene Drawing
**File:** `src/game/scenes.py` (Lines 263–282)

```python
def draw(self, surface: pygame.Surface):
    self.panel.draw(surface)                     # Dark background
    title = self.font_title.render("Settings", True, WHITE)
    surface.blit(title, (100, 100))
    
    self.close_btn.draw(surface)                 # Close button
    self.scan_btn.draw(surface)                  # Scan BLE button
    self.sim_toggle.draw(surface)                # Simulation toggle
    
    self.step_emg_max.draw(surface)              # All 4 steppers
    self.step_threshold.draw(surface)
    self.step_countdown.draw(surface)
    self.step_target_close.draw(surface)
    
    hint = self.font.render("Scan and bind devices; adjust EMG range/threshold and countdown.", True, WHITE)
    surface.blit(hint, (120, 410))
    
    for b, _, _ in self._device_buttons:         # Draw all discovered device buttons
        b.draw(surface)
```

---

## Complete Call Chain Diagram

```
User clicks "Settings" button on Game Scene
    ↓
GameScene.handle_event(event)
    ↓
settings_button.handle_event(event)  [in src/ui/widgets.py]
    ↓
settings_button.on_click() triggered
    ↓
open_settings() callback [defined in App._build_scenes(), main.py:95–116]
    ↓
Creates SettingsScene with all callbacks and BLE manager
    ↓
self.scenes.set_scene(settings_scene)  [SceneManager switches scene]
    ↓
SettingsScene now active; handle_event/update/draw called each frame
    ↓
User interacts with Settings controls:
    - Close button → on_close() → set_scene(game_scene)
    - Scan button → _scan() → discovers devices via BLE
    - Simulation toggle → _toggle_sim() → flip simulation mode
    - Steppers → callbacks to App methods (_set_emg_max, etc.)
    - Device buttons → ble.connect() + bind callbacks
```

---

## Key Files & Classes

| File | Class | Purpose |
|------|-------|---------|
| `main.py` | `App` | Manages scenes, callbacks, and state |
| `src/game/scenes.py` | `GameScene` | Main game screen with Settings button |
| `src/game/scenes.py` | `SettingsScene` | Settings panel with controls |
| `src/game/scene_manager.py` | `SceneManager` | Manages active scene and event routing |
| `src/ui/widgets.py` | `Button`, `NumericStepper` | Reusable UI components |
| `src/ble/ble_manager.py` | `BLEManager` | Bluetooth scanning and device management |

---

## Summary

**When Settings button is clicked:**
1. GameScene passes event to Button widget
2. Button triggers `on_click=self.open_settings` callback
3. `open_settings()` (defined in App._build_scenes) creates SettingsScene with all callbacks
4. SceneManager switches from GameScene to SettingsScene
5. SettingsScene becomes active and renders its UI each frame
6. User can then:
   - Scan for BLE devices
   - Toggle simulation mode
   - Adjust game settings (EMG range, threshold, countdown, target close %)
   - Bind discovered BLE devices
   - Close to return to GameScene
