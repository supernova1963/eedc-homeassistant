"""
Import/Export Helper Functions

Gemeinsame Hilfsfunktionen für CSV und JSON Import/Export.
"""

import re
import logging
from typing import Optional
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from backend.models.investition import Investition, InvestitionMonatsdaten

logger = logging.getLogger(__name__)


def _sanitize_column_name(name: str) -> str:
    """Bereinigt einen Namen für CSV-Spalten (keine Sonderzeichen, keine Leerzeichen)."""
    # Umlaute ersetzen
    replacements = {'ä': 'ae', 'ö': 'oe', 'ü': 'ue', 'Ä': 'Ae', 'Ö': 'Oe', 'Ü': 'Ue', 'ß': 'ss'}
    for old, new in replacements.items():
        name = name.replace(old, new)
    # Nur alphanumerische Zeichen und Unterstriche
    name = re.sub(r'[^a-zA-Z0-9_]', '_', name)
    # Mehrfache Unterstriche entfernen
    name = re.sub(r'_+', '_', name)
    # Unterstriche am Anfang/Ende entfernen
    return name.strip('_')


def _normalize_for_matching(name: str) -> str:
    """Normalisiert einen Namen für Vergleiche (lowercase, ohne Sonderzeichen)."""
    # Alles lowercase
    name = name.lower()
    # Umlaute ersetzen
    replacements = {'ä': 'ae', 'ö': 'oe', 'ü': 'ue', 'ß': 'ss'}
    for old, new in replacements.items():
        name = name.replace(old, new)
    # Nur alphanumerische Zeichen behalten
    name = re.sub(r'[^a-z0-9]', '', name)
    return name


def _parse_date(date_str: Optional[str]) -> Optional[date]:
    """Parst ein Datum aus einem ISO-String."""
    if not date_str:
        return None
    try:
        from datetime import datetime
        return datetime.fromisoformat(date_str.replace('Z', '+00:00')).date()
    except (ValueError, AttributeError):
        return None


async def _upsert_investition_monatsdaten(
    db: AsyncSession,
    investition_id: int,
    jahr: int,
    monat: int,
    verbrauch_daten: dict,
    ueberschreiben: bool
):
    """Erstellt oder aktualisiert InvestitionMonatsdaten.

    Bei existierenden Einträgen werden neue Felder IMMER ergänzt.
    Bestehende Felder werden nur bei ueberschreiben=True überschrieben.
    """
    existing = await db.execute(
        select(InvestitionMonatsdaten).where(
            InvestitionMonatsdaten.investition_id == investition_id,
            InvestitionMonatsdaten.jahr == jahr,
            InvestitionMonatsdaten.monat == monat
        )
    )
    existing_imd = existing.scalar_one_or_none()

    if existing_imd:
        # Immer mergen: Neue Felder ergänzen
        if existing_imd.verbrauch_daten:
            if ueberschreiben:
                # Überschreiben: Neue Daten haben Priorität
                existing_imd.verbrauch_daten = {**existing_imd.verbrauch_daten, **verbrauch_daten}
            else:
                # Nicht überschreiben: Nur fehlende Felder ergänzen
                merged = {**verbrauch_daten, **existing_imd.verbrauch_daten}
                existing_imd.verbrauch_daten = merged
        else:
            existing_imd.verbrauch_daten = verbrauch_daten
        # WICHTIG: SQLAlchemy erkennt JSON-Änderungen nicht automatisch!
        flag_modified(existing_imd, "verbrauch_daten")
    else:
        imd = InvestitionMonatsdaten(
            investition_id=investition_id,
            jahr=jahr,
            monat=monat,
            verbrauch_daten=verbrauch_daten
        )
        db.add(imd)


