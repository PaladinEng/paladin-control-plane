"""
Parse a markdown or text file into a list of prompts.

Two conventions supported:
1. ## header sections: each ## heading + body is one prompt
2. Blank-line paragraphs: each paragraph (text block) is one prompt
"""

import re


def parse_prompts(content: str) -> list[str]:
    """Parse file content into ordered list of prompt strings."""
    content = content.strip()
    if not content:
        return []

    if re.search(r'^##\s+', content, re.MULTILINE):
        return _parse_by_headers(content)

    return _parse_by_paragraphs(content)


def _parse_by_headers(content: str) -> list[str]:
    """Split on ## headings -- each section becomes one prompt."""
    sections = re.split(r'\n(?=##\s+)', content)
    prompts = []
    for section in sections:
        section = section.strip()
        if section:
            prompts.append(section)
    return [p for p in prompts if p.strip()]


def _parse_by_paragraphs(content: str) -> list[str]:
    """Split on blank lines -- each paragraph becomes one prompt."""
    paragraphs = re.split(r'\n\s*\n', content)
    return [p.strip() for p in paragraphs if p.strip()]
