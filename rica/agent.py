import uuid
import re
from loguru import logger
from rica.planner import RicaPlanner
from rica.codegen import RicaCodegen
from rica.executor import RicaExecutor
from rica.debugger import RicaDebugger
from rica.workspace import WorkspaceMemory
from rica.result import RicaResult
from rica.utils.paths import ensure_workspace

MAX_ITERATIONS = 5

class RicaAgent:
    """
    Autonomous coding agent.
    Callable by ALARA's CodingAgent.

    Usage:
        from rica import RicaAgent
        agent = RicaAgent(config)
        result = agent.run(goal, workspace_name)
    """

    def __init__(self, config: dict):
        """
        config must contain:
            api_key: str    (Gemini API key)
            model: str      (e.g. gemini-2.5-flash)
        """
        self.config = config
        self.planner = RicaPlanner(config)
        self.codegen = RicaCodegen(config)
        self.debugger = RicaDebugger(config)

    def run(
        self,
        goal: str,
        workspace_name: str | None = None,
    ) -> RicaResult:
        """
        Main entry point. Runs the full
        plan → generate → execute → debug loop.
        Returns a RicaResult.
        """
        # Fix B: Sanitize workspace name if provided to remove special characters
        if workspace_name:
            # Apply the same sanitization logic as specified
            slug = re.sub(
                r"[^a-zA-Z0-9_\-]", "", 
                workspace_name[:50].lower().replace(' ', '_')
            )[:35]
            workspace_name = slug
        
        ws_name = workspace_name or (
            f"rica_{uuid.uuid4().hex[:8]}"
        )
        workspace_dir = str(
            ensure_workspace(ws_name)
        )
        memory = WorkspaceMemory(
            goal=goal,
            workspace_dir=workspace_dir,
        )

        logger.info(
            f"[rica] Starting: {goal[:60]}"
        )
        logger.info(
            f"[rica] Workspace: {workspace_dir}"
        )

        try:
            tasks = self.planner.plan(goal)
            logger.info(
                f"[rica] Planned "
                f"{len(tasks)} tasks"
            )

            for task in tasks:
                memory.iteration += 1
                self._run_task(
                    task, memory, workspace_dir
                )

            logger.info(
                f"[rica] Completed: "
                f"{memory.summary()}"
            )
            return RicaResult(
                success=True,
                goal=goal,
                workspace_dir=workspace_dir,
                files_created=memory.files_created,
                files_modified=memory.files_modified,
                summary=memory.summary(),
                iterations=memory.iteration,
            )

        except Exception as e:
            logger.error(
                f"[rica] Failed: {e}"
            )
            return RicaResult(
                success=False,
                goal=goal,
                workspace_dir=workspace_dir,
                error=str(e),
                iterations=memory.iteration,
            )

    def _run_task(
        self,
        task: dict,
        memory: WorkspaceMemory,
        workspace_dir: str,
    ) -> None:
        """
        Runs a single task through the
        codegen → execute → debug loop.
        """
        logger.debug(
            f"[rica] Task {task['id']}: "
            f"{task['description'][:60]}"
        )

        executor = RicaExecutor(workspace_dir)

        # Step 1: Generate code
        files = self.codegen.generate(
            task, workspace_dir,
            context=memory.summary()
        )
        for f in files:
            memory.record_file(f, created=True)

        if not files:
            logger.warning(
                f"[rica] No files generated "
                f"for task {task['id']}"
            )
            return

        # Step 2: If task type is execute or test,
        # run the command
        if task['type'] in ('execute', 'test'):
            original_cmd = task.get('command', '')
            if not original_cmd:
                # Infer: python <first_file>
                rel = files[0].replace(
                    workspace_dir, ''
                ).lstrip('/\\')
                original_cmd = f"python {rel}"

            cmd_to_run = original_cmd
            result = executor.run(cmd_to_run)
            logger.info(
                f"[rica] Executed: {cmd_to_run} → "
                f"exit={result['exit_code']}"
            )

            # Step 3: Debug loop if failed
            iteration = 0
            while (
                not result['success']
                and iteration < MAX_ITERATIONS
            ):
                iteration += 1
                memory.iteration += 1
                error = (
                    result['stderr']
                    or result['stdout']
                )
                memory.record_error(error)

                logger.warning(
                    f"[rica] Error on attempt "
                    f"{iteration}: {error[:80]}"
                )

                # Read current file for context
                code_context = ""
                if files:
                    try:
                        code_context = open(
                            files[0]
                        ).read()
                    except Exception:
                        pass

                fix_result = self.debugger.analyze(
                    error, code_context
                )
                
                # Extract fix text and revised command
                if isinstance(fix_result, dict):
                    fix_text = fix_result.get("fix", "")
                    revised_cmd = fix_result.get("revised_command")
                else:
                    fix_text = fix_result
                    revised_cmd = None

                # Use revised command if available, otherwise keep original
                cmd_to_run = revised_cmd or original_cmd

                # Re-generate with fix context
                fix_task = {
                    "id": task['id'],
                    "description": (
                        f"{task['description']}. "
                        f"{fix_text}"
                    ),
                    "type": "fix",
                }
                new_files = self.codegen.generate(
                    fix_task, workspace_dir,
                    context=memory.summary()
                )
                for f in new_files:
                    memory.record_file(
                        f, created=False
                    )
                if new_files:
                    files = new_files

                result = executor.run(cmd_to_run)
                logger.info(
                    f"[rica] Re-ran after fix "
                    f"{iteration}: "
                    f"exit={result['exit_code']}"
                )

            if result['success']:
                logger.info(
                    f"[rica] Task {task['id']} "
                    f"succeeded after "
                    f"{iteration} fixes"
                )
            else:
                logger.error(
                    f"[rica] Task {task['id']} "
                    f"failed after "
                    f"{MAX_ITERATIONS} attempts"
                )
