"""GitHub OAuth 2.0 login flow.

1. GET  /auth/github/login    → redirect user to GitHub authorize page
2. GET  /auth/github/callback → exchange code for access token, upsert user, return JWT
3. GET  /auth/me              → return current user profile from JWT
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException
from jose import jwt
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.config import settings
from app.database import get_db
from app.models import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_USER_URL = "https://api.github.com/user"


# ------------------------------------------------------------------
# Response schemas
# ------------------------------------------------------------------


class LoginURLResponse(BaseModel):
    url: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserProfile


class CallbackRequest(BaseModel):
    code: str


class UserProfile(BaseModel):
    id: int
    github_username: str
    avatar_url: str | None


# Rebuild TokenResponse so it sees the now-defined UserProfile
TokenResponse.model_rebuild()


# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------


@router.get("/github/login", response_model=LoginURLResponse)
async def github_login() -> LoginURLResponse:
    """Return the GitHub OAuth authorize URL the frontend should redirect to."""
    if not settings.github_client_id:
        raise HTTPException(status_code=500, detail="GITHUB_CLIENT_ID not configured")

    params = {
        "client_id": settings.github_client_id,
        "redirect_uri": f"{settings.frontend_url}/api/auth/callback",
        "scope": "repo read:user",
    }
    qs = "&".join(f"{k}={v}" for k, v in params.items())
    return LoginURLResponse(url=f"{GITHUB_AUTHORIZE_URL}?{qs}")


@router.post("/github/callback", response_model=TokenResponse)
async def github_callback(
    body: CallbackRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """Exchange a GitHub OAuth code for an access token.

    - Calls GitHub to exchange the code
    - Fetches the user profile from GitHub
    - Upserts the User row in our DB (create or update token)
    - Returns a signed JWT the frontend stores
    """
    # 1. Exchange code for GitHub access token
    async with httpx.AsyncClient() as client:
        token_resp = await client.post(
            GITHUB_TOKEN_URL,
            json={
                "client_id": settings.github_client_id,
                "client_secret": settings.github_client_secret,
                "code": body.code,
            },
            headers={"Accept": "application/json"},
        )

    if token_resp.status_code != 200:
        logger.error("GitHub token exchange failed: %s", token_resp.text)
        raise HTTPException(status_code=502, detail="GitHub token exchange failed")

    token_data = token_resp.json()
    github_token = token_data.get("access_token")
    if not github_token:
        logger.error("No access_token in GitHub response: %s", token_data)
        raise HTTPException(status_code=502, detail=token_data.get("error_description", "No access token"))

    # 2. Fetch user profile from GitHub
    async with httpx.AsyncClient() as client:
        user_resp = await client.get(
            GITHUB_USER_URL,
            headers={
                "Authorization": f"Bearer {github_token}",
                "Accept": "application/json",
            },
        )

    if user_resp.status_code != 200:
        logger.error("GitHub user fetch failed: %s", user_resp.text)
        raise HTTPException(status_code=502, detail="Failed to fetch GitHub user profile")

    gh_user = user_resp.json()
    username = gh_user["login"]
    avatar = gh_user.get("avatar_url")

    # 3. Upsert user in DB
    stmt = select(User).where(User.github_username == username)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if user is None:
        user = User(
            github_username=username,
            github_token=github_token,
            avatar_url=avatar,
        )
        db.add(user)
        await db.flush()
        logger.info("Created new user: %s (id=%d)", username, user.id)
    else:
        user.github_token = github_token
        user.avatar_url = avatar
        await db.flush()
        logger.info("Updated existing user: %s (id=%d)", username, user.id)

    # 4. Issue JWT
    jwt_token = _create_jwt(user_id=user.id, username=username)

    return TokenResponse(
        access_token=jwt_token,
        user=UserProfile(
            id=user.id,
            github_username=username,
            avatar_url=avatar,
        ),
    )


@router.get("/me", response_model=UserProfile)
async def get_me(user: User = Depends(get_current_user)) -> UserProfile:
    """Return the profile of the currently authenticated user."""
    return UserProfile(
        id=user.id,
        github_username=user.github_username,
        avatar_url=user.avatar_url,
    )


# ------------------------------------------------------------------
# JWT helper
# ------------------------------------------------------------------


def _create_jwt(*, user_id: int, username: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {
        "sub": str(user_id),
        "username": username,
        "exp": expire,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
