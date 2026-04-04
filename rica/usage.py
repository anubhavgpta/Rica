"""
Read-side helpers for LLM usage data.
All write-side logic lives in rica/llm.py.
"""

from __future__ import annotations
from rica.db import get_connection


def get_usage_for_session(session_id: str) -> list[dict]:
    """
    Return all llm_usage rows for a given session_id, ordered by created_at asc.
    Each row is a plain dict with keys:
        id, session_id, layer, call_type,
        input_tokens, output_tokens, cached_tokens,
        model, created_at
    """
    conn = get_connection()
    cursor = conn.execute(
        """
        SELECT id, session_id, layer, call_type,
               input_tokens, output_tokens, cached_tokens,
               model, created_at
        FROM llm_usage
        WHERE session_id = ?
        ORDER BY created_at ASC
        """,
        (session_id,)
    )
    rows = cursor.fetchall()
    columns = [desc[0] for desc in cursor.description]
    return [dict(zip(columns, row)) for row in rows]


def get_aggregate_usage(session_id: str | None = None) -> dict:
    """
    Return aggregate token counts.
    If session_id is provided, aggregate is scoped to that session.
    If session_id is None, aggregate is across all sessions.

    Returns:
        {
            "total_input_tokens": int,
            "total_output_tokens": int,
            "total_cached_tokens": int,
            "total_calls": int,
            "by_layer": {
                "<layer>": {
                    "input_tokens": int,
                    "output_tokens": int,
                    "cached_tokens": int,
                    "calls": int
                },
                ...
            }
        }
    """
    conn = get_connection()
    
    # Get overall totals
    if session_id:
        cursor = conn.execute(
            """
            SELECT 
                SUM(input_tokens) as total_input,
                SUM(output_tokens) as total_output,
                SUM(cached_tokens) as total_cached,
                COUNT(*) as total_calls
            FROM llm_usage
            WHERE session_id = ?
            """,
            (session_id,)
        )
    else:
        cursor = conn.execute(
            """
            SELECT 
                SUM(input_tokens) as total_input,
                SUM(output_tokens) as total_output,
                SUM(cached_tokens) as total_cached,
                COUNT(*) as total_calls
            FROM llm_usage
            """
        )
    
    totals = cursor.fetchone()
    result = {
        "total_input_tokens": totals[0] or 0,
        "total_output_tokens": totals[1] or 0,
        "total_cached_tokens": totals[2] or 0,
        "total_calls": totals[3] or 0,
        "by_layer": {}
    }
    
    # Get breakdown by layer
    if session_id:
        cursor = conn.execute(
            """
            SELECT 
                layer,
                SUM(input_tokens) as input_tokens,
                SUM(output_tokens) as output_tokens,
                SUM(cached_tokens) as cached_tokens,
                COUNT(*) as calls
            FROM llm_usage
            WHERE session_id = ?
            GROUP BY layer
            ORDER BY layer
            """,
            (session_id,)
        )
    else:
        cursor = conn.execute(
            """
            SELECT 
                layer,
                SUM(input_tokens) as input_tokens,
                SUM(output_tokens) as output_tokens,
                SUM(cached_tokens) as cached_tokens,
                COUNT(*) as calls
            FROM llm_usage
            GROUP BY layer
            ORDER BY layer
            """
        )
    
    for row in cursor.fetchall():
        layer = row[0]
        result["by_layer"][layer] = {
            "input_tokens": row[1] or 0,
            "output_tokens": row[2] or 0,
            "cached_tokens": row[3] or 0,
            "calls": row[4] or 0
        }
    
    return result


def get_all_session_summaries() -> list[dict]:
    """
    Return one summary row per session_id, ordered by total tokens desc.
    Each dict has:
        session_id, total_input_tokens, total_output_tokens,
        total_cached_tokens, total_calls, first_call_at, last_call_at
    """
    conn = get_connection()
    cursor = conn.execute(
        """
        SELECT 
            session_id,
            SUM(input_tokens) as total_input_tokens,
            SUM(output_tokens) as total_output_tokens,
            SUM(cached_tokens) as total_cached_tokens,
            COUNT(*) as total_calls,
            MIN(created_at) as first_call_at,
            MAX(created_at) as last_call_at
        FROM llm_usage
        WHERE session_id IS NOT NULL
        GROUP BY session_id
        ORDER BY (SUM(input_tokens) + SUM(output_tokens) + SUM(cached_tokens)) DESC
        """
    )
    
    rows = cursor.fetchall()
    columns = [desc[0] for desc in cursor.description]
    return [dict(zip(columns, row)) for row in rows]
