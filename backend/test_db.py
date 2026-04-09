"""Step 3 — FastAPI health + DB test.

1. Generates the initial Alembic migration (if none exist)
2. Runs `alembic upgrade head`
3. Hits GET /health via the FastAPI test client
4. Saves a dummy User → Repo → Review chain and reads it back
5. Cleans up test data

Prerequisites:
  - DATABASE_URL in .env pointing to your Neon database, e.g.:
    DATABASE_URL=postgresql+asyncpg://user:pass@ep-xxx.us-east-2.aws.neon.tech/neondb?sslmode=require
  - Get your connection string from https://console.neon.tech

Usage:
  cd backend
  venv/bin/python test_db.py
"""

import asyncio
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def run_cmd(args: list[str], label: str) -> bool:
    print(f"\n→ {label}")
    print(f"  $ {' '.join(args)}")
    result = subprocess.run(args, capture_output=True, text=True)
    if result.stdout.strip():
        for line in result.stdout.strip().splitlines():
            print(f"    {line}")
    if result.returncode != 0:
        print(f"  FAILED (exit {result.returncode})")
        if result.stderr.strip():
            for line in result.stderr.strip().splitlines():
                print(f"    {line}")
        return False
    print(f"  OK")
    return True


async def main() -> None:
    # ------------------------------------------------------------------
    # 1. Alembic migrations
    # ------------------------------------------------------------------
    versions_dir = Path("alembic/versions")
    has_migrations = any(versions_dir.glob("*.py")) if versions_dir.exists() else False

    if not has_migrations:
        ok = run_cmd(
            [sys.executable, "-m", "alembic", "revision", "--autogenerate", "-m", "initial tables"],
            "Generating initial Alembic migration",
        )
        if not ok:
            print("\nMigration generation failed. Is your DATABASE_URL correct and the DB reachable?")
            sys.exit(1)

    ok = run_cmd(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        "Running alembic upgrade head",
    )
    if not ok:
        print("\nMigration failed. Check DATABASE_URL and that the database exists.")
        sys.exit(1)

    # ------------------------------------------------------------------
    # 2. GET /health (using ASGI test transport — no server needed)
    # ------------------------------------------------------------------
    from httpx import ASGITransport, AsyncClient

    from app.main import app

    print("\n→ Testing GET /health")
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        resp = await client.get("/health")
    print(f"  Status : {resp.status_code}")
    print(f"  Body   : {resp.json()}")
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
    print("  OK")

    # ------------------------------------------------------------------
    # 3. Save a dummy Review row and read it back
    # ------------------------------------------------------------------
    from sqlalchemy import select

    from app.database import async_session, engine, Base
    from app.models import Repo, Review, ReviewStatus, User

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    print("\n→ Inserting test data: User → Repo → Review")
    async with async_session() as session:
        user = User(github_username="test-bot", github_token="fake-token-123")
        session.add(user)
        await session.flush()

        repo = Repo(user_id=user.id, full_name="test-org/test-repo")
        session.add(repo)
        await session.flush()

        review = Review(
            repo_id=repo.id,
            pr_number=99,
            pr_title="Test PR for DB validation",
            status=ReviewStatus.COMPLETED,
            total_comments=3,
            critical_count=1,
            warning_count=1,
            info_count=1,
        )
        session.add(review)
        await session.commit()

        review_id = review.id
        print(f"  Created → Review(id={review_id}, pr_title='{review.pr_title}', status={review.status.value})")

    print("\n→ Reading it back")
    async with async_session() as session:
        row = (await session.execute(select(Review).where(Review.id == review_id))).scalar_one()
        print(f"  Read   → Review(id={row.id}, pr_title='{row.pr_title}', status={row.status.value})")
        assert row.pr_title == "Test PR for DB validation"
        assert row.critical_count == 1
        print("  OK — data matches")

    # ------------------------------------------------------------------
    # 4. Cleanup
    # ------------------------------------------------------------------
    print("\n→ Cleaning up test data")
    async with async_session() as session:
        from sqlalchemy import text
        await session.execute(text(f"DELETE FROM reviews WHERE id = {review_id}"))
        await session.execute(text("DELETE FROM repos WHERE full_name = 'test-org/test-repo'"))
        await session.execute(text("DELETE FROM users WHERE github_username = 'test-bot'"))
        await session.commit()
    print("  OK — test rows removed")

    await engine.dispose()
    print("\nAll DB tests passed.")


if __name__ == "__main__":
    asyncio.run(main())
