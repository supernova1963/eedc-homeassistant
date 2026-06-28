"""Prognose-Kanon — EIN kanonischer Rechenweg für die PV-Tagesprognose.

Single Source of Truth für „PV-Tagesprognose heute (+ Rest, + morgen/
übermorgen, + VM/NM, + Stundenprofil)". Vor diesem Service holten vier Pfade
(``live_wetter``, ``solar_forecast_service``, ``eedc_prognose_service``,
``ha_export_prognose``) OpenMeteo je eigenständig, korrigierten an
verschiedenen Stellen (GTI vs. Energie-Slot) und mit verschiedenen
losses-Quellen → vier verschiedene „heute"-Werte (Rainer-PN 2026-06-26).

Bau-Vertrag: ``docs/drafts/KONZEPT-PROGNOSE-KANON.md``.

Kanon-Rechenweg (abgenommen):

1. **Orientierungsgruppen** (``pv_orientation.orientierungs_gruppen``) — Multi-
   String-Fan-out wie der Live-Pfad: pro Gruppe ein OpenMeteo-Abruf
   (``get_solar_prognose``, PVGIS-Losses via ``resolve_system_losses``).
2. **Gruppen slot-weise summieren** → rohes OM-kWh-Stundenprofil/Tag
   (= „OpenMeteo"-Spalte überall, multi-string, unkorrigiert).
3. **eedc-Korrektur PRO ENERGIE-SLOT** (``korrigiere_tagesprofil`` +
   Kaskade ``korrekturfaktoren_fuer_tag``): GTI bleibt voll im Basismodell
   (GTI→kWh mit Temp/Schnee), nur der gelernte Residual-Faktor liegt auf der
   Energie — self-consistent (Faktor = Σ IST_kWh / Σ Prognose_kWh) und
   Invariante ``tageswert == Σ Export-Slots``.
4. **VM/NM**-Split an Solar-Noon; **rest_heute**/**ist_bisher**/
   **heute_rollend** aus den korrigierten Slots + ``TagesEnergieProfil``.

Konsumenten (alle über diesen Service → per Konstruktion derselbe Wert):
``eedc_prognose_service`` (dünner Adapter), ``live_wetter`` (Anzeige +
Persistenz + Chart-Slots), ``ha_export_prognose`` (MQTT), ``api/routes/
prognosen`` (Vergleich eedc-/OM-Spalte).

Robustheit: fehlende Koordinaten/kWp/OpenMeteo → ``None``. Multi-String-
Unvollständigkeit (#306) wird pro Tag als ``om_vollstaendig=False`` markiert,
damit der Persist-Pfad einen kollabierten Tageswert NICHT einfriert.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

from sqlalchemy import select

from backend.core.berechnungen.prognose_korrektur import (
    KorrigiertesTagesprofil,
    korrigiere_tagesprofil,
)
from backend.models.investition import Investition
from backend.models.pvgis_prognose import PVGISPrognose
from backend.models.tages_energie_profil import TagesEnergieProfil
from backend.services import solar_forecast_service as sfs
from backend.services.korrekturprofil_lookup import korrekturfaktoren_fuer_tag
from backend.services.pv_orientation import (
    Orientierungsgruppe,
    get_pv_azimut,
    get_pv_neigung,
    orientierungs_gruppen,
    resolve_system_losses,
)

logger = logging.getLogger(__name__)

_BERLIN_TZ = ZoneInfo("Europe/Berlin")


@dataclass
class KanonTag:
    """Kanonische Prognose eines Tages (Offset ab heute)."""

    datum: str
    om_kwh: Optional[float]            # Multi-String roh-OM-Tagessumme (= OM-Spalte)
    eedc_kwh: Optional[float]          # korrigierte Tagessumme (= Σ Export-Slots)
    vm_kwh: Optional[float]            # eedc vor Solar-Noon
    nm_kwh: Optional[float]            # eedc ab Solar-Noon
    # Korrigiertes Stundenprofil (eedc); None im OpenMeteo-Schätzpfad ohne
    # Hourly-Basis (dann eedc_kwh = Σ Tages-Ertrag × Skalar).
    profil: Optional[KorrigiertesTagesprofil]
    om_stundenprofil_kwh: Optional[list]   # 24 roh-OM-Slots (multi-string)
    om_vollstaendig: bool             # #306: False wenn Fan-out untergewichtet


@dataclass
class KanonPrognose:
    """Kanonische Prognose über mehrere Tage. ``tage[i]`` = heute + i Tage."""

    tage: list[Optional[KanonTag]]
    rest_heute_kwh: Optional[float]    # Σ korrigierte Slots der Reststunden
    ist_bisher_kwh: Optional[float]    # IST heute bis jetzt (TagesEnergieProfil)
    heute_rollend_kwh: Optional[float]  # ist_bisher + rest_heute
    skalar_fallback: Optional[float]   # Legacy-Lernfaktor (Diagnose/Fallback)


async def _aktive_pv_invs(db, anlage, heute: date) -> list[Investition]:
    res = await db.execute(
        select(Investition).where(
            Investition.anlage_id == anlage.id,
            Investition.typ.in_(["pv-module", "balkonkraftwerk"]),
            Investition.aktiv.is_(True),
        )
    )
    return [
        i for i in res.scalars().all()
        if not i.stilllegungsdatum or i.stilllegungsdatum >= heute
    ]


async def kanon_tagesprognose(
    db,
    anlage,
    days: int = 4,
    skip_jitter: bool = False,
) -> Optional[KanonPrognose]:
    """Berechnet die kanonische PV-Tagesprognose einer Anlage.

    Quelle ist IMMER die eedc-eigene Prognose (OpenMeteo-Basis × Korrektur) —
    Solcast/SFML sind eigene Pfade. ``None`` bei fehlenden Koordinaten,
    fehlender PV-Leistung oder fehlgeschlagenem OpenMeteo-Abruf.
    """
    if not anlage.latitude or not anlage.longitude:
        return None

    heute = date.today()
    invs = await _aktive_pv_invs(db, anlage, heute)
    gruppen = orientierungs_gruppen(invs)

    if not gruppen:
        # Keine Modul-Orientierung gepflegt → eine Default-Gruppe aus der
        # Anlage-Gesamtleistung (Süd/35°), damit Bestandsanlagen ohne
        # Orientierungs-Pflege weiter eine Prognose erhalten.
        kwp = anlage.leistung_kwp or 0.0
        if kwp <= 0:
            return None
        gruppen = [Orientierungsgruppe(neigung=35, ausrichtung=0, kwp=kwp)]

    pvgis_res = await db.execute(
        select(PVGISPrognose).where(
            PVGISPrognose.anlage_id == anlage.id,
            PVGISPrognose.ist_aktiv == True,  # noqa: E712 (SQLAlchemy-Vergleich)
        ).order_by(PVGISPrognose.abgerufen_am.desc()).limit(1)
    )
    system_losses = resolve_system_losses(pvgis_res.scalar_one_or_none())

    # Fan-out: pro Orientierungsgruppe ein get_solar_prognose (eigener Cache-
    # Eintrag, parallel). Aufruf über das Modul (sfs.) — Monkeypatch-fähig.
    coros = [
        sfs.get_solar_prognose(
            latitude=anlage.latitude,
            longitude=anlage.longitude,
            kwp=g.kwp,
            neigung=g.neigung,
            ausrichtung=g.ausrichtung,
            days=days,
            system_losses=system_losses,
            skip_jitter=skip_jitter,
        )
        for g in gruppen
    ]
    ergebnisse = await asyncio.gather(*coros)
    if all(r is None or not getattr(r, "tageswerte", None) for r in ergebnisse):
        return None

    # Pro Gruppe: Tag-Index nach Datum.
    by_datum: list[dict] = []
    for r in ergebnisse:
        if r is None or not getattr(r, "tageswerte", None):
            by_datum.append({})
        else:
            by_datum.append({t.datum: t for t in r.tageswerte})

    # Legacy-Skalar (Kaskaden-Miss-Fallback). Function-local Import =
    # Monkeypatch-fähig (Tests patchen live_wetter._get_lernfaktor).
    from backend.api.routes.live_wetter import _get_lernfaktor
    skalar = await _get_lernfaktor(anlage.id, db)

    tage: list[Optional[KanonTag]] = []
    for offset in range(days):
        datum = heute + timedelta(days=offset)
        datum_iso = datum.isoformat()

        om_slots = [0.0] * 24
        pv_ertrag_sum = 0.0
        groups_present = 0
        has_hourly = False
        wetter_bew = wetter_nieder = wetter_code = None

        for grp_idx in range(len(gruppen)):
            tag = by_datum[grp_idx].get(datum_iso)
            if tag is None:
                continue
            groups_present += 1
            pv_ertrag_sum += getattr(tag, "pv_ertrag_kwh", 0.0) or 0.0
            stunden_kw = getattr(tag, "stunden_kw", None)
            if stunden_kw and any(v for v in stunden_kw):
                has_hourly = True
                for h in range(min(24, len(stunden_kw))):
                    om_slots[h] += stunden_kw[h] or 0.0
            # Wetter ist standort- (nicht orientierungs-)abhängig → erste
            # liefernde Gruppe genügt für die Kaskaden-Klassifikation.
            if wetter_bew is None:
                wetter_bew = getattr(tag, "stunden_bewoelkung", None)
                wetter_nieder = getattr(tag, "stunden_niederschlag", None)
                wetter_code = getattr(tag, "stunden_wetter_code", None)

        # #306: untergewichtet, wenn nicht alle Gruppen den Tag lieferten.
        om_vollstaendig = groups_present == len(gruppen)

        if groups_present == 0:
            tage.append(None)
            continue

        if has_hourly:
            faktoren = await korrekturfaktoren_fuer_tag(
                db,
                anlage_id=anlage.id,
                lat=anlage.latitude,
                lon=anlage.longitude,
                datum=datum,
                stunden_bewoelkung=wetter_bew,
                stunden_niederschlag=wetter_nieder,
                stunden_wetter_code=wetter_code,
            )
            profil = korrigiere_tagesprofil(om_slots, faktoren, fallback_faktor=skalar)
            eedc_kwh = profil.tageswert_kwh
            om_kwh = round(sum(om_slots), 1)
            vm_kwh, nm_kwh = _vm_nm_split(
                profil.stundenprofil_export_kwh, datum_iso, anlage.longitude
            )
        else:
            # OpenMeteo-Schätzpfad (Tagessumme ohne Hourly): Tages-Ertrag ×
            # Skalar, kein Profil (bisheriges Verhalten, eedc_prognose_service).
            profil = None
            eedc_kwh = (
                round(pv_ertrag_sum * (skalar or 1.0), 1) if pv_ertrag_sum else None
            )
            om_kwh = round(pv_ertrag_sum, 1) if pv_ertrag_sum else None
            vm_kwh = nm_kwh = None

        tage.append(KanonTag(
            datum=datum_iso,
            om_kwh=om_kwh,
            eedc_kwh=eedc_kwh,
            vm_kwh=vm_kwh,
            nm_kwh=nm_kwh,
            profil=profil,
            om_stundenprofil_kwh=[round(v, 3) for v in om_slots] if has_hourly else None,
            om_vollstaendig=om_vollstaendig,
        ))

    # Rollende „heute"-Größen aus den korrigierten Slots + IST.
    rest_heute = ist_bisher = heute_rollend = None
    heute_tag = tage[0] if tage else None
    if heute_tag is not None and heute_tag.profil is not None:
        from backend.services.prognose_adapter import ist_profil
        now = datetime.now(_BERLIN_TZ)
        slots = heute_tag.profil.stunden_kwh
        rest_heute = round(sum(slots[h] for h in range(now.hour + 1, 24)), 1)
        ist_res = await db.execute(
            select(TagesEnergieProfil).where(
                TagesEnergieProfil.anlage_id == anlage.id,
                TagesEnergieProfil.datum == heute,
            ).order_by(TagesEnergieProfil.stunde)
        )
        ist_p = ist_profil(ist_res.scalars().all(), jetzt_stunde=now.hour, datum=heute)
        ist_bisher = round(ist_p.tageswert_kwh or 0.0, 1)
        heute_rollend = round(ist_bisher + rest_heute, 1)

    return KanonPrognose(
        tage=tage,
        rest_heute_kwh=rest_heute,
        ist_bisher_kwh=ist_bisher,
        heute_rollend_kwh=heute_rollend,
        skalar_fallback=skalar,
    )


def _vm_nm_split(
    export_slots, datum_iso: str, longitude: Optional[float]
) -> tuple[Optional[float], Optional[float]]:
    """Splittet die korrigierten Export-Slots am Solar-Noon (Backward-Slots).

    Slot ``h`` = Energie im Intervall ``[h-1, h)``. Konsistent zur
    ``_berechne_tageshaelfte``-Logik im Prognosen-Vergleich.
    """
    if longitude is None:
        return None, None
    noon = sfs._solar_noon_hour(datum_iso, longitude)
    vm = 0.0
    nm = 0.0
    for h in range(24):
        wert = export_slots[h] if h < len(export_slots) else 0.0
        slot_start = h - 1
        if h <= noon:
            vm += wert
        elif slot_start >= noon:
            nm += wert
        else:
            frac_vm = max(0.0, min(1.0, noon - slot_start))
            vm += wert * frac_vm
            nm += wert * (1 - frac_vm)
    return round(vm, 1), round(nm, 1)
