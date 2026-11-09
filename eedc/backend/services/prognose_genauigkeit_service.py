"""Prognose-Genauigkeit: welcher Prognosewert eines Tages gilt, und der mittlere Fehler der letzten N Tage.

Zwei Dinge stehen hier, und beide brauchen die Auswertung *Prognosen → Genauigkeit*
(``api/routes/prognosen.py::get_prognosen_genauigkeit``) **und** die Abweichungs-Ampel des
HA-Exports (S3/P6, ``eedc_mae_prozent``) — damit beide dieselbe Zahl nennen:

1. :func:`prognosen_zum_zeitpunkt` — der Prognosewert je Quelle für einen vergangenen Tag,
   zu einem von drei **Zeitpunkten** (N-782, «Mittag» seit Päckchen CC):

   * ``day_ahead`` — Σ der gespeicherten first-write-Stundenprofile: eedc
     ``pv_prognose_stundenprofil`` (die gezeigte, korrigierte Kanon-Reihe), OpenMeteo
     ``lern_soll_stundenprofil_kwh`` (roh, gekappt), Solcast ``solcast_prognose_stundenprofil``,
     SFML ``sfml_prognose_stundenprofil``. eedc, OpenMeteo und Solcast schreibt der Prefetch im
     ersten Lauf nach Mitternacht (bis 00:45; Solcast erst seit N-782 — davor beim ersten Aufruf
     der Live-Sicht), SFML nur die Live-Sicht beim ersten Aufruf des Tages.
   * ``mittag`` (Päckchen CC) — der Stand beim ersten Lauf ab 12:00 lokal (Prefetch bis 12:45 oder die Live-Sicht):
     eedc ``pv_prognose_eedc_mittag_kwh`` (IST bisher + Rest des Kanons), OpenMeteo ``pv_prognose_om_mittag_kwh``
     (Modell-Tageswert des Laufs, gekappt), Solcast ``solcast_mittag_kwh`` (per Satellit nachgeführt), SFML
     ``sfml_mittag_kwh``. Ab dem Päckchen erhoben, ältere Tage ``None``.
   * ``abend`` — die eingefrorenen Abendstände: OpenMeteo ``pv_prognose_final_kwh`` (Fallback
     ``pv_prognose_kwh``, roh und **ungekappt**), eedc ``pv_prognose_eedc_final_kwh`` (seit N-782),
     Solcast ``solcast_prognose_kwh`` (letzter Schreiber, tagsüber per Satellit nachgeführt),
     SFML ``sfml_prognose_kwh``.

   Wo kein Wert aufgezeichnet ist, steht ``None`` — „nicht erhoben", keine Rückrechnung, kein
   Rückfall auf einen anderen Stand (N-547-Haltung).

2. :func:`eedc_mae_prozent` — der mittlere Fehler der eedc-Prognose, Zeitpunkt Day-Ahead.

⛔ **Bis N-782 war die eedc-Quelle hier „OpenMeteo-Endwert × heutiger Lernfaktor"** — ein
Skalar, rückwirkend auf alle Tage angewandt, und nicht die Prognose, die eedc an dem Tag gezeigt
hat (die läuft über die Korrekturprofil-Kaskade). Gemessen 9.11.2026 (Winterborn, 30 Tage):
Tabelle +13 % Bias, die gezeigte Prognose abends +4 %. Die eedc-Reihe hängt seitdem an keinem
Lernfaktor mehr: **ohne Day-Ahead-Profile keine Reihe und damit keine Schwelle** — dann entsteht
auch kein Ampel-Sensor (ADR-002/P4).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Literal, Optional, Sequence

from sqlalchemy import select

from backend.core.berechnungen.prognose_genauigkeit import (
    mae_prozent,
    relativer_tagesfehler_prozent,
)
from backend.models.tages_energie_profil import TagesZusammenfassung

logger = logging.getLogger(__name__)

#: Die drei Zeitpunkte des Genauigkeits-Trackings (N-782; «Mittag» seit Päckchen CC). Day-Ahead ist der Standard: er
#: vergleicht gleich lange Vorlaufzeiten; der Mittags- und der Abendstand von Solcast sind per Satellit nachgeführt.
Zeitpunkt = Literal["day_ahead", "mittag", "abend"]
ZEITPUNKT_STANDARD: Zeitpunkt = "day_ahead"


def profil_tageswert_kwh(profil: Optional[Sequence[Optional[float]]]) -> Optional[float]:
    """Tagessumme eines gespeicherten Stundenprofils (kWh-Slots) — ``None``, wenn nichts erhoben ist.

    ``None`` bei fehlendem oder leerem Profil **und** bei Σ ≤ 0: eine Reihe aus lauter Nullen ist
    kein Prognosestand, sondern „keine Daten" (der Solcast-Dienst füllte so die Heute-Slots, wenn
    die Quelle kein Profil lieferte, und die Live-Sicht hat solche Reihen bis N-782 eingefroren).
    """
    if not profil:
        return None
    summe = sum(v for v in profil if v is not None)
    return summe if summe > 0 else None


@dataclass(frozen=True)
class TagesPrognosen:
    """Die Prognosewerte eines Tages je Quelle zu einem Zeitpunkt (kWh, ``None`` = nicht erhoben)."""

    openmeteo_kwh: Optional[float]
    eedc_kwh: Optional[float]
    solcast_kwh: Optional[float]
    sfml_kwh: Optional[float]


def prognosen_zum_zeitpunkt(tz: TagesZusammenfassung, zeitpunkt: str) -> TagesPrognosen:
    """Die Prognosewerte eines vergangenen Tages zum gewählten Zeitpunkt (Modul-Kopf).

    Jeder Wert, der nicht ``"abend"`` oder ``"mittag"`` ist, gilt als Day-Ahead (der Standard der Route).
    """
    if zeitpunkt == "mittag":
        return TagesPrognosen(
            openmeteo_kwh=tz.pv_prognose_om_mittag_kwh,
            eedc_kwh=tz.pv_prognose_eedc_mittag_kwh,
            solcast_kwh=tz.solcast_mittag_kwh,
            sfml_kwh=tz.sfml_mittag_kwh,
        )
    if zeitpunkt == "abend":
        # Prognose-Kanon §6: der konvergenz-gefrorene Endwert hat Vorrang, solange ein Tag
        # noch nicht final ist der rollende Wert — die Vorrangregel aus der Zeit vor N-782.
        om = (
            tz.pv_prognose_final_kwh
            if tz.pv_prognose_final_kwh is not None
            else tz.pv_prognose_kwh
        )
        return TagesPrognosen(
            openmeteo_kwh=om,
            eedc_kwh=tz.pv_prognose_eedc_final_kwh,
            solcast_kwh=tz.solcast_prognose_kwh,
            sfml_kwh=tz.sfml_prognose_kwh,
        )
    return TagesPrognosen(
        openmeteo_kwh=profil_tageswert_kwh(tz.lern_soll_stundenprofil_kwh),
        eedc_kwh=profil_tageswert_kwh(tz.pv_prognose_stundenprofil),
        solcast_kwh=profil_tageswert_kwh(tz.solcast_prognose_stundenprofil),
        sfml_kwh=profil_tageswert_kwh(tz.sfml_prognose_stundenprofil),
    )


async def eedc_mae_prozent(
    db, anlage_id: int, *, heute: date, tage: int = 30
) -> tuple[Optional[float], int]:
    """``(MAE in %, Anzahl ausgewerteter Tage)`` der eedc-Prognose, Zeitpunkt Day-Ahead.

    Die eedc-Reihe ist die gezeigte Prognose (Σ ``pv_prognose_stundenprofil``, derselbe Wert wie
    die eedc-Spalte der Auswertung im Standard-Zeitpunkt) — kein Lernfaktor (N-782).

    ``heute`` ist ein **Parameter** und kein ``date.today()`` in dieser
    Funktion — dasselbe Muster wie ``grundlast_sensorwert``: sonst müsste jede
    Probe die Prozessuhr lesen und auf die Stunde ihres Laufs wetten (N-167).

    Returns:
        ``(None, 0)``, wenn kein Tag ein Day-Ahead-Profil und ein brauchbares IST hat.
    """
    try:
        von = heute - timedelta(days=tage)
        res = await db.execute(
            select(TagesZusammenfassung).where(
                TagesZusammenfassung.anlage_id == anlage_id,
                TagesZusammenfassung.datum >= von,
                TagesZusammenfassung.datum < heute,
            )
        )
        from backend.services.energie_profil.vergleichstage import tage_ohne_tagesvergleich
        # Zählerlücken wie HA (§2): D und D+1 um ein Mitternachtsbündel sowie
        # Tage mit verworfener PV sind keine Einzeltage für einen Tagesfehler.
        ohne = await tage_ohne_tagesvergleich(db, anlage_id, "pv", von=von, bis=heute)
        tageszeilen = res.scalars().all()
        # HA-Bauform S5 (§3 (A) 11–15): PV-IST an der einen Stelle — an einem Kanal-Tag aus `kanal_tage`.
        from backend.services.energie_profil.kanal_stunden import pv_ist_je_tag

        ist_je_tag = await pv_ist_je_tag(db, anlage_id, tageszeilen)
        fehler: list[float] = []
        for tz in tageszeilen:
            if tz.datum in ohne:
                continue
            eedc = prognosen_zum_zeitpunkt(tz, ZEITPUNKT_STANDARD).eedc_kwh
            abweichung = relativer_tagesfehler_prozent(eedc, ist_je_tag.get(tz.datum))
            if abweichung is not None:
                fehler.append(abweichung)

        return mae_prozent(fehler), len(fehler)
    except Exception as e:  # der Export darf an der Genauigkeit nicht sterben
        logger.warning(
            "MAE-Ermittlung fehlgeschlagen (Anlage %s): %s: %s",
            anlage_id, type(e).__name__, e,
        )
        return None, 0
