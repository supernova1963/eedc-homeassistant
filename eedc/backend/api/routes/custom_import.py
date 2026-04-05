"""
Custom-Import API Routes.

Ermöglicht den Import von beliebigen CSV/JSON-Dateien mit benutzerdefiniertem
Feld-Mapping. Der User kann Spalten seiner Datei den EEDC-Feldern zuordnen
und das Mapping als Template speichern.
"""

import csv
import io
import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_db
from backend.models.anlage import Anlage
from backend.models.investition import Investition
from backend.models.monatsdaten import Monatsdaten
from backend.models.settings import Settings
from backend.api.routes.import_export.helpers import (
    _import_investition_monatsdaten_v09,
    _upsert_investition_monatsdaten,
    _sanitize_column_name,
    _distribute_legacy_pv_to_modules,
    _distribute_legacy_battery_to_storages,
)
from backend.services.activity_service import log_activity

logger = logging.getLogger(__name__)

router = APIRouter()


# ─── EEDC-Zielfelder ─────────────────────────────────────────────────────────

EEDC_FIELDS = [
    {"id": "jahr", "label": "Jahr", "required": True, "group": "zeit"},
    {"id": "monat", "label": "Monat", "required": True, "group": "zeit"},
    {"id": "pv_erzeugung_kwh", "label": "PV-Erzeugung (kWh)", "required": False, "group": "energie"},
    {"id": "einspeisung_kwh", "label": "Einspeisung (kWh)", "required": False, "group": "energie"},
    {"id": "netzbezug_kwh", "label": "Netzbezug (kWh)", "required": False, "group": "energie"},
    {"id": "eigenverbrauch_kwh", "label": "Eigenverbrauch (kWh)", "required": False, "group": "energie"},
    {"id": "batterie_ladung_kwh", "label": "Batterie Ladung (kWh)", "required": False, "group": "batterie"},
    {"id": "batterie_entladung_kwh", "label": "Batterie Entladung (kWh)", "required": False, "group": "batterie"},
    {"id": "wallbox_ladung_kwh", "label": "Wallbox Ladung (kWh)", "required": False, "group": "wallbox"},
    {"id": "wallbox_ladung_pv_kwh", "label": "Wallbox PV-Ladung (kWh)", "required": False, "group": "wallbox"},
    {"id": "wallbox_ladevorgaenge", "label": "Wallbox Ladevorgänge", "required": False, "group": "wallbox"},
    {"id": "eauto_km_gefahren", "label": "E-Auto km gefahren", "required": False, "group": "eauto"},
]

SETTINGS_KEY = "custom_import_templates"

# ─── Schemas ──────────────────────────────────────────────────────────────────


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


class FieldMapping(BaseModel):
    spalte: str
    eedc_feld: str
    invertieren: bool = False  # Vorzeichen invertieren (negative → positive)


class MappingConfig(BaseModel):
    mappings: list[FieldMapping]
    einheit: str = "kwh"  # "wh", "kwh", "mwh"
    dezimalzeichen: str = "auto"  # "auto", "punkt", "komma"
    datum_spalte: Optional[str] = None  # Falls Jahr+Monat in einer Spalte
    datum_format: Optional[str] = None  # z.B. "YYYY-MM", "MM/YYYY"


class PreviewRequest(BaseModel):
    mapping: MappingConfig


class PreviewMonth(BaseModel):
    jahr: int
    monat: int
    pv_erzeugung_kwh: Optional[float] = None
    einspeisung_kwh: Optional[float] = None
    netzbezug_kwh: Optional[float] = None
    batterie_ladung_kwh: Optional[float] = None
    batterie_entladung_kwh: Optional[float] = None
    eigenverbrauch_kwh: Optional[float] = None
    wallbox_ladung_kwh: Optional[float] = None
    wallbox_ladung_pv_kwh: Optional[float] = None
    wallbox_ladevorgaenge: Optional[int] = None
    eauto_km_gefahren: Optional[float] = None


class PreviewResponse(BaseModel):
    monate: list[PreviewMonth]
    anzahl_monate: int
    warnungen: list[str]


class TemplateInfo(BaseModel):
    name: str
    mapping: MappingConfig


class TemplateListResponse(BaseModel):
    templates: list[TemplateInfo]


class ApplyResponse(BaseModel):
    erfolg: bool
    importiert: int
    uebersprungen: int
    fehler: list[str]
    warnungen: list[str]


# ─── Hilfsfunktionen ─────────────────────────────────────────────────────────


def _read_file_content(content_bytes: bytes) -> str:
    """Datei als Text lesen (UTF-8 oder Latin-1)."""
    try:
        return content_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            return content_bytes.decode("latin-1")
        except UnicodeDecodeError:
            raise HTTPException(400, "Datei konnte nicht gelesen werden. Bitte UTF-8 oder Latin-1 verwenden.")


