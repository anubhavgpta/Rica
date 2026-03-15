import json
import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import google.genai as genai

from rica.agents import (
    CoderAgent,
    DebuggerAgent,
    ExecutorAgent,
    PlannerAgent,
    ReviewerAgent,
    TestAgent,
)
from rica.core.task_queue import TaskQueue
from rica.core.worker_pool import WorkerPool
from rica.executor import RicaExecutor
from rica.logging_utils import (
    configure_workspace_logging,
    get_component_logger,
)
from rica.memory import ProjectMemory
from rica.reader import CodebaseReader, scan_project_structure
from rica.result import RicaResult
from rica.tools import ToolRegistry
from rica.utils.agent_logger import get_agent_logger
from rica.utils.dependency_manager import DependencyManager
from rica.utils.paths import ensure_workspace
from rica.workspace import detect_workspace_metadata
from rica.core.repo_graph import RepoGraph
from rica.core.context_builder import ContextBuilder
import os

MAX_REVIEW_LOOPS = 3
MAX_REVIEW_DEPTH = 2

logger = get_component_logger("agent")


def classify_task_for_routing(task_description: str) -> str:
    """Classify task type to determine the best execution path."""
    desc = task_description.lower()
    
    if any(x in desc for x in ["delete", "remove", "rm"]):
        return "file_delete"
    
    if any(x in desc for x in ["install", "pip install", "requirements"]):
        return "dependency_install"
    
    if any(x in desc for x in ["run", "execute", "python"]):
        return "command_run"
    
    if any(x in desc for x in ["create", "write", "modify", "edit"]):
        return "code_generation"
    
    return "code_generation"


def classify_task_type(description: str) -> str:
    """Classify task type for proper routing."""
    desc = description.lower()
    
    if desc.startswith("delete") or desc.startswith("remove") or desc.startswith("rm"):
        return "delete"
    
    if desc.startswith("install") or "run" in desc or "execute" in desc:
        return "execute"
    
    if desc.startswith("create") or desc.startswith("write") or desc.startswith("modify") or desc.startswith("edit"):
        return "code"
    
    if desc.startswith("report"):
        return "report"
    
    return "unknown"


def validate_tasks(goal: str, tasks: list[dict]) -> list[dict]:
    """Validate that tasks are related to the user's goal."""
    goal_words = set(goal.lower().split())
    
    valid_tasks = []
    
    for task in tasks:
        task_words = set(task.get("description", "").lower().split())
        
        if goal_words.intersection(task_words):
            valid_tasks.append(task)
        else:
            logger.warning(f"[planner] Dropping unrelated task: {task.get('description', 'unknown')}")
    
    return valid_tasks


def extract_file_from_task(desc: str) -> str | None:
    """Extract file path from task description using regex."""
    import re
    
    # backticks
    matches = re.findall(r'`([^`]+)`', desc)
    if matches:
        return matches[0]

    # quotes
    matches = re.findall(r"'([^']+)'", desc)
    if matches:
        return matches[0]

    matches = re.findall(r'"([^"]+)"', desc)
    if matches:
        return matches[0]

    # fallback: detect .py or .txt
    matches = re.findall(r'([\w./-]+\.(py|txt|json|yaml|yml))', desc)
    if matches:
        return matches[0][0]

    return None


def classify_task(task_description: str) -> str:
    """Classify task type to determine the best execution path."""
    desc = task_description.lower()
    
    if any(x in desc for x in ["delete", "remove", "rm"]):
        return "file_delete"
    
    if any(x in desc for x in ["install", "pip install", "requirements"]):
        return "dependency_install"
    
    if any(x in desc for x in ["run", "execute", "python"]):
        return "command_run"
    
    if any(x in desc for x in ["create", "write", "modify", "edit"]):
        return "code_generation"
    
    return "code_generation"


