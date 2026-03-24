"""Tool-call correction utilities.

Corrects hallucinated tool names and argument names emitted by small open-weight
models before the tool is actually invoked.  All functions are pure / stateless
and operate only on the tool-call dict and the tool_map.

Shared core
-----------
correct_tool_name(name, tool_map)
    Alias table + difflib fuzzy → used by both exec-time _fix_tool_name
    and plan-time fix_plan_tool_names.  Add new aliases here once and both
    paths benefit automatically.
"""

import difflib
import re

# ---------------------------------------------------------------------------
# Tool name correction
# ---------------------------------------------------------------------------

# Mapping of commonly hallucinated tool names → correct MCP tool names.
# Observed across llama3.2:3b, mistral and other small open-weight models.
_TOOL_NAME_ALIAS: dict[str, str] = {
    # filesystem — read
    "read_text_file":            "read_file",
    "read_file_content":         "read_file",
    "open_file":                 "read_file",
    "get_file_content":          "read_file",
    # filesystem — write  (edit/modify/update all mean "write")
    "write_text_file":           "write_file",
    "write_to_file":             "write_file",
    "create_file":               "write_file",
    "save_file":                 "write_file",
    "edit_file":                 "write_file",
    "modify_file":               "write_file",
    "update_file":               "write_file",
    "append_file":               "write_file",
    "overwrite_file":            "write_file",
    # filesystem — directory
    "list_files":                "list_directory",
    "list_dir":                  "list_directory",
    "list_directory_with_sizes": "list_directory",
    "ls":                        "list_directory",
    "delete_file":               "remove_file",
    # shell
    "run_command":               "execute_command",
    "run_shell":                 "execute_command",
    "shell_execute":             "execute_command",
    "bash":                      "execute_command",
    "exec":                      "execute_command",
    "execute":                   "execute_command",
    "run_bash":                  "execute_command",
    "run_python":                "execute_command",
    # websearch
    "search_web":                "web_search",
    "internet_search":           "web_search",
    "browse_web":                "web_search",
    "get_page":                  "fetch_page",
    "fetch_url":                 "fetch_page",
    "open_url":                  "fetch_page",
    "browse_url":                "fetch_page",
    # time
    "current_time":              "get_current_datetime",
    "get_time":                  "get_current_datetime",
    "get_datetime":              "get_current_datetime",
    "now":                       "get_current_datetime",
    # sqlite
    "sql_query":                 "query",
    "execute_sql":               "query",
    "run_sql":                   "query",
    # memory
    "store_memory":              "remember",
    "save_memory":               "remember",
    "get_memory":                "recall",
    "retrieve_memory":           "recall",
    "delete_memory":             "forget",
    "remove_memory":             "forget",
}

# Minimum similarity ratio accepted by difflib fuzzy fallback.
# 0.80 is intentionally conservative to avoid mis-corrections.
_FUZZY_CUTOFF = 0.80


def correct_tool_name(name: str, tool_map: dict) -> tuple[str, str | None]:
    """Shared core: alias table lookup + difflib fuzzy match.

    Returns (corrected_name, fix_description) where fix_description is None
    when no correction was needed.  Used by both exec-time _fix_tool_name and
    plan-time fix_plan_tool_names — add new aliases to _TOOL_NAME_ALIAS once
    and both paths benefit automatically.
    """
    if name in tool_map:
        return name, None

    if name in _TOOL_NAME_ALIAS:
        corrected = _TOOL_NAME_ALIAS[name]
        if corrected in tool_map:
            return corrected, f"{name} → {corrected}"

    candidates = difflib.get_close_matches(name, tool_map.keys(), n=1, cutoff=_FUZZY_CUTOFF)
    if candidates:
        return candidates[0], f"{name} ~> {candidates[0]}"

    return name, None


def _fix_tool_name(tc: dict, tool_map: dict) -> tuple[dict, str | None]:
    """Exec-time wrapper: correct hallucinated tool name in a tool-call dict."""
    corrected, fix = correct_tool_name(tc["name"], tool_map)
    if fix:
        return {**tc, "name": corrected}, fix
    return tc, None


# Pattern matching "N. tool_name: description" step format.
_STEP_TOOL_RE = re.compile(r'^(\d+\.\s*)([A-Za-z_]\w*)(\s*:.*)', re.DOTALL)


