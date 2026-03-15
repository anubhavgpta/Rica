from __future__ import annotations

from pathlib import Path
import re

import google.genai as genai

from rica.logging_utils import get_component_logger

from .replacer import StrReplacer

logger = get_component_logger("codegen")


def sanitize_path(relative_path: str, workspace_dir: str) -> str:
    """Sanitize file path to prevent traversal attacks."""
    parsed_path = Path(relative_path)
    workspace_name = Path(workspace_dir).name
    parts = parsed_path.parts
    if parts and parts[0] == workspace_name:
        relative_path = str(Path(*parts[1:]))
        parsed_path = Path(relative_path)

    if parsed_path.is_absolute() or '..' in parsed_path.parts:
        return parsed_path.name

    return relative_path


class RicaCodegen:
    """Generate and apply code changes from a task description."""

    def __init__(self, config: dict):
        self.config = config
        self.client = genai.Client(api_key=config["api_key"])
        self.max_attempts = int(config.get("codegen_attempts", 2))  # Reduced from 3

    @staticmethod
    def _resolve_target(
        rel_path: str,
        workspace_dir: str,
        project_dir: str | None,
        snapshot: "CodebaseSnapshot | None",
    ) -> Path:
        target_dir = workspace_dir

        if project_dir and snapshot:
            normalized_rel = rel_path.replace('\\', '/')
            snapshot_files_normalized = {k.replace('\\', '/') for k in snapshot.files}
            if normalized_rel in snapshot_files_normalized:
                target_dir = project_dir
                logger.info(f"[codegen] Writing to project: {rel_path}")

        return Path(target_dir) / rel_path

    def _apply_edit(
        self,
        rel_path: str,
        old_str: str,
        new_str: str,
        workspace_dir: str,
        project_dir: str | None,
        snapshot: "CodebaseSnapshot | None",
    ) -> Path | None:
        target = self._resolve_target(rel_path, workspace_dir, project_dir, snapshot)
        success = StrReplacer.apply(target, old_str, new_str)
        if not success:
            logger.warning("[codegen] str_replace failed, falling back to full write")
            return None
        self._normalize_imports(target)
        return target

    def _apply_append(
        self,
        rel_path: str,
        content: str,
        workspace_dir: str,
        project_dir: str | None,
        snapshot: "CodebaseSnapshot | None",
    ) -> Path:
        target = self._resolve_target(rel_path, workspace_dir, project_dir, snapshot)
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding='utf-8')
            logger.info(f"[codegen] Created new file: {target}")
        else:
            StrReplacer.append(target, content)
            self._normalize_imports(target)
        return target

    def _normalize_imports(
        self,
        filepath: Path
    ) -> None:
        """Move stray imports to the top of a Python file."""
        content = filepath.read_text(encoding='utf-8')
        lines = content.splitlines(keepends=True)

        top_lines = []
        body_lines = []
        import_lines = []

        in_header = True
        for line in lines:
            stripped = line.strip()
            if in_header:
                if (stripped == ''
                    or stripped.startswith('#')
                    or stripped.startswith('import ')
                    or stripped.startswith('from ')):
                    top_lines.append(line)
                else:
                    in_header = False
                    body_lines.append(line)
            else:
                if (stripped.startswith('import ')
                        or stripped.startswith(
                            'from ')):
                    import_lines.append(line)
                else:
                    body_lines.append(line)

        if not import_lines:
            return

        existing_top = ''.join(top_lines)
        new_imports = [
            l for l in import_lines
            if l.strip() not in existing_top
        ]
        if not new_imports:
            return

        new_content = (
            ''.join(top_lines).rstrip('\n')
            + '\n'
            + ''.join(new_imports)
            + '\n'
            + ''.join(body_lines)
        )
        filepath.write_text(
            new_content, encoding='utf-8'
        )
        logger.info(
            f"[codegen] Normalized imports"
            f" in {filepath.name}"
        )

    def generate(
        self,
        task: dict,
        snapshot = None,
        workspace_dir: str = None,
        project_dir: str = None,
        context: str = ""
    ) -> list[str]:
        """Return a list of generated or modified file paths."""
        logger.debug(
            f"[codegen] Generating for: "
            f"{task['description'][:60]}"
        )

        if snapshot and not snapshot.is_empty:
            context = snapshot.format_for_prompt()

        target_file = self._extract_target_file(task['description'], snapshot)
        current_content = ""
        if target_file and snapshot and target_file in snapshot.files:
            current_content = snapshot.files[target_file]

        prompt = self._build_prompt(task, context, workspace_dir, target_file, current_content)

        try:
            response_text = self._generate_response_text(prompt)
            return self._parse_and_apply_response(
                response_text,
                workspace_dir,
                project_dir,
                snapshot,
            )
        except Exception as error:
            logger.error(f"[codegen] Generation failed after retries: {error}")
            return []

    def _generate_response_text(self, prompt: str) -> str:
        """Generate robust text output with validation and retries."""
        last_error: Exception | None = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                response = self.client.models.generate_content(
                    model=self.config["model"],
                    contents=prompt,
                )
                if response is None:
                    raise RuntimeError("LLM returned no response")
                if not hasattr(response, "text") or not response.text:
                    raise RuntimeError("LLM returned empty text")
                text = response.text.strip()
                if not text:
                    raise RuntimeError("LLM returned blank text")
                return text
            except Exception as error:
                last_error = error
                logger.warning(
                    f"[codegen] Attempt {attempt}/{self.max_attempts} failed: {error}"
                )
        raise RuntimeError(str(last_error) if last_error else "LLM generation failed")

    def _extract_target_file(self, description: str, snapshot) -> str | None:
        """Extract target file from task description."""
        patterns = [
            r'to\s+([a-zA-Z0-9_/.]+\.py)',
            r'([a-zA-Z0-9_/.]+\.py)\s+to',
            r'([a-zA-Z0-9_/.]+\.py)\s+file',
        ]

        for pattern in patterns:
            match = re.search(pattern, description)
            if match:
                file_path = match.group(1)
                if not file_path.startswith('utils/'):
                    file_path = file_path.replace('\\', '/')
                return file_path

        return None

    def _build_prompt(self, task: dict, context: str, workspace_dir: str, target_file: str | None, current_content: str) -> str:
        """Build the appropriate prompt based on whether we're modifying existing files."""
        base_prompt = f"""{context}

Task: {task['description']}
Workspace: {workspace_dir}

Generate the code for this task.

Respond in one of these formats:

FORMAT A - for new files or full rewrites:
FILE: relative/path/to/file.py
[complete file contents here]

FORMAT B - for surgical edits to existing files:
EDIT: relative/path/to/file.py
<<<OLD
[exact text to replace]
>>>NEW
[replacement text]
>>>END

FORMAT C - for appending to existing files:
APPEND: relative/path/to/file.py
[content to append]

Rules:
- Write complete, working code
- Use relative paths from workspace root
- One file per response
- No explanation outside the format
- If you cannot produce a valid edit, return FILE:, EDIT:, or APPEND: with concrete content only"""

        if target_file and current_content:
            return f"""{base_prompt}

The file `{target_file}` already exists with this content:
{current_content}

Use EDIT: format to make a targeted change, or APPEND: to add new content at the end.
Do NOT use FILE: format unless you need to rewrite the entire file."""
        
        return base_prompt

    @staticmethod
    def looks_like_python(code: str) -> bool:
        """Check if the output looks like raw Python code."""
        indicators = [
            "import ",
            "def ",
            "class ",
            "if __name__",
            "print(",
            "from ",
            "# ",
            "'''",
            '"""',
            "return ",
            "pass",
            "break",
            "continue"
        ]
        
        return any(ind in code for ind in indicators)

    def _parse_and_apply_response(self, response_text: str, workspace_dir: str, project_dir: str | None, snapshot) -> list[str]:
        """Parse response and apply appropriate operation."""
        if not response_text:
            logger.warning("[codegen] Empty response text after validation")
            return []
        
        # Try flexible parsing first
        import re
        
        # Look for FILE/EDIT blocks more flexibly
        file_pattern = re.findall(
            r"(?:FILE|EDIT):\s*(.+?)\n(.*?)(?=\n(?:FILE|EDIT):|\Z)",
            response_text,
            re.DOTALL
        )
        
        if file_pattern:
            files = []
            for path, content in file_pattern:
                files.append({
                    "file": path.strip(),
                    "content": content.strip(),
                    "type": "edit"
                })
            
            # Apply the parsed files
            created_files = []
            for file_info in files:
                try:
                    file_path = Path(workspace_dir) / file_info["file"]
                    file_path.parent.mkdir(parents=True, exist_ok=True)
                    file_path.write_text(file_info["content"], encoding='utf-8')
                    created_files.append(str(file_path))
                    logger.info(f"[codegen] Created/edited file: {file_path}")
                except Exception as e:
                    logger.error(f"[codegen] Failed to create {file_info['file']}: {e}")
            
            return created_files
        
        # Fall back to line-based parsing for strict formats
        lines = response_text.strip().split('\n')
        if not lines:
            logger.warning("[codegen] Empty response")
            return []
        
        first_line = lines[0].strip()
        
        if first_line.startswith('FILE:'):
            return self._handle_file_format(lines, workspace_dir, project_dir, snapshot)
        if first_line.startswith('EDIT:'):
            return self._handle_edit_format(lines, workspace_dir, project_dir, snapshot)
        if first_line.startswith('APPEND:'):
            return self._handle_append_format(lines, workspace_dir, project_dir, snapshot)

        # Check if output looks like raw Python code
        if RicaCodegen.looks_like_python(response_text):
            logger.info("[codegen] Detected raw Python code, creating script.py")
            script_path = Path(workspace_dir) / "script.py"
            script_path.parent.mkdir(parents=True, exist_ok=True)
            script_path.write_text(response_text.strip(), encoding='utf-8')
            return [str(script_path)]

        # Final fallback: treat output as a single file creation
        logger.warning("[codegen] Unknown response format — using fallback")
        fallback_file = "script.py"
        
        # Create the fallback file
        fallback_path = Path(workspace_dir) / fallback_file
        fallback_path.parent.mkdir(parents=True, exist_ok=True)
        fallback_path.write_text(response_text.strip(), encoding='utf-8')
        
        logger.info(f"[codegen] Created fallback file: {fallback_path}")
        return [str(fallback_path)]

    def _handle_file_format(self, lines: list[str], workspace_dir: str, project_dir: str | None, snapshot) -> list[str]:
        if len(lines) < 2:
            logger.warning("[codegen] Incomplete FILE format — using fallback")
            # Fallback: treat entire output as file content
            fallback_file = "script.py"
            fallback_path = Path(workspace_dir) / fallback_file
            fallback_path.parent.mkdir(parents=True, exist_ok=True)
            fallback_path.write_text('\n'.join(lines).strip(), encoding='utf-8')
            logger.info(f"[codegen] Created fallback file: {fallback_path}")
            return [str(fallback_path)]
        
        relative_path = lines[0].replace('FILE:', '').strip()
        safe_path = sanitize_path(relative_path, workspace_dir)
        
        content = '\n'.join(lines[1:]).strip()
        if not content:
            logger.warning("[codegen] No file content found")
            return []
        
        target = self._resolve_target(safe_path, workspace_dir, project_dir, snapshot)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding='utf-8')
        
        logger.info(f"[codegen] Created file: {target}")
        return [str(target)]

    def _handle_edit_format(self, lines: list[str], workspace_dir: str, project_dir: str | None, snapshot) -> list[str]:
        relative_path = lines[0].replace('EDIT:', '').strip()
        safe_path = sanitize_path(relative_path, workspace_dir)

        old_str = []
        new_str = []
        current_section = None

        for line in lines[1:]:
            if line.strip() == '<<<OLD':
                current_section = 'old'
            elif line.strip() == '>>>NEW':
                current_section = 'new'
            elif line.strip() == '>>>END':
                break
            elif current_section == 'old':
                old_str.append(line)
            elif current_section == 'new':
                new_str.append(line)
        
        if not old_str or not new_str:
            logger.warning("[codegen] Incomplete EDIT format")
            return []
        
        old_text = '\n'.join(old_str)
        new_text = '\n'.join(new_str)
        
        logger.info(f"[codegen] EDIT: {safe_path}")
        target = self._apply_edit(safe_path, old_text, new_text, workspace_dir, project_dir, snapshot)
        
        if target:
            return [str(target)]

        logger.warning("[codegen] Edit failed, falling back to full write")
        return self._fallback_to_full_write(
            safe_path,
            new_text,
            workspace_dir,
            project_dir,
            snapshot,
        )

    def _handle_append_format(self, lines: list[str], workspace_dir: str, project_dir: str | None, snapshot) -> list[str]:
        if len(lines) < 2:
            logger.warning("[codegen] Incomplete APPEND format")
            return []
        
        relative_path = lines[0].replace('APPEND:', '').strip()
        safe_path = sanitize_path(relative_path, workspace_dir)
        
        content = '\n'.join(lines[1:]).strip()
        if not content:
            logger.warning("[codegen] No append content found")
            return []
        
        logger.info(f"[codegen] APPEND: {safe_path}")
        target = self._apply_append(safe_path, content, workspace_dir, project_dir, snapshot)
        return [str(target)]

    def _fallback_to_full_write(self, safe_path: str, content: str, workspace_dir: str, project_dir: str | None, snapshot) -> list[str]:
        """Fallback to a complete file replacement when an edit fails."""
        target = self._resolve_target(safe_path, workspace_dir, project_dir, snapshot)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding='utf-8')
        logger.info(f"[codegen] Fallback full write: {target}")
        return [str(target)]
