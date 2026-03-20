import math
import time
from typing import Optional

import numpy as np
import pygame


class AudioManager:
    def __init__(self):
        self._sfx_enabled = True
        self._music_enabled = True
        self._sfx_volume_percent = 60.0
        self._music_volume_percent = 18.0
        self._available = False
        self._bell_sound: Optional[pygame.mixer.Sound] = None
        self._start_sound: Optional[pygame.mixer.Sound] = None
        self._completion_sound: Optional[pygame.mixer.Sound] = None
        self._music_sound: Optional[pygame.mixer.Sound] = None
        self._music_channel: Optional[pygame.mixer.Channel] = None
        self._next_music_sound: Optional[pygame.mixer.Sound] = None
        self._next_music_channel: Optional[pygame.mixer.Channel] = None
        self._music_track_started_at = 0.0
        self._music_track_duration_s = 0.0
        self._music_crossfade_started_at: Optional[float] = None
        self._music_crossfade_seconds = 2.2
        self._available = self._init_audio()
        if self._available:
            self._apply_volumes()

    def _init_audio(self) -> bool:
        try:
            if pygame.mixer.get_init() is None:
                pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=1024)
            self._bell_sound = self._build_bell_sound()
            self._start_sound = self._build_start_chime_sound()
            self._completion_sound = self._build_completion_jingle_sound()
            self._music_sound = self._build_background_music_loop()
            return True
        except Exception as exc:
            print(f"[WARNING] Audio initialization failed: {exc}")
            self._bell_sound = None
            self._start_sound = None
            self._completion_sound = None
            self._music_sound = None
            self._music_channel = None
            self._next_music_sound = None
            self._next_music_channel = None
            return False

    def _build_bell_sound(self) -> pygame.mixer.Sound:
        sample_rate = 44100
        duration_s = 0.65
        t = np.linspace(0.0, duration_s, int(sample_rate * duration_s), endpoint=False, dtype=np.float32)
        envelope = np.exp(-7.8 * t)
        wave = (
            0.52 * np.sin(2.0 * math.pi * 1046.5 * t)
            + 0.19 * np.sin(2.0 * math.pi * 1568.0 * t + 0.24)
            + 0.08 * np.sin(2.0 * math.pi * 2093.0 * t + 0.51)
        ) * envelope
        stereo = np.column_stack((wave, wave))
        audio = np.int16(np.clip(stereo, -1.0, 1.0) * 32767)
        return pygame.sndarray.make_sound(audio)

    def _build_background_music_loop(self) -> pygame.mixer.Sound:
        sample_rate = 44100
        duration_s = 120.0
        t = np.linspace(0.0, duration_s, int(sample_rate * duration_s), endpoint=False, dtype=np.float32)
        left = np.zeros_like(t)
        right = np.zeros_like(t)
        rng = np.random.default_rng()

        # Slow binaural-style bed with gentle motion.
        bed_lfo_a = 0.5 + 0.5 * np.sin(2.0 * math.pi * (1.0 / 17.0) * t + 0.45)
        bed_lfo_b = 0.5 + 0.5 * np.sin(2.0 * math.pi * (1.0 / 23.0) * t + 2.1)
        left += 0.034 * np.sin(2.0 * math.pi * 109.0 * t + 0.1) * (0.55 + 0.45 * bed_lfo_a)
        right += 0.034 * np.sin(2.0 * math.pi * 109.6 * t + 0.3) * (0.55 + 0.45 * bed_lfo_b)
        left += 0.024 * np.sin(2.0 * math.pi * 164.0 * t + 0.35) * (0.55 + 0.45 * (1.0 - bed_lfo_b))
        right += 0.024 * np.sin(2.0 * math.pi * 164.8 * t + 0.5) * (0.55 + 0.45 * (1.0 - bed_lfo_a))

        # Add softly randomized "droplet" notes for ASMR-like variation.
        note_scale = np.array([220.0, 246.94, 293.66, 329.63, 392.0, 440.0], dtype=np.float32)
        note_count = 48
        for _ in range(note_count):
            start = float(rng.uniform(0.0, duration_s - 5.2))
            dur = float(rng.uniform(2.8, 5.0))
            end = min(duration_s, start + dur)
            start_idx = int(start * sample_rate)
            end_idx = int(end * sample_rate)
            if end_idx - start_idx <= 8:
                continue
            local_t = t[start_idx:end_idx] - start
            env = np.sin(np.linspace(0.0, math.pi, end_idx - start_idx, dtype=np.float32)) ** 1.7
            note_hz = float(rng.choice(note_scale))
            shimmer = 0.84 + 0.16 * np.sin(
                2.0 * math.pi * float(rng.uniform(0.08, 0.22)) * local_t
                + float(rng.uniform(0.0, math.tau))
            )
            note = (
                0.019 * np.sin(2.0 * math.pi * note_hz * local_t + float(rng.uniform(0.0, math.tau)))
                + 0.006 * np.sin(2.0 * math.pi * (note_hz * 2.0) * local_t + float(rng.uniform(0.0, math.tau)))
            ) * env * shimmer
            pan = float(rng.uniform(-0.5, 0.5))
            left_gain = 1.0 - max(0.0, pan)
            right_gain = 1.0 - max(0.0, -pan)
            left[start_idx:end_idx] += note * left_gain
            right[start_idx:end_idx] += note * right_gain

        # Very low-level filtered noise for soft texture.
        noise = rng.normal(0.0, 1.0, size=t.shape).astype(np.float32)
        kernel = np.ones(520, dtype=np.float32) / 520.0
        smooth_noise = np.convolve(noise, kernel, mode="same")
        left += 0.008 * smooth_noise * (0.6 + 0.4 * bed_lfo_b)
        right += 0.008 * smooth_noise * (0.6 + 0.4 * bed_lfo_a)

        # Light edge softening; runtime crossfade handles the actual loop seam.
        fade_len = int(sample_rate * 0.35)
        fade = np.ones_like(t)
        fade[:fade_len] = np.linspace(0.0, 1.0, fade_len, dtype=np.float32)
        fade[-fade_len:] = np.linspace(1.0, 0.0, fade_len, dtype=np.float32)
        left *= fade
        right *= fade
        stereo = np.column_stack((left, right))
        audio = np.int16(np.clip(stereo, -1.0, 1.0) * 32767)
        return pygame.sndarray.make_sound(audio)

    def _build_start_chime_sound(self) -> pygame.mixer.Sound:
        sample_rate = 44100
        notes_hz = [523.25, 659.26, 783.99]  # C5 -> E5 -> G5
        note_duration_s = 0.16
        gap_s = 0.03
        total_s = len(notes_hz) * (note_duration_s + gap_s) + 0.05
        total_samples = int(sample_rate * total_s)
        mono = np.zeros(total_samples, dtype=np.float32)
        cursor = 0
        for hz in notes_hz:
            note_samples = int(sample_rate * note_duration_s)
            note_t = np.linspace(0.0, note_duration_s, note_samples, endpoint=False, dtype=np.float32)
            env = np.sin(np.linspace(0.0, math.pi, note_samples, dtype=np.float32)) ** 1.2
            tone = (
                0.24 * np.sin(2.0 * math.pi * hz * note_t)
                + 0.08 * np.sin(2.0 * math.pi * (hz * 2.0) * note_t + 0.1)
            ) * env
            end = min(total_samples, cursor + note_samples)
            mono[cursor:end] += tone[: end - cursor]
            cursor += note_samples + int(sample_rate * gap_s)

        stereo = np.column_stack((mono, mono))
        audio = np.int16(np.clip(stereo, -1.0, 1.0) * 32767)
        return pygame.sndarray.make_sound(audio)

    def _build_completion_jingle_sound(self) -> pygame.mixer.Sound:
        sample_rate = 44100
        notes_hz = [523.25, 659.26, 783.99, 1046.5]  # C5 -> E5 -> G5 -> C6
        note_duration_s = 0.24
        gap_s = 0.04
        total_s = len(notes_hz) * (note_duration_s + gap_s) + 0.12
        total_samples = int(sample_rate * total_s)
        mono = np.zeros(total_samples, dtype=np.float32)
        cursor = 0
        for hz in notes_hz:
            note_samples = int(sample_rate * note_duration_s)
            note_t = np.linspace(0.0, note_duration_s, note_samples, endpoint=False, dtype=np.float32)
            env = np.sin(np.linspace(0.0, math.pi, note_samples, dtype=np.float32)) ** 1.6
            upper_boost = 1.12 if hz >= 1000.0 else 1.0
            tone = upper_boost * (
                0.24 * np.sin(2.0 * math.pi * hz * note_t)
                + 0.09 * np.sin(2.0 * math.pi * (hz * 2.0) * note_t + 0.1)
                + 0.035 * np.sin(2.0 * math.pi * (hz * 3.0) * note_t + 0.2)
            ) * env
            end = min(total_samples, cursor + note_samples)
            mono[cursor:end] += tone[: end - cursor]
            # Soft shimmer layer keeps it chime-like instead of buzzy.
            mono[cursor:end] += (
                0.02
                * np.sin(2.0 * math.pi * (hz * 0.5) * note_t[: end - cursor] + 0.15)
                * env[: end - cursor]
            )
            cursor += note_samples + int(sample_rate * gap_s)

        stereo = np.column_stack((mono, mono))
        audio = np.int16(np.clip(stereo, -1.0, 1.0) * 32767)
        return pygame.sndarray.make_sound(audio)

    def set_sound_effect_enabled(self, enabled: bool):
        self._sfx_enabled = bool(enabled)
        self._apply_volumes()

    def is_sound_effect_enabled(self) -> bool:
        return self._sfx_enabled

    def set_music_enabled(self, enabled: bool):
        self._music_enabled = bool(enabled)
        self._apply_volumes()

    def is_music_enabled(self) -> bool:
        return self._music_enabled

    def set_sound_effect_volume_percent(self, volume_percent: float):
        self._sfx_volume_percent = max(0.0, min(100.0, float(volume_percent)))
        self._apply_volumes()

    def set_music_volume_percent(self, volume_percent: float):
        self._music_volume_percent = max(0.0, min(100.0, float(volume_percent)))
        self._apply_volumes()

    def play_progress_bell(self):
        if not self._available or not self._sfx_enabled or self._bell_sound is None:
            return
        self._bell_sound.play()

    def play_start_chime(self):
        if not self._available or not self._sfx_enabled or self._start_sound is None:
            return
        self._start_sound.play()

    def play_completion_jingle(self):
        if not self._available or not self._sfx_enabled or self._completion_sound is None:
            return
        self._completion_sound.play()

    def set_main_scene_active(self, active: bool):
        if not self._available or self._music_sound is None:
            return
        if not active or not self._music_enabled:
            self._stop_all_music_channels()
            return
        if self._music_channel is None or not self._music_channel.get_busy():
            self._start_current_music_track()
        self._update_music_crossfade()
        self._apply_volumes()

    def _stop_all_music_channels(self):
        if self._music_channel is not None:
            self._music_channel.stop()
            self._music_channel = None
        if self._next_music_channel is not None:
            self._next_music_channel.stop()
            self._next_music_channel = None
        self._next_music_sound = None
        self._music_crossfade_started_at = None

    def _start_current_music_track(self):
        if self._music_sound is None:
            self._music_sound = self._build_background_music_loop()
        self._music_channel = self._music_sound.play(loops=0)
        self._music_track_started_at = time.perf_counter()
        self._music_track_duration_s = float(self._music_sound.get_length())
        self._music_crossfade_started_at = None
        self._next_music_sound = None
        self._next_music_channel = None

    def _update_music_crossfade(self):
        if (
            self._music_channel is None
            or not self._music_channel.get_busy()
            or self._music_track_duration_s <= 0.0
        ):
            return
        now = time.perf_counter()
        elapsed = now - self._music_track_started_at
        remaining = self._music_track_duration_s - elapsed

        # Start next randomized track early and crossfade into it.
        if remaining <= self._music_crossfade_seconds and self._next_music_channel is None:
            self._next_music_sound = self._build_background_music_loop()
            self._next_music_channel = self._next_music_sound.play(loops=0)
            self._music_crossfade_started_at = now
            if self._next_music_channel is not None:
                self._next_music_channel.set_volume(0.0)

        if self._next_music_channel is None or self._music_crossfade_started_at is None:
            return

        progress = (now - self._music_crossfade_started_at) / max(0.05, self._music_crossfade_seconds)
        progress = max(0.0, min(1.0, progress))
        target_music_volume = (self._music_volume_percent / 100.0) if self._music_enabled else 0.0
        if self._music_channel is not None:
            self._music_channel.set_volume(target_music_volume * (1.0 - progress))
        self._next_music_channel.set_volume(target_music_volume * progress)

        if progress >= 1.0 or (self._music_channel is not None and not self._music_channel.get_busy()):
            if self._music_channel is not None:
                self._music_channel.stop()
            self._music_channel = self._next_music_channel
            self._music_sound = self._next_music_sound
            self._music_track_started_at = float(self._music_crossfade_started_at)
            self._music_track_duration_s = (
                float(self._music_sound.get_length()) if self._music_sound is not None else 0.0
            )
            self._next_music_channel = None
            self._next_music_sound = None
            self._music_crossfade_started_at = None

    def _apply_volumes(self):
        if pygame.mixer.get_init() is None:
            return
        sfx_volume = (self._sfx_volume_percent / 100.0) if self._sfx_enabled else 0.0
        music_volume = (self._music_volume_percent / 100.0) if self._music_enabled else 0.0
        if self._bell_sound is not None:
            self._bell_sound.set_volume(sfx_volume)
        if self._start_sound is not None:
            self._start_sound.set_volume(sfx_volume)
        if self._completion_sound is not None:
            self._completion_sound.set_volume(sfx_volume)
        if self._music_sound is not None:
            self._music_sound.set_volume(music_volume)
        if self._music_channel is not None and self._next_music_channel is None:
            self._music_channel.set_volume(music_volume)
        if self._next_music_channel is not None and self._music_crossfade_started_at is None:
            self._next_music_channel.set_volume(music_volume)

    def shutdown(self):
        self._stop_all_music_channels()
