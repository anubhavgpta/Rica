"""
Unified diff generation and application for targeted file edits.
Pure stdlib. No PyPI dependencies.
"""

import difflib
import re
import subprocess
import sys
from pathlib import Path

from .models import ApplyResult, EditSpec, PatchResult


def generate_diff(original: str, modified: str, filepath: Path) -> str:
    """Return a unified diff string between original and modified content."""
    if original == modified:
        return ""
    orig_lines = original.splitlines(keepends=True)
    mod_lines = modified.splitlines(keepends=True)
    diff = difflib.unified_diff(
        orig_lines,
        mod_lines,
        fromfile=f"a/{filepath}",
        tofile=f"b/{filepath}",
    )
    return "".join(diff)


# ---------------------------------------------------------------------------
# Diff parsing helpers
# ---------------------------------------------------------------------------

def _parse_diff(diff_str: str) -> dict[str, list[dict]]:
    """
    Parse a unified diff into {filepath_str: [hunk, ...]}.

    Each hunk is:
      {'old_start': int, 'old_count': int,
       'new_start': int, 'new_count': int,
       'changes': list[tuple[op, line_text]]}
    where op is '+', '-', or ' '.
    """
    result: dict[str, list[dict]] = {}
    current_file: str | None = None
    current_hunks: list[dict] = []
    current_hunk: dict | None = None

    lines = diff_str.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("--- "):
            # Finalise any in-progress file section
            if current_file is not None:
                if current_hunk is not None:
                    current_hunks.append(current_hunk)
                    current_hunk = None
                result[current_file] = current_hunks

            # The +++ line immediately follows
            i += 1
            if i < len(lines) and lines[i].startswith("+++ "):
                raw = lines[i][4:].split("\t")[0].rstrip()
                # Strip b/ prefix added by generate_diff
                if raw.startswith("b/"):
                    raw = raw[2:]
                current_file = raw
                current_hunks = []
                current_hunk = None
        elif line.startswith("@@ ") and current_file is not None:
            if current_hunk is not None:
                current_hunks.append(current_hunk)
            m = re.match(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", line)
            if m:
                current_hunk = {
                    "old_start": int(m.group(1)),
                    "old_count": int(m.group(2)) if m.group(2) is not None else 1,
                    "new_start": int(m.group(3)),
                    "new_count": int(m.group(4)) if m.group(4) is not None else 1,
                    "changes": [],
                }
            else:
                current_hunk = None
        elif current_hunk is not None:
            if line.startswith("+"):
                current_hunk["changes"].append(("+", line[1:]))
            elif line.startswith("-"):
                current_hunk["changes"].append(("-", line[1:]))
            elif line.startswith(" "):
                current_hunk["changes"].append((" ", line[1:]))
            # Ignore "\ No newline at end of file" and other meta lines
        i += 1

    # Finalise last file section
    if current_file is not None:
        if current_hunk is not None:
            current_hunks.append(current_hunk)
        result[current_file] = current_hunks

    return result


def _apply_hunk(lines: list[str], hunk: dict) -> list[str] | None:
    """
    Apply one hunk to a list of lines (without line endings).
    Returns the updated list, or None if the context cannot be located.
    """
    # Old-side lines: context + deleted
    old_side = [(op, text) for op, text in hunk["changes"] if op in (" ", "-")]
    old_texts = [text for _, text in old_side]

    if not old_texts:
        # Pure insertion: insert at old_start position
        pos = max(0, min(hunk["old_start"] - 1, len(lines)))
        new_lines = [(op, text) for op, text in hunk["changes"] if op in (" ", "+")]
        return list(lines[:pos]) + [text for _, text in new_lines] + list(lines[pos:])

    # Search for a matching position, allowing ±3 lines of drift
    start_pos = hunk["old_start"] - 1
    found_pos: int | None = None

    for drift in range(4):
        for sign in ([0] if drift == 0 else [1, -1]):
            pos = start_pos + drift * sign
            if pos < 0:
                continue
            end = pos + len(old_texts)
            if end > len(lines):
                continue
            if lines[pos:end] == old_texts:
                found_pos = pos
                break
        if found_pos is not None:
            break

    if found_pos is None:
        return None

    result = list(lines[:found_pos])
    for op, text in hunk["changes"]:
        if op in (" ", "+"):
            result.append(text)
        # "-" lines are removed
    result.extend(lines[found_pos + len(old_texts):])
    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def apply_diff(diff_str: str, repo_path: Path) -> ApplyResult:
    """Apply a unified diff to files under repo_path. Returns structured result."""
    parsed = _parse_diff(diff_str)

    if not parsed:
        return ApplyResult(
            success=False,
            files_patched=[],
            errors=["No patches found in diff string"],
        )

    files_patched: list[Path] = []
    errors: list[str] = []

    for filepath_str, hunks in parsed.items():
        raw = Path(filepath_str)
        resolved: Path = raw if raw.is_absolute() else repo_path / raw

        if not resolved.exists():
            errors.append(f"File not found: {resolved}")
            continue

        try:
            content = resolved.read_text(encoding="utf-8")
        except Exception as exc:
            errors.append(f"Cannot read {resolved}: {exc}")
            continue

        # Work on lines without endings for simpler matching
        lines = content.splitlines()
        original_lines = list(lines)
        ok = True

        for hunk in hunks:
            updated = _apply_hunk(lines, hunk)
            if updated is None:
                errors.append(
                    f"Hunk @@ -{hunk['old_start']} failed to apply in {resolved}"
                )
                ok = False
                break
            lines = updated

        if not ok:
            continue

        # Reconstruct content, preserving trailing newline behaviour
        new_content = "\n".join(lines)
        if content.endswith("\n"):
            new_content += "\n"

        # Atomic write
        tmp = resolved.with_suffix(resolved.suffix + ".tmp")
        try:
            tmp.write_text(new_content, encoding="utf-8")
            tmp.replace(resolved)
            files_patched.append(resolved)
        except Exception as exc:
            try:
                tmp.unlink(missing_ok=True)
            except Exception:
                pass
            errors.append(f"Write failed for {resolved}: {exc}")

    success = len(files_patched) > 0 and not errors
    return ApplyResult(success=success, files_patched=files_patched, errors=errors)


def patch_file(
    filepath: Path,
    edit_spec: EditSpec,
    validate_cmd: list[str] | None = None,
) -> PatchResult:
    """
    Apply an EditSpec to a single file with optional post-patch validation.
    If validate_cmd is given, run it after patching; roll back on non-zero exit.
    """
    try:
        original = filepath.read_text(encoding="utf-8")
    except Exception as exc:
        return PatchResult(success=False, diff_applied="", error=str(exc))

    lines = original.splitlines(keepends=True)
    total_lines = len(lines)

    if edit_spec.start_line < 1 or edit_spec.start_line > total_lines:
        return PatchResult(
            success=False,
            diff_applied="",
            error=(
                f"start_line {edit_spec.start_line} out of range "
                f"(file has {total_lines} lines)"
            ),
        )

    end_line = min(edit_spec.end_line, total_lines)

    # Build replacement lines, ensuring each ends with a newline
    replacement: list[str] = []
    for raw_line in edit_spec.replacement_lines:
        replacement.append(raw_line if raw_line.endswith("\n") else raw_line + "\n")

    new_lines = lines[: edit_spec.start_line - 1] + replacement + lines[end_line:]
    new_content = "".join(new_lines)

    diff_str = generate_diff(original, new_content, filepath)

    # Atomic write
    tmp = filepath.with_suffix(filepath.suffix + ".tmp")
    try:
        tmp.write_text(new_content, encoding="utf-8")
        tmp.replace(filepath)
    except Exception as exc:
        try:
            tmp.unlink(missing_ok=True)
        except Exception:
            pass
        return PatchResult(success=False, diff_applied=diff_str, error=str(exc))

    # Optional validation
    if validate_cmd is not None:
        cmd = [
            sys.executable if tok == "python" else tok for tok in validate_cmd
        ]
        try:
            proc = subprocess.run(
                cmd, capture_output=True, timeout=60
            )
            exit_code: int | None = proc.returncode
        except Exception as exc:
            exit_code = 1

        if exit_code != 0:
            # Rollback to original
            rollback_tmp = filepath.with_suffix(filepath.suffix + ".tmp")
            try:
                rollback_tmp.write_text(original, encoding="utf-8")
                rollback_tmp.replace(filepath)
            except Exception:
                pass
            return PatchResult(
                success=False,
                diff_applied=diff_str,
                validation_exit_code=exit_code,
                rolled_back=True,
                error=f"Validation failed with exit code {exit_code}",
            )

        return PatchResult(
            success=True,
            diff_applied=diff_str,
            validation_exit_code=exit_code,
        )

    return PatchResult(success=True, diff_applied=diff_str)
