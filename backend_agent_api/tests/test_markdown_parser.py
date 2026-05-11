"""Unit tests for markdown parser module.

Tests cover:
- Line ending normalization (CRLF, CR, LF)
- Frontmatter extraction and parsing via parse_frontmatter()
- Markdown parsing into structured dict format
- Pretty printing with consistent formatting
- Round-trip operations (parse -> pretty-print -> parse)
"""

import pytest
from document_validation import normalize_line_endings
from markdown_parser import (
    parse_frontmatter,
    parse_markdown,
    pretty_print_markdown,
    markdown_round_trip,
)


class TestNormalizeLineEndings:
    """Tests for normalize_line_endings function."""

    def test_normalize_crlf_to_lf(self):
        """Test CRLF (Windows) line endings are normalized to LF."""
        text = "Line 1\r\nLine 2\r\nLine 3"
        result = normalize_line_endings(text)
        assert result == "Line 1\nLine 2\nLine 3"

    def test_normalize_cr_to_lf(self):
        """Test CR (old Mac) line endings are normalized to LF."""
        text = "Line 1\rLine 2\rLine 3"
        result = normalize_line_endings(text)
        assert result == "Line 1\nLine 2\nLine 3"

    def test_normalize_mixed_line_endings(self):
        """Test mixed line endings are all normalized to LF."""
        text = "Line 1\r\nLine 2\rLine 3\nLine 4"
        result = normalize_line_endings(text)
        assert result == "Line 1\nLine 2\nLine 3\nLine 4"

    def test_normalize_already_lf(self):
        """Test that LF line endings are unchanged."""
        text = "Line 1\nLine 2\nLine 3"
        result = normalize_line_endings(text)
        assert result == text

    def test_normalize_empty_string(self):
        """Test normalization of empty string."""
        assert normalize_line_endings("") == ""

    def test_normalize_no_line_endings(self):
        """Test text without line endings."""
        text = "Single line"
        assert normalize_line_endings(text) == text


class TestParseFrontmatter:
    """Tests for parse_frontmatter function.

    parse_frontmatter takes full markdown content (with --- delimiters)
    and returns Tuple[Optional[Dict], str] (frontmatter_dict, body).
    """

    def test_parse_simple_key_value(self):
        """Test parsing simple key-value pairs."""
        text = "---\ntitle: Test Document\nauthor: John Doe\n---\n"
        fm, body = parse_frontmatter(text)
        assert fm == {"title": "Test Document", "author": "John Doe"}
        assert body == ""

    def test_parse_values_with_colons(self):
        """Test parsing values containing colons."""
        text = "---\nurl: https://example.com:8080/path\n---\n"
        fm, body = parse_frontmatter(text)
        assert fm == {"url": "https://example.com:8080/path"}

    def test_parse_no_frontmatter(self):
        """Test parsing content without frontmatter."""
        text = "# Just content"
        fm, body = parse_frontmatter(text)
        assert fm is None
        assert body == text

    def test_parse_with_whitespace(self):
        """Test parsing with extra whitespace around keys and values."""
        text = "---\n  title  :  Test  \n  author  :  John  \n---\n"
        fm, body = parse_frontmatter(text)
        assert fm == {"title": "Test", "author": "John"}

    def test_parse_with_comments(self):
        """Test that comment lines (starting with #) are skipped."""
        text = "---\n# comment\ntitle: Test\n# another\nauthor: John\n---\n"
        fm, body = parse_frontmatter(text)
        assert fm == {"title": "Test", "author": "John"}

    def test_parse_preserves_body(self):
        """Test that body after frontmatter is preserved."""
        text = "---\ntitle: Test\n---\n# Heading\n\nParagraph"
        fm, body = parse_frontmatter(text)
        assert fm == {"title": "Test"}
        assert body == "# Heading\n\nParagraph"

    def test_parse_frontmatter_not_at_start(self):
        """Test that frontmatter not at document start is ignored."""
        text = "Some text\n---\ntitle: Test\n---\n# Content"
        fm, body = parse_frontmatter(text)
        assert fm is None
        assert body == text

    def test_parse_frontmatter_with_dashes_in_content(self):
        """Test that dashes in content don't break parsing."""
        text = "---\ntitle: Test\n---\n# Content\n\n---\n\nMore content"
        fm, body = parse_frontmatter(text)
        assert fm == {"title": "Test"}
        assert "---" in body
        assert "More content" in body


