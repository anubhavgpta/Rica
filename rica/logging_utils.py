"""Helpers for configuring workspace-scoped loguru logging."""

from __future__ import annotations

from pathlib import Path

from loguru import logger

_CONFIGURED_WORKSPACES: set[str] = set()


def get_component_logger(component: str):
    """Return a logger bound to a logical RICA component."""
    return logger.bind(component=component)


def configure_workspace_logging(workspace_dir: str) -> Path:
    """Configure per-component file logs for a workspace once."""
    workspace_key = str(Path(workspace_dir).resolve())
    logs_dir = Path(workspace_key) / ".rica_logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    if workspace_key in _CONFIGURED_WORKSPACES:
        return logs_dir

    logger.add(
        logs_dir / "planner.log",
        encoding="utf-8",
        filter=_component_filter("planner"),
    )
    logger.add(
        logs_dir / "codegen.log",
        encoding="utf-8",
        filter=_component_filter("codegen"),
    )
    logger.add(
        logs_dir / "executor.log",
        encoding="utf-8",
        filter=_component_filter("executor"),
    )
    logger.add(
        logs_dir / "debugger.log",
        encoding="utf-8",
        filter=_component_filter("debugger"),
    )
    logger.add(
        logs_dir / "agent.log",
        encoding="utf-8",
        filter=_component_filter("agent"),
    )

    _CONFIGURED_WORKSPACES.add(workspace_key)
    return logs_dir


def setup_workspace_logging(workspace_dir: str) -> Path:
    """Backward-compatible alias for workspace log setup."""
    return configure_workspace_logging(workspace_dir)


def _component_filter(component: str):
    def predicate(record: dict) -> bool:
        return record["extra"].get("component") == component

    return predicate
