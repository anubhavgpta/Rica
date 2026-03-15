from rica.agents import (
    CoderAgent,
    DebuggerAgent,
    PlannerAgent,
    ReviewerAgent,
)
from rica.core.controller import MultiAgentController
from rica.logging_utils import setup_workspace_logging
from rica.memory import memory_manager
from rica.utils.paths import (
    ensure_workspace,
    sanitize_workspace_name,
)


class RicaAgent:
    """
    Autonomous multi-agent coding system.

    Public contract remains:
        agent = RicaAgent(config)
        result = agent.run(goal, project_dir, workspace_name)
    """

    def __init__(self, config: dict):
        self.config = config
        self.planner_agent = PlannerAgent(config)
        self.coder_agent = CoderAgent(config)
        self.reviewer_agent = ReviewerAgent(config)
        self.debugger_agent = DebuggerAgent(config)
        self.controller = MultiAgentController(config)

        # Preserve access to the existing core components.
        self.planner = self.planner_agent.planner
        self.codegen = self.coder_agent.codegen
        self.debugger = self.debugger_agent.debugger
        self.model = config.get(
            "model", "gemini-2.5-flash"
        )

    def run(
        self,
        goal: str,
        project_dir: str = None,
        workspace_name: str | None = None,
    ):
        resolved_workspace_name = (
            sanitize_workspace_name(workspace_name)
            if workspace_name
            else "project_x"
        )
        workspace = str(
            ensure_workspace(resolved_workspace_name)
        )
        setup_workspace_logging(workspace)
        memory_manager.load_memory(
            workspace, goal=goal
        )
        return self.controller.run(
            goal=goal,
            project_dir=project_dir,
            workspace_name=resolved_workspace_name,
        )
