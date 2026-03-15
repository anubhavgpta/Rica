"""Agent Orchestrator for coordinating multi-agent execution."""

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from loguru import logger

from rica.agents.planner_agent import PlannerAgent
from rica.agents.research_agent import ResearchAgent
from rica.agents.coder_agent import CoderAgent
from rica.agents.executor_agent import ExecutorAgent
from rica.agents.debugger_agent import DebuggerAgent
from rica.agents.reviewer_agent import ReviewerAgent
from rica.agents.memory_agent import MemoryAgent
from rica.logging_utils import get_component_logger
from rica.reader import CodebaseReader
from rica.result import RicaResult
from rica.tools import ToolRegistry
from rica.utils.paths import ensure_workspace
from rica.workspace import detect_workspace_metadata


class AgentOrchestrator:
    """Central orchestrator for coordinating multi-agent execution."""
    
    def __init__(self, config: dict):
        self.config = config
        self.logger = get_component_logger("orchestrator")
        
        # Initialize agents (will be fully initialized with workspace)
        self.planner = None
        self.researcher = None
        self.coder = None
        self.executor = None
        self.debugger = None
        self.reviewer = None
        self.memory = None
        
        # Execution state
        self.workspace_dir = None
        self.project_dir = None
        self.snapshot = None
        self.tool_registry = None
        self.client = None
        
        # Performance tracking
        self.start_time = None
        self.agent_performance = {}
        self.task_queue = []
        self.completed_tasks = []
        
        # Parallel execution settings
        self.max_workers = config.get("max_parallel_workers", 4)
        self.enable_parallel = config.get("enable_parallel_execution", True)
        
        self.logger.info(f"[orchestrator] initialized with max_workers={self.max_workers}")
    
    def run(self, goal: str, project_dir: str = None, workspace_name: str = None) -> RicaResult:
        """
        Main execution method for the orchestrator.
        
        Args:
            goal: The user's goal
            project_dir: Target project directory
            workspace_name: Workspace name
            
        Returns:
            RicaResult with execution results
        """
        self.start_time = time.time()
        self.logger.info(f"[orchestrator] starting execution for goal: {goal[:50]}...")
        
        try:
            # Setup workspace and initialize agents
            self._setup_workspace(goal, project_dir, workspace_name)
            self._initialize_agents()
            
            # Generate tasks using planner
            tasks = self._plan_tasks(goal)
            self.logger.info(f"[planner] generated {len(tasks)} tasks")
            
            # Execute tasks (parallel or sequential)
            if self.enable_parallel and self._can_run_parallel(tasks):
                results = self._execute_tasks_parallel(tasks)
            else:
                results = self._execute_tasks_sequential(tasks)
            
            # Generate final result
            return self._generate_result(goal, results)
            
        except Exception as e:
            self.logger.error(f"[orchestrator] execution failed: {e}")
            return RicaResult(
                success=False,
                goal=goal,
                workspace_dir=self.workspace_dir,
                error=str(e),
                iterations=0
            )
        finally:
            self._cleanup()
    
    def _setup_workspace(self, goal: str, project_dir: str = None, workspace_name: str = None) -> None:
        """Setup workspace and project directories."""
        # Create workspace
        workspace_name = workspace_name or f"orchestrated_{int(time.time())}"
        self.workspace_dir = str(ensure_workspace(workspace_name))
        
        # Resolve project directory
        self.project_dir = self._resolve_project_dir(project_dir, self.workspace_dir)
        
        self.logger.info(f"[orchestrator] workspace: {self.workspace_dir}")
        self.logger.info(f"[orchestrator] project: {self.project_dir}")
        
        # Initialize client and tools
        import google.genai as genai
        self.client = genai.Client(api_key=self.config["api_key"])
        
        self.tool_registry = ToolRegistry()
        self.reader = CodebaseReader()
        
        # Create snapshot
        self.snapshot = self.reader.snapshot(
            self.project_dir,
            goal,
            self.client,
            self.config["model"]
        )
    
    def _initialize_agents(self) -> None:
        """Initialize all agents with workspace context."""
        self.logger.info(f"[orchestrator] initializing agents...")
        
        # Initialize specialized agents
        self.planner = PlannerAgent(self.config)
        self.researcher = ResearchAgent(self.config)
        self.coder = CoderAgent(self.config)
        self.executor = ExecutorAgent(self.project_dir)
        self.debugger = DebuggerAgent(self.config, self.workspace_dir)
        self.reviewer = ReviewerAgent(self.config)
        self.memory = MemoryAgent(self.config, self.workspace_dir)
        
        self.logger.info(f"[orchestrator] all agents initialized")
    
    def _plan_tasks(self, goal: str) -> List[Dict[str, Any]]:
        """Generate tasks using the planner agent."""
        self.logger.info(f"[planner] generating tasks for goal...")
        
        # Get workspace files for context
        workspace_files = []
        try:
            if Path(self.workspace_dir).exists():
                workspace_files = list(Path(self.workspace_dir).iterdir())
                workspace_files = [f.name for f in workspace_files if f.is_file()]
        except Exception as e:
            self.logger.warning(f"[orchestrator] failed to list workspace files: {e}")
        
        # Generate tasks
        tasks = self.planner.plan(
            goal,
            self.snapshot,
            tool_names=self.tool_registry.names(),
            workspace_files=workspace_files,
            workspace_dir=self.workspace_dir
        )
        
        # Validate and enhance tasks
        tasks = self._validate_tasks(tasks)
        tasks = self._enhance_tasks_with_memory(tasks)
        
        return tasks
    
    def _validate_tasks(self, tasks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Validate and filter tasks."""
        validated_tasks = []
        
        for task in tasks:
            # Basic validation
            if not task.get("description"):
                self.logger.warning(f"[orchestrator] skipping task without description: {task}")
                continue
            
            # Add required fields
            task.setdefault("id", f"task-{len(validated_tasks) + 1}")
            task.setdefault("type", "codegen")
            task.setdefault("status", "pending")
            task.setdefault("priority", "medium")
            
            validated_tasks.append(task)
        
        self.logger.info(f"[orchestrator] validated {len(validated_tasks)} tasks")
        return validated_tasks
    
    def _enhance_tasks_with_memory(self, tasks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Enhance tasks with memory context."""
        enhanced_tasks = []
        
        for task in tasks:
            # Get memory context for the task
            context = self.memory.get_context_for_task(task)
            
            # Add context to task
            if context:
                task["memory_context"] = context
                self.logger.debug(f"[orchestrator] enhanced task {task['id']} with memory context")
            
            enhanced_tasks.append(task)
        
        return enhanced_tasks
    
    def _can_run_parallel(self, tasks: List[Dict[str, Any]]) -> bool:
        """Determine if tasks can run in parallel."""
        if len(tasks) <= 1:
            return False
        
        # Check for dependencies between tasks
        task_descriptions = [task.get("description", "").lower() for task in tasks]
        
        # Simple dependency detection - can be enhanced
        dependency_keywords = ["after", "before", "depends", "once", "previous", "following"]
        
        for desc in task_descriptions:
            if any(keyword in desc for keyword in dependency_keywords):
                self.logger.info(f"[orchestrator] detected dependencies, using sequential execution")
                return False
        
        self.logger.info(f"[orchestrator] tasks can run in parallel")
        return True
    
    def _execute_tasks_sequential(self, tasks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Execute tasks sequentially."""
        results = []
        
        for i, task in enumerate(tasks, 1):
            self.logger.info(f"[orchestrator] executing task {i}/{len(tasks)}: {task.get('description', '')[:50]}...")
            
            result = self._execute_single_task(task)
            results.append(result)
            
            # Store result in memory
            self.memory.store_task_result(task, result)
            
            # Check if execution should continue
            if not result.get("success", True) and task.get("priority") == "high":
                self.logger.warning(f"[orchestrator] high priority task failed, stopping execution")
                break
        
        return results
    
    def _execute_tasks_parallel(self, tasks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Execute tasks in parallel using ThreadPoolExecutor."""
        results = []
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit all tasks
            future_to_task = {
                executor.submit(self._execute_single_task, task): task
                for task in tasks
            }
            
            # Collect results as they complete
            completed_count = 0
            for future in as_completed(future_to_task):
                task = future_to_task[future]
                completed_count += 1
                
                try:
                    result = future.result()
                    results.append(result)
                    
                    # Store result in memory
                    self.memory.store_task_result(task, result)
                    
                    self.logger.info(f"[orchestrator] completed task {completed_count}/{len(tasks)}: "
                                   f"{task.get('description', '')[:50]}...")
                    
                except Exception as e:
                    self.logger.error(f"[orchestrator] task failed: {task.get('id')} - {e}")
                    results.append({
                        "success": False,
                        "error": str(e),
                        "task_id": task.get("id")
                    })
        
        return results
    
    def _execute_single_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a single task using the coordinated agent flow."""
        task_id = task.get("id", "unknown")
        task_desc = task.get("description", "")
        task_type = task.get("type", "codegen")
        
        start_time = time.time()
        
        try:
            # Step 1: Research (optional)
            context = {}
            if task_type in ["codegen", "debug", "complex"]:
                self.logger.info(f"[researcher] gathering context for task {task_id}")
                context = self.researcher.gather(task, self.workspace_dir, self.project_dir)
            
            # Step 2: Code generation/execution based on task type
            if task_type == "codegen":
                result = self._execute_codegen_task(task, context)
            elif task_type == "debug":
                result = self._execute_debug_task(task, context)
            elif task_type == "command":
                result = self._execute_command_task(task, context)
            else:
                # Default to codegen
                result = self._execute_codegen_task(task, context)
            
            # Step 3: Review (if code was generated)
            if result.get("files") and self.config.get("enable_reviewer", True):
                self.logger.info(f"[reviewer] validating code for task {task_id}")
                review_result = self._review_code(result, task)
                
                if review_result.get("requires_fix"):
                    self.logger.info(f"[coder] revising code based on review for task {task_id}")
                    result = self._revise_code(task, result, review_result)
            
            # Step 4: Execution (if applicable)
            if result.get("files") and task.get("execute", True):
                self.logger.info(f"[executor] running commands for task {task_id}")
                exec_result = self._execute_task_commands(task, result)
                result.update(exec_result)
            
            # Calculate execution time
            result["execution_time"] = time.time() - start_time
            result["agent"] = "orchestrator"
            
            # Log completion
            status = "completed" if result.get("success", True) else "failed"
            self.logger.info(f"[orchestrator] task {task_id} {status} in {result['execution_time']:.2f}s")
            
            return result
            
        except Exception as e:
            self.logger.error(f"[orchestrator] task {task_id} failed with exception: {e}")
            return {
                "success": False,
                "error": str(e),
                "execution_time": time.time() - start_time,
                "agent": "orchestrator"
            }
    
    def _execute_codegen_task(self, task: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a code generation task."""
        self.logger.info(f"[coder] generating code for task {task.get('id')}")
        
        # Enhance task with research context
        enhanced_task = task.copy()
        if context:
            enhanced_task["research_context"] = context
        
        # Generate code
        files = self.coder.execute(
            enhanced_task,
            snapshot=self.snapshot,
            workspace_dir=self.workspace_dir,
            project_dir=self.project_dir
        )
        
        return {
            "success": len(files) > 0,
            "files": files,
            "context_used": bool(context)
        }
    
    def _execute_debug_task(self, task: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a debug task."""
        self.logger.info(f"[debugger] analyzing issue for task {task.get('id')}")
        
        # Get error from task or context
        error = task.get("error") or context.get("error", "")
        
        if not error:
            return {
                "success": False,
                "error": "No error provided for debug task"
            }
        
        # Generate fix
        fix_result = self.debugger.analyze(error, task, self.snapshot)
        
        # Apply fix using coder
        if fix_result.get("fix"):
            fix_task = {
                "id": f"{task.get('id')}-fix",
                "description": f"Apply fix: {fix_result['fix']}",
                "type": "fix"
            }
            
            files = self.coder.execute(
                fix_task,
                snapshot=self.snapshot,
                workspace_dir=self.workspace_dir,
                project_dir=self.project_dir
            )
            
            return {
                "success": len(files) > 0,
                "files": files,
                "fix_applied": fix_result["fix"]
            }
        
        return {
            "success": False,
            "error": "No fix generated"
        }
    
    def _execute_command_task(self, task: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a command task."""
        command = task.get("description", "")
        self.logger.info(f"[executor] running command: {command[:50]}...")
        
        result = self.executor.run(command)
        
        # Store command in memory
        self.memory.store_command_execution(
            command,
            result.get("success", False),
            result.get("stdout") or result.get("stderr"),
            task.get("id")
        )
        
        return {
            "success": result.get("success", False),
            "output": result.get("stdout") or result.get("stderr"),
            "exit_code": result.get("exit_code")
        }
    
    def _review_code(self, result: Dict[str, Any], task: Dict[str, Any]) -> Dict[str, Any]:
        """Review generated code."""
        files = result.get("files", [])
        if not files:
            return {"requires_fix": False}
        
        # Simple review - can be enhanced with actual code analysis
        review_result = {
            "requires_fix": False,
            "issues": [],
            "suggestions": []
        }
        
        # Check for common issues
        for file_path in files:
            try:
                content = Path(file_path).read_text(encoding='utf-8')
                
                # Basic checks
                if not content.strip():
                    review_result["issues"].append(f"File {file_path} is empty")
                    review_result["requires_fix"] = True
                
                if "TODO" in content or "FIXME" in content:
                    review_result["suggestions"].append(f"File {file_path} has TODO/FIXME comments")
                
            except Exception as e:
                review_result["issues"].append(f"Could not read {file_path}: {e}")
                review_result["requires_fix"] = True
        
        return review_result
    
    def _revise_code(self, task: Dict[str, Any], result: Dict[str, Any], review: Dict[str, Any]) -> Dict[str, Any]:
        """Revise code based on review feedback."""
        issues = review.get("issues", [])
        if not issues:
            return result
        
        # Create revision task
        revision_desc = f"Revise code to fix issues: {'; '.join(issues)}"
        revision_task = {
            "id": f"{task.get('id')}-revise",
            "description": revision_desc,
            "type": "fix",
            "original_files": result.get("files", [])
        }
        
        # Generate revised code
        files = self.coder.execute(
            revision_task,
            snapshot=self.snapshot,
            workspace_dir=self.workspace_dir,
            project_dir=self.project_dir
        )
        
        return {
            "success": len(files) > 0,
            "files": files,
            "revised": True,
            "original_issues": issues
        }
    
    def _execute_task_commands(self, task: Dict[str, Any], result: Dict[str, Any]) -> Dict[str, Any]:
        """Execute commands related to the task."""
        files = result.get("files", [])
        if not files:
            return {"success": True}
        
        # Look for execution commands in task
        task_desc = task.get("description", "").lower()
        
        # Common execution patterns
        if any(keyword in task_desc for keyword in ["run", "execute", "test", "build"]):
            # Try to infer and run appropriate commands
            commands = self._infer_execution_commands(files, task_desc)
            
            for command in commands:
                self.logger.info(f"[executor] running inferred command: {command}")
                exec_result = self.executor.run(command)
                
                if not exec_result.get("success", False):
                    return {
                        "success": False,
                        "error": f"Command failed: {command}",
                        "output": exec_result.get("stderr")
                    }
        
        return {"success": True}
    
    def _infer_execution_commands(self, files: List[str], task_desc: str) -> List[str]:
        """Infer appropriate commands to run based on files and task."""
        commands = []
        
        # Check for Python files
        py_files = [f for f in files if f.endswith('.py')]
        if py_files:
            if "test" in task_desc:
                commands.append("python -m pytest")
            elif "run" in task_desc or "execute" in task_desc:
                main_file = next((f for f in py_files if "main" in f.lower()), py_files[0])
                commands.append(f"python {main_file}")
        
        # Check for setup files
        if any("requirements.txt" in f for f in files):
            commands.append("pip install -r requirements.txt")
        
        return commands
    
    def _generate_result(self, goal: str, results: List[Dict[str, Any]]) -> RicaResult:
        """Generate final result from task results."""
        # Calculate success
        successful_tasks = [r for r in results if r.get("success", True)]
        success = len(successful_tasks) == len(results)
        
        # Collect created files
        all_files = []
        for result in results:
            if result.get("files"):
                all_files.extend(result["files"])
        
        # Calculate total execution time
        total_time = time.time() - self.start_time
        
        # Generate summary
        summary = self._generate_execution_summary(results)
        
        # Store final knowledge
        self._store_execution_knowledge(goal, results)
        
        self.logger.info(f"[orchestrator] execution completed: {len(successful_tasks)}/{len(results)} tasks successful")
        
        return RicaResult(
            success=success,
            goal=goal,
            workspace_dir=self.workspace_dir,
            files_created=all_files,
            summary=summary,
            iterations=len(results)
        )
    
    def _generate_execution_summary(self, results: List[Dict[str, Any]]) -> str:
        """Generate execution summary."""
        summary_parts = []
        
        # Task summary
        successful = len([r for r in results if r.get("success", True)])
        total = len(results)
        summary_parts.append(f"Tasks: {successful}/{total} completed")
        
        # File summary
        all_files = []
        for result in results:
            if result.get("files"):
                all_files.extend(result["files"])
        
        if all_files:
            summary_parts.append(f"Files created: {len(all_files)}")
        
        # Performance summary
        total_time = sum(r.get("execution_time", 0) for r in results)
        summary_parts.append(f"Total execution time: {total_time:.2f}s")
        
        # Error summary
        failed_tasks = [r for r in results if not r.get("success", True)]
        if failed_tasks:
            summary_parts.append(f"Failed tasks: {len(failed_tasks)}")
        
        return "\n".join(summary_parts)
    
    def _store_execution_knowledge(self, goal: str, results: List[Dict[str, Any]]) -> None:
        """Store execution knowledge and patterns."""
        try:
            # Analyze execution patterns
            successful_patterns = []
            failed_patterns = []
            
            for result in results:
                if result.get("success", True):
                    successful_patterns.append({
                        "task_type": result.get("task_type", "unknown"),
                        "execution_time": result.get("execution_time", 0),
                        "files_created": len(result.get("files", []))
                    })
                else:
                    failed_patterns.append({
                        "error": result.get("error", "unknown"),
                        "task_type": result.get("task_type", "unknown")
                    })
            
            # Store insights
            if successful_patterns:
                insight = f"Successfully executed {len(successful_patterns)} tasks with average time " \
                         f"{sum(p['execution_time'] for p in successful_patterns) / len(successful_patterns):.2f}s"
                self.memory.store_knowledge(insight, "execution_patterns", "orchestrator")
            
            if failed_patterns:
                insight = f"Failed {len(failed_patterns)} tasks, common issues: " \
                         f"{list(set(p.get('error', 'unknown')[:50] for p in failed_patterns[:3]))}"
                self.memory.store_knowledge(insight, "failure_patterns", "orchestrator")
                
        except Exception as e:
            self.logger.warning(f"[orchestrator] failed to store execution knowledge: {e}")
    
    def _resolve_project_dir(self, project_dir: str = None, workspace_dir: str = None) -> str:
        """Resolve project directory."""
        if project_dir and Path(project_dir).exists():
            return project_dir
        
        # Default to workspace directory
        return workspace_dir
    
    def _cleanup(self) -> None:
        """Cleanup resources."""
        try:
            # Store final performance metrics
            if self.start_time:
                total_time = time.time() - self.start_time
                self.logger.info(f"[orchestrator] total execution time: {total_time:.2f}s")
                
                # Store performance in memory
                performance_data = {
                    "total_execution_time": total_time,
                    "tasks_completed": len(self.completed_tasks),
                    "agents_used": ["planner", "coder", "executor", "debugger", "reviewer", "memory"],
                    "parallel_execution": self.enable_parallel,
                    "max_workers": self.max_workers
                }
                self.memory.store(performance_data, "performance_metrics", importance=7)
        
        except Exception as e:
            self.logger.warning(f"[orchestrator] cleanup error: {e}")
        
        self.logger.info(f"[orchestrator] cleanup completed")
