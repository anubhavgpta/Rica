"""Git repository management for RICA autonomous development."""

import subprocess
import json
from pathlib import Path
from typing import List, Optional, Dict, Any
from loguru import logger

from rica.logging_utils import get_component_logger

git_logger = get_component_logger("git_manager")


class GitManager:
    """Manages Git repository operations for RICA workspaces."""
    
    def __init__(self, workspace_dir: str):
        self.workspace_dir = Path(workspace_dir)
        self.git_dir = self.workspace_dir / ".git"
        
    def _run_git_command(self, args: List[str], capture_output: bool = True) -> subprocess.CompletedProcess:
        """Run a git command and return the result."""
        try:
            cmd = ["git"] + args
            result = subprocess.run(
                cmd,
                cwd=self.workspace_dir,
                capture_output=capture_output,
                text=True,
                timeout=30
            )
            
            if capture_output:
                git_logger.debug(f"[git] {' '.join(cmd)} -> {result.returncode}")
                if result.stdout:
                    git_logger.debug(f"[git] stdout: {result.stdout.strip()}")
                if result.stderr:
                    git_logger.debug(f"[git] stderr: {result.stderr.strip()}")
            
            return result
            
        except subprocess.TimeoutExpired:
            git_logger.error(f"[git] Command timed out: {' '.join(args)}")
            raise
        except Exception as e:
            git_logger.error(f"[git] Command failed: {' '.join(args)} - {e}")
            raise
    
    def is_git_repository(self) -> bool:
        """Check if the workspace is a git repository."""
        return self.git_dir.exists()
    
    def init_repo(self) -> bool:
        """Initialize a git repository in the workspace."""
        try:
            if self.is_git_repository():
                git_logger.info("[git] Repository already exists")
                return True
            
            result = self._run_git_command(["init"])
            if result.returncode == 0:
                # Configure git user if not set
                self._configure_git_user()
                
                # Create initial commit if there are files
                if any(self.workspace_dir.iterdir()):
                    self._create_initial_commit()
                
                git_logger.info(f"[git] Initialized repository in {self.workspace_dir}")
                return True
            else:
                git_logger.error(f"[git] Failed to initialize repository: {result.stderr}")
                return False
                
        except Exception as e:
            git_logger.error(f"[git] Repository initialization failed: {e}")
            return False
    
    def _configure_git_user(self):
        """Configure git user if not already set."""
        try:
            # Check if user name is configured
            name_result = self._run_git_command(["config", "user.name"])
            if not name_result.stdout.strip():
                self._run_git_command(["config", "user.name", "RICA Autonomous Developer"])
            
            # Check if user email is configured
            email_result = self._run_git_command(["config", "user.email"])
            if not email_result.stdout.strip():
                self._run_git_command(["config", "user.email", "rica@autonomous.dev"])
                
        except Exception as e:
            git_logger.warning(f"[git] Failed to configure git user: {e}")
    
    def _create_initial_commit(self):
        """Create initial commit with all files."""
        try:
            # Add all files
            add_result = self._run_git_command(["add", "."])
            if add_result.returncode != 0:
                git_logger.warning(f"[git] Failed to add files: {add_result.stderr}")
                return
            
            # Create initial commit
            commit_result = self._run_git_command(["commit", "-m", "Initial RICA project setup"])
            if commit_result.returncode == 0:
                git_logger.info("[git] Created initial commit")
            else:
                git_logger.warning(f"[git] Failed to create initial commit: {commit_result.stderr}")
                
        except Exception as e:
            git_logger.error(f"[git] Initial commit failed: {e}")
    
    def commit_changes(self, message: str, add_all: bool = True) -> bool:
        """Commit changes with a message."""
        try:
            if not self.is_git_repository():
                git_logger.warning("[git] Not a git repository, skipping commit")
                return False
            
            # Stage changes
            if add_all:
                add_result = self._run_git_command(["add", "."])
                if add_result.returncode != 0:
                    git_logger.error(f"[git] Failed to stage changes: {add_result.stderr}")
                    return False
            
            # Check if there are changes to commit
            status_result = self._run_git_command(["status", "--porcelain"])
            if not status_result.stdout.strip():
                git_logger.info("[git] No changes to commit")
                return True
            
            # Commit changes
            commit_result = self._run_git_command(["commit", "-m", message])
            if commit_result.returncode == 0:
                git_logger.info(f"[git] Committed changes: {message}")
                return True
            else:
                git_logger.error(f"[git] Failed to commit: {commit_result.stderr}")
                return False
                
        except Exception as e:
            git_logger.error(f"[git] Commit failed: {e}")
            return False
    
    def create_branch(self, branch_name: str) -> bool:
        """Create and switch to a new branch."""
        try:
            if not self.is_git_repository():
                git_logger.warning("[git] Not a git repository, cannot create branch")
                return False
            
            # Check if branch already exists
            branch_result = self._run_git_command(["branch", "--list", branch_name])
            if branch_result.stdout.strip():
                git_logger.info(f"[git] Branch {branch_name} already exists")
                return self.switch_branch(branch_name)
            
            # Create and switch to new branch
            result = self._run_git_command(["checkout", "-b", branch_name])
            if result.returncode == 0:
                git_logger.info(f"[git] Created and switched to branch: {branch_name}")
                return True
            else:
                git_logger.error(f"[git] Failed to create branch {branch_name}: {result.stderr}")
                return False
                
        except Exception as e:
            git_logger.error(f"[git] Branch creation failed: {e}")
            return False
    
    def switch_branch(self, branch_name: str) -> bool:
        """Switch to an existing branch."""
        try:
            if not self.is_git_repository():
                return False
            
            result = self._run_git_command(["checkout", branch_name])
            if result.returncode == 0:
                git_logger.info(f"[git] Switched to branch: {branch_name}")
                return True
            else:
                git_logger.error(f"[git] Failed to switch to branch {branch_name}: {result.stderr}")
                return False
                
        except Exception as e:
            git_logger.error(f"[git] Branch switch failed: {e}")
            return False
    
    def current_branch(self) -> str:
        """Get the current branch name."""
        try:
            if not self.is_git_repository():
                return "main"
            
            result = self._run_git_command(["rev-parse", "--abbrev-ref", "HEAD"])
            if result.returncode == 0:
                branch = result.stdout.strip()
                git_logger.debug(f"[git] Current branch: {branch}")
                return branch or "main"
            else:
                git_logger.warning(f"[git] Failed to get current branch: {result.stderr}")
                return "main"
                
        except Exception as e:
            git_logger.error(f"[git] Failed to get current branch: {e}")
            return "main"
    
    def get_status(self) -> Dict[str, Any]:
        """Get repository status information."""
        try:
            if not self.is_git_repository():
                return {"is_repo": False, "branch": "main", "status": "Not a git repository"}
            
            # Get current branch
            branch = self.current_branch()
            
            # Get status
            status_result = self._run_git_command(["status", "--porcelain"])
            status_lines = status_result.stdout.strip().splitlines() if status_result.stdout else []
            
            # Parse status
            modified = []
            added = []
            deleted = []
            untracked = []
            
            for line in status_lines:
                if len(line) >= 3:
                    status_code = line[:2]
                    file_path = line[3:]
                    
                    if status_code[0] in ['M', ' ']:
                        if status_code[1] == 'M':
                            modified.append(file_path)
                        elif status_code[1] == 'A':
                            added.append(file_path)
                        elif status_code[1] == 'D':
                            deleted.append(file_path)
                        elif status_code == '??':
                            untracked.append(file_path)
            
            return {
                "is_repo": True,
                "branch": branch,
                "modified": modified,
                "added": added,
                "deleted": deleted,
                "untracked": untracked,
                "has_changes": bool(status_lines)
            }
            
        except Exception as e:
            git_logger.error(f"[git] Failed to get status: {e}")
            return {"is_repo": False, "error": str(e)}
    
    def get_commit_history(self, limit: int = 10) -> List[Dict[str, str]]:
        """Get recent commit history."""
        try:
            if not self.is_git_repository():
                return []
            
            result = self._run_git_command([
                "log", 
                f"--oneline", 
                f"-n{limit}", 
                "--pretty=format:%H|%h|%s|%an|%ad",
                "--date=iso"
            ])
            
            if result.returncode != 0:
                return []
            
            commits = []
            for line in result.stdout.strip().splitlines():
                parts = line.split('|')
                if len(parts) >= 5:
                    commits.append({
                        "hash": parts[0],
                        "short_hash": parts[1],
                        "message": parts[2],
                        "author": parts[3],
                        "date": parts[4]
                    })
            
            return commits
            
        except Exception as e:
            git_logger.error(f"[git] Failed to get commit history: {e}")
            return []
    
    def has_uncommitted_changes(self) -> bool:
        """Check if there are uncommitted changes."""
        status = self.get_status()
        return status.get("has_changes", False)
