"""
Custom-Import — Analyze-Slice.

POST /analyze   — Datei hochladen, Spalten + Auto-Mapping erkennen.
GET  /fields    — Verfügbare EEDC-Zielfelder.
"""

from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_db
from backend.api.routes.import_export.helpers import (
    _normalize_for_matching,
    _sanitize_column_name,
)
from backend.core.field_definitions import get_alle_felder_fuer_investition
from backend.models.investition import Investition

from ._shared import (
    EEDC_FIELDS,
    _cache_key,
    _parse_csv_rows,
    _parse_json_rows,
    _read_file_content,
    _upload_cache,
)

router = APIRouter()


# ─── Models ──────────────────────────────────────────────────────────────────

class ColumnInfo(BaseModel):
    name: str
    sample_values: list[str]


class InvestitionSpalteInfo(BaseModel):
    spalte: str           # CSV-Spaltenname, z.B. "BYD_HVS_12_8_Ladung_kWh"
    inv_id: int
    inv_bezeichnung: str  # z.B. "BYD HVS 12.8"
    inv_typ: str          # z.B. "speicher"
    suffix: str           # z.B. "Ladung_kWh"


class AnalyzeResponse(BaseModel):
    dateiname: str
    format: str  # "csv" oder "json"
    spalten: list[ColumnInfo]
    zeilen_gesamt: int
    eedc_felder: list[dict]
    auto_mapping: dict[str, str]  # spalte → eedc_feld
    investitions_spalten: list[InvestitionSpalteInfo] = []
    investitions_felder: list[dict] = []  # dynamische Zielfelder für Mapping-Dropdown


# ─── Analyze-spezifische Helpers ─────────────────────────────────────────────

def _auto_detect_mapping(headers: list[str]) -> dict[str, str]:
    """Versucht automatisch Spalten auf EEDC-Felder zu mappen."""
    mapping: dict[str, str] = {}

    # Normalisierte Header für Matching
    header_lower = {h: h.lower().replace(" ", "_").replace("-", "_") for h in headers}

    patterns: dict[str, list[str]] = {
        "jahr": ["jahr", "year", "date_year"],
        "monat": ["monat", "month", "date_month"],
        "pv_erzeugung_kwh": ["pv_erzeugung", "pv_ertrag", "erzeugung", "yield", "production", "generation", "pv_kwh", "pv_erzeugung_kwh"],
        "einspeisung_kwh": ["einspeisung", "feed_in", "export", "grid_export", "einspeisung_kwh"],
        "netzbezug_kwh": ["netzbezug", "grid_import", "bezug", "consumption_grid", "netzbezug_kwh", "buy"],
        "eigenverbrauch_kwh": ["eigenverbrauch", "self_consumption", "direct_use", "eigenverbrauch_kwh"],
        "batterie_ladung_kwh": ["batterie_ladung", "battery_charge", "bat_charge", "ladung", "batterie_ladung_kwh", "charge"],
        "batterie_entladung_kwh": ["batterie_entladung", "battery_discharge", "bat_discharge", "entladung", "batterie_entladung_kwh", "discharge"],
        "wallbox_ladung_kwh": ["wallbox_ladung", "wallbox", "ev_charge", "wallbox_ladung_kwh"],
        "eauto_km_gefahren": ["km_gefahren", "km", "mileage", "distance", "eauto_km"],
    }

    used_headers: set[str] = set()
    for eedc_feld, keywords in patterns.items():
        for header in headers:
            if header in used_headers:
                continue
            normalized = header_lower[header]
            for keyword in keywords:
                if keyword == normalized or keyword in normalized:
                    mapping[header] = eedc_feld
                    used_headers.add(header)
                    break
            if header in mapping:
                break

    return mapping


def _build_investition_felder(investitionen: list) -> list[dict]:
    """
    Erzeugt dynamische Zielfelder für das Mapping-Dropdown aus den Investitionen einer Anlage.
    Format: {"id": "inv:42:pv_erzeugung_kwh", "label": "PV-Modul: Bauer 385 – Erzeugung (kWh)", ...}

    Felddefinitionen kommen aus field_definitions.INVESTITION_FELDER — kein hardcodierter Typ-Check.
    """
    # Typ → Gruppen-ID + Anzeige-Präfix
    TYP_META = {
        "pv-module":      ("inv_pv",        "PV-Modul"),
        "wechselrichter": ("inv_pv",        "Wechselrichter"),
        "speicher":       ("inv_speicher",   "Speicher"),
        "e-auto":         ("inv_eauto",      "E-Auto"),
        "wallbox":        ("inv_wallbox",    "Wallbox"),
        "waermepumpe":    ("inv_wp",         "WP"),
        "balkonkraftwerk":("inv_bkw",        "BKW"),
        "sonstiges":      ("inv_sonstiges",  "Sonstiges"),
    }

    felder = []
    for inv in investitionen:
        group, prefix = TYP_META.get(inv.typ, ("inv_sonstiges", inv.typ))
        bez = inv.bezeichnung
        inv_id = inv.id

        for feld in get_alle_felder_fuer_investition(inv.typ, inv.parameter):
            feld_name = feld["feld"]
            einheit = feld["einheit"]
            label_teil = feld["label"]
            einheit_str = f" ({einheit})" if einheit else ""
            felder.append({
                "id": f"inv:{inv_id}:{feld_name}",
                "label": f"{prefix}: {bez} – {label_teil}{einheit_str}",
                "required": False,
                "group": group,
            })

    return felder


