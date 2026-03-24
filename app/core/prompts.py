# ── Sentence fragments ──────────────────────────────────────────────────────
# Atomic prompt sentences reused across prompt types and variants.
# Each value is a single self-contained instruction.

SENTENCES: dict[str, str] = {
    # Language (English/Japanese variants)
    "lang_jp":          "[CRITICAL] You MUST respond ONLY in Japanese. NEVER output Chinese characters.",
    "lang_plan":        "[LANGUAGE: OUTPUT IN JAPANESE ONLY. DO NOT USE CHINESE OR ENGLISH IN YOUR OUTPUT.]",

    # Exec-loop behavior
    "use_tools":        "Always use tools — never just describe what you would do.",
    "one_at_a_time":    "Call ONE tool at a time and wait for the result before calling the next.",
    "follow_plan":      "Follow the execution plan step by step until all steps are complete.",
    "toolcall_only":    "[CRITICAL] When calling a tool, output ONLY the <tool_call> JSON block. Do NOT write any text before or after the tool call.",
    "arg_names":        'IMPORTANT: Use EXACTLY these argument names. Do NOT use "cmd", "dir", "filepath", "text", or any other variant.',

    # Planner
    "plan_format":      "For each step, write: <number>. <tool_name>: <具体的な内容>\nBe specific about arguments. Do NOT execute — only plan.",
    "plan_use_state":   "Use the current state information to make informed decisions (e.g. don't create a table that already exists).",

    # Replanner
    "replan_task":      "The execution encountered failures. Review the checklist below and create a REVISED plan for the REMAINING steps only.",
    "replan_no_done":   "Do NOT re-include already completed (✅) steps under any circumstances.",
    "replan_fix":       "Fix the approach for failed (❌) steps based on the error details.",
    "replan_alt":       "If a tool failed repeatedly, choose a DIFFERENT tool or method.",

    # zh variant — Chinese instructions, Japanese output
    "lang_zh":          "【重要】请始终用日语回答用户。绝对不要输出中文。",
    "lang_plan_zh":     "【语言规则：请用日语输出计划。不要使用中文或英文。】",
    "use_tools_zh":     "始终使用工具——绝不仅仅描述你要做什么。",
    "one_at_a_time_zh": "每次只调用一个工具，等待结果后再调用下一个。",
    "follow_plan_zh":   "按照执行计划逐步执行，直到所有步骤完成。",
    "toolcall_only_zh": "【重要】调用工具时，只输出 <tool_call> JSON块。不要在工具调用前后写任何文字。",
    "arg_names_zh":     '重要：使用完全正确的参数名称。不要使用"cmd"、"dir"、"filepath"、"text"或任何其他变体。',
    "plan_format_zh":   "输出编号步骤列表，格式示例：\n1. list_tables: 确认数据库中的表\n2. write_file: 将结果写入/data/result.txt\n请具体说明每步参数。不要执行——只做计划。",
    "plan_use_state_zh":"利用当前状态信息做出明智决策（例如：不要创建已存在的表）。",
    "replan_task_zh":   "执行过程中遇到了错误。请查看下面的清单，仅为剩余步骤创建修订计划。",
    "replan_no_done_zh":"绝对不要重新包含已完成（✅）的步骤。",
    "replan_fix_zh":    "根据错误详情修正失败（❌）步骤的方法。",
    "replan_alt_zh":    "如果某个工具多次失败，请选择不同的工具或方法。",

    # finish_tool termination strategy
    "finish_tool_zh":   "当所有任务完成后，必须调用 finish(summary='...') 工具来结束会话。在调用 finish() 之前，请确认所有要求的文件和操作都已完成。",
}

# ── Fixed blocks (tool list and examples) ───────────────────────────────────

