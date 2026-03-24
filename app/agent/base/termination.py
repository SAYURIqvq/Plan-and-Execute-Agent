"""Termination strategies for the ReAct loop.

Defines how the loop decides to stop.  Each strategy is a class that
implements :class:`TerminationStrategy`.  Use :func:`get_termination_strategy`
to obtain the active strategy by name.

Strategies
----------
text
    Current default.  Any text response (no tool call) ends the loop.
    Simple, but cannot distinguish a "thinking" response from a real answer.

finish_tool
    The model must call ``finish(summary=...)`` to end the loop.
    Text-only responses are treated as in-progress thinking and the loop
    continues with a feedback nudge.  This prevents premature exit when the
    model outputs planning text without acting.

Adding a new strategy
---------------------
1. Subclass :class:`TerminationStrategy`.
2. Implement :meth:`check` (and optionally override :attr:`extra_tools`).
3. Register it in :data:`_REGISTRY`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

from langchain_core.tools import tool as lc_tool


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass
class TerminationResult:
    """Outcome of a single :meth:`TerminationStrategy.check` call."""

    should_stop: bool
    """True → exit the loop and return *answer* as the final output."""

    answer: Optional[str] = None
    """Final answer string.  Only meaningful when *should_stop* is True."""

    feedback: Optional[str] = None
    """Human-turn message to inject when *should_stop* is False.
    If None, the loop continues silently (normal tool execution path).
    """


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------

class TerminationStrategy(ABC):
    """Decide whether the ReAct loop should stop after each LLM response."""

    @abstractmethod
    def check(self, response) -> TerminationResult:
        """Inspect an LLM response and return a :class:`TerminationResult`.

        Called once per turn, before any tool execution.
        """

    @property
    def extra_tools(self) -> list:
        """LangChain tools to add to the model's tool list.

        Override to inject strategy-specific tools (e.g. ``finish``).
        """
        return []


# ---------------------------------------------------------------------------
# Strategy: text (current default)
# ---------------------------------------------------------------------------

class TextTermination(TerminationStrategy):
    """Stop on any text response (no tool call)."""

    def check(self, response) -> TerminationResult:
        if not response.tool_calls:
            from core.utils import _sanitize  # avoid circular import at module level
            return TerminationResult(should_stop=True, answer=_sanitize(response.content))
        return TerminationResult(should_stop=False)


# ---------------------------------------------------------------------------
# Strategy: finish_tool
# ---------------------------------------------------------------------------

FINISH_TOOL_NAME = "finish"

_FINISH_FEEDBACK = (
    "まだタスクが完了していません。"
    "ツールを使って作業を続け、全て完了したら finish() を呼び出してください。"
)


def _make_finish_tool():
    @lc_tool
    def finish(summary: str) -> str:
        """Call this when the task is fully complete.

        Args:
            summary: Brief description of everything that was accomplished.
        """
        return summary

    return finish


class FinishToolTermination(TerminationStrategy):
    """Stop only when the model explicitly calls ``finish()``.

    Text-only responses are treated as thinking and the loop continues
    with a feedback nudge.
    """

    def __init__(self) -> None:
        self._finish_tool = _make_finish_tool()

    def check(self, response) -> TerminationResult:
        if response.tool_calls:
            if response.tool_calls[0]["name"] == FINISH_TOOL_NAME:
                answer = response.tool_calls[0]["args"].get("summary", "")
                return TerminationResult(should_stop=True, answer=answer)
            # Normal tool call — continue without feedback
            return TerminationResult(should_stop=False)

        # Text-only response: treat as thinking, nudge to act
        return TerminationResult(should_stop=False, feedback=_FINISH_FEEDBACK)

    @property
    def extra_tools(self) -> list:
        return [self._finish_tool]


# ---------------------------------------------------------------------------
# Registry + factory
# ---------------------------------------------------------------------------

_REGISTRY: dict[str, type[TerminationStrategy]] = {
    "text":        TextTermination,
    "finish_tool": FinishToolTermination,
}


def get_termination_strategy(name: str) -> TerminationStrategy:
    """Return a new instance of the named termination strategy.

    Args:
        name: One of the keys in :data:`_REGISTRY`.

    Raises:
        ValueError: If *name* is not registered.
    """
    cls = _REGISTRY.get(name)
    if cls is None:
        raise ValueError(
            f"Unknown termination strategy: {name!r}. "
            f"Available: {sorted(_REGISTRY)}"
        )
    return cls()
