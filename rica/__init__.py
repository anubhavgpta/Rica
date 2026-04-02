"""Rica - Language-Agnostic Autonomous Coding Agent."""

__version__ = "0.1.0"

from rica import api as api  # re-export for `from rica import api`

# Re-export notes API functions
from rica.api import add_note, get_notes, update_note, delete_note