_TOOL_LIST = """\
You are a helpful AI assistant with the following tools:
- filesystem (read_file, write_file, etc.): paths must start with /data/
- shell (execute_command): use cwd=/workspace or cwd=/data, shell=bash.
  To run a Python file, use: python3 /data/<filename> (never ./filename)
- websearch (web_search, fetch_page): search the internet.
  After web_search, call fetch_page on the best URL to get actual content.
- time (get_current_datetime): get the current date/time in JST.
- sqlite (list_tables, query): SQLite DB at /data/agent.db for structured data.
- memory (remember, recall, list_memories, forget): persist key-value notes across sessions. Do NOT use as a substitute for write_file — always save task outputs to /data/ files."""

_TOOL_LIST_ZH = """\
你是一个有用的AI助手，拥有以下工具：
- 文件系统 (read_file, write_file等)：路径必须以 /data/ 开头。
- Shell (execute_command)：使用 cwd=/workspace 或 cwd=/data，shell=bash。
  运行Python文件时，使用：python3 /data/<文件名>（不要用 ./文件名）。
- 网络搜索 (web_search, fetch_page)：搜索互联网。
  web_search后，对最佳URL调用fetch_page获取实际内容。
- 时间 (get_current_datetime)：获取日本标准时间（JST）的当前日期/时间。
- SQLite (list_tables, query)：/data/agent.db 中的SQLite数据库，用于结构化数据。
- 内存 (remember, recall, list_memories, forget)：在会话间持久化键值笔记。不要用来代替 write_file——任务输出必须保存到 /data/ 文件。"""

_TOOL_EXAMPLES = """\
## Tool call examples (correct argument names)

Example 1 — Run a shell command:
<tool_call>
{"name": "execute_command", "arguments": {"command": "python3 /data/test.py", "cwd": "/data", "shell": "bash"}}
</tool_call>

Example 2 — Write a file:
<tool_call>
{"name": "write_file", "arguments": {"path": "/data/hello.py", "content": "print('hello')"}}
</tool_call>"""

# ── System prompt variant definitions ───────────────────────────────────────
# "rules":    ordered SENTENCES keys → assembled into numbered Rules: block
# "examples": bool → include _TOOL_EXAMPLES
# "footer":   SENTENCES keys appended after examples (unnumbered)

_SYSTEM_VARIANTS: dict[str, dict] = {
    # Baseline: current behaviour
    "default": {
        "rules":    ["lang_jp", "use_tools", "one_at_a_time", "follow_plan"],
        "examples": True,
        "footer":   ["arg_names"],
    },
    # v1: add explicit "output ONLY <tool_call>" rule, drop examples
    "v1": {
        "rules":    ["lang_jp", "toolcall_only", "use_tools", "one_at_a_time", "follow_plan"],
        "examples": False,
        "footer":   ["arg_names"],
    },
    # v2: strict toolcall + keep examples for argument-name guidance
    "v2": {
        "rules":    ["lang_jp", "toolcall_only", "use_tools", "one_at_a_time", "follow_plan"],
        "examples": True,
        "footer":   ["arg_names"],
    },
    # zh: Chinese instructions → better instruction-following for qwen2.5 small models
    #     Output is still Japanese (lang_zh rule enforces it)
    "zh": {
        "tool_list": _TOOL_LIST_ZH,
        "rules":    ["lang_zh", "use_tools_zh", "one_at_a_time_zh", "follow_plan_zh"],
        "examples": True,
        "footer":   ["arg_names_zh"],
    },
    # react: ReAct mode (no follow_plan — there is no pre-built plan to follow)
    "react": {
        "rules":    ["lang_jp", "use_tools", "one_at_a_time"],
        "examples": True,
        "footer":   ["arg_names"],
    },
    # react_zh: ReAct mode with Chinese instructions
    "react_zh": {
        "tool_list": _TOOL_LIST_ZH,
        "rules":    ["lang_zh", "use_tools_zh", "one_at_a_time_zh"],
        "examples": True,
        "footer":   ["arg_names_zh"],
    },
    # react_zh_finish: react_zh + finish() tool termination instruction
    "react_zh_finish": {
        "tool_list": _TOOL_LIST_ZH,
        "rules":    ["lang_zh", "use_tools_zh", "one_at_a_time_zh"],
        "examples": True,
        "footer":   ["arg_names_zh", "finish_tool_zh"],
    },
}


