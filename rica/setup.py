from getpass import getpass

from rica.config import (
    DEFAULT_MODEL,
    get_config_path,
    load_config,
    normalize_config,
    save_config,
)


def run_setup() -> dict[str, str | None]:
    existing = _load_existing_config()

    print("Welcome to RICA.\n")
    print("Let's set up your coding agent.\n")

    name = _prompt(
        "What should I call you?",
        default=existing.get("name", ""),
        secret=False,
        required=True,
    )
    api_key = _prompt(
        "Enter your Gemini API key:",
        default=existing.get("api_key", ""),
        secret=True,
        required=True,
    )
    model = _prompt(
        f"Preferred model (default: {DEFAULT_MODEL}):",
        default=existing.get("model", DEFAULT_MODEL),
        secret=False,
        required=False,
    )
    workspace = _prompt(
        "Workspace location (optional):",
        default=existing.get("workspace", "") or "",
        secret=False,
        required=False,
    )

    config = normalize_config(
        {
            "name": name,
            "api_key": api_key,
            "model": model or DEFAULT_MODEL,
            "workspace": workspace or None,
        }
    )
    save_config(config)

    print("\nSetup complete.")
    print(f"Config saved to: {get_config_path()}")
    return config


def ensure_setup() -> dict[str, str | None]:
    try:
        return load_config()
    except FileNotFoundError:
        return run_setup()


def _load_existing_config() -> dict[str, str | None]:
    try:
        return load_config()
    except FileNotFoundError:
        return normalize_config({})


def _prompt(
    label: str,
    default: str = "",
    secret: bool = False,
    required: bool = False,
) -> str:
    while True:
        if default and not secret:
            raw = input(f"{label}\n> [{default}] ").strip()
        else:
            raw = (
                getpass(f"{label}\n> ")
                if secret
                else input(f"{label}\n> ")
            ).strip()

        if raw:
            return raw
        if default:
            return default
        if not required:
            return ""

        print("This value is required.\n")