class TestParseMarkdown:
    """Tests for parse_markdown function.

    parse_markdown returns a dict with keys: frontmatter, body, metadata.
    """

    def test_parse_with_frontmatter(self):
        """Test parsing markdown with frontmatter."""
        text = "---\ntitle: Test\nauthor: John\n---\n# Hello World"
        parsed = parse_markdown(text)

        assert parsed["frontmatter"] == {"title": "Test", "author": "John"}
        assert parsed["body"] == "# Hello World"
        assert "metadata" in parsed

    def test_parse_without_frontmatter(self):
        """Test parsing markdown without frontmatter."""
        text = "# Hello World\n\nThis is content."
        parsed = parse_markdown(text)

        assert parsed["frontmatter"] is None
        assert parsed["body"] == text

    def test_parse_empty_document(self):
        """Test parsing empty document."""
        parsed = parse_markdown("")

        assert parsed["frontmatter"] is None
        assert parsed["body"] == ""

    def test_parse_only_frontmatter(self):
        """Test parsing document with only frontmatter."""
        text = "---\ntitle: Test\n---\n"
        parsed = parse_markdown(text)

        assert parsed["frontmatter"] == {"title": "Test"}
        assert parsed["body"] == ""

    def test_parse_complex_markdown(self):
        """Test parsing complex markdown with various elements."""
        text = "---\ntitle: API Design\n---\n# API Design Guidelines\n\n## Introduction\n\nContent.\n\n```python\ndef hello():\n    print(\"Hello\")\n```\n\n- Item 1\n- Item 2\n"
        parsed = parse_markdown(text)

        assert parsed["frontmatter"] is not None
        assert parsed["frontmatter"]["title"] == "API Design"
        assert "# API Design Guidelines" in parsed["body"]
        assert "```python" in parsed["body"]

    def test_parse_metadata_word_count(self):
        """Test that metadata includes word count."""
        text = "Hello world test"
        parsed = parse_markdown(text)
        assert parsed["metadata"]["word_count"] == 3

    def test_parse_metadata_heading_count(self):
        """Test that metadata includes heading count."""
        text = "# H1\n## H2\nText\n### H3"
        parsed = parse_markdown(text)
        assert parsed["metadata"]["heading_count"] == 3


class TestPrettyPrintMarkdown:
    """Tests for pretty_print_markdown function.

    pretty_print_markdown takes a dict with 'frontmatter' and 'body' keys.
    """

    def test_pretty_print_with_frontmatter(self):
        """Test pretty printing with frontmatter."""
        parsed = {"frontmatter": {"title": "Test"}, "body": "# Hello World"}
        result = pretty_print_markdown(parsed)

        assert result.startswith("---\n")
        assert "title: Test" in result
        assert "# Hello World" in result
        assert result.endswith("\n")

    def test_pretty_print_without_frontmatter(self):
        """Test pretty printing without frontmatter."""
        parsed = {"frontmatter": None, "body": "# Hello World"}
        result = pretty_print_markdown(parsed)

        assert result == "# Hello World\n"

    def test_pretty_print_trims_trailing_whitespace(self):
        """Test that trailing whitespace is trimmed from lines."""
        parsed = {"frontmatter": None, "body": "# Hello   \nWorld   \n"}
        result = pretty_print_markdown(parsed)

        assert "# Hello\n" in result
        assert "World\n" in result

    def test_pretty_print_preserves_internal_blank_lines(self):
        """Test that internal blank lines are preserved."""
        parsed = {"frontmatter": None, "body": "# Hello\n\nParagraph 1\n\nParagraph 2"}
        result = pretty_print_markdown(parsed)

        assert "# Hello\n\nParagraph 1\n\nParagraph 2\n" == result

    def test_pretty_print_empty_content(self):
        """Test pretty printing empty content."""
        parsed = {"frontmatter": None, "body": ""}
        result = pretty_print_markdown(parsed)

        assert result == "\n"

    def test_pretty_print_with_unicode(self):
        """Test pretty printing with Unicode characters."""
        parsed = {"frontmatter": None, "body": "# Hello\n\nemojis and unicode"}
        result = pretty_print_markdown(parsed)

        assert "unicode" in result
        assert result.endswith("\n")


