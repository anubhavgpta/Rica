"""Unit tests for memory store functionality."""

import pytest
import json
import tempfile
import shutil
from pathlib import Path
from rica.memory.memory_store import MemoryStore, get_memory_store, load_memory, save_memory, append_memory


class TestMemoryStore:
    """Test cases for MemoryStore functionality."""

    def setup_method(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.memory_store = MemoryStore(self.temp_dir)

    def teardown_method(self):
        """Clean up test environment."""
        shutil.rmtree(self.temp_dir)

    def test_memory_store_initialization(self):
        """Test that MemoryStore initializes correctly."""
        assert self.memory_store.workspace_dir == Path(self.temp_dir)
        assert self.memory_store.memory_file == Path(self.temp_dir) / ".rica_memory.json"
        assert self.memory_store.max_entries_per_category == 100
        
        # Check default structure
        assert "tasks_completed" in self.memory_store.memory
        assert "files_created" in self.memory_store.memory
        assert "bugs_fixed" in self.memory_store.memory
        assert "commands_run" in self.memory_store.memory
        assert "knowledge" in self.memory_store.memory
        assert "project_metadata" in self.memory_store.memory

    def test_memory_store_load_existing(self):
        """Test loading existing memory file."""
        # Create existing memory file
        existing_data = {
            "tasks_completed": [{"id": "1", "description": "Test task"}],
            "files_created": [{"path": "test.py"}],
            "project_metadata": {"created_at": 1234567890}
        }
        
        memory_file = Path(self.temp_dir) / ".rica_memory.json"
        with open(memory_file, 'w') as f:
            json.dump(existing_data, f)
        
        # Create new MemoryStore instance
        new_store = MemoryStore(self.temp_dir)
        
        assert len(new_store.memory["tasks_completed"]) == 1
        assert new_store.memory["tasks_completed"][0]["description"] == "Test task"
        assert len(new_store.memory["files_created"]) == 1
        assert new_store.memory["files_created"][0]["path"] == "test.py"

    def test_append_memory(self):
        """Test appending data to memory categories."""
        # Test appending to tasks_completed
        task_data = {"id": "task1", "description": "Create hello world script"}
        self.memory_store.append_memory("tasks_completed", task_data)
        
        tasks = self.memory_store.get_category("tasks_completed")
        assert len(tasks) == 1
        assert tasks[0]["id"] == "task1"
        assert tasks[0]["description"] == "Create hello world script"
        assert "timestamp" in tasks[0]

    def test_append_memory_with_timestamp(self):
        """Test that timestamp is added if not present."""
        data_without_timestamp = {"path": "test.py", "size": 1024}
        self.memory_store.append_memory("files_created", data_without_timestamp)
        
        files = self.memory_store.get_category("files_created")
        assert len(files) == 1
        assert "timestamp" in files[0]
        assert files[0]["path"] == "test.py"
        assert files[0]["size"] == 1024

    def test_append_memory_preserves_existing_timestamp(self):
        """Test that existing timestamp is preserved."""
        data_with_timestamp = {"path": "test.py", "timestamp": 1234567890}
        self.memory_store.append_memory("files_created", data_with_timestamp)
        
        files = self.memory_store.get_category("files_created")
        assert len(files) == 1
        assert files[0]["timestamp"] == 1234567890

    def test_category_size_limiting(self):
        """Test that categories respect size limits."""
        # Set a small limit for testing
        self.memory_store.max_entries_per_category = 3
        
        # Add more entries than the limit
        for i in range(5):
            self.memory_store.append_memory("tasks_completed", {"id": f"task{i}", "description": f"Task {i}"})
        
        tasks = self.memory_store.get_category("tasks_completed")
        assert len(tasks) == 3  # Should be limited to 3
        
        # Should keep the most recent entries
        assert tasks[0]["id"] == "task2"
        assert tasks[1]["id"] == "task3"
        assert tasks[2]["id"] == "task4"

    def test_memory_persistence(self):
        """Test that memory is persisted to disk."""
        # Add some data
        self.memory_store.append_memory("tasks_completed", {"id": "1", "description": "Test task"})
        self.memory_store.append_memory("files_created", {"path": "test.py"})
        
        # Create new instance to test loading
        new_store = MemoryStore(self.temp_dir)
        
        tasks = new_store.get_category("tasks_completed")
        files = new_store.get_category("files_created")
        
        assert len(tasks) == 1
        assert tasks[0]["description"] == "Test task"
        assert len(files) == 1
        assert files[0]["path"] == "test.py"

    def test_get_memory_summary(self):
        """Test memory summary generation."""
        # Add some test data
        import time
        current_time = time.time()
        
        self.memory_store.memory["project_metadata"]["created_at"] = current_time
        self.memory_store.append_memory("tasks_completed", {"id": "1", "description": "Task 1"})
        self.memory_store.append_memory("files_created", {"path": "file1.py"})
        self.memory_store.append_memory("bugs_fixed", {"error": "SyntaxError", "fix": "Added missing colon"})
        
        summary = self.memory_store.get_memory_summary()
        
        assert "Total tasks: 1" in summary
        assert "Total files: 1" in summary
        assert "Total bugs fixed: 1" in summary
        assert "Task 1" in summary
        assert "file1.py" in summary
        assert "SyntaxError" in summary

    def test_search_memory(self):
        """Test memory search functionality."""
        # Add test data
        self.memory_store.append_memory("tasks_completed", {"id": "1", "description": "Create API endpoint"})
        self.memory_store.append_memory("files_created", {"path": "api.py"})
        self.memory_store.append_memory("bugs_fixed", {"error": "ImportError", "fix": "Add missing import"})
        
        # Search for "API"
        results = self.memory_store.search_memory("API")
        
        assert len(results) == 2  # Should find task and file
        assert any(r["category"] == "tasks_completed" for r in results)
        assert any(r["category"] == "files_created" for r in results)

    def test_clear_category(self):
        """Test clearing a memory category."""
        # Add some data
        self.memory_store.append_memory("tasks_completed", {"id": "1", "description": "Task 1"})
        self.memory_store.append_memory("tasks_completed", {"id": "2", "description": "Task 2"})
        
        assert len(self.memory_store.get_category("tasks_completed")) == 2
        
        # Clear category
        self.memory_store.clear_category("tasks_completed")
        
        assert len(self.memory_store.get_category("tasks_completed")) == 0

    def test_get_statistics(self):
        """Test memory statistics generation."""
        # Add test data
        self.memory_store.append_memory("tasks_completed", {"id": "1", "description": "Task 1"})
        self.memory_store.append_memory("files_created", {"path": "file1.py"})
        self.memory_store.append_memory("bugs_fixed", {"error": "SyntaxError", "fix": "Fix"})
        
        stats = self.memory_store.get_statistics()
        
        assert stats["total_entries"] == 3
        assert stats["categories"]["tasks_completed"] == 1
        assert stats["categories"]["files_created"] == 1
        assert stats["categories"]["bugs_fixed"] == 1
        assert stats["file_size_bytes"] > 0
        assert stats["file_size_mb"] >= 0

    def test_corrupted_memory_file_handling(self):
        """Test handling of corrupted memory file."""
        # Use a different temp directory to avoid conflicts
        temp_dir = tempfile.mkdtemp()
        try:
            memory_file = Path(temp_dir) / ".rica_memory.json"
            
            # Create corrupted JSON file
            with open(memory_file, 'w') as f:
                f.write("{ invalid json")
            
            # Should create new memory file without recursion
            new_store = MemoryStore(temp_dir)
            
            # Should have default structure
            assert "tasks_completed" in new_store.memory
            assert len(new_store.memory["tasks_completed"]) == 0
        finally:
            shutil.rmtree(temp_dir)

    def test_global_memory_functions(self):
        """Test global memory store functions."""
        # Test get_memory_store
        store1 = get_memory_store(self.temp_dir)
        store2 = get_memory_store(self.temp_dir)
        
        # Should return same instance
        assert store1 is store2
        
        # Test load_memory
        memory_data = load_memory(self.temp_dir)
        assert isinstance(memory_data, dict)
        assert "tasks_completed" in memory_data
        
        # Test append_memory
        append_memory(self.temp_dir, "tasks_completed", {"id": "global_test", "description": "Global test"})
        
        # Verify it was added
        updated_memory = load_memory(self.temp_dir)
        assert len(updated_memory["tasks_completed"]) == 1
        assert updated_memory["tasks_completed"][0]["id"] == "global_test"

    def test_memory_metadata_updates(self):
        """Test that metadata is automatically updated."""
        # Add some data
        self.memory_store.append_memory("tasks_completed", {"id": "1", "description": "Task 1"})
        self.memory_store.append_memory("files_created", {"path": "file.py"})
        self.memory_store.append_memory("bugs_fixed", {"error": "SyntaxError", "fix": "Fix"})
        
        metadata = self.memory_store.memory["project_metadata"]
        
        assert metadata["total_tasks"] == 1
        assert metadata["total_files"] == 1
        assert metadata["total_bugs"] == 1
        assert metadata["last_updated"] is not None
        assert metadata["created_at"] is not None

    def test_memory_file_creation(self):
        """Test that memory file is created if it doesn't exist."""
        # Use a different temp directory to ensure clean state
        temp_dir = tempfile.mkdtemp()
        try:
            memory_file = Path(temp_dir) / ".rica_memory.json"
            
            # Ensure file doesn't exist initially
            assert not memory_file.exists()
            
            # Create MemoryStore (should create file)
            store = MemoryStore(temp_dir)
            
            # File should now exist
            assert memory_file.exists()
            
            # Should contain valid JSON
            with open(memory_file, 'r') as f:
                data = json.load(f)
                assert isinstance(data, dict)
        finally:
            shutil.rmtree(temp_dir)


if __name__ == "__main__":
    pytest.main([__file__])
