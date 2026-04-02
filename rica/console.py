import sys
import io
from rich.console import Console

def _make_console() -> Console:
    is_tty = hasattr(sys.stdout, "isatty") and sys.stdout.isatty()
    if is_tty:
        return Console()
    safe_stdout = io.TextIOWrapper(
        sys.stdout.buffer,
        encoding="utf-8",
        errors="replace",
        line_buffering=True,
    ) if hasattr(sys.stdout, "buffer") else sys.stdout
    return Console(
        file=safe_stdout,
        highlight=False,
        markup=False,
        emoji=False,
        no_color=True,
    )

console: Console = _make_console()

def get_console() -> Console:
    return console
