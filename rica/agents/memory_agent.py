"""Memory Agent for centralized memory management and intelligent storage."""

import json
import time
from pathlib import Path
from typing import Dict, List, Any, Optional
from loguru import logger

from rica.logging_utils import get_component_logger
from rica.memory.memory_store import get_memory_store, append_memory


class MemoryAgent:
    """Agent responsible for intelligent memory management and storage."""
    
    def __init__(self, config: dict, workspace_dir: str = None):
        self.config = config
        self.workspace_dir = workspace_dir
        self.logger = get_component_logger("memory_agent")
        
        # Initialize memory store
        self.memory_store = None
        if workspace_dir:
            self.memory_store = get_memory_store(workspace_dir)
            self.logger.info(f"[memory] initialized memory store for {workspace_dir}")
        
        # Memory categorization rules
        self.categorization_rules = {
            "task_completion": {
                "keywords": ["completed", "finished", "done", "success"],
                "category": "tasks_completed"
            },
            "bug_fix": {
                "keywords": ["error", "bug", "fix", "debug", "issue"],
                "category": "bugs_fixed"
            },
            "file_creation": {
                "keywords": ["create", "write", "generate", "new file"],
                "category": "files_created"
            },
            "command_execution": {
                "keywords": ["run", "execute", "command", "shell"],
                "category": "commands_run"
            },
            "knowledge": {
                "keywords": ["learn", "discover", "insight", "pattern"],
                "category": "knowledge"
            }
        }
        
        # Memory importance scoring
        self.importance_factors = {
            "error_fix": 10,
            "task_completion": 8,
            "file_creation": 5,
            "command_success": 3,
            "general_info": 1
        }
    
    def store(self, data: Dict[str, Any], category: str = None, importance: int = None) -> bool:
        """
        Store data in memory with intelligent categorization.
        
        Args:
            data: Data to store
            category: Optional category override
            importance: Optional importance score (1-10)
            
        Returns:
            True if stored successfully, False otherwise
        """
        if not self.memory_store:
            self.logger.warning(f"[memory] no memory store available")
            return False
        
        try:
            # Auto-categorize if not provided
            if not category:
                category = self._categorize_data(data)
            
            # Add metadata
            enriched_data = self._enrich_data(data, category, importance)
            
            # Store in memory
            self.memory_store.append_memory(category, enriched_data)
            
            self.logger.info(f"[memory] stored {category} entry (importance: {enriched_data.get('importance', 1)})")
            return True
            
        except Exception as e:
            self.logger.error(f"[memory] failed to store data: {e}")
            return False
    
    def retrieve(self, category: str = None, query: str = None, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Retrieve data from memory with optional filtering.
        
        Args:
            category: Optional category filter
            query: Optional search query
            limit: Maximum number of results
            
        Returns:
            List of retrieved memory entries
        """
        if not self.memory_store:
            self.logger.warning(f"[memory] no memory store available")
            return []
        
        try:
            if query:
                # Search across all categories
                results = self.memory_store.search_memory(query)
                if category:
                    results = [r for r in results if r["category"] == category]
                return [r["entry"] for r in results[:limit]]
            
            elif category:
                # Get specific category
                entries = self.memory_store.get_category(category)
                return entries[-limit:] if entries else []
            
            else:
                # Get recent entries from all categories
                all_entries = []
                for cat in ["tasks_completed", "files_created", "bugs_fixed", "commands_run", "knowledge"]:
                    entries = self.memory_store.get_category(cat)
                    all_entries.extend(entries)
                
                # Sort by timestamp and limit
                all_entries.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
                return all_entries[:limit]
                
        except Exception as e:
            self.logger.error(f"[memory] failed to retrieve data: {e}")
            return []
    
    def analyze_patterns(self) -> Dict[str, Any]:
        """
        Analyze memory patterns and provide insights.
        
        Returns:
            Dictionary containing pattern analysis
        """
        if not self.memory_store:
            return {}
        
        try:
            analysis = {
                "success_patterns": [],
                "failure_patterns": [],
                "common_errors": [],
                "productivity_metrics": {},
                "recommendations": []
            }
            
            # Analyze task completion patterns
            tasks = self.memory_store.get_category("tasks_completed")
            if tasks:
                success_rate = len([t for t in tasks if t.get("success", True)]) / len(tasks)
                analysis["productivity_metrics"]["task_success_rate"] = success_rate
                
                # Find successful patterns
                successful_tasks = [t for t in tasks if t.get("success", True)]
                analysis["success_patterns"] = self._extract_patterns(successful_tasks)
            
            # Analyze bug fixes
            bugs = self.memory_store.get_category("bugs_fixed")
            if bugs:
                error_types = {}
                for bug in bugs:
                    error_type = bug.get("error_type", "unknown")
                    error_types[error_type] = error_types.get(error_type, 0) + 1
                
                analysis["common_errors"] = sorted(error_types.items(), key=lambda x: x[1], reverse=True)
                analysis["failure_patterns"] = self._extract_patterns(bugs)
            
            # Generate recommendations
            analysis["recommendations"] = self._generate_recommendations(analysis)
            
            return analysis
            
        except Exception as e:
            self.logger.error(f"[memory] failed to analyze patterns: {e}")
            return {}
    
    def get_context_for_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        Get relevant memory context for a specific task.
        
        Args:
            task: The task requiring context
            
        Returns:
            Dictionary containing relevant context
        """
        if not self.memory_store:
            return {}
        
        try:
            context = {
                "similar_tasks": [],
                "related_bugs": [],
                "relevant_files": [],
                "previous_commands": [],
                "knowledge_base": []
            }
            
            task_desc = task.get("description", "").lower()
            
            # Find similar tasks
            tasks = self.memory_store.get_category("tasks_completed")
            for task_entry in tasks:
                if self._text_similarity(task_desc, task_entry.get("description", "").lower()) > 0.5:
                    context["similar_tasks"].append(task_entry)
            
            # Find related bug fixes
            bugs = self.memory_store.get_category("bugs_fixed")
            for bug_entry in bugs:
                if self._text_similarity(task_desc, bug_entry.get("error", "").lower()) > 0.3:
                    context["related_bugs"].append(bug_entry)
            
            # Find relevant files
            files = self.memory_store.get_category("files_created")
            for file_entry in files:
                file_path = file_entry.get("path", "").lower()
                if any(keyword in file_path for keyword in task_desc.split()):
                    context["relevant_files"].append(file_entry)
            
            # Find previous commands
            commands = self.memory_store.get_category("commands_run")
            for cmd_entry in commands:
                if self._text_similarity(task_desc, cmd_entry.get("command", "").lower()) > 0.3:
                    context["previous_commands"].append(cmd_entry)
            
            # Get knowledge base entries
            knowledge = self.memory_store.get_category("knowledge")
            context["knowledge_base"] = knowledge[-5:] if knowledge else []
            
            return context
            
        except Exception as e:
            self.logger.error(f"[memory] failed to get task context: {e}")
            return {}
    
    def store_task_result(self, task: Dict[str, Any], result: Dict[str, Any]) -> bool:
        """
        Store task result with intelligent categorization.
        
        Args:
            task: The completed task
            result: The task result
            
        Returns:
            True if stored successfully
        """
        task_data = {
            "task_id": task.get("id", "unknown"),
            "description": task.get("description", ""),
            "type": task.get("type", "unknown"),
            "success": result.get("success", False),
            "completed_at": time.time(),
            "files_created": result.get("files", []),
            "error": result.get("error"),
            "execution_time": result.get("execution_time"),
            "agent_used": result.get("agent", "unknown")
        }
        
        return self.store(task_data, "tasks_completed", importance=8)
    
    def store_bug_fix(self, error: str, fix: str, task_id: str = None, error_type: str = None) -> bool:
        """
        Store bug fix information.
        
        Args:
            error: The error that occurred
            fix: The fix that was applied
            task_id: Associated task ID
            error_type: Type of error
            
        Returns:
            True if stored successfully
        """
        bug_data = {
            "error": error[:500],  # Truncate long errors
            "error_type": error_type or "unknown",
            "fix": fix,
            "task_id": task_id,
            "fixed_at": time.time(),
            "fix_success": True
        }
        
        return self.store(bug_data, "bugs_fixed", importance=10)
    
    def store_file_creation(self, file_path: str, task_id: str = None, file_type: str = None) -> bool:
        """
        Store file creation information.
        
        Args:
            file_path: Path to created file
            task_id: Associated task ID
            file_type: Type of file
            
        Returns:
            True if stored successfully
        """
        file_data = {
            "path": file_path,
            "task_id": task_id,
            "file_type": file_type or Path(file_path).suffix,
            "created_at": time.time(),
            "size": self._get_file_size(file_path)
        }
        
        return self.store(file_data, "files_created", importance=5)
    
    def store_command_execution(self, command: str, success: bool, output: str = None, task_id: str = None) -> bool:
        """
        Store command execution information.
        
        Args:
            command: The command that was executed
            success: Whether the command succeeded
            output: Command output
            task_id: Associated task ID
            
        Returns:
            True if stored successfully
        """
        command_data = {
            "command": command,
            "success": success,
            "output": output[:500] if output else None,  # Truncate long output
            "task_id": task_id,
            "executed_at": time.time()
        }
        
        importance = 5 if success else 3
        return self.store(command_data, "commands_run", importance=importance)
    
    def store_knowledge(self, knowledge: str, category: str = "general", source: str = None) -> bool:
        """
        Store knowledge/insights.
        
        Args:
            knowledge: The knowledge to store
            category: Knowledge category
            source: Source of knowledge
            
        Returns:
            True if stored successfully
        """
        knowledge_data = {
            "content": knowledge,
            "category": category,
            "source": source,
            "learned_at": time.time(),
            "verified": False
        }
        
        return self.store(knowledge_data, "knowledge", importance=6)
    
    def _categorize_data(self, data: Dict[str, Any]) -> str:
        """Automatically categorize data based on content."""
        content = str(data).lower()
        
        for rule_name, rule_info in self.categorization_rules.items():
            keywords = rule_info["keywords"]
            if any(keyword in content for keyword in keywords):
                return rule_info["category"]
        
        return "knowledge"  # Default category
    
    def _enrich_data(self, data: Dict[str, Any], category: str, importance: int = None) -> Dict[str, Any]:
        """Enrich data with metadata."""
        enriched = data.copy()
        
        # Add timestamp if not present
        if "timestamp" not in enriched:
            enriched["timestamp"] = time.time()
        
        # Add category
        enriched["category"] = category
        
        # Calculate importance if not provided
        if importance is None:
            importance = self._calculate_importance(enriched, category)
        
        enriched["importance"] = importance
        
        # Add workspace info
        if self.workspace_dir:
            enriched["workspace"] = self.workspace_dir
        
        return enriched
    
    def _calculate_importance(self, data: Dict[str, Any], category: str) -> int:
        """Calculate importance score for data."""
        base_score = self.importance_factors.get(category, 1)
        
        # Adjust based on content
        content = str(data).lower()
        
        # High importance indicators
        if any(indicator in content for indicator in ["error", "critical", "important", "urgent"]):
            base_score += 3
        
        # Medium importance indicators
        if any(indicator in content for indicator in ["success", "completed", "finished"]):
            base_score += 2
        
        # Cap at 10
        return min(base_score, 10)
    
    def _extract_patterns(self, entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Extract patterns from entries."""
        patterns = []
        
        # Simple pattern extraction - can be enhanced with ML
        for entry in entries:
            pattern = {
                "type": entry.get("type", "unknown"),
                "description": entry.get("description", "")[:100],
                "frequency": 1,
                "success_rate": entry.get("success", True)
            }
            patterns.append(pattern)
        
        return patterns[:5]  # Limit to top 5 patterns
    
    def _generate_recommendations(self, analysis: Dict[str, Any]) -> List[str]:
        """Generate recommendations based on analysis."""
        recommendations = []
        
        # Success rate recommendations
        metrics = analysis.get("productivity_metrics", {})
        success_rate = metrics.get("task_success_rate", 0)
        
        if success_rate < 0.7:
            recommendations.append("Consider reviewing task planning - success rate is below 70%")
        
        # Error pattern recommendations
        common_errors = analysis.get("common_errors", [])
        if common_errors and common_errors[0][1] > 3:
            most_common = common_errors[0][0]
            recommendations.append(f"Most common error type is '{most_common}' - consider preventive measures")
        
        # General recommendations
        if not recommendations:
            recommendations.append("Memory patterns look healthy - continue current approach")
        
        return recommendations
    
    def _text_similarity(self, text1: str, text2: str) -> float:
        """Calculate simple text similarity."""
        if not text1 or not text2:
            return 0.0
        
        words1 = set(text1.split())
        words2 = set(text2.split())
        
        intersection = words1.intersection(words2)
        union = words1.union(words2)
        
        return len(intersection) / len(union) if union else 0.0
    
    def _get_file_size(self, file_path: str) -> int:
        """Get file size in bytes."""
        try:
            return Path(file_path).stat().st_size
        except Exception:
            return 0
