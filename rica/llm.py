"""LLM client wrapper for Gemini 2.5 Flash."""

from typing import Optional
from pathlib import Path

import google.genai
from google.genai import types
from rich.console import Console

from .config import GEMINI_API_KEY, validate_config

console = Console()

# Layer tag injected by callers via kwarg; defaults to "unknown"
_DEFAULT_LAYER = "unknown"


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
    
    def generate(
        self, 
        system_prompt: str, 
        user_prompt: str,
        *,
        layer: str = _DEFAULT_LAYER,
        call_type: str = "generate",
        session_id: str | None = None
    ) -> str:
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
            
            # Extract usage metadata
            usage = getattr(response, "usage_metadata", None)
            input_tokens = getattr(usage, "prompt_token_count", 0) or 0
            output_tokens = getattr(usage, "candidates_token_count", 0) or 0
            cached_tokens = getattr(usage, "cached_content_token_count", 0) or 0
            model_name = getattr(response, "model", "gemini-2.5-flash")
            
            # Persist usage data
            try:
                _persist_usage(
                    session_id=session_id,
                    layer=layer,
                    call_type=call_type,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cached_tokens=cached_tokens,
                    model=model_name,
                )
            except Exception:
                pass  # tracking must never break a command
            
            return response.text
        except Exception as e:
            console.print(f"[red]Error calling Gemini API: {e}[/red]")
            raise


def _persist_usage(
    *,
    session_id: str | None,
    layer: str,
    call_type: str,
    input_tokens: int,
    output_tokens: int,
    cached_tokens: int,
    model: str,
) -> None:
    """Insert one row into llm_usage. Called only from the LLM wrapper."""
    from datetime import datetime, timezone
    from rica.db import get_connection
    
    now = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO llm_usage
                (session_id, layer, call_type,
                 input_tokens, output_tokens, cached_tokens,
                 model, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (session_id, layer, call_type,
             input_tokens, output_tokens, cached_tokens,
             model, now),
        )


def generate(
    system_prompt_file: str, 
    user_prompt: str,
    *,
    layer: str = _DEFAULT_LAYER,
    call_type: str = "generate",
    session_id: str | None = None
) -> str:
    """Standalone generate function that reads system prompt from file."""
    # Read system prompt from file
    system_prompt_path = Path(system_prompt_file)
    if not system_prompt_path.exists():
        raise FileNotFoundError(f"System prompt file not found: {system_prompt_file}")
    
    system_prompt = system_prompt_path.read_text()
    
    # Use global LLM client
    return llm.generate(
        system_prompt, 
        user_prompt,
        layer=layer,
        call_type=call_type,
        session_id=session_id
    )


# Global LLM client instance
llm = LLMClient()