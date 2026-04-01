"""LLM client wrapper for Gemini 2.5 Flash."""

from typing import Optional
from pathlib import Path

import google.genai
from google.genai import types
from rich.console import Console

from .config import GEMINI_API_KEY, validate_config

console = Console()


class LLMClient:
    """Gemini 2.5 Flash client wrapper."""
    
    def __init__(self) -> None:
        """Initialize the Gemini client."""
        self.client = None
        self.model = "gemini-2.5-flash"
    
    def _ensure_client(self) -> None:
        """Ensure the client is initialized."""
        if self.client is None:
            validate_config()
            self.client = google.genai.Client(api_key=GEMINI_API_KEY)
    
    def generate(self, system_prompt: str, user_prompt: str) -> str:
        """Generate content using Gemini 2.5 Flash."""
        self._ensure_client()
        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=user_prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                )
            )
            return response.text
        except Exception as e:
            console.print(f"[red]Error calling Gemini API: {e}[/red]")
            raise


def generate(system_prompt_file: str, user_prompt: str) -> str:
    """Standalone generate function that reads system prompt from file."""
    # Read system prompt from file
    system_prompt_path = Path(system_prompt_file)
    if not system_prompt_path.exists():
        raise FileNotFoundError(f"System prompt file not found: {system_prompt_file}")
    
    system_prompt = system_prompt_path.read_text()
    
    # Use global LLM client
    return llm.generate(system_prompt, user_prompt)


# Global LLM client instance
llm = LLMClient()