from .filesystem import SERVER_CONFIG as FILESYSTEM_CONFIG
from .memory import SERVER_CONFIG as MEMORY_CONFIG
from .shell import SERVER_CONFIG as SHELL_CONFIG
from .sqlite import SERVER_CONFIG as SQLITE_CONFIG
from .time import SERVER_CONFIG as TIME_CONFIG
from .websearch import SERVER_CONFIG as WEBSEARCH_CONFIG

__all__ = [
    "FILESYSTEM_CONFIG",
    "MEMORY_CONFIG",
    "SHELL_CONFIG",
    "SQLITE_CONFIG",
    "TIME_CONFIG",
    "WEBSEARCH_CONFIG",
]
