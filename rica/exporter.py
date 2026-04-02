"""Session export functionality for Rica .rica archives."""

import json
import sqlite3
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .console import get_console
from .db import get_connection
from .hooks import fire_hook


def _get_table_rows(session_id: str, table_name: str) -> list[dict]:
    """Get all rows from a table for a given session_id."""
    conn = get_connection()
    try:
        cursor = conn.execute(f"SELECT * FROM {table_name} WHERE session_id = ?", (session_id,))
        rows = cursor.fetchall()
        
        if not rows:
            return []
        
        # Get column names from cursor description
        columns = [desc[0] for desc in cursor.description]
        return [dict(zip(columns, row)) for row in rows]
    except sqlite3.OperationalError:
        # Table doesn't exist or no session_id column
        return []
    finally:
        conn.close()


def export_session(session_id: str, out_path: Path) -> dict:
    """
    Bundle session into a .rica ZIP archive at out_path.
    Returns a summary dict with keys:
      plan_included: bool
      workspace_file_count: int
      archive_size_bytes: int
      tables_exported: list[str]
    Raises ValueError if session not found in DB.
    """
    console = get_console()
    
    # Fire pre_export hook
    pre_hook_result = fire_hook("pre_export", session_id=session_id, extra={"out_path": str(out_path)})
    if pre_hook_result.get("status") in ["error", "timeout"]:
        console.print(f"[dim]Hook warning (pre_export): {pre_hook_result.get('stderr') or pre_hook_result.get('status')}[/dim]")
    
    # 1. Look up session from DB
    conn = get_connection()
    try:
        cursor = conn.execute(
            "SELECT id, goal, language, created_at FROM sessions WHERE id = ?",
            (session_id,)
        )
        session_row = cursor.fetchone()
        
        if not session_row:
            raise ValueError(f"Session not found: {session_id}")
        
        columns = [desc[0] for desc in cursor.description]
        session = dict(zip(columns, session_row))
    finally:
        conn.close()
    
    # 2. Collect data from DB tables
    tables_to_export = [
        "executions", "debug_history", "reviews", "refactors",
        "test_generations", "explanations", "tags"
    ]
    
    table_data = {}
    tables_exported = []
    
    for table in tables_to_export:
        rows = _get_table_rows(session_id, table)
        if rows:
            table_data[table] = rows
            tables_exported.append(table)
    
    # 3. Build meta.json
    # Get tags for the session
    conn = get_connection()
    try:
        cursor = conn.execute("SELECT tag FROM tags WHERE session_id = ? ORDER BY tag", (session_id,))
        tags = [row[0] for row in cursor.fetchall()]
    finally:
        conn.close()
    
    meta = {
        "rica_version": "0.15.0",
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "session": {
            "session_id": session["id"],
            "goal": session["goal"],
            "language": session["language"],
            "created_at": session["created_at"],
            "updated_at": session["created_at"]
        },
        "tags": tags
    }
    
    # 4. Create ZIP archive
    workspace_file_count = 0
    plan_included = False
    
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        # 5. Write metadata and table data
        zf.writestr("meta.json", json.dumps(meta, indent=2))
        
        for table_name, rows in table_data.items():
            zf.writestr(f"{table_name}.json", json.dumps(rows, indent=2))
        
        # 6. Add plan JSON if exists
        plan_path = Path.home() / ".rica" / "plans" / f"{session_id}.json"
        if plan_path.exists():
            zf.write(plan_path, arcname="plan.json")
            plan_included = True
        
        # 7. Add workspace files
        ws_path = Path.home() / ".rica" / "workspaces" / session_id
        if ws_path.exists():
            for file_path in ws_path.rglob("*"):
                if file_path.is_file():
                    # Convert path separators to forward slashes for ZIP compatibility
                    arcname = "workspace/" + str(file_path.relative_to(ws_path)).replace("\\", "/")
                    zf.write(file_path, arcname=arcname)
                    workspace_file_count += 1
    
    # 8. Return summary
    archive_size_bytes = out_path.stat().st_size
    
    # Fire post_export hook
    post_hook_result = fire_hook("post_export", session_id=session_id, extra={"out_path": str(out_path), "size_bytes": archive_size_bytes})
    if post_hook_result.get("status") in ["error", "timeout"]:
        console.print(f"[dim]Hook warning (post_export): {post_hook_result.get('stderr') or post_hook_result.get('status')}[/dim]")
    
    return {
        "plan_included": plan_included,
        "workspace_file_count": workspace_file_count,
        "archive_size_bytes": archive_size_bytes,
        "tables_exported": tables_exported
    }
