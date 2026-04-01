"""Database management for Rica using SQLite with WAL mode."""

import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from .config import DB_PATH
from .models import ExecutionResult


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
                    FOREIGN KEY (session_id) REFERENCES sessions(id)
                )
            """)
            
            # Create executions table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS executions (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    command TEXT NOT NULL,
                    exit_code INTEGER,
                    stdout TEXT,
                    stderr TEXT,
                    timed_out INTEGER DEFAULT 0,
                    executed_at TEXT NOT NULL,
                    FOREIGN KEY (session_id) REFERENCES sessions(id)
                )
            """)
            
            # Create debug_sessions table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS debug_sessions (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    iterations INTEGER DEFAULT 0,
                    final_status TEXT NOT NULL DEFAULT 'in_progress',
                    started_at TEXT NOT NULL,
                    completed_at TEXT,
                    FOREIGN KEY (session_id) REFERENCES sessions(id)
                )
            """)
            
            # Create debug_iterations table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS debug_iterations (
                    id TEXT PRIMARY KEY,
                    debug_session_id TEXT NOT NULL,
                    iteration INTEGER NOT NULL,
                    error_class TEXT,
                    implicated_files TEXT,
                    check_passed INTEGER,
                    run_exit_code INTEGER,
                    fixed_at TEXT,
                    FOREIGN KEY (debug_session_id) REFERENCES debug_sessions(id)
                )
            """)
            
            # Create reviews table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS reviews (
                    id TEXT PRIMARY KEY,
                    path TEXT NOT NULL,
                    language TEXT NOT NULL,
                    files_reviewed INTEGER NOT NULL,
                    issue_count INTEGER NOT NULL,
                    error_count INTEGER NOT NULL,
                    report_json TEXT NOT NULL,
                    reviewed_at TEXT NOT NULL
                )
            """)
            
            # Create explanations table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS explanations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    path TEXT NOT NULL,
                    language TEXT NOT NULL,
                    files_analyzed INTEGER NOT NULL,
                    explanation TEXT NOT NULL,
                    explained_at TEXT NOT NULL
                )
            """)
            
            # Create refactors table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS refactors (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    path TEXT NOT NULL,
                    language TEXT NOT NULL,
                    goal TEXT NOT NULL,
                    files_analyzed INTEGER NOT NULL,
                    files_changed INTEGER NOT NULL,
                    report_json TEXT NOT NULL,
                    refactored_at TEXT NOT NULL
                )
            """)
            
            # Create test_generations table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS test_generations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    language TEXT NOT NULL,
                    goal TEXT NOT NULL,
                    files_analyzed INTEGER NOT NULL,
                    tests_generated INTEGER NOT NULL,
                    report_json TEXT NOT NULL,
                    generated_at TEXT NOT NULL
                )
            """)
            
            # Create file_snapshots table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS file_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    path TEXT NOT NULL,
                    sha256 TEXT,
                    mtime REAL NOT NULL,
                    snapshotted_at TEXT NOT NULL
                )
            """)
            
            # Create rebuild_logs table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS rebuild_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    files_checked INTEGER,
                    files_changed INTEGER,
                    files_cascaded INTEGER,
                    files_rewritten INTEGER,
                    files_skipped INTEGER,
                    rebuilt_at TEXT NOT NULL
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
    
    def save_execution(self, result: ExecutionResult, session_id: str) -> str:
        """Persist an ExecutionResult to the executions table. Returns the new row id."""
        execution_id = str(uuid.uuid4())
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO executions (
                    id, session_id, command, exit_code, stdout, stderr, 
                    timed_out, executed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                execution_id,
                session_id,
                " ".join(result.command),
                result.exit_code,
                result.stdout,
                result.stderr,
                1 if result.timed_out else 0,
                result.executed_at
            ))
            conn.commit()
        return execution_id

    def insert_debug_session(self, debug_session_id: str, session_id: str, started_at: str) -> None:
        """Insert a new debug session record."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO debug_sessions (id, session_id, started_at)
                VALUES (?, ?, ?)
            """, (debug_session_id, session_id, started_at))
            conn.commit()

    def insert_debug_iteration(
        self,
        id: str,
        debug_session_id: str,
        iteration: int,
        error_class: str,
        implicated_files: str,  # JSON-encoded list
        check_passed: int,
        run_exit_code: int | None,
        fixed_at: str,
    ) -> None:
        """Insert a new debug iteration record."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO debug_iterations (
                    id, debug_session_id, iteration, error_class, implicated_files, 
                    check_passed, run_exit_code, fixed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (id, debug_session_id, iteration, error_class, implicated_files, check_passed, run_exit_code, fixed_at))
            conn.commit()

    def complete_debug_session(self, debug_session_id: str, final_status: str, completed_at: str) -> None:
        """Mark a debug session as completed."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                UPDATE debug_sessions 
                SET final_status = ?, completed_at = ?, 
                    iterations = (SELECT COUNT(*) FROM debug_iterations WHERE debug_session_id = ?)
                WHERE id = ?
            """, (final_status, completed_at, debug_session_id, debug_session_id))
            conn.commit()

    def get_debug_sessions_for_session(self, session_id: str) -> list[dict]:
        """Get all debug sessions for a given session."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT id, session_id, iterations, final_status, started_at, completed_at
                FROM debug_sessions
                WHERE session_id = ?
                ORDER BY started_at DESC
            """, (session_id,))
            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def get_debug_iterations_for_session(self, debug_session_id: str) -> list[dict]:
        """Get all debug iterations for a debug session."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT id, debug_session_id, iteration, error_class, implicated_files, 
                       check_passed, run_exit_code, fixed_at
                FROM debug_iterations
                WHERE debug_session_id = ?
                ORDER BY iteration ASC
            """, (debug_session_id,))
            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]