class MultiAgentController:
    def __init__(self, config: dict):
        self.config = config
        self.max_iterations = int(
            config.get("max_iterations", 5)
        )
        self.max_fix_attempts = int(
            config.get("max_fix_attempts", 5)
        )
        self.max_test_iterations = int(
            config.get("max_test_iterations", 3)
        )
        self.enable_reviewer = config.get("enable_reviewer", True)
        self.progress_callback = config.get(
            "event_callback"
        )
        self.reader = CodebaseReader()
        self.tool_registry = ToolRegistry(
            reader=self.reader
        )
        self.planner_agent = PlannerAgent(config)
        self.coder_agent = CoderAgent(config)
        self.executor_agent = None  # Will be initialized with workspace
        self.reviewer_agent = ReviewerAgent(config)
        self.debugger_agent = DebuggerAgent(config)
        self.worker_pool = WorkerPool(size=1)
        self.dependency_manager = None  # Will be initialized with project
        self.agent_logger = None  # Will be initialized with workspace
        self.snapshot = None
        self.client = None
        self.logs_dir = None
        self.repo_graph = None  # Will be initialized with project
        self.context_builder = ContextBuilder()

    def run(
        self,
        goal: str,
        project_dir: str | None = None,
        workspace_name: str | None = None,
    ) -> RicaResult:
        self.start_time = time.time()
        
        workspace_name = self._sanitize_workspace_name(
            workspace_name
        )
        ws_name = workspace_name or (
            f"rica_{uuid.uuid4().hex[:8]}"
        )
        workspace_dir = str(
            ensure_workspace(ws_name)
        )
        resolved_project_dir = self._resolve_project_dir(
            project_dir, workspace_dir
        )
        self._ensure_logging(workspace_dir)

        # Initialize agent logging system
        self.agent_logger = get_agent_logger(workspace_dir)
        self.agent_logger.log_agent_activity("agent", "SESSION_START", f"Goal: {goal}")

        self.client = genai.Client(
            api_key=self.config["api_key"]
        )
        # Initialize executor agent with resolved project directory
        self.executor_agent = ExecutorAgent(resolved_project_dir)
        
        # Initialize dependency manager
        self.dependency_manager = DependencyManager(resolved_project_dir, self.executor_agent)
        
        # Initialize repository graph
        self.repo_graph = RepoGraph()
        self.repo_graph.index_project(resolved_project_dir)
        
        # Scan project structure for context
        project_structure = scan_project_structure(resolved_project_dir)
        logger.info(f"[agent] Project structure: {len(project_structure['python_files'])} files, "
                   f"{len(project_structure['dependencies'])} dependencies")
        metadata = detect_workspace_metadata(
            resolved_project_dir
        )
        self.snapshot = self.reader.snapshot(
            resolved_project_dir,
            goal,
            self.client,
            self.config["model"],
        )
        memory = ProjectMemory.load_or_create(
            goal=goal,
            workspace_dir=workspace_dir,
            project_dir=resolved_project_dir,
            snapshot_summary=self.snapshot.summary,
            project_summary=self.snapshot.summary,
            project_metadata=metadata.to_dict(),
        )
        memory.set_project_context(
            project_summary=self.snapshot.summary,
            project_metadata=metadata.to_dict(),
            dependencies=self._detect_dependencies(
                resolved_project_dir
            ),
        )
        queue = TaskQueue()

        self._emit(
            "planner",
            "planning",
            f"Planning project for goal: {goal}",
        )
        
        if self.agent_logger:
            self.agent_logger.log_agent_activity("planner", "PLANNING", f"Goal: {goal}")
        
        # Get workspace files to provide better context to planner
        workspace_files = []
        try:
            if os.path.exists(workspace_dir):
                workspace_files = os.listdir(workspace_dir)
        except Exception as e:
            logger.warning(f"[controller] Failed to list workspace files: {e}")
        
        tasks = self.planner_agent.plan(
            goal,
            self.snapshot,
            tool_names=self.tool_registry.names(),
            workspace_files=workspace_files,
        )
        
        # Validate tasks to prevent hallucinations
        original_count = len(tasks)
        tasks = validate_tasks(goal, tasks)
        if len(tasks) != original_count:
            logger.info(f"[planner] Validated tasks: {len(tasks)} (dropped {original_count - len(tasks)} unrelated)")
        
        queue.add_tasks(tasks)
        self._emit(
            "planner",
            "planned",
            f"Generated {len(tasks)} tasks",
        )
        
        if self.agent_logger:
            self.agent_logger.log_agent_activity("planner", "TASKS_GENERATED", f"Count: {len(tasks)}")
            for task in tasks:
                self.agent_logger.log_task_start("planner", str(task.get("id", "unknown")), task.get("description", ""))

        task_results = []
        review_attempts = 0
        iterations = 0  # Only count primary tasks
        
        while True:
            task = queue.next_task()
            if task is None:
                break

            # Check review depth
            task_id = str(task.get("id", ""))
            review_depth = task_id.count("-review-")
            
            # Only count primary tasks (not review tasks)
            if "-review-" not in task_id:
                iterations += 1
            
            if review_depth >= MAX_REVIEW_DEPTH:
                logger.warning("Review depth exceeded. Auto approving.")
                # Mark as completed to break the loop
                task_results.append({
                    "success": True,
                    "revision_tasks": [],
                    "files": [],
                    "error": None
                })
                continue

            result = self.worker_pool.execute_task(
                task,
                lambda current_task: self._process_task(
                    current_task,
                    memory,
                    workspace_dir,
                    resolved_project_dir,
                ),
            )
            task_results.append(result)
            
            # Check for revision requests
            if result.get("revision_tasks"):
                review_attempts += 1
                
                if review_attempts > MAX_REVIEW_LOOPS:
                    logger.warning("Review loop limit reached, approving task")
                    # Mark as completed to break the loop
                    result["success"] = True
                    result["revision_tasks"] = []
                else:
                    queue.add_tasks(
                        result.get("revision_tasks", []),
                        front=True,
                    )
            
            status = (
                "completed"
                if result.get("success", True)
                else "failed"
            )
            memory.save()
            memory.record_task(task, status)
            
            # Enhanced memory tracking
            if self.agent_logger:
                if result.get("files"):
                    memory.record_files_created(result.get("files", []))
                    self.agent_logger.log_agent_activity("memory", "FILES_CREATED", f"Count: {len(result.get('files', []))}")
            
            if result.get("error"):
                memory.record_error(
                    result["error"]
                )
                if self.agent_logger:
                    self.agent_logger.log_error("agent", result["error"], f"Task {task.get('id', 'unknown')}")

        test_result = self._run_test_phase(
            memory,
            workspace_dir,
            resolved_project_dir,
        )
        
        # Log session completion with correct iteration count and duration
        if self.agent_logger:
            duration = time.time() - self.start_time
            self.agent_logger.log_agent_activity("agent", "SESSION_COMPLETE", f"Iterations: {iterations}, Duration: {duration:.2f}s")
        
        # Add clear agent completion logging
        logger.info(f"[agent] Completed in {iterations} iterations")
        
        # Update memory with correct iteration count
        memory.iteration = iterations
        
        if not test_result["success"]:
            return RicaResult(
                success=False,
                goal=goal,
                workspace_dir=workspace_dir,
                files_created=memory.files_created,
                files_modified=memory.files_modified,
                error=test_result["error"],
                iterations=iterations,
            )

        return RicaResult(
            success=all(
                item.get("success", True)
                for item in task_results
            )
            and test_result["success"],
            goal=goal,
            workspace_dir=workspace_dir,
            files_created=memory.files_created,
            files_modified=memory.files_modified,
            summary=memory.summary(),
            iterations=iterations,
        )

    def _process_task(
        self,
        task: dict,
        memory: ProjectMemory,
        workspace_dir: str,
        project_dir: str,
    ) -> dict:
        memory.iteration += 1
        memory.save()
        
        task_id = str(task.get("id", "unknown"))
        task_desc = task.get("description", "")
        
        if self.agent_logger:
            self.agent_logger.log_task_start("agent", task_id, task_desc)
        
        self._emit(
            "worker",
            "task_started",
            task.get("description", ""),
        )

        if task.get("type") == "tool":
            result = self.tool_registry.run(
                task,
                workspace_dir,
                project_dir,
            )
            self._emit(
                "tool",
                task.get("tool", "unknown"),
                str(result.get("success")),
            )
            return {
                "success": result.get("success", False),
                "files": result.get("files", []),
                "revision_tasks": [],
                "error": None
                if result.get("success")
                else result.get("output", ""),
            }

        # Classify task type and route accordingly
        task_type = classify_task_for_routing(task_desc)
        
        # Handle report tasks (no execution needed)
        if task_desc.lower().startswith("report"):
            logger.info("[executor] Report-only task — skipping execution")
            return {
                "success": True,
                "files": [],
                "revision_tasks": [],
                "error": None
            }
        
        if task_type == "file_delete":
            # Extract file path using proper regex parsing
            file_path = extract_file_from_task(task_desc)
            
            # Try to find the file in workspace if not an absolute path
            if file_path and not os.path.isabs(file_path):
                full_path = os.path.join(workspace_dir, file_path)
                if os.path.exists(full_path):
                    file_path = full_path
            
            if file_path and os.path.exists(file_path):
                os.remove(file_path)
                logger.info(f"[executor] Deleted file: {file_path}")
                return {
                    "success": True,
                    "files": [],
                    "revision_tasks": [],
                    "error": None
                }
            else:
                # File not found - this is expected for report tasks, so treat as success
                logger.info(f"[executor] File already absent: {file_path}")
                return {
                    "success": True,
                    "files": [],
                    "revision_tasks": [],
                    "error": None
                }
        
        elif task_type == "dependency_install":
            # Run dependency installation
            install_script = os.path.join(workspace_dir, "install_dependencies.py")
            if os.path.exists(install_script):
                # Quote the script path to handle spaces in Windows paths
                command = f'python "{install_script}"'
                result = self.executor_agent.run(command)
                return {
                    "success": result.get("success", False),
                    "files": [],
                    "revision_tasks": [],
                    "error": result.get("stderr") if not result.get("success") else None
                }
            else:
                error_msg = "install_dependencies.py not found"
                logger.warning(f"[executor] {error_msg}")
                return {
                    "success": False,
                    "files": [],
                    "revision_tasks": [],
                    "error": error_msg
                }
        
        elif task_type == "command_run":
            # Execute the command directly
            result = self.executor_agent.run(task_desc)
            return {
                "success": result.get("success", False),
                "files": [],
                "revision_tasks": [],
                "error": result.get("stderr") if not result.get("success") else None
            }
        
        # Default to code generation for create/write/modify tasks
        self._emit(
            "coder",
            "writing_code",
            task.get("description", ""),
        )
        known_files = set(self.snapshot.files.keys()) if self.snapshot else set()
        files = self.coder_agent.execute(
            task,
            snapshot=self.snapshot,
            workspace_dir=workspace_dir,
            project_dir=project_dir,
        )
        if not files and not task.get("command"):
            return {
                "success": False,
                "files": [],
                "revision_tasks": [],
                "error": (
                    f"No files generated for task "
                    f"{task['id']}"
                ),
            }
        for file_path in files:
            created = self._was_created(
                file_path,
                known_files,
                workspace_dir,
                project_dir,
            )
            memory.record_file(
                file_path,
                created=created,
            )
            self._update_snapshot_file(
                file_path,
                workspace_dir,
                project_dir,
            )

        # Auto-detect and install dependencies after code generation
        if self.dependency_manager and files:
            self._emit(
                "dependency",
                "checking",
                "Checking for missing dependencies...",
            )
            dep_result = self.dependency_manager.auto_detect_and_install()
            if dep_result["success"] and dep_result["installed"]:
                self._emit(
                    "dependency",
                    "installed",
                    f"Installed {len(dep_result['installed'])} packages: {', '.join(dep_result['installed'])}",
                )
            elif not dep_result["success"]:
                self._emit(
                    "dependency",
                    "failed",
                    f"Failed to install dependencies: {dep_result['message']}",
                )

        try:
            if self.enable_reviewer:
                review = self.reviewer_agent.review(
                    task,
                    files,
                    workspace_dir,
                    project_dir,
                    self.snapshot,
                )
            else:
                review = {"issues": []}
                self._emit(
                    "reviewer",
                    "skipped",
                    "Reviewer disabled in configuration",
                )
        except Exception as error:
            logger.warning(f"[agent] Reviewer failed, proceeding without review: {error}")
            review = {"issues": []}  # Fallback to no issues
        
        if review["issues"]:
            memory.record_decision(
                f"Reviewer requested changes for "
                f"task {task['id']}: "
                f"{'; '.join(review['issues'])}"
            )
            self._emit(
                "reviewer",
                "revision_requested",
                "; ".join(review["issues"]),
            )
        else:
            self._emit(
                "reviewer",
                "approved",
                f"Approved task {task['id']}",
            )

        execution = {
            "success": True,
            "error": None,
        }
        if task.get("type") in {"execute", "test"}:
            execution = self._run_execution_loop(
                task,
                files,
                memory,
                workspace_dir,
                project_dir,
            )

        return {
            "success": execution["success"],
            "files": files,
            "revision_tasks": review[
                "revision_tasks"
            ],
            "error": execution["error"],
        }

    def _run_execution_loop(
        self,
        task: dict,
        files: list[str],
        memory: ProjectMemory,
        workspace_dir: str,
        project_dir: str,
    ) -> dict:
        command = task.get("command") or self._infer_command(
            files, workspace_dir
        )
        iteration = 0
        error_history: list[str] = []

        while iteration < self.max_fix_attempts:
            if self._should_skip_execution(command):
                result = {
                    "success": True,
                    "stderr": "",
                    "stdout": (
                        f"Skipped execution for {command}"
                    ),
                }
            else:
                self._emit(
                    "executor",
                    "running_command",
                    command,
                )
                result = self.executor_agent.run(command)

            if result["success"]:
                return {
                    "success": True,
                    "error": None,
                }

            iteration += 1
            error = (
                result.get("stderr")
                or result.get("stdout")
                or "Unknown execution failure"
            )
            error_history.append(error)
            memory.record_error(error)
            if error_history.count(error) >= 3:
                logger.warning(
                    f"[agent] Repeated execution error detected for task {task['id']}"
                )
                break
            self._emit(
                "debugger",
                "debugging",
                error[:120],
            )
            fix = self.debugger_agent.analyze(
                error,
                task,
                self.snapshot,
            )
            fix_task = {
                "id": f"{task['id']}-debug-{iteration}",
                "description": (
                    f"{task['description']}. "
                    f"{fix['fix']}"
                ),
                "type": "fix",
                "status": "pending",
                "source": "debugger",
            }
            new_files = self.coder_agent.execute(
                fix_task,
                snapshot=self.snapshot,
                workspace_dir=workspace_dir,
                project_dir=project_dir,
            )
            for file_path in new_files:
                memory.record_file(
                    file_path, created=False
                )
                self._update_snapshot_file(
                    file_path,
                    workspace_dir,
                    project_dir,
                )
            command = (
                fix.get("revised_command")
                or command
            )

        return {
            "success": False,
            "error": (
                f"Task {task['id']} failed after "
                f"{self.max_fix_attempts} retries"
            ),
        }

    def _run_test_phase(
        self,
        memory: ProjectMemory,
        workspace_dir: str,
        project_dir: str,
    ) -> dict:
        test_agent = TestAgent(project_dir)
        test_files = test_agent.find_tests(
            self.snapshot
        )
        if not test_files:
            self._emit(
                "tester",
                "skipped",
                "No tests found",
            )
            return {"success": True}

        iteration = 0
        error_history: list[str] = []
        while iteration < min(
            self.max_test_iterations,
            self.max_fix_attempts,
        ):
            self._emit(
                "tester",
                "running_tests",
                f"{len(test_files)} tests discovered",
            )
            result = test_agent.run()
            if result["success"]:
                self._emit(
                    "tester",
                    "tests_passed",
                    result.get("summary", ""),
                )
                return {"success": True}

            iteration += 1
            error = result.get("output", "")
            error_history.append(error)
            memory.record_error(error)
            if error_history.count(error) >= 3:
                logger.warning("[agent] Repeated test failure detected")
                break
            self._emit(
                "debugger",
                "fixing_tests",
                result.get("summary", ""),
            )
            fix = self.debugger_agent.analyze(
                error,
                {
                    "id": "test-fix",
                    "description": "Fix failing tests",
                    "type": "test_fix",
                },
                self.snapshot,
            )
            fix_task = {
                "id": f"test-fix-{iteration}",
                "description": (
                    f"Fix failing tests. {fix['fix']}"
                ),
                "type": "fix",
                "status": "pending",
                "source": "tester",
            }
            new_files = self.coder_agent.execute(
                fix_task,
                snapshot=self.snapshot,
                workspace_dir=workspace_dir,
                project_dir=project_dir,
            )
            for file_path in new_files:
                memory.record_file(
                    file_path, created=False
                )
                self._update_snapshot_file(
                    file_path,
                    workspace_dir,
                    project_dir,
                )

        return {
            "success": False,
            "error": (
                "Tests failed after "
                f"{self.max_test_iterations} retries"
            ),
        }

    def _update_snapshot_file(
        self,
        file_path: str,
        workspace_dir: str,
        project_dir: str,
    ) -> None:
        path = Path(file_path)
        if not path.exists():
            return
        try:
            relative = path.relative_to(project_dir)
        except ValueError:
            relative = path.relative_to(workspace_dir)
        self.snapshot.files[
            str(relative).replace("\\", "/")
        ] = path.read_text(encoding="utf-8")
        self.snapshot.is_empty = False
        self.reader.invalidate_index(project_dir)

    def _infer_command(
        self,
        files: list[str],
        workspace_dir: str,
    ) -> str:
        if not files:
            return ""
        file_path = Path(files[0])
        try:
            rel_path = str(
                file_path.relative_to(workspace_dir)
            )
        except ValueError:
            rel_path = str(file_path)
        return f"python {rel_path}"

    def _should_skip_execution(
        self,
        command: str,
    ) -> bool:
        match = re.search(
            r'python\s+"?([^\s"]+\.py)"?',
            command,
            re.IGNORECASE,
        )
        if not match or not self.snapshot:
            return False

        fname = Path(match.group(1)).name
        for rel_path, content in self.snapshot.files.items():
            if Path(rel_path).name == fname:
                return (
                    "__main__" not in content
                    and "if __name__" not in content
                )
        return False

    def _resolve_project_dir(
        self,
        project_dir: str | None,
        workspace_dir: str,
    ) -> str:
        if project_dir and Path(project_dir).exists():
            return str(Path(project_dir).resolve())
        return workspace_dir

    def _sanitize_workspace_name(
        self,
        workspace_name: str | None,
    ) -> str | None:
        if not workspace_name:
            return None
        return re.sub(
            r"[^a-zA-Z0-9_\-]",
            "",
            workspace_name[:50].lower().replace(" ", "_"),
        )[:35]

    def _ensure_logging(
        self,
        workspace_dir: str,
    ) -> None:
        self.logs_dir = configure_workspace_logging(
            workspace_dir
        )

    def _emit(
        self,
        agent: str,
        action: str,
        result: str,
    ) -> None:
        message = f"[{agent}] {action}: {result}"
        logger.info(message)
        if self.progress_callback:
            self.progress_callback(
                agent=agent,
                action=action,
                result=result,
            )

        if not self.logs_dir:
            return
        entry = {
            "timestamp": datetime.now(
                timezone.utc
            ).isoformat(),
            "agent": agent,
            "action": action,
            "result": result,
        }
        log_path = self.logs_dir / "activity.log"
        with log_path.open(
            "a", encoding="utf-8"
        ) as handle:
            handle.write(json.dumps(entry) + "\n")

    def _detect_dependencies(
        self, project_dir: str
    ) -> list[str]:
        dependencies: list[str] = []
        requirements = Path(project_dir) / "requirements.txt"
        if requirements.exists():
            for line in requirements.read_text(
                encoding="utf-8"
            ).splitlines():
                item = line.strip()
                if item and not item.startswith("#"):
                    dependencies.append(item)
        return dependencies

    def _was_created(
        self,
        file_path: str,
        known_files: set[str],
        workspace_dir: str,
        project_dir: str,
    ) -> bool:
        path = Path(file_path)
        for base in (project_dir, workspace_dir):
            try:
                relative = str(path.relative_to(base)).replace("\\", "/")
                return relative not in known_files
            except ValueError:
                continue
        return True
