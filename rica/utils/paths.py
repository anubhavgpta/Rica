import os
from pathlib import Path

def get_workspace_root() -> Path:
    """
    Default workspace root for Rica outputs.
    Uses RICA_WORKSPACE env var if set,
    otherwise ~/rica_workspace.
    """
    env = os.environ.get("RICA_WORKSPACE")
    if env:
        return Path(env)
    return Path.home() / "rica_workspace"

def ensure_workspace(name: str) -> Path:
    """
    Create and return a named workspace dir
    under the workspace root.
    """
    ws = get_workspace_root() / name
    ws.mkdir(parents=True, exist_ok=True)
    return ws
