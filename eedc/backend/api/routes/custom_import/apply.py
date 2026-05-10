"""
Custom-Import — Apply-Slice.

POST /apply/{anlage_id} — Wendet Custom-Mapping auf hochgeladene Datei
                          an und schreibt in DB. Nutzt Provenance-Wrapper
                          (`source="manual:csv_import"`, writer="csv_wizard").
"""

import json
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_db
from backend.api.routes.import_export.helpers import (
    _distribute_legacy_battery_to_storages,
    _distribute_legacy_pv_to_modules,
    _import_investition_monatsdaten_v09,
    _upsert_investition_monatsdaten,
)
from backend.models.anlage import Anlage
from backend.models.investition import Investition
from backend.models.monatsdaten import Monatsdaten
from backend.services.activity_service import log_activity
from backend.services.provenance import write_with_provenance

from ._shared import (
    MappingConfig,
    _convert_unit,
    _parse_csv_rows,
    _parse_date_column,
    _parse_json_rows,
    _parse_number,
    _read_file_content,
    logger,
)

router = APIRouter()


# ─── Models ──────────────────────────────────────────────────────────────────

class ApplyResponse(BaseModel):
    erfolg: bool
    importiert: int
    uebersprungen: int
    fehler: list[str]
    warnungen: list[str]
    # Etappe 3d Päckchen 3: Hierarchie-Schutz-Tracking — Top-Level-Felder +
    # Investitions-Sub-Keys, deren manuelle Werte den CSV-Apply abgewiesen haben.
    geschuetzt_count: int = 0
    geschuetzte_felder: list[str] = []


# ─── Endpoint ────────────────────────────────────────────────────────────────


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

    # Etappe 3d Päckchen 3: Hierarchie-Schutz-Tracking analog zu data_import.py.
    geschuetzt_count = 0
    geschuetzte_felder: list[str] = []

    def _record_upsert(upsert_res) -> None:
        """Sammler für Wizard-Telemetrie. Sowohl `_track_upsert` als auch der
        `on_upsert`-Callback der Helpers (`_distribute_*`,
        `_import_investition_monatsdaten_v09`) rufen dies, damit indirekt
        geschriebene Felder nicht ohne Tracking durchschlüpfen."""
        nonlocal geschuetzt_count
        geschuetzt_count += upsert_res.rejected_count
        for sub_key in upsert_res.rejected_fields:
            if len(geschuetzte_felder) < 15 and sub_key not in geschuetzte_felder:
                geschuetzte_felder.append(sub_key)

    async def _track_upsert(*args, **kwargs):
        upsert_res = await _upsert_investition_monatsdaten(*args, **kwargs)
        _record_upsert(upsert_res)
        return upsert_res

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
                    db, row, parse_float, investitionen, jahr, monat, ueberschreiben,
                    source="manual:csv_import", writer="csv_wizard",
                    on_upsert=_record_upsert,
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
                await _track_upsert(
                    db, inv_id_int, jahr, monat, verbrauch_daten, ueberschreiben,
                    source="manual:csv_import", writer="csv_wizard",
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
                        db, pv_mapped, pv_module, jahr, monat, ueberschreiben,
                        source="manual:csv_import", writer="csv_wizard",
                        on_upsert=_record_upsert,
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
                        speicher, jahr, monat, ueberschreiben,
                        source="manual:csv_import", writer="csv_wizard",
                        on_upsert=_record_upsert,
                    )
                    if importiert == 0:
                        warnungen.extend(w)
                bat_ladung = bat_ladung_mapped
                bat_entladung = bat_entladung_mapped

            # ── Monatsdaten schreiben ─────────────────────────────────────────
            # Top-Level-Felder gehen über write_with_provenance (CSV-Wizard ist
            # User-bestätigt → manual:csv_import). Hierarchie: gleiche MANUAL-
            # Klasse wie manual:form, also Last-Writer-Wins beim ueberschreiben=True.
            if existing_md:
                md = existing_md
            else:
                md = Monatsdaten(anlage_id=anlage_id, jahr=jahr, monat=monat)
                db.add(md)
                await db.flush()  # damit md.id existiert

            top_level_writes: list[tuple[str, Optional[float]]] = [
                ("einspeisung_kwh", einspeisung),
                ("netzbezug_kwh", netzbezug),
                ("eigenverbrauch_kwh", eigenverbrauch),
                ("pv_erzeugung_kwh", pv_erzeugung),
                ("batterie_ladung_kwh", bat_ladung),
                ("batterie_entladung_kwh", bat_entladung),
            ]
            for field_name, value in top_level_writes:
                if value is not None:
                    result = await write_with_provenance(
                        db, md, field_name, value,
                        source="manual:csv_import", writer="csv_wizard",
                    )
                    if result.decision == "rejected_lower_priority":
                        geschuetzt_count += 1
                        if len(geschuetzte_felder) < 15 and field_name not in geschuetzte_felder:
                            geschuetzte_felder.append(field_name)
            md.datenquelle = "custom_import"

            importiert += 1

        except Exception as e:
            logger.exception(f"Fehler bei Zeile (Jahr={jahr}, Monat={monat})")
            fehler.append(f"{jahr}/{monat:02d}: {str(e)}")

    await db.flush()

    # Etappe 3d Päckchen 3: Wizard-Hinweis bei aktivierter Quellen-Hierarchie.
    if geschuetzt_count > 0:
        sample = ", ".join(geschuetzte_felder[:5])
        suffix = f" (z. B. {sample})" if sample else ""
        warnungen.insert(0, (
            f"{geschuetzt_count} Felder wurden durch manuell gepflegte Werte "
            f"geschützt{suffix} — Reset über Reparatur-Werkbank wenn gewollt."
        ))

    await log_activity(
        kategorie="portal_import",
        aktion=f"Custom-Import: {importiert} Monate importiert",
        erfolg=len(fehler) == 0,
        details=f"Anlage {anlage_id}, übersprungen: {uebersprungen}, geschützt: {geschuetzt_count}",
        details_json={
            "importiert": importiert, "uebersprungen": uebersprungen,
            "geschuetzt": geschuetzt_count, "fehler": fehler[:5],
        },
        anlage_id=anlage_id,
    )

    return ApplyResponse(
        erfolg=len(fehler) == 0,
        importiert=importiert,
        uebersprungen=uebersprungen,
        fehler=fehler[:20],
        warnungen=warnungen[:10],
        geschuetzt_count=geschuetzt_count,
        geschuetzte_felder=geschuetzte_felder,
    )
