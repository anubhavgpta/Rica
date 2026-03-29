"""Main CLI interface for Rica."""

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.tree import Tree

from .config import PLANS_DIR, RICA_HOME
from .codegen import build_project
from .db import db
from .models import BuildPlan
from .planner import create_plan

app = typer.Typer(help="Rica - Language-Agnostic Autonomous Coding Agent")
console = Console()

PACKAGE_MANAGER_HINTS: dict[str, str] = {
    "go":         "go mod tidy && go build ./...",
    "rust":       "cargo build",
    "javascript": "npm install && npm run build",
    "typescript": "npm install && npm run build",
    "python":     "pip install -r requirements.txt",
    "ruby":       "bundle install",
    "php":        "composer install",
    "elixir":     "mix deps.get && mix compile",
    "dart":       "flutter pub get",
}


def print_banner() -> None:
    """Print Rica banner."""
    banner = r"""                   _..._               
                .-'_..._''.            
        .--.  .' .'      '.\           
        |__| / .'                      
.-,.--. .--.. '                        
|  .-. ||  || |                 __     
| |  | ||  || |              .:--.'.   
| |  | ||  |. '             / |   \ |  
| |  '- |  | \ '.          .`" __ | |  
| |     |__|  '. `._____.-'/ .'.''| |  
| |             `-.______ / / /   | |_ 
|_|                      `  \\._,\ '/ 
                             `--'  """
    
    console.print(banner, style="bold white")
    console.print("Language-Agnostic Coding Agent  v0.1.0", style="dim")
    console.print("─" * 80, style="dim")


def display_plan(plan: BuildPlan) -> None:
    """Display a plan beautifully using Rich."""
    # Main panel with goal and language
    info_text = f"Language: [bold green]{plan.language}[/bold green]\n"
    info_text += f"Files: [bold blue]{plan.estimated_files}[/bold blue]\n"
    info_text += f"Session: [bold cyan]{plan.session_id}[/bold cyan]"
    
    console.print(Panel(
        f"[bold]{plan.goal}[/bold]\n\n{info_text}",
        title="Build Plan",
        border_style="dim"
    ))
    
    # Rationale
    if plan.rationale:
        console.print(Panel(
            plan.rationale,
            title="Rationale",
            border_style="dim"
        ))
    
    # Milestones table
    if plan.milestones:
        console.print("─" * 80, style="dim")
        console.print("Milestones", style="bold")
        console.print("─" * 80, style="dim")
        
        table = Table(show_header=True, header_style="bold blue")
        table.add_column("Milestone", style="cyan")
        table.add_column("Files", justify="right", style="blue")
        table.add_column("Description", style="white")
        
        for milestone in plan.milestones:
            table.add_row(
                milestone.name,
                str(len(milestone.files)),
                milestone.description[:80] + "..." if len(milestone.description) > 80 else milestone.description
            )
        
        console.print(table)
    
    # File tree
    if plan.milestones:
        console.print("─" * 80, style="dim")
        console.print("Project Structure", style="bold")
        console.print("─" * 80, style="dim")
        
        tree = Tree("Project Structure")
        for milestone in plan.milestones:
            milestone_node = tree.add(f"{milestone.name}")
            for file_plan in milestone.files:
                file_node = milestone_node.add(f"{file_plan.path}")
                file_node.add(f"{file_plan.description}")
                if file_plan.dependencies:
                    file_node.add(f"Deps: {', '.join(file_plan.dependencies)}")
        
        console.print(tree)
    
    # Install commands
    if plan.install_commands:
        console.print(Panel(
            "\n".join(f"$ {cmd}" for cmd in plan.install_commands),
            title="Install Commands",
            border_style="dim"
        ))
    
    # Notes
    if plan.notes:
        console.print(Panel(
            plan.notes,
            title="Notes",
            border_style="dim"
        ))


