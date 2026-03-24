"""React loop watchdog strategies.

Defines how the react loop responds to repeated tool errors.
Each strategy is a class implementing :class:`ReactWatchdog`.
Use :func:`get_react_watchdog` to obtain the active strategy by name.

Strategies
----------
none
    Default. No intervention — existing behaviour is preserved.

consecutive
    Triggers after N consecutive tool errors.  Injects a feedback message
    urging the model to try a completely different approach.

Adding a new strategy
---------------------
1. Subclass :class:`ReactWatchdog`.
2. Implement :meth:`check`.
3. Register it in :data:`_REGISTRY`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class ReactWatchdog(ABC):
    """Decide whether to inject a corrective feedback message."""

    @abstractmethod
    def check(self, consecutive_errors: int, last_result: str) -> str | None:
        """Return a feedback string when intervention is needed, else None.

        Args:
            consecutive_errors: Number of consecutive tool errors so far.
            last_result:        The last tool result string (may contain error text).
        """


# ---------------------------------------------------------------------------
# Strategy: none (noop)
# ---------------------------------------------------------------------------

class NoopWatchdog(ReactWatchdog):
    """Never intervenes — preserves existing react loop behaviour."""

    def check(self, consecutive_errors: int, last_result: str) -> str | None:
        return None


# ---------------------------------------------------------------------------
# Strategy: consecutive
# ---------------------------------------------------------------------------

class ConsecutiveErrorWatchdog(ReactWatchdog):
    """Trigger after *threshold* consecutive tool errors.

    Injects a feedback message asking the model to try a different approach.
    """

    def __init__(self, threshold: int = 2) -> None:
        self.threshold = threshold

    def check(self, consecutive_errors: int, last_result: str) -> str | None:
        if consecutive_errors >= self.threshold:
            return (
                f"[WATCHDOG] {consecutive_errors}回連続でツールエラーが発生しています。"
                "同じアプローチを繰り返さず、別のツールや方法を試してください。"
                "例: スクリプトを write_file で全体的に書き直す、"
                "またはツールを組み合わせる方法を変える。"
            )
        return None


# ---------------------------------------------------------------------------
# Registry + factory
# ---------------------------------------------------------------------------

_REGISTRY: dict[str, type[ReactWatchdog]] = {
    "none":        NoopWatchdog,
    "consecutive": ConsecutiveErrorWatchdog,
}


def get_react_watchdog(name: str) -> ReactWatchdog:
    """Return a new instance of the named watchdog strategy.

    Args:
        name: One of the keys in :data:`_REGISTRY`.

    Raises:
        ValueError: If *name* is not registered.
    """
    cls = _REGISTRY.get(name)
    if cls is None:
        raise ValueError(
            f"Unknown react watchdog: {name!r}. "
            f"Available: {sorted(_REGISTRY)}"
        )
    return cls()
