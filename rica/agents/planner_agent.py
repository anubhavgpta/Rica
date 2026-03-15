from rica.planner import RicaPlanner


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
    ) -> list[dict]:
        planning_goal = goal
        if tool_names:
            planning_goal = (
                f"{goal}\n"
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
