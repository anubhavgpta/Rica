"""Unit tests for the Agent Orchestrator."""

import pytest
from unittest.mock import Mock, patch, MagicMock
from rica.core.orchestrator import AgentOrchestrator


class TestAgentOrchestrator:
    """Test cases for AgentOrchestrator functionality."""

    def test_orchestrator_initialization(self):
        """Test that AgentOrchestrator initializes correctly."""
        config = {
            "max_parallel_workers": 4,
            "enable_parallel_execution": True,
            "api_key": "test_key"
        }
        orchestrator = AgentOrchestrator(config)
        
        assert orchestrator.config == config
        assert orchestrator.max_workers == 4
        assert orchestrator.enable_parallel is True
        assert orchestrator.planner is None  # Not initialized yet
        assert orchestrator.memory is None  # Not initialized yet

    @patch('rica.core.orchestrator.ensure_workspace')
    @patch('rica.core.orchestrator.CodebaseReader')
    @patch('google.genai.Client')
    @patch('rica.core.orchestrator.AgentOrchestrator._initialize_agents')
    @patch('rica.core.orchestrator.AgentOrchestrator._plan_tasks')
    def test_orchestrator_run_basic(self, mock_plan_tasks, mock_init_agents, mock_client, mock_reader, mock_workspace):
        """Test basic orchestrator run functionality."""
        config = {"api_key": "test_key", "model": "test_model"}
        orchestrator = AgentOrchestrator(config)
        
        # Mock workspace setup
        mock_workspace.return_value = "/test/workspace"
        
        # Mock CodebaseReader and snapshot
        mock_reader_instance = Mock()
        mock_reader.return_value = mock_reader_instance
        mock_snapshot = Mock()
        mock_snapshot.summary = "Test project summary"
        mock_reader_instance.snapshot.return_value = mock_snapshot
        
        # Mock genai client
        mock_client_instance = Mock()
        mock_client.return_value = mock_client_instance
        
        # Mock task planning
        mock_tasks = [
            {"id": "task-1", "description": "Create main.py", "type": "codegen"},
            {"id": "task-2", "description": "Test the application", "type": "test"}
        ]
        mock_plan_tasks.return_value = mock_tasks
        
        # Mock task execution
        with patch.object(orchestrator, '_execute_tasks_sequential') as mock_execute:
            mock_execute.return_value = [
                {"success": True, "files": ["main.py"]},
                {"success": True, "files": []}
            ]
            
            # Mock cleanup and result generation
            with patch.object(orchestrator, '_cleanup'), \
                 patch.object(orchestrator, '_generate_result') as mock_result:
                
                mock_result.return_value = Mock(
                    success=True,
                    goal="Create a Python application",
                    workspace_dir="/test/workspace",
                    files_created=["main.py"],
                    iterations=1
                )
                
                result = orchestrator.run("Create a Python application", "/test/project")
        
        assert result.success is True
        assert result.goal == "Create a Python application"
        assert len(result.files_created) == 1
        assert "main.py" in result.files_created

    def test_can_run_parallel_detection(self):
        """Test parallel execution detection logic."""
        config = {"api_key": "test_key"}
        orchestrator = AgentOrchestrator(config)
        
        # Independent tasks should run in parallel
        independent_tasks = [
            {"description": "Create file A"},
            {"description": "Create file B"},
            {"description": "Create file C"}
        ]
        assert orchestrator._can_run_parallel(independent_tasks) is True
        
        # Tasks with dependencies should run sequentially
        dependent_tasks = [
            {"description": "Create file A after file B"},
            {"description": "Create file B"},
            {"description": "Create file C before file D"}
        ]
        assert orchestrator._can_run_parallel(dependent_tasks) is False
        
        # Single task should run sequentially
        single_task = [{"description": "Create file A"}]
        assert orchestrator._can_run_parallel(single_task) is False

    def test_validate_tasks(self):
        """Test task validation."""
        config = {"api_key": "test_key"}
        orchestrator = AgentOrchestrator(config)
        
        # Valid tasks
        valid_tasks = [
            {"description": "Create main.py"},
            {"description": "Write tests"}
        ]
        validated = orchestrator._validate_tasks(valid_tasks)
        
        assert len(validated) == 2
        assert all("id" in task for task in validated)
        assert all("type" in task for task in validated)
        assert all("status" in task for task in validated)
        
        # Tasks without descriptions should be filtered
        invalid_tasks = [
            {"description": "Create main.py"},
            {"type": "codegen"},  # Missing description
            {"description": "Write tests"}
        ]
        validated = orchestrator._validate_tasks(invalid_tasks)
        
        assert len(validated) == 2  # One filtered out

    @patch('rica.core.orchestrator.MemoryAgent')
    @patch('rica.core.orchestrator.DebuggerAgent')
    @patch('rica.core.orchestrator.ReviewerAgent')
    @patch('rica.core.orchestrator.ExecutorAgent')
    @patch('rica.core.orchestrator.CoderAgent')
    @patch('rica.core.orchestrator.ResearchAgent')
    @patch('rica.core.orchestrator.PlannerAgent')
    def test_initialize_agents(self, mock_planner, mock_researcher, mock_coder, 
                              mock_executor, mock_reviewer, mock_debugger, mock_memory):
        """Test agent initialization."""
        config = {"api_key": "test_key"}
        orchestrator = AgentOrchestrator(config)
        
        # Set up workspace
        orchestrator.workspace_dir = "/test/workspace"
        orchestrator.project_dir = "/test/project"
        
        # Initialize agents
        orchestrator._initialize_agents()
        
        # Check that all agents were created
        mock_planner.assert_called_once_with(config)
        mock_researcher.assert_called_once_with(config)
        mock_coder.assert_called_once_with(config)
        mock_executor.assert_called_once_with("/test/project")
        mock_debugger.assert_called_once_with(config, "/test/workspace")
        mock_reviewer.assert_called_once_with(config)
        mock_memory.assert_called_once_with(config, "/test/workspace")

    def test_generate_execution_summary(self):
        """Test execution summary generation."""
        config = {"api_key": "test_key"}
        orchestrator = AgentOrchestrator(config)
        
        results = [
            {"success": True, "files": ["main.py", "utils.py"], "execution_time": 2.5},
            {"success": True, "files": [], "execution_time": 1.0},
            {"success": False, "files": [], "execution_time": 0.5, "error": "Test failed"}
        ]
        
        summary = orchestrator._generate_execution_summary(results)
        
        assert "Tasks: 2/3 completed" in summary
        assert "Files created: 2" in summary
        assert "Total execution time: 4.00s" in summary
        assert "Failed tasks: 1" in summary

    @patch('rica.core.orchestrator.MemoryAgent')
    def test_enhance_tasks_with_memory(self, mock_memory):
        """Test task enhancement with memory context."""
        config = {"api_key": "test_key"}
        orchestrator = AgentOrchestrator(config)
        orchestrator.memory = mock_memory
        
        tasks = [
            {"id": "task-1", "description": "Create API endpoint"},
            {"id": "task-2", "description": "Write tests"}
        ]
        
        # Mock memory context
        mock_memory.get_context_for_task.return_value = {
            "similar_tasks": [{"description": "Previous API work"}],
            "related_bugs": []
        }
        
        enhanced = orchestrator._enhance_tasks_with_memory(tasks)
        
        assert len(enhanced) == 2
        assert "memory_context" in enhanced[0]
        assert "memory_context" in enhanced[1]
        mock_memory.get_context_for_task.assert_called()

    def test_infer_execution_commands(self):
        """Test command inference for different file types."""
        config = {"api_key": "test_key"}
        orchestrator = AgentOrchestrator(config)
        
        # Python files with test description
        py_files = ["test_main.py", "main.py"]
        commands = orchestrator._infer_execution_commands(py_files, "test the application")
        assert "python -m pytest" in commands
        
        # Python files with run description - test_main.py contains "main" so it gets chosen
        commands = orchestrator._infer_execution_commands(py_files, "run the application")
        assert any("python test_main.py" in cmd for cmd in commands)
        
        # Files with requirements
        files_with_req = ["requirements.txt", "main.py"]
        commands = orchestrator._infer_execution_commands(files_with_req, "setup project")
        assert "pip install -r requirements.txt" in commands

    @patch('rica.core.orchestrator.ThreadPoolExecutor')
    @patch('rica.core.orchestrator.as_completed')
    def test_execute_tasks_parallel(self, mock_as_completed, mock_executor):
        """Test parallel task execution."""
        config = {"api_key": "test_key"}
        orchestrator = AgentOrchestrator(config)
        orchestrator.enable_parallel = True
        orchestrator.max_workers = 2
        
        # Mock memory agent
        mock_memory = Mock()
        orchestrator.memory = mock_memory
        
        tasks = [
            {"id": "task-1", "description": "Create file A"},
            {"id": "task-2", "description": "Create file B"}
        ]
        
        # Mock ThreadPoolExecutor and futures
        mock_future = Mock()
        mock_future.result.return_value = {"success": True, "files": ["fileA.py"]}
        
        mock_executor_instance = Mock()
        mock_executor_instance.__enter__ = Mock(return_value=mock_executor_instance)
        mock_executor_instance.__exit__ = Mock(return_value=None)
        mock_executor_instance.submit.return_value = mock_future
        mock_executor.return_value = mock_executor_instance
        
        # Mock as_completed to return the future
        mock_as_completed.return_value = [mock_future]
        
        with patch.object(orchestrator, '_execute_single_task') as mock_execute:
            mock_execute.return_value = {"success": True, "files": ["fileA.py"]}
            
            results = orchestrator._execute_tasks_parallel(tasks)
        
        assert len(results) == 1
        assert results[0]["success"] is True

    @patch('rica.core.orchestrator.MemoryAgent')
    def test_store_execution_knowledge(self, mock_memory):
        """Test execution knowledge storage."""
        config = {"api_key": "test_key"}
        orchestrator = AgentOrchestrator(config)
        orchestrator.memory = mock_memory
        
        results = [
            {"success": True, "task_type": "codegen", "execution_time": 2.0, "files": ["main.py"]},
            {"success": False, "task_type": "test", "error": "Test failed"}
        ]
        
        orchestrator._store_execution_knowledge("Build application", results)
        
        # Check that knowledge was stored
        assert mock_memory.store_knowledge.called
        calls = mock_memory.store_knowledge.call_args_list
        assert len(calls) >= 1  # At least success or failure patterns stored


if __name__ == "__main__":
    pytest.main([__file__])
