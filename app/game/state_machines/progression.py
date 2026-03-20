from dataclasses import replace

from .models import ProgressInputs, ProgressOutput, ProgressState


class _BaseProgressMachine:
    def step(self, inputs: ProgressInputs, state: ProgressState) -> ProgressOutput:
        raise NotImplementedError()

    def _base_output(
        self,
        *,
        state: ProgressState,
        should_return_early: bool,
        play_progress_bell: bool = False,
        play_completion_jingle: bool = False,
    ) -> ProgressOutput:
        return ProgressOutput(
            should_return_early=should_return_early,
            stars_collected=state.stars_collected,
            cycle_phase=state.cycle_phase,
            countdown_timer=state.countdown_timer,
            trigger_phase_wait_timer=state.trigger_phase_wait_timer,
            show_great_job=state.show_great_job,
            great_job_muscle=state.great_job_muscle,
            trigger_repetition_count=state.trigger_repetition_count,
            trigger_require_relax_phase=state.trigger_require_relax_phase,
            play_progress_bell=play_progress_bell,
            play_completion_jingle=play_completion_jingle,
        )

    def _phase_target_reached(
        self,
        *,
        inputs: ProgressInputs,
        state: ProgressState,
        trigger_mode_active: bool,
    ) -> bool:
        if trigger_mode_active:
            # Trigger sessions use endpoint tolerance because hardware may not
            # consistently hit exact 0.0/1.0 positions.
            end_tolerance = max(0.02, state.grip_step * 0.5)
            trigger_flexion_goal = min(inputs.target_flexion, 1.0 - end_tolerance)
            trigger_extension_goal = max(inputs.target_extension, end_tolerance)
            if state.cycle_phase == "flexion":
                return inputs.hand_pos >= trigger_flexion_goal
            return inputs.hand_pos <= trigger_extension_goal
        if state.cycle_phase == "flexion":
            return inputs.hand_pos >= inputs.target_flexion
        return inputs.hand_pos <= inputs.target_extension

    def _target_muscle(self, state: ProgressState) -> str:
        if state.effective_training_mode == "flexor_only":
            return "flexor"
        if state.effective_training_mode == "extensor_only":
            return "extensor"
        return "flexor" if state.cycle_phase == "flexion" else "extensor"


class _AutoProgressMachine(_BaseProgressMachine):
    def step(self, inputs: ProgressInputs, state: ProgressState) -> ProgressOutput:
        if not state.is_motor_output_enabled:
            state = replace(state, countdown_timer=0.0, trigger_phase_wait_timer=0.0)
            return self._base_output(state=state, should_return_early=False)
        if state.stars_collected >= state.max_stars:
            state = replace(state, countdown_timer=0.0, trigger_phase_wait_timer=0.0)
            return self._base_output(
                state=state,
                should_return_early=True,
                play_completion_jingle=not inputs.was_complete_before_tick,
            )

        if state.effective_training_mode == "flexor_only":
            state = replace(state, cycle_phase="flexion")
        elif state.effective_training_mode == "extensor_only":
            state = replace(state, cycle_phase="extension")

        phase_target_reached = self._phase_target_reached(
            inputs=inputs,
            state=state,
            trigger_mode_active=False,
        )
        if state.active_muscle != self._target_muscle(state):
            phase_target_reached = False

        play_progress_bell = False
        play_completion_jingle = False
        if phase_target_reached:
            if state.countdown_timer <= 0.0:
                # First frame of successful hold: arm countdown timer.
                state = replace(state, countdown_timer=inputs.countdown_seconds)
            else:
                state = replace(state, countdown_timer=max(0.0, state.countdown_timer - inputs.dt))
                if state.countdown_timer == 0.0:
                    state = replace(state, show_great_job=True, great_job_muscle=state.active_muscle)
                    if state.effective_training_mode == "both" and state.cycle_phase == "flexion":
                        state = replace(state, cycle_phase="extension")
                    else:
                        next_stars = min(state.max_stars, state.stars_collected + 1)
                        next_phase = "flexion"
                        if state.effective_training_mode == "extensor_only":
                            next_phase = "extension"
                        state = replace(state, stars_collected=next_stars, cycle_phase=next_phase)
        else:
            state = replace(state, countdown_timer=0.0, trigger_phase_wait_timer=0.0)

        progress_units_after = state.stars_collected * 2
        if state.effective_training_mode == "both" and state.stars_collected < state.max_stars and state.cycle_phase == "extension":
            progress_units_after += 1
        if progress_units_after > inputs.progress_units_before:
            play_progress_bell = True
        if (not inputs.was_complete_before_tick) and state.stars_collected >= state.max_stars:
            play_completion_jingle = True
        return self._base_output(
            state=state,
            should_return_early=False,
            play_progress_bell=play_progress_bell,
            play_completion_jingle=play_completion_jingle,
        )


