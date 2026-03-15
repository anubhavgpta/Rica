from pathlib import Path
from rica.utils.paths import ensure_workspace


def test_workspace_created():
    """Test that workspace can be created."""
    # Test workspace creation
    workspace_name = "test_workspace_rica"
    workspace_path = ensure_workspace(workspace_name)
    
    assert isinstance(workspace_path, Path)
    assert workspace_path.exists()
    assert workspace_path.is_dir()
    assert workspace_path.name == workspace_name
    
    # Clean up
    if workspace_path.exists():
        import shutil
        shutil.rmtree(workspace_path)


def test_workspace_persistence():
    """Test that workspace creation is persistent."""
    workspace_name = "test_workspace_persist"
    
    # Create workspace first time
    workspace_path1 = ensure_workspace(workspace_name)
    assert workspace_path1.exists()
    
    # Create workspace second time (should return same path)
    workspace_path2 = ensure_workspace(workspace_name)
    assert workspace_path1 == workspace_path2
    assert workspace_path2.exists()
    
    # Clean up
    if workspace_path1.exists():
        import shutil
        shutil.rmtree(workspace_path1)
