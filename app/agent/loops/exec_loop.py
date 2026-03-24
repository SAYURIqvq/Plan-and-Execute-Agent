"""Core Plan-and-Execute loop.

Drives the agent through its plan: calls the LLM, dispatches tool calls,
updates step status, and triggers replanning on failures.

Helpers are split across:
  agent/base/fixers.py           — tool name / arg / content correction (via apply_fixers)
  agent/components/loop_helpers  — tool invocation, step status, trimming, window, watchdog
"""

import asyncio
import time
from collections import defaultdict

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from config import (
    EXEC_TIMEOUT,
    FEATURES,
    MAX_FAILURES_BEFORE_REPLAN,
    MAX_REPLANS,
    MAX_STEPS,
)
from agent.components.loop_helpers import (
    _apply_window,
    _build_watchdog_hint,
    _do_replan,
    _invoke_tool,
    _trim_tool_result,
    _update_step,
    apply_fixers,
)
from core.models import Step, format_checklist
from core.prompts import SYSTEM_PROMPT
from core.utils import MetricsLogger, _sanitize, _task_message


async def run_exec_loop(
    prompt: str, steps: list[Step], tools: list, tool_map: dict,
    model, logger, replan_model=None,
) -> str | None:
    """Execute the plan loop.

    model        — LLM for exec turns (tool calling).
    replan_model — LLM for replan calls (defaults to model when None).
                   Use a model with higher num_predict for better replan quality.
    """
    if replan_model is None:
        replan_model = model
    llm_with_tools = model.bind_tools(tools)
    execution_history: list[str] = []
    consecutive_failures = 0
    replan_count = 0
    current_step_idx = 0

    model_name: str = getattr(model, "model", "unknown")
    metrics = MetricsLogger(model_name=model_name, prompt=prompt)
    # Tracks total failures per tool name across all replans (never resets).
    # Used by the Execution Watchdog to detect tools that keep failing.
    tool_failure_counts: dict[str, int] = defaultdict(int)

    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=_task_message(prompt, steps)),
    ]

    loop_start = time.perf_counter()

    def _remaining() -> float:
        """Remaining seconds before EXEC_TIMEOUT (minimum 5s to avoid instant kill)."""
        return max(5.0, EXEC_TIMEOUT - (time.perf_counter() - loop_start))

    for turn in range(MAX_STEPS):
        elapsed = time.perf_counter() - loop_start
        if elapsed > EXEC_TIMEOUT:
            logger.warning(f"タイムアウト ({elapsed:.0f}s > {EXEC_TIMEOUT}s)。")
            metrics.write_summary(steps, termination="timeout")
            return None

        ctx_messages = messages
        if FEATURES.get("message_window", False):
            ctx_messages, truncated = _apply_window(messages)
            if truncated:
                logger.info(
                    f"[window] {len(messages)} → {len(ctx_messages)} messages"
                    f" (dropped {len(messages) - len(ctx_messages)} oldest)"
                )

        logger.info(f"[exec:llm] start (turn {turn + 1}, step {current_step_idx + 1}/{len(steps)})")
        t0 = time.perf_counter()
        try:
            response = await asyncio.wait_for(
                llm_with_tools.ainvoke(ctx_messages), timeout=_remaining()
            )
        except asyncio.TimeoutError:
            elapsed = time.perf_counter() - loop_start
            logger.warning(f"[exec:llm] LLM呼び出しがタイムアウト ({elapsed:.0f}s)。")
            metrics.write_summary(steps, termination="timeout")
            return None
        except Exception as e:
            logger.error(f"[exec:llm] LLM呼び出しエラー: {type(e).__name__}: {e}")
            metrics.write_summary(steps, termination="llm_error")
            return f"[エラー] このモデルはツール呼び出しに非対応か、LLM呼び出しに失敗しました: {e}"
        logger.info(f"[exec:llm] done in {time.perf_counter() - t0:.1f}s")

        if not response.tool_calls:
            metrics.log_turn(turn=turn + 1, tool_called=False)
            pending_steps = [s for s in steps if s.status == "pending"]
            if (pending_steps or consecutive_failures > 0) and replan_count < MAX_REPLANS:
                replan_count += 1
                metrics.log_replan()
                reason = "pending steps remain" if pending_steps else "gave up after error"
                logger.info(f"[replan triggered] {reason} (replan {replan_count}/{MAX_REPLANS})")
                result = await _do_replan(
                    prompt, steps, execution_history, tools, replan_model, logger,
                    tool_failure_counts, _remaining,
                    tool_map=tool_map,
                )
                if result is None:
                    logger.warning(f"[replan] LLM呼び出しがタイムアウト ({time.perf_counter() - loop_start:.0f}s)。")
                    metrics.write_summary(steps, termination="timeout")
                    return None
                steps, current_step_idx = result
                consecutive_failures = 0
                messages.append(HumanMessage(content=_task_message(prompt, steps)))
                continue

            answer = _sanitize(response.content)
            logger.info(f"final answer:\n{answer}")
            metrics.write_summary(steps, termination="answer")
            return answer

        tc = response.tool_calls[0]
        tc, tool_name_fix, arg_fixes = apply_fixers(tc, tool_map, logger)

        logger.info(f"[Tool Call] {tc['name']}({tc['args']})")
        messages.append(AIMessage(content=response.content, tool_calls=[tc]))

        result_str, is_error = await _invoke_tool(tc, tool_map)
        logger.info(f"[Tool Result] {result_str[:500]}")

        metrics.log_turn(
            turn=turn + 1,
            tool_called=True,
            tool_name=tc["name"],
            tool_name_fix=tool_name_fix,
            arg_fixes=arg_fixes,
            is_error=is_error,
        )

        execution_history.append(
            f"{tc['name']}({tc['args']}) → {'ERROR: ' if is_error else ''}{result_str[:200]}"
        )

        # --- Tool Result Trimming: prevent context overflow ---
        ctx_result = result_str
        if FEATURES.get("tool_result_trimming", True):
            ctx_result, original_len = _trim_tool_result(tc["name"], result_str)
            if len(ctx_result) < original_len:
                logger.info(
                    f"[trim] {tc['name']}: {original_len} → {len(ctx_result)} chars"
                )
        messages.append(ToolMessage(content=ctx_result, tool_call_id=tc["id"]))

        current_step_idx = _update_step(steps, current_step_idx, is_error, result_str)
        logger.info(f"[checklist]\n{format_checklist(steps)}")

        if is_error:
            consecutive_failures += 1
            tool_failure_counts[tc["name"]] += 1

            if consecutive_failures >= MAX_FAILURES_BEFORE_REPLAN and replan_count < MAX_REPLANS:
                replan_count += 1
                metrics.log_replan()
                logger.info(
                    f"[replan triggered] {consecutive_failures} consecutive failures"
                    f" (replan {replan_count}/{MAX_REPLANS})"
                )
                result = await _do_replan(
                    prompt, steps, execution_history, tools, replan_model, logger,
                    tool_failure_counts, _remaining,
                    tool_map=tool_map,
                )
                if result is None:
                    logger.warning(f"[replan] LLM呼び出しがタイムアウト ({time.perf_counter() - loop_start:.0f}s)。")
                    metrics.write_summary(steps, termination="timeout")
                    return None
                steps, current_step_idx = result
                consecutive_failures = 0
                messages.append(HumanMessage(content=_task_message(prompt, steps)))
        else:
            consecutive_failures = 0

    logger.warning("最大ステップ数に達しました。")
    metrics.write_summary(steps, termination="max_steps")
