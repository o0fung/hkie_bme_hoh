import time


class DynamicMVCMixin:
    """
    Runtime MVC auto-calibration behavior used by the App control loop.
    """

    def _set_dynamic_mvc_alpha_up(self, v: float):
        self.dynamic_mvc_alpha_up = max(0.0, min(1.0, float(v)))

    def _set_dynamic_mvc_alpha_down(self, v: float):
        self.dynamic_mvc_alpha_down = max(0.0, min(1.0, float(v)))

    def _set_dynamic_mvc_up_margin_ratio(self, v: float):
        self.dynamic_mvc_up_margin_ratio = max(0.0, min(1.0, float(v)))

    def _set_dynamic_mvc_hold_activity_ratio(self, v: float):
        self.dynamic_mvc_hold_activity_ratio = max(0.0, min(1.0, float(v)))

    def _set_dynamic_mvc_decay_trigger_ratio(self, v: float):
        self.dynamic_mvc_decay_trigger_ratio = max(0.0, min(1.0, float(v)))

    def _set_dynamic_mvc_decay_grace_seconds(self, v: float):
        self.dynamic_mvc_decay_grace_seconds = max(0.0, float(v))

    def _update_dynamic_mvc_flexor(self, rms: float):
        self._update_dynamic_mvc(
            rms=rms,
            current_max=self.emg_max_range_flexor,
            set_max=self._set_emg_max_flexor_runtime,
            floor=self.settings_emg_max_range_flexor,
            last_strong_attr="_dynamic_mvc_last_strong_ts_flexor",
        )

    def _update_dynamic_mvc_extensor(self, rms: float):
        self._update_dynamic_mvc(
            rms=rms,
            current_max=self.emg_max_range_extensor,
            set_max=self._set_emg_max_extensor_runtime,
            floor=self.settings_emg_max_range_extensor,
            last_strong_attr="_dynamic_mvc_last_strong_ts_extensor",
        )

    def _update_dynamic_mvc(
        self,
        rms: float,
        current_max: float,
        set_max,
        floor: float,
        last_strong_attr: str,
    ):
        now = time.perf_counter()
        alpha_up = self.dynamic_mvc_alpha_up
        alpha_down = self.dynamic_mvc_alpha_down
        up_margin_ratio = self.dynamic_mvc_up_margin_ratio
        hold_activity_ratio = self.dynamic_mvc_hold_activity_ratio
        decay_trigger_ratio = self.dynamic_mvc_decay_trigger_ratio
        decay_grace_s = self.dynamic_mvc_decay_grace_seconds

        floor = max(1.0, float(floor))
        current_max = max(floor, float(current_max))
        rms = max(0.0, float(rms))

        up_trigger = current_max * (1.0 + up_margin_ratio)
        hold_trigger = current_max * hold_activity_ratio
        decay_trigger = current_max * decay_trigger_ratio

        if rms >= up_trigger:
            new_max = current_max + (rms - current_max) * alpha_up
            set_max(max(floor, new_max))
            setattr(self, last_strong_attr, now)
            return

        if rms >= hold_trigger:
            setattr(self, last_strong_attr, now)
            return

        last_strong_ts = float(getattr(self, last_strong_attr, now))
        if rms >= decay_trigger or (now - last_strong_ts) < decay_grace_s:
            return

        new_max = max(floor, current_max * (1.0 - alpha_down))
        if new_max < current_max:
            set_max(new_max)
