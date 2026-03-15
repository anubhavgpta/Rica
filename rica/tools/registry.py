from rica.tools.builtin import (
    install_package_tool,
    read_file_tool,
    run_command_tool,
    search_code_tool,
    write_file_tool,
)


class ToolRegistry:
    def __init__(self, reader=None):
        self.reader = reader
        self._tools = {
            "read_file": read_file_tool,
            "write_file": write_file_tool,
            "search_code": search_code_tool,
            "run_command": run_command_tool,
            "install_package": install_package_tool,
        }

    def names(self) -> list[str]:
        return sorted(self._tools.keys())

    def run(
        self,
        task: dict,
        workspace_dir: str,
        project_dir: str | None = None,
    ) -> dict:
        tool_name = task.get("tool")
        if tool_name not in self._tools:
            raise ValueError(
                f"Unknown tool: {tool_name}"
            )
        return self._tools[tool_name](
            task=task,
            workspace_dir=workspace_dir,
            project_dir=project_dir,
            reader=self.reader,
        )
