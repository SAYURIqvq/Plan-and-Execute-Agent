import re
import time

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_mcp_adapters.client import MultiServerMCPClient

import core.llm as llm
from agent.components.planner import make_plan_steps
from agent.loops.exec_loop import run_exec_loop
from agent.loops.react_loop import run_react_loop
from config import AGENT_MODE, FEATURES
from core.prompts import CHAT_PROMPT, ROUTER_PROMPT
from core.utils import _sanitize, setup_logging
from servers import (
    FILESYSTEM_CONFIG,
    MEMORY_CONFIG,
    SHELL_CONFIG,
    SQLITE_CONFIG,
    TIME_CONFIG,
    WEBSEARCH_CONFIG,
)


# Patterns that are unambiguously conversational — no LLM call needed.
_CHAT_RE = re.compile(
    r'^(こんにちは|おはよう|こんばんは|ありがとう|どうも|よろしく|'
    r'お疲れ|ただいま|いただきます|ごちそうさま|はじめまして|'
    r'hello|hi\b|hey\b|thanks|thank you|good (morning|evening|night))',
    re.IGNORECASE,
)


def _quick_classify(prompt: str) -> str | None:
    """Keyword pre-filter: returns 'chat' for obvious greetings, else None."""
    if _CHAT_RE.match(prompt.strip()):
        return "chat"
    return None


async def classify_intent(prompt: str, model, logger) -> str:
    """Classify prompt as 'chat' or 'agent' with a single lightweight LLM call.

    Defaults to 'agent' on any ambiguous or unexpected output to ensure
    tool-requiring tasks are never silently dropped.
    """
    t0 = time.perf_counter()
    logger.info("[router] classifying intent...")
    response = await model.ainvoke([
        SystemMessage(content=ROUTER_PROMPT),
        HumanMessage(content=prompt),
    ])
    # Strip <think>...</think> blocks emitted by reasoning models (deepseek-r1, etc.)
    # before checking for CHAT/AGENT, then search anywhere in the response.
    raw = re.sub(r"<think>.*?</think>", "", response.content, flags=re.DOTALL).strip().upper()
    m = re.search(r"\b(CHAT|AGENT)\b", raw)
    intent = "chat" if (m and m.group(1) == "CHAT") else "agent"
    logger.info(f"[router] raw={raw[:120]!r} → intent={intent} ({time.perf_counter() - t0:.1f}s)")
    return intent


async def run(prompt: str) -> str | None:
    logger = setup_logging()

    # Each phase gets its own LLM instance so num_predict can differ.
    # When FEATURES["num_predict_limit"] is False all instances are identical.
    router_model = llm.get_llm("router")
    chat_model   = llm.get_llm("chat")
    plan_model   = llm.get_llm("plan")
    exec_model   = llm.get_llm("exec")
    replan_model = llm.get_llm("replan")

    logger.info(f"prompt: {prompt}")

    # --- Router: keyword pre-filter, then LLM fallback ---
    intent = _quick_classify(prompt)
    if intent:
        logger.info(f"[router] quick_classify → {intent}")
    else:
        intent = await classify_intent(prompt, router_model, logger)

    if intent == "chat":
        response = await chat_model.ainvoke([
            SystemMessage(content=CHAT_PROMPT),
            HumanMessage(content=prompt),
        ])
        answer = _sanitize(response.content)
        logger.info(f"[chat] answer: {answer}")
        return answer

    # --- Agent mode: route by AGENT_MODE ---
    client = MultiServerMCPClient({
        "filesystem": FILESYSTEM_CONFIG,
        "shell":      SHELL_CONFIG,
        "websearch":  WEBSEARCH_CONFIG,
        "time":       TIME_CONFIG,
        "sqlite":     SQLITE_CONFIG,
        "memory":     MEMORY_CONFIG,
    })
    tools = await client.get_tools()
    tool_map = {t.name: t for t in tools}

    logger.info(f"[executor] agent_mode={AGENT_MODE}")

    if AGENT_MODE == "react":
        return await run_react_loop(prompt, tools, tool_map, exec_model, logger)

    # plan_exec (default): Plan-and-Execute
    steps = await make_plan_steps(prompt, tools, tool_map, plan_model, logger)
    return await run_exec_loop(prompt, steps, tools, tool_map, exec_model, logger,
                               replan_model=replan_model)