def _detect_csv_dialect(content: str) -> csv.Dialect:
    """Erkennt CSV-Trennzeichen automatisch."""
    try:
        sniffer = csv.Sniffer()
        dialect = sniffer.sniff(content[:4096], delimiters=";,\t")
        return dialect
    except csv.Error:
        # Fallback: Semikolon (deutsch) oder Komma
        if ";" in content[:1000]:
            csv.register_dialect("fallback", delimiter=";", quoting=csv.QUOTE_MINIMAL)
            return csv.get_dialect("fallback")
        csv.register_dialect("fallback_comma", delimiter=",", quoting=csv.QUOTE_MINIMAL)
        return csv.get_dialect("fallback_comma")


def _parse_csv_rows(content: str) -> tuple[list[str], list[dict[str, str]]]:
    """Parst CSV und gibt (header, rows) zurück."""
    dialect = _detect_csv_dialect(content)
    reader = csv.DictReader(io.StringIO(content), dialect=dialect)

    if not reader.fieldnames:
        raise HTTPException(400, "Keine Spaltenüberschriften in der CSV-Datei gefunden.")

    headers = [h.strip() for h in reader.fieldnames if h and h.strip()]
    rows = []
    for row in reader:
        cleaned = {k.strip(): (v.strip() if v else "") for k, v in row.items() if k and k.strip()}
        if any(v for v in cleaned.values()):
            rows.append(cleaned)

    return headers, rows


def _parse_json_rows(content: str) -> tuple[list[str], list[dict[str, str]]]:
    """Parst JSON-Array und gibt (header, rows) zurück."""
    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        raise HTTPException(400, f"Ungültiges JSON-Format: {e}")

    if isinstance(data, dict):
        # Mögliches Wrapper-Objekt — nach Array suchen
        for key in data:
            if isinstance(data[key], list) and len(data[key]) > 0:
                data = data[key]
                break
        else:
            raise HTTPException(400, "JSON enthält kein Array mit Datensätzen.")

    if not isinstance(data, list) or len(data) == 0:
        raise HTTPException(400, "JSON enthält keine Datensätze.")

    if not isinstance(data[0], dict):
        raise HTTPException(400, "JSON-Einträge müssen Objekte mit Key-Value-Paaren sein.")

    # Alle Keys sammeln
    all_keys: set[str] = set()
    for item in data:
        if isinstance(item, dict):
            all_keys.update(item.keys())

    headers = sorted(all_keys)
    rows = [{k: str(v) if v is not None else "" for k, v in item.items()} for item in data if isinstance(item, dict)]

    return headers, rows


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


def _parse_number(value: str, dezimalzeichen: str = "auto") -> Optional[float]:
    """Parst einen Zahlenwert mit konfigurierbarem Dezimalzeichen."""
    if not value or value.strip() in ("", "-", "–", "n/a", "N/A"):
        return None

    value = value.strip()

    if dezimalzeichen == "komma":
        value = value.replace(".", "").replace(",", ".")
    elif dezimalzeichen == "punkt":
        value = value.replace(",", "")
    else:
        # Auto-Detect
        if "," in value and "." in value:
            # 1.234,56 (deutsch) oder 1,234.56 (englisch)
            if value.rfind(",") > value.rfind("."):
                value = value.replace(".", "").replace(",", ".")
            else:
                value = value.replace(",", "")
        elif "," in value:
            value = value.replace(",", ".")

    try:
        return float(value)
    except ValueError:
        return None


def _convert_unit(value: Optional[float], einheit: str) -> Optional[float]:
    """Konvertiert Wh/MWh zu kWh."""
    if value is None:
        return None
    if einheit == "wh":
        return round(value / 1000, 2)
    if einheit == "mwh":
        return round(value * 1000, 2)
    return round(value, 2)


def _parse_date_column(value: str, fmt: str) -> tuple[Optional[int], Optional[int]]:
    """Extrahiert Jahr und Monat aus einer kombinierten Datumsspalte."""
    value = value.strip()
    if not value:
        return None, None

    from datetime import datetime

    # Vordefinierte Formate probieren
    formats = [fmt] if fmt else []
    formats.extend([
        "%Y-%m", "%m/%Y", "%Y/%m", "%m-%Y",
        "%Y-%m-%d", "%d.%m.%Y", "%m/%d/%Y",
        "%Y%m",
    ])

    for f in formats:
        try:
            dt = datetime.strptime(value, f)
            return dt.year, dt.month
        except (ValueError, TypeError):
            continue

    # Fallback: Nur Zahl = evtl. YYYYMM
    try:
        num = int(value)
        if 190001 <= num <= 210012:
            return num // 100, num % 100
    except ValueError:
        pass

    return None, None


