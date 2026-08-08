"""Wie viel der Heimladung aus der eigenen Sonne kam — ohne dass es jemand misst.

Single Source of Truth für die **Ableitung** des PV-Anteils einer Heimladung aus
eedcs eigenen Zeitreihen (Fund **N-141 Weg (c)**, ``KONZEPT-WALLBOX-EAUTO.md``).

**Warum es diese Datei gibt.** Eine Wallbox misst ihren PV-Anteil nicht. Sie
zählt Kilowattstunden, nicht deren Herkunft — an Gernots Anlage belegt: der
SMA eCharger liefert einen reinen Ladungszähler, der PV-Anteil daneben ist eine
Rechnung von **evcc**, keine Messung. Wer kein evcc betreibt, hatte bis hierher
gar nichts: ``ladung_pv_kwh`` blieb leer, und der Leser
(``get_emob_pv_netz_kwh``) setzte den PV-Anteil auf **0** — die gesamte
Heimladung galt als Netzstrom. Gleichzeitig las die ROI-**Prognose** einen von
Hand gepflegten ``pv_ladeanteil_prozent`` (Default 60 %). Dieselbe Anlage stand
damit auf **60 % PV in der Prognose und 0 % im IST** (Fund **N-188**).

**Die Idee ist von evcc geborgt, nicht erfunden.** evcc kennt ebenfalls keinen
PV-Sensor an der Wallbox — es kennt PV-Leistung, Netzbezug/Einspeisung und
Ladeleistung und rechnet je Zeitschritt, welcher Teil der Ladung gerade durch
Überschuss gedeckt war. Genau das tut ``leite_pv_anteil_ab``, nur mit eedcs
eigenen Stundengrößen.

Vermessen am 2026-08-08 gegen evcc als Referenz (Anlage 1, Feb–Aug 2026,
963 kWh Heimladung, evcc-Referenz 67,9 % PV) — drei Regeln standen zur Wahl:

=================================  =========  =====================
Regel                              PV-Anteil  Abweichung zu evcc
=================================  =========  =====================
netzbasiert                          73,8 %   **+5,9 pp** (zu hoch)
netz + Speicherentladung             60,8 %   −7,2 pp (zu tief)
**Einspeise-Deckung (gebaut)**     **64,7 %** **−3,2 pp**
=================================  =========  =====================

Gernots Entscheid: **Einspeise-Deckung**. Sie trifft die Referenz am besten und
irrt in die unverdächtige Richtung — sie schreibt die Ersparnis eher zu klein
als zu groß.

⚠ **Das Ergebnis ist eine Schätzung und muss als solche gekennzeichnet werden.**
Der Aufrufer trägt es nach der P4-Linie als abgeleitet aus (Muster
„geschätzt (kWp-Anteil)"). Ein gepflegter echter Wert gewinnt **immer** — diese
Rechnung füllt Lücken, sie überschreibt nichts.

⚠ **Die Auflösung begrenzt die Genauigkeit, nicht die Formel.** An Gernots
Anlage meldet der Wallbox-Zähler nur **ganze Kilowattstunden** (218 von 218
Stunden-Deltas ganzzahlig, kleinster Wert 1,000 kWh); ein Zuwachs von 20 kWh
landete am 05.06. vollständig in der Stunde 05:00. Wo ein Zähler so grob meldet,
kann keine noch so feine Rechnung die Stunde richtig treffen — die Ableitung ist
dann über den Monat brauchbar und über die einzelne Stunde nicht. Eine feinere
Eingangsebene (5-Min-Overlays) hilft nur dort, wo der Zähler selbst feiner ist.
"""

from dataclasses import dataclass
from typing import Final, Optional

#: Ladung unterhalb dieser Schwelle (kWh je Stunde) gilt als Rauschen und wird
#: übersprungen — sie trägt weder zum PV- noch zum Netz-Anteil bei.
_LADUNG_EPSILON: Final[float] = 0.001

