"""
Energie-Profil API — Repair- / Write-Endpoints.

Seit Etappe 3d Päckchen 4 sind alle Repair-Endpoints Wrapper über den
`services.repair_orchestrator`. Der Wrapper ruft intern
`orchestrator.plan(req)` + `orchestrator.execute(plan_id)` und mapt
die alten Response-Felder, damit Bestand-Frontends nicht brechen.

Konzept: docs/archive/KONZEPT-DATENPIPELINE.md Sektion 5.2.

Endpunkt-Inventar:

  DELETE /api/energie-profil/{anlage_id}/rohdaten — Löscht Daten einer Anlage
  DELETE /api/energie-profil/rohdaten — Löscht Daten aller Anlagen
  POST   /api/energie-profil/reaggregate-heute — Triggert Aggregation heute
  POST   /api/energie-profil/{anlage_id}/reaggregate-tag — Reaggregate eines Tages
  POST   /api/energie-profil/{anlage_id}/reaggregate-bereich — Reaggregate mehrerer Tage (max 31)
  POST   /api/energie-profil/{anlage_id}/vollbackfill — Lückenfüller HA-LTS (additiv)
  POST   /api/energie-profil/{anlage_id}/kraftstoffpreis-backfill[/tages|/monats]
  POST   /api/energie-profil/{anlage_id}/kanal-abgleich — HA-Spiegel jetzt abgleichen (Lauf des Nachtjobs 02:45)
  POST   /api/energie-profil/{anlage_id}/spiegel-abgleich-tag — Abgleich + Neu-Aggregation eines Tages (N-790)

DELETE-Endpoints bleiben direkt (Bulk-Delete, kein Plan-Mehrwert; Konzept
Sektion 5.2: "DELETE bleibt direkt, schreibt aber Audit-Log").
"""

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.exceptions import not_found
from backend.api.deps import get_db
from backend.core.berechnungen import (
    summe_pv_bkw_kwh,
    pruefe_tep_komponenten_intern_konsistenz,
)
from backend.models.anlage import Anlage
from backend.models.emob_ladeblock import EmobLadeblock
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
    db: AsyncSession = Depends(get_db, scope="function"),
):
    """
    Löscht alle TagesEnergieProfil- und TagesZusammenfassung-Daten einer Anlage.

    Bleibt direkter Pfad (Konzept Sektion 5.2 — Bulk-Delete kein
    Orchestrator-Bedarf). Der Scheduler schreibt ab dem nächsten Lauf
    (alle 15 Min) neue Daten. Monatsdaten bleiben erhalten.

    ⛔ **Zwei Dinge kommen NICHT zurück, und der Hinweis sagt das jetzt**
    (Forum simon42 T89667, PN rapahl 15.09.2026):

    1. **Die aufgezeichneten Prognosen.** ``pv_prognose_final_kwh`` /
       ``pv_prognose_final_at`` und die SFML-/Solcast-Felder hängen an
       ``TagesEnergieProfil`` und sind Aufzeichnungen eines vergangenen
       Zeitpunkts — Grundlage des Genauigkeits-Vergleichs. Neu *berechnen*
       kann sie niemand.
    2. **Messwerte jenseits der Recorder-Tiefe.** Zurück kommt nur, was die
       HA-Langzeitstatistik noch führt; nach Purge, Sensor-Umbau oder
       Neuinstallation reicht sie oft kürzer als das gepflegte Profil. Das
       ist dieselbe Begründung, aus der der Overwrite-Modus des
       Vollbackfills mit v3.25.22 entfernt wurde — sie galt hier genauso,
       stand aber nirgends.

    ⚠ Die Funktion selbst bleibt unverändert: Sie wird bewusst genutzt, und
    die Entscheidung gehört dem Anwender. Geändert ist nur, dass er sie
    informiert trifft.
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
    # N-555 Stufe 3 (NF-1): die Ladeblöcke sind sitzungsgebunden und aus denselben Tagen
    # gebildet — gelöscht wird jeder Tag, also jeder Block der Anlage. Rechnerisch wäre ein
    # Rest folgenlos (ohne Tageszeilen mit Regelmarke gelten keine Blöcke, W-C); der
    # Scheduler bildet sie mit den Tagen neu.
    await db.execute(delete(EmobLadeblock).where(EmobLadeblock.anlage_id == anlage_id))
    # Flag zurücksetzen (Bestand). ⚠ Seit HA-Bauform E4f liest es niemand mehr: der
    # Monatsabschluss stößt keinen Auto-Vollbackfill mehr an (`monatsabschluss_aggregator`,
    # Schritt 3 entfallen) — die gelöschten Tage füllt die Werkbank „Lücken aus HA-LTS
    # nachfüllen", die Summen der Sichten kommen aus den Kanälen.
    anlage.vollbackfill_durchgefuehrt = False
    await db.commit()

    return {
        "geloescht_stundenwerte": del_stunden.rowcount,
        "geloescht_tagessummen": del_tage.rowcount,
        "hinweis": (
            "Der Scheduler holt die Messwerte aus der HA-Langzeitstatistik "
            "nach (max. 15 Min), soweit sie zurückreicht. Aufgezeichnete "
            "PV-Prognosen sind nicht rekonstruierbar. Monatsdaten bleiben "
            "erhalten."
        ),
    }


@router.post("/reaggregate-heute")
async def reaggregate_heute(db: AsyncSession = Depends(get_db, scope="function")):
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
    db: AsyncSession = Depends(get_db, scope="function"),
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

    Dazu (N-58) die Aussage **je Komponente**: `komponenten_erwartet` /
    `komponenten_geschrieben` / `komponenten_ohne_wert` samt Detail-Liste.
    `status: "ok"` bleibt der reine Transport-Status — dass der Lauf für eine
    Wärmepumpe nichts holen konnte, stand vorher nirgends und war von
    „PV-Wert unverändert" nicht unterscheidbar (Forum simon42 #89667/83).
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
    pv_kwh_aus_luecke = await _pv_aus_luecke(db, anlage_id, datum)
    return {
        "status": "ok",
        "datum": summary.get("datum", datum.isoformat()),
        "stunden_verfuegbar": summary.get("stunden_verfuegbar"),
        "stunden_mit_messdaten": stunden_mit_messdaten,
        "pv_kwh_alt": pv_kwh_alt,
        "pv_kwh_neu": pv_kwh_neu,
        # Zählerlücken wie HA (§2): wie viel von `pv_kwh_neu` in Stunden steht,
        # die mehr als eine reale Stunde tragen — die Energie einer Lücke in HA.
        # Die Rückmeldung beschriftet das Δ damit („davon … aus einer Lücke").
        "pv_kwh_aus_luecke": pv_kwh_aus_luecke,
        "komponenten": summary.get("komponenten", []),
        "komponenten_erwartet": summary.get("komponenten_erwartet", 0),
        "komponenten_geschrieben": summary.get("komponenten_geschrieben", 0),
        "komponenten_ohne_wert": summary.get("komponenten_ohne_wert", []),
        # HA-Bauform S5 (E-S5-3): an einem Kanal-Tag die Gruppen, deren Mengen der Lauf leer lässt (der Tag liest sie
        # aus dem HA-Spiegel bzw. den eigenen Zählerständen).
        "kanal_gruppen": summary.get("kanal_gruppen", []),
        # N-791: woher der Lauf schrieb, und an einem Tag ohne Leistungskurve der Satz «Gerätewerte aus der
        # Home-Assistant-Statistik neu geschrieben; der gespeicherte Leistungsverlauf blieb stehen.»
        "quelle": summary.get("quelle"),
        "quelle_text": summary.get("quelle_text"),
    }


#: Die Mengen-Spalten, an denen ``_stunden_mit_messdaten`` eine Stunde «mit Messdaten» erkennt.
_MENGEN_FELDER = ("pv_kw", "verbrauch_kw", "einspeisung_kw", "netzbezug_kw", "batterie_kw", "waermepumpe_kw",
                  "wallbox_kw")


async def _stunden_mit_messdaten(
    db: AsyncSession, anlage_id: int, datum: date,
) -> int:
    """Zählt die Stunden des Tages mit mindestens einem nicht-NULL-Mengenwert.

    Im Orchestrator-Refactor 2026-05-10 (Commit 17db2350) ging das Feld
    aus dem alten /reaggregate-tag-Endpoint verloren — das Frontend
    (`ReaggregatePreviewModal` → `handlePreviewApplied`) wertet `> 0` aus
    und zeigte dadurch dauerhaft die „0/24 Stunden mit Messdaten —
    keine Snapshots in der DB und HA-Statistics nicht erreichbar"-Warnung,
    auch wenn die Reaggregation tatsächlich erfolgreich war (#290 detLAN).

    `stunden_verfuegbar` aus `TagesZusammenfassung` zählt alle 24 Slots
    auch wenn alle Werte NULL sind (synthetisches MQTT-Energy-Setup) —
    dieser Wert hier ist der ehrlichere Erfolgsindikator.

    HA-Bauform S5 (E-S5-3): die Stunden über die Lesestelle ``kanal_stunden.stunden_der_tage`` — an einem Kanal-Tag die
    Mischzeilen (der Lauf schreibt dort keine Mengen in die Stundenzeile, der Tag liest sie aus den Kanälen; ohne das
    meldete die Rückmeldung «0/24 Stunden mit Messdaten»), an einem Bestandstag die Stundenzeilen wie bisher.
    """
    from backend.services.energie_profil.kanal_stunden import stunden_der_tage

    zeilen = await stunden_der_tage(db, anlage_id, datum, datum, felder=_MENGEN_FELDER)
    return sum(1 for z in zeilen if any(getattr(z, f, None) is not None for f in _MENGEN_FELDER))


async def _pv_aus_luecke(
    db: AsyncSession, anlage_id: int, datum: date,
) -> Optional[float]:
    """Σ PV der Stunden des Tages, deren PV-Menge mehr als eine reale Stunde trägt.

    Zählerlücken wie HA (§2, Repair-Vorschau Δ): Nach einer Neuaggregation
    steht die Energie einer Lücke in der Folgestunde bzw. im Folgetag — das Δ
    der Rückmeldung ist dann keine „Reparatur eines Fehlers", sondern die
    Energie, die HA nachgeliefert hat. ``None``, wenn keine Stunde gebündelt ist.
    HA-Bauform S5 (E-S5-3): die Stunden über die Lesestelle (an einem Kanal-Tag die Mischzeilen mit den Kanal-Spannen).
    """
    from backend.core.berechnungen.spannen import spanne
    from backend.services.energie_profil.kanal_stunden import stunden_der_tage

    zeilen = await stunden_der_tage(db, anlage_id, datum, datum, felder=("pv_kw",))
    summe = sum(z.pv_kw for z in zeilen if z.pv_kw is not None and spanne(z.spannen, "pv") > 1)
    return round(summe, 2) if summe > 0 else None


async def _pv_tagessumme(
    db: AsyncSession, anlage_id: int, datum: date,
) -> Optional[float]:
    """Liefert die PV-Tagessumme (Σ pv_* + bkw_* aus komponenten_kwh) für
    einen Tag. None, wenn keine TagesZusammenfassung existiert.

    Nutzt dieselbe Aggregationslogik wie _check_datenquelle_drift —
    damit ist das Frontend-Δ konsistent mit der Drift-Anzeige.

    HA-Bauform S5 (E-S5-3): über die Lesestelle ``kanal_stunden.pv_ist_je_tag`` — an einem Kanal-Tag die PV aus den
    Kanälen (der Lauf schreibt dort keine PV-Schlüssel in die Tageszeile; «vorher/nachher» bleibt die Zahl von
    *Cockpit → Tag*), an einem Bestandstag die Tageszeile wie bisher.
    """
    from backend.services.energie_profil.kanal_stunden import pv_ist_je_tag

    tz_result = await db.execute(
        select(TagesZusammenfassung).where(
            TagesZusammenfassung.anlage_id == anlage_id,
            TagesZusammenfassung.datum == datum,
        )
    )
    tz = tz_result.scalar_one_or_none()
    if tz is None:
        return None
    pv = (await pv_ist_je_tag(db, anlage_id, [tz])).get(datum)
    return round(pv, 2) if pv is not None else None


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
    db: AsyncSession = Depends(get_db, scope="function"),
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
    (#315) über viele Tage, bevor an der Rekonstruktions-Kette etwas geändert
    wird.

    ⚠ **Der Satz „die angezeigten Werte stammen aus dem Zählerpfad" galt hier
    bis 2026-09-02 ohne Einschränkung — er hat eine.** Die Tages-Hauptzahlen
    kommen aus dem Zählerpfad; die **Erträge je Erzeuger** fallen seit #350 auf
    die Σ des Leistungspfads zurück, wenn ein Tag keinen Boundary-Rollup hat
    (``energie_profil/tage_werte.py``), und der Client summiert BKW,
    E-Mobilität und Sonstiges direkt von den Stunden
    (``v4/TagKomponenten.tsx``).

    ⭐ Seit N-187 vergleicht die Invariante nur Geräte, die **beide** Pfade
    führen — die Zuordnung dieses Tages nennt die Menge. Vorher meldete ein
    Gerät mit Leistungs-, aber ohne Zählersensor täglich eine „Drift", die
    exakt seine eigene Σ war.

    **HA-Bauform S5b (E-S5-4, ⚑ A-7 aus E-S5-3):** an einem Kanal-Tag trägt die Stundenzeile keine Zähler-Spalten
    der Gruppen aus dem HA-Spiegel bzw. den eigenen Zählerständen (``aggregate_day``, ``mengen_weiche``) — dort gibt es
    nichts zu vergleichen. Die Antwort nennt diese Tage (``kanal_tage_ohne_vergleich``, ``hinweis``); der Vergleich
    selbst bleibt, wie er ist.
    """
    from backend.services.kanal.bilanz_leser import kanal_tage

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

    # Grundgesamtheit je Tag (N-187) — dieselbe Menge, die der Aggregator
    # benutzt. Sie ist **tagesabhängig**: eine an diesem Tag noch nicht
    # angeschaffte oder bereits stillgelegte Komponente verspricht nichts.
    from backend.models.investition import Investition
    from backend.services.snapshot.komponenten_beitraege import (
        erwartete_komponenten_keys,
    )

    anlage_obj = (await db.execute(
        select(Anlage).where(Anlage.id == anlage_id)
    )).scalar_one_or_none()
    invs = (await db.execute(
        select(Investition).where(Investition.anlage_id == anlage_id)
    )).scalars().all()
    invs_by_id = {str(inv.id): inv for inv in invs}
    sensor_mapping = (anlage_obj.sensor_mapping if anlage_obj else None) or {}

    tage_out: list[dict] = []
    for datum_, tep_rows in sorted(nach_tag.items()):
        gedeckt = set(erwartete_komponenten_keys(
            sensor_mapping, invs_by_id, datum_,
        ))
        kategorien = [
            {
                "name": bericht.name,
                "zaehler_kwh": round(bericht.erwartet, 3),
                "leistung_kwh": round(bericht.tatsaechlich, 3),
                "abweichung_kwh": round(bericht.abweichung_kwh, 3),
                "toleranz_kwh": bericht.toleranz_kwh,
            }
            for bericht in pruefe_tep_komponenten_intern_konsistenz(
                tep_rows, gedeckt,
            )
            if not bericht.konsistent
        ]
        if kategorien:
            tage_out.append({"datum": datum_.isoformat(), "drift": kategorien})

    ohne_vergleich = sorted(d for d in await kanal_tage(db, anlage_id, von, bis) if d in nach_tag)
    return {
        "status": "ok",
        "anlage_id": anlage_id,
        "von": von.isoformat(),
        "bis": bis.isoformat(),
        "tage_mit_drift": len(tage_out),
        "tage": tage_out,
        "kanal_tage_ohne_vergleich": len(ohne_vergleich),
        "hinweis": (
            f"{len(ohne_vergleich)} Tag(e) des Bereichs lesen ihre Mengen aus dem HA-Spiegel bzw. den eigenen "
            "Zählerständen — die Stundenzeile trägt dort (sobald der Tag ohne Mengen geschrieben ist) keine "
            "Zähler-Spalten, es gibt nichts zu vergleichen, was eine Sicht zeigt."
            if ohne_vergleich else None
        ),
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
    db: AsyncSession = Depends(get_db, scope="function"),
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
    db: AsyncSession = Depends(get_db, scope="function"),
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
    db: AsyncSession = Depends(get_db, scope="function"),
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
    db: AsyncSession = Depends(get_db, scope="function"),
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


def _abgleich_meldung(erg) -> str:
    """Ein Satz für die Ergebniszeile der Werkbank — nur aus dem, was der Lauf zurückgibt."""
    from datetime import datetime as _dt

    if erg.korrigiert:
        teile = "; ".join(
            f"{k['key']} ab {_dt.fromtimestamp(int(k['ab_ts'])).strftime('%d.%m.%Y %H:%M')} "
            f"({k['zeilen']} Stundenzeile(n))"
            for k in erg.korrigiert
        )
        satz = (f"{len(erg.korrigiert)} von {erg.abschnitte} Abschnitt(en) wichen von der HA-Statistik ab und "
                f"wurden ab der ersten Abweichung neu gespiegelt: {teile}.")
    else:
        satz = (f"Alle {erg.abschnitte} geprüften Abschnitt(e) in {erg.kanaele} Kanal/Kanälen stimmen mit der "
                "HA-Statistik überein — nichts zu übernehmen.")
    if erg.gekuerzt:
        satz += (f" {len(erg.gekuerzt)} Abschnitt(e): HA hält den Anfang nicht mehr, der ältere Spiegel bleibt "
                 "stehen.")
    if erg.fehler:
        satz += (f" {erg.fehler} Abschnitt(e) konnten nicht geprüft werden (Home Assistant unterwegs nicht "
                 "erreichbar?) — dort wurde nichts geändert.")
    return satz


async def _kanal_abgleich_lauf(db: AsyncSession, anlage_id: int) -> tuple[dict, object]:
    """Der Lauf hinter «HA-Spiegel jetzt abgleichen» — gemeinsam für ``kanal-abgleich`` und ``spiegel-abgleich-tag``.

    Ruft ``kanal/konsistenz.konsistenz_anlage`` mit denselben kurzen eigenen Sitzungen wie der Nachtjob (``get_session``),
    damit kein HA-Abruf in einer offenen Schreib-Transaktion liegt. Antwort-Felder wie ``kanal-abgleich`` und das
    Ergebnis des Laufs (``None`` ohne Spiegel). Unbekannte Anlage ⇒ 404, HA nicht erreichbar ⇒ 503. Schreibt kein
    Aktivitätsprotokoll — das tut die Route, die den Lauf ruft.
    """
    from backend.core.database import get_session
    from backend.services.kanal.konsistenz import konsistenz_anlage, spiegel_quellen_anzahl

    anlage = (await db.execute(select(Anlage).where(Anlage.id == anlage_id))).scalar_one_or_none()
    if not anlage:
        raise not_found("Anlage")

    if not await spiegel_quellen_anzahl(db, anlage_id):
        return {
            "anlage_id": anlage_id, "hat_spiegel": False, "kanaele": 0, "abschnitte": 0, "gleich": 0,
            "korrigiert": [], "gekuerzt": [], "uebersprungen": {}, "fehler": 0,
            "meldung": ("Für diese Anlage führt eedc keinen HA-Spiegel — ohne Zähler aus der "
                        "Home-Assistant-Statistik gibt es nichts abzugleichen."),
        }, None

    erg = await konsistenz_anlage(get_session, anlage_id)
    if erg.uebersprungen.get("ha_nicht_erreichbar"):
        raise HTTPException(
            status_code=503,
            detail="Home Assistant ist nicht erreichbar — der Abgleich braucht die HA-Langzeitstatistik.",
        )
    return {
        "anlage_id": anlage_id, "hat_spiegel": True,
        "kanaele": erg.kanaele, "abschnitte": erg.abschnitte, "gleich": erg.gleich,
        "korrigiert": erg.korrigiert, "gekuerzt": erg.gekuerzt,
        "uebersprungen": erg.uebersprungen, "fehler": erg.fehler,
        "meldung": _abgleich_meldung(erg),
    }, erg


@router.post("/{anlage_id}/kanal-abgleich")
async def kanal_abgleich(
    anlage_id: int,
    db: AsyncSession = Depends(get_db, scope="function"),
):
    """HA-Spiegel jetzt abgleichen — derselbe Lauf wie der Nachtjob 02:45, für EINE Anlage (MartyBr, simon42 #429).

    Der Nachtjob (``scheduler.kanal_konsistenz_job`` → ``kanal/konsistenz.konsistenz_alle``) ruft je Anlage
    ``konsistenz_anlage``; diese Route ruft genau sie (``_kanal_abgleich_lauf``), mit denselben kurzen eigenen Sitzungen
    (``get_session``), damit kein HA-Abruf in einer offenen Schreib-Transaktion liegt. Wozu: nach einer Korrektur in
    Home Assistant (Entwicklerwerkzeuge → Statistik → „Wert anpassen") zeigten die Tages-Kennzahlen bis zum nächsten
    Morgen den alten Spiegel.

    Antwort: die Zähler des Laufs (``kanaele``, ``abschnitte``, ``gleich``, ``korrigiert`` je Kanal mit erster
    abweichender Stunde und Zeilenzahl, ``gekuerzt``, ``uebersprungen``, ``fehler``) und ein Satz ``meldung``.
    Ohne Spiegel (Standalone, kein HA-Zähler) ⇒ ``hat_spiegel: false``, kein HA-Aufruf. HA nicht erreichbar ⇒ 503.
    """
    from backend.services.activity_service import log_activity

    antwort, erg = await _kanal_abgleich_lauf(db, anlage_id)
    if erg is None:
        return antwort

    await log_activity(
        kategorie="ha_statistics",
        aktion=("HA-Spiegel von Hand abgeglichen: unvollständig" if erg.fehler
                else "HA-Spiegel von Hand abgeglichen: an HA angeglichen" if erg.korrigiert
                else "HA-Spiegel von Hand abgeglichen: keine Abweichung"),
        erfolg=erg.fehler == 0,
        details=antwort["meldung"],
        details_json={"korrigiert": erg.korrigiert, "gekuerzt": erg.gekuerzt,
                      "uebersprungen": erg.uebersprungen, "fehler": erg.fehler},
        anlage_id=anlage_id,
        db=db,
    )
    return antwort


def _anzahl_kanaele(n: int) -> str:
    return f"{n} Kanal" if n == 1 else f"{n} Kanäle"


def _abgleich_tag_meldung(abgleich: dict, datum: date, reaggregation_fehler: Optional[str] = None,
                          quelle_text: Optional[str] = None) -> str:
    """Ein Satz in Anwender-Sprache für «Aus Home Assistant neu übernehmen» (N-790) — nur aus den Antworten der Läufe;
    ``quelle_text`` (N-791) hängt den Satz der Neu-Aggregation an (Tag ohne Leistungskurve: Zähler neu, Verlauf bleibt)."""
    from datetime import datetime as _dt

    tag = (f"Tag {datum.strftime('%d.%m.%Y')} neu aufgebaut" if reaggregation_fehler is None
           else f"den Tag {datum.strftime('%d.%m.%Y')} konnte eedc nicht neu aufbauen ({reaggregation_fehler})")
    quelle = f" {quelle_text}" if quelle_text else ""
    if not abgleich["hat_spiegel"]:
        return f"Für diese Anlage übernimmt eedc keine Statistik aus Home Assistant — {tag}.{quelle}"
    korrigiert = abgleich["korrigiert"]
    if korrigiert:
        ab = _dt.fromtimestamp(min(int(k["ab_ts"]) for k in korrigiert)).strftime("%d.%m. %H:%M")
        satz = (f"Statistik aus Home Assistant neu übernommen, {_anzahl_kanaele(len(korrigiert))} ab {ab} "
                f"korrigiert; {tag}.")
    else:
        satz = f"Statistik aus Home Assistant geprüft — nichts zu korrigieren, {tag}."
    if abgleich["gekuerzt"]:
        satz += (f" Home Assistant hat für {_anzahl_kanaele(len(abgleich['gekuerzt']))} keinen Anfang mehr — "
                 "ältere Werte bleiben.")
    if abgleich["fehler"]:
        satz += (f" {_anzahl_kanaele(abgleich['fehler'])} konnten nicht geprüft werden (Home Assistant unterwegs "
                 "nicht erreichbar?) — dort wurde nichts geändert.")
    return satz + quelle


class SpiegelAbgleichTagRequest(BaseModel):
    datum: date


@router.post("/{anlage_id}/spiegel-abgleich-tag")
async def spiegel_abgleich_tag(
    anlage_id: int,
    body: SpiegelAbgleichTagRequest,
    db: AsyncSession = Depends(get_db, scope="function"),
):
    """«Aus Home Assistant neu übernehmen» — der Handgriff der Drift-, Zählersprung- und Rückgang-Befunde (N-790,
    Melder ottokar, simon42 PN T95600).

    An einem Kanal-Tag liest der Tag seine Mengen aus dem HA-Spiegel, und ``aggregate_day`` schreibt dort keine
    Mengen (``mengen_weiche``) — «Tag reparieren» allein konnte eine Drift gegen HA nie beheben. Diese Route verkettet
    die zwei bestehenden Läufe: zuerst den Abgleich (``_kanal_abgleich_lauf``, derselbe wie «HA-Spiegel jetzt
    abgleichen»; er übernimmt nur, was Home Assistant hat, und löscht nichts), danach die Neu-Aggregation des Tages
    (``reaggregate_tag``, wie «Tag reparieren»). Ohne Spiegel nur die Neu-Aggregation.

    Antwort: ``abgleich`` (Felder von ``kanal-abgleich``), ``reaggregation`` (Felder von ``reaggregate-tag``; scheitert
    sie, ``status: "fehler"`` mit ``fehler`` — der Abgleich ist dann schon geschehen und bleibt), ``datum`` und ein
    Satz ``meldung``. Unbekannte Anlage ⇒ 404, HA nicht erreichbar ⇒ 503 (vor der Neu-Aggregation).
    """
    from backend.services.activity_service import log_activity

    datum = body.datum
    abgleich, erg = await _kanal_abgleich_lauf(db, anlage_id)
    reaggregation_fehler: Optional[str] = None
    try:
        reaggregation = await reaggregate_tag(anlage_id, datum=datum, mit_resnap=True, db=db)
    except HTTPException as e:
        reaggregation_fehler = str(e.detail)
        reaggregation = {"status": "fehler", "datum": datum.isoformat(), "fehler": reaggregation_fehler}
    meldung = _abgleich_tag_meldung(abgleich, datum, reaggregation_fehler, reaggregation.get("quelle_text"))

    await log_activity(
        kategorie="ha_statistics",
        aktion=("Aus Home Assistant neu übernommen: ohne HA-Spiegel" if erg is None
                else "Aus Home Assistant neu übernommen: unvollständig" if erg.fehler
                else "Aus Home Assistant neu übernommen: an HA angeglichen" if erg.korrigiert
                else "Aus Home Assistant neu übernommen: keine Abweichung"),
        erfolg=(erg is None or erg.fehler == 0) and reaggregation_fehler is None,
        details=meldung,
        details_json={"datum": datum.isoformat(), "korrigiert": abgleich["korrigiert"],
                      "gekuerzt": abgleich["gekuerzt"], "uebersprungen": abgleich["uebersprungen"],
                      "fehler": abgleich["fehler"], "reaggregation_fehler": reaggregation_fehler},
        anlage_id=anlage_id,
        db=db,
    )
    return {"anlage_id": anlage_id, "datum": datum.isoformat(), "abgleich": abgleich,
            "reaggregation": reaggregation, "meldung": meldung}


@router.delete("/rohdaten")
async def delete_alle_rohdaten(
    db: AsyncSession = Depends(get_db, scope="function"),
):
    """
    Löscht alle TagesEnergieProfil- und TagesZusammenfassung-Daten aller Anlagen.

    Bleibt direkter Pfad (Konzept Sektion 5.2 — Bulk-Delete). Wird
    verwendet wenn Energieprofil-Daten durch falsch gemappte Sensoren
    korrumpiert wurden. Monatsdaten bleiben erhalten. Der Scheduler holt
    die Messwerte nach (max. 15 Min).

    ⛔ Wie beim anlagenweiten Zwilling darüber: aufgezeichnete Prognosen
    sind endgültig weg, und Messwerte kommen nur so weit zurück, wie die
    HA-Langzeitstatistik reicht.
    """
    del_stunden = await db.execute(delete(TagesEnergieProfil))
    del_tage = await db.execute(delete(TagesZusammenfassung))
    # N-555 Stufe 3 (NF-1): mit allen Tagen gehen alle Ladeblöcke (s. `delete_rohdaten`).
    await db.execute(delete(EmobLadeblock))
    # Flag bei ALLEN Anlagen zurücksetzen (Bestand; seit HA-Bauform E4f ohne Leser, s.
    # `delete_rohdaten`)
    await db.execute(update(Anlage).values(vollbackfill_durchgefuehrt=False))
    await db.commit()

    return {
        "geloescht_stundenwerte": del_stunden.rowcount,
        "geloescht_tagessummen": del_tage.rowcount,
        "hinweis": (
            "Der Scheduler holt die Messwerte aus der HA-Langzeitstatistik "
            "nach (max. 15 Min), soweit sie zurückreicht. Aufgezeichnete "
            "PV-Prognosen sind nicht rekonstruierbar. Monatsdaten bleiben "
            "erhalten."
        ),
    }
