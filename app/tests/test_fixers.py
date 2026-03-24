import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.base.fixers import (
    _fix_args,
    _fix_content,
    _fix_tool_name,
    correct_tool_name,
    fix_plan_tool_names,
)
from core.models import Step


def _make_tool_with_schema(properties: dict):
    tool = MagicMock()
    tool.args_schema = {"properties": properties}
    return tool


# ── correct_tool_name ─────────────────────────────────────────────

def test_correct_tool_name_already_correct():
    tool_map = {"read_file": MagicMock(), "write_file": MagicMock()}
    name, fix = correct_tool_name("read_file", tool_map)
    assert name == "read_file"
    assert fix is None


def test_correct_tool_name_alias():
    tool_map = {"read_file": MagicMock()}
    name, fix = correct_tool_name("open_file", tool_map)
    assert name == "read_file"
    assert fix is not None


def test_correct_tool_name_fuzzy():
    tool_map = {"execute_command": MagicMock()}
    name, fix = correct_tool_name("execute_comand", tool_map)  # one-char typo
    assert name == "execute_command"
    assert fix is not None


def test_correct_tool_name_unknown_unchanged():
    tool_map = {"read_file": MagicMock()}
    name, fix = correct_tool_name("completely_unknown_xyz_123", tool_map)
    assert name == "completely_unknown_xyz_123"
    assert fix is None


# ── _fix_tool_name ────────────────────────────────────────────────

def test_fix_tool_name_corrects_alias():
    tc = {"name": "open_file", "args": {}}
    tool_map = {"read_file": MagicMock()}
    fixed_tc, fix = _fix_tool_name(tc, tool_map)
    assert fixed_tc["name"] == "read_file"
    assert fix is not None


def test_fix_tool_name_noop_when_correct():
    tc = {"name": "write_file", "args": {}}
    tool_map = {"write_file": MagicMock()}
    fixed_tc, fix = _fix_tool_name(tc, tool_map)
    assert fixed_tc["name"] == "write_file"
    assert fix is None


def test_fix_tool_name_preserves_other_fields():
    tc = {"name": "save_file", "args": {"path": "/f"}, "id": "abc"}
    tool_map = {"write_file": MagicMock()}
    fixed_tc, _ = _fix_tool_name(tc, tool_map)
    assert fixed_tc["args"] == {"path": "/f"}
    assert fixed_tc["id"] == "abc"


# ── fix_plan_tool_names ───────────────────────────────────────────

def test_fix_plan_tool_names_corrects_step():
    steps = [Step(number=1, text="1. open_file: read something", status="pending")]
    tool_map = {"read_file": MagicMock()}
    fixed, fixes = fix_plan_tool_names(steps, tool_map)
    assert fixed[0].text == "1. read_file: read something"
    assert len(fixes) == 1


def test_fix_plan_tool_names_noop_when_correct():
    steps = [Step(number=1, text="1. read_file: read something", status="pending")]
    tool_map = {"read_file": MagicMock()}
    fixed, fixes = fix_plan_tool_names(steps, tool_map)
    assert fixed[0].text == "1. read_file: read something"
    assert fixes == []


def test_fix_plan_tool_names_preserves_status_and_note():
    steps = [Step(number=1, text="1. save_file: save it", status="done", note="ok")]
    tool_map = {"write_file": MagicMock()}
    fixed, _ = fix_plan_tool_names(steps, tool_map)
    assert fixed[0].status == "done"
    assert fixed[0].note == "ok"


def test_fix_plan_tool_names_multiple_steps():
    steps = [
        Step(number=1, text="1. open_file: read it", status="pending"),
        Step(number=2, text="2. write_file: write it", status="pending"),
        Step(number=3, text="3. save_file: save it", status="pending"),
    ]
    tool_map = {"read_file": MagicMock(), "write_file": MagicMock()}
    fixed, fixes = fix_plan_tool_names(steps, tool_map)
    assert fixed[0].text == "1. read_file: read it"
    assert fixed[1].text == "2. write_file: write it"   # already correct
    assert fixed[2].text == "3. write_file: save it"    # save_file → write_file
    assert len(fixes) == 2


# ── _fix_args ─────────────────────────────────────────────────────

def test_fix_args_noop_when_correct():
    tc = {"name": "read_file", "args": {"path": "/data/file.txt"}}
    tool_map = {"read_file": _make_tool_with_schema({"path": {}})}
    fixed_tc, fixes = _fix_args(tc, tool_map)
    assert fixed_tc["args"] == {"path": "/data/file.txt"}
    assert fixes == []


def test_fix_args_alias():
    tc = {"name": "read_file", "args": {"file_path": "/data/file.txt"}}
    tool_map = {"read_file": _make_tool_with_schema({"path": {}})}
    fixed_tc, fixes = _fix_args(tc, tool_map)
    assert "path" in fixed_tc["args"]
    assert "file_path" not in fixed_tc["args"]
    assert len(fixes) == 1


def test_fix_args_fuzzy():
    tc = {"name": "execute_command", "args": {"comand": "ls"}}  # typo
    tool_map = {"execute_command": _make_tool_with_schema({"command": {}})}
    fixed_tc, fixes = _fix_args(tc, tool_map)
    assert "command" in fixed_tc["args"]
    assert len(fixes) == 1


def test_fix_args_unknown_key_preserved():
    # Unrecognized args that don't match anything are kept as-is.
    tc = {"name": "read_file", "args": {"zzz_unknown": "val"}}
    tool_map = {"read_file": _make_tool_with_schema({"path": {}})}
    fixed_tc, fixes = _fix_args(tc, tool_map)
    assert "zzz_unknown" in fixed_tc["args"]
    assert fixes == []


def test_fix_args_unknown_tool_noop():
    tc = {"name": "ghost_tool", "args": {"x": 1}}
    fixed_tc, fixes = _fix_args(tc, {})
    assert fixed_tc["args"] == {"x": 1}
    assert fixes == []


def test_fix_args_pydantic_schema():
    # Also supports Pydantic-backed tools (model_fields attribute).
    tc = {"name": "some_tool", "args": {"file_path": "/f"}}
    schema = MagicMock()
    schema.model_fields = {"path": MagicMock()}
    tool = MagicMock()
    tool.args_schema = schema
    tool_map = {"some_tool": tool}
    fixed_tc, fixes = _fix_args(tc, tool_map)
    assert "path" in fixed_tc["args"]
    assert len(fixes) == 1


# ── _fix_content ──────────────────────────────────────────────────

def test_fix_content_unescapes_newlines():
    tc = {"name": "write_file", "args": {"content": "line1\\nline2", "path": "/f"}}
    fixed_tc, fix = _fix_content(tc)
    assert fixed_tc["args"]["content"] == "line1\nline2"
    assert fix is not None


def test_fix_content_unescapes_tabs():
    tc = {"name": "write_file", "args": {"content": "col1\\tcol2", "path": "/f"}}
    fixed_tc, fix = _fix_content(tc)
    assert fixed_tc["args"]["content"] == "col1\tcol2"
    assert fix is not None


def test_fix_content_noop_for_other_tools():
    tc = {"name": "read_file", "args": {"path": "/f"}}
    fixed_tc, fix = _fix_content(tc)
    assert fixed_tc == tc
    assert fix is None


def test_fix_content_noop_when_no_backslash():
    tc = {"name": "write_file", "args": {"content": "already\nfine", "path": "/f"}}
    fixed_tc, fix = _fix_content(tc)
    assert fix is None
    assert fixed_tc["args"]["content"] == "already\nfine"
