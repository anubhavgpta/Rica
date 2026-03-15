from pathlib import Path
from rica.config import get_config_path


def test_config_exists():
    """Test that config path can be retrieved."""
    path = get_config_path()
    assert isinstance(path, str) or isinstance(path, Path)
    
    # The config file might not exist yet, but the path should be valid
    config_path = Path(path)
    assert config_path.name == "config.json"
    assert config_path.parent.name == ".rica"
