"""
Monatsabschluss API — Wizard-Save-Pfad.

POST /{anlage_id}/{jahr}/{monat}  — Speichert Wizard-Eingabe via
                                     Provenance-Resolver (manual:form).

Background-Task `_post_save_hintergrund` triggert nach erfolgreichem
Save:
  1. MQTT Publish (final_month_data)
  2. Energie-Profil Auto-Aggregation (services/monatsabschluss_aggregator.py)
  3. Community Auto-Share (falls aktiviert)
"""

from datetime import date as _date  # noqa: F401
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database import async_session_maker, get_db
from backend.core.field_definitions import ALLE_MONATSDATEN_FELDNAMEN
from backend.models.anlage import Anlage
from backend.models.investition import InvestitionMonatsdaten
from backend.models.monatsdaten import Monatsdaten
from backend.services.activity_service import log_activity
from backend.services.ha_mqtt_sync import get_ha_mqtt_sync_service
from backend.services.provenance import (
    write_json_subkey_with_provenance,
    write_with_provenance,
)
from backend.services.vorschlag_service import VorschlagService

from ._shared import (
    MONAT_NAMEN,
    WarnungResponse,
    _warnung_to_response,
    logger,
)

router = APIRouter()

# Wizard-Save ist User-Eingabe = `manual:form`. Auto-Aggregation läuft danach
# im Background-Task (services/monatsabschluss_aggregator.py).
_WIZARD_WRITER = "monatsabschluss_wizard"


# =============================================================================
# Pydantic-Models — wizard-spezifisch
# =============================================================================

class FeldWert(BaseModel):
    """Wert für ein Feld."""
    feld: str
    wert: float


class InvestitionWerte(BaseModel):
    """Werte für eine Investition."""
    investition_id: int
    felder: list[FeldWert]
    sonstige_positionen: Optional[list[dict]] = None  # Strukturierte Erträge & Ausgaben


class MonatsabschlussInput(BaseModel):
    """Eingabedaten für den Monatsabschluss."""
    # Basis-Zählerdaten
    # HINWEIS: direktverbrauch_kwh wird automatisch berechnet (PV-Erzeugung - Einspeisung)
    einspeisung_kwh: Optional[float] = None
    netzbezug_kwh: Optional[float] = None
    globalstrahlung_kwh_m2: Optional[float] = None
    sonnenstunden: Optional[float] = None
    durchschnittstemperatur: Optional[float] = None

    # Optionale manuelle Felder (nicht aus HA)
    netzbezug_durchschnittspreis_cent: Optional[float] = None
    kraftstoffpreis_euro: Optional[float] = None  # €/L Monatsdurchschnitt
    gaspreis_cent_kwh: Optional[float] = None  # ct/kWh Endpreis Gas/Öl für WP-Vergleich
    sonderkosten_euro: Optional[float] = None
    sonderkosten_beschreibung: Optional[str] = None
    notizen: Optional[str] = None

    # Investitionen
    investitionen: list[InvestitionWerte] = []

    # Datenquelle (z.B. "mqtt_inbound", "cloud_import", "ha_statistics")
    datenquelle: Optional[str] = None


class MonatsabschlussResult(BaseModel):
    """Ergebnis des Monatsabschlusses."""
    success: bool
    message: str
    monatsdaten_id: Optional[int] = None
    investition_monatsdaten_ids: list[int] = []
    warnungen: list[WarnungResponse] = []


# =============================================================================
# Background-Task
# =============================================================================

