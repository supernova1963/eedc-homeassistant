"""
Investitionen API Routes

CRUD Endpoints für Investitionen (E-Auto, Wärmepumpe, Speicher, etc.).

Seit 18.09.2026 (Vorlage 5 des Refactorings grosser Dateien, reiner Umzug) liegen die Schemas in
``schemas.py`` und das ROI-Dashboard samt Gruppierung und Kennwert-Aufloesern in ``roi.py``; dieses Modul
behaelt die CRUD-Routen, haengt den ROI-Router nach ihnen ein und exportiert die bisherigen Namen weiter.
"""

import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.orm.attributes import flag_modified
from pydantic import BaseModel
from backend.core.exceptions import not_found
from backend.core.field_definitions import innengeraet_id_von_feld
from backend.services.datenquellen_mapping_sync import inv_feld_der_investition
from backend.services.activity_service import log_activity
from backend.core.zahlenformat import fmt_datum
from backend.api.deps import get_db
from backend.models.investition import (
    Investition,
    InvestitionTyp,
    ERLAUBTE_PARENT_TYPEN,
    PARENT_PFLICHT_TYPEN,
    TYP_LABELS as _TYP_LABEL,
)
from backend.utils.investition_filter import aktiv_jetzt, sort_investitionen_nach_typ
from backend.models.anlage import Anlage
from backend.core.investition_parameter import lade_innengeraete
from backend.api.routes.investitionen.schemas import (  # noqa: F401 — Re-Export (dashboards.py, aussichten/finanz_zerlegung.py, finanzbericht.py, Tests)
    InvestitionBase,
    InvestitionCreate,
    InvestitionUpdate,
    InvestitionResponse,
)
from backend.api.routes.investitionen.roi import (  # noqa: F401 — Re-Export (dashboards.py, aussichten/finanz_zerlegung.py, finanzbericht.py, Tests)
    _gruppiere_investitionen,
    ROIKomponente,
    ROIBerechnung,
    AmortisationsVerlaufJahr,
    ROIDashboardResponse,
    get_roi_dashboard,
)
from backend.api.routes.investitionen.roi import router as _roi_router

logger = logging.getLogger(__name__)
router = APIRouter()


# v3.25.0: Phantom-Endpoint /typen + InvestitionTypInfo + parameter_schema entfernt.
# Niemand hat das Schema im Frontend gelesen (useInvestitionTypen war exportiert, aber
# nirgends aufgerufen), und der Schema-Inhalt war historisch von Form/Wizard und
# Backend-Reads auseinandergedriftet — siehe docs/archive/INVENTUR-INVESTITIONS-PARAMETER.md.
# Single Source of Truth ist jetzt:
#   - Frontend: eedc/frontend/src/lib/investitionParameter.ts
#   - Backend:  eedc/backend/core/investition_parameter.py


class ParentOption(BaseModel):
    """Verfügbare Parent-Investition."""
    id: int
    bezeichnung: str
    typ: str
    required: bool = False

