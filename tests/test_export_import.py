"""Tests for export/import functionality."""

import json
import pytest
import tempfile
import os
import zipfile
from pathlib import Path
from unittest.mock import patch

# Point RICA_HOME at a temp dir before importing modules
@pytest.fixture(autouse=True)
def temp_rica_home(tmp_path):
    with patch.dict(os.environ, {"RICA_HOME": str(tmp_path)}):
        # Re-init modules with temp path
        import importlib
        import rica.config as config
        import rica.db as db
        import rica.exporter as exporter
        import rica.importer as importer
        importlib.reload(config)
        importlib.reload(db)
        importlib.reload(exporter)
        importlib.reload(importer)
        # Initialize the global db instance
        db.db._init_db()
        yield db, exporter, importer

@pytest.fixture(autouse=True)
def clean_database():
    """Clean database before each test."""
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

@pytest.fixture
def sample_session(temp_rica_home):
    """Create a sample session for testing."""
    db, _, _ = temp_rica_home
    session_id = db.save_session("Build a todo app", "python")
    return session_id

def test_export_creates_valid_zip(temp_rica_home, sample_session):
    """Test that export creates a valid ZIP file."""
    db, exporter, _ = temp_rica_home
    out_path = Path(tempfile.mktemp(suffix=".rica"))
    
    summary = exporter.export_session(sample_session, out_path)
    
    # Assert file exists
    assert out_path.exists()
    
    # Assert it's a valid ZIP
    assert zipfile.is_zipfile(out_path)
    
    # Assert meta.json is present
    with zipfile.ZipFile(out_path, "r") as zf:
        assert "meta.json" in zf.namelist()
    
    # Clean up
    out_path.unlink()

def test_export_import_roundtrip(temp_rica_home, sample_session):
    """Test that export followed by import preserves data."""
    db, exporter, importer = temp_rica_home
    original_goal = "Build a todo app"
    
    # Export
    export_path = Path(tempfile.mktemp(suffix=".rica"))
    summary = exporter.export_session(sample_session, export_path)
    
    # Import
    import_summary = importer.import_session(export_path)
    
    # Assert goal matches
    assert import_summary["goal"] == original_goal
    
    # Assert new session ID is different
    assert import_summary["new_session_id"] != sample_session
    
    # Assert session exists in DB
    conn = db.get_connection()
    cursor = conn.execute(
        "SELECT goal FROM sessions WHERE id = ?",
        (import_summary["new_session_id"],)
    )
    result = cursor.fetchone()
    assert result is not None
    assert result[0] == original_goal
    
    conn.close()
    
    # Clean up
    export_path.unlink()

def test_import_with_extra_tag(temp_rica_home, sample_session):
    """Test that extra tag is applied during import."""
    db, exporter, importer = temp_rica_home
    
    # Export
    export_path = Path(tempfile.mktemp(suffix=".rica"))
    exporter.export_session(sample_session, export_path)
    
    # Import with extra tag
    import_summary = importer.import_session(export_path, extra_tag="imported")
    
    # Assert tag is applied
    assert "imported" in import_summary["tags_applied"]
    
    # Verify tag in DB
    tags = db.get_tags(import_summary["new_session_id"])
    assert "imported" in tags
    
    # Clean up
    export_path.unlink()

def test_export_nonexistent_session(temp_rica_home):
    """Test that exporting nonexistent session raises ValueError."""
    _, exporter, _ = temp_rica_home
    out_path = Path(tempfile.mktemp(suffix=".rica"))
    
    with pytest.raises(ValueError, match="Session not found"):
        exporter.export_session("nonexistent-id", out_path)
    
    # Clean up if file was created
    if out_path.exists():
        out_path.unlink()

def test_import_corrupted_archive(temp_rica_home):
    """Test that importing corrupted archive raises ValueError."""
    _, _, importer = temp_rica_home
    
    # Create a file that is not a valid ZIP
    bad_path = Path(tempfile.mktemp(suffix=".rica"))
    bad_path.write_text("This is not a ZIP file")
    
    with pytest.raises(ValueError, match="not a valid ZIP"):
        importer.import_session(bad_path)
    
    # Clean up
    bad_path.unlink()

def test_import_missing_meta_json(temp_rica_home):
    """Test that importing archive without meta.json raises ValueError."""
    _, _, importer = temp_rica_home
    
    # Create a ZIP without meta.json
    bad_path = Path(tempfile.mktemp(suffix=".rica"))
    with zipfile.ZipFile(bad_path, "w") as zf:
        zf.writestr("somefile.txt", "content")
    
    with pytest.raises(ValueError, match="meta.json missing"):
        importer.import_session(bad_path)
    
    # Clean up
    bad_path.unlink()

