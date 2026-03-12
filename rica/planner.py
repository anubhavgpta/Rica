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

    def plan(self, goal: str) -> list[dict]:
        """
        Returns list of subtask dicts.
        Calls Gemini to decompose the goal into 2-6 ordered subtasks.
        """
        logger.debug(
            f"[planner] Planning: {goal[:60]}"
        )
        
        prompt = f"""You are a coding task planner.
Goal: {goal}

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
                    logger.info(f"[planner] Generated {len(tasks)} tasks")
                    return tasks
                    
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
