"""Gemini (Google) LLM provider for the PRAgent ReAct loop.

Extracted from orchestrator.py so the loop itself stays provider-agnostic.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

from google import genai
from google.genai import types as genai_types

from app.agent.llm.base import LLMProvider, LLMResponse, ToolCall, ToolResult
from app.config import settings

logger = logging.getLogger(__name__)

# Maximum time (seconds) to wait for a single Gemini API call.  Fires only on
# genuine hangs (dropped connection, service unresponsive) — well above the
# typical p99 latency of any real generation.
LLM_CALL_TIMEOUT = 5 * 60

# Upper bound on generated tokens per call.  Covers any REVIEW_COMPLETE JSON
# output (even 30+ findings with long suggestions) and verbose THOUGHT messages.
MAX_OUTPUT_TOKENS = 8192


class GeminiProvider(LLMProvider):
    """Drives the ReAct loop via the Google Gemini API."""

    def __init__(self, model: str) -> None:
        self._model = model
        self._client = genai.Client(api_key=settings.gemini_api_key)
        self._contents: list[genai_types.Content] = []
        self._config: genai_types.GenerateContentConfig | None = None
        self._json_only_config: genai_types.GenerateContentConfig | None = None
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
        tool_declarations = [
            genai_types.FunctionDeclaration(
                name=t["name"],
                description=t["description"],
                parameters_json_schema=t["parameters"],
            )
            for t in tools
        ]
        self._tool_names = {t["name"] for t in tools}

        self._config = genai_types.GenerateContentConfig(
            system_instruction=system_prompt,
            tools=[genai_types.Tool(function_declarations=tool_declarations)],
            tool_config=genai_types.ToolConfig(
                function_calling_config=genai_types.FunctionCallingConfig(
                    mode="VALIDATED",
                ),
            ),
            max_output_tokens=MAX_OUTPUT_TOKENS,
        )
        self._json_only_config = genai_types.GenerateContentConfig(
            system_instruction=system_prompt,
            max_output_tokens=MAX_OUTPUT_TOKENS,
        )

        self._contents = [
            genai_types.Content(
                role="user", parts=[genai_types.Part(text=first_message)]
            )
        ]
        return await self._generate()

    async def submit_tool_results(self, results: list[ToolResult]) -> LLMResponse:
        # Prune previous rounds' raw tool responses from history before appending
        # the new ones.  The model already processed the earlier results and
        # reasoned about them in THOUGHT messages; keeping their full text only
        # bloats the context on every subsequent API call.
        self._prune_previous_tool_results()

        fn_response_parts = [
            genai_types.Part(
                function_response=genai_types.FunctionResponse(
                    name=r.name,
                    response={"result": r.content},
                )
            )
            for r in results
        ]
        self._contents.append(
            genai_types.Content(role="user", parts=fn_response_parts)
        )
        return await self._generate()

    async def continue_after_thought(self) -> LLMResponse:
        # Gemini can generate a continuation when the last message in
        # contents is a model-role text block; no extra user turn needed.
        return await self._generate()

    async def generate_no_tools(self, message: str) -> LLMResponse:
        self._contents.append(
            genai_types.Content(role="user", parts=[genai_types.Part(text=message)])
        )
        async with asyncio.timeout(LLM_CALL_TIMEOUT):
            response = await self._client.aio.models.generate_content(
                model=self._model,
                contents=self._contents,
                config=self._json_only_config,
            )
        text = response.text or ""
        self._contents.append(
            genai_types.Content(role="model", parts=[genai_types.Part(text=text)])
        )
        return LLMResponse(text=text)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _generate(self) -> LLMResponse:
        async with asyncio.timeout(LLM_CALL_TIMEOUT):
            response = await self._client.aio.models.generate_content(
                model=self._model,
                contents=self._contents,
                config=self._config,
            )

        if response.function_calls:
            model_content = response.candidates[0].content
            self._contents.append(model_content)
            tool_calls = [
                ToolCall(
                    id=str(uuid.uuid4()),
                    name=fc.name,
                    args=dict(fc.args) if fc.args else {},
                )
                for fc in response.function_calls
            ]
            logger.debug("Gemini returned %d tool call(s)", len(tool_calls))
            return LLMResponse(tool_calls=tool_calls)

        text = response.text or ""
        self._contents.append(
            genai_types.Content(role="model", parts=[genai_types.Part(text=text)])
        )
        return LLMResponse(text=text)

    def _prune_previous_tool_results(self) -> None:
        """Replace old tool-result payloads in history with compact placeholders.

        Called at the start of ``submit_tool_results`` so that by the time new
        results are appended, every previous function_response in ``_contents``
        has been replaced with a one-line summary.  The model got the full
        content when it originally processed the result; the summary preserves
        traceability without re-sending kilobytes of file content on every
        subsequent API call.
        """
        for i, content in enumerate(self._contents):
            if content.role != "user":
                continue
            pruned_parts: list[genai_types.Part] = []
            was_pruned = False
            for part in content.parts:
                if part.function_response is not None:
                    name = part.function_response.name
                    result_str = str(
                        (part.function_response.response or {}).get("result", "")
                    )
                    summary = (
                        f"[Tool: {name} — {len(result_str)} chars, already processed]"
                    )
                    pruned_parts.append(genai_types.Part(text=summary))
                    was_pruned = True
                else:
                    pruned_parts.append(part)
            if was_pruned:
                self._contents[i] = genai_types.Content(
                    role="user", parts=pruned_parts
                )
