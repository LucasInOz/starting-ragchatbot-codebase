"""Tests for AIGenerator's tool-calling behavior (item 2).

The anthropic client is patched (see the ``patched_ai_generator`` fixture), so no
real API calls happen. We assert that AIGenerator wires tools into the request,
executes the tool the model asks for, and synthesizes a final answer.
"""

from unittest.mock import MagicMock


def _tool_definitions():
    return [{"name": "search_course_content", "description": "x", "input_schema": {}}]


def test_no_tool_use_returns_text_directly(patched_ai_generator, anthropic_factories):
    generator, mock_client = patched_ai_generator
    mock_client.messages.create.return_value = anthropic_factories.response(
        content=[anthropic_factories.text_block("Paris is the capital of France.")],
        stop_reason="end_turn",
    )
    tool_manager = MagicMock()

    result = generator.generate_response(
        query="What is the capital of France?",
        tools=_tool_definitions(),
        tool_manager=tool_manager,
    )

    assert result == "Paris is the capital of France."
    # No tool was requested, so the tool manager must never be touched.
    tool_manager.execute_tool.assert_not_called()
    assert mock_client.messages.create.call_count == 1


def test_first_call_includes_tools_and_auto_choice(
    patched_ai_generator, anthropic_factories
):
    generator, mock_client = patched_ai_generator
    mock_client.messages.create.return_value = anthropic_factories.response(
        content=[anthropic_factories.text_block("hi")], stop_reason="end_turn"
    )

    generator.generate_response(query="hi", tools=_tool_definitions())

    _, kwargs = mock_client.messages.create.call_args
    assert kwargs["tools"] == _tool_definitions()
    assert kwargs["tool_choice"] == {"type": "auto"}


def test_tool_use_executes_tool_and_synthesizes(
    patched_ai_generator, anthropic_factories
):
    generator, mock_client = patched_ai_generator

    tool_use_resp = anthropic_factories.response(
        content=[
            anthropic_factories.tool_use_block(
                name="search_course_content",
                tool_input={"query": "MCP", "lesson_number": 1},
                block_id="toolu_abc",
            )
        ],
        stop_reason="tool_use",
    )
    final_resp = anthropic_factories.response(
        content=[anthropic_factories.text_block("MCP is a protocol.")],
        stop_reason="end_turn",
    )
    mock_client.messages.create.side_effect = [tool_use_resp, final_resp]

    tool_manager = MagicMock()
    tool_manager.execute_tool.return_value = "search results text"

    result = generator.generate_response(
        query="What is MCP lesson 1?",
        tools=_tool_definitions(),
        tool_manager=tool_manager,
    )

    # The exact tool name + input from the content block were forwarded.
    tool_manager.execute_tool.assert_called_once_with(
        "search_course_content", query="MCP", lesson_number=1
    )
    assert result == "MCP is a protocol."
    assert mock_client.messages.create.call_count == 2


def test_tool_result_threading_and_message_roles(
    patched_ai_generator, anthropic_factories
):
    """After one tool round, the next call must carry the conversation forward:
    user query -> assistant tool_use -> user tool_result (with the matching id)."""
    generator, mock_client = patched_ai_generator

    tool_use_resp = anthropic_factories.response(
        content=[
            anthropic_factories.tool_use_block(
                name="search_course_content",
                tool_input={"query": "MCP"},
                block_id="toolu_xyz",
            )
        ],
        stop_reason="tool_use",
    )
    final_resp = anthropic_factories.response(
        content=[anthropic_factories.text_block("done")], stop_reason="end_turn"
    )
    mock_client.messages.create.side_effect = [tool_use_resp, final_resp]

    tool_manager = MagicMock()
    tool_manager.execute_tool.return_value = "RESULT_TEXT"

    generator.generate_response(
        query="q", tools=_tool_definitions(), tool_manager=tool_manager
    )

    # Inspect the SECOND (round-2) call's messages.
    second_kwargs = mock_client.messages.create.call_args_list[1].kwargs
    messages = second_kwargs["messages"]
    assert messages[0]["role"] == "user"
    assert messages[1]["role"] == "assistant"
    assert messages[2]["role"] == "user"

    tool_result_block = messages[2]["content"][0]
    assert tool_result_block["type"] == "tool_result"
    assert tool_result_block["tool_use_id"] == "toolu_xyz"
    assert tool_result_block["content"] == "RESULT_TEXT"


def test_conversation_history_in_system_prompt(
    patched_ai_generator, anthropic_factories
):
    generator, mock_client = patched_ai_generator
    mock_client.messages.create.return_value = anthropic_factories.response(
        content=[anthropic_factories.text_block("ok")], stop_reason="end_turn"
    )

    generator.generate_response(
        query="q", conversation_history="User: hi\nAssistant: hello"
    )

    _, kwargs = mock_client.messages.create.call_args
    assert "Previous conversation:" in kwargs["system"]
    assert "User: hi" in kwargs["system"]


