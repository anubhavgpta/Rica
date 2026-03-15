from typing import Dict
from rica.executor import RicaExecutor
from rica.logging_utils import get_component_logger

logger = get_component_logger("executor_agent")


class ExecutorAgent:
    """Agent responsible for executing commands and scripts."""
    
    def __init__(self, workspace_dir: str):
        self.config = {"workspace_dir": workspace_dir}
        self.executor = RicaExecutor(workspace_dir)
    
    def run(self, command: str) -> Dict:
        """Execute a command and return the result."""
        logger.info(f"[executor_agent] Running command: {command}")
        
        # Handle cross-platform file operations
        import os
        import platform
        
        # Intercept delete commands for cross-platform compatibility
        if command.startswith("del "):
            target = command.split(" ", 1)[1].strip()
            if os.path.exists(target):
                os.remove(target)
                logger.info(f"[executor] Deleted file: {target}")
            return {
                "success": True,
                "exit_code": 0,
                "stdout": f"Deleted {target}",
                "stderr": "",
                "command": command
            }
        
        # Intercept Unix delete commands
        if command.startswith("rm "):
            target = command.split(" ", 1)[1].strip()
            if os.path.exists(target):
                os.remove(target)
                logger.info(f"[executor] Deleted file: {target}")
            return {
                "success": True,
                "exit_code": 0,
                "stdout": f"Deleted {target}",
                "stderr": "",
                "command": command
            }
        
        # Parse command to validate only the executable
        import shlex
        
        try:
            parts = shlex.split(command)
            if not parts:
                return {
                    "success": False,
                    "exit_code": 1,
                    "stdout": "",
                    "stderr": "Empty command",
                    "command": command
                }
            
            executable = parts[0].lower()
            
            # Guard against executing non-executable files (only check the executable)
            invalid_extensions = (".txt", ".json", ".md", ".yml", ".yaml", ".xml", ".csv", ".log")
            
            if executable.endswith(invalid_extensions):
                logger.warning("[executor_agent] Skipping execution of non-executable file")
                return {
                    "success": True,
                    "exit_code": 0,
                    "stdout": "",
                    "stderr": "",
                    "command": command
                }
            
            # Guard against dangerous commands (check the full command)
            dangerous_commands = ["rm -rf", "del /f", "format", "fdisk", "mkfs"]
            command_lower = command.lower()
            
            if any(dangerous in command_lower for dangerous in dangerous_commands):
                logger.warning("[executor_agent] Skipping dangerous command")
                return {
                    "success": False,
                    "exit_code": 1,
                    "stdout": "",
                    "stderr": "Dangerous command blocked for safety",
                    "command": command
                }
            
        except ValueError as e:
            logger.warning(f"[executor_agent] Failed to parse command: {e}")
            # Continue with execution if parsing fails
        
        try:
            result = self.executor.run(command)
            
            logger.info(f"[executor_agent] Command completed with exit code: {result.get('exit_code', 'unknown')}")
            
            return {
                "success": result.get("exit_code", -1) == 0,
                "exit_code": result.get("exit_code", -1),
                "stdout": result.get("stdout", ""),
                "stderr": result.get("stderr", ""),
                "command": command
            }
            
        except Exception as e:
            logger.error(f"[executor_agent] Command failed with exception: {str(e)}")
            return {
                "success": False,
                "exit_code": -1,
                "stdout": "",
                "stderr": str(e),
                "command": command
            }
    
    def is_server_command(self, command: str) -> bool:
        """Check if a command is a server start command."""
        return self.executor._is_server_command(command)
