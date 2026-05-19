"""Pytest-Konfiguration und gemeinsame Fixtures für Backend-Akzeptanztests.

Bündelt das pro-Datei duplizierte `_session_ctx`-Boilerplate aus den
Akzeptanztests (Aufräum-Plan E nach v3.31.5). Pytest ist seit v3.27.x
der einzige Test-Runner — der frühere Dual-Mode (Standalone-Script-
Aufruf mit `__main__`-Runner) ist abgelöst.

Auch `sys.path`-Einbindung für `from backend...`-Imports erfolgt hier
einmal zentral statt pro Test-Datei.
"""

from __future__ import annotations

import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[2]  # eedc/
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.core.database import Base


@pytest_asyncio.fixture
async def db() -> AsyncSession:
    """Frisches In-Memory-SQLite + Schema pro Test, sauberes Teardown.

    Fixture-Name `db` matcht die FastAPI-Konvention (`db: AsyncSession =
    Depends(get_db)`) und die in den Tests übliche Variable.
    """
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    session = Session()
    try:
        yield session
    finally:
        await session.close()
        await engine.dispose()
