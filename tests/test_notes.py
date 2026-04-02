"""Tests for Rica notes functionality."""

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
        # Clean notes table
        conn.execute("DELETE FROM notes")
        conn.commit()
    yield

# Import after fixtures are defined
from rica.db import add_note, get_notes, update_note, delete_note, get_note


class TestAddNote:
    """Test add_note function."""

    def test_add_note_returns_id(self):
        """Test add_note returns an integer > 0."""
        note_id = add_note("sess1", "hello world")
        assert isinstance(note_id, int)
        assert note_id > 0


class TestGetNotes:
    """Test get_notes function."""

    def test_get_notes_empty(self):
        """Test get_notes returns [] for session with no notes."""
        notes = get_notes("sess1")
        assert notes == []

    def test_get_notes_returns_all(self):
        """Test get_notes returns all notes for a session."""
        # Add 3 notes
        add_note("sess1", "first note")
        add_note("sess1", "second note")
        add_note("sess1", "third note")
        
        notes = get_notes("sess1")
        assert len(notes) == 3
        assert notes[0]["content"] == "first note"
        assert notes[1]["content"] == "second note"
        assert notes[2]["content"] == "third note"

    def test_get_notes_ordered_by_created_at(self):
        """Test get_notes returns notes ordered by created_at ASC."""
        # Add 2 notes
        note1_id = add_note("sess1", "first note")
        note2_id = add_note("sess1", "second note")
        
        notes = get_notes("sess1")
        assert len(notes) == 2
        assert notes[0]["id"] == note1_id
        assert notes[1]["id"] == note2_id
        assert notes[0]["content"] == "first note"
        assert notes[1]["content"] == "second note"


class TestGetNote:
    """Test get_note function."""

    def test_get_note_by_id(self):
        """Test get_note returns correct note by id."""
        note_id = add_note("sess1", "hello world")
        note = get_note(note_id)
        
        assert note is not None
        assert note["id"] == note_id
        assert note["session_id"] == "sess1"
        assert note["content"] == "hello world"

    def test_get_note_missing(self):
        """Test get_note returns None for non-existent note."""
        note = get_note(99999)
        assert note is None


class TestUpdateNote:
    """Test update_note function."""

    def test_update_note(self):
        """Test update_note updates note content successfully."""
        note_id = add_note("sess1", "original content")
        
        success = update_note(note_id, "updated content")
        assert success is True
        
        note = get_note(note_id)
        assert note["content"] == "updated content"

    def test_update_note_missing(self):
        """Test update_note returns False for non-existent note."""
        success = update_note(99999, "new content")
        assert success is False


class TestDeleteNote:
    """Test delete_note function."""

    def test_delete_note(self):
        """Test delete_note deletes note successfully."""
        note_id = add_note("sess1", "to be deleted")
        
        # Verify note exists
        assert get_note(note_id) is not None
        
        success = delete_note(note_id)
        assert success is True
        
        # Verify note is gone
        assert get_note(note_id) is None

    def test_delete_note_missing(self):
        """Test delete_note returns False for non-existent note."""
        success = delete_note(99999)
        assert success is False
