import json
import os
import re
from typing import Dict, List, Optional, Set, Tuple

DEFAULT_LANGUAGE_PACKS: Dict[str, Dict[str, object]] = {
    "en": {
        "name": "English",
        "texts": {
            "btn_settings": "Settings",
            "btn_reset": "Reset",
            "btn_start": "Start",
            "btn_resume": "Resume",
            "btn_pause": "Pause",
            "btn_stop": "Stop",
            "btn_mirror_off": "Mirror: OFF",
            "btn_mirror_on": "Mirror: ON",
            "btn_exit": "Exit",
            "title_main": "Try Control the Exoskeleton Hand !!!",
            "label_flexor_emg": "Flexor EMG",
            "label_extensor_emg": "Extensor EMG",
            "status_lets_start": "Let's Start !!!",
            "status_great_job": "Great Job !!!",
            "status_hold_on_flexion": "Hold Flexion... {count}",
            "status_hold_on_extension": "Hold Extension... {count}",
            "status_games_on_flexion": "Grasp Hand !",
            "status_games_on_extension": "Open Hand !",
            "status_try_harder_flexion": "Try Harder (Flexion) !!!",
            "status_try_harder_extension": "Try Harder (Extension) !!!",
            "round_text": "Round {current}|{total}",
            "win_text": "You Win!",
            "settings_stepper_stars_to_collect": "Stars to Collect",
            "settings_stepper_training_duration_minutes": "Training Duration (min)",
            "settings_option_sound_enabled": "Sound Enabled",
            "settings_option_music_enabled": "Music Enabled",
            "settings_stepper_sound_effect_volume_percent": "Sound Effects Volume %",
            "settings_stepper_music_volume_percent": "Music Volume %",
            "settings_training_muscle_button": "Training Muscle: {mode}",
            "settings_training_muscle_auto": "Auto",
            "settings_training_muscle_flexor_only": "Flexor Only",
            "settings_training_muscle_extensor_only": "Extensor Only",
            "settings_training_muscle_both": "Both Flexor and Extensor",
            "settings_stepper_relax_flexion_percent": "Relax Flexion %",
            "settings_stepper_relax_extension_percent": "Relax Extension %",
            "trigger_time_left_text": "Time Left {minutes}:{seconds}",
            "trigger_repetition_text": "Repetitions {count}",
            "trigger_session_complete": "Session Complete",
            "btn_sound_on": "Sound: ON",
            "btn_sound_off": "Sound: OFF",
            "btn_music_on": "Music: ON",
            "btn_music_off": "Music: OFF",
        },
    },
    "zh-Hant": {
        "name": "Traditional Chinese",
        "texts": {},
    },
    "zh-Hans": {
        "name": "Simplified Chinese",
        "texts": {},
    },
}


