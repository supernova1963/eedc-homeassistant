"""
Korrekturprofil-Endpoints.

Bündelt Endpoints rund um das Korrekturprofil-Konzept:
- Wetter-Backfill aus Open-Meteo Archive
- Wetter-Stratifizierung als interne EEDC-Diagnose
- (später) Korrekturprofil-Status und Heatmap-Daten

Siehe `docs/KONZEPT-KORREKTURPROFIL.md` für Architektur und Reihenfolge.
"""

from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database import get_db
from backend.models.anlage import Anlage
from backend.models.tages_energie_profil import TagesEnergieProfil, TagesZusammenfassung
from backend.services.wetter.utils import (
    WETTERKLASSEN,
    Wetterklasse,
    klassifiziere_stunde,
)
from backend.services.wetter_backfill_service import (
    DEFAULT_MAX_TAGE,
    wetter_backfill_anlage,
)

router = APIRouter()


class WetterBackfillResponse(BaseModel):
    status: str  # "ok" | "skipped" | "error"
    grund: Optional[str] = None
    fehler: Optional[str] = None
    tage_geupdated: Optional[int] = None
    stunden_geupdated: Optional[int] = None
    von: Optional[str] = None
    bis: Optional[str] = None


@router.post(
    "/{anlage_id}/wetter-backfill",
    response_model=WetterBackfillResponse,
)
async def wetter_backfill_endpoint(
    anlage_id: int,
    max_tage: int = Query(
        DEFAULT_MAX_TAGE,
        ge=1,
        le=2000,
        description="Maximale Rückwärts-Tiefe in Tagen (Default 730 = 2 Jahre)",
    ),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Stößt einen Wetter-Backfill aus Open-Meteo Archive an.

    Strikt additiv — füllt nur fehlende Wetter-Felder
    (`bewoelkung_prozent`, `niederschlag_mm`, `wetter_code`) in
    `TagesEnergieProfil`. Bestehende Werte bleiben unangetastet.

    Idempotent: mehrfacher Aufruf ohne Effekt, sobald alle Felder gefüllt sind.
    """
    result = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    anlage = result.scalar_one_or_none()
    if not anlage:
        raise HTTPException(status_code=404, detail="Anlage nicht gefunden")

    return await wetter_backfill_anlage(anlage, db, max_tage=max_tage)


# ── Wetter-Stratifizierung — interne EEDC-Diagnose ──────────────────────────


class StratifizierungEintrag(BaseModel):
    """MAE/MBE pro Wetterklasse oder pro (Stunde × Wetterklasse).

    MAE = Mean Absolute Error in % vom IST
    MBE = Mean Bias Error in % vom IST (vorzeichenbehaftet)
    """
    stunden_count: int = 0
    mae_pct: Optional[float] = None
    mbe_pct: Optional[float] = None


class StratifizierungResponse(BaseModel):
    """Wetter-stratifizierte Genauigkeit der EEDC-Tagesprognose.

    Pro Wetter-Klasse aggregierte Stunden-Statistik plus optional
    aufgeschlüsselt pro Stunde im Tagesgang. Datenbasis: stündliches IST
    aus TagesEnergieProfil + Day-Ahead-Prognose-Stundenprofil aus
    TagesZusammenfassung.

    Strikt EEDC-intern (kein Quellen-Vergleich, siehe Tom-HA-Versprechen).
    """
    anlage_id: int
    tage_zeitraum: int
    stunden_klassifiziert: int
    # Day-Ahead-Snapshots im Zeitraum (aus TagesZusammenfassung).
    tage_mit_prognose: int
    # Tage mit Day-Ahead-Snapshot, aber ohne irgendeine klassifizierbare
    # Stunde — typisch wenn Wetter-Backfill noch nicht gelaufen ist.
    tage_ohne_wetter: int
    # Unabhängig vom Stundenprofil: Anzahl der Tage im Zeitraum mit
    # mindestens einer TagesEnergieProfil-Zeile ohne Wetter-Spalten.
    # Dieses Feld treibt den Backfill-Button im UI — sodass der Trigger
    # auch dann erscheint, wenn Day-Ahead-Snapshots (noch) fehlen.
    tep_tage_ohne_wetter: int
    pro_klasse: dict[str, StratifizierungEintrag]
    # Schlüssel: "klar.7", "klar.8", ... — JSON-konform und einfach im Frontend
    # zu pivottieren. Nur Stunden 5-21 werden gefüllt (Tageslicht).
    pro_klasse_stunde: dict[str, StratifizierungEintrag]


def _aggregiere_eintrag(rel_errors: list[float]) -> StratifizierungEintrag:
    """rel_errors enthält (ist - prog) / ist als signed Werte."""
    if not rel_errors:
        return StratifizierungEintrag(stunden_count=0)
    n = len(rel_errors)
    mae = sum(abs(e) for e in rel_errors) / n * 100
    mbe = sum(rel_errors) / n * 100
    return StratifizierungEintrag(
        stunden_count=n,
        mae_pct=round(mae, 2),
        mbe_pct=round(mbe, 2),
    )


@router.get(
    "/{anlage_id}/stratifizierung",
    response_model=StratifizierungResponse,
)
async def stratifizierung_endpoint(
    anlage_id: int,
    tage: int = Query(90, ge=7, le=730, description="Auswertungs-Zeitraum in Tagen"),
    db: AsyncSession = Depends(get_db),
) -> StratifizierungResponse:
    """
    Wetter-stratifizierte Stunden-Genauigkeit der EEDC-Tagesprognose.

    Vergleicht die Day-Ahead-Stundenprognose (`pv_prognose_stundenprofil`)
    mit dem stündlichen IST (`TagesEnergieProfil.pv_kw`) und schlüsselt
    den Fehler nach Wetter-Klasse (klar/diffus/wechselhaft) auf.
    """
    result = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    anlage = result.scalar_one_or_none()
    if not anlage:
        raise HTTPException(status_code=404, detail="Anlage nicht gefunden")

    heute = date.today()
    von = heute - timedelta(days=tage)

    # TagesEnergieProfil-Tage mit fehlendem Wetter zählen — unabhängig von
    # Day-Ahead-Snapshots. Treibt im Frontend den "Wetter-Historie nachladen"-
    # Empty-State, auch wenn pv_prognose_stundenprofil noch nicht gefüllt ist.
    tep_ohne_wetter_query = await db.execute(
        select(TagesEnergieProfil.datum)
        .where(
            and_(
                TagesEnergieProfil.anlage_id == anlage_id,
                TagesEnergieProfil.datum >= von,
                TagesEnergieProfil.datum < heute,
                TagesEnergieProfil.bewoelkung_prozent.is_(None),
            )
        )
        .distinct()
    )
    tep_tage_ohne_wetter = len({r[0] for r in tep_ohne_wetter_query.all()})

    # Day-Ahead-Prognose-Stundenprofile laden
    tz_query = await db.execute(
        select(TagesZusammenfassung.datum, TagesZusammenfassung.pv_prognose_stundenprofil)
        .where(
            and_(
                TagesZusammenfassung.anlage_id == anlage_id,
                TagesZusammenfassung.datum >= von,
                TagesZusammenfassung.datum < heute,
                TagesZusammenfassung.pv_prognose_stundenprofil.isnot(None),
            )
        )
    )
    prognose_pro_tag: dict[date, list[float]] = {}
    for tz_datum, profil in tz_query.all():
        if isinstance(profil, list) and len(profil) == 24:
            prognose_pro_tag[tz_datum] = profil

    if not prognose_pro_tag:
        return StratifizierungResponse(
            anlage_id=anlage_id,
            tage_zeitraum=tage,
            stunden_klassifiziert=0,
            tage_mit_prognose=0,
            tage_ohne_wetter=0,
            tep_tage_ohne_wetter=tep_tage_ohne_wetter,
            pro_klasse={k: StratifizierungEintrag(stunden_count=0) for k in WETTERKLASSEN},
            pro_klasse_stunde={},
        )

    # Stündliches IST + Wetter laden für die gleichen Tage
    tep_query = await db.execute(
        select(
            TagesEnergieProfil.datum,
            TagesEnergieProfil.stunde,
            TagesEnergieProfil.pv_kw,
            TagesEnergieProfil.bewoelkung_prozent,
            TagesEnergieProfil.niederschlag_mm,
            TagesEnergieProfil.wetter_code,
        ).where(
            and_(
                TagesEnergieProfil.anlage_id == anlage_id,
                TagesEnergieProfil.datum.in_(list(prognose_pro_tag.keys())),
            )
        )
    )

    # Rel-Error sammeln pro Klasse und pro (Klasse, Stunde)
    rel_pro_klasse: dict[Wetterklasse, list[float]] = {k: [] for k in WETTERKLASSEN}
    rel_pro_klasse_stunde: dict[tuple[Wetterklasse, int], list[float]] = {}
    # Pro-Tag-Tracking für Empty-State-Diagnose
    tage_mit_klassifikation: set[date] = set()

    for tep_datum, stunde, pv_kw, bw, ns, wc in tep_query.all():
        if pv_kw is None or pv_kw < 0.05:
            continue  # Nacht / Sensor-Lücke / unter Mess-Schwelle
        prognose_profil = prognose_pro_tag.get(tep_datum)
        if not prognose_profil:
            continue
        prog = prognose_profil[stunde] if 0 <= stunde < 24 else None
        if prog is None or prog < 0.05:
            continue
        klasse = klassifiziere_stunde(bw, ns, wc)
        if klasse is None:
            continue

        # rel_error vorzeichenbehaftet: positiv = IST > Prognose (Prognose unterschätzt)
        rel = (pv_kw - prog) / pv_kw
        rel_pro_klasse[klasse].append(rel)
        key = (klasse, stunde)
        rel_pro_klasse_stunde.setdefault(key, []).append(rel)
        tage_mit_klassifikation.add(tep_datum)

    pro_klasse = {
        k: _aggregiere_eintrag(rel_pro_klasse[k]) for k in WETTERKLASSEN
    }
    pro_klasse_stunde = {
        f"{k}.{h}": _aggregiere_eintrag(errors)
        for (k, h), errors in rel_pro_klasse_stunde.items()
    }
    stunden_total = sum(e.stunden_count for e in pro_klasse.values())
    tage_ohne_wetter = len(prognose_pro_tag) - len(tage_mit_klassifikation)

    return StratifizierungResponse(
        anlage_id=anlage_id,
        tage_zeitraum=tage,
        stunden_klassifiziert=stunden_total,
        tage_mit_prognose=len(prognose_pro_tag),
        tage_ohne_wetter=tage_ohne_wetter,
        tep_tage_ohne_wetter=tep_tage_ohne_wetter,
        pro_klasse=pro_klasse,
        pro_klasse_stunde=pro_klasse_stunde,
    )
