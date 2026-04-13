"""Prompt loading and rendering utilities."""

import re


def render_prompt(template: str, variables: dict) -> str:
    """
    Render a prompt template.

    1. Evaluate {{#if key}}...{{/if}} blocks: include content when
       variables.get(key) is truthy, strip the whole block otherwise.
    2. Substitute remaining {{var}} placeholders with str values from variables.

    Pure Python — no templating libraries.
    """
    def _replace_if(match: re.Match) -> str:
        key = match.group(1)
        content = match.group(2)
        return content if variables.get(key) else ""

    result = re.sub(
        r"\{\{#if\s+(\w+)\}\}(.*?)\{\{/if\}\}",
        _replace_if,
        template,
        flags=re.DOTALL,
    )

    for key, value in variables.items():
        result = result.replace(f"{{{{{key}}}}}", str(value))

    return result
