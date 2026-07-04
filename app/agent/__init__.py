__all__ = ["run"]


def __getattr__(name):
    """Load the high-level executor only when callers ask for it."""
    if name == "run":
        from agent.executor import run

        return run
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
