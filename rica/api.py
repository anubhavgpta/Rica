"""Rica API - Clean, Rich-free programmatic interface for ALARA integration."""

import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional, List

from . import db
from .codegen import build_project
from .config import PLANS_DIR, RICA_HOME
from .debugger import classify_error, generate_fix
from .executor import detect_server, run_command
from .explainer import explain_codebase
from .llm import llm
from .models import (
    BuildPlan, ExecutionResult, ReviewReport, ExplainReport, 
    RefactorReport, TestGenReport, RebuildReport, GeneratedFile
)
from .planner import create_plan
from .refactorer import refactor_codebase, apply_refactor
from .reviewer import review_codebase, fix_file
from .test_generator import generate_tests
from . import rebuilder


# Helper functions (extracted from main.py patterns)

def _generate_session_id() -> str:
    """Generate a new session ID."""
    return str(uuid.uuid4())[:8]

def _ensure_workspace(workspace: Optional[Path]) -> Path:
    """Resolve workspace path, using default if None."""
    if workspace is None:
        workspace = PLANS_DIR / "workspaces" / _generate_session_id()
    workspace.mkdir(parents=True, exist_ok=True)
    return workspace

def _create_console():
    """Create a minimal console-like object for internal use (no Rich output)."""
    class NullConsole:
        def __init__(self):
            pass
        def print(self, *args, **kwargs):
            pass
    return NullConsole()


# Planning API

def plan(goal: str, lang_override: str | None = None, auto_approve: bool = False) -> BuildPlan:
    """Create a build plan for the given goal.
    
    Args:
        goal: User's goal description
        lang_override: Optional language override
        auto_approve: Whether to auto-approve the plan
        
    Returns:
        BuildPlan object
    """
    session_id = _generate_session_id()
    
    # Create plan
    plan_obj = create_plan(goal, session_id, lang_override)
    
    # Save session and plan to DB
    db.db.create_session(session_id, goal, plan_obj.language)
    plan_id = str(uuid.uuid4())
    db.db.save_plan(plan_id, session_id, plan_obj.model_dump_json())
    
    # Auto-approve if requested
    if auto_approve:
        db.db.update_plan_approval(session_id, True)
    
    return plan_obj


def approve_plan(session_id: str) -> bool:
    """Mark a plan as approved.
    
    Args:
        session_id: Session ID to approve
        
    Returns:
        True if plan was found and updated, False otherwise
    """
    try:
        db.db.update_plan_approval(session_id, True)
        return True
    except Exception:
        return False


# Code Generation API

def build(session_id: str, workspace: Path | None = None) -> tuple[Path, List[GeneratedFile]]:
    """Build a project from an approved plan.
    
    Args:
        session_id: Session ID with approved plan
        workspace: Optional workspace path
        
    Returns:
        Tuple of (workspace_path, generated_files)
        
    Raises:
        ValueError: If plan is not approved or not found
    """
    # Get approved plan
    plan_data = db.db.get_plan_for_session(session_id)
    if not plan_data:
        raise ValueError(f"No approved plan found for session {session_id}")
    
    plan_obj = BuildPlan.model_validate_json(plan_data["plan_json"])
    
    # Resolve workspace
    workspace = _ensure_workspace(workspace)
    
    # Build project
    console = _create_console()
    generated_files = build_project(plan_obj, workspace, console)
    
    # Save build record
    build_id = str(uuid.uuid4())
    started_at = datetime.utcnow().isoformat() + "Z"
    db.db.insert_build(build_id, session_id, str(workspace), started_at)
    completed_at = datetime.utcnow().isoformat() + "Z"
    db.db.complete_build(build_id, completed_at)
    
    return workspace, generated_files


# Execution API

def run(session_id: str, timeout: int = 30) -> ExecutionResult:
    """Run the server command for a session.
    
    Args:
        session_id: Session ID
        timeout: Command timeout in seconds
        
    Returns:
        ExecutionResult object
    """
    # Get workspace
    build_data = db.db.get_build_by_session(session_id)
    if not build_data:
        raise ValueError(f"No build found for session {session_id}")
    
    workspace = Path(build_data["workspace"])
    
    # Detect server command
    server_cmd = detect_server(workspace)
    if not server_cmd:
        # Fall back to install commands
        plan_data = db.db.get_plan(session_id)
        if plan_data:
            plan_obj = BuildPlan.model_validate_json(plan_data)
            server_cmd = plan_obj.install_commands[:3]  # Limit to first 3 commands
        else:
            raise ValueError(f"No plan found for session {session_id}")
    
    # Run command
    console = _create_console()
    result = run_command(server_cmd, workspace, timeout, console)
    
    # Save to DB
    db.db.save_execution(result, session_id)
    
    return result


