from rica.planner import RicaPlanner
from rica.memory.memory_store import get_memory_store


class PlannerAgent:
    def __init__(self, config: dict):
        self.config = config
        self.planner = RicaPlanner(config)

    def plan(
        self,
        goal: str,
        snapshot=None,
        tool_names: list[str] | None = None,
        workspace_files: list[str] | None = None,
        workspace_dir: str | None = None,
    ) -> list[dict]:
        planning_goal = goal
        
        # Add memory context if available
        if workspace_dir:
            try:
                memory_store = get_memory_store(workspace_dir)
                memory_summary = memory_store.get_memory_summary()
                if memory_summary:
                    planning_goal = (
                        f"{goal}\n\n"
                        f"Previous work completed:\n"
                        f"{memory_summary}\n\n"
                        f"Use this context when planning."
                    )
            except Exception as e:
                # If memory loading fails, continue without it
                pass
        
        if tool_names:
            planning_goal = (
                f"{planning_goal}\n"
                f"Available tools: "
                f"{', '.join(tool_names)}"
            )
        tasks = self.planner.plan(
            planning_goal, snapshot, tool_names, workspace_files
        )
        normalized = []
        for index, task in enumerate(tasks, start=1):
            item = dict(task)
            item.setdefault("id", index)
            item.setdefault("type", "codegen")
            item.setdefault("status", "pending")
            if tool_names:
                item.setdefault("available_tools", tool_names)
            normalized.append(item)
        return normalized
