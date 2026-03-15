from rica.debugger import RicaDebugger
from rica.logging_utils import get_component_logger
from typing import List, Dict, Any, Optional
import re

logger = get_component_logger("debugger_agent")


class DebuggerAgent:
    def __init__(self, config: dict):
        self.config = config
        self.debugger = RicaDebugger(config)
        self.error_history: List[Dict[str, str]] = []
        self.max_error_history = int(config.get("max_error_history", 50))
        self.repeat_threshold = int(config.get("error_repeat_threshold", 3))
        
        # Pattern recognition for common errors
        self.error_patterns = {
            "ModuleNotFoundError": {
                "pattern": r"ModuleNotFoundError: No module named '(\w+)'",
                "action": "install_dependency",
                "description": "Install missing dependency"
            },
            "ImportError": {
                "pattern": r"ImportError: (?:cannot import name|cannot import) '(\w+)'",
                "action": "fix_import",
                "description": "Fix import statement"
            },
            "SyntaxError": {
                "pattern": r"SyntaxError: (.+)",
                "action": "regenerate_code",
                "description": "Regenerate code with correct syntax"
            },
            "NameError": {
                "pattern": r"NameError: name '(\w+)' is not defined",
                "action": "define_variable",
                "description": "Define missing variable"
            },
            "TypeError": {
                "pattern": r"TypeError: (.+)",
                "action": "fix_type_mismatch",
                "description": "Fix type mismatch"
            },
            "AttributeError": {
                "pattern": r"AttributeError: '(\w+)' object has no attribute '(\w+)'",
                "action": "add_attribute",
                "description": "Add missing attribute"
            },
            "KeyError": {
                "pattern": r"KeyError: '(\w+)'",
                "action": "handle_missing_key",
                "description": "Handle missing dictionary key"
            },
            "FileNotFoundError": {
                "pattern": r"FileNotFoundError: \[Errno 2\] No such file or directory: (.+)",
                "action": "create_file",
                "description": "Create missing file"
            },
            "PermissionError": {
                "pattern": r"PermissionError: \[Errno 13\] Permission denied: (.+)",
                "action": "fix_permissions",
                "description": "Fix file permissions"
            },
            "ConnectionError": {
                "pattern": r"ConnectionError: (.+)",
                "action": "handle_connection",
                "description": "Handle connection issues"
            },
            "ValueError": {
                "pattern": r"ValueError: (.+)",
                "action": "validate_input",
                "description": "Add input validation"
            },
            "IndexError": {
                "pattern": r"IndexError: (.+)",
                "action": "fix_index_bounds",
                "description": "Fix index bounds"
            },
            "AssertionError": {
                "pattern": r"AssertionError: (.+)",
                "action": "fix_assertion",
                "description": "Fix failed assertion"
            }
        }
        
        # Learned patterns from previous sessions
        self.learned_patterns: List[Dict[str, Any]] = []

    def _should_stop_retrying(self, error: str) -> bool:
        """Check if we've seen this error too many times and should stop retrying."""
        error_normalized = self._normalize_error(error)
        
        # Count occurrences of this error
        count = sum(1 for item in self.error_history 
                   if self._normalize_error(item["error"]) == error_normalized)
        
        if count >= self.repeat_threshold:
            logger.warning(f"[debugger_agent] Error repeated {count} times, stopping retries: {error_normalized[:100]}")
            return True
        
        return False

    def _normalize_error(self, error: str) -> str:
        """Normalize error message for comparison (remove line numbers, paths, etc)."""
        # Remove line numbers
        error = re.sub(r'line \d+', 'line X', error)
        
        # Remove file paths (keep only filename)
        error = re.sub(r'[A-Za-z]:\\[^\\s]*\\|/[^/\s]*/[^/\s]*', 'path/', error)
        
        # Remove whitespace variations
        error = ' '.join(error.split())
        
        return error.lower().strip()

    def _record_error(self, error: str, task: dict, fix_suggestion: str = ""):
        """Record error in history for pattern detection."""
        error_entry = {
            "error": error,
            "task_id": str(task.get("id", "unknown")),
            "task_description": task.get("description", ""),
            "fix_suggestion": fix_suggestion,
            "timestamp": str(logger._core.start_time if hasattr(logger, '_core') else "unknown")
        }
        
        self.error_history.append(error_entry)
        
        # Keep history size manageable
        if len(self.error_history) > self.max_error_history:
            self.error_history = self.error_history[-self.max_error_history:]
        
        logger.info(f"[debugger_agent] Recorded error (history size: {len(self.error_history)})")

    def get_similar_errors(self, error: str, limit: int = 3) -> List[Dict[str, str]]:
        """Get similar errors from history."""
        error_normalized = self._normalize_error(error)
        
        similar = []
        for item in self.error_history:
            if self._normalize_error(item["error"]) == error_normalized:
                similar.append(item)
                if len(similar) >= limit:
                    break
        
        return similar

    def _recognize_error_pattern(self, error: str) -> Optional[Dict[str, Any]]:
        """Recognize error patterns and suggest fixes."""
        for error_type, pattern_info in self.error_patterns.items():
            match = re.search(pattern_info["pattern"], error, re.IGNORECASE)
            if match:
                return {
                    "error_type": error_type,
                    "action": pattern_info["action"],
                    "description": pattern_info["description"],
                    "match_groups": match.groups(),
                    "confidence": 0.8  # High confidence for pattern matches
                }
        
        # Check learned patterns
        for learned_pattern in self.learned_patterns:
            if learned_pattern.get("pattern") in error.lower():
                return {
                    "error_type": "learned",
                    "action": learned_pattern.get("action", "retry"),
                    "description": learned_pattern.get("description", "Apply learned fix"),
                    "confidence": learned_pattern.get("confidence", 0.6)
                }
        
        return None

    def _generate_pattern_based_fix(self, pattern_info: Dict[str, Any], error: str, task: dict) -> str:
        """Generate a fix based on recognized pattern."""
        action = pattern_info["action"]
        match_groups = pattern_info.get("match_groups", [])
        
        if action == "install_dependency" and match_groups:
            module_name = match_groups[0]
            return f"Install missing dependency: pip install {module_name}"
        
        elif action == "fix_import" and match_groups:
            import_name = match_groups[0]
            return f"Fix import for '{import_name}'. Check if the module is installed or if the import statement is correct."
        
        elif action == "regenerate_code":
            return f"Regenerate the code with correct syntax. The error indicates a syntax issue that needs to be fixed."
        
        elif action == "define_variable" and match_groups:
            var_name = match_groups[0]
            return f"Define the variable '{var_name}' before using it, or check for spelling mistakes."
        
        elif action == "fix_type_mismatch":
            return f"Fix the type mismatch. Ensure variables are of the correct type before operations."
        
        elif action == "add_attribute" and match_groups:
            obj_type, attr_name = match_groups
            return f"Add the missing attribute '{attr_name}' to the {obj_type} object or check the object type."
        
        elif action == "handle_missing_key" and match_groups:
            key_name = match_groups[0]
            return f"Handle the missing key '{key_name}' in the dictionary. Use .get() method or check if key exists."
        
        elif action == "create_file" and match_groups:
            file_path = match_groups[0]
            return f"Create the missing file: {file_path}"
        
        elif action == "fix_permissions":
            return "Fix file permissions. Check if the file exists and if you have the right permissions."
        
        elif action == "handle_connection":
            return "Handle connection issues. Check if the server is running and network connectivity."
        
        elif action == "validate_input":
            return "Add input validation to prevent invalid values."
        
        elif action == "fix_index_bounds":
            return "Fix index bounds. Ensure the index is within the valid range for the list/array."
        
        elif action == "fix_assertion":
            return "Fix the failed assertion. Check the condition and ensure it's correct."
        
        else:
            return f"Apply {action} to fix the error: {error}"

    def learn_pattern(self, error: str, fix: str, success: bool):
        """Learn successful patterns for future use."""
        if success:
            pattern_entry = {
                "pattern": self._normalize_error(error)[:100],  # First 100 chars
                "fix": fix,
                "action": "apply_learned_fix",
                "description": "Previously successful fix",
                "confidence": 0.7,
                "learned_at": str(logger._core.start_time if hasattr(logger, '_core') else "unknown")
            }
            self.learned_patterns.append(pattern_entry)
            logger.info(f"[debugger_agent] Learned new pattern (total: {len(self.learned_patterns)})")

    def analyze(
        self,
        error: str,
        task: dict,
        snapshot=None,
    ) -> dict:
        # Check if we should stop retrying this error
        if self._should_stop_retrying(error):
            similar_errors = self.get_similar_errors(error)
            previous_fixes = [item.get("fix_suggestion", "") for item in similar_errors if item.get("fix_suggestion")]
            
            return {
                "fix": f"Error repeated {self.repeat_threshold} times. Previous fixes attempted: {'; '.join(previous_fixes) if previous_fixes else 'None'}",
                "revised_command": None,
                "stop_retrying": True
            }
        
        # Try to recognize the error pattern
        pattern_info = self._recognize_error_pattern(error)
        
        # Get similar errors for context
        similar_errors = self.get_similar_errors(error)
        context = ""
        if similar_errors:
            context = f"Similar errors have been seen {len(similar_errors)} times before. "
            previous_fixes = [item.get("fix_suggestion", "") for item in similar_errors if item.get("fix_suggestion")]
            if previous_fixes:
                context += f"Previous fix attempts: {'; '.join(previous_fixes[:2])}"
        
        # Generate fix based on pattern recognition
        if pattern_info:
            pattern_fix = self._generate_pattern_based_fix(pattern_info, error, task)
            
            # Combine with context
            if context:
                full_fix = f"{pattern_fix}\n\nContext: {context}"
            else:
                full_fix = pattern_fix
            
            result = {
                "fix": full_fix,
                "revised_command": None,
                "pattern_recognized": True,
                "pattern_type": pattern_info["error_type"],
                "confidence": pattern_info["confidence"],
                "stop_retrying": False
            }
            
            # Record the error with pattern-based fix
            self._record_error(error, task, pattern_fix)
            
            return result
        
        # Fall back to original debugger if no pattern recognized
        try:
            debugger_result = self.debugger.analyze(error, task, snapshot)
            
            # Convert to dict format and record the error
            if isinstance(debugger_result, dict):
                fix_suggestion = debugger_result.get("fix", "")
            else:
                fix_suggestion = str(debugger_result)
                debugger_result = {
                    "fix": fix_suggestion,
                    "revised_command": None,
                }
            
            # Record this error for future reference
            self._record_error(error, task, fix_suggestion)
            
            # Add context about similar errors if available
            if context and "fix" in debugger_result:
                debugger_result["fix"] = f"{debugger_result['fix']}\n\nContext: {context}"
            
            debugger_result.update({
                "pattern_recognized": False,
                "stop_retrying": False
            })
            
            return debugger_result
            
        except Exception as e:
            logger.error(f"[debugger_agent] Original debugger failed: {e}")
            
            # Fallback fix
            fallback_fix = f"Error occurred: {error}. Please review the code and fix the issue manually."
            self._record_error(error, task, fallback_fix)
            
            return {
                "fix": fallback_fix,
                "revised_command": None,
                "pattern_recognized": False,
                "stop_retrying": False
            }
