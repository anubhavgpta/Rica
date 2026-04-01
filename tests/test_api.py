"""Smoke tests for rica.api — no LLM calls, only structural checks."""
import importlib
import inspect
import rica.api as api_module

EXPECTED_FUNCTIONS = [
    "plan", "approve_plan", "build", "run", "check",
    "debug", "review", "fix", "explain", "refactor",
    "generate_tests", "rebuild",
    "get_session", "list_sessions", "get_plan", "get_builds",
    "get_executions", "get_reviews", "get_explanations",
    "get_refactors", "get_test_generations", "get_rebuild_history",
]

def test_all_functions_exported():
    for name in EXPECTED_FUNCTIONS:
        assert hasattr(api_module, name), f"Missing: {name}"
        assert callable(getattr(api_module, name)), f"Not callable: {name}"

def test_no_rich_imports():
    source = inspect.getsource(api_module)
    assert "from rich" not in source
    assert "import rich" not in source

def test_no_sys_exit():
    source = inspect.getsource(api_module)
    assert "sys.exit" not in source
