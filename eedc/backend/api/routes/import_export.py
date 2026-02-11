"""
Import/Export API Routes

CSV-Import und Export-Funktionen.
"""

from io import StringIO
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
import csv

from backend.api.deps import get_db
from backend.models.anlage import Anlage
from backend.models.monatsdaten import Monatsdaten
from backend.models.investition import Investition, InvestitionMonatsdaten
from backend.models.strompreis import Strompreis
from backend.models.pvgis_prognose import PVGISPrognose as PVGISPrognoseModel, PVGISMonatsprognose
from backend.services.wetter_service import get_wetterdaten


# =============================================================================
# Pydantic Schemas
# =============================================================================

class ImportResult(BaseModel):
    """Ergebnis eines CSV-Imports."""
    erfolg: bool
    importiert: int
    uebersprungen: int
    fehler: list[str]


class DemoDataResult(BaseModel):
    """Ergebnis der Demo-Daten Erstellung."""
    erfolg: bool
    anlage_id: int
    anlage_name: str
    monatsdaten_count: int
    investitionen_count: int
    strompreise_count: int
    message: str


class CSVTemplateInfo(BaseModel):
    """Info über das CSV-Template."""
    spalten: list[str]
    beschreibung: dict[str, str]


# =============================================================================
# Helper Functions
# =============================================================================

