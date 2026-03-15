from loguru import logger

from rica.core.task_queue import (
    TASK_COMPLETED,
    TASK_FAILED,
    TASK_IN_PROGRESS,
)


class WorkerPool:
    def __init__(self, size: int = 1):
        self.size = max(size, 1)

    def execute_task(
        self,
        task: dict,
        worker_fn,
    ) -> dict:
        task["status"] = TASK_IN_PROGRESS
        logger.info(
            f"[worker] Executing task {task['id']}: "
            f"{task.get('description', '')[:80]}"
        )
        try:
            result = worker_fn(task) or {}
            task["status"] = TASK_COMPLETED
            return result
        except Exception as error:
            task["status"] = TASK_FAILED
            logger.error(
                f"[worker] Task {task['id']} failed: {error}"
            )
            return {
                "success": False,
                "error": str(error),
                "revision_tasks": [],
            }