def _apply_mapping(
    headers: list[str],
    rows: list[dict[str, str]],
    config: MappingConfig,
) -> tuple[list[PreviewMonth], list[str]]:
    """Wendet das Mapping auf die Daten an und gibt PreviewMonths zurück."""
    # Mapping aufbauen: spalte → eedc_feld, invertieren
    field_map: dict[str, str] = {}
    invert_map: dict[str, bool] = {}
    for m in config.mappings:
        field_map[m.spalte] = m.eedc_feld
        if m.invertieren:
            invert_map[m.spalte] = True

    results: list[PreviewMonth] = []
    warnungen: list[str] = []
    skipped = 0

    for row_idx, row in enumerate(rows):
        values: dict[str, Optional[float]] = {}
        jahr: Optional[int] = None
        monat: Optional[int] = None

        # Datum aus kombinierter Spalte?
        if config.datum_spalte and config.datum_spalte in row:
            j, m = _parse_date_column(row[config.datum_spalte], config.datum_format or "")
            if j and m:
                jahr = j
                monat = m

        for spalte, eedc_feld in field_map.items():
            raw = row.get(spalte, "")
            if not raw:
                continue

            if eedc_feld == "jahr" and jahr is None:
                try:
                    jahr = int(float(raw))
                except (ValueError, TypeError):
                    pass
            elif eedc_feld == "monat" and monat is None:
                try:
                    monat = int(float(raw))
                except (ValueError, TypeError):
                    pass
            else:
                num = _parse_number(raw, config.dezimalzeichen)
                if num is not None:
                    val = _convert_unit(num, config.einheit)
                    if val is not None and invert_map.get(spalte):
                        val = abs(val)
                    values[eedc_feld] = val

        if jahr is None or monat is None or monat < 1 or monat > 12:
            skipped += 1
            continue

        month = PreviewMonth(
            jahr=jahr,
            monat=monat,
            pv_erzeugung_kwh=values.get("pv_erzeugung_kwh"),
            einspeisung_kwh=values.get("einspeisung_kwh"),
            netzbezug_kwh=values.get("netzbezug_kwh"),
            eigenverbrauch_kwh=values.get("eigenverbrauch_kwh"),
            batterie_ladung_kwh=values.get("batterie_ladung_kwh"),
            batterie_entladung_kwh=values.get("batterie_entladung_kwh"),
            wallbox_ladung_kwh=values.get("wallbox_ladung_kwh"),
            wallbox_ladung_pv_kwh=values.get("wallbox_ladung_pv_kwh"),
            wallbox_ladevorgaenge=int(values["wallbox_ladevorgaenge"]) if values.get("wallbox_ladevorgaenge") is not None else None,
            eauto_km_gefahren=values.get("eauto_km_gefahren"),
        )

        # Nur Monate mit mindestens einem Wert
        has_data = any(
            v is not None for v in [
                month.pv_erzeugung_kwh, month.einspeisung_kwh, month.netzbezug_kwh,
                month.eigenverbrauch_kwh, month.batterie_ladung_kwh, month.batterie_entladung_kwh,
                month.wallbox_ladung_kwh, month.eauto_km_gefahren,
            ]
        )
        if has_data:
            results.append(month)

    if skipped > 0:
        warnungen.append(f"{skipped} Zeilen übersprungen (kein gültiges Jahr/Monat)")

    # Nach Jahr+Monat sortieren
    results.sort(key=lambda m: (m.jahr, m.monat))

    return results, warnungen


