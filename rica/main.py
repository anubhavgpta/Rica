"""Main CLI interface for Rica."""

import difflib
import glob
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
from .debugger import classify_error, generate_fix
from .executor import detect_server, run_command
from .llm import llm
from .models import BuildPlan
from .planner import create_plan
from .registry import get_language_config, LANGUAGE_REGISTRY
from .reviewer import review_codebase, fix_file
from .models import ReviewIssue, ReviewReport
from .db import save_review, get_reviews_for_path

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


@app.command()
def check(session_id: str) -> None:
    """Run compile/syntax check on a completed build."""
    print_banner()
    
    # Load build
    build = db.get_build_by_session(session_id)
    if not build or build["status"] != "completed":
        console.print("[red]Build not found or not completed. Run `rica build` first.[/red]")
        raise typer.Exit(1)
    
    # Load session to get language
    sessions = db.list_sessions()
    session = next((s for s in sessions if s["id"] == session_id), None)
    if not session:
        console.print(f"[red]Session not found: {session_id}[/red]")
        raise typer.Exit(1)
    
    language = session["language"].lower()
    
    # Get check command
    try:
        config = get_language_config(language)
        check_cmd = config.get("check_cmd")
    except ValueError:
        console.print(f"[yellow]No check command configured for {language}[/yellow]")
        raise typer.Exit(0)
    
    if not check_cmd:
        console.print(f"[yellow]No check command configured for {language}[/yellow]")
        raise typer.Exit(0)
    
    # Resolve {file} placeholder if needed
    workspace = Path(build["workspace"])
    if "{file}" in " ".join(check_cmd):
        extension = config.get("extension", "")
        pattern = f"*{extension}"
        files = list(workspace.rglob(pattern))
        if not files:
            console.print(f"[red]No {extension} files found in workspace[/red]")
            raise typer.Exit(1)
        check_cmd = [arg.replace("{file}", str(files[0])) for arg in check_cmd]
    
    # Run check command
    result = run_command(check_cmd, workspace, timeout=30, console=console)
    
    # Save execution
    db.save_execution(result, session_id)
    
    # Display output
    if result.stdout:
        console.print(Panel(result.stdout, title="stdout", border_style="dim"))
    if result.stderr:
        console.print(Panel(result.stderr, title="stderr", border_style="dim"))
    
    # Show result
    if result.exit_code == 0:
        console.print("[green]PASS[/green]")
    else:
        console.print("[red]FAIL[/red]")


@app.command()
def run(session_id: str, timeout: int = typer.Option(10, "--timeout")) -> None:
    """Execute the built project and interpret output with LLM."""
    print_banner()
    
    # Load build
    build = db.get_build_by_session(session_id)
    if not build or build["status"] != "completed":
        console.print("[red]Build not found or not completed. Run `rica build` first.[/red]")
        raise typer.Exit(1)
    
    # Load session to get language
    sessions = db.list_sessions()
    session = next((s for s in sessions if s["id"] == session_id), None)
    if not session:
        console.print(f"[red]Session not found: {session_id}[/red]")
        raise typer.Exit(1)
    
    language = session["language"].lower()
    
    # Get run command
    try:
        config = get_language_config(language)
        run_cmd = config.get("run_cmd")
    except ValueError:
        console.print(f"[red]No run command configured for {language}[/red]")
        raise typer.Exit(1)
    
    if not run_cmd:
        console.print(f"[red]No run command configured for {language}[/red]")
        raise typer.Exit(1)
    
    # Resolve {file} placeholder if needed
    workspace = Path(build["workspace"])
    if "{file}" in " ".join(run_cmd):
        extension = config.get("extension", "")
        pattern = f"*{extension}"
        files = list(workspace.rglob(pattern))
        if not files:
            console.print(f"[red]No {extension} files found in workspace[/red]")
            raise typer.Exit(1)
        run_cmd = [arg.replace("{file}", str(files[0])) for arg in run_cmd]
    
    # Detect server and set timeout
    is_server = detect_server(workspace, language)
    if is_server:
        effective_timeout = timeout
        console.print(f"[dim]Detected server process — running with {timeout}s timeout[/dim]")
    else:
        effective_timeout = min(timeout, 60)
    
    # Run command
    result = run_command(run_cmd, workspace, effective_timeout, console=console)
    
    # Save execution
    db.save_execution(result, session_id)
    
    # Display output
    if result.stdout:
        console.print(Panel(result.stdout, title="stdout", border_style="dim"))
    if result.stderr:
        console.print(Panel(result.stderr, title="stderr", border_style="dim"))
    
    # LLM interpretation
    try:
        # Load executor prompt
        prompt_path = Path(__file__).parent / "prompts" / "executor.txt"
        executor_prompt = prompt_path.read_text().strip()
        
        user_msg = f"Exit code: {result.exit_code}\nTimed out: {result.timed_out}\nStdout:\n{result.stdout}\nStderr:\n{result.stderr}"
        interpretation = llm.generate(system_prompt=executor_prompt, user_prompt=user_msg)
        
        console.print(Panel(
            interpretation,
            title="Execution Summary",
            border_style="dim"
        ))
    except Exception as e:
        console.print(f"[yellow]Could not generate interpretation: {e}[/yellow]")


