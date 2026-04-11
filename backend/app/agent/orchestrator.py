"""ReAct agent orchestrator — the core of PRAgent.

Drives a Gemini 2.5 Flash model through a Reason → Act → Observe loop,
routing tool calls through the MCP client to the GitHub MCP server, and
persisting the final structured review to the database.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from google import genai
from google.genai import types as genai_types
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.prompts import (
    FORCE_CONCLUDE,
    RETRY_MALFORMED_JSON,
    SYSTEM_PROMPT,
    build_first_user_message,
)
from app.agent.schemas import ReviewOutput
from app.config import settings
from app.mcp.bridge import mcp_tools_to_gemini_declarations
from app.mcp.client import MCPClientManager
from app.models import (
    AgentEventType,
    AgentLog,
    Review,
    ReviewComment,
    ReviewStatus,
)

logger = logging.getLogger(__name__)

MAX_ITERATIONS = 15


# ------------------------------------------------------------------
# Public entry-point
# ------------------------------------------------------------------


async def run_review(
    *,
    repo_full_name: str,
    pr_number: int,
    pr_title: str,
    pr_description: str,
    base_branch: str,
    head_branch: str,
    changed_files: list[str],
    github_token: str,
    review_id: int,
    db: AsyncSession,
) -> int:
    """Run a full agentic PR review and persist results.

    Returns the review_id on success.
    """
    owner, repo = repo_full_name.split("/", 1)
    client = MCPClientManager()

    try:
        # ---- 1. SETUP ------------------------------------------------
        await _update_review_status(db, review_id, ReviewStatus.REVIEWING)

        logger.info("[review=%d] Connecting to GitHub MCP server…", review_id)
        await client.connect(github_token)

        mcp_tools = await client.list_tools()
        gemini_decls = mcp_tools_to_gemini_declarations(mcp_tools)
        logger.info(
            "[review=%d] %d Gemini tool declarations ready",
            review_id,
            len(gemini_decls),
        )

        gemini = genai.Client(api_key=settings.gemini_api_key)

        tool_declarations = [
            genai_types.FunctionDeclaration(
                name=d["name"],
                description=d["description"],
                parameters_json_schema=d["parameters"],
            )
            for d in gemini_decls
        ]

        first_user_msg = build_first_user_message(
            owner=owner,
            repo=repo,
            pr_number=pr_number,
            pr_title=pr_title,
            pr_description=pr_description,
            base_branch=base_branch,
            head_branch=head_branch,
            changed_files=changed_files,
        )

        contents: list[genai_types.Content] = [
            genai_types.Content(role="user", parts=[genai_types.Part(text=first_user_msg)]),
        ]

        config = genai_types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            tools=[genai_types.Tool(function_declarations=tool_declarations)],
            tool_config=genai_types.ToolConfig(
                function_calling_config=genai_types.FunctionCallingConfig(
                    mode="VALIDATED",
                ),
            ),
        )

        declared_names = {d["name"] for d in gemini_decls}

        json_only_config = genai_types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
        )

        # ---- 2. REACT LOOP -------------------------------------------
        review_output: ReviewOutput | None = None

        for iteration in range(1, MAX_ITERATIONS + 1):
            logger.info("[review=%d] Iteration %d/%d", review_id, iteration, MAX_ITERATIONS)

            response = await gemini.aio.models.generate_content(
                model=settings.gemini_model,
                contents=contents,
                config=config,
            )

            # -- Case A: function call(s) from model --------------------
            if response.function_calls:
                model_content = response.candidates[0].content
                contents.append(model_content)

                fn_response_parts: list[genai_types.Part] = []

                for fc in response.function_calls:
                    tool_name = fc.name
                    tool_args = fc.args or {}

                    logger.info(
                        "[review=%d] Tool call: %s(%s)",
                        review_id, tool_name, _trunc(str(tool_args)),
                    )
                    await _log_agent_event(
                        db, review_id, AgentEventType.FETCHING,
                        f"Calling {tool_name}",
                    )

                    if tool_name not in declared_names:
                        logger.warning(
                            "[review=%d] Hallucinated tool '%s' — not in declared set",
                            review_id, tool_name,
                        )
                        result_text = (
                            f"ERROR: Unknown tool '{tool_name}'. "
                            f"Available tools: {sorted(declared_names)}"
                        )
                    else:
                        try:
                            mcp_result = await client.call_tool(tool_name, tool_args)
                            result_text = _extract_mcp_text(mcp_result)
                        except Exception as exc:
                            logger.warning(
                                "[review=%d] Tool %s failed: %s",
                                review_id, tool_name, exc,
                            )
                            result_text = f"ERROR: {exc}"

                    fn_response_parts.append(
                        genai_types.Part(
                            function_response=genai_types.FunctionResponse(
                                name=tool_name,
                                response={"result": result_text},
                            )
                        )
                    )

                contents.append(
                    genai_types.Content(role="user", parts=fn_response_parts)
                )
                continue

            # -- Case B: text response ----------------------------------
            text = response.text or ""
            block_type = parse_block_type(text)

            contents.append(
                genai_types.Content(
                    role="model",
                    parts=[genai_types.Part(text=text)],
                )
            )

            if block_type == "REVIEW_COMPLETE":
                logger.info("[review=%d] Agent signalled REVIEW_COMPLETE", review_id)
                await _log_agent_event(db, review_id, AgentEventType.DONE, "Review complete")

                review_output = _try_parse_review(text)
                if review_output is None:
                    logger.warning("[review=%d] Malformed JSON — requesting retry (no tools)", review_id)
                    contents.append(
                        genai_types.Content(
                            role="user",
                            parts=[genai_types.Part(text=RETRY_MALFORMED_JSON)],
                        )
                    )
                    retry_resp = await gemini.aio.models.generate_content(
                        model=settings.gemini_model,
                        contents=contents,
                        config=json_only_config,
                    )
                    retry_text = retry_resp.text or ""
                    contents.append(
                        genai_types.Content(
                            role="model",
                            parts=[genai_types.Part(text=retry_text)],
                        )
                    )
                    review_output = _try_parse_review(retry_text)

                break

            elif block_type == "THOUGHT":
                thought_content = text.split("THOUGHT:", 1)[-1].strip()[:200]
                logger.info("[review=%d] Thought: %s", review_id, thought_content)
                await _log_agent_event(
                    db, review_id, AgentEventType.THINKING, thought_content,
                )

            else:
                logger.info("[review=%d] Agent text (type=%s)", review_id, block_type)
                await _log_agent_event(
                    db, review_id, AgentEventType.THINKING, text[:200],
                )

        # -- Force conclude if loop exhausted without REVIEW_COMPLETE ---
        if review_output is None:
            logger.warning("[review=%d] Max iterations reached — forcing conclude (no tools)", review_id)
            contents.append(
                genai_types.Content(
                    role="user",
                    parts=[genai_types.Part(text=FORCE_CONCLUDE)],
                )
            )
            force_resp = await gemini.aio.models.generate_content(
                model=settings.gemini_model,
                contents=contents,
                config=json_only_config,
            )
            force_text = force_resp.text or ""
            review_output = _try_parse_review(force_text)

        # ---- 3. PERSIST RESULTS --------------------------------------
        if review_output is not None:
            review_output.recompute_stats()
            await _save_review_results(db, review_id, review_output)
            await _update_review_status(db, review_id, ReviewStatus.COMPLETED)
            logger.info(
                "[review=%d] Saved %d comments (C:%d W:%d I:%d)",
                review_id,
                len(review_output.comments),
                review_output.stats.critical,
                review_output.stats.warning,
                review_output.stats.info,
            )
        else:
            logger.error("[review=%d] No valid review output produced", review_id)
            await _update_review_status(db, review_id, ReviewStatus.FAILED)

    except Exception:
        logger.exception("[review=%d] Review failed with exception", review_id)
        await _update_review_status(db, review_id, ReviewStatus.FAILED)
        raise

    finally:
        if client.is_connected:
            await client.disconnect()

    return review_id


# ------------------------------------------------------------------
# Parsing helpers
# ------------------------------------------------------------------


REVIEW_MARKER = "---REVIEW_COMPLETE---"


def parse_block_type(text: str) -> str:
    """Classify a model text response into REVIEW_COMPLETE, THOUGHT, or UNKNOWN.

    Uses the distinctive ---REVIEW_COMPLETE--- marker to avoid false positives
    from code snippets that happen to contain "REVIEW_COMPLETE".
    """
    if REVIEW_MARKER in text:
        return "REVIEW_COMPLETE"
    if re.search(r"^THOUGHT\s*:", text, re.IGNORECASE | re.MULTILINE):
        return "THOUGHT"
    return "UNKNOWN"


REQUIRED_REVIEW_KEYS = {"summary", "comments"}


def extract_review_json(text: str) -> dict[str, Any] | None:
    """Extract the JSON object following the ---REVIEW_COMPLETE--- marker.

    Handles:
    - Raw JSON after the marker
    - JSON wrapped in ```json ... ``` fences
    - Multiple { } blocks (skips non-review objects like code snippets)
    """
    idx = text.find(REVIEW_MARKER)
    if idx == -1:
        return None

    after_marker = text[idx + len(REVIEW_MARKER):]

    # Strip markdown fences if present
    fence_pattern = re.compile(r"```(?:json)?\s*\n?(.*?)\n?\s*```", re.DOTALL)
    fence_match = fence_pattern.search(after_marker)
    if fence_match:
        after_marker = fence_match.group(1)

    # Try each top-level { } block until we find one that parses as valid
    # review JSON (has "summary" and "comments" keys). This skips code
    # snippets the model may have included before the actual JSON.
    search_from = 0
    while True:
        brace_start = after_marker.find("{", search_from)
        if brace_start == -1:
            logger.error(
                "No valid review JSON found after %s. Raw text:\n%s",
                REVIEW_MARKER, after_marker[:500],
            )
            return None

        depth = 0
        end = -1
        for i, ch in enumerate(after_marker[brace_start:], start=brace_start):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = i
                    break

        if end == -1:
            logger.error("Unbalanced braces in JSON. Raw text:\n%s", after_marker[:500])
            return None

        candidate = after_marker[brace_start : end + 1]

        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            search_from = end + 1
            continue

        if isinstance(parsed, dict) and REQUIRED_REVIEW_KEYS.issubset(parsed.keys()):
            return parsed

        logger.debug("Skipping non-review JSON object: keys=%s", list(parsed.keys()) if isinstance(parsed, dict) else type(parsed))
        search_from = end + 1


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------


def _try_parse_review(text: str) -> ReviewOutput | None:
    """Attempt to parse REVIEW_COMPLETE JSON into a validated ReviewOutput."""
    raw = extract_review_json(text)
    if raw is None:
        return None
    try:
        return ReviewOutput.model_validate(raw)
    except Exception as exc:
        logger.error("ReviewOutput validation failed: %s\nRaw dict: %s", exc, str(raw)[:500])
        return None


def _extract_mcp_text(result: Any) -> str:
    """Pull plain text from an MCP CallToolResult."""
    parts: list[str] = []
    for item in result.content:
        if hasattr(item, "text"):
            parts.append(item.text)
    return "\n".join(parts) if parts else "(no text content)"


def _trunc(s: str, max_len: int = 150) -> str:
    return s if len(s) <= max_len else s[:max_len] + "…"


async def _update_review_status(
    db: AsyncSession, review_id: int, status: ReviewStatus
) -> None:
    review = await db.get(Review, review_id)
    if review:
        review.status = status
        await db.commit()


async def _log_agent_event(
    db: AsyncSession,
    review_id: int,
    event_type: AgentEventType,
    content: str,
) -> None:
    log = AgentLog(review_id=review_id, event_type=event_type, content=content[:2000])
    db.add(log)
    await db.commit()


async def _save_review_results(
    db: AsyncSession, review_id: int, output: ReviewOutput
) -> None:
    review = await db.get(Review, review_id)
    if not review:
        logger.error("Review %d not found when saving results", review_id)
        return

    review.total_comments = len(output.comments)
    review.critical_count = output.stats.critical
    review.warning_count = output.stats.warning
    review.info_count = output.stats.info

    for c in output.comments:
        comment = ReviewComment(
            review_id=review_id,
            file_path=c.file,
            line_number=c.line,
            category=c.category_enum,
            severity=c.severity_enum,
            body=c.comment,
            fix_suggestion=c.suggestion if c.suggestion else None,
        )
        db.add(comment)

    await db.commit()
