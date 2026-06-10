import anthropic
from typing import List, Optional, Dict, Any

class AIGenerator:
    """Handles interactions with Anthropic's Claude API for generating responses"""
    
    # Static system prompt to avoid rebuilding on each call
    SYSTEM_PROMPT = """ You are an AI assistant specialized in course materials and educational content with access to tools for course information.

Tool Usage:
- **search_course_content** — use for questions about specific course *content* or detailed educational materials (what a lesson teaches, explanations, examples).
- **get_course_outline** — use for questions about a course's *outline, structure, syllabus, or lesson list*. When answering an outline query, return the course title, the course link, and every lesson's number and title.
- **Up to two tool calls per query, made in sequence.** You may call a tool, observe its result, reason about it, and then make ONE more tool call if the first result is insufficient. Use a second call when the answer depends on the first — for example, get a course outline to find a lesson's title, then search course content for that title; or gather information from different courses or lessons to compare them.
- If a single tool call fully answers the question, just answer — do not make a second call.
- After at most two tool calls, answer using the information gathered. Do not ask to keep searching.
- Synthesize tool results into accurate, fact-based responses
- If a tool yields no results, state this clearly without offering alternatives

Response Protocol:
- **General knowledge questions**: Answer using existing knowledge without using tools
- **Course content questions**: Search first, then answer
- **Course outline/structure questions**: Use the outline tool first, then answer
- **Complex or comparative questions**: Gather the needed information across at most two sequential tool calls, then answer
- **No meta-commentary**:
 - Provide direct answers only — no reasoning process, search explanations, or question-type analysis
 - Do not mention "based on the search results"


All responses must be:
1. **Brief, Concise and focused** - Get to the point quickly
2. **Educational** - Maintain instructional value
3. **Clear** - Use accessible language
4. **Example-supported** - Include relevant examples when they aid understanding
Provide only the direct answer to what was asked.
"""

    # Maximum number of sequential tool-calling rounds per user query.
    MAX_TOOL_ROUNDS = 2
    
    def __init__(self, api_key: str, model: str):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model
        
        # Pre-build base API parameters
        self.base_params = {
            "model": self.model,
            "temperature": 0,
            "max_tokens": 800
        }
    
    def generate_response(self, query: str,
                         conversation_history: Optional[str] = None,
                         tools: Optional[List] = None,
                         tool_manager=None) -> str:
        """
        Generate AI response with optional sequential tool usage and conversation context.

        Claude may make up to ``MAX_TOOL_ROUNDS`` tool calls in separate API rounds,
        reasoning about each round's results before deciding whether to call another
        tool. The loop terminates when (a) the round budget is exhausted, (b) Claude
        returns a response with no tool_use blocks, or (c) a tool execution raises.

        Args:
            query: The user's question or request
            conversation_history: Previous messages for context
            tools: Available tools the AI can use
            tool_manager: Manager to execute tools

        Returns:
            Generated response as string
        """

        # Build system content efficiently - avoid string ops when possible.
        # Built once and reused on every round so conversation context is preserved.
        system_content = (
            f"{self.SYSTEM_PROMPT}\n\nPrevious conversation:\n{conversation_history}"
            if conversation_history
            else self.SYSTEM_PROMPT
        )

        # Accumulate the conversation as it grows across tool rounds.
        messages: List[Dict[str, Any]] = [{"role": "user", "content": query}]

        for _ in range(self.MAX_TOOL_ROUNDS):
            response = self._call_model(messages, system_content, tools)

            # Termination (b): Claude answered directly (or we can't run tools).
            if response.stop_reason != "tool_use" or not tool_manager:
                return self._first_text(response)

            # Record Claude's tool-use turn (preserves tool_use ids for the results).
            messages.append({"role": "assistant", "content": response.content})

            try:
                tool_results = self._run_tools(response, tool_manager)
            except Exception as exc:
                # Termination (c): a tool raised. Surface the error to Claude and
                # ask it to answer gracefully with whatever it has.
                messages.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": self._first_tool_use_id(response),
                        "content": f"Tool execution failed: {exc}",
                        "is_error": True,
                    }],
                })
                return self._finalize_without_tools(messages, system_content)

            messages.append({"role": "user", "content": tool_results})

        # Termination (a): round budget exhausted but Claude still wanted a tool.
        # Force a final text answer by calling once more without tools.
        return self._finalize_without_tools(messages, system_content)

    def _call_model(self, messages: List[Dict[str, Any]], system_content: str,
                    tools: Optional[List]):
        """Make a single Claude API call, offering tools when available."""
        api_params = {
            **self.base_params,
            "messages": messages,
            "system": system_content,
        }
        if tools:
            api_params["tools"] = tools
            api_params["tool_choice"] = {"type": "auto"}
        return self.client.messages.create(**api_params)

    def _run_tools(self, response, tool_manager) -> List[Dict[str, Any]]:
        """Execute every tool_use block in a response and return tool_result blocks.

        Raises whatever the tool execution raises (caught by the caller to terminate
        the loop gracefully).
        """
        tool_results = []
        for content_block in response.content:
            if content_block.type == "tool_use":
                tool_result = tool_manager.execute_tool(
                    content_block.name,
                    **content_block.input
                )
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": content_block.id,
                    "content": tool_result,
                })
        return tool_results

    def _finalize_without_tools(self, messages: List[Dict[str, Any]],
                                system_content: str) -> str:
        """Make a final call with no tools, forcing Claude to produce a text answer."""
        final_response = self.client.messages.create(
            **self.base_params,
            messages=messages,
            system=system_content,
        )
        return self._first_text(final_response)

    @staticmethod
    def _first_text(response) -> str:
        """Return the first text block's content, or '' if there is none.

        Safer than ``response.content[0].text``: a tool_use-only response has no
        text block at index 0.
        """
        for content_block in response.content:
            if getattr(content_block, "type", None) == "text":
                return content_block.text
        return ""

    @staticmethod
    def _first_tool_use_id(response) -> str:
        """Return the id of the first tool_use block (for an error tool_result)."""
        for content_block in response.content:
            if content_block.type == "tool_use":
                return content_block.id
        return ""