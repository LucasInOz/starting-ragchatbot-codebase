"""Tests for the FastAPI API endpoints (/api/query, /api/courses, /api/session).

RAGSystem is mocked before the app module is imported (see the ``api_client``
fixture in conftest.py), so no ChromaDB connection or Anthropic API call is
made. StaticFiles is also mocked to avoid a missing frontend directory.
"""

import pytest


# ---------------------------------------------------------------------------
# Per-test mock reset
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_api_mocks(mock_rag_system):
    """Reset all mock state before each test and provide safe defaults.

    side_effect=True is required: reset_mock() alone does not clear side_effect,
    so a prior test's raised exception would bleed into the next test.
    """
    mock_rag_system.reset_mock(side_effect=True)
    mock_rag_system.query.return_value = ("", [])
    mock_rag_system.session_manager.create_session.return_value = "session_1"
    mock_rag_system.get_course_analytics.return_value = {
        "total_courses": 0,
        "course_titles": [],
    }
    yield
    mock_rag_system.reset_mock(side_effect=True)


# ---------------------------------------------------------------------------
# GET /api/courses
# ---------------------------------------------------------------------------

def test_get_courses_returns_stats(api_client, mock_rag_system):
    mock_rag_system.get_course_analytics.return_value = {
        "total_courses": 3,
        "course_titles": ["Course A", "Course B", "Course C"],
    }
    response = api_client.get("/api/courses")
    assert response.status_code == 200
    body = response.json()
    assert body["total_courses"] == 3
    assert body["course_titles"] == ["Course A", "Course B", "Course C"]


def test_get_courses_empty_catalog(api_client, mock_rag_system):
    mock_rag_system.get_course_analytics.return_value = {
        "total_courses": 0,
        "course_titles": [],
    }
    response = api_client.get("/api/courses")
    assert response.status_code == 200
    assert response.json() == {"total_courses": 0, "course_titles": []}


def test_get_courses_500_on_analytics_error(api_client, mock_rag_system):
    mock_rag_system.get_course_analytics.side_effect = RuntimeError("db unavailable")
    response = api_client.get("/api/courses")
    assert response.status_code == 500


# ---------------------------------------------------------------------------
# POST /api/query
# ---------------------------------------------------------------------------

def test_query_with_session_id(api_client, mock_rag_system):
    mock_rag_system.query.return_value = (
        "Python is a programming language.",
        [{"text": "Intro to Python - Lesson 1", "link": "http://example.com/l1"}],
    )
    response = api_client.post(
        "/api/query",
        json={"query": "What is Python?", "session_id": "session_42"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == "Python is a programming language."
    assert body["session_id"] == "session_42"
    assert body["sources"][0]["text"] == "Intro to Python - Lesson 1"
    assert body["sources"][0]["link"] == "http://example.com/l1"
    # session_manager.create_session must NOT be called when a session_id is provided.
    mock_rag_system.session_manager.create_session.assert_not_called()


def test_query_without_session_id_auto_creates_session(api_client, mock_rag_system):
    mock_rag_system.session_manager.create_session.return_value = "session_new"
    mock_rag_system.query.return_value = ("Some answer.", [])
    response = api_client.post("/api/query", json={"query": "How do LLMs work?"})
    assert response.status_code == 200
    body = response.json()
    assert body["session_id"] == "session_new"
    assert body["answer"] == "Some answer."
    assert body["sources"] == []
    mock_rag_system.session_manager.create_session.assert_called_once()


def test_query_passes_raw_query_to_rag_system(api_client, mock_rag_system):
    mock_rag_system.query.return_value = ("ok", [])
    api_client.post(
        "/api/query", json={"query": "What is retrieval?", "session_id": "s1"}
    )
    mock_rag_system.query.assert_called_once_with("What is retrieval?", "s1")


def test_query_source_without_link_defaults_to_null(api_client, mock_rag_system):
    mock_rag_system.query.return_value = (
        "An answer.",
        [{"text": "Course Overview"}],  # no 'link' key
    )
    response = api_client.post(
        "/api/query", json={"query": "Give me an overview.", "session_id": "s1"}
    )
    assert response.status_code == 200
    source = response.json()["sources"][0]
    assert source["text"] == "Course Overview"
    assert source["link"] is None


def test_query_multiple_sources(api_client, mock_rag_system):
    mock_rag_system.query.return_value = (
        "Detailed answer.",
        [
            {"text": "Course A - Lesson 1", "link": "http://example.com/a1"},
            {"text": "Course A - Lesson 2", "link": "http://example.com/a2"},
        ],
    )
    response = api_client.post(
        "/api/query", json={"query": "Tell me about Course A.", "session_id": "s2"}
    )
    assert response.status_code == 200
    sources = response.json()["sources"]
    assert len(sources) == 2
    assert sources[1]["text"] == "Course A - Lesson 2"


def test_query_500_on_rag_error(api_client, mock_rag_system):
    mock_rag_system.query.side_effect = ValueError("vector store unavailable")
    response = api_client.post(
        "/api/query", json={"query": "anything", "session_id": "s1"}
    )
    assert response.status_code == 500


def test_query_missing_required_field_returns_422(api_client):
    """Omitting the required 'query' field triggers FastAPI validation."""
    response = api_client.post("/api/query", json={"session_id": "s1"})
    assert response.status_code == 422


def test_query_empty_string_is_accepted(api_client, mock_rag_system):
    mock_rag_system.query.return_value = ("I need more context.", [])
    response = api_client.post(
        "/api/query", json={"query": "", "session_id": "s1"}
    )
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# DELETE /api/session/{session_id}
# ---------------------------------------------------------------------------

def test_delete_session_returns_ok(api_client, mock_rag_system):
    response = api_client.delete("/api/session/session_99")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    mock_rag_system.session_manager.delete_session.assert_called_once_with("session_99")


def test_delete_session_500_on_error(api_client, mock_rag_system):
    mock_rag_system.session_manager.delete_session.side_effect = KeyError("missing")
    response = api_client.delete("/api/session/bad_id")
    assert response.status_code == 500
