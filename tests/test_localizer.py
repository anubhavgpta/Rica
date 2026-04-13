"""Tests for rica/localizer.py."""

from pathlib import Path

import pytest

from rica.localizer import localize


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _reasons(results):
    return [r for _, _, r in results]


def _files(results):
    return [p for p, _, _ in results]


# ---------------------------------------------------------------------------
# 1. Python stack trace
# ---------------------------------------------------------------------------

def test_python_stack_trace(tmp_path):
    target = tmp_path / "mymodule.py"
    target.write_text("def broken():\n    raise ValueError('oops')\n")

    error = (
        "Traceback (most recent call last):\n"
        f'  File "{target}", line 2, in broken\n'
        "ValueError: oops\n"
    )

    results = localize(error, tmp_path)
    assert results, "expected at least one result"
    first_file, first_line, first_reason = results[0]
    assert first_file == target
    assert first_line == 2
    assert first_reason == "stack_trace"


# ---------------------------------------------------------------------------
# 2. Node.js stack trace — both formats
# ---------------------------------------------------------------------------

def test_nodejs_stack_trace_with_function(tmp_path):
    target = tmp_path / "server.js"
    target.write_text("function handler() {}\n")

    # Use filename only as Node.js typically reports in stack traces
    error = "Error: boom\n    at handler (server.js:1:5)\n"

    results = localize(error, tmp_path)
    files = _files(results)
    assert target in files
    idx = files.index(target)
    assert results[idx][2] == "stack_trace"


def test_nodejs_stack_trace_bare(tmp_path):
    target = tmp_path / "app.js"
    target.write_text("console.log('hi');\n")

    # Use filename only (no spaces) as Node.js typically reports in stack traces
    error = "Error: bad\n    at app.js:1:1\n"

    results = localize(error, tmp_path)
    files = _files(results)
    assert target in files
    idx = files.index(target)
    assert results[idx][2] == "stack_trace"


# ---------------------------------------------------------------------------
# 3. Ignored paths (.venv, site-packages)
# ---------------------------------------------------------------------------

def test_ignored_venv_path(tmp_path):
    venv_file = tmp_path / ".venv" / "lib" / "example.py"
    venv_file.parent.mkdir(parents=True)
    venv_file.write_text("pass\n")

    real_file = tmp_path / "real.py"
    real_file.write_text("def real(): pass\n")

    error = (
        "Traceback (most recent call last):\n"
        f'  File "{venv_file}", line 1, in <module>\n'
        f'  File "{real_file}", line 1, in real\n'
        "RuntimeError: from venv\n"
    )

    results = localize(error, tmp_path)
    files = _files(results)
    assert venv_file not in files
    assert real_file in files


def test_ignored_site_packages(tmp_path):
    sp_file = tmp_path / "site-packages" / "pkg" / "module.py"
    sp_file.parent.mkdir(parents=True)
    sp_file.write_text("pass\n")

    error = (
        "Traceback (most recent call last):\n"
        f'  File "{sp_file}", line 1, in <module>\n'
        "ImportError: nope\n"
    )

    results = localize(error, tmp_path)
    assert sp_file not in _files(results)


# ---------------------------------------------------------------------------
# 4. Keyword match
# ---------------------------------------------------------------------------

def test_keyword_match(tmp_path):
    src = tmp_path / "utils.py"
    src.write_text(
        "def calculate_total(items):\n"
        "    return sum(items)\n"
    )

    error = "NameError: name 'calculate_total' is not defined"

    results = localize(error, tmp_path)
    assert results, "expected keyword match"
    kw_hits = [(p, ln, r) for p, ln, r in results if r == "keyword_match"]
    assert any(p == src for p, _, _ in kw_hits), "expected src in keyword matches"


# ---------------------------------------------------------------------------
# 5. Mentioned filename
# ---------------------------------------------------------------------------

def test_mentioned_filename(tmp_path):
    target = tmp_path / "config.py"
    target.write_text("DEBUG = True\n")

    error = "Error loading config.py: invalid syntax at line 1"

    results = localize(error, tmp_path)
    assert results, "expected at least one result"
    files = _files(results)
    assert target in files
    idx = files.index(target)
    assert results[idx][2] == "mentioned_in_error"


# ---------------------------------------------------------------------------
# 6. Empty output
# ---------------------------------------------------------------------------

def test_empty_output(tmp_path):
    assert localize("", tmp_path) == []


# ---------------------------------------------------------------------------
# 7. Nonexistent repo
# ---------------------------------------------------------------------------

def test_nonexistent_repo():
    result = localize("some error occurred", Path("/nonexistent/path/xyz123"))
    assert result == []


# ---------------------------------------------------------------------------
# 8. Ranking — stack_trace beats keyword_match for same (file, line)
# ---------------------------------------------------------------------------

def test_ranking_stack_trace_beats_keyword(tmp_path):
    target = tmp_path / "service.py"
    # Line 1 contains the identifier; stack trace also points to line 1
    target.write_text("def process_request(data):\n    pass\n")

    error = (
        "Traceback (most recent call last):\n"
        f'  File "{target}", line 1, in process_request\n'
        "NameError: process_request is not defined\n"
    )

    results = localize(error, tmp_path)
    assert results

    # The file must appear exactly once with reason stack_trace
    hits = [(p, ln, r) for p, ln, r in results if p == target and ln == 1]
    assert len(hits) == 1
    assert hits[0][2] == "stack_trace"


# ---------------------------------------------------------------------------
# 9. Cap at 20
# ---------------------------------------------------------------------------

def test_cap_at_20(tmp_path):
    # Create 30 distinct Python files and build a traceback referencing each
    frames = []
    for i in range(30):
        f = tmp_path / f"module_{i:02d}.py"
        f.write_text(f"def func_{i}(): pass\n")
        frames.append(f'  File "{f}", line 1, in func_{i}')

    error = "Traceback (most recent call last):\n" + "\n".join(frames) + "\nRuntimeError: too many\n"

    results = localize(error, tmp_path)
    assert len(results) <= 20
