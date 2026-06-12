"""eedc-eigene PV-Prognose mit Korrekturprofil-Kaskade — gemeinsamer Pfad.

Single Source of Truth für die eedc-Tagesprognose (heute + Folgetage):
OpenMeteo-GTI-Stundenprofil × Korrekturprofil-Kaskade pro Stunde
(``korrekturprofil_lookup``: sonnenstand_wetter → stunde → sonnenstand →
Skalar), Legacy-Skalar ``_get_lernfaktor`` als Fallback bei Kaskaden-Miss.
Tageswert = Σ korrigierte Export-Slots (Invariante, ``prognose_korrektur``).

Konsumenten:
  - ``services/ha_export_prognose.py`` — HA-Export-Sensoren #150
  - ``api/routes/prognosen.py`` — Spalte „eedc" im Prognosen-Vergleich

Beide zeigen damit per Konstruktion denselben Tageswert
([[feedback_aggregator_symmetrie]] — Symmetrie-Test in
``tests/test_eedc_prognose_kaskade.py``).

Der Live-Pfad (``live_wetter.py``) bleibt unangetastet — er skaliert GTI
(W/m²) statt Energie-Slots und war bereits auf der Kaskade.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

from sqlalchemy import select

from backend.core.berechnungen.prognose_korrektur import (
    KorrigiertesTagesprofil,
    korrigiere_tagesprofil,
)
from backend.models.investition import Investition
from backend.models.pvgis_prognose import PVGISPrognose
from backend.services.korrekturprofil_lookup import korrekturfaktoren_fuer_tag

logger = logging.getLogger(__name__)


@dataclass
class EedcPrognoseTag:
    """eedc-Prognose eines Tages (Offset ab heute)."""

    datum: str
    # Korrigiertes Stundenprofil; None wenn keine Stunden-Basis vorliegt
    # (z. B. OpenMeteo-Tagessummen-Schätzpfad ohne Hourly-Daten).
    profil: Optional[KorrigiertesTagesprofil]
    # Tageswert: aus dem Profil (= Σ Export-Slots) oder — ohne Stunden-Basis —
    # Tages-Ertrag × Skalar-Fallback (bisheriges Verhalten).
    tageswert_kwh: Optional[float]


@dataclass
class EedcPrognose:
    """eedc-Prognose über mehrere Tage. ``tage[i]`` = heute + i Tage."""

    tage: list[Optional[EedcPrognoseTag]]
    skalar_fallback: Optional[float]  # Legacy-Lernfaktor (Diagnose/Fallback)


async def berechne_eedc_prognose(
    db,
    anlage,
    days: int = 4,
    skip_jitter: bool = False,
) -> Optional[EedcPrognose]:
    """Berechnet die kaskaden-korrigierte eedc-Prognose einer Anlage.

    Quellen-Regel #150: IMMER nur die eedc-eigene Prognose (OpenMeteo-Basis),
    nie Solcast/SFML — unabhängig von der gewählten Anzeige-Quelle.

    Returns ``None`` bei fehlenden Koordinaten, fehlender PV-Leistung oder
    fehlgeschlagenem OpenMeteo-Abruf.
    """
    if not anlage.latitude or not anlage.longitude:
        return None

    from backend.services.solar_forecast_service import get_solar_prognose
    from backend.services.pv_orientation import (
        get_pv_kwp,
        get_pv_neigung,
        get_pv_azimut,
        resolve_system_losses,
    )
    # Function-local: live_wetter zieht beim Import viele Services nach.
    from backend.api.routes.live_wetter import _get_lernfaktor

    heute = date.today()

    # Aktive PV-/Balkonkraftwerk-Module — kWp + dominante Orientierung
    # (gleicher Pfad wie die Tagesprognose in energie_profil/views.py).
    res = await db.execute(
        select(Investition).where(
            Investition.anlage_id == anlage.id,
            Investition.typ.in_(["pv-module", "balkonkraftwerk"]),
            Investition.aktiv.is_(True),
        )
    )
    invs = [
        i for i in res.scalars().all()
        if not i.stilllegungsdatum or i.stilllegungsdatum >= heute
    ]
    kwp = sum(get_pv_kwp(i) for i in invs)
    if kwp <= 0:
        kwp = anlage.leistung_kwp or 0.0
    if kwp <= 0:
        return None

    pvgis_res = await db.execute(
        select(PVGISPrognose).where(
            PVGISPrognose.anlage_id == anlage.id,
            PVGISPrognose.ist_aktiv == True,  # noqa: E712 (SQLAlchemy-Vergleich)
        ).order_by(PVGISPrognose.abgerufen_am.desc()).limit(1)
    )
    system_losses = resolve_system_losses(pvgis_res.scalar_one_or_none())
    neigung = get_pv_neigung(invs[0]) if invs else 35
    azimut = get_pv_azimut(invs[0]) if invs else 0

    # eedc-Basis = OpenMeteo-GTI; Tag 0..days-1 (heute + Folgetage)
    prognose = await get_solar_prognose(
        latitude=anlage.latitude,
        longitude=anlage.longitude,
        kwp=kwp,
        neigung=neigung,
        ausrichtung=azimut,
        days=days,
        system_losses=system_losses,
        skip_jitter=skip_jitter,
    )
    if not prognose or not prognose.tageswerte:
        return None

    # Legacy-Skalar als Fallback für Kaskaden-Miss-Stunden (z. B. frisch
    # installierte Anlagen ohne aggregierte Profile).
    skalar = await _get_lernfaktor(anlage.id, db)

    by_datum = {t.datum: t for t in prognose.tageswerte}
    tage: list[Optional[EedcPrognoseTag]] = []
    for offset in range(days):
        datum = heute + timedelta(days=offset)
        tag = by_datum.get(datum.isoformat())
        if tag is None:
            tage.append(None)
            continue

        # getattr-robust: alte/fremde Strukturen ohne die neuen Wetter-Felder
        # (persistenter Cache + Versions-Skew) → Klasse None, Kaskade greift
        # ab Stufe `stunde`.
        stunden_kw = getattr(tag, "stunden_kw", None)
        if stunden_kw and any(v for v in stunden_kw):
            faktoren = await korrekturfaktoren_fuer_tag(
                db,
                anlage_id=anlage.id,
                lat=anlage.latitude,
                lon=anlage.longitude,
                datum=datum,
                stunden_bewoelkung=getattr(tag, "stunden_bewoelkung", None),
                stunden_niederschlag=getattr(tag, "stunden_niederschlag", None),
                stunden_wetter_code=getattr(tag, "stunden_wetter_code", None),
            )
            profil = korrigiere_tagesprofil(stunden_kw, faktoren, fallback_faktor=skalar)
            tage.append(EedcPrognoseTag(
                datum=tag.datum,
                profil=profil,
                tageswert_kwh=profil.tageswert_kwh,
            ))
        else:
            # Keine Stunden-Basis (OpenMeteo-Schätzpfad aus Tagessumme) →
            # bisheriges Verhalten: Tages-Ertrag × Skalar, kein Profil.
            tageswert = None
            if tag.pv_ertrag_kwh is not None:
                tageswert = round(tag.pv_ertrag_kwh * (skalar or 1.0), 1)
            tage.append(EedcPrognoseTag(
                datum=tag.datum, profil=None, tageswert_kwh=tageswert,
            ))

    return EedcPrognose(tage=tage, skalar_fallback=skalar)
