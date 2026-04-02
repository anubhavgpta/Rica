"""Interactive terminal dashboard for Rica sessions."""

import re
import subprocess
import sys
import threading
import time
from typing import Optional

from prompt_toolkit import prompt
from prompt_toolkit.formatted_text import HTML
from rich.box import SIMPLE
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from . import db


def _langs(session) -> str:
    """Helper to handle both single languages and language lists."""
    # Try to get languages from plan_json first
    try:
        plan_data = db.db.get_plan_for_session(session["id"])
        if plan_data:
            import json
            plan = json.loads(plan_data["plan_json"])
            if "languages" in plan and plan["languages"]:
                result = " / ".join(plan["languages"])
                return result
    except Exception as e:
        pass
    
    # Fall back to the language field
    language_field = session["language"]
    
    if isinstance(language_field, list):
        return " / ".join(language_field)
    elif isinstance(language_field, str):
        # Check if it looks like a JSON-encoded list
        if language_field.startswith('[') and language_field.endswith(']'):
            try:
                import json
                lang_list = json.loads(language_field)
                if isinstance(lang_list, list):
                    return " / ".join(lang_list)
            except:
                pass
        return language_field
    else:
        return str(language_field)


def is_session_id(text: str) -> bool:
    """Returns True if text looks like a Rica session ID — alphanumeric, 6–12 characters, no spaces."""
    return bool(re.match(r'^[a-zA-Z0-9]{6,12}$', text))


def build_session_table(limit: int = 5) -> Table:
    """Build a Rich table with session information (limited to latest sessions)."""
    table = Table(style="dim", show_header=True, header_style="dim", box=SIMPLE, title=f"Latest {limit} Sessions")
    table.add_column("ID", style="cyan", max_width=36)
    table.add_column("Goal", style="white", no_wrap=True, max_width=38)
    table.add_column("Lang", style="green", max_width=10)
    table.add_column("Status", style="yellow", max_width=12)
    table.add_column("Build", style="blue", max_width=12)
    table.add_column("Debug", style="magenta", max_width=8)
    table.add_column("Tests", style="cyan", max_width=6)
    table.add_column("Created", style="dim", max_width=16, no_wrap=True)
    
    sessions = db.get_sessions()
    
    # Limit to latest sessions
    latest_sessions = sessions[:limit]
    
    for session in latest_sessions:
        session_id = session["id"]  # Show full ID
        goal = session["goal"][:38] + "..." if len(session["goal"]) > 38 else session["goal"]
        language = session["language"]
        status = session["status"]
        
        # Status color
        if status == "complete":
            status_style = "[green]complete[/green]"
        elif status == "failed":
            status_style = "[red]failed[/red]"
        elif status == "in_progress":
            status_style = "[yellow]in_progress[/yellow]"
        else:
            status_style = f"[dim]{status}[/dim]"
        
        # Build status
        build = db.get_latest_build(session_id)
        if build:
            build_status = build["status"]
            if build_status == "completed":
                build_style = "[green]completed[/green]"
            elif build_status == "failed":
                build_style = "[red]failed[/red]"
            else:
                build_style = f"[yellow]{build_status}[/yellow]"
        else:
            build_style = "[dim]—[/dim]"
        
        # Debug status
        debug = db.get_latest_debug(session_id)
        if debug:
            debug_status = debug["final_status"]
            if debug_status == "success":
                debug_style = "[green]success[/green]"
            elif debug_status == "failed":
                debug_style = "[red]failed[/red]"
            else:
                debug_style = f"[yellow]{debug_status}[/yellow]"
        else:
            debug_style = "[dim]—[/dim]"
        
        # Tests
        test_gen = db.get_latest_test_gen(session_id)
        if test_gen:
            tests_style = f"[cyan]{test_gen['tests_generated']}[/cyan]"
        else:
            tests_style = "[dim]—[/dim]"
        
        # Created timestamp
        created = session["created_at"].replace("T", " ")[:16]  # Format as YYYY-MM-DD HH:MM
        
        table.add_row(
            session_id,  # Full ID
            goal,
            _langs(session),
            status_style,
            build_style,
            debug_style,
            tests_style,
            f"[dim]{created}[/dim]"
        )
    
    return table


