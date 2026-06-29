"""
Energie-Profil API — Repair- / Write-Endpoints.

Seit Etappe 3d Päckchen 4 sind alle Repair-Endpoints Wrapper über den
`services.repair_orchestrator`. Der Wrapper ruft intern
`orchestrator.plan(req)` + `orchestrator.execute(plan_id)` und mapt
die alten Response-Felder, damit Bestand-Frontends nicht brechen.

Konzept: docs/KONZEPT-DATENPIPELINE.md Sektion 5.2.

Endpunkt-Inventar:

  DELETE /api/energie-profil/{anlage_id}/rohdaten — Löscht Daten einer Anlage
  DELETE /api/energie-profil/rohdaten — Löscht Daten aller Anlagen
  POST   /api/energie-profil/reaggregate-heute — Triggert Aggregation heute
  POST   /api/energie-profil/{anlage_id}/reaggregate-tag — Reaggregate eines Tages
  POST   /api/energie-profil/{anlage_id}/reaggregate-bereich — Reaggregate mehrerer Tage (max 31)
  POST   /api/energie-profil/{anlage_id}/vollbackfill — Lückenfüller HA-LTS (additiv)
  POST   /api/energie-profil/{anlage_id}/kraftstoffpreis-backfill[/tages|/monats]

DELETE-Endpoints bleiben direkt (Bulk-Delete, kein Plan-Mehrwert; Konzept
Sektion 5.2: "DELETE bleibt direkt, schreibt aber Audit-Log").
"""

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.exceptions import not_found
from backend.api.deps import get_db
from backend.core.berechnungen import (
    summe_pv_bkw_kwh,
    pruefe_tep_komponenten_intern_konsistenz,
)
from backend.models.anlage import Anlage
from backend.models.tages_energie_profil import TagesEnergieProfil, TagesZusammenfassung
from backend.services import repair_orchestrator as orch
from backend.services.repair_orchestrator import (
    RepairOperationRequest,
    RepairOperationType,
)

from ._shared import logger

router = APIRouter()


async def _run_via_orchestrator(
    db: AsyncSession,
    *,
    anlage_id: Optional[int],
    operation: RepairOperationType,
    params: dict,
) -> dict:
    """Wrapper-Helper: plan() + execute() + heave die alten Response-Felder.

    Wirft HTTPException bei domänen-spezifischen Fehlern (404 wenn Anlage
    fehlt, 400 bei ValueError, 500 bei sonstigen). Damit verhalten sich
    die Wrapper wie die alten Direkt-Endpoints.
    """
    try:
        req = RepairOperationRequest(
            anlage_id=anlage_id, operation=operation, params=params,
        )
        plan_obj = await orch.plan(req, db)
        result = await orch.execute(plan_obj.plan_id, db)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        # Operations werfen RuntimeError für "logisch fehlgeschlagen"
        # (z. B. ha_unavailable). Mappt auf 503/500 je nach Wortlaut.
        msg = str(e)
        status = 503 if "ha" in msg.lower() and "unavailable" in msg.lower() else 500
        raise HTTPException(status_code=status, detail=msg)
    except NotImplementedError as e:
        raise HTTPException(status_code=501, detail=str(e))

    return result.operation_summary


