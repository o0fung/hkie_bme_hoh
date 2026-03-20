from dataclasses import dataclass
from typing import Optional


VALID_TRIGGER_MODES = {"auto", "trigger-and-go", "trigger-and-maintain"}


def normalize_trigger_mode(value: str) -> str:
    mode = str(value or "auto").strip().lower()
    if mode not in VALID_TRIGGER_MODES:
        return "auto"
    return mode


def control_mode_key(*, effective_training_mode: str, trigger_mode: str) -> str:
    """
    Build a stable dispatch key for control/progression state-machine lookup.

    Key format is "<trigger_family>:<training_mode>" where:
    - trigger_family is "auto", "trigger-and-go", or "trigger-and-maintain"
    - training_mode is "both", "flexor_only", "extensor_only", or "none"
    """
    normalized_trigger = normalize_trigger_mode(trigger_mode)
    training_mode = str(effective_training_mode or "none")
    if training_mode == "none":
        return "auto:none"
    if normalized_trigger in {"trigger-and-go", "trigger-and-maintain"}:
        return f"{normalized_trigger}:{training_mode}"
    return f"auto:{training_mode}"


@dataclass
class ControlInputs:
    mode_key: str
    use_flexor: bool
    use_extensor: bool
    emg_flexor: float
    emg_extensor: float
    hand_start: float
    base_thr: float
    relax_flexion_thr: float
    relax_extension_thr: float
    trigger_thr: float
    activation_hysteresis: float
    deactivation_hysteresis: float
    grip_step: float
    is_motor_output_enabled: bool
    current_time: float
    hand_pos: float


@dataclass
class ControlState:
    cycle_phase: str
    active_muscle: Optional[str]
    grip_target_hold: float
    last_target_direction: int
    last_command_time: float
    trigger_go_latched_phase: Optional[str]
    trigger_maintain_active_phase: Optional[str]
    trigger_require_relax_phase: Optional[str]


@dataclass
class ControlOutput:
    raw_target: float
    cycle_phase: str
    active_muscle: Optional[str]
    grip_target_hold: float
    last_target_direction: int
    last_command_time: float
    trigger_go_latched_phase: Optional[str]
    trigger_maintain_active_phase: Optional[str]
    trigger_require_relax_phase: Optional[str]
    immediate_grip_command: Optional[float]
    is_trigger_session_mode: bool
    mode_key: str


@dataclass
class ProgressInputs:
    mode_key: str
    dt: float
    hand_pos: float
    target_flexion: float
    target_extension: float
    countdown_seconds: float
    trigger_wait_seconds: float
    progress_units_before: int
    was_complete_before_tick: bool


@dataclass
class ProgressState:
    is_motor_output_enabled: bool
    is_trigger_session_mode: bool
    trigger_session_remaining_s: float
    stars_collected: int
    max_stars: int
    effective_training_mode: str
    cycle_phase: str
    active_muscle: Optional[str]
    countdown_timer: float
    trigger_phase_wait_timer: float
    show_great_job: bool
    great_job_muscle: Optional[str]
    trigger_repetition_count: int
    trigger_require_relax_phase: Optional[str]
    grip_step: float


@dataclass
class ProgressOutput:
    should_return_early: bool
    stars_collected: int
    cycle_phase: str
    countdown_timer: float
    trigger_phase_wait_timer: float
    show_great_job: bool
    great_job_muscle: Optional[str]
    trigger_repetition_count: int
    trigger_require_relax_phase: Optional[str]
    play_progress_bell: bool
    play_completion_jingle: bool
