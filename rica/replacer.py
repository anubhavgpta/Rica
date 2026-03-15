from pathlib import Path
import re
from loguru import logger
from rica.utils.ast_editor import (
    replace_function,
    insert_import_source,
    add_function_source
)


class StrReplacer:

    @staticmethod
    def apply(
        filepath: Path,
        old_str: str,
        new_str: str,
    ) -> bool:
        """
        Replace exactly one occurrence of
        old_str in filepath with new_str.
        Returns True on success, False if
        old_str not found or multiple matches.
        """
        content = filepath.read_text(
            encoding='utf-8'
        )
        count = content.count(old_str)
        if count == 0:
            logger.warning(
                f"[replacer] old_str not found"
                f" in {filepath.name}"
            )
            return False
        if count > 1:
            logger.warning(
                f"[replacer] old_str matches"
                f" {count} times in"
                f" {filepath.name} — ambiguous,"
                f" skipping"
            )
            return False
        new_content = content.replace(
            old_str, new_str, 1
        )
        filepath.write_text(
            new_content, encoding='utf-8'
        )
        logger.info(
            f"[replacer] Applied str_replace"
            f" to {filepath.name}"
        )
        return True

    @staticmethod
    def append(
        filepath: Path,
        content: str,
    ) -> None:
        """
        Append content to end of file,
        ensuring a blank line separator.
        """
        existing = filepath.read_text(
            encoding='utf-8'
        )
        if not existing.endswith('\n\n'):
            content = '\n' + content
        filepath.write_text(
            existing + content,
            encoding='utf-8'
        )
        logger.info(
            f"[replacer] Appended to"
            f" {filepath.name}"
        )

    @staticmethod
    def apply_patch(
        filepath: Path,
        old_code: str,
        new_code: str,
        fuzzy: bool = True
    ) -> bool:
        """
        Apply a precise patch to a file by locating and replacing
        a specific code section while preserving the rest of the file.
        
        Args:
            filepath: Path to the file to modify
            old_code: The exact code section to replace
            new_code: The new code to insert
            fuzzy: If True, allows minor whitespace differences
            
        Returns:
            True if patch was applied successfully, False otherwise
        """
        try:
            content = filepath.read_text(encoding='utf-8')
            
            # Try exact match first
            if old_code in content:
                new_content = content.replace(old_code, new_code, 1)
                filepath.write_text(new_content, encoding='utf-8')
                logger.info(f"[replacer] Applied exact patch to {filepath.name}")
                return True
            
            # If fuzzy matching enabled, try with normalized whitespace
            if fuzzy:
                normalized_old = re.sub(r'\s+', ' ', old_code.strip())
                normalized_content_lines = content.splitlines()
                
                for i, line in enumerate(normalized_content_lines):
                    normalized_line = re.sub(r'\s+', ' ', line.strip())
                    if normalized_old in normalized_line:
                        # Find the actual original line that matches
                        original_lines = content.splitlines()
                        if i < len(original_lines):
                            # Replace the original line
                            original_lines[i] = new_code.rstrip()
                            new_content = '\n'.join(original_lines)
                            filepath.write_text(new_content, encoding='utf-8')
                            logger.info(f"[replacer] Applied fuzzy patch to {filepath.name}")
                            return True
            
            logger.warning(f"[replacer] Patch not found in {filepath.name}")
            return False
            
        except Exception as e:
            logger.error(f"[replacer] Failed to apply patch to {filepath.name}: {e}")
            return False

    @staticmethod
    def insert_after(
        filepath: Path,
        marker: str,
        content: str,
    ) -> bool:
        """
        Insert content immediately after a marker line.
        
        Args:
            filepath: Path to the file to modify
            marker: The line after which to insert content
            content: Content to insert
            
        Returns:
            True if insertion was successful, False otherwise
        """
        try:
            lines = filepath.read_text(encoding='utf-8').splitlines()
            
            for i, line in enumerate(lines):
                if marker in line:
                    # Insert after this line
                    lines.insert(i + 1, content)
                    new_content = '\n'.join(lines)
                    filepath.write_text(new_content, encoding='utf-8')
                    logger.info(f"[replacer] Inserted content after marker in {filepath.name}")
                    return True
            
            logger.warning(f"[replacer] Marker not found in {filepath.name}")
            return False
            
        except Exception as e:
            logger.error(f"[replacer] Failed to insert content in {filepath.name}: {e}")
            return False

    @staticmethod
    def insert_before(
        filepath: Path,
        marker: str,
        content: str,
    ) -> bool:
        """
        Insert content immediately before a marker line.
        
        Args:
            filepath: Path to the file to modify
            marker: The line before which to insert content
            content: Content to insert
            
        Returns:
            True if insertion was successful, False otherwise
        """
        try:
            lines = filepath.read_text(encoding='utf-8').splitlines()
            
            for i, line in enumerate(lines):
                if marker in line:
                    # Insert before this line
                    lines.insert(i, content)
                    new_content = '\n'.join(lines)
                    filepath.write_text(new_content, encoding='utf-8')
                    logger.info(f"[replacer] Inserted content before marker in {filepath.name}")
                    return True
            
            logger.warning(f"[replacer] Marker not found in {filepath.name}")
            return False
            
        except Exception as e:
            logger.error(f"[replacer] Failed to insert content in {filepath.name}: {e}")
            return False

    @staticmethod
    def is_python_file(filepath: Path) -> bool:
        """Check if the file is a Python file."""
        return filepath.suffix.lower() == '.py'

    @staticmethod
    def replace_function_ast(
        filepath: Path,
        func_name: str,
        new_code: str,
    ) -> bool:
        """
        Replace a function using AST editing for Python files.
        Falls back to string replacement if AST parsing fails.
        
        Args:
            filepath: Path to the Python file
            func_name: Name of the function to replace
            new_code: New function code
            
        Returns:
            True if replacement was successful, False otherwise
        """
        if not StrReplacer.is_python_file(filepath):
            logger.warning(f"[replacer] AST editing only supported for Python files: {filepath.name}")
            return False
            
        try:
            content = filepath.read_text(encoding='utf-8')
            modified_content = replace_function(content, func_name, new_code)
            
            if modified_content is None:
                logger.warning(f"[replacer] AST editing failed for {filepath.name}, falling back to string replacement")
                return StrReplacer._fallback_function_replacement(filepath, func_name, new_code)
                
            filepath.write_text(modified_content, encoding='utf-8')
            logger.info(f"[replacer] Applied AST function replacement to {filepath.name}")
            return True
            
        except Exception as e:
            logger.error(f"[replacer] AST function replacement failed for {filepath.name}: {e}")
            return False

    @staticmethod
    def insert_import_ast(
        filepath: Path,
        module: str,
        name: str = None,
        alias: str = None,
    ) -> bool:
        """
        Insert an import statement using AST editing for Python files.
        Falls back to string replacement if AST parsing fails.
        
        Args:
            filepath: Path to the Python file
            module: Module to import
            name: Name to import from module
            alias: Alias for the imported name
            
        Returns:
            True if insertion was successful, False otherwise
        """
        if not StrReplacer.is_python_file(filepath):
            logger.warning(f"[replacer] AST editing only supported for Python files: {filepath.name}")
            return False
            
        try:
            content = filepath.read_text(encoding='utf-8')
            modified_content = insert_import_source(content, module, name, alias)
            
            if modified_content is None:
                logger.warning(f"[replacer] AST editing failed for {filepath.name}, falling back to string replacement")
                return StrReplacer._fallback_import_insertion(filepath, module, name, alias)
                
            filepath.write_text(modified_content, encoding='utf-8')
            logger.info(f"[replacer] Applied AST import insertion to {filepath.name}")
            return True
            
        except Exception as e:
            logger.error(f"[replacer] AST import insertion failed for {filepath.name}: {e}")
            return False

    @staticmethod
    def add_function_ast(
        filepath: Path,
        code: str,
    ) -> bool:
        """
        Add a function using AST editing for Python files.
        Falls back to string replacement if AST parsing fails.
        
        Args:
            filepath: Path to the Python file
            code: Function code to add
            
        Returns:
            True if addition was successful, False otherwise
        """
        if not StrReplacer.is_python_file(filepath):
            logger.warning(f"[replacer] AST editing only supported for Python files: {filepath.name}")
            return False
            
        try:
            content = filepath.read_text(encoding='utf-8')
            modified_content = add_function_source(content, code)
            
            if modified_content is None:
                logger.warning(f"[replacer] AST editing failed for {filepath.name}, falling back to string replacement")
                return StrReplacer._fallback_function_addition(filepath, code)
                
            filepath.write_text(modified_content, encoding='utf-8')
            logger.info(f"[replacer] Applied AST function addition to {filepath.name}")
            return True
            
        except Exception as e:
            logger.error(f"[replacer] AST function addition failed for {filepath.name}: {e}")
            return False

    @staticmethod
    def _fallback_function_replacement(filepath: Path, func_name: str, new_code: str) -> bool:
        """Fallback method for function replacement using string operations."""
        try:
            content = filepath.read_text(encoding='utf-8')
            
            # Try to find function definition pattern
            import_pattern = rf'def {func_name}\([^)]*\):'
            
            if re.search(import_pattern, content):
                # Simple string-based fallback
                lines = content.splitlines()
                func_start = None
                indent_level = None
                
                for i, line in enumerate(lines):
                    if re.match(import_pattern, line):
                        func_start = i
                        indent_level = len(line) - len(line.lstrip())
                        break
                
                if func_start is not None:
                    # Find end of function
                    func_end = func_start + 1
                    for j in range(func_start + 1, len(lines)):
                        line = lines[j]
                        if line.strip() and len(line) - len(line.lstrip()) <= indent_level and not line.strip().startswith('#'):
                            func_end = j
                            break
                    
                    # Replace function body
                    new_lines = lines[:func_start + 1] + new_code.splitlines() + lines[func_end:]
                    filepath.write_text('\n'.join(new_lines), encoding='utf-8')
                    logger.info(f"[replacer] Applied fallback function replacement to {filepath.name}")
                    return True
            
            return False
            
        except Exception as e:
            logger.error(f"[replacer] Fallback function replacement failed: {e}")
            return False

    @staticmethod
    def _fallback_import_insertion(filepath: Path, module: str, name: str = None, alias: str = None) -> bool:
        """Fallback method for import insertion using string operations."""
        try:
            content = filepath.read_text(encoding='utf-8')
            lines = content.splitlines()
            
            if name:
                import_line = f"from {module} import {name}"
                if alias:
                    import_line += f" as {alias}"
            else:
                import_line = f"import {module}"
                if alias:
                    import_line += f" as {alias}"
            
            # Insert after existing imports or at the beginning
            insert_pos = 0
            for i, line in enumerate(lines):
                if line.strip().startswith(('import ', 'from ')):
                    insert_pos = i + 1
                elif line.strip() and not line.strip().startswith('#'):
                    break
            
            lines.insert(insert_pos, import_line)
            filepath.write_text('\n'.join(lines), encoding='utf-8')
            logger.info(f"[replacer] Applied fallback import insertion to {filepath.name}")
            return True
            
        except Exception as e:
            logger.error(f"[replacer] Fallback import insertion failed: {e}")
            return False

    @staticmethod
    def _fallback_function_addition(filepath: Path, code: str) -> bool:
        """Fallback method for function addition using string operations."""
        try:
            content = filepath.read_text(encoding='utf-8')
            
            # Append function to end of file
            if not content.endswith('\n'):
                content += '\n'
            
            content += '\n' + code
            filepath.write_text(content, encoding='utf-8')
            logger.info(f"[replacer] Applied fallback function addition to {filepath.name}")
            return True
            
        except Exception as e:
            logger.error(f"[replacer] Fallback function addition failed: {e}")
            return False
