import ast
import asyncio
import logging
import re
import time

from langchain_core.messages import HumanMessage, SystemMessage

from agent.base.fixers import fix_plan_tool_names
from config import FEATURES
from core.models import Step, format_checklist, parse_steps
from core.prompts import PLAN_PROMPT, REPLAN_PROMPT
from core.utils import _tool_descriptions

logger = logging.getLogger("agent")

# Prompts containing these keywords likely need filesystem/DB state.
_STATE_NEEDED_RE = re.compile(
    r'(ファイル|file|/data|データベース|database|db|テーブル|table|'
    r'メモ|memo|記憶|memory|履歴|history|保存|save|作成|creat|書)',
    re.IGNORECASE,
)


def _parse_tables(result) -> list[str]:
    """list_tables の ainvoke 結果からテーブル名リストを抽出する。

    MCP ツールの戻り値は [{'type': 'text', 'text': "['t1', 't2']", ...}] 形式。
    """
    if isinstance(result, list):
        for block in result:
            if isinstance(block, dict) and isinstance(block.get("text"), str):
                try:
                    tables = ast.literal_eval(block["text"])
                    if isinstance(tables, list):
                        return [t for t in tables if isinstance(t, str)]
                except Exception:
                    pass
    # フォールバック: 文字列からパターンマッチ
    text = str(result)
    for pat in [r"'text':\s*\"(\[[^\"]*\])\"", r"'text':\s*'(\[[^']*\])'"]:
        m = re.search(pat, text)
        if m:
            try:
                tables = ast.literal_eval(m.group(1))
                if isinstance(tables, list):
                    return [t for t in tables if isinstance(t, str)]
            except Exception:
                pass
    return []


async def gather_current_state(tool_map: dict, prompt: str = "") -> str:
    if FEATURES.get("state_skip_optimization", True) and prompt and not _STATE_NEEDED_RE.search(prompt):
        logger.info("[gather_state] skipped (no filesystem/DB keywords in prompt)")
        return "(state gathering skipped)"

    async def _fetch(tool_name: str, label: str, args: dict) -> str | None:
        if tool_name not in tool_map:
            return None
        try:
            result = await tool_map[tool_name].ainvoke(args)
            return f"[{label}]\n{result}"
        except Exception as e:
            return f"[{label}]\n(error: {e})"

    t0 = time.perf_counter()
    logger.info("[gather_state] start")

    # list_tables を先に取得してスキーマ探索に使う
    tables_raw = None
    if "list_tables" in tool_map:
        try:
            tables_raw = await tool_map["list_tables"].ainvoke({})
        except Exception:
            pass

    table_names = _parse_tables(tables_raw) if tables_raw is not None else []

    # ディレクトリ・メモリ・各テーブルスキーマを並列取得
    schema_fetches = [
        _fetch("query", f"Schema of '{t}' (column names/types)", {"sql": f"PRAGMA table_info({t})"})
        for t in table_names
        if "query" in tool_map
    ]
    parallel_results = await asyncio.gather(
        _fetch("list_directory", "Files in /data", {"path": "/data"}),
        _fetch("list_memories",  "Stored memories", {}),
        *schema_fetches,
    )

    parts = []
    if tables_raw is not None:
        parts.append(f"[SQLite tables]\n{tables_raw}")
    parts.extend(r for r in parallel_results if r is not None)

    logger.info(f"[gather_state] done in {time.perf_counter() - t0:.1f}s")
    return "\n\n".join(parts) if parts else "(no state available)"


async def make_plan(prompt: str, tools: list, tool_map: dict, model) -> str:
    current_state = await gather_current_state(tool_map, prompt)
    messages = [
        SystemMessage(content=PLAN_PROMPT.format(
            current_state=current_state,
            tool_descriptions=_tool_descriptions(tools),
        )),
        HumanMessage(content=prompt),
    ]
    logger.info("[plan:llm] start")
    t0 = time.perf_counter()
    result = (await model.ainvoke(messages)).content
    logger.info(f"[plan:llm] done in {time.perf_counter() - t0:.1f}s")
    return result


async def make_plan_steps(
    prompt: str,
    tools: list,
    tool_map: dict,
    model,
    run_logger=None,
) -> list[Step]:
    """Plan, parse, and fix tool names in one call.

    Replaces the make_plan + parse_steps + fix_plan_tool_names sequence that
    previously lived in executor.py.  Keeps executor at Layer 4 with no direct
    dependency on agent.base.fixers.

    run_logger — caller's logger for fix/plan log lines (falls back to module logger).
    """
    log = run_logger or logger
    plan_text = await make_plan(prompt, tools, tool_map, model)
    steps = parse_steps(plan_text)
    if tool_map and FEATURES.get("plan_tool_name_fixer", True):
        steps, plan_fixes = fix_plan_tool_names(steps, tool_map)
        for fix in plan_fixes:
            log.warning(f"[plan_fix] {fix}")
    log.info(f"[plan]\n{format_checklist(steps)}")
    return steps


async def replan(
    prompt: str,
    steps: list[Step],
    execution_history: list[str],
    tools: list,
    model,
    watchdog_hint: str = "",
) -> str:
    checklist = format_checklist(steps)
    history_text = "\n".join(execution_history[-10:])  # 直近10件に絞る

    # Prepend watchdog alert when repeated tool failures have been detected.
    watchdog_block = f"{watchdog_hint}\n\n" if watchdog_hint else ""

    messages = [
        SystemMessage(content=REPLAN_PROMPT.format(tool_descriptions=_tool_descriptions(tools))),
        HumanMessage(content=(
            f"{watchdog_block}"
            f"Original task: {prompt}\n\n"
            f"Current checklist:\n{checklist}\n\n"
            f"Recent execution history:\n{history_text}\n\n"
            "Create a revised plan for the remaining ⏳ and ❌ steps only."
        )),
    ]
    logger.info("[replan:llm] start")
    t0 = time.perf_counter()
    result = (await model.ainvoke(messages)).content
    logger.info(f"[replan:llm] done in {time.perf_counter() - t0:.1f}s")
    return result


async def _apply_replan(
    prompt, steps, execution_history, tools, model, logger,
    watchdog_hint: str = "",
    tool_map: dict | None = None,
) -> tuple[list[Step], int]:
    new_plan_text = await replan(
        prompt, steps, execution_history, tools, model,
        watchdog_hint=watchdog_hint,
    )
    new_steps = parse_steps(new_plan_text)
    if tool_map and FEATURES.get("plan_tool_name_fixer", True):
        new_steps, plan_fixes = fix_plan_tool_names(new_steps, tool_map)
        for fix in plan_fixes:
            logger.warning(f"[plan_fix] {fix}")
    done_steps = [s for s in steps if s.status == "done"]
    merged = done_steps + new_steps
    logger.info(f"[replan]\n{format_checklist(merged)}")
    return merged, len(done_steps)