@app.command()
def test(session_id: str) -> None:
    """Run the test suite for a completed build."""
    print_banner()
    
    # Load build
    build = db.get_build_by_session(session_id)
    if not build or build["status"] != "completed":
        console.print("[red]Build not found or not completed. Run `rica build` first.[/red]")
        raise typer.Exit(1)
    
    # Load session to get language
    sessions = db.list_sessions()
    session = next((s for s in sessions if s["id"] == session_id), None)
    if not session:
        console.print(f"[red]Session not found: {session_id}[/red]")
        raise typer.Exit(1)
    
    language = session["language"].lower()
    
    # Get test command
    try:
        config = get_language_config(language)
        test_cmd = config.get("test_cmd")
    except ValueError:
        console.print(f"[yellow]No test command configured for {language}[/yellow]")
        raise typer.Exit(0)
    
    if not test_cmd:
        console.print(f"[yellow]No test command configured for {language}[/yellow]")
        raise typer.Exit(0)
    
    # Resolve {file} placeholder if needed (unlikely for test commands)
    workspace = Path(build["workspace"])
    if "{file}" in " ".join(test_cmd):
        extension = config.get("extension", "")
        pattern = f"*{extension}"
        files = list(workspace.rglob(pattern))
        if not files:
            console.print(f"[red]No {extension} files found in workspace[/red]")
            raise typer.Exit(1)
        test_cmd = [arg.replace("{file}", str(files[0])) for arg in test_cmd]
    
    # Run test command (fixed 60s timeout)
    result = run_command(test_cmd, workspace, timeout=60, console=console)
    
    # Save execution
    db.save_execution(result, session_id)
    
    # Display output
    if result.stdout:
        console.print(Panel(result.stdout, title="stdout", border_style="dim"))
    if result.stderr:
        console.print(Panel(result.stderr, title="stderr", border_style="dim"))
    
    # LLM interpretation
    try:
        # Load executor prompt
        prompt_path = Path(__file__).parent / "prompts" / "executor.txt"
        executor_prompt = prompt_path.read_text().strip()
        
        user_msg = f"Exit code: {result.exit_code}\nTimed out: {result.timed_out}\nStdout:\n{result.stdout}\nStderr:\n{result.stderr}"
        interpretation = llm.generate(system_prompt=executor_prompt, user_prompt=user_msg)
        
        console.print(Panel(
            interpretation,
            title="Execution Summary",
            border_style="dim"
        ))
    except Exception as e:
        console.print(f"[yellow]Could not generate interpretation: {e}[/yellow]")