def build_system_prompt(variant: str = "default") -> str:
    cfg = _SYSTEM_VARIANTS.get(variant, _SYSTEM_VARIANTS["default"])
    tool_list = cfg.get("tool_list", _TOOL_LIST)
    header = "规则：" if "zh" in variant else "Rules:"
    parts = [tool_list, header]
    for i, key in enumerate(cfg["rules"], 1):
        parts.append(f"{i}. {SENTENCES[key]}")
    if cfg.get("examples"):
        parts.append(_TOOL_EXAMPLES)
    for key in cfg.get("footer", []):
        parts.append(SENTENCES[key])
    return "\n".join(parts)


def build_plan_prompt(variant: str = "default") -> str:
    s = SENTENCES
    if variant == "zh":
        return (
            s["lang_plan_zh"] + "\n\n"
            "你是一个任务规划师。根据用户请求、当前系统状态和可用工具，输出具体的编号执行计划。\n"
            + s["plan_format_zh"] + "\n"
            + s["plan_use_state_zh"] + "\n\n"
            "当前系统状态：\n{current_state}\n\n"
            "可用工具：\n{tool_descriptions}"
        )
    return (
        s["lang_plan"] + "\n\n"
        "You are a task planner. Given a user request, the current system state, "
        "and available tools, output a concrete numbered execution plan.\n"
        + s["plan_format"] + "\n"
        + s["plan_use_state"] + "\n\n"
        "Current system state:\n{current_state}\n\n"
        "Available tools:\n{tool_descriptions}"
    )


def build_replan_prompt(variant: str = "default") -> str:
    s = SENTENCES
    if variant == "zh":
        rules = [s["replan_no_done_zh"], s["replan_fix_zh"], s["replan_alt_zh"]]
        return (
            s["lang_plan_zh"] + "\n\n"
            "你是一个任务规划师。" + s["replan_task_zh"] + "\n"
            "绝对规则：\n"
            + "\n".join(f"- {r}" for r in rules) + "\n\n"
            "可用工具：\n{tool_descriptions}"
        )
    rules = [s["replan_no_done"], s["replan_fix"], s["replan_alt"]]
    return (
        s["lang_plan"] + "\n\n"
        "You are a task planner. " + s["replan_task"] + "\n"
        "ABSOLUTE RULES:\n"
        + "\n".join(f"- {r}" for r in rules) + "\n\n"
        "Available tools:\n{tool_descriptions}"
    )


# ── Router / Chat (no variants needed) ──────────────────────────────────────

ROUTER_PROMPT = """\
You are an input classifier. Decide if the user's message needs tool use.

CHAT — no tools needed: greetings, casual conversation, thanks, opinions,
follow-up questions about a previous answer.
  Examples: "こんにちは", "ありがとう", "それはどういう意味？", "元気ですか"

AGENT — tool use required: search, file operations, calculations, data
retrieval, code writing, date/time lookup, or any action-oriented request.
  Examples: "天気を調べて", "ファイルを作成して", "今日の日付は？", "〇〇を検索して"

Reply with exactly one word: CHAT or AGENT"""

# Chat path only. No tools are bound here — tool instructions cause
# hallucinated tool calls on instruction-following models like mistral.
CHAT_PROMPT = """\
You are a friendly and helpful AI assistant.
[CRITICAL] You MUST respond ONLY in Japanese. NEVER output Chinese characters."""

# ── Module-level exports (backward-compatible) ───────────────────────────────
# Built at import time from PROMPT_VARIANT in config.
# All existing `from core.prompts import SYSTEM_PROMPT` calls continue to work.

from config import PROMPT_VARIANT as _VARIANT  # noqa: E402

SYSTEM_PROMPT = build_system_prompt(_VARIANT)
PLAN_PROMPT   = build_plan_prompt(_VARIANT)
REPLAN_PROMPT = build_replan_prompt(_VARIANT)