@router.delete("/{anlage_id}/rohdaten")
async def delete_rohdaten(
    anlage_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Löscht alle TagesEnergieProfil- und TagesZusammenfassung-Daten einer Anlage.

    Bleibt direkter Pfad (Konzept Sektion 5.2 — Bulk-Delete kein
    Orchestrator-Bedarf). Der Scheduler schreibt ab dem nächsten Lauf
    (alle 15 Min) neue, korrekte Daten. Monatsdaten bleiben erhalten.
    """
    result = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    anlage = result.scalar_one_or_none()
    if not anlage:
        raise not_found("Anlage")

    del_stunden = await db.execute(
        delete(TagesEnergieProfil).where(TagesEnergieProfil.anlage_id == anlage_id)
    )
    del_tage = await db.execute(
        delete(TagesZusammenfassung).where(TagesZusammenfassung.anlage_id == anlage_id)
    )
    # Flag zurücksetzen, damit der nächste Monatsabschluss den Auto-Vollbackfill
    # aus HA Statistics erneut anstößt
    anlage.vollbackfill_durchgefuehrt = False
    await db.commit()

    return {
        "geloescht_stundenwerte": del_stunden.rowcount,
        "geloescht_tagessummen": del_tage.rowcount,
        "hinweis": "Scheduler schreibt ab dem nächsten Lauf (max. 15 Min) neue Daten. Monatsdaten bleiben erhalten.",
    }


@router.post("/reaggregate-heute")
async def reaggregate_heute(db: AsyncSession = Depends(get_db)):
    """Triggert sofortige Neu-Aggregation des heutigen Tages für alle Anlagen.

    Wrapper über RepairOperationType.REAGGREGATE_TODAY. System-weite
    Operation ohne anlage_id.
    """
    summary = await _run_via_orchestrator(
        db,
        anlage_id=None,
        operation=RepairOperationType.REAGGREGATE_TODAY,
        params={},
    )
    return {"status": "ok", **summary}


@router.post("/{anlage_id}/reaggregate-tag")
async def reaggregate_tag(
    anlage_id: int,
    datum: date = Query(..., description="Tag, der neu aggregiert werden soll"),
    mit_resnap: bool = Query(
        True,
        description="Vor dem Aggregat die SensorSnapshots des Tages frisch aus HA-Statistics ziehen "
                    "(repariert Counter-Spikes, z. B. nach Update-Restarts). Default an.",
    ),
    db: AsyncSession = Depends(get_db),
):
    """
    Aggregiert einen einzelnen Tag für eine Anlage neu.

    Wrapper über RepairOperationType.REAGGREGATE_DAY. Verhalten identisch
    zur Vor-3d-Direkt-Variante: mit_resnap=True (Default) zieht vorher
    Snapshots aus HA-LTS für Vortag-23:00 + Folgetag-00:00 Boundaries,
    danach `aggregate_day(source=Source.MANUAL_REPAIR)`.

    Response enthält die PV-Tagessumme vor und nach dem Lauf, damit das
    Frontend dem Anwender konkret zeigen kann, was sich geändert hat
    (oder eben nicht — siehe Drift-Knopf-Diagnose im Daten-Checker).
    """
    pv_kwh_alt = await _pv_tagessumme(db, anlage_id, datum)
    summary = await _run_via_orchestrator(
        db,
        anlage_id=anlage_id,
        operation=RepairOperationType.REAGGREGATE_DAY,
        params={"datum": datum.isoformat(), "mit_resnap": mit_resnap},
    )
    pv_kwh_neu = await _pv_tagessumme(db, anlage_id, datum)
    stunden_mit_messdaten = await _stunden_mit_messdaten(db, anlage_id, datum)
    return {
        "status": "ok",
        "datum": summary.get("datum", datum.isoformat()),
        "stunden_verfuegbar": summary.get("stunden_verfuegbar"),
        "stunden_mit_messdaten": stunden_mit_messdaten,
        "pv_kwh_alt": pv_kwh_alt,
        "pv_kwh_neu": pv_kwh_neu,
    }


async def _stunden_mit_messdaten(
    db: AsyncSession, anlage_id: int, datum: date,
) -> int:
    """Zählt TEP-Stunden des Tages mit mindestens einem nicht-NULL-Leistungswert.

    Im Orchestrator-Refactor 2026-05-10 (Commit 17db2350) ging das Feld
    aus dem alten /reaggregate-tag-Endpoint verloren — das Frontend
    (`ReaggregatePreviewModal` → `handlePreviewApplied`) wertet `> 0` aus
    und zeigte dadurch dauerhaft die „0/24 Stunden mit Messdaten —
    keine Snapshots in der DB und HA-Statistics nicht erreichbar"-Warnung,
    auch wenn die Reaggregation tatsächlich erfolgreich war (#290 detLAN).

    `stunden_verfuegbar` aus `TagesZusammenfassung` zählt alle 24 Slots
    auch wenn alle Werte NULL sind (synthetisches MQTT-Energy-Setup) —
    dieser Wert hier ist der ehrlichere Erfolgsindikator.
    """
    from sqlalchemy import or_
    result = await db.execute(
        select(func.count(TagesEnergieProfil.id)).where(
            TagesEnergieProfil.anlage_id == anlage_id,
            TagesEnergieProfil.datum == datum,
            or_(
                TagesEnergieProfil.pv_kw.is_not(None),
                TagesEnergieProfil.verbrauch_kw.is_not(None),
                TagesEnergieProfil.einspeisung_kw.is_not(None),
                TagesEnergieProfil.netzbezug_kw.is_not(None),
                TagesEnergieProfil.batterie_kw.is_not(None),
                TagesEnergieProfil.waermepumpe_kw.is_not(None),
                TagesEnergieProfil.wallbox_kw.is_not(None),
            ),
        )
    )
    return int(result.scalar_one() or 0)


async def _pv_tagessumme(
    db: AsyncSession, anlage_id: int, datum: date,
) -> Optional[float]:
    """Liefert die PV-Tagessumme (Σ pv_* + bkw_* aus komponenten_kwh) für
    einen Tag. None, wenn keine TagesZusammenfassung existiert.

    Nutzt dieselbe Aggregationslogik wie _check_datenquelle_drift —
    damit ist das Frontend-Δ konsistent mit der Drift-Anzeige.
    """
    tz_result = await db.execute(
        select(TagesZusammenfassung).where(
            TagesZusammenfassung.anlage_id == anlage_id,
            TagesZusammenfassung.datum == datum,
        )
    )
    tz = tz_result.scalar_one_or_none()
    if tz is None or not tz.komponenten_kwh:
        return None
    return round(summe_pv_bkw_kwh(tz.komponenten_kwh), 2)


@router.post("/{anlage_id}/reaggregate-bereich")
async def reaggregate_bereich(
    anlage_id: int,
    von: date = Query(..., description="Startdatum des Bereichs (inkl.)"),
    bis: date = Query(..., description="Enddatum des Bereichs (inkl., muss vor heute liegen)"),
    mit_resnap: bool = Query(
        True,
        description="Vor jeder Tages-Aggregation die SensorSnapshots des Tages frisch aus "
                    "HA-Statistics ziehen. Default an.",
    ),
    db: AsyncSession = Depends(get_db),
):
    """Aggregiert mehrere Tage seriell neu (max. REAGGREGATE_RANGE_MAX_DAYS=31).

    Wrapper über RepairOperationType.REAGGREGATE_RANGE. Pro Tag erfolgt
    ein eigener DB-Commit, damit bei Abbruch (Netz, Worker-Restart) der
    bereits verarbeitete Teil erhalten bleibt. Prognose-Felder bleiben
    pro Tag durch preserved_prognose erhalten (gleiches Verhalten wie
    /reaggregate-tag).

    Für 32+ Tage in mehreren Schüben aufrufen.
    """
    summary = await _run_via_orchestrator(
        db,
        anlage_id=anlage_id,
        operation=RepairOperationType.REAGGREGATE_RANGE,
        params={
            "von": von.isoformat(),
            "bis": bis.isoformat(),
            "mit_resnap": mit_resnap,
        },
    )
    return {"status": "ok", **summary}


@router.get("/{anlage_id}/achse2-drift")
async def achse2_drift_diagnose(
    anlage_id: int,
    von: date = Query(..., description="Startdatum (inkl.)"),
    bis: date = Query(..., description="Enddatum (inkl.)"),
    db: AsyncSession = Depends(get_db),
):
    """Read-only-Diagnose (v3.45.9): Achse-2-Magnitude-Drift pro Tag.

    Vergleicht je Tag die GESPEICHERTEN ``TagesEnergieProfil``-Stunden-
    Repräsentationen: Zähler-Spalten (``*_kw``, Boundary-/Zählerpfad) gegen das
    ``komponenten``-JSON (Leistungspfad, W-Integration) — über dieselbe
    Invariante wie der Aggregator (``pruefe_tep_komponenten_intern_konsistenz``,
    Toleranz 0,5 kWh). **Kein Schreibzugriff, keine Re-Aggregation.**

    Maintainer-Werkzeug zum Vermessen der gegenläufigen Magnitude-Drift
    (#315, Memory ``project_achse2_magnitude_drift``) über viele Tage, bevor an
    der Rekonstruktions-Kette etwas geändert wird. Die angezeigten Werte
    (Kacheln/Bilanz/Chart) stammen aus dem Zählerpfad und sind korrekt — diese
    Drift ist rein diagnostisch (log-only im Aggregator, hier abfragbar).
    """
    result = await db.execute(
        select(TagesEnergieProfil)
        .where(
            TagesEnergieProfil.anlage_id == anlage_id,
            TagesEnergieProfil.datum >= von,
            TagesEnergieProfil.datum <= bis,
        )
        .order_by(TagesEnergieProfil.datum, TagesEnergieProfil.stunde)
    )
    rows = list(result.scalars().all())

    nach_tag: dict[date, list] = {}
    for row in rows:
        nach_tag.setdefault(row.datum, []).append(row)

    tage_out: list[dict] = []
    for datum_, tep_rows in sorted(nach_tag.items()):
        kategorien = [
            {
                "name": bericht.name,
                "zaehler_kwh": round(bericht.erwartet, 3),
                "leistung_kwh": round(bericht.tatsaechlich, 3),
                "abweichung_kwh": round(bericht.abweichung_kwh, 3),
                "toleranz_kwh": bericht.toleranz_kwh,
            }
            for bericht in pruefe_tep_komponenten_intern_konsistenz(tep_rows)
            if not bericht.konsistent
        ]
        if kategorien:
            tage_out.append({"datum": datum_.isoformat(), "drift": kategorien})

    return {
        "status": "ok",
        "anlage_id": anlage_id,
        "von": von.isoformat(),
        "bis": bis.isoformat(),
        "tage_mit_drift": len(tage_out),
        "tage": tage_out,
    }


@router.post("/{anlage_id}/vollbackfill")
async def vollbackfill(
    anlage_id: int,
    von: Optional[date] = Query(None, description="Startdatum (Standard: frühestes Datum in HA Statistics)"),
    bis: Optional[date] = Query(None, description="Enddatum (Standard: gestern)"),
    overwrite: Optional[bool] = Query(
        None,
        description="DEPRECATED (#190): wird ignoriert. Vollbackfill ist immer additiv.",
        deprecated=True,
    ),
    db: AsyncSession = Depends(get_db),
):
    """
    Füllt fehlende Tage im Energieprofil aus HA Long-Term Statistics nach.

    Wrapper über RepairOperationType.VOLLBACKFILL. **Immer additiv** (#190):
    bestehende Tage bleiben unverändert. Für gezielte Reparatur einzelner
    Tage: /reaggregate-tag mit Vorschau.
    """
    if overwrite:
        logger.info(
            f"Vollbackfill Anlage {anlage_id}: overwrite=true wurde gesendet, wird ignoriert "
            "(#190: nur additiv, bestehende Tage bleiben)"
        )

    summary = await _run_via_orchestrator(
        db,
        anlage_id=anlage_id,
        operation=RepairOperationType.VOLLBACKFILL,
        params={
            "von": von.isoformat() if von else None,
            "bis": bis.isoformat() if bis else None,
        },
    )
    return summary


@router.post("/{anlage_id}/kraftstoffpreis-backfill/tages")
async def kraftstoffpreis_backfill_tages(
    anlage_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Befüllt TagesZusammenfassung.kraftstoffpreis_euro aus EU Oil Bulletin
    für alle Tage ohne Preis. Wrapper über
    RepairOperationType.KRAFTSTOFFPREIS_BACKFILL mit scope=tages.
    """
    summary = await _run_via_orchestrator(
        db,
        anlage_id=anlage_id,
        operation=RepairOperationType.KRAFTSTOFFPREIS_BACKFILL,
        params={"scope": "tages"},
    )
    return {
        "aktualisiert": summary.get("tages_aktualisiert", 0),
        "land": summary.get("land", "DE"),
        "hinweis": summary.get("tages_hinweis"),
        "fehler": summary.get("tages_fehler"),
    }


@router.post("/{anlage_id}/kraftstoffpreis-backfill/monats")
async def kraftstoffpreis_backfill_monats(
    anlage_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Befüllt Monatsdaten.kraftstoffpreis_euro aus EU Oil Bulletin
    (Monatsdurchschnitt aus Wochenpreisen) für alle Monate ohne Preis.
    """
    summary = await _run_via_orchestrator(
        db,
        anlage_id=anlage_id,
        operation=RepairOperationType.KRAFTSTOFFPREIS_BACKFILL,
        params={"scope": "monats"},
    )
    return {
        "aktualisiert": summary.get("monats_aktualisiert", 0),
        "land": summary.get("land", "DE"),
        "hinweis": summary.get("monats_hinweis"),
        "fehler": summary.get("monats_fehler"),
    }


@router.post("/{anlage_id}/kraftstoffpreis-backfill")
async def kraftstoffpreis_backfill(
    anlage_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Alt-Endpoint (Rückwärtskompatibilität): befüllt Tages- und Monats-Kraftstoffpreise
    in einem Aufruf. Neue UIs sollten die split-Endpoints ``/tages`` und ``/monats`` nutzen.
    """
    summary = await _run_via_orchestrator(
        db,
        anlage_id=anlage_id,
        operation=RepairOperationType.KRAFTSTOFFPREIS_BACKFILL,
        params={"scope": "beides"},
    )
    return {
        "tages_aktualisiert": summary.get("tages_aktualisiert", 0),
        "monats_aktualisiert": summary.get("monats_aktualisiert", 0),
        "land": summary.get("land", "DE"),
    }


@router.delete("/rohdaten")
async def delete_alle_rohdaten(
    db: AsyncSession = Depends(get_db),
):
    """
    Löscht alle TagesEnergieProfil- und TagesZusammenfassung-Daten aller Anlagen.

    Bleibt direkter Pfad (Konzept Sektion 5.2 — Bulk-Delete). Wird
    verwendet wenn Energieprofil-Daten durch falsch gemappte Sensoren
    korrumpiert wurden. Monatsdaten bleiben erhalten. Der Scheduler
    berechnet alles neu (max. 15 Min).
    """
    del_stunden = await db.execute(delete(TagesEnergieProfil))
    del_tage = await db.execute(delete(TagesZusammenfassung))
    # Flag bei ALLEN Anlagen zurücksetzen, damit der nächste Monatsabschluss
    # den Auto-Vollbackfill aus HA Statistics erneut anstößt
    await db.execute(update(Anlage).values(vollbackfill_durchgefuehrt=False))
    await db.commit()

    return {
        "geloescht_stundenwerte": del_stunden.rowcount,
        "geloescht_tagessummen": del_tage.rowcount,
        "hinweis": "Scheduler schreibt ab dem nächsten Lauf (max. 15 Min) neue Daten. Monatsdaten bleiben erhalten.",
    }
