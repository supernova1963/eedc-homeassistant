"""Alt-Schema → ``run_migrations`` → Schema geprüft (M10, E6).

**Was bisher fehlte.** Alle neun benannten ``_migrate_*``-Funktionen und die
sechs Module unter ``services/migrations/`` haben Tests. Der ``ALTER TABLE ADD
COLUMN``-Block in ``core/database.py`` hatte keinen — **86 ergänzte Spalten
über zehn Tabellen** (mechanisch gezählt 2026-08-24 über die literalen
Anweisungen *und* die ``new_columns``-Schleifen; der Plan sagte „>30", die
reine Textzählung liefert 46).

**Warum das die riskanteste ungedeckte Fläche der Suite ist.** Der Block läuft
genau einmal je Anwender-Installation, beim ersten Start nach dem Update, gegen
eine Datenbank, die es auf keiner Entwicklungsbox gibt. Ein frischer Testlauf
trifft ihn **nie**: ``create_all`` legt die Tabellen schon vollständig an, und
``run_migrations`` findet nichts zu tun. Schlägt er fehl, merkt es niemand hier
— nur der Anwender, dessen Sicht danach leer ist.

⭐ **Das Alt-Schema wird aus den Modellen ABGELEITET, nicht getippt.** Ein
handgeschriebenes „so sah die Tabelle 2024 aus" baut zwangsläufig eine
Vergangenheit nach, die es nie gab — beim Bau dieser Datei zweimal passiert
(``pvgis_prognosen.ist_aktiv`` und ``investitionen.parameter`` stehen seit dem
Commit dort, der die Tabelle angelegt hat, ``c3c0c75f`` bzw. ``8ae06f8b``).
Deshalb: **heutige Tabelle minus die Spalten, die die Migration ergänzt.** Das
ist per Konstruktion genau der Zustand von davor, und es bleibt richtig, wenn
jemand eine Spalte ergänzt.
"""

from __future__ import annotations

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.dialects import sqlite as sqlite_dialect
from sqlalchemy.schema import CreateTable

from backend.core.database import Base, run_migrations

# Die Modelle registrieren ihre Tabellen erst beim Import auf `Base.metadata`.
# ⚠ Dieselbe Liste wie in `init_db()` — `backend.models` allein genuegt NICHT,
# `sensor_snapshots` und `mqtt_gateway_mappings` fehlen dort (gemessen).
from backend.models import (  # noqa: F401  (Seiteneffekt: Registrierung)
    activity_log, anlage, api_cache, data_provenance_log, infothek,
    investition, monatsdaten as _monatsdaten_model, mqtt_energy_snapshot,
    mqtt_gateway_mapping, mqtt_live_snapshot, pvgis_prognose, sensor_snapshot,
    settings as _settings_model, strompreis, tages_energie_profil,
)

