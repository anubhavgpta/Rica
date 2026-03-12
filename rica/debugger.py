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
        code_context: str = ""
    ) -> str:
        """
        Returns a fix prompt string.
        Calls Gemini to analyze error and provide specific fix instruction.
        """
        logger.debug(
            f"[debugger] Analyzing error: "
            f"{error[:80]}"
        )
        
        prompt = f"""You are a debugging expert.

Error:
{error}

Code context:
{code_context}

Analyze this error and provide a specific,
actionable fix instruction.

Return ONLY the fix instruction as plain text.
One sentence. No markdown."""

        try:
            response = self.client.models.generate_content(
                model=self.config["model"],
                contents=prompt
            )
            
            fix_instruction = response.text.strip()
            if fix_instruction:
                logger.info(f"[debugger] Generated fix: {fix_instruction[:60]}")
                return fix_instruction
            else:
                logger.warning("[debugger] Empty fix instruction")
                return f"Fix error: {error}"
                
        except Exception as e:
            logger.error(f"[debugger] Analysis failed: {e}")
            return f"Fix error: {error}"
