"""
Custom-Import — gemeinsame Models, Parser-Helpers, Konstanten.

Genutzt von analyze.py, preview.py, apply.py und templates.py.
Alle Sub-Slices teilen sich die Datei-Lese- und Number-Parsing-
Pipeline; Mapping-Schemas (`MappingConfig`/`FieldMapping`) sind in
mehreren Endpoints im Body-Schema.
"""

import csv
import hashlib
import io
import json
import logging
from typing import Optional

from fastapi import HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)


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
    {"id": "eauto_km_gefahren", "label": "E-Auto Gefahrene km", "required": False, "group": "eauto"},
]

SETTINGS_KEY = "custom_import_templates"


# ─── Mapping-Models — gemeinsam zwischen preview, apply, templates ──────────

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


# ─── Datei-/Parser-Helpers ──────────────────────────────────────────────────

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


# ─── Temporärer Speicher für Upload-Sessions ─────────────────────────────────
# In-Memory Cache für die aktuelle Upload-Session (zwischen Analyze und Preview)
# Key: session_id (filename hash), Value: (headers, rows, filename)
_upload_cache: dict[str, tuple[list[str], list[dict[str, str]], str]] = {}


def _cache_key(filename: str, content: str) -> str:
    """Erzeugt einen Cache-Key aus Dateiname und Content-Hash."""
    h = hashlib.md5(content[:2048].encode()).hexdigest()[:12]
    return f"{filename}_{h}"