def fix_plan_tool_names(
    steps: list, tool_map: dict
) -> tuple[list, list[str]]:
    """Plan-time: correct hallucinated tool names in Step.text fields.

    Applies the same correction logic as _fix_tool_name so plan steps and
    exec calls are always consistent.  Steps without a recognised tool-name
    prefix are left unchanged.

    Returns (fixed_steps, list_of_fix_descriptions).
    """
    from core.models import Step  # local import to avoid circular dependency

    fixed: list[Step] = []
    fixes: list[str] = []

    for step in steps:
        m = _STEP_TOOL_RE.match(step.text)
        if m:
            prefix, tool_name, rest = m.groups()
            corrected, fix = correct_tool_name(tool_name, tool_map)
            if fix:
                new_text = f"{prefix}{corrected}{rest}"
                fixed.append(Step(
                    number=step.number, text=new_text,
                    status=step.status, note=step.note,
                ))
                fixes.append(f"step {step.number}: {fix}")
                continue
        fixed.append(step)

    return fixed, fixes


# ---------------------------------------------------------------------------
# Argument name correction
# ---------------------------------------------------------------------------

# Alias table for arg names that fuzzy matching alone cannot catch
# (short abbreviations, semantically shifted names, etc.).
_ARG_ALIAS: dict[str, str] = {
    "cmd":          "command",
    "shell_cmd":    "command",
    "sh":           "shell",
    "dir":          "cwd",
    "working_dir":  "cwd",
    "workdir":      "cwd",
    "file":         "path",
    "filepath":     "path",
    "filename":     "path",
    "file_path":    "path",
    "text":         "content",
    "value":        "content",
    "body":         "content",
    "data":         "content",
    "q":            "query",
    "search":       "query",
    "sql_query":    "sql",
    "statement":    "sql",
    "url":          "uri",
    "link":         "uri",
}

_ARG_FUZZY_CUTOFF = 0.75


def _fix_args(tc: dict, tool_map: dict) -> tuple[dict, list[str]]:
    """Normalize argument names to match the tool's declared schema.

    Correction order:
    1. Key already correct → keep.
    2. Alias table lookup  → deterministic, handles short/semantic differences.
    3. difflib fuzzy match against schema keys → catches near-misses not in table.

    Handles both Pydantic-backed LangChain tools (args_schema.model_fields)
    and MCP tools that expose a raw JSON Schema dict (args_schema["properties"]).
    """
    tool = tool_map.get(tc["name"])
    if tool is None:
        return tc, []

    schema = tool.args_schema
    if isinstance(schema, dict):
        expected_keys: set[str] = set(schema.get("properties", {}).keys())
    elif hasattr(schema, "model_fields"):
        expected_keys = set(schema.model_fields.keys())
    else:
        return tc, []

    new_args: dict = {}
    fixes: list[str] = []

    for k, v in tc["args"].items():
        if k in expected_keys:
            new_args[k] = v
        elif k in _ARG_ALIAS and _ARG_ALIAS[k] in expected_keys:
            correct = _ARG_ALIAS[k]
            new_args[correct] = v
            fixes.append(f"{k} → {correct}")
        else:
            candidates = difflib.get_close_matches(
                k, expected_keys, n=1, cutoff=_ARG_FUZZY_CUTOFF
            )
            if candidates:
                correct = candidates[0]
                new_args[correct] = v
                fixes.append(f"{k} ~> {correct}")
            else:
                new_args[k] = v

    return {**tc, "args": new_args}, fixes


# ---------------------------------------------------------------------------
# Content fixer
# ---------------------------------------------------------------------------

def _fix_content(tc: dict) -> tuple[dict, str | None]:
    """In write_file calls, convert literal \\n / \\t escape sequences to actual
    characters.  Small models often emit JSON with double-escaped newlines
    (e.g. "content": "line1\\nline2") which produce a SyntaxError when the
    string is written verbatim to a Python file.
    """
    if tc["name"] != "write_file":
        return tc, None
    content = tc["args"].get("content", "")
    if "\\" not in content:
        return tc, None
    fixed = content.replace("\\n", "\n").replace("\\t", "\t")
    if fixed == content:
        return tc, None
    return {**tc, "args": {**tc["args"], "content": fixed}}, "\\n/\\t → actual chars in content"
