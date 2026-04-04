"""Agent memory management for Rica L18 autonomous agent."""

import json
from datetime import datetime, timezone
from typing import Optional

from .db import get_connection


def save_turn(
    session_id: str,
    turn_index: int,
    role: str,
    content: str,
    subtasks: list | None,
    trace: list | None
) -> None:
    """Save a turn to agent memory."""
    conn = get_connection()
    with conn:
        conn.execute(
            """
            INSERT INTO agent_memory (session_id, turn_index, role, content, subtasks, trace, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                turn_index,
                role,
                content,
                json.dumps(subtasks) if subtasks else None,
                json.dumps(trace) if trace else None,
                datetime.now(timezone.utc).isoformat()
            )
        )


def load_history(session_id: str, last_n: int = 10) -> list[dict]:
    """Load agent memory history for a session."""
    conn = get_connection()
    cursor = conn.execute(
        """
        SELECT id, session_id, turn_index, role, content, subtasks, trace, created_at
        FROM agent_memory
        WHERE session_id = ?
        ORDER BY turn_index DESC
        LIMIT ?
        """,
        (session_id, last_n)
    )
    
    rows = cursor.fetchall()
    columns = [desc[0] for desc in cursor.description]
    history = []
    
    for row in rows:
        entry = dict(zip(columns, row))
        # Parse JSON fields
        if entry["subtasks"]:
            entry["subtasks"] = json.loads(entry["subtasks"])
        if entry["trace"]:
            entry["trace"] = json.loads(entry["trace"])
        history.append(entry)
    
    # Return in chronological order (oldest first)
    return list(reversed(history))


def get_turn_count(session_id: str) -> int:
    """Get the number of turns for a session."""
    conn = get_connection()
    cursor = conn.execute(
        "SELECT COUNT(*) FROM agent_memory WHERE session_id = ?",
        (session_id,)
    )
    return cursor.fetchone()[0]


def clear_history(session_id: str) -> int:
    """Clear all agent memory for a session. Returns number of deleted turns."""
    conn = get_connection()
    with conn:
        cursor = conn.execute(
            "DELETE FROM agent_memory WHERE session_id = ?",
            (session_id,)
        )
        return cursor.rowcount


def get_latest_turn(session_id: str) -> Optional[dict]:
    """Get the latest turn for a session."""
    conn = get_connection()
    cursor = conn.execute(
        """
        SELECT id, session_id, turn_index, role, content, subtasks, trace, created_at
        FROM agent_memory
        WHERE session_id = ?
        ORDER BY turn_index DESC
        LIMIT 1
        """,
        (session_id,)
    )
    
    row = cursor.fetchone()
    if not row:
        return None
    
    columns = [desc[0] for desc in cursor.description]
    entry = dict(zip(columns, row))
    
    # Parse JSON fields
    if entry["subtasks"]:
        entry["subtasks"] = json.loads(entry["subtasks"])
    if entry["trace"]:
        entry["trace"] = json.loads(entry["trace"])
    
    return entry