def _build_investition_felder(investitionen: list) -> list[dict]:
    """
    Erzeugt dynamische Zielfelder für das Mapping-Dropdown aus den Investitionen einer Anlage.
    Format: {"id": "inv:42:pv_erzeugung_kwh", "label": "PV-Modul: Bauer 385 – Erzeugung (kWh)", ...}
    """
    felder = []
    for inv in investitionen:
        bez = inv.bezeichnung
        inv_id = inv.id
        typ = inv.typ

        if typ == "pv-module":
            felder.append({"id": f"inv:{inv_id}:pv_erzeugung_kwh", "label": f"PV-Modul: {bez} – Erzeugung (kWh)", "required": False, "group": f"inv_pv"})

        elif typ == "speicher":
            felder.append({"id": f"inv:{inv_id}:ladung_kwh",          "label": f"Speicher: {bez} – Ladung (kWh)",          "required": False, "group": "inv_speicher"})
            felder.append({"id": f"inv:{inv_id}:entladung_kwh",       "label": f"Speicher: {bez} – Entladung (kWh)",       "required": False, "group": "inv_speicher"})
            felder.append({"id": f"inv:{inv_id}:ladung_netz_kwh",     "label": f"Speicher: {bez} – Netzladung/Arbitrage (kWh)", "required": False, "group": "inv_speicher"})
            felder.append({"id": f"inv:{inv_id}:speicher_ladepreis_cent", "label": f"Speicher: {bez} – Ladepreis Arbitrage (Cent)", "required": False, "group": "inv_speicher"})

        elif typ == "e-auto":
            felder.append({"id": f"inv:{inv_id}:km_gefahren",       "label": f"E-Auto: {bez} – km gefahren",         "required": False, "group": "inv_eauto"})
            felder.append({"id": f"inv:{inv_id}:verbrauch_kwh",     "label": f"E-Auto: {bez} – Verbrauch (kWh)",      "required": False, "group": "inv_eauto"})
            felder.append({"id": f"inv:{inv_id}:ladung_pv_kwh",     "label": f"E-Auto: {bez} – Ladung PV (kWh)",      "required": False, "group": "inv_eauto"})
            felder.append({"id": f"inv:{inv_id}:ladung_netz_kwh",   "label": f"E-Auto: {bez} – Ladung Netz (kWh)",    "required": False, "group": "inv_eauto"})
            felder.append({"id": f"inv:{inv_id}:ladung_extern_kwh", "label": f"E-Auto: {bez} – Laden extern (kWh)",   "required": False, "group": "inv_eauto"})
            felder.append({"id": f"inv:{inv_id}:ladung_extern_euro","label": f"E-Auto: {bez} – Laden extern (€)",     "required": False, "group": "inv_eauto"})
            felder.append({"id": f"inv:{inv_id}:v2h_entladung_kwh", "label": f"E-Auto: {bez} – V2H Entladung (kWh)", "required": False, "group": "inv_eauto"})

        elif typ == "wallbox":
            felder.append({"id": f"inv:{inv_id}:ladung_kwh",    "label": f"Wallbox: {bez} – Ladung (kWh)",  "required": False, "group": "inv_wallbox"})
            felder.append({"id": f"inv:{inv_id}:ladevorgaenge", "label": f"Wallbox: {bez} – Ladevorgänge",  "required": False, "group": "inv_wallbox"})

        elif typ == "waermepumpe":
            felder.append({"id": f"inv:{inv_id}:stromverbrauch_kwh",  "label": f"WP: {bez} – Stromverbrauch gesamt (kWh)",  "required": False, "group": "inv_wp"})
            felder.append({"id": f"inv:{inv_id}:strom_heizen_kwh",    "label": f"WP: {bez} – Strom Heizung (kWh)",          "required": False, "group": "inv_wp"})
            felder.append({"id": f"inv:{inv_id}:strom_warmwasser_kwh","label": f"WP: {bez} – Strom Warmwasser (kWh)",       "required": False, "group": "inv_wp"})
            felder.append({"id": f"inv:{inv_id}:heizenergie_kwh",     "label": f"WP: {bez} – Heizenergie (kWh)",            "required": False, "group": "inv_wp"})
            felder.append({"id": f"inv:{inv_id}:warmwasser_kwh",      "label": f"WP: {bez} – Warmwasser Wärme (kWh)",       "required": False, "group": "inv_wp"})

        elif typ == "balkonkraftwerk":
            felder.append({"id": f"inv:{inv_id}:pv_erzeugung_kwh",    "label": f"BKW: {bez} – Erzeugung (kWh)",         "required": False, "group": "inv_bkw"})
            felder.append({"id": f"inv:{inv_id}:eigenverbrauch_kwh",  "label": f"BKW: {bez} – Eigenverbrauch (kWh)",    "required": False, "group": "inv_bkw"})
            felder.append({"id": f"inv:{inv_id}:speicher_ladung_kwh", "label": f"BKW: {bez} – Speicher Ladung (kWh)",   "required": False, "group": "inv_bkw"})
            felder.append({"id": f"inv:{inv_id}:speicher_entladung_kwh","label": f"BKW: {bez} – Speicher Entladung (kWh)","required": False, "group": "inv_bkw"})

        elif typ == "sonstiges":
            kategorie = (inv.parameter or {}).get("kategorie", "erzeuger")
            if kategorie == "erzeuger":
                felder.append({"id": f"inv:{inv_id}:erzeugung_kwh",      "label": f"Sonstiges: {bez} – Erzeugung (kWh)",  "required": False, "group": "inv_sonstiges"})
            elif kategorie == "verbraucher":
                felder.append({"id": f"inv:{inv_id}:verbrauch_sonstig_kwh", "label": f"Sonstiges: {bez} – Verbrauch (kWh)", "required": False, "group": "inv_sonstiges"})
            elif kategorie == "speicher":
                felder.append({"id": f"inv:{inv_id}:ladung_kwh",    "label": f"Sonstiges: {bez} – Ladung (kWh)",    "required": False, "group": "inv_sonstiges"})
                felder.append({"id": f"inv:{inv_id}:entladung_kwh", "label": f"Sonstiges: {bez} – Entladung (kWh)", "required": False, "group": "inv_sonstiges"})

    return felder