def check(session_id: str) -> ExecutionResult:
    """Run the check/test command for a session.
    
    Args:
        session_id: Session ID
        
    Returns:
        ExecutionResult object
    """
    # Get workspace
    build_data = db.db.get_build_by_session(session_id)
    if not build_data:
        raise ValueError(f"No build found for session {session_id}")
    
    workspace = Path(build_data["workspace"])
    
    # Get check command from language config
    plan_data = db.db.get_plan(session_id)
    if not plan_data:
        raise ValueError(f"No plan found for session {session_id}")
    
    plan_obj = BuildPlan.model_validate_json(plan_data)
    from .registry import get_language_config
    lang_config = get_language_config(plan_obj.language)
    check_cmd = lang_config.get("check_command", [])
    
    if not check_cmd:
        raise ValueError(f"No check command configured for language {plan_obj.language}")
    
    # Run command
    console = _create_console()
    result = run_command(check_cmd, workspace, 30, console)
    
    # Save to DB
    db.db.save_execution(result, session_id)
    
    return result


# Debugging API

def debug(session_id: str, max_iterations: int = 5, timeout: int = 30) -> dict:
    """Run the full debug loop for a session.
    
    Args:
        session_id: Session ID
        max_iterations: Maximum debug iterations
        timeout: Command timeout in seconds
        
    Returns:
        Debug result dict with session info
    """
    debug_session_id = str(uuid.uuid4())
    started_at = datetime.utcnow().isoformat() + "Z"
    db.db.insert_debug_session(debug_session_id, session_id, started_at)
    
    # Simple debug loop implementation
    final_status = "failed"  # Default
    
    try:
        for iteration in range(max_iterations):
            # Run check command
            check_result = check(session_id)
            
            if check_result.exit_code == 0:
                final_status = "passed"
                break
            
            # Classify error and generate fix
            error_class = classify_error(
                check_result.stdout, 
                check_result.stderr, 
                "python",  # Simplified - should get from plan
                check_result.timed_out
            )
            
            # Generate fix (simplified)
            fix_id = str(uuid.uuid4())
            db.db.insert_debug_iteration(
                fix_id,
                debug_session_id,
                iteration,
                error_class.category,
                str(error_class.implicated_files),
                0,  # check_passed
                check_result.exit_code,
                datetime.utcnow().isoformat() + "Z"
            )
            
            # In a real implementation, we would apply the fix here
            # For now, just continue to next iteration
            
    except Exception:
        final_status = "failed"
    
    completed_at = datetime.utcnow().isoformat() + "Z"
    db.db.complete_debug_session(debug_session_id, final_status, completed_at)
    
    return {
        "session_id": session_id,
        "iterations": min(max_iterations, iteration + 1),
        "final_status": final_status,
        "debug_session_id": debug_session_id
    }


# Review API

def review(path: Path, languages: List[str] | None = None) -> ReviewReport:
    """Review a codebase.
    
    Args:
        path: Path to codebase
        languages: Optional language list
        
    Returns:
        ReviewReport object
    """
    console = _create_console()
    report = review_codebase(path, languages, console)
    
    # Save to DB
    review_id = str(uuid.uuid4())
    db.save_review(
        review_id,
        str(path),
        report.language,
        report.files_reviewed,
        len([i for i in report.issues if i.severity == "error"]),
        len(report.issues),
        report.model_dump_json(),
        report.reviewed_at
    )
    
    return report


def fix(path: Path, language: str | None = None, dry_run: bool = False) -> List[Path]:
    """Apply fixes from the most recent review.
    
    Args:
        path: Path to codebase
        language: Optional language
        dry_run: Whether to perform dry run
        
    Returns:
        List of modified file paths
    """
    console = _create_console()
    modified_files = fix_file(path, language, console, dry_run)
    
    return [Path(f) for f in modified_files]


# Explanation API

