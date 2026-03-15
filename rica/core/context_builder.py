"""
Context Builder for optimizing LLM context size and relevance.
"""

from typing import List, Dict, Any
from pathlib import Path


class ContextBuilder:
    """Builds optimized context for LLM by selecting relevant files."""
    
    def __init__(self, max_files: int = 10, max_context_size: int = 50000):
        self.max_files = max_files
        self.max_context_size = max_context_size
    
    def build_context(self, goal: str, search_results: List[Dict[str, Any]], repo_graph) -> List[str]:
        """Build optimized context for the coder agent."""
        
        # Get primary relevant files from search results
        primary_files = []
        for result in search_results[:self.max_files // 2]:
            if 'file_path' in result:
                primary_files.append(result['file_path'])
        
        # Get related files through repository graph
        related_files = []
        for file_path in primary_files:
            if hasattr(repo_graph, 'related_files'):
                related = repo_graph.related_files(file_path)
                related_files.extend(related)
        
        # Remove duplicates and combine
        all_files = list(set(primary_files + related_files))
        
        # Filter to existing files
        existing_files = []
        for file_path in all_files:
            if Path(file_path).exists():
                existing_files.append(file_path)
        
        # Sort by relevance (primary files first)
        context_files = []
        for file_path in primary_files:
            if file_path in existing_files:
                context_files.append(file_path)
                existing_files.remove(file_path)
        
        # Add related files up to max limit
        for file_path in existing_files:
            if len(context_files) >= self.max_files:
                break
            context_files.append(file_path)
        
        # Check context size and trim if necessary
        if self._get_context_size(context_files) > self.max_context_size:
            context_files = self._trim_context(context_files)
        
        return context_files
    
    def _get_context_size(self, file_paths: List[str]) -> int:
        """Calculate total context size in characters."""
        total_size = 0
        for file_path in file_paths:
            try:
                path = Path(file_path)
                if path.exists():
                    total_size += path.stat().st_size
            except Exception:
                continue
        return total_size
    
    def _trim_context(self, file_paths: List[str]) -> List[str]:
        """Trim context to fit within size limit."""
        trimmed_files = []
        current_size = 0
        
        # Prioritize primary files
        for file_path in file_paths:
            try:
                path = Path(file_path)
                if path.exists():
                    file_size = path.stat().st_size
                    if current_size + file_size <= self.max_context_size:
                        trimmed_files.append(file_path)
                        current_size += file_size
                    else:
                        break
            except Exception:
                continue
        
        return trimmed_files
    
    def build_relevant_context(self, goal: str, target_file: str, repo_graph) -> List[str]:
        """Build context specifically for editing a target file."""
        context_files = []
        
        # Always include the target file
        if Path(target_file).exists():
            context_files.append(target_file)
        
        # Get related files
        if hasattr(repo_graph, 'related_files'):
            related = repo_graph.related_files(target_file)
            for file_path in related:
                if Path(file_path).exists() and file_path not in context_files:
                    context_files.append(file_path)
        
        # Get dependencies
        if hasattr(repo_graph, 'get_dependencies'):
            deps = repo_graph.get_dependencies(target_file)
            for file_path in deps:
                if Path(file_path).exists() and file_path not in context_files:
                    context_files.append(file_path)
        
        # Limit to max files
        return context_files[:self.max_files]
    
    def prioritize_files_by_goal(self, goal: str, file_paths: List[str]) -> List[str]:
        """Prioritize files based on goal relevance."""
        goal_lower = goal.lower()
        prioritized = []
        
        # Define file type priorities based on common goals
        file_priorities = {
            'test': ['test_', '_test.py', 'tests/'],
            'api': ['api/', 'routes/', 'views/', 'endpoints.py'],
            'model': ['models/', 'schema/', 'entities/'],
            'config': ['config', 'settings', '.env'],
            'main': ['main.py', 'app.py', 'run.py', 'server.py'],
            'util': ['utils/', 'helpers/', 'tools/'],
            'data': ['data/', 'database/', 'db/'],
        }
        
        # Score files based on goal
        scored_files = []
        for file_path in file_paths:
            score = 0
            
            # Check for goal-specific patterns
            for keyword, patterns in file_priorities.items():
                if keyword in goal_lower:
                    for pattern in patterns:
                        if pattern in file_path.lower():
                            score += 10
            
            # Check for direct keyword matches in filename
            for keyword in ['test', 'api', 'model', 'config', 'main', 'util', 'data']:
                if keyword in goal_lower and keyword in file_path.lower():
                    score += 5
            
            scored_files.append((file_path, score))
        
        # Sort by score (descending)
        scored_files.sort(key=lambda x: x[1], reverse=True)
        
        # Return just the file paths
        return [file_path for file_path, score in scored_files]
