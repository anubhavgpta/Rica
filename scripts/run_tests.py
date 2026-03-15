#!/usr/bin/env python3
"""Integration test runner for RICA system."""

import subprocess
import sys
from pathlib import Path
from typing import List, Dict, Any


def run_command(cmd: List[str], description: str) -> Dict[str, Any]:
    """Run a command and return results."""
    print(f"\n{'='*60}")
    print(f"Running: {description}")
    print(f"Command: {' '.join(cmd)}")
    print(f"{'='*60}")
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300  # 5 minute timeout
        )
        
        print(f"Return code: {result.returncode}")
        
        if result.stdout:
            print(f"STDOUT:\n{result.stdout}")
        
        if result.stderr:
            print(f"STDERR:\n{result.stderr}")
        
        return {
            "success": result.returncode == 0,
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr
        }
        
    except subprocess.TimeoutExpired:
        print("Command timed out!")
        return {
            "success": False,
            "returncode": -1,
            "stdout": "",
            "stderr": "Command timed out after 5 minutes"
        }
    except Exception as e:
        print(f"Error running command: {e}")
        return {
            "success": False,
            "returncode": -1,
            "stdout": "",
            "stderr": str(e)
        }


def run_unit_tests():
    """Run unit tests using pytest."""
    return run_command(
        ["python", "-m", "pytest", "tests/", "-v", "--tb=short"],
        "Unit Tests"
    )


def run_cli_test():
    """Test CLI functionality."""
    return run_command(
        ["python", "-m", "rica.cli", "--help"],
        "CLI Help Command"
    )


def run_import_tests():
    """Test that all modules can be imported."""
    import_tests = [
        ("python", "-c", "from rica.agent import RicaAgent; print('✅ RicaAgent import')"),
        ("python", "-c", "from rica.core.controller import MultiAgentController; print('✅ MultiAgentController import')"),
        ("python", "-c", "from rica.git.git_manager import GitManager; print('✅ GitManager import')"),
        ("python", "-c", "from rica.core.repo_summary import RepoSummarizer; print('✅ RepoSummarizer import')"),
        ("python", "-c", "from rica.core.project_analyzer import ProjectAnalyzer; print('✅ ProjectAnalyzer import')"),
        ("python", "-c", "from rica.core.task_queue import ParallelTaskQueue; print('✅ ParallelTaskQueue import')"),
        ("python", "-c", "from rica.memory.project_memory import ProjectMemory; print('✅ ProjectMemory import')"),
        ("python", "-c", "from rica.agents.debugger_agent import DebuggerAgent; print('✅ DebuggerAgent import')"),
    ]
    
    results = []
    for cmd in import_tests:
        result = run_command(list(cmd), f"Import Test: {cmd[2]}")
        results.append(result)
    
    return {
        "success": all(r["success"] for r in results),
        "results": results
    }


def run_integration_tests():
    """Run integration tests."""
    return run_command(
        ["python", "-m", "pytest", "tests/test_agent_e2e.py", "-v", "-s"],
        "Integration Tests"
    )


def check_project_structure():
    """Check that all required files and directories exist."""
    project_root = Path(__file__).parent.parent
    
    required_files = [
        "rica/__init__.py",
        "rica/cli.py",
        "rica/agent.py",
        "rica/config.py",
        "rica/core/__init__.py",
        "rica/core/controller.py",
        "rica/core/task_queue.py",
        "rica/agents/__init__.py",
        "rica/agents/planner_agent.py",
        "rica/agents/coder_agent.py",
        "rica/agents/debugger_agent.py",
        "rica/git/__init__.py",
        "rica/git/git_manager.py",
        "rica/core/repo_summary.py",
        "rica/core/project_analyzer.py",
        "rica/memory/__init__.py",
        "rica/memory/project_memory.py",
        "tests/__init__.py",
        "tests/test_cli.py",
        "tests/test_planner.py",
        "tests/test_agent_e2e.py",
        "scripts/run_tests.py",
        "pyproject.toml",
    ]
    
    print(f"\n{'='*60}")
    print("Checking Project Structure")
    print(f"{'='*60}")
    
    missing_files = []
    for file_path in required_files:
        full_path = project_root / file_path
        if full_path.exists():
            print(f"✅ {file_path}")
        else:
            print(f"❌ {file_path} - MISSING")
            missing_files.append(file_path)
    
    return {
        "success": len(missing_files) == 0,
        "missing_files": missing_files
    }


def main():
    """Main test runner."""
    print("🚀 RICA System Test Runner")
    print("Running comprehensive tests to validate the autonomous developer system...")
    
    # Change to project root
    project_root = Path(__file__).parent.parent
    import os
    os.chdir(project_root)
    
    all_results = []
    
    # 1. Check project structure
    structure_result = check_project_structure()
    all_results.append(("Project Structure", structure_result))
    
    # 2. Run import tests
    import_result = run_import_tests()
    all_results.append(("Import Tests", import_result))
    
    # 3. Run CLI test
    cli_result = run_cli_test()
    all_results.append(("CLI Test", cli_result))
    
    # 4. Run unit tests
    unit_result = run_unit_tests()
    all_results.append(("Unit Tests", unit_result))
    
    # 5. Run integration tests
    integration_result = run_integration_tests()
    all_results.append(("Integration Tests", integration_result))
    
    # Summary
    print(f"\n{'='*60}")
    print("TEST SUMMARY")
    print(f"{'='*60}")
    
    passed = 0
    total = len(all_results)
    
    for test_name, result in all_results:
        success = result.get("success", False)
        status = "✅ PASSED" if success else "❌ FAILED"
        print(f"{status} {test_name}")
        if success:
            passed += 1
    
    print(f"\nResults: {passed}/{total} test suites passed")
    
    if passed == total:
        print("🎉 All tests passed! RICA system is ready for autonomous development.")
        return 0
    else:
        print("⚠️  Some tests failed. Please review the output above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
