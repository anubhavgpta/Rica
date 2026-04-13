"""Pydantic models for Rica planning system."""

from typing import List, Optional, Literal
from pathlib import Path

from pydantic import BaseModel, Field, model_validator


class FilePlanLanguage(BaseModel):
    """Language tag attached to each FilePlan — added in L9."""
    language: str   # resolved language string, e.g. "python", "typescript"


class FilePlan(BaseModel):
    """Plan for a single file to be created."""
    path: str = Field(description="Relative path to the file")
    description: str = Field(description="What this file does and its purpose")
    language: str = Field(description="Programming language for this file")
    dependencies: List[str] = Field(default_factory=list, description="External dependencies needed")
    language_tag: Optional[FilePlanLanguage] = None


class Milestone(BaseModel):
    """A milestone in the build plan representing a logical grouping of files."""
    name: str = Field(description="Name of this milestone")
    description: str = Field(description="What this milestone accomplishes")
    files: List[FilePlan] = Field(description="Files to be created in this milestone")


class LanguageInstallBlock(BaseModel):
    language: str
    commands: List[str]


class BuildPlan(BaseModel):
    """Complete build plan for a coding project."""
    session_id: str = Field(description="Unique session identifier")
    goal: str = Field(description="User's original goal")
    languages: List[str] = Field(description="List of programming languages used")
    language: str = Field(description="Primary programming language (backwards-compat)")
    rationale: str = Field(description="Why this language and approach was chosen")
    estimated_files: int = Field(description="Total number of files to be created")
    milestones: List[Milestone] = Field(description="List of milestones to complete")
    install_steps: List[LanguageInstallBlock] = Field(description="Ordered per-language install blocks")
    install_commands: List[str] = Field(default_factory=list, description="Commands to install dependencies (backwards-compat)")
    notes: str = Field(default="", description="Additional notes or warnings")
    
    @model_validator(mode="after")
    def populate_backwards_compat_fields(self):
        """Populate backwards-compatibility fields from multi-language fields."""
        # Set language to first language if not already set
        if not self.language and self.languages:
            self.language = self.languages[0]
        elif self.languages and self.language != self.languages[0]:
            # Ensure language always matches first language
            self.language = self.languages[0]
        
        # Flatten install_steps to install_commands
        if self.install_steps:
            self.install_commands = []
            for step in self.install_steps:
                self.install_commands.extend(step.commands)
        
        return self


class GeneratedFile(BaseModel):
    """Represents a generated file in the build process."""
    path: str
    content: str
    language: str
    generated_at: str


class ExecutionResult(BaseModel):
    """Result of executing a command."""
    command: list[str]
    exit_code: int | None
    stdout: str
    stderr: str
    timed_out: bool
    executed_at: str


class ErrorClass(BaseModel):
    """Classification of an error for debugging."""
    category: str  # "compile_error" | "runtime_error" | "import_error" | "type_error" | "assertion_error" | "timeout" | "unknown"
    implicated_files: list[str]
    error_summary: str
    raw_stderr: str


class ReviewIssue(BaseModel):
    file: str
    line: int | None = None
    severity: str  # "error", "warning", "info"
    category: str  # "bug", "security", "performance", "style", "maintainability", "unused_code"
    description: str
    suggestion: str


class ReviewReport(BaseModel):
    path: str
    language: str
    files_reviewed: int
    issues: list[ReviewIssue]
    summary: str


class ExplainReport(BaseModel):
    path: str
    language: str
    files_analyzed: int
    explanation: str
    explained_at: str


class RefactorChange(BaseModel):
    path: str
    content: str


class RefactorReport(BaseModel):
    path: str
    language: str
    goal: str
    files_analyzed: int
    changes: list[RefactorChange]
    refactored_at: str


class GeneratedTest(BaseModel):
    """Represents a generated test file."""
    path: str
    content: str


class TestGenReport(BaseModel):
    """Report for test generation session."""
    session_id: str
    language: str
    goal: str
    files_analyzed: int
    tests_generated: list[GeneratedTest]
    generated_at: str


class FileSnapshot(BaseModel):
    """Snapshot of a file at a point in time."""
    path: str                    # relative path within workspace
    sha256: str | None = None
    mtime: float
    snapshotted_at: str


