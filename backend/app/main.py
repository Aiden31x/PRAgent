from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import engine, Base, get_db
from app.auth.router import router as auth_router, _create_jwt
from app.repos.router import router as repos_router
from app.reviews.router import router as reviews_router
from app.models import User


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


app = FastAPI(
    title=settings.app_name,
    description="Autonomous PR Review Agent powered by MCP + Gemini",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(auth_router)
app.include_router(repos_router)
app.include_router(reviews_router)


@app.get("/health")
async def health_check():
    return {"status": "ok", "app": settings.app_name}

@app.get("/dev/token")
async def dev_token(db: AsyncSession = Depends(get_db)):
    """TEMPORARY dev endpoint — delete before Phase 5."""
    result = await db.execute(
        select(User).where(User.github_username == "Aiden31x")
    )
    user = result.scalar_one_or_none()

    if user is None:
        user = User(
            github_username="Aiden31x",
            github_token=settings.github_token,
            avatar_url="",
        )
        db.add(user)
        await db.flush()
    else:
        user.github_token = settings.github_token
        await db.flush()

    token = _create_jwt(user_id=user.id, username=user.github_username)
    return {"token": token, "user_id": user.id}