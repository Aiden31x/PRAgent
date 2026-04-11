"""Review endpoints — trigger and query PR reviews."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.agent.orchestrator import post_review_to_github, run_review
from app.auth.dependencies import get_current_user
from app.database import get_db
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


class TriggerReviewResponse(BaseModel):
    review_id: int
    status: str
    findings_count: int


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
    created_at: str
    comments: list[ReviewCommentResponse]


# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------


@router.post("", response_model=TriggerReviewResponse)
async def trigger_review(
    body: TriggerReviewRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TriggerReviewResponse:
    """Trigger a new PR review using the authenticated user's GitHub token."""
    # Verify the repo belongs to this user
    repo = await db.get(Repo, body.repo_id)
    if repo is None or repo.user_id != user.id:
        raise HTTPException(status_code=404, detail="Repo not found")

    review = Review(
        repo_id=repo.id,
        pr_number=body.pr_number,
        pr_title=body.pr_title or f"PR #{body.pr_number}",
        status=ReviewStatus.PENDING,
    )
    db.add(review)
    await db.flush()

    logger.info(
        "User %s triggered review %d for %s #%d",
        user.github_username, review.id, repo.full_name, body.pr_number,
    )

    await run_review(
        repo_full_name=repo.full_name,
        pr_number=body.pr_number,
        pr_title=body.pr_title,
        pr_description=body.pr_description,
        base_branch=body.base_branch,
        head_branch=body.head_branch,
        changed_files=body.changed_files,
        github_token=user.github_token,
        review_id=review.id,
        db=db,
    )

    await db.refresh(review)

    return TriggerReviewResponse(
        review_id=review.id,
        status=review.status.value,
        findings_count=review.total_comments,
    )


@router.get("", response_model=list[ReviewDetailResponse])
async def list_reviews(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ReviewDetailResponse]:
    """List all reviews for repos owned by the current user."""
    stmt = (
        select(Review)
        .join(Repo)
        .where(Repo.user_id == user.id)
        .options(selectinload(Review.comments), selectinload(Review.repo))
        .order_by(Review.created_at.desc())
    )
    result = await db.execute(stmt)
    reviews = result.scalars().all()

    return [_review_to_response(r) for r in reviews]


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