def get_connection():
    """Get a database connection."""
    return sqlite3.connect(DB_PATH)


def save_review(
    id: str,
    path: str,
    language: str,
    files_reviewed: int,
    issue_count: int,
    error_count: int,
    report_json: str,
    reviewed_at: str,
) -> None:
    conn = get_connection()
    with conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO reviews
            (id, path, language, files_reviewed, issue_count, error_count, report_json, reviewed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (id, path, language, files_reviewed, issue_count, error_count, report_json, reviewed_at),
        )


def get_reviews_for_path(path: str | None) -> list[dict]:
    conn = get_connection()
    if path:
        rows = conn.execute(
            "SELECT * FROM reviews WHERE path = ? ORDER BY reviewed_at DESC",
            (path,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM reviews ORDER BY reviewed_at DESC"
        ).fetchall()
    
    # Get column names from cursor description
    columns = [description[0] for description in conn.execute("SELECT * FROM reviews LIMIT 1").description] if rows else []
    return [dict(zip(columns, row)) for row in rows]


# Global database instance
db = Database()


def save_explanation(report: "ExplainReport") -> int:
    """Persist an ExplainReport and return its row id."""
    conn = get_connection()
    with conn:
        cursor = conn.execute(
            """
            INSERT INTO explanations (path, language, files_analyzed, explanation, explained_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (report.path, report.language, report.files_analyzed, report.explanation, report.explained_at),
        )
        return cursor.lastrowid


def list_explanations(path_filter: str | None = None) -> list[dict]:
    """Return all explanation rows, optionally filtered by path prefix."""
    conn = get_connection()
    if path_filter:
        rows = conn.execute(
            "SELECT * FROM explanations WHERE path LIKE ? ORDER BY explained_at DESC",
            (path_filter + "%",),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM explanations ORDER BY explained_at DESC"
        ).fetchall()
    
    # Get column names from cursor description
    columns = [description[0] for description in conn.execute("SELECT * FROM explanations LIMIT 1").description] if rows else []
    return [dict(zip(columns, row)) for row in rows]


def save_refactor(report: "RefactorReport") -> None:
    """Persist a RefactorReport to the refactors table."""
    conn = get_connection()
    with conn:
        conn.execute(
            """
            INSERT INTO refactors (path, language, goal, files_analyzed, files_changed, report_json, refactored_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                report.path,
                report.language,
                report.goal,
                report.files_analyzed,
                len(report.changes),
                report.model_dump_json(),
                report.refactored_at,
            ),
        )


def list_refactors(path_filter: str | None = None) -> list[dict]:
    """Return all refactor rows, optionally filtered by path prefix."""
    conn = get_connection()
    if path_filter:
        rows = conn.execute(
            "SELECT * FROM refactors WHERE path = ? ORDER BY refactored_at DESC",
            (path_filter,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM refactors ORDER BY refactored_at DESC"
        ).fetchall()
    
    # Get column names from cursor description
    columns = [description[0] for description in conn.execute("SELECT * FROM refactors LIMIT 1").description] if rows else []
    return [dict(zip(columns, row)) for row in rows]


def save_test_generation(report: "TestGenReport") -> None:
    """Persist a TestGenReport to the test_generations table."""
    conn = get_connection()
    with conn:
        conn.execute(
            """
            INSERT INTO test_generations (session_id, language, goal, files_analyzed, tests_generated, report_json, generated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                report.session_id,
                report.language,
                report.goal,
                report.files_analyzed,
                len(report.tests_generated),
                report.model_dump_json(),
                report.generated_at,
            ),
        )


def list_test_generations(session_id: str | None = None) -> list[dict]:
    """Return all test generation rows, optionally filtered by session_id."""
    conn = get_connection()
    if session_id:
        rows = conn.execute(
            "SELECT * FROM test_generations WHERE session_id = ? ORDER BY generated_at DESC",
            (session_id,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM test_generations ORDER BY generated_at DESC"
        ).fetchall()
    
    # Get column names from cursor description
    columns = [description[0] for description in conn.execute("SELECT * FROM test_generations LIMIT 1").description] if rows else []
    return [dict(zip(columns, row)) for row in rows]


def get_sessions_by_language(language: str) -> list[dict]:
    """
    Return all sessions whose language column contains the given language
    string (case-insensitive substring match).
    """
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM sessions WHERE language LIKE ? ORDER BY created_at DESC",
        (f"%{language}%",),
    ).fetchall()
    
    # Get column names from cursor description
    columns = [description[0] for description in conn.execute("SELECT * FROM sessions LIMIT 1").description] if rows else []
    return [dict(zip(columns, row)) for row in rows]


def save_snapshot(session_id: str, snapshots: list[dict]) -> None:
    """Save file snapshots for a session, replacing any existing snapshots."""
    conn = get_connection()
    with conn:
        # Delete existing snapshots for this session
        conn.execute("DELETE FROM file_snapshots WHERE session_id = ?", (session_id,))
        
        # Insert new snapshots
        for snapshot in snapshots:
            conn.execute("""
                INSERT INTO file_snapshots (session_id, path, sha256, mtime, snapshotted_at)
                VALUES (?, ?, ?, ?, ?)
            """, (
                session_id,
                snapshot["path"],
                snapshot.get("sha256"),
                snapshot["mtime"],
                datetime.utcnow().isoformat() + "Z"
            ))


def get_snapshot(session_id: str) -> list[dict]:
    """Get all file snapshots for a session."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT path, sha256, mtime FROM file_snapshots WHERE session_id = ? ORDER BY path",
        (session_id,)
    ).fetchall()
    
    columns = ["path", "sha256", "mtime"]
    return [dict(zip(columns, row)) for row in rows]


def save_rebuild_log(session_id: str, checked: int, changed: int,
                   cascaded: int, rewritten: int, skipped: int) -> None:
    """Save a rebuild log entry."""
    conn = get_connection()
    with conn:
        conn.execute("""
            INSERT INTO rebuild_logs (session_id, files_checked, files_changed, 
                                    files_cascaded, files_rewritten, files_skipped, rebuilt_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            session_id, checked, changed, cascaded, rewritten, skipped,
            datetime.utcnow().isoformat() + "Z"
        ))


def get_rebuild_logs(session_id: str) -> list[dict]:
    """Get all rebuild logs for a session in descending order."""
    conn = get_connection()
    rows = conn.execute(
        """SELECT files_checked, files_changed, files_cascaded, files_rewritten, 
                  files_skipped, rebuilt_at 
           FROM rebuild_logs 
           WHERE session_id = ? 
           ORDER BY rebuilt_at DESC""",
        (session_id,)
    ).fetchall()
    
    columns = ["files_checked", "files_changed", "files_cascaded", 
              "files_rewritten", "files_skipped", "rebuilt_at"]
    return [dict(zip(columns, row)) for row in rows]
