"""
Repository Graph for understanding file relationships in Python projects.
"""

import ast
from pathlib import Path
from typing import Dict, List, Set


class RepoGraph:
    """Dependency graph between project files using Python imports."""
    
    def __init__(self):
        self.graph: Dict[str, List[str]] = {}
        self.reverse_graph: Dict[str, List[str]] = {}
    
    def index_project(self, project_dir: str):
        """Index all Python files and their imports."""
        project_path = Path(project_dir)
        
        for python_file in project_path.rglob("*.py"):
            if python_file.is_file():
                imports = self._extract_imports(python_file)
                file_path = str(python_file)
                self.graph[file_path] = imports
                
                # Build reverse graph (which files import this file)
                for imported_file in imports:
                    if imported_file not in self.reverse_graph:
                        self.reverse_graph[imported_file] = []
                    self.reverse_graph[imported_file].append(file_path)
    
    def _extract_imports(self, file_path: Path) -> List[str]:
        """Extract import statements from a Python file."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            tree = ast.parse(content)
            imports = []
            
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        imports.append(alias.name)
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        imports.append(node.module)
                        for alias in node.names:
                            if alias.name != '*':
                                imports.append(f"{node.module}.{alias.name}")
            
            return list(set(imports))  # Remove duplicates
            
        except (SyntaxError, UnicodeDecodeError):
            return []
    
    def related_files(self, file_path: str) -> List[str]:
        """Get files that are related to the given file."""
        # Files that this file imports
        direct_imports = self.graph.get(file_path, [])
        
        # Files that import this file
        importers = self.reverse_graph.get(file_path, [])
        
        # Combine both directions
        related = list(set(direct_imports + importers))
        
        # Filter to only files in our graph
        return [f for f in related if f in self.graph or f in self.reverse_graph]
    
    def get_dependencies(self, file_path: str) -> List[str]:
        """Get files that this file depends on."""
        return self.graph.get(file_path, [])
    
    def get_dependents(self, file_path: str) -> List[str]:
        """Get files that depend on this file."""
        return self.reverse_graph.get(file_path, [])
    
    def get_all_files(self) -> List[str]:
        """Get all indexed files."""
        return list(self.graph.keys())
    
    def find_cycles(self) -> List[List[str]]:
        """Find circular dependencies in the graph."""
        visited = set()
        rec_stack = set()
        cycles = []
        
        def dfs(node: str, path: List[str]):
            if node in rec_stack:
                # Found a cycle
                cycle_start = path.index(node)
                cycles.append(path[cycle_start:] + [node])
                return
            
            if node in visited:
                return
            
            visited.add(node)
            rec_stack.add(node)
            
            for neighbor in self.graph.get(node, []):
                if neighbor in self.graph:  # Only consider files in our project
                    dfs(neighbor, path + [node])
            
            rec_stack.remove(node)
        
        for file_path in self.graph:
            if file_path not in visited:
                dfs(file_path, [])
        
        return cycles
