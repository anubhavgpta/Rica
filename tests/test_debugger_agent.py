"""Unit tests for the autonomous debugger agent."""

import pytest
from unittest.mock import Mock, patch
from rica.agents.debugger_agent import DebuggerAgent


class TestDebuggerAgent:
    """Test cases for DebuggerAgent autonomous debugging functionality."""

    def test_debugger_agent_initialization(self):
        """Test that DebuggerAgent initializes correctly."""
        config = {
            "max_error_history": 100,
            "error_repeat_threshold": 3,
            "api_key": "test_key"
        }
        agent = DebuggerAgent(config)
        
        assert agent.config == config
        assert agent.max_error_history == 100
        assert agent.repeat_threshold == 3
        assert agent.error_history == []
        assert agent.learned_patterns == []

    def test_error_pattern_recognition(self):
        """Test that common error patterns are recognized correctly."""
        config = {"max_error_history": 50, "error_repeat_threshold": 3, "api_key": "test_key"}
        agent = DebuggerAgent(config)
        
        # Test ModuleNotFoundError
        error = "ModuleNotFoundError: No module named 'numpy'"
        pattern = agent._recognize_error_pattern(error)
        
        assert pattern is not None
        assert pattern["error_type"] == "ModuleNotFoundError"
        assert pattern["action"] == "install_dependency"
        assert pattern["match_groups"] == ("numpy",)

    def test_syntax_error_recognition(self):
        """Test syntax error pattern recognition."""
        config = {"max_error_history": 50, "error_repeat_threshold": 3, "api_key": "test_key"}
        agent = DebuggerAgent(config)
        
        error = "SyntaxError: invalid syntax (<unknown>, line 5)"
        pattern = agent._recognize_error_pattern(error)
        
        assert pattern is not None
        assert pattern["error_type"] == "SyntaxError"
        assert pattern["action"] == "regenerate_code"

    def test_name_error_recognition(self):
        """Test NameError pattern recognition."""
        config = {"max_error_history": 50, "error_repeat_threshold": 3, "api_key": "test_key"}
        agent = DebuggerAgent(config)
        
        error = "NameError: name 'undefined_var' is not defined"
        pattern = agent._recognize_error_pattern(error)
        
        assert pattern is not None
        assert pattern["error_type"] == "NameError"
        assert pattern["match_groups"] == ("undefined_var",)

    def test_pattern_based_fix_generation(self):
        """Test fix generation based on recognized patterns."""
        config = {"max_error_history": 50, "error_repeat_threshold": 3, "api_key": "test_key"}
        agent = DebuggerAgent(config)
        
        # Test ModuleNotFoundError fix
        pattern_info = {
            "error_type": "ModuleNotFoundError",
            "action": "install_dependency",
            "match_groups": ("pandas",)
        }
        
        fix = agent._generate_pattern_based_fix(pattern_info, "", {})
        assert "pip install pandas" in fix

    def test_error_normalization(self):
        """Test error message normalization for comparison."""
        config = {"max_error_history": 50, "error_repeat_threshold": 3, "api_key": "test_key"}
        agent = DebuggerAgent(config)
        
        error1 = "FileNotFoundError: [Errno 2] No such file or directory: 'C:\\Users\\test\\file.py'"
        error2 = "FileNotFoundError: [Errno 2] No such file or directory: 'D:\\other\\path\\file.py'"
        
        normalized1 = agent._normalize_error(error1)
        normalized2 = agent._normalize_error(error2)
        
        # Both should be normalized to lowercase
        assert normalized1.islower()
        assert normalized2.islower()
        
        # Both should contain the error type
        assert "filenotfounderror" in normalized1
        assert "filenotfounderror" in normalized2
        
        # Both should contain the error description
        assert "no such file or directory" in normalized1
        assert "no such file or directory" in normalized2
        
        # Line numbers should be normalized
        assert "line x" in normalized1 or "line" not in normalized1
        assert "line x" in normalized2 or "line" not in normalized2
        
        # Test that whitespace is normalized
        assert "  " not in normalized1  # no double spaces
        assert "  " not in normalized2

    def test_should_stop_retrying(self):
        """Test retry stopping logic."""
        config = {"max_error_history": 50, "error_repeat_threshold": 2, "api_key": "test_key"}
        agent = DebuggerAgent(config)
        
        error = "NameError: name 'x' is not defined"
        task = {"id": "test_task", "description": "Test task"}
        
        # First time - should not stop
        assert not agent._should_stop_retrying(error)
        
        # Record the error
        agent._record_error(error, task, "fix suggestion")
        
        # Second time - should not stop yet
        assert not agent._should_stop_retrying(error)
        
        # Record same error again
        agent._record_error(error, task, "fix suggestion")
        
        # Third time - should stop
        assert agent._should_stop_retrying(error)

    def test_extract_failing_file(self):
        """Test extraction of failing file from traceback."""
        config = {"max_error_history": 50, "error_repeat_threshold": 3, "api_key": "test_key"}
        agent = DebuggerAgent(config)
        
        error = 'Traceback (most recent call last):\n  File "C:\\test\\script.py", line 10, in <module>\n    main()\nNameError: name \'x\' is not defined'
        
        failing_file = agent._extract_failing_file(error)
        assert failing_file == "C:\\test\\script.py"

    def test_extract_code_snippet(self):
        """Test extraction of code snippet from snapshot."""
        config = {"max_error_history": 50, "error_repeat_threshold": 3, "api_key": "test_key"}
        agent = DebuggerAgent(config)
        
        # Mock snapshot
        snapshot = Mock()
        snapshot.files = {
            "script.py": "def main():\n    x = 5\n    print(y)\n    return x"
        }
        
        snippet = agent._extract_code_snippet("script.py", snapshot)
        assert "def main():" in snippet
        assert "print(y)" in snippet

    def test_build_debugger_prompt(self):
        """Test debugger prompt building."""
        config = {"max_error_history": 50, "error_repeat_threshold": 3, "api_key": "test_key"}
        agent = DebuggerAgent(config)
        
        error = "NameError: name 'x' is not defined"
        task = {"description": "Fix the undefined variable error"}
        failing_file = "script.py"
        code_snippet = "def main():\n    print(x)"
        context = "Similar errors seen before"
        
        prompt = agent._build_debugger_prompt(error, task, failing_file, code_snippet, context)
        
        assert error in prompt
        assert failing_file in prompt
        assert code_snippet in prompt
        assert task["description"] in prompt
        assert context in prompt
        assert "Fix the bug" in prompt

    @patch('rica.agents.debugger_agent.logger')
    def test_analyze_with_pattern_recognition(self, mock_logger):
        """Test analyze method with pattern recognition."""
        config = {"max_error_history": 50, "error_repeat_threshold": 3, "api_key": "test_key"}
        agent = DebuggerAgent(config)
        
        error = "ModuleNotFoundError: No module named 'requests'"
        task = {"id": "test", "description": "Test task"}
        
        result = agent.analyze(error, task)
        
        assert result["pattern_recognized"] is True
        assert result["pattern_type"] == "ModuleNotFoundError"
        assert "pip install requests" in result["fix"]
        assert result["stop_retrying"] is False

    @patch('rica.agents.debugger_agent.logger')
    def test_analyze_with_stop_retrying(self, mock_logger):
        """Test analyze method when retry should stop."""
        config = {"max_error_history": 50, "error_repeat_threshold": 2, "api_key": "test_key"}
        agent = DebuggerAgent(config)
        
        error = "NameError: name 'x' is not defined"
        task = {"id": "test", "description": "Test task"}
        
        # Record error multiple times to trigger stop
        agent._record_error(error, task, "fix1")
        agent._record_error(error, task, "fix2")
        
        result = agent.analyze(error, task)
        
        assert result["stop_retrying"] is True
        assert "Error repeated 2 times" in result["fix"]

    def test_learn_pattern(self):
        """Test pattern learning from successful fixes."""
        config = {"max_error_history": 50, "error_repeat_threshold": 3, "api_key": "test_key"}
        agent = DebuggerAgent(config)
        
        error = "ValueError: invalid literal for int()"
        fix = "Add input validation for integer conversion"
        
        agent.learn_pattern(error, fix, success=True)
        
        assert len(agent.learned_patterns) == 1
        assert agent.learned_patterns[0]["pattern"] == agent._normalize_error(error)[:100]
        assert agent.learned_patterns[0]["fix"] == fix
        assert agent.learned_patterns[0]["confidence"] == 0.7

    def test_get_similar_errors(self):
        """Test retrieval of similar errors from history."""
        config = {"max_error_history": 50, "error_repeat_threshold": 3, "api_key": "test_key"}
        agent = DebuggerAgent(config)
        
        error = "NameError: name 'x' is not defined"
        task = {"id": "test", "description": "Test task"}
        
        # Record similar errors
        agent._record_error(error, task, "fix1")
        agent._record_error("NameError: name 'x' is not defined", task, "fix2")
        agent._record_error("ValueError: something else", task, "fix3")
        
        similar = agent.get_similar_errors(error)
        
        assert len(similar) == 2
        assert all("name 'x' is not defined" in item["error"] for item in similar)

    def test_error_history_size_limit(self):
        """Test that error history respects size limits."""
        config = {"max_error_history": 3, "error_repeat_threshold": 3, "api_key": "test_key"}
        agent = DebuggerAgent(config)
        
        task = {"id": "test", "description": "Test task"}
        
        # Add more errors than the limit
        for i in range(5):
            agent._record_error(f"Error {i}", task, f"fix {i}")
        
        assert len(agent.error_history) == 3
        assert agent.error_history[-1]["error"] == "Error 4"

    def test_comprehensive_error_patterns(self):
        """Test all defined error patterns."""
        config = {"max_error_history": 50, "error_repeat_threshold": 3, "api_key": "test_key"}
        agent = DebuggerAgent(config)
        
        test_cases = [
            ("ImportError: cannot import name 'nonexistent'", "ImportError"),
            ("TypeError: can only concatenate str (not \"int\") to str", "TypeError"),
            ("AttributeError: 'list' object has no attribute 'push'", "AttributeError"),
            ("KeyError: 'missing_key'", "KeyError"),
            ("FileNotFoundError: [Errno 2] No such file or directory: 'test.txt'", "FileNotFoundError"),
            ("PermissionError: [Errno 13] Permission denied: 'protected.txt'", "PermissionError"),
            ("ConnectionError: Failed to establish connection", "ConnectionError"),
            ("ValueError: invalid literal for int() with base 10: 'abc'", "ValueError"),
            ("IndexError: list index out of range", "IndexError"),
            ("AssertionError: assert x == y", "AssertionError"),
        ]
        
        for error, expected_type in test_cases:
            pattern = agent._recognize_error_pattern(error)
            assert pattern is not None, f"Pattern not recognized for {expected_type}"
            assert pattern["error_type"] == expected_type


if __name__ == "__main__":
    pytest.main([__file__])
