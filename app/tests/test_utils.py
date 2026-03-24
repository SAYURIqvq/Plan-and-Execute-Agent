import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.models import Step
from core.utils import _sanitize, _task_message, _tool_descriptions


def test_sanitize_removes_tool_call_tags():
    text = "before<tool_call>some content</tool_call>after"
    assert _sanitize(text) == "beforeafter"


def test_sanitize_removes_tool_call_tags_multiline():
    text = 'line1\n<tool_call>\n{"name": "foo"}\n</tool_call>\nline2'
    result = _sanitize(text)
    assert "<tool_call>" not in result
    assert "line1" in result
    assert "line2" in result


def test_sanitize_removes_json_name_lines():
    text = 'normal line\n  {"name": "some_tool", "args": {}}\nanother line'
    result = _sanitize(text)
    assert '{"name":' not in result
    assert "normal line" in result
    assert "another line" in result


def test_sanitize_passthrough():
    text = "This is a normal response."
    assert _sanitize(text) == text


def test_tool_descriptions():
    tools = [
        SimpleNamespace(name="tool_a", description="does A"),
        SimpleNamespace(name="tool_b", description="does B"),
    ]
    result = _tool_descriptions(tools)
    assert "- tool_a: does A" in result
    assert "- tool_b: does B" in result


def test_task_message_pending_count():
    steps = [
        Step(number=1, text="1. step one", status="done"),
        Step(number=2, text="2. step two", status="pending"),
        Step(number=3, text="3. step three", status="pending"),
    ]
    msg = _task_message("do the task", steps)
    assert "2 steps remaining" in msg
    assert "do the task" in msg
