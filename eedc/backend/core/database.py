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


# v3.15.2: Anlagen mit mindestens dieser Anzahl Tagen TagesZusammenfassung
# gelten als "Bestand" und überspringen den Auto-Vollbackfill beim ersten
# Monatsabschluss nach Upgrade. Schwelle bewusst niedrig, damit auch frische
# Installationen mit ein paar Wochen Datenbestand nicht überraschend einen
# Multi-Jahres-Backfill auslösen.
VOLLBACKFILL_BESTAND_SCHWELLE_TAGE = 30


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
                # v2.6.0: Connector-Konfiguration für direkte Geräteverbindung
                ('connector_config', 'JSON'),
                # v3.5.0: Wettermodell für Solar-Prognose (Kaskade mit Fallback)
                ('wetter_modell', "VARCHAR(50) DEFAULT 'auto'"),
                # v3.5.0: Community Auto-Share nach Monatsabschluss
                ('community_auto_share', 'BOOLEAN DEFAULT 0'),
                # v3.5.0: Netz-Puffer für Energiefluss-Farbwechsel (Watt)
                ('netz_puffer_w', 'INTEGER DEFAULT 100'),
                ('vollbackfill_durchgefuehrt', 'BOOLEAN DEFAULT 0'),
                # v3.17: Prognose-Basis (openmeteo, solcast, sfml)
                ('prognose_basis', "VARCHAR(30) DEFAULT 'openmeteo'"),
            ]
            newly_added = set()
            for col_name, col_type in new_columns:
                if col_name not in existing_columns:
                    connection.execute(text(f'ALTER TABLE anlagen ADD COLUMN {col_name} {col_type}'))
                    newly_added.add(col_name)

            # Bestandsdaten-Heuristik: Anlagen mit substanzieller Energieprofil-Historie
            # sollen den Auto-Vollbackfill NICHT erneut auslösen. Nur beim erstmaligen
            # Anlegen der Spalte einmalig markieren.
            if 'vollbackfill_durchgefuehrt' in newly_added and 'tages_zusammenfassung' in inspector.get_table_names():
                connection.execute(text(f"""
                    UPDATE anlagen SET vollbackfill_durchgefuehrt = 1
                    WHERE id IN (
                        SELECT anlage_id FROM tages_zusammenfassung
                        GROUP BY anlage_id HAVING COUNT(*) > {VOLLBACKFILL_BESTAND_SCHWELLE_TAGE}
                    )
                """))

        # v1.1.0: Neue Spalten zur monatsdaten Tabelle
        if 'monatsdaten' in inspector.get_table_names():
            existing_columns = {col['name'] for col in inspector.get_columns('monatsdaten')}
            new_columns = [
                ('durchschnittstemperatur', 'FLOAT'),
                ('sonderkosten_euro', 'FLOAT'),
                ('sonderkosten_beschreibung', 'VARCHAR(500)'),
                ('notizen', 'VARCHAR(1000)'),
                ('netzbezug_durchschnittspreis_cent', 'FLOAT'),
                # v3.1.0: Energiebilanz-Analyse
                ('ueberschuss_kwh', 'FLOAT'),
                ('defizit_kwh', 'FLOAT'),
                ('batterie_vollzyklen', 'FLOAT'),
                ('performance_ratio', 'FLOAT'),
                ('peak_netzbezug_kw', 'FLOAT'),
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
                # v3.14.0: Stilllegungsdatum (Issue #123) — historische Aggregate
                # blenden Investitionen nicht mehr rückwirkend aus
                ('stilllegungsdatum', 'DATE'),
            ]
            for col_name, col_type in new_columns:
                if col_name not in existing_columns:
                    connection.execute(text(f'ALTER TABLE investitionen ADD COLUMN {col_name} {col_type}'))

        # Spezialtarife: verwendung-Feld für Strompreise
        if 'strompreise' in inspector.get_table_names():
            existing_columns = {col['name'] for col in inspector.get_columns('strompreise')}
            if 'verwendung' not in existing_columns:
                connection.execute(text("ALTER TABLE strompreise ADD COLUMN verwendung VARCHAR(30) DEFAULT 'allgemein'"))

        # v3.5.0: Preset-ID für MQTT-Gateway-Mappings
        if 'mqtt_gateway_mappings' in inspector.get_table_names():
            existing_columns = {col['name'] for col in inspector.get_columns('mqtt_gateway_mappings')}
            if 'preset_id' not in existing_columns:
                connection.execute(text('ALTER TABLE mqtt_gateway_mappings ADD COLUMN preset_id VARCHAR(50)'))

        # v3.2.0: Per-Komponenten kWh in TagesZusammenfassung
        if 'tages_zusammenfassung' in inspector.get_table_names():
            existing_columns = {col['name'] for col in inspector.get_columns('tages_zusammenfassung')}
            if 'komponenten_kwh' not in existing_columns:
                connection.execute(text('ALTER TABLE tages_zusammenfassung ADD COLUMN komponenten_kwh JSON'))
            # v3.3.0: PV-Prognose für Lernfaktor
            if 'pv_prognose_kwh' not in existing_columns:
                connection.execute(text('ALTER TABLE tages_zusammenfassung ADD COLUMN pv_prognose_kwh FLOAT'))
            # v3.4.1: SFML-Tagesprognose für Prognose-Vergleich
            if 'sfml_prognose_kwh' not in existing_columns:
                connection.execute(text('ALTER TABLE tages_zusammenfassung ADD COLUMN sfml_prognose_kwh FLOAT'))
            # v3.16.0: Börsenpreis-Tagesaggregation
            if 'boersenpreis_avg_cent' not in existing_columns:
                connection.execute(text('ALTER TABLE tages_zusammenfassung ADD COLUMN boersenpreis_avg_cent FLOAT'))
            if 'boersenpreis_min_cent' not in existing_columns:
                connection.execute(text('ALTER TABLE tages_zusammenfassung ADD COLUMN boersenpreis_min_cent FLOAT'))
            if 'negative_preis_stunden' not in existing_columns:
                connection.execute(text('ALTER TABLE tages_zusammenfassung ADD COLUMN negative_preis_stunden INTEGER'))
            if 'einspeisung_neg_preis_kwh' not in existing_columns:
                connection.execute(text('ALTER TABLE tages_zusammenfassung ADD COLUMN einspeisung_neg_preis_kwh FLOAT'))
            # v3.17.0: Solcast PV-Prognose (p50, p10, p90)
            if 'solcast_prognose_kwh' not in existing_columns:
                connection.execute(text('ALTER TABLE tages_zusammenfassung ADD COLUMN solcast_prognose_kwh FLOAT'))
            if 'solcast_p10_kwh' not in existing_columns:
                connection.execute(text('ALTER TABLE tages_zusammenfassung ADD COLUMN solcast_p10_kwh FLOAT'))
            if 'solcast_p90_kwh' not in existing_columns:
                connection.execute(text('ALTER TABLE tages_zusammenfassung ADD COLUMN solcast_p90_kwh FLOAT'))

        # v3.6.9: Energieprofil-Revision — vorzeichenbasierte Aggregation, WP/Wallbox separat
        # Altdaten werden gelöscht (fehlerhafte kategorie-basierte Aggregation),
        # neue Spalten waermepumpe_kw und wallbox_kw werden ergänzt.
        if 'tages_energie_profil' in inspector.get_table_names():
            existing_columns = {col['name'] for col in inspector.get_columns('tages_energie_profil')}
            if 'waermepumpe_kw' not in existing_columns:
                # Altdaten löschen (einmalig, nur wenn neue Spalten noch nicht existieren)
                connection.execute(text('DELETE FROM tages_energie_profil'))
                connection.execute(text('DELETE FROM tages_zusammenfassung'))
                connection.execute(text('ALTER TABLE tages_energie_profil ADD COLUMN waermepumpe_kw FLOAT'))
                connection.execute(text('ALTER TABLE tages_energie_profil ADD COLUMN wallbox_kw FLOAT'))
            # v3.12.3: Per-Komponenten-Aufschlüsselung für Vollbackfill
            if 'komponenten' not in existing_columns:
                connection.execute(text('ALTER TABLE tages_energie_profil ADD COLUMN komponenten JSON'))
            # v3.16.0: Stündlicher Strompreis (Sensor + Börsenpreis getrennt)
            if 'strompreis_cent' not in existing_columns:
                connection.execute(text('ALTER TABLE tages_energie_profil ADD COLUMN strompreis_cent FLOAT'))
            if 'boersenpreis_cent' not in existing_columns:
                connection.execute(text('ALTER TABLE tages_energie_profil ADD COLUMN boersenpreis_cent FLOAT'))

        # v3.5.0: Infothek — Ansprechpartner-Verknüpfung
        if 'infothek_eintraege' in inspector.get_table_names():
            existing_columns = {col['name'] for col in inspector.get_columns('infothek_eintraege')}
            if 'ansprechpartner_id' not in existing_columns:
                connection.execute(text('ALTER TABLE infothek_eintraege ADD COLUMN ansprechpartner_id INTEGER REFERENCES infothek_eintraege(id) ON DELETE SET NULL'))
            # v3.15.2: Flag für Anlagendokumentation
            if 'in_anlagendoku' not in existing_columns:
                connection.execute(text('ALTER TABLE infothek_eintraege ADD COLUMN in_anlagendoku BOOLEAN DEFAULT 1'))

        # v3.15.2: Infothek N:M Verknüpfung mit Investitionen (Junction Table)
        # Tabelle wird von create_all erstellt (SQLAlchemy Model), hier nur Datenmigration
        table_names = inspector.get_table_names()
        if 'infothek_investition' not in table_names and 'infothek_eintraege' in table_names:
            # Junction Table manuell erstellen (vor create_all, damit Datenmigration sofort läuft)
            connection.execute(text("""
                CREATE TABLE infothek_investition (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    infothek_eintrag_id INTEGER NOT NULL REFERENCES infothek_eintraege(id) ON DELETE CASCADE,
                    investition_id INTEGER NOT NULL REFERENCES investitionen(id) ON DELETE CASCADE,
                    UNIQUE(infothek_eintrag_id, investition_id)
                )
            """))
            # Bestehende 1:1-Verknüpfungen übertragen
            connection.execute(text("""
                INSERT OR IGNORE INTO infothek_investition (infothek_eintrag_id, investition_id)
                SELECT id, investition_id FROM infothek_eintraege WHERE investition_id IS NOT NULL
            """))

    await conn.run_sync(_run_migrations)


async def init_db():
    """
    Initialisiert die Datenbank.

    Erstellt alle Tabellen falls sie nicht existieren.
    Wird beim App-Start aufgerufen.
    """
    # Importiere alle Models damit sie registriert werden
    from backend.models import anlage, monatsdaten, investition, strompreis, settings as settings_model, pvgis_prognose, activity_log, mqtt_energy_snapshot, mqtt_live_snapshot, tages_energie_profil, mqtt_gateway_mapping, infothek, api_cache

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
