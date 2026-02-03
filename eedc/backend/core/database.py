"""
EEDC Datenbank Setup

SQLite Datenbank mit SQLAlchemy 2.0 (async).
"""

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from backend.core.config import settings


# Async Engine erstellen
engine = create_async_engine(
    settings.database_url,
    echo=settings.log_level == "debug",  # SQL Logging nur im Debug-Modus
    future=True,
)

# Session Factory
async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


# Base Class für alle Models
class Base(DeclarativeBase):
    """Basis-Klasse für alle SQLAlchemy Models."""
    pass


async def init_db():
    """
    Initialisiert die Datenbank.

    Erstellt alle Tabellen falls sie nicht existieren.
    Wird beim App-Start aufgerufen.
    """
    # Importiere alle Models damit sie registriert werden
    from backend.models import anlage, monatsdaten, investition, strompreis, settings as settings_model

    async with engine.begin() as conn:
        # Erstelle alle Tabellen
        await conn.run_sync(Base.metadata.create_all)


async def get_db() -> AsyncSession:
    """
    Dependency für FastAPI Endpoints.

    Liefert eine Datenbank-Session und schließt sie nach dem Request.

    Verwendung:
        @app.get("/example")
        async def example(db: AsyncSession = Depends(get_db)):
            ...

    Yields:
        AsyncSession: Datenbank-Session
    """
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
