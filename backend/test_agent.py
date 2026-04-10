"""Step 2 — Exercise the full ReAct agent loop (Gemini + MCP + DB).

Creates (or reuses) User + Repo rows, inserts a Review, then calls ``run_review``.

Prerequisites:
  - Docker running (GitHub MCP server)
  - ``backend/.env`` with DATABASE_URL, GEMINI_API_KEY, GITHUB_TOKEN
  - A real open PR you can access with that token

Environment:
  TEST_REPO_FULL_NAME   Owner/repo (default: fastapi/fastapi)
  TEST_PR_NUMBER        Integer (default: 1)
  TEST_GITHUB_USERNAME  DB user row; default = owner segment of TEST_REPO_FULL_NAME

Usage:
  cd backend
  python test_agent.py
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# Load .env before app settings
load_dotenv(Path(__file__).resolve().parent / ".env")

from sqlalchemy import select

from app.agent.orchestrator import run_review
from app.config import settings
from app.database import async_session
from app.models import Repo, Review, ReviewStatus, User


def _repo_target() -> tuple[str, str, int]:
    full = os.environ.get("TEST_REPO_FULL_NAME", os.environ.get("MCP_TEST_REPO_FULL_NAME", "fastapi/fastapi")).strip()
    if "/" not in full:
        print("ERROR: TEST_REPO_FULL_NAME must be 'owner/repo'")
        sys.exit(1)
    owner, name = full.split("/", 1)
    raw = os.environ.get("TEST_PR_NUMBER", os.environ.get("MCP_TEST_PR_NUMBER", "1")).strip()
    try:
        pr_num = int(raw)
    except ValueError:
        print("ERROR: TEST_PR_NUMBER must be an integer")
        sys.exit(1)
    return owner, name, pr_num


async def _get_or_create_user(db, username: str, token: str) -> User:
    result = await db.execute(select(User).where(User.github_username == username))
    user = result.scalar_one_or_none()
    if user is not None:
        user.github_token = token
        await db.flush()
        return user
    user = User(github_username=username, github_token=token, avatar_url=None)
    db.add(user)
    await db.flush()
    return user


async def _get_or_create_repo(db, user_id: int, full_name: str) -> Repo:
    result = await db.execute(
        select(Repo).where(Repo.user_id == user_id, Repo.full_name == full_name)
    )
    repo = result.scalar_one_or_none()
    if repo is not None:
        return repo
    repo = Repo(user_id=user_id, full_name=full_name)
    db.add(repo)
    await db.flush()
    return repo


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if not token:
        print("ERROR: GITHUB_TOKEN not set in .env")
        sys.exit(1)
    if not settings.gemini_api_key:
        print("ERROR: GEMINI_API_KEY not set in .env")
        sys.exit(1)

    owner, _repo_name, pr_number = _repo_target()
    full_name = f"{owner}/{_repo_name}"
    gh_username = os.environ.get("TEST_GITHUB_USERNAME", owner).strip() or owner

    print(f"Target PR: {full_name}#{pr_number}")
    print(f"DB user row github_username: {gh_username}\n")

    async with async_session() as db:
        user = await _get_or_create_user(db, gh_username, token)
        repo = await _get_or_create_repo(db, user.id, full_name)

        review = Review(
            repo_id=repo.id,
            pr_number=pr_number,
            pr_title=f"Test run PR #{pr_number}",
            status=ReviewStatus.PENDING,
        )
        db.add(review)
        await db.flush()
        rid = review.id

        print(f"Created Review id={rid} — starting orchestrator…\n")

        await run_review(
            repo_full_name=full_name,
            pr_number=pr_number,
            pr_title="",
            pr_description="",
            base_branch="main",
            head_branch="",
            changed_files=[],
            github_token=token,
            review_id=rid,
            db=db,
        )

        await db.refresh(review)
        print(
            f"\nDone. Review {rid} status={review.status.value} "
            f"findings={review.total_comments}"
        )


if __name__ == "__main__":
    asyncio.run(main())
