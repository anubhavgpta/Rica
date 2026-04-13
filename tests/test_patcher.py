"""Tests for rica/patcher.py."""

import sys
from pathlib import Path

import pytest

from rica.models import EditSpec
from rica.patcher import apply_diff, generate_diff, patch_file


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# 1. generate_diff — changed content
# ---------------------------------------------------------------------------

def test_generate_diff_changed(tmp_path):
    original = "line one\nline two\nline three\n"
    modified = "line one\nline TWO\nline three\n"
    fp = tmp_path / "sample.py"

    diff = generate_diff(original, modified, fp)

    assert diff != ""
    assert "+" in diff
    assert "-" in diff


# ---------------------------------------------------------------------------
# 2. generate_diff — identical content
# ---------------------------------------------------------------------------

def test_generate_diff_identical(tmp_path):
    content = "no changes here\n"
    fp = tmp_path / "same.py"

    assert generate_diff(content, content, fp) == ""


# ---------------------------------------------------------------------------
# 3. generate_diff — filepath in headers
# ---------------------------------------------------------------------------

def test_generate_diff_headers(tmp_path):
    fp = tmp_path / "myfile.py"
    diff = generate_diff("old\n", "new\n", fp)

    assert "a/" in diff
    assert "b/" in diff


# ---------------------------------------------------------------------------
# 4. apply_diff — round-trip
# ---------------------------------------------------------------------------

def test_apply_diff_roundtrip(tmp_path):
    fp = tmp_path / "code.py"
    original = "x = 1\ny = 2\nz = 3\n"
    modified = "x = 1\ny = 99\nz = 3\n"
    _write(fp, original)

    diff = generate_diff(original, modified, fp)
    result = apply_diff(diff, tmp_path)

    assert result.success
    assert fp in result.files_patched
    assert _read(fp) == modified


# ---------------------------------------------------------------------------
# 5. apply_diff — multi-file diff
# ---------------------------------------------------------------------------

def test_apply_diff_multi_file(tmp_path):
    fp_a = tmp_path / "alpha.py"
    fp_b = tmp_path / "beta.py"
    orig_a = "a = 1\n"
    orig_b = "b = 2\n"
    mod_a = "a = 10\n"
    mod_b = "b = 20\n"
    _write(fp_a, orig_a)
    _write(fp_b, orig_b)

    diff = generate_diff(orig_a, mod_a, fp_a) + generate_diff(orig_b, mod_b, fp_b)
    result = apply_diff(diff, tmp_path)

    assert fp_a in result.files_patched
    assert fp_b in result.files_patched
    assert _read(fp_a) == mod_a
    assert _read(fp_b) == mod_b


# ---------------------------------------------------------------------------
# 6. apply_diff — bad diff
# ---------------------------------------------------------------------------

def test_apply_diff_bad_diff(tmp_path):
    result = apply_diff("this is not a valid unified diff at all", tmp_path)

    assert result.success is False
    assert result.errors


# ---------------------------------------------------------------------------
# 7. patch_file — basic EditSpec
# ---------------------------------------------------------------------------

def test_patch_file_basic(tmp_path):
    fp = tmp_path / "file.py"
    _write(fp, "line1\nline2\nline3\nline4\nline5\n")

    spec = EditSpec(
        filepath=fp,
        start_line=2,
        end_line=3,
        replacement_lines=["replaced2", "replaced3"],
    )
    result = patch_file(fp, spec)

    assert result.success
    assert _read(fp) == "line1\nreplaced2\nreplaced3\nline4\nline5\n"


# ---------------------------------------------------------------------------
# 8. patch_file — single line replacement
# ---------------------------------------------------------------------------

def test_patch_file_single_line(tmp_path):
    fp = tmp_path / "single.py"
    _write(fp, "aaa\nbbb\nccc\n")

    spec = EditSpec(filepath=fp, start_line=2, end_line=2, replacement_lines=["BBB"])
    result = patch_file(fp, spec)

    assert result.success
    assert _read(fp) == "aaa\nBBB\nccc\n"


# ---------------------------------------------------------------------------
# 9. patch_file — validate_cmd success
# ---------------------------------------------------------------------------

def test_patch_file_validate_success(tmp_path):
    fp = tmp_path / "ok.py"
    _write(fp, "x = 1\nx = 2\nx = 3\n")

    # python -c "import sys; sys.exit(0)" always succeeds
    spec = EditSpec(filepath=fp, start_line=2, end_line=2, replacement_lines=["x = 99"])
    result = patch_file(fp, spec, validate_cmd=["python", "-c", "import sys; sys.exit(0)"])

    assert result.success
    assert result.rolled_back is False
    assert result.validation_exit_code == 0


# ---------------------------------------------------------------------------
# 10. patch_file — validate_cmd failure + rollback
# ---------------------------------------------------------------------------

def test_patch_file_validate_rollback(tmp_path):
    fp = tmp_path / "fail.py"
    original = "x = 1\nx = 2\nx = 3\n"
    _write(fp, original)

    # python -c "import sys; sys.exit(1)" always fails
    spec = EditSpec(filepath=fp, start_line=2, end_line=2, replacement_lines=["x = 99"])
    result = patch_file(fp, spec, validate_cmd=["python", "-c", "import sys; sys.exit(1)"])

    assert result.rolled_back is True
    assert result.success is False
    assert _read(fp) == original


# ---------------------------------------------------------------------------
# 11. patch_file — out-of-range lines
# ---------------------------------------------------------------------------

def test_patch_file_out_of_range(tmp_path):
    fp = tmp_path / "short.py"
    _write(fp, "a\nb\nc\n")

    spec = EditSpec(filepath=fp, start_line=100, end_line=102, replacement_lines=["x"])
    result = patch_file(fp, spec)

    assert result.success is False
    assert result.error != ""


# ---------------------------------------------------------------------------
# 12. Atomic write — original not corrupted on write failure
# ---------------------------------------------------------------------------

def test_atomic_write_no_corruption(tmp_path, monkeypatch):
    fp = tmp_path / "atomic.py"
    original = "safe = True\nsafe = True\n"
    _write(fp, original)

    original_replace = Path.replace

    def failing_replace(self, target_path):
        if str(self).endswith(".tmp"):
            raise OSError("Simulated disk failure")
        return original_replace(self, target_path)

    monkeypatch.setattr(Path, "replace", failing_replace)

    spec = EditSpec(filepath=fp, start_line=1, end_line=1, replacement_lines=["safe = False"])
    result = patch_file(fp, spec)

    assert result.success is False
    # Original file must be intact
    assert _read(fp) == original
