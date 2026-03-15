import json
import subprocess
from pathlib import Path

from rica import cli
from rica import config as config_module
from rica.result import RicaResult


def test_cli_runs():
    """Test that CLI command runs without errors."""
    result = subprocess.run(["python", "-m", "rica.cli", "--help"], capture_output=True, text=True)
    assert result.returncode == 0
    assert "RICA" in result.stdout or "rica" in result.stdout


def test_save_and_load_config(
    monkeypatch, tmp_path
):
    config_path = (
        tmp_path / ".rica" / "config.json"
    )
    monkeypatch.setattr(
        config_module,
        "get_config_path",
        lambda: config_path,
    )

    saved_path = config_module.save_config(
        {
            "name": "Alex",
            "api_key": "secret-key",
            "model": "",
            "workspace": "~/rica_workspace",
        }
    )
    loaded = config_module.load_config()

    assert saved_path == config_path
    assert loaded["name"] == "Alex"
    assert loaded["api_key"] == "secret-key"
    assert loaded["model"] == "gemini-2.5-flash"
    assert loaded["workspace"]


def test_cli_run_shorthand(
    monkeypatch, capsys
):
    captured = {}

    class FakeAgent:
        def __init__(self, config):
            captured["config"] = config

        def run(self, goal, workspace=None):
            captured["goal"] = goal
            captured["workspace_arg"] = workspace
            return RicaResult(
                success=True,
                goal=goal,
                workspace_dir="fake-ws",
                files_created=["app.py"],
                files_modified=[],
                summary="done",
            )

    monkeypatch.setattr(
        cli,
        "ensure_setup",
        lambda: {
            "name": "Alex",
            "api_key": "abc123",
            "model": "gemini-2.5-flash",
            "workspace": "C:/tmp/rica",
        },
    )
    monkeypatch.setattr(cli, "RicaAgent", FakeAgent)

    exit_code = cli.main(
        ["build", "a", "flask", "todo", "api"]
    )
    stdout = capsys.readouterr().out
    output = json.loads(
        stdout[stdout.index("{") :]
    )

    assert exit_code == 0
    assert captured["goal"] == "build a flask todo api"
    assert captured["config"]["api_key"] == "abc123"
    assert "event_callback" in captured["config"]
    assert output["success"] is True


def test_cli_config_command_redacts_key(
    monkeypatch, capsys
):
    monkeypatch.setattr(
        cli,
        "ensure_setup",
        lambda: {
            "name": "Alex",
            "api_key": "1234567890",
            "model": "gemini-2.5-flash",
            "workspace": None,
        },
    )
    monkeypatch.setattr(
        cli,
        "get_config_path",
        lambda: Path("/tmp/.rica/config.json"),
    )

    exit_code = cli.main(["config"])
    payload = json.loads(
        capsys.readouterr().out
    )

    assert exit_code == 0
    assert payload["api_key"] == "1234...7890"


def test_doctor_collect_diagnostics(
    monkeypatch, tmp_path
):
    from rica import doctor

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    config_path = tmp_path / ".rica" / "config.json"

    monkeypatch.setattr(
        doctor, "get_config_path", lambda: config_path
    )
    monkeypatch.setattr(
        doctor,
        "load_config",
        lambda: {
            "name": "Alex",
            "api_key": "token",
            "model": "gemini-2.5-flash",
            "workspace": str(workspace),
        },
    )
    monkeypatch.setattr(
        doctor,
        "_check_gemini_connectivity",
        lambda config: True,
    )
    monkeypatch.setattr(
        doctor.importlib.util,
        "find_spec",
        lambda name: object(),
    )
    config_path.parent.mkdir()
    config_path.write_text("{}", encoding="utf-8")

    checks = doctor.collect_diagnostics()

    assert all(ok for _, ok, _ in checks)


def test_cli_memory_command(
    monkeypatch, tmp_path, capsys
):
    monkeypatch.setattr(
        cli,
        "ensure_setup",
        lambda: {
            "name": "Alex",
            "api_key": "abc123",
            "model": "gemini-2.5-flash",
            "workspace": None,
        },
    )
    (tmp_path / ".rica_memory.json").write_text(
        json.dumps({"goal": "build api"}),
        encoding="utf-8",
    )

    exit_code = cli.main(
        ["memory", "--workspace", str(tmp_path)]
    )
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["goal"] == "build api"


def test_cli_logs_command(
    monkeypatch, tmp_path, capsys
):
    monkeypatch.setattr(
        cli,
        "ensure_setup",
        lambda: {
            "name": "Alex",
            "api_key": "abc123",
            "model": "gemini-2.5-flash",
            "workspace": None,
        },
    )
    logs_dir = tmp_path / ".rica_logs"
    logs_dir.mkdir()
    (logs_dir / "agent.log").write_text("", encoding="utf-8")

    exit_code = cli.main(
        ["logs", "--workspace", str(tmp_path)]
    )
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["logs"] == ["agent.log"]


def test_cli_search_command(
    monkeypatch, tmp_path, capsys
):
    monkeypatch.setattr(
        cli,
        "ensure_setup",
        lambda: {
            "name": "Alex",
            "api_key": "abc123",
            "model": "gemini-2.5-flash",
            "workspace": None,
        },
    )

    class FakeReader:
        def search(self, project_dir, query, client=None, model=None):
            return [
                {
                    "path": "app.py",
                    "score": 0.9,
                    "snippet": "def app(): ...",
                    "start_line": 1,
                }
            ]

    monkeypatch.setattr(cli, "CodebaseReader", FakeReader)

    class FakeClient:
        def __init__(self, api_key):
            self.api_key = api_key

    monkeypatch.setattr(cli.genai, "Client", FakeClient)

    exit_code = cli.main(
        ["search", "app factory", "--workspace", str(tmp_path)]
    )
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["results"][0]["path"] == "app.py"
