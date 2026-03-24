import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.models import Step, format_checklist, parse_steps


def test_parse_steps_basic():
    steps = parse_steps("1. foo\n2. bar")
    assert len(steps) == 2
    assert steps[0].number == 1
    assert steps[0].text == "1. foo"
    assert steps[1].number == 2
    assert steps[1].text == "2. bar"


def test_parse_steps_empty():
    assert parse_steps("") == []


def test_parse_steps_ignores_non_numbered():
    steps = parse_steps("1. first\nsome text\n- bullet\n2. second")
    assert len(steps) == 2
    assert steps[0].number == 1
    assert steps[1].number == 2


def test_format_checklist_pending():
    steps = [Step(number=1, text="1. do something", status="pending")]
    result = format_checklist(steps)
    assert result.startswith("⏳")
    assert "1. do something" in result


def test_format_checklist_done():
    steps = [Step(number=1, text="1. done step", status="done")]
    result = format_checklist(steps)
    assert result.startswith("✅")


def test_format_checklist_failed_with_note():
    steps = [Step(number=1, text="1. failed step", status="failed", note="some error")]
    result = format_checklist(steps)
    assert result.startswith("❌")
    assert "→ some error" in result


def test_format_checklist_mixed():
    steps = [
        Step(number=1, text="1. step one", status="done"),
        Step(number=2, text="2. step two", status="failed", note="err"),
        Step(number=3, text="3. step three", status="pending"),
    ]
    lines = format_checklist(steps).splitlines()
    assert len(lines) == 3
    assert lines[0].startswith("✅")
    assert lines[1].startswith("❌")
    assert lines[2].startswith("⏳")