def build_detail_panel(session_id: str) -> Panel:
    """Build a Rich panel with detailed session information."""
    # Get session data
    sessions = db.get_sessions()
    session = next((s for s in sessions if s["id"] == session_id), None)
    
    if not session:
        return Panel(
            "[red]Session not found[/red]",
            title=f"session {session_id[:8]}",
            border_style="dim"
        )
    
    # Get related data
    build = db.get_latest_build(session_id)
    debug = db.get_latest_debug(session_id)
    review = db.get_latest_review(session_id)
    test_gen = db.get_latest_test_gen(session_id)
    executions = db.get_executions(session_id)
    
    # Build content
    content_lines = []
    
    # Goal and basic info
    content_lines.append(f"[bold]Goal:[/bold] {session['goal']}")
    content_lines.append(f"[bold]Language:[/bold] {_langs(session)}")
    content_lines.append(f"[bold]Status:[/bold] {session['status']}")
    content_lines.append("")
    
    # Build info
    if build:
        workspace_path = build["workspace"]
        build_status = build["status"]
        status_color = "green" if build_status == "completed" else "yellow" if build_status == "in_progress" else "red"
        content_lines.append(f"[bold]Build:[/bold] {workspace_path} [{status_color}]{build_status}[/{status_color}]")
    else:
        content_lines.append("[bold]Build:[/bold] No build on record")
    content_lines.append("")
    
    # Debug info
    if debug:
        iterations = debug["iterations"] or 0
        final_status = debug["final_status"]
        status_color = "green" if final_status == "success" else "red" if final_status == "failed" else "yellow"
        content_lines.append(f"[bold]Debug:[/bold] {iterations} iterations, [{status_color}]{final_status}[/{status_color}]")
    else:
        content_lines.append("[bold]Debug:[/bold] No debug session on record")
    content_lines.append("")
    
    # Review info
    if review:
        issue_count = review["issue_count"]
        error_count = review["error_count"]
        content_lines.append(f"[bold]Review:[/bold] {issue_count} issues, {error_count} errors")
    else:
        content_lines.append("[bold]Review:[/bold] No review on record")
    content_lines.append("")
    
    # Test generation info
    if test_gen:
        tests_generated = test_gen["tests_generated"]
        content_lines.append(f"[bold]Tests:[/bold] {tests_generated} generated")
    else:
        content_lines.append("[bold]Tests:[/bold] No test generation on record")
    content_lines.append("")
    
    # Last stdout
    if executions:
        latest_execution = executions[0]  # Most recent
        stdout = latest_execution.get("stdout", "")
        if stdout:
            stdout_lines = stdout.strip().split('\n')
            # Get last 8 lines
            last_lines = stdout_lines[-8:] if len(stdout_lines) > 8 else stdout_lines
            content_lines.append("[bold]Last stdout (last 8 lines):[/bold]")
            for line in last_lines:
                content_lines.append(f"[dim]{line}[/dim]")
        else:
            content_lines.append("[bold]Last stdout:[/bold] [dim]No output[/dim]")
    else:
        content_lines.append("[bold]Last stdout:[/bold] [dim]No executions on record[/dim]")
    
    content_lines.append("")
    content_lines.append("[dim][esc / back]  return to dashboard[/dim]")
    
    content = "\n".join(content_lines)
    
    return Panel(
        content,
        title=f"session {session_id[:8]}",
        border_style="dim"
    )


def run_dashboard(refresh: int = 5) -> None:
    """Main entry point for the interactive dashboard."""
    console = Console()
    
    # Print banner
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
    console.print("Interactive Session Dashboard", style="dim")
    console.print("─" * 80, style="dim")
    
    # Threading setup
    stop_event = threading.Event()
    current_session_id_ref = [None]  # Use list to make it mutable in closure
    live = None
    render_thread = None
    
    def get_content():
        current_session_id = current_session_id_ref[0]
        if current_session_id:
            return build_detail_panel(current_session_id)
        else:
            return build_session_table(limit=5)
    
    def render_loop(live_obj, get_content_func, refresh_interval):
        while not stop_event.is_set():
            try:
                live_obj.update(get_content_func())
                time.sleep(refresh_interval)
            except Exception:
                break
    
    def start_live_display():
        nonlocal live, render_thread
        stop_event.clear()  # Reset the stop event
        live = Live(get_content(), refresh_per_second=1, console=console)
        live.__enter__()
        render_thread = threading.Thread(
            target=render_loop,
            args=(live, get_content, refresh),
            daemon=True
        )
        render_thread.start()
    
    def stop_live_display():
        nonlocal live, render_thread
        stop_event.set()
        if render_thread and render_thread.is_alive():
            render_thread.join(timeout=1)
        if live:
            try:
                live.__exit__(None, None, None)
            except Exception:
                pass
    
    try:
        # Start display initially with table
        start_live_display()
        
        while True:
            try:
                # Stop display for input
                stop_live_display()
                
                # Get input
                text = prompt(
                    "> ",
                    bottom_toolbar=HTML(
                        "<b>rica dashboard</b>  |  "
                        "enter a session ID to inspect  |  "
                        "enter a goal to start a new session  |  "
                        "<b>ctrl-c</b> exit"
                    )
                ).strip()
                
                if not text:
                    start_live_display()
                    continue
                
                if text.lower() in ("back", "esc", ".."):
                    current_session_id_ref[0] = None
                    start_live_display()
                    continue
                
                if is_session_id(text):
                    # Verify it exists in DB
                    sessions = db.get_sessions()
                    ids = [s["id"] for s in sessions]
                    
                    if text in ids:
                        current_session_id_ref[0] = text
                    elif any(s["id"].startswith(text) for s in sessions):
                        # Resolve partial match
                        match = next((s["id"] for s in sessions if s["id"].startswith(text)), None)
                        current_session_id_ref[0] = match
                    else:
                        console.print(f"[red]session not found:[/red] {text}")
                    
                    # Start display with new session
                    start_live_display()
                    continue
                
                # Treat as new goal
                console.print(f"\n[dim]launching:[/dim] rica plan \"{text}\" --yes")
                subprocess.run([sys.executable, "-m", "rica", "plan", text, "--yes"])
                
                # After plan completes, prompt user to build
                session_rows = db.get_sessions()
                if session_rows:
                    newest_id = session_rows[0]["id"]
                    console.print(f"[dim]building session:[/dim] {newest_id}")
                    subprocess.run([sys.executable, "-m", "rica", "build", newest_id])
                
                # Re-launch dashboard after build completes
                run_dashboard(refresh)
                return
                
            except KeyboardInterrupt:
                break
            except EOFError:
                break
    
    finally:
        stop_live_display()
        console.print("[dim]exiting rica dashboard[/dim]")
