from dataclasses import replace

from .primitives import snap_grip_target
from .models import ControlInputs, ControlOutput, ControlState


def _clear_trigger_latches(state: ControlState) -> ControlState:
    return replace(
        state,
        trigger_go_latched_phase=None,
        trigger_maintain_active_phase=None,
        trigger_require_relax_phase=None,
    )


def _phase_for_state(state: ControlState) -> str:
    return "flexion" if state.cycle_phase == "flexion" else "extension"


class _BaseControlMachine:
    def step(self, inputs: ControlInputs, state: ControlState) -> ControlOutput:
        raise NotImplementedError()

    def _make_output(
        self,
        *,
        mode_key: str,
        raw_target: float,
        state: ControlState,
        immediate_grip_command: float | None = None,
        is_trigger_session_mode: bool = False,
    ) -> ControlOutput:
        return ControlOutput(
            raw_target=raw_target,
            cycle_phase=state.cycle_phase,
            active_muscle=state.active_muscle,
            grip_target_hold=state.grip_target_hold,
            last_target_direction=state.last_target_direction,
            last_command_time=state.last_command_time,
            trigger_go_latched_phase=state.trigger_go_latched_phase,
            trigger_maintain_active_phase=state.trigger_maintain_active_phase,
            trigger_require_relax_phase=state.trigger_require_relax_phase,
            immediate_grip_command=immediate_grip_command,
            is_trigger_session_mode=is_trigger_session_mode,
            mode_key=mode_key,
        )


class _AutoBothMachine(_BaseControlMachine):
    def step(self, inputs: ControlInputs, state: ControlState) -> ControlOutput:
        state = _clear_trigger_latches(state)
        if state.active_muscle == "flexor":
            # Analog mapping in dual-channel mode:
            # threshold crossing starts movement from hand_start toward full close.
            flex_norm = (inputs.emg_flexor - inputs.base_thr) / max(0.01, 1.0 - inputs.base_thr)
            flex_norm = max(0.0, min(1.0, flex_norm))
            raw_target = inputs.hand_start + (1.0 - inputs.hand_start) * flex_norm
        elif state.active_muscle == "extensor":
            # Analog mapping from hand_start toward full open.
            ext_norm = (inputs.emg_extensor - inputs.base_thr) / max(0.01, 1.0 - inputs.base_thr)
            ext_norm = max(0.0, min(1.0, ext_norm))
            raw_target = inputs.hand_start * (1.0 - ext_norm)
        else:
            # No arbitration winner: hold previous target to avoid command jitter.
            raw_target = state.grip_target_hold
        return self._make_output(mode_key=inputs.mode_key, raw_target=raw_target, state=state)


class _AutoFlexorOnlyMachine(_BaseControlMachine):
    def step(self, inputs: ControlInputs, state: ControlState) -> ControlOutput:
        # Single-channel training locks phase by definition.
        state = replace(state, cycle_phase="flexion")
        state = _clear_trigger_latches(state)
        flex_norm = (inputs.emg_flexor - inputs.relax_flexion_thr) / max(0.01, 1.0 - inputs.relax_flexion_thr)
        raw_target = max(0.0, min(1.0, flex_norm))
        return self._make_output(mode_key=inputs.mode_key, raw_target=raw_target, state=state)


class _AutoExtensorOnlyMachine(_BaseControlMachine):
    def step(self, inputs: ControlInputs, state: ControlState) -> ControlOutput:
        state = replace(state, cycle_phase="extension")
        state = _clear_trigger_latches(state)
        ext_norm = (inputs.emg_extensor - inputs.relax_extension_thr) / max(0.01, 1.0 - inputs.relax_extension_thr)
        raw_target = 1.0 - max(0.0, min(1.0, ext_norm))
        return self._make_output(mode_key=inputs.mode_key, raw_target=raw_target, state=state)


class _AutoNoneMachine(_BaseControlMachine):
    def step(self, inputs: ControlInputs, state: ControlState) -> ControlOutput:
        state = _clear_trigger_latches(state)
        return self._make_output(mode_key=inputs.mode_key, raw_target=state.grip_target_hold, state=state)


class _BaseTriggerMachine(_BaseControlMachine):
    def _common_prestep(self, state: ControlState, mode_key: str) -> tuple[ControlState, str, str]:
        # Single-channel trigger modes still use the same trigger state machine, but
        # their cycle phase is hard-locked to one side.
        if mode_key.endswith(":flexor_only"):
            state = replace(state, cycle_phase="flexion")
        elif mode_key.endswith(":extensor_only"):
            state = replace(state, cycle_phase="extension")
        phase = _phase_for_state(state)
        target_muscle = "flexor" if phase == "flexion" else "extensor"
        if state.trigger_go_latched_phase != phase:
            state = replace(state, trigger_go_latched_phase=None)
        if state.trigger_maintain_active_phase != phase:
            state = replace(state, trigger_maintain_active_phase=None)
        return state, phase, target_muscle

    def _needs_relax_before_rearm(self, state: ControlState, mode_key: str, phase: str) -> bool:
        # Relax-before-rearm is only meaningful for dual-channel trigger training.
        return mode_key.endswith(":both") and state.trigger_require_relax_phase == phase