@router.get("/parent-options/{anlage_id}", response_model=dict[str, list[ParentOption]])
async def get_parent_options(
    anlage_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Gibt verfügbare Parent-Optionen für jeden Typ zurück.

    Gebaut aus `ERLAUBTE_PARENT_TYPEN`/`PARENT_PFLICHT_TYPEN`
    (`models/investition.py`) — derselben SoT, gegen die
    `_validate_parent_child` prüft. Bis 2026-07-31 zählte diese Funktion
    ausschließlich Wechselrichter auf und behauptete damit, ein Speicher könne
    keinem Balkonkraftwerk zugeordnet werden — im Widerspruch zur Validierung
    UND zum Formular (BKW mit Akku ist genau der Fall, für den es die
    Zuordnung gibt).

    Returns:
        dict: Typ -> Liste der möglichen Parents (leer, wo es keine gibt)

    Beispiel:
        {
            "pv-module": [{"id": 1, "bezeichnung": "Fronius GEN24", "typ": "wechselrichter", "required": true}],
            "speicher": [{"id": 1, "bezeichnung": "Fronius GEN24", "typ": "wechselrichter", "required": false},
                         {"id": 9, "bezeichnung": "Balkon Süd", "typ": "balkonkraftwerk", "required": false}]
        }
    """
    benoetigte_typen = {t for typen in ERLAUBTE_PARENT_TYPEN.values() for t in typen}
    kandidaten = (await db.execute(
        select(Investition)
        .where(Investition.anlage_id == anlage_id)
        .where(Investition.typ.in_(benoetigte_typen))
        .where(aktiv_jetzt())
        .order_by(Investition.bezeichnung)
    )).scalars().all()

    optionen: dict[str, list[ParentOption]] = {t.value: [] for t in InvestitionTyp}
    for typ, erlaubte in ERLAUBTE_PARENT_TYPEN.items():
        passend = [k for k in kandidaten if k.typ in erlaubte]
        # `required` ist keine Eigenschaft des Typs allein: Pflicht wird die
        # Zuordnung erst, wenn es überhaupt einen möglichen Parent gibt
        # (sonst bliebe ein Altbestands-Modul unspeicherbar) — dieselbe
        # Bedingung wie in `_validate_parent_child`.
        pflicht = typ in PARENT_PFLICHT_TYPEN and len(passend) > 0
        optionen[typ] = [
            ParentOption(id=k.id, bezeichnung=k.bezeichnung, typ=k.typ, required=pflicht)
            for k in passend
        ]
    return optionen

@router.get("/", response_model=list[InvestitionResponse])
async def list_investitionen(
    anlage_id: Optional[int] = Query(None, description="Filter nach Anlage"),
    typ: Optional[str] = Query(None, description="Filter nach Typ"),
    aktiv: Optional[bool] = Query(None, description="Filter nach Status"),
    db: AsyncSession = Depends(get_db)
):
    """
    Gibt Investitionen zurück, optional gefiltert.

    Args:
        anlage_id: Optional - nur Investitionen dieser Anlage
        typ: Optional - nur dieser Investitionstyp
        aktiv: Optional - nur aktive/inaktive

    Returns:
        list[InvestitionResponse]: Liste der Investitionen
    """
    query = select(Investition)

    if anlage_id:
        query = query.where(Investition.anlage_id == anlage_id)
    if typ:
        query = query.where(Investition.typ == typ)
    if aktiv is not None:
        query = query.where(Investition.aktiv == aktiv)

    # Kanonische Typ-Reihenfolge (Fundament P4 / F7) statt alphabetisch.
    query = query.order_by(Investition.bezeichnung)

    # N-266/E5: Kinder MITLADEN, damit `leistung_kwp_effektiv` an einem
    # Balkonkraftwerk mit Modul-Kindern deren Σ ausweist statt der eigenen,
    # inzwischen gesperrten Pflege (`get_bkw_kwp`). `selectinload` statt eines
    # Lazy-Zugriffs: Letzterer läuft in async SQLAlchemy auf `MissingGreenlet`,
    # und ohne geladene Beziehung schweigt der Helper bewusst.
    query = query.options(selectinload(Investition.children))

    result = await db.execute(query)
    return sort_investitionen_nach_typ(result.scalars().all())

@router.get("/{investition_id}", response_model=InvestitionResponse)
async def get_investition(investition_id: int, db: AsyncSession = Depends(get_db)):
    """
    Gibt eine einzelne Investition zurück.

    Args:
        investition_id: ID der Investition

    Returns:
        InvestitionResponse: Die Investition

    Raises:
        404: Nicht gefunden
    """
    result = await db.execute(
        select(Investition)
        .where(Investition.id == investition_id)
        # N-266/E5 — wie in `list_investitionen`: ohne geladene Kinder weist
        # `leistung_kwp_effektiv` an einem abtretenden BKW die eigene, gesperrte
        # Pflege aus statt der Σ seiner Module.
        .options(selectinload(Investition.children))
    )
    inv = result.scalar_one_or_none()

    if not inv:
        raise not_found("Investition")

    return inv

@router.post("/", response_model=InvestitionResponse, status_code=status.HTTP_201_CREATED)
async def create_investition(data: InvestitionCreate, db: AsyncSession = Depends(get_db, scope="function")):
    """
    Erstellt eine neue Investition.

    Args:
        data: Investitions-Daten

    Returns:
        InvestitionResponse: Die erstellte Investition

    Raises:
        404: Anlage nicht gefunden
        400: Ungültiger Typ oder fehlende Parent-Zuordnung
    """
    # Anlage prüfen
    anlage_result = await db.execute(select(Anlage).where(Anlage.id == data.anlage_id))
    anlage = anlage_result.scalar_one_or_none()
    if not anlage:
        raise not_found("Anlage")

    # Typ validieren
    valid_types = [t.value for t in InvestitionTyp]
    if data.typ not in valid_types:
        raise HTTPException(
            status_code=400,
            detail=f"Ungültiger Typ. Erlaubt: {valid_types}"
        )

    # Parent-Child Validierung (v0.9)
    await _validate_parent_child(db, data.anlage_id, data.typ, data.parent_investition_id)

    inv = Investition(**data.model_dump())
    db.add(inv)
    await db.flush()
    await db.refresh(inv)
    # N-560: in DIESER Sitzung (N-532) — die Zeile geht mit dem Commit der Route.
    await log_activity(
        kategorie=KATEGORIE_KOMPONENTEN,
        aktion="Komponente angelegt",
        details=_komponente_klartext(anlage, inv),
        details_json={"investition_id": inv.id, "typ": inv.typ},
        anlage_id=inv.anlage_id,
        db=db,
    )
    return inv


#: N-560: Kategorie des Aktivitätsprotokolls für Anlegen/Ändern/Löschen einer
#: Komponente. Keine der vorhandenen passt — `sensor_mapping` ist die Zuordnung
#: einer Datenquelle, `backup_import` die Übernahme einer ganzen Anlage.
KATEGORIE_KOMPONENTEN = "investitionen"

#: Welche Änderungen einer Komponente eine Protokollzeile wert sind (N-560): die,
#: die entscheiden, OB und AB WANN sie in Auswertungen zählt. Parameter und
#: Kosten ändern Zahlen, nicht die Zugehörigkeit — sie stehen nicht im Protokoll.
_PROTOKOLL_FELDER = {
    "typ": "Typ",
    "aktiv": "Aktiv",
    "anschaffungsdatum": "Anschaffung",
    "stilllegungsdatum": "Stilllegung",
}


def _komponente_klartext(anlage, inv) -> str:
    """„Anlage · Typ · Bezeichnung" für das Aktivitätsprotokoll (N-560)."""
    name = getattr(anlage, "anlagenname", None) or f"Anlage {inv.anlage_id}"
    return f"{name} · {_TYP_LABEL.get(inv.typ, inv.typ)} · {inv.bezeichnung}"


def _wert_klartext(feld: str, wert) -> str:
    if feld == "typ":
        return _TYP_LABEL.get(wert, str(wert))
    if feld == "aktiv":
        return "ja" if wert else "nein"
    return fmt_datum(wert, leer="—")

async def _validate_parent_child(
    db: AsyncSession,
    anlage_id: int,
    typ: str,
    parent_id: Optional[int],
    exclude_id: Optional[int] = None
):
    """
    Validiert Parent-Child Beziehungen für Investitionen.

    Die erlaubten Kombinationen stehen NICHT hier, sondern in der SoT
    `models/investition.py::ERLAUBTE_PARENT_TYPEN` / `PARENT_PFLICHT_TYPEN` —
    dieselbe Quelle, aus der `get_parent_options` seine Liste baut und die das
    Client-Pendant spiegelt. Bis 2026-07-31 gab es drei uneinige Kopien.

    Regeln:
    - PV-Module MÜSSEN einem Wechselrichter zugeordnet sein (sofern einer existiert)
    - Speicher KÖNNEN optional einem Wechselrichter (Hybrid-WR) oder einem
      Balkonkraftwerk (BKW mit Akku) zugeordnet sein
    - Andere Typen haben keinen Parent
    """
    erlaubt = ERLAUBTE_PARENT_TYPEN.get(typ, ())

    # Typen ohne Parent-Beziehung: jede Zuordnung ist ein Fehler.
    if not erlaubt:
        if parent_id:
            raise HTTPException(
                status_code=400,
                detail=f"Investitionen vom Typ '{typ}' können keinem Parent zugeordnet werden"
            )
        return

    if not parent_id:
        if typ not in PARENT_PFLICHT_TYPEN:
            return
        # Pflicht — aber nur, wenn es überhaupt einen möglichen Parent gibt.
        # Ohne einen bleibt die Investition parentlos (Migration/Altbestand).
        moegliche = (await db.execute(
            select(Investition)
            .where(Investition.anlage_id == anlage_id)
            .where(Investition.typ.in_(erlaubt))
        )).scalars().all()
        if moegliche:
            raise HTTPException(
                status_code=400,
                detail=f"{_TYP_LABEL.get(typ, typ)} müssen zugeordnet werden. "
                       f"Verfügbar: {[m.bezeichnung for m in moegliche]}"
            )
        return

    parent = (await db.execute(
        select(Investition).where(Investition.id == parent_id)
    )).scalar_one_or_none()
    if not parent:
        raise not_found("Parent-Investition")
    if parent.typ not in erlaubt:
        erlaubt_labels = " oder ".join(_TYP_LABEL.get(t, t) for t in erlaubt)
        raise HTTPException(
            status_code=400,
            detail=f"{_TYP_LABEL.get(typ, typ)} können nur {erlaubt_labels} "
                   f"zugeordnet werden, nicht '{parent.typ}'"
        )
    if parent.anlage_id != anlage_id:
        raise HTTPException(
            status_code=400,
            detail="Parent-Investition gehört zu einer anderen Anlage"
        )

@router.put("/{investition_id}", response_model=InvestitionResponse)
async def update_investition(
    investition_id: int,
    data: InvestitionUpdate,
    db: AsyncSession = Depends(get_db, scope="function")
):
    """
    Aktualisiert eine Investition.

    Args:
        investition_id: ID der Investition
        data: Zu aktualisierende Felder

    Returns:
        InvestitionResponse: Die aktualisierte Investition

    Raises:
        404: Nicht gefunden
        400: Ungültige Parent-Zuordnung
    """
    result = await db.execute(select(Investition).where(Investition.id == investition_id))
    inv = result.scalar_one_or_none()

    if not inv:
        raise not_found("Investition")

    update_data = data.model_dump(exclude_unset=True)

    # Parent-Child Validierung wenn parent_investition_id geändert wird
    if 'parent_investition_id' in update_data:
        await _validate_parent_child(
            db,
            inv.anlage_id,
            inv.typ,
            update_data['parent_investition_id'],
            exclude_id=investition_id
        )

    # #263 — Innengeräte-Zuordnungen aufräumen, BEVOR der neue Parameter steht.
    # Sonst bliebe die Zuordnung eines gelöschten Innengeräts im
    # `sensor_mapping` liegen: auf der Datenquellen-Fläche unsichtbar (das Feld
    # wird nicht mehr erzeugt) und damit nicht mehr entfernbar — dieselbe
    # Falle, vor der `get_alle_felder_fuer_investition` warnt. Schlimmer noch:
    # ihr Wert liefe weiter in die Auswertung.
    if inv.typ == "waermepumpe" and "parameter" in update_data:
        await _raeume_innengeraete_zuordnungen(
            db, inv, neu_parameter=update_data.get("parameter"),
        )

    # N-560: alt → neu der protokollwürdigen Felder, bevor `setattr` sie überschreibt.
    aenderungen = [
        f"{label}: {_wert_klartext(feld, getattr(inv, feld))} → {_wert_klartext(feld, update_data[feld])}"
        for feld, label in _PROTOKOLL_FELDER.items()
        if feld in update_data and update_data[feld] != getattr(inv, feld)
    ]

    for field, value in update_data.items():
        setattr(inv, field, value)

    await db.flush()
    await db.refresh(inv)
    if aenderungen:
        anlage = (await db.execute(select(Anlage).where(Anlage.id == inv.anlage_id))).scalar_one_or_none()
        await log_activity(
            kategorie=KATEGORIE_KOMPONENTEN,
            aktion="Komponente geändert",
            details=f"{_komponente_klartext(anlage, inv)} · " + " · ".join(aenderungen),
            details_json={"investition_id": inv.id, "felder": [
                f for f in _PROTOKOLL_FELDER if f in update_data]},
            anlage_id=inv.anlage_id,
            db=db,
        )
    return inv

async def _raeume_innengeraete_zuordnungen(
    db: AsyncSession, inv: Investition, neu_parameter,
) -> None:
    """Entfernt die Sensor-Zuordnungen entfallener Innengeräte (#263).

    **Warum überhaupt aufräumen und nicht nur beim Lesen filtern.** Beides:
    Die Auswertung geht ohnehin nur über die Geräte der Liste — aber eine
    Zuordnung, die niemand mehr sieht und niemand mehr löschen kann, ist ein
    Rest, der beim nächsten Anlegen eines Innengeräts wieder auftauchen würde,
    wenn jemand die ID doch einmal wiederverwendet. Deshalb wird sie hier
    entfernt, wo die alte und die neue Liste beide bekannt sind.

    ⚠ **Nur entfallene IDs.** Wer nur eine Bezeichnung ändert, verliert nichts.
    """
    alt_ids = {g["id"] for g in lade_innengeraete(inv.parameter)}
    neu_ids = {g["id"] for g in lade_innengeraete(neu_parameter)}
    entfallen = alt_ids - neu_ids
    if not entfallen:
        return

    anlage = (await db.execute(
        select(Anlage).where(Anlage.id == inv.anlage_id)
    )).scalar_one_or_none()
    if not anlage or not anlage.sensor_mapping:
        return

    def _betroffen(key: str) -> bool:
        gid = innengeraet_id_von_feld(key)
        return gid is not None and gid in entfallen

    geaendert = False
    eintrag = (anlage.sensor_mapping.get("investitionen") or {}).get(str(inv.id))
    if isinstance(eintrag, dict):
        for abschnitt in ("live", "live_invert", "felder"):
            werte = eintrag.get(abschnitt)
            if not isinstance(werte, dict):
                continue
            for key in [k for k in werte if _betroffen(k)]:
                del werte[key]
                geaendert = True

    # Die feld-zentrischen Ablagen der Fläche (`quellen`, `invertieren`) tragen
    # dieselben Zuordnungen unter der Feld-ID — sie gehören mit aufgeräumt, sonst
    # holt der Read-Through (`snapshot/keys.extract_quellen_energy`) sie zurück.
    # ⚠ Kein früher Ausstieg ohne klassischen Eintrag: eine MQTT-Zuordnung steht
    # NUR in `quellen`.
    feld_geaendert, gateway_ids = _raeume_feld_ablagen(anlage.sensor_mapping, inv.id, _betroffen)
    if feld_geaendert:
        geaendert = True

    if geaendert:
        flag_modified(anlage, "sensor_mapping")
    # N-561: die Gateway-Zeilen der entfallenen Felder gehen mit — sonst abonniert
    # der Gateway ihr Topic weiter.
    await _entferne_gateway_zeilen(db, gateway_ids)


def _raeume_feld_ablagen(mapping: dict, inv_id: int, betroffen) -> tuple[bool, list[int]]:
    """Entfernt aus `quellen` und `invertieren` die Feld-IDs dieser Investition,
    deren Feld-Key ``betroffen`` ist (N-559). In-place.

    Returns:
        ``(geändert, gateway_ids)`` — die `mapping_id` jeder entfernten
        Gateway-Zuordnung, damit der Aufrufer ihre Zeile löscht (N-561).

    N-559: Bis 25.09.2026 suchte das Aufräumen nach ``inv:<id>:<feld>`` — das ist
    der Snapshot-Schlüssel, den `extract_quellen_energy` erst beim Lesen bildet,
    nicht die gespeicherte Feld-ID (``inv_energy_<id>_<feld>`` /
    ``inv_live_<id>_<key>``). Es fand nie etwas; gemessen blieben nach dem
    Entfernen eines Innengeräts alle elf seiner `quellen`-Einträge liegen. Die Form
    kommt jetzt aus `datenquellen_mapping_sync` — derselben Quelle wie die Fläche.
    """
    geaendert = False
    gateway_ids: list[int] = []
    for ablage in ("quellen", "invertieren"):
        werte = mapping.get(ablage)
        if not isinstance(werte, dict):
            continue
        for fid in list(werte):
            feld = inv_feld_der_investition(fid, inv_id)
            if feld is not None and betroffen(feld):
                eintrag = werte.pop(fid)
                if isinstance(eintrag, dict) and eintrag.get("mapping_id") is not None:
                    gateway_ids.append(eintrag["mapping_id"])
                geaendert = True
    return geaendert, gateway_ids


async def _entferne_gateway_zeilen(db: AsyncSession, gateway_ids: list[int]) -> list[str]:
    """Löscht die Gateway-Zeilen und lädt den Gateway neu (N-561).

    Derselbe Löschweg wie das Wegschalten in `datenquellen.set_feld_quelle`
    (`mqtt_gateway.entferne_gateway_zeile`), derselbe Reload (`_reload_gateway`).
    Der Reload liest in DIESER Sitzung und sieht die Löschung schon vor dem
    Commit — dieselbe Reihenfolge wie `DELETE /mqtt/gateway/mappings/{id}`.
    Gibt die Topics der gelöschten Zeilen zurück (für das Protokoll).
    """
    if not gateway_ids:
        return []
    from backend.api.routes.mqtt_gateway import _reload_gateway, entferne_gateway_zeile

    topics = []
    for mid in gateway_ids:
        row = await entferne_gateway_zeile(db, mid)
        if row is not None:
            topics.append(row.quell_topic)
    if topics:
        try:
            await _reload_gateway(db)
        except Exception:  # Reload ist best-effort — wie in `set_feld_quelle`.
            logger.warning("Gateway-Reload nach dem Aufräumen fehlgeschlagen", exc_info=True)
    return topics

@router.delete("/{investition_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_investition(investition_id: int, db: AsyncSession = Depends(get_db, scope="function")):
    """
    Löscht eine Investition.

    Args:
        investition_id: ID der Investition

    Raises:
        404: Nicht gefunden
    """
    result = await db.execute(select(Investition).where(Investition.id == investition_id))
    inv = result.scalar_one_or_none()

    if not inv:
        raise not_found("Investition")

    # sensor_mapping der Anlage aufräumen (verwaiste Einträge vermeiden)
    anlage_result = await db.execute(select(Anlage).where(Anlage.id == inv.anlage_id))
    anlage = anlage_result.scalar_one_or_none()
    gateway_topics: list[str] = []
    if anlage and anlage.sensor_mapping:
        geaendert = False
        inv_mapping = anlage.sensor_mapping.get("investitionen", {})
        if str(investition_id) in inv_mapping:
            del inv_mapping[str(investition_id)]
            geaendert = True
        # N-559: auch die feld-zentrischen Ablagen der Fläche — sonst bleiben
        # `quellen`/`invertieren` dieser ID liegen und gelten für die nächste
        # Investition, die dieselbe ID bekommt (§13: SQLite vergibt sie wieder).
        feld_geaendert, gateway_ids = _raeume_feld_ablagen(
            anlage.sensor_mapping, investition_id, lambda _feld: True,
        )
        if feld_geaendert:
            geaendert = True
        if geaendert:
            flag_modified(anlage, "sensor_mapping")
        # N-561: und die Gateway-Zeilen dieser Zuordnungen, samt Reload.
        gateway_topics = await _entferne_gateway_zeilen(db, gateway_ids)

    # N-560: in DIESER Sitzung (N-532), vor dem Löschen — danach gibt es die
    # Bezeichnung nicht mehr.
    await log_activity(
        kategorie=KATEGORIE_KOMPONENTEN,
        aktion="Komponente gelöscht",
        details=_komponente_klartext(anlage, inv) + (
            f" · MQTT-Gateway-Zuordnung entfernt ({', '.join(gateway_topics)})"
            if gateway_topics else ""
        ),
        details_json={"investition_id": inv.id, "typ": inv.typ},
        anlage_id=inv.anlage_id,
        db=db,
    )

    await db.delete(inv)


# Der ROI-Endpunkt (`roi.py`) haengt NACH den CRUD-Routen — wie vor dem Umzug.
router.include_router(_roi_router)
