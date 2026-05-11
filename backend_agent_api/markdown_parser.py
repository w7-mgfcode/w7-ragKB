"""Markdown parsing and formatting utilities.

Provides functions for parsing markdown into structured format and
pretty-printing with consistent formatting and frontmatter preservation.
"""

import re
from typing import Dict, Optional, Tuple


def parse_frontmatter(content: str) -> Tuple[Optional[Dict[str, str]], str]:
    """Extract YAML frontmatter from markdown content.
    
    Args:
        content: Markdown content potentially with frontmatter
        
    Returns:
        Tuple of (frontmatter_dict, content_without_frontmatter)
        Returns (None, content) if no frontmatter found
    """
    # Match YAML frontmatter: --- at start, --- at end
    frontmatter_pattern = re.compile(
        r"^---\s*\n(.*?)\n---\s*\n",
        re.DOTALL | re.MULTILINE
    )
    
    match = frontmatter_pattern.match(content)
    if not match:
        return None, content
    
    frontmatter_text = match.group(1)
    content_without_frontmatter = content[match.end():]
    
    # Parse YAML frontmatter into dict (simple key: value pairs)
    frontmatter = {}
    for line in frontmatter_text.split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        
        if ":" in line:
            key, value = line.split(":", 1)
            frontmatter[key.strip()] = value.strip()
    
    return frontmatter, content_without_frontmatter


def serialize_frontmatter(frontmatter: Dict[str, str]) -> str:
    """Serialize frontmatter dict to YAML format.
    
    Args:
        frontmatter: Dictionary of frontmatter key-value pairs
        
    Returns:
        YAML frontmatter string with delimiters
    """
    if not frontmatter:
        return ""
    
    lines = ["---"]
    for key, value in frontmatter.items():
        lines.append(f"{key}: {value}")
    lines.append("---")
    lines.append("")  # Blank line after frontmatter
    
    return "\n".join(lines)


def parse_markdown(content: str) -> Dict[str, any]:
    """Parse markdown content into structured format.
    
    Args:
        content: Raw markdown content
        
    Returns:
        Dict with 'frontmatter', 'body', and 'metadata' keys
    """
    frontmatter, body = parse_frontmatter(content)
    
    # Extract basic metadata
    lines = body.split("\n")
    word_count = len(body.split())
    heading_count = sum(1 for line in lines if line.strip().startswith("#"))
    
    return {
        "frontmatter": frontmatter,
        "body": body,
        "metadata": {
            "word_count": word_count,
            "heading_count": heading_count,
            "line_count": len(lines),
        }
    }


def pretty_print_markdown(parsed: Dict[str, any]) -> str:
    """Format parsed markdown with consistent spacing and indentation.
    
    Args:
        parsed: Parsed markdown dict from parse_markdown()
        
    Returns:
        Formatted markdown string
    """
    parts = []
    
    # Add frontmatter if present
    if parsed.get("frontmatter"):
        parts.append(serialize_frontmatter(parsed["frontmatter"]))
    
    # Add body with normalized spacing
    body = parsed["body"]
    
    # Normalize multiple blank lines to single blank line
    body = re.sub(r"\n{3,}", "\n\n", body)
    
    # Ensure single blank line before headings (except first line)
    body = re.sub(r"([^\n])\n(#{1,6} )", r"\1\n\n\2", body)
    
    # Ensure single blank line after headings
    body = re.sub(r"(#{1,6} [^\n]+)\n([^\n#])", r"\1\n\n\2", body)
    
    # Strip trailing whitespace from lines
    lines = [line.rstrip() for line in body.split("\n")]
    body = "\n".join(lines)
    
    parts.append(body)
    
    # Ensure file ends with single newline
    result = "\n".join(parts)
    if not result.endswith("\n"):
        result += "\n"
    
    return result


def markdown_round_trip(content: str) -> str:
    """Parse and pretty-print markdown (round-trip test helper).
    
    Args:
        content: Raw markdown content
        
    Returns:
        Formatted markdown content
    """
    parsed = parse_markdown(content)
    return pretty_print_markdown(parsed)
