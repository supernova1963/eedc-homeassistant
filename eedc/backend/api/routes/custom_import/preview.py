"""
Custom-Import — Preview-Slice.

POST /preview — wendet Mapping auf hochgeladene Datei an und liefert
                Vorschau der erkannten Monate (ohne DB-Schreib-Effekt).
"""

import json
from collections.abc import Mapping, Sequence
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database import get_db
from backend.models.investition import Investition

from ._shared import (
    MappingConfig,
    ZeilenAbsturz,
    _parse_csv_rows,
    _parse_json_rows,
    _read_file_content,
    lies_monate,
    plane_zuordnung,
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
    inv_werte: dict[str, float] = {}


class PreviewResponse(BaseModel):
    monate: list[PreviewMonth]
    anzahl_monate: int
    warnungen: list[str]
    inv_spalten: list[str] = []


# ─── Mapping-Anwendung ───────────────────────────────────────────────────────

def _apply_mapping(
    headers: list[str],
    rows: list[dict[str, str]],
    config: MappingConfig,
    auto_inv_spalten: "Optional[Mapping[str, tuple[Optional[int], Optional[dict]]] | set[str]]" = None,
    investitionen: Optional[Sequence[Investition]] = None,
) -> tuple[list[PreviewMonth], list[str], list[str]]:
    """Wendet das Mapping auf die Daten an und gibt PreviewMonths zurück.

    ⛔ **Die Vorschau zeigt, was der Import schreibt (N-706, Prinzip N-666).** Sie liest über denselben Zeilen-Kern
    wie `apply.py` (`_shared.plane_zuordnung` + `lies_monate`) — vorher las sie mit eigener Handschrift und zeigte
    für Geräte-Spalten in Wh ein Tausendstel dessen, was der Import schrieb, bot «Jahr 0» an und listete Tageszeilen
    als mehrere gleiche Monate.

    `auto_inv_spalten` sind CSV-Spalten, die als Investitions-Suffix-Match erkannt wurden (z.B.
    `Wollis_ID5_Ladung_PV_kWh`) — als Spalte → (Investitions-ID, Registry-Feld) aus
    `analyze._erkannte_geraete_spalten`, oder als bloßes Namens-Set. Sie stehen im Wizard-Mapping auf „Ignorieren",
    werden aber beim Apply automatisch importiert. Diese Spalten und die gültigen `inv:`-Spalten landen pro Monat in
    `inv_werte`, damit die Vorschau-Tabelle sie als eigene Spalten anzeigen kann (#222). `investitionen` sind die der
    Ziel-Anlage; ohne sie (keine Anlage gewählt) prüft die Vorschau `inv:`-Zuordnungen nicht.

    Ein Monat, den der Import nicht schreiben würde (Zeilenfehler), steht nicht in der Liste; der Grund steht in
    den Warnungen.

    Rückgabe: (monate, warnungen, inv_spalten_sortiert).
    """
    plan = plane_zuordnung(config, investitionen, auto_inv_spalten or ())
    eintraege, skipped = lies_monate(rows, plan)

    results: list[PreviewMonth] = []
    warnungen: list[str] = list(plan.warnungen)
    used_inv_spalten: set[str] = set()  # nur Spalten, die in mind. einer Zeile einen Wert hatten
    zusammengefasst = 0

    for eintrag in eintraege:
        if isinstance(eintrag, ZeilenAbsturz):
            raise eintrag.fehler  # wie vor dem Kern (B7, verworfen): die Vorschau scheitert an dieser Zeile
        if eintrag.fehler:
            warnungen.append(
                f"{eintrag.jahr}/{eintrag.monat:02d}: {eintrag.fehler[0]} — dieser Monat wird nicht importiert"
            )
            continue
        values = eintrag.generisch
        inv_werte: dict[str, float] = {**eintrag.inv_werte, **eintrag.geraete_werte}
        lv = values.get("wallbox_ladevorgaenge")
        month = PreviewMonth(
            jahr=eintrag.jahr,
            monat=eintrag.monat,
            pv_erzeugung_kwh=values.get("pv_erzeugung_kwh"),
            einspeisung_kwh=values.get("einspeisung_kwh"),
            netzbezug_kwh=values.get("netzbezug_kwh"),
            eigenverbrauch_kwh=values.get("eigenverbrauch_kwh"),
            batterie_ladung_kwh=values.get("batterie_ladung_kwh"),
            batterie_entladung_kwh=values.get("batterie_entladung_kwh"),
            wallbox_ladung_kwh=values.get("wallbox_ladung_kwh"),
            wallbox_ladung_pv_kwh=values.get("wallbox_ladung_pv_kwh"),
            wallbox_ladevorgaenge=None if lv is None else int(lv),
            eauto_km_gefahren=values.get("eauto_km_gefahren"),
            inv_werte=inv_werte,
        )

        has_data = bool(inv_werte) or any(
            v is not None for v in [
                month.pv_erzeugung_kwh, month.einspeisung_kwh, month.netzbezug_kwh,
                month.eigenverbrauch_kwh, month.batterie_ladung_kwh, month.batterie_entladung_kwh,
                month.wallbox_ladung_kwh, month.wallbox_ladung_pv_kwh,
                month.wallbox_ladevorgaenge, month.eauto_km_gefahren,
            ]
        )
        if has_data:
            results.append(month)
            used_inv_spalten.update(inv_werte.keys())
            if len(eintrag.zeilen) > 1:
                zusammengefasst += 1

    if skipped > 0:
        warnungen.append(f"{skipped} Zeilen übersprungen (kein gültiges Jahr/Monat)")

    if zusammengefasst > 0:
        warnungen.append(
            f"{zusammengefasst} Monat(e) stehen in mehreren Zeilen (z. B. Tageswerte) — "
            "der Import schreibt je Monat die Summe"
        )

    if plan.geraete_spalten:
        warnungen.append(
            f"{len(plan.geraete_spalten)} eedc-Investitions-Spalte(n) automatisch erkannt: "
            f"{', '.join(sorted(plan.geraete_spalten))} — werden beim Import den passenden "
            "Investitionen zugeordnet (Einheit laut Spaltenname, ohne Umrechnung)."
        )

    # Nach Jahr+Monat sortieren
    results.sort(key=lambda m: (m.jahr, m.monat))

    # Inv-Spalten sortiert, beschränkt auf Spalten mit tatsächlichen Werten
    inv_spalten_sortiert = sorted(used_inv_spalten)

    return results, warnungen, inv_spalten_sortiert


# ─── Endpoint ────────────────────────────────────────────────────────────────


@router.post("/preview", response_model=PreviewResponse)
async def preview_mapping(
    file: UploadFile = File(...),
    mapping_json: str = Query(..., description="JSON-String mit MappingConfig"),
    anlage_id: Optional[int] = Query(None, description="Für Auto-Erkennung von Investitions-Spalten"),
    db: AsyncSession = Depends(get_db, scope="function"),
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

    # Investitions-Spalten der Anlage erkennen (gleiche Logik wie in /analyze und im Import).
    # Wenn anlage_id mitgegeben, kennt die Vorschau Spalten, die beim Apply
    # automatisch zugeordnet werden — sonst würden Zeilen ohne globale Felder
    # fälschlich als „keine Daten" verworfen (#222 NongJoWo) — und prüft die
    # `inv:`-Zuordnungen gegen die Anlage wie der Import (N-705).
    investitionen: Optional[list[Investition]] = None
    erkannte: dict[str, tuple[int, Optional[dict]]] = {}
    if anlage_id is not None:
        from .analyze import _erkannte_geraete_spalten
        investitionen = list((await db.execute(
            select(Investition).where(Investition.anlage_id == anlage_id)
        )).scalars().all())
        erkannte = _erkannte_geraete_spalten(headers, investitionen)

    monate, warnungen, inv_spalten = _apply_mapping(headers, rows, config, erkannte, investitionen)

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
        inv_spalten=inv_spalten,
    )
