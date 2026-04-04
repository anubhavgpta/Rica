"""Verification gate for Rica L18 autonomous agent."""

from typing import Union

from .models import SubTask, SubTaskResult


UNRETRYABLE_PATTERNS = [
    'execvpe',
    'No such file or directory',
    '/bin/bash',
    '/bin/sh',
    'not recognized as an internal or external command',
    'WinError 267',         # invalid directory
    'WinError 2',           # file not found (Windows)
    'WinError 193',         # not a valid Win32 application
    'cannot find the path', # Windows path errors
    'Failed to start process',
    'The directory name is invalid',
    'unsupported operand type',  # Path operation errors
]


def is_unretryable(result: SubTaskResult) -> bool:
    """Check if a result contains an unretryable environment error."""
    error_text = result.detail.get('error', '') + result.detail.get('output', '')
    return any(pat in error_text for pat in UNRETRYABLE_PATTERNS)


class VerificationResult:
    """Result of verifying a subtask execution."""
    
    def __init__(self, passed: bool, reason: str):
        self.passed = passed
        self.reason = reason


class Verifier:
    """Verification gate that inspects subtask results."""
    
    def verify(self, task: SubTask, result: SubTaskResult) -> VerificationResult:
        """Verify a subtask result and return pass/fail with reason."""
        task_type = task.type
        
        if task_type == "plan":
            return self._verify_plan(task, result)
        elif task_type == "build":
            return self._verify_build(task, result)
        elif task_type == "execute":
            return self._verify_execute(task, result)
        elif task_type == "debug":
            return self._verify_debug(task, result)
        elif task_type == "review":
            return self._verify_review(task, result)
        elif task_type == "fix":
            return self._verify_fix(task, result)
        elif task_type == "explain":
            return self._verify_explain(task, result)
        elif task_type == "refactor":
            return self._verify_refactor(task, result)
        elif task_type == "gen_tests":
            return self._verify_gen_tests(task, result)
        elif task_type == "rebuild":
            return self._verify_rebuild(task, result)
        elif task_type == "watch_start":
            return self._verify_watch_start(task, result)
        elif task_type == "watch_stop":
            return self._verify_watch_stop(task, result)
        elif task_type == "ask_user":
            return self._verify_ask_user(task, result)
        else:
            return VerificationResult(False, f"Unknown task type: {task_type}")
    
    def _verify_plan(self, task: SubTask, result: SubTaskResult) -> VerificationResult:
        """Verify plan subtask."""
        detail = result.detail
        
        # Check if we have a valid session_id or plan JSON
        has_session_id = isinstance(detail.get("session_id"), str) and detail["session_id"]
        has_plan_json = isinstance(detail.get("plan_json"), str) and detail["plan_json"]
        is_approved = detail.get("approved") is True
        
        if has_session_id and (is_approved or has_plan_json):
            return VerificationResult(True, "Plan created successfully")
        else:
            return VerificationResult(False, "Plan creation failed - no valid session_id or approval")
    
    def _verify_build(self, task: SubTask, result: SubTaskResult) -> VerificationResult:
        """Verify build subtask."""
        detail = result.detail
        
        files_generated = detail.get("files_generated", 0)
        files_failed = detail.get("files_failed", 0)
        
        if files_generated > 0 and files_failed == 0:
            return VerificationResult(True, f"Build succeeded - {files_generated} files generated")
        else:
            return VerificationResult(False, f"Build failed - {files_generated} files generated, {files_failed} failed")
    
    def _verify_execute(self, task: SubTask, result: SubTaskResult) -> VerificationResult:
        """Verify execute subtask."""
        detail = result.detail
        
        exit_code = detail.get("exit_code")
        timed_out = detail.get("timed_out", False)
        
        passed = (
            exit_code == 0
            and not timed_out
        )
        
        if passed:
            return VerificationResult(True, "Command executed successfully")
        elif timed_out:
            return VerificationResult(False, f"Command timed out")
        elif exit_code is None:
            # subprocess creation error
            reason = f"Failed to start process: {detail.get('error', '')[:120]}"
            return VerificationResult(False, reason)
        elif exit_code != 0:
            reason = f"exit_code {detail.get('exit_code')}: {detail.get('error', '')[:120]}"
            return VerificationResult(False, reason)
        else:
            return VerificationResult(False, "Command execution status unknown")
    
    def _verify_debug(self, task: SubTask, result: SubTaskResult) -> VerificationResult:
        """Verify debug subtask."""
        detail = result.detail
        
        status = detail.get("status")
        iterations = detail.get("iterations", 0)
        
        if status == "resolved":
            return VerificationResult(True, f"Debugging resolved in {iterations} iterations")
        elif status in ["exhausted", "failed"]:
            return VerificationResult(False, f"Debugging {status} after {iterations} iterations")
        else:
            return VerificationResult(False, f"Debugging ended with unknown status: {status}")
    
    def _verify_review(self, task: SubTask, result: SubTaskResult) -> VerificationResult:
        """Verify review subtask."""
        detail = result.detail
        
        # Review passes if it completes without exception
        # (zero issues is also a valid pass)
        if not detail.get("error"):
            files_reviewed = detail.get("files_reviewed", 0)
            issues_found = detail.get("issues", [])
            return VerificationResult(True, f"Review completed - {files_reviewed} files reviewed, {len(issues_found)} issues found")
        else:
            return VerificationResult(False, f"Review failed with error: {detail.get('error')}")
    
    def _verify_fix(self, task: SubTask, result: SubTaskResult) -> VerificationResult:
        """Verify fix subtask."""
        detail = result.detail
        
        files_fixed = detail.get("files_fixed", 0)
        issues_remaining = detail.get("issues_remaining", 0)
        
        if files_fixed > 0 or issues_remaining == 0:
            return VerificationResult(True, f"Fix succeeded - {files_fixed} files fixed, {issues_remaining} issues remaining")
        else:
            return VerificationResult(False, f"Fix failed - no files fixed, {issues_remaining} issues remaining")
    
    def _verify_explain(self, task: SubTask, result: SubTaskResult) -> VerificationResult:
        """Verify explain subtask."""
        detail = result.detail
        
        explanation = detail.get("explanation", "")
        files_analyzed = detail.get("files_analyzed", 0)
        
        if explanation and len(explanation.strip()) > 0:
            return VerificationResult(True, f"Explanation generated - {files_analyzed} files analyzed")
        else:
            return VerificationResult(False, "Explanation failed - no content generated")
    
    def _verify_refactor(self, task: SubTask, result: SubTaskResult) -> VerificationResult:
        """Verify refactor subtask."""
        detail = result.detail
        
        suggestions = detail.get("suggestions", [])
        files_analyzed = detail.get("files_analyzed", 0)
        has_candidates = detail.get("has_refactor_candidates", True)
        
        if len(suggestions) > 0 or not has_candidates:
            return VerificationResult(True, f"Refactor analysis complete - {len(suggestions)} suggestions, {files_analyzed} files analyzed")
        else:
            return VerificationResult(False, "Refactor failed - no suggestions generated")
    
    def _verify_gen_tests(self, task: SubTask, result: SubTaskResult) -> VerificationResult:
        """Verify gen_tests subtask."""
        detail = result.detail
        
        files_written = detail.get("files_written", 0)
        tests_generated = detail.get("tests_generated", [])
        
        if files_written > 0 or len(tests_generated) > 0:
            return VerificationResult(True, f"Test generation succeeded - {files_written} files written, {len(tests_generated)} tests")
        else:
            return VerificationResult(False, "Test generation failed - no tests generated")
    
    def _verify_rebuild(self, task: SubTask, result: SubTaskResult) -> VerificationResult:
        """Verify rebuild subtask."""
        detail = result.detail
        
        files_regenerated = detail.get("files_regenerated", 0)
        error = detail.get("error")
        
        if not error and files_regenerated >= 0:
            return VerificationResult(True, f"Rebuild succeeded - {files_regenerated} files regenerated")
        elif error:
            return VerificationResult(False, f"Rebuild failed with error: {error}")
        else:
            return VerificationResult(False, "Rebuild failed - unknown error")
    
    def _verify_watch_start(self, task: SubTask, result: SubTaskResult) -> VerificationResult:
        """Verify watch_start subtask."""
        detail = result.detail
        
        is_alive = detail.get("is_alive", False)
        
        if is_alive:
            return VerificationResult(True, "File watcher started successfully")
        else:
            return VerificationResult(False, "File watcher failed to start")
    
    def _verify_watch_stop(self, task: SubTask, result: SubTaskResult) -> VerificationResult:
        """Verify watch_stop subtask."""
        detail = result.detail
        
        is_alive = detail.get("is_alive", True)  # Default to True to check it stopped
        
        if not is_alive:
            return VerificationResult(True, "File watcher stopped successfully")
        else:
            return VerificationResult(False, "File watcher is still running")
    
    def _verify_ask_user(self, task: SubTask, result: SubTaskResult) -> VerificationResult:
        """Verify ask_user subtask."""
        # ask_user always passes - it's a signal, not an action
        return VerificationResult(True, "User question posed")
