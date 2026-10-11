"""
Custom-Import — Apply-Slice.

POST /apply/{anlage_id} — Wendet Custom-Mapping auf hochgeladene Datei
                          an und schreibt in DB. Nutzt Provenance-Wrapper
                          (`source="manual:csv_import"`, writer="csv_wizard").
"""

import json
from dataclasses import dataclass, field
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
    _maybe_convert,
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


# ─── Zustand des Imports (RF-10) ─────────────────────────────────────────────

@dataclass
class _ImportKontext:
    """Was jede Zeile braucht: Mapping, Investitionen der Anlage und ihre Pools."""

    config: MappingConfig
    investitionen: list[Investition]
    pv_module: list[Investition]
    speicher: list[Investition]
    eautos_priv: list[Investition]
    wallboxen_priv: list[Investition]
    field_map: dict[str, str]
    invert_map: dict[str, bool]

    def parse_float(self, val: str) -> Optional[float]:
        return _parse_number(val, self.config.dezimalzeichen)

    def parse_float_inv(self, val: str, spalte: str) -> Optional[float]:
        """parse_float + Vorzeichen-Inversion wenn konfiguriert."""
        num = _parse_number(val, self.config.dezimalzeichen)
        if num is not None and self.invert_map.get(spalte):
            num = abs(num)
        return num


@dataclass
class _ImportStand:
    """Zähler und Meldungen über alle Zeilen; `importiert == 0` lässt die Verteil-Warnungen durch."""

    importiert: int = 0
    uebersprungen: int = 0
    fehler: list[str] = field(default_factory=list)
    warnungen: list[str] = field(default_factory=list)


@dataclass
class _ZeilenPosition:
    """Jahr und Monat einer Zeile, schrittweise erkannt."""

    jahr: Optional[int] = None
    monat: Optional[int] = None


@dataclass
class _GenerischeWerte:
    """Die generisch gemappten Werte einer Zeile."""

    einspeisung: Optional[float]
    netzbezug: Optional[float]
    eigenverbrauch: Optional[float]
    pv_mapped: Optional[float]
    bat_ladung_mapped: Optional[float]
    bat_entladung_mapped: Optional[float]
    eauto_km_legacy: Optional[float]
    wallbox_lv_legacy: Optional[int]


# ─── Endpoint ────────────────────────────────────────────────────────────────