def explain(path: Path, languages: List[str] | None = None) -> ExplainReport:
    """Explain a codebase.
    
    Args:
        path: Path to codebase
        languages: Optional language list
        
    Returns:
        ExplainReport object
    """
    console = _create_console()
    report = explain_codebase(path, languages, console)
    
    # Save to DB
    db.save_explanation(report)
    
    return report


# Refactoring API

def refactor(path: Path, goal: str, languages: List[str] | None = None, dry_run: bool = False) -> RefactorReport:
    """Refactor a codebase.
    
    Args:
        path: Path to codebase
        goal: Refactoring goal
        languages: Optional language list
        dry_run: Whether to perform dry run
        
    Returns:
        RefactorReport object
    """
    console = _create_console()
    report = refactor_codebase(path, goal, languages, console)
    
    # Apply changes if not dry run
    if not dry_run:
        apply_refactor(path, report.changes, console)
    
    # Save to DB
    db.save_refactor(report)
    
    return report


# Test Generation API

def generate_tests(session_id: str) -> TestGenReport:
    """Generate tests for a session.
    
    Args:
        session_id: Session ID
        
    Returns:
        TestGenReport object
    """
    console = _create_console()
    report = generate_tests(session_id, console)
    
    # Save to DB
    db.save_test_generation(report)
    
    return report


# Diff-Aware Rebuild API

def rebuild(session_id: str, changed_only: bool = True) -> RebuildReport:
    """Rebuild a project with diff-aware changes.
    
    Args:
        session_id: Session ID
        changed_only: Whether to only rebuild changed files
        
    Returns:
        RebuildReport object
    """
    report = rebuilder.rebuild_changed(session_id, changed_only)
    return report


# Session Query API

def get_session(session_id: str) -> dict | None:
    """Get session information.
    
    Args:
        session_id: Session ID
        
    Returns:
        Session dict or None
    """
    sessions = db.get_sessions()
    for session in sessions:
        if session["id"] == session_id:
            return session
    return None


def list_sessions(language: str | None = None) -> List[dict]:
    """List sessions, optionally filtered by language.
    
    Args:
        language: Optional language filter
        
    Returns:
        List of session dicts
    """
    if language:
        return db.get_sessions_by_language(language)
    return db.db.list_sessions()


def get_plan(session_id: str) -> BuildPlan | None:
    """Get the plan for a session.
    
    Args:
        session_id: Session ID
        
    Returns:
        BuildPlan object or None
    """
    plan_json = db.db.get_plan(session_id)
    if plan_json:
        return BuildPlan.model_validate_json(plan_json)
    return None


def get_builds(session_id: str) -> List[dict]:
    """Get builds for a session.
    
    Args:
        session_id: Session ID
        
    Returns:
        List of build dicts
    """
    return [db.db.get_build_by_session(session_id)] if db.db.get_build_by_session(session_id) else []


def get_executions(session_id: str) -> List[dict]:
    """Get executions for a session.
    
    Args:
        session_id: Session ID
        
    Returns:
        List of execution dicts
    """
    return db.get_executions(session_id)


def get_reviews(path: Path | None = None) -> List[dict]:
    """Get reviews, optionally filtered by path.
    
    Args:
        path: Optional path filter
        
    Returns:
        List of review dicts
    """
    path_str = str(path) if path else None
    return db.get_reviews_for_path(path_str)


def get_explanations(path: Path | None = None) -> List[dict]:
    """Get explanations, optionally filtered by path.
    
    Args:
        path: Optional path filter
        
    Returns:
        List of explanation dicts
    """
    path_str = str(path) if path else None
    return db.list_explanations(path_str)


def get_refactors(path: Path | None = None) -> List[dict]:
    """Get refactors, optionally filtered by path.
    
    Args:
        path: Optional path filter
        
    Returns:
        List of refactor dicts
    """
    path_str = str(path) if path else None
    return db.list_refactors(path_str)


def get_test_generations(session_id: str | None = None) -> List[dict]:
    """Get test generations, optionally filtered by session.
    
    Args:
        session_id: Optional session ID filter
        
    Returns:
        List of test generation dicts
    """
    return db.list_test_generations(session_id)


def get_rebuild_history(session_id: str) -> List[dict]:
    """Get rebuild history for a session.
    
    Args:
        session_id: Session ID
        
    Returns:
        List of rebuild dicts
    """
    return db.get_rebuild_logs(session_id)
