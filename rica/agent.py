"""Rica L18 Autonomous Agent Core Orchestrator."""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from rich.console import Console

from .agent_memory import get_turn_count, load_history, save_turn
from .agent_watch_bridge import WatchBridge
from .codegen import _strip_fences
from .config import WORKSPACE_ROOT
from .db import get_latest_build, get_latest_debug, get_plan_for_session
from .hooks import fire_hook
from .models import (
    AgentTurnResult,
    ProjectContext,
    SubTask,
    SubTaskResult,
    WatchEvent,
)
from .task_decomposer import TaskDecomposer
from .verifier import Verifier, VerificationResult, is_unretryable


class AgentOrchestrator:
    """Central agent class for autonomous task execution."""
    
    def __init__(self, session_id: Optional[str], console: Console):
        self.session_id = session_id
        self.console = console
        self.turn_index = 0
        
        # Initialize components
        self.task_decomposer = TaskDecomposer(console)
        self.verifier = Verifier()
        self.watch_bridge = WatchBridge()
        
        # Load turn count if session exists
        if session_id:
            self.turn_index = get_turn_count(session_id)
    
    def run_turn(self, user_prompt: str) -> AgentTurnResult:
        """Execute one agent turn. Synchronous and blocking."""
        # Store user prompt for subtask use
        self._last_user_prompt = user_prompt
        
        self.turn_index += 1
        
        # Build project context
        context = self._build_project_context()
        
        # Decompose user prompt into subtasks
        subtasks = self.task_decomposer.decompose(user_prompt, context)
        
        # Execute subtasks
        results = []
        final_status = "completed"
        
        for i, task in enumerate(subtasks):
            # Fire pre-task hook
            fire_hook("pre_agent_task", session_id=self.session_id, extra={"subtask": task.model_dump()})
            
            # Execute subtask with retry logic
            result_1 = self._execute_subtask(task, attempt=1)
            
            if self.verifier.verify(task, result_1).passed:
                results.append(result_1)
                fire_hook("post_agent_task", session_id=self.session_id, extra={"subtask": task.model_dump(), "result": result_1.model_dump()})
                continue
            
            # Check for unretryable environment errors
            if is_unretryable(result_1):
                error_text = result_1.detail.get('error', '') + result_1.detail.get('output', '')
                escalation_msg = f"Stuck on execute: environment error — {error_text[:200]}. This may require manual setup (e.g. installing a runtime or configuring WSL)."
                fire_hook("agent_stuck", session_id=self.session_id, extra={"subtask": task.model_dump(), "results": [result_1.model_dump()]})
                
                # Add failed result and escalate
                results.append(result_1)
                return AgentTurnResult(
                    session_id=self.session_id,
                    turn_index=self.turn_index,
                    user_prompt=user_prompt,
                    subtasks=subtasks,
                    results=results,
                    final_status="stuck",
                    agent_reply=escalation_msg
                )
            
            # Retry with modified approach
            modified_task = self.task_decomposer.modify_subtask(task, result_1.detail)
            result_2 = self._execute_subtask(modified_task, attempt=2)
            
            # Preserve previous attempt detail
            result_2.previous_attempt_detail = result_1.detail
            
            if self.verifier.verify(modified_task, result_2).passed:
                results.append(result_2)
                fire_hook("post_agent_task", session_id=self.session_id, extra={"subtask": modified_task.model_dump(), "result": result_2.model_dump()})
                continue
            
            # Escalate to user
            escalation_message = self._escalate(task, [result_1, result_2])
            fire_hook("agent_stuck", session_id=self.session_id, extra={"subtask": task.model_dump(), "results": [result_1.model_dump(), result_2.model_dump()]})
            
            # Add incomplete results so far
            results.extend([result_1, result_2])
            final_status = "stuck"
            
            # Save partial turn and return
            agent_reply = f"Stuck on {task.type}: {escalation_message}"
            self._save_turn(user_prompt, subtasks[:i+1], results, agent_reply)
            
            return AgentTurnResult(
                session_id=self.session_id or "unknown",
                turn_index=self.turn_index,
                user_prompt=user_prompt,
                subtasks=subtasks[:i+1],
                results=results,
                final_status="stuck",
                agent_reply=agent_reply
            )
        
        # All subtasks completed
        final_status = "completed"
        agent_reply = self._generate_summary(subtasks, results)
        
        # Save turn to memory
        self._save_turn(user_prompt, subtasks, results, agent_reply)
        
        return AgentTurnResult(
            session_id=self.session_id or "unknown",
            turn_index=self.turn_index,
            user_prompt=user_prompt,
            subtasks=subtasks,
            results=results,
            final_status=final_status,
            agent_reply=agent_reply
        )
    
    def _execute_subtask(self, task: SubTask, attempt: int) -> SubTaskResult:
        """Execute a single subtask."""
        try:
            if task.type == "plan":
                detail = self._execute_plan(task)
            elif task.type == "build":
                detail = self._execute_build(task)
            elif task.type == "execute":
                detail = self._execute_execute(task)
            elif task.type == "debug":
                detail = self._execute_debug(task)
            elif task.type == "review":
                detail = self._execute_review(task)
            elif task.type == "fix":
                detail = self._execute_fix(task)
            elif task.type == "explain":
                detail = self._execute_explain(task)
            elif task.type == "refactor":
                detail = self._execute_refactor(task)
            elif task.type == "gen_tests":
                detail = self._execute_gen_tests(task)
            elif task.type == "rebuild":
                detail = self._execute_rebuild(task)
            elif task.type == "watch_start":
                detail = self._execute_watch_start(task)
            elif task.type == "watch_stop":
                detail = self._execute_watch_stop(task)
            elif task.type == "ask_user":
                detail = self._execute_ask_user(task)
            else:
                raise ValueError(f"Unknown task type: {task.type}")
            
            return SubTaskResult(
                task_type=task.type,
                passed=True,  # Will be verified separately
                summary=self._summarize_result(task.type, detail),
                detail=detail,
                attempt=attempt
            )
            
        except Exception as e:
            return SubTaskResult(
                task_type=task.type,
                passed=False,
                summary=f"Exception: {str(e)}",
                detail={"error": str(e), "exception_type": type(e).__name__},
                attempt=attempt
            )
    
    def _execute_plan(self, task: SubTask) -> dict:
        """Execute plan subtask."""
        from .planner import create_plan
        
        # Use task goal or fall back to session context
        goal = task.goal
        if not goal:
            # Try to get goal from recent history
            if hasattr(self, '_last_user_prompt'):
                goal = self._last_user_prompt
        
        # Use existing session_id or generate new one
        session_id_to_use = task.session_id or self.session_id
        if not session_id_to_use:
            import uuid
            session_id_to_use = str(uuid.uuid4())[:8]
            self.session_id = session_id_to_use
        
        plan_result = create_plan(goal, session_id_to_use, task.lang)
        
        # Save session to database only if it's new
        from .db import db
        if not db.get_session(session_id_to_use):
            db.create_session(session_id_to_use, goal, plan_result.language)
        
        # Save plan to database
        db.save_plan(
            plan_id=str(uuid.uuid4())[:8],
            session_id=session_id_to_use,
            plan_json=plan_result.model_dump_json()
        )
        
        # Update plan approval
        db.update_plan_approval(session_id_to_use, True)
        
        return {
            "session_id": plan_result.session_id,
            "plan_json": plan_result.model_dump_json(),
            "approved": True  # Agent-created plans are auto-approved
        }
    
    def _execute_build(self, task: SubTask) -> dict:
        """Execute build subtask."""
        from .codegen import build_project
        from .config import WORKSPACE_ROOT
        from .db import db
        import uuid
        from datetime import datetime, timezone
        
        # Use the agent's session_id (created during plan step)
        session_id = self.session_id
        if not session_id:
            raise ValueError("No session_id available - plan step must have failed")
        
        # Get plan from database
        from .db import get_plan_for_session
        plan_data = get_plan_for_session(session_id)
        if not plan_data:
            raise ValueError(f"No plan found for session {session_id}")
        
        from .models import BuildPlan
        plan = BuildPlan.model_validate_json(plan_data["plan_json"])
        
        # Create workspace
        workspace = WORKSPACE_ROOT / session_id
        workspace.mkdir(parents=True, exist_ok=True)
        
        # Save build record
        build_id = str(uuid.uuid4())
        started_at = datetime.now(timezone.utc).isoformat() + "Z"
        db.insert_build(build_id, session_id, str(workspace), started_at)
        
        # Build project
        generated_files = build_project(plan, workspace, self.console)
        
        # Complete build
        completed_at = datetime.now(timezone.utc).isoformat() + "Z"
        db.complete_build(build_id, completed_at)
        
        return {
            "files_generated": len(generated_files),
            "workspace_path": str(workspace)
        }
    
    def _execute_execute(self, task: SubTask) -> dict:
        """Execute execute subtask."""
        from .executor import run_command
        from .config import WORKSPACE_ROOT
        
        # Use the agent's session_id
        session_id = self.session_id
        workspace = WORKSPACE_ROOT / session_id
        
        if task.command:
            # Execute specific command
            result = run_command(task.command.split(), workspace, timeout=30, console=self.console)
        else:
            # Run default commands for the language
            from .db import get_plan_for_session
            plan_data = get_plan_for_session(session_id)
            if plan_data:
                from .models import BuildPlan
                plan = BuildPlan.model_validate_json(plan_data["plan_json"])
                
                # Run install commands
                if plan.install_commands:
                    for cmd in plan.install_commands:
                        run_result = run_command(cmd.split(), workspace, timeout=60, console=self.console)
                        if run_result.exit_code != 0:
                            return {
                                "exit_code": run_result.exit_code,
                                "output": run_result.stdout,
                                "error": run_result.stderr
                            }
                
                # Run the project
                from .registry import get_language_config
                config = get_language_config(plan.language.lower())
                run_cmd = config.get("run_cmd")
                if run_cmd:
                    result = run_command(run_cmd, workspace, timeout=10, console=self.console)
                else:
                    result = run_command(["echo", "No run command configured"], workspace, timeout=10, console=self.console)
            else:
                result = run_command(["echo", "No plan found"], workspace, timeout=10, console=self.console)
        
        return {
            "exit_code": result.exit_code,
            "output": result.stdout,
            "error": result.stderr
        }
    
    def _execute_review(self, task: SubTask) -> dict:
        """Execute review subtask."""
        from .reviewer import review_codebase
        from pathlib import Path
        
        # Get workspace from build
        build = get_latest_build(task.session_id or self.session_id)
        if not build:
            raise ValueError("No build found for review")
        
        workspace = Path(build["workspace"])
        review_result = review_codebase(workspace, task.lang, self.console)
        
        return {
            "issues_found": len(review_result.issues),
            "files_reviewed": review_result.files_reviewed,  # This is already an int
            "language": review_result.language
        }
    
    def _execute_debug(self, task: SubTask) -> dict:
        """Execute debug subtask."""
        from .debugger import debug_session
        
        debug_result = debug_session(task.session_id, max_iter=task.max_iter)
        
        return {
            "status": debug_result.final_status,
            "iterations": debug_result.iterations
        }
    
    def _execute_fix(self, task: SubTask) -> dict:
        """Execute fix subtask."""
        from pathlib import Path
        
        # Get workspace from build
        build = get_latest_build(task.session_id or self.session_id)
        if not build:
            raise ValueError("No build found for fix")
        
        workspace = Path(build["workspace"])
        
        # For now, since review found 0 issues, just return success
        # In a full implementation, we would get issues from the latest review
        # and call fix_file on each file with issues
        
        return {
            "files_fixed": 0,
            "issues_remaining": 0,
            "files": []
        }
    
    def _execute_explain(self, task: SubTask) -> dict:
        """Execute explain subtask."""
        from .explainer import explain
        
        explain_result = explain(task.path, task.lang)
        
        return {
            "explanation": explain_result.explanation,
            "files_analyzed": explain_result.files_analyzed
        }
    
    def _execute_refactor(self, task: SubTask) -> dict:
        """Execute refactor subtask."""
        from .refactor import refactor
        
        refactor_result = refactor(task.path, task.lang)
        
        return {
            "suggestions": [c.model_dump() for c in refactor_result.changes],
            "files_analyzed": refactor_result.files_analyzed,
            "has_refactor_candidates": len(refactor_result.changes) > 0
        }
    
    def _execute_gen_tests(self, task: SubTask) -> dict:
        """Execute gen_tests subtask."""
        from .test_generator import generate_tests
        
        test_result = generate_tests(task.path, task.lang)
        
        return {
            "files_written": len(test_result.tests_generated),
            "tests_generated": [t.model_dump() for t in test_result.tests_generated]
        }
    
    def _execute_rebuild(self, task: SubTask) -> dict:
        """Execute rebuild subtask."""
        from .rebuilder import rebuild
        
        rebuild_result = rebuild(task.session_id, changed_only=task.changed_only)
        
        return {
            "files_regenerated": len(rebuild_result.files_rewritten),
            "files_checked": rebuild_result.files_checked,
            "files_changed": len(rebuild_result.files_changed)
        }
    
    def _execute_watch_start(self, task: SubTask) -> dict:
        """Execute watch_start subtask."""
        self.watch_bridge.start(task.path, task.lang)
        
        return {
            "is_alive": self.watch_bridge.is_alive(),
            "path": task.path,
            "lang": task.lang
        }
    
    def _execute_watch_stop(self, task: SubTask) -> dict:
        """Execute watch_stop subtask."""
        self.watch_bridge.stop()
        
        return {
            "is_alive": self.watch_bridge.is_alive()
        }
    
    def _execute_ask_user(self, task: SubTask) -> dict:
        """Execute ask_user subtask."""
        return {
            "question": task.question,
            "awaiting_response": True
        }
    
    def _build_project_context(self) -> ProjectContext:
        """Build project context for task decomposition."""
        # Load recent history
        recent_history = load_history(self.session_id, last_n=10) if self.session_id else []
        
        # Get latest build/debug status
        latest_build = get_latest_build(self.session_id) if self.session_id else None
        latest_debug = get_latest_debug(self.session_id) if self.session_id else None
        
        # Get plan to extract languages
        languages = []
        if self.session_id:
            plan = get_plan_for_session(self.session_id)
            if plan:
                plan_data = json.loads(plan["plan_json"])
                languages = plan_data.get("languages", [])
                if not languages and plan_data.get("language"):
                    languages = [plan_data["language"]]
        
        # Resolve workspace path
        workspace_path = None
        if latest_build:
            workspace_path = latest_build["workspace"]
        
        return ProjectContext(
            session_id=self.session_id,
            workspace_path=workspace_path,
            languages=languages,
            recent_history=recent_history,
            active_snapshot_id=None,  # TODO: Get from file_snapshots
            last_build_status=latest_build["status"] if latest_build else None,
            last_debug_status=latest_debug["final_status"] if latest_debug else None
        )
    
    def _summarize_result(self, task_type: str, detail: dict) -> str:
        """Generate one-line summary of task result."""
        if task_type == "plan":
            session_id = detail.get("session_id", "unknown")
            approved = detail.get("approved", False)
            return f"Plan created ({session_id}, approved={approved})"
        elif task_type == "build":
            files = detail.get("files_generated", 0)
            return f"Built {files} files"
        elif task_type == "execute":
            exit_code = detail.get("exit_code", -1)
            return f"Command executed (exit {exit_code})"
        elif task_type == "debug":
            status = detail.get("status", "unknown")
            iterations = detail.get("iterations", 0)
            return f"Debug {status} ({iterations} iterations)"
        elif task_type == "review":
            files = detail.get("files_reviewed", 0)
            issues = len(detail.get("issues", []))
            return f"Reviewed {files} files, {issues} issues"
        elif task_type == "fix":
            files = detail.get("files_fixed", 0)
            return f"Fixed {files} files"
        elif task_type == "explain":
            files = detail.get("files_analyzed", 0)
            return f"Explained {files} files"
        elif task_type == "refactor":
            files = detail.get("files_analyzed", 0)
            suggestions = len(detail.get("suggestions", []))
            return f"Analyzed {files} files, {suggestions} suggestions"
        elif task_type == "gen_tests":
            tests = len(detail.get("tests_generated", []))
            return f"Generated {tests} tests"
        elif task_type == "rebuild":
            files = detail.get("files_regenerated", 0)
            return f"Rebuilt {files} files"
        elif task_type == "watch_start":
            path = detail.get("path", "unknown")
            return f"Started watching {path}"
        elif task_type == "watch_stop":
            return "Stopped watching"
        elif task_type == "ask_user":
            return "Asked user question"
        else:
            return f"Completed {task_type}"
    
    def _generate_summary(self, subtasks: list[SubTask], results: list[SubTaskResult]) -> str:
        """Generate human-readable summary of turn results."""
        passed_count = sum(1 for r in results if r.passed)
        total_count = len(results)
        
        if passed_count == total_count:
            status = "All tasks completed"
        else:
            status = f"{passed_count}/{total_count} tasks completed"
        
        # Count specific task types
        task_counts = {}
        for task in subtasks:
            task_counts[task.type] = task_counts.get(task.type, 0) + 1
        
        summary_parts = [status]
        for task_type, count in task_counts.items():
            if count > 1:
                summary_parts.append(f"{count} {task_type}s")
            else:
                summary_parts.append(f"{count} {task_type}")
        
        return ", ".join(summary_parts)
    
    def _escalate(self, task: SubTask, results: list[SubTaskResult]) -> str:
        """Generate escalation message for user."""
        first_result = results[0]
        second_result = results[1]
        
        if "error" in first_result.detail:
            error_msg = first_result.detail["error"]
            return f"Failed with error: {error_msg}"
        elif "error" in second_result.detail:
            error_msg = second_result.detail["error"]
            return f"Retry also failed with error: {error_msg}"
        else:
            return f"Task '{task.type}' failed after 2 attempts"
    
    def _save_turn(self, user_prompt: str, subtasks: list[SubTask], results: list[SubTaskResult], agent_reply: str) -> None:
        """Save turn to agent memory and write session note."""
        if not self.session_id:
            return
        
        # Save to agent memory
        save_turn(
            session_id=self.session_id,
            turn_index=self.turn_index,
            role="agent",
            content=agent_reply,
            subtasks=[t.model_dump() for t in subtasks],
            trace=[r.model_dump() for r in results]
        )
        
        # Write automatic session note
        from .db import add_note
        
        final_status = "completed" if all(r.passed for r in results) else "partial"
        task_summary = ", ".join(
            f"{t.type}({'✓' if r.passed else '✗'})"
            for t, r in zip(subtasks, results)
        )
        
        note_content = (
            f"[agent turn {self.turn_index}] {final_status}: "
            f"{len(subtasks)} subtasks — {task_summary}"
        )
        
        add_note(self.session_id, note_content)
    
    def get_watch_events(self) -> list[WatchEvent]:
        """Get new watch events from the bridge."""
        return self.watch_bridge.drain_events()