async def _detect_investition_spalten(
    headers: list[str],
    anlage_id: int,
    db: AsyncSession,
) -> list[InvestitionSpalteInfo]:
    """Erkennt welche CSV-Spalten zu Investitionen der Anlage gehören.

    known_suffixes werden aus field_definitions abgeleitet — kein hardcodierter Suffix-Block.
    """
    result = await db.execute(
        select(Investition).where(Investition.anlage_id == anlage_id)
    )
    investitionen = result.scalars().all()
    if not investitionen:
        return []

    # Lookup-Tabelle + known_suffixes aus Registry
    inv_field_entries = []
    for inv in investitionen:
        sanitized = _sanitize_column_name(inv.bezeichnung)
        normalized = _normalize_for_matching(inv.bezeichnung)
        for feld in get_alle_felder_fuer_investition(inv.typ, inv.parameter):
            csv_suffix = feld.get("csv_suffix")
            if csv_suffix:
                inv_field_entries.append((inv, sanitized, normalized, csv_suffix))
            alt = feld.get("csv_suffix_alt")
            if alt:
                inv_field_entries.append((inv, sanitized, normalized, alt))

    # Sonderkosten für alle Typen ergänzen
    SONDERKOSTEN_SUFFIXE = ("Sonderkosten_Euro", "Sonderkosten_Notiz")
    for inv in investitionen:
        sanitized = _sanitize_column_name(inv.bezeichnung)
        normalized = _normalize_for_matching(inv.bezeichnung)
        for sk in SONDERKOSTEN_SUFFIXE:
            inv_field_entries.append((inv, sanitized, normalized, sk))

    known_suffixes = sorted(
        {entry[3] for entry in inv_field_entries},
        key=len, reverse=True
    )

    detected: list[InvestitionSpalteInfo] = []
    for col in headers:
        matched = False
        for inv, sanitized, normalized, csv_suffix in inv_field_entries:
            # Strategie 1: exaktes Präfix-Match
            if col == f"{sanitized}_{csv_suffix}" or col == sanitized:
                detected.append(InvestitionSpalteInfo(
                    spalte=col,
                    inv_id=inv.id,
                    inv_bezeichnung=inv.bezeichnung,
                    inv_typ=inv.typ,
                    suffix=csv_suffix,
                ))
                matched = True
                break

        if matched:
            continue

        # Strategie 2: Suffix-basiertes Matching
        for suffix in known_suffixes:
            if col.endswith("_" + suffix):
                prefix = col[: -len(suffix) - 1]
                prefix_norm = _normalize_for_matching(prefix)
                for inv, sanitized, normalized, csv_suffix in inv_field_entries:
                    if csv_suffix == suffix and (
                        prefix_norm == normalized or prefix == sanitized
                    ):
                        detected.append(InvestitionSpalteInfo(
                            spalte=col,
                            inv_id=inv.id,
                            inv_bezeichnung=inv.bezeichnung,
                            inv_typ=inv.typ,
                            suffix=suffix,
                        ))
                        matched = True
                        break
            if matched:
                break

    return detected


# ─── Endpoints ────────────────────────────────────────────────────────────────


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze_file(
    file: UploadFile = File(...),
    anlage_id: Optional[int] = Query(None, description="Anlage-ID für Investitions-Erkennung"),
    db: AsyncSession = Depends(get_db),
):
    """Datei hochladen und Spalten erkennen. Gibt Spalten mit Beispielwerten zurück."""
    content_bytes = await file.read()
    content = _read_file_content(content_bytes)

    if not content.strip():
        raise HTTPException(400, "Die Datei ist leer.")

    filename = file.filename or "upload"
    is_json = filename.lower().endswith(".json") or content.strip().startswith(("{", "["))

    if is_json:
        headers, rows = _parse_json_rows(content)
        file_format = "json"
    else:
        headers, rows = _parse_csv_rows(content)
        file_format = "csv"

    if not rows:
        raise HTTPException(400, "Keine Datenzeilen in der Datei gefunden.")

    # Sample-Werte sammeln (max 3 pro Spalte)
    spalten: list[ColumnInfo] = []
    for h in headers:
        samples = []
        for row in rows[:5]:
            val = row.get(h, "")
            if val and len(samples) < 3:
                samples.append(val[:50])
        spalten.append(ColumnInfo(name=h, sample_values=samples))

    # Auto-Mapping versuchen
    auto_mapping = _auto_detect_mapping(headers)

    # Investitions-Spalten erkennen + Zielfelder für Dropdown generieren (wenn anlage_id bekannt)
    investitions_spalten: list[InvestitionSpalteInfo] = []
    investitions_felder: list[dict] = []
    if anlage_id:
        inv_result = await db.execute(
            select(Investition).where(Investition.anlage_id == anlage_id)
        )
        investitionen_list = list(inv_result.scalars().all())
        investitions_spalten = await _detect_investition_spalten(headers, anlage_id, db)
        investitions_felder = _build_investition_felder(investitionen_list)

    # In Cache speichern für Preview
    key = _cache_key(filename, content)
    _upload_cache[key] = (headers, rows, filename)

    # Cache aufräumen (max 20 Einträge)
    if len(_upload_cache) > 20:
        oldest = list(_upload_cache.keys())[0]
        del _upload_cache[oldest]

    return AnalyzeResponse(
        dateiname=filename,
        format=file_format,
        spalten=spalten,
        zeilen_gesamt=len(rows),
        eedc_felder=EEDC_FIELDS,
        auto_mapping=auto_mapping,
        investitions_spalten=investitions_spalten,
        investitions_felder=investitions_felder,
    )


@router.get("/fields")
async def get_fields():
    """Verfügbare EEDC-Zielfelder für das Mapping."""
    return EEDC_FIELDS