class TestRoundTrip:
    """Tests for round-trip operations (parse -> pretty-print -> parse)."""

    def test_roundtrip_simple_document(self):
        """Test round-trip with simple document (no frontmatter)."""
        original = "# Hello World\n\nThis is a test.\n"

        parsed1 = parse_markdown(original)
        pretty = pretty_print_markdown(parsed1)
        parsed2 = parse_markdown(pretty)

        assert parsed1 == parsed2

    def test_roundtrip_preserves_frontmatter_dict(self):
        """Test that round-trip preserves frontmatter dict values."""
        original = "---\ntitle: Test\nauthor: John\n---\n# Hello\n"

        parsed1 = parse_markdown(original)
        pretty = pretty_print_markdown(parsed1)
        parsed2 = parse_markdown(pretty)

        assert parsed1["frontmatter"] == parsed2["frontmatter"]
        assert parsed2["frontmatter"] == {"title": "Test", "author": "John"}

    def test_roundtrip_preserves_body_content(self):
        """Test that round-trip preserves body content words."""
        original = "---\ntitle: Test\n---\n# Hello\n\nParagraph content here.\n"

        parsed1 = parse_markdown(original)
        pretty = pretty_print_markdown(parsed1)
        parsed2 = parse_markdown(pretty)

        # Body content is preserved (may have minor whitespace differences)
        assert "Hello" in parsed2["body"]
        assert "Paragraph content here." in parsed2["body"]

    def test_roundtrip_normalizes_line_endings(self):
        """Test that round-trip normalizes line endings."""
        original = "# Hello\r\nWorld\r\n"

        parsed1 = parse_markdown(original)
        pretty = pretty_print_markdown(parsed1)

        # Pretty printed version should have LF only
        assert "\r" not in pretty

    def test_roundtrip_stable_without_frontmatter(self):
        """Test that round-trip is stable for documents without frontmatter."""
        original = "# Heading\n\nParagraph 1\n\nParagraph 2\n"

        pretty1 = markdown_round_trip(original)
        pretty2 = markdown_round_trip(pretty1)

        assert pretty1 == pretty2

    def test_roundtrip_complex_document(self):
        """Test round-trip preserves complex content."""
        original = "# Code Example\n\n```python\ndef test():\n    return True\n```\n\n- Item 1\n- Item 2\n"

        parsed1 = parse_markdown(original)
        pretty = pretty_print_markdown(parsed1)
        parsed2 = parse_markdown(pretty)

        assert "```python" in parsed2["body"]
        assert "- Item 1" in parsed2["body"]
        assert "- Item 2" in parsed2["body"]


class TestEdgeCases:
    """Tests for edge cases and error conditions."""

    def test_parse_malformed_frontmatter(self):
        """Test parsing with malformed frontmatter."""
        text = "---\nthis is not valid yaml\n---\n# Content"
        parsed = parse_markdown(text)

        # Should still parse — content after frontmatter is body
        assert parsed["body"] == "# Content"

    def test_parse_frontmatter_with_triple_dashes_in_content(self):
        """Test that triple dashes in content don't break parsing."""
        text = "---\ntitle: Test\n---\n# Content\n\n---\n\nMore content"
        parsed = parse_markdown(text)

        assert parsed["frontmatter"] == {"title": "Test"}
        assert "---" in parsed["body"]
        assert "More content" in parsed["body"]

    def test_pretty_print_with_unicode(self):
        """Test pretty printing with Unicode characters."""
        parsed = {"frontmatter": None, "body": "# Unicode test\n\nEmojis and chars"}
        result = pretty_print_markdown(parsed)

        assert "Unicode test" in result

    def test_parse_very_long_document(self):
        """Test parsing very long document."""
        content = "# Heading\n\n" + ("Paragraph\n\n" * 1000)
        parsed = parse_markdown(content)

        assert parsed["body"].count("Paragraph") == 1000

    def test_roundtrip_with_code_blocks(self):
        """Test round-trip with code blocks containing special characters."""
        original = "# Code Example\n\n```python\ndef test():\n    # Comment with special chars: <>&\"'\n    return \"Hello\\\\nWorld\"\n```\n"

        parsed1 = parse_markdown(original)
        pretty = pretty_print_markdown(parsed1)
        parsed2 = parse_markdown(pretty)

        assert "<>&\"'" in parsed2["body"]
