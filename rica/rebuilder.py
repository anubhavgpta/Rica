"""Rebuilder functionality for Rica rebuild system."""

from pathlib import Path
from typing import List
from datetime import datetime, timezone
import hashlib

from . import db
from .db import get_latest_build, get_plan_for_session
from .models import BuildPlan, RebuildReport
from .snapshotter import load_snapshot, diff_snapshot
from .dep_graph import build_dep_graph, cascade_changed
from .llm import generate
from .codegen import _strip_fences
from .config import RICA_HOME
import json
from rich.console import Console

console = Console()


def take_snapshot_without_saving(workspace: Path) -> List:
    """Take snapshot without saving to database."""
    snapshots = []
    runtime_dirs = {".venv", "venv", "env", "node_modules", "__pycache__", 
                   ".git", "dist", "build", "target", ".tox"}
    
    for file_path in workspace.rglob("*"):
        if file_path.is_file():
            # Skip files in runtime directories
            if any(part in runtime_dirs for part in file_path.parts):
                continue
                
            try:
                # Calculate SHA256
                sha256 = None
                try:
                    with open(file_path, "rb") as f:
                        content = f.read()
                        sha256 = hashlib.sha256(content).hexdigest()
                except (IOError, OSError):
                    sha256 = None
                
                # Get modification time
                mtime = file_path.stat().st_mtime
                
                # Create snapshot dict with relative path
                rel_path = file_path.relative_to(workspace)
                snapshots.append({
                    "path": str(rel_path),
                    "sha256": sha256,
                    "mtime": mtime
                })
                
            except (OSError, IOError):
                # Skip files that can't be accessed
                continue
    
    return snapshots


def rebuild_changed(
    session_id: str,
    workspace: Path,
    plan: BuildPlan,
    changed_only: bool = True
) -> RebuildReport:
    """Rebuild changed files and their dependents."""
    
    # 1. Take current snapshot without saving
    current_snapshot_data = take_snapshot_without_saving(workspace)
    
    # 2. Load prior snapshot
    old_snapshot_dict = load_snapshot(session_id)
    if not old_snapshot_dict:
        # No prior snapshot - treat all files as changed and create initial snapshot
        console.print("[dim]No prior snapshot found. Treating all files as changed and creating initial snapshot.[/dim]")
        
        # Get all plan files as "changed"
        all_plan_files = []
        for milestone in plan.milestones:
            for file_plan in milestone.files:
                all_plan_files.append(file_plan.path)
        
        # Create initial snapshot after rebuild
        from . import snapshotter
        snapshotter.take_snapshot(session_id, workspace)
        
        return RebuildReport(
            session_id=session_id,
            workspace=str(workspace),
            files_checked=len(current_snapshot_data),
            files_changed=all_plan_files,
            files_cascaded=[],
            files_rewritten=[],
            files_skipped=[],
            rebuilt_at=datetime.now(timezone.utc).isoformat() + "Z"
        )
    
    # 3. Diff to find changed files
    changed_paths = diff_snapshot(old_snapshot_dict, current_snapshot_data)
    
    # 4. Check if no changes and changed_only is True
    if changed_only and not changed_paths:
        console.print("[dim]No changes detected. Nothing to rebuild.[/dim]")
        db.save_rebuild_log(session_id, len(current_snapshot_data), 0, 0, 0, len(current_snapshot_data))
        return RebuildReport(
            session_id=session_id,
            workspace=str(workspace),
            files_checked=len(current_snapshot_data),
            files_changed=[],
            files_cascaded=[],
            files_rewritten=[],
            files_skipped=[fp.path for milestone in plan.milestones for fp in milestone.files],
            rebuilt_at=datetime.now(timezone.utc).isoformat() + "Z"
        )
    
    # 5. Build dependency graph
    graph = build_dep_graph(plan)
    
    # 6. Cascade changes to find dependents
    cascaded_paths = cascade_changed(changed_paths, graph)
    
    # 7. Determine files to rebuild
    to_rebuild = sorted(set(changed_paths) | set(cascaded_paths))
    
    # 8. Rebuild each file
    rewritten = []
    skipped = []
    
    for file_path in to_rebuild:
        # Normalize path for comparison (convert backslashes to forward slashes)
        normalized = file_path.replace("\\", "/")
        
        # Find matching FilePlan
        fp = None
        for milestone in plan.milestones:
            for f in milestone.files:
                if f.path.replace("\\", "/") == normalized:
                    fp = f
                    break
            if fp:
                break
        
        if not fp:
            skipped.append(file_path)
            continue
        
        try:
            # Generate content for this single file
            prompt = f"""Regenerate the file `{fp.path}` for the following project.
Goal: {plan.goal}
File description: {fp.description}
Dependencies: {fp.dependencies}
Return ONLY the raw file content. No markdown fences, no explanations, no extra text."""
            
            response = generate(
                system_prompt_file="rica/prompts/codegen.txt",
                user_prompt=prompt,
                layer="L10",
                call_type="rebuild",
                session_id=session_id
            )
            
            # Strip fences and write to file
            content = _strip_fences(response)
            
            # Create parent directories if needed (pathlib handles separator conversion)
            dest = workspace / Path(fp.path)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(content, encoding="utf-8")
            
            rewritten.append(file_path)
            
        except Exception as e:
            console.print(f"[red]Error rebuilding {file_path}: {e}[/red]")
            skipped.append(file_path)
    
    # 9. Files in plan that were not rebuilt are skipped
    all_plan_paths = set()
    for milestone in plan.milestones:
        for f in milestone.files:
            all_plan_paths.add(f.path.replace("\\", "/"))
    
    rewritten_normalized = {p.replace("\\", "/") for p in rewritten}
    skipped = sorted(
        p for p in all_plan_paths
        if p not in rewritten_normalized
        and p not in {r.replace("\\", "/") for r in changed_paths}
        and p not in {c.replace("\\", "/") for c in cascaded_paths}
    )
    
    # 10. Take fresh snapshot after rebuild and save it
    from . import snapshotter
    snapshotter.take_snapshot(session_id, workspace)
    
    # 11. Save rebuild log
    db.save_rebuild_log(
        session_id,
        len(current_snapshot_data),
        len(changed_paths),
        len(cascaded_paths),
        len(rewritten),
        len(skipped)
    )
    
    # 12. Return report
    return RebuildReport(
        session_id=session_id,
        workspace=str(workspace),
        files_checked=len(current_snapshot_data),
        files_changed=changed_paths,
        files_cascaded=cascaded_paths,
        files_rewritten=rewritten,
        files_skipped=skipped,
        rebuilt_at=datetime.now(timezone.utc).isoformat() + "Z"
    )


