from dataclasses import dataclass, field

@dataclass
class RicaResult:
    success: bool
    goal: str
    workspace_dir: str
    files_created: list[str] = field(
        default_factory=list
    )
    files_modified: list[str] = field(
        default_factory=list
    )
    summary: str = ""
    error: str | None = None
    iterations: int = 0