class _TriggerGoMachine(_BaseTriggerMachine):
    def step(self, inputs: ControlInputs, state: ControlState) -> ControlOutput:
        state, phase, target_muscle = self._common_prestep(state, inputs.mode_key)
        target_emg = inputs.emg_flexor if target_muscle == "flexor" else inputs.emg_extensor
        trigger_activate_thr = min(1.0, inputs.trigger_thr + inputs.activation_hysteresis)
        trigger_deactivate_thr = max(0.0, inputs.trigger_thr - inputs.deactivation_hysteresis)

        if self._needs_relax_before_rearm(state, inputs.mode_key, phase) and target_emg > trigger_deactivate_thr:
            # Phase was advanced previously; require true relax before accepting next trigger.
            state = replace(state, active_muscle=None)
            return self._make_output(
                mode_key=inputs.mode_key,
                raw_target=state.grip_target_hold,
                state=state,
                is_trigger_session_mode=True,
            )

        if not inputs.mode_key.endswith(":both"):
            # Single-channel trigger sessions cannot deadlock on opposite-side relax.
            state = replace(state, trigger_require_relax_phase=None)
        state = replace(state, trigger_maintain_active_phase=None)
        if state.trigger_go_latched_phase is None and target_emg >= trigger_activate_thr:
            # Rising edge latches command for the current phase.
            state = replace(state, trigger_go_latched_phase=phase)

        if state.trigger_go_latched_phase == "flexion":
            state = replace(state, active_muscle="flexor")
            raw_target = 1.0
        elif state.trigger_go_latched_phase == "extension":
            state = replace(state, active_muscle="extensor")
            raw_target = 0.0
        else:
            state = replace(state, active_muscle=None)
            raw_target = state.grip_target_hold
        return self._make_output(
            mode_key=inputs.mode_key,
            raw_target=raw_target,
            state=state,
            is_trigger_session_mode=True,
        )


class _TriggerMaintainMachine(_BaseTriggerMachine):
    def step(self, inputs: ControlInputs, state: ControlState) -> ControlOutput:
        state, phase, target_muscle = self._common_prestep(state, inputs.mode_key)
        target_emg = inputs.emg_flexor if target_muscle == "flexor" else inputs.emg_extensor
        trigger_activate_thr = min(1.0, inputs.trigger_thr + inputs.activation_hysteresis)
        trigger_deactivate_thr = max(0.0, inputs.trigger_thr - inputs.deactivation_hysteresis)

        if self._needs_relax_before_rearm(state, inputs.mode_key, phase) and target_emg > trigger_deactivate_thr:
            state = replace(state, active_muscle=None)
            return self._make_output(
                mode_key=inputs.mode_key,
                raw_target=state.grip_target_hold,
                state=state,
                is_trigger_session_mode=True,
            )

        if not inputs.mode_key.endswith(":both"):
            state = replace(state, trigger_require_relax_phase=None)
        state = replace(state, trigger_go_latched_phase=None)
        maintain_was_active = state.trigger_maintain_active_phase == phase
        if state.trigger_maintain_active_phase is None:
            if target_emg >= trigger_activate_thr:
                state = replace(state, trigger_maintain_active_phase=phase)
        elif target_emg < trigger_deactivate_thr:
            state = replace(state, trigger_maintain_active_phase=None)
        maintain_is_active = state.trigger_maintain_active_phase == phase

        if maintain_is_active:
            state = replace(state, active_muscle=target_muscle)
            raw_target = 1.0 if target_muscle == "flexor" else 0.0
            return self._make_output(
                mode_key=inputs.mode_key,
                raw_target=raw_target,
                state=state,
                is_trigger_session_mode=True,
            )

        state = replace(state, active_muscle=None)
        if maintain_was_active and not maintain_is_active:
            # Falling edge should preserve current measured position and immediately
            # push one hold command to prevent endpoint drift.
            hold_target = snap_grip_target(
                grip_target=inputs.hand_pos,
                grip_step=inputs.grip_step,
            )
            state = replace(
                state,
                grip_target_hold=hold_target,
                last_target_direction=0,
                last_command_time=inputs.current_time if inputs.is_motor_output_enabled else state.last_command_time,
            )
            return self._make_output(
                mode_key=inputs.mode_key,
                raw_target=hold_target,
                state=state,
                immediate_grip_command=hold_target if inputs.is_motor_output_enabled else None,
                is_trigger_session_mode=True,
            )
        return self._make_output(
            mode_key=inputs.mode_key,
            raw_target=state.grip_target_hold,
            state=state,
            is_trigger_session_mode=True,
        )


# Explicit mode matrix. Single-channel trigger variants are intentionally listed
# as separate entries to avoid hidden branching between mode families.
_MODE_MACHINES: dict[str, _BaseControlMachine] = {
    "auto:both": _AutoBothMachine(),
    "auto:flexor_only": _AutoFlexorOnlyMachine(),
    "auto:extensor_only": _AutoExtensorOnlyMachine(),
    "auto:none": _AutoNoneMachine(),
    "trigger-and-go:both": _TriggerGoMachine(),
    "trigger-and-go:flexor_only": _TriggerGoMachine(),
    "trigger-and-go:extensor_only": _TriggerGoMachine(),
    "trigger-and-maintain:both": _TriggerMaintainMachine(),
    "trigger-and-maintain:flexor_only": _TriggerMaintainMachine(),
    "trigger-and-maintain:extensor_only": _TriggerMaintainMachine(),
}


def step_control_state_machine(*, inputs: ControlInputs, state: ControlState) -> ControlOutput:
    machine = _MODE_MACHINES.get(inputs.mode_key, _MODE_MACHINES["auto:none"])
    return machine.step(inputs=inputs, state=state)
