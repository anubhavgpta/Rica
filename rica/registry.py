"""Language registry for Rica - defines supported languages and their commands."""

from typing import List, Optional

LANGUAGE_REGISTRY = {
    "python": {
        "run_cmd": ["python", "{file}"],
        "test_cmd": ["pytest"],
        "install_cmd": ["pip", "install", "-r", "requirements.txt"],
        "extension": ".py",
        "check_cmd": ["python", "--version"],
    },
    "javascript": {
        "run_cmd": ["node", "{file}"],
        "test_cmd": ["npm", "test"],
        "install_cmd": ["npm", "install"],
        "extension": ".js",
        "check_cmd": ["node", "--version"],
    },
    "typescript": {
        "run_cmd": ["npx", "ts-node", "{file}"],
        "test_cmd": ["npm", "test"],
        "install_cmd": ["npm", "install"],
        "extension": ".ts",
        "check_cmd": ["npx", "tsc", "--version"],
    },
    "go": {
        "run_cmd": ["go", "run", "{file}"],
        "test_cmd": ["go", "test", "./..."],
        "install_cmd": ["go", "mod", "tidy"],
        "extension": ".go",
        "check_cmd": ["go", "version"],
    },
    "rust": {
        "run_cmd": ["cargo", "run"],
        "test_cmd": ["cargo", "test"],
        "install_cmd": ["cargo", "build"],
        "extension": ".rs",
        "check_cmd": ["rustc", "--version"],
    },
    "bash": {
        "run_cmd": ["bash", "{file}"],
        "test_cmd": None,
        "install_cmd": None,
        "extension": ".sh",
        "check_cmd": ["bash", "--version"],
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
