"""Shared pytest fixtures and import-path setup for the backend test suite.

Backend modules use top-level imports (e.g. ``from vector_store import VectorStore``),
so the ``backend/`` directory must be on ``sys.path`` for tests to import them.
"""

import os
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

# Put backend/ (the parent of this tests/ dir) on the import path.
BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from vector_store import SearchResults, VectorStore  # noqa: E402


# --------------------------------------------------------------------------- #
# SearchResults builders
# --------------------------------------------------------------------------- #
@pytest.fixture
def make_search_results():
    """Factory for SearchResults objects (populated / empty / error)."""

    def _make(documents=None, metadata=None, distances=None, error=None):
        documents = documents or []
        metadata = metadata or []
        if distances is None:
            distances = [0.1] * len(documents)
        return SearchResults(
            documents=documents,
            metadata=metadata,
            distances=distances,
            error=error,
        )

    return _make


@pytest.fixture
def populated_search_results(make_search_results):
    """A typical two-hit search result spanning two lessons of one course."""
    return make_search_results(
        documents=[
            "Chunk about MCP servers and tools.",
            "Chunk about MCP client architecture.",
        ],
        metadata=[
            {"course_title": "MCP Course", "lesson_number": 1},
            {"course_title": "MCP Course", "lesson_number": 2},
        ],
    )


# --------------------------------------------------------------------------- #
# Mocked VectorStore
# --------------------------------------------------------------------------- #
@pytest.fixture
def mock_vector_store():
    """A VectorStore mock with a configurable .search() and a stub lesson link."""
    store = MagicMock(spec=VectorStore)
    store.get_lesson_link.return_value = "http://example.com/lesson"
    return store


# --------------------------------------------------------------------------- #
# Fake Anthropic response builders
# --------------------------------------------------------------------------- #
def make_text_block(text):
    return SimpleNamespace(type="text", text=text)


def make_tool_use_block(name, tool_input, block_id="toolu_123"):
    return SimpleNamespace(type="tool_use", name=name, input=tool_input, id=block_id)


def make_response(content, stop_reason="end_turn"):
    """Build a fake anthropic Message-like object."""
    return SimpleNamespace(content=content, stop_reason=stop_reason)


@pytest.fixture
def anthropic_factories():
    """Expose the fake-response builders to tests."""
    return SimpleNamespace(
        text_block=make_text_block,
        tool_use_block=make_tool_use_block,
        response=make_response,
    )


@pytest.fixture
def patched_ai_generator(mocker):
    """An AIGenerator whose anthropic client is fully mocked (no real network).

    Returns (generator, mock_client). Tests set
    ``mock_client.messages.create.side_effect = [...]`` to script responses.
    """
    mock_anthropic_cls = mocker.patch("ai_generator.anthropic.Anthropic")
    mock_client = MagicMock()
    mock_anthropic_cls.return_value = mock_client

    from ai_generator import AIGenerator

    generator = AIGenerator(api_key="test-key", model="test-model")
    return generator, mock_client


# --------------------------------------------------------------------------- #
# FastAPI test app fixtures
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def mock_rag_system():
    """The RAGSystem mock instance wired into the test FastAPI app.

    Module-scoped so it survives the full test_api.py run alongside api_client.
    Individual tests configure return values via this fixture; the autouse
    ``_reset_api_mocks`` fixture in test_api.py resets state between tests.
    """
    return MagicMock()


@pytest.fixture(scope="module")
def api_client(mock_rag_system):
    """TestClient for the FastAPI app with RAGSystem and StaticFiles mocked.

    RAGSystem is patched before app import so the module-level
    ``rag_system = RAGSystem(config)`` in app.py gets the mock instance.
    StaticFiles is patched to avoid a missing ``../frontend`` directory error.
    """
    from fastapi.testclient import TestClient

    # Force a clean import of app so the patches take effect.
    sys.modules.pop("app", None)

    with patch("rag_system.RAGSystem", return_value=mock_rag_system), \
         patch("fastapi.staticfiles.StaticFiles"):
        from app import app as fastapi_app  # noqa: E402

        with TestClient(fastapi_app, raise_server_exceptions=False) as client:
            yield client
