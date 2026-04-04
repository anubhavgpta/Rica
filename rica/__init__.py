"""Rica - Language-Agnostic Autonomous Coding Agent."""

__version__ = "0.1.0"

from rica import api as api  # re-export for `from rica import api`

# Re-export notes API functions
from rica.api import add_note, get_notes, update_note, delete_note

# Re-export agent API functions
from rica.api import run_agent_turn, get_agent_history, clear_agent_history
