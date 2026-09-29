"""Die EINE Auflösung eines Monats-Wetterwerts — für jeden, der sie braucht.

**Warum es dieses Modul gibt (Paket „Die Wetterreihe geradeziehen", #395 Punkt 1).**
Bis hierher gab es zwei Antworten auf dieselbe Frage:

* die **Route** ``GET /api/wetter/monat/…`` rief ``get_wetterdaten_multi`` mit
  der an der Anlage gewählten Quelle und stellte der Antwort die **eigene
  Messreihe** für die Ø-Temperatur voran (N-426);
* der **CSV-Import** rief ``get_wetterdaten`` — eine Kaskade ohne
  Bright-Sky-Zweig, also **immer Open-Meteo**, gegen die Zusage der Oberfläche
  („Automatische Auswahl: Bright Sky für DE").

Gemessen am 29.09.2026 unterscheiden sich die beiden Anbieter bei den
**Sonnenstunden um Faktor 1,6–2,0** (2025-06: 380 h gegen 231,8 h), bei der
Globalstrahlung um 12–16 %. Eine Reihe, die aus beiden Quellen zusammengesetzt
ist, beantwortet die Frage „war mein Jahr schwach?" falsch: an einer echten
Anlage wurde aus −1 % ein −37 %.

**Konvergenz statt zweitem Code-Pfad.** Route, CSV-Import, Nachzug und
Lückenschluss rufen ab jetzt diese eine Funktion. Was sie tut, steht damit an
einer Stelle — und was sie liefert, trägt die Quelle mit (`datenquelle`,
`temperatur_herkunft`), damit der Schreiber sie in die Provenance eintragen
kann statt zu raten.

⛔ **Die Ø-Temperatur ist nicht einfach „der Provider-Wert".** Die eigene
Messreihe steht **vor** dem Archiv (N-426) — ein Nachzug, der nur den Provider
fragt, ersetzte eine Messung durch einen Regionalwert. Das ist der Grund, warum
die Vorrangkette hier liegt und nicht in der Route.
"""

from __future__ import annotations

import calendar
import logging
from datetime import date
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.anlage import Anlage
from backend.services.mitteltemperatur import lade_monatsmittel_temperatur
from backend.services.wetter.orchestrator import get_wetterdaten_multi

logger = logging.getLogger(__name__)


#: Die drei Monatsfelder, um die es geht — Spiegel der Gruppe ``wetter`` in
#: ``core/field_definitions/registry.py``. Sie steht hier als Reihenfolge für
#: Schreiber und Meldungen; wer fragt „ist das ein Wetterfeld?", nimmt
#: ``ist_wetter_feld`` aus ``core.field_definitions``.
WETTER_MONATSFELDER: tuple[str, str, str] = (
    "globalstrahlung_kwh_m2",
    "sonnenstunden",
    "durchschnittstemperatur",
)

#: Welches Provenance-Label zu welcher gelieferten Quelle gehört.
#:
#: ⛔ Geschrieben wird das Label des **tatsächlich liefernden** Anbieters, nicht
#: das des gewünschten: ``auto`` ist über die Zeit nicht stabil (es hängt an
#: Land, Koordinaten-Box und ``settings.brightsky_enabled``), und ein Monat,
#: für den Bright Sky nichts hat, kommt über die Kette von Open-Meteo. Ohne die
#: echte Quelle in der Provenance kann niemand — auch kein Checker — sehen,
#: dass eine Reihe gemischt ist.
#:
#: ``pvgis-tmy`` und ``defaults`` stehen bewusst **nicht** hier: ein
#: langjähriges Mittel ist keine Messung *dieses* Monats und wird von keinem
#: automatischen Pfad geschrieben (siehe Lückenschluss-Job).
PROVENANCE_LABEL: dict[str, str] = {
    "brightsky": "external:brightsky",
    "open-meteo": "external:openmeteo",
}


def provenance_label(datenquelle: Optional[str]) -> Optional[str]:
    """Das Provenance-Label zu einer gelieferten ``datenquelle`` — oder ``None``.

    ``None`` heißt „diese Quelle darf kein automatischer Pfad festschreiben"
    (PVGIS-TMY, statische Defaults, Messreihe-ohne-Anbieter).
    """
    if not datenquelle:
        return None
    return PROVENANCE_LABEL.get(datenquelle)


