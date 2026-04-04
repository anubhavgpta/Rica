"""
Dependency graph utilities for parallel subtask scheduling.

Terminology:
    wave  — a set of subtask indices that can execute concurrently
            because none of them depend on each other and all their
            dependencies have already completed.
"""

from __future__ import annotations
from collections import defaultdict, deque


def build_execution_waves(subtasks: list) -> list[list[int]]:
    """
    Given an ordered list of SubTask objects (each with a .depends_on
    field — list[int] of indices into the same list), return an ordered
    list of waves.

    Each wave is a list of subtask indices that can run concurrently.
    Waves are ordered: wave N+1 only starts after all tasks in wave N
    complete successfully.

    Raises ValueError if a cycle is detected.

    Example:
        subtasks = [
            SubTask(depends_on=[]),       # 0
            SubTask(depends_on=[]),       # 1
            SubTask(depends_on=[0]),      # 2
            SubTask(depends_on=[0, 1]),   # 3
            SubTask(depends_on=[2, 3]),   # 4
        ]
        build_execution_waves(subtasks)
        -> [[0, 1], [2, 3], [4]]
    """
    n = len(subtasks)
    in_degree = [0] * n
    dependents: dict[int, list[int]] = defaultdict(list)

    for i, task in enumerate(subtasks):
        deps = getattr(task, "depends_on", None) or []
        for d in deps:
            dependents[d].append(i)
            in_degree[i] += 1

    queue: deque[int] = deque(i for i in range(n) if in_degree[i] == 0)
    waves: list[list[int]] = []
    visited = 0

    while queue:
        wave = list(queue)
        queue.clear()
        waves.append(wave)
        visited += len(wave)
        for idx in wave:
            for dep in dependents[idx]:
                in_degree[dep] -= 1
                if in_degree[dep] == 0:
                    queue.append(dep)

    if visited != n:
        raise ValueError(
            f"Cycle detected in subtask dependency graph. "
            f"Visited {visited}/{n} nodes."
        )

    return waves


def validate_depends_on(subtasks: list) -> list[str]:
    """
    Return a list of human-readable error strings for any invalid
    depends_on values (out-of-range indices, self-references).
    Returns empty list if all dependencies are valid.
    """
    n = len(subtasks)
    errors: list[str] = []
    for i, task in enumerate(subtasks):
        deps = getattr(task, "depends_on", None) or []
        for d in deps:
            if d == i:
                errors.append(f"Subtask {i} depends on itself.")
            elif d < 0 or d >= n:
                errors.append(
                    f"Subtask {i} has out-of-range dependency {d} "
                    f"(valid: 0..{n - 1})."
                )
    return errors