async def _import_investition_monatsdaten_v09(
    db: AsyncSession,
    row: dict,
    parse_float,
    investitionen: list[Investition],
    jahr: int,
    monat: int,
    ueberschreiben: bool
) -> dict:
    """
    v0.9: Importiert Investitions-Monatsdaten aus personalisierten CSV-Spalten.

    Spalten werden nach Investitions-Bezeichnung gematcht, z.B.:
    - "Sueddach_kWh" -> PV-Modul "Süddach"
    - "Smart_1_km" -> E-Auto "Smart #1"
    - "BYD_HVS_12_8_Ladung_kWh" -> Speicher "BYD HVS 12.8"

    Returns:
        dict: Summen für Anlage-Monatsdaten (pv_sum, batterie_ladung_sum, batterie_entladung_sum)

    Raises:
        ValueError: Bei negativen Werten in kWh/km/€-Feldern
    """
    def parse_float_positive(val: str, spaltenname: str):
        """Wrapper für parse_float mit Negativ-Prüfung."""
        result = parse_float(val)
        if result is not None and result < 0:
            raise ValueError(f"Spalte '{spaltenname}': Wert darf nicht negativ sein ({result})")
        return result

    summen = {
        "pv_erzeugung_sum": 0.0,
        "batterie_ladung_sum": 0.0,
        "batterie_entladung_sum": 0.0,
    }

    # Sammle alle Daten pro Investition, bevor wir speichern
    collected_data: dict[int, dict] = {}

    # Mapping: Verschiedene Varianten für flexibles Matching
    # (sanitized, normalized, inv)
    inv_variants: list[tuple[str, str, Investition]] = []
    for inv in investitionen:
        sanitized = _sanitize_column_name(inv.bezeichnung)
        normalized = _normalize_for_matching(inv.bezeichnung)
        inv_variants.append((sanitized, normalized, inv))
        logger.debug(f"Investment variant: bezeichnung='{inv.bezeichnung}', sanitized='{sanitized}', normalized='{normalized}', typ={inv.typ}")

    # Bekannte Suffixe für jeden Typ - sortiert nach Länge (längste zuerst für korrektes Matching)
    known_suffixes = sorted([
        "kWh", "km", "Verbrauch_kWh", "Ladung_PV_kWh", "Ladung_Netz_kWh",
        "Ladung_Extern_kWh", "Ladung_Extern_Euro", "V2H_kWh",
        "Ladung_kWh", "Entladung_kWh", "Ladevorgaenge",
        "Netzladung_kWh", "Ladepreis_Cent",  # Speicher Arbitrage
        "Strom_kWh", "Heizung_kWh", "Warmwasser_kWh",
        "Speicher_Ladung_kWh", "Speicher_Entladung_kWh",
        "Erzeugung_kWh",  # Sonstiges Erzeuger
        "Sonderkosten_Euro", "Sonderkosten_Notiz",  # Sonderkosten für alle
    ], key=len, reverse=True)

    # Alle Spalten durchgehen und Investitionen matchen
    for col_name, value in row.items():
        if not value or not value.strip():
            continue

        # Überspringe Basis-Spalten
        if col_name in ("Jahr", "Monat", "Einspeisung_kWh", "Netzbezug_kWh",
                        "PV_Erzeugung_kWh", "Batterie_Ladung_kWh", "Batterie_Entladung_kWh",
                        "Globalstrahlung_kWh_m2", "Sonnenstunden", "Notizen"):
            continue

        # Versuche Investition aus Spaltenname zu extrahieren
        matched_inv = None
        suffix = ""

        for sanitized_name, normalized_name, inv in inv_variants:
            # Strategie 1: Exaktes Match mit sanitized name als Präfix
            if col_name.startswith(sanitized_name + "_"):
                suffix = col_name[len(sanitized_name) + 1:]  # +1 für den Unterstrich
                matched_inv = inv
                logger.debug(f"Strategie 1 Match: col='{col_name}' -> inv='{inv.bezeichnung}', suffix='{suffix}'")
                break
            elif col_name == sanitized_name:
                suffix = ""
                matched_inv = inv
                logger.debug(f"Strategie 1 exakt Match: col='{col_name}' -> inv='{inv.bezeichnung}'")
                break

        # Strategie 2: Falls Strategie 1 nicht gematcht hat, versuche Suffix-basiertes Matching
        if not matched_inv:
            for known_suffix in known_suffixes:
                if col_name.endswith("_" + known_suffix):
                    # Extrahiere Präfix (alles vor dem Suffix)
                    prefix = col_name[:-len(known_suffix) - 1]  # -1 für den Unterstrich
                    prefix_normalized = _normalize_for_matching(prefix)

                    for sanitized_name, normalized_name, inv in inv_variants:
                        if prefix_normalized == normalized_name or prefix == sanitized_name:
                            suffix = known_suffix
                            matched_inv = inv
                            logger.debug(f"Strategie 2 Match: col='{col_name}', prefix='{prefix}' -> inv='{inv.bezeichnung}', suffix='{suffix}'")
                            break

                    if matched_inv:
                        break

        if not matched_inv:
            logger.debug(f"Keine Investition gefunden für Spalte: '{col_name}'")
            continue

        inv = matched_inv
        field_key = None
        field_value = None

        # PV-Module
        if inv.typ == "pv-module" and suffix == "kWh":
            pv_val = parse_float_positive(value, col_name)
            if pv_val is not None:
                field_key = "pv_erzeugung_kwh"
                field_value = pv_val
                summen["pv_erzeugung_sum"] += pv_val

        # Speicher
        elif inv.typ == "speicher":
            if suffix == "Ladung_kWh":
                val = parse_float_positive(value, col_name)
                if val is not None:
                    field_key = "ladung_kwh"
                    field_value = val
                    summen["batterie_ladung_sum"] += val
            elif suffix == "Entladung_kWh":
                val = parse_float_positive(value, col_name)
                if val is not None:
                    field_key = "entladung_kwh"
                    field_value = val
                    summen["batterie_entladung_sum"] += val
            # Arbitrage-Felder
            elif suffix == "Netzladung_kWh":
                val = parse_float_positive(value, col_name)
                if val is not None:
                    field_key = "speicher_ladung_netz_kwh"
                    field_value = val
            elif suffix == "Ladepreis_Cent":
                val = parse_float_positive(value, col_name)
                if val is not None:
                    field_key = "speicher_ladepreis_cent"
                    field_value = val

        # E-Auto
        elif inv.typ == "e-auto":
            if suffix == "km":
                val = parse_float_positive(value, col_name)
                if val is not None:
                    field_key = "km_gefahren"
                    field_value = val
            elif suffix == "Verbrauch_kWh":
                val = parse_float_positive(value, col_name)
                if val is not None:
                    field_key = "verbrauch_kwh"
                    field_value = val
            elif suffix == "Ladung_PV_kWh":
                val = parse_float_positive(value, col_name)
                if val is not None:
                    field_key = "ladung_pv_kwh"
                    field_value = val
            elif suffix == "Ladung_Netz_kWh":
                val = parse_float_positive(value, col_name)
                if val is not None:
                    field_key = "ladung_netz_kwh"
                    field_value = val
            elif suffix == "Ladung_Extern_kWh":
                val = parse_float_positive(value, col_name)
                if val is not None:
                    field_key = "ladung_extern_kwh"
                    field_value = val
            elif suffix == "Ladung_Extern_Euro":
                val = parse_float_positive(value, col_name)
                if val is not None:
                    field_key = "ladung_extern_euro"
                    field_value = val
            elif suffix == "V2H_kWh":
                val = parse_float_positive(value, col_name)
                if val is not None:
                    field_key = "v2h_entladung_kwh"
                    field_value = val

        # Wallbox
        elif inv.typ == "wallbox":
            if suffix == "Ladung_kWh":
                val = parse_float_positive(value, col_name)
                if val is not None:
                    field_key = "ladung_kwh"
                    field_value = val
            elif suffix == "Ladevorgaenge":
                val = parse_float_positive(value, col_name)
                if val is not None:
                    field_key = "ladevorgaenge"
                    field_value = int(val)

        # Wärmepumpe
        elif inv.typ == "waermepumpe":
            if suffix == "Strom_kWh":
                val = parse_float_positive(value, col_name)
                if val is not None:
                    field_key = "stromverbrauch_kwh"
                    field_value = val
            elif suffix == "Heizung_kWh":
                val = parse_float_positive(value, col_name)
                if val is not None:
                    field_key = "heizenergie_kwh"
                    field_value = val
            elif suffix == "Warmwasser_kWh":
                val = parse_float_positive(value, col_name)
                if val is not None:
                    field_key = "warmwasser_kwh"
                    field_value = val

        # Balkonkraftwerk
        elif inv.typ == "balkonkraftwerk":
            if suffix == "Erzeugung_kWh" or suffix == "kWh":  # kWh für Rückwärtskompatibilität
                val = parse_float_positive(value, col_name)
                if val is not None:
                    field_key = "pv_erzeugung_kwh"
                    field_value = val
                    summen["pv_erzeugung_sum"] += val
            elif suffix == "Eigenverbrauch_kWh":
                val = parse_float_positive(value, col_name)
                if val is not None:
                    field_key = "eigenverbrauch_kwh"
                    field_value = val
            elif suffix == "Speicher_Ladung_kWh":
                val = parse_float_positive(value, col_name)
                if val is not None:
                    field_key = "speicher_ladung_kwh"
                    field_value = val
                    summen["batterie_ladung_sum"] += val
            elif suffix == "Speicher_Entladung_kWh":
                val = parse_float_positive(value, col_name)
                if val is not None:
                    field_key = "speicher_entladung_kwh"
                    field_value = val
                    summen["batterie_entladung_sum"] += val

        # Sonstiges (kategorie-abhängig)
        elif inv.typ == "sonstiges":
            kategorie = inv.parameter.get("kategorie", "erzeuger") if inv.parameter else "erzeuger"
            if suffix == "Erzeugung_kWh" and kategorie == "erzeuger":
                val = parse_float_positive(value, col_name)
                if val is not None:
                    field_key = "erzeugung_kwh"
                    field_value = val
                    summen["pv_erzeugung_sum"] += val  # Zur Gesamt-Erzeugung addieren
            elif suffix == "Verbrauch_kWh" and kategorie == "verbraucher":
                val = parse_float_positive(value, col_name)
                if val is not None:
                    field_key = "verbrauch_sonstig_kwh"
                    field_value = val
            elif suffix == "Ladung_kWh" and kategorie == "speicher":
                val = parse_float_positive(value, col_name)
                if val is not None:
                    field_key = "ladung_kwh"
                    field_value = val
                    summen["batterie_ladung_sum"] += val
            elif suffix == "Entladung_kWh" and kategorie == "speicher":
                val = parse_float_positive(value, col_name)
                if val is not None:
                    field_key = "entladung_kwh"
                    field_value = val
                    summen["batterie_entladung_sum"] += val

        # Sonderkosten (für alle Investitionstypen)
        if suffix == "Sonderkosten_Euro":
            val = parse_float_positive(value, col_name)
            if val is not None:
                field_key = "sonderkosten_euro"
                field_value = val
        elif suffix == "Sonderkosten_Notiz":
            if value and value.strip():
                field_key = "sonderkosten_notiz"
                field_value = value.strip()

        # Sammle alle Daten für jede Investition
        if field_key and field_value is not None:
            if inv.id not in collected_data:
                collected_data[inv.id] = {}
            collected_data[inv.id][field_key] = field_value

    # Alle gesammelten Daten auf einmal speichern
    for inv_id, verbrauch_daten in collected_data.items():
        if verbrauch_daten:
            await _upsert_investition_monatsdaten(db, inv_id, jahr, monat, verbrauch_daten, ueberschreiben)

    return summen