async def _detect_investition_spalten(
    headers: list[str],
    anlage_id: int,
    db: AsyncSession,
) -> list[InvestitionSpalteInfo]:
    """Erkennt welche CSV-Spalten zu Investitionen der Anlage gehören."""
    result = await db.execute(
        select(Investition).where(Investition.anlage_id == anlage_id)
    )
    investitionen = result.scalars().all()
    if not investitionen:
        return []

    # Bekannte Suffixe (sortiert nach Länge: längste zuerst)
    known_suffixes = sorted([
        "kWh", "km", "Verbrauch_kWh", "Ladung_PV_kWh", "Ladung_Netz_kWh",
        "Ladung_Extern_kWh", "Ladung_Extern_Euro", "V2H_kWh",
        "Ladung_kWh", "Entladung_kWh", "Ladevorgaenge",
        "Netzladung_kWh", "Ladepreis_Cent",
        "Strom_kWh", "Heizung_kWh", "Warmwasser_kWh",
        "Speicher_Ladung_kWh", "Speicher_Entladung_kWh",
        "Erzeugung_kWh", "Sonderkosten_Euro", "Sonderkosten_Notiz",
    ], key=len, reverse=True)

    inv_variants = [(
        _sanitize_column_name(inv.bezeichnung), inv
    ) for inv in investitionen]

    detected: list[InvestitionSpalteInfo] = []
    for col in headers:
        for sanitized, inv in inv_variants:
            # Strategie 1: Spaltenname beginnt mit sanitized_name + "_"
            if col.startswith(sanitized + "_"):
                suffix = col[len(sanitized) + 1:]
                detected.append(InvestitionSpalteInfo(
                    spalte=col,
                    inv_id=inv.id,
                    inv_bezeichnung=inv.bezeichnung,
                    inv_typ=inv.typ,
                    suffix=suffix,
                ))
                break
            # Strategie 2: Suffix-basiertes Matching
            for known_suffix in known_suffixes:
                if col.endswith("_" + known_suffix):
                    prefix = col[:-len(known_suffix) - 1]
                    if prefix == sanitized:
                        detected.append(InvestitionSpalteInfo(
                            spalte=col,
                            inv_id=inv.id,
                            inv_bezeichnung=inv.bezeichnung,
                            inv_typ=inv.typ,
                            suffix=known_suffix,
                        ))
                        break
            else:
                continue
            break

    return detected


# ─── Temporärer Speicher für Upload-Sessions ─────────────────────────────────
# In-Memory Cache für die aktuelle Upload-Session (zwischen Analyze und Preview)
# Key: session_id (filename hash), Value: (headers, rows)
_upload_cache: dict[str, tuple[list[str], list[dict[str, str]], str]] = {}


def _cache_key(filename: str, content: str) -> str:
    """Erzeugt einen Cache-Key aus Dateiname und Content-Hash."""
    import hashlib
    h = hashlib.md5(content[:2048].encode()).hexdigest()[:12]
    return f"{filename}_{h}"


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


@router.post("/preview", response_model=PreviewResponse)
async def preview_mapping(
    file: UploadFile = File(...),
    mapping_json: str = Query(..., description="JSON-String mit MappingConfig"),
):
    """Wendet das Mapping auf die Datei an und gibt eine Vorschau zurück."""
    try:
        mapping_data = json.loads(mapping_json)
        config = MappingConfig(**(mapping_data.get("mapping", mapping_data)))
    except (json.JSONDecodeError, Exception) as e:
        raise HTTPException(400, f"Ungültiges Mapping-Format: {e}")

    content_bytes = await file.read()
    content = _read_file_content(content_bytes)

    if not content.strip():
        raise HTTPException(400, "Die Datei ist leer.")

    filename = file.filename or "upload"
    is_json = filename.lower().endswith(".json") or content.strip().startswith(("{", "["))

    if is_json:
        headers, rows = _parse_json_rows(content)
    else:
        headers, rows = _parse_csv_rows(content)

    if not rows:
        raise HTTPException(400, "Keine Datenzeilen in der Datei gefunden.")

    monate, warnungen = _apply_mapping(headers, rows, config)

    if not monate:
        raise HTTPException(
            400,
            "Keine gültigen Monatsdaten mit diesem Mapping gefunden. "
            "Bitte prüfe die Zuordnung von Jahr und Monat."
        )

    return PreviewResponse(
        monate=monate,
        anzahl_monate=len(monate),
        warnungen=warnungen,
    )


