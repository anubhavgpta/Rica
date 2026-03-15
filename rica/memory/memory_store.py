"""Enhanced persistent memory store for Rica projects."""

import json
from pathlib import Path
from typing import Any, List, Dict
from loguru import logger


class MemoryStore:
    """Enhanced memory store with size limiting and categorization."""
    
    def __init__(self, workspace_dir: str):
        self.workspace_dir = Path(workspace_dir)
        self.memory_file = self.workspace_dir / ".rica_memory.json"
        self.max_entries_per_category = 100
        
        # Initialize memory structure
        self.memory = self._load_memory()
    
    def _load_memory(self) -> Dict[str, Any]:
        """Load memory from file or create default structure."""
        if not self.memory_file.exists():
            default_memory = {
                "tasks_completed": [],
                "files_created": [],
                "bugs_fixed": [],
                "commands_run": [],
                "knowledge": [],
                "project_metadata": {
                    "created_at": None,
                    "last_updated": None,
                    "total_tasks": 0,
                    "total_files": 0,
                    "total_bugs": 0
                }
            }
            self._save_memory(default_memory)
            return default_memory
        
        try:
            with open(self.memory_file, 'r', encoding='utf-8') as f:
                memory = json.load(f)
            
            # Ensure all required categories exist
            default_categories = ["tasks_completed", "files_created", "bugs_fixed", "commands_run", "knowledge"]
            for category in default_categories:
                if category not in memory:
                    memory[category] = []
            
            if "project_metadata" not in memory:
                memory["project_metadata"] = {}
            
            return memory
            
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"[memory] Could not load memory file, creating new: {e}")
            # Create default memory directly without recursion
            default_memory = {
                "tasks_completed": [],
                "files_created": [],
                "bugs_fixed": [],
                "commands_run": [],
                "knowledge": [],
                "project_metadata": {
                    "created_at": None,
                    "last_updated": None,
                    "total_tasks": 0,
                    "total_files": 0,
                    "total_bugs": 0
                }
            }
            self._save_memory(default_memory)
            return default_memory
    
    def _save_memory(self, memory: Dict[str, Any] = None) -> None:
        """Save memory to file."""
        if memory is None:
            memory = self.memory
        
        try:
            # Ensure directory exists
            self.memory_file.parent.mkdir(parents=True, exist_ok=True)
            
            # Update metadata
            import time
            memory["project_metadata"]["last_updated"] = time.time()
            memory["project_metadata"]["total_tasks"] = len(memory.get("tasks_completed", []))
            memory["project_metadata"]["total_files"] = len(memory.get("files_created", []))
            memory["project_metadata"]["total_bugs"] = len(memory.get("bugs_fixed", []))
            
            # Set created_at if not present
            if not memory["project_metadata"].get("created_at"):
                memory["project_metadata"]["created_at"] = time.time()
            
            with open(self.memory_file, 'w', encoding='utf-8') as f:
                json.dump(memory, f, indent=2, ensure_ascii=False)
                
        except IOError as e:
            logger.error(f"[memory] Failed to save memory: {e}")
    
    def _limit_category_size(self, category: str) -> List[Any]:
        """Limit category size to max_entries_per_category."""
        items = self.memory.get(category, [])
        if len(items) > self.max_entries_per_category:
            # Keep the most recent entries
            limited_items = items[-self.max_entries_per_category:]
            self.memory[category] = limited_items
            logger.info(f"[memory] Limited {category} to {len(limited_items)} entries")
            return limited_items
        return items
    
    def append_memory(self, category: str, data: Any) -> None:
        """Append data to a memory category with timestamp."""
        if category not in self.memory:
            self.memory[category] = []
        
        # Add timestamp to entry if it's a dict
        entry = data.copy() if isinstance(data, dict) else data
        if isinstance(entry, dict) and "timestamp" not in entry:
            import time
            entry["timestamp"] = time.time()
        
        self.memory[category].append(entry)
        
        # Limit size
        self._limit_category_size(category)
        
        # Save to disk
        self._save_memory()
        
        logger.info(f"[memory] stored {category} entry")
    
    def get_memory_summary(self) -> str:
        """Get a formatted summary of project memory."""
        summary_parts = []
        
        # Project metadata
        metadata = self.memory.get("project_metadata", {})
        if metadata:
            import time
            created_at = metadata.get("created_at")
            if created_at:
                from datetime import datetime
                created_str = datetime.fromtimestamp(created_at).strftime("%Y-%m-%d %H:%M")
                summary_parts.append(f"Project created: {created_str}")
            
            summary_parts.append(f"Total tasks: {metadata.get('total_tasks', 0)}")
            summary_parts.append(f"Total files: {metadata.get('total_files', 0)}")
            summary_parts.append(f"Total bugs fixed: {metadata.get('total_bugs', 0)}")
        
        # Recent entries from each category
        for category in ["tasks_completed", "files_created", "bugs_fixed", "commands_run"]:
            entries = self.memory.get(category, [])
            if entries:
                summary_parts.append(f"\nRecent {category.replace('_', ' ').title()} ({len(entries)} total):")
                for entry in entries[-3:]:  # Show last 3
                    if isinstance(entry, dict):
                        if "description" in entry:
                            summary_parts.append(f"  - {entry['description']}")
                        elif "path" in entry:
                            summary_parts.append(f"  - {entry['path']}")
                        elif "command" in entry:
                            summary_parts.append(f"  - {entry['command']}")
                        else:
                            summary_parts.append(f"  - {str(entry)[:80]}...")
                    else:
                        summary_parts.append(f"  - {str(entry)[:80]}...")
        
        return "\n".join(summary_parts)
    
    def get_category(self, category: str) -> List[Any]:
        """Get all entries from a category."""
        return self.memory.get(category, [])
    
    def search_memory(self, query: str) -> List[Dict[str, Any]]:
        """Search across all memory categories for query."""
        results = []
        query_lower = query.lower()
        
        for category, entries in self.memory.items():
            if category == "project_metadata":
                continue
                
            if not isinstance(entries, list):
                continue
                
            for entry in entries:
                # Convert entry to string for searching
                entry_str = str(entry).lower()
                if query_lower in entry_str:
                    results.append({
                        "category": category,
                        "entry": entry,
                        "match_context": entry_str[:100] + "..." if len(entry_str) > 100 else entry_str
                    })
        
        return results
    
    def clear_category(self, category: str) -> None:
        """Clear all entries from a category."""
        if category in self.memory:
            self.memory[category] = []
            self._save_memory()
            logger.info(f"[memory] cleared category: {category}")
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get memory usage statistics."""
        stats = {
            "total_entries": 0,
            "categories": {},
            "file_size_bytes": 0,
            "file_size_mb": 0
        }
        
        for category, entries in self.memory.items():
            if isinstance(entries, list):
                entry_count = len(entries)
                stats["categories"][category] = entry_count
                stats["total_entries"] += entry_count
        
        # File size
        if self.memory_file.exists():
            stats["file_size_bytes"] = self.memory_file.stat().st_size
            stats["file_size_mb"] = round(stats["file_size_bytes"] / (1024 * 1024), 2)
        
        return stats


# Global memory store instance
_memory_store: Dict[str, MemoryStore] = {}


def get_memory_store(workspace_dir: str) -> MemoryStore:
    """Get or create memory store for workspace."""
    workspace_key = str(Path(workspace_dir).resolve())
    if workspace_key not in _memory_store:
        _memory_store[workspace_key] = MemoryStore(workspace_dir)
    return _memory_store[workspace_key]


def load_memory(workspace_dir: str) -> Dict[str, Any]:
    """Load memory for workspace."""
    store = get_memory_store(workspace_dir)
    return store.memory


def save_memory(workspace_dir: str, memory: Dict[str, Any]) -> None:
    """Save memory for workspace."""
    store = get_memory_store(workspace_dir)
    store.memory = memory
    store._save_memory()


def append_memory(workspace_dir: str, category: str, data: Any) -> None:
    """Append data to memory category."""
    store = get_memory_store(workspace_dir)
    store.append_memory(category, data)
