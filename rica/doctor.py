import importlib.util
import platform
import sys
from pathlib import Path

from rica.config import (
    get_config_path,
    load_config,
    normalize_config,
)


def run_doctor() -> int:
    print("RICA Doctor\n")

    checks = collect_diagnostics()
    for label, ok, detail in checks:
        status = "OK" if ok else "FAIL"
        suffix = f" ({detail})" if detail else ""
        print(f"{label}: {status}{suffix}")

    if all(item[1] for item in checks):
        print("\nSystem ready.")
        return 0

    print("\nSystem not ready.")
    return 1


def collect_diagnostics() -> list[tuple[str, bool, str]]:
    config_path = get_config_path()
    config_exists = config_path.exists()
    config = (
        normalize_config(load_config())
        if config_exists
        else normalize_config({})
    )

    workspace = (
        Path(config["workspace"]).expanduser()
        if config.get("workspace")
        else Path.home() / "rica_workspace"
    )

    return [
        (
            "Python version",
            sys.version_info >= (3, 11),
            platform.python_version(),
        ),
        (
            "RICA config file",
            config_exists,
            str(config_path),
        ),
        (
            "Gemini API connectivity",
            bool(config.get("api_key"))
            and _check_gemini_connectivity(config),
            "",
        ),
        (
            "Workspace",
            workspace.exists(),
            str(workspace),
        ),
        (
            "pytest installed",
            importlib.util.find_spec("pytest")
            is not None,
            "",
        ),
    ]


def _check_gemini_connectivity(
    config: dict[str, str | None],
) -> bool:
    try:
        import google.genai as genai

        client = genai.Client(
            api_key=config["api_key"]
        )
        pager = client.models.list(
            config={"page_size": 1}
        )
        next(iter(pager))
        return True
    except Exception:
        return False