async def _post_save_hintergrund(
    anlage_id: int,
    jahr: int,
    monat: int,
    monatsdaten_dict: dict,
    community_auto_share: bool,
    community_hash: str | None,
) -> None:
    """MQTT-Publish, Energie-Profil-Auto-Aggregation und Community Auto-Share im Hintergrund."""
    from backend.services.monatsabschluss_aggregator import (
        run_post_monatsabschluss_aggregation,
    )

    # 1. MQTT Publish
    mqtt_sync = get_ha_mqtt_sync_service()
    try:
        await mqtt_sync.publish_final_month_data(anlage_id, jahr, monat, monatsdaten_dict)
    except Exception as e:
        logger.warning(f"MQTT-Publish fehlgeschlagen: {type(e).__name__}: {e}")

    # 2. Energie-Profil: Closing-Month-Backfill + Rollup + einmaliger Auto-Vollbackfill
    async with async_session_maker() as db:
        result = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
        anlage = result.scalar_one_or_none()
        if anlage is None:
            return

        await run_post_monatsabschluss_aggregation(anlage, jahr, monat, db)

    # 3. Community Auto-Share
    if community_auto_share:
        async with async_session_maker() as db:
            try:
                from backend.services.community_service import COMMUNITY_SERVER_URL, prepare_community_data
                import httpx
                share_data = await prepare_community_data(db, anlage_id)
                if share_data and share_data.get("monatswerte"):
                    async with httpx.AsyncClient(timeout=15.0) as client:
                        resp = await client.post(f"{COMMUNITY_SERVER_URL}/api/submit", json=share_data)
                        if resp.status_code == 200:
                            result_data = resp.json()
                            if result_data.get("anlage_hash") and not community_hash:
                                result2 = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
                                anlage_obj = result2.scalar_one_or_none()
                                if anlage_obj:
                                    anlage_obj.community_hash = result_data["anlage_hash"]
                                    await db.commit()
                            logger.info(f"Auto-Share für Anlage {anlage_id} erfolgreich")
                        else:
                            logger.warning(f"Auto-Share HTTP {resp.status_code}: {resp.text[:200]}")
            except Exception as e:
                logger.warning(f"Auto-Share fehlgeschlagen: {type(e).__name__}: {e}")


# =============================================================================
# Endpoint
# =============================================================================

