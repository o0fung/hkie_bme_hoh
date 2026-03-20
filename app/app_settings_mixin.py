import platform
import subprocess
import time
from .emg.dynamic_mvc import DynamicMVCMixin


class AppSettingsMixin(DynamicMVCMixin):
    def _set_emg_max_flexor(self, v: float):
        value = float(v)
        self.settings_emg_max_range_flexor = value
        self._set_emg_max_flexor_runtime(value)

    def _set_emg_max_extensor(self, v: float):
        value = float(v)
        self.settings_emg_max_range_extensor = value
        self._set_emg_max_extensor_runtime(value)

    def _set_emg_max_flexor_runtime(self, v: float):
        self.emg_max_range_flexor = float(v)
        self.emg_flexor.set_max_range(self.emg_max_range_flexor)

    def _set_emg_max_extensor_runtime(self, v: float):
        self.emg_max_range_extensor = float(v)
        self.emg_extensor.set_max_range(self.emg_max_range_extensor)

    def _set_training_muscle_mode(self, mode: str):
        normalized = str(mode or "").strip().lower()
        if normalized not in {"auto", "flexor_only", "extensor_only", "both"}:
            normalized = "auto"
        self.training_muscle_mode = normalized

    def _set_training_trigger_mode(self, mode: str):
        normalized = str(mode or "").strip().lower()
        if normalized not in {"auto", "trigger-and-go", "trigger-and-maintain"}:
            normalized = "auto"
        self.training_trigger_mode = normalized

    def _set_hand_start_percent(self, v: float):
        self.hand_start_percent = float(v)
        start_pos = max(0.0, min(1.0, self.hand_start_percent / 100.0))
        self._hand_target = start_pos

    def _set_threshold_percent(self, v: float):
        self.threshold_percent = float(v)

    def _set_trigger_threshold_percent(self, v: float):
        self.trigger_threshold_percent = max(0.0, min(100.0, float(v)))

    def _set_trigger_wait_seconds(self, v: float):
        self.trigger_wait_seconds = max(0.0, float(v))

    def _set_relax_flexion_percent(self, v: float):
        self.relax_flexion_percent = max(0.0, min(100.0, float(v)))

    def _set_relax_extension_percent(self, v: float):
        self.relax_extension_percent = max(0.0, min(100.0, float(v)))

    def _set_countdown_seconds(self, v: float):
        self.countdown_seconds = float(v)

    def _set_stars_to_collect(self, v: float):
        self.stars_to_collect = int(max(1, min(7, round(float(v)))))
        if hasattr(self, "game_scene") and self.game_scene is not None:
            self.game_scene.set_max_stars(self.stars_to_collect)

    def _set_training_duration_minutes(self, v: float):
        self.training_duration_minutes = int(max(1, min(240, round(float(v)))))

    def _set_target_flexion_percent(self, v: float):
        self.target_flexion_percent = max(0.0, min(100.0, float(v)))

    def _set_target_extension_percent(self, v: float):
        self.target_extension_percent = max(0.0, min(100.0, float(v)))

    def _set_grip_step_percent(self, v: float):
        self.grip_step_percent = float(v)

    def _set_command_rate_hz(self, v: float):
        self.command_rate_hz = float(v)

    def _set_activation_hysteresis_percent(self, v: float):
        self.activation_hysteresis_percent = float(v)

    def _set_deactivation_hysteresis_percent(self, v: float):
        self.deactivation_hysteresis_percent = float(v)

    def _set_forward_deadband_percent(self, v: float):
        self.forward_deadband_percent = max(0.0, min(100.0, float(v)))

    def _set_reversal_deadband_percent(self, v: float):
        self.reversal_deadband_percent = max(0.0, min(100.0, float(v)))

    def _set_background_blur_percent(self, v: float):
        self.background_blur_percent = max(0.0, min(100.0, float(v)))
        if hasattr(self, "game_scene") and self.game_scene is not None:
            self.game_scene.set_background_blur_percent(self.background_blur_percent)

    def _set_sound_effect_quick_enabled(self, enabled: bool):
        self.sound_effect_quick_enabled = bool(enabled)
        self.audio_manager.set_sound_effect_enabled(self.sound_effect_quick_enabled)

    def _set_music_quick_enabled(self, enabled: bool):
        self.music_quick_enabled = bool(enabled)
        self.audio_manager.set_music_enabled(self.music_quick_enabled)

    def _set_sound_effect_volume_percent(self, v: float):
        self.sound_effect_volume_percent = max(0.0, min(100.0, float(v)))
        self.audio_manager.set_sound_effect_volume_percent(self.sound_effect_volume_percent)

    def _set_music_volume_percent(self, v: float):
        self.music_volume_percent = max(0.0, min(100.0, float(v)))
        self.audio_manager.set_music_volume_percent(self.music_volume_percent)

    def _toggle_sound_effect_quick_enabled(self):
        self._set_sound_effect_quick_enabled(not self.sound_effect_quick_enabled)

    def _get_sound_effect_quick_enabled(self) -> bool:
        return self.sound_effect_quick_enabled

    def _toggle_music_quick_enabled(self):
        self._set_music_quick_enabled(not self.music_quick_enabled)

    def _get_music_quick_enabled(self) -> bool:
        return self.music_quick_enabled

    def _normalize_theme_mode(self, mode: object) -> str:
        normalized = str(mode).strip().lower()
        if normalized not in {"system", "dark", "light"}:
            return "system"
        return normalized

    def _read_system_theme_is_dark(self) -> bool:
        system_name = platform.system()
        try:
            if system_name == "Darwin":
                result = subprocess.run(
                    ["defaults", "read", "-g", "AppleInterfaceStyle"],
                    capture_output=True,
                    text=True,
                    timeout=0.3,
                    check=False,
                )
                return result.returncode == 0 and "dark" in (result.stdout or "").strip().lower()
            if system_name == "Windows":
                try:
                    import winreg  # type: ignore

                    with winreg.OpenKey(
                        winreg.HKEY_CURRENT_USER,
                        r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
                    ) as key:
                        value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
                        return int(value) == 0
                except Exception:
                    return True
        except Exception:
            return True
        return True

    def _get_is_dark_theme(self) -> bool:
        if self.theme_mode == "dark":
            return True
        if self.theme_mode == "light":
            return False
        now = time.perf_counter()
        if (now - self._system_theme_last_check) >= 2.0:
            self._system_theme_is_dark_cache = self._read_system_theme_is_dark()
            self._system_theme_last_check = now
        return self._system_theme_is_dark_cache

    def _set_theme_mode(self, mode: str):
        self.theme_mode = self._normalize_theme_mode(mode)
        self._system_theme_last_check = 0.0

