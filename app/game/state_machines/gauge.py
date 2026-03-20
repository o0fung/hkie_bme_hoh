from dataclasses import dataclass


@dataclass
class GaugeInputs:
    mode_key: str
    use_flexor: bool
    use_extensor: bool
    hand_pos: float
    hand_start: float
    raw_target: float
    target_flexion_ratio: float
    target_extension_ratio: float
    is_mirrored: bool


@dataclass
class GaugeOutput:
    target_flexion: float
    target_extension: float
    mirrored: bool
    show_flexion: bool
    show_extension: bool
    show_partition: bool
    show_flexion_target: bool
    show_extension_target: bool
    value: float
    partition: float
    gauge_target_flexion: float
    gauge_target_extension: float


def build_gauge_output(*, inputs: GaugeInputs) -> GaugeOutput:
    """
    Build a mode-aware gauge view model.

    Trigger families should not depend on hand_start partition semantics, so in
    trigger modes we render full-range gauge targets (ratio domain) and hide the
    partition marker. Auto families preserve original hand_start-partition behavior.
    """
    trigger_mode_active = inputs.mode_key.startswith("trigger-and-")
    target_flexion = inputs.hand_start + (1.0 - inputs.hand_start) * inputs.target_flexion_ratio
    target_extension = inputs.hand_start * (1.0 - inputs.target_extension_ratio)

    if trigger_mode_active and inputs.use_flexor and inputs.use_extensor:
        return GaugeOutput(
            target_flexion=target_flexion,
            target_extension=target_extension,
            mirrored=inputs.is_mirrored,
            show_flexion=True,
            show_extension=True,
            show_partition=False,
            show_flexion_target=True,
            show_extension_target=True,
            value=max(0.0, min(1.0, inputs.hand_pos)),
            partition=0.0,
            gauge_target_flexion=max(0.0, min(1.0, inputs.target_flexion_ratio)),
            gauge_target_extension=max(0.0, min(1.0, inputs.target_extension_ratio)),
        )

    if inputs.use_flexor and inputs.use_extensor:
        return GaugeOutput(
            target_flexion=target_flexion,
            target_extension=target_extension,
            mirrored=inputs.is_mirrored,
            show_flexion=True,
            show_extension=True,
            show_partition=True,
            show_flexion_target=True,
            show_extension_target=True,
            value=max(0.0, min(1.0, inputs.hand_pos)),
            partition=inputs.hand_start,
            gauge_target_flexion=target_flexion,
            gauge_target_extension=target_extension,
        )

    if inputs.use_flexor:
        return GaugeOutput(
            target_flexion=target_flexion,
            target_extension=target_extension,
            mirrored=not inputs.is_mirrored,
            show_flexion=True,
            show_extension=False,
            show_partition=False,
            show_flexion_target=True,
            show_extension_target=False,
            value=max(0.0, min(1.0, inputs.raw_target)),
            partition=0.0,
            gauge_target_flexion=max(0.0, min(1.0, inputs.target_flexion_ratio)),
            gauge_target_extension=0.0,
        )

    if inputs.use_extensor:
        return GaugeOutput(
            target_flexion=target_flexion,
            target_extension=target_extension,
            mirrored=inputs.is_mirrored,
            show_flexion=False,
            show_extension=True,
            show_partition=False,
            show_flexion_target=False,
            show_extension_target=True,
            value=max(0.0, min(1.0, 1.0 - inputs.raw_target)),
            partition=0.0,
            gauge_target_flexion=0.0,
            gauge_target_extension=max(0.0, min(1.0, inputs.target_extension_ratio)),
        )

    return GaugeOutput(
        target_flexion=target_flexion,
        target_extension=target_extension,
        mirrored=inputs.is_mirrored,
        show_flexion=False,
        show_extension=False,
        show_partition=False,
        show_flexion_target=False,
        show_extension_target=False,
        value=max(0.0, min(1.0, inputs.hand_pos)),
        partition=inputs.hand_start,
        gauge_target_flexion=target_flexion,
        gauge_target_extension=target_extension,
    )
