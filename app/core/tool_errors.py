"""Tool-result error classification.

The execution loop receives plain strings from heterogeneous MCP tools.  Keeping
the error classifier here makes the policy explicit and independently testable.
"""

from __future__ import annotations

import re
from typing import Any


ERROR_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b(error|exception|traceback|failed|failure)\b", re.IGNORECASE),
    re.compile(r"\b(permission denied|not found|no such file)\b", re.IGNORECASE),
    re.compile(r"\b(sql error|syntax error|connection refused)\b", re.IGNORECASE),
)


def is_tool_error(result: Any) -> bool:
    """Return True when a tool result looks like an operational failure."""
    if result is None:
        return False

    text = str(result).strip()
    if not text:
        return False

    return any(pattern.search(text) for pattern in ERROR_PATTERNS)