@app.command()
def debug(
    session_id: str = typer.Argument(..., help="Session ID to debug"),
    max_iter: int = typer.Option(5, "--max-iter", help="Maximum debug iterations"),
    timeout: int = typer.Option(30, "--timeout", help="Timeout per run in seconds"),
) -> None:
    """Debug a session using autonomous fix generation."""
    print_banner()
    
    # Load plan
    plan_file = PLANS_DIR / f"{session_id}.json"
    if not plan_file.exists():
        console.print(f"[red]Plan not found: {session_id}[/red]")
        raise typer.Exit(1)
    
    try:
        with open(plan_file, "r", encoding="utf-8") as f:
            plan_data = json.load(f)
        plan = BuildPlan.model_validate(plan_data)
    except Exception as e:
        console.print(f"[red]Error loading plan: {e}[/red]")
        raise typer.Exit(1)
    
    # Get workspace
    build = db.get_build_by_session(session_id)
    if not build:
        console.print(f"[red]No completed build found for session {session_id}[/red]")
        raise typer.Exit(1)
    
    workspace = Path(build["workspace"])
    
    # Check for resumability
    debug_sessions = db.get_debug_sessions_for_session(session_id)
    in_progress_sessions = [s for s in debug_sessions if s["final_status"] == "in_progress"]
    
    if in_progress_sessions:
        debug_session_id = in_progress_sessions[0]["id"]
        start_iteration = len(db.get_debug_iterations_for_session(debug_session_id))
        console.print(f"[dim]Resuming debug session from iteration {start_iteration}[/dim]")
    else:
        debug_session_id = str(uuid.uuid4())
        started_at = datetime.utcnow().isoformat() + "Z"
        db.insert_debug_session(debug_session_id, session_id, started_at)
        start_iteration = 0
    
    # Get language config
    try:
        config = get_language_config(plan.language.lower())
        check_cmd = config.get("check_cmd")
        run_cmd = config.get("run_cmd")
    except ValueError:
        console.print(f"[red]Unsupported language: {plan.language}[/red]")
        raise typer.Exit(1)
    
    if not check_cmd:
        console.print(f"[yellow]No check command configured for {plan.language}[/yellow]")
        raise typer.Exit(0)
    
    if not run_cmd:
        console.print(f"[yellow]No run command configured for {plan.language}[/yellow]")
        raise typer.Exit(0)
    
    # Run initial check
    console.print("[dim]Running initial check...[/dim]")
    if "{file}" in " ".join(check_cmd):
        extension = config.get("extension", "")
        pattern = f"*{extension}"
        files = list(workspace.rglob(pattern))
        if not files:
            console.print(f"[red]No {extension} files found in workspace[/red]")
            raise typer.Exit(1)
        initial_check_cmd = [arg.replace("{file}", str(files[0])) for arg in check_cmd]
    else:
        initial_check_cmd = check_cmd
    
    check_result = run_command(initial_check_cmd, workspace, timeout=timeout, console=console)
    
    # Resolve run command (needed for both initial run and debug loop)
    if "{file}" in " ".join(run_cmd):
        extension = config.get("extension", "")
        pattern = f"*{extension}"
        files = list(workspace.rglob(pattern))
        if not files:
            console.print(f"[red]No {extension} files found in workspace[/red]")
            raise typer.Exit(1)
        resolved_run_cmd = [arg.replace("{file}", str(files[0])) for arg in run_cmd]
    else:
        resolved_run_cmd = run_cmd
    
    # Detect server and set timeout
    is_server = detect_server(workspace, plan.language.lower())
    effective_timeout = min(timeout, 60) if not is_server else timeout
    
    # If check passes, try running
    if check_result.exit_code == 0:
        console.print("[dim]Check passed, running project...[/dim]")
        
        run_result = run_command(resolved_run_cmd, workspace, effective_timeout, console=console)
        
        if run_result.exit_code == 0:
            console.print("[green]Project runs successfully. No debug needed.[/green]")
            completed_at = datetime.utcnow().isoformat() + "Z"
            db.complete_debug_session(debug_session_id, "success", completed_at)
            return
    
    # Debug loop
    for iteration in range(start_iteration, max_iter):
        console.print(f"[dim]--- Iteration {iteration + 1} / {max_iter} ---[/dim]")
        
        # Run check
        check_result = run_command(initial_check_cmd, workspace, timeout=timeout, console=console)
        
        # Classify error
        error = classify_error(
            check_result.stdout, 
            check_result.stderr, 
            plan.language, 
            check_result.timed_out
        )
        
        # Get implicated files
        implicated_files = error.implicated_files
        if not implicated_files and check_result.stderr:
            # Try to extract from run result if check doesn't have files
            run_error = classify_error(
                check_result.stdout,
                check_result.stderr,
                plan.language,
                check_result.timed_out
            )
            implicated_files = run_error.implicated_files
        
        if not implicated_files:
            console.print("[yellow]Warning: No implicated files found, using all source files[/yellow]")
            extension = config.get("extension", "")
            if extension:
                implicated_files = [str(p.relative_to(workspace)) for p in workspace.rglob(f"*{extension}")]
        
        # Fix each implicated file
        for file_name in implicated_files:
            file_path = workspace / file_name
            if not file_path.exists():
                console.print(f"[yellow]Warning: File not found: {file_name}[/yellow]")
                continue
            
            console.print(f"[dim]Fixing: {file_name}[/dim]")
            fixed_content = generate_fix(error, file_path, workspace, plan, console)
            
            # Write fixed content
            try:
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(fixed_content)
            except Exception as e:
                console.print(f"[red]Error writing file {file_name}: {e}[/red]")
        
        # Re-run check
        recheck_result = run_command(initial_check_cmd, workspace, timeout=timeout, console=console)
        check_passed = recheck_result.exit_code == 0
        
        # Re-run run
        run_result = run_command(resolved_run_cmd, workspace, effective_timeout, console=console)
        
        # Persist iteration
        iteration_id = str(uuid.uuid4())
        fixed_at = datetime.utcnow().isoformat() + "Z"
        db.insert_debug_iteration(
            id=iteration_id,
            debug_session_id=debug_session_id,
            iteration=iteration,
            error_class=error.category,
            implicated_files=json.dumps(error.implicated_files),
            check_passed=int(check_passed),
            run_exit_code=run_result.exit_code,
            fixed_at=fixed_at,
        )
        
        # Check if successful
        if run_result.exit_code == 0:
            completed_at = datetime.utcnow().isoformat() + "Z"
            db.complete_debug_session(debug_session_id, "success", completed_at)
            
            console.print(Panel(
                "[green]Debug successful![/green]",
                title="Success",
                border_style="green"
            ))
            break
    
    # If loop exhausted
    else:
        completed_at = datetime.utcnow().isoformat() + "Z"
        db.complete_debug_session(debug_session_id, "max_iterations_reached", completed_at)
        console.print(f"[yellow]Max iterations reached ({max_iter}). Review errors manually.[/yellow]")
    
    # Show summary table
    console.print("─" * 80, style="dim")
    console.print("Debug Summary", style="bold")
    console.print("─" * 80, style="dim")
    
    iterations = db.get_debug_iterations_for_session(debug_session_id)
    if iterations:
        summary_table = Table()
        summary_table.add_column("Iteration", style="cyan")
        summary_table.add_column("Error Class", style="yellow")
        summary_table.add_column("Files Fixed", style="white")
        summary_table.add_column("Check", style="green")
        summary_table.add_column("Run Result", style="blue")
        
        for iteration_data in iterations:
            files = json.loads(iteration_data["implicated_files"]) if iteration_data["implicated_files"] else []
            files_text = f"{len(files)} files" if files else "None"
            check_text = "[green]PASS[/green]" if iteration_data["check_passed"] else "[red]FAIL[/red]"
            run_text = "[green]SUCCESS[/green]" if iteration_data["run_exit_code"] == 0 else f"[red]FAIL({iteration_data['run_exit_code']})[/red]"
            
            summary_table.add_row(
                str(iteration_data["iteration"] + 1),
                iteration_data["error_class"] or "unknown",
                files_text,
                check_text,
                run_text
            )
        
        console.print(summary_table)


