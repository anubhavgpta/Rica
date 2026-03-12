from pathlib import Path
from dataclasses import dataclass, field

@dataclass
class WorkspaceMemory:
    goal: str
    workspace_dir: str
    files_created: list[str] = field(
        default_factory=list
    )
    files_modified: list[str] = field(
        default_factory=list
    )
    decisions: list[str] = field(
        default_factory=list
    )
    errors_seen: list[str] = field(
        default_factory=list
    )
    iteration: int = 0

    def record_file(
        self, path: str, created: bool = True
    ) -> None:
        if created:
            if path not in self.files_created:
                self.files_created.append(path)
        else:
            if path not in self.files_modified:
                self.files_modified.append(path)

    def record_decision(
        self, decision: str
    ) -> None:
        self.decisions.append(decision)

    def record_error(
        self, error: str
    ) -> None:
        if error not in self.errors_seen:
            self.errors_seen.append(error)

    def summary(self) -> str:
        return (
            f"Goal: {self.goal}\n"
            f"Iteration: {self.iteration}\n"
            f"Files created: "
            f"{len(self.files_created)}\n"
            f"Files modified: "
            f"{len(self.files_modified)}\n"
            f"Errors seen: "
            f"{len(self.errors_seen)}"
        )
