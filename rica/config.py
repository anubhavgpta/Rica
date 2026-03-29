"""Configuration management for Rica."""

import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Paths
RICA_HOME = Path.home() / ".rica"
RICA_HOME.mkdir(parents=True, exist_ok=True)

PLANS_DIR = RICA_HOME / "plans"
PLANS_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = RICA_HOME / "rica.db"

# API Keys
GEMINI_API_KEY: Optional[str] = os.getenv("GEMINI_API_KEY")

# Validate required environment variables
def validate_config() -> None:
    """Validate that required configuration is present."""
    if not GEMINI_API_KEY:
        raise ValueError(
            "GEMINI_API_KEY is required. Set it in your environment or .env file."
        )

def get_config() -> dict:
    """Get current configuration status."""
    return {
        "gemini_api_key": bool(GEMINI_API_KEY),
        "rica_home": str(RICA_HOME),
        "plans_dir": str(PLANS_DIR),
        "db_path": str(DB_PATH),
    }
