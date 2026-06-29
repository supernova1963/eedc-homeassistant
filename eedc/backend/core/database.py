"""
EEDC Datenbank Setup

SQLite Datenbank mit SQLAlchemy 2.0 (async).
"""

import logging

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import event

from backend.core.config import settings

logger = logging.getLogger(__name__)


# Async Engine erstellen
engine = create_async_engine(
    settings.database_url,
    echo=settings.log_level == "debug",  # SQL Logging nur im Debug-Modus
    future=True,
)


# SQLite PRAGMAs: Foreign Keys (CASCADE DELETE), WAL (concurrent reads + 1 writer)
# und busy_timeout (zweiter Writer wartet statt sofort "database is locked").
# busy_timeout 30s als Safety-Net: die Backfill-Loops in `energie_profil/backfill.py`
# committen seit #291 pro Tag, aber bei sehr großen Cloud-Imports oder vielen
# parallelen Anlagen-Aggregaten bleibt etwas Schutz nötig (Vorher 10s reichten
# bei kingcap1 nicht).
@event.listens_for(engine.sync_engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    """Aktiviert SQLite Foreign Keys, WAL-Journal und Busy-Timeout."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=30000")
    cursor.execute("PRAGMA synchronous=NORMAL")
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


def _migrate_investitionen_parameter_keys_v325(connection) -> None:
    """
    v3.25.0 Migration: Drift zwischen Form/Wizard-Keys und Backend-Read-Keys auflösen.

    Hintergrund: Inventur in v3.25.0 hat 7 Drift-Bugs aufgedeckt — Backend-Lese-Code
    las Schlüssel, die Form/Wizard nie geschrieben haben. Mehrere Pfade (E-Auto V2H,
    E-Auto Fahrleistung, Speicher Arbitrage, Wallbox Leistung) waren dadurch effektiv
    tot. Diese Migration schreibt alle alten Keys auf den neuen Kanon um, damit
    auch historische DB-Inhalte (HA-Import, manueller JSON-Edit) konsistent sind.

    Idempotent: läuft beim ersten Mal echt, danach No-Op.
    """
    import json
    from sqlalchemy import text as _text

    # Pro Investitions-Typ: alter Key → neuer Key
    KEY_MAPPING_BY_TYP = {
        'e-auto': {
            'nutzt_v2h': 'v2h_faehig',
            'km_jahr': 'jahresfahrleistung_km',
            'pv_anteil_prozent': 'pv_ladeanteil_prozent',
            'benzin_verbrauch_liter_100km': 'vergleich_verbrauch_l_100km',
        },
        'speicher': {
            'nutzt_arbitrage': 'arbitrage_faehig',
        },
        'wallbox': {
            'leistung_kw': 'max_ladeleistung_kw',
            'ladeleistung_kw': 'max_ladeleistung_kw',  # community_service-Drift
        },
        'wechselrichter': {
            'leistung_ac_kw': 'max_leistung_kw',  # nur im toten parameter_schema
        },
    }

    rows = connection.execute(_text(
        "SELECT id, typ, parameter FROM investitionen WHERE parameter IS NOT NULL"
    )).fetchall()

    for inv_id, typ, parameter_raw in rows:
        if not parameter_raw:
            continue
        try:
            params = json.loads(parameter_raw) if isinstance(parameter_raw, str) else dict(parameter_raw)
        except (TypeError, ValueError):
            continue

        if not isinstance(params, dict):
            continue

        changed = False
        mapping = KEY_MAPPING_BY_TYP.get(typ, {})
        for alt_key, neu_key in mapping.items():
            if alt_key in params:
                # Wenn neu_key bereits gesetzt → alten Key einfach löschen,
                # neuen Wert nicht überschreiben (User hat Form-Wert geschrieben).
                if neu_key not in params or params[neu_key] in (None, '', 0, False):
                    params[neu_key] = params[alt_key]
                del params[alt_key]
                changed = True

        # Bug #8: getrennte_strommessung String 'true'/'false' → echter Boolean
        if typ == 'waermepumpe':
            gs = params.get('getrennte_strommessung')
            if isinstance(gs, str):
                params['getrennte_strommessung'] = (gs == 'true')
                changed = True

        if changed:
            connection.execute(
                _text("UPDATE investitionen SET parameter = :p WHERE id = :id"),
                {'p': json.dumps(params), 'id': inv_id},
            )


def _migrate_speicher_laedt_aus_netz_backfill(connection) -> None:
    """
    Etappe A (Issue #264): `laedt_aus_netz` als eigener Erfassungs-Schalter.

    `arbitrage_faehig=true` impliziert Netzladung — Bestands-Anlagen mit
    aktivem Arbitrage-Flag bekommen `laedt_aus_netz=true` gesetzt, damit das
    Eingabefeld `ladung_netz_kwh` weiter sichtbar bleibt (Bedingung wechselt
    von `arbitrage_faehig` auf `laedt_aus_netz`).

    Idempotent: läuft beim ersten Mal echt, danach No-Op.
    """
    import json
    from sqlalchemy import text as _text

    rows = connection.execute(_text(
        "SELECT id, parameter FROM investitionen "
        "WHERE typ = 'speicher' AND parameter IS NOT NULL"
    )).fetchall()

    for inv_id, parameter_raw in rows:
        if not parameter_raw:
            continue
        try:
            params = json.loads(parameter_raw) if isinstance(parameter_raw, str) else dict(parameter_raw)
        except (TypeError, ValueError):
            continue

        if not isinstance(params, dict):
            continue

        if not params.get('arbitrage_faehig'):
            continue
        if params.get('laedt_aus_netz') is True:
            continue  # bereits gesetzt — No-Op

        params['laedt_aus_netz'] = True
        connection.execute(
            _text("UPDATE investitionen SET parameter = :p WHERE id = :id"),
            {'p': json.dumps(params), 'id': inv_id},
        )


def _migrate_pv_erzeugung_aggregat_clear(connection) -> None:
    """kWp-Verteilung-Etappe: `monatsdaten.pv_erzeugung_kwh` als rein manuelles
    Aggregat etablieren (Invariante, [[project_kwp_verteilung_aggregator]]).

    Bestandszeilen, bei denen für denselben Monat Pro-Modul-IMD-Werte
    (pv-module/balkonkraftwerk mit `pv_erzeugung_kwh`) existieren, hatten das
    Feld bislang als Auto-Summe der Module befüllt (alter Form-Pfad
    MonatsdatenForm). Diese Auto-Summen werden geleert — die Pro-Modul-Werte
    sind die Wahrheit und werden zur Lesezeit aggregiert/verteilt. Feldwerte
    OHNE Pro-Modul-Werte bleiben erhalten (echtes Aggregat, z. B. JayJayX #651).
    Kriterium ist „Pro-Modul vorhanden ja/nein", NICHT die Herkunft.

    Idempotent (No-Op nach erstem Lauf — danach gibt es keine Zeile mehr mit
    Feldwert UND Pro-Modul-Werten). Verifiziert 2026-06-06: kein Code-Pfad
    schrieb je verteilte Werte in die Modul-IMD, Bestands-Pro-Modul-Werte sind
    gemessen/importiert → Migration sicher.
    """
    import json
    from sqlalchemy import text as _text

    md_rows = connection.execute(_text(
        "SELECT id, anlage_id, jahr, monat FROM monatsdaten "
        "WHERE pv_erzeugung_kwh IS NOT NULL"
    )).fetchall()
    if not md_rows:
        return

    for md_id, anlage_id, jahr, monat in md_rows:
        imd_rows = connection.execute(_text(
            "SELECT imd.verbrauch_daten FROM investition_monatsdaten imd "
            "JOIN investitionen i ON i.id = imd.investition_id "
            "WHERE i.anlage_id = :aid AND i.typ IN ('pv-module', 'balkonkraftwerk') "
            "AND imd.jahr = :j AND imd.monat = :m"
        ), {"aid": anlage_id, "j": jahr, "m": monat}).fetchall()

        hat_pro_modul = False
        for (vd_raw,) in imd_rows:
            if not vd_raw:
                continue
            try:
                vd = json.loads(vd_raw) if isinstance(vd_raw, str) else dict(vd_raw)
            except (TypeError, ValueError):
                continue
            if isinstance(vd, dict) and vd.get("pv_erzeugung_kwh") is not None:
                hat_pro_modul = True
                break

        if hat_pro_modul:
            connection.execute(
                _text("UPDATE monatsdaten SET pv_erzeugung_kwh = NULL WHERE id = :id"),
                {"id": md_id},
            )


_DEAD_STRATEGIEN = {"kwp_verteilung", "ev_quote", "cop_berechnung", "manuell"}


def _migrate_sensor_mapping_strategien_clear(connection) -> None:
    """Datenchecker-Achse A1 (v3.39.0): Dead-Strategie-Werte im
    `anlagen.sensor_mapping`-JSON auf `keine` umschreiben.

    Das `StrategieTyp`-Enum wurde auf `sensor` + `keine` reduziert
    (`api/routes/sensor_mapping.py`). Die früheren Werte
    `kwp_verteilung`/`ev_quote`/`cop_berechnung`/`manuell` waren Dead Code —
    nur `sensor` wird in den Aggregatoren ausgewertet, der Rest lieferte nie
    Daten. **HARD-PRECONDITION:** `FeldMapping.strategie` ist Pydantic-
    validiert; gespeicherte Mappings mit einem Dead-Wert scheitern beim
    nächsten Save-Parse, sobald das reduzierte Enum live ist. Diese Migration
    muss vorher laufen.

    Idempotent: nach dem ersten Lauf existiert kein Dead-Wert mehr → No-Op.
    Verschachtelung: `basis.<feld>` und `investitionen.<id>.felder.<feld>`
    tragen `{strategie, ...}`-Dicts; `live`/`live_invert` sind String-/Bool-
    Maps und werden übersprungen.
    """
    import json
    from sqlalchemy import text as _text

    rows = connection.execute(_text(
        "SELECT id, sensor_mapping FROM anlagen WHERE sensor_mapping IS NOT NULL"
    )).fetchall()
    if not rows:
        return

    def _rewrite_feld(feld) -> bool:
        """True wenn ein Dead-Wert auf `keine` umgeschrieben wurde."""
        if isinstance(feld, dict) and feld.get("strategie") in _DEAD_STRATEGIEN:
            feld["strategie"] = "keine"
            return True
        return False

    for anlage_id, mapping_raw in rows:
        if not mapping_raw:
            continue
        try:
            mapping = json.loads(mapping_raw) if isinstance(mapping_raw, str) else dict(mapping_raw)
        except (TypeError, ValueError):
            continue
        if not isinstance(mapping, dict):
            continue

        changed = False

        for feld in (mapping.get("basis") or {}).values():
            changed |= _rewrite_feld(feld)

        for inv_data in (mapping.get("investitionen") or {}).values():
            if isinstance(inv_data, dict):
                for feld in (inv_data.get("felder") or {}).values():
                    changed |= _rewrite_feld(feld)

        if changed:
            connection.execute(
                _text("UPDATE anlagen SET sensor_mapping = :m WHERE id = :id"),
                {"m": json.dumps(mapping), "id": anlage_id},
            )


def _migrate_connector_field_inv_map_backfill(connection) -> None:
    """Fall B (#300): vor v3.39.0 angelegte `connector_config` hat keine
    `field_inv_map`. Der automatische Energy-Poll (`e4471ca2`/v3.39.0) publisht
    PV dann nur aufs Fallback-Topic `pv_gesamt_kwh` und Speicher/Wallbox gar
    nicht — die Werte aktualisieren sich nicht automatisch, nur der manuelle
    `/fetch` füllt sie. Diese Migration leitet die `field_inv_map` einmalig aus
    den Investitionen der Anlage ab — gleiche Typ-Regeln wie der
    `/connectors/mapping`-Endpoint, aber NUR bei eindeutiger Zuordnung (genau
    eine aktive Investition des passenden Typs). Mehrdeutige Kategorien bleiben
    offen, der Nutzer ordnet sie im UI zu (kein erfundener Default).

    Idempotent: bestehende nicht-leere `field_inv_map` → No-Op. Konnte nichts
    abgeleitet werden, bleibt das Feld absent und ein späterer Boot versucht es
    erneut (z. B. nachdem die passende Investition angelegt wurde).
    [[project_connector_mqtt_energie]]
    """
    import json
    from sqlalchemy import text as _text

    # Spiegelt _KATEGORIE_TYPEN aus api/routes/connector.py
    KATEGORIE_TYPEN = {
        "pv": {"pv-module", "balkonkraftwerk"},
        "speicher": {"speicher"},
        "wallbox": {"wallbox"},
    }

    rows = connection.execute(_text(
        "SELECT id, connector_config FROM anlagen WHERE connector_config IS NOT NULL"
    )).fetchall()
    if not rows:
        return

    for anlage_id, cfg_raw in rows:
        if not cfg_raw:
            continue
        try:
            cfg = json.loads(cfg_raw) if isinstance(cfg_raw, str) else dict(cfg_raw)
        except (TypeError, ValueError):
            continue
        if not isinstance(cfg, dict):
            continue
        # Nur konfigurierte Connectoren ohne (sinnvolle) Zuordnung
        if not cfg.get("connector_id") or not cfg.get("host"):
            continue
        if cfg.get("field_inv_map"):  # bereits gesetzt (nicht-leer) → No-Op
            continue

        # Aktive Investitionen der Anlage (aktiv != False) nach Typ
        inv_rows = connection.execute(_text(
            "SELECT id, typ FROM investitionen "
            "WHERE anlage_id = :aid AND (aktiv IS NULL OR aktiv != 0)"
        ), {"aid": anlage_id}).fetchall()

        derived: dict[str, int] = {}
        for kategorie, typen in KATEGORIE_TYPEN.items():
            matches = [inv_id for inv_id, typ in inv_rows if typ in typen]
            if len(matches) == 1:  # nur Eindeutiges automatisch zuordnen
                derived[kategorie] = matches[0]

        if not derived:
            continue

        cfg["field_inv_map"] = derived
        connection.execute(
            _text("UPDATE anlagen SET connector_config = :c WHERE id = :id"),
            {"c": json.dumps(cfg), "id": anlage_id},
        )


def _migrate_verbrauch_daten_keys_v326(connection) -> None:
    """
    v3.25.8 Migration: Drift-Pairs in verbrauch_daten-JSON konsolidieren.

    Hintergrund: Drift-Audit Bündel G hat 27+ Stellen identifiziert mit
    Mustern wie `data.get("a", 0) or data.get("b", 0)` für historisch
    umbenannte Felder. Beide Keys konnten parallel in derselben Row stehen.
    Diese Migration zieht den Legacy-Wert auf den kanonischen Key, falls
    dieser fehlt — danach lesen die zentralen Reader-Helper aus
    field_definitions.py konsistent.

    Konsolidierte Pairs (Legacy → Kanon):
      erzeugung_kwh        → pv_erzeugung_kwh        (PV-Modul, BKW)
      heizung_kwh          → heizenergie_kwh         (WP)
      verbrauch_kwh        → ladung_kwh              (E-Auto, Wallbox)
      speicher_ladung_netz_kwh → ladung_netz_kwh     (Speicher Arbitrage)

    Achtung: `verbrauch_kwh` ist bei Sonstiges-Investitionen ein eigenes
    legitimes Feld (Verbraucher-Kategorie). Diese Migration prüft daher den
    Investitions-Typ; bei Sonstiges bleibt `verbrauch_kwh` unangetastet.

    Idempotent: läuft beim ersten Mal echt, danach No-Op.
    """
    import json
    from sqlalchemy import text as _text

    # Pro Investitions-Typ: Legacy-Key → Kanon-Key
    KEY_MAPPING_BY_TYP = {
        'pv-module': {
            'erzeugung_kwh': 'pv_erzeugung_kwh',
        },
        'balkonkraftwerk': {
            'erzeugung_kwh': 'pv_erzeugung_kwh',
        },
        'waermepumpe': {
            'heizung_kwh': 'heizenergie_kwh',
        },
        'e-auto': {
            'verbrauch_kwh': 'ladung_kwh',
        },
        'wallbox': {
            'verbrauch_kwh': 'ladung_kwh',
        },
        'speicher': {
            'speicher_ladung_netz_kwh': 'ladung_netz_kwh',
        },
        # 'sonstiges': absichtlich nicht — verbrauch_kwh ist dort der kanon. Key
    }

    # Investitionen mit Typ joinen
    rows = connection.execute(_text(
        "SELECT imd.id, i.typ, imd.verbrauch_daten "
        "FROM investition_monatsdaten imd "
        "JOIN investitionen i ON i.id = imd.investition_id "
        "WHERE imd.verbrauch_daten IS NOT NULL"
    )).fetchall()

    for imd_id, typ, daten_raw in rows:
        if not daten_raw:
            continue
        try:
            data = json.loads(daten_raw) if isinstance(daten_raw, str) else dict(daten_raw)
        except (TypeError, ValueError):
            continue

        if not isinstance(data, dict):
            continue

        changed = False
        mapping = KEY_MAPPING_BY_TYP.get(typ, {})
        for legacy_key, kanon_key in mapping.items():
            if legacy_key in data:
                # Wenn Kanon-Key bereits gesetzt → Legacy einfach löschen,
                # neuen Wert nicht überschreiben.
                if kanon_key not in data or data[kanon_key] in (None, '', 0):
                    data[kanon_key] = data[legacy_key]
                del data[legacy_key]
                changed = True

        if changed:
            connection.execute(
                _text("UPDATE investition_monatsdaten SET verbrauch_daten = :d WHERE id = :id"),
                {'d': json.dumps(data), 'id': imd_id},
            )


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
                # v3.17: Prognose-Basis (openmeteo, solcast, sfml) — DEPRECATED, durch prognose_quelle ersetzt
                ('prognose_basis', "VARCHAR(30) DEFAULT 'openmeteo'"),
                # v3.30: Prognosequelle pro Anlage (eedc, solcast, sfml)
                ('prognose_quelle', "VARCHAR(30) DEFAULT 'eedc'"),
                # §51 EEG Negativpreis-Abzug pro Anlage (manueller Schalter, Default aus)
                ('unterliegt_eeg_51', 'BOOLEAN DEFAULT 0'),
                # v3.43: Günstig-Schwelle der Börsenpreis-Sensoren (% unter Ø ohne 3 Peaks)
                ('guenstig_schwelle_prozent', 'FLOAT DEFAULT 10.0'),
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

            # v3.30: prognose_basis → prognose_quelle migrieren
            if 'prognose_quelle' in newly_added:
                # openmeteo → eedc (Default), solcast → solcast (pur)
                connection.execute(text("""
                    UPDATE anlagen SET prognose_quelle = CASE
                        WHEN prognose_basis = 'solcast' THEN 'solcast'
                        ELSE 'eedc'
                    END
                    WHERE prognose_quelle IS NULL OR prognose_quelle = 'eedc'
                """))

            # Datenchecker-Achse A1 (v3.39.0): Dead-Strategie-Werte im
            # sensor_mapping-JSON auf `keine` umschreiben — Hard-Precondition
            # vor der StrategieTyp-Enum-Reduktion (Pydantic-validiert).
            # Idempotent. [[project_datenchecker_konsistenz]]
            _migrate_sensor_mapping_strategien_clear(connection)

            # Fall B (#300): vor v3.39.0 angelegte connector_config ohne
            # field_inv_map nachrüsten — der automatische Energy-Poll publisht
            # sonst PV nur aufs Fallback-Topic und Speicher/Wallbox gar nicht.
            # Leitet die Zuordnung eindeutig aus den Investitionen ab. Idempotent.
            # [[project_connector_mqtt_energie]]
            _migrate_connector_field_inv_map_backfill(connection)

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
                # v3.17.0: Kraftstoffpreis aus EU Oil Bulletin
                ('kraftstoffpreis_euro', 'FLOAT'),
                # v3.21.0: Alter Energiepreis (Gas/Öl) pro Monat für WP-Alternativvergleich
                ('gaspreis_cent_kwh', 'FLOAT'),
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
                # #284: Graue Herstellungs-Last (CO2) — optionales Override für die
                # CO2-Amortisation; leer = Default-Richtwert nach Typ/Größe.
                ('graue_last_kg', 'FLOAT'),
            ]
            for col_name, col_type in new_columns:
                if col_name not in existing_columns:
                    connection.execute(text(f'ALTER TABLE investitionen ADD COLUMN {col_name} {col_type}'))

            # v3.25.0: Investitions-Parameter-Key-Vereinheitlichung (siehe
            # docs/drafts/INVENTUR-INVESTITIONS-PARAMETER.md). 7 Drift-Bugs zwischen Form/Wizard
            # und Backend-Reads sind in v3.25.0 gefixt — bestehende Anlagen können historisch
            # aber alte Keys gespeichert haben (typischerweise nicht, weil Form/Wizard-Schreibseite
            # immer kanonisch war, aber HA-Import o. ä. Schreib-Pfade können zu Drift geführt haben).
            # Diese Migration schreibt alte Keys auf neue Kanon-Keys um. Idempotent.
            _migrate_investitionen_parameter_keys_v325(connection)

            # v3.25.8: verbrauch_daten-JSON Legacy-Keys auf Kanon-Keys umschreiben
            # (Drift-Audit Bündel G — `pv_erzeugung_kwh`/`erzeugung_kwh`,
            # `heizenergie_kwh`/`heizung_kwh`, `ladung_kwh`/`verbrauch_kwh`,
            # `ladung_netz_kwh`/`speicher_ladung_netz_kwh`). Idempotent.
            _migrate_verbrauch_daten_keys_v326(connection)

            # Etappe A (Issue #264): `laedt_aus_netz` als eigener Erfassungs-
            # Schalter. Backfill: arbitrage_faehig=true ⇒ laedt_aus_netz=true.
            _migrate_speicher_laedt_aus_netz_backfill(connection)

            # kWp-Verteilung-Etappe (#289/#651): pv_erzeugung_kwh ist ein rein
            # manuelles Aggregat — Auto-Summen mit Pro-Modul-Werten im Monat
            # leeren, Read-time-Verteilung übernimmt. Idempotent.
            _migrate_pv_erzeugung_aggregat_clear(connection)

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
            # Kraftstoffpreis (EU Weekly Oil Bulletin, €/L)
            if 'kraftstoffpreis_euro' not in existing_columns:
                connection.execute(text('ALTER TABLE tages_zusammenfassung ADD COLUMN kraftstoffpreis_euro FLOAT'))
            # v3.17.0: Solcast PV-Prognose (p50, p10, p90)
            if 'solcast_prognose_kwh' not in existing_columns:
                connection.execute(text('ALTER TABLE tages_zusammenfassung ADD COLUMN solcast_prognose_kwh FLOAT'))
            if 'solcast_p10_kwh' not in existing_columns:
                connection.execute(text('ALTER TABLE tages_zusammenfassung ADD COLUMN solcast_p10_kwh FLOAT'))
            if 'solcast_p90_kwh' not in existing_columns:
                connection.execute(text('ALTER TABLE tages_zusammenfassung ADD COLUMN solcast_p90_kwh FLOAT'))
            # Day-Ahead Stundenprofil-Snapshot (24 Werte JSON, vor Sonnenaufgang gefroren)
            if 'pv_prognose_stundenprofil' not in existing_columns:
                connection.execute(text('ALTER TABLE tages_zusammenfassung ADD COLUMN pv_prognose_stundenprofil JSON'))
            if 'solcast_prognose_stundenprofil' not in existing_columns:
                connection.execute(text('ALTER TABLE tages_zusammenfassung ADD COLUMN solcast_prognose_stundenprofil JSON'))
            # Tracking #110 „A": SFML/Tom-HA echtes Stundenprofil (Backward-Slots)
            if 'sfml_prognose_stundenprofil' not in existing_columns:
                connection.execute(text('ALTER TABLE tages_zusammenfassung ADD COLUMN sfml_prognose_stundenprofil JSON'))
            # v3.24.0 (Issue #136): WP-Starts und andere Counter pro Komponente
            if 'komponenten_starts' not in existing_columns:
                connection.execute(text('ALTER TABLE tages_zusammenfassung ADD COLUMN komponenten_starts JSON'))
            # Prognose-Kanon §6: konvergenz-gefrorener Genauigkeits-Endwert
            # (rollt mit, bis OM für den Tag konvergiert; dann via _final_at fix).
            if 'pv_prognose_final_kwh' not in existing_columns:
                connection.execute(text('ALTER TABLE tages_zusammenfassung ADD COLUMN pv_prognose_final_kwh FLOAT'))
            if 'pv_prognose_final_at' not in existing_columns:
                connection.execute(text('ALTER TABLE tages_zusammenfassung ADD COLUMN pv_prognose_final_at VARCHAR(40)'))

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
            # v3.24.0 (Issue #136): WP-Kompressor-Starts pro Stunde
            if 'wp_starts_anzahl' not in existing_columns:
                connection.execute(text('ALTER TABLE tages_energie_profil ADD COLUMN wp_starts_anzahl INTEGER'))
            # Issue #238: WP-Betriebsstunden pro Stunde (analog Kompressor-Starts)
            if 'wp_betriebsstunden' not in existing_columns:
                connection.execute(text('ALTER TABLE tages_energie_profil ADD COLUMN wp_betriebsstunden FLOAT'))
            # v3.26.0: Stündliches Wetter (Bewölkung, Niederschlag, WMO-Code)
            # für Wetter-Stratifizierung und Korrekturprofil — siehe KONZEPT-KORREKTURPROFIL.md
            if 'bewoelkung_prozent' not in existing_columns:
                connection.execute(text('ALTER TABLE tages_energie_profil ADD COLUMN bewoelkung_prozent FLOAT'))
            if 'niederschlag_mm' not in existing_columns:
                connection.execute(text('ALTER TABLE tages_energie_profil ADD COLUMN niederschlag_mm FLOAT'))
            if 'wetter_code' not in existing_columns:
                connection.execute(text('ALTER TABLE tages_energie_profil ADD COLUMN wetter_code INTEGER'))

        # Etappe 3c P1 (KONZEPT-ENERGIEPROFIL-3C.md): Source-Marker auf SensorSnapshot.
        # Diagnostiziert Schreib-Pfad pro Snapshot — Voraussetzung für 3d-Schablone.
        if 'sensor_snapshots' in inspector.get_table_names():
            existing_columns = {col['name'] for col in inspector.get_columns('sensor_snapshots')}
            if 'quelle' not in existing_columns:
                connection.execute(text(
                    "ALTER TABLE sensor_snapshots ADD COLUMN quelle VARCHAR(20) NOT NULL DEFAULT 'unknown'"
                ))
                # Idempotenz-Sicherheitsnetz: bestehende Zeilen explizit auf 'unknown'
                # setzen, falls die DEFAULT-Klausel auf älteren SQLite-Versionen nicht
                # rückwirkend wirkt.
                connection.execute(text(
                    "UPDATE sensor_snapshots SET quelle = 'unknown' WHERE quelle IS NULL"
                ))

        # Etappe 3d P1 (KONZEPT-DATENPIPELINE.md Sektion 3.2 + 6.1):
        # source_provenance JSON-Spalte auf 4 Aggregat-Tabellen für Per-Feld-Provenance,
        # source_hash TEXT-Spalte auf monatsdaten + investition_monatsdaten für
        # Idempotenz-Detection bei Cloud-/CSV-Re-Imports (P2-Lieferung).
        # Helper write_with_provenance() liest/schreibt diese Spalten erst ab P3.
        for tbl in ('monatsdaten', 'investition_monatsdaten',
                    'tages_zusammenfassung', 'tages_energie_profil'):
            if tbl in inspector.get_table_names():
                existing = {col['name'] for col in inspector.get_columns(tbl)}
                if 'source_provenance' not in existing:
                    connection.execute(text(
                        f"ALTER TABLE {tbl} ADD COLUMN source_provenance JSON "
                        "NOT NULL DEFAULT '{}'"
                    ))
                    # Idempotenz-Sicherheitsnetz für ältere SQLite-Versionen,
                    # bei denen DEFAULT '{}' beim ALTER nicht rückwirkend wirkt.
                    connection.execute(text(
                        f"UPDATE {tbl} SET source_provenance = '{{}}' "
                        "WHERE source_provenance IS NULL"
                    ))
        for tbl in ('monatsdaten', 'investition_monatsdaten'):
            if tbl in inspector.get_table_names():
                existing = {col['name'] for col in inspector.get_columns(tbl)}
                if 'source_hash' not in existing:
                    connection.execute(text(
                        f"ALTER TABLE {tbl} ADD COLUMN source_hash VARCHAR(80)"
                    ))

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


async def _run_data_migrations() -> None:
    """Idempotente asynchrone Daten-Migrationen.

    Im Gegensatz zu `_run_migrations` (sync, SQLite-DDL) brauchen wir hier
    Snapshot-Reads + Aggregator-Aufrufe, also einen Async-Session-Pfad.
    Idempotenz über `migrations`-Tabelle: pro `name` läuft die Migration
    genau einmal pro Installation.
    """
    from datetime import datetime as _dt
    from sqlalchemy import text as _text

    async with async_session_maker() as session:
        await session.execute(_text(
            "CREATE TABLE IF NOT EXISTS migrations ("
            "  name VARCHAR(100) PRIMARY KEY,"
            "  applied_at TEXT NOT NULL"
            ")"
        ))
        await session.commit()

        async def _apply_once(name: str, fn) -> None:
            already = await session.execute(
                _text("SELECT 1 FROM migrations WHERE name = :n"), {"n": name}
            )
            if already.scalar_one_or_none():
                return
            try:
                await fn(session)
            except Exception as e:
                logger.error(f"Daten-Migration {name} fehlgeschlagen: {type(e).__name__}: {e}")
                await session.rollback()
                return
            await session.execute(
                _text("INSERT INTO migrations (name, applied_at) VALUES (:n, :t)"),
                {"n": name, "t": _dt.now().isoformat()},
            )
            await session.commit()

        # Etappe 3c P2: Counter-Stundenwerte auf Backward umrechnen
        from backend.services.snapshot.migrate import migrate_3c_p2_counter_backward
        await _apply_once("etappe_3c_p2_counter_hourly_backward", migrate_3c_p2_counter_backward)

        # Etappe 3d P3: Initial-source_provenance für Bestandsdaten
        from backend.services.provenance_migrate import (
            migrate_3d_p3_initial_provenance_legacy_unknown,
        )
        await _apply_once(
            "etappe_3d_p3_initial_provenance_legacy_unknown",
            migrate_3d_p3_initial_provenance_legacy_unknown,
        )

        # Etappe 4 (v3.31.0): reset vollbackfill_durchgefuehrt für Anlagen
        # mit HA-Integration, damit der nächste Monatsabschluss einen
        # Auto-Vollbackfill aus HA-LTS auslöst und alte Mix-Source-Aggregate
        # durch saubere LTS-Werte ersetzt werden.
        from backend.services.etappe_4_migrate import (
            migrate_etappe_4_reset_vollbackfill,
        )
        await _apply_once(
            "etappe_4_v3_31_0_reset_vollbackfill_for_ha_lts_switch",
            migrate_etappe_4_reset_vollbackfill,
        )

        # v3.33.0 (Issue #290): Historische LTS-komponenten_kwh-Drift
        # bereinigen. MUSS nach dem Helper-basierten Aggregator-Fix
        # (Schritt 1–3) laufen, sonst reaggregiert sie mit dem alten Bug.
        from backend.services.migrations.migrate_v3_33_0_lts_komponenten_kwh import (
            migrate_lts_komponenten_kwh_bug,
        )
        await _apply_once(
            "v3_33_0_lts_komponenten_kwh_bereinigung",
            migrate_lts_komponenten_kwh_bug,
        )

        # Phase 2a Etappe 4 (#262 u. a.): E-Mob-Heimladung in den kanonischen
        # Wallbox-Slot konsolidieren, damit der strukturelle Read (Etappe 2)
        # un-migrierte Dual-Daten nicht unterzählt. MUSS mit der Read-/Write-
        # Umstellung (Etappe 2+3) zusammen ausgeliefert werden.
        from backend.services.migrations.migrate_emob_canonical_source import (
            migrate_emob_canonical_source,
        )
        await _apply_once(
            "phase_2a_emob_canonical_source",
            migrate_emob_canonical_source,
        )

        # HINWEIS (v3.45.8): Die in v3.45.7 hier registrierte Migration
        # `batterie_kw_entladung_positiv` wurde ENTFERNT. Sie reaggregierte beim
        # Start ALLE historischen Tage über externe HTTP-Calls (HA-History +
        # awattar + open-meteo) und blockierte damit den App-Start so lange, dass
        # der Supervisor den Add-on-Start abbrach → Neustart-Schleife. Der
        # Code-Fix (batterie_kw_spalte + komponenten_beitraege) bleibt aktiv, d.h.
        # NEUE Aggregationen sind korrekt; Alt-Tage heilen sich beim nächsten
        # regulären Reaggregieren bzw. via „Tag neu berechnen". Eine sichere,
        # nicht-blockierende Historien-Korrektur kann separat nachgezogen werden.


async def init_db():
    """
    Initialisiert die Datenbank.

    Erstellt alle Tabellen falls sie nicht existieren.
    Wird beim App-Start aufgerufen.
    """
    # Importiere alle Models damit sie registriert werden
    from backend.models import anlage, monatsdaten, investition, strompreis, settings as settings_model, pvgis_prognose, activity_log, mqtt_energy_snapshot, mqtt_live_snapshot, tages_energie_profil, mqtt_gateway_mapping, infothek, api_cache, sensor_snapshot, data_provenance_log

    async with engine.begin() as conn:
        # Migrationen ausführen
        await run_migrations(conn)
        # Erstelle alle Tabellen
        await conn.run_sync(Base.metadata.create_all)

    # Asynchrone Daten-Migrationen (idempotent über migrations-Tabelle)
    await _run_data_migrations()


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
