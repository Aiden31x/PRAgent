"""Review endpoints — trigger and query PR reviews."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncGenerator

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.agent.orchestrator import (
    post_review_to_github,
    run_review,
    subscribe_review,
    unsubscribe_review,
)
from app.auth.dependencies import get_current_user
from app.config import settings
from app.database import async_session, get_db
from app.models import AgentLog, Repo, Review, ReviewComment, ReviewStatus, User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/reviews", tags=["reviews"])


# ------------------------------------------------------------------
# Schemas
# ------------------------------------------------------------------


class TriggerReviewRequest(BaseModel):
    repo_id: int
    pr_number: int
    pr_title: str = ""
    pr_description: str = ""
    base_branch: str = "main"
    head_branch: str = ""
    changed_files: list[str] = []
    provider: str | None = None   # "gemini" or "claude"; falls back to user preference
    model: str | None = None      # specific model string; falls back to provider default


class TriggerReviewResponse(BaseModel):
    review_id: int
    status: str
    findings_count: int
    llm_provider: str
    llm_model: str


class ReviewCommentResponse(BaseModel):
    id: int
    file_path: str
    line_number: int
    category: str
    severity: str
    body: str
    fix_suggestion: str | None


class ReviewDetailResponse(BaseModel):
    id: int
    repo_full_name: str
    pr_number: int
    pr_title: str
    status: str
    total_comments: int
    critical_count: int
    warning_count: int
    info_count: int
    github_review_posted: bool
    llm_provider: str
    llm_model: str
    created_at: str
    comments: list[ReviewCommentResponse]


# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------


async def _run_review_background(
    *,
    review_id: int,
    repo_full_name: str,
    pr_number: int,
    pr_title: str,
    pr_description: str,
    base_branch: str,
    head_branch: str,
    changed_files: list[str],
    github_token: str,
    provider: str,
    model: str,
) -> None:
    """Run a review in a background task with its own DB session."""
    async with async_session() as db:
        try:
            await run_review(
                repo_full_name=repo_full_name,
                pr_number=pr_number,
                pr_title=pr_title,
                pr_description=pr_description,
                base_branch=base_branch,
                head_branch=head_branch,
                changed_files=changed_files,
                github_token=github_token,
                review_id=review_id,
                db=db,
                provider=provider,
                model=model,
            )
        except Exception:
            logger.exception("Background review %d failed", review_id)


@router.post("", response_model=TriggerReviewResponse)
async def trigger_review(
    body: TriggerReviewRequest,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TriggerReviewResponse:
    """Trigger a new PR review; returns immediately and runs the agent in the background."""
    # Verify the repo belongs to this user
    repo = await db.get(Repo, body.repo_id)
    if repo is None or repo.user_id != user.id:
        raise HTTPException(status_code=404, detail="Repo not found")

    # Resolve provider/model: request body > user preference > global default
    resolved_provider = (
        body.provider
        or user.preferred_llm_provider
        or settings.default_llm_provider
    )
    resolved_model = (
        body.model
        or user.preferred_llm_model
        or settings.default_model_for(resolved_provider)
    )

    review = Review(
        repo_id=repo.id,
        pr_number=body.pr_number,
        pr_title=body.pr_title or f"PR #{body.pr_number}",
        status=ReviewStatus.PENDING,
        llm_provider=resolved_provider,
        llm_model=resolved_model,
    )
    db.add(review)
    await db.commit()
    await db.refresh(review)

    logger.info(
        "User %s triggered review %d for %s #%d (provider=%s model=%s)",
        user.github_username, review.id, repo.full_name, body.pr_number,
        resolved_provider, resolved_model,
    )

    background_tasks.add_task(
        _run_review_background,
        review_id=review.id,
        repo_full_name=repo.full_name,
        pr_number=body.pr_number,
        pr_title=body.pr_title,
        pr_description=body.pr_description,
        base_branch=body.base_branch,
        head_branch=body.head_branch,
        changed_files=body.changed_files,
        github_token=user.github_token,
        provider=resolved_provider,
        model=resolved_model,
    )

    return TriggerReviewResponse(
        review_id=review.id,
        status=review.status.value,
        findings_count=0,
        llm_provider=resolved_provider,
        llm_model=resolved_model,
    )


@router.get("", response_model=list[ReviewDetailResponse])
async def list_reviews(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    skip: int = Query(0, ge=0, description="Number of reviews to skip"),
    limit: int = Query(20, ge=1, le=100, description="Maximum number of reviews to return"),
    status: str | None = Query(None, description="Filter by review status"),
) -> list[ReviewDetailResponse]:
    """List reviews for repos owned by the current user, with optional pagination and status filter."""
    stmt = (
        select(Review)
        .join(Repo)
        .where(Repo.user_id == user.id)
        .options(selectinload(Review.comments), selectinload(Review.repo))
        .order_by(Review.created_at.desc())
        .offset(skip)
        .limit(limit)
    )

    if status:
        stmt = stmt.where(Review.status == status)

    result = await db.execute(stmt)
    reviews = result.scalars().all()

    return [_review_to_response(r) for r in reviews]


@router.delete("/{review_id}", status_code=204)
async def delete_review(
    review_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a review and all associated comments and logs."""
    review = await db.get(Review, review_id)

    if review is None:
        raise HTTPException(status_code=404, detail="Review not found")

    await db.delete(review)
    await db.commit()


