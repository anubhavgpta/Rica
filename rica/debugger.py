from loguru import logger
import google.genai as genai

class RicaDebugger:
    """
    Analyzes execution errors and builds a
    fix prompt for RicaCodegen.
    """

    def __init__(self, config: dict):
        self.config = config
        self.client = genai.Client(api_key=config["api_key"])

    def analyze(
        self,
        error: str,
        task: dict,
        snapshot = None,
    ) -> dict | str:
        """
        Returns a dict with fix description and optional revised command.
        Calls Gemini to analyze error and provide specific fix instruction.
        """
        logger.debug(
            f"[debugger] Analyzing error: "
            f"{error[:80]}"
        )
        
        # Prepare context from snapshot
        if snapshot and not snapshot.is_empty:
            context = f"Codebase summary: {snapshot.summary}"
        else:
            context = ""
        
        prompt = f"""You are a debugging expert.

Error:
{error}

Task: {task.get('description', '')}

{context}

Analyze this error and provide a specific,
actionable fix instruction. If the error is related
to a command that should be different on Windows,
provide the corrected command.

Return a JSON response:
{{
    "fix": "human readable explanation of the fix",
    "revised_command": "the corrected command to run, or null if command is fine"
}}

If the command is correct, set revised_command to null.
One sentence for the fix. No markdown."""

        try:
            response = self.client.models.generate_content(
                model=self.config["model"],
                contents=prompt
            )
            
            response_text = response.text.strip()
            if response_text:
                # Try to parse as JSON first
                try:
                    import json
                    result = json.loads(response_text)
                    if isinstance(result, dict) and "fix" in result:
                        logger.info(f"[debugger] Generated fix: {result.get('fix', '')[:60]}")
                        if result.get("revised_command"):
                            logger.info(f"[debugger] Revised command: {result['revised_command']}")
                        return result
                except json.JSONDecodeError:
                    # Fallback: treat as plain text (backward compatibility)
                    logger.info(f"[debugger] Generated fix (text): {response_text[:60]}")
                    return {"fix": response_text, "revised_command": None}
                
                logger.warning("[debugger] Invalid JSON response, using fallback")
                return {"fix": response_text, "revised_command": None}
            else:
                logger.warning("[debugger] Empty fix instruction")
                return {"fix": f"Fix error: {error}", "revised_command": None}
                
        except Exception as e:
            logger.error(f"[debugger] Analysis failed: {e}")
            return {"fix": f"Fix error: {error}", "revised_command": None}
