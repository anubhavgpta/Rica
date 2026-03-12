import subprocess
from loguru import logger

class RicaExecutor:
    """
    Runs code in workspace_dir.
    Captures stdout, stderr, exit code.
    """

    SERVER_COMMANDS = [
        'flask run',
        'uvicorn',
        'gunicorn',
        'python -m flask',
        'npm start',
        'node server',
        'python -m http.server',
        'manage.py runserver',
        'fastapi run',
    ]

    def __init__(self, workspace_dir: str):
        self.workspace_dir = workspace_dir

    def _is_server_command(
        self, command: str
    ) -> bool:
        lower = command.lower().strip()
        return any(
            s in lower
            for s in self.SERVER_COMMANDS
        )

    def run(
        self, command: str
    ) -> dict:
        """
        Returns dict with keys:
            stdout, stderr, exit_code, success
        Executes command in workspace_dir with 60s timeout.
        Skips server commands and treats as success.
        """
        logger.debug(
            f"[executor] Running: {command}"
        )
        
        # Check for server commands first
        if self._is_server_command(command):
            logger.info(
                f"[executor] Server command detected "
                f"— skipping execution: {command}"
            )
            return {
                "stdout": (
                    f"Server command '{command}' "
                    f"recognized — skipping live "
                    f"execution in agentic context."
                ),
                "stderr": "",
                "exit_code": 0,
                "success": True,
            }
        
        try:
            result = subprocess.run(
                command,
                shell=True,
                cwd=self.workspace_dir,
                capture_output=True,
                text=True,
                timeout=60,
            )
            
            return {
                "stdout": result.stdout,
                "stderr": result.stderr,
                "exit_code": result.returncode,
                "success": result.returncode == 0,
            }
            
        except subprocess.TimeoutExpired:
            logger.warning(f"[executor] Command timed out: {command}")
            return {
                "stdout": "",
                "stderr": "Command timed out after 60s",
                "exit_code": -1,
                "success": False,
            }
        except Exception as e:
            logger.error(f"[executor] Command failed: {e}")
            return {
                "stdout": "",
                "stderr": str(e),
                "exit_code": -1,
                "success": False,
            }