def test_two_round_dependent_sequence(patched_ai_generator, anthropic_factories):
    """The headline feature: Claude chains two tools across two API rounds,
    reasoning about round 1's result before the round-2 search."""
    generator, mock_client = patched_ai_generator

    round1 = anthropic_factories.response(
        content=[
            anthropic_factories.tool_use_block(
                name="get_course_outline",
                tool_input={"course_name": "X"},
                block_id="t1",
            )
        ],
        stop_reason="tool_use",
    )
    round2 = anthropic_factories.response(
        content=[
            anthropic_factories.tool_use_block(
                name="search_course_content",
                tool_input={"query": "lesson 4 title"},
                block_id="t2",
            )
        ],
        stop_reason="tool_use",
    )
    final = anthropic_factories.response(
        content=[anthropic_factories.text_block("final answer")],
        stop_reason="end_turn",
    )
    mock_client.messages.create.side_effect = [round1, round2, final]

    tool_manager = MagicMock()
    tool_manager.execute_tool.side_effect = ["outline text", "search text"]

    result = generator.generate_response(
        query="find a course on the same topic as lesson 4 of X",
        tools=_tool_definitions(),
        tool_manager=tool_manager,
    )

    assert result == "final answer"
    assert mock_client.messages.create.call_count == 3
    assert tool_manager.execute_tool.call_count == 2
    first_call, second_call = tool_manager.execute_tool.call_args_list
    assert first_call.args[0] == "get_course_outline"
    assert first_call.kwargs == {"course_name": "X"}
    assert second_call.args[0] == "search_course_content"
    assert second_call.kwargs == {"query": "lesson 4 title"}

    # Round-2 request carries round-1's tool_use + tool_result forward.
    round2_messages = mock_client.messages.create.call_args_list[1].kwargs["messages"]
    assert round2_messages[1]["role"] == "assistant"
    assert round2_messages[2]["role"] == "user"
    assert round2_messages[2]["content"][0]["tool_use_id"] == "t1"


def test_round_two_still_offers_tools(patched_ai_generator, anthropic_factories):
    """The core fix: round 2 must keep offering tools so a dependent search is possible."""
    generator, mock_client = patched_ai_generator

    round1 = anthropic_factories.response(
        content=[
            anthropic_factories.tool_use_block(
                name="search_course_content", tool_input={"query": "a"}
            )
        ],
        stop_reason="tool_use",
    )
    final = anthropic_factories.response(
        content=[anthropic_factories.text_block("answer")], stop_reason="end_turn"
    )
    mock_client.messages.create.side_effect = [round1, final]

    tool_manager = MagicMock()
    tool_manager.execute_tool.return_value = "results"

    generator.generate_response(
        query="q", tools=_tool_definitions(), tool_manager=tool_manager
    )

    second_kwargs = mock_client.messages.create.call_args_list[1].kwargs
    assert second_kwargs["tools"] == _tool_definitions()
    assert second_kwargs["tool_choice"] == {"type": "auto"}


def test_caps_at_two_rounds(patched_ai_generator, anthropic_factories):
    """If Claude still wants a tool after 2 rounds, we make one final no-tools call
    to force a text answer — never a 3rd tool execution."""
    generator, mock_client = patched_ai_generator

    wants_tool = anthropic_factories.response(
        content=[
            anthropic_factories.tool_use_block(
                name="search_course_content", tool_input={"query": "a"}
            )
        ],
        stop_reason="tool_use",
    )
    # Two tool rounds, both wanting a tool, then the forced synthesis text.
    final = anthropic_factories.response(
        content=[anthropic_factories.text_block("capped answer")],
        stop_reason="end_turn",
    )
    mock_client.messages.create.side_effect = [wants_tool, wants_tool, final]

    tool_manager = MagicMock()
    tool_manager.execute_tool.return_value = "results"

    result = generator.generate_response(
        query="q", tools=_tool_definitions(), tool_manager=tool_manager
    )

    assert result == "capped answer"
    assert tool_manager.execute_tool.call_count == 2  # never a 3rd execution
    assert mock_client.messages.create.call_count == 3
    # The final (synthesis) call drops tools to force a text answer.
    final_kwargs = mock_client.messages.create.call_args_list[2].kwargs
    assert "tools" not in final_kwargs
    assert "tool_choice" not in final_kwargs


def test_tool_failure_returns_useful_string(patched_ai_generator, anthropic_factories):
    """A raised tool exception terminates the loop gracefully: no further tool
    rounds, an is_error result is surfaced to Claude, and a real answer is returned."""
    generator, mock_client = patched_ai_generator

    round1 = anthropic_factories.response(
        content=[
            anthropic_factories.tool_use_block(
                name="search_course_content",
                tool_input={"query": "a"},
                block_id="terr",
            )
        ],
        stop_reason="tool_use",
    )
    graceful = anthropic_factories.response(
        content=[anthropic_factories.text_block("graceful answer")],
        stop_reason="end_turn",
    )
    mock_client.messages.create.side_effect = [round1, graceful]

    tool_manager = MagicMock()
    tool_manager.execute_tool.side_effect = RuntimeError("boom")

    result = generator.generate_response(
        query="q", tools=_tool_definitions(), tool_manager=tool_manager
    )

    assert result == "graceful answer"
    assert tool_manager.execute_tool.call_count == 1  # no second round
    assert mock_client.messages.create.call_count == 2

    # The finalize call drops tools and carries an is_error tool_result.
    final_kwargs = mock_client.messages.create.call_args_list[1].kwargs
    assert "tools" not in final_kwargs
    error_block = final_kwargs["messages"][-1]["content"][0]
    assert error_block["type"] == "tool_result"
    assert error_block["is_error"] is True
    assert error_block["tool_use_id"] == "terr"
