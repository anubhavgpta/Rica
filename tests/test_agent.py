import os
import pytest
from pathlib import Path
from rica import RicaAgent, RicaResult

def test_import():
    assert RicaAgent is not None
    assert RicaResult is not None

def test_instantiate():
    agent = RicaAgent({
        "api_key": "test",
        "model": "gemini-2.5-flash"
    })
    assert agent is not None
    assert agent.planner is not None
    assert agent.codegen is not None
    assert agent.debugger is not None

def test_run_stub():
    agent = RicaAgent({
        "api_key": "test",
        "model": "gemini-2.5-flash"
    })
    result = agent.run(
        "create hello world script",
        workspace_name="test_ws"
    )
    assert isinstance(result, RicaResult)
    assert result.goal == \
        "create hello world script"

REAL_KEY = os.environ.get("GEMINI_API_KEY", "")

@pytest.mark.skipif(
    not REAL_KEY,
    reason="GEMINI_API_KEY not set"
)
def test_real_codegen():
    agent = RicaAgent({
        "api_key": REAL_KEY,
        "model": "gemini-2.5-flash",
    })
    result = agent.run(
        "write a python script that prints "
        "'Hello from Rica' to stdout",
        workspace_name="test_hello"
    )
    assert result.success
    assert len(result.files_created) > 0
    # Verify file exists
    assert Path(
        result.files_created[0]
    ).exists()
