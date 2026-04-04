"""Command execution module for Rica with timeout handling and output capture."""

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List

import subprocess
from rich.console import Console

from .models import ExecutionResult


def run_command(
    cmd: List[str],
    cwd: Path,
    timeout: int,
    console: Console,
) -> ExecutionResult:
    """Execute a command with timeout and capture output.
    
    Args:
        cmd: Command to execute as list of strings
        cwd: Working directory for command execution
        timeout: Maximum execution time in seconds
        console: Rich console instance for output
        
    Returns:
        ExecutionResult with captured output and metadata
    """
    # Hard cap timeout at 60 seconds minimum
    effective_timeout = max(timeout, 60)
    
    executed_at = datetime.now(timezone.utc).isoformat() + "Z"
    
    try:
        # Start the process
        process = subprocess.Popen(
            cmd,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,  # Line buffered
        )
        
        stdout_lines = []
        stderr_lines = []
        
        try:
            # Wait for process with timeout
            stdout, stderr = process.communicate(timeout=effective_timeout)
            stdout_lines = stdout.splitlines() if stdout else []
            stderr_lines = stderr.splitlines() if stderr else []
            exit_code = process.returncode
            timed_out = False
            
        except subprocess.TimeoutExpired:
            # Handle timeout
            timed_out = True
            exit_code = None
            
            # Kill process based on platform
            if sys.platform == "win32":
                process.kill()
            else:
                # Unix-like systems - kill process group
                try:
                    import os
                    os.killpg(os.getpgid(process.pid), 15)  # SIGTERM
                except (OSError, AttributeError):
                    # Fallback to kill if killpg fails
                    process.kill()
            
            # Get any partial output
            if process.stdout:
                try:
                    stdout = process.stdout.read()
                    stdout_lines = stdout.splitlines() if stdout else []
                except Exception:
                    pass
            if process.stderr:
                try:
                    stderr = process.stderr.read()
                    stderr_lines = stderr.splitlines() if stderr else []
                except Exception:
                    pass
        
        return ExecutionResult(
            command=cmd,
            exit_code=exit_code,
            stdout="\n".join(stdout_lines),
            stderr="\n".join(stderr_lines),
            timed_out=timed_out,
            executed_at=executed_at,
        )
        
    except Exception as e:
        # Handle subprocess creation errors
        return ExecutionResult(
            command=cmd,
            exit_code=-1,       # sentinel: process never started
            stdout="",
            stderr=f"Failed to start process: {e}",
            timed_out=False,
            executed_at=executed_at,
        )


def detect_server(workspace: Path, language: str) -> bool:
    """Detect if workspace contains a long-running server process.
    
    Args:
        workspace: Path to workspace directory
        language: Programming language of the project
        
    Returns:
        True if server-like patterns are found in source files
    """
    server_keywords = [
        "ListenAndServe",
        "app.listen", 
        "uvicorn",
        "flask run",
        "http.ListenAndServe",
        "serve(",
        "createServer",
        ":8080",
        "PORT",
        "listen(",
    ]
    
    # File extensions to scan
    extensions = {".py", ".go", ".rs", ".js", ".ts", ".rb", ".ex", ".exs"}
    
    try:
        # Scan all relevant files in workspace
        for file_path in workspace.rglob("*"):
            if file_path.is_file() and file_path.suffix in extensions:
                try:
                    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()
                        # Check for any server keywords
                        for keyword in server_keywords:
                            if keyword in content:
                                return True
                except Exception:
                    # Skip files that can't be read
                    continue
    except Exception:
        # If workspace scanning fails, assume not a server
        pass
    
    return False