#: Kennzeichen der Bildungsvorschrift. Wandert in die Provenance, damit später
#: unterscheidbar bleibt, WIE ein abgeleiteter Wert entstanden ist.
REGEL_EINSPEISE_DECKUNG: Final[str] = "einspeise_deckung"


def stunde_aus_bilanzwerten(
    *,
    ladung: Optional[float],
    netzbezug: Optional[float],
    einspeisung: Optional[float],
    batterie_spalte: Optional[float],
) -> dict[str, Optional[float]]:
    """Baut eine Eingangs-Stunde aus den Größen, wie der Aggregator sie hält.

    **Warum es diese Funktion gibt: wegen genau eines Vorzeichens.**
    ``leite_pv_anteil_ab`` verlangt eine **positive** Speicherentladung. Im
    Aggregator liegt die Batterie aber in der *Spalten-Konvention* vor
    (``batterie_kw_spalte``: **ENTLADUNG positiv, LADUNG negativ**), und daneben
    liegt der Rohwert ``snap_h['batterie_netto']`` mit dem **umgekehrten**
    Vorzeichen. Wer den Rohwert übergibt, bekommt keinen Fehler: der Layer
    klemmt eine negative Entladung mit ``max(0, …)`` auf 0 — die
    Speicherentladung fiele **still** aus der Rechnung, und die Regel wäre
    heimlich eine andere (netzbasiert + Einspeisung statt Einspeise-Deckung,
    an Gernots Anlage +9 pp).

    Das ist die Klasse, an der am 2026-08-08 schon eine Test-Fixture scheiterte
    (F-14): eine Vorzeichen-Konvention, die man nicht sieht, wenn man sie
    verwechselt. Deshalb steht die Übersetzung hier — benannt, mit Proben —
    statt als Ausdruck in der Stundenschleife.

    Args:
        ladung: Heimladung der Stunde (kWh, positiv).
        netzbezug: Netzbezug der Stunde (kWh, positiv).
        einspeisung: Einspeisung der Stunde (kWh, positiv).
        batterie_spalte: Batterie in der **Spalten-Konvention** — Entladung
            positiv. ``None`` = keine Batterie oder kein Wert.

    Returns:
        Das Dict, das ``leite_pv_anteil_ab`` je Stunde erwartet.
    """
    return {
        "ladung": ladung,
        "netzbezug": netzbezug,
        "einspeisung": einspeisung,
        # Nur die Entladung interessiert: eine Stunde, in der der Speicher LÄDT,
        # liefert nichts an die Wallbox. Der Ladeanteil ist bereits im
        # Netzbezug/in der fehlenden Einspeisung enthalten.
        "speicher_entladung": (
            max(0.0, batterie_spalte) if batterie_spalte is not None else None
        ),
    }


@dataclass(frozen=True)
class AbgeleiteterLadeAnteil:
    """Aufgeteilte Heimladung eines Zeitraums — abgeleitet, nicht gemessen.

    ``pv_kwh + netz_kwh`` ist die Ladung der **gedeckten** Stunden, nicht
    zwingend die Ladung des ganzen Tages: Stunden ohne vollständige Eingänge
    zählen nicht mit. ``stunden_gedeckt``/``stunden_mit_ladung`` machen das
    sichtbar, statt eine Teilsumme als Ganzes auszugeben (P4).
    """

    pv_kwh: float
    netz_kwh: float
    #: Bildungsvorschrift, siehe ``REGEL_EINSPEISE_DECKUNG``.
    regel: str
    #: Stunden mit Ladung, für die alle Eingänge vorlagen.
    stunden_gedeckt: int
    #: Stunden mit Ladung überhaupt — inklusive der ungedeckten.
    stunden_mit_ladung: int

    @property
    def vollstaendig(self) -> bool:
        """Lagen für **jede** Ladestunde alle Eingänge vor?

        Nur dann beschreibt ``pv_kwh + netz_kwh`` die ganze Heimladung des
        Zeitraums. Sonst ist es eine Teilsumme, und der Aufrufer muss das
        ausweisen statt sie stillschweigend als Tageswert zu führen.
        """
        return self.stunden_gedeckt == self.stunden_mit_ladung

    @property
    def ladung_kwh(self) -> float:
        """Die Ladung, über die diese Aufteilung überhaupt eine Aussage macht."""
        return self.pv_kwh + self.netz_kwh


