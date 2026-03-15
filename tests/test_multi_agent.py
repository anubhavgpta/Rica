import json
from pathlib import Path

from rica.core.task_queue import (
    TASK_PENDING,
    TaskQueue,
)
from rica.memory import memory_manager
from rica.memory.project_memory import ProjectMemory
from rica.tools.registry import ToolRegistry


def test_task_queue_front_insertion_order():
    queue = TaskQueue()
    queue.add_tasks(
        [
            {"id": 1, "description": "first"},
            {"id": 2, "description": "second"},
        ]
    )
    queue.add_tasks(
        [
            {"id": "r1", "description": "review"},
            {"id": "r2", "description": "fix"},
        ],
        front=True,
    )

    assert queue.next_task()["id"] == "r1"
    assert queue.next_task()["id"] == "r2"
    assert queue.next_task()["id"] == 1


def test_project_memory_persists_to_disk(
    tmp_path,
):
    memory = ProjectMemory.load_or_create(
        goal="build api",
        workspace_dir=str(tmp_path),
        project_dir=str(tmp_path),
        snapshot_summary="empty",
    )
    memory.record_file("app.py", created=True)
    memory.record_error("boom")
    memory.record_decision("use flask")
    memory.record_task(
        {
            "id": 1,
            "description": "create app",
            "type": "codegen",
            "status": TASK_PENDING,
        },
        "completed",
    )

    payload = json.loads(
        (tmp_path / ".rica_memory.json").read_text(
            encoding="utf-8"
        )
    )

    assert payload["goal"] == "build api"
    assert payload["files_created"] == ["app.py"]
    assert payload["created_files"] == ["app.py"]
    assert payload["errors_encountered"] == ["boom"]
    assert payload["errors_seen"] == ["boom"]
    assert payload["decisions_made"] == ["use flask"]
    assert payload["tasks_completed"] == ["create app"]
    assert len(payload["task_history"]) == 1


def test_tool_registry_exposes_expected_tools():
    registry = ToolRegistry(reader=None)

    assert registry.names() == [
        "install_package",
        "read_file",
        "run_command",
        "search_code",
        "write_file",
    ]


def test_memory_manager_creates_workspace_file(
    tmp_path,
):
    payload = memory_manager.load_memory(
        str(tmp_path),
        goal="hello",
    )

    assert payload["goal"] == "hello"
    assert (
        Path(tmp_path) / ".rica_memory.json"
    ).exists()
