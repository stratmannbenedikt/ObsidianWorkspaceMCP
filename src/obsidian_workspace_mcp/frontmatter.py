"""Frontmatter parsing — lightweight YAML-like extraction.

We deliberately avoid pulling in `pyyaml` as a runtime dependency. Obsidian
frontmatter is a small subset of YAML (scalars, lists, simple dicts). This
module handles that subset robustly enough for property queries.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any


_FRONTMATTER_RE = re.compile(
    r"^---[ \t]*\n(.*?)\n---[ \t]*",
    re.DOTALL,
)


def parse_frontmatter(text: str) -> dict[str, Any]:
    """Extract YAML frontmatter from markdown text.

    Returns an empty dict if no frontmatter block is found.
    Only handles the YAML subset Obsidian actually uses:
    - scalar values (string, int, float, bool)
    - lists (inline ``[a, b]`` and block ``- item``)
    - simple ``key: value`` pairs
    """
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return {}

    raw = m.group(1)
    props: dict[str, Any] = {}

    # Try to use yaml if available (handles edge cases better)
    try:
        import yaml  # type: ignore[import-untyped]
        result = yaml.safe_load(raw)
        if isinstance(result, dict):
            return result
        return {}
    except ImportError:
        pass
    except Exception:
        pass  # Fall through to our parser

    # Minimal fallback parser
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        match = re.match(r"^([a-zA-Z_][a-zA-Z0-9_./ -]*?)\s*:\s*(.*)", stripped)
        if not match:
            continue

        key = match.group(1).strip()
        value_str = match.group(2).strip()

        if not value_str:
            props[key] = None
            continue

        # Inline list: [a, b, c]
        if value_str.startswith("[") and value_str.endswith("]"):
            items = [s.strip().strip("\"'") for s in value_str[1:-1].split(",") if s.strip()]
            props[key] = items
            continue

        # Boolean
        if value_str.lower() in ("true", "false"):
            props[key] = value_str.lower() == "true"
            continue

        # Quoted string
        if (value_str.startswith('"') and value_str.endswith('"')) or \
           (value_str.startswith("'") and value_str.endswith("'")):
            props[key] = value_str[1:-1]
            continue

        # Number
        try:
            props[key] = int(value_str)
            continue
        except ValueError:
            pass
        try:
            props[key] = float(value_str)
            continue
        except ValueError:
            pass

        # Date-like (YYYY-MM-DD or ISO datetime)
        date_match = re.match(r"^(\d{4}-\d{2}-\d{2})(?:[T ](\d{2}:\d{2}(?::\d{2})?)([+-]\d{2}:\d{2})?)?$", value_str)
        if date_match:
            props[key] = value_str
            continue

        # Fallback: unquoted string
        props[key] = value_str

    return props


def read_frontmatter(path: Path) -> dict[str, Any]:
    """Read a markdown file and return its frontmatter as a dict."""
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return {}
    return parse_frontmatter(text)
