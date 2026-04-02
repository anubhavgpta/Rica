"""Tests for Rica hook system."""

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from rica.hooks import build_payload, discover_hooks, fire_hook


class TestDiscoverHooks:
    """Test hook discovery functionality."""

    def test_discover_hooks_empty(self, tmp_path, monkeypatch):
        """Test discover_hooks returns {} when HOOKS_DIR doesn't exist."""
        # Monkeypatch HOOKS_DIR to tmp_path/hooks
        hooks_dir = tmp_path / "hooks"
        monkeypatch.setattr("rica.hooks.HOOKS_DIR", hooks_dir)
        
        # Directory doesn't exist
        assert not hooks_dir.exists()
        
        result = discover_hooks()
        assert result == {}

    def test_discover_hooks_finds_valid_event(self, tmp_path, monkeypatch):
        """Test discover_hooks finds valid event scripts."""
        # Monkeypatch HOOKS_DIR
        hooks_dir = tmp_path / "hooks"
        hooks_dir.mkdir()
        monkeypatch.setattr("rica.hooks.HOOKS_DIR", hooks_dir)
        
        # Create a valid hook script
        hook_script = hooks_dir / "post_plan.py"
        hook_script.write_text("# Valid hook script")
        
        result = discover_hooks()
        assert result == {"post_plan": hook_script}

    def test_discover_hooks_ignores_invalid_event(self, tmp_path, monkeypatch):
        """Test discover_hooks ignores invalid event scripts."""
        # Monkeypatch HOOKS_DIR
        hooks_dir = tmp_path / "hooks"
        hooks_dir.mkdir()
        monkeypatch.setattr("rica.hooks.HOOKS_DIR", hooks_dir)
        
        # Create an invalid hook script
        hook_script = hooks_dir / "unknown_event.py"
        hook_script.write_text("# Invalid hook script")
        
        result = discover_hooks()
        assert result == {}


class TestBuildPayload:
    """Test payload building functionality."""

    def test_build_payload_shape(self, monkeypatch):
        """Test build_payload creates correct payload shape."""
        # Mock version
        monkeypatch.setattr("rica.hooks.__version__", "1.0.0")
        
        payload = build_payload("pre_plan", "abc123", {"foo": "bar"})
        
        # Check required keys
        assert "event" in payload
        assert "session_id" in payload
        assert "rica_version" in payload
        assert "timestamp" in payload
        assert "extra" in payload
        
        # Check values
        assert payload["event"] == "pre_plan"
        assert payload["session_id"] == "abc123"
        assert payload["rica_version"] == "1.0.0"
        assert payload["extra"] == {"foo": "bar"}
        assert isinstance(payload["timestamp"], str)

    def test_build_payload_no_extra(self, monkeypatch):
        """Test build_payload with no extra data."""
        # Mock version
        monkeypatch.setattr("rica.hooks.__version__", "1.0.0")
        
        payload = build_payload("post_build", None, None)
        
        assert payload["event"] == "post_build"
        assert payload["session_id"] is None
        assert payload["extra"] == {}


class TestFireHook:
    """Test hook firing functionality."""

    def test_fire_hook_no_hook_returns_skipped(self, tmp_path, monkeypatch):
        """Test fire_hook returns skipped when no hook found."""
        # Monkeypatch HOOKS_DIR to empty directory
        hooks_dir = tmp_path / "hooks"
        hooks_dir.mkdir()
        monkeypatch.setattr("rica.hooks.HOOKS_DIR", hooks_dir)
        
        result = fire_hook("pre_plan")
        
        assert result["skipped"] is True
        assert result["status"] == "no_hook"
        assert result["event"] == "pre_plan"
        assert result["returncode"] is None

    def test_fire_hook_ok(self, tmp_path, monkeypatch):
        """Test fire_hook executes successful hook."""
        # Monkeypatch HOOKS_DIR
        hooks_dir = tmp_path / "hooks"
        hooks_dir.mkdir()
        monkeypatch.setattr("rica.hooks.HOOKS_DIR", hooks_dir)
        
        # Create a successful hook script
        hook_script = hooks_dir / "post_plan.py"
        hook_script.write_text("import sys; sys.exit(0)")
        
        result = fire_hook("post_plan")
        
        assert result["skipped"] is False
        assert result["status"] == "ok"
        assert result["returncode"] == 0
        assert result["event"] == "post_plan"

    def test_fire_hook_error_returncode(self, tmp_path, monkeypatch):
        """Test fire_hook handles hook script with error return code."""
        # Monkeypatch HOOKS_DIR
        hooks_dir = tmp_path / "hooks"
        hooks_dir.mkdir()
        monkeypatch.setattr("rica.hooks.HOOKS_DIR", hooks_dir)
        
        # Create a failing hook script
        hook_script = hooks_dir / "post_plan.py"
        hook_script.write_text("import sys; sys.exit(1)")
        
        result = fire_hook("post_plan")
        
        assert result["skipped"] is False
        assert result["status"] == "error"
        assert result["returncode"] == 1
        assert result["event"] == "post_plan"

    @patch('subprocess.run')
    def test_fire_hook_timeout(self, mock_run, tmp_path, monkeypatch):
        """Test fire_hook handles timeout."""
        # Monkeypatch HOOKS_DIR
        hooks_dir = tmp_path / "hooks"
        hooks_dir.mkdir()
        monkeypatch.setattr("rica.hooks.HOOKS_DIR", hooks_dir)
        
        # Create a hook script
        hook_script = hooks_dir / "post_plan.py"
        hook_script.write_text("import time; time.sleep(60)")
        
        # Mock subprocess to raise TimeoutExpired
        import subprocess
        mock_run.side_effect = subprocess.TimeoutExpired("python", 30)
        
        result = fire_hook("post_plan")
        
        assert result["skipped"] is False
        assert result["status"] == "timeout"
        assert result["returncode"] is None
        assert result["event"] == "post_plan"

    @patch('subprocess.run')
    def test_fire_hook_exception(self, mock_run, tmp_path, monkeypatch):
        """Test fire_hook handles general exceptions."""
        # Monkeypatch HOOKS_DIR
        hooks_dir = tmp_path / "hooks"
        hooks_dir.mkdir()
        monkeypatch.setattr("rica.hooks.HOOKS_DIR", hooks_dir)
        
        # Create a hook script
        hook_script = hooks_dir / "post_plan.py"
        hook_script.write_text("print('hello')")
        
        # Mock subprocess to raise general exception
        mock_run.side_effect = Exception("Test error")
        
        result = fire_hook("post_plan")
        
        assert result["skipped"] is False
        assert result["status"] == "error"
        assert result["returncode"] is None
        assert result["stderr"] == "Test error"
        assert result["event"] == "post_plan"
