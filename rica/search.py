"""Semantic search utilities for project code."""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from loguru import logger

from rica.logging_utils import get_component_logger

search_logger = get_component_logger("agent")


@dataclass
class CodeChunk:
    """A chunk of code indexed for semantic retrieval."""

    file_path: str
    content: str
    start_line: int
    vector: list[float]


class CodeIndex:
    """Simple in-memory vector index for code chunks."""

    def __init__(
        self,
        client=None,
        model: str | None = None,
        chunk_size: int = 1200,
        overlap: int = 200,
    ) -> None:
        self.client = client
        self.model = model
        self.chunk_size = chunk_size
        self.overlap = overlap
        self.chunks: list[CodeChunk] = []

    def add_file(self, file_path: str, content: str) -> None:
        """Split a file into chunks and index them."""
        for chunk_text, start_line in self._split_content(content):
            self.chunks.append(
                CodeChunk(
                    file_path=file_path,
                    content=chunk_text,
                    start_line=start_line,
                    vector=self._embed_text(chunk_text),
                )
            )

    def search(
        self, query: str, top_k: int = 5
    ) -> list[dict[str, str | int | float]]:
        """Return the best matching chunks for a query."""
        if not query.strip() or not self.chunks:
            return []

        query_vector = self._embed_text(query)
        ranked = sorted(
            (
                {
                    "path": chunk.file_path,
                    "score": self._cosine_similarity(
                        query_vector, chunk.vector
                    ),
                    "snippet": chunk.content,
                    "start_line": chunk.start_line,
                }
                for chunk in self.chunks
            ),
            key=lambda item: float(item["score"]),
            reverse=True,
        )

        seen: set[tuple[str, int]] = set()
        results = []
        for item in ranked:
            key = (str(item["path"]), int(item["start_line"]))
            if key in seen:
                continue
            seen.add(key)
            results.append(item)
            if len(results) >= top_k:
                break
        return results

    def _split_content(
        self, content: str
    ) -> Iterable[tuple[str, int]]:
        lines = content.splitlines()
        if not lines:
            return []

        chunks: list[tuple[str, int]] = []
        start = 0
        while start < len(lines):
            current_lines: list[str] = []
            current_size = 0
            idx = start
            while idx < len(lines):
                line = lines[idx]
                proposed = current_size + len(line) + 1
                if current_lines and proposed > self.chunk_size:
                    break
                current_lines.append(line)
                current_size = proposed
                idx += 1
            chunks.append(("\n".join(current_lines), start + 1))
            if idx >= len(lines):
                break
            start = max(start + 1, idx - self._line_overlap(lines, start, idx))
        return chunks

    def _line_overlap(
        self, lines: list[str], start: int, end: int
    ) -> int:
        overlap = 0
        size = 0
        for index in range(end - 1, start - 1, -1):
            size += len(lines[index]) + 1
            if size > self.overlap:
                break
            overlap += 1
        return overlap

    def _embed_text(self, text: str) -> list[float]:
        normalized = text.strip()
        if not normalized:
            return [0.0] * 32

        if self.client and self.model:
            try:
                response = self.client.models.embed_content(
                    model=self.model,
                    contents=normalized,
                )
                embedding = getattr(response, "embeddings", None) or []
                if embedding:
                    values = getattr(embedding[0], "values", None)
                    if values:
                        return [float(value) for value in values]
            except Exception as error:
                search_logger.debug(
                    f"[search] Embedding fallback for text chunk: {error}"
                )

        return _hashed_embedding(normalized)

    @staticmethod
    def _cosine_similarity(
        left: list[float], right: list[float]
    ) -> float:
        if not left or not right or len(left) != len(right):
            return 0.0
        numerator = sum(a * b for a, b in zip(left, right))
        left_norm = math.sqrt(sum(a * a for a in left))
        right_norm = math.sqrt(sum(b * b for b in right))
        if left_norm == 0.0 or right_norm == 0.0:
            return 0.0
        return numerator / (left_norm * right_norm)


def build_code_index(
    project_dir: str,
    files: dict[str, str],
    client=None,
    model: str | None = None,
) -> CodeIndex:
    """Build an in-memory index for a project."""
    import os
    
    # Guard against empty files
    if not files:
        logger.info("[search] No files to index")
        return CodeIndex(client=client, model=model)
    
    # Filter files to only include existing Python files
    filtered_files = {}
    for file_path, content in files.items():
        if file_path.endswith(".py") and os.path.exists(file_path):
            filtered_files[file_path] = content
    
    # Guard against no valid files after filtering
    if not filtered_files:
        logger.info("[search] No valid Python files to index")
        return CodeIndex(client=client, model=model)
    
    index = CodeIndex(client=client, model=model)
    for file_path, content in filtered_files.items():
        index.add_file(file_path, content)
    
    logger.info(f"[search] Indexed {len(filtered_files)} project files")
    return index


def _hashed_embedding(text: str, dimensions: int = 32) -> list[float]:
    vector = [0.0] * dimensions
    for token in text.lower().split():
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        slot = digest[0] % dimensions
        sign = 1.0 if digest[1] % 2 == 0 else -1.0
        weight = 1.0 + (digest[2] / 255.0)
        vector[slot] += sign * weight
    return vector