def extract_placeholders(text: str) -> Set[str]:
    """Collect Python format placeholders like {count} from a text template."""
    return set(re.findall(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}", str(text)))


def normalize_language_packs(
    packs: Dict[str, Dict[str, object]],
    default_language_packs: Optional[Dict[str, Dict[str, object]]] = None,
) -> Dict[str, Dict[str, object]]:
    """
    Validate and normalize translation packs for runtime safety.

    Rules:
    - English ("en") is canonical key set.
    - Missing keys in non-English packs are auto-filled with English text.
    - Placeholder mismatches are auto-replaced by English text.
    """
    defaults = default_language_packs or DEFAULT_LANGUAGE_PACKS
    default_en_payload = defaults.get("en", {})
    default_en_texts_raw = default_en_payload.get("texts", {})
    default_en_texts = dict(default_en_texts_raw) if isinstance(default_en_texts_raw, dict) else {}

    en_payload = packs.get("en", {})
    en_name = "English"
    en_texts = dict(default_en_texts)
    if isinstance(en_payload, dict):
        en_name = str(en_payload.get("name", en_name))
        en_incoming = en_payload.get("texts", {})
        if isinstance(en_incoming, dict):
            en_texts.update({str(k): str(v) for k, v in en_incoming.items()})

    normalized: Dict[str, Dict[str, object]] = {"en": {"name": en_name, "texts": en_texts}}
    en_keys = set(en_texts.keys())

    for code, payload in packs.items():
        if code == "en":
            continue

        if not isinstance(payload, dict):
            normalized[code] = {"name": str(code), "texts": dict(en_texts)}
            print(f"[WARNING] Language '{code}' has invalid structure; using English placeholders.")
            continue

        name = str(payload.get("name", code))
        incoming_texts_raw = payload.get("texts", {})
        incoming_texts: Dict[str, str] = {}
        if isinstance(incoming_texts_raw, dict):
            incoming_texts = {str(k): str(v) for k, v in incoming_texts_raw.items()}

        missing_keys: List[str] = []
        placeholder_fixed: List[str] = []
        resolved_texts = dict(incoming_texts)
        for key, en_text in en_texts.items():
            candidate = resolved_texts.get(key)
            if not candidate:
                resolved_texts[key] = en_text
                missing_keys.append(key)
                continue

            if extract_placeholders(candidate) != extract_placeholders(en_text):
                resolved_texts[key] = en_text
                placeholder_fixed.append(key)

        extra_keys = [k for k in resolved_texts.keys() if k not in en_keys]
        if missing_keys:
            preview = ", ".join(sorted(missing_keys)[:5])
            if len(missing_keys) > 5:
                preview += ", ..."
            print(
                f"[WARNING] Language '{code}' missing {len(missing_keys)} keys; "
                f"filled with English placeholders. Keys: {preview}"
            )
        if placeholder_fixed:
            preview = ", ".join(sorted(placeholder_fixed)[:5])
            if len(placeholder_fixed) > 5:
                preview += ", ..."
            print(
                f"[WARNING] Language '{code}' has {len(placeholder_fixed)} placeholder mismatches; "
                f"replaced with English placeholders. Keys: {preview}"
            )
        if extra_keys:
            print(f"[INFO] Language '{code}' includes {len(extra_keys)} extra keys not used by the game.")

        normalized[code] = {"name": name, "texts": resolved_texts}

    # Ensure default expected languages always appear in the selector.
    for code, payload in defaults.items():
        if code in normalized:
            continue
        default_name = str(payload.get("name", code)) if isinstance(payload, dict) else code
        normalized[code] = {"name": default_name, "texts": dict(en_texts)}
        print(f"[WARNING] Language '{code}' missing entirely; added with English placeholders.")

    return normalized


def _read_json(path: str) -> Optional[dict]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        print(f"[WARNING] Failed to load language pack file at {path}: {exc}")
        return None


def _read_packaged_json(filename: str) -> Optional[dict]:
    try:
        import importlib.resources as pkg_resources

        assets_pkg = pkg_resources.files("assets")
        assets_file = assets_pkg.joinpath(filename)
        if assets_file.is_file():
            return json.loads(assets_file.read_text(encoding="utf-8"))
    except (
        ImportError,
        ModuleNotFoundError,
        FileNotFoundError,
        AttributeError,
        TypeError,
        OSError,
        json.JSONDecodeError,
    ):
        pass

    # Python < 3.9 fallback
    try:
        import importlib_resources as pkg_resources  # type: ignore

        assets_pkg = pkg_resources.files("assets")
        assets_file = assets_pkg.joinpath(filename)
        with assets_file.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (
        ImportError,
        ModuleNotFoundError,
        FileNotFoundError,
        AttributeError,
        TypeError,
        OSError,
        json.JSONDecodeError,
    ):
        return None


def _parse_language_payload(
    raw: dict,
    default_packs: Dict[str, Dict[str, object]],
) -> Optional[Tuple[Dict[str, Dict[str, object]], str]]:
    if not isinstance(raw, dict):
        return None

    raw_languages = raw.get("languages")
    if not isinstance(raw_languages, dict):
        return None

    parsed: Dict[str, Dict[str, object]] = {}
    for code, payload in raw_languages.items():
        if not isinstance(code, str) or not isinstance(payload, dict):
            continue
        name = payload.get("name", code)
        texts = payload.get("texts", {})
        if not isinstance(name, str) or not isinstance(texts, dict):
            continue
        parsed[code] = {
            "name": name,
            "texts": {str(k): str(v) for k, v in texts.items()},
        }

    if "en" not in parsed:
        parsed["en"] = default_packs["en"]

    # Merge parsed values over defaults so missing keys still fall back.
    merged: Dict[str, Dict[str, object]] = {}
    all_codes = set(default_packs.keys()) | set(parsed.keys())
    for code in all_codes:
        base_name = str(default_packs.get(code, {}).get("name", code))
        base_texts = dict(default_packs.get(code, {}).get("texts", {}))
        incoming = parsed.get(code, {})
        merged_name = str(incoming.get("name", base_name))
        incoming_texts = incoming.get("texts", {})
        if isinstance(incoming_texts, dict):
            base_texts.update({str(k): str(v) for k, v in incoming_texts.items()})
        merged[code] = {"name": merged_name, "texts": base_texts}

    default_language = raw.get("default_language", "en")
    normalized = normalize_language_packs(merged, default_language_packs=default_packs)
    if not isinstance(default_language, str) or default_language not in normalized:
        default_language = "en"
    return normalized, default_language


def load_language_packs(
    candidate_paths: List[str],
    default_language_packs: Optional[Dict[str, Dict[str, object]]] = None,
) -> Tuple[Dict[str, Dict[str, object]], str]:
    default_source = default_language_packs or DEFAULT_LANGUAGE_PACKS
    default_packs = {
        code: {"name": data["name"], "texts": dict(data["texts"])}
        for code, data in default_source.items()
    }

    for path in candidate_paths:
        if not os.path.exists(path):
            continue
        raw = _read_json(path)
        parsed_payload = _parse_language_payload(raw, default_packs) if raw is not None else None
        if parsed_payload is not None:
            print(f"[INFO] Loaded language packs: {path}")
            return parsed_payload

    packaged_languages = _read_packaged_json("languages.json")
    parsed_packaged_payload = (
        _parse_language_payload(packaged_languages, default_packs)
        if packaged_languages is not None
        else None
    )
    if parsed_packaged_payload is not None:
        print("[INFO] Loaded packaged language packs: assets/languages.json")
        return parsed_packaged_payload

    print("[WARNING] No language pack file found. Using built-in English text.")
    return normalize_language_packs(default_packs, default_language_packs=default_packs), "en"
