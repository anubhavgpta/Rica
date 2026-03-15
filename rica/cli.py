import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import google.genai as genai

from rica.memory import load_memory
from rica.reader import CodebaseReader
from rica import RicaAgent
from rica.config import (
    DEFAULT_MODEL,
    get_config_path,
    redact_config,
)
from rica.doctor import run_doctor
from rica.setup import ensure_setup, run_setup


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()

    if argv and argv[0] not in {
        "build",
        "run",
        "setup",
        "config",
        "doctor",
        "memory",
        "logs",
        "search",
        "-h",
        "--help",
    }:
        argv = ["run", *argv]

    args = parser.parse_args(argv)

    if args.command == "setup":
        run_setup()
        return 0

    if args.command == "doctor":
        return run_doctor()

    config = ensure_setup()

    if args.command == "config":
        payload = redact_config(config)
        payload["config_path"] = str(
            get_config_path()
        )
        print(json.dumps(payload, indent=2))
        return 0

    if args.command == "memory":
        return _show_memory(args.workspace)

    if args.command == "logs":
        return _show_logs(args.workspace)

    if args.command == "search":
        return _run_search(args.query, args.workspace, config)

    if args.command in {"run", "build"}:
        goal = " ".join(args.goal).strip()
        if args.command == "build" and goal:
            goal = f"build {goal}"
        if not goal:
            _print_greeting(config)
            goal = input("> ").strip()
        if not goal:
            print("No goal provided.")
            return 1
        return _run_agent(goal, args.workspace, config)

    _print_greeting(config)
    goal = input("> ").strip()
    if not goal:
        parser.print_help()
        return 1
    return _run_agent(goal, None, config)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="RICA standalone coding agent"
    )
    sub = parser.add_subparsers(
        dest="command"
    )

    run_parser = sub.add_parser(
        "run",
        help="Run the agent with a goal",
    )
    run_parser.add_argument(
        "goal",
        nargs="*",
        help="Goal for the coding agent",
    )
    run_parser.add_argument(
        "--workspace",
        help=(
            "Target project directory. "
            "Defaults to configured workspace."
        ),
    )
    build_parser = sub.add_parser(
        "build",
        help="Build a project using the multi-agent system",
    )
    build_parser.add_argument(
        "goal",
        nargs="*",
        help="Goal for the coding agent",
    )
    build_parser.add_argument(
        "--workspace",
        help=(
            "Target project directory. "
            "Defaults to configured workspace."
        ),
    )

    sub.add_parser(
        "setup",
        help="Run the first-time setup wizard",
    )
    sub.add_parser(
        "config",
        help="Print the current configuration",
    )
    sub.add_parser(
        "doctor",
        help="Run environment diagnostics",
    )
    memory_parser = sub.add_parser(
        "memory",
        help="Show project memory",
    )
    memory_parser.add_argument(
        "--workspace",
        help="Project directory containing .rica_memory.json",
    )
    logs_parser = sub.add_parser(
        "logs",
        help="List available workspace logs",
    )
    logs_parser.add_argument(
        "--workspace",
        help="Project directory containing .rica_logs",
    )
    search_parser = sub.add_parser(
        "search",
        help="Perform semantic code search in the project",
    )
    search_parser.add_argument(
        "query",
        help="Search query",
    )
    search_parser.add_argument(
        "--workspace",
        help="Project directory to search",
    )
    return parser


def _run_agent(
    goal: str,
    workspace: str | None,
    config: dict[str, str | None],
) -> int:
    if config.get("workspace"):
        os.environ["RICA_WORKSPACE"] = str(
            config["workspace"]
        )

    agent = RicaAgent(
        {
            "api_key": config["api_key"],
            "model": config.get("model")
            or DEFAULT_MODEL,
            "event_callback": _print_activity,
        }
    )
    result = agent.run(goal, workspace)
    print(
        json.dumps(
            {
                "success": result.success,
                "workspace": result.workspace_dir,
                "files_created": result.files_created,
                "files_modified": result.files_modified,
                "summary": result.summary,
                "error": result.error,
            },
            indent=2,
        )
    )
    return 0 if result.success else 1


def _show_memory(workspace: str | None) -> int:
    project_dir = _resolve_project_dir(workspace)
    payload = load_memory(project_dir / ".rica_memory.json")
    print(json.dumps(payload, indent=2))
    return 0


def _show_logs(workspace: str | None) -> int:
    project_dir = _resolve_project_dir(workspace)
    logs_dir = project_dir / ".rica_logs"
    payload = {
        "workspace": str(project_dir),
        "logs": (
            sorted(path.name for path in logs_dir.glob("*.log"))
            if logs_dir.exists()
            else []
        ),
    }
    print(json.dumps(payload, indent=2))
    return 0


def _run_search(
    query: str,
    workspace: str | None,
    config: dict[str, str | None],
) -> int:
    project_dir = _resolve_project_dir(workspace)
    reader = CodebaseReader()
    client = genai.Client(api_key=config["api_key"])
    results = reader.search(
        str(project_dir),
        query,
        client=client,
        model=config.get("model") or DEFAULT_MODEL,
    )
    print(
        json.dumps(
            {
                "workspace": str(project_dir),
                "query": query,
                "results": results,
            },
            indent=2,
        )
    )
    return 0


def _print_greeting(
    config: dict[str, str | None],
) -> None:
    name = config.get("name") or "there"
    hour = datetime.now().hour
    if hour < 12:
        greeting = "Good morning"
    elif hour < 18:
        greeting = "Good afternoon"
    else:
        greeting = "Good evening"

    print(f"{greeting} {name}.\n")
    print("What would you like me to build today?\n")


def _print_activity(
    *,
    agent: str,
    action: str,
    result: str,
) -> None:
    messages = {
        ("planner", "planning"): "📋 Planning project...",
        ("planner", "planned"): "✅ Created {} tasks",
        ("coder", "writing_code"): "👨‍💻 Writing code...",
        ("reviewer", "revision_requested"): (
            "🔍 Reviewer requested revisions..."
        ),
        ("reviewer", "approved"): "✅ Review complete.",
        ("reviewer", "skipped"): "⏭️ Review skipped.",
        ("executor", "running_command"): "🚀 Running: {}",
        ("debugger", "debugging"): "🐛 Fixing errors...",
        ("debugger", "fixing_tests"): (
            "🧪 Fixing failing tests..."
        ),
        ("tester", "running_tests"): "🧪 Running tests...",
        ("tester", "tests_passed"): "✅ Tests passed.",
    }
    
    # Format messages with dynamic content
    if (agent, action) == ("planner", "planned"):
        message = messages[(agent, action)].format(result)
    elif (agent, action) == ("executor", "running_command"):
        message = messages[(agent, action)].format(result[:50] + "..." if len(result) > 50 else result)
    else:
        message = messages.get(
            (agent, action),
            f"[{agent}] {action}: {result}",
        )
    
    print(message)


def _resolve_project_dir(
    workspace: str | None,
) -> Path:
    target = Path(workspace) if workspace else Path.cwd()
    return target.resolve()


if __name__ == "__main__":
    raise SystemExit(main())