@app.command()
def debug_history(
    session_id: str = typer.Argument(..., help="Session ID"),
) -> None:
    """Show debug history for a session."""
    print_banner()
    
    debug_sessions = db.get_debug_sessions_for_session(session_id)
    
    if not debug_sessions:
        console.print(f"[yellow]No debug sessions found for {session_id}[/yellow]")
        return
    
    console.print("─" * 80, style="dim")
    console.print("Debug Sessions", style="bold")
    console.print("─" * 80, style="dim")
    
    # Debug sessions table
    sessions_table = Table()
    sessions_table.add_column("Debug Session ID", style="cyan")
    sessions_table.add_column("Started At", style="white")
    sessions_table.add_column("Completed At", style="white")
    sessions_table.add_column("Status", style="yellow")
    sessions_table.add_column("Iterations", style="blue")
    
    for session in debug_sessions:
        session_id_short = session["id"][:8]
        started = session["started_at"][:19].replace("T", " ")
        completed = session["completed_at"][:19].replace("T", " ") if session["completed_at"] else "N/A"
        status = session["final_status"]
        iterations = str(session["iterations"])
        
        sessions_table.add_row(session_id_short, started, completed, status, iterations)
    
    console.print(sessions_table)
    
    # Debug iterations for each session
    for session in debug_sessions:
        console.print()
        console.print(f"[dim]Debug Session {session['id'][:8]} - Iterations[/dim]")
        console.print("─" * 80, style="dim")
        
        iterations = db.get_debug_iterations_for_session(session["id"])
        if iterations:
            iterations_table = Table()
            iterations_table.add_column("Iter #", style="cyan")
            iterations_table.add_column("Error Class", style="yellow")
            iterations_table.add_column("Files Fixed", style="white")
            iterations_table.add_column("Check", style="green")
            iterations_table.add_column("Run Exit Code", style="blue")
            iterations_table.add_column("Fixed At", style="dim")
            
            for iteration in iterations:
                files = json.loads(iteration["implicated_files"]) if iteration["implicated_files"] else []
                files_text = f"{len(files)} files" if files else "None"
                check_text = "[green]PASS[/green]" if iteration["check_passed"] else "[red]FAIL[/red]"
                run_exit = str(iteration["run_exit_code"]) if iteration["run_exit_code"] is not None else "N/A"
                fixed_at = iteration["fixed_at"][:19].replace("T", " ") if iteration["fixed_at"] else "N/A"
                
                iterations_table.add_row(
                    str(iteration["iteration"] + 1),
                    iteration["error_class"] or "unknown",
                    files_text,
                    check_text,
                    run_exit,
                    fixed_at
                )
            
            console.print(iterations_table)
        else:
            console.print("[dim]No iterations recorded[/dim]")


