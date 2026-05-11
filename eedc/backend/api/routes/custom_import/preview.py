"""
Custom-Import — Preview-Slice.

POST /preview — wendet Mapping auf hochgeladene Datei an und liefert
                Vorschau der erkannten Monate (ohne DB-Schreib-Effekt).
"""

import json
from typing import Optional

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from pydantic import BaseModel

from ._shared import (
    MappingConfig,
    _convert_unit,
    _parse_csv_rows,
    _parse_date_column,
    _parse_json_rows,
    _parse_number,
    _read_file_content,
)

router = APIRouter()


# ─── Models ──────────────────────────────────────────────────────────────────

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


# ─── Mapping-Anwendung ───────────────────────────────────────────────────────

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
        row_has_inv_data = False

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
            elif eedc_feld.startswith("inv:"):
                if _parse_number(raw, config.dezimalzeichen) is not None:
                    row_has_inv_data = True
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

        # Nur Monate mit mindestens einem Wert (inkl. Investitions-Slot-Daten,
        # die in der Vorschau zwar nicht sichtbar sind, aber beim Import landen).
        has_data = row_has_inv_data or any(
            v is not None for v in [
                month.pv_erzeugung_kwh, month.einspeisung_kwh, month.netzbezug_kwh,
                month.eigenverbrauch_kwh, month.batterie_ladung_kwh, month.batterie_entladung_kwh,
                month.wallbox_ladung_kwh, month.wallbox_ladung_pv_kwh,
                month.wallbox_ladevorgaenge, month.eauto_km_gefahren,
            ]
        )
        if has_data:
            results.append(month)

    if skipped > 0:
        warnungen.append(f"{skipped} Zeilen übersprungen (kein gültiges Jahr/Monat)")

    inv_mapping_count = sum(1 for f in field_map.values() if f.startswith("inv:"))
    if inv_mapping_count > 0:
        warnungen.append(
            f"{inv_mapping_count} Spalte(n) als Investitions-Daten gemappt — "
            "werden beim Import automatisch der zugehörigen Investition zugeordnet "
            "(Werte in der Vorschau-Tabelle nicht sichtbar)."
        )

    # Nach Jahr+Monat sortieren
    results.sort(key=lambda m: (m.jahr, m.monat))

    return results, warnungen


# ─── Endpoint ────────────────────────────────────────────────────────────────


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
        diagnose = " ".join(warnungen) if warnungen else (
            f"Mapping hat {len(rows)} Zeilen gelesen, aber keine enthielt erkennbare Zahlenwerte."
        )
        raise HTTPException(
            400,
            "Keine gültigen Monatsdaten mit diesem Mapping gefunden. "
            f"{diagnose} "
            "Häufige Ursachen: Datums-Format der Quelldatei nicht erkannt "
            "(z. B. ISO-Zeitstempel wie '2026-05-10T14:32:00'), oder Dezimalzeichen falsch "
            "gewählt (Punkt vs. Komma). Bitte Datums-Spalte/-Format und Dezimalzeichen "
            "im Wizard prüfen."
        )

    return PreviewResponse(
        monate=monate,
        anzahl_monate=len(monate),
        warnungen=warnungen,
    )
