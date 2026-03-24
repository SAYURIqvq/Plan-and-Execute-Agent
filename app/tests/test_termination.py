import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.base.termination import (
    FINISH_TOOL_NAME,
    FinishToolTermination,
    TextTermination,
    get_termination_strategy,
)


def _make_response(content="", tool_calls=None):
    r = MagicMock()
    r.content = content
    r.tool_calls = tool_calls or []
    return r


# ── TextTermination ───────────────────────────────────────────────

def test_text_termination_stops_on_text_response():
    strategy = TextTermination()
    response = _make_response(content="final answer", tool_calls=[])
    result = strategy.check(response)
    assert result.should_stop is True
    assert result.answer == "final answer"


def test_text_termination_continues_on_tool_call():
    strategy = TextTermination()
    response = _make_response(tool_calls=[{"name": "read_file", "args": {}}])
    result = strategy.check(response)
    assert result.should_stop is False
    assert result.feedback is None


def test_text_termination_has_no_extra_tools():
    assert TextTermination().extra_tools == []


# ── FinishToolTermination ─────────────────────────────────────────

def test_finish_tool_terminates_on_finish_call():
    strategy = FinishToolTermination()
    response = _make_response(
        tool_calls=[{"name": FINISH_TOOL_NAME, "args": {"summary": "all done"}}]
    )
    result = strategy.check(response)
    assert result.should_stop is True
    assert result.answer == "all done"


def test_finish_tool_terminates_with_empty_summary():
    strategy = FinishToolTermination()
    response = _make_response(
        tool_calls=[{"name": FINISH_TOOL_NAME, "args": {}}]
    )
    result = strategy.check(response)
    assert result.should_stop is True
    assert result.answer == ""


def test_finish_tool_continues_on_other_tool():
    strategy = FinishToolTermination()
    response = _make_response(tool_calls=[{"name": "read_file", "args": {}}])
    result = strategy.check(response)
    assert result.should_stop is False
    assert result.feedback is None


def test_finish_tool_injects_feedback_on_text_only():
    strategy = FinishToolTermination()
    response = _make_response(content="I will do this next...", tool_calls=[])
    result = strategy.check(response)
    assert result.should_stop is False
    assert result.feedback is not None
    assert len(result.feedback) > 0


def test_finish_tool_registers_one_extra_tool():
    strategy = FinishToolTermination()
    assert len(strategy.extra_tools) == 1
    assert strategy.extra_tools[0].name == FINISH_TOOL_NAME


# ── get_termination_strategy (factory) ───────────────────────────

def test_factory_returns_text_strategy():
    assert isinstance(get_termination_strategy("text"), TextTermination)


def test_factory_returns_finish_tool_strategy():
    assert isinstance(get_termination_strategy("finish_tool"), FinishToolTermination)


def test_factory_raises_on_unknown_name():
    with pytest.raises(ValueError, match="Unknown termination strategy"):
        get_termination_strategy("nonexistent")


def test_factory_returns_new_instance_each_call():
    s1 = get_termination_strategy("finish_tool")
    s2 = get_termination_strategy("finish_tool")
    assert s1 is not s2
