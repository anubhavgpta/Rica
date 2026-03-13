import os
import re
from pathlib import Path
from loguru import logger
import google.genai as genai
from .replacer import StrReplacer

def sanitize_path(relative_path: str, workspace_dir: str) -> str:
    """
    Sanitize file path to prevent traversal attacks.
    
    Args:
        relative_path: Path from Gemini response
        workspace_dir: Current workspace directory
        
    Returns:
        str: Safe relative path within workspace
    """
    parsed_path = Path(relative_path)
    
    # Fix A: Strip leading workspace name to prevent nested subdirectories
    workspace_name = Path(workspace_dir).name
    parts = parsed_path.parts
    if parts and parts[0] == workspace_name:
        relative_path = str(Path(*parts[1:]))
        parsed_path = Path(relative_path)
    
    # If path is absolute AND outside workspace, use only filename
    if parsed_path.is_absolute() or '..' in parsed_path.parts:
        return parsed_path.name
    
    return relative_path

class RicaCodegen:
    """
    Generates code files from a task description
    using Gemini. Supports surgical edits via str_replace.
    """

    def __init__(self, config: dict):
        self.config = config
        self.client = genai.Client(api_key=config["api_key"])

    @staticmethod
    def _resolve_target(
        rel_path: str,
        workspace_dir: str,
        project_dir: str | None,
        snapshot: "CodebaseSnapshot | None",
    ) -> Path:
        """Resolve target path for file operations."""
        target_dir = workspace_dir
        
        if project_dir and snapshot:
            # Check if this file exists in snapshot (meaning it's an edit, not a new file)
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
        """Apply a surgical edit to an existing file."""
        target = self._resolve_target(rel_path, workspace_dir, project_dir, snapshot)
        success = StrReplacer.apply(target, old_str, new_str)
        if not success:
            # Fall back to full file write
            logger.warning("[codegen] str_replace failed, falling back to full write")
            return None
        return target

    def _apply_append(
        self,
        rel_path: str,
        content: str,
        workspace_dir: str,
        project_dir: str | None,
        snapshot: "CodebaseSnapshot | None",
    ) -> Path:
        """Append content to an existing or new file."""
        target = self._resolve_target(rel_path, workspace_dir, project_dir, snapshot)
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding='utf-8')
            logger.info(f"[codegen] Created new file: {target}")
        else:
            StrReplacer.append(target, content)
        return target

    def generate(
        self,
        task: dict,
        snapshot = None,
        workspace_dir: str = None,
        project_dir: str = None,
        context: str = ""
    ) -> list[str]:
        """
        Returns list of file paths created.
        Supports FILE:, EDIT:, and APPEND: formats.
        """
        logger.debug(
            f"[codegen] Generating for: "
            f"{task['description'][:60]}"
        )
        
        # Prepare context from snapshot
        if snapshot and not snapshot.is_empty:
            context = snapshot.format_for_prompt()
        else:
            context = ""
        
        # Check if this is modifying an existing file
        target_file = self._extract_target_file(task['description'], snapshot)
        current_content = ""
        if target_file and snapshot and target_file in snapshot.files:
            current_content = snapshot.files[target_file]
        
        prompt = self._build_prompt(task, context, workspace_dir, target_file, current_content)

        try:
            response = self.client.models.generate_content(
                model=self.config["model"],
                contents=prompt
            )
            
            return self._parse_and_apply_response(response.text, workspace_dir, project_dir, snapshot)
            
        except Exception as e:
            logger.error(f"[codegen] Generation failed: {e}")
            return []

    def _extract_target_file(self, description: str, snapshot) -> str | None:
        """Extract target file from task description."""
        import re
        # Look for patterns like "add X to utils/paths.py" or "modify utils/paths.py"
        patterns = [
            r'to\s+([a-zA-Z0-9_/.]+\.py)',
            r'([a-zA-Z0-9_/.]+\.py)\s+to',
            r'([a-zA-Z0-9_/.]+\.py)\s+file',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, description)
            if match:
                file_path = match.group(1)
                # Normalize path
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
- No explanation outside the format"""

        if target_file and current_content:
            # Add specific instructions for existing files
            return f"""{base_prompt}

The file `{target_file}` already exists with this content:
{current_content}

Use EDIT: format to make a targeted change, or APPEND: to add new content at the end.
Do NOT use FILE: format unless you need to rewrite the entire file."""
        
        return base_prompt

    def _parse_and_apply_response(self, response_text: str, workspace_dir: str, project_dir: str | None, snapshot) -> list[str]:
        """Parse response and apply appropriate operation."""
        lines = response_text.strip().split('\n')
        if not lines:
            logger.warning("[codegen] Empty response")
            return []
        
        first_line = lines[0].strip()
        
        # Handle FILE: format (new files or full rewrites)
        if first_line.startswith('FILE:'):
            return self._handle_file_format(lines, workspace_dir, project_dir, snapshot)
        
        # Handle EDIT: format (surgical edits)
        elif first_line.startswith('EDIT:'):
            return self._handle_edit_format(lines, workspace_dir, project_dir, snapshot)
        
        # Handle APPEND: format (append operations)
        elif first_line.startswith('APPEND:'):
            return self._handle_append_format(lines, workspace_dir, project_dir, snapshot)
        
        else:
            logger.warning("[codegen] Unknown response format")
            return []

    def _handle_file_format(self, lines: list[str], workspace_dir: str, project_dir: str | None, snapshot) -> list[str]:
        """Handle FILE: format - create new file or full rewrite."""
        if len(lines) < 2:
            logger.warning("[codegen] Incomplete FILE format")
            return []
        
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
        """Handle EDIT: format - surgical edits."""
        relative_path = lines[0].replace('EDIT:', '').strip()
        safe_path = sanitize_path(relative_path, workspace_dir)
        
        # Parse the <<<OLD >>>NEW >>>END block
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
        else:
            # Fall back to full file write
            logger.warning("[codegen] Edit failed, falling back to full write")
            return self._fallback_to_full_write(safe_path, workspace_dir, project_dir, snapshot)

    def _handle_append_format(self, lines: list[str], workspace_dir: str, project_dir: str | None, snapshot) -> list[str]:
        """Handle APPEND: format - append to file."""
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

    def _fallback_to_full_write(self, safe_path: str, workspace_dir: str, project_dir: str | None, snapshot) -> list[str]:
        """Fallback to full file write when edit fails."""
        # This would need the full file content - for now, return empty
        logger.warning("[codegen] Full write fallback not implemented")
        return []
