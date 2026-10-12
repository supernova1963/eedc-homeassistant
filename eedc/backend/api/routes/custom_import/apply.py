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
from backend.api.routes.data_import import ApplyMonthInput, _wallbox_verbrauch
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

from .analyze import _erkannte_geraete_spalten
from ._shared import (
    MappingConfig,
    MonatsWerte,
    ZeilenAbsturz,
    ZeilenPosition,
    ZuordnungsPlan,
    _parse_csv_rows,
    _parse_json_rows,
    _parse_number,
    _read_file_content,
    lies_monate,
    logger,
    plane_zuordnung,
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
    """Was jeder Monat braucht: Mapping, Plan (Zeilen-Kern), Investitionen der Anlage und ihre Pools."""

    config: MappingConfig
    plan: ZuordnungsPlan
    investitionen: list[Investition]
    pv_module: list[Investition]
    speicher: list[Investition]
    eautos_priv: list[Investition]
    wallboxen_priv: list[Investition]
    wallboxen: list[Investition]

    def parse_float(self, val: str) -> Optional[float]:
        return _parse_number(val, self.config.dezimalzeichen)


@dataclass
class _ImportStand:
    """Zähler und Meldungen über alle Monate; `importiert == 0` lässt die Verteil-Warnungen durch."""

    importiert: int = 0
    uebersprungen: int = 0
    fehler: list[str] = field(default_factory=list)
    warnungen: list[str] = field(default_factory=list)


@dataclass
class _GenerischeWerte:
    """Die generisch gemappten Werte eines Monats."""

    einspeisung: Optional[float]
    netzbezug: Optional[float]
    eigenverbrauch: Optional[float]
    pv_mapped: Optional[float]
    bat_ladung_mapped: Optional[float]
    bat_entladung_mapped: Optional[float]
    eauto_km_legacy: Optional[float]
    wallbox_lv_legacy: Optional[int]
    wallbox_ladung: Optional[float]
    wallbox_ladung_pv: Optional[float]


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
    3. Ausdrücklich zugeordnete `inv:<id>:<feld>`-Spalten → InvestitionMonatsdaten

    Gelesen wird über den Zeilen-Kern (`_shared.lies_monate`) — derselbe, den die Vorschau zeigt (N-706).
    """
    # Anlage prüfen
    anlage_result = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    anlage = anlage_result.scalar_one_or_none()
    if not anlage:
        raise HTTPException(404, f"Anlage {anlage_id} nicht gefunden.")

    config, selected = _lies_parameter(mapping_json, monate_json)
    headers, rows = await _lies_datei(file)
    kontext = await _lade_kontext(db, anlage_id, config, headers)
    stand = _ImportStand()
    # N-705: eine ignorierte `inv:`-Zuordnung (fremde/gelöschte Investition) wird gesagt, nicht still verworfen.
    stand.warnungen.extend(kontext.plan.warnungen)

    # ⛔ Kein Schutz-Zaehler auf diesem Weg (N-538, gemessen 20.09.2026): die Quelle
    # ist `manual:*`, und eine manuelle Quelle schreibt seit #251 (`f0b45bcc`)
    # UNBEDINGT — `provenance._decide` kennt fuer sie kein `rejected_lower_priority`.
    # Ohne Haken wird ein bestehender Monat oben uebersprungen, mit Haken gewinnt
    # der letzte Schreiber (MANUAL gegen MANUAL). Der Zaehler samt Hinweis
    # „X Felder geschuetzt" lief hier deshalb nie und ist entfernt; er lebt nur
    # im Portal-Import (`data_import.py`, Quelle `external:*`, geraetegebunden).

    eintraege, _ungueltig = lies_monate(rows, kontext.plan)

    # ⛔ **Äußerer SAVEPOINT — nicht weglassen.** Jeder Monat läuft in einem eigenen SAVEPOINT (N-704). SQLite
    # beginnt mit einem SAVEPOINT außerhalb einer Transaktion SELBST die Transaktion, und dessen RELEASE COMMITTET
    # sie (pysqlite öffnet vor einem SAVEPOINT kein BEGIN; bis hier liefen nur SELECTs). Ohne diese Klammer wäre
    # jeder Monat sofort dauerhaft, und ein späterer Abbruch mit 500 ließe die schon geschriebenen Monate stehen
    # (gemessen 12.10.2026 im GM-Fall B7). So rollt ein Fehler je Monat genau diesen Monat zurück, ein Abbruch
    # der Anfrage aber weiter alles — wie vor dem SAVEPOINT je Monat.
    async with db.begin_nested():
        for eintrag in eintraege:
            await _importiere_monat(db, anlage_id, eintrag, kontext, selected, ueberschreiben, stand)

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
# Die Schreibreihenfolge eines Monats bleibt die des Schleifenkörpers vor dem
# Schnitt — Investitions-Spalten (v09) → manuell gemappte `inv:`-Felder →
# PV-/Batterie-Verteilung → Monatsdaten → Legacy-E-Auto/Wallbox; Quelle überall
# `manual:csv_import`. Seit Päckchen G (12.10.2026) liest der Zeilen-Kern die
# Datei vorher einmal (`lies_monate`), und jeder Monat schreibt atomar.


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


async def _lies_datei(file: UploadFile) -> tuple[list[str], list[dict[str, str]]]:
    """Datei lesen und als JSON oder CSV in Kopfzeile und Zeilen zerlegen — 400 bei leerer Datei oder ohne
    Datenzeilen. Die Kopfzeile braucht die Erkennung der Geräte-Spalten (dieselbe wie in der Vorschau)."""
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

    return headers, rows


async def _lade_kontext(
    db: AsyncSession, anlage_id: int, config: MappingConfig, headers: list[str],
) -> _ImportKontext:
    """Investitionen der Anlage, ihre Pools und der Plan des Mappings — einmal je Import."""
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

    plan = plane_zuordnung(config, investitionen, _erkannte_geraete_spalten(headers, investitionen))

    return _ImportKontext(
        config=config,
        plan=plan,
        investitionen=investitionen,
        pv_module=pv_module,
        speicher=speicher,
        eautos_priv=eautos_priv,
        wallboxen_priv=wallboxen_priv,
        wallboxen=list(plan.wallboxen or []),
    )


async def _importiere_monat(
    db: AsyncSession,
    anlage_id: int,
    eintrag: "MonatsWerte | ZeilenAbsturz",
    kontext: _ImportKontext,
    selected: set[tuple[int, int]],
    ueberschreiben: bool,
    stand: _ImportStand,
) -> None:
    """Ein Monat (alle Zeilen dieses Monats) → eine Monatszeile samt Geräten.

    ⛔ **Atomar (N-704).** Bis 12.10.2026 blieb, was eine Zeile vor ihrem Fehler geschrieben hatte, in der Sitzung
    stehen (Gerätezeile ohne Monatszeile). Jetzt läuft jeder Monat in einem SAVEPOINT — ein Fehler rollt genau
    diesen Monat zurück und zählt in `stand.fehler`; die anderen Monate bleiben unberührt (dieselbe Bauform wie
    `scheduler.py`, N-656).
    """
    pos = eintrag.pos if isinstance(eintrag, ZeilenAbsturz) else ZeilenPosition(eintrag.jahr, eintrag.monat)
    try:
        if isinstance(eintrag, ZeilenAbsturz):
            raise eintrag.fehler

        # Nur ausgewählte Monate importieren
        if (eintrag.jahr, eintrag.monat) not in selected:
            return

        async with db.begin_nested():
            await _schreibe_monat(db, anlage_id, eintrag, kontext, ueberschreiben, stand)

    except Exception as e:
        logger.exception(f"Fehler bei Zeile (Jahr={pos.jahr}, Monat={pos.monat})")
        stand.fehler.append(f"{pos.jahr}/{pos.monat:02d}: {str(e)}")


async def _schreibe_monat(
    db: AsyncSession,
    anlage_id: int,
    mw: MonatsWerte,
    kontext: _ImportKontext,
    ueberschreiben: bool,
    stand: _ImportStand,
) -> None:
    """Den Monat schreiben — Bestand ohne Haken wird übersprungen, ein Fehler des Zeilen-Kerns ist der Zeilenfehler."""
    jahr, monat = mw.jahr, mw.monat

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

    # Was der Kern nicht schreiben kann (negativer Gerätewert, Wallbox-Menge ohne Wallbox, ein Stand in mehreren
    # Zeilen …), schreibt der Monat gar nicht.
    if mw.fehler:
        raise ValueError(mw.fehler[0])

    # ── Investitions-Spalten verarbeiten ──────────────────────────────
    # Liefert Summen: pv_erzeugung_sum, batterie_ladung_sum, batterie_entladung_sum
    summen = await _summen_aus_investitions_spalten(
        db, mw.geraete_zeile(kontext.plan), kontext, jahr, monat, ueberschreiben,
    )

    # ── Investitions-Felder aus manuellem Mapping (inv:ID:feld) ──────
    # z.B. {"Ertrag_Sued": "inv:42:pv_erzeugung_kwh"}
    inv_collected = _sammle_inv_felder(mw, kontext.plan)

    # Manuell gemappte Investitions-Felder speichern + Summen berechnen
    await _schreibe_inv_felder(db, inv_collected, kontext.plan, jahr, monat, ueberschreiben, summen)

    # ── Generische Felder aus Mapping ─────────────────────────────────
    werte = _generische_felder(mw)

    # ── PV-Erzeugung: Investitions-Summe hat Vorrang ──────────────────
    pv_erzeugung = await _pv_erzeugung(db, kontext, summen, werte, jahr, monat, ueberschreiben, stand)

    # ── Batterie: Investitions-Summe hat Vorrang ──────────────────────
    bat_ladung, bat_entladung = await _batterie(db, kontext, summen, werte, jahr, monat, ueberschreiben, stand)

    # ── Monatsdaten schreiben ─────────────────────────────────────────
    await _schreibe_monatsdaten(
        db, anlage_id, existing_md, jahr, monat, werte, pv_erzeugung, bat_ladung, bat_entladung,
    )

    await _schreibe_legacy_emob(db, kontext, werte, jahr, monat, ueberschreiben, stand)

    stand.importiert += 1


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


def _sammle_inv_felder(mw: MonatsWerte, plan: ZuordnungsPlan) -> dict[int, dict]:
    """Die gültigen `inv:<id>:<feld>`-Werte des Monats, je Investition gesammelt (Reihenfolge des Mappings).
    Gelesen, umgerechnet und geprüft hat sie der Zeilen-Kern; ungültige Zuordnungen kennt der Plan nicht (N-705)."""
    inv_collected: dict[int, dict] = {}
    for spalte, (inv_id, feld_name, _feld) in plan.inv_slots.items():
        if spalte not in mw.inv_werte:
            continue
        inv_collected.setdefault(inv_id, {})[feld_name] = mw.inv_werte[spalte]
    return inv_collected


async def _schreibe_inv_felder(
    db: AsyncSession, inv_collected: dict[int, dict], plan: ZuordnungsPlan,
    jahr: int, monat: int, ueberschreiben: bool, summen: dict,
) -> None:
    """Die gesammelten `inv:`-Felder je Investition schreiben und ihre Anteile am Monats-Aggregat addieren.

    ⛔ **Das Aggregat nur über `aggregiert_in` der Registry (N-702).** Bis 12.10.2026 summierte dieser Weg nach dem
    Feldnamen: jede `ladung_kwh` ging ins Batterie-Aggregat — auch die einer Wallbox oder eines E-Autos (Hinweis
    «Legacy-Daten» in der Monatsliste) —, und eine Geräte-Spalte, die zusätzlich auf ihren eigenen Slot gelegt war,
    zählte zweimal (PV 600 statt 300). Den zweiten Fall verhindert der Plan (v09 bekommt die Spalte dann nicht);
    hier entscheidet die Registry derselben Investition, wohin ein Wert zählt — dieselbe Regel wie v09.
    """
    aggregat = {
        (inv_id, feld_name): (feld or {}).get("aggregiert_in")
        for inv_id, feld_name, feld in plan.inv_slots.values()
    }
    for inv_id_int, verbrauch_daten in inv_collected.items():
        await _upsert_investition_monatsdaten(
            db, inv_id_int, jahr, monat, verbrauch_daten, ueberschreiben,
            source="manual:csv_import", writer="csv_wizard",
        )
        for feld_name, wert in verbrauch_daten.items():
            ziel = aggregat.get((inv_id_int, feld_name))
            if ziel and ziel in summen:
                summen[ziel] += wert


def _generische_felder(mw: MonatsWerte) -> _GenerischeWerte:
    """Die generisch gemappten Felder des Monats (ohne Jahr/Monat und ohne `inv:`-Slots)."""
    g = mw.generisch
    # Legacy-Top-Level-Targets, die nicht auf einer einzelnen Investition
    # liegen — werden weiter unten anteilig auf die jeweilige Pool-
    # Investition geschrieben (E-Auto: erstes nicht-dienstliches,
    # Wallbox: erste nicht-dienstliche).
    lv = g.get("wallbox_ladevorgaenge")
    return _GenerischeWerte(
        einspeisung=g.get("einspeisung_kwh"),
        netzbezug=g.get("netzbezug_kwh"),
        eigenverbrauch=g.get("eigenverbrauch_kwh"),
        pv_mapped=g.get("pv_erzeugung_kwh"),
        bat_ladung_mapped=g.get("batterie_ladung_kwh"),
        bat_entladung_mapped=g.get("batterie_entladung_kwh"),
        eauto_km_legacy=g.get("eauto_km_gefahren"),
        wallbox_lv_legacy=None if lv is None else int(lv),
        wallbox_ladung=g.get("wallbox_ladung_kwh"),
        wallbox_ladung_pv=g.get("wallbox_ladung_pv_kwh"),
    )


async def _pv_erzeugung(
    db: AsyncSession, kontext: _ImportKontext, summen: dict, werte: _GenerischeWerte,
    jahr: int, monat: int, ueberschreiben: bool, stand: _ImportStand,
) -> Optional[float]:
    """PV-Erzeugung des Monats: die Investitions-Summe hat Vorrang; ein generischer Wert wird auf die Module verteilt.

    N-707: eine ausdrücklich importierte **0 ist ein Messwert** und steht danach in der Monatszeile (wie die
    Batterie); eine leere Zelle bleibt leer. Bis 12.10.2026 wurde PV 0 zu NULL — der Daten-Checker meldete
    «PV-Erzeugung fehlt», das Cockpit zeigte «—».
    """
    pv_erzeugung: Optional[float] = None
    if summen["pv_erzeugung_sum"] > 0:
        # Individuelle PV-Modul-Werte vorhanden → Summe verwenden
        pv_erzeugung = summen["pv_erzeugung_sum"]
    elif werte.pv_mapped is not None and werte.pv_mapped >= 0:
        # Nur generischer Wert → auf PV-Module verteilen (wenn vorhanden; eine 0 verteilt nichts)
        if werte.pv_mapped > 0 and kontext.pv_module:
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
    die Speicher verteilt — bei Ladung ODER Entladung > 0, dieselbe Regel wie der Portal-Import (N-709;
    `data_import.py::_verteile_batterie`, Verteiler `_distribute_legacy_battery_to_storages`)."""
    bat_ladung: Optional[float] = None
    bat_entladung: Optional[float] = None
    if summen["batterie_ladung_sum"] > 0 or summen["batterie_entladung_sum"] > 0:
        bat_ladung = summen["batterie_ladung_sum"] or None
        bat_entladung = summen["batterie_entladung_sum"] or None
    else:
        lad, ent = werte.bat_ladung_mapped, werte.bat_entladung_mapped
        if ((lad or 0) > 0 or (ent or 0) > 0) and kontext.speicher:
            w = await _distribute_legacy_battery_to_storages(
                db, lad or 0, ent or 0,
                kontext.speicher, jahr, monat, ueberschreiben,
                source="manual:csv_import", writer="csv_wizard",
            )
            if stand.importiert == 0:
                stand.warnungen.extend(w)
        bat_ladung = lad
        bat_entladung = ent
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
    stand: _ImportStand,
) -> None:
    """E-Auto-km und die Anlagen-Wallbox-Werte ohne Investitions-Slot auf die erste nicht-dienstliche Investition."""
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
    lv = werte.wallbox_lv_legacy if (werte.wallbox_lv_legacy is not None and werte.wallbox_lv_legacy > 0) else None
    if werte.wallbox_ladung is not None and werte.wallbox_ladung > 0 and kontext.wallboxen:
        # N-703: die Wallbox-Menge wie im Portal-Import (`data_import._schreibe_wallbox`) — die Wallbox ist die
        # Quelle (Konzept Wallbox/E-Auto), die erste Wallbox der Anlage bekommt sie samt Ladevorgängen,
        # `ladung_netz_kwh` = Gesamt − PV über denselben Baustein (`data_import._wallbox_verbrauch`). Bis
        # 12.10.2026 hatte dieser Weg keinen Zweig dafür: der Import meldete Erfolg und schrieb nichts. Ohne
        # Wallbox ist der Monat ein Zeilenfehler (Zeilen-Kern), nie still verworfen.
        wb = kontext.wallboxen[0]
        if len(kontext.wallboxen) > 1:
            hinweis = (
                f"Mehrere Wallboxen vorhanden – Ladedaten wurden der ersten "
                f"Wallbox '{wb.bezeichnung or wb.typ}' zugeordnet."
            )
            if hinweis not in stand.warnungen:
                stand.warnungen.append(hinweis)
        await _upsert_investition_monatsdaten(
            db, wb.id, jahr, monat,
            _wallbox_verbrauch(ApplyMonthInput(
                jahr=jahr, monat=monat,
                wallbox_ladung_kwh=werte.wallbox_ladung,
                wallbox_ladung_pv_kwh=werte.wallbox_ladung_pv,
                wallbox_ladevorgaenge=lv,
            )),
            ueberschreiben,
            source="manual:csv_import", writer="csv_wizard",
        )
    elif lv is not None and kontext.wallboxen_priv:
        wb = kontext.wallboxen_priv[0]
        await _upsert_investition_monatsdaten(
            db, wb.id, jahr, monat, {"ladevorgaenge": lv},
            ueberschreiben,
            source="manual:csv_import", writer="csv_wizard",
        )
