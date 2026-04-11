"""Repo management — add repos, list repos, list open PRs."""

from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models import Repo, User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/repos", tags=["repos"])

GITHUB_API = "https://api.github.com"


# ------------------------------------------------------------------
# Schemas
# ------------------------------------------------------------------


class AddRepoRequest(BaseModel):
    full_name: str  # "owner/repo"


class RepoResponse(BaseModel):
    id: int
    full_name: str
    webhook_id: int | None


class PRSummary(BaseModel):
    number: int
    title: str
    description: str
    base_branch: str
    head_branch: str
    author: str
    changed_files: list[str]


# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------


@router.post("", response_model=RepoResponse)
async def add_repo(
    body: AddRepoRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RepoResponse:
    """Register a GitHub repo for the current user.

    Validates the repo exists and the user has access via their GitHub token.
    """
    owner, repo_name = _split_full_name(body.full_name)

    # Verify the repo exists and user has access
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{GITHUB_API}/repos/{owner}/{repo_name}",
            headers=_gh_headers(user.github_token),
        )

    if resp.status_code == 404:
        raise HTTPException(status_code=404, detail="Repository not found or no access")
    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail=f"GitHub API error: {resp.status_code}")

    # Check if already added
    stmt = select(Repo).where(Repo.user_id == user.id, Repo.full_name == body.full_name)
    result = await db.execute(stmt)
    existing = result.scalar_one_or_none()

    if existing:
        return RepoResponse(id=existing.id, full_name=existing.full_name, webhook_id=existing.webhook_id)

    repo = Repo(user_id=user.id, full_name=body.full_name)
    db.add(repo)
    await db.flush()

    logger.info("User %s added repo %s (id=%d)", user.github_username, body.full_name, repo.id)
    return RepoResponse(id=repo.id, full_name=repo.full_name, webhook_id=repo.webhook_id)


@router.get("", response_model=list[RepoResponse])
async def list_repos(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[RepoResponse]:
    """List all repos registered by the current user."""
    stmt = select(Repo).where(Repo.user_id == user.id).order_by(Repo.created_at.desc())
    result = await db.execute(stmt)
    repos = result.scalars().all()
    return [RepoResponse(id=r.id, full_name=r.full_name, webhook_id=r.webhook_id) for r in repos]


@router.get("/{repo_id}/pulls", response_model=list[PRSummary])
async def list_open_prs(
    repo_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[PRSummary]:
    """Fetch open PRs for a registered repo from GitHub."""
    repo = await db.get(Repo, repo_id)
    if repo is None or repo.user_id != user.id:
        raise HTTPException(status_code=404, detail="Repo not found")

    owner, repo_name = _split_full_name(repo.full_name)

    async with httpx.AsyncClient() as client:
        # Fetch open PRs
        prs_resp = await client.get(
            f"{GITHUB_API}/repos/{owner}/{repo_name}/pulls",
            params={"state": "open", "per_page": 30},
            headers=_gh_headers(user.github_token),
        )

    if prs_resp.status_code != 200:
        raise HTTPException(status_code=502, detail=f"GitHub API error: {prs_resp.status_code}")

    summaries: list[PRSummary] = []
    for pr in prs_resp.json():
        # Fetch changed files for each PR (lightweight — just filenames)
        files: list[str] = []
        async with httpx.AsyncClient() as client:
            files_resp = await client.get(
                f"{GITHUB_API}/repos/{owner}/{repo_name}/pulls/{pr['number']}/files",
                params={"per_page": 100},
                headers=_gh_headers(user.github_token),
            )
            if files_resp.status_code == 200:
                files = [f["filename"] for f in files_resp.json()]

        summaries.append(PRSummary(
            number=pr["number"],
            title=pr["title"],
            description=pr.get("body") or "",
            base_branch=pr["base"]["ref"],
            head_branch=pr["head"]["ref"],
            author=pr["user"]["login"],
            changed_files=files,
        ))

    return summaries


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _split_full_name(full_name: str) -> tuple[str, str]:
    parts = full_name.split("/", 1)
    if len(parts) != 2 or not all(parts):
        raise HTTPException(status_code=400, detail="full_name must be 'owner/repo'")
    return parts[0], parts[1]


def _gh_headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