#: Was der Migrationsblock je Tabelle ergänzt — Stand 2026-08-24, mechanisch
#: über `ALTER TABLE … ADD COLUMN` **und** die `new_columns`-Schleifen erhoben.
#: ⚠ Diese Liste ist zugleich Fixture (was weggelassen wird) und Behauptung
#: (was danach da sein muss). Wer eine Spalte ergänzt, trägt sie hier ein.
ERGAENZTE_SPALTEN: dict[str, list[str]] = {
    "anlagen": [
        "community_auto_share", "community_hash", "connector_config",
        "guenstig_schwelle_prozent", "ha_sensor_batterie_entladung",
        "ha_sensor_batterie_ladung", "ha_sensor_einspeisung",
        "ha_sensor_netzbezug", "ha_sensor_pv_erzeugung", "horizont_daten",
        "mastr_id", "netz_puffer_w", "prognose_basis", "prognose_quelle",
        "sensor_mapping", "standort_land", "steuerliche_behandlung",
        "unterliegt_eeg_51", "ust_satz_prozent", "versorger_daten",
        "vollbackfill_durchgefuehrt", "wechselrichter_hersteller",
        "wetter_modell", "wetter_provider",
    ],
    "monatsdaten": [
        "batterie_vollzyklen", "defizit_kwh", "durchschnittstemperatur",
        "einspeise_durchschnittspreis_cent", "gaspreis_cent_kwh",
        "kraftstoffpreis_euro", "netzbezug_durchschnittspreis_cent", "notizen",
        "peak_netzbezug_kw", "performance_ratio", "sonderkosten_beschreibung",
        "sonderkosten_euro", "sonstige_positionen", "ueberschuss_kwh",
        # Etappe 3d P1/P2 — eigener Block, nicht in `new_columns`
        "source_provenance", "source_hash",
    ],
    "investitionen": [
        "ausrichtung", "graue_last_kg", "ha_entity_id", "leistung_kwp",
        "neigung_grad", "stilllegungsdatum",
    ],
    "investition_monatsdaten": ["source_provenance", "source_hash"],
    "strompreise": [
        "einspeisung_variabel", "verwendung", "zaehlergebuehr_euro_jahr",
    ],
    "pvgis_prognosen": [
        "gesamt_leistung_kwp", "horizont_verwendet", "module_monatswerte",
        "raddatabase",
    ],
    "mqtt_gateway_mappings": ["preset_id"],
    "sensor_snapshots": ["quelle"],
    "infothek_eintraege": ["ansprechpartner_id", "in_anlagendoku"],
    "tages_energie_profil": [
        "betriebsmodus_je_wp", "bewoelkung_prozent", "boersenpreis_cent",
        "komponenten", "niederschlag_mm", "soc_je_speicher", "strompreis_cent",
        "waermepumpe_kw", "wallbox_kw", "wetter_code", "wp_betriebsstunden",
        "wp_starts_anzahl", "source_provenance",
    ],
    "tages_zusammenfassung": [
        "boersenpreis_avg_cent", "boersenpreis_min_cent",
        "einspeisung_neg_preis_kwh", "emob_ladung_netz_abgeleitet_kwh",
        "emob_ladung_pv_abgeleitet_kwh", "komponenten_kwh",
        "komponenten_starts", "kraftstoffpreis_euro", "negative_preis_stunden",
        "pv_prognose_final_at", "pv_prognose_final_kwh", "pv_prognose_kwh",
        "pv_prognose_stundenprofil", "sfml_prognose_kwh",
        "sfml_prognose_stundenprofil", "solcast_p10_kwh", "solcast_p90_kwh",
        "solcast_prognose_kwh", "solcast_prognose_stundenprofil",
        "source_provenance",
    ],
}


def _alt_ddl(tabellenname: str) -> str:
    """``CREATE TABLE`` des heutigen Modells **ohne** die ergänzten Spalten."""
    heute = Base.metadata.tables[tabellenname]
    weglassen = set(ERGAENZTE_SPALTEN.get(tabellenname, ()))
    alt = heute.to_metadata(
        type(heute.metadata)(),          # eigene, leere MetaData
        referred_schema_fn=lambda *_a, **_k: None,
    )
    for spalte in list(alt.columns):
        if spalte.name in weglassen:
            alt._columns.remove(spalte)
    # Fremdschlüssel/Indizes interessieren hier nicht — nur die Spaltenmenge.
    alt.constraints = {c for c in alt.constraints if c.__class__.__name__
                       == "PrimaryKeyConstraint"}
    alt.indexes.clear()
    return str(CreateTable(alt).compile(dialect=sqlite_dialect.dialect()))


async def _einfuegen(conn, tabelle: str, **werte):
    """Fügt eine Zeile ein und füllt übrige Pflichtspalten mit Platzhaltern.

    ⚠ Bewusst generisch: welche Spalte gerade ``NOT NULL`` ist, ist eine
    Eigenschaft des Modells und ändert sich. Eine handgepflegte INSERT-Liste
    wäre der nächste Ort, an dem diese Datei veraltet.
    """
    tab = Base.metadata.tables[tabelle]
    weglassen = set(ERGAENZTE_SPALTEN.get(tabelle, ()))
    zeile = dict(werte)
    for spalte in tab.columns:
        if spalte.name in weglassen or spalte.name in zeile:
            continue
        if spalte.nullable or spalte.primary_key:
            continue
        typ = spalte.type.__class__.__name__.lower()
        if "date" in typ and "time" not in typ:
            zeile[spalte.name] = "2024-01-01"
        elif "datetime" in typ or "timestamp" in typ:
            zeile[spalte.name] = "2024-01-01 00:00:00"
        elif "int" in typ or "float" in typ or "numeric" in typ or "bool" in typ:
            zeile[spalte.name] = 0
        else:
            zeile[spalte.name] = ""
    spalten = ", ".join(zeile)
    platzhalter = ", ".join(f":{k}" for k in zeile)
    await conn.execute(
        text(f"INSERT INTO {tabelle} ({spalten}) VALUES ({platzhalter})"), zeile
    )


async def _alt_datenbank(tmp_path, *, tabellen=None, mit_zeilen=True):
    """Legt eine SQLite-Datei mit dem abgeleiteten Alt-Schema an."""
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'alt.db'}")
    namen = list(ERGAENZTE_SPALTEN) if tabellen is None else tabellen
    async with engine.begin() as conn:
        for name in namen:
            await conn.execute(text(_alt_ddl(name)))
        if mit_zeilen:
            await _einfuegen(
                conn, "anlagen",
                id=1, anlagenname="Bestandsanlage", leistung_kwp=9.9,
            )
            await _einfuegen(
                conn, "monatsdaten",
                id=1, anlage_id=1, jahr=2024, monat=7, pv_erzeugung_kwh=1234.5,
            )
            await _einfuegen(
                conn, "strompreise",
                id=1, anlage_id=1, gueltig_ab="2024-01-01",
                netzbezug_arbeitspreis_cent_kwh=31.5,
            )
    return engine


async def _spalten(engine, tabelle: str) -> set[str]:
    async with engine.begin() as conn:
        return set(await conn.run_sync(
            lambda sync: {c["name"] for c in inspect(sync).get_columns(tabelle)}
        ))


class TestDieFixtureSelbst:
    """Eine Fixture, die nichts weglässt, prüft nichts — das steht hier."""

    def test_das_alt_schema_laesst_die_ergaenzten_spalten_WIRKLICH_weg(self):
        for tabelle, spalten in ERGAENZTE_SPALTEN.items():
            ddl = _alt_ddl(tabelle)
            drin = [s for s in spalten if f"\t{s} " in ddl or f"\n\t{s}\t" in ddl]
            assert not drin, f"{tabelle}: {drin} stehen noch im Alt-Schema"

    def test_das_alt_schema_behaelt_seine_uebrigen_spalten(self):
        """Sonst baut die Probe eine Vergangenheit nach, die es nie gab."""
        ddl = _alt_ddl("anlagen")
        assert "anlagenname" in ddl and "leistung_kwp" in ddl

    def test_jede_ergaenzte_spalte_gibt_es_heute_wirklich(self):
        """Ein Tippfehler in der Liste machte den Round-Trip stumm."""
        unbekannt: dict[str, list[str]] = {}
        for tabelle, spalten in ERGAENZTE_SPALTEN.items():
            heute = set(Base.metadata.tables[tabelle].columns.keys())
            fehlt = [s for s in spalten if s not in heute]
            if fehlt:
                unbekannt[tabelle] = fehlt
        assert not unbekannt, f"Spalten ohne Entsprechung im Modell: {unbekannt}"