def rebuild(session_id: str, changed_only: bool = False) -> RebuildReport:
    """Main rebuild function that agent orchestrator calls.
    
    Args:
        session_id: Session ID to rebuild
        changed_only: Whether to only rebuild changed files
        
    Returns:
        RebuildReport with rebuild results
    """
    try:
        # Get workspace and plan
        build = get_latest_build(session_id)
        if not build:
            raise ValueError(f"No build found for session {session_id}")
        
        workspace = Path(build["workspace"])
        plan_data = get_plan_for_session(session_id)
        if not plan_data:
            raise ValueError(f"No plan found for session {session_id}")
        
        plan = BuildPlan.model_validate_json(plan_data["plan_json"])
        
        # If changed_only is False, rebuild all files
        if not changed_only:
            # Get all plan files as "changed"
            all_files = []
            for milestone in plan.milestones:
                for file_plan in milestone.files:
                    all_files.append(file_plan.path)
            
            return rebuild_changed(session_id, workspace, plan, all_files)
        else:
            # Get actual changed files from snapshot diff
            current_snapshot_data = take_snapshot_without_saving(workspace)
            saved_snapshot_data = load_snapshot(session_id)
            
            if not saved_snapshot_data:
                # No saved snapshot, treat all files as changed
                all_files = []
                for milestone in plan.milestones:
                    for file_plan in milestone.files:
                        all_files.append(file_plan.path)
                return rebuild_changed(session_id, workspace, plan, all_files)
            
            # Compare snapshots to find changed files
            changed_paths = []
            saved_dict = saved_snapshot_data  # Already a Dict[str, FileSnapshot]
            
            for current in current_snapshot_data:
                path = current["path"]
                if path not in saved_dict:
                    # New file
                    changed_paths.append(path)
                elif saved_dict[path].sha256 != current["sha256"]:
                    # Modified file
                    changed_paths.append(path)
            
            return rebuild_changed(session_id, workspace, plan, changed_paths)
    except Exception as e:
        console.print(f"[red]Rebuild error: {e}[/red]")
        console.print(f"[red]Error type: {type(e).__name__}[/red]")
        import traceback
        console.print(f"[red]Traceback: {traceback.format_exc()}[/red]")
        # Return a minimal report on error
        return RebuildReport(
            session_id=session_id,
            workspace="",
            files_checked=0,
            files_changed=[],
            files_cascaded=[],
            files_rewritten=[],
            files_skipped=[],
            rebuilt_at=datetime.now(timezone.utc).isoformat() + "Z"
        )
