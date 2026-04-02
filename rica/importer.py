"""Session import functionality for Rica .rica archives."""

import json
import sqlite3
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .console import get_console
from .db import get_connection, add_tag
from .hooks import fire_hook


def import_session(archive_path: Path, extra_tag: str | None = None) -> dict:
    """
    Restore a session from a .rica archive into a fresh session ID.
    Returns a summary dict with keys:
      new_session_id: str
      original_session_id: str
      goal: str
      plan_restored: bool
      workspace_files_restored: int
      tags_applied: list[str]
    Raises ValueError if archive not found or meta.json missing/corrupt.
    """
    console = get_console()
    
    # 1. Check if archive exists
    if not archive_path.exists():
        raise ValueError(f"Archive not found: {archive_path}")
    
    # 2. Open ZIP and check for meta.json
    try:
        with zipfile.ZipFile(archive_path, "r") as zf:
            namelist = zf.namelist()
            
            if "meta.json" not in namelist:
                raise ValueError("Invalid .rica archive: meta.json missing")
            
            # 3. Parse meta.json
            try:
                meta_bytes = zf.read("meta.json")
                meta = json.loads(meta_bytes.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                raise ValueError(f"Corrupt .rica archive: meta.json is not valid JSON: {e}")
            
            # 4. Extract fields
            session_data = meta["session"]
            original_session_id = session_data["session_id"]
            goal = session_data["goal"]
            language = session_data["language"]
            created_at = session_data["created_at"]
            tags = meta.get("tags", [])
            
            # 5. Generate new session ID
            new_session_id = str(uuid.uuid4())
            
            # 6. Insert session row into DB
            conn = get_connection()
            try:
                with conn:
                    conn.execute(
                        """INSERT INTO sessions (id, goal, language, status, created_at)
                           VALUES (?, ?, ?, 'active', ?)""",
                        (new_session_id, goal, language, created_at)
                    )
            finally:
                conn.close()
            
            # 7. Restore plan JSON if present
            plans_dir = Path.home() / ".rica" / "plans"
            plans_dir.mkdir(parents=True, exist_ok=True)
            plan_restored = False
            
            if "plan.json" in namelist:
                plan_bytes = zf.read("plan.json")
                plan_path = plans_dir / f"{new_session_id}.json"
                plan_path.write_bytes(plan_bytes)
                plan_restored = True
            
            # 8. Restore workspace files
            ws_root = Path.home() / ".rica" / "workspaces" / new_session_id
            workspace_files_restored = 0
            
            for name in namelist:
                if name.startswith("workspace/"):
                    relative = name[len("workspace/"):]
                    if not relative:  # skip the directory entry itself
                        continue
                    
                    dest = ws_root / Path(relative)
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(zf.read(name))
                    workspace_files_restored += 1
            
            # 9. Restore history tables
            tables_to_restore = [
                "executions", "debug_history", "reviews", "refactors",
                "test_generations", "explanations", "tags"
            ]
            
            conn = get_connection()
            try:
                with conn:
                    for table_name in tables_to_restore:
                        filename = f"{table_name}.json"
                        if filename not in namelist:
                            continue
                        
                        try:
                            table_bytes = zf.read(filename)
                            rows = json.loads(table_bytes.decode("utf-8"))
                            
                            for row in rows:
                                # Update session_id to new session
                                if table_name != "tags":
                                    row["session_id"] = new_session_id
                                
                                # Build INSERT dynamically
                                cols = ", ".join(row.keys())
                                placeholders = ", ".join(["?"] * len(row))
                                sql = f"INSERT OR IGNORE INTO {table_name} ({cols}) VALUES ({placeholders})"
                                
                                try:
                                    conn.execute(sql, list(row.values()))
                                except sqlite3.OperationalError as e:
                                    # Table might not exist or column mismatch
                                    console.print(f"[dim]Warning: Could not restore {table_name}: {e}[/dim]")
                                    continue
                        
                        except (json.JSONDecodeError, UnicodeDecodeError) as e:
                            console.print(f"[dim]Warning: Could not parse {filename}: {e}[/dim]")
                            continue
            finally:
                conn.close()
            
            # 10. Apply tags
            all_tags = list(tags)
            if extra_tag:
                all_tags.append(extra_tag)
            
            tags_applied = []
            for tag in all_tags:
                # Normalize: strip → lower → replace spaces with hyphens
                normalized_tag = tag.strip().lower().replace(" ", "-")
                try:
                    if add_tag(new_session_id, normalized_tag):
                        tags_applied.append(normalized_tag)
                except Exception as e:
                    console.print(f"[dim]Warning: Could not add tag '{normalized_tag}': {e}[/dim]")
            
            # Fire post_import hook
            post_hook_result = fire_hook("post_import", session_id=new_session_id, extra={"source_file": str(archive_path)})
            if post_hook_result.get("status") in ["error", "timeout"]:
                console.print(f"[dim]Hook warning (post_import): {post_hook_result.get('stderr') or post_hook_result.get('status')}[/dim]")
            
            return {
                "new_session_id": new_session_id,
                "original_session_id": original_session_id,
                "goal": goal,
                "plan_restored": plan_restored,
                "workspace_files_restored": workspace_files_restored,
                "tags_applied": tags_applied
            }
    
    except zipfile.BadZipFile:
        raise ValueError(f"Corrupt .rica archive: {archive_path} is not a valid ZIP file")
