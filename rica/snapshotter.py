"""File snapshot functionality for Rica rebuild system."""

import hashlib
from pathlib import Path
from datetime import datetime
from typing import Dict, List

from . import db
from .models import FileSnapshot


def take_snapshot(session_id: str, workspace: Path) -> List[FileSnapshot]:
    """Take a snapshot of all files in the workspace and save to database."""
    snapshots = []
    runtime_dirs = {".venv", "venv", "env", "node_modules", "__pycache__", 
                   ".git", "dist", "build", "target", ".tox"}
    
    for file_path in workspace.rglob("*"):
        if file_path.is_file():
            # Skip files in runtime directories
            if any(part in runtime_dirs for part in file_path.parts):
                continue
                
            try:
                # Calculate SHA256
                sha256 = None
                try:
                    with open(file_path, "rb") as f:
                        content = f.read()
                        sha256 = hashlib.sha256(content).hexdigest()
                except (IOError, OSError):
                    sha256 = None
                
                # Get modification time
                mtime = file_path.stat().st_mtime
                
                # Create snapshot with relative path
                rel_path = file_path.relative_to(workspace)
                snapshot = FileSnapshot(
                    path=str(rel_path),
                    sha256=sha256,
                    mtime=mtime,
                    snapshotted_at=datetime.utcnow().isoformat() + "Z"
                )
                snapshots.append(snapshot)
                
            except (OSError, IOError):
                # Skip files that can't be accessed
                continue
    
    # Save to database
    snapshot_dicts = [
        {"path": s.path, "sha256": s.sha256, "mtime": s.mtime}
        for s in snapshots
    ]
    db.save_snapshot(session_id, snapshot_dicts)
    
    return snapshots


def load_snapshot(session_id: str) -> Dict[str, FileSnapshot]:
    """Load a snapshot from the database and return as dict."""
    snapshot_data = db.get_snapshot(session_id)
    
    snapshots = {}
    for entry in snapshot_data:
        snapshot = FileSnapshot(
            path=entry["path"],
            sha256=entry.get("sha256"),
            mtime=entry["mtime"],
            snapshotted_at=""  # Not stored in DB, not needed for diff
        )
        snapshots[entry["path"]] = snapshot
    
    return snapshots


def diff_snapshot(old: Dict[str, FileSnapshot], current: List) -> List[str]:
    """Compare old snapshot with current files and return changed paths."""
    changed_paths = []
    
    # Convert current list to dict for easier lookup
    current_dict = {}
    for entry in current:
        if isinstance(entry, dict):
            current_dict[entry["path"]] = entry
        else:
            current_dict[entry.path] = entry
    
    for path, current_entry in current_dict.items():
        if path not in old:
            # New file
            changed_paths.append(path)
        else:
            old_snapshot = old[path]
            
            # Get current values
            if isinstance(current_entry, dict):
                current_sha256 = current_entry.get("sha256")
                current_mtime = current_entry.get("mtime")
            else:
                current_sha256 = current_entry.sha256
                current_mtime = current_entry.mtime
            
            # Check if changed
            if old_snapshot.sha256 and current_sha256:
                # Both have hashes, compare hashes
                if old_snapshot.sha256 != current_sha256:
                    changed_paths.append(path)
            else:
                # Fallback to mtime comparison
                if old_snapshot.mtime != current_mtime:
                    changed_paths.append(path)
    
    return changed_paths
