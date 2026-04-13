"""Tests for Rica L23 SWE-bench mode."""

from pathlib import Path

import pytest

from rica.prompts import render_prompt


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_plan():
    from rica.models import BuildPlan, LanguageInstallBlock
    return BuildPlan(
        session_id="test-sw",
        goal="test",
        languages=["python"],
        language="python",
        rationale="test",
        estimated_files=1,
        milestones=[],
        install_steps=[],
    )


def _make_error(stderr: str = "RuntimeError: test"):
    from rica.models import ErrorClass
    return ErrorClass(
        category="runtime_error",
        implicated_files=[],
        error_summary=stderr[:120],
        raw_stderr=stderr,
    )


# ---------------------------------------------------------------------------
# 1 & 2. CLI flag parsing
# ---------------------------------------------------------------------------

def test_swebench_flag_present(monkeypatch, tmp_path):
    monkeypatch.setenv("RICA_HOME", str(tmp_path / ".rica"))

    captured = {}

    def mock_dashboard(**kwargs):
        captured.update(kwargs)

    import rica.dashboard
    monkeypatch.setattr(rica.dashboard, "run_dashboard", mock_dashboard)

    from typer.testing import CliRunner
    from rica.main import app

    runner = CliRunner()
    runner.invoke(app, ["agent", "--swebench"])

    assert captured.get("swebench_mode") is True


def test_swebench_flag_absent(monkeypatch, tmp_path):
    monkeypatch.setenv("RICA_HOME", str(tmp_path / ".rica"))

    captured = {}

    def mock_dashboard(**kwargs):
        captured.update(kwargs)

    import rica.dashboard
    monkeypatch.setattr(rica.dashboard, "run_dashboard", mock_dashboard)

    from typer.testing import CliRunner
    from rica.main import app

    runner = CliRunner()
    runner.invoke(app, ["agent"])

    assert captured.get("swebench_mode") is False


# ---------------------------------------------------------------------------
# 3. render_prompt — if-block included
# ---------------------------------------------------------------------------

def test_render_prompt_block_included():
    template = "BEFORE\n{{#if swebench_mode}}\nSTRICT\n{{/if}}\nAFTER"
    result = render_prompt(template, {"swebench_mode": True})
    assert "STRICT" in result
    assert "{{#if" not in result
    assert "{{/if}}" not in result


# ---------------------------------------------------------------------------
# 4. render_prompt — if-block excluded
# ---------------------------------------------------------------------------

def test_render_prompt_block_excluded():
    template = "BEFORE\n{{#if swebench_mode}}\nSTRICT\n{{/if}}\nAFTER"
    result = render_prompt(template, {"swebench_mode": False})
    assert "STRICT" not in result
    assert "{{#if" not in result
    assert "{{/if}}" not in result


# ---------------------------------------------------------------------------
# 5. render_prompt — variable substitution works alongside if-block
# ---------------------------------------------------------------------------

def test_render_prompt_variable_substitution():
    template = "Hello {{name}}!\n{{#if flag}}\nFLAG_CONTENT\n{{/if}}"
    result = render_prompt(template, {"name": "world", "flag": True})
    assert "Hello world!" in result
    assert "FLAG_CONTENT" in result


# ---------------------------------------------------------------------------
# 6. render_prompt — unknown key is falsy (no exception)
# ---------------------------------------------------------------------------

def test_render_prompt_unknown_key_is_falsy():
    template = "{{#if unknown_key}}X{{/if}}rest"
    result = render_prompt(template, {})
    assert "X" not in result
    assert "rest" in result


# ---------------------------------------------------------------------------
# 7. Patcher is default in swebench mode
# ---------------------------------------------------------------------------

def test_swebench_patcher_is_default(tmp_path, monkeypatch):
    fp = tmp_path / "code.py"
    fp.write_text("x = 1\nx = 2\n")

    from rica.models import PatchResult
    patch_calls = []

    def mock_patch_file(filepath, edit_spec, validate_cmd=None):
        patch_calls.append(filepath)
        filepath.write_text("x = fixed\n")
        return PatchResult(success=True, diff_applied="@@")

    import rica.debugger
    monkeypatch.setattr(rica.debugger, "patch_file", mock_patch_file)
    monkeypatch.setattr(rica.debugger, "localize", lambda error_output, repo_path: [])
    monkeypatch.setattr(rica.debugger.llm, "generate", lambda *a, **kw: "x = fixed")

    from rica.debugger import generate_fix
    from rich.console import Console

    generate_fix(
        _make_error(),
        fp,
        tmp_path,
        _make_plan(),
        Console(),
        swebench_mode=True,
    )

    assert patch_calls, "patch_file must be called in swebench mode"


# ---------------------------------------------------------------------------
# 8. Fallback to whole-file rewrite in swebench mode when rolled_back + no localized
# ---------------------------------------------------------------------------

def test_swebench_fallback_to_whole_file(tmp_path, monkeypatch):
    fp = tmp_path / "code.py"
    fp.write_text("x = 1\n")

    from rica.models import PatchResult

    monkeypatch.setattr(
        "rica.debugger._attempt_patch_fix",
        lambda **kw: PatchResult(success=False, diff_applied="", rolled_back=True),
    )
    monkeypatch.setattr("rica.debugger.localize", lambda error_output, repo_path: [])

    generate_calls = []

    def mock_llm_generate(*args, **kwargs):
        generate_calls.append(kwargs.get("call_type"))
        return "x = whole_file_fixed"

    import rica.debugger
    monkeypatch.setattr(rica.debugger.llm, "generate", mock_llm_generate)

    from rica.debugger import generate_fix
    from rich.console import Console

    result = generate_fix(
        _make_error(),
        fp,
        tmp_path,
        _make_plan(),
        Console(),
        swebench_mode=True,
    )

    assert "debug" in generate_calls, "whole-file LLM call (call_type=debug) must occur"
    assert result == "x = whole_file_fixed"


# ---------------------------------------------------------------------------
# 9. Non-swebench mode: patch_file NOT called for keyword_match-only results
# ---------------------------------------------------------------------------

def test_non_swebench_no_patch_for_keyword_match(tmp_path, monkeypatch):
    fp = tmp_path / "code.py"
    fp.write_text("x = 1\n")

    # Localize returns only keyword_match (no stack_trace)
    monkeypatch.setattr(
        "rica.debugger.localize",
        lambda error_output, repo_path: [(fp, 1, "keyword_match")],
    )

    patch_calls = []

    from rica.models import PatchResult

    def mock_patch_file(filepath, edit_spec, validate_cmd=None):
        patch_calls.append(filepath)
        return PatchResult(success=True, diff_applied="@@")

    import rica.debugger
    monkeypatch.setattr(rica.debugger, "patch_file", mock_patch_file)
    monkeypatch.setattr(rica.debugger.llm, "generate", lambda *a, **kw: "x = 2")

    from rica.debugger import generate_fix
    from rich.console import Console

    generate_fix(
        _make_error(),
        fp,
        tmp_path,
        _make_plan(),
        Console(),
        swebench_mode=False,
    )

    assert not patch_calls, "patch_file must NOT be called for keyword_match-only in non-swebench mode"
