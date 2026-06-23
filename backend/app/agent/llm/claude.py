"""Claude (Anthropic) LLM provider for the PRAgent ReAct loop.

Key wire-format differences from Gemini that this module hides:
- Tool declarations: {name, description, input_schema} instead of FunctionDeclaration
- Tool calls returned as content blocks with type="tool_use"
- Tool results returned as user-role content blocks with type="tool_result"
- After every assistant message Claude requires a user turn to continue;
  continue_after_thought() inserts a brief "Continue." message for this.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import anthropic

from app.agent.llm.base import LLMProvider, LLMResponse, ToolCall, ToolResult
from app.config import settings

logger = logging.getLogger(__name__)

# Maximum time (seconds) to wait for a single Claude API call.
LLM_CALL_TIMEOUT = 5 * 60


class ClaudeProvider(LLMProvider):
    """Drives the ReAct loop via the Anthropic Claude API."""

    def __init__(self, model: str) -> None:
        self._model = model
        self._client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        self._messages: list[dict[str, Any]] = []
        self._tools: list[dict[str, Any]] = []
        self._system_prompt: str = ""
        self._tool_names: set[str] = set()

    @property
    def tool_names(self) -> set[str]:
        return self._tool_names

    async def start(
        self,
        *,
        system_prompt: str,
        tools: list[dict[str, Any]],
        first_message: str,
    ) -> LLMResponse:
        self._system_prompt = system_prompt
        # Convert MCP-format tool dicts to Anthropic's schema format.
        self._tools = [
            {
                "name": t["name"],
                "description": t["description"],
                "input_schema": t["parameters"],
            }
            for t in tools
        ]
        self._tool_names = {t["name"] for t in tools}
        self._messages = [{"role": "user", "content": first_message}]
        return await self._generate()

    async def submit_tool_results(self, results: list[ToolResult]) -> LLMResponse:
        # Prune previous rounds' raw tool responses from history before appending
        # the new ones.  The model already processed the earlier results and
        # reasoned about them in THOUGHT messages; keeping their full text only
        # bloats the context on every subsequent API call.
        self._prune_previous_tool_results()

        tool_result_blocks = [
            {
                "type": "tool_result",
                "tool_use_id": r.call_id,
                "content": r.content,
            }
            for r in results
        ]
        self._messages.append({"role": "user", "content": tool_result_blocks})
        return await self._generate()

    async def continue_after_thought(self) -> LLMResponse:
        # Claude requires alternating user/assistant turns. After the model
        # produces a THOUGHT text we must add a user turn before generating.
        self._messages.append({"role": "user", "content": "Continue."})
        return await self._generate()

    async def generate_no_tools(self, message: str) -> LLMResponse:
        self._messages.append({"role": "user", "content": message})
        async with asyncio.timeout(LLM_CALL_TIMEOUT):
            response = await self._client.messages.create(
                model=self._model,
                max_tokens=8096,
                system=self._system_prompt,
                messages=self._messages,
            )
        text = _extract_text(response)
        self._messages.append({"role": "assistant", "content": response.content})
        return LLMResponse(text=text)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _generate(self) -> LLMResponse:
        async with asyncio.timeout(LLM_CALL_TIMEOUT):
            response = await self._client.messages.create(
                model=self._model,
                max_tokens=8096,
                system=self._system_prompt,
                tools=self._tools,
                messages=self._messages,
            )
        # Always append the raw assistant content to history first.
        self._messages.append({"role": "assistant", "content": response.content})

        tool_use_blocks = [b for b in response.content if b.type == "tool_use"]
        if tool_use_blocks:
            tool_calls = [
                ToolCall(
                    id=b.id,
                    name=b.name,
                    args=dict(b.input) if b.input else {},
                )
                for b in tool_use_blocks
            ]
            logger.debug("Claude returned %d tool call(s)", len(tool_calls))
            return LLMResponse(tool_calls=tool_calls)

        return LLMResponse(text=_extract_text(response))

    def _prune_previous_tool_results(self) -> None:
        """Compact old tool-result payloads in history to save context tokens.

        Called at the start of ``submit_tool_results`` so that by the time new
        results are appended, every previous tool_result block in ``_messages``
        has its content replaced with a short summary.

        IMPORTANT: We keep the ``tool_result`` block structure and
        ``tool_use_id`` intact.  Claude requires every ``tool_use`` in an
        assistant message to be answered by a matching ``tool_result`` in the
        very next user message — replacing the whole message with a plain
        string breaks that pairing and causes a 400 error.
        """
        for i, msg in enumerate(self._messages):
            if msg["role"] != "user" or not isinstance(msg["content"], list):
                continue
            if not any(
                isinstance(b, dict) and b.get("type") == "tool_result"
                for b in msg["content"]
            ):
                continue
            pruned_blocks: list[dict] = []
            for block in msg["content"]:
                if not (isinstance(block, dict) and block.get("type") == "tool_result"):
                    pruned_blocks.append(block)
                    continue
                content = block.get("content", "")
                length = len(content) if isinstance(content, str) else len(str(content))
                pruned_blocks.append({
                    "type": "tool_result",
                    "tool_use_id": block["tool_use_id"],
                    "content": f"[Result truncated — {length} chars, already processed]",
                })
            self._messages[i] = {"role": "user", "content": pruned_blocks}


def _extract_text(response: anthropic.types.Message) -> str:
    """Pull the first text block from a Claude message response."""
    for block in response.content:
        if hasattr(block, "type") and block.type == "text":
            return block.text
    return ""
