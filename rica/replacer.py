from pathlib import Path
from loguru import logger


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
