"""eedc-eigene PV-Prognose-Werte für den HA-Export (#150 Slice A).

Liefert die Vorausschau-Sensoren für `calculate_anlage_sensors()`:
  - Tagesprognose heute — der **kanonische** eedc-Tageswert (= persistierter
    `pv_prognose_kwh` = Cockpit/Aussicht/Kurzfrist/Vergleich-eedc), rollt
    intraday mit OpenMeteo mit. **Ein Wert überall** (Prognose-Kanon-Fix V3):
    der frühere MQTT-„heute" (IST bisher + Rest) war genau die Inkonsistenz
    aus Rainers PN 2026-06-26 (MQTT 76,8 ≠ Anzeige 75,3) und entfällt.
  - Rest-Ertrag heute (NUR Σ Prognose der verbleibenden Stunden) — aus
    DEMSELBEN Kanon-Helper wie „heute", damit beide synchron mit OM rollen.
  - Tagesprognose morgen / übermorgen / in 3 Tagen
  - „Speicher voll um" (SoC-Simulation ab AKTUELLEM Speicherstand)
  - die eedc-Stundenprofile heute + Tag+1/2/3 (als Sensor-Attribut, kein
    eigenes Topic)

Prognose-Basis: ``services/prognose_kanon.py`` (Multi-String-Fan-out +
eedc-Korrektur pro Energie-Slot), Tageswert = Σ korrigierte Stunden-Slots
(Invariante: Sensor-State == Σ Attribut-Slots). Identischer Kanon wie die
„eedc"-Spalte im Prognosen-Vergleich und der Live-/Persistenz-Pfad.

Quellen-Regel (Export-Rahmen): es wird IMMER nur die **eedc-eigene** Prognose
exportiert — nie Solcast/SFML, die liegen via eigene HA-Integration schon in
HA. Die gewählte Anzeige-Quelle der Anlage ist hier deshalb bewusst
irrelevant.

Robustheit: fehlende Koordinaten / keine PV / Netzwerkfehler → ``None``; die
Sensoren entfallen dann lautlos (Export bleibt für die übrigen Sensoren grün).
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

from sqlalchemy import select

from backend.core.investition_kennwerte import aggregiere_speicher_basis
from backend.models.investition import Investition
from backend.models.tages_energie_profil import TagesEnergieProfil

logger = logging.getLogger(__name__)

_BERLIN_TZ = ZoneInfo("Europe/Berlin")


async def berechne_prognose_export(db, anlage) -> Optional[dict]:
    """Berechnet die eedc-eigenen PV-Prognose-Exportwerte einer Anlage.

    Returns:
        dict mit ``heute_kwh`` (kanonische eedc-Tagesprognose, rollt mit den
        OpenMeteo-Aktualisierungen — **nicht** IST bisher + Rest),
        ``rest_today_kwh`` (verbleibende Stunden ab jetzt, laufende Stunde
        anteilig nach verstrichenen Minuten, #339), ``day_plus_1_kwh``,
        ``day_plus_2_kwh``, ``day_plus_3_kwh``, ``speicher_voll_um``
        (str "HH:00" | None), ``verbrauch_heute_kwh`` (Σ des Live-Verbrauchsprofils,
        nur aus einem individuellen Profil — sonst None, #395), ``stundenprofil_heute`` und
        ``stundenprofil_day_plus_1/2/3`` (je 24 kWh-Slots) — oder ``None``.
    """
    try:
        from backend.services.prognose_kanon import kanon_tagesprognose
        from backend.services.verbrauch_prognose_service import get_verbrauch_prognose
        from backend.core.berechnungen.speicher_simulation import simuliere_speicher_tag

        heute = date.today()

        prognose = await kanon_tagesprognose(db, anlage, days=4)
        if not prognose:
            return None

        def _tageswert(offset: int) -> Optional[float]:
            tag = prognose.tage[offset] if offset < len(prognose.tage) else None
            return tag.eedc_kwh if tag else None

        def _haelften(offset: int) -> tuple[Optional[float], Optional[float]]:
            """Vormittag/Nachmittag desselben Tages — am **Solar Noon** (#395/3).

            ⛔ **Die öffentliche Zusage in #395 nannte einen festen 13-Uhr-Schnitt
            und behauptete, das sei „die Aufteilung, die auf deinem Bildschirm
            steht". Beides ist am Code falsch** (Fund N-331, gemessen 27.08.):
            eedc schneidet an **allen** drei rechnenden Stellen am Solar Noon —
            `solar_forecast_service:829`, `prognose_kanon::vm_nm_split` und
            `prognosen.py::_berechne_tageshaelfte` (für alle vier Quellen).
            Quelle des Irrtums war ein veralteter Feldkommentar
            (`prognosen.py:95`, „0:00–12:59"), der drei Zeilen über der Funktion
            steht, die es anders macht.

            **Der Sensor folgt der Anzeige, nicht der Zusage** — sonst stünden
            wieder zwei Zahlen für dieselbe Größe auf einer Seite, genau die
            Klasse, die der Prognose-Kanon in v4.0.1 beseitigt hat.

            ⭐ **Der Einwand aus der Zusage bleibt trotzdem beantwortet:** dass
            eine bewegliche Grenze eine Automation an zwei Tagen verschieden
            entscheiden lässt, stimmt — deshalb reist die Grenze als Attribut
            `solar_noon` mit, statt geraten werden zu müssen.
            """
            tag = prognose.tage[offset] if offset < len(prognose.tage) else None
            if tag is None:
                return None, None
            return tag.vm_kwh, tag.nm_kwh

        def _stundenprofil(offset: int) -> Optional[list]:
            tag = prognose.tage[offset] if offset < len(prognose.tage) else None
            if tag is None or tag.profil is None:
                return None
            return list(tag.profil.stundenprofil_export_kwh)

        heute_tag = prognose.tage[0] if prognose.tage else None
        stunden_kwh_heute = (
            list(heute_tag.profil.stunden_kwh)
            if heute_tag and heute_tag.profil
            else [0.0] * 24
        )

        # „heute" = kanonischer eedc-Tageswert (= Anzeige/Persistenz, rollt mit
        # OM). „Rest heute" + „heute" aus DEMSELBEN Kanon-Helper (§5.4).
        now = datetime.now(_BERLIN_TZ)
        heute_kwh = heute_tag.eedc_kwh if heute_tag else None
        # Rest NUR aus dem Kanon (#339: laufende Stunde anteilig). Ohne Profil ist
        # `stunden_kwh_heute` ohnehin [0.0]*24 — eine zweite Rest-Formel hier wäre
        # eine zweite Wahrheit, die beim nächsten Konventionswechsel driftet.
        rest_today = prognose.rest_heute_kwh if prognose.rest_heute_kwh is not None else 0.0

        # „Speicher voll um" — Simulation ab aktuellem SoC (nicht Mitternacht).
        speicher_voll_um = None
        speicher_kap, speicher_eta, akt_soc = await _aktueller_speicher(
            db, anlage.id, heute
        )
        if speicher_kap > 0 and akt_soc is not None:
            vp = await get_verbrauch_prognose(anlage.id, heute, db)
            verbrauch_stunden = vp["stunden_kw"] if vp else [0.0] * 24
            sim = simuliere_speicher_tag(
                pv_stunden=stunden_kwh_heute,
                verbrauch_stunden=verbrauch_stunden,
                speicher_kap_kwh=speicher_kap,
                start_soc_prozent=akt_soc,
                start_stunde=now.hour,
                wirkungsgrad_prozent=speicher_eta,
            )
            speicher_voll_um = sim.speicher_voll_um

        # #395 (OB73-gif): die Verbrauchsprognose des Tages — dieselbe Zahl wie
        # die Kachel in Cockpit → Live, aus demselben Dienst. `None` ohne
        # individuelles Profil (kein Sensor aus einem Standardprofil, N-332).
        from backend.services.verbrauchsprognose_heute import verbrauchsprognose_heute
        verbrauch = await verbrauchsprognose_heute(anlage, db)

        return {
            "heute_kwh": heute_kwh,
            "rest_today_kwh": rest_today,
            # rapahl-PN 2026-08-23: IST bisher + Rest — die nachgeführte
            # Tageszahl. Sie steht NEBEN `heute_kwh`, nicht an dessen Stelle:
            # jener bleibt der kanonische Wert, der in App, MQTT und Persistenz
            # dieselbe Zahl trägt (Prognose-Kanon-Fix V3). Wer die beiden
            # verwechselt, hat wieder zwei Wahrheiten — deshalb heißt der Sensor
            # ausdrücklich „(nachgeführt)".
            "heute_rollend_kwh": prognose.heute_rollend_kwh,
            "ist_bisher_kwh": prognose.ist_bisher_kwh,
            "heute_vormittag_kwh": _haelften(0)[0],
            "heute_nachmittag_kwh": _haelften(0)[1],
            "morgen_vormittag_kwh": _haelften(1)[0],
            "morgen_nachmittag_kwh": _haelften(1)[1],
            # Die Schnittgrenze selbst — als „HH:MM" für heute. Sie ist die
            # Antwort auf „wann genau teilt ihr?", und ohne sie müsste eine
            # Automation sie schätzen.
            "solar_noon_heute": _solar_noon_text(heute, anlage.longitude),
            "solar_noon_morgen": _solar_noon_text(heute + timedelta(days=1), anlage.longitude),
            "day_plus_1_kwh": _tageswert(1),
            "day_plus_2_kwh": _tageswert(2),
            "day_plus_3_kwh": _tageswert(3),
            "speicher_voll_um": speicher_voll_um,
            "verbrauch_heute_kwh": verbrauch.summe_kwh if verbrauch else None,
            "verbrauch_profil_typ": verbrauch.profil_typ if verbrauch else None,
            "verbrauch_profil_tage": verbrauch.profil_tage if verbrauch else None,
            "verbrauch_profil_slots": verbrauch.profil_slots if verbrauch else None,
            "stundenprofil_heute": [round(v, 2) for v in stunden_kwh_heute],
            "stundenprofil_day_plus_1": _stundenprofil(1),
            "stundenprofil_day_plus_2": _stundenprofil(2),
            "stundenprofil_day_plus_3": _stundenprofil(3),
        }
    except Exception as e:  # Export bleibt für die übrigen Sensoren grün
        logger.warning(
            "HA-Export PV-Prognose fehlgeschlagen (Anlage %s): %s: %s",
            getattr(anlage, "id", "?"), type(e).__name__, e,
        )
        return None


def _solar_noon_text(tag: date, longitude: Optional[float]) -> Optional[str]:
    """Solar Noon dieses Tages als „HH:MM" — dieselbe Quelle wie der Schnitt.

    Bewusst über `_solar_noon_hour` und nicht über eine eigene Formel: die
    Grenze im Attribut MUSS dieselbe sein, an der die beiden Zahlen daneben
    getrennt wurden. Eine zweite Berechnung wäre die nächste zweite Wahrheit.
    """
    if longitude is None:
        return None
    from backend.services.solar_forecast_service import _solar_noon_hour

    noon = _solar_noon_hour(tag.isoformat(), longitude)
    h = int(noon)
    return f"{h:02d}:{int((noon - h) * 60):02d}"


async def _aktueller_speicher(
    db, anlage_id: int, heute: date
) -> tuple[float, float, Optional[float]]:
    """(Speicher-Kapazität kWh, Wirkungsgrad %, aktueller SoC %).

    Der „aktuelle SoC" ist der zuletzt gespeicherte Stunden-SoC (heute, sonst
    gestern) aus ``TagesEnergieProfil`` — robust und ohne Live-Abhängigkeit.
    """
    res = await db.execute(
        select(Investition).where(
            Investition.anlage_id == anlage_id,
            Investition.typ == "speicher",
            Investition.aktiv.is_(True),
        )
    )
    speicher = [
        i for i in res.scalars().all()
        if not i.stilllegungsdatum or i.stilllegungsdatum >= heute
    ]
    # A31-2/E18: NETTO wie im Planungs-Tab. Der Sensor `eedc_speicher_voll_um`
    # und die KPI-Kachel „Speicher voll" tragen denselben Namen und dieselbe
    # Simulation — sie dürfen nicht auf verschiedenen Kapazitäten laufen. Seit
    # N-238 gilt das auch für den **Wirkungsgrad**, deshalb der geteilte Helper
    # statt zweier gleichlautender Faltungen.
    # (Der abweichende Start-SoC und die abweichende Start-Stunde bleiben
    # bewusst, s. Modul-Docstring von `speicher_simulation`.)
    kap, eta = aggregiere_speicher_basis(speicher)
    if not kap:
        return 0.0, eta, None

    soc_res = await db.execute(
        select(TagesEnergieProfil.soc_prozent).where(
            TagesEnergieProfil.anlage_id == anlage_id,
            TagesEnergieProfil.datum >= heute - timedelta(days=1),
            TagesEnergieProfil.soc_prozent.isnot(None),
        ).order_by(
            TagesEnergieProfil.datum.desc(), TagesEnergieProfil.stunde.desc()
        ).limit(1)
    )
    return float(kap), eta, soc_res.scalar_one_or_none()