def test_export_with_plan_and_workspace(temp_rica_home):
    """Test export with plan and workspace files."""
    db, exporter, _ = temp_rica_home
    session_id = db.save_session("Test project", "python")
    
    # Create a plan file
    plans_dir = Path.home() / ".rica" / "plans"
    plans_dir.mkdir(parents=True, exist_ok=True)
    plan_path = plans_dir / f"{session_id}.json"
    plan_data = {
        "goal": "Test project",
        "language": "python",
        "session_id": session_id
    }
    plan_path.write_text(json.dumps(plan_data, indent=2))
    
    # Create workspace files
    ws_dir = Path.home() / ".rica" / "workspaces" / session_id
    ws_dir.mkdir(parents=True, exist_ok=True)
    (ws_dir / "main.py").write_text("print('hello')")
    (ws_dir / "utils.py").write_text("def helper(): pass")
    
    # Export
    out_path = Path(tempfile.mktemp(suffix=".rica"))
    summary = exporter.export_session(session_id, out_path)
    
    # Verify summary
    assert summary["plan_included"] is True
    assert summary["workspace_file_count"] == 2
    
    # Verify ZIP contents
    with zipfile.ZipFile(out_path, "r") as zf:
        namelist = zf.namelist()
        assert "plan.json" in namelist
        assert "workspace/main.py" in namelist
        assert "workspace/utils.py" in namelist
        
        # Verify meta.json
        meta = json.loads(zf.read("meta.json").decode("utf-8"))
        assert meta["session"]["session_id"] == session_id
        assert meta["session"]["goal"] == "Test project"
    
    # Clean up
    out_path.unlink()

def test_import_restores_plan_and_workspace(temp_rica_home, sample_session):
    """Test that import restores plan and workspace files."""
    db, exporter, importer = temp_rica_home
    
    # Create plan and workspace for original session
    plans_dir = Path.home() / ".rica" / "plans"
    plans_dir.mkdir(parents=True, exist_ok=True)
    plan_path = plans_dir / f"{sample_session}.json"
    plan_data = {"goal": "Test project", "language": "python"}
    plan_path.write_text(json.dumps(plan_data, indent=2))
    
    ws_dir = Path.home() / ".rica" / "workspaces" / sample_session
    ws_dir.mkdir(parents=True, exist_ok=True)
    (ws_dir / "main.py").write_text("print('hello world')")
    
    # Export
    export_path = Path(tempfile.mktemp(suffix=".rica"))
    exporter.export_session(sample_session, export_path)
    
    # Import
    import_summary = importer.import_session(export_path)
    
    # Verify plan restored
    assert import_summary["plan_restored"] is True
    new_plan_path = plans_dir / f"{import_summary['new_session_id']}.json"
    assert new_plan_path.exists()
    
    restored_plan = json.loads(new_plan_path.read_text())
    assert restored_plan["goal"] == "Test project"
    
    # Verify workspace restored
    assert import_summary["workspace_files_restored"] == 1
    new_ws_dir = Path.home() / ".rica" / "workspaces" / import_summary["new_session_id"]
    assert (new_ws_dir / "main.py").exists()
    assert (new_ws_dir / "main.py").read_text() == "print('hello world')"
    
    # Clean up
    export_path.unlink()

def test_export_with_tags(temp_rica_home):
    """Test export includes tags."""
    db, exporter, _ = temp_rica_home
    session_id = db.save_session("Tagged project", "python")
    
    # Add tags
    db.add_tag(session_id, "backend")
    db.add_tag(session_id, "api")
    
    # Export
    out_path = Path(tempfile.mktemp(suffix=".rica"))
    summary = exporter.export_session(session_id, out_path)
    
    # Verify tags in meta.json
    with zipfile.ZipFile(out_path, "r") as zf:
        meta = json.loads(zf.read("meta.json").decode("utf-8"))
        assert set(meta["tags"]) == {"api", "backend"}
    
    # Clean up
    out_path.unlink()

def test_import_with_existing_tags(temp_rica_home):
    """Test import preserves original tags."""
    db, exporter, importer = temp_rica_home
    session_id = db.save_session("Tagged project", "python")
    
    # Add tags to original
    db.add_tag(session_id, "backend")
    db.add_tag(session_id, "api")
    
    # Export
    export_path = Path(tempfile.mktemp(suffix=".rica"))
    exporter.export_session(session_id, export_path)
    
    # Import
    import_summary = importer.import_session(export_path)
    
    # Verify tags restored
    assert set(import_summary["tags_applied"]) == {"api", "backend"}
    
    # Verify in DB
    new_tags = db.get_tags(import_summary["new_session_id"])
    assert set(new_tags) == {"api", "backend"}
    
    # Clean up
    export_path.unlink()
