"""Tests for tokenizer-free Markdown chunking."""

from mcp_builder.search.chunking import chunks, utf8_size


def test_chunks_respect_utf8_budget_for_multilingual_text():
    """Every fragment respects byte limits even for multibyte characters."""
    result = list(chunks("# Title\n" + "é漢字 " * 80, limit=90))
    assert len(result) > 1
    assert all(utf8_size(content) <= 90 for _, content in result)
    assert "".join(content for _, content in result).replace("\n", "").startswith("# Title")


def test_split_code_fences_remain_balanced():
    """Split code blocks are closed and reopened around chunk boundaries."""
    result = list(chunks("# Code\n```python\n" + "x = 1\n" * 30 + "```\n", limit=80))
    assert len(result) > 1
    assert all(content.count("```") % 2 == 0 for _, content in result)
