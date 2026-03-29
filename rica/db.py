"""Database management for Rica using SQLite with WAL mode."""

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

from .config import DB_PATH


class Database:
    """SQLite database manager for Rica sessions and plans."""
    
    def __init__(self) -> None:
        """Initialize database connection and create tables."""
        self.db_path = DB_PATH
        self._init_db()
    
    def _init_db(self) -> None:
        """Initialize database with required tables and WAL mode."""
        with sqlite3.connect(self.db_path) as conn:
            # Enable WAL mode for better concurrency
            conn.execute("PRAGMA journal_mode=WAL")
            
            # Create sessions table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    goal TEXT NOT NULL,
                    language TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active',
                    created_at TEXT NOT NULL
                )
            """)
            
            # Create plans table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS plans (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    plan_json TEXT NOT NULL,
                    approved INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (session_id) REFERENCES sessions (id)
                )
            """)
            
            # Create builds table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS builds (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    workspace TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'in_progress',
                    started_at TEXT NOT NULL,
                    completed_at TEXT,
                    FOREIGN KEY (session_id) REFERENCES sessions (id)
                )
            """)
            
            conn.commit()
    
    def create_session(self, session_id: str, goal: str, language: str) -> None:
        """Create a new planning session."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO sessions (id, goal, language, status, created_at)
                VALUES (?, ?, ?, 'active', ?)
            """, (session_id, goal, language, datetime.utcnow().isoformat()))
            conn.commit()
    
    def save_plan(self, plan_id: str, session_id: str, plan_json: str) -> None:
        """Save a plan to the database."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO plans (id, session_id, plan_json, approved, created_at)
                VALUES (?, ?, ?, 0, ?)
            """, (plan_id, session_id, plan_json, datetime.utcnow().isoformat()))
            conn.commit()
    
    def get_plan(self, session_id: str) -> Optional[str]:
        """Get plan JSON for a session."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT plan_json FROM plans 
                WHERE session_id = ? 
                ORDER BY created_at DESC 
                LIMIT 1
            """, (session_id,))
            result = cursor.fetchone()
            return result[0] if result else None
    
    def update_plan_approval(self, session_id: str, approved: bool) -> None:
        """Update plan approval status."""
        with sqlite3.connect(self.db_path) as conn:
            # First get the latest plan ID for this session
            cursor = conn.execute("""
                SELECT id FROM plans 
                WHERE session_id = ? 
                ORDER BY created_at DESC 
                LIMIT 1
            """, (session_id,))
            result = cursor.fetchone()
            
            if result:
                plan_id = result[0]
                conn.execute("""
                    UPDATE plans SET approved = ? 
                    WHERE id = ?
                """, (1 if approved else 0, plan_id))
                conn.commit()
    
    def list_sessions(self) -> list[dict]:
        """List all sessions with their latest plan status."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT 
                    s.id,
                    s.goal,
                    s.language,
                    s.status,
                    s.created_at,
                    (SELECT approved FROM plans 
                     WHERE session_id = s.id 
                     ORDER BY created_at DESC 
                     LIMIT 1) as approved
                FROM sessions s
                ORDER BY s.created_at DESC
            """)
            
            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]
    
    def insert_build(self, build_id: str, session_id: str, workspace: str, started_at: str) -> None:
        """Insert a new build record."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO builds (id, session_id, workspace, status, started_at)
                VALUES (?, ?, ?, 'in_progress', ?)
            """, (build_id, session_id, workspace, started_at))
            conn.commit()
    
    def complete_build(self, build_id: str, completed_at: str) -> None:
        """Mark a build as completed."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                UPDATE builds SET status = 'completed', completed_at = ?
                WHERE id = ?
            """, (completed_at, build_id))
            conn.commit()
    
    def get_build_by_session(self, session_id: str) -> Optional[dict]:
        """Get the latest build for a session."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT id, session_id, workspace, status, started_at, completed_at
                FROM builds
                WHERE session_id = ?
                ORDER BY started_at DESC
                LIMIT 1
            """, (session_id,))
            result = cursor.fetchone()
            if result:
                columns = [desc[0] for desc in cursor.description]
                return dict(zip(columns, result))
            return None
    
    def get_all_builds(self) -> list[dict]:
        """Get all builds."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT id, session_id, workspace, status, started_at, completed_at
                FROM builds
                ORDER BY started_at DESC
            """)
            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]
    
    def get_plan_for_session(self, session_id: str) -> Optional[dict]:
        """Get the approved plan for a session."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT id, plan_json, approved
                FROM plans
                WHERE session_id = ? AND approved = 1
                ORDER BY created_at DESC
                LIMIT 1
            """, (session_id,))
            result = cursor.fetchone()
            if result:
                columns = [desc[0] for desc in cursor.description]
                return dict(zip(columns, result))
            return None


# Global database instance
db = Database()
