import json
import logging
import re
from datetime import datetime
from pathlib import Path

from config import AGENT_MODE, FEATURES, LOG_DIR, LOG_LEVEL, PROMPT_VARIANT, TASK_ID, TASK_TIER
from core.models import Step, format_checklist

METRICS_FILE = LOG_DIR / "metrics.jsonl"


def _tool_descriptions(tools: list) -> str:
    return "\n".join(f"- {t.name}: {t.description}" for t in tools)


def _task_message(prompt: str, steps: list[Step]) -> str:
    checklist = format_checklist(steps)
    pending = sum(1 for s in steps if s.status == "pending")
    return (
        f"Task: {prompt}\n\n"
        f"Execution checklist ({pending} steps remaining):\n{checklist}\n\n"
        "IMPORTANT: Execute the ⏳ steps one by one using tools. "
        "Do NOT give a final answer until all steps are ✅."
    )


def _sanitize(text: str) -> str:
    text = re.sub(r"<tool_call>.*?</tool_call>", "", text, flags=re.DOTALL)
    lines = [line for line in text.splitlines() if not re.match(r'\s*\{"name":', line)]
    return "\n".join(lines).strip()


class MetricsLogger:
    """Per-session metrics collector.

    Tracks TCA, Arg-Fit Rate, Step Completion Rate, Error Rate, elapsed time,
    and replan count, then appends a single JSONL record to METRICS_FILE.
    """

    def __init__(self, model_name: str, prompt: str):
        self.model_name = model_name
        self.prompt = prompt
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        self._start = datetime.now()
        self._turns: list[dict] = []
        self._replan_count: int = 0
        # Capture test context from env at construction time
        self._prompt_variant = PROMPT_VARIANT
        self._task_tier = TASK_TIER
        self._task_id = TASK_ID

    def log_turn(
        self,
        turn: int,
        tool_called: bool,
        tool_name: str | None = None,
        tool_name_fix: str | None = None,
        arg_fixes: list[str] | None = None,
        is_error: bool | None = None,
    ) -> None:
        """Record one LLM turn."""
        self._turns.append({
            "turn": turn,
            "tool_called": tool_called,
            "tool_name": tool_name,
            "tool_name_fix": tool_name_fix,
            "arg_fixes": arg_fixes or [],
            "is_error": is_error,
        })

    def log_replan(self) -> None:
        """Increment the replan counter."""
        self._replan_count += 1

    def write_summary(
        self,
        steps: list[Step],
        *,
        termination: str = "answer",
    ) -> None:
        """Compute aggregated metrics and append to metrics.jsonl.

        No-op in production mode (LOG_LEVEL=WARNING).

        termination — reason the loop ended:
          "answer"    normal completion with a final answer
          "timeout"   EXEC_TIMEOUT or LLM call timeout
          "max_steps" hit MAX_STEPS limit
          "llm_error" unrecoverable LLM error
        """
        if logging.getLevelName(LOG_LEVEL.upper()) >= logging.WARNING:
            return  # production mode: skip metrics
        elapsed_sec = (datetime.now() - self._start).total_seconds()

        total_turns = len(self._turns)
        tool_turns = [t for t in self._turns if t["tool_called"]]
        name_fix_turns = [t for t in tool_turns if t.get("tool_name_fix")]
        arg_fix_turns  = [t for t in tool_turns if t["arg_fixes"]]
        error_turns    = [t for t in tool_turns if t.get("is_error")]

        tca = len(tool_turns) / total_turns if total_turns > 0 else 0.0

        # Tool-Name Accuracy: fraction of tool calls with correct name on first try
        tool_name_accuracy = (
            (len(tool_turns) - len(name_fix_turns)) / len(tool_turns)
            if tool_turns else 1.0
        )
        # Arg-Fit Rate: tool calls where all args matched schema without fixing
        arg_fit_rate = (
            (len(tool_turns) - len(arg_fix_turns)) / len(tool_turns)
            if tool_turns else 1.0
        )
        # Error Rate: fraction of tool calls that returned an error
        error_rate = len(error_turns) / len(tool_turns) if tool_turns else 0.0

        total_steps = len(steps)
        done_count  = sum(1 for s in steps if s.status == "done")
        step_completion_rate = round(done_count / total_steps, 3) if total_steps else None

        record = {
            "session_id":           self.session_id,
            "timestamp":            datetime.now().isoformat(),
            "model":                self.model_name,
            "prompt_variant":       self._prompt_variant,
            "agent_mode":           AGENT_MODE,
            "task_tier":            self._task_tier,
            "task_id":              self._task_id,
            "termination":          termination,
            "elapsed_sec":          round(elapsed_sec),
            "prompt_preview":       self.prompt[:100],
            "tca":                  round(tca, 3),
            "tool_name_accuracy":   round(tool_name_accuracy, 3),
            "arg_fit_rate":         round(arg_fit_rate, 3),
            "error_rate":           round(error_rate, 3),
            "step_completion_rate": step_completion_rate,
            "replan_count":         self._replan_count,
            "total_turns":          total_turns,
            "total_steps":          total_steps,
            "done_steps":           done_count,
            "tool_name_fixes":      len(name_fix_turns),
            "arg_fixes":            len(arg_fix_turns),
            "turns":                self._turns,
        }

        METRICS_FILE.parent.mkdir(exist_ok=True)
        with METRICS_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


def setup_logging() -> logging.Logger:
    level = getattr(logging, LOG_LEVEL.upper(), logging.WARNING)
    logger = logging.getLogger("agent")
    logger.setLevel(logging.DEBUG)  # capture all; handlers filter
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

    if level < logging.WARNING:
        # Dev mode: write full DEBUG log to file
        LOG_DIR.mkdir(exist_ok=True)
        log_file = LOG_DIR / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(formatter)
        logger.addHandler(fh)

    # Console handler: always present, respects LOG_LEVEL
    sh = logging.StreamHandler()
    sh.setLevel(level)
    sh.setFormatter(formatter)
    logger.addHandler(sh)
    return logger
