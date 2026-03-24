import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.models import Step
from agent.components.planner import _apply_replan, gather_current_state, make_plan_steps


def _make_tool(return_value=None, side_effect=None):
    tool = MagicMock()
    if side_effect is not None:
        tool.ainvoke = AsyncMock(side_effect=side_effect)
    else:
        tool.ainvoke = AsyncMock(return_value=return_value)
    return tool


@pytest.mark.asyncio
async def test_gather_current_state_all_ok():
    tool_map = {
        "list_tables":    _make_tool("table1, table2"),
        "list_directory": _make_tool("file1.txt"),
        "list_memories":  _make_tool("key=value"),
    }
    result = await gather_current_state(tool_map)
    assert "SQLite tables" in result
    assert "table1, table2" in result
    assert "Files in /data" in result
    assert "file1.txt" in result
    assert "Stored memories" in result
    assert "key=value" in result
    tool_map["list_tables"].ainvoke.assert_called_once_with({})
    tool_map["list_directory"].ainvoke.assert_called_once_with({"path": "/data"})
    tool_map["list_memories"].ainvoke.assert_called_once_with({})


@pytest.mark.asyncio
async def test_gather_current_state_missing_tool():
    tool_map = {
        "list_tables": _make_tool("table1"),
        # list_directory and list_memories are absent
    }
    result = await gather_current_state(tool_map)
    assert "SQLite tables" in result
    assert "Files in /data" not in result
    assert "Stored memories" not in result


@pytest.mark.asyncio
async def test_gather_current_state_list_tables_error_is_silent():
    # list_tables failure is silently swallowed; other tools still populate.
    tool_map = {
        "list_tables":    _make_tool(side_effect=Exception("db unavailable")),
        "list_directory": _make_tool("file.txt"),
        "list_memories":  _make_tool("mem"),
    }
    result = await gather_current_state(tool_map)
    assert "SQLite tables" not in result          # tables section absent on error
    assert "file.txt" in result                   # directory listing still present
    assert "mem" in result                        # memories still present


@pytest.mark.asyncio
async def test_gather_current_state_parallel_tool_error():
    # Errors in parallel tools (list_directory, list_memories) are reported inline.
    tool_map = {
        "list_directory": _make_tool(side_effect=Exception("no access")),
        "list_memories":  _make_tool("mem"),
    }
    result = await gather_current_state(tool_map)
    assert "(error: no access)" in result
    assert "mem" in result


@pytest.mark.asyncio
async def test_make_plan_steps_returns_parsed_steps():
    # Prompt without filesystem keywords → state gathering skipped.
    plan_text = "1. do something\n2. verify result"
    model = MagicMock()
    model.ainvoke = AsyncMock(return_value=MagicMock(content=plan_text))
    logger = MagicMock()

    steps = await make_plan_steps("do task", [], {}, model, logger)

    assert len(steps) == 2
    assert steps[0].text == "1. do something"
    assert steps[1].text == "2. verify result"
    assert all(s.status == "pending" for s in steps)


@pytest.mark.asyncio
async def test_make_plan_steps_fixes_tool_names():
    plan_text = "1. open_file: read the config"
    model = MagicMock()
    model.ainvoke = AsyncMock(return_value=MagicMock(content=plan_text))
    tool_map = {"read_file": MagicMock()}
    logger = MagicMock()

    steps = await make_plan_steps("do task", [], tool_map, model, logger)

    assert steps[0].text == "1. read_file: read the config"
    logger.warning.assert_called()   # fix was logged


@pytest.mark.asyncio
async def test_apply_replan_merges_done_steps():
    done_step = Step(number=1, text="1. already done", status="done", note="ok")
    failed_step = Step(number=2, text="2. failed step", status="failed", note="err")
    pending_step = Step(number=3, text="3. pending step", status="pending")
    existing_steps = [done_step, failed_step, pending_step]

    new_plan_text = "1. revised step A\n2. revised step B"
    model = MagicMock()
    model.ainvoke = AsyncMock(return_value=MagicMock(content=new_plan_text))
    tools = []
    logger = MagicMock()

    merged, new_idx = await _apply_replan(
        "do task", existing_steps, [], tools, model, logger
    )

    # done_steps (1) + new_steps (2) = 3 total
    assert len(merged) == 3
    # first entry is the done step carried over
    assert merged[0].status == "done"
    assert merged[0].text == "1. already done"
    # new index equals the number of done steps
    assert new_idx == 1
    # new steps follow
    assert merged[1].text == "1. revised step A"
    assert merged[2].text == "2. revised step B"