async def _import_investition_monatsdaten_legacy(
    db: AsyncSession,
    row: dict,
    parse_float,
    inv_by_type: dict[str, Investition],
    jahr: int,
    monat: int,
    ueberschreiben: bool
):
    """
    LEGACY: Importiert Investitions-Monatsdaten aus generischen CSV-Spalten.

    Unterstützt alte Spaltenformate wie EAuto_km, Batterie_Ladung_kWh etc.
    Wird für Rückwärtskompatibilität beibehalten.
    """
    # E-Auto Daten
    eauto_km = parse_float(row.get("EAuto_km", ""))
    eauto_verbrauch = parse_float(row.get("EAuto_Verbrauch_kWh", ""))
    eauto_pv = parse_float(row.get("EAuto_Ladung_PV_kWh", ""))
    eauto_netz = parse_float(row.get("EAuto_Ladung_Netz_kWh", ""))

    if "e-auto" in inv_by_type and (eauto_km or eauto_verbrauch):
        inv = inv_by_type["e-auto"]
        verbrauch_daten = {}
        if eauto_km:
            verbrauch_daten["km_gefahren"] = eauto_km
        if eauto_verbrauch:
            verbrauch_daten["verbrauch_kwh"] = eauto_verbrauch
        if eauto_pv:
            verbrauch_daten["ladung_pv_kwh"] = eauto_pv
        if eauto_netz:
            verbrauch_daten["ladung_netz_kwh"] = eauto_netz

        if verbrauch_daten:
            await _upsert_investition_monatsdaten(db, inv.id, jahr, monat, verbrauch_daten, ueberschreiben)

    # Wallbox Daten
    wallbox_ladung = parse_float(row.get("Wallbox_Ladung_kWh", ""))
    wallbox_vorgaenge = parse_float(row.get("Wallbox_Ladevorgaenge", ""))

    if "wallbox" in inv_by_type and (wallbox_ladung or wallbox_vorgaenge):
        inv = inv_by_type["wallbox"]
        verbrauch_daten = {}
        if wallbox_ladung:
            verbrauch_daten["ladung_kwh"] = wallbox_ladung
        if wallbox_vorgaenge:
            verbrauch_daten["ladevorgaenge"] = int(wallbox_vorgaenge)

        if verbrauch_daten:
            await _upsert_investition_monatsdaten(db, inv.id, jahr, monat, verbrauch_daten, ueberschreiben)

    # Speicher Daten (werden bereits in Monatsdaten gespeichert, hier optional zusätzlich)
    batt_ladung = parse_float(row.get("Batterie_Ladung_kWh", ""))
    batt_entladung = parse_float(row.get("Batterie_Entladung_kWh", ""))

    if "speicher" in inv_by_type and (batt_ladung or batt_entladung):
        inv = inv_by_type["speicher"]
        verbrauch_daten = {}
        if batt_ladung:
            verbrauch_daten["ladung_kwh"] = batt_ladung
        if batt_entladung:
            verbrauch_daten["entladung_kwh"] = batt_entladung

        if verbrauch_daten:
            await _upsert_investition_monatsdaten(db, inv.id, jahr, monat, verbrauch_daten, ueberschreiben)

    # Wärmepumpe Daten
    wp_strom = parse_float(row.get("WP_Strom_kWh", ""))
    wp_heizung = parse_float(row.get("WP_Heizung_kWh", ""))
    wp_warmwasser = parse_float(row.get("WP_Warmwasser_kWh", ""))

    if "waermepumpe" in inv_by_type and (wp_strom or wp_heizung or wp_warmwasser):
        inv = inv_by_type["waermepumpe"]
        verbrauch_daten = {}
        if wp_strom:
            verbrauch_daten["stromverbrauch_kwh"] = wp_strom
        if wp_heizung:
            verbrauch_daten["heizenergie_kwh"] = wp_heizung
        if wp_warmwasser:
            verbrauch_daten["warmwasser_kwh"] = wp_warmwasser

        if verbrauch_daten:
            await _upsert_investition_monatsdaten(db, inv.id, jahr, monat, verbrauch_daten, ueberschreiben)
