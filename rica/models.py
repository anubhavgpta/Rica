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