# ─── Templates ────────────────────────────────────────────────────────────────


@router.get("/templates", response_model=TemplateListResponse)
async def get_templates(db: AsyncSession = Depends(get_db)):
    """Gespeicherte Mapping-Templates abrufen."""
    result = await db.execute(select(Settings).where(Settings.key == SETTINGS_KEY))
    setting = result.scalar_one_or_none()

    templates = []
    if setting and setting.value:
        for name, mapping_data in setting.value.items():
            try:
                config = MappingConfig(**mapping_data)
                templates.append(TemplateInfo(name=name, mapping=config))
            except Exception:
                pass

    return TemplateListResponse(templates=templates)


@router.post("/templates/{name}")
async def save_template(
    name: str,
    mapping: MappingConfig,
    db: AsyncSession = Depends(get_db),
):
    """Mapping-Template speichern."""
    if not name.strip():
        raise HTTPException(400, "Template-Name darf nicht leer sein.")

    result = await db.execute(select(Settings).where(Settings.key == SETTINGS_KEY))
    setting = result.scalar_one_or_none()

    if setting:
        templates = dict(setting.value) if setting.value else {}
    else:
        setting = Settings(key=SETTINGS_KEY, value={})
        db.add(setting)
        templates = {}

    templates[name.strip()] = mapping.model_dump()
    setting.value = templates

    from sqlalchemy.orm.attributes import flag_modified
    flag_modified(setting, "value")
    await db.flush()

    return {"erfolg": True, "message": f"Template '{name}' gespeichert."}


@router.delete("/templates/{name}")
async def delete_template(
    name: str,
    db: AsyncSession = Depends(get_db),
):
    """Mapping-Template löschen."""
    result = await db.execute(select(Settings).where(Settings.key == SETTINGS_KEY))
    setting = result.scalar_one_or_none()

    if not setting or not setting.value or name not in setting.value:
        raise HTTPException(404, f"Template '{name}' nicht gefunden.")

    templates = dict(setting.value)
    del templates[name]
    setting.value = templates

    from sqlalchemy.orm.attributes import flag_modified
    flag_modified(setting, "value")
    await db.flush()

    return {"erfolg": True, "message": f"Template '{name}' gelöscht."}


