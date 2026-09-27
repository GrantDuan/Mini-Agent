"""Live streaming display for LLM output.

Renders a small fixed-height strip (default 3 lines) at the bottom of the
terminal that redraws itself in place while the LLM streams, so the user can
see the model is working without the stream flooding the whole terminal.
When the stream finishes, the strip is erased, leaving the terminal clean.

The display is a no-op when stdout is not a TTY (e.g. piped output).
"""

import shutil
import sys
import threading
import time

from .utils import calculate_display_width

# Spinner frames cycled on the header line while content is streaming
SPINNER_FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

# ANSI helpers
CURSOR_UP = "\x1b[1A"
CLEAR_LINE = "\r\x1b[2K"
DIM = "\033[2m"
RESET = "\033[0m"
CYAN = "\033[36m"


def _hard_wrap(text: str, width: int) -> list[str]:
    """Split text into lines of at most ``width`` display columns.

    Uses display width so CJK characters (2 columns) do not overflow.
    Newlines in the text are honored.
    """
    lines: list[str] = []
    for paragraph in text.split("\n"):
        line = ""
        line_width = 0
        for char in paragraph:
            char_width = calculate_display_width(char)
            if line_width + char_width > width:
                lines.append(line)
                line = ""
                line_width = 0
            line += char
            line_width += char_width
        lines.append(line)
    return lines


class StreamingDisplay:
    """Fixed-height in-place streaming strip.

    Usage:
        display = StreamingDisplay()
        display.update(delta_text)   # called for each streamed delta
        display.finish()             # erase the strip when done
    """

    def __init__(
        self,
        max_lines: int = 3,
        stream=None,
        min_interval: float = 0.05,
    ):
        """Initialize the display.

        Args:
            max_lines: Total strip height in lines, including the header line
            stream: Output stream (defaults to sys.stdout)
            min_interval: Minimum seconds between redraws (throttling)
        """
        self.stream = stream or sys.stdout
        self.max_lines = max(2, max_lines)  # need 1 header + at least 1 content line
        self.min_interval = min_interval

        # Disabled when not a real terminal: in-place ANSI rewriting would
        # just dump control codes into a pipe or log file.
        self.enabled = hasattr(self.stream, "isatty") and self.stream.isatty()

        self._lock = threading.Lock()
        self._text = ""
        self._chars = 0
        self._lines_drawn = 0
        self._last_render = 0.0
        self._spinner_index = 0

    def update(self, text: str) -> None:
        """Feed one streamed delta and redraw the strip (throttled)."""
        if not self.enabled or not text:
            return

        with self._lock:
            self._text += text
            self._chars += len(text)
            now = time.monotonic()
            if now - self._last_render < self.min_interval:
                return
            self._last_render = now
            self._spinner_index += 1
            self._render()

    def finish(self) -> None:
        """Erase the strip and reset state."""
        with self._lock:
            self._erase()
            self._text = ""
            self._chars = 0
            self._lines_drawn = 0
            self._last_render = 0.0

    # ------------------------------------------------------------------
    # Internal rendering (must be called with the lock held)
    # ------------------------------------------------------------------

    def _erase(self) -> None:
        """Erase the previously drawn strip lines."""
        if not self._lines_drawn:
            return
        parts = [CLEAR_LINE]
        parts.extend([CURSOR_UP, CLEAR_LINE] * (self._lines_drawn - 1))
        self.stream.write("".join(parts))
        self.stream.flush()
        self._lines_drawn = 0

    def _render(self) -> None:
        """Redraw the whole strip in place."""
        width = max(20, shutil.get_terminal_size().columns - 2)

        # Header line: spinner + status + character counter
        spinner = SPINNER_FRAMES[self._spinner_index % len(SPINNER_FRAMES)]
        counter = f"{self._chars:,} chars" if self._chars else "waiting for first token"
        header = f"{CYAN}{spinner}{RESET} {DIM}streaming... ({counter}){RESET}"

        # Content lines: the tail of the streamed text, wrapped to width.
        # One line goes to the header, the rest to content.
        content_capacity = self.max_lines - 1
        wrapped = _hard_wrap(self._text, width) if self._text else []
        shown = wrapped[-content_capacity:] if wrapped else [""]

        # Build the output: erase old lines, then write the new ones
        parts = []
        if self._lines_drawn:
            parts.append(CLEAR_LINE)
            parts.extend([CURSOR_UP, CLEAR_LINE] * (self._lines_drawn - 1))

        for i, line in enumerate(shown):
            # Truncate each content line to width (they are wrapped already,
            # but the last shown line may itself need trimming)
            parts.append(f"{DIM}{line[:width]}{RESET}")
            if i < len(shown) - 1:
                parts.append("\n")

        self.stream.write("".join(parts))
        self.stream.flush()
        self._lines_drawn = len(shown)