def leite_pv_anteil_ab(
    stunden: list[dict[str, Optional[float]]],
) -> Optional[AbgeleiteterLadeAnteil]:
    """Teilt eine Heimladung in PV- und Netzanteil, ohne dass jemand sie misst.

    Je Stunde gilt die **Einspeise-Deckung**:

    1. Was die Ladung übersteigt, das gleichzeitig aus Netz und Speicher kam,
       kann nur aus der PV gekommen sein::

           ungedeckt = max(0, ladung − netzbezug − speicher_entladung)

    2. Was in derselben Stunde eingespeist wurde, hätte stattdessen laden
       können — es belegt zusätzlichen Überschuss. Das fängt die Unschärfe der
       Stundenmittelung auf, in der Bezug und Einspeisung nebeneinander stehen::

           pv = min(ladung, ungedeckt + einspeisung)

    3. Der Rest ist Netzstrom.

    Args:
        stunden: je Stunde ein Dict mit ``ladung``, ``netzbezug``,
            ``einspeisung`` und ``speicher_entladung`` (kWh, nicht-negativ).
            ``None`` bedeutet „nicht erhoben"; fehlt eine der vier Größen in
            einer Ladestunde, zählt diese Stunde als **ungedeckt** und geht
            nicht in die Summen ein. Die Schlüssel entsprechen dem Vertrag von
            ``get_hourly_kwh_by_category``.

    Returns:
        Die Aufteilung, oder ``None``, wenn im Zeitraum keine Ladung stattfand
        oder keine einzige Ladestunde gedeckt war. ``None`` heißt „keine
        Aussage" — der Aufrufer darf daraus **nicht** 0 kWh PV machen, das wäre
        genau die Behauptung, die dieser Fund auflöst.
    """
    pv_summe = 0.0
    netz_summe = 0.0
    gedeckt = 0
    mit_ladung = 0

    for stunde in stunden:
        ladung = stunde.get("ladung")
        if ladung is None or ladung <= _LADUNG_EPSILON:
            continue
        mit_ladung += 1

        netzbezug = stunde.get("netzbezug")
        einspeisung = stunde.get("einspeisung")
        speicher = stunde.get("speicher_entladung")
        # Der Speicher ist der einzige optionale Eingang: eine Anlage ohne
        # Batterie hat hier dauerhaft nichts stehen, und das ist kein Mangel.
        # Netzbezug und Einspeisung dagegen MÜSSEN vorliegen — ohne sie ist die
        # Deckung nicht bestimmbar, und ein fehlender Wert als 0 zu lesen hieße,
        # die ganze Stunde der Sonne gutzuschreiben.
        if netzbezug is None or einspeisung is None:
            continue
        if speicher is None:
            speicher = 0.0

        ungedeckt = max(0.0, ladung - max(0.0, netzbezug) - max(0.0, speicher))
        pv = min(ladung, ungedeckt + max(0.0, einspeisung))

        pv_summe += pv
        netz_summe += ladung - pv
        gedeckt += 1

    if mit_ladung == 0 or gedeckt == 0:
        return None

    return AbgeleiteterLadeAnteil(
        pv_kwh=round(pv_summe, 3),
        netz_kwh=round(netz_summe, 3),
        regel=REGEL_EINSPEISE_DECKUNG,
        stunden_gedeckt=gedeckt,
        stunden_mit_ladung=mit_ladung,
    )