@router.post("/apply/{anlage_id}", response_model=ApplyResponse)
async def apply_custom_import(
    anlage_id: int,
    file: UploadFile = File(...),
    mapping_json: str = Query(..., description="JSON-String mit MappingConfig"),
    monate_json: str = Query(..., description="JSON-Array mit [{jahr, monat}] der zu importierenden Monate"),
    ueberschreiben: bool = Query(False),
    db: AsyncSession = Depends(get_db),
):
    """
    Wendet das Custom-Mapping auf die Datei an und importiert die Daten.

    Verarbeitet:
    1. Generische Felder (via MappingConfig) → Monatsdaten
    2. Investitions-Spalten (automatisch erkannt) → InvestitionMonatsdaten
       via _import_investition_monatsdaten_v09 (identisch mit regulärem CSV-Import)
    """
    # Anlage prüfen
    anlage_result = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    anlage = anlage_result.scalar_one_or_none()
    if not anlage:
        raise HTTPException(404, f"Anlage {anlage_id} nicht gefunden.")

    # Parameter parsen
    try:
        mapping_data = json.loads(mapping_json)
        config = MappingConfig(**(mapping_data.get("mapping", mapping_data)))
    except Exception as e:
        raise HTTPException(400, f"Ungültiges Mapping-Format: {e}")

    try:
        selected_raw = json.loads(monate_json)
        selected: set[tuple[int, int]] = {(m["jahr"], m["monat"]) for m in selected_raw}
    except Exception as e:
        raise HTTPException(400, f"Ungültiges Monate-Format: {e}")

    # Datei lesen und parsen
    content_bytes = await file.read()
    content = _read_file_content(content_bytes)
    if not content.strip():
        raise HTTPException(400, "Die Datei ist leer.")

    filename = file.filename or "upload"
    is_json = filename.lower().endswith(".json") or content.strip().startswith(("{", "["))
    if is_json:
        headers, rows = _parse_json_rows(content)
    else:
        headers, rows = _parse_csv_rows(content)

    if not rows:
        raise HTTPException(400, "Keine Datenzeilen in der Datei gefunden.")

    # Investitionen laden
    inv_result = await db.execute(
        select(Investition).where(Investition.anlage_id == anlage_id)
    )
    investitionen = list(inv_result.scalars().all())
    pv_module = [i for i in investitionen if i.typ == "pv-module"]
    speicher = [i for i in investitionen if i.typ == "speicher"]

    # Mapping aufbauen: spalte → eedc_feld / invertieren
    field_map: dict[str, str] = {m.spalte: m.eedc_feld for m in config.mappings}
    invert_map: dict[str, bool] = {m.spalte: True for m in config.mappings if m.invertieren}

    importiert = 0
    uebersprungen = 0
    fehler: list[str] = []
    warnungen: list[str] = []

    def parse_float(val: str) -> Optional[float]:
        return _parse_number(val, config.dezimalzeichen)

    def parse_float_inv(val: str, spalte: str) -> Optional[float]:
        """parse_float + Vorzeichen-Inversion wenn konfiguriert."""
        num = _parse_number(val, config.dezimalzeichen)
        if num is not None and invert_map.get(spalte):
            num = abs(num)
        return num

    for row in rows:
        try:
            # Jahr + Monat extrahieren
            jahr: Optional[int] = None
            monat: Optional[int] = None

            if config.datum_spalte and config.datum_spalte in row:
                j, m = _parse_date_column(row[config.datum_spalte], config.datum_format or "")
                if j and m:
                    jahr, monat = j, m

            for spalte, eedc_feld in field_map.items():
                raw = row.get(spalte, "")
                if not raw:
                    continue
                if eedc_feld == "jahr" and jahr is None:
                    try:
                        jahr = int(float(raw))
                    except (ValueError, TypeError):
                        pass
                elif eedc_feld == "monat" and monat is None:
                    try:
                        monat = int(float(raw))
                    except (ValueError, TypeError):
                        pass

            if not jahr or not monat or monat < 1 or monat > 12:
                continue

            # Nur ausgewählte Monate importieren
            if (jahr, monat) not in selected:
                continue

            # Bestehende Monatsdaten prüfen
            existing = await db.execute(
                select(Monatsdaten).where(
                    Monatsdaten.anlage_id == anlage_id,
                    Monatsdaten.jahr == jahr,
                    Monatsdaten.monat == monat,
                )
            )
            existing_md = existing.scalar_one_or_none()
            if existing_md and not ueberschreiben:
                uebersprungen += 1
                continue

            # ── Investitions-Spalten verarbeiten ──────────────────────────────
            # Liefert Summen: pv_erzeugung_sum, batterie_ladung_sum, batterie_entladung_sum
            summen = {"pv_erzeugung_sum": 0.0, "batterie_ladung_sum": 0.0, "batterie_entladung_sum": 0.0}
            if investitionen:
                summen = await _import_investition_monatsdaten_v09(
                    db, row, parse_float, investitionen, jahr, monat, ueberschreiben
                )

            # ── Investitions-Felder aus manuellem Mapping (inv:ID:feld) ──────
            # z.B. {"Ertrag_Sued": "inv:42:pv_erzeugung_kwh"}
            inv_collected: dict[int, dict] = {}
            for spalte, eedc_feld in field_map.items():
                if not eedc_feld.startswith("inv:"):
                    continue
                raw = row.get(spalte, "")
                if not raw:
                    continue
                parts = eedc_feld.split(":", 2)
                if len(parts) != 3:
                    continue
                inv_id_str, field_key = parts[1], parts[2]
                try:
                    inv_id_int = int(inv_id_str)
                except ValueError:
                    continue
                val = _convert_unit(parse_float_inv(raw, spalte), config.einheit)
                if val is None:
                    continue
                if field_key == "ladevorgaenge":
                    val = int(val)
                if inv_id_int not in inv_collected:
                    inv_collected[inv_id_int] = {}
                inv_collected[inv_id_int][field_key] = val

            # Manuell gemappte Investitions-Felder speichern + Summen berechnen
            for inv_id_int, verbrauch_daten in inv_collected.items():
                await _upsert_investition_monatsdaten(
                    db, inv_id_int, jahr, monat, verbrauch_daten, ueberschreiben
                )
                # PV- und Batterie-Summen für Monatsdaten-Aggregat pflegen
                if "pv_erzeugung_kwh" in verbrauch_daten:
                    summen["pv_erzeugung_sum"] += verbrauch_daten["pv_erzeugung_kwh"]
                if "erzeugung_kwh" in verbrauch_daten:
                    summen["pv_erzeugung_sum"] += verbrauch_daten["erzeugung_kwh"]
                if "ladung_kwh" in verbrauch_daten:
                    summen["batterie_ladung_sum"] += verbrauch_daten["ladung_kwh"]
                if "entladung_kwh" in verbrauch_daten:
                    summen["batterie_entladung_sum"] += verbrauch_daten["entladung_kwh"]
                # BKW-Speicher
                if "speicher_ladung_kwh" in verbrauch_daten:
                    summen["batterie_ladung_sum"] += verbrauch_daten["speicher_ladung_kwh"]
                if "speicher_entladung_kwh" in verbrauch_daten:
                    summen["batterie_entladung_sum"] += verbrauch_daten["speicher_entladung_kwh"]

            # ── Generische Felder aus Mapping ─────────────────────────────────
            einspeisung: Optional[float] = None
            netzbezug: Optional[float] = None
            eigenverbrauch: Optional[float] = None
            pv_mapped: Optional[float] = None
            bat_ladung_mapped: Optional[float] = None
            bat_entladung_mapped: Optional[float] = None

            for spalte, eedc_feld in field_map.items():
                raw = row.get(spalte, "")
                if not raw or eedc_feld in ("jahr", "monat") or eedc_feld.startswith("inv:"):
                    continue
                val = _convert_unit(parse_float_inv(raw, spalte), config.einheit)
                if val is None:
                    continue
                if eedc_feld == "einspeisung_kwh":
                    einspeisung = val
                elif eedc_feld == "netzbezug_kwh":
                    netzbezug = val
                elif eedc_feld == "eigenverbrauch_kwh":
                    eigenverbrauch = val
                elif eedc_feld == "pv_erzeugung_kwh":
                    pv_mapped = val
                elif eedc_feld == "batterie_ladung_kwh":
                    bat_ladung_mapped = val
                elif eedc_feld == "batterie_entladung_kwh":
                    bat_entladung_mapped = val

            # ── PV-Erzeugung: Investitions-Summe hat Vorrang ──────────────────
            pv_erzeugung: Optional[float] = None
            if summen["pv_erzeugung_sum"] > 0:
                # Individuelle PV-Modul-Werte vorhanden → Summe verwenden
                pv_erzeugung = summen["pv_erzeugung_sum"]
            elif pv_mapped is not None and pv_mapped > 0:
                # Nur generischer Wert → auf PV-Module verteilen (wenn vorhanden)
                if pv_module:
                    w = await _distribute_legacy_pv_to_modules(
                        db, pv_mapped, pv_module, jahr, monat, ueberschreiben
                    )
                    if importiert == 0:
                        warnungen.extend(w)
                pv_erzeugung = pv_mapped

            # ── Batterie: Investitions-Summe hat Vorrang ──────────────────────
            bat_ladung: Optional[float] = None
            bat_entladung: Optional[float] = None
            if summen["batterie_ladung_sum"] > 0 or summen["batterie_entladung_sum"] > 0:
                bat_ladung = summen["batterie_ladung_sum"] or None
                bat_entladung = summen["batterie_entladung_sum"] or None
            else:
                if bat_ladung_mapped is not None and bat_ladung_mapped > 0 and speicher:
                    w = await _distribute_legacy_battery_to_storages(
                        db, bat_ladung_mapped, bat_entladung_mapped or 0,
                        speicher, jahr, monat, ueberschreiben
                    )
                    if importiert == 0:
                        warnungen.extend(w)
                bat_ladung = bat_ladung_mapped
                bat_entladung = bat_entladung_mapped

            # ── Monatsdaten schreiben ─────────────────────────────────────────
            if existing_md:
                md = existing_md
            else:
                md = Monatsdaten(anlage_id=anlage_id, jahr=jahr, monat=monat)
                db.add(md)

            if einspeisung is not None:
                md.einspeisung_kwh = einspeisung
            if netzbezug is not None:
                md.netzbezug_kwh = netzbezug
            if eigenverbrauch is not None:
                md.eigenverbrauch_kwh = eigenverbrauch
            if pv_erzeugung is not None:
                md.pv_erzeugung_kwh = pv_erzeugung
            if bat_ladung is not None:
                md.batterie_ladung_kwh = bat_ladung
            if bat_entladung is not None:
                md.batterie_entladung_kwh = bat_entladung
            md.datenquelle = "custom_import"

            importiert += 1

        except Exception as e:
            logger.exception(f"Fehler bei Zeile (Jahr={jahr}, Monat={monat})")
            fehler.append(f"{jahr}/{monat:02d}: {str(e)}")

    await db.flush()

    await log_activity(
        kategorie="portal_import",
        aktion=f"Custom-Import: {importiert} Monate importiert",
        erfolg=len(fehler) == 0,
        details=f"Anlage {anlage_id}, übersprungen: {uebersprungen}",
        details_json={"importiert": importiert, "uebersprungen": uebersprungen, "fehler": fehler[:5]},
        anlage_id=anlage_id,
    )

    return ApplyResponse(
        erfolg=len(fehler) == 0,
        importiert=importiert,
        uebersprungen=uebersprungen,
        fehler=fehler[:20],
        warnungen=warnungen[:10],
    )


@router.get("/fields")
async def get_fields():
    """Verfügbare EEDC-Zielfelder für das Mapping."""
    return EEDC_FIELDS
