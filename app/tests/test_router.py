import logging
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.executor import classify_intent

logger = logging.getLogger("agent")


def _make_model(response_text: str):
    model = MagicMock()
    model.ainvoke = AsyncMock(return_value=MagicMock(content=response_text))
    return model


# ── classify_intent ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_chat_greeting():
    model = _make_model("CHAT")
    intent = await classify_intent("こんにちは", model, logger)
    assert intent == "chat"


@pytest.mark.asyncio
async def test_chat_thanks():
    model = _make_model("CHAT")
    intent = await classify_intent("ありがとう", model, logger)
    assert intent == "chat"


@pytest.mark.asyncio
async def test_agent_websearch():
    model = _make_model("AGENT")
    intent = await classify_intent("東京の天気を調べて", model, logger)
    assert intent == "agent"


@pytest.mark.asyncio
async def test_agent_file_operation():
    model = _make_model("AGENT")
    intent = await classify_intent("hello.py というファイルを作成して", model, logger)
    assert intent == "agent"


@pytest.mark.asyncio
async def test_agent_datetime():
    model = _make_model("AGENT")
    intent = await classify_intent("今日の日付を教えて", model, logger)
    assert intent == "agent"


@pytest.mark.asyncio
async def test_fallback_on_unexpected_output():
    """Unexpected model output must default to 'agent' (safe fallback)."""
    model = _make_model("わかりません")
    intent = await classify_intent("何かしてください", model, logger)
    assert intent == "agent"


@pytest.mark.asyncio
async def test_fallback_on_empty_output():
    """Empty model output must default to 'agent'."""
    model = _make_model("")
    intent = await classify_intent("", model, logger)
    assert intent == "agent"


@pytest.mark.asyncio
async def test_chat_case_insensitive():
    """'chat' (lowercase) should also be recognized."""
    model = _make_model("chat")
    intent = await classify_intent("やあ", model, logger)
    assert intent == "chat"


@pytest.mark.asyncio
async def test_chat_with_trailing_text():
    """'CHAT (greeting)' style output should still resolve to chat."""
    model = _make_model("CHAT (greeting)")
    intent = await classify_intent("おはよう", model, logger)
    assert intent == "chat"
