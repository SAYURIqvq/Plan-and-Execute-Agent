import os
from pathlib import Path

# Prompt variant to use (overridable via PROMPT_VARIANT env var).
# Variants are defined in core/prompts.py.
#   "default" — current baseline behaviour
#   "v1"      — adds explicit "output ONLY <tool_call>" rule, no examples
#   "v2"      — v1 + keep examples for argument-name guidance
PROMPT_VARIANT: str = os.environ.get("PROMPT_VARIANT", "default")

# Logging verbosity (overridable via LOG_LEVEL env var).
#   WARNING (default) — production mode: console only, no file log, no metrics
#   INFO              — dev mode: file log + metrics + INFO console
#   DEBUG             — dev mode: file log + metrics + full DEBUG console
LOG_LEVEL: str = os.environ.get("LOG_LEVEL", "WARNING")

# Test-context labels written into metrics records (set by compare script).
#   TASK_TIER — easy / medium / hard / "" (unknown)
#   TASK_ID   — 1-based index of the task within the current tier run
TASK_TIER: str = os.environ.get("TASK_TIER", "")
TASK_ID:   str = os.environ.get("TASK_ID", "")

# Strategy name for the ReAct loop termination logic.
# See app/agent/termination.py for available strategies.
#   "text"        — any text response ends the loop (current default)
#   "finish_tool" — loop ends only when the model calls finish()
AGENT_MODE:        str = os.environ.get("AGENT_MODE", "plan_exec")
REACT_TERMINATION: str = os.environ.get("REACT_TERMINATION", "text")
# Watchdog strategy for the ReAct loop.
# See app/agent/base/watchdog.py for available strategies.
#   "none"        — no intervention (default)
#   "consecutive" — inject feedback after N consecutive tool errors
REACT_WATCHDOG:    str = os.environ.get("REACT_WATCHDOG", "none")

MAX_STEPS = 30
MAX_FAILURES_BEFORE_REPLAN = 1
MAX_REPLANS = 3
EXEC_TIMEOUT = 1200  # seconds; exec loop is aborted when this is exceeded
LOG_DIR = Path("/app/logs")

# ---------------------------------------------------------------------------
# Feature flags
# ---------------------------------------------------------------------------
# Toggle experimental or optional behaviours without touching logic code.
# Each flag is a bool; set to False to disable a feature entirely.
#
FEATURES: dict[str, bool] = {
    # Trim long ToolMessage content before adding to the LLM context.
    # Prevents context overflow when fetch_page / read_file return large text.
    "tool_result_trimming": True,

    # Correct hallucinated tool names via alias table + fuzzy match (exec-time).
    "tool_name_fixer": True,

    # Correct hallucinated tool names in plan steps before execution starts.
    # Uses the same alias + fuzzy logic as tool_name_fixer, applied at plan-time.
    "plan_tool_name_fixer": True,

    # Normalise hallucinated argument names to match the tool schema.
    "arg_fixer": True,

    # Unescape literal \\n / \\t in write_file content strings.
    "content_fixer": True,

    # Watchdog: warn when the same tool fails repeatedly.
    "watchdog": True,

    # Skip gather_current_state for prompts that don't need filesystem info.
    "state_skip_optimization": True,

    # Limit token generation per LLM call by phase (see NUM_PREDICT_PER_PHASE).
    # Prevents runaway generation (e.g. 3000-token stuck turns on 14b).
    "num_predict_limit": False,

    # Sliding window: keep only the most recent N messages in the exec loop
    # context, preserving the fixed System + Task head.
    # Reduces prefill time as conversation grows (prefill is the main bottleneck
    # on CPU: 29 tok/s → 3000 token context costs ~103s just for prefill).
    "message_window": True,
}

# ---------------------------------------------------------------------------
# Per-phase num_predict (used when FEATURES["num_predict_limit"] is True)
# ---------------------------------------------------------------------------
# num_predict caps how many tokens the LLM generates in a single call.
# Setting this too low risks truncating the response before a tool call is
# emitted; too high wastes time on runaway generation.
#
# Phase descriptions:
#   router  — single word output (CHAT / AGENT); very short
#   chat    — conversational reply; moderate length
#   plan    — numbered step list; can be long for complex tasks
#   exec    — tool call JSON + brief reasoning; compact
#   replan  — revised numbered list; similar to plan
#
# Tuning guide (CPU: ~6 tok/s for 14b, ~11 tok/s for 7b):
#   128 tokens → ~21s (14b) /  12s (7b)
#   256 tokens → ~43s (14b) /  23s (7b)
#   512 tokens → ~85s (14b) /  47s (7b)
#  1024 tokens → ~171s (14b) / 94s (7b)
#
# ---------------------------------------------------------------------------
# Sliding window (used when FEATURES["message_window"] is True)
# ---------------------------------------------------------------------------
# Number of messages kept from the *tail* of the conversation history.
# The first MESSAGE_WINDOW_HEAD messages (System + Task) are always preserved.
#
# Each exec turn adds 2 messages (AIMessage + ToolMessage), so:
#   window=8  → keeps 4 recent tool-call turns  ≈ 1200-1600 tokens
#   window=6  → keeps 3 recent tool-call turns  ≈  900-1200 tokens
#   window=4  → keeps 2 recent tool-call turns  ≈  600- 800 tokens
#
# Tuning guide (prefill: 29 tok/s on Ryzen 9 6900HX CPU):
#   window=8  → ~1400 tok → prefill ~48s  (vs ~103s at full context)
#   window=6  → ~1050 tok → prefill ~36s
#   window=4  → ~  700 tok → prefill ~24s  (risk: forgets earlier errors)
#
MESSAGE_WINDOW_HEAD: int = 2    # System + Task; never dropped
MESSAGE_WINDOW_SIZE: int = 12   # tail messages to keep (must be even: AI+Tool pairs)

NUM_PREDICT_PER_PHASE: dict[str, int] = {
    "router": 32,
    "chat":   512,
    "plan":   1024,
    "exec":   768,   # 512 は TCA 低下あり。768 が次の試験候補
    "replan": 1024,
}

# ---------------------------------------------------------------------------
# Tool result trimming (used when FEATURES["tool_result_trimming"] is True)
# ---------------------------------------------------------------------------
# Characters to keep in a ToolMessage before adding to the LLM context.
#
# Rules (applied in order):
#   1. Per-tool limit in TOOL_RESULT_MAX_CHARS  (highest priority)
#   2. TOOL_RESULT_DEFAULT_MAX_CHARS            (fallback for unlisted tools)
#   3. 0 or None means "no limit"
#
# Tuning guide (1 token ≈ 3-4 chars for mixed JP/EN text):
#   2000 chars ≈  500 tokens  — generous, safe for 4096 ctx
#   1000 chars ≈  250 tokens  — tight but sufficient for most tool outputs
#    500 chars ≈  125 tokens  — very tight; may lose important details
#
TOOL_RESULT_DEFAULT_MAX_CHARS: int = 2000

TOOL_RESULT_MAX_CHARS: dict[str, int] = {
    # Web content tends to be very long; limit aggressively.
    "fetch_page":        1500,
    "web_search":        1000,
    # File / command output can also be large.
    "read_file":         2000,
    "execute_command":   1500,
    # SQLite results are usually compact; keep more.
    "query":             2000,
    # Small tools — default is fine, but list explicitly for clarity.
    "list_directory":    1000,
    "write_file":         500,
    "create_directory":   500,
    "remember":           500,
    "recall":            1000,
}
