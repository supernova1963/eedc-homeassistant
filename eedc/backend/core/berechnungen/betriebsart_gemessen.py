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
    "MODI_OHNE_BEWERTETE_NUTZENERGIE",
    "betriebsart_strom_kwh",
    "betriebsart_strom_felder_belegt",
    "betriebsart_nutzenergie_kwh",
    "funktionsfremd_abzug_kwh",
    "geraetefeld_oder_innengeraete",
    "hat_gemessene_betriebsart",
    "ModusStromZeile",
    "modus_strom_zeile",
    "NutzenergieOhneKennzahl",
    "summanden_gelten",
    "nutzenergie_ohne_kennzahl_kwh",
]


#: Die Betriebsarten **ohne bewertete Nutzenergie** — Kühlen · Lüften ·
#: Entfeuchten (SOLL §3.2a/**E4**). Ihr Strom ist der Nenner-Abzug einer
#: Arbeitszahl ({@link ModusStromZeile.funktionsfremd_kwh}) und — auf der
#: Zuordnungs-Ebene — der Teil der Betriebsart-Zähler, der **neben** den
#: Summanden-Achsen steht statt darin (W-16).
#:
#: ⛔ **Sie stehen als Liste hier und nicht dreimal ausgeschrieben.** Bis zum
#: 15.09.2026 gab es nur die Summe; mit R-1 fragt auch die Beitragsschicht des
#: Tages nach **genau diesen drei**, und eine zweite Aufzählung daneben wäre die
#: Bauform, an der W-14 entstanden ist.
MODI_OHNE_BEWERTETE_NUTZENERGIE: tuple[str, ...] = (KUEHLEN, LUEFTEN, ENTFEUCHTEN)


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


def geraetefeld_oder_innengeraete(
    daten: Optional[dict], basis_feld: str,
) -> Optional[float]:
    """Die Auflösungsregel für **ein** Feld, das es auch je Innengerät gibt.

    Öffentlicher Name für {@link _aufgeloest} — für Leser, die dieselbe Frage an
    **anderen** Daten stellen als an einer IMD-Zeile: der Tagespfad
    (``snapshot/aggregator.py::get_tagesdetail_kwh``) und der Bereichs-Leser
    fragen sie an den Tages-Diffs der Zähler (Konzept Wärme/Klima §8,
    Bauschnitt 6 — die Kälte je Tag). Die Regel selbst bleibt damit hier und
    nur hier: Gerätefeld, sonst Σ Innengeräte, sonst ``None``, **nie addiert**.
    """
    return _aufgeloest(daten, basis_feld)


def betriebsart_strom_kwh(daten: Optional[dict], modus: str) -> Optional[float]:
    """Gemessener **Strom**verbrauch dieser Betriebsart, oder ``None``."""
    feld = BETRIEBSART_STROM_FELD.get(modus)
    return _aufgeloest(daten, feld) if feld else None


def betriebsart_nutzenergie_kwh(daten: Optional[dict], modus: str) -> Optional[float]:
    """Gemessene **abgegebene Nutzenergie** dieser Betriebsart, oder ``None``."""
    feld = BETRIEBSART_NUTZENERGIE_FELD.get(modus)
    return _aufgeloest(daten, feld) if feld else None