class TestRoundTrip:
    """Aus dem Alt-Schema wird das heutige — 86 Spalten über zehn Tabellen."""

    @pytest.mark.asyncio
    async def test_alle_ergaenzten_spalten_kommen_an(self, tmp_path):
        engine = await _alt_datenbank(tmp_path)
        try:
            async with engine.begin() as conn:
                await run_migrations(conn)

            fehlend: dict[str, list[str]] = {}
            for tabelle, spalten in ERGAENZTE_SPALTEN.items():
                ist = await _spalten(engine, tabelle)
                luecke = [s for s in spalten if s not in ist]
                if luecke:
                    fehlend[tabelle] = luecke
            assert not fehlend, (
                f"Die Migration ergaenzt diese Spalten nicht: {fehlend}. Auf "
                "einer Bestands-Installation bleibt die zugehoerige Sicht "
                "danach leer — hier ist der einzige Ort, an dem das auffaellt."
            )
        finally:
            await engine.dispose()

    @pytest.mark.asyncio
    async def test_bestandsdaten_ueberleben_die_migration(self, tmp_path):
        """Eine Migration, die Zeilen verliert, ist schlimmer als keine."""
        engine = await _alt_datenbank(tmp_path)
        try:
            async with engine.begin() as conn:
                await run_migrations(conn)
            async with engine.begin() as conn:
                assert (await conn.execute(text(
                    "SELECT anlagenname, leistung_kwp FROM anlagen WHERE id = 1"
                ))).one() == ("Bestandsanlage", 9.9)
                assert (await conn.execute(text(
                    "SELECT pv_erzeugung_kwh FROM monatsdaten WHERE id = 1"
                ))).scalar_one() == 1234.5
        finally:
            await engine.dispose()

    @pytest.mark.asyncio
    async def test_die_neuen_spalten_sind_auf_bestandszeilen_leer(self, tmp_path):
        """Kein erfundener Wert auf einer Zeile, die ihn nie hatte."""
        engine = await _alt_datenbank(tmp_path)
        try:
            async with engine.begin() as conn:
                await run_migrations(conn)
            async with engine.begin() as conn:
                assert (await conn.execute(text(
                    "SELECT sensor_mapping FROM anlagen WHERE id = 1"
                ))).scalar_one() is None
        finally:
            await engine.dispose()

    @pytest.mark.asyncio
    async def test_die_gesetzten_defaults_stehen_wirklich_da(self, tmp_path):
        """Wo ein DEFAULT im DDL steht, muss die Bestandszeile ihn tragen."""
        engine = await _alt_datenbank(tmp_path)
        try:
            async with engine.begin() as conn:
                await run_migrations(conn)
            async with engine.begin() as conn:
                assert (await conn.execute(text(
                    "SELECT verwendung, einspeisung_variabel "
                    "FROM strompreise WHERE id = 1"
                ))).one() == ("allgemein", 0)
                # Etappe 3d P1: `source_provenance` ist NOT NULL DEFAULT '{}' —
                # eine Bestandszeile mit NULL brächte jeden Provenance-Leser um.
                assert (await conn.execute(text(
                    "SELECT source_provenance FROM monatsdaten WHERE id = 1"
                ))).scalar_one() == "{}"
        finally:
            await engine.dispose()

    @pytest.mark.asyncio
    async def test_die_migration_ist_idempotent(self, tmp_path):
        """Sie läuft bei JEDEM Start — der zweite Lauf darf nichts tun."""
        engine = await _alt_datenbank(tmp_path)
        try:
            async with engine.begin() as conn:
                await run_migrations(conn)
            vorher = {t: await _spalten(engine, t) for t in ERGAENZTE_SPALTEN}
            async with engine.begin() as conn:
                await run_migrations(conn)          # darf nicht werfen
            assert {t: await _spalten(engine, t) for t in ERGAENZTE_SPALTEN} == vorher
        finally:
            await engine.dispose()

    @pytest.mark.asyncio
    async def test_eine_frische_datenbank_ueberlebt_den_lauf(self, tmp_path):
        """Erstinstallation: `run_migrations` läuft VOR `create_all`.

        Es gibt dann keine einzige Tabelle. Jeder Block muss das aushalten —
        die ``if '<tabelle>' in inspector.get_table_names()``-Wächter sind
        genau dafür da, und hier steht, dass keiner davon fehlt.
        """
        engine = await _alt_datenbank(tmp_path, tabellen=[], mit_zeilen=False)
        try:
            async with engine.begin() as conn:
                await run_migrations(conn)          # darf nicht werfen
        finally:
            await engine.dispose()

    @pytest.mark.asyncio
    async def test_eine_TEILWEISE_alte_datenbank_laeuft_ebenfalls(self, tmp_path):
        """Der reale Fall: manche Tabellen sind neu, andere alt.

        Wer ein Update überspringt, hat genau diese Mischung. Ein Block, der
        die Anwesenheit einer *anderen* Tabelle voraussetzt, fällt hier auf.
        """
        engine = await _alt_datenbank(
            tmp_path, tabellen=["anlagen", "strompreise"], mit_zeilen=False
        )
        try:
            async with engine.begin() as conn:
                await run_migrations(conn)
            assert "sensor_mapping" in await _spalten(engine, "anlagen")
            assert "verwendung" in await _spalten(engine, "strompreise")
        finally:
            await engine.dispose()