def _display_review_report(report: ReviewReport, console: Console) -> None:
    """Render a ReviewReport to the console using Rich."""
    console.print(
        Panel(
            f"[dim]Language:[/dim] {report.language}   "
            f"[dim]Files reviewed:[/dim] {report.files_reviewed}   "
            f"[dim]Issues found:[/dim] {len(report.issues)}",
            title=f"[dim]Review: {report.path}[/dim]",
            border_style="dim",
        )
    )

    console.print(
        Panel(report.summary, title="[dim]Summary[/dim]", border_style="dim")
    )

    if not report.issues:
        console.print("[dim]No issues found.[/dim]")
        return

    table = Table(border_style="dim", header_style="dim")
    table.add_column("File")
    table.add_column("Line", justify="right", width=6)
    table.add_column("Severity", width=9)
    table.add_column("Category", width=16)
    table.add_column("Description")

    severity_colors = {"error": "red", "warning": "yellow", "info": "dim"}

    for issue in report.issues:
        color = severity_colors.get(issue.severity, "dim")
        table.add_row(
            issue.file,
            str(issue.line) if issue.line is not None else "-",
            f"[{color}]{issue.severity}[/{color}]",
            issue.category,
            issue.description,
        )

    console.print(table)


@app.command()
def review(
    path: str = typer.Argument(..., help="Path to the codebase directory to review"),
    lang: str | None = typer.Option(None, "--lang", help="Language override"),
) -> None:
    """Analyze an existing codebase for issues."""
    console = Console()
    print_banner()

    target = Path(path).resolve()
    if not target.is_dir():
        console.print(Panel("[red]Path is not a directory or does not exist.[/red]", border_style="dim", title="[red]Error[/red]"))
        raise typer.Exit(1)

    report = review_codebase(target, lang, console)

    _display_review_report(report, console)

    # Persist
    review_id = uuid.uuid4().hex[:8]
    error_count = sum(1 for i in report.issues if i.severity == "error")
    save_review(
        id=review_id,
        path=str(target),
        language=report.language,
        files_reviewed=report.files_reviewed,
        issue_count=len(report.issues),
        error_count=error_count,
        report_json=report.model_dump_json(),
        reviewed_at=datetime.utcnow().isoformat() + "Z",
    )
    console.print(f"[dim]Review saved. ID: {review_id}[/dim]")

    if report.issues:
        console.print(f"\n[dim]Run `rica fix {path}` to apply fixes for error-severity issues.[/dim]")


