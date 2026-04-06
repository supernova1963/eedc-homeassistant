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
from backend.core.field_definitions import get_alle_felder_fuer_investition, IMPORT_SUMMEN_KEYS

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
    Importiert Investitions-Monatsdaten aus personalisierten CSV-Spalten.

    Spalten werden nach Investitions-Bezeichnung gematcht, z.B.:
    - "Sueddach_kWh" -> PV-Modul "Süddach"
    - "Smart_1_km" -> E-Auto "Smart #1"
    - "BYD_HVS_12_8_Ladung_kWh" -> Speicher "BYD HVS 12.8"

    Felddefinitionen kommen vollständig aus field_definitions.INVESTITION_FELDER.
    Neue Felder oder Investitionstypen nur dort ergänzen — kein Code hier ändern.

    Returns:
        dict: Summen für Anlage-Monatsdaten (pv_sum, batterie_ladung_sum, batterie_entladung_sum)

    Raises:
        ValueError: Bei negativen Werten in kWh/km/€-Feldern
    """
    def parse_float_positive(val: str, spaltenname: str):
        result = parse_float(val)
        if result is not None and result < 0:
            raise ValueError(f"Spalte '{spaltenname}': Wert darf nicht negativ sein ({result})")
        return result

    summen = {key: 0.0 for key in IMPORT_SUMMEN_KEYS}
    collected_data: dict[int, dict] = {}

    # ── Lookup-Tabelle aus Registry aufbauen ─────────────────────────────────
    # Für jede (Investition, Feld)-Kombination: Namen + csv_suffix vorberechnen
    inv_field_entries = []
    for inv in investitionen:
        sanitized = _sanitize_column_name(inv.bezeichnung)
        normalized = _normalize_for_matching(inv.bezeichnung)
        logger.debug(
            f"Investment: bezeichnung='{inv.bezeichnung}' sanitized='{sanitized}' "
            f"normalized='{normalized}' typ={inv.typ}"
        )
        for feld in get_alle_felder_fuer_investition(inv.typ, inv.parameter):
            csv_suffix = feld.get("csv_suffix")
            if not csv_suffix:
                continue
            inv_field_entries.append((inv, feld, sanitized, normalized, csv_suffix))
            # Alternativer Suffix für Rückwärtskompatibilität (z.B. BKW "kWh")
            alt = feld.get("csv_suffix_alt")
            if alt:
                inv_field_entries.append((inv, feld, sanitized, normalized, alt))

    # known_suffixes aus Registry — längste zuerst für korrektes Matching
    known_suffixes = sorted(
        {entry[4] for entry in inv_field_entries},
        key=len, reverse=True
    )

    # Basis-CSV-Spalten überspringen
    BASIS_SPALTEN = frozenset({
        "Jahr", "Monat", "Einspeisung_kWh", "Netzbezug_kWh",
        "PV_Erzeugung_kWh", "Batterie_Ladung_kWh", "Batterie_Entladung_kWh",
        "Globalstrahlung_kWh_m2", "Sonnenstunden", "Notizen",
    })

    # ── Spalten matchen und Werte sammeln ────────────────────────────────────
    for col_name, value in row.items():
        if not value or not value.strip():
            continue
        if col_name in BASIS_SPALTEN:
            continue

        matched_inv = None
        matched_feld = None

        # Strategie 1: Exaktes Präfix-Match (sanitized name + "_" + suffix)
        for inv, feld, sanitized, normalized, csv_suffix in inv_field_entries:
            if col_name == f"{sanitized}_{csv_suffix}" or col_name == sanitized:
                matched_inv = inv
                matched_feld = feld
                logger.debug(
                    f"S1: col='{col_name}' -> inv='{inv.bezeichnung}' feld='{feld['feld']}'"
                )
                break

        # Strategie 2: Suffix-basiertes Matching (Fallback wenn S1 nicht greift)
        if not matched_inv:
            for suffix in known_suffixes:
                if col_name.endswith("_" + suffix):
                    prefix = col_name[: -len(suffix) - 1]
                    prefix_norm = _normalize_for_matching(prefix)
                    for inv, feld, sanitized, normalized, csv_suffix in inv_field_entries:
                        if csv_suffix == suffix and (
                            prefix_norm == normalized or prefix == sanitized
                        ):
                            matched_inv = inv
                            matched_feld = feld
                            logger.debug(
                                f"S2: col='{col_name}' prefix='{prefix}' "
                                f"-> inv='{inv.bezeichnung}' feld='{feld['feld']}'"
                            )
                            break
                if matched_inv:
                    break

        if not matched_inv or not matched_feld:
            logger.debug(f"Keine Investition für Spalte: '{col_name}'")
            continue

        # ── Wert parsen ──────────────────────────────────────────────────────
        field_key = matched_feld["feld"]
        feld_typ = matched_feld.get("typ", "float")

        if feld_typ == "int":
            raw = parse_float(value)
            if raw is None:
                continue
            field_value = int(raw)
        else:
            raw = parse_float_positive(value, col_name)
            if raw is None:
                continue
            field_value = raw

        # ── Aggregat-Summe aktualisieren ─────────────────────────────────────
        aggregiert_in = matched_feld.get("aggregiert_in")
        if aggregiert_in and aggregiert_in in summen:
            summen[aggregiert_in] += field_value

        # ── Für Batch-Speicherung sammeln ────────────────────────────────────
        if matched_inv.id not in collected_data:
            collected_data[matched_inv.id] = {}
        # Bei Duplikat (csv_suffix_alt trifft nochmal): ersten Treffer behalten
        if field_key not in collected_data[matched_inv.id]:
            collected_data[matched_inv.id][field_key] = field_value

    # ── Sonderkosten (Sonderfall: für alle Typen, erzeugen sonstige_positionen)
    for inv in investitionen:
        sanitized = _sanitize_column_name(inv.bezeichnung)
        sk_euro_raw = row.get(f"{sanitized}_Sonderkosten_Euro", "")
        sk_notiz = (row.get(f"{sanitized}_Sonderkosten_Notiz", "") or "").strip()
        sk_euro = parse_float(sk_euro_raw) if sk_euro_raw else None
        if sk_euro is not None and sk_euro > 0:
            if inv.id not in collected_data:
                collected_data[inv.id] = {}
            collected_data[inv.id]["sonstige_positionen"] = [{
                "bezeichnung": sk_notiz or "CSV Import",
                "betrag": float(sk_euro),
                "typ": "ausgabe",
            }]

    # ── Batch-Speicherung ────────────────────────────────────────────────────
    for inv_id, verbrauch_daten in collected_data.items():
        if verbrauch_daten:
            await _upsert_investition_monatsdaten(db, inv_id, jahr, monat, verbrauch_daten, ueberschreiben)

    return summen


async def _distribute_legacy_pv_to_modules(
    db: AsyncSession,
    pv_erzeugung: float,
    pv_module: list[Investition],
    jahr: int,
    monat: int,
    ueberschreiben: bool
) -> list[str]:
    """
    Verteilt einen Legacy-PV-Erzeugungswert proportional auf die PV-Module.

    Die Verteilung erfolgt nach kWp-Anteil. Bei fehlenden kWp-Werten wird
    gleichmäßig verteilt.

    Returns:
        Liste von Warnungen
    """
    warnungen = []

    if not pv_module or pv_erzeugung <= 0:
        return warnungen

    # Gesamt-kWp berechnen
    total_kwp = sum(
        (inv.parameter or {}).get("leistung_kwp", 0) or 0
        for inv in pv_module
    )

    for inv in pv_module:
        inv_kwp = (inv.parameter or {}).get("leistung_kwp", 0) or 0

        if total_kwp > 0:
            # Proportionale Verteilung nach kWp
            anteil = inv_kwp / total_kwp
        else:
            # Gleichmäßige Verteilung wenn keine kWp-Werte
            anteil = 1.0 / len(pv_module)

        pv_anteil = round(pv_erzeugung * anteil, 1)

        verbrauch_daten = {"pv_erzeugung_kwh": pv_anteil}
        await _upsert_investition_monatsdaten(db, inv.id, jahr, monat, verbrauch_daten, ueberschreiben)

    if total_kwp > 0:
        warnungen.append(
            f"Legacy PV-Erzeugung ({pv_erzeugung:.0f} kWh) wurde proportional nach kWp "
            f"auf {len(pv_module)} PV-Module verteilt."
        )
    else:
        warnungen.append(
            f"Legacy PV-Erzeugung ({pv_erzeugung:.0f} kWh) wurde gleichmäßig "
            f"auf {len(pv_module)} PV-Module verteilt (keine kWp-Werte definiert)."
        )

    return warnungen


async def _distribute_legacy_battery_to_storages(
    db: AsyncSession,
    batterie_ladung: float,
    batterie_entladung: float,
    speicher: list[Investition],
    jahr: int,
    monat: int,
    ueberschreiben: bool
) -> list[str]:
    """
    Verteilt Legacy-Batteriewerte proportional auf die Speicher.

    Die Verteilung erfolgt nach Kapazität (kapazitaet_kwh). Bei fehlenden
    Kapazitätswerten wird gleichmäßig verteilt.

    Returns:
        Liste von Warnungen
    """
    warnungen = []

    if not speicher:
        return warnungen

    if batterie_ladung <= 0 and batterie_entladung <= 0:
        return warnungen

    # Gesamt-Kapazität berechnen
    total_kapazitaet = sum(
        (inv.parameter or {}).get("kapazitaet_kwh", 0) or 0
        for inv in speicher
    )

    for inv in speicher:
        inv_kap = (inv.parameter or {}).get("kapazitaet_kwh", 0) or 0

        if total_kapazitaet > 0:
            # Proportionale Verteilung nach Kapazität
            anteil = inv_kap / total_kapazitaet
        else:
            # Gleichmäßige Verteilung
            anteil = 1.0 / len(speicher)

        verbrauch_daten = {}
        if batterie_ladung > 0:
            verbrauch_daten["ladung_kwh"] = round(batterie_ladung * anteil, 1)
        if batterie_entladung > 0:
            verbrauch_daten["entladung_kwh"] = round(batterie_entladung * anteil, 1)

        if verbrauch_daten:
            await _upsert_investition_monatsdaten(db, inv.id, jahr, monat, verbrauch_daten, ueberschreiben)

    teile = []
    if batterie_ladung > 0:
        teile.append(f"Ladung {batterie_ladung:.0f} kWh")
    if batterie_entladung > 0:
        teile.append(f"Entladung {batterie_entladung:.0f} kWh")

    if total_kapazitaet > 0:
        warnungen.append(
            f"Legacy Batterie-Werte ({', '.join(teile)}) wurden proportional nach Kapazität "
            f"auf {len(speicher)} Speicher verteilt."
        )
    else:
        warnungen.append(
            f"Legacy Batterie-Werte ({', '.join(teile)}) wurden gleichmäßig "
            f"auf {len(speicher)} Speicher verteilt (keine Kapazitätswerte definiert)."
        )

    return warnungen


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