async def _import_investition_monatsdaten_v09(
    db: AsyncSession,
    row: dict,
    parse_float,
    investitionen: list["Investition"],
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
    """
    import logging
    logger = logging.getLogger(__name__)

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
            pv_val = parse_float(value)
            if pv_val is not None:
                field_key = "pv_erzeugung_kwh"
                field_value = pv_val
                summen["pv_erzeugung_sum"] += pv_val

        # Speicher
        elif inv.typ == "speicher":
            if suffix == "Ladung_kWh":
                val = parse_float(value)
                if val is not None:
                    field_key = "ladung_kwh"
                    field_value = val
                    summen["batterie_ladung_sum"] += val
            elif suffix == "Entladung_kWh":
                val = parse_float(value)
                if val is not None:
                    field_key = "entladung_kwh"
                    field_value = val
                    summen["batterie_entladung_sum"] += val
            # Arbitrage-Felder
            elif suffix == "Netzladung_kWh":
                val = parse_float(value)
                if val is not None:
                    field_key = "speicher_ladung_netz_kwh"
                    field_value = val
            elif suffix == "Ladepreis_Cent":
                val = parse_float(value)
                if val is not None:
                    field_key = "speicher_ladepreis_cent"
                    field_value = val

        # E-Auto
        elif inv.typ == "e-auto":
            if suffix == "km":
                val = parse_float(value)
                if val is not None:
                    field_key = "km_gefahren"
                    field_value = val
            elif suffix == "Verbrauch_kWh":
                val = parse_float(value)
                if val is not None:
                    field_key = "verbrauch_kwh"
                    field_value = val
            elif suffix == "Ladung_PV_kWh":
                val = parse_float(value)
                if val is not None:
                    field_key = "ladung_pv_kwh"
                    field_value = val
            elif suffix == "Ladung_Netz_kWh":
                val = parse_float(value)
                if val is not None:
                    field_key = "ladung_netz_kwh"
                    field_value = val
            elif suffix == "Ladung_Extern_kWh":
                val = parse_float(value)
                if val is not None:
                    field_key = "ladung_extern_kwh"
                    field_value = val
            elif suffix == "Ladung_Extern_Euro":
                val = parse_float(value)
                if val is not None:
                    field_key = "ladung_extern_euro"
                    field_value = val
            elif suffix == "V2H_kWh":
                val = parse_float(value)
                if val is not None:
                    field_key = "v2h_entladung_kwh"
                    field_value = val

        # Wallbox
        elif inv.typ == "wallbox":
            if suffix == "Ladung_kWh":
                val = parse_float(value)
                if val is not None:
                    field_key = "ladung_kwh"
                    field_value = val
            elif suffix == "Ladevorgaenge":
                val = parse_float(value)
                if val is not None:
                    field_key = "ladevorgaenge"
                    field_value = int(val)

        # Wärmepumpe
        elif inv.typ == "waermepumpe":
            if suffix == "Strom_kWh":
                val = parse_float(value)
                if val is not None:
                    field_key = "stromverbrauch_kwh"
                    field_value = val
            elif suffix == "Heizung_kWh":
                val = parse_float(value)
                if val is not None:
                    field_key = "heizenergie_kwh"
                    field_value = val
            elif suffix == "Warmwasser_kWh":
                val = parse_float(value)
                if val is not None:
                    field_key = "warmwasser_kwh"
                    field_value = val

        # Balkonkraftwerk
        elif inv.typ == "balkonkraftwerk":
            if suffix == "kWh":
                val = parse_float(value)
                if val is not None:
                    field_key = "pv_erzeugung_kwh"
                    field_value = val
                    summen["pv_erzeugung_sum"] += val
            elif suffix == "Speicher_Ladung_kWh":
                val = parse_float(value)
                if val is not None:
                    field_key = "speicher_ladung_kwh"
                    field_value = val
                    summen["batterie_ladung_sum"] += val
            elif suffix == "Speicher_Entladung_kWh":
                val = parse_float(value)
                if val is not None:
                    field_key = "speicher_entladung_kwh"
                    field_value = val
                    summen["batterie_entladung_sum"] += val

        # Sonstiges (kategorie-abhängig)
        elif inv.typ == "sonstiges":
            kategorie = inv.parameter.get("kategorie", "erzeuger") if inv.parameter else "erzeuger"
            if suffix == "Erzeugung_kWh" and kategorie == "erzeuger":
                val = parse_float(value)
                if val is not None:
                    field_key = "erzeugung_kwh"
                    field_value = val
                    summen["pv_erzeugung_sum"] += val  # Zur Gesamt-Erzeugung addieren
            elif suffix == "Verbrauch_kWh" and kategorie == "verbraucher":
                val = parse_float(value)
                if val is not None:
                    field_key = "verbrauch_sonstig_kwh"
                    field_value = val
            elif suffix == "Ladung_kWh" and kategorie == "speicher":
                val = parse_float(value)
                if val is not None:
                    field_key = "ladung_kwh"
                    field_value = val
                    summen["batterie_ladung_sum"] += val
            elif suffix == "Entladung_kWh" and kategorie == "speicher":
                val = parse_float(value)
                if val is not None:
                    field_key = "entladung_kwh"
                    field_value = val
                    summen["batterie_entladung_sum"] += val

        # Sonderkosten (für alle Investitionstypen)
        if suffix == "Sonderkosten_Euro":
            val = parse_float(value)
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


async def _import_investition_monatsdaten(
    db: AsyncSession,
    row: dict,
    parse_float,
    inv_by_type: dict[str, "Investition"],
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
    else:
        imd = InvestitionMonatsdaten(
            investition_id=investition_id,
            jahr=jahr,
            monat=monat,
            verbrauch_daten=verbrauch_daten
        )
        db.add(imd)


# =============================================================================
# Router
# =============================================================================

router = APIRouter()


def _sanitize_column_name(name: str) -> str:
    """Bereinigt einen Namen für CSV-Spalten (keine Sonderzeichen, keine Leerzeichen)."""
    import re
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
    import re
    # Alles lowercase
    name = name.lower()
    # Umlaute ersetzen
    replacements = {'ä': 'ae', 'ö': 'oe', 'ü': 'ue', 'ß': 'ss'}
    for old, new in replacements.items():
        name = name.replace(old, new)
    # Nur alphanumerische Zeichen behalten
    name = re.sub(r'[^a-z0-9]', '', name)
    return name


@router.get("/template/{anlage_id}", response_model=CSVTemplateInfo)
async def get_csv_template_info(anlage_id: int, db: AsyncSession = Depends(get_db)):
    """
    Gibt Informationen über das personalisierte CSV-Template für eine Anlage zurück.

    v0.9: Template basiert auf angelegten Investitionen mit deren Bezeichnungen.
    Spalten werden dynamisch generiert, z.B. "Speicher_Keller_Ladung_kWh".

    Args:
        anlage_id: ID der Anlage

    Returns:
        CSVTemplateInfo: Spalten und Beschreibungen

    Raises:
        404: Anlage nicht gefunden
    """
    # Anlage prüfen
    anlage_result = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    if not anlage_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Anlage nicht gefunden")

    # Basis-Spalten (nur Zählerwerte!)
    # WICHTIG: PV_Erzeugung_kWh ist LEGACY - PV-Erzeugung wird pro PV-Modul erfasst
    # Globalstrahlung/Sonnenstunden werden automatisch via Wetter-API gefüllt
    spalten = ["Jahr", "Monat", "Einspeisung_kWh", "Netzbezug_kWh"]
    beschreibung = {
        "Jahr": "Jahr (z.B. 2024)",
        "Monat": "Monat (1-12)",
        "Einspeisung_kWh": "Ins Netz eingespeiste Energie (Zählerwert)",
        "Netzbezug_kWh": "Aus dem Netz bezogene Energie (Zählerwert)",
    }

    # Investitionen laden, nach Typ und ID sortiert
    inv_result = await db.execute(
        select(Investition)
        .where(Investition.anlage_id == anlage_id, Investition.aktiv == True)
        .order_by(Investition.typ, Investition.id)
    )
    investitionen = inv_result.scalars().all()

    # Personalisierte Spalten je nach Investition (v0.9)
    for inv in investitionen:
        prefix = _sanitize_column_name(inv.bezeichnung)

        if inv.typ == "pv-module":
            # PV-Module: Erzeugung pro String
            col = f"{prefix}_kWh"
            spalten.append(col)
            beschreibung[col] = f"PV-Erzeugung {inv.bezeichnung} (kWh)"

        elif inv.typ == "speicher":
            # Speicher: Ladung und Entladung
            col_ladung = f"{prefix}_Ladung_kWh"
            col_entladung = f"{prefix}_Entladung_kWh"
            spalten.extend([col_ladung, col_entladung])
            beschreibung[col_ladung] = f"Ladung {inv.bezeichnung} (kWh)"
            beschreibung[col_entladung] = f"Entladung {inv.bezeichnung} (kWh)"
            # Arbitrage wenn aktiviert
            if inv.parameter and inv.parameter.get("arbitrage_faehig"):
                col_netz = f"{prefix}_Netzladung_kWh"
                col_preis = f"{prefix}_Ladepreis_Cent"
                spalten.extend([col_netz, col_preis])
                beschreibung[col_netz] = f"Netzladung {inv.bezeichnung} (kWh) - Arbitrage"
                beschreibung[col_preis] = f"Ø Ladepreis {inv.bezeichnung} (ct/kWh) - Arbitrage"

        elif inv.typ == "e-auto":
            # E-Auto: km, Verbrauch, Ladungen, optional V2H
            cols = [
                (f"{prefix}_km", f"Gefahrene km {inv.bezeichnung}"),
                (f"{prefix}_Verbrauch_kWh", f"Verbrauch {inv.bezeichnung} (kWh)"),
                (f"{prefix}_Ladung_PV_kWh", f"PV-Ladung {inv.bezeichnung} (kWh)"),
                (f"{prefix}_Ladung_Netz_kWh", f"Netz-Ladung {inv.bezeichnung} (kWh)"),
                (f"{prefix}_Ladung_Extern_kWh", f"Externe Ladung {inv.bezeichnung} (kWh)"),
                (f"{prefix}_Ladung_Extern_Euro", f"Externe Ladekosten {inv.bezeichnung} (€)"),
            ]
            # V2H wenn aktiviert (nutzt_v2h ODER v2h_faehig)
            if inv.parameter and (inv.parameter.get("nutzt_v2h") or inv.parameter.get("v2h_faehig")):
                cols.append((f"{prefix}_V2H_kWh", f"V2H-Entladung {inv.bezeichnung} (kWh)"))

            for col, desc in cols:
                spalten.append(col)
                beschreibung[col] = desc

        elif inv.typ == "wallbox":
            # Wallbox: Ladung und Ladevorgänge
            cols = [
                (f"{prefix}_Ladung_kWh", f"Ladung {inv.bezeichnung} (kWh)"),
                (f"{prefix}_Ladevorgaenge", f"Ladevorgänge {inv.bezeichnung}"),
            ]
            for col, desc in cols:
                spalten.append(col)
                beschreibung[col] = desc

        elif inv.typ == "waermepumpe":
            # Wärmepumpe: Strom, Heizung, Warmwasser
            cols = [
                (f"{prefix}_Strom_kWh", f"Stromverbrauch {inv.bezeichnung} (kWh)"),
                (f"{prefix}_Heizung_kWh", f"Heizenergie {inv.bezeichnung} (kWh)"),
                (f"{prefix}_Warmwasser_kWh", f"Warmwasser {inv.bezeichnung} (kWh)"),
            ]
            for col, desc in cols:
                spalten.append(col)
                beschreibung[col] = desc

        elif inv.typ == "balkonkraftwerk":
            # Balkonkraftwerk: Erzeugung + optionaler Speicher
            col_pv = f"{prefix}_kWh"
            spalten.append(col_pv)
            beschreibung[col_pv] = f"PV-Erzeugung {inv.bezeichnung} (kWh)"
            # Optional: Speicher falls Parameter vorhanden
            if inv.parameter and inv.parameter.get("hat_speicher"):
                col_sp_l = f"{prefix}_Speicher_Ladung_kWh"
                col_sp_e = f"{prefix}_Speicher_Entladung_kWh"
                spalten.extend([col_sp_l, col_sp_e])
                beschreibung[col_sp_l] = f"Speicher-Ladung {inv.bezeichnung} (kWh)"
                beschreibung[col_sp_e] = f"Speicher-Entladung {inv.bezeichnung} (kWh)"

        elif inv.typ == "sonstiges":
            # Sonstiges: Kategorie-abhängig (erzeuger/verbraucher/speicher)
            kategorie = inv.parameter.get("kategorie", "erzeuger") if inv.parameter else "erzeuger"
            if kategorie == "erzeuger":
                col = f"{prefix}_Erzeugung_kWh"
                spalten.append(col)
                beschreibung[col] = f"Erzeugung {inv.bezeichnung} (kWh)"
            elif kategorie == "verbraucher":
                col = f"{prefix}_Verbrauch_kWh"
                spalten.append(col)
                beschreibung[col] = f"Verbrauch {inv.bezeichnung} (kWh)"
            elif kategorie == "speicher":
                col_l = f"{prefix}_Ladung_kWh"
                col_e = f"{prefix}_Entladung_kWh"
                spalten.extend([col_l, col_e])
                beschreibung[col_l] = f"Ladung {inv.bezeichnung} (kWh)"
                beschreibung[col_e] = f"Entladung {inv.bezeichnung} (kWh)"

        # Sonderkosten für alle Investitionen (optional)
        col_sk = f"{prefix}_Sonderkosten_Euro"
        col_skn = f"{prefix}_Sonderkosten_Notiz"
        spalten.extend([col_sk, col_skn])
        beschreibung[col_sk] = f"Sonderkosten {inv.bezeichnung} (€) - Reparatur, Wartung, etc."
        beschreibung[col_skn] = f"Sonderkosten-Beschreibung {inv.bezeichnung}"

    # Optionale Spalte am Ende (nur Notizen - Wetterdaten werden automatisch gefüllt)
    spalten.append("Notizen")
    beschreibung["Notizen"] = "Notizen (optional)"

    return CSVTemplateInfo(spalten=spalten, beschreibung=beschreibung)


@router.get("/template/{anlage_id}/download")
async def download_csv_template(anlage_id: int, db: AsyncSession = Depends(get_db)):
    """
    Lädt ein CSV-Template für eine Anlage herunter.

    Args:
        anlage_id: ID der Anlage

    Returns:
        CSV-Datei als Download
    """
    template_info = await get_csv_template_info(anlage_id, db)

    output = StringIO()
    writer = csv.writer(output, delimiter=";")
    writer.writerow(template_info.spalten)

    # Beispielzeile
    beispiel = []
    for spalte in template_info.spalten:
        if spalte == "Jahr":
            beispiel.append("2024")
        elif spalte == "Monat":
            beispiel.append("1")
        elif "kWh" in spalte:
            beispiel.append("0")
        elif spalte == "Notizen":
            beispiel.append("")
        else:
            beispiel.append("0")
    writer.writerow(beispiel)

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=eedc_template_{anlage_id}.csv"}
    )


@router.post("/csv/{anlage_id}", response_model=ImportResult)
async def import_csv(
    anlage_id: int,
    file: UploadFile = File(...),
    ueberschreiben: bool = Query(False, description="Existierende Monate überschreiben"),
    auto_wetter: bool = Query(True, description="Wetterdaten automatisch abrufen wenn leer"),
    db: AsyncSession = Depends(get_db)
):
    """
    Importiert Monatsdaten aus einer CSV-Datei.

    v0.9: Unterstützt personalisierte Spalten basierend auf Investitions-Bezeichnungen.
    Beispiel: "Sueddach_kWh", "Speicher_Keller_Ladung_kWh"

    v0.9.8: Automatischer Wetterdaten-Abruf wenn Globalstrahlung/Sonnenstunden leer sind.

    Summenberechnung:
    - pv_erzeugung: Summe aus PV-Modul-Spalten wenn vorhanden
    - batterie_ladung/entladung: Summe aus Speicher-Spalten wenn vorhanden

    Args:
        anlage_id: ID der Anlage
        file: CSV-Datei
        ueberschreiben: Wenn True, werden existierende Monate überschrieben
        auto_wetter: Wenn True, werden fehlende Wetterdaten automatisch abgerufen

    Returns:
        ImportResult: Ergebnis des Imports
    """
    # Anlage prüfen und laden (für Koordinaten bei Wetter-Abruf)
    anlage_result = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    anlage = anlage_result.scalar_one_or_none()
    if not anlage:
        raise HTTPException(status_code=404, detail="Anlage nicht gefunden")

    # Investitionen laden für Investitions-Monatsdaten
    inv_result = await db.execute(
        select(Investition).where(Investition.anlage_id == anlage_id, Investition.aktiv == True)
    )
    investitionen = list(inv_result.scalars().all())

    # Investitionen nach Typ gruppieren (erste aktive je Typ) - für Legacy-Import
    inv_by_type: dict[str, Investition] = {}
    for inv in investitionen:
        if inv.typ not in inv_by_type:
            inv_by_type[inv.typ] = inv

    # CSV lesen
    try:
        content = await file.read()
        text = content.decode("utf-8-sig")  # BOM handling
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Fehler beim Lesen der Datei: {e}")

    # CSV parsen - automatische Trennzeichen-Erkennung (Semikolon oder Komma)
    first_line = text.split('\n')[0] if text else ''
    delimiter = ';' if ';' in first_line else ','

    reader = csv.DictReader(StringIO(text), delimiter=delimiter)

    # Prüfen ob personalisierte Spalten vorhanden (v0.9 Format)
    # Flexibleres Matching: Normalisierte Namen vergleichen
    fieldnames = reader.fieldnames or []
    has_personalized_columns = False

    for inv in investitionen:
        sanitized = _sanitize_column_name(inv.bezeichnung)
        normalized = _normalize_for_matching(inv.bezeichnung)

        for col in fieldnames:
            # Exaktes Match mit sanitized name
            if sanitized in col:
                has_personalized_columns = True
                break

            # Flexibles Match: Normalisierte Namen
            col_normalized = _normalize_for_matching(col)
            if col_normalized.startswith(normalized) and len(normalized) >= 3:
                has_personalized_columns = True
                break

        if has_personalized_columns:
            break

    importiert = 0
    uebersprungen = 0
    fehler = []

    for i, row in enumerate(reader, start=2):  # Zeile 2 (nach Header)
        try:
            # Pflichtfelder
            jahr = int(row.get("Jahr", "").strip())
            monat = int(row.get("Monat", "").strip())

            if not (2000 <= jahr <= 2100):
                fehler.append(f"Zeile {i}: Ungültiges Jahr {jahr}")
                continue
            if not (1 <= monat <= 12):
                fehler.append(f"Zeile {i}: Ungültiger Monat {monat}")
                continue

            # Existierenden Eintrag prüfen
            existing = await db.execute(
                select(Monatsdaten).where(
                    Monatsdaten.anlage_id == anlage_id,
                    Monatsdaten.jahr == jahr,
                    Monatsdaten.monat == monat
                )
            )
            existing_md = existing.scalar_one_or_none()

            if existing_md and not ueberschreiben:
                uebersprungen += 1
                continue

            # Werte parsen (deutsche Zahlenformate)
            def parse_float(val: str) -> Optional[float]:
                if not val or not val.strip():
                    return None
                val = val.strip().replace(",", ".")
                return float(val)

            einspeisung = parse_float(row.get("Einspeisung_kWh", "")) or 0
            netzbezug = parse_float(row.get("Netzbezug_kWh", "")) or 0
            globalstrahlung = parse_float(row.get("Globalstrahlung_kWh_m2", ""))
            sonnenstunden = parse_float(row.get("Sonnenstunden", ""))
            notizen = row.get("Notizen", "").strip() or None

            # v0.9.8: Wetterdaten automatisch abrufen wenn leer und Koordinaten vorhanden
            if auto_wetter and globalstrahlung is None and sonnenstunden is None:
                if anlage.latitude and anlage.longitude:
                    try:
                        wetter = await get_wetterdaten(
                            latitude=anlage.latitude,
                            longitude=anlage.longitude,
                            jahr=jahr,
                            monat=monat
                        )
                        globalstrahlung = wetter.get("globalstrahlung_kwh_m2")
                        sonnenstunden = wetter.get("sonnenstunden")
                    except Exception as e:
                        # Bei Fehlern Wetterdaten ignorieren, Import fortsetzen
                        import logging
                        logging.getLogger(__name__).warning(
                            f"Wetterdaten für {monat}/{jahr} nicht abrufbar: {e}"
                        )

            # v0.9: Personalisierte Spalten verarbeiten und Summen berechnen
            summen = {"pv_erzeugung_sum": 0.0, "batterie_ladung_sum": 0.0, "batterie_entladung_sum": 0.0}
            if has_personalized_columns and investitionen:
                summen = await _import_investition_monatsdaten_v09(
                    db, row, parse_float, investitionen, jahr, monat, ueberschreiben
                )

            # PV-Erzeugung: Summe aus PV-Modulen (InvestitionMonatsdaten) ist primär
            # LEGACY: PV_Erzeugung_kWh Spalte wird nur als Fallback akzeptiert
            # Die Summe wird für Berechnungen (Direktverbrauch, Eigenverbrauch) benötigt
            pv_erzeugung_explicit = parse_float(row.get("PV_Erzeugung_kWh", ""))
            if summen["pv_erzeugung_sum"] > 0:
                # Primär: Summe aus individuellen PV-Modul-Spalten
                pv_erzeugung = summen["pv_erzeugung_sum"]
            elif pv_erzeugung_explicit is not None:
                # Fallback: Legacy-Spalte PV_Erzeugung_kWh (für alte CSV-Dateien)
                pv_erzeugung = pv_erzeugung_explicit
            else:
                pv_erzeugung = None

            # Batterie: NUR expliziter Wert aus Batterie_*_kWh Spalten
            # WICHTIG: Summen aus Speicher-Investitionen werden NICHT in Legacy-Felder geschrieben!
            # Die Daten sind bereits in InvestitionMonatsdaten gespeichert (v0.9.7+)
            # Legacy-Felder nur bei expliziter Batterie_*_kWh Spalte befüllen (Rückwärtskompatibilität)
            batterie_ladung_explicit = parse_float(row.get("Batterie_Ladung_kWh", ""))
            batterie_entladung_explicit = parse_float(row.get("Batterie_Entladung_kWh", ""))

            # Legacy-Felder nur bei explizitem Wert setzen
            batterie_ladung = batterie_ladung_explicit  # None wenn nicht explizit angegeben
            batterie_entladung = batterie_entladung_explicit  # None wenn nicht explizit angegeben

            # Für Berechnungen (Direktverbrauch, Eigenverbrauch) die Summen verwenden
            batterie_ladung_for_calc = batterie_ladung if batterie_ladung is not None else summen["batterie_ladung_sum"] if summen["batterie_ladung_sum"] > 0 else 0
            batterie_entladung_for_calc = batterie_entladung if batterie_entladung is not None else summen["batterie_entladung_sum"] if summen["batterie_entladung_sum"] > 0 else 0

            # Berechnete Felder
            # Werden berechnet wenn pv_erzeugung vorhanden ist (auch bei 0)
            direktverbrauch = None
            eigenverbrauch = None
            gesamtverbrauch = None
            if pv_erzeugung is not None:
                # Für Berechnungen die _for_calc Werte verwenden (inkl. InvestitionMonatsdaten-Summen)
                direktverbrauch = max(0, pv_erzeugung - einspeisung - batterie_ladung_for_calc)
                eigenverbrauch = direktverbrauch + batterie_entladung_for_calc
                gesamtverbrauch = eigenverbrauch + netzbezug
            elif einspeisung > 0 or netzbezug > 0:
                # Fallback: Wenn keine PV-Erzeugung aber Einspeisung/Netzbezug vorhanden,
                # können wir zumindest gesamtverbrauch berechnen
                gesamtverbrauch = netzbezug + einspeisung  # Einspeisung = min. Eigenproduktion

            if existing_md:
                # Update
                existing_md.einspeisung_kwh = einspeisung
                existing_md.netzbezug_kwh = netzbezug
                existing_md.pv_erzeugung_kwh = pv_erzeugung
                existing_md.direktverbrauch_kwh = direktverbrauch
                existing_md.eigenverbrauch_kwh = eigenverbrauch
                existing_md.gesamtverbrauch_kwh = gesamtverbrauch
                existing_md.batterie_ladung_kwh = batterie_ladung
                existing_md.batterie_entladung_kwh = batterie_entladung
                existing_md.globalstrahlung_kwh_m2 = globalstrahlung
                existing_md.sonnenstunden = sonnenstunden
                existing_md.notizen = notizen
                existing_md.datenquelle = "csv"
            else:
                # Neu anlegen
                md = Monatsdaten(
                    anlage_id=anlage_id,
                    jahr=jahr,
                    monat=monat,
                    einspeisung_kwh=einspeisung,
                    netzbezug_kwh=netzbezug,
                    pv_erzeugung_kwh=pv_erzeugung,
                    direktverbrauch_kwh=direktverbrauch,
                    eigenverbrauch_kwh=eigenverbrauch,
                    gesamtverbrauch_kwh=gesamtverbrauch,
                    batterie_ladung_kwh=batterie_ladung,
                    batterie_entladung_kwh=batterie_entladung,
                    globalstrahlung_kwh_m2=globalstrahlung,
                    sonnenstunden=sonnenstunden,
                    notizen=notizen,
                    datenquelle="csv"
                )
                db.add(md)

            # Legacy: Generische Investitions-Spalten IMMER verarbeiten
            # (auch wenn personalisierte Spalten vorhanden sind - sie ergänzen sich)
            await _import_investition_monatsdaten(
                db, row, parse_float, inv_by_type, jahr, monat, ueberschreiben
            )

            importiert += 1

        except ValueError as e:
            fehler.append(f"Zeile {i}: Ungültiger Wert - {e}")
        except Exception as e:
            fehler.append(f"Zeile {i}: Fehler - {e}")

    # Änderungen persistieren
    await db.flush()

    return ImportResult(
        erfolg=len(fehler) == 0,
        importiert=importiert,
        uebersprungen=uebersprungen,
        fehler=fehler[:20]  # Max 20 Fehler anzeigen
    )


@router.get("/export/{anlage_id}")
async def export_csv(
    anlage_id: int,
    jahr: Optional[int] = Query(None, description="Filter nach Jahr"),
    include_investitionen: bool = Query(True, description="Investitions-Monatsdaten einschließen"),
    db: AsyncSession = Depends(get_db)
):
    """
    Exportiert Monatsdaten als CSV.

    v0.9: Unterstützt personalisierte Spalten basierend auf Investitions-Bezeichnungen.

    Args:
        anlage_id: ID der Anlage
        jahr: Optional - nur dieses Jahr exportieren
        include_investitionen: Investitions-Monatsdaten einschließen (Standard: True)

    Returns:
        CSV-Datei als Download
    """
    # Anlage prüfen
    anlage_result = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    anlage = anlage_result.scalar_one_or_none()
    if not anlage:
        raise HTTPException(status_code=404, detail="Anlage nicht gefunden")

    # Monatsdaten laden
    query = select(Monatsdaten).where(Monatsdaten.anlage_id == anlage_id)
    if jahr:
        query = query.where(Monatsdaten.jahr == jahr)
    query = query.order_by(Monatsdaten.jahr, Monatsdaten.monat)

    result = await db.execute(query)
    monatsdaten = result.scalars().all()

    # Investitionen und deren Monatsdaten laden
    investitionen = []
    inv_monatsdaten_map: dict[tuple[int, int, int], dict] = {}  # (inv_id, jahr, monat) -> verbrauch_daten

    if include_investitionen:
        inv_result = await db.execute(
            select(Investition)
            .where(Investition.anlage_id == anlage_id, Investition.aktiv == True)
            .order_by(Investition.typ, Investition.id)
        )
        investitionen = list(inv_result.scalars().all())

        # Investitions-Monatsdaten laden
        for inv in investitionen:
            imd_query = select(InvestitionMonatsdaten).where(
                InvestitionMonatsdaten.investition_id == inv.id
            )
            if jahr:
                imd_query = imd_query.where(InvestitionMonatsdaten.jahr == jahr)

            imd_result = await db.execute(imd_query)
            for imd in imd_result.scalars().all():
                inv_monatsdaten_map[(inv.id, imd.jahr, imd.monat)] = imd.verbrauch_daten or {}

    # CSV erstellen
    output = StringIO()
    writer = csv.writer(output, delimiter=";")

    # Dynamische Header basierend auf Investitionen (v0.9)
    # WICHTIG: PV_Erzeugung_kWh ist LEGACY - wird aus PV-Modul-Spalten aggregiert
    # Globalstrahlung/Sonnenstunden werden automatisch via Wetter-API gefüllt
    header = ["Jahr", "Monat", "Einspeisung_kWh", "Netzbezug_kWh"]

    # Investitions-Spalten nach Template-Logik hinzufügen
    inv_columns: list[tuple[Investition, str, str]] = []  # (inv, suffix, data_key)

    for inv in investitionen:
        prefix = _sanitize_column_name(inv.bezeichnung)

        if inv.typ == "pv-module":
            inv_columns.append((inv, "kWh", "pv_erzeugung_kwh"))
            header.append(f"{prefix}_kWh")

        elif inv.typ == "speicher":
            inv_columns.append((inv, "Ladung_kWh", "ladung_kwh"))
            inv_columns.append((inv, "Entladung_kWh", "entladung_kwh"))
            header.extend([f"{prefix}_Ladung_kWh", f"{prefix}_Entladung_kWh"])
            # Arbitrage wenn aktiviert
            if inv.parameter and inv.parameter.get("arbitrage_faehig"):
                inv_columns.append((inv, "Netzladung_kWh", "speicher_ladung_netz_kwh"))
                inv_columns.append((inv, "Ladepreis_Cent", "speicher_ladepreis_cent"))
                header.extend([f"{prefix}_Netzladung_kWh", f"{prefix}_Ladepreis_Cent"])

        elif inv.typ == "e-auto":
            cols = [
                ("km", "km_gefahren"),
                ("Verbrauch_kWh", "verbrauch_kwh"),
                ("Ladung_PV_kWh", "ladung_pv_kwh"),
                ("Ladung_Netz_kWh", "ladung_netz_kwh"),
                ("Ladung_Extern_kWh", "ladung_extern_kwh"),
                ("Ladung_Extern_Euro", "ladung_extern_euro"),
            ]
            # V2H wenn aktiviert (nutzt_v2h ODER v2h_faehig)
            if inv.parameter and (inv.parameter.get("nutzt_v2h") or inv.parameter.get("v2h_faehig")):
                cols.append(("V2H_kWh", "v2h_entladung_kwh"))
            for suffix, key in cols:
                inv_columns.append((inv, suffix, key))
                header.append(f"{prefix}_{suffix}")

        elif inv.typ == "wallbox":
            inv_columns.append((inv, "Ladung_kWh", "ladung_kwh"))
            inv_columns.append((inv, "Ladevorgaenge", "ladevorgaenge"))
            header.extend([f"{prefix}_Ladung_kWh", f"{prefix}_Ladevorgaenge"])

        elif inv.typ == "waermepumpe":
            cols = [
                ("Strom_kWh", "stromverbrauch_kwh"),
                ("Heizung_kWh", "heizenergie_kwh"),
                ("Warmwasser_kWh", "warmwasser_kwh"),
            ]
            for suffix, key in cols:
                inv_columns.append((inv, suffix, key))
                header.append(f"{prefix}_{suffix}")

        elif inv.typ == "balkonkraftwerk":
            inv_columns.append((inv, "kWh", "pv_erzeugung_kwh"))
            header.append(f"{prefix}_kWh")
            if inv.parameter and inv.parameter.get("hat_speicher"):
                inv_columns.append((inv, "Speicher_Ladung_kWh", "speicher_ladung_kwh"))
                inv_columns.append((inv, "Speicher_Entladung_kWh", "speicher_entladung_kwh"))
                header.extend([f"{prefix}_Speicher_Ladung_kWh", f"{prefix}_Speicher_Entladung_kWh"])

        elif inv.typ == "sonstiges":
            kategorie = inv.parameter.get("kategorie", "erzeuger") if inv.parameter else "erzeuger"
            if kategorie == "erzeuger":
                inv_columns.append((inv, "Erzeugung_kWh", "erzeugung_kwh"))
                header.append(f"{prefix}_Erzeugung_kWh")
            elif kategorie == "verbraucher":
                inv_columns.append((inv, "Verbrauch_kWh", "verbrauch_sonstig_kwh"))
                header.append(f"{prefix}_Verbrauch_kWh")
            elif kategorie == "speicher":
                inv_columns.append((inv, "Ladung_kWh", "ladung_kwh"))
                inv_columns.append((inv, "Entladung_kWh", "entladung_kwh"))
                header.extend([f"{prefix}_Ladung_kWh", f"{prefix}_Entladung_kWh"])

        # Sonderkosten für alle Investitionen
        inv_columns.append((inv, "Sonderkosten_Euro", "sonderkosten_euro"))
        inv_columns.append((inv, "Sonderkosten_Notiz", "sonderkosten_notiz"))
        header.extend([f"{prefix}_Sonderkosten_Euro", f"{prefix}_Sonderkosten_Notiz"])

    # Optionale Spalte am Ende (Wetterdaten werden automatisch gefüllt)
    header.append("Notizen")

    writer.writerow(header)

    # Daten
    for md in monatsdaten:
        row = [
            md.jahr,
            md.monat,
            md.einspeisung_kwh,
            md.netzbezug_kwh,
        ]

        # Investitions-Daten hinzufügen
        for inv, suffix, data_key in inv_columns:
            inv_data = inv_monatsdaten_map.get((inv.id, md.jahr, md.monat), {})
            value = inv_data.get(data_key, "")
            row.append(value if value != "" else "")

        # Optionale Felder (Wetterdaten werden automatisch gefüllt)
        row.append(md.notizen or "")

        writer.writerow(row)

    output.seek(0)
    filename = f"eedc_export_{anlage.anlagenname}_{jahr or 'alle'}.csv"

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


# =============================================================================
# Demo-Daten
# =============================================================================

# Demo-Monatsdaten (Juni 2023 - Dezember 2025)
# Erweitert um Wetterdaten und externe Ladung
# Globalstrahlung und Sonnenstunden: Typische Werte für Wien (48.2°N)
DEMO_MONATSDATEN = [
    # Jahr, Monat, Einspeisung, Netzbezug, PV_Erzeugung, Batt_Ladung, Batt_Entladung,
    # EAuto_km, EAuto_Verbrauch, EAuto_PV, EAuto_Netz, EAuto_Extern_kWh, EAuto_Extern_Euro, V2H,
    # WP_Strom, WP_Heizung, WP_Warmwasser, Globalstrahlung_kWh_m2, Sonnenstunden
    (2023, 6, 517.08, 1.84, 668.54, 70.3, 50.56, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 165.2, 248),
    (2023, 7, 1179.67, 4.43, 1571.53, 176.82, 151.21, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 172.8, 275),
    (2023, 8, 1014.27, 4.88, 1400.24, 194.34, 166.74, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 148.5, 245),
    (2023, 9, 1273.4, 4.24, 1622.29, 194.61, 167.49, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 112.3, 185),
    (2023, 10, 471.98, 38.65, 804.61, 215.27, 202.08, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 68.4, 125),
    (2023, 11, 82.14, 154.84, 294.28, 141.48, 135.77, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 32.1, 58),
    (2023, 12, 10.92, 364.96, 171.8, 85.01, 73.92, 650, 125, 10, 115, 0, 0, 0, 180, 720, 90, 22.5, 42),
    (2024, 1, 122.81, 333.59, 432.86, 165.3, 148.69, 1186, 237.27, 37, 175, 25, 12.50, 0, 320, 1280, 120, 28.3, 55),
    (2024, 2, 164.35, 261.82, 476.23, 183.07, 164.65, 959, 191.81, 91, 80, 20, 10.00, 0, 290, 1160, 110, 48.7, 85),
    (2024, 3, 461.1, 122.08, 979.25, 247.51, 233.23, 1201, 240.35, 200, 41, 0, 0, 0, 240, 960, 100, 89.2, 142),
    (2024, 4, 564.72, 25.45, 1140.2, 226.08, 214.78, 1032, 206.55, 201, 6, 0, 0, 0, 180, 720, 90, 128.5, 195),
    (2024, 5, 873.29, 22.82, 1475.49, 225.59, 212.61, 1002, 200.58, 195, 5, 0, 0, 0, 120, 480, 85, 158.3, 228),
    (2024, 6, 1036.34, 10.31, 1559.33, 199.62, 192.79, 717, 143.43, 140, 3, 0, 0, 0, 80, 320, 80, 168.7, 255),
    (2024, 7, 1120.43, 12.1, 1657.77, 194.21, 183.88, 851, 170.36, 165, 6, 0, 0, 0, 70, 280, 75, 175.4, 282),
    (2024, 8, 1228.31, 43.6, 1772.38, 195.89, 184.81, 1119, 223.8, 150, 24, 50, 27.50, 0, 75, 300, 78, 152.1, 252),
    (2024, 9, 781.13, 10.48, 1244.02, 202.86, 191.13, 659, 131.82, 100, 31, 0, 0, 0, 95, 380, 82, 108.6, 178),
    (2024, 10, 262.54, 88.54, 761.48, 271.57, 257.8, 876, 175.26, 110, 50, 15, 8.25, 0, 150, 600, 95, 65.2, 118),
    (2024, 11, 135.33, 303.18, 379.7, 134.7, 116.05, 758, 151.69, 52, 75, 25, 13.75, 25, 280, 1120, 105, 29.8, 52),
    (2024, 12, 35.29, 357.37, 227.94, 88.81, 68.01, 564, 112.86, 12, 70, 30, 16.50, 35, 350, 1400, 115, 20.1, 38),
    (2025, 1, 115.61, 373.9, 383.3, 157.3, 115.83, 974, 194.96, 24, 130, 40, 22.00, 40, 380, 1520, 125, 25.7, 48),
    (2025, 2, 319.24, 165.63, 781.89, 236.56, 184.74, 1111, 222.29, 32, 155, 35, 19.25, 45, 340, 1360, 115, 52.4, 92),
    (2025, 3, 1106.2, 114.73, 1647.26, 291.98, 236.09, 621, 124.23, 74, 50, 0, 0, 30, 280, 1120, 105, 95.8, 155),
    (2025, 4, 1115.4, 46.09, 1734.5, 256.47, 200.62, 1036, 207.35, 167, 41, 0, 0, 25, 200, 800, 95, 135.2, 205),
    (2025, 5, 1171.87, 16.82, 1837.58, 254.87, 205.58, 193, 38.66, 35, 4, 0, 0, 15, 140, 560, 85, 162.7, 238),
    (2025, 6, 1318.13, 9.43, 1884.72, 210.36, 154.59, 651, 130.25, 115, 15, 0, 0, 20, 90, 360, 80, 171.3, 262),
    (2025, 7, 1051.23, 9.73, 1642.45, 233.19, 189.15, 801, 160.38, 120, 20, 20, 11.00, 18, 75, 300, 75, 168.9, 268),
    (2025, 8, 1117.5, 10.1, 1727.63, 247.98, 193.78, 857, 171.53, 140, 21, 10, 5.50, 22, 80, 320, 78, 155.6, 258),
    (2025, 9, 721.12, 18.3, 1172.37, 242.38, 194.34, 323, 64.61, 54, 10, 0, 0, 12, 110, 440, 85, 105.2, 172),
    (2025, 10, 132.83, 229.36, 569.49, 247.04, 205.23, 1118, 223.67, 100, 89, 35, 19.25, 38, 180, 720, 98, 62.8, 112),
    (2025, 11, 173.16, 185.21, 541.48, 206.04, 165.63, 574, 114.94, 40, 55, 20, 11.00, 28, 300, 1200, 108, 31.5, 55),
    (2025, 12, 125.91, 405.5, 432.72, 168.77, 132.41, 1205, 241.17, 21, 175, 45, 24.75, 42, 370, 1480, 118, 18.9, 35),
]


@router.post("/demo", response_model=DemoDataResult)
async def create_demo_data(db: AsyncSession = Depends(get_db)):
    """
    Erstellt eine komplette Demo-Anlage mit allen Daten.

    Beinhaltet:
    - PV-Anlage (20 kWp)
    - Speicher (15 kWh)
    - E-Auto (Tesla Model 3) mit V2H
    - Wärmepumpe (Heizung + Warmwasser)
    - Wallbox (11 kW)
    - Balkonkraftwerk (800 Wp mit Speicher)
    - Sonstiges: Mini-BHKW (Erzeuger)
    - Strompreise (2023-2025)
    - 31 Monate Monatsdaten (Juni 2023 - Dezember 2025)

    Returns:
        DemoDataResult: Zusammenfassung der erstellten Daten
    """
    from datetime import date

    # Prüfen ob Demo-Anlage bereits existiert
    existing = await db.execute(
        select(Anlage).where(Anlage.anlagenname == "Demo-Anlage")
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=400,
            detail="Demo-Anlage existiert bereits. Bitte zuerst löschen."
        )

    # 1. Anlage erstellen
    anlage = Anlage(
        anlagenname="Demo-Anlage",
        leistung_kwp=20.0,
        installationsdatum=date(2023, 6, 1),
        standort_plz="1220",
        standort_ort="Wien",
        ausrichtung="Süd",
        neigung_grad=30.0,
        latitude=48.2,
        longitude=16.4,
    )
    db.add(anlage)
    await db.flush()  # ID generieren

    # 2. Strompreise erstellen
    strompreise = [
        Strompreis(
            anlage_id=anlage.id,
            netzbezug_arbeitspreis_cent_kwh=28.5,
            einspeiseverguetung_cent_kwh=7.5,
            grundpreis_euro_monat=12.0,
            gueltig_ab=date(2023, 6, 1),
            gueltig_bis=date(2024, 3, 31),
            tarifname="Standardtarif 2023",
            anbieter="Wien Energie",
        ),
        Strompreis(
            anlage_id=anlage.id,
            netzbezug_arbeitspreis_cent_kwh=32.0,
            einspeiseverguetung_cent_kwh=8.0,
            grundpreis_euro_monat=13.5,
            gueltig_ab=date(2024, 4, 1),
            gueltig_bis=date(2024, 12, 31),
            tarifname="Standardtarif 2024",
            anbieter="Wien Energie",
        ),
        Strompreis(
            anlage_id=anlage.id,
            netzbezug_arbeitspreis_cent_kwh=30.0,
            einspeiseverguetung_cent_kwh=7.0,
            grundpreis_euro_monat=14.0,
            gueltig_ab=date(2025, 1, 1),
            gueltig_bis=None,  # aktuell gültig
            tarifname="Dynamischer Tarif 2025",
            anbieter="Wien Energie",
        ),
    ]
    for sp in strompreise:
        db.add(sp)

    # 3. Investitionen erstellen
    # Wechselrichter (muss zuerst erstellt werden für Parent-Verknüpfungen)
    wechselrichter = Investition(
        anlage_id=anlage.id,
        typ="wechselrichter",
        bezeichnung="Fronius Symo GEN24 10.0 Plus",
        anschaffungsdatum=date(2023, 6, 1),
        anschaffungskosten_gesamt=3500,
        parameter={
            "hersteller": "fronius",
            "max_leistung_kw": 10,
            "hybrid": True,
            "notstromfaehig": True,
            "phasen": 3,
        },
        aktiv=True,
    )
    db.add(wechselrichter)
    await db.flush()  # ID für Verknüpfungen generieren

    # DC-Speicher (am Wechselrichter angeschlossen)
    speicher = Investition(
        anlage_id=anlage.id,
        typ="speicher",
        bezeichnung="BYD HVS 15.4",
        anschaffungsdatum=date(2023, 6, 1),
        anschaffungskosten_gesamt=12000,
        parent_investition_id=wechselrichter.id,  # DC-seitig am WR
        parameter={
            "kapazitaet_kwh": 15.4,
            "max_ladeleistung_kw": 10,
            "max_entladeleistung_kw": 10,
            "wirkungsgrad_prozent": 95,
            "typ": "dc",  # DC-gekoppelt
            "arbitrage_faehig": True,  # Kann Netzstrom zu günstigen Zeiten laden
        },
        aktiv=True,
    )
    db.add(speicher)

    # E-Auto
    eauto = Investition(
        anlage_id=anlage.id,
        typ="e-auto",
        bezeichnung="Tesla Model 3 LR",
        anschaffungsdatum=date(2023, 12, 1),
        anschaffungskosten_gesamt=52000,
        anschaffungskosten_alternativ=35000,  # Verbrenner-Alternative
        parameter={
            "km_jahr": 12000,
            "verbrauch_kwh_100km": 18,
            "pv_anteil_prozent": 60,
            "benzinpreis_euro": 1.65,
            "vergleich_verbrauch_l_100km": 7.5,
            "nutzt_v2h": True,
            "v2h_entlade_preis_cent": 25,
            "batterie_kapazitaet_kwh": 75,
        },
        aktiv=True,
    )
    db.add(eauto)

    # Wärmepumpe
    waermepumpe = Investition(
        anlage_id=anlage.id,
        typ="waermepumpe",
        bezeichnung="Daikin Altherma 3 H HT",
        anschaffungsdatum=date(2024, 4, 1),
        anschaffungskosten_gesamt=18000,
        anschaffungskosten_alternativ=8000,  # Gas-/Ölheizung
        betriebskosten_jahr=200,
        parameter={
            "heizlast_kw": 12,
            "cop_durchschnitt": 4.0,
            "warmwasser_anteil_prozent": 15,
            "gas_kwh_preis_cent": 12,
            "gas_verbrauch_alt_kwh": 18000,
        },
        aktiv=True,
    )
    db.add(waermepumpe)

    # Wallbox
    wallbox = Investition(
        anlage_id=anlage.id,
        typ="wallbox",
        bezeichnung="go-eCharger HOMEfix 11kW",
        anschaffungsdatum=date(2023, 12, 1),
        anschaffungskosten_gesamt=800,
        parameter={
            "ladeleistung_kw": 11,
            "phasen": 3,
        },
        aktiv=True,
    )
    db.add(wallbox)

    # PV-Module (für PVGIS Prognose) - alle am Wechselrichter angeschlossen
    # Süddach - Hauptfläche (String 1)
    pv_sued = Investition(
        anlage_id=anlage.id,
        typ="pv-module",
        bezeichnung="Süddach",
        anschaffungsdatum=date(2023, 6, 1),
        anschaffungskosten_gesamt=15000,
        leistung_kwp=12.0,
        ausrichtung="Süd",
        neigung_grad=30,
        parent_investition_id=wechselrichter.id,
        parameter={
            "anzahl_module": 24,
            "modul_typ": "Longi Hi-MO 5",
            "modul_leistung_wp": 500,
        },
        aktiv=True,
    )
    db.add(pv_sued)

    # Ostdach (String 2)
    pv_ost = Investition(
        anlage_id=anlage.id,
        typ="pv-module",
        bezeichnung="Ostdach",
        anschaffungsdatum=date(2023, 6, 1),
        anschaffungskosten_gesamt=5000,
        leistung_kwp=5.0,
        ausrichtung="Ost",
        neigung_grad=25,
        parent_investition_id=wechselrichter.id,
        parameter={
            "anzahl_module": 10,
            "modul_typ": "Longi Hi-MO 5",
            "modul_leistung_wp": 500,
        },
        aktiv=True,
    )
    db.add(pv_ost)

    # Westdach (String 3)
    pv_west = Investition(
        anlage_id=anlage.id,
        typ="pv-module",
        bezeichnung="Westdach",
        anschaffungsdatum=date(2023, 6, 1),
        anschaffungskosten_gesamt=4000,
        leistung_kwp=3.0,
        ausrichtung="West",
        neigung_grad=25,
        parent_investition_id=wechselrichter.id,
        parameter={
            "anzahl_module": 6,
            "modul_typ": "Longi Hi-MO 5",
            "modul_leistung_wp": 500,
        },
        aktiv=True,
    )
    db.add(pv_west)

    # Balkonkraftwerk mit Speicher
    balkonkraftwerk = Investition(
        anlage_id=anlage.id,
        typ="balkonkraftwerk",
        bezeichnung="Balkon Süd",
        anschaffungsdatum=date(2024, 3, 1),
        anschaffungskosten_gesamt=1200,
        parameter={
            "leistung_wp": 400,
            "anzahl": 2,
            "ausrichtung": "Süd",
            "neigung_grad": 35,
            "hat_speicher": True,
            "speicher_kapazitaet_wh": 1024,
        },
        aktiv=True,
    )
    db.add(balkonkraftwerk)

    # Sonstiges: Mini-BHKW (Erzeuger)
    mini_bhkw = Investition(
        anlage_id=anlage.id,
        typ="sonstiges",
        bezeichnung="Mini-BHKW",
        anschaffungsdatum=date(2024, 10, 1),
        anschaffungskosten_gesamt=8000,
        betriebskosten_jahr=300,
        parameter={
            "kategorie": "erzeuger",
            "beschreibung": "Blockheizkraftwerk für Strom und Wärme, Erdgas-betrieben",
        },
        aktiv=True,
    )
    db.add(mini_bhkw)

    await db.flush()

    # 4. Monatsdaten erstellen
    monatsdaten_count = 0
    for row in DEMO_MONATSDATEN:
        (jahr, monat, einspeisung, netzbezug, pv_erzeugung, batt_ladung, batt_entladung,
         eauto_km, eauto_verbrauch, eauto_pv, eauto_netz, eauto_extern_kwh, eauto_extern_euro, v2h,
         wp_strom, wp_heizung, wp_warmwasser, globalstrahlung, sonnenstunden) = row

        # Berechnete Felder
        direktverbrauch = max(0, pv_erzeugung - einspeisung - batt_ladung)
        eigenverbrauch = direktverbrauch + batt_entladung
        gesamtverbrauch = eigenverbrauch + netzbezug

        md = Monatsdaten(
            anlage_id=anlage.id,
            jahr=jahr,
            monat=monat,
            einspeisung_kwh=einspeisung,
            netzbezug_kwh=netzbezug,
            pv_erzeugung_kwh=pv_erzeugung,
            direktverbrauch_kwh=direktverbrauch,
            eigenverbrauch_kwh=eigenverbrauch,
            gesamtverbrauch_kwh=gesamtverbrauch,
            batterie_ladung_kwh=batt_ladung if batt_ladung > 0 else None,
            batterie_entladung_kwh=batt_entladung if batt_entladung > 0 else None,
            globalstrahlung_kwh_m2=globalstrahlung,
            sonnenstunden=sonnenstunden,
            datenquelle="demo",
        )
        db.add(md)
        monatsdaten_count += 1

        # E-Auto Monatsdaten (ab Dezember 2023)
        if eauto_km > 0:
            eauto_verbrauch_daten = {
                "km_gefahren": eauto_km,
                "verbrauch_kwh": eauto_verbrauch,
                "ladung_pv_kwh": eauto_pv,
                "ladung_netz_kwh": eauto_netz,
                "v2h_entladung_kwh": v2h,
            }
            # Externe Ladung hinzufügen wenn vorhanden
            if eauto_extern_kwh > 0:
                eauto_verbrauch_daten["ladung_extern_kwh"] = eauto_extern_kwh
                eauto_verbrauch_daten["ladung_extern_euro"] = eauto_extern_euro

            # Sonderkosten: Reifenwechsel im April, Service im November
            if monat == 4:
                eauto_verbrauch_daten["sonderkosten_euro"] = 120.0
                eauto_verbrauch_daten["sonderkosten_notiz"] = "Reifenwechsel Sommer"
            elif monat == 11 and jahr == 2024:
                eauto_verbrauch_daten["sonderkosten_euro"] = 250.0
                eauto_verbrauch_daten["sonderkosten_notiz"] = "Jahresservice + Bremsflüssigkeit"

            eauto_md = InvestitionMonatsdaten(
                investition_id=eauto.id,
                jahr=jahr,
                monat=monat,
                verbrauch_daten=eauto_verbrauch_daten,
            )
            db.add(eauto_md)

        # Speicher Monatsdaten (mit Arbitrage ab 2025)
        if batt_ladung > 0:
            speicher_daten = {
                "ladung_kwh": batt_ladung,
                "entladung_kwh": batt_entladung,
            }
            # Arbitrage ab 2025: Ca. 15-25% der Ladung aus dem Netz zu günstigen Zeiten
            if jahr >= 2025:
                arbitrage_anteil = 0.15 + (monat % 3) * 0.05
                netzladung = round(batt_ladung * arbitrage_anteil, 1)
                ladepreis = round(18 + (monat % 4) * 2, 1)  # 18-24 ct/kWh
                speicher_daten["speicher_ladung_netz_kwh"] = netzladung
                speicher_daten["speicher_ladepreis_cent"] = ladepreis

            # Sonderkosten: Firmware-Update Service im März 2025
            if jahr == 2025 and monat == 3:
                speicher_daten["sonderkosten_euro"] = 95.0
                speicher_daten["sonderkosten_notiz"] = "Firmware-Update + Zellkalibrierung"

            speicher_md = InvestitionMonatsdaten(
                investition_id=speicher.id,
                jahr=jahr,
                monat=monat,
                verbrauch_daten=speicher_daten,
            )
            db.add(speicher_md)

        # Wärmepumpe Monatsdaten (ab April 2024)
        if wp_strom > 0:
            wp_daten = {
                "stromverbrauch_kwh": wp_strom,
                "heizenergie_kwh": wp_heizung,
                "warmwasser_kwh": wp_warmwasser,
            }
            # Sonderkosten: Jährliche Wartung im Oktober
            if monat == 10:
                wp_daten["sonderkosten_euro"] = 180.0
                wp_daten["sonderkosten_notiz"] = "Jahreswartung inkl. Kältemittelprüfung"

            wp_md = InvestitionMonatsdaten(
                investition_id=waermepumpe.id,
                jahr=jahr,
                monat=monat,
                verbrauch_daten=wp_daten,
            )
            db.add(wp_md)

        # Balkonkraftwerk Monatsdaten (ab März 2024)
        if jahr > 2024 or (jahr == 2024 and monat >= 3):
            # Saisonale Erzeugung basierend auf PV-Daten (skaliert auf 800Wp)
            bkw_skalierung = 0.04  # 800Wp / 20kWp
            bkw_erzeugung = round(pv_erzeugung * bkw_skalierung, 1)
            # Höhere Eigenverbrauchsquote beim Balkonkraftwerk (80%)
            bkw_eigenverbrauch = round(bkw_erzeugung * 0.8, 1)
            bkw_einspeisung = round(bkw_erzeugung * 0.2, 1)
            # Speicher: ca. 30% der Erzeugung wird zwischengespeichert
            bkw_speicher_ladung = round(bkw_erzeugung * 0.3, 1)
            bkw_speicher_entladung = round(bkw_speicher_ladung * 0.92, 1)  # 92% Effizienz

            bkw_md = InvestitionMonatsdaten(
                investition_id=balkonkraftwerk.id,
                jahr=jahr,
                monat=monat,
                verbrauch_daten={
                    "pv_erzeugung_kwh": bkw_erzeugung,
                    "speicher_ladung_kwh": bkw_speicher_ladung,
                    "speicher_entladung_kwh": bkw_speicher_entladung,
                },
            )
            db.add(bkw_md)

        # Mini-BHKW Monatsdaten (ab Oktober 2024 - Heizsaison)
        if (jahr == 2024 and monat >= 10) or jahr > 2024:
            # BHKW läuft primär in der Heizsaison
            if monat in [1, 2, 3, 10, 11, 12]:
                # Winter/Übergang: 100-200 kWh Stromerzeugung
                bhkw_erzeugung = 120 + (monat % 3) * 30
                bhkw_eigenverbrauch = round(bhkw_erzeugung * 0.85, 1)
                bhkw_einspeisung = round(bhkw_erzeugung * 0.15, 1)
            else:
                # Sommer: Nur für Warmwasser, weniger Betrieb
                bhkw_erzeugung = 30 + (monat % 2) * 10
                bhkw_eigenverbrauch = round(bhkw_erzeugung * 0.9, 1)
                bhkw_einspeisung = round(bhkw_erzeugung * 0.1, 1)

            bhkw_md = InvestitionMonatsdaten(
                investition_id=mini_bhkw.id,
                jahr=jahr,
                monat=monat,
                verbrauch_daten={
                    "erzeugung_kwh": bhkw_erzeugung,
                },
            )
            db.add(bhkw_md)

        # PV-Module InvestitionMonatsdaten (Verteilung der Gesamterzeugung auf Strings)
        if pv_erzeugung > 0:
            # Verteilung nach kWp und Ausrichtung:
            # Süd (12 kWp): Beste Erträge, dominiert im Winter
            # Ost (5 kWp): Morgenertrag
            # West (3 kWp): Abendertrag
            if monat in [5, 6, 7]:  # Sommer - Ost/West profitieren
                sued_anteil, ost_anteil, west_anteil = 0.55, 0.27, 0.18
            elif monat in [11, 12, 1, 2]:  # Winter - Süd dominiert
                sued_anteil, ost_anteil, west_anteil = 0.70, 0.18, 0.12
            else:  # Übergang
                sued_anteil, ost_anteil, west_anteil = 0.60, 0.24, 0.16

            for pv_inv, anteil in [(pv_sued, sued_anteil), (pv_ost, ost_anteil), (pv_west, west_anteil)]:
                pv_md = InvestitionMonatsdaten(
                    investition_id=pv_inv.id,
                    jahr=jahr,
                    monat=monat,
                    verbrauch_daten={"pv_erzeugung_kwh": round(pv_erzeugung * anteil, 1)},
                )
                db.add(pv_md)

        # Wallbox InvestitionMonatsdaten (Heimladung = PV + Netz)
        # Hinweis: ladung_pv_kwh gehört zum E-Auto, nicht zur Wallbox
        if eauto_km > 0:
            heimladung = eauto_pv + eauto_netz
            wallbox_md = InvestitionMonatsdaten(
                investition_id=wallbox.id,
                jahr=jahr,
                monat=monat,
                verbrauch_daten={
                    "ladung_kwh": heimladung,
                    "ladevorgaenge": max(4, int(heimladung / 25)),
                },
            )
            db.add(wallbox_md)

    # 5. PVGIS Prognose erstellen (realistische Werte für Wien, 48.2°N)
    # Typische Monatserträge für eine 20 kWp Anlage in Wien (kWh)
    # Basierend auf: Süd 12kWp (30°), Ost 5kWp (25°), West 3kWp (25°)
    pvgis_monatswerte = [
        {"monat": 1, "e_m": 680, "h_m": 32.5, "sd_m": 85},
        {"monat": 2, "e_m": 1020, "h_m": 52.8, "sd_m": 115},
        {"monat": 3, "e_m": 1650, "h_m": 95.2, "sd_m": 145},
        {"monat": 4, "e_m": 2150, "h_m": 128.5, "sd_m": 165},
        {"monat": 5, "e_m": 2480, "h_m": 158.2, "sd_m": 175},
        {"monat": 6, "e_m": 2620, "h_m": 168.5, "sd_m": 155},
        {"monat": 7, "e_m": 2750, "h_m": 175.8, "sd_m": 160},
        {"monat": 8, "e_m": 2450, "h_m": 152.5, "sd_m": 145},
        {"monat": 9, "e_m": 1850, "h_m": 112.8, "sd_m": 125},
        {"monat": 10, "e_m": 1180, "h_m": 68.5, "sd_m": 105},
        {"monat": 11, "e_m": 680, "h_m": 35.2, "sd_m": 75},
        {"monat": 12, "e_m": 490, "h_m": 25.5, "sd_m": 65},
    ]
    jahresertrag = sum(m["e_m"] for m in pvgis_monatswerte)  # ~20.000 kWh
    spezifischer_ertrag = jahresertrag / 20.0  # ~1000 kWh/kWp

    pvgis_prognose = PVGISPrognoseModel(
        anlage_id=anlage.id,
        latitude=48.2,
        longitude=16.4,
        neigung_grad=28.0,  # Gewichteter Durchschnitt
        ausrichtung_grad=-10.0,  # Leicht nach Osten (Gewichtung Ost/West)
        system_losses=14.0,
        jahresertrag_kwh=jahresertrag,
        spezifischer_ertrag_kwh_kwp=spezifischer_ertrag,
        monatswerte=pvgis_monatswerte,
        ist_aktiv=True,
    )
    db.add(pvgis_prognose)
    await db.flush()

    # Normalisierte Monatsprognosen
    for m in pvgis_monatswerte:
        monats_prognose = PVGISMonatsprognose(
            prognose_id=pvgis_prognose.id,
            monat=m["monat"],
            ertrag_kwh=m["e_m"],
            einstrahlung_kwh_m2=m["h_m"],
            standardabweichung_kwh=m["sd_m"],
        )
        db.add(monats_prognose)

    return DemoDataResult(
        erfolg=True,
        anlage_id=anlage.id,
        anlage_name=anlage.anlagenname,
        monatsdaten_count=monatsdaten_count,
        investitionen_count=10,  # WR, Speicher, E-Auto, WP, Wallbox, Balkonkraftwerk, Mini-BHKW + 3 PV-Module
        strompreise_count=3,
        message=f"Demo-Anlage '{anlage.anlagenname}' mit {monatsdaten_count} Monatsdaten, 10 Investitionen (WR + DC-Speicher + 3 PV-Module + E-Auto + WP + Wallbox + BKW + BHKW) und 3 Strompreisen erstellt.",
    )


@router.delete("/demo", response_model=dict)
async def delete_demo_data(db: AsyncSession = Depends(get_db)):
    """
    Löscht die Demo-Anlage und alle zugehörigen Daten.

    Returns:
        dict: Bestätigung der Löschung
    """
    # Demo-Anlage finden
    result = await db.execute(
        select(Anlage).where(Anlage.anlagenname == "Demo-Anlage")
    )
    anlage = result.scalar_one_or_none()

    if not anlage:
        raise HTTPException(status_code=404, detail="Demo-Anlage nicht gefunden")

    # Cascade Delete löscht alle verknüpften Daten
    await db.delete(anlage)

    return {"message": "Demo-Anlage und alle zugehörigen Daten gelöscht"}