@router.post("/{anlage_id}/{jahr}/{monat}", response_model=MonatsabschlussResult)
async def save_monatsabschluss(
    anlage_id: int,
    jahr: int,
    monat: int,
    daten: MonatsabschlussInput,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """
    Speichert Monatsdaten.

    Ablauf:
    1. Validierung + Plausibilitätsprüfung
    2. Speichern in Monatsdaten + InvestitionMonatsdaten
    3. Optional: Startwerte für nächsten Monat auf MQTT publizieren
    """
    logger.info(
        f"Monatsabschluss speichern: Anlage {anlage_id}, {monat:02d}/{jahr}, "
        f"Basis: einspeisung={daten.einspeisung_kwh}, netzbezug={daten.netzbezug_kwh}, "
        f"Investitionen: {len(daten.investitionen)} Stück"
    )
    for inv_w in daten.investitionen:
        logger.info(
            f"  Investition {inv_w.investition_id}: "
            f"{len(inv_w.felder)} Felder [{', '.join(f'{f.feld}={f.wert}' for f in inv_w.felder)}]"
        )

    # Anlage laden
    result = await db.execute(
        select(Anlage).where(Anlage.id == anlage_id)
    )
    anlage = result.scalar_one_or_none()
    if not anlage:
        raise HTTPException(status_code=404, detail="Anlage nicht gefunden")

    vorschlag_service = VorschlagService(db)
    alle_warnungen: list[WarnungResponse] = []

    # Plausibilität prüfen
    for feld in ["einspeisung_kwh", "netzbezug_kwh"]:
        wert = getattr(daten, feld, None)
        if wert is not None:
            warnungen = await vorschlag_service.pruefe_plausibilitaet(
                anlage_id, feld, wert, jahr, monat
            )
            alle_warnungen.extend([_warnung_to_response(w) for w in warnungen])

    # Monatsdaten erstellen oder aktualisieren
    md_result = await db.execute(
        select(Monatsdaten)
        .where(and_(
            Monatsdaten.anlage_id == anlage_id,
            Monatsdaten.jahr == jahr,
            Monatsdaten.monat == monat,
        ))
    )
    monatsdaten = md_result.scalar_one_or_none()

    if not monatsdaten:
        monatsdaten = Monatsdaten(
            anlage_id=anlage_id,
            jahr=jahr,
            monat=monat,
        )
        db.add(monatsdaten)
        try:
            await db.flush()  # ID benötigt für Provenance-Audit-Log-Eintrag
        except Exception as e:
            logger.error(f"Monatsabschluss flush Monatsdaten fehlgeschlagen: {type(e).__name__}: {e}")
            raise HTTPException(status_code=500, detail=f"Fehler beim Speichern der Monatsdaten: {e}")

    # Basis-Felder generisch aus Registry setzen — durch den Provenance-Resolver,
    # damit manuelle Wizard-Eingaben gegen frühere Cloud/HA-Stats/legacy-Werte
    # gewinnen (Source `manual:form`, Stufe 1).
    # direktverbrauch_kwh wird automatisch berechnet (PV-Erzeugung - Einspeisung)
    for feld in ALLE_MONATSDATEN_FELDNAMEN:
        wert = getattr(daten, feld, None)
        if wert is None:
            continue
        await write_with_provenance(
            db, monatsdaten, feld, wert,
            source="manual:form", writer=_WIZARD_WRITER,
        )
    if daten.datenquelle:
        # `datenquelle` ist Metadata-Feld (welcher Wizard-Pfad wurde benutzt) —
        # kein eigener Provenance-Eintrag nötig.
        monatsdaten.datenquelle = daten.datenquelle

    try:
        await db.flush()
    except Exception as e:
        logger.error(f"Monatsabschluss flush Monatsdaten fehlgeschlagen: {type(e).__name__}: {e}")
        raise HTTPException(status_code=500, detail=f"Fehler beim Speichern der Monatsdaten: {e}")
    monatsdaten_id = monatsdaten.id

    # Investition-Monatsdaten speichern
    inv_ids: list[int] = []
    for inv_werte in daten.investitionen:
        # Bestehenden Datensatz suchen oder neu erstellen
        imd_result = await db.execute(
            select(InvestitionMonatsdaten)
            .where(and_(
                InvestitionMonatsdaten.investition_id == inv_werte.investition_id,
                InvestitionMonatsdaten.jahr == jahr,
                InvestitionMonatsdaten.monat == monat,
            ))
        )
        imd = imd_result.scalar_one_or_none()

        if not imd:
            imd = InvestitionMonatsdaten(
                investition_id=inv_werte.investition_id,
                jahr=jahr,
                monat=monat,
                verbrauch_daten={},
            )
            db.add(imd)
            try:
                await db.flush()  # ID für Provenance-Audit-Log-Eintrag
            except Exception as e:
                logger.error(f"Monatsabschluss flush Investition {inv_werte.investition_id} fehlgeschlagen: {type(e).__name__}: {e}")
                raise HTTPException(
                    status_code=500,
                    detail=f"Fehler beim Speichern der Investition {inv_werte.investition_id}: {e}"
                )

        # Felder in verbrauch_daten via Resolver — pro Sub-Key, damit ein
        # paralleler Cloud-Sync die manuell gepflegten Felder NICHT
        # überschreiben kann (P3 Akzeptanz Risiko #1).
        # Rejected Writes sammeln (FrodoVDR #251 Folge): bisher gingen
        # Schreibversuche, die wegen höherwertiger bestehender Quelle
        # abgelehnt wurden, still durch — User sah „erfolgreich gespeichert"
        # aber Werte unverändert. Jetzt: rejected_fields → Warnung im Result.
        inv_label = f"Investition {inv_werte.investition_id}"
        for feld_wert in inv_werte.felder:
            res = await write_json_subkey_with_provenance(
                db, imd, "verbrauch_daten", feld_wert.feld, feld_wert.wert,
                source="manual:form", writer=_WIZARD_WRITER,
            )
            if not res.applied and res.decision == "rejected_lower_priority":
                alle_warnungen.append(WarnungResponse(
                    typ="schreibschutz_aktiv",
                    schwere="warning",
                    meldung=(
                        f"{inv_label} – {feld_wert.feld}: Eintrag wurde nicht "
                        f"übernommen, weil bereits ein Wert höherer Quelle "
                        f"({res.conflicting_source}) existiert."
                    ),
                    details={
                        "investition_id": inv_werte.investition_id,
                        "feld": feld_wert.feld,
                        "konflikt_quelle": res.conflicting_source,
                        "hinweis": (
                            "Über Wartung → Reparatur-Werkbank → 'Daten-Quellen-"
                            "Konflikte auflösen' können konfliktierende Cloud-/"
                            "Import-Quellen zurückgesetzt werden, danach greift "
                            "die manuelle Eingabe."
                        ),
                    },
                ))

        # Sonstige Positionen (Erträge & Ausgaben) — landen als ein Sub-Key
        # mit Listen-Wert, ebenfalls über den Resolver.
        if inv_werte.sonstige_positionen is not None:
            gueltige = [
                p for p in inv_werte.sonstige_positionen
                if isinstance(p, dict) and p.get("betrag", 0) > 0 and str(p.get("bezeichnung", "")).strip()
            ]
            res = await write_json_subkey_with_provenance(
                db, imd, "verbrauch_daten", "sonstige_positionen", gueltige,
                source="manual:form", writer=_WIZARD_WRITER,
            )
            if not res.applied and res.decision == "rejected_lower_priority":
                alle_warnungen.append(WarnungResponse(
                    typ="schreibschutz_aktiv",
                    schwere="warning",
                    meldung=(
                        f"{inv_label} – Sonstige Positionen: Eintrag wurde nicht "
                        f"übernommen, weil bereits ein Wert höherer Quelle "
                        f"({res.conflicting_source}) existiert."
                    ),
                    details={
                        "investition_id": inv_werte.investition_id,
                        "feld": "sonstige_positionen",
                        "konflikt_quelle": res.conflicting_source,
                    },
                ))

        try:
            await db.flush()
        except Exception as e:
            logger.error(f"Monatsabschluss flush Investition {inv_werte.investition_id} fehlgeschlagen: {type(e).__name__}: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Fehler beim Speichern der Investition {inv_werte.investition_id}: {e}"
            )
        inv_ids.append(imd.id)

    try:
        await db.commit()
    except Exception as e:
        logger.error(f"Monatsabschluss commit fehlgeschlagen: {type(e).__name__}: {e}")
        raise HTTPException(status_code=500, detail=f"Fehler beim Commit: {e}")

    # MQTT, Energie-Profil Rollup und Community Auto-Share im Hintergrund
    background_tasks.add_task(
        _post_save_hintergrund,
        anlage_id=anlage_id,
        jahr=jahr,
        monat=monat,
        monatsdaten_dict={
            "jahr": jahr,
            "monat": monat,
            "einspeisung_kwh": daten.einspeisung_kwh,
            "netzbezug_kwh": daten.netzbezug_kwh,
        },
        community_auto_share=bool(anlage.community_auto_share),
        community_hash=anlage.community_hash,
    )

    await log_activity(
        kategorie="monatsabschluss",
        aktion=f"Monatsabschluss {MONAT_NAMEN[monat]} {jahr} gespeichert",
        erfolg=True,
        anlage_id=anlage_id,
    )

    return MonatsabschlussResult(
        success=True,
        message=f"Monatsdaten für {MONAT_NAMEN[monat]} {jahr} gespeichert",
        monatsdaten_id=monatsdaten_id,
        investition_monatsdaten_ids=inv_ids,
        warnungen=alle_warnungen,
    )
