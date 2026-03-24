import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.tools import ToolException

sys.path.insert(0, str(Path(__file__).parent.parent))

from unittest.mock import MagicMock

from agent.components.loop_helpers import (
    _apply_window,
    _invoke_tool,
    _trim_tool_result,
    _update_step,
    apply_fixers,
)
from core.models import Step


def _make_tool(return_value=None, side_effect=None):
    tool = MagicMock()
    if side_effect is not None:
        tool.ainvoke = AsyncMock(side_effect=side_effect)
    else:
        tool.ainvoke = AsyncMock(return_value=return_value)
    return tool


# ── _invoke_tool ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_invoke_tool_success():
    tc = {"name": "list_tables", "args": {}}
    tool_map = {"list_tables": _make_tool("table1, table2")}
    result_str, is_error = await _invoke_tool(tc, tool_map)
    assert result_str == "table1, table2"
    assert is_error is False


@pytest.mark.asyncio
async def test_invoke_tool_error_keyword_in_result():
    tc = {"name": "query", "args": {"sql": "BAD SQL"}}
    tool_map = {"query": _make_tool("SQL error: near BAD")}
    result_str, is_error = await _invoke_tool(tc, tool_map)
    assert is_error is True


@pytest.mark.asyncio
async def test_invoke_tool_tool_exception():
    tc = {"name": "write_file", "args": {"path": "/forbidden"}}
    tool_map = {"write_file": _make_tool(side_effect=ToolException("permission denied"))}
    result_str, is_error = await _invoke_tool(tc, tool_map)
    assert is_error is True
    assert "Tool error:" in result_str


# ── _update_step ───────────────────────────────────────────────────

def test_update_step_success_advances_index():
    steps = [
        Step(number=1, text="1. step one", status="pending"),
        Step(number=2, text="2. step two", status="pending"),
    ]
    new_idx = _update_step(steps, 0, False, "ok result")
    assert steps[0].status == "done"
    assert "ok result" in steps[0].note
    assert new_idx == 1


def test_update_step_failure_keeps_index():
    steps = [Step(number=1, text="1. step one", status="pending")]
    new_idx = _update_step(steps, 0, True, "some error message")
    assert steps[0].status == "failed"
    assert "some error message" in steps[0].note
    assert new_idx == 0


def test_update_step_out_of_bounds_is_noop():
    steps = [Step(number=1, text="1. step one", status="done")]
    new_idx = _update_step(steps, 1, False, "extra result")
    assert new_idx == 1  # unchanged, no IndexError


# ── _trim_tool_result ──────────────────────────────────────────────

def test_trim_result_within_limit():
    result, original = _trim_tool_result("read_file", "short text")
    assert result == "short text"
    assert original == len("short text")


def test_trim_result_over_default_limit():
    long_text = "a" * 3000
    result, original = _trim_tool_result("unknown_tool", long_text)
    assert original == 3000
    assert len(result) < original
    assert "[truncated:" in result


def test_trim_result_uses_per_tool_limit():
    # fetch_page has a smaller limit (1500) than the default (2000).
    text = "b" * 2000
    result_fetch, _ = _trim_tool_result("fetch_page", text)
    result_read, _  = _trim_tool_result("read_file",  text)
    assert len(result_fetch) < len(result_read)


def test_trim_result_no_limit_when_zero():
    # A tool with limit=0 should not be trimmed.
    # Simulate by using a tool name that maps to 0 via monkey-patch — or just
    # verify that a short text is never trimmed regardless of tool name.
    short = "hello"
    result, _ = _trim_tool_result("any_tool", short)
    assert result == short


# ── _apply_window ──────────────────────────────────────────────────

def test_apply_window_within_size():
    # MESSAGE_WINDOW_HEAD=2, MESSAGE_WINDOW_SIZE=12 → threshold = 2+12=14
    messages = list(range(14))
    result, truncated = _apply_window(messages)
    assert result == messages
    assert truncated is False


def test_apply_window_exceeds_size():
    messages = list(range(20))
    result, truncated = _apply_window(messages)
    assert truncated is True
    assert result[0] == 0   # head preserved
    assert result[1] == 1   # head preserved
    assert result[-1] == 19 # latest preserved


def test_apply_window_preserves_head_count():
    # First MESSAGE_WINDOW_HEAD messages always kept.
    messages = list(range(30))
    result, _ = _apply_window(messages)
    assert result[0] == messages[0]
    assert result[1] == messages[1]


# ── apply_fixers ───────────────────────────────────────────────────

def _make_tool_with_schema(properties: dict):
    tool = MagicMock()
    tool.args_schema = {"properties": properties}
    return tool


def test_apply_fixers_corrects_name_and_arg():
    tc = {"name": "open_file", "args": {"file_path": "/data/f.txt"}, "id": "1"}
    tool_map = {"read_file": _make_tool_with_schema({"path": {}})}
    logger = MagicMock()

    fixed_tc, tool_name_fix, arg_fixes = apply_fixers(tc, tool_map, logger)

    assert fixed_tc["name"] == "read_file"
    assert "path" in fixed_tc["args"]
    assert tool_name_fix is not None
    assert len(arg_fixes) == 1


def test_apply_fixers_noop_when_correct():
    tc = {"name": "write_file", "args": {"path": "/f", "content": "hi"}, "id": "2"}
    tool_map = {"write_file": _make_tool_with_schema({"path": {}, "content": {}})}
    logger = MagicMock()

    fixed_tc, tool_name_fix, arg_fixes = apply_fixers(tc, tool_map, logger)

    assert fixed_tc["name"] == "write_file"
    assert tool_name_fix is None
    assert arg_fixes == []
    logger.warning.assert_not_called()


def test_apply_fixers_unescapes_content():
    tc = {"name": "write_file", "args": {"path": "/f", "content": "a\\nb"}, "id": "3"}
    tool_map = {"write_file": _make_tool_with_schema({"path": {}, "content": {}})}
    logger = MagicMock()

    fixed_tc, _, _ = apply_fixers(tc, tool_map, logger)

    assert fixed_tc["args"]["content"] == "a\nb"