@router.get("/{review_id}", response_model=ReviewDetailResponse)
async def get_review(
    review_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ReviewDetailResponse:
    """Get a single review with its comments."""
    stmt = (
        select(Review)
        .join(Repo)
        .where(Review.id == review_id, Repo.user_id == user.id)
        .options(selectinload(Review.comments), selectinload(Review.repo))
    )
    result = await db.execute(stmt)
    review = result.scalar_one_or_none()

    if review is None:
        raise HTTPException(status_code=404, detail="Review not found")

    return _review_to_response(review)


@router.get("/{review_id}/comments", response_model=list[ReviewCommentResponse])
async def get_review_comments(
    review_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ReviewCommentResponse]:
    """List all comments for a review."""
    stmt = (
        select(Review)
        .join(Repo)
        .where(Review.id == review_id, Repo.user_id == user.id)
    )
    result = await db.execute(stmt)
    review = result.scalar_one_or_none()
    if review is None:
        raise HTTPException(status_code=404, detail="Review not found")

    comments_result = await db.execute(
        select(ReviewComment)
        .where(ReviewComment.review_id == review_id)
        .order_by(ReviewComment.id)
    )
    return [
        ReviewCommentResponse(
            id=c.id,
            file_path=c.file_path,
            line_number=c.line_number,
            category=c.category.value,
            severity=c.severity.value,
            body=c.body,
            fix_suggestion=c.fix_suggestion,
        )
        for c in comments_result.scalars().all()
    ]


class AgentLogResponse(BaseModel):
    id: int
    event_type: str
    content: str
    created_at: str


@router.get("/{review_id}/logs", response_model=list[AgentLogResponse])
async def get_review_logs(
    review_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[AgentLogResponse]:
    """List agent logs for a review (thought stream)."""
    stmt = (
        select(Review)
        .join(Repo)
        .where(Review.id == review_id, Repo.user_id == user.id)
    )
    result = await db.execute(stmt)
    review = result.scalar_one_or_none()
    if review is None:
        raise HTTPException(status_code=404, detail="Review not found")

    logs_result = await db.execute(
        select(AgentLog)
        .where(AgentLog.review_id == review_id)
        .order_by(AgentLog.id)
    )
    return [
        AgentLogResponse(
            id=log.id,
            event_type=log.event_type.value,
            content=log.content,
            created_at=log.created_at.isoformat() if log.created_at else "",
        )
        for log in logs_result.scalars().all()
    ]


@router.get("/{review_id}/stream")
async def stream_review_events(
    review_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Stream live agent events for a review as Server-Sent Events.

    Sends a catch-up burst of all existing log entries, then streams new
    events in real time until the review finishes or the client disconnects.

    Event types emitted:
    - ``log``    — new AgentLog row  (id, event_type, content, created_at)
    - ``status`` — review status changed  (status)
    - ``done``   — terminal event with final stats; client should close
    """
    # Auth: verify review belongs to this user
    stmt = (
        select(Review)
        .join(Repo)
        .where(Review.id == review_id, Repo.user_id == user.id)
    )
    result = await db.execute(stmt)
    review = result.scalar_one_or_none()
    if review is None:
        raise HTTPException(status_code=404, detail="Review not found")

    async def _event_generator() -> AsyncGenerator[str, None]:
        sent_ids: set[int] = set()

        # Subscribe BEFORE fetching catch-up so we don't miss events that
        # arrive between the DB read and the queue subscription.
        queue = subscribe_review(review_id)
        try:
            # Fetch and emit all existing logs (catch-up)
            logs_result = await db.execute(
                select(AgentLog)
                .where(AgentLog.review_id == review_id)
                .order_by(AgentLog.id)
            )
            for log in logs_result.scalars().all():
                sent_ids.add(log.id)
                payload = json.dumps({
                    "id": log.id,
                    "event_type": log.event_type.value,
                    "content": log.content,
                    "created_at": log.created_at.isoformat() if log.created_at else "",
                })
                yield f"event: log\ndata: {payload}\n\n"

            # Emit current status
            await db.refresh(review)
            yield f"event: status\ndata: {json.dumps({'status': review.status.value})}\n\n"

            # If already finished, send done and close
            if review.status in (ReviewStatus.COMPLETED, ReviewStatus.FAILED):
                yield f"event: done\ndata: {json.dumps({'status': review.status.value, 'total_comments': review.total_comments, 'critical_count': review.critical_count, 'warning_count': review.warning_count, 'info_count': review.info_count})}\n\n"
                return

            # Stream live events from the in-process queue
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=20.0)
                except asyncio.TimeoutError:
                    # Keepalive comment so the connection stays open through proxies
                    yield ": keepalive\n\n"
                    continue

                if event is None:
                    # Sentinel — review finished, generator can close
                    break

                event_type = event["type"]
                event_data = event["data"]

                # Deduplicate log events that were already in the catch-up burst
                if event_type == "log":
                    log_id = event_data.get("id")
                    if log_id in sent_ids:
                        continue
                    sent_ids.add(log_id)

                yield f"event: {event_type}\ndata: {json.dumps(event_data)}\n\n"

                if event_type == "done":
                    break

        finally:
            unsubscribe_review(review_id, queue)

    return StreamingResponse(
        _event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.post("/{review_id}/post-to-github")
async def post_to_github(
    review_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Manually trigger posting a completed review to GitHub.

    Useful for retrying a failed post without re-running the agent.
    """
    stmt = (
        select(Review)
        .join(Repo)
        .where(Review.id == review_id, Repo.user_id == user.id)
        .options(selectinload(Review.comments), selectinload(Review.repo))
    )
    result = await db.execute(stmt)
    review = result.scalar_one_or_none()

    if review is None:
        raise HTTPException(status_code=404, detail="Review not found")

    if review.status != ReviewStatus.COMPLETED:
        raise HTTPException(
            status_code=400,
            detail=f"Review is {review.status.value}, not completed",
        )

    if not review.comments:
        raise HTTPException(status_code=400, detail="No comments to post")

    await post_review_to_github(
        review_id=review.id,
        repo_full_name=review.repo.full_name,
        pr_number=review.pr_number,
        comments=list(review.comments),
        github_token=user.github_token,
        db=db,
    )

    return {"status": "posted", "review_id": str(review.id)}


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _review_to_response(review: Review) -> ReviewDetailResponse:
    return ReviewDetailResponse(
        id=review.id,
        repo_full_name=review.repo.full_name,
        pr_number=review.pr_number,
        pr_title=review.pr_title,
        status=review.status.value,
        total_comments=review.total_comments,
        critical_count=review.critical_count,
        warning_count=review.warning_count,
        info_count=review.info_count,
        github_review_posted=review.github_review_posted,
        llm_provider=review.llm_provider,
        llm_model=review.llm_model,
        created_at=review.created_at.isoformat() if review.created_at else "",
        comments=[
            ReviewCommentResponse(
                id=c.id,
                file_path=c.file_path,
                line_number=c.line_number,
                category=c.category.value,
                severity=c.severity.value,
                body=c.body,
                fix_suggestion=c.fix_suggestion,
            )
            for c in review.comments
        ],
    )
