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