@app.command()
def plan(
    goal: str = typer.Argument(..., help="Your coding goal"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Auto-approve the plan"),
    lang: Optional[str] = typer.Option(None, "--lang", "-l", help="Preferred language"),
) -> None:
    """Create a new build plan."""
    print_banner()
    
    # Generate session ID
    session_id = str(uuid.uuid4())[:8]
    
    try:
        # Create the plan
        plan_obj = create_plan(goal, session_id)
        
        # Override language if specified
        if lang:
            plan_obj.language = lang
        
        # Create session in database
        db.create_session(session_id, goal, plan_obj.language)
        
        # Display the plan
        display_plan(plan_obj)
        
        # Handle approval
        if yes:
            console.print("[green]Plan auto-approved (--yes)[/green]")
            db.update_plan_approval(session_id, True)
            console.print(f"[green]Saved:[/green] {PLANS_DIR / f'{session_id}.json'}")
        else:
            response = typer.confirm("Proceed with this plan?", default=False)
            if response:
                console.print("[green]Plan approved[/green]")
                db.update_plan_approval(session_id, True)
                console.print(f"[green]Saved:[/green] {PLANS_DIR / f'{session_id}.json'}")
            else:
                console.print("[dim]Plan discarded[/dim]")
                return
        
        console.print(f"Session: {session_id}")
        
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def plans() -> None:
    """List all saved plans."""
    print_banner()
    
    sessions = db.list_sessions()
    
    if not sessions:
        console.print("No saved plans found.")
        return
    
    table = Table(title="Saved Plans")
    table.add_column("Session ID", style="cyan")
    table.add_column("Goal", style="white")
    table.add_column("Language", style="green")
    table.add_column("Status", style="yellow")
    table.add_column("Created", style="blue")
    
    for session in sessions:
        goal = session["goal"][:60] + "..." if len(session["goal"]) > 60 else session["goal"]
        status = "[green]Approved[/green]" if session["approved"] else "[dim]Pending[/dim]"
        created = session["created_at"][:19].replace("T", " ")
        
        table.add_row(
            session["id"],
            goal,
            session["language"],
            status,
            created
        )
    
    console.print(table)


@app.command()
def show(session_id: str) -> None:
    """Show details of a saved plan."""
    print_banner()
    
    # Load plan from file
    plan_file = PLANS_DIR / f"{session_id}.json"
    if not plan_file.exists():
        console.print(f"[red]Plan not found: {session_id}[/red]")
        raise typer.Exit(1)
    
    try:
        with open(plan_file, "r", encoding="utf-8") as f:
            plan_data = json.load(f)
        plan = BuildPlan.model_validate(plan_data)
        display_plan(plan)
    except Exception as e:
        console.print(f"[red]Error loading plan: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def build(
    session_id: str = typer.Argument(..., help="Session ID to build"),
    workspace: Optional[Path] = typer.Option(None, "--workspace", help="Workspace directory")
) -> None:
    """Build a project from an approved plan."""
    print_banner()
    
    # Load plan from DB
    plan_data = db.get_plan_for_session(session_id)
    if not plan_data:
        console.print(f"[red]No plan found for session: {session_id}[/red]")
        raise typer.Exit(1)
    
    if plan_data["approved"] != 1:
        console.print("[red]Plan is not approved. Run `rica plan` and approve it first.[/red]")
        raise typer.Exit(1)
    
    # Parse plan
    try:
        plan = BuildPlan.model_validate_json(plan_data["plan_json"])
    except Exception as e:
        console.print(f"[red]Error parsing plan: {e}[/red]")
        raise typer.Exit(1)
    
    # Resolve workspace
    if workspace:
        workspace_path = workspace
    else:
        workspace_path = RICA_HOME / "workspaces" / session_id
    
    # Create workspace directory
    workspace_path.mkdir(parents=True, exist_ok=True)
    
    # Insert build record
    build_id = str(uuid.uuid4())
    started_at = datetime.utcnow().isoformat() + "Z"
    db.insert_build(build_id, session_id, str(workspace_path), started_at)
    
    # Show build starting panel
    console.print(Panel(
        f"Building: [bold]{plan.goal}[/bold]\nWorkspace: {workspace_path}",
        title="Build starting",
        border_style="dim"
    ))
    
    try:
        # Build the project
        generated_files = build_project(plan, workspace_path, console)
        
        # Show summary table
        console.print("─" * 80, style="dim")
        console.print("Build Summary", style="bold")
        console.print("─" * 80, style="dim")
        
        summary_table = Table()
        summary_table.add_column("File", style="cyan")
        summary_table.add_column("Language", style="green")
        summary_table.add_column("Size (bytes)", justify="right", style="blue")
        
        for gen_file in generated_files:
            file_path = workspace_path / gen_file.path
            size_bytes = file_path.stat().st_size if file_path.exists() else 0
            summary_table.add_row(gen_file.path, gen_file.language, str(size_bytes))
        
        console.print(summary_table)
        
        # Show package manager hint if available
        hint = PACKAGE_MANAGER_HINTS.get(plan.language.lower())
        if hint:
            console.print()
            console.print(
                f"  [dim]Next step: cd {workspace_path} && {hint}[/dim]"
            )
        
        # Complete build
        completed_at = datetime.utcnow().isoformat() + "Z"
        db.complete_build(build_id, completed_at)
        
        console.print(f"[green]Build complete. Workspace: {workspace_path}[/green]")
        
    except Exception as e:
        console.print(f"[red]Build failed: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def builds() -> None:
    """List all build sessions."""
    print_banner()
    
    builds = db.get_all_builds()
    
    if not builds:
        console.print("No builds yet.")
        return
    
    table = Table(title="Build Sessions")
    table.add_column("ID", style="cyan")
    table.add_column("Session", style="green")
    table.add_column("Workspace", style="white")
    table.add_column("Status", style="yellow")
    table.add_column("Started", style="blue")
    table.add_column("Completed", style="blue")
    
    for build in builds:
        build_id = build["id"][:8]  # First 8 chars
        session_id = build["session_id"][:8]  # First 8 chars
        workspace = Path(build["workspace"]).name  # Just the folder name
        status = "[green]completed[/green]" if build["status"] == "completed" else "[yellow]in_progress[/yellow]"
        started = build["started_at"][:19].replace("T", " ")
        completed = build["completed_at"][:19].replace("T", " ") if build["completed_at"] else "N/A"
        
        table.add_row(build_id, session_id, workspace, status, started, completed)
    
    console.print(table)


@app.command()
def workspace(session_id: str) -> None:
    """Get the workspace path for a session."""
    build = db.get_build_by_session(session_id)
    
    if not build:
        console.print(f"[red]No build found for session {session_id}[/red]")
        raise typer.Exit(1)
    
    # Print just the workspace path (no markup) for shell scripting
    print(build["workspace"])


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    version: bool = typer.Option(False, "--version", "-v", help="Show Rica version")
) -> None:
    """Rica - Language-Agnostic Autonomous Coding Agent."""
    if version or ctx.invoked_subcommand is None:
        console.print("Rica v0.1.0 — Language-Agnostic Coding Agent")
        raise typer.Exit()


if __name__ == "__main__":
    app()
