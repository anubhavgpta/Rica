"""Language registry for Rica - defines supported languages and their commands."""

import pathlib
from typing import List, Optional

LANGUAGE_REGISTRY = {
    "python": {
        "run_cmd": ["python", "{file}"],
        "test_cmd": ["pytest"],
        "install_cmd": ["pip", "install", "-r", "requirements.txt"],
        "extension": ".py",
        "check_cmd": ["python", "-m", "py_compile", "{file}"],
    },
    "javascript": {
        "run_cmd": ["node", "{file}"],
        "test_cmd": ["npm", "test"],
        "install_cmd": ["npm", "install"],
        "extension": ".js",
        "check_cmd": ["node", "--check", "{file}"],
    },
    "typescript": {
        "run_cmd": ["npx", "ts-node", "{file}"],
        "test_cmd": ["npm", "test"],
        "install_cmd": ["npm", "install"],
        "extension": ".ts",
        "check_cmd": ["npx", "tsc", "--noEmit"],
    },
    "go": {
        "run_cmd": ["go", "run", "{file}"],
        "test_cmd": ["go", "test", "./..."],
        "install_cmd": ["go", "mod", "tidy"],
        "extension": ".go",
        "check_cmd": ["go", "build", "./..."],
    },
    "rust": {
        "run_cmd": ["cargo", "run"],
        "test_cmd": ["cargo", "test"],
        "install_cmd": ["cargo", "build"],
        "extension": ".rs",
        "check_cmd": ["cargo", "check"],
    },
    "bash": {
        "run_cmd": ["bash", "{file}"],
        "test_cmd": None,
        "install_cmd": None,
        "extension": ".sh",
        "check_cmd": ["bash", "-n", "{file}"],
    },
}


def get_supported_languages() -> List[str]:
    """Get list of supported programming languages."""
    return list(LANGUAGE_REGISTRY.keys())


def get_language_config(language: str) -> dict:
    """Get configuration for a specific language."""
    if language not in LANGUAGE_REGISTRY:
        raise ValueError(f"Unsupported language: {language}")
    return LANGUAGE_REGISTRY[language]


def is_supported(language: str) -> bool:
    """Check if a language is supported."""
    return language in LANGUAGE_REGISTRY


def detect_languages(path: pathlib.Path) -> List[str]:
    """
    Walk path, collect all file extensions, map each to a language via
    LANGUAGE_REGISTRY, deduplicate, return sorted list.
    Ignores runtime dirs (.venv, node_modules, __pycache__, .git,
    dist, build, target, .tox, venv, env).
    Returns ["unknown"] if nothing matches.
    """
    runtime_dirs = {
        ".venv", "venv", "env", "node_modules", "__pycache__", 
        ".git", "dist", "build", "target", ".tox"
    }
    
    extension_counts = {}
    
    for file_path in path.rglob("*"):
        if file_path.is_file():
            # Skip runtime directories
            if any(runtime_dir in file_path.parts for runtime_dir in runtime_dirs):
                continue
                
            ext = file_path.suffix.lower()
            if not ext:
                continue
                
            # Map extension to language
            for lang, config in LANGUAGE_REGISTRY.items():
                if config.get("extension") == ext:
                    extension_counts[lang] = extension_counts.get(lang, 0) + 1
                    break
    
    if not extension_counts:
        return ["unknown"]
    
    # Return sorted list of detected languages
    return sorted(extension_counts.keys())


def primary_language(path: pathlib.Path) -> str:
    """Returns the most-common language by file count."""
    languages = detect_languages(path)
    if languages == ["unknown"]:
        return "unknown"
    
    # Count files per language to find primary
    runtime_dirs = {
        ".venv", "venv", "env", "node_modules", "__pycache__", 
        ".git", "dist", "build", "target", ".tox"
    }
    
    extension_counts = {}
    
    for file_path in path.rglob("*"):
        if file_path.is_file():
            if any(runtime_dir in file_path.parts for runtime_dir in runtime_dirs):
                continue
                
            ext = file_path.suffix.lower()
            if not ext:
                continue
                
            for lang, config in LANGUAGE_REGISTRY.items():
                if config.get("extension") == ext:
                    extension_counts[lang] = extension_counts.get(lang, 0) + 1
                    break
    
    if not extension_counts:
        return "unknown"
    
    # Return language with most files
    return max(extension_counts, key=extension_counts.get)
