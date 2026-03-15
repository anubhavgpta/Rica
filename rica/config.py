import json
from pathlib import Path
from typing import Any


DEFAULT_MODEL = "gemini-2.5-flash"
CONFIG_DIRNAME = ".rica"
CONFIG_FILENAME = "config.json"


def get_config_dir() -> Path:
    return Path.home() / CONFIG_DIRNAME


def get_config_path() -> Path:
    return get_config_dir() / CONFIG_FILENAME


def config_exists() -> bool:
    return get_config_path().exists()


def load_config() -> dict[str, Any]:
    config_path = get_config_path()
    if not config_path.exists():
        raise FileNotFoundError(
            f"RICA config not found at {config_path}"
        )

    with config_path.open(
        "r", encoding="utf-8"
    ) as handle:
        data = json.load(handle)

    return normalize_config(data)


def save_config(config: dict[str, Any]) -> Path:
    config_path = get_config_path()
    config_path.parent.mkdir(
        parents=True, exist_ok=True
    )

    normalized = normalize_config(config)
    with config_path.open(
        "w", encoding="utf-8"
    ) as handle:
        json.dump(normalized, handle, indent=2)
        handle.write("\n")

    return config_path


def normalize_config(
    config: dict[str, Any] | None,
) -> dict[str, Any]:
    data = dict(config or {})

    workspace = data.get("workspace")
    if workspace:
        data["workspace"] = str(
            Path(workspace).expanduser()
        )
    else:
        data["workspace"] = None

    data["name"] = str(data.get("name", "")).strip()
    data["api_key"] = str(
        data.get("api_key", "")
    ).strip()
    data["model"] = str(
        data.get("model") or DEFAULT_MODEL
    ).strip()
    if not data["model"]:
        data["model"] = DEFAULT_MODEL
    
    # Default timeout and reviewer settings
    data["review_timeout"] = int(data.get("review_timeout", 15))  # Reduced from 30
    data["enable_reviewer"] = bool(data.get("enable_reviewer", False))  # Disabled by default for speed
    data["max_fix_attempts"] = int(data.get("max_fix_attempts", 2))  # Reduced from 5
    data["max_test_iterations"] = int(data.get("max_test_iterations", 1))  # Reduced from 3
    data["codegen_attempts"] = int(data.get("codegen_attempts", 2))  # Reduced from 3

    return data


def redact_config(
    config: dict[str, Any],
) -> dict[str, Any]:
    redacted = normalize_config(config)
    api_key = redacted.get("api_key", "")
    if api_key:
        if len(api_key) <= 8:
            redacted["api_key"] = "*" * len(api_key)
        else:
            redacted["api_key"] = (
                f"{api_key[:4]}...{api_key[-4:]}"
            )
    return redacted
