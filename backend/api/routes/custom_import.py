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
from backend.models.settings import Settings

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


class AnalyzeResponse(BaseModel):
    dateiname: str
    format: str  # "csv" oder "json"
    spalten: list[ColumnInfo]
    zeilen_gesamt: int
    eedc_felder: list[dict]
    auto_mapping: dict[str, str]  # spalte → eedc_feld


class FieldMapping(BaseModel):
    spalte: str
    eedc_feld: str


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
    # Mapping aufbauen: spalte → eedc_feld
    field_map: dict[str, str] = {}
    for m in config.mappings:
        field_map[m.spalte] = m.eedc_feld

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
                    values[eedc_feld] = _convert_unit(num, config.einheit)

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


@router.get("/fields")
async def get_fields():
    """Verfügbare EEDC-Zielfelder für das Mapping."""
    return EEDC_FIELDS
