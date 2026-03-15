"""Persistent workspace memory for RICA runs."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def load_memory(memory_path: str | Path) -> dict[str, Any]:
    """Load memory data from disk."""
    path = Path(memory_path)
    if not path.exists():
        return _default_payload()
    payload = json.loads(path.read_text(encoding="utf-8"))
    return _merge_defaults(payload)


def save_memory(
    memory_path: str | Path, payload: dict[str, Any]
) -> dict[str, Any]:
    """Save memory data to disk and return the normalized payload."""
    path = Path(memory_path)
    normalized = _merge_defaults(payload)
    path.write_text(
        json.dumps(normalized, indent=2) + "\n",
        encoding="utf-8",
    )
    return normalized


def update_memory(
    memory_path: str | Path, **updates: Any
) -> dict[str, Any]:
    """Merge updates into the current payload and persist them."""
    payload = load_memory(memory_path)
    for key, value in updates.items():
        if value is None:
            continue
        if key in _LIST_FIELDS:
            items = payload.setdefault(key, [])
            for item in value:
                if item not in items:
                    items.append(item)
        elif key in _DICT_FIELDS and isinstance(value, dict):
            payload.setdefault(key, {}).update(value)
        else:
            payload[key] = value
    return save_memory(memory_path, payload)


@dataclass
class ProjectMemory:
    """In-memory view over `.rica_memory.json`."""

    goal: str
    workspace_dir: str
    project_dir: str | None = None
    snapshot_summary: str = ""
    project_summary: str = ""
    project_metadata: dict[str, Any] = field(default_factory=dict)
    created_files: list[str] = field(default_factory=list)
    modified_files: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    errors_seen: list[str] = field(default_factory=list)
    tasks_completed: list[str] = field(default_factory=list)
    task_history: list[dict[str, Any]] = field(default_factory=list)
    decisions_made: list[str] = field(default_factory=list)
    iteration: int = 0
    
    # Enhanced long-term memory fields
    goal_history: list[dict[str, Any]] = field(default_factory=list)
    learned_patterns: list[dict[str, Any]] = field(default_factory=list)
    successful_approaches: list[dict[str, Any]] = field(default_factory=list)
    failed_approaches: list[dict[str, Any]] = field(default_factory=list)
    git_commits: list[dict[str, str]] = field(default_factory=list)
    repository_evolution: list[dict[str, Any]] = field(default_factory=list)
    performance_metrics: dict[str, Any] = field(default_factory=dict)
    user_preferences: dict[str, Any] = field(default_factory=dict)

    @property
    def memory_path(self) -> Path:
        return Path(self.workspace_dir) / ".rica_memory.json"

    @property
    def files_created(self) -> list[str]:
        return self.created_files

    @property
    def files_modified(self) -> list[str]:
        return self.modified_files

    @property
    def errors_encountered(self) -> list[str]:
        return self.errors_seen

    @classmethod
    def load_or_create(
        cls,
        goal: str,
        workspace_dir: str,
        project_dir: str | None = None,
        snapshot_summary: str = "",
        project_summary: str = "",
        project_metadata: dict[str, Any] | None = None,
    ) -> "ProjectMemory":
        memory_path = Path(workspace_dir) / ".rica_memory.json"
        payload = load_memory(memory_path)
        payload["goal"] = goal or payload.get("goal", "")
        payload["workspace_dir"] = workspace_dir
        payload["project_dir"] = project_dir or payload.get("project_dir")
        if snapshot_summary:
            payload["snapshot_summary"] = snapshot_summary
        if project_summary:
            payload["project_summary"] = project_summary
        if project_metadata:
            payload["project_metadata"] = {
                **payload.get("project_metadata", {}),
                **project_metadata,
            }
        save_memory(memory_path, payload)
        return cls.from_payload(payload)

    @classmethod
    def from_payload(
        cls, payload: dict[str, Any]
    ) -> "ProjectMemory":
        normalized = _merge_defaults(payload)
        return cls(
            goal=normalized["goal"],
            workspace_dir=normalized["workspace_dir"],
            project_dir=normalized["project_dir"],
            snapshot_summary=normalized["snapshot_summary"],
            project_summary=normalized["project_summary"],
            project_metadata=normalized["project_metadata"],
            created_files=normalized["created_files"],
            modified_files=normalized["modified_files"],
            dependencies=normalized["dependencies"],
            errors_seen=normalized["errors_seen"],
            tasks_completed=normalized["tasks_completed"],
            task_history=normalized["task_history"],
            decisions_made=normalized["decisions_made"],
            iteration=normalized["iteration"],
        )

    def save(self) -> None:
        save_memory(self.memory_path, self.to_payload())

    def update(self, **updates: Any) -> None:
        payload = update_memory(self.memory_path, **updates)
        refreshed = ProjectMemory.from_payload(payload)
        self.__dict__.update(refreshed.__dict__)

    def record_task(
        self, task: dict[str, Any], result: str
    ) -> None:
        task_history_entry = {
            "timestamp": _utc_now(),
            "id": task.get("id"),
            "description": task.get("description", ""),
            "type": task.get("type"),
            "status": task.get("status"),
            "result": result,
        }
        task_description = task.get("description", "")
        updates: dict[str, Any] = {"task_history": [task_history_entry]}
        if result == "completed" and task_description:
            updates["tasks_completed"] = [task_description]
        self.update(**updates)

    def record_file(
        self, path: str, created: bool = True
    ) -> None:
        field_name = "created_files" if created else "modified_files"
        self.update(**{field_name: [path]})

    def record_files_created(self, files: list[str]) -> None:
        """Record multiple files as created."""
        if files:
            self.update(created_files=files)

    def record_files_modified(self, files: list[str]) -> None:
        """Record multiple files as modified."""
        if files:
            self.update(modified_files=files)

    def record_error(self, error: str) -> None:
        if error:
            self.update(errors_seen=[error])

    def record_decision(self, decision: str) -> None:
        if decision:
            self.update(decisions_made=[decision])

    def set_project_context(
        self,
        *,
        project_summary: str | None = None,
        project_metadata: dict[str, Any] | None = None,
        dependencies: list[str] | None = None,
    ) -> None:
        self.update(
            project_summary=project_summary,
            project_metadata=project_metadata,
            dependencies=dependencies,
        )

    # Enhanced long-term memory methods
    def record_goal_start(self, goal: str, context: dict[str, Any] | None = None) -> None:
        """Record the start of a new goal with context."""
        goal_entry = {
            "goal": goal,
            "start_time": _utc_now(),
            "context": context or {},
            "status": "in_progress"
        }
        
        # Update current goal and add to history
        self.update(
            goal=goal,
            goal_history=[goal_entry]
        )

    def record_goal_completion(self, success: bool, result_summary: str = "") -> None:
        """Record the completion of the current goal."""
        # Update the most recent goal entry
        if self.goal_history:
            last_goal = self.goal_history[-1].copy()
            last_goal.update({
                "end_time": _utc_now(),
                "status": "completed" if success else "failed",
                "result_summary": result_summary,
                "success": success
            })
            
            # Replace the last entry
            updated_history = self.goal_history[:-1] + [last_goal]
            self.update(goal_history=updated_history)

    def learn_pattern(self, pattern_type: str, pattern: dict[str, Any]) -> None:
        """Record a learned pattern for future reference."""
        pattern_entry = {
            "type": pattern_type,
            "pattern": pattern,
            "learned_at": _utc_now(),
            "usage_count": 0
        }
        self.update(learned_patterns=[pattern_entry])

    def record_successful_approach(self, approach: dict[str, Any]) -> None:
        """Record a successful approach for future reuse."""
        approach_entry = {
            "approach": approach,
            "used_at": _utc_now(),
            "success_rate": 1.0
        }
        self.update(successful_approaches=[approach_entry])

    def record_failed_approach(self, approach: dict[str, Any], reason: str = "") -> None:
        """Record a failed approach to avoid repetition."""
        approach_entry = {
            "approach": approach,
            "failed_at": _utc_now(),
            "reason": reason
        }
        self.update(failed_approaches=[approach_entry])

    def record_git_commit(self, commit_hash: str, message: str, files_changed: list[str]) -> None:
        """Record a git commit for repository evolution tracking."""
        commit_entry = {
            "hash": commit_hash,
            "message": message,
            "files_changed": files_changed,
            "timestamp": _utc_now()
        }
        self.update(git_commits=[commit_entry])

    def record_repository_evolution(self, change_type: str, details: dict[str, Any]) -> None:
        """Record significant repository changes."""
        evolution_entry = {
            "change_type": change_type,
            "details": details,
            "timestamp": _utc_now()
        }
        self.update(repository_evolution=[evolution_entry])

    def update_performance_metrics(self, metrics: dict[str, Any]) -> None:
        """Update performance metrics for the project."""
        current_metrics = self.performance_metrics.copy()
        current_metrics.update(metrics)
        current_metrics["last_updated"] = _utc_now()
        self.update(performance_metrics=current_metrics)

    def set_user_preference(self, key: str, value: Any) -> None:
        """Set a user preference for future sessions."""
        current_prefs = self.user_preferences.copy()
        current_prefs[key] = value
        current_prefs["last_updated"] = _utc_now()
        self.update(user_preferences=current_prefs)

    def get_similar_patterns(self, pattern_type: str, context: dict[str, Any]) -> list[dict[str, Any]]:
        """Get similar learned patterns based on type and context."""
        similar_patterns = []
        for pattern_entry in self.learned_patterns:
            if pattern_entry["type"] == pattern_type:
                # Simple similarity check - can be enhanced
                similar_patterns.append(pattern_entry)
        return similar_patterns

    def get_successful_approaches_for_task(self, task_type: str) -> list[dict[str, Any]]:
        """Get successful approaches for a specific task type."""
        relevant_approaches = []
        for approach_entry in self.successful_approaches:
            approach = approach_entry["approach"]
            if approach.get("task_type") == task_type:
                relevant_approaches.append(approach_entry)
        return relevant_approaches

    def should_avoid_approach(self, approach: dict[str, Any]) -> bool:
        """Check if an approach should be avoided based on past failures."""
        for failed_entry in self.failed_approaches:
            failed_approach = failed_entry["approach"]
            # Simple matching - can be enhanced with more sophisticated comparison
            if (failed_approach.get("task_type") == approach.get("task_type") and
                failed_approach.get("method") == approach.get("method")):
                return True
        return False

    def get_project_evolution_summary(self) -> str:
        """Get a summary of repository evolution over time."""
        if not self.repository_evolution:
            return "No significant evolution recorded."
        
        summary_parts = []
        for change in self.repository_evolution[-10:]:  # Last 10 changes
            change_type = change["change_type"]
            timestamp = change["timestamp"]
            summary_parts.append(f"{timestamp}: {change_type}")
        
        return "Recent evolution: " + "; ".join(summary_parts)

    def summary(self) -> str:
        lines = [
            f"Goal: {self.goal}",
            f"Iteration: {self.iteration}",
            f"Files created: {len(self.created_files)}",
            f"Files modified: {len(self.modified_files)}",
            f"Errors seen: {len(self.errors_seen)}",
        ]
        if self.project_summary:
            lines.append(f"Project summary: {self.project_summary}")
        if self.project_metadata:
            lines.append(
                f"Project metadata: {self.project_metadata}"
            )
        return "\n".join(lines)

    def to_payload(self) -> dict[str, Any]:
        return {
            "goal": self.goal,
            "workspace_dir": self.workspace_dir,
            "project_dir": self.project_dir,
            "snapshot_summary": self.snapshot_summary,
            "project_summary": self.project_summary,
            "project_metadata": self.project_metadata,
            "created_files": self.created_files,
            "modified_files": self.modified_files,
            "dependencies": self.dependencies,
            "errors_seen": self.errors_seen,
            "tasks_completed": self.tasks_completed,
            "task_history": self.task_history,
            "decisions_made": self.decisions_made,
            "iteration": self.iteration,
            # Enhanced long-term memory fields
            "goal_history": self.goal_history,
            "learned_patterns": self.learned_patterns,
            "successful_approaches": self.successful_approaches,
            "failed_approaches": self.failed_approaches,
            "git_commits": self.git_commits,
            "repository_evolution": self.repository_evolution,
            "performance_metrics": self.performance_metrics,
            "user_preferences": self.user_preferences,
            # Backward-compatible aliases expected by older code/tests.
            "files_created": self.created_files,
            "files_modified": self.modified_files,
            "errors_encountered": self.errors_seen,
        }


_LIST_FIELDS = {
    "created_files",
    "modified_files",
    "dependencies",
    "errors_seen",
    "tasks_completed",
    "task_history",
    "decisions_made",
    "goal_history",
    "learned_patterns",
    "successful_approaches",
    "failed_approaches",
    "git_commits",
    "repository_evolution",
}
_DICT_FIELDS = {"project_metadata", "performance_metrics", "user_preferences"}


def _default_payload() -> dict[str, Any]:
    return {
        "goal": "",
        "workspace_dir": "",
        "project_dir": None,
        "snapshot_summary": "",
        "project_summary": "",
        "project_metadata": {},
        "created_files": [],
        "modified_files": [],
        "dependencies": [],
        "errors_seen": [],
        "tasks_completed": [],
        "task_history": [],
        "decisions_made": [],
        "iteration": 0,
        "goal_history": [],
        "learned_patterns": [],
        "successful_approaches": [],
        "failed_approaches": [],
        "git_commits": [],
        "repository_evolution": [],
        "performance_metrics": {},
        "user_preferences": {},
        "files_created": [],
        "files_modified": [],
        "errors_encountered": [],
    }


def _merge_defaults(payload: dict[str, Any]) -> dict[str, Any]:
    merged = {**_default_payload(), **payload}
    if payload.get("files_created") and not payload.get("created_files"):
        merged["created_files"] = list(payload["files_created"])
    if payload.get("files_modified") and not payload.get("modified_files"):
        merged["modified_files"] = list(payload["files_modified"])
    if payload.get("errors_encountered") and not payload.get("errors_seen"):
        merged["errors_seen"] = list(payload["errors_encountered"])

    merged["files_created"] = list(merged["created_files"])
    merged["files_modified"] = list(merged["modified_files"])
    merged["errors_encountered"] = list(merged["errors_seen"])
    return merged


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
