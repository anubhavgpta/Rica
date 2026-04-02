"""L6 Watch Mode — monitor directory for changes and auto-review."""

import queue
import threading
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from watchdog.events import FileSystemEventHandler, FileSystemEvent
from watchdog.observers import Observer

from .db import save_review
from .models import ReviewIssue, ReviewReport
from .registry import LANGUAGE_REGISTRY
from .reviewer import review_codebase


# Runtime directories to skip (mirrors L2/L5 filter)
_SKIP_DIRS = frozenset(
    {
        ".venv", "venv", "env", "node_modules", "__pycache__",
        ".git", "dist", "build", "target", ".tox",
    }
)


def diff_reports(prior: ReviewReport, current: ReviewReport) -> tuple[list[ReviewIssue], list[ReviewIssue]]:
    """Compare two ReviewReport objects and return (new_issues, resolved_issues).
    
    A ReviewIssue is considered the same issue if file, line, and category match.
    """
    def key(issue: ReviewIssue) -> tuple:
        return (issue.file, issue.line, issue.category)

    prior_keys = {key(i) for i in prior.issues}
    current_keys = {key(i) for i in current.issues}

    new_issues = [i for i in current.issues if key(i) not in prior_keys]
    resolved_issues = [i for i in prior.issues if key(i) not in current_keys]

    return new_issues, resolved_issues


def _should_watch_file(file_path: Path) -> bool:
    """Check if a file should be watched based on extension and location."""
    # Check if file is in a runtime directory
    if any(part in _SKIP_DIRS for part in file_path.parts):
        return False
    
    # Check if file extension is recognized
    ext = file_path.suffix.lower()
    for lang_info in LANGUAGE_REGISTRY.values():
        if lang_info.get("extension") == ext:
            return True
    
    return False


class ChangeHandler(FileSystemEventHandler):
    """Handle file system events for the watcher."""
    
    def __init__(self, debounce_callback):
        super().__init__()
        self.debounce_callback = debounce_callback
    
    def on_modified(self, event: FileSystemEvent):
        if not event.is_directory and _should_watch_file(Path(event.src_path)):
            self.debounce_callback()
    
    def on_created(self, event: FileSystemEvent):
        if not event.is_directory and _should_watch_file(Path(event.src_path)):
            self.debounce_callback()
    
    def on_deleted(self, event: FileSystemEvent):
        if not event.is_directory and _should_watch_file(Path(event.src_path)):
            self.debounce_callback()


def watch_path(
    path: Path,
    lang_override: Optional[str],
    debounce: float,
    console: Console
) -> None:
    """Watch a directory for changes and auto-review on file modifications."""
    # Validate path
    if not path.is_dir():
        console.print(Panel("[red]Path is not a directory or does not exist.[/red]", border_style="dim", title="[red]Error[/red]"))
        return
    
    # Display startup header
    console.print(f"[dim]Watching: {path}[/dim]")
    if lang_override:
        console.print(f"[dim]Language: {lang_override}[/dim]")
    console.print(f"[dim]Debounce: {debounce}s[/dim]")
    console.print("[dim]Press Ctrl+C to stop.[/dim]")
    console.print()
    
    # Run initial review
    try:
        initial_report = review_codebase(path, lang_override, console)
        _display_review_report(initial_report, console)
        
        # Save initial review
        import uuid
        from datetime import datetime, timezone
        review_id = uuid.uuid4().hex[:8]
        error_count = sum(1 for i in initial_report.issues if i.severity == "error")
        save_review(
            id=review_id,
            path=str(path),
            language=initial_report.language,
            files_reviewed=initial_report.files_reviewed,
            issue_count=len(initial_report.issues),
            error_count=error_count,
            report_json=initial_report.model_dump_json(),
            reviewed_at=datetime.now(timezone.utc).isoformat() + "Z",
        )
        console.print(f"[dim]Review saved. ID: {review_id}[/dim]")
        
        prior_report = initial_report
        
    except Exception as e:
        console.print(f"[red]Initial review failed: {e}[/red]")
        return
    
    # Set up debounce mechanism
    pending = queue.Queue()
    timer: threading.Timer | None = None
    
    def on_change():
        nonlocal timer
        if timer:
            timer.cancel()
        timer = threading.Timer(debounce, lambda: pending.put(True))
        timer.start()
    
    # Set up file system observer
    event_handler = ChangeHandler(on_change)
    observer = Observer()
    observer.schedule(event_handler, str(path), recursive=True)
    observer.start()
    
    console.print()
    
    # Main watch loop
    try:
        while True:
            try:
                # Wait for change event with timeout
                pending.get(timeout=0.2)
                
                # Change detected - run re-review
                console.print("─" * 34, style="dim")
                console.print("[dim]Change detected — re-reviewing...[/dim]")
                
                try:
                    current_report = review_codebase(path, lang_override, console)
                    
                    # Calculate diff
                    new_issues, resolved_issues = diff_reports(prior_report, current_report)
                    unchanged_count = len(current_report.issues) - len(new_issues)
                    
                    # Display issue delta
                    _display_issue_delta(new_issues, resolved_issues, unchanged_count, console)
                    
                    # Save re-review
                    import uuid
                    from datetime import datetime, timezone
                    review_id = uuid.uuid4().hex[:8]
                    error_count = sum(1 for i in current_report.issues if i.severity == "error")
                    save_review(
                        id=review_id,
                        path=str(path),
                        language=current_report.language,
                        files_reviewed=current_report.files_reviewed,
                        issue_count=len(current_report.issues),
                        error_count=error_count,
                        report_json=current_report.model_dump_json(),
                        reviewed_at=datetime.now(timezone.utc).isoformat() + "Z",
                    )
                    
                    prior_report = current_report
                    
                except Exception as e:
                    console.print(f"[red]Re-review failed: {e}[/red]")
                
            except queue.Empty:
                # No event, continue loop
                continue
                
    except KeyboardInterrupt:
        console.print("[dim]Watch stopped.[/dim]")
    finally:
        observer.stop()
        observer.join()


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

    from rich.table import Table
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


def _display_issue_delta(
    new_issues: list[ReviewIssue],
    resolved_issues: list[ReviewIssue],
    unchanged_count: int,
    console: Console
) -> None:
    """Display the issue delta panel."""
    if not new_issues and not resolved_issues:
        console.print("[dim]No change since last review.[/dim]")
        console.print()
        return
    
    # Build panel content
    lines = []
    
    # New issues (green + prefix)
    for issue in new_issues:
        line_prefix = f"+ {issue.file}:{issue.line if issue.line else '?'} [{issue.severity}] {issue.category} — {issue.description}"
        lines.append(f"[green]{line_prefix}[/green]")
    
    # Resolved issues (red dim - prefix)
    for issue in resolved_issues:
        line_prefix = f"- {issue.file}:{issue.line if issue.line else '?'} [{issue.severity}] {issue.category} — {issue.description}"
        lines.append(f"[red dim]{line_prefix}[/red dim]")
    
    # Summary line
    if new_issues or resolved_issues:
        summary = f"{len(new_issues)} new, {len(resolved_issues)} resolved, {unchanged_count} unchanged"
        lines.append(f"[dim]{summary}[/dim]")
    
    # Display in panel
    content = "\n".join(lines)
    console.print(Panel(content, title="Issue Delta", border_style="dim"))
    console.print()
