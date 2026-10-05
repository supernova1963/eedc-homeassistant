"""Monatsraster der Lese-Schicht (HA-Bauform E3, Auftrag Punkt 5; Gegenprüfung G7, Bauplan §5).

``monatsreihe(db, anlage_id, benoetigte_kanaele, von_monat, bis_monat)`` liefert je Monat Δ und Abdeckung jedes
benötigten Kanals — über ``lesen.reihe_stapel`` mit den Monatsfenstern des Bestands (``fenster.monatsgrenzen``, n+1
Randstände für n Monate), dazu je Monat die EINE Quellenwahl über ALLE benötigten Schlüssel
(``quellenwahl.waehle_quelle``, Bauplan §3b) — dieselbe Regel wie ``quellenwahl()`` für einen Tag:

* ein benötigter Schlüssel ohne Kanal (Sensor ohne HA-Statistik) ⇒ ``kein_kanal`` ⇒ der Monat nimmt den Bestand.
  Deshalb nimmt das Raster SCHLÜSSEL, nicht Kanal-Objekte: ein Feld ohne Kanal könnte der Aufrufer sonst gar nicht
  übergeben, und der Monat meldete still ``kanal`` (Nachmessung E3, Punkt 3).
* keine benötigten Schlüssel ⇒ je Monat ``bestand`` (``keine_eingaenge``), nicht eine leere Liste.
* ein Mittelwert-Kanal hat kein Δ ⇒ benannter Grund ``mittelwert_kein_delta``, der Monat nimmt den Bestand. Ein
  Monats-Mittel je Monat läse jede Stunde aller Monate (``mittel`` je Monat oder ein Aggregat über alle Zeilen) — im
  Raster nicht gebaut; Preis und Kosten kommen in E4 als abgeleitete Mengen-Kanäle (``kosten:*``, Bauplan §2).

**Was NICHT hierher gehört:** die Überlagerung „gespeichert schlägt gerechnet" (ADR-002/P8) — die machen die
Monats-Fakten in E4. Die Schicht liefert nur das Raster. Zeiträume ab Monatslänge laufen in den Sichten über dieses
Raster, nie über ein direktes ``zeitraum()`` über Monatsgrenzen (Wächter ``test_kanal_lesen_waechter.py``: außerhalb
``services/kanal/`` importiert die Schicht in E3 niemand).

**Stand E3: von niemandem benutzt.**

Schwesterdateien: ``lesen.py``, ``fenster.py``, ``quellenwahl.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.kanal import ART_MEAN
from backend.services.kanal.fenster import monate, monatsgrenzen
from backend.services.kanal.lesen import Zeitraum, kanaele_laden, reihe_stapel
from backend.services.kanal.quellenwahl import QUELLE_BESTAND, Quellenwahl, waehle_quelle

#: Ein Mittelwert-Kanal im Raster: kein Δ — der Monat nimmt den Bestand.
GRUND_MITTELWERT_KEIN_DELTA = "mittelwert_kein_delta"


@dataclass(frozen=True)
class Monatswert:
    jahr: int
    monat: int
    #: Monatsfenster (absolute Grenzen, ``fenster.monatsfenster``).
    von: int
    bis: int
    #: Je vorhandenem Mengen-/Stand-Kanal Δ und Abdeckung des Monats.
    werte: dict[str, Zeitraum]
    #: Die eine Quellenwahl des Monats über ALLE benötigten Schlüssel.
    wahl: Quellenwahl


async def monatsreihe(
    db: AsyncSession, anlage_id: int, benoetigte_kanaele: Iterable[str],
    von_monat: tuple[int, int], bis_monat: tuple[int, int], *, jetzt: Optional[int] = None,
) -> list[Monatswert]:
    """Je Monat ``von_monat`` … ``bis_monat`` (inklusive) Δ, Abdeckung und Quellenwahl der benötigten Kanäle — zwei
    Anweisungen gesamt (Kanäle laden; Randstände)."""
    liste = monate(von_monat, bis_monat)
    if not liste:
        return []
    benoetigte = list(dict.fromkeys(benoetigte_kanaele))
    grenzen = monatsgrenzen(von_monat, bis_monat)
    kanaele = await kanaele_laden(db, anlage_id, benoetigte) if benoetigte else {}
    mengen = [k for k in kanaele.values() if k.art != ART_MEAN]
    mittelwerte = {k.key for k in kanaele.values() if k.art == ART_MEAN}
    je_kanal = await reihe_stapel(db, mengen, grenzen, jetzt=jetzt) if mengen else {}
    out: list[Monatswert] = []
    for i, (jahr, monat) in enumerate(liste):
        werte = {key: reihe[i] for key, reihe in je_kanal.items()}
        wahl = waehle_quelle(werte, benoetigte)
        if mittelwerte:
            gruende = {**wahl.gruende, **{key: GRUND_MITTELWERT_KEIN_DELTA for key in mittelwerte}}
            wahl = Quellenwahl(QUELLE_BESTAND, gruende, wahl.ergebnisse)
        out.append(Monatswert(jahr, monat, grenzen[i], grenzen[i + 1], werte, wahl))
    return out
