"""Tests for mini_agent.utils.markdown_renderer.

has_markdown is deliberately high-precision: it must never flag plain text
as Markdown (false positives visibly mangle content through rich rendering),
while missing some Markdown (false negatives) is acceptable — plain text is
printed as-is and still perfectly readable.
"""

import pytest

from mini_agent.utils.markdown_renderer import display_assistant_text, has_markdown


class TestHasMarkdownPositive:
    """Texts that clearly contain Markdown and should be detected."""

    def test_table(self):
        assert has_markdown("| a | b |\n|---|---|\n| 1 | 2 |")

    def test_table_without_delimiting_pipes_missed_ok(self):
        # Header row not delimited by pipes — a false negative, acceptable
        # by design (plain-text printing is harmless)
        assert not has_markdown("a | b\n--- | ---")

    def test_fenced_code_block(self):
        assert has_markdown("Example:\n\n```python\nprint('hi')\n```")

    def test_tilde_fence(self):
        assert has_markdown("~~~\ncode\n~~~")

    def test_atx_heading(self):
        assert has_markdown("## Results")

    def test_unordered_list(self):
        assert has_markdown("Steps:\n\n- first\n- second")

    def test_ordered_list(self):
        assert has_markdown("1. first\n2. second")


class TestHasMarkdownNegative:
    """Plain text that must NOT be flagged as Markdown."""

    def test_empty(self):
        assert not has_markdown("")

    def test_plain_prose(self):
        assert not has_markdown("Hello, the cost is 5 dollars and the answer is yes.")

    def test_dunder_filename(self):
        # __init__.py must not be read as bold markup
        assert not has_markdown("Please edit mini_agent/utils/__init__.py")

    def test_dunder_methods(self):
        assert not has_markdown("The __init__ and __call__ methods were updated.")

    def test_exponent_operator(self):
        # 2 ** 3 must not be read as bold markup
        assert not has_markdown("Compute 2 ** 3 ** 2 in Python.")

    def test_stray_backticks(self):
        assert not has_markdown("Use the ` quote character carefully.")

    def test_pipes_in_prose(self):
        assert not has_markdown("Either | or / separates the path parts.")

    def test_hash_number_sign(self):
        # "#1" has no space after the hash — not a heading
        assert not has_markdown("This is the #1 choice.")

    def test_indented_comment_is_not_heading(self):
        # 4+ space indent is an indented code block / comment, not a heading
        assert not has_markdown("    # this is a python comment")


class TestDisplayAssistantText:
    def test_plain_text_printed_verbatim(self, capsys):
        display_assistant_text("Plain __init__.py text")
        assert capsys.readouterr().out == "Plain __init__.py text\n"

    def test_markdown_rendered_without_exception(self, capsys):
        display_assistant_text("| a | b |\n|---|---|\n| 1 | 2 |")
        assert capsys.readouterr().out  # rich produced some output


@pytest.mark.parametrize("text", ["", "| a | b |\n|---|---|"])
def test_never_raises(text):
    display_assistant_text(text)
