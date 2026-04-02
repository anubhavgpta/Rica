"""Unit tests for session tagging and search — no LLM calls."""
import pytest
import tempfile
import os
from pathlib import Path
from unittest.mock import patch
import sqlite3

# Point RICA_HOME at a temp dir before importing db
@pytest.fixture(autouse=True)
def temp_rica_home(tmp_path):
    with patch.dict(os.environ, {"RICA_HOME": str(tmp_path)}):
        # Re-init db with temp path
        import importlib
        import rica.config as config
        import rica.db as db
        importlib.reload(config)
        importlib.reload(db)
        # Initialize the global db instance
        db.db._init_db()
        yield db

@pytest.fixture(autouse=True)
def clean_database():
    """Clean database before each test."""
    # This fixture runs after temp_rica_home, so we have access to the db
    import rica.db as db_module
    conn = db_module.get_connection()
    with conn:
        # Clean all tables
        conn.execute("DELETE FROM tags")
        conn.execute("DELETE FROM sessions")
        conn.execute("DELETE FROM plans")
        conn.execute("DELETE FROM builds")
        conn.execute("DELETE FROM executions")
        conn.execute("DELETE FROM debug_sessions")
        conn.execute("DELETE FROM debug_iterations")
        conn.execute("DELETE FROM reviews")
        conn.execute("DELETE FROM explanations")
        conn.execute("DELETE FROM refactors")
        conn.execute("DELETE FROM test_generations")
        conn.execute("DELETE FROM file_snapshots")
        conn.execute("DELETE FROM rebuild_logs")

def test_add_and_get_tags(temp_rica_home):
    db = temp_rica_home
    # Need a real session row first
    session_id = db.save_session("test goal", "python")
    db.add_tag(session_id, "backend")
    db.add_tag(session_id, "api")
    tags = db.get_tags(session_id)
    assert tags == ["api", "backend"]  # alphabetical

def test_duplicate_tag_returns_false(temp_rica_home):
    db = temp_rica_home
    session_id = db.save_session("test goal", "python")
    assert db.add_tag(session_id, "backend") == True
    assert db.add_tag(session_id, "backend") == False

def test_remove_tag(temp_rica_home):
    db = temp_rica_home
    session_id = db.save_session("test goal", "python")
    db.add_tag(session_id, "backend")
    assert db.remove_tag(session_id, "backend") == True
    assert db.get_tags(session_id) == []

def test_remove_nonexistent_tag_returns_false(temp_rica_home):
    db = temp_rica_home
    session_id = db.save_session("test goal", "python")
    assert db.remove_tag(session_id, "nonexistent") == False

def test_get_sessions_by_tag(temp_rica_home):
    db = temp_rica_home
    s1 = db.save_session("build a todo app", "python")
    s2 = db.save_session("build a REST API", "typescript")
    db.add_tag(s1, "backend")
    db.add_tag(s2, "backend")
    results = db.get_sessions_by_tag("backend")
    ids = [r["id"] for r in results]
    assert s1 in ids and s2 in ids

def test_search_sessions(temp_rica_home):
    db = temp_rica_home
    db.save_session("build a todo app in Python", "python")
    db.save_session("build a REST API in Go", "go")
    results = db.search_sessions("todo")
    assert len(results) == 1
    assert "todo" in results[0]["goal"]

def test_search_case_insensitive(temp_rica_home):
    db = temp_rica_home
    db.save_session("Build a FastAPI backend", "python")
    assert len(db.search_sessions("fastapi")) == 1
    assert len(db.search_sessions("FASTAPI")) == 1

def test_get_all_tags(temp_rica_home):
    db = temp_rica_home
    s1 = db.save_session("goal 1", "python")
    s2 = db.save_session("goal 2", "python")
    db.add_tag(s1, "frontend")
    db.add_tag(s2, "backend")
    db.add_tag(s1, "backend")
    all_tags = db.get_all_tags()
    assert all_tags == ["backend", "frontend"]  # deduped, alphabetical