class RebuildReport(BaseModel):
    """Report of a rebuild operation."""
    session_id: str
    workspace: str
    files_checked: int
    files_changed: list[str]
    files_cascaded: list[str]
    files_rewritten: list[str]
    files_skipped: list[str]
    rebuilt_at: str


# L18 Autonomous Agent Models

class SubTask(BaseModel):
    """A single subtask in an agent execution plan."""
    type: Literal['plan', 'build', 'execute', 'debug', 'review', 'fix',
                  'explain', 'refactor', 'gen_tests', 'rebuild',
                  'watch_start', 'watch_stop', 'ask_user']
    goal: str | None = None
    session_id: str | None = None
    path: str | None = None
    lang: str | None = None
    command: str | None = None
    max_iter: int = 5
    changed_only: bool = True
    question: str | None = None
    depends_on: list[int] = Field(
        default_factory=list,
        description=(
            "Indices of other subtasks in the same turn that must complete "
            "before this subtask can start. Empty list means no dependencies."
        ),
    )


class SubTaskResult(BaseModel):
    """Result of executing a single subtask."""
    task_type: str
    passed: bool
    summary: str          # one-line human-readable outcome
    detail: dict          # raw return value from the called layer
    attempt: int          # 1 = first try, 2 = retry
    previous_attempt_detail: dict | None = None  # populated on retry
    wave_index: int = Field(
        default=0,
        description="Zero-based index of the execution wave this subtask ran in.",
    )
    status: str = Field(
        default="completed",
        description="Status of this subtask: 'completed', 'stuck', or 'failed'.",
    )
    subtask: SubTask | None = Field(
        default=None,
        description="The subtask that produced this result.",
    )
    output: str | None = Field(
        default=None,
        description="Output string for error reporting.",
    )


class AgentTurnResult(BaseModel):
    """Result of a complete agent turn."""
    session_id: str
    turn_index: int
    user_prompt: str
    subtasks: list[SubTask]
    results: list[SubTaskResult]
    final_status: Literal['completed', 'partial', 'stuck', 'waiting_for_user']
    agent_reply: str      # human-readable summary to display in TUI


class AgentMemoryEntry(BaseModel):
    """Entry in agent memory for persistence."""
    id: int
    session_id: str
    turn_index: int
    role: str
    content: str
    subtasks: list[SubTask] | None
    trace: list[SubTaskResult] | None
    created_at: str


class ProjectContext(BaseModel):
    """Context about the current project for agent decision making."""
    session_id: str | None
    workspace_path: str | None        # resolved from session if exists
    languages: list[str]              # from BuildPlan.languages if exists
    recent_history: list[dict]        # last N agent_memory turns
    active_snapshot_id: int | None    # latest file_snapshots row id
    last_build_status: str | None     # 'success' | 'failed' | None
    last_debug_status: str | None     # 'resolved' | 'exhausted' | None


class AgentParallelConfig(BaseModel):
    """
    Controls parallel execution behaviour for the agent orchestrator.
    Stored in agent_memory as JSON alongside AgentTurnResult.
    """
    max_workers: int = Field(
        default=4,
        ge=1,
        le=16,
        description="Maximum number of concurrent subtask threads.",
    )
    enabled: bool = Field(
        default=True,
        description="If False, fall back to sequential execution regardless of DAG.",
    )
    swebench_mode: bool = False


class WatchEvent(BaseModel):
    """Event from file watcher in agent mode."""
    path: str
    issues: list[dict]  # List of issues found by watcher
    timestamp: str


class EditSpec(BaseModel):
    """Describes a targeted edit to a single file."""
    filepath: Path
    start_line: int          # 1-indexed, inclusive
    end_line: int            # 1-indexed, inclusive
    replacement_lines: list[str]   # lines to substitute for [start_line, end_line]
    description: str = ""


class ApplyResult(BaseModel):
    success: bool
    files_patched: list[Path]
    errors: list[str]


class PatchResult(BaseModel):
    success: bool
    diff_applied: str        # the unified diff that was applied (or attempted)
    validation_exit_code: int | None = None  # None if no validate_cmd
    rolled_back: bool = False
    error: str = ""
