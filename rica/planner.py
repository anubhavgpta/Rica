import json
import re
from loguru import logger
import google.genai as genai

class RicaPlanner:
    """
    Breaks a coding goal into ordered subtasks.
    Each subtask has: id, description, type
    (scaffold | codegen | execute | test | fix)
    """

    def __init__(self, config: dict):
        self.config = config
        self.client = genai.Client(api_key=config["api_key"])

    def _clean_json(self, text: str) -> str:
        """Extract JSON from text, removing markdown and extra content."""
        # Remove markdown code blocks
        text = re.sub(r'```json\s*', '', text)
        text = re.sub(r'```\s*', '', text)
        
        # Find JSON array
        match = re.search(r'\[.*\]', text, re.DOTALL)
        if match:
            return match.group(0)
        
        # Fallback: return original text
        return text.strip()

    def plan(self, goal: str, snapshot = None) -> list[dict]:
        """
        Returns list of subtask dicts.
        Calls Gemini to decompose the goal into 2-6 ordered subtasks.
        """
        logger.debug(
            f"[planner] Planning: {goal[:60]}"
        )
        
        # Prepare context from snapshot
        if snapshot and not snapshot.is_empty:
            context = snapshot.format_for_prompt()
        else:
            context = "Starting a fresh project."
        
        prompt = f"""{context}

Goal: {goal}

You are a coding task planner.
Break this into 2-6 ordered subtasks.
Each task must be concrete and actionable.

Return ONLY a JSON array:
[
  {{
    "id": 1,
    "description": "...",
    "type": "scaffold|codegen|execute|test|fix"
  }}
]

Rules:
- Start with scaffold if files need creating
- codegen tasks must name the specific file to create
- execute tasks must give the exact command
- IMPORTANT: For web applications (Flask, FastAPI, Django, Express, etc.), do NOT include a task to start/run the server. Only scaffold and write the code files. The user will start the server themselves.
- IMPORTANT: You are running on Windows.
  - Use `mkdir` only via Python (os.makedirs) not as a shell command.
  - Never use `source` — use `.\venv\Scripts\activate` for venv.
  - Never plan a "activate venv" task — venv activation doesn't persist across subprocess calls. Install packages with `pip install` directly instead.
  - Use `python` not `python3`.
  - Use backslashes or pathlib for paths.
  - Do NOT plan tasks that start a server (flask run, uvicorn, etc).
  - To install from requirements.txt, always use `pip install -r requirements.txt`, never `python requirements.txt`.
  - To install a single package, use `pip install <package>`.
  - When modifying existing files, reference their actual paths from the codebase above.
  - Do not recreate files that already exist unless the goal requires replacing them.
  - Do NOT plan a task to "run" or "execute" a file that is a module/utility (e.g. utils/paths.py, helpers.py, models.py, src/utils/*.py, lib/*.py). Only plan execution for scripts that have a meaningful __main__ block or are entry points.
  - Do NOT plan a task to "verify" a file was written by running it. Verification of file contents should be done by reading the file, not executing it. This applies to ALL files, especially module/utility files like utils/paths.py, helpers.py, models.py, etc.
  - Do NOT plan any task that involves reading, checking, or verifying the contents of a file by executing it. File content verification should only involve reading operations, not execution.
  - When testing a CLI app that requires arguments, always include the arguments in the run command. Never plan to run a CLI script bare (python script.py) if it requires args to do anything useful.
- When modifying an existing file, prefer surgical edits over full rewrites. Use EDIT: or APPEND: format rather than FILE: when adding to or modifying an existing file.
- Only use FILE: format when: creating a brand new file, or the task requires rewriting the entire file structure.
- No explanations, no markdown, JSON only"""

        # Try 3 times to get valid JSON
        for attempt in range(3):
            try:
                response = self.client.models.generate_content(
                    model=self.config["model"],
                    contents=prompt
                )
                
                json_text = self._clean_json(response.text)
                tasks = json.loads(json_text)
                
                # Validate structure
                if isinstance(tasks, list) and all(
                    isinstance(task, dict) and 
                    "id" in task and 
                    "description" in task and 
                    "type" in task
                    for task in tasks
                ):
                    # Filter out verification tasks for module files
                    filtered_tasks = []
                    for task in tasks:
                        desc = task.get('description', '').lower()
                        if ('verify' in desc or 'check' in desc or 'confirm' in desc) and \
                           ('utils/paths.py' in desc or 'utils\\paths.py' in desc or 
                            'module' in desc or 'content' in desc):
                            logger.info(f"[planner] Filtered out verification task: {task.get('description', '')[:50]}")
                            continue
                        filtered_tasks.append(task)
                    
                    logger.info(f"[planner] Generated {len(filtered_tasks)} tasks (filtered from {len(tasks)})")
                    return filtered_tasks
                    
            except Exception as e:
                logger.warning(f"[planner] Attempt {attempt + 1} failed: {e}")
                continue
        
        # Fallback: return single task
        logger.warning("[planner] All attempts failed, using fallback")
        return [{
            "id": 1,
            "description": goal,
            "type": "codegen",
        }]