def betriebsart_strom_felder_belegt(
    kandidaten, ist_belegt, *, modi=MESSBARE_MODI,
) -> list[str]:
    """Die Betriebsart-Strom-**Feldnamen**, die für dieses Gerät einen Zähler
    tragen — Gerätefeld schlägt Innengeräte, je Betriebsart (K2 auf der
    **Zuordnungs**-Ebene).

    ⭐ **Warum das hierher gehört und nicht in die Beitragsschicht** (R-1,
    15.09.2026): Es ist dieselbe Regel, die {@link _aufgeloest} auf der
    **Werte**-Ebene anwendet — *Gerätefeld, sonst Σ Innengeräte, nie beides*.
    Der Tag fragt sie an der Zuordnung (*„ist ein Zähler da?"*), der Monat an der
    Zeile (*„steht ein Wert?"*); die Regel steht deshalb einmal hier und nicht
    zweimal (F-56).

    Args:
        kandidaten: alle Feldnamen, die dieses Gerät tragen **kann** — inklusive
            der Innengerät-Kopien mit ``-<id>``-Suffix
            (``snapshot/keys.zaehler_feld_kandidaten``).
        ist_belegt: ``feld -> bool`` — trägt dieses Feld einen Zähler?
        modi: welche Betriebsarten gefragt sind. Default **alle messbaren**
            (K3 Regel 4: sie sind zusammen die Menge). Die Summanden-Lage fragt
            nur nach {@link MODI_OHNE_BEWERTETE_NUTZENERGIE} — dort steht
            ``betriebsart_strom_heizen_kwh`` **in** ``strom_heizen_kwh``, und
            beide zu nehmen wäre Doppelzählung (W-16/W-16b).

    Returns:
        Sortierte Feldnamen; leer, wenn kein Betriebsart-Zähler zugeordnet ist.
    """
    treffer: list[str] = []
    for modus in modi:
        basis = BETRIEBSART_STROM_FELD.get(modus)
        if not basis:
            continue
        if ist_belegt(basis):
            treffer.append(basis)
            continue
        treffer.extend(sorted(
            k for k in kandidaten
            if k != basis and basis_feld_key(k) == basis and ist_belegt(k)
        ))
    return treffer


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
    * ``warmwasser_kwh`` kommt im **gemessenen** Zweig nur aus dem Summanden
      ``strom_warmwasser_kwh`` — einen Betriebsart-Zähler dafür gibt es nicht
      (Begründung bei ``MESSBARE_MODI``); ohne getrennte Strommessung bleibt es
      dort 0 (N-766, s. {@link summanden_gelten}).

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
    def gemessene_summe_kwh(self) -> float:
        """Σ **aller** Betriebsart-Ströme dieser Zeile — die Menge in K3-Stufe 4.

        ⚠ **Nur im gemessenen Zweig eine Menge.** Im abgeleiteten Zweig
        *verteilt* der Split eine Menge, die schon woanders steht; ihn hier zu
        summieren gäbe sie ein zweites Mal (W-16b). Der einzige Aufrufer
        ({@link backend.core.field_definitions.wp_strom_aufteilung}) fragt
        deshalb vorher ``gemessen``.

        ⭐ **Warum sie neben ``funktionsfremd_kwh`` steht und nicht darin.** Jene
        Eigenschaft beantwortet *„welcher Teil hat keine bewertete
        Nutzenergie?"* (E4, der Nenner-Abzug); diese beantwortet *„wie viel hat
        das Gerät insgesamt verbraucht?"* (K1/R-1). Zwei Fragen, zwei Namen —
        sie zu einer zu falten wäre die F-56-Form.
        """
        return self.heizen_kwh + self.warmwasser_kwh + self.funktionsfremd_kwh

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
        je_modus = {
            KUEHLEN: self.kuehlen_kwh,
            LUEFTEN: self.lueften_kwh,
            ENTFEUCHTEN: self.entfeuchten_kwh,
        }
        return sum(je_modus[m] for m in MODI_OHNE_BEWERTETE_NUTZENERGIE)

    #: Stunden mit gültigem Modus-Signal, aus der Zeile übernommen.
    abdeckung_h: float = 0.0

    #: Nur im **gemessenen** Zweig belegt — der abgeleitete Split kennt sie
    #: nicht (s. Klassen-Docstring).
    lueften_kwh: float = 0.0
    entfeuchten_kwh: float = 0.0

    #: Abgeleitet aus dem Modus (N-336) ODER gemessen aus dem Summanden
    #: ``strom_warmwasser_kwh`` (N-766, nur bei getrennter Strommessung, s.
    #: {@link summanden_gelten}). Einen Betriebsart-Zähler für Warmwasser gibt
    #: es nicht; die *Arbeitszahl Warmwasser* liest ihren Nenner weiter direkt
    #: aus ``strom_warmwasser_kwh`` — eine andere Frage.
    warmwasser_kwh: float = 0.0


def summanden_gelten(params: Optional[dict]) -> bool:
    """Sind ``strom_heizen_kwh``/``strom_warmwasser_kwh`` dieses Geräts **Summanden** (N-766)?

    Das Kennzeichen ``getrennte_strommessung`` — dieselbe Frage, die
    ``field_definitions/wp_strom.py::wp_strom_aufteilung`` vor der K3-Stufe und
    ``waerme_verteilung.verteile_geraet_strom`` vor der Summanden-Familie stellt.
    Ohne Kennzeichen sind die Felder keine Summanden (ein alter Wert in der
    Zeile nach dem Abschalten) und gehen nicht in die Betriebsart-Aufteilung.
    """
    return bool((params or {}).get("getrennte_strommessung"))


def _summand(daten: dict, feld: str) -> Optional[float]:
    wert = daten.get(feld)
    if wert is None:
        return None
    try:
        return float(wert)
    except (TypeError, ValueError):
        return None


