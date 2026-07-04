import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.tool_errors import is_tool_error


def test_tool_error_detects_common_failure_strings():
    assert is_tool_error("SQL error: near BAD")
    assert is_tool_error("Traceback (most recent call last):")
    assert is_tool_error("permission denied while writing file")
    assert is_tool_error("connection refused")


def test_tool_error_is_case_insensitive():
    assert is_tool_error("ERROR: file not found")
    assert is_tool_error("Command Failed with exit code 1")


def test_tool_error_ignores_normal_results():
    assert not is_tool_error("created report.txt successfully")
    assert not is_tool_error("0 rows returned")
    assert not is_tool_error("")
    assert not is_tool_error(None)