@router.post("/apply/{anlage_id}", response_model=ApplyResponse)
async def apply_custom_import(
    anlage_id: int,
    file: UploadFile = File(...),
    mapping_json: str = Query(..., description="JSON-String mit MappingConfig"),
    monate_json: str = Query(..., description="JSON-Array mit [{jahr, monat}] der zu importierenden Monate"),
    ueberschreiben: bool = Query(False),
    db: AsyncSession = Depends(get_db, scope="function"),
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

    config, selected = _lies_parameter(mapping_json, monate_json)
    rows = await _lies_datei(file)
    kontext = await _lade_kontext(db, anlage_id, config)
    stand = _ImportStand()

    # ⛔ Kein Schutz-Zaehler auf diesem Weg (N-538, gemessen 20.09.2026): die Quelle
    # ist `manual:*`, und eine manuelle Quelle schreibt seit #251 (`f0b45bcc`)
    # UNBEDINGT — `provenance._decide` kennt fuer sie kein `rejected_lower_priority`.
    # Ohne Haken wird ein bestehender Monat oben uebersprungen, mit Haken gewinnt
    # der letzte Schreiber (MANUAL gegen MANUAL). Der Zaehler samt Hinweis
    # „X Felder geschuetzt" lief hier deshalb nie und ist entfernt; er lebt nur
    # im Portal-Import (`data_import.py`, Quelle `external:*`, geraetegebunden).

    for row in rows:
        await _importiere_zeile(db, anlage_id, row, kontext, selected, ueberschreiben, stand)

    await db.flush()

    await log_activity(
        kategorie="portal_import",
        aktion=f"Custom-Import: {stand.importiert} Monate importiert",
        erfolg=len(stand.fehler) == 0,
        details=f"Anlage {anlage_id}, übersprungen: {stand.uebersprungen}",
        details_json={
            "importiert": stand.importiert, "uebersprungen": stand.uebersprungen,
            "fehler": stand.fehler[:5],
        },
        anlage_id=anlage_id,
        db=db,
    )

    return ApplyResponse(
        erfolg=len(stand.fehler) == 0,
        importiert=stand.importiert,
        uebersprungen=stand.uebersprungen,
        fehler=stand.fehler[:20],
        warnungen=stand.warnungen[:10],
    )


# =============================================================================
# Phasen von `apply_custom_import` (RF-10 der Serie „Funktion vor Datei")
# =============================================================================
#
# Reiner Umzug: jede Phase nimmt ihre Verzweigungen mit. Die Schreibreihenfolge
# einer Zeile bleibt die des Schleifenkörpers vor dem Schnitt — Investitions-
# Spalten (v09) → manuell gemappte `inv:`-Felder → PV-/Batterie-Verteilung →
# Monatsdaten → Legacy-E-Auto/Wallbox; Quelle überall `manual:csv_import`.


def _lies_parameter(mapping_json: str, monate_json: str) -> tuple[MappingConfig, set[tuple[int, int]]]:
    """Mapping und Monatsauswahl aus den Query-Parametern — 400 bei ungültigem Format."""
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

    return config, selected


async def _lies_datei(file: UploadFile) -> list[dict[str, str]]:
    """Datei lesen und als JSON oder CSV in Zeilen zerlegen — 400 bei leerer Datei oder ohne Datenzeilen."""
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

    return rows


async def _lade_kontext(db: AsyncSession, anlage_id: int, config: MappingConfig) -> _ImportKontext:
    """Investitionen der Anlage, ihre Pools und das Spalten-Mapping — einmal je Import."""
    # Investitionen laden
    inv_result = await db.execute(
        select(Investition).where(Investition.anlage_id == anlage_id)
    )
    investitionen = list(inv_result.scalars().all())
    pv_module = [i for i in investitionen if i.typ == "pv-module"]
    speicher = [i for i in investitionen if i.typ == "speicher"]
    # Legacy-Top-Level-Targets `eauto_km_gefahren` und `wallbox_ladevorgaenge`
    # haben keinen Investitions-Slot — landen auf der jeweils ersten nicht-
    # dienstlichen Investition (analog `data_import.py` Re-Import-Pfad).
    from backend.core.investition_parameter import ist_dienstlich as _ist_dienstlich
    eautos_priv = [i for i in investitionen if i.typ == "e-auto" and not _ist_dienstlich(i)]
    wallboxen_priv = [i for i in investitionen if i.typ == "wallbox" and not _ist_dienstlich(i)]

    # Mapping aufbauen: spalte → eedc_feld / invertieren
    field_map: dict[str, str] = {m.spalte: m.eedc_feld for m in config.mappings}
    invert_map: dict[str, bool] = {m.spalte: True for m in config.mappings if m.invertieren}

    return _ImportKontext(
        config=config,
        investitionen=investitionen,
        pv_module=pv_module,
        speicher=speicher,
        eautos_priv=eautos_priv,
        wallboxen_priv=wallboxen_priv,
        field_map=field_map,
        invert_map=invert_map,
    )


async def _importiere_zeile(
    db: AsyncSession,
    anlage_id: int,
    row: dict[str, str],
    kontext: _ImportKontext,
    selected: set[tuple[int, int]],
    ueberschreiben: bool,
    stand: _ImportStand,
) -> None:
    """Eine Datenzeile → ein Monat. Ein Fehler zählt die Zeile in `stand.fehler`; was sie bis dahin
    geschrieben hat, bleibt in der Sitzung (kein Rollback je Zeile)."""
    pos = _ZeilenPosition()
    try:
        # Jahr + Monat extrahieren
        _lies_jahr_monat(row, kontext.config, kontext.field_map, pos)
        jahr, monat = pos.jahr, pos.monat

        if not jahr or not monat or monat < 1 or monat > 12:
            return

        # Nur ausgewählte Monate importieren
        if (jahr, monat) not in selected:
            return

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
            stand.uebersprungen += 1
            return

        # ── Investitions-Spalten verarbeiten ──────────────────────────────
        # Liefert Summen: pv_erzeugung_sum, batterie_ladung_sum, batterie_entladung_sum
        summen = await _summen_aus_investitions_spalten(db, row, kontext, jahr, monat, ueberschreiben)

        # ── Investitions-Felder aus manuellem Mapping (inv:ID:feld) ──────
        # z.B. {"Ertrag_Sued": "inv:42:pv_erzeugung_kwh"}
        inv_collected = _sammle_inv_felder(row, kontext)

        # Manuell gemappte Investitions-Felder speichern + Summen berechnen
        await _schreibe_inv_felder(db, inv_collected, jahr, monat, ueberschreiben, summen)

        # ── Generische Felder aus Mapping ─────────────────────────────────
        werte = _generische_felder(row, kontext)

        # ── PV-Erzeugung: Investitions-Summe hat Vorrang ──────────────────
        pv_erzeugung = await _pv_erzeugung(db, kontext, summen, werte, jahr, monat, ueberschreiben, stand)

        # ── Batterie: Investitions-Summe hat Vorrang ──────────────────────
        bat_ladung, bat_entladung = await _batterie(db, kontext, summen, werte, jahr, monat, ueberschreiben, stand)

        # ── Monatsdaten schreiben ─────────────────────────────────────────
        await _schreibe_monatsdaten(
            db, anlage_id, existing_md, jahr, monat, werte, pv_erzeugung, bat_ladung, bat_entladung,
        )

        await _schreibe_legacy_emob(db, kontext, werte, jahr, monat, ueberschreiben)

        stand.importiert += 1

    except Exception as e:
        logger.exception(f"Fehler bei Zeile (Jahr={pos.jahr}, Monat={pos.monat})")
        stand.fehler.append(f"{pos.jahr}/{pos.monat:02d}: {str(e)}")


def _lies_jahr_monat(
    row: dict[str, str], config: MappingConfig, field_map: dict[str, str], pos: _ZeilenPosition,
) -> None:
    """Jahr und Monat der Zeile: zuerst die kombinierte Datumsspalte, dann die Jahr-/Monat-Spalten.

    Schreibt schrittweise in `pos` — die Fehlermeldung der Zeile nennt, was bis zu einem Fehler erkannt war.
    """
    if config.datum_spalte and config.datum_spalte in row:
        j, m = _parse_date_column(row[config.datum_spalte], config.datum_format or "")
        if j and m:
            pos.jahr, pos.monat = j, m

    for spalte, eedc_feld in field_map.items():
        raw = row.get(spalte, "")
        if not raw:
            continue
        if eedc_feld == "jahr" and pos.jahr is None:
            try:
                pos.jahr = int(float(raw))
            except (ValueError, TypeError):
                pass
        elif eedc_feld == "monat" and pos.monat is None:
            try:
                pos.monat = int(float(raw))
            except (ValueError, TypeError):
                pass


async def _summen_aus_investitions_spalten(
    db: AsyncSession, row: dict[str, str], kontext: _ImportKontext, jahr: int, monat: int, ueberschreiben: bool,
) -> dict:
    """Automatisch erkannte Investitions-Spalten schreiben (identisch mit dem regulären CSV-Import) und ihre
    Summen für das Monatsdaten-Aggregat liefern — ohne Investitionen bleiben die Summen 0."""
    summen = {"pv_erzeugung_sum": 0.0, "batterie_ladung_sum": 0.0, "batterie_entladung_sum": 0.0}
    if kontext.investitionen:
        summen = await _import_investition_monatsdaten_v09(
            db, row, kontext.parse_float, kontext.investitionen, jahr, monat, ueberschreiben,
            source="manual:csv_import", writer="csv_wizard",
        )
    return summen


def _sammle_inv_felder(row: dict[str, str], kontext: _ImportKontext) -> dict[int, dict]:
    """Manuell auf `inv:<id>:<feld>` gemappte Spalten der Zeile, je Investition gesammelt."""
    inv_collected: dict[int, dict] = {}
    for spalte, eedc_feld in kontext.field_map.items():
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
        val = _maybe_convert(kontext.parse_float_inv(raw, spalte), kontext.config.einheit, eedc_feld)
        if val is None:
            continue
        if field_key == "ladevorgaenge":
            val = int(val)
        if inv_id_int not in inv_collected:
            inv_collected[inv_id_int] = {}
        inv_collected[inv_id_int][field_key] = val
    return inv_collected


async def _schreibe_inv_felder(
    db: AsyncSession, inv_collected: dict[int, dict], jahr: int, monat: int, ueberschreiben: bool, summen: dict,
) -> None:
    """Die gesammelten `inv:`-Felder je Investition schreiben und ihre PV-/Batterie-Anteile in `summen` addieren."""
    for inv_id_int, verbrauch_daten in inv_collected.items():
        await _upsert_investition_monatsdaten(
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


def _generische_felder(row: dict[str, str], kontext: _ImportKontext) -> _GenerischeWerte:
    """Die generisch gemappten Felder der Zeile (ohne Jahr/Monat und ohne `inv:`-Slots)."""
    einspeisung: Optional[float] = None
    netzbezug: Optional[float] = None
    eigenverbrauch: Optional[float] = None
    pv_mapped: Optional[float] = None
    bat_ladung_mapped: Optional[float] = None
    bat_entladung_mapped: Optional[float] = None

    # Legacy-Top-Level-Targets, die nicht auf einer einzelnen Investition
    # liegen — werden weiter unten anteilig auf die jeweilige Pool-
    # Investition geschrieben (E-Auto: erstes nicht-dienstliches,
    # Wallbox: erste nicht-dienstliche).
    eauto_km_legacy: Optional[float] = None
    wallbox_lv_legacy: Optional[int] = None

    for spalte, eedc_feld in kontext.field_map.items():
        raw = row.get(spalte, "")
        if not raw or eedc_feld in ("jahr", "monat") or eedc_feld.startswith("inv:"):
            continue
        val = _maybe_convert(kontext.parse_float_inv(raw, spalte), kontext.config.einheit, eedc_feld)
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
        elif eedc_feld == "eauto_km_gefahren":
            eauto_km_legacy = val
        elif eedc_feld == "wallbox_ladevorgaenge":
            wallbox_lv_legacy = int(val)

    return _GenerischeWerte(
        einspeisung=einspeisung,
        netzbezug=netzbezug,
        eigenverbrauch=eigenverbrauch,
        pv_mapped=pv_mapped,
        bat_ladung_mapped=bat_ladung_mapped,
        bat_entladung_mapped=bat_entladung_mapped,
        eauto_km_legacy=eauto_km_legacy,
        wallbox_lv_legacy=wallbox_lv_legacy,
    )


async def _pv_erzeugung(
    db: AsyncSession, kontext: _ImportKontext, summen: dict, werte: _GenerischeWerte,
    jahr: int, monat: int, ueberschreiben: bool, stand: _ImportStand,
) -> Optional[float]:
    """PV-Erzeugung des Monats: die Investitions-Summe hat Vorrang; ein generischer Wert wird auf die Module verteilt."""
    pv_erzeugung: Optional[float] = None
    if summen["pv_erzeugung_sum"] > 0:
        # Individuelle PV-Modul-Werte vorhanden → Summe verwenden
        pv_erzeugung = summen["pv_erzeugung_sum"]
    elif werte.pv_mapped is not None and werte.pv_mapped > 0:
        # Nur generischer Wert → auf PV-Module verteilen (wenn vorhanden)
        if kontext.pv_module:
            w = await _distribute_legacy_pv_to_modules(
                db, werte.pv_mapped, kontext.pv_module, jahr, monat, ueberschreiben,
                source="manual:csv_import", writer="csv_wizard",
            )
            if stand.importiert == 0:
                stand.warnungen.extend(w)
        pv_erzeugung = werte.pv_mapped
    return pv_erzeugung


async def _batterie(
    db: AsyncSession, kontext: _ImportKontext, summen: dict, werte: _GenerischeWerte,
    jahr: int, monat: int, ueberschreiben: bool, stand: _ImportStand,
) -> tuple[Optional[float], Optional[float]]:
    """Batterie-Ladung/-Entladung des Monats: die Investitions-Summe hat Vorrang; ein generischer Wert wird auf
    die Speicher verteilt."""
    bat_ladung: Optional[float] = None
    bat_entladung: Optional[float] = None
    if summen["batterie_ladung_sum"] > 0 or summen["batterie_entladung_sum"] > 0:
        bat_ladung = summen["batterie_ladung_sum"] or None
        bat_entladung = summen["batterie_entladung_sum"] or None
    else:
        if werte.bat_ladung_mapped is not None and werte.bat_ladung_mapped > 0 and kontext.speicher:
            w = await _distribute_legacy_battery_to_storages(
                db, werte.bat_ladung_mapped, werte.bat_entladung_mapped or 0,
                kontext.speicher, jahr, monat, ueberschreiben,
                source="manual:csv_import", writer="csv_wizard",
            )
            if stand.importiert == 0:
                stand.warnungen.extend(w)
        bat_ladung = werte.bat_ladung_mapped
        bat_entladung = werte.bat_entladung_mapped
    return bat_ladung, bat_entladung


async def _schreibe_monatsdaten(
    db: AsyncSession, anlage_id: int, existing_md: Optional[Monatsdaten], jahr: int, monat: int,
    werte: _GenerischeWerte, pv_erzeugung: Optional[float],
    bat_ladung: Optional[float], bat_entladung: Optional[float],
) -> None:
    """Die Monatszeile anlegen oder übernehmen und die Top-Level-Felder über die Provenance schreiben."""
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
        ("einspeisung_kwh", werte.einspeisung),
        ("netzbezug_kwh", werte.netzbezug),
        ("eigenverbrauch_kwh", werte.eigenverbrauch),
        ("pv_erzeugung_kwh", pv_erzeugung),
        ("batterie_ladung_kwh", bat_ladung),
        ("batterie_entladung_kwh", bat_entladung),
    ]
    for field_name, value in top_level_writes:
        if value is not None:
            await write_with_provenance(
                db, md, field_name, value,
                source="manual:csv_import", writer="csv_wizard",
            )
    md.datenquelle = "custom_import"


async def _schreibe_legacy_emob(
    db: AsyncSession, kontext: _ImportKontext, werte: _GenerischeWerte, jahr: int, monat: int, ueberschreiben: bool,
) -> None:
    """E-Auto-km und Wallbox-Ladevorgänge ohne Investitions-Slot auf die erste nicht-dienstliche Investition."""
    # Legacy-Top-Level-Felder ohne Investitions-Slot (#229 JanKgh-Folge):
    # auf die erste nicht-dienstliche E-Auto-/Wallbox-Investition schreiben,
    # analog data_import.py-Re-Import-Pfad. Falls der User stattdessen den
    # per-investitions-Slot gewählt hat (`inv:<id>:km_gefahren`), läuft der
    # Wert bereits über die inv_collected-Schiene oben.
    if werte.eauto_km_legacy is not None and werte.eauto_km_legacy > 0 and kontext.eautos_priv:
        ea = kontext.eautos_priv[0]
        await _upsert_investition_monatsdaten(
            db, ea.id, jahr, monat, {"km_gefahren": werte.eauto_km_legacy},
            ueberschreiben,
            source="manual:csv_import", writer="csv_wizard",
        )
    if werte.wallbox_lv_legacy is not None and werte.wallbox_lv_legacy > 0 and kontext.wallboxen_priv:
        wb = kontext.wallboxen_priv[0]
        await _upsert_investition_monatsdaten(
            db, wb.id, jahr, monat, {"ladevorgaenge": werte.wallbox_lv_legacy},
            ueberschreiben,
            source="manual:csv_import", writer="csv_wizard",
        )
