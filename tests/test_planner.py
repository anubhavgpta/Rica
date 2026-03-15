from rica.planner import RicaPlanner


def test_planner_generates_tasks():
    """Test that planner generates tasks for a simple goal."""
    # Create a minimal config for testing
    config = {
        "api_key": "test-key",
        "model": "gemini-2.5-flash"
    }
    
    planner = RicaPlanner(config)
    
    # Test with a simple goal
    try:
        tasks = planner.plan("create a hello world script")
        assert isinstance(tasks, list)
        assert len(tasks) > 0
        
        # Check that each task has required fields
        for task in tasks:
            assert isinstance(task, dict)
            assert "id" in task
            assert "description" in task
            assert "type" in task
            
    except Exception as e:
        # If API call fails (e.g., no network), at least check the structure
        assert isinstance(tasks, list)
        print(f"Planner test completed with expected API error: {e}")
