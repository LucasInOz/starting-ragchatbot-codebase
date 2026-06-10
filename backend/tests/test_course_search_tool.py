"""Tests for CourseSearchTool.execute (item 1).

The tool is driven against a mocked VectorStore so we test the tool's own
formatting / source-tracking / error-handling logic, not ChromaDB.
"""

from search_tools import CourseSearchTool


def test_execute_returns_formatted_results_with_headers(
    mock_vector_store, populated_search_results
):
    mock_vector_store.search.return_value = populated_search_results
    tool = CourseSearchTool(mock_vector_store)

    output = tool.execute(query="what is MCP")

    # Each hit is prefixed with a [Course - Lesson N] header followed by its text.
    assert "[MCP Course - Lesson 1]" in output
    assert "Chunk about MCP servers and tools." in output
    assert "[MCP Course - Lesson 2]" in output
    assert "Chunk about MCP client architecture." in output


def test_execute_populates_last_sources(
    mock_vector_store, populated_search_results
):
    mock_vector_store.search.return_value = populated_search_results
    tool = CourseSearchTool(mock_vector_store)

    tool.execute(query="what is MCP")

    assert tool.last_sources == [
        {"text": "MCP Course - Lesson 1", "link": "http://example.com/lesson"},
        {"text": "MCP Course - Lesson 2", "link": "http://example.com/lesson"},
    ]
    # The link came from the store, looked up per (course_title, lesson_number).
    mock_vector_store.get_lesson_link.assert_any_call("MCP Course", 1)
    mock_vector_store.get_lesson_link.assert_any_call("MCP Course", 2)


def test_execute_passes_filters_through_to_store(
    mock_vector_store, populated_search_results
):
    mock_vector_store.search.return_value = populated_search_results
    tool = CourseSearchTool(mock_vector_store)

    tool.execute(query="topic", course_name="MCP", lesson_number=2)

    mock_vector_store.search.assert_called_once_with(
        query="topic", course_name="MCP", lesson_number=2
    )


def test_execute_empty_results_no_filters(mock_vector_store, make_search_results):
    mock_vector_store.search.return_value = make_search_results()
    tool = CourseSearchTool(mock_vector_store)

    output = tool.execute(query="nothing here")

    assert output == "No relevant content found."


def test_execute_empty_results_includes_filter_info(
    mock_vector_store, make_search_results
):
    mock_vector_store.search.return_value = make_search_results()
    tool = CourseSearchTool(mock_vector_store)

    output = tool.execute(query="x", course_name="MCP", lesson_number=3)

    assert "No relevant content found" in output
    assert "in course 'MCP'" in output
    assert "in lesson 3" in output


def test_execute_returns_error_verbatim(mock_vector_store, make_search_results):
    mock_vector_store.search.return_value = make_search_results(
        error="No course found matching 'Bogus'"
    )
    tool = CourseSearchTool(mock_vector_store)

    output = tool.execute(query="x", course_name="Bogus")

    assert output == "No course found matching 'Bogus'"


def test_execute_result_without_lesson_number(
    mock_vector_store, make_search_results
):
    """A chunk whose metadata has no lesson_number should produce a header with no
    'Lesson' suffix and a None link (and not call get_lesson_link)."""
    mock_vector_store.search.return_value = make_search_results(
        documents=["Course-level overview text."],
        metadata=[{"course_title": "MCP Course", "lesson_number": None}],
    )
    tool = CourseSearchTool(mock_vector_store)

    output = tool.execute(query="overview")

    assert "[MCP Course]" in output
    assert "Lesson" not in output
    assert tool.last_sources == [{"text": "MCP Course", "link": None}]
    mock_vector_store.get_lesson_link.assert_not_called()


def test_get_tool_definition_schema(mock_vector_store):
    tool = CourseSearchTool(mock_vector_store)
    definition = tool.get_tool_definition()

    assert definition["name"] == "search_course_content"
    assert definition["input_schema"]["required"] == ["query"]
    properties = definition["input_schema"]["properties"]
    assert set(properties) == {"query", "course_name", "lesson_number"}
