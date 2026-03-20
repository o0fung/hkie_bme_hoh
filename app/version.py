import os
import re
from importlib import metadata as importlib_metadata

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:  # pragma: no cover - runtime fallback for older Python
    tomllib = None  # type: ignore[assignment]


def resolve_game_version() -> str:
    """
    Resolve app version from a single source of truth.

    Priority:
      1) pyproject.toml beside this source tree
      2) Installed package metadata
      3) Safe fallback
    """
    pyproject_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "pyproject.toml",
    )
    if os.path.exists(pyproject_path):
        try:
            if tomllib:
                with open(pyproject_path, "rb") as f:
                    pyproject = tomllib.load(f)
                version = str(pyproject.get("project", {}).get("version", "")).strip()
                if version:
                    return version
            else:
                # Python < 3.11 fallback: parse [project] version line safely.
                with open(pyproject_path, "r", encoding="utf-8") as f:
                    in_project_section = False
                    for raw_line in f:
                        line = raw_line.strip()
                        if line.startswith("[") and line.endswith("]"):
                            in_project_section = line == "[project]"
                            continue
                        if in_project_section:
                            match = re.match(r'version\s*=\s*"([^"]+)"', line)
                            if match:
                                return match.group(1).strip()
        except Exception:
            pass

    for package_name in ("hoh-game", "hkie-bme-hoh"):
        try:
            return importlib_metadata.version(package_name)
        except importlib_metadata.PackageNotFoundError:
            pass
        except Exception:
            pass

    return "0.0.0"


GAME_VERSION = resolve_game_version()