class _TriggerProgressMachine(_BaseProgressMachine):
    def step(self, inputs: ProgressInputs, state: ProgressState) -> ProgressOutput:
        if not state.is_motor_output_enabled:
            state = replace(state, countdown_timer=0.0, trigger_phase_wait_timer=0.0)
            return self._base_output(state=state, should_return_early=False)
        if state.trigger_session_remaining_s <= 0.0:
            state = replace(state, countdown_timer=0.0, trigger_phase_wait_timer=0.0)
            return self._base_output(
                state=state,
                should_return_early=True,
                play_completion_jingle=not inputs.was_complete_before_tick,
            )
        if state.stars_collected >= state.max_stars:
            state = replace(state, countdown_timer=0.0, trigger_phase_wait_timer=0.0)
            return self._base_output(
                state=state,
                should_return_early=True,
                play_completion_jingle=not inputs.was_complete_before_tick,
            )

        if state.effective_training_mode == "flexor_only":
            state = replace(state, cycle_phase="flexion")
        elif state.effective_training_mode == "extensor_only":
            state = replace(state, cycle_phase="extension")

        phase_target_reached = self._phase_target_reached(
            inputs=inputs,
            state=state,
            trigger_mode_active=True,
        )
        trigger_phase_progressed = False
        if phase_target_reached:
            state = replace(state, countdown_timer=0.0)
            trigger_wait_done = False
            if inputs.trigger_wait_seconds <= 0.0:
                trigger_wait_done = True
            elif state.trigger_phase_wait_timer <= 0.0:
                state = replace(state, trigger_phase_wait_timer=inputs.trigger_wait_seconds)
            else:
                timer = max(0.0, state.trigger_phase_wait_timer - inputs.dt)
                trigger_wait_done = timer == 0.0
                state = replace(state, trigger_phase_wait_timer=timer)

            if trigger_wait_done:
                trigger_phase_progressed = True
                state = replace(
                    state,
                    trigger_phase_wait_timer=0.0,
                    show_great_job=True,
                    great_job_muscle=state.active_muscle,
                )
                if state.effective_training_mode == "both" and state.cycle_phase == "flexion":
                    state = replace(
                        state,
                        cycle_phase="extension",
                        trigger_require_relax_phase="extension",
                    )
                else:
                    next_reps = state.trigger_repetition_count + 1
                    next_phase = "flexion"
                    next_relax_phase = state.trigger_require_relax_phase
                    if state.effective_training_mode == "both":
                        next_phase = "flexion"
                        next_relax_phase = "flexion"
                    elif state.effective_training_mode == "extensor_only":
                        next_phase = "extension"
                    state = replace(
                        state,
                        trigger_repetition_count=next_reps,
                        cycle_phase=next_phase,
                        trigger_require_relax_phase=next_relax_phase,
                    )
        else:
            state = replace(state, countdown_timer=0.0, trigger_phase_wait_timer=0.0)

        play_completion = (not inputs.was_complete_before_tick) and (
            state.trigger_session_remaining_s <= 0.0 or state.stars_collected >= state.max_stars
        )
        return self._base_output(
            state=state,
            should_return_early=False,
            play_progress_bell=trigger_phase_progressed,
            play_completion_jingle=play_completion,
        )


# Keep explicit matrix entries so every supported combination has a visible owner.
_PROGRESSION_MACHINES: dict[str, _BaseProgressMachine] = {
    "auto:both": _AutoProgressMachine(),
    "auto:flexor_only": _AutoProgressMachine(),
    "auto:extensor_only": _AutoProgressMachine(),
    "auto:none": _AutoProgressMachine(),
    "trigger-and-go:both": _TriggerProgressMachine(),
    "trigger-and-go:flexor_only": _TriggerProgressMachine(),
    "trigger-and-go:extensor_only": _TriggerProgressMachine(),
    "trigger-and-maintain:both": _TriggerProgressMachine(),
    "trigger-and-maintain:flexor_only": _TriggerProgressMachine(),
    "trigger-and-maintain:extensor_only": _TriggerProgressMachine(),
}


def step_progression_state_machine(*, inputs: ProgressInputs, state: ProgressState) -> ProgressOutput:
    machine = _PROGRESSION_MACHINES.get(inputs.mode_key, _PROGRESSION_MACHINES["auto:none"])
    return machine.step(inputs=inputs, state=state)
