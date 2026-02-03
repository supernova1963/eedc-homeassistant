"""
API Dependencies

Gemeinsam genutzte Dependencies für FastAPI Endpoints.
"""

from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database import async_session_maker


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency für Datenbank-Session.

    Verwendung in Endpoints:
        @router.get("/")
        async def example(db: AsyncSession = Depends(get_db)):
            ...

    Yields:
        AsyncSession: Aktive Datenbank-Session
    """
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
