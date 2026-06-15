"""ReAct agent orchestrator — the core of PRAgent.

Drives an LLM through a Reason → Act → Observe loop, routing tool calls
through the MCP client to the GitHub MCP server, and persisting the final
structured review to the database.

The LLM is swappable at call time via the provider/model parameters.
Provider-specific SDK code lives in app/agent/llm/; the loop itself is
fully provider-agnostic.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.llm.base import ToolResult
from app.agent.llm.factory import get_provider
from app.agent.language_context import load_language_context
from app.agent.prompts import (
    FORCE_CONCLUDE,
    RETRY_MALFORMED_JSON,
    SYSTEM_PROMPT,
    build_first_user_message,
)
from app.agent.schemas import ReviewOutput
from app.config import settings
from app.mcp.bridge import mcp_tools_to_declarations
from app.mcp.client import MCPClientManager
from app.models import (
    AgentEventType,
    AgentLog,
    Review,
    ReviewComment,
    ReviewStatus,
    Severity,
)

logger = logging.getLogger(__name__)

MAX_ITERATIONS = 15

# ------------------------------------------------------------------
# Timeout constants — generous dead-man switches, not tight SLOs.
# These fire only on genuine hangs (dropped connections, service
# unresponsive) rather than legitimately slow-but-running calls.
# ------------------------------------------------------------------

# Per-MCP-tool-call timeout: 5 minutes.  On timeout the call is treated as
# an ERROR result so the agent can continue rather than crashing the review.
MCP_TOOL_TIMEOUT = 5 * 60

# Overall review deadline: 25 minutes.  If the review hasn't finished within
# this window, mark it FAILED and clean up rather than hanging indefinitely.
REVIEW_TOTAL_TIMEOUT = 25 * 60

# ------------------------------------------------------------------
# File display constants
# ------------------------------------------------------------------

# File name patterns (lowercase substring match) to exclude from the
# changed_files list shown in the first user message.  These are lockfiles,
# generated artefacts, vendored code, and minified assets — files the agent
# should never need to read directly for a code review.
_SKIP_FILE_PATTERNS = (
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "composer.lock",
    "poetry.lock",
    "cargo.lock",
    "gemfile.lock",
    "go.sum",
    ".min.js",
    ".min.css",
    ".pb.go",
    "/vendor/",
    "/node_modules/",
    "/__generated__/",
    "/dist/",
    "/build/",
    "/.next/",
)

# Maximum number of files shown in the first user message.  The agent uses
# tool calls to read files anyway; this just keeps the initial context lean.
_MAX_DISPLAY_FILES = 150

# Maximum number of GitHub issues opened per review.  Opening an unbounded
# number of issues for every critical finding risks API rate limits and
# pollutes the issue tracker.
MAX_GITHUB_ISSUES = 3


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
    provider: str = "gemini",
    model: str | None = None,
) -> int:
    """Run a full agentic PR review and persist results.

    Parameters
    ----------
    provider:
        LLM provider name — ``"gemini"`` or ``"claude"``.
    model:
        Specific model string.  Defaults to the configured default for
        the chosen provider when not supplied.

    Returns the review_id on success.
    """
    owner, repo = repo_full_name.split("/", 1)
    mcp_client = MCPClientManager()
    resolved_model = model or settings.default_model_for(provider)
    llm = get_provider(provider, resolved_model)

    try:
        # Outer dead-man switch: if the review takes longer than
        # REVIEW_TOTAL_TIMEOUT the TimeoutError is caught below, the review is
        # marked FAILED, and the finally block cleans up the MCP client.
        async with asyncio.timeout(REVIEW_TOTAL_TIMEOUT):

            # ---- 1. SETUP ------------------------------------------------
            await _update_review_status(db, review_id, ReviewStatus.REVIEWING)

            logger.info("[review=%d] Connecting to GitHub MCP server…", review_id)
            await mcp_client.connect(github_token)

            mcp_tools = await mcp_client.list_tools()
            tool_dicts = mcp_tools_to_declarations(mcp_tools)
            logger.info(
                "[review=%d] %d tool declarations ready (provider=%s model=%s)",
                review_id, len(tool_dicts), provider, resolved_model,
            )

            # Build the display-safe file list (filtered + capped) for the
            # first user message.  Language detection still uses the full list
            # so extension coverage is accurate regardless of the cap.
            display_files, skipped_count = _filter_files_for_display(changed_files)

            first_user_msg = build_first_user_message(
                owner=owner,
                repo=repo,
                pr_number=pr_number,
                pr_title=pr_title,
                pr_description=pr_description,
                base_branch=base_branch,
                head_branch=head_branch,
                changed_files=display_files,
                skipped_files_count=skipped_count,
                language_context=load_language_context(changed_files),
            )

            # ---- 2. REACT LOOP -------------------------------------------
            review_output: ReviewOutput | None = None

            response = await llm.start(
                system_prompt=SYSTEM_PROMPT,
                tools=tool_dicts,
                first_message=first_user_msg,
            )

            for iteration in range(1, MAX_ITERATIONS + 1):
                logger.info("[review=%d] Iteration %d/%d", review_id, iteration, MAX_ITERATIONS)

                # -- Case A: tool calls from model --------------------------
                if response.has_tool_calls:
                    tool_results: list[ToolResult] = []

                    for tc in response.tool_calls:
                        logger.info(
                            "[review=%d] Tool call: %s(%s)",
                            review_id, tc.name, _trunc(str(tc.args)),
                        )
                        await _log_agent_event(
                            db, review_id, AgentEventType.FETCHING,
                            f"Calling {tc.name}",
                        )

                        if tc.name not in llm.tool_names:
                            logger.warning(
                                "[review=%d] Hallucinated tool '%s' — not in declared set",
                                review_id, tc.name,
                            )
                            result_text = (
                                f"ERROR: Unknown tool '{tc.name}'. "
                                f"Available tools: {sorted(llm.tool_names)}"
                            )
                        else:
                            try:
                                mcp_result = await asyncio.wait_for(
                                    mcp_client.call_tool(tc.name, tc.args),
                                    timeout=MCP_TOOL_TIMEOUT,
                                )
                                result_text = _extract_mcp_text(mcp_result)
                            except asyncio.TimeoutError:
                                logger.warning(
                                    "[review=%d] Tool %s timed out after %ds — returning error to agent",
                                    review_id, tc.name, MCP_TOOL_TIMEOUT,
                                )
                                result_text = (
                                    f"ERROR: Tool '{tc.name}' timed out after "
                                    f"{MCP_TOOL_TIMEOUT}s. Skip this file and continue."
                                )
                            except Exception as exc:
                                logger.warning(
                                    "[review=%d] Tool %s failed: %s",
                                    review_id, tc.name, exc,
                                )
                                result_text = f"ERROR: {exc}"

                        tool_results.append(
                            ToolResult(call_id=tc.id, name=tc.name, content=result_text)
                        )

                    response = await llm.submit_tool_results(tool_results)
                    continue

                # -- Case B: text response ----------------------------------
                text = response.text or ""
                block_type = parse_block_type(text)

                if block_type == "REVIEW_COMPLETE":
                    logger.info("[review=%d] Agent signalled REVIEW_COMPLETE", review_id)
                    await _log_agent_event(db, review_id, AgentEventType.DONE, "Review complete")

                    review_output = _try_parse_review(text)
                    if review_output is None:
                        logger.warning("[review=%d] Malformed JSON — requesting retry (no tools)", review_id)
                        retry_resp = await llm.generate_no_tools(RETRY_MALFORMED_JSON)
                        review_output = _try_parse_review(retry_resp.text or "")

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

                response = await llm.continue_after_thought()

            # -- Force conclude if loop exhausted without REVIEW_COMPLETE ---
            if review_output is None:
                logger.warning("[review=%d] Max iterations reached — forcing conclude (no tools)", review_id)
                force_resp = await llm.generate_no_tools(FORCE_CONCLUDE)
                review_output = _try_parse_review(force_resp.text or "")

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

                # ---- 4. POST TO GITHUB (best-effort) --------------------
                try:
                    saved_comments = await _load_review_comments(db, review_id)
                    if saved_comments:
                        await post_review_to_github(
                            review_id=review_id,
                            repo_full_name=repo_full_name,
                            pr_number=pr_number,
                            comments=saved_comments,
                            mcp_client=mcp_client,
                            db=db,
                        )
                except Exception:
                    logger.exception(
                        "[review=%d] GitHub posting failed — findings are saved in DB",
                        review_id,
                    )
            else:
                logger.error("[review=%d] No valid review output produced", review_id)
                await _update_review_status(db, review_id, ReviewStatus.FAILED)

    except TimeoutError:
        logger.error(
            "[review=%d] Review timed out after %ds — marking FAILED",
            review_id, REVIEW_TOTAL_TIMEOUT,
        )
        await _update_review_status(db, review_id, ReviewStatus.FAILED)

    except Exception:
        logger.exception("[review=%d] Review failed with exception", review_id)
        await _update_review_status(db, review_id, ReviewStatus.FAILED)
        raise

    finally:
        if mcp_client.is_connected:
            await mcp_client.disconnect()

    return review_id


# ------------------------------------------------------------------
# File display helpers
# ------------------------------------------------------------------


def _filter_files_for_display(files: list[str]) -> tuple[list[str], int]:
    """Filter and cap the changed-files list for display in the first user message.

    Returns ``(display_list, total_skipped_count)``.

    Filtering removes lockfiles, generated artefacts, vendored directories,
    and minified assets — files that are large, rarely meaningful for review,
    and that the agent should not waste tool-call iterations reading.

    The display list is then capped at ``_MAX_DISPLAY_FILES`` entries.  The
    agent uses ``get_file_contents`` tool calls to read files anyway; a shorter
    initial list keeps the first user message lean.

    Language detection (``load_language_context``) is always called with the
    original unfiltered list so that extension coverage is accurate.
    """
    # Prepend "/" so that directory patterns like "/dist/" match both
    # "dist/bundle.js" (repo root) and "src/dist/bundle.js" (subdirectory)
    # without also matching "src/distutils.py".
    kept = [
        f for f in files
        if not any(p in ("/" + f.lower()) for p in _SKIP_FILE_PATTERNS)
    ]
    total_skipped = len(files) - len(kept)

    if len(kept) > _MAX_DISPLAY_FILES:
        total_skipped += len(kept) - _MAX_DISPLAY_FILES
        kept = kept[:_MAX_DISPLAY_FILES]

    return kept, total_skipped


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

        logger.debug(
            "Skipping non-review JSON object: keys=%s",
            list(parsed.keys()) if isinstance(parsed, dict) else type(parsed),
        )
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


async def _load_review_comments(
    db: AsyncSession, review_id: int
) -> list[ReviewComment]:
    """Load all ReviewComment rows for a given review."""
    from sqlalchemy import select

    result = await db.execute(
        select(ReviewComment).where(ReviewComment.review_id == review_id)
    )
    return list(result.scalars().all())


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


# ------------------------------------------------------------------
# Post review to GitHub via MCP
# ------------------------------------------------------------------


async def post_review_to_github(
    *,
    review_id: int,
    repo_full_name: str,
    pr_number: int,
    comments: list[ReviewComment],
    mcp_client: MCPClientManager,
    db: AsyncSession,
) -> None:
    """Post saved review findings to GitHub as a PR review with inline comments.

    Reuses the already-connected ``mcp_client`` from ``run_review`` — no
    second Docker container is spawned.  Creates a pending review, attaches
    inline comments for findings that have valid file_path + line_number,
    submits the review, and opens GitHub issues (capped at
    ``MAX_GITHUB_ISSUES``) for critical findings.  Failures here never fail
    the overall review — the findings are already persisted in the DB.
    """
    owner, repo = repo_full_name.split("/", 1)

    critical = [c for c in comments if c.severity == Severity.CRITICAL]
    warnings = [c for c in comments if c.severity == Severity.WARNING]
    infos = [c for c in comments if c.severity == Severity.INFO]

    review_body = (
        f"**PRAgent automated review** — "
        f"{len(critical)} critical, {len(warnings)} warnings, {len(infos)} info"
    )

    await _log_agent_event(db, review_id, AgentEventType.POSTING, "Posting review to GitHub")

    # -- Step 1: Create a pending review on the PR ------------------
    try:
        await mcp_client.call_tool(
            "pull_request_review_write",
            {
                "owner": owner,
                "repo": repo,
                "pullNumber": pr_number,
                "method": "create",
                "body": review_body,
            },
        )
        logger.info("[review=%d] Created pending GitHub review", review_id)
    except Exception:
        logger.exception("[review=%d] Failed to create pending review", review_id)

    # -- Step 2: Add inline comments for each finding ---------------
    posted_count = 0
    for c in comments:
        if not c.file_path or not c.line_number:
            continue

        body_parts = [f"**[{c.severity.value.upper()}] {c.category.value.replace('_', ' ').title()}**\n"]
        body_parts.append(c.body)
        if c.fix_suggestion:
            body_parts.append(f"\n💡 **Suggested fix:**\n{c.fix_suggestion}")
        comment_body = "\n".join(body_parts)

        try:
            await mcp_client.call_tool(
                "add_comment_to_pending_review",
                {
                    "owner": owner,
                    "repo": repo,
                    "pullNumber": pr_number,
                    "path": c.file_path,
                    "line": c.line_number,
                    "body": comment_body,
                    "subjectType": "LINE",
                },
            )
            posted_count += 1
        except Exception:
            logger.warning(
                "[review=%d] Failed to post inline comment on %s:%d — skipping",
                review_id, c.file_path, c.line_number,
                exc_info=True,
            )

    logger.info("[review=%d] Posted %d/%d inline comments", review_id, posted_count, len(comments))

    # -- Step 3: Submit the review ----------------------------------
    submit_event = "REQUEST_CHANGES" if critical else "COMMENT"
    try:
        await mcp_client.call_tool(
            "pull_request_review_write",
            {
                "owner": owner,
                "repo": repo,
                "pullNumber": pr_number,
                "method": "submit_pending",
                "event": submit_event,
                "body": review_body,
            },
        )
        logger.info("[review=%d] Submitted review with event=%s", review_id, submit_event)
    except Exception:
        logger.exception("[review=%d] Failed to submit review — trying COMMENT fallback", review_id)
        try:
            await mcp_client.call_tool(
                "pull_request_review_write",
                {
                    "owner": owner,
                    "repo": repo,
                    "pullNumber": pr_number,
                    "method": "submit_pending",
                    "event": "COMMENT",
                    "body": review_body,
                },
            )
        except Exception:
            logger.exception("[review=%d] Fallback submit also failed", review_id)

    # -- Step 4: Open issues for critical findings (capped) ---------
    issues_to_open = critical[:MAX_GITHUB_ISSUES]
    if len(critical) > MAX_GITHUB_ISSUES:
        logger.info(
            "[review=%d] Capping GitHub issue creation at %d (had %d critical findings)",
            review_id, MAX_GITHUB_ISSUES, len(critical),
        )

    for c in issues_to_open:
        issue_title = f"PRAgent: {c.category.value.replace('_', ' ').title()} issue in {c.file_path}"
        issue_body = (
            f"**Severity:** {c.severity.value}\n"
            f"**File:** `{c.file_path}` (line {c.line_number})\n"
            f"**PR:** #{pr_number}\n\n"
            f"### Description\n{c.body}\n"
        )
        if c.fix_suggestion:
            issue_body += f"\n### Suggested Fix\n{c.fix_suggestion}\n"

        try:
            await mcp_client.call_tool(
                "issue_write",
                {
                    "owner": owner,
                    "repo": repo,
                    "method": "create",
                    "title": issue_title,
                    "body": issue_body,
                    "labels": ["bug", "pr-agent"],
                },
            )
            logger.info("[review=%d] Opened issue for critical finding in %s", review_id, c.file_path)
        except Exception:
            logger.warning(
                "[review=%d] Failed to open issue for %s — skipping",
                review_id, c.file_path,
                exc_info=True,
            )

    # -- Step 5: Mark as posted in DB -------------------------------
    review = await db.get(Review, review_id)
    if review:
        review.github_review_posted = True
        await db.commit()

    await _log_agent_event(db, review_id, AgentEventType.DONE, "Posted review to GitHub")
