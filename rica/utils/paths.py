import os
import re
from pathlib import Path

def sanitize_workspace_name(slug: str) -> str:
    """
    Sanitize a string to create a safe workspace name.
    
    Strips everything except alphanumeric, underscore, and hyphen.
    No apostrophes, backticks, brackets, or dots.
    Limited to 40 characters.
    
    Args:
        slug: Input string (typically from goal)
        
    Returns:
        str: Safe workspace name
    """
    safe = re.sub(r"[^a-zA-Z0-9_\-]", "", slug)
    return safe[:40]

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
