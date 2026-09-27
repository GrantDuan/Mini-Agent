"""Render assistant output in the terminal.

Plain text is printed as-is; text containing Markdown elements (tables,
headings, code fences, lists, etc.) is rendered through ``rich.markdown.Markdown``
for a friendlier display — most notably for Markdown tables.
"""

import re

from rich.console import Console
from rich.markdown import Markdown

# Detection is intentionally high-precision: we would rather print Markdown
# as plain text (harmless) than render non-Markdown through rich (mangles
# content, e.g. ``__init__.py`` bolded or tables drawn where none exist).
# Only structural, unambiguous constructs are detected — no inline emphasis,
# bold or backtick spans, which are too easy to false-positive on
# (``__init__``, ``2 ** 3``, stray backticks...).

# Matches a Markdown table: a header row of |...| cells followed by a
# |---|---| separator row (leading/trailing pipes optional).
_TABLE_RE = re.compile(r"^\s*\|.*\|\s*\n\s*\|?[\s:|-]*-[\s:|-]*\|?", re.MULTILINE)
# Fenced code block (``` or ~~~)
_FENCE_RE = re.compile(r"^ {0,3}(```|~~~)", re.MULTILINE)
# ATX heading (# Title), indented at most 3 spaces like real Markdown —
# deeper indentation is an indented code block or a comment, not a heading
_HEADING_RE = re.compile(r"^ {0,3}#{1,6}\s+\S", re.MULTILINE)
# Unordered/ordered list item
_LIST_RE = re.compile(r"^ {0,3}(?:[-*+]|\d{1,9}[.)])\s+\S", re.MULTILINE)

_rich_console = Console()


def has_markdown(text: str) -> bool:
    """Return True if the text looks like it contains Markdown markup.

    Only structural constructs are detected: tables, fenced code blocks,
    headings and list items. Inline emphasis, bold and inline code are
    deliberately ignored (too easy to false-positive on). Plain prose
    (even with ``|`` characters scattered around) stays untouched.
    """
    if not text:
        return False
    return bool(
        _TABLE_RE.search(text)
        or _FENCE_RE.search(text)
        or _HEADING_RE.search(text)
        or _LIST_RE.search(text)
    )


def display_assistant_text(text: str) -> None:
    """Print assistant output, rendering Markdown through rich when detected."""
    if has_markdown(text):
        _rich_console.print(Markdown(text))
    else:
        print(text)