def ist_messende_quelle(datenquelle: Optional[str]) -> bool:
    """Hat ein Archiv diesen Monat wirklich **gemessen**?

    Der Unterschied trägt die Zusage „kein abgeschlossener Monat ohne Werte":
    sie gilt, solange ein messendes Archiv den Ort erreicht. PVGIS-TMY und die
    statischen Defaults erreichen ihn immer — und sagen deshalb nichts.
    """
    return provenance_label(datenquelle) is not None


async def loese_monats_wetter(
    db: AsyncSession,
    anlage: Anlage,
    jahr: int,
    monat: int,
    provider: Optional[str] = None,
) -> dict[str, Any]:
    """Die Wetterwerte eines Monats für **diese** Anlage, auf einem Lineal.

    Args:
        db: Sitzung des Aufrufers — für die eigene Messreihe.
        anlage: Trägt Koordinaten, ``standort_land`` und ``wetter_provider``.
        jahr, monat: Der gefragte Monat.
        provider: Ausdrücklicher Wunsch. Ohne ihn gilt die an der Anlage
            gespeicherte Wahl (#386), ohne die ``auto``.

    Returns:
        Das dict von ``get_wetterdaten_multi`` — ``globalstrahlung_kwh_m2``,
        ``sonnenstunden``, ``datenquelle``, ``standort``, ``provider_info`` … —
        mit der Ø-Temperatur aus der **Vorrangkette**:

        1. die eigene Messreihe der Anlage (``temperatur_herkunft="messung"``),
        2. sonst der Wert des liefernden Anbieters.

        ⛔ **Ohne die dritte Stufe** der Temperaturkette, und das ist keine
        Sparsamkeit: Stufe 3 wäre ``Monatsdaten.durchschnittstemperatur`` —
        genau das Feld, das diese Antwort füllen soll. Gäbe man
        ``gepflegt_je_monat`` mit, bestätigte der Abruf dem Anwender seinen
        eigenen Wert als „gemessen", und die Kette liefe im Kreis.

    Raises:
        ValueError: Wenn die Anlage keine Geokoordinaten hat. Der Aufrufer
            entscheidet, ob das ein HTTP-400 ist (Route) oder ein
            übersprungener Monat (Nachzug).
    """
    if not anlage.latitude or not anlage.longitude:
        raise ValueError(
            "Anlage hat keine Geokoordinaten. Bitte latitude/longitude in den "
            "Stammdaten ergänzen."
        )

    gewaehlt = provider or getattr(anlage, "wetter_provider", None) or "auto"

    data = await get_wetterdaten_multi(
        latitude=anlage.latitude,
        longitude=anlage.longitude,
        jahr=jahr,
        monat=monat,
        provider=gewaehlt,  # type: ignore[arg-type]
        land=anlage.standort_land,
    )

    # ── Ø-Temperatur: die eigene Messreihe steht VOR dem Archiv (N-426) ──────
    #
    # Der Provider-Wert oben ist damit die **letzte** Stufe derselben
    # Vorrangkette, mit der die Temperaturlinie des Wärme/Klima-Verlaufs
    # rechnet — und sie wird GERUFEN, nicht nachgebaut (`services/
    # mitteltemperatur.py`, ADR-001): Stundenmittel, sonst Tages-Min/Max.
    #
    # ⚠ Für den LAUFENDEN Monat liefert der Provider ohnehin nichts (die
    # Anbieter-Schleife greift nur für vergangene Monate, `orchestrator.py`) —
    # dort ist die Messreihe nicht nur besser, sondern die einzige Quelle.
    letzter_tag = calendar.monthrange(jahr, monat)[1]
    gemessen = await lade_monatsmittel_temperatur(
        db,
        anlage.id,
        von=date(jahr, monat, 1),
        bis=date(jahr, monat, letzter_tag),
    )
    kettenwert = gemessen.get((jahr, monat))
    if kettenwert is not None:
        data["durchschnittstemperatur_c"] = kettenwert
        data["temperatur_herkunft"] = "messung"

    return data