@app.command()
def fix(
    path: str = typer.Argument(..., help="Path to the codebase directory to fix"),
    lang: str | None = typer.Option(None, "--lang", help="Language override"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show diffs without writing"),
) -> None:
    """Apply fixes for error-severity issues in a codebase."""
    console = Console()
    print_banner()

    target = Path(path).resolve()
    if not target.is_dir():
        console.print(Panel("[red]Path is not a directory or does not exist.[/red]", border_style="dim", title="[red]Error[/red]"))
        raise typer.Exit(1)

    console.print("[dim]Running review...[/dim]")
    report = review_codebase(target, lang, console)

    error_issues = [i for i in report.issues if i.severity == "error"]
    if not error_issues:
        console.print("[dim]No errors to fix.[/dim]")
        raise typer.Exit(0)

    if dry_run:
        console.print(f"[dim]Dry run — {len(error_issues)} error(s) would be fixed.[/dim]")

    # Group by file
    by_file: dict[str, list[ReviewIssue]] = {}
    for issue in error_issues:
        by_file.setdefault(issue.file, []).append(issue)

    # Load all source files for cross-file context
    from rica.reviewer import _collect_files, _load_files
    all_source = _load_files(target, _collect_files(target), console)

    fixed_count = 0
    for rel_file, issues in by_file.items():
        file_path = target / rel_file
        if not file_path.is_file():
            console.print(f"[dim]Skipping {rel_file} — not found on disk.[/dim]")
            continue

        console.print(f"[dim]Fixing {rel_file} ({len(issues)} issue(s))...[/dim]")
        original = file_path.read_text(encoding="utf-8", errors="replace")

        fixed_content = fix_file(file_path, issues, all_source, report.language, console)

        if dry_run:
            diff = list(
                difflib.unified_diff(
                    original.splitlines(keepends=True),
                    fixed_content.splitlines(keepends=True),
                    fromfile=f"a/{rel_file}",
                    tofile=f"b/{rel_file}",
                )
            )
            diff_text = "".join(diff) if diff else "(no changes)"
            console.print(Panel(diff_text, title=f"[dim]Diff: {rel_file}[/dim]", border_style="dim"))
        else:
            file_path.write_text(fixed_content, encoding="utf-8")
            fixed_count += 1

    if dry_run:
        console.print(f"[dim]Dry run complete. {len(by_file)} file(s) would be modified.[/dim]")
        raise typer.Exit(0)

    # Re-review
    console.print("[dim]Re-running review after fixes...[/dim]")
    updated_report = review_codebase(target, report.language, console)
    remaining = len(updated_report.issues)
    console.print(f"\n[dim]Fixed {fixed_count} file(s). {remaining} issue(s) remaining.[/dim]")

    # Persist updated review
    review_id = uuid.uuid4().hex[:8]
    error_count = sum(1 for i in updated_report.issues if i.severity == "error")
    save_review(
        id=review_id,
        path=str(target),
        language=updated_report.language,
        files_reviewed=updated_report.files_reviewed,
        issue_count=remaining,
        error_count=error_count,
        report_json=updated_report.model_dump_json(),
        reviewed_at=datetime.utcnow().isoformat() + "Z",
    )

    _display_review_report(updated_report, console)


@app.command()
def reviews(
    path: str | None = typer.Option(None, "--path", help="Filter by directory path"),
) -> None:
    """List past review sessions."""
    console = Console()
    print_banner()

    rows = get_reviews_for_path(path)
    if not rows:
        console.print("[dim]No reviews found.[/dim]")
        raise typer.Exit(0)

    table = Table(border_style="dim", header_style="dim")
    table.add_column("ID", style="dim", width=10)
    table.add_column("Path")
    table.add_column("Language", width=12)
    table.add_column("Files", justify="right", width=7)
    table.add_column("Issues", justify="right", width=7)
    table.add_column("Errors", justify="right", width=7)
    table.add_column("Reviewed At")

    for row in rows:
        truncated_path = row["path"]
        if len(truncated_path) > 48:
            truncated_path = "..." + truncated_path[-45:]
        table.add_row(
            row["id"][:8],
            truncated_path,
            row["language"],
            str(row["files_reviewed"]),
            str(row["issue_count"]),
            str(row["error_count"]),
            row["reviewed_at"],
        )

    console.print(table)


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
