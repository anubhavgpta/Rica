"""
Rica Hook System - Plugin/Hook Infrastructure

Provides event-driven hook system for extending Rica functionality.
"""

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

# Try to import version, fallback to "unknown"
try:
    from rica import __version__
except ImportError:
    __version__ = "unknown"

# Constants
HOOKS_DIR = Path.home() / ".rica" / "hooks"

VALID_EVENTS = [
    "pre_plan",
    "post_plan", 
    "pre_build",
    "post_build",
    "pre_debug",
    "post_debug",
    "pre_export",
    "post_export",
    "post_import",
    # L18 agent events
    "pre_agent_task",
    "post_agent_task", 
    "agent_stuck",
]


def discover_hooks() -> Dict[str, Path]:
    """
    Scan HOOKS_DIR for hook scripts.
    
    Returns:
        Dict mapping event names to their script paths
    """
    hooks = {}
    
    if not HOOKS_DIR.exists():
        return hooks
    
    for event in VALID_EVENTS:
        hook_script = HOOKS_DIR / f"{event}.py"
        if hook_script.exists() and hook_script.is_file():
            hooks[event] = hook_script
    
    return hooks


def build_payload(event: str, session_id: Optional[str], extra: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Build payload dictionary for hook execution.
    
    Args:
        event: Hook event name
        session_id: Optional session identifier
        extra: Optional additional data
        
    Returns:
        Payload dictionary
    """
    return {
        "event": event,
        "session_id": session_id,
        "rica_version": __version__,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "extra": extra or {}
    }


def fire_hook(event: str, session_id: Optional[str] = None, extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Execute hook script for given event.
    
    Args:
        event: Hook event name
        session_id: Optional session identifier  
        extra: Optional additional data
        
    Returns:
        Result dictionary with execution details
    """
    result = {
        "event": event,
        "status": "no_hook",
        "skipped": True,
        "returncode": None,
        "stdout": "",
        "stderr": ""
    }
    
    # Discover hook script
    hooks = discover_hooks()
    if event not in hooks:
        return result
    
    hook_script = hooks[event]
    payload = build_payload(event, session_id, extra)
    
    try:
        # Execute hook script
        proc = subprocess.run(
            [sys.executable, str(hook_script), json.dumps(payload)],
            timeout=30,
            capture_output=True,
            text=True,
            cwd=HOOKS_DIR
        )
        
        result.update({
            "status": "ok" if proc.returncode == 0 else "error",
            "skipped": False,
            "returncode": proc.returncode,
            "stdout": proc.stdout.strip(),
            "stderr": proc.stderr.strip()
        })
        
    except subprocess.TimeoutExpired:
        result.update({
            "status": "timeout",
            "skipped": False,
            "returncode": None
        })
        
    except Exception as e:
        result.update({
            "status": "error", 
            "skipped": False,
            "returncode": None,
            "stderr": str(e)
        })
    
    return result
