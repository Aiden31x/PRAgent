"""GitHub webhook receiver — verifies signatures and triggers reviews."""

from __future__ import annotations

import hashlib
import hmac
import logging

from fastapi import APIRouter, BackgroundTasks, Request, Response
from sqlalchemy import select

from app.agent.orchestrator import run_review
from app.config import settings
from app.database import async_session
from app.models import Repo, Review, ReviewStatus, User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

HANDLED_ACTIONS = {"opened", "synchronize"}


def _verify_signature(payload: bytes, signature_header: str | None) -> bool:
    """Verify the HMAC-SHA256 signature GitHub sends with each webhook."""
    if not signature_header:
        return False
    if not signature_header.startswith("sha256="):
        return False

    expected = hmac.new(
        settings.webhook_secret.encode(),
        payload,
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(f"sha256={expected}", signature_header)


@router.post("/github")
async def github_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
) -> Response:
    """Receive GitHub webhook events and trigger reviews for PR events."""
    body = await request.body()

    # -- Step 1: Verify signature --------------------------------------
    signature = request.headers.get("X-Hub-Signature-256")
    if not _verify_signature(body, signature):
        logger.warning("Webhook signature verification failed")
        return Response(status_code=403, content="Invalid signature")

    # -- Step 2: Parse event -------------------------------------------
    event_type = request.headers.get("X-GitHub-Event", "")
    if event_type != "pull_request":
        return Response(status_code=200, content="OK")

    try:
        payload = await request.json()
    except Exception:
        logger.warning("Failed to parse webhook JSON body")
        return Response(status_code=400, content="Invalid JSON")

    action = payload.get("action", "")
    if action not in HANDLED_ACTIONS:
        logger.debug("Ignoring pull_request action=%s", action)
        return Response(status_code=200, content="OK")

    pr = payload.get("pull_request", {})
    repo_full_name = payload.get("repository", {}).get("full_name", "")
    pr_number = pr.get("number", 0)
    pr_title = pr.get("title", "")
    pr_description = pr.get("body") or ""
    base_branch = pr.get("base", {}).get("ref", "main")
    head_branch = pr.get("head", {}).get("ref", "")
    sender_login = payload.get("sender", {}).get("login", "")
    changed_files: list[str] = []

    if not repo_full_name or not pr_number:
        logger.warning("Webhook missing repo or PR number")
        return Response(status_code=200, content="OK")

    logger.info(
        "Webhook: pull_request %s on %s #%d by %s",
        action, repo_full_name, pr_number, sender_login,
    )

    # -- Step 3: Find or create repo + user ----------------------------
    async with async_session() as db:
        # Look up the repo
        result = await db.execute(
            select(Repo).where(Repo.full_name == repo_full_name)
        )
        repo = result.scalar_one_or_none()

        if repo is None:
            # Repo not registered — look up the sender as a user
            user_result = await db.execute(
                select(User).where(User.github_username == sender_login)
            )
            user = user_result.scalar_one_or_none()
            if user is None:
                logger.info(
                    "Webhook from unregistered user %s for %s — ignoring",
                    sender_login, repo_full_name,
                )
                return Response(status_code=200, content="OK")

            repo = Repo(user_id=user.id, full_name=repo_full_name)
            db.add(repo)
            await db.flush()
            logger.info("Auto-created repo %s for user %s", repo_full_name, sender_login)
        else:
            user_result = await db.execute(
                select(User).where(User.id == repo.user_id)
            )
            user = user_result.scalar_one_or_none()
            if user is None:
                logger.error("Repo %s has no user — skipping", repo_full_name)
                return Response(status_code=200, content="OK")

        # -- Step 4: Create Review row and schedule background task ----
        review = Review(
            repo_id=repo.id,
            pr_number=pr_number,
            pr_title=pr_title or f"PR #{pr_number}",
            status=ReviewStatus.PENDING,
        )
        db.add(review)
        await db.flush()

        review_id = review.id
        github_token = user.github_token
        await db.commit()

    logger.info(
        "Webhook: created review %d for %s #%d — dispatching to background",
        review_id, repo_full_name, pr_number,
    )

    background_tasks.add_task(
        _run_review_background,
        repo_full_name=repo_full_name,
        pr_number=pr_number,
        pr_title=pr_title,
        pr_description=pr_description,
        base_branch=base_branch,
        head_branch=head_branch,
        changed_files=changed_files,
        github_token=github_token,
        review_id=review_id,
    )

    return Response(status_code=200, content="OK")


async def _run_review_background(
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
) -> None:
    """Run a review in the background with its own DB session."""
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
            )
        except Exception:
            logger.exception(
                "Background review %d failed for %s #%d",
                review_id, repo_full_name, pr_number,
            )
