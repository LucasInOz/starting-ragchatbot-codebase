"""Tests for RAGSystem.query content-query handling (item 3), fully mocked.

The heavy collaborators (VectorStore -> ChromaDB, AIGenerator -> Anthropic,
DocumentProcessor, SessionManager) are patched at the rag_system module level so
no network/DB access happens. We verify the orchestration query() performs:
tools + tool_manager are threaded into the AI call, sources flow back out via the
tool manager's mutable state and are reset, and session history is recorded.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import rag_system as rag_module
from rag_system import RAGSystem


@pytest.fixture
def config():
    return SimpleNamespace(
        CHUNK_SIZE=800,
        CHUNK_OVERLAP=100,
        CHROMA_PATH="./chroma_db",
        EMBEDDING_MODEL="all-MiniLM-L6-v2",
        MAX_RESULTS=5,
        ANTHROPIC_API_KEY="test-key",
        ANTHROPIC_MODEL="test-model",
        MAX_HISTORY=2,
    )


@pytest.fixture
def rag(mocker, config):
    """A RAGSystem with collaborators that construct ChromaDB / Anthropic patched out.

    The real ToolManager + CourseSearchTool/CourseOutlineTool are kept (only the
    VectorStore they wrap is a mock), so the source-flow plumbing is exercised
    for real.
    """
    mocker.patch.object(rag_module, "DocumentProcessor")
    mocker.patch.object(rag_module, "VectorStore")
    mocker.patch.object(rag_module, "AIGenerator")
    mocker.patch.object(rag_module, "SessionManager")
    return RAGSystem(config)


def test_query_threads_tools_and_manager_into_ai_call(rag):
    rag.ai_generator.generate_response.return_value = "an answer"

    rag.query("What does lesson 1 of MCP cover?")

    _, kwargs = rag.ai_generator.generate_response.call_args
    # The two registered tool definitions are passed along...
    assert kwargs["tools"] == rag.tool_manager.get_tool_definitions()
    tool_names = {t["name"] for t in kwargs["tools"]}
    assert {"search_course_content", "get_course_outline"} <= tool_names
    # ...and the tool manager itself, so the AI can execute them.
    assert kwargs["tool_manager"] is rag.tool_manager


def test_query_returns_answer_and_sources_tuple(rag):
    # Make the AI "use" the search tool: invoking the tool populates last_sources.
    def fake_generate(*args, **kwargs):
        kwargs["tool_manager"].tools["search_course_content"].last_sources = [
            {"text": "MCP Course - Lesson 1", "link": "http://example.com/l1"}
        ]
        return "MCP lesson 1 covers servers."

    rag.ai_generator.generate_response.side_effect = fake_generate

    answer, sources = rag.query("What does lesson 1 of MCP cover?")

    assert answer == "MCP lesson 1 covers servers."
    assert sources == [
        {"text": "MCP Course - Lesson 1", "link": "http://example.com/l1"}
    ]


def test_query_resets_sources_after_returning(rag):
    def fake_generate(*args, **kwargs):
        kwargs["tool_manager"].tools["search_course_content"].last_sources = [
            {"text": "MCP Course - Lesson 1", "link": None}
        ]
        return "answer"

    rag.ai_generator.generate_response.side_effect = fake_generate

    rag.query("first question")
    # After the first query, sources must be cleared so the next query doesn't
    # leak stale citations.
    assert rag.tool_manager.get_last_sources() == []


def test_query_without_session_skips_history(rag):
    rag.ai_generator.generate_response.return_value = "answer"

    rag.query("a content question")

    # No session -> no history fetch, no exchange recorded.
    rag.session_manager.get_conversation_history.assert_not_called()
    rag.session_manager.add_exchange.assert_not_called()
    _, kwargs = rag.ai_generator.generate_response.call_args
    assert kwargs["conversation_history"] is None


def test_query_with_session_uses_and_records_history(rag):
    rag.session_manager.get_conversation_history.return_value = "prev history"
    rag.ai_generator.generate_response.return_value = "answer"

    rag.query("a content question", session_id="sess-1")

    rag.session_manager.get_conversation_history.assert_called_once_with("sess-1")
    _, kwargs = rag.ai_generator.generate_response.call_args
    assert kwargs["conversation_history"] == "prev history"
    # The exchange is persisted for future turns.
    rag.session_manager.add_exchange.assert_called_once()
    assert rag.session_manager.add_exchange.call_args.args[0] == "sess-1"
