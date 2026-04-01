"""Dependency graph functionality for Rica rebuild system."""

from collections import defaultdict
from typing import Dict, List, Set

from .models import BuildPlan


def build_dep_graph(plan: BuildPlan) -> Dict[str, Set[str]]:
    """Build a reverse dependency graph from a BuildPlan.
    
    Returns: dict where key = file path, value = set of files that depend on it
    (i.e., reverse dependencies - "who imports me")
    """
    graph = defaultdict(set)
    
    for milestone in plan.milestones:
        for file_plan in milestone.files:
            # For each dependency this file has, add this file to the dependency's dependents
            for dep_path in file_plan.dependencies:
                graph[dep_path].add(file_plan.path)
    
    return dict(graph)


def cascade_changed(changed: List[str], graph: Dict[str, Set[str]]) -> List[str]:
    """Find all files that transitively depend on the changed files.
    
    Args:
        changed: List of file paths that have changed
        graph: Reverse dependency graph (file -> set of files that depend on it)
    
    Returns:
        List of all files reachable from the changed files (transitive dependents)
        that are NOT already in the changed set, deduplicated and sorted.
    """
    # BFS/DFS from each changed file
    all_dependents = set()
    visited = set()
    stack = list(changed)
    
    while stack:
        current = stack.pop()
        if current in visited:
            continue
        visited.add(current)
        
        # Get files that depend on current
        dependents = graph.get(current, set())
        
        for dependent in dependents:
            if dependent not in visited and dependent not in changed:
                all_dependents.add(dependent)
                stack.append(dependent)
    
    return sorted(all_dependents)
