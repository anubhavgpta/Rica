import os
import re
from pathlib import Path
from loguru import logger
import google.genai as genai

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
    using Gemini. Writes files to workspace_dir.
    """

    def __init__(self, config: dict):
        self.config = config
        self.client = genai.Client(api_key=config["api_key"])

    def generate(
        self,
        task: dict,
        workspace_dir: str,
        context: str = ""
    ) -> list[str]:
        """
        Returns list of file paths created.
        Calls Gemini to generate code and writes files to workspace_dir.
        """
        logger.debug(
            f"[codegen] Generating for: "
            f"{task['description'][:60]}"
        )
        
        prompt = f"""You are an expert software engineer.

Task: {task['description']}
Workspace: {workspace_dir}
Context: {context}

Generate the complete code for this task.

Respond in this EXACT format:

FILE: relative/path/to/file.py
[complete file contents here]

Rules:
- Write complete, working code
- Use relative paths from workspace root
- One file per response
- No explanation outside the format"""

        try:
            response = self.client.models.generate_content(
                model=self.config["model"],
                contents=prompt
            )
            
            # Parse the response
            lines = response.text.strip().split('\n')
            if len(lines) < 2 or not lines[0].startswith('FILE:'):
                logger.warning("[codegen] Invalid response format")
                return []
            
            # Extract file path and sanitize it
            relative_path = lines[0].replace('FILE:', '').strip()
            if not relative_path:
                logger.warning("[codegen] No file path found")
                return []
            
            # Sanitize path to prevent traversal
            safe_path = sanitize_path(relative_path, workspace_dir)
            
            # Extract file content (everything after FILE: line)
            content = '\n'.join(lines[1:]).strip()
            if not content:
                logger.warning("[codegen] No file content found")
                return []
            
            # Create full path and ensure parent directories exist
            full_path = Path(workspace_dir) / safe_path
            full_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Write the file
            with open(full_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            logger.info(f"[codegen] Created file: {full_path}")
            return [str(full_path)]
            
        except Exception as e:
            logger.error(f"[codegen] Generation failed: {e}")
            return []
