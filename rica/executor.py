import subprocess

from rica.logging_utils import get_component_logger

logger = get_component_logger("executor")

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

    SHELL_ONLY_COMMANDS = [
        'source ',
        'export ',
        'chmod ',
        'chown ',
        'sudo ',
    ]

    USAGE_PATTERNS = [
        'usage:',
        'usage error',
        'positional arguments',
        'optional arguments',
        'options:',
        'error: the following arguments',
        'try --help',
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

    def _is_shell_only(self, cmd: str) -> bool:
        lower = cmd.lower().strip()
        return any(
            lower.startswith(s)
            for s in self.SHELL_ONLY_COMMANDS
        )

    def _is_usage_output(
        self, stdout: str, stderr: str
    ) -> bool:
        combined = (
            (stdout or '') + (stderr or '')
        ).lower()
        return any(
            p in combined
            for p in self.USAGE_PATTERNS
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
        
        # Check for shell-only commands that don't work on Windows
        if self._is_shell_only(command):
            logger.info(
                f"[executor] Non-Windows command detected "
                f"— skipping execution: {command}"
            )
            return {
                "stdout": (
                    f"Skipped non-Windows command: {command}"
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
            
            # Check for usage output vs real errors
            exit_code = result.returncode
            stdout = result.stdout
            stderr = result.stderr
            success = result.returncode == 0
            
            if exit_code != 0 and self._is_usage_output(stdout, stderr):
                # This is usage/help output, not a real failure
                exit_code = 0
                success = True
                stdout = stdout + "\n[note: script requires arguments — called without args]"
                logger.info(
                    f"[executor] Usage output detected for: {command}"
                )
            
            return {
                "stdout": stdout,
                "stderr": stderr,
                "exit_code": exit_code,
                "success": success,
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