def modus_strom_zeile(
    daten: Optional[dict], *, summanden_zaehlen: bool = False,
) -> ModusStromZeile:
    """**Gemessen schlägt abgeleitet** — ganz oder gar nicht je Zeile (F-56).

    ⭐ **N-766 (simon42 MartyBr, 23.10.2026): im gemessenen Zweig zählen die
    Summanden mit, wenn sie Summanden sind** (``summanden_zaehlen``, das
    Kennzeichen ``getrennte_strommessung`` des Geräts — {@link
    summanden_gelten}). Heizen = ``betriebsart_strom_heizen_kwh`` (Gerätefeld,
    sonst Σ Innengeräte), sonst ``strom_heizen_kwh``; Warmwasser =
    ``strom_warmwasser_kwh``; jeweils nur ``is not None`` (0,0 ist eine Messung).
    Alle drei sind Zähler — die Regel «ganz oder gar nicht» (eine Hälfte Zähler,
    die andere Rechnung) bleibt gewahrt. Bis dahin zeigte eine Wärmepumpe mit
    Strom Heizen · Strom Warmwasser und einem Kühlzähler Heizen 0 und den ganzen
    Strom «nicht aufgeteilt». Ohne Kennzeichen wie bisher.

    Die Regel steht **nur hier**, obwohl sie an mehreren Flächen gebraucht wird:
    Monats-Fakten (Cockpit, Komponenten-Hub) und HA-/MQTT-Export, der seine
    IMD-Zeilen je Investition faltet und deshalb nicht über die Monats-Fakten
    geht (bekannte P10-Restschuld von ``ha_export/investition_sensoren.py``).

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
        heizen = betriebsart_strom_kwh(daten, HEIZEN)
        warmwasser = None
        if summanden_zaehlen:
            if heizen is None:
                heizen = _summand(daten, "strom_heizen_kwh")
            warmwasser = _summand(daten, "strom_warmwasser_kwh")
        return ModusStromZeile(
            heizen_kwh=heizen or 0.0,
            kuehlen_kwh=betriebsart_strom_kwh(daten, KUEHLEN) or 0.0,
            lueften_kwh=betriebsart_strom_kwh(daten, LUEFTEN) or 0.0,
            entfeuchten_kwh=betriebsart_strom_kwh(daten, ENTFEUCHTEN) or 0.0,
            warmwasser_kwh=warmwasser or 0.0,
            gemessen=True,
            abdeckung_h=abdeckung,
        )
    return ModusStromZeile(
        heizen_kwh=_zahl(daten.get(MODUS_STROM_FELD[HEIZEN])),
        kuehlen_kwh=_zahl(daten.get(MODUS_STROM_FELD[KUEHLEN])),
        # N-336: Warmwasser hier abgeleitet aus dem Modus; im gemessenen Zweig
        # gemessen aus dem Summanden (N-766, nur mit Kennzeichen).
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


def funktionsfremd_abzug_kwh(zeile: ModusStromZeile, *, hat_split: bool) -> float:
    """Was vom Nenner einer Arbeitszahl abgezogen werden **darf** — SOLL-§9-E7.

    ⭐ **Die Regel in einem Satz: abgezogen wird nur, was im Nenner steht.**
    Ein Abzug ist nur dann eine *Abgrenzung*, wenn die abgezogene Menge im
    Nenner **enthalten** ist. Steht sie nicht darin, ist er keine Präzisierung,
    sondern eine **Kürzung** — dieselbe Kategorie wie ADR-002/P4 („keine
    erfundene Menge"), nur mit umgekehrtem Vorzeichen.

    ⛔ **Zwei Fragen, zwei Namen — deshalb steht das hier und nicht in**
    {@link ModusStromZeile.funktionsfremd_kwh}. Jene Eigenschaft ist die
    *Definition* (*„welche Betriebsarten haben keine bewertete Nutzenergie?"* —
    Kühlen · Lüften · Entfeuchten, W-14/E4); diese Funktion ist die
    *Abzugsregel* (*„welcher Teil davon steckt überhaupt im Nenner?"*). Beide
    in eine Zahl zu falten hieße, eine Mengen-Aussage von einer
    Kennzahl-Entscheidung abhängig zu machen — die Aufteilung, die Restmenge
    und die Betriebsart-Balken lesen weiterhin die Definition und dürfen sich
    nicht mitverändern (K1: die Mengen bleiben unberührt).

    **Die vier Lagen, an der Additionsseite abgelesen** (`wp_strom_aufteilung`,
    `field_definitions.py` — sie trifft dieselbe Unterscheidung bereits, und
    Option A stellt nur die Symmetrie her, die dort schon steht):

    | Zweig | im Nenner enthalten? | Abzug |
    | --- | --- | --- |
    | **ohne** getrennte Strommessung | ja — ``stromverbrauch_kwh`` ist der Zählerstand des ganzen Geräts | ganz (**W-14**) |
    | F5, Stufe **„gesamt"** (ein Gesamtzähler ist zugeordnet bzw. gepflegt) | ja — der Nenner **ist** der Gesamtzähler (K1), und der trägt den Kühlstrom wie in Zeile 1 | **ganz** |
    | F5, Stufe **„fein"**, **mit gemessenem** Betriebsart-Zähler | ja — die Menge addiert ihn zu den Achsen (**W-16**) | ganz (**W-16b**) |
    | F5, Stufe **„fein"**, **abgeleiteter** Split | **nein** — der Split *verteilt* ``strom_heizen_kwh + strom_warmwasser_kwh``, er stellt nichts daneben | **0** |

    ⭐ **Die zweite Zeile hieß bis zum 14.09.2026 „feine Achse unvollständig"**
    und die vierte „**und vollständiger** feiner Achse". Seit WK-16d entscheidet
    nicht mehr die Vollständigkeit der Achse, sondern ob ein Gesamtzähler da
    ist — er ist dann die Menge (K1), auch neben zwei gepflegten Achsen. Die
    Regel hier ist unverändert: *abgezogen wird, was im Nenner steht*; nur die
    Lage, in der das zutrifft, ist häufiger geworden.

    ⭐ **Warum der dritte Fall keine Ausnahme, sondern derselbe Grundsatz ist**
    (SOLL §4.1, *„Ergänzung zu E7"*, Entscheid Gernot 12.09.2026 — Option A):
    E7 begründet an der **Kategorie**, dass eine *Verteilung* kein Nenner sein
    darf — *„eine Verteilung erbt jede Unschärfe ihres Schlüssels, eine Messung
    nicht."* Diese Begründung sagt nichts darüber, dass sie nur auf der
    Divisionsseite gälte: Ein Abzug nach der alten Bauform machte aus dem
    Nenner **Messung − Verteilung**, und das ist keine Messung mehr.

    ⚠ **Gemessen (Fixture ``test_n445_kuehlstrom_im_f5_heizstrom.py``,
    12.09.2026):** Dieselbe Anlage — Heizen 750 kWh Strom auf 3000 kWh Wärme,
    Warmwasser 200 auf 600, Kühlanteil 100 — zeigte **3,79** mit Kühlzähler
    (Handbuch Fall B) und **4,24** mit Betriebsmodus-Sensor. Ein Erfassungsweg
    *verbesserte* die Kennzahl um 12 %; das ist SOLL §3.3/**S1** in seiner
    Kern-Verletzung. Im Sommer stand *„nur Kühlbetrieb in diesem Zeitraum"*
    neben einer *Arbeitszahl Warmwasser 3,0* aus derselben Zeile.

    ⛔ **Die Funktions-Arbeitszahlen bleiben unberührt** (E7): Ihr Nenner ist
    der gemessene F5-Zähler, und dort wird ohnehin nichts abgezogen
    ({@link waermepumpe_kennzahl.arbeitszahl_je_funktion}).

    ⛔ **Die vierte Zeile ist seit dem 13.09.2026 da, und sie hat die Bedeutung
    des Arguments korrigiert (N-462).** ``hat_split`` hieß bis dahin faktisch
    „das Kennzeichen ``getrennte_strommessung`` ist gesetzt". Seit Etappe 3
    (26.08.2026) trägt der Bezug in der F5-Lücke aber den **Gesamtzähler** — und
    mit dem Kennzeichen als Kriterium zeigte dasselbe Gerät mit denselben
    Zählern **3,0 statt 3,75**, 20 % schlechter, allein weil ein Schalter
    gesetzt war, der in dieser Lage nichts misst. Genau die S1-Verletzung, gegen
    die E7 gebaut wurde, mit umgekehrtem Vorzeichen. **Die Tabelle oben ist an
    der Additionsseite abgelesen** — ändert sich die, muss die Abzugsseite
    mitziehen (Klasse **N-450**: dieselben *Eingänge*, nicht nur derselbe Layer).

    ⛔ **Dasselbe Wort, zwei Fragen — nicht verwechseln.** ``hat_split`` an
    {@link waermepumpe_kennzahl.arbeitszahl_je_funktion} und
    ``ImdTypBeitrag.wp_hat_split`` bleiben das **Kennzeichen**: Dort lautet die
    Frage *liegt der Strom getrennt je Funktion vor?*, und deren Antwort ist
    unverändert nein, sobald ein feiner Zähler fehlt. Hier lautet sie *ist der
    Nenner die feine Summe?*. Zwei Bedeutungen unter einem Namen sind die
    F-56-Falle; deshalb steht sie ausgeschrieben hier.

    Args:
        zeile: die aufgelöste Betriebsart-Zeile dieses Geräts.
        hat_split: **ist der Nenner dieser Zeile die feine Summe?** Also die
            Stufe, die {@link
            backend.core.field_definitions.wp_strom_aufteilung} gewählt hat —
            nicht das Kennzeichen. Die Aufrufer holen sie aus
            ``field_definitions.nenner_ist_feine_summe`` bzw. direkt aus
            ``wp_strom_aufteilung(...).stufe`` (Monatszeile) und aus
            ``aggregator.get_wp_strom_stufe_je_investition`` (Tag).
            ⛔ **Je Gerät, nie anlagenweit** — eine Anlage darf ein F5-Gerät
            neben einem nicht-F5-Gerät haben, und die Regel entscheidet für
            jedes einzeln (K2: *„je Gerät, ganz oder gar nicht"*).

    Returns:
        Die kWh, die vom Nenner abgezogen werden dürfen.
    """
    if hat_split and not zeile.gemessen:
        return 0.0
    return zeile.funktionsfremd_kwh


@dataclass(frozen=True)
class NutzenergieOhneKennzahl:
    """Die gemessene **Nutzenergie** der beiden Betriebsarten ohne Kennzahl (E4).

    ⭐ **Warum es diese Klasse gibt und nicht einfach zwei ``get``-Aufrufe:**
    Lüften und Entfeuchten bekommen nach **E4** bewusst keine Arbeitszahl — sie
    erzeugen keine Nutzenergie, die eedc bewerten könnte. *Erfassen* lässt sie
    sich trotzdem, und seit dem 26.08.2026 steht je Betriebsart ein
    Nutzenergie-Feld in der Registry. Bis zum 14.09.2026 hat sie **niemand
    gelesen** (N-398): vier zuordenbare Felder, vier Zähler, kein Ort, an dem
    ihre Zahl erschien.

    ⚠ **Menge ja, Kennzahl nein — und das ist keine halbe Lösung, sondern E4.**
    Die beiden Zeilen stehen als *Mengen* neben „Strom Lüften"/„Strom
    Entfeuchten"; ein Quotient aus ihnen wäre eine Effizienz-Aussage über einen
    Vorgang, dessen Nutzen eedc nicht kennt.

    ⛔ **Heizen und Kühlen stehen hier NICHT.** Für sie gibt es je einen
    eigenen, älteren Weg, und ein dritter Ort für dieselbe Menge wäre die
    W-3-Klasse: Die Nutzenergie **Heizen** ist Heizwärme und trägt **D1**
    ({@link backend.core.berechnungen.waermepumpe_kennzahl.heizwaerme_kwh}), die
    Nutzenergie **Kühlen** ist die Kältemenge und trägt die *Arbeitszahl Kühlen*
    ({@link backend.core.berechnungen.waermepumpe_kennzahl.arbeitszahl_kuehlen}).
    """

    lueften_kwh: float = 0.0
    entfeuchten_kwh: float = 0.0
    #: Liegt für **mindestens eine** der beiden ein Wert vor? `is not None`,
    #: nicht truthy: eine gemessene 0 ist eine Messung (CLAUDE.md, F-42).
    gemessen: bool = False


def nutzenergie_ohne_kennzahl_kwh(daten: Optional[dict]) -> NutzenergieOhneKennzahl:
    """Nutzenergie **Lüften** und **Entfeuchten** einer Zeile (E4, N-398).

    Gerätefeld schlägt Σ Innengeräte wie bei jedem Betriebsart-Feld — die Regel
    steht in {@link _aufgeloest} und nur dort.
    """
    lueften = betriebsart_nutzenergie_kwh(daten, LUEFTEN)
    entfeuchten = betriebsart_nutzenergie_kwh(daten, ENTFEUCHTEN)
    return NutzenergieOhneKennzahl(
        lueften_kwh=lueften or 0.0,
        entfeuchten_kwh=entfeuchten or 0.0,
        gemessen=lueften is not None or entfeuchten is not None,
    )
