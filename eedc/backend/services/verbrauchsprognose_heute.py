"""Verbrauchsprognose heute — die eine Zahl, die *Cockpit → Live* und der
HA-/MQTT-Export gemeinsam tragen (#395, OB73-gif: „Kannst Du die Prognose des
Tagesverbrauchs auch über MQTT ausgeben?").

**Was diese Zahl ist.** Die Summe des stündlichen Verbrauchsprofils, das
*Cockpit → Live* unter „Heute" als *Verbrauchsprognose* zeigt — das
**individuelle** Profil der Anlage (Werktag oder Wochenende, aus der eigenen
Historie), bei einer Wärmepumpe mit der Temperaturkorrektur aus dem Forecast.
Es ist der **Gesamt**verbrauch: Haus + Batterie + Wärmepumpe + Wallbox +
Sonstige — so steht es im Tooltip der Kachel, und so heißt es hier. Eine
Prognose nur für den Haushalt gibt es in eedc nicht; sie wäre eine zweite
Zahl, die niemand anzeigt.

**Warum ein eigener Dienst und nicht ein Griff in die Route.** Bis hierher
lebte die Profilwahl (Werktag/Wochenende, Wärmepumpen-Profil, Referenz-
temperatur) nur in ``get_live_wetter``. Der Export hätte sie ein zweites Mal
gebraucht — zwei Fassungen derselben Wahl sind die Klasse, aus der N-332
entstand (zwei „Grundlast"-Zahlen unter einem Namen). Deshalb steht die Wahl
hier **einmal**, und die Route ruft sie.

⛔ **Nur aus einem individuellen Profil, nie aus dem BDEW-Standardprofil.**
Dieselbe Regel wie beim Grundlast-Sensor (N-332): Ein Modellwert, der als
Sensor in eine Automation läuft, ist die teuerste Sorte Zahl — er sieht aus
wie eine Messung und ist eine Annahme. Ohne eigene Historie gibt es hier
**keinen** Wert und damit keinen Sensor; die Anzeige zeigt in dieser Lage
das Standardprofil und **sagt es dazu** — das kann ein Sensor nicht.

⚠ **Zwei Verbrauchsprognosen gibt es im Baum**, und das ist bekannt: Diese
hier (7-Tage-Profil des Live-Pfads) und ``verbrauch_prognose_service``
(gewichtetes 8-Wochen-Profil für *Auswertungen → Prognose* und „Speicher
voll um"). Der Sensor folgt der Zahl, die der Anwender **sieht** — der
Kachel in *Cockpit → Live*. Wer beide zusammenführen will, tut das nicht
hier (Register N-392, Verdacht).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.anlage import Anlage
from backend.models.investition import Investition
from backend.services.live_power_service import get_live_power_service
from backend.utils.investition_filter import aktiv_jetzt

logger = logging.getLogger(__name__)


@dataclass
class ProfilWahl:
    """Das für heute gewählte Verbrauchsprofil — oder das Standardprofil."""

    ind_stunden_profil: Optional[dict] = None
    profil_typ: str = "bdew_h0"  # individuell_werktag · individuell_wochenende · bdew_h0
    profil_tage: Optional[int] = None
    profil_slots: Optional[int] = None
    wp_profil: Optional[dict] = None
    referenz_temp_c: Optional[float] = None

    @property
    def ist_individuell(self) -> bool:
        return self.profil_typ.startswith("individuell")


async def waehle_verbrauchsprofil(
    anlage: Anlage,
    db: AsyncSession,
    now: datetime,
) -> ProfilWahl:
    """Wählt das Tagesprofil (Werktag/Wochenende) samt Wärmepumpen-Anteil.

    Herausgezogen aus ``get_live_wetter`` — die Route ruft diese Funktion, der
    Export auch. ``now`` kommt vom Aufrufer: die Funktion liest keine Uhr
    (N-167 — Proben, die die echte Uhr lesen, sind vier von 24 Stunden rot).
    """
    service = get_live_power_service()
    ind_profil_data = await service.get_verbrauchsprofil(anlage, db)

    wahl = ProfilWahl()
    if not ind_profil_data:
        return wahl

    ist_wochenende = now.weekday() >= 5
    if ist_wochenende and ind_profil_data.get("wochenende"):
        wahl.ind_stunden_profil = ind_profil_data["wochenende"]
        wahl.profil_typ = "individuell_wochenende"
        wahl.profil_tage = ind_profil_data["tage_wochenende"]
        wahl.profil_slots = ind_profil_data.get("slots_wochenende")
    elif not ist_wochenende and ind_profil_data.get("werktag"):
        wahl.ind_stunden_profil = ind_profil_data["werktag"]
        wahl.profil_typ = "individuell_werktag"
        wahl.profil_tage = ind_profil_data["tage_werktag"]
        wahl.profil_slots = ind_profil_data.get("slots_werktag")

    wp_key = "wp_wochenende" if ist_wochenende else "wp_werktag"
    wahl.wp_profil = ind_profil_data.get(wp_key)
    wahl.referenz_temp_c = ind_profil_data.get("referenz_temp_c")
    return wahl


@dataclass
class VerbrauchsprognoseHeute:
    """Die Tageszahl samt ihrer Grundlage — für Sensor-Attribut und Rechenweg."""

    summe_kwh: float
    profil_typ: str
    profil_tage: Optional[int]
    profil_slots: Optional[int]


def summe_verbrauchsprofil_kwh(profil: list[dict]) -> float:
    """Σ der 24 Stunden-kW = kWh des Tages — dieselbe Rechnung wie die Kachel
    (``SolarAussicht3Tage``: ``reduce((s, v) => s + v.verbrauch_kw, 0)``)."""
    return round(sum(float(p.get("verbrauch_kw") or 0.0) for p in profil), 1)


async def verbrauchsprognose_heute(
    anlage: Anlage,
    db: AsyncSession,
    now: Optional[datetime] = None,
) -> Optional[VerbrauchsprognoseHeute]:
    """Die Verbrauchsprognose für heute — ``None``, wenn es keine eigene gibt.

    ``None`` in drei Lagen, alle drei ohne Sensor: kein Standort (kein
    Forecast, keine Temperaturkorrektur — die Anzeige zeigt dann auch
    nichts), Forecast nicht erreichbar, oder **kein individuelles Profil**
    (dann stünde nur das Standardprofil zur Verfügung, s. Modul-Docstring).

    Rechnet bitgleich den Weg der Anzeige: derselbe gecachte Forecast
    (``_lade_forecast_gecached``, gleicher Cache-Schlüssel), dieselbe
    Profilwahl, dieselbe Formel (``_berechne_verbrauchsprofil``).
    """
    if not anlage.latitude or not anlage.longitude:
        return None

    now = now or datetime.now(ZoneInfo("Europe/Berlin"))
    wahl = await waehle_verbrauchsprofil(anlage, db, now)
    if not wahl.ist_individuell:
        return None

    # Lokale Importe: die Route importiert diesen Dienst — ein Import auf
    # Modulebene wäre zirkulär. Dieselbe Bauform wie `_helpers._get_wetter_ist`.
    from backend.api.routes.live_wetter import (
        _berechne_verbrauchsprofil,
        _get_pv_orientierungsgruppen,
        _lade_forecast_gecached,
        live_wetter_cache_key,
    )

    pv_result = await db.execute(
        select(Investition).where(
            Investition.anlage_id == anlage.id,
            Investition.typ.in_(["pv-module", "balkonkraftwerk"]),
            aktiv_jetzt(),
        )
    )
    gruppen = _get_pv_orientierungsgruppen(list(pv_result.scalars().all()))
    kwp = sum(g["kwp"] for g in gruppen) if gruppen else (anlage.leistung_kwp or 10.0)
    wetter_modell_key = getattr(anlage, "wetter_modell", "auto") or "auto"
    cache_key = live_wetter_cache_key(
        anlage.latitude, anlage.longitude, gruppen, wetter_modell_key
    )

    try:
        geladen = await _lade_forecast_gecached(anlage, gruppen, cache_key)
    except Exception as e:  # noqa: BLE001 — der Export darf am Wetter nicht sterben
        logger.debug("Verbrauchsprognose heute: Forecast nicht verfügbar (%s)", e)
        return None
    if geladen is None:
        return None
    data, _multi_gti, _vollstaendig = geladen
    hourly = data.get("hourly", {})
    times = hourly.get("time", [])
    temps = hourly.get("temperature_2m", [None] * len(times))

    # Für das Verbrauchsprofil zählt allein die Temperatur je Stunde (Wärme-
    # pumpen-Korrektur). GTI/GHI bleiben bewusst leer — der PV-Anteil dieser
    # Rechnung ist hier nicht die Frage und hat mit dem Kanon seine eigene SoT.
    stunden = [
        {"zeit": f"{int(t[11:13]):02d}:00", "temperatur_c": temps[i] if i < len(temps) else None}
        for i, t in enumerate(times)
    ]
    profil, _pv, _grundlast, _ist_ind = _berechne_verbrauchsprofil(
        stunden, kwp, individuelles_profil=wahl.ind_stunden_profil,
        wp_profil=wahl.wp_profil, referenz_temp_c=wahl.referenz_temp_c,
    )
    if not profil:
        return None
    return VerbrauchsprognoseHeute(
        summe_kwh=summe_verbrauchsprofil_kwh(profil),
        profil_typ=wahl.profil_typ,
        profil_tage=wahl.profil_tage,
        profil_slots=wahl.profil_slots,
    )
