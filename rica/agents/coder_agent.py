from rica.codegen import RicaCodegen
from rica.search import CodeIndex
from rica.logging_utils import get_component_logger

logger = get_component_logger("coder_agent")


class CoderAgent:
    """Agent responsible for generating and modifying code."""
    
    # Ignore directories that should never be indexed
    IGNORE_DIRS = {
        ".venv",
        "venv", 
        "__pycache__",
        ".git",
        "node_modules",
        "dist",
        "build",
        "site-packages",
        ".pytest_cache",
        ".mypy_cache",
        ".tox"
    }
    
    def __init__(self, config: dict):
        self.config = config
        self.codegen = RicaCodegen(config)
        self.code_index = None

    def _initialize_search(self, project_dir: str | None, workspace_dir: str | None):
        """Initialize semantic search for the project."""
        if not project_dir or not self.code_index:
            from pathlib import Path
            import google.genai as genai
            
            target_dir = Path(project_dir or workspace_dir)
            if not target_dir.exists():
                return
                
            client = genai.Client(api_key=self.config["api_key"])
            self.code_index = CodeIndex(
                client=client,
                model=self.config.get("model", "gemini-2.5-flash")
            )
            
            # Index all Python files in project, ignoring specified directories
            indexed_files = 0
            python_files = []
            
            # First, collect all Python files
            for py_file in target_dir.rglob("*.py"):
                # Check if file is in an ignored directory
                rel_path = py_file.relative_to(target_dir)
                parts = rel_path.parts
                
                # Skip if any part matches an ignored directory
                if any(part in self.IGNORE_DIRS for part in parts):
                    logger.debug(f"[coder_agent] Skipping ignored directory: {rel_path}")
                    continue
                
                python_files.append(py_file)
            
            # Guard against no Python files
            if not python_files:
                logger.info("[search] No valid Python files to index")
                return
            
            # Now index the files
            for py_file in python_files:
                try:
                    content = py_file.read_text(encoding="utf-8")
                    rel_path_str = str(py_file.relative_to(target_dir))
                    self.code_index.add_file(rel_path_str, content)
                    indexed_files += 1
                    logger.info(f"[coder_agent] Indexed {rel_path_str}")
                except Exception as e:
                    logger.warning(f"[coder_agent] Failed to index {py_file.name}: {e}")
            
            logger.info(f"[search] Indexed {indexed_files} project files (ignored: venv, cache, git)")

    def _search_context(self, task_description: str, top_k: int = 3) -> str:
        """Search for relevant code context."""
        if not self.code_index:
            return ""
            
        try:
            results = self.code_index.search(task_description, top_k=top_k)
            if not results:
                return ""
                
            context_parts = []
            for result in results:
                context_parts.append(
                    f"File: {result['path']} (lines {result['start_line']}-{result['start_line']+10}):\n"
                    f"```python\n{result['snippet'][:500]}...\n```"
                )
            
            context = "\n\n".join(context_parts)
            logger.info(f"[coder_agent] Found {len(results)} relevant code snippets")
            return context
            
        except Exception as e:
            logger.warning(f"[coder_agent] Search failed: {e}")
            return ""

    def execute(
        self,
        task: dict,
        snapshot=None,
        workspace_dir: str | None = None,
        project_dir: str | None = None,
        context: str = "",
    ) -> list[str]:
        # Initialize search if not already done
        if not self.code_index:
            self._initialize_search(project_dir, workspace_dir)
        
        # Get semantic search context
        search_context = self._search_context(task.get("description", ""))
        
        # Combine existing context with search context
        combined_context = context
        if search_context:
            combined_context = f"{context}\n\nRelevant existing code:\n{search_context}" if context else search_context
        
        return self.codegen.generate(
            task,
            snapshot=snapshot,
            workspace_dir=workspace_dir,
            project_dir=project_dir,
            context=combined_context,
        )
