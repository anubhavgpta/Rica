from collections import deque
from concurrent.futures import ThreadPoolExecutor, Future
from typing import List, Dict, Any, Optional, Set
import threading
from dataclasses import dataclass
from loguru import logger

from rica.logging_utils import get_component_logger

task_logger = get_component_logger("task_queue")


TASK_PENDING = "pending"
TASK_IN_PROGRESS = "in_progress"
TASK_COMPLETED = "completed"
TASK_FAILED = "failed"


@dataclass
class TaskDependency:
    """Represents a dependency relationship between tasks."""
    task_id: str
    depends_on: str  # ID of task this depends on


class ParallelTaskQueue:
    """Enhanced task queue supporting parallel execution with dependency management."""
    
    def __init__(self, max_workers: int = 3):
        self._queue = deque()
        self._max_workers = max_workers
        self._executor = None
        self._running_tasks: Dict[str, Future] = {}
        self._completed_tasks: Set[str] = set()
        self._task_dependencies: List[TaskDependency] = []
        self._lock = threading.Lock()
        
    def add_tasks(
        self,
        tasks: list[dict],
        front: bool = False,
        dependencies: Optional[List[TaskDependency]] = None
    ) -> None:
        """Add tasks to the queue with optional dependencies."""
        iterable = reversed(tasks) if front else tasks
        for task in iterable:
            normalized = dict(task)
            normalized.setdefault("status", TASK_PENDING)
            normalized.setdefault("id", str(len(self._queue) + len(self._completed_tasks)))
            
            if front:
                self._queue.appendleft(normalized)
            else:
                self._queue.append(normalized)
        
        # Add dependencies if provided
        if dependencies:
            self._task_dependencies.extend(dependencies)
            task_logger.info(f"[task_queue] Added {len(dependencies)} task dependencies")
    
    def next_task(self) -> dict | None:
        """Get the next available task that can be executed."""
        with self._lock:
            for task in list(self._queue):
                if (task.get("status") == TASK_PENDING and 
                    self._can_execute_task(task.get("id", ""))):
                    task["status"] = TASK_IN_PROGRESS
                    return task
        return None
    
    def _can_execute_task(self, task_id: str) -> bool:
        """Check if a task can be executed based on its dependencies."""
        for dep in self._task_dependencies:
            if dep.task_id == task_id:
                if dep.depends_on not in self._completed_tasks:
                    return False
        return True
    
    def execute_tasks_parallel(
        self, 
        task_processor: callable, 
        workspace_dir: str,
        project_dir: str,
        memory: Any
    ) -> List[Dict[str, Any]]:
        """Execute tasks in parallel respecting dependencies."""
        if not self._executor:
            self._executor = ThreadPoolExecutor(max_workers=self._max_workers)
        
        results = []
        
        try:
            while self.has_pending() or self._running_tasks:
                # Start new tasks that are ready
                while len(self._running_tasks) < self._max_workers:
                    task = self.next_task()
                    if not task:
                        break
                    
                    future = self._executor.submit(
                        self._execute_single_task,
                        task,
                        task_processor,
                        workspace_dir,
                        project_dir,
                        memory
                    )
                    self._running_tasks[task.get("id", "")] = future
                    task_logger.info(f"[task_queue] Started task {task.get('id')}: {task.get('description', '')[:50]}")
                
                # Check for completed tasks
                completed_tasks = []
                for task_id, future in list(self._running_tasks.items()):
                    if future.done():
                        try:
                            result = future.result()
                            results.append(result)
                            completed_tasks.append(task_id)
                            self._completed_tasks.add(task_id)
                            task_logger.info(f"[task_queue] Completed task {task_id}")
                        except Exception as e:
                            task_logger.error(f"[task_queue] Task {task_id} failed: {e}")
                            results.append({
                                "success": False,
                                "error": str(e),
                                "task_id": task_id
                            })
                            completed_tasks.append(task_id)
                
                # Remove completed tasks from running list
                for task_id in completed_tasks:
                    del self._running_tasks[task_id]
                
                # Small delay to prevent busy waiting
                if self._running_tasks:
                    import time
                    time.sleep(0.1)
        
        finally:
            if self._executor:
                self._executor.shutdown(wait=True)
                self._executor = None
        
        task_logger.info(f"[task_queue] Parallel execution complete: {len(results)} tasks processed")
        return results
    
    def _execute_single_task(
        self, 
        task: dict, 
        task_processor: callable,
        workspace_dir: str,
        project_dir: str,
        memory: Any
    ) -> Dict[str, Any]:
        """Execute a single task."""
        try:
            result = task_processor(task, memory, workspace_dir, project_dir)
            return {
                "success": True,
                "task_id": task.get("id", ""),
                "result": result,
                "task": task
            }
        except Exception as e:
            return {
                "success": False,
                "task_id": task.get("id", ""),
                "error": str(e),
                "task": task
            }
    
    def requeue(self, task: dict) -> None:
        """Requeue a failed task for retry."""
        with self._lock:
            task["status"] = TASK_PENDING
            self._queue.appendleft(task)
            task_logger.info(f"[task_queue] Requeued task {task.get('id', '')}")
    
    def has_pending(self) -> bool:
        """Check if there are pending tasks."""
        return any(
            task.get("status") == TASK_PENDING
            for task in self._queue
        )
    
    def get_pending_count(self) -> int:
        """Get the number of pending tasks."""
        return sum(
            1 for task in self._queue
            if task.get("status") == TASK_PENDING
        )
    
    def get_running_count(self) -> int:
        """Get the number of currently running tasks."""
        return len(self._running_tasks)
    
    def get_completed_count(self) -> int:
        """Get the number of completed tasks."""
        return len(self._completed_tasks)
    
    def __len__(self) -> int:
        return len(self._queue)


# Backward compatibility - keep original TaskQueue
class TaskQueue(ParallelTaskQueue):
    """Backward compatible TaskQueue that defaults to single-threaded execution."""
    
    def __init__(self):
        super().__init__(max_workers=1)  # Single worker for backward compatibility
    
    def execute_tasks_parallel(self, task_processor, workspace_dir, project_dir, memory):
        """Fallback to sequential execution for backward compatibility."""
        results = []
        while self.has_pending():
            task = self.next_task()
            if not task:
                break
            
            try:
                result = self._execute_single_task(task, task_processor, workspace_dir, project_dir, memory)
                results.append(result)
            except Exception as e:
                results.append({
                    "success": False,
                    "error": str(e),
                    "task_id": task.get("id", "")
                })
        
        return results
