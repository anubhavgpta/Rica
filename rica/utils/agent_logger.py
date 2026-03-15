"""Agent-specific logging system for RICA."""

import os
from pathlib import Path
from typing import Optional
from loguru import logger
from rica.logging_utils import get_component_logger


class AgentLogger:
    """Manages agent-specific log files in workspace .rica_logs directory."""
    
    def __init__(self, workspace_dir: str):
        self.workspace_dir = Path(workspace_dir)
        self.logs_dir = self.workspace_dir / ".rica_logs"
        self.logs_dir.mkdir(exist_ok=True)
        
        # Configure agent-specific log files
        self.agent_loggers = {}
        self._setup_agent_loggers()
    
    def _setup_agent_loggers(self):
        """Set up separate log files for each agent."""
        agent_names = [
            "planner", "coder", "executor", "debugger", 
            "test", "reviewer", "dependency", "agent"
        ]
        
        # Remove default handlers to avoid duplication
        logger.remove()
        
        # Add console handler for main output
        logger.add(
            sink=lambda msg: print(msg, end=""),
            level="INFO",
            format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>: <white>{message}</white>",
            colorize=True
        )
        
        # Add file handlers for each agent
        for agent_name in agent_names:
            log_file = self.logs_dir / f"{agent_name}.log"
            
            # Create agent-specific logger
            agent_logger = get_component_logger(agent_name)
            
            # Add file handler for this agent
            logger.add(
                sink=str(log_file),
                level="DEBUG",
                format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
                rotation="10 MB",
                retention="5 days",
                filter=lambda record: record["extra"].get("agent_name") == agent_name,
                serialize=False
            )
            
            self.agent_loggers[agent_name] = agent_logger
    
    def get_logger(self, agent_name: str):
        """Get logger for a specific agent."""
        if agent_name not in self.agent_loggers:
            # Fallback to creating a new logger
            return get_component_logger(agent_name)
        
        return self.agent_loggers[agent_name]
    
    def log_agent_activity(
        self, 
        agent_name: str, 
        action: str, 
        details: str = "",
        level: str = "INFO"
    ):
        """Log agent activity with standardized format."""
        agent_logger = self.get_logger(agent_name)
        
        # Use positional arguments to avoid Loguru formatting issues
        message = "[{}] {}".format(agent_name, action)
        if details:
            message += ": {}".format(details)
        
        log_method = getattr(agent_logger, level.lower())
        
        log_method(
            message,
            extra={"agent_name": agent_name}
        )
    
    def log_task_start(self, agent_name: str, task_id: str, task_description: str):
        """Log the start of a task."""
        result = "ID=" + task_id + ", Description=" + (task_description[:100] + "..." if len(task_description) > 100 else task_description)
        self.log_agent_activity(agent_name, "TASK_START", result)

    def log_task_complete(self, agent_name: str, task_id: str, result: str = ""):
        """Log the completion of a task."""
        if result:
            details = "ID=" + task_id + ", Result=" + (result[:100] + "..." if len(result) > 100 else result)
        else:
            details = "ID=" + task_id
        self.log_agent_activity(agent_name, "TASK_COMPLETE", details)
    
    def log_error(self, agent_name: str, error: str, context: str = ""):
        """Log an error for an agent."""
        # Use string concatenation to avoid formatting issues
        details = "Error: " + error
        if context:
            details += ", Context: " + context
        
        self.log_agent_activity(agent_name, "ERROR", details, "ERROR")
    
    def log_dependency_action(self, action: str, packages: list, success: bool):
        """Log dependency-related actions."""
        status = "SUCCESS" if success else "FAILED"
        details = action + " " + ", ".join(packages) + " - " + status
        self.log_agent_activity("dependency", action, details)
    
    def get_log_summary(self) -> dict:
        """Get a summary of all agent logs."""
        summary = {}
        
        for log_file in self.logs_dir.glob("*.log"):
            if log_file.is_file():
                try:
                    content = log_file.read_text(encoding="utf-8")
                    lines = content.splitlines()
                    
                    agent_name = log_file.stem
                    summary[agent_name] = {
                        "file": str(log_file),
                        "lines": len(lines),
                        "size_bytes": log_file.stat().st_size,
                        "last_modified": log_file.stat().st_mtime
                    }
                except Exception as e:
                    summary[agent_name] = {"error": str(e)}
        
        return summary
    
    def cleanup_old_logs(self, days: int = 7):
        """Clean up log files older than specified days."""
        import time
        
        cutoff_time = time.time() - (days * 24 * 60 * 60)
        
        for log_file in self.logs_dir.glob("*.log"):
            if log_file.stat().st_mtime < cutoff_time:
                try:
                    log_file.unlink()
                    logger.info(f"[agent_logger] Cleaned up old log: {log_file.name}")
                except Exception as e:
                    logger.error(f"[agent_logger] Failed to clean up {log_file.name}: {e}")


# Global instance management
_agent_logger_instances = {}


def get_agent_logger(workspace_dir: str) -> AgentLogger:
    """Get or create an AgentLogger instance for a workspace."""
    workspace_path = str(Path(workspace_dir).resolve())
    
    if workspace_path not in _agent_logger_instances:
        _agent_logger_instances[workspace_path] = AgentLogger(workspace_dir)
    
    return _agent_logger_instances[workspace_path]


def setup_workspace_logging(workspace_dir: str):
    """Set up agent logging for a workspace."""
    agent_logger = get_agent_logger(workspace_dir)
    return agent_logger
