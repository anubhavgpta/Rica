"""Core planning logic for Rica."""

import json
import uuid
from pathlib import Path

from rich.console import Console
from rich.progress import SpinnerColumn, TextColumn
from rich.progress import Progress as RichProgress

from .config import PLANS_DIR
from .db import db
from .llm import llm
from .models import BuildPlan

console = Console()


def create_plan(goal: str, session_id: str) -> BuildPlan:
    """Create a build plan for the given goal."""
    # Load system prompt
    system_prompt_path = Path(__file__).parent / "prompts" / "planner.txt"
    with open(system_prompt_path, "r", encoding="utf-8") as f:
        system_prompt = f.read()
    
    # Create user prompt
    user_prompt = f"Create a build plan for this goal: {goal}"
    
    # Show spinner while calling LLM
    with RichProgress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Thinking about your goal...", total=None)
        try:
            response = llm.generate(system_prompt, user_prompt)
        except Exception as e:
            console.print(f"[red]Error generating plan: {e}[/red]")
            raise
        finally:
            progress.remove_task(task)
    
    # Clean response (remove any accidental markdown)
    response = response.strip()
    if response.startswith("```json"):
        response = response[7:]
    if response.endswith("```"):
        response = response[:-3]
    response = response.strip()
    
    # Parse JSON
    try:
        plan_data = json.loads(response)
        plan_data["session_id"] = session_id  # Ensure session_id is set
        plan = BuildPlan.model_validate(plan_data)
    except json.JSONDecodeError as e:
        console.print(f"[red]Failed to parse plan JSON: {e}[/red]")
        console.print(f"[yellow]Raw LLM response:[/yellow]")
        console.print(response)
        raise
    except Exception as e:
        console.print(f"[red]Failed to validate plan: {e}[/red]")
        console.print(f"[yellow]Parsed JSON:[/yellow]")
        console.print(json.dumps(plan_data, indent=2))
        raise
    
    # Save plan to file
    plan_file = PLANS_DIR / f"{session_id}.json"
    with open(plan_file, "w", encoding="utf-8") as f:
        f.write(plan.model_dump_json(indent=2))
    
    # Save to database
    plan_id = str(uuid.uuid4())
    db.save_plan(plan_id, session_id, plan.model_dump_json())
    
    return plan
