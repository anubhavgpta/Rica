"""Pydantic models for Rica planning system."""

from typing import List

from pydantic import BaseModel, Field


class FilePlan(BaseModel):
    """Plan for a single file to be created."""
    path: str = Field(description="Relative path to the file")
    description: str = Field(description="What this file does and its purpose")
    language: str = Field(description="Programming language for this file")
    dependencies: List[str] = Field(default_factory=list, description="External dependencies needed")


class Milestone(BaseModel):
    """A milestone in the build plan representing a logical grouping of files."""
    name: str = Field(description="Name of this milestone")
    description: str = Field(description="What this milestone accomplishes")
    files: List[FilePlan] = Field(description="Files to be created in this milestone")


class BuildPlan(BaseModel):
    """Complete build plan for a coding project."""
    session_id: str = Field(description="Unique session identifier")
    goal: str = Field(description="User's original goal")
    language: str = Field(description="Primary programming language")
    rationale: str = Field(description="Why this language and approach was chosen")
    estimated_files: int = Field(description="Total number of files to be created")
    milestones: List[Milestone] = Field(description="List of milestones to complete")
    install_commands: List[str] = Field(default_factory=list, description="Commands to install dependencies")
    notes: str = Field(default="", description="Additional notes or warnings")


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
