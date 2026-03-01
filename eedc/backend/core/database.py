"""
EEDC Datenbank Setup

SQLite Datenbank mit SQLAlchemy 2.0 (async).
"""

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import event

from backend.core.config import settings


# Async Engine erstellen
engine = create_async_engine(
    settings.database_url,
    echo=settings.log_level == "debug",  # SQL Logging nur im Debug-Modus
    future=True,
)


# SQLite Foreign Keys aktivieren (WICHTIG für CASCADE DELETE)
@event.listens_for(engine.sync_engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    """Aktiviert SQLite Foreign Key Constraints."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()

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


async def run_migrations(conn):
    """
    Führt einfache Migrationen durch.

    SQLite unterstützt keine nativen ALTER TABLE ADD COLUMN,
    daher prüfen wir ob Spalten existieren und fügen sie hinzu.
    """
    from sqlalchemy import text, inspect

    def _run_migrations(connection):
        inspector = inspect(connection)

        # v0.8.0+: Neue Spalten zur anlagen Tabelle
        if 'anlagen' in inspector.get_table_names():
            existing_columns = {col['name'] for col in inspector.get_columns('anlagen')}
            new_columns = [
                ('ha_sensor_pv_erzeugung', 'VARCHAR(255)'),
                ('ha_sensor_einspeisung', 'VARCHAR(255)'),
                ('ha_sensor_netzbezug', 'VARCHAR(255)'),
                ('ha_sensor_batterie_ladung', 'VARCHAR(255)'),
                ('ha_sensor_batterie_entladung', 'VARCHAR(255)'),
                ('wechselrichter_hersteller', 'VARCHAR(50)'),
                # v1.0.0-beta.6: Versorger-Stammdaten
                ('mastr_id', 'VARCHAR(20)'),
                ('versorger_daten', 'JSON'),
                # v1.0.0-beta.10: Wetterdaten-Provider
                ('wetter_provider', 'VARCHAR(30)'),
                # v1.1.0: Sensor-Mapping für HA-Integration
                ('sensor_mapping', 'JSON'),
                # v2.0.3: Community-Sharing Hash
                ('community_hash', 'VARCHAR(64)'),
                # v2.3.0: Land-Auswahl für DACH-Unterstützung
                ('standort_land', 'VARCHAR(5)'),
                # Horizont-Profil für PVGIS
                ('horizont_daten', 'JSON'),
                # Steuerliche Behandlung (Kleinunternehmerregelung)
                ('steuerliche_behandlung', "VARCHAR(30) DEFAULT 'keine_ust'"),
                ('ust_satz_prozent', 'FLOAT DEFAULT 19.0'),
            ]
            for col_name, col_type in new_columns:
                if col_name not in existing_columns:
                    connection.execute(text(f'ALTER TABLE anlagen ADD COLUMN {col_name} {col_type}'))

        # v1.1.0: Neue Spalten zur monatsdaten Tabelle
        if 'monatsdaten' in inspector.get_table_names():
            existing_columns = {col['name'] for col in inspector.get_columns('monatsdaten')}
            new_columns = [
                ('durchschnittstemperatur', 'FLOAT'),
                ('sonderkosten_euro', 'FLOAT'),
                ('sonderkosten_beschreibung', 'VARCHAR(500)'),
                ('notizen', 'VARCHAR(1000)'),
            ]
            for col_name, col_type in new_columns:
                if col_name not in existing_columns:
                    connection.execute(text(f'ALTER TABLE monatsdaten ADD COLUMN {col_name} {col_type}'))

        # v2.3.2: Neue Spalten zur pvgis_prognosen Tabelle (per-Modul-Daten + gesamt kWp)
        if 'pvgis_prognosen' in inspector.get_table_names():
            existing_columns = {col['name'] for col in inspector.get_columns('pvgis_prognosen')}
            new_columns = [
                ('gesamt_leistung_kwp', 'FLOAT'),
                ('module_monatswerte', 'JSON'),
                ('horizont_verwendet', 'BOOLEAN DEFAULT 0'),
            ]
            for col_name, col_type in new_columns:
                if col_name not in existing_columns:
                    connection.execute(text(f'ALTER TABLE pvgis_prognosen ADD COLUMN {col_name} {col_type}'))

        # v0.9.5+: Neue Spalten zur investitionen Tabelle (PV-Module spezifisch)
        if 'investitionen' in inspector.get_table_names():
            existing_columns = {col['name'] for col in inspector.get_columns('investitionen')}
            new_columns = [
                ('leistung_kwp', 'FLOAT'),
                ('ausrichtung', 'VARCHAR(50)'),
                ('neigung_grad', 'FLOAT'),
                ('ha_entity_id', 'VARCHAR(255)'),
            ]
            for col_name, col_type in new_columns:
                if col_name not in existing_columns:
                    connection.execute(text(f'ALTER TABLE investitionen ADD COLUMN {col_name} {col_type}'))

        # Spezialtarife: verwendung-Feld für Strompreise
        if 'strompreise' in inspector.get_table_names():
            existing_columns = {col['name'] for col in inspector.get_columns('strompreise')}
            if 'verwendung' not in existing_columns:
                connection.execute(text("ALTER TABLE strompreise ADD COLUMN verwendung VARCHAR(30) DEFAULT 'allgemein'"))

    await conn.run_sync(_run_migrations)


async def init_db():
    """
    Initialisiert die Datenbank.

    Erstellt alle Tabellen falls sie nicht existieren.
    Wird beim App-Start aufgerufen.
    """
    # Importiere alle Models damit sie registriert werden
    from backend.models import anlage, monatsdaten, investition, strompreis, settings as settings_model, pvgis_prognose

    async with engine.begin() as conn:
        # Migrationen ausführen
        await run_migrations(conn)
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


from contextlib import asynccontextmanager

@asynccontextmanager
async def get_session():
    """
    Context Manager für Datenbank-Session.

    Verwendung außerhalb von FastAPI Dependencies.

    Verwendung:
        async with get_session() as session:
            result = await session.execute(...)

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
