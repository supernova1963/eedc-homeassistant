"""Gemessener Verbrauch je Betriebsart — Gerät oder Innengeräte (#263).

**Wozu diese Datei.** Seit der Konzept-Fassung vom 2026-08-21 kann eine
Split-Klimaanlage ihren Verbrauch je Betriebsart **gemessen** mitbringen, statt
ihn eedc aus dem Betriebsmodus ableiten zu lassen: vier Zähler (Heizen ·
Kühlen · Lüften · Entfeuchten), am Gerät oder je Innengerät. Wer sie in Home
Assistant nicht direkt bekommt, baut sie sich mit einem **Utility Meter** und
einem Tarif je Betriebsart.

**Die eine Regel, und sie steht nur hier** (ADR-001 — eine Auflösung ist eine
Formel, kein Routen-Detail):

1. **Das Gerätefeld gewinnt.** Wer den ganzen Verbrauch einer Betriebsart an
   einem Zähler hat, hat die vollständigere Zahl — die Innengeräte sind dann
   die Aufschlüsselung, nicht die Summe.
2. **Sonst die Summe der Innengeräte.**
3. **Sonst nichts** (``None``, nicht ``0.0``): „kein Zähler" und „Zähler stand
   auf null" sind verschiedene Aussagen. Ein ``0.0`` an dieser Stelle
   verdrängte die abgeleitete Aufteilung und ersetzte sie durch eine Null —
   die F-42-Klasse.

⛔ **Gerätefeld und Innengeräte werden NIE addiert.** Beide beschreiben
dieselbe Menge auf verschiedenen Ebenen; sie zu summieren wäre die
Doppelzählungs-Klasse, die uns beim BKW, beim Speicher und beim
Wallbox/E-Auto-Pool je einmal getroffen hat.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from backend.core.betriebsmodus import (
    BETRIEBSART_NUTZENERGIE_FELD,
    BETRIEBSART_STROM_FELD,
    ENTFEUCHTEN,
    HEIZEN,
    KUEHLEN,
    LUEFTEN,
    MESSBARE_MODI,
    MODUS_ABDECKUNG_FELD,
    MODUS_STROM_FELD,
    WARMWASSER,
)
from backend.core.field_definitions import basis_feld_key

__all__ = [
    "betriebsart_strom_kwh",
    "betriebsart_nutzenergie_kwh",
    "hat_gemessene_betriebsart",
    "ModusStromZeile",
    "modus_strom_zeile",
]


def _aufgeloest(daten: Optional[dict], basis_feld: str) -> Optional[float]:
    """Gerätefeld, sonst Σ Innengeräte, sonst ``None`` — siehe Modul-Kopf."""
    if not isinstance(daten, dict):
        return None

    direkt = daten.get(basis_feld)
    if direkt is not None:
        try:
            return float(direkt)
        except (TypeError, ValueError):
            return None

    summe = 0.0
    gefunden = False
    for key, wert in daten.items():
        if wert is None or key == basis_feld:
            continue
        if basis_feld_key(key) != basis_feld:
            continue
        try:
            summe += float(wert)
        except (TypeError, ValueError):
            continue
        gefunden = True
    return summe if gefunden else None


def betriebsart_strom_kwh(daten: Optional[dict], modus: str) -> Optional[float]:
    """Gemessener **Strom**verbrauch dieser Betriebsart, oder ``None``."""
    feld = BETRIEBSART_STROM_FELD.get(modus)
    return _aufgeloest(daten, feld) if feld else None


def betriebsart_nutzenergie_kwh(daten: Optional[dict], modus: str) -> Optional[float]:
    """Gemessene **abgegebene Nutzenergie** dieser Betriebsart, oder ``None``."""
    feld = BETRIEBSART_NUTZENERGIE_FELD.get(modus)
    return _aufgeloest(daten, feld) if feld else None


def hat_gemessene_betriebsart(daten: Optional[dict]) -> bool:
    """Bringt diese Zeile **irgendeinen** gemessenen Betriebsart-Strom mit?

    Das ist die Weiche für ADR-002/P8 an dieser Stelle: **gemessen schlägt
    abgeleitet**. Wo sie ``True`` sagt, darf die aus dem Betriebsmodus
    gerechnete Aufteilung nicht zusätzlich angewandt werden — sonst stünde
    dieselbe Menge zweimal in derselben Zeile.

    ⚠ Bewusst nur der **Strom**: die Nutzenergie ist eine andere Größe und
    verdrängt keine Stromaufteilung.
    """
    return any(
        betriebsart_strom_kwh(daten, modus) is not None for modus in MESSBARE_MODI
    )


@dataclass(frozen=True)
class ModusStromZeile:
    """Die Betriebsart-Aufteilung **einer** IMD-Zeile — mit ihrer Herkunft.

    ``gemessen`` sagt, welcher der beiden Wege gegriffen hat. Er ist nicht
    Kosmetik: Wo er ``True`` ist, darf der aus dem Betriebsmodus *gerechnete*
    Split (``lade_modus_split_ohne_abschluss``) für dieses Gerät **nicht**
    zusätzlich angewandt werden — sonst stünde dieselbe Menge zweimal in
    derselben Zeile.

    ⭐ **Die zwei Wege können verschieden viel — und zwar in BEIDE Richtungen.**
    Die Zeile bildet ab, was ein **Zähler** hergibt: vier Betriebsarten
    (``MESSBARE_MODI``). Der aus dem Modus-Signal *abgeleitete* Split kann
    dagegen Heizen, **Warmwasser** und Kühlen (``AUFGETEILTE_MODI``).

    * ``lueften_kwh``/``entfeuchten_kwh`` bleiben im abgeleiteten Zweig 0 — ein
      Modus-Signal gibt sie nicht her.
    * ``warmwasser_kwh`` bleibt im **gemessenen** Zweig 0 — dafür gibt es keinen
      Betriebsart-Zähler, sondern ``strom_warmwasser_kwh`` aus der
      Summanden-Familie (Begründung bei ``MESSBARE_MODI``).

    **Beides ist keine Lücke, sondern die Aussage:** jeder Weg trägt, was er
    wissen kann. ⚠ Bis zum 27.08.2026 stand hier *„nur Heizen und Kühlen …
    belegt durch D11"* — richtig für die Split-Klimaanlage, für die #263
    geschrieben ist, und unhaltbar als Satz über die ganze Fläche (N-336).

    Bis zum 26.08.2026 las auch der **gemessene** Zweig nur zwei der vier
    Felder. Wer einen Lüftungs- oder Entfeuchtungs-Zähler zuordnete, sah seine
    Kilowattstunden **nirgends** — sie fielen stumm unter „nicht aufgeteilt",
    obwohl die Registry das Feld anbietet und der Anwender es gepflegt hat.
    Das ist die P-6-Falle: ein Angebot, das niemand einlösen kann.
    """

    heizen_kwh: float
    kuehlen_kwh: float
    gemessen: bool

    @property
    def hat_aufteilung(self) -> bool:
        """Trägt die Zeile überhaupt eine Aufteilung — gemessen oder abgeleitet?"""
        return self.gemessen or self.abdeckung_h > 0

    @property
    def funktionsfremd_kwh(self) -> float:
        """Strom in Funktionen **ohne bewertete Nutzenergie** — der JAZ-Nenner-Abzug.

        ⭐ **Die eine Stelle, die sagt, was „funktionsfremd" heißt** (ADR-001:
        eine Auflösung ist eine Formel, kein Routen-Detail). Bis zum 26.08.2026
        stand dafür an vier Aufrufern der Kühlstrom **direkt** — der Docstring
        von ``arbeitszahl`` nannte ihn ausdrücklich *„heute der Kühlbetrieb"*,
        und genau dieses „heute" tritt hier ein.

        **Warum Lüften und Entfeuchten dazugehören:** Sie sind nach Konzept
        §2.3/**E4** *erfassbar, aber keine bewertete Funktion* — sie erzeugen
        keine Wärme, die in einem Wärmemengenzähler landet. Stünde ihr Strom im
        Nenner, drückte er die Arbeitszahl aus demselben Grund wie der
        Kühlstrom vor W-14: **ein Kategorienfehler, kein Messfehler.**

        ⛔ **`warmwasser_kwh` gehört NICHT dazu — das ist die Falle von N-336.**
        Warmwasser sieht in dieser Zeile aus wie Kühlen, Lüften und Entfeuchten:
        eine Betriebsart neben dem Heizen. Es ist aber die einzige davon, die
        eine **bewertete Nutzenergie** erzeugt — sie steht in ``warmwasser_kwh``
        und geht über ``waerme_gesamt_kwh`` in den **Zähler** desselben
        Quotienten ein. Zöge man ihren Strom aus dem Nenner, stünde die
        Warmwasser-Wärme oben und ihr Strom nirgends: **die Arbeitszahl jeder
        Brauchwasser-Wärmepumpe stiege ohne einen einzigen neuen Messwert.**

        ⭐ Die Trennlinie ist damit nicht *„Heizen gegen den Rest"*, sondern die
        des SOLL §3.2a: **hat diese Funktion ein Q?** Heizen und Warmwasser
        haben eins, Kühlen hat eins (Kälte, nur selten gemessen — s.
        ``arbeitszahl_kuehlen``), Lüften und Entfeuchten haben keins.

        ⚠ **Abgezogen, nicht gesperrt.** Die Mengen bleiben unverändert in
        allen Bilanzen und Kosten; es ändert sich allein der Nenner der
        Kennzahl.
        """
        return self.kuehlen_kwh + self.lueften_kwh + self.entfeuchten_kwh

    #: Stunden mit gültigem Modus-Signal, aus der Zeile übernommen.
    abdeckung_h: float = 0.0

    #: Nur im **gemessenen** Zweig belegt — der abgeleitete Split kennt sie
    #: nicht (s. Klassen-Docstring).
    lueften_kwh: float = 0.0
    entfeuchten_kwh: float = 0.0

    #: Nur im **abgeleiteten** Zweig belegt — die Gegenrichtung zu den zwei
    #: Feldern darüber (N-336). Für Warmwasser gibt es keinen
    #: Betriebsart-Zähler; wer seinen Warmwasser-Strom getrennt misst, pflegt
    #: ``strom_warmwasser_kwh`` und bekommt daraus seine *Arbeitszahl
    #: Warmwasser* — eine andere Familie, eine andere Frage.
    warmwasser_kwh: float = 0.0


def modus_strom_zeile(daten: Optional[dict]) -> ModusStromZeile:
    """**Gemessen schlägt abgeleitet** — ganz oder gar nicht je Zeile (F-56).

    Die Regel steht **nur hier**, obwohl sie an mehreren Flächen gebraucht wird:
    Monats-Fakten (Cockpit, Komponenten-Hub) und HA-/MQTT-Export, der seine
    IMD-Zeilen je Investition faltet und deshalb nicht über die Monats-Fakten
    geht (bekannte P10-Restschuld von ``ha_export.py``).

    ⛔ **Warum sie eine Funktion ist und keine zwei Codestellen — F-56 ist genau
    daran entstanden.** Die Weiche stand bis dahin inline in
    ``imd_monatsaggregat``, und der Export baute sie daneben nach: **ohne** den
    ``hat_gemessene_betriebsart``-Zweig. Folge: Wer die mit v4.0.24 neu
    eingeführten Zähler zuordnete, sah die Aufteilung in eedc — und bekam in
    Home Assistant **keinen Wert**. Genau davor warnt der Modul-Kopf von
    ``modus_split_monat.py`` seit F-52 wörtlich: *„eine Regel, die an zwei
    Stellen nachgebaut wird, driftet."* Sie ist im selben Paket noch einmal
    gedriftet.

    ⚠ **Ganz oder gar nicht je Zeile** (Begründung ausführlich in
    ``imd_monatsaggregat``): Ein Balken, dessen eine Hälfte aus einem Zähler und
    dessen andere aus einer Rechnung stammt, trägt ein halbwahres Etikett — und
    das ist schlechter als eine fehlende Zahl (ADR-002/P4).
    """
    daten = daten if isinstance(daten, dict) else {}
    abdeckung = _zahl(daten.get(MODUS_ABDECKUNG_FELD))
    if hat_gemessene_betriebsart(daten):
        # E4 (Konzept §2.3): **alle vier** messbaren Betriebsarten, nicht nur
        # die zwei, die der abgeleitete Split hergibt. Ein zugeordneter
        # Lüftungs-Zähler ist eine Messung wie jede andere — sie hier zu
        # übergehen hieße, ein Feld anzubieten und seinen Wert wegzuwerfen.
        return ModusStromZeile(
            heizen_kwh=betriebsart_strom_kwh(daten, HEIZEN) or 0.0,
            kuehlen_kwh=betriebsart_strom_kwh(daten, KUEHLEN) or 0.0,
            lueften_kwh=betriebsart_strom_kwh(daten, LUEFTEN) or 0.0,
            entfeuchten_kwh=betriebsart_strom_kwh(daten, ENTFEUCHTEN) or 0.0,
            gemessen=True,
            abdeckung_h=abdeckung,
        )
    return ModusStromZeile(
        heizen_kwh=_zahl(daten.get(MODUS_STROM_FELD[HEIZEN])),
        kuehlen_kwh=_zahl(daten.get(MODUS_STROM_FELD[KUEHLEN])),
        # N-336: der abgeleitete Zweig kann Warmwasser, der gemessene nicht.
        # Altmonate tragen das Feld nicht — dort bleibt der Anteil in der
        # Restmenge, und das ist die Wahrheit: eedc hat ihn damals nicht
        # mitgeschrieben. **Kein Nachrechnen der Historie.**
        warmwasser_kwh=_zahl(daten.get(MODUS_STROM_FELD[WARMWASSER])),
        gemessen=False,
        abdeckung_h=abdeckung,
    )


def _zahl(wert) -> float:
    try:
        return float(wert or 0)
    except (TypeError, ValueError):
        return 0.0
