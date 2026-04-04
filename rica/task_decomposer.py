"""Task decomposer for Rica L18 autonomous agent."""

import json
from pathlib import Path
from typing import Optional

from google import genai
from rich.console import Console

from .agent_memory import load_history
from .config import GEMINI_API_KEY
from .models import ProjectContext, SubTask


class TaskDecomposer:
    """LLM-driven task planner that breaks user prompts into subtasks."""
    
    def __init__(self, console: Console):
        self.console = console
        self.client = genai.Client(api_key=GEMINI_API_KEY)
        self._decomposer_prompt = self._load_decomposer_prompt()
        self._modify_prompt = self._load_modify_prompt()
    
    def _load_decomposer_prompt(self) -> str:
        """Load the task decomposer prompt."""
        prompt_path = Path(__file__).parent / "prompts" / "agent_decomposer.txt"
        if not prompt_path.exists():
            # Fallback prompt if file doesn't exist
            return """You are Rica's task decomposer. Given a user prompt and project context,
return a JSON array of subtasks to execute in order.

Rules:
- Return ONLY a JSON array. No preamble, no markdown fences, no explanation.
- Each subtask must have a "type" field matching one of:
  plan, build, execute, debug, review, fix, explain, refactor,
  gen_tests, rebuild, watch_start, watch_stop, ask_user
- Prefer "rebuild" over "build" when a workspace already exists.
- Never emit "watch_start" unless the user explicitly asked for file watching.
- Emit a single {"type": "ask_user", "question": "..."} when the prompt
  is genuinely ambiguous and cannot be safely decomposed.
- Keep the subtask list minimal — do not add steps the user did not ask for.
- If the user asks to "add a feature", prefer: rebuild → review → fix.
- If the user asks to "start a new project", prefer: plan → build → execute.

Project context:
{context}

User prompt:
{prompt}"""
        
        return prompt_path.read_text(encoding="utf-8")
    
    def _load_modify_prompt(self) -> str:
        """Load the modify subtask prompt."""
        prompt_path = Path(__file__).parent / "prompts" / "agent_modify_subtask.txt"
        if not prompt_path.exists():
            # Fallback prompt if file doesn't exist
            return """A Rica subtask failed. Suggest a modified version to retry.

Failed subtask:
{subtask}

Failure detail:
{detail}

Return ONLY a single JSON object with the same "type" as the failed subtask,
with adjustments that might resolve the failure. No preamble, no fences."""
        
        return prompt_path.read_text(encoding="utf-8")
    
    def _build_context(self, project_context: ProjectContext) -> str:
        """Build compact JSON context for LLM."""
        context = {
            "session_id": project_context.session_id,
            "workspace_path": project_context.workspace_path,
            "languages": project_context.languages,
            "recent_history": project_context.recent_history[-5:],  # Only last 5 turns
            "last_build_status": project_context.last_build_status,
            "last_debug_status": project_context.last_debug_status,
        }
        # Remove None/empty values for compactness
        return json.dumps({k: v for k, v in context.items() if v is not None and v != ""})
    
    def decompose(self, user_prompt: str, project_context: ProjectContext) -> list[SubTask]:
        """Decompose user prompt into ordered subtasks."""
        context_str = self._build_context(project_context)
        full_prompt = self._decomposer_prompt.format(
            context=context_str,
            prompt=user_prompt
        )
        
        try:
            response = self.client.models.generate_content(
                model="gemini-2.5-flash",
                contents=full_prompt
            )
            
            # Extract JSON from response
            json_text = response.text.strip()
            self.console.print(f"[dim]LLM response: {json_text[:200]}...[/dim]")
            
            if json_text.startswith("```"):
                json_text = json_text.split("\n", 1)[1].rsplit("\n", 1)[0].strip()
            
            # Try to parse JSON
            try:
                subtask_dicts = json.loads(json_text)
            except json.JSONDecodeError as e:
                self.console.print(f"[red]JSON decode error: {e}[/red]")
                self.console.print(f"[red]Raw response: {json_text}[/red]")
                # Fallback to ask_user
                return [SubTask(
                    type="ask_user",
                    question=f"I couldn't process your request due to a formatting issue. Could you rephrase: '{user_prompt}'?"
                )]
            
            # Validate it's a list
            if not isinstance(subtask_dicts, list):
                self.console.print(f"[red]Expected list, got {type(subtask_dicts)}[/red]")
                return [SubTask(
                    type="ask_user",
                    question=f"I couldn't process your request due to a formatting issue. Could you rephrase: '{user_prompt}'?"
                )]
            
            # Convert to SubTask objects
            subtasks = []
            for task_dict in subtask_dicts:
                # Validate required fields
                if "type" not in task_dict:
                    continue
                
                # Create SubTask with defaults
                subtask = SubTask(**task_dict)
                subtasks.append(subtask)
            
            return subtasks
            
        except Exception as e:
            self.console.print(f"[red]Task decomposition failed: {e}[/red]")
            # Fallback to ask_user
            return [SubTask(
                type="ask_user",
                question=f"I couldn't break down your request: '{user_prompt}'. Could you provide more specific guidance?"
            )]
    
    def modify_subtask(self, failed_task: SubTask, failure_detail: dict) -> SubTask:
        """Suggest a modified version of a failed subtask."""
        full_prompt = self._modify_prompt.format(
            subtask=failed_task.model_dump_json(),
            detail=json.dumps(failure_detail, indent=2)
        )
        
        try:
            response = self.client.models.generate_content(
                model="gemini-2.5-flash",
                contents=full_prompt
            )
            
            # Extract JSON from response
            json_text = response.text.strip()
            if json_text.startswith("```"):
                json_text = json_text.split("\n", 1)[1].rsplit("\n", 1)[0].strip()
            
            task_dict = json.loads(json_text)
            
            # Ensure type matches failed task
            task_dict["type"] = failed_task.type
            
            return SubTask(**task_dict)
            
        except Exception as e:
            self.console.print(f"[red]Subtask modification failed: {e}[/red]")
            # Return original task as fallback
            return failed_task
