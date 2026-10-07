"""Arbeitszahl einer Wärmepumpe — **die eine Definitionsstelle** (ADR-001).

Die Zahl ist ein Quotient aus zwei Zeilen, und genau deshalb steht sie hier:
Ihr Wert ist trivial, ihre **Sperre** ist es nicht. Ob aus Q und E überhaupt
ein Quotient gebildet werden darf, ist eine Abgrenzungsfrage (SOLL Wärme/Klima
§3.2b, Regel **R2**) — und die war bis 2026-08-26 an **drei** Stellen
nachgebaut, davon einer im Client:

======================================  ===================================
Stelle                                  Sperre
======================================  ===================================
``cockpit/komponenten.py:216`` (Hub)    ``jaz_belastbar``
``cockpit/uebersicht.py:456``           ``wp_waerme_abgeleitet <= 0``
``v4/KomponentenSektionen.tsx:311``     **keine**
======================================  ===================================

Die dritte ist die Sicht, die die Melder tatsächlich ansehen (*Cockpit →
Tag/Monat/Jahr*). Sie **konnte** die Sperre nicht kennen: Die Response lieferte
``wp_waerme_kwh`` und ``wp_strom_kwh``, sonst nichts. Folge — dieselbe Anlage
zeigte im Hub „—" und im Cockpit eine Zahl (Befund W-3).

⭐ **Der Fall ist der Lehrsatz von ADR-001 in Reinform:** Nicht die Formel ist
gedriftet, sondern ihre **Voraussetzung**. Eine Aggregat-Formel gehört in den
Layer, damit ihre Bedingungen mitwandern — nicht nur ihr Rechenweg.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence, Set as AbstractSet
from dataclasses import dataclass
from typing import Optional

# ⚠ **Ein Text-Modul, keine Registry** — die Layer-Regel aus ADR-001 hält.
# Die drei Tages-Zustände (W-18) erscheinen als Grund unter derselben
# Kachel wie die Gründe dieser Datei; ihre Klassifizierung gehört deshalb
# in DIESELBE Tabelle. Sie danebenzuschreiben wäre die W-3-Klasse.
from backend.core.betriebsmodus import (
    BETRIEBSART_NUTZENERGIE_FELD,
    HEIZEN,
    WAERME_ACHSEN,
    WARMWASSER,
)
from backend.core.tageswert_grund import (
    GRUND_KEINE_ZAEHLERSTAENDE,
    GRUND_ZAEHLER_RUECKSPRUNG,
    TAGESWERT_GRUND_KURZ,
)

#: Unterhalb dieser Arbeitszahl bekommt die Zahl einen erklärenden Satz
#: (SOLL §2.2.1, Fall **H-B**). Die Grenze ist bewusst großzügig: Eine
#: Wärmepumpe erreicht 3–4, ein elektrischer Heizstab ≈ 1. Alles unter 2 heißt,
#: dass ein erheblicher Teil der Wärme direkt elektrisch erzeugt wurde.
JAZ_HEIZSTAB_SCHWELLE = 2.0


@dataclass(frozen=True)
class Arbeitszahl:
    """Die Arbeitszahl **mit ihrer Begründung** — nie nur die Zahl.

    ``wert`` ist ``None``, wo keine Kennzahl gebildet werden darf; ``grund``
    sagt dann warum. Beides zusammen, weil ein „—" ohne Grund die häufigste
    Beschwerde dieser Fläche ist (SOLL §3.3/**S3**).
    """

    wert: Optional[float]
    #: Warum es die Zahl nicht gibt. **Bewusst kurz** — der Text steht als
    #: sichtbare Zeile unter dem „—", nicht in einem Hover-Tooltip: S3 verlangt
    #: *„nicht ‚—', sondern der Grund"*, und ein Tooltip ist auf dem Telefon
    #: keine Auskunft. Was ausführlicher erklärt werden muss, gehört ins
    #: Handbuch, nicht auf die Kachel.
    grund: Optional[str] = None
    #: Die Zahl ist gebildet, aber erklärungsbedürftig (Fall H-B, Heizstab).
    #: **Kein** Fehler und keine Bewertung — eine Anlage, die ihr Warmwasser
    #: über den Heizstab macht, *hat* eine Arbeitszahl nahe 1.
    hinweis: Optional[str] = None
    #: Die beiden Zahlen, aus denen ``wert`` **tatsächlich** entstanden ist —
    #: Q im Zähler, E im Nenner, beide in kWh. Nur gesetzt, wenn es einen
    #: ``wert`` gibt.
    #:
    #: ⭐ **Warum sie aus dem Layer kommen müssen und nicht aus der Response.**
    #: Der Nenner ist **nicht** ``wp_strom_kwh``: ``strom_funktionsfremd_kwh``
    #: (Kühlen, Lüften, Entfeuchten) ist abgezogen. Wer die Herleitung aus den
    #: beiden Anzeigefeldern nachbaut, zeigt bei jeder Anlage mit erfasstem
    #: Betriebsmodus eine Rechnung, die **nicht** auf die Zahl daneben führt —
    #: dieselbe Klasse wie eine Zahl, die aus zwei gerundeten zurückgerechnet
    #: wird. Deshalb reicht diese Stelle die benutzten Werte heraus, so wie sie
    #: ``grund`` und ``hinweis`` schon herausreicht.
    #:
    #: ⚑ Der Anlass: Ein Melder (dietmar1968, T89667 #283) hatte eine
    #: Arbeitszahl von 0,7 vor sich — physikalisch unmöglich und damit ein
    #: sicheres Zeichen für einen falsch zugeordneten Zähler. Die Kachel nannte
    #: als Formel nur „JAZ = Wärme ÷ Strom"; mit den Zahlen daneben wäre die
    #: Ursache sofort sichtbar gewesen. **eedc warnt deshalb nicht** — es zeigt,
    #: womit es gerechnet hat, und überlässt den Schluss dem Anwender.
    zaehler_kwh: Optional[float] = None
    nenner_kwh: Optional[float] = None

    @property
    def belastbar(self) -> bool:
        return self.wert is not None


#: Der Satz für Fall H-B. Er erklärt die **Zahl**, er bewertet nicht den
#: Anwender — eedc ist nicht die Strom-Polizei.
HEIZSTAB_HINWEIS = (
    "Eine Arbeitszahl nahe 1 entsteht, wenn ein großer Teil der Wärme direkt "
    "elektrisch erzeugt wurde (Heizstab, Zusatz- oder Notheizung). Die Zahl "
    "beschreibt die Anlage in diesem Zeitraum, sie ist kein Fehler."
)


def waerme_gesamt_kwh(
    waerme_kwh: Optional[float],
    heizung_kwh: Optional[float],
    warmwasser_kwh: Optional[float],
) -> float:
    """Die Wärme **gesamt** — Gesamtwert vor Summanden (D1, kanonisch).

    Liegt eine gemessene Gesamtwärme vor, gilt sie. Sonst ist die Wärme die
    Summe ihrer beiden Achsen.

    ⭐ **Warum das eine Funktion ist:** Die Regel stand im Layer
    (`imd_monatsaggregat`) **und** im Client (`v4/TagKomponenten.tsx:89`, dort
    seit der ersten Fassung der Datei). Der Client hatte nur die zweite Hälfte —
    für den Tag richtig, weil es dort keine gepflegte Gesamtwärme gibt, aber
    eine zweite Stelle für dieselbe Regel (Befund W-9, ADR-001/S1). Seit
    2026-08-26 liefert der Tages-Endpoint die Größe fertig.
    """
    if waerme_kwh:
        return float(waerme_kwh)
    return float(heizung_kwh or 0.0) + float(warmwasser_kwh or 0.0)


def heizwaerme_kwh(daten: Optional[dict]) -> Optional[float]:
    """Die **Heizwärme** einer Monatszeile — Gerätefeld, sonst Betriebsart (N-398).

    Der Zähler von D1 auf der Heizachse, an **einer** Stelle:

    1. ``heizenergie_kwh`` — der Wärmemengenzähler des Geräts.
    2. ``heizung_kwh`` — derselbe Wert unter dem Legacy-Namen (die Lesetür
       {@link backend.core.field_definitions.get_wp_heizenergie_kwh} kennt ihn
       seit jeher; ihn hier zu übergehen hieße, Altbestand zu verlieren).
    3. **Sonst** die gemessene *Nutzenergie Heizbetrieb* —
       ``betriebsart_nutzenergie_heizen_kwh``, am Gerät oder je Innengerät.
    4. Sonst ``None`` — **nicht 0**: „kein Zähler" und „Zähler stand auf null"
       sind verschiedene Aussagen (ADR-002/P4).

    ⭐ **Warum Stufe 3 überhaupt dazugehört (N-398, offen seit 05.09.2026).**
    Das Feld ist seit dem 26.08.2026 zuordenbar und wurde von **nichts**
    gelesen. Wer es pflegte — der Kanon für eine Split-Klimaanlage, die ihre
    abgegebene Wärme je Innengerät misst —, sah im Komponenten-Hub
    ``gesamt_heizenergie_kwh`` **0** und darunter den Grund *„kein
    Wärmemengenzähler zugeordnet"*. Der Satz war nicht nur nutzlos, er war
    **falsch**: Der Zähler war zugeordnet.

    ⚠ **Dieselbe Weiche wie auf der Stromseite (K2), nicht eine neue.**
    ``_aufgeloest`` entscheidet Gerätefeld-vor-Innengeräten für jedes
    Betriebsart-Feld; hier kommt nur die Ebene darüber dazu — die **Achse**
    (``heizenergie_kwh``) schlägt die **Teilmenge** (Betriebsart). Das ist die
    Richtung von K1: Der gröbere, vollständigere Zähler gewinnt.

    ⛔ **Eine gepflegte 0 gewinnt gegen Stufe 3.** „Diesen Monat nicht geheizt"
    ist eine Messung und darf nicht von einem Betriebsart-Zähler verdrängt
    werden — die F-42-Klasse. ⚠ Wie genau der Vorrang der ersten beiden Stufen
    untereinander fällt, entscheidet dagegen **die alte Lesetür und nicht diese
    Funktion**: Sie ist dort bitgleich nachgebaut (s. Kommentar im Rumpf), damit
    an bestehenden Zeilen nichts kippt.

    ⛔ **Sie addiert nichts.** Gerätefeld und Betriebsart-Nutzenergie beschreiben
    dieselbe Wärme auf zwei Ebenen; sie zu summieren wäre die Doppelzählung, vor
    der der Modulkopf von ``betriebsart_gemessen`` warnt.
    """
    d = daten if isinstance(daten, dict) else {}
    # ⚠ **Die ersten beiden Zeilen sind bitgleich zu**
    # {@link backend.core.field_definitions.get_wp_heizenergie_kwh} — mit
    # ``or``, nicht mit ``is not None``. Das ist kein Flüchtigkeitsfehler,
    # sondern Absicht: Eine Zeile, die ``heizenergie_kwh: 0`` **und** den
    # Legacy-Wert ``heizung_kwh: 7`` trägt, liefert dort seit jeher 7. Diese
    # Funktion darf an bestehenden Zeilen **nichts** verändern; sie hängt nur
    # eine dritte Stufe an, wo bisher 0 herauskam.
    wert = d.get("heizenergie_kwh") or d.get("heizung_kwh")
    if wert:
        try:
            return float(wert)
        except (TypeError, ValueError):
            return None
    # **Eine gemessene 0 ist eine Messung** (CLAUDE.md, F-42) und verdrängt den
    # Rückfall — „diesen Monat nicht geheizt" ist eine Aussage über das Gerät.
    if d.get("heizenergie_kwh") is not None or d.get("heizung_kwh") is not None:
        return 0.0
    # Lokaler Import: `betriebsart_gemessen` liest `field_definitions`, dieses
    # Modul wird von dort NICHT gelesen — ein Import auf Modulebene wäre
    # zulässig, bleibt aber hier, damit die Abhängigkeit an der Stelle steht,
    # die sie braucht (dieselbe Bauform wie in `wp_strom_aufteilung`).
    from backend.core.berechnungen.betriebsart_gemessen import (
        betriebsart_nutzenergie_kwh,
    )
    from backend.core.betriebsmodus import HEIZEN

    return betriebsart_nutzenergie_kwh(d, HEIZEN)


def heizwaerme_je_geraet(
    heizenergie_je_inv: Optional[Mapping[str, float]],
    betriebsart_heizen_je_inv: Optional[Mapping[str, float]],
) -> dict[str, float]:
    """**D1-Stufe 3 je Gerät** — Wärmemengenzähler, sonst Nutzenergie Heizbetrieb.

    Der Zwilling zu {@link waerme_gesamt_je_geraet} eine Achse tiefer, und aus
    demselben Grund **je Gerät**: Welcher Zähler die Heizwärme trägt, entscheidet
    das Gerät, nicht die Anlage (E1 — die Anlage ist die Summe ihrer je
    aufgelösten Geräte, nie die Auflösung ihrer Summe).

    ⭐ **Wozu (R-2, N-487):** Bis zum 15.09.2026 kannte der **Tag** von den vier
    Nutzenergie-Feldern nur KÜHLEN. Ein Gerät, das seine abgegebene Heizwärme je
    Betriebsart misst (der #263-Kanon einer Split-Klimaanlage), zeigte sie in
    Monat und Jahr — und im Tag stand *„kein Wärmemengenzähler zugeordnet"*,
    obwohl er zugeordnet war. Dieselbe Falschaussage, die N-398 im Monat
    beseitigt hat, eine Zeitebene tiefer.

    ⛔ **Die Regel selbst wird nicht nachgebaut** — jede Zeile läuft durch
    {@link heizwaerme_kwh}. Damit gilt auch hier: eine gemessene **0** aus dem
    Wärmemengenzähler gewinnt gegen den Betriebsart-Zähler (F-42), und addiert
    wird nie.

    Args:
        heizenergie_je_inv: ``{inv_id: kwh}`` des Heiz-Wärmemengenzählers
            (Tages-Ausgabekey ``wp_heizung_kwh``).
        betriebsart_heizen_je_inv: ``{inv_id: kwh}`` der gemessenen Nutzenergie
            Heizbetrieb (``wp_betriebsart_heizen_kwh``), je Gerät bereits
            K2-aufgelöst.

    Returns:
        ``{inv_id: kwh}`` über die Vereinigung beider Schlüsselmengen; Geräte
        ohne jede Heizwärme erscheinen **nicht** (ADR-002/P4).
    """
    _achse: Mapping[str, float] = heizenergie_je_inv or {}
    _betriebsart: Mapping[str, float] = betriebsart_heizen_je_inv or {}
    ergebnis: dict[str, float] = {}
    for inv in set(_achse) | set(_betriebsart):
        daten: dict[str, float] = {}
        if inv in _achse:
            daten["heizenergie_kwh"] = _achse[inv]
        if inv in _betriebsart:
            daten[BETRIEBSART_NUTZENERGIE_FELD[HEIZEN]] = _betriebsart[inv]
        wert = heizwaerme_kwh(daten)
        if wert is not None:
            ergebnis[inv] = wert
    return ergebnis


def waerme_gesamt_je_geraet(
    gesamt_je_inv: Optional[Mapping[str, float]],
    *teile_je_inv: Optional[Mapping[str, float]],
) -> dict[str, float]:
    """D1 **je Gerät** — und erst danach summieren.

    ⛔ **Warum das nicht dieselbe Frage auf der Anlagensumme ist.** ``waerme_kwh``
    ist ein Feld **am Gerät** (`INVESTITION_FELDER["waermepumpe"]`), und E1 sagt
    für die Anlage: *„Mengen dürfen nebeneinander stehen"* — die Anlage ist die
    **Summe ihrer Geräte nach der Auflösung**, nie eine Auflösung über den
    Summen. Der Unterschied wird sichtbar, sobald zwei Wärmepumpen verschieden
    zählen (gemessen 14.09.2026, N-391b):

    ======================  =============  ==========================
    Gerät                   Felder         D1 dieses Geräts
    ======================  =============  ==========================
    WP1 (Gesamtzähler)      waerme 30      **30**
    WP2 (zwei Zähler)       heiz 20, ww 5  **25**
    ======================  =============  ==========================

    Je Gerät ergibt das **55**, wie der Monat für denselben Bestand. Auf den
    Anlagensummen (``waerme_gesamt_kwh(30, 20, 5)``) ergibt es **30** — die
    Aufteilung von WP2 verschwindet still hinter dem Gesamtwert von WP1, und
    genau diese Teilsumme ohne Hinweis verbietet ADR-002/**P4**.

    Args:
        gesamt_je_inv: ``{inv_id: kwh}`` des gemeinsamen Wärmemengenzählers.
        *teile_je_inv: die **Summanden** je Gerät, eine Abbildung je Achse
            (Heizwärme, Warmwasser-Wärme). Variadisch, weil die Aufrufer ihre
            Achsen aus einer benannten Menge nehmen
            (``aggregator.WAERME_AUSGABE_KEYS``) und eine dritte Achse dort
            sonst still aus der Summe fiele.

    Returns:
        ``{inv_id: waerme_kwh}`` über die Vereinigung aller Schlüssel — jede
        Zeile über {@link waerme_gesamt_kwh}, damit die Regel eine Stelle hat.
    """
    _gesamt: Mapping[str, float] = gesamt_je_inv or {}
    _teile = [t or {} for t in teile_je_inv]
    inv_ids = set(_gesamt) | {inv for teil in _teile for inv in teil}
    return {
        inv: waerme_gesamt_kwh(
            _gesamt.get(inv),
            sum(float(teil.get(inv) or 0.0) for teil in _teile),
            None,
        )
        for inv in inv_ids
    }


def geraete_mit_gesamtwaerme(
    gesamt_je_inv: Optional[Mapping[str, float]],
) -> frozenset[str]:
    """Die Geräte, an denen D1 auf den **Gesamtwert** fällt.

    Dieselbe Bedingung wie in {@link waerme_gesamt_kwh} (``if waerme_kwh``), nur
    als Menge statt als Zweig — für Leser, die nicht die Menge brauchen, sondern
    die Frage *„welche Zähler zeichnen dieses Gerät?"*: die Stundenlinie legt für
    genau diese Geräte den Gesamtschlüssel und für alle anderen die beiden Achsen.
    Eine gemessene **0** ist kein Gesamtwert — sonst verlöre ein Gerät seine
    Aufteilung an einen Zähler, der an diesem Tag nichts gemeldet hat.
    """
    return frozenset(inv for inv, wert in (gesamt_je_inv or {}).items() if wert)


#: **Gemessene Null, nicht fehlender Zähler** — die Gegenstücke zu
#: {@link GRUND_KEIN_KUEHLBETRIEB} auf der Wärmeseite (dietmar1968, T89667 #322).
#:
#: ⛔ **Der Fall, den sie abdecken, sah bis hierher aus wie ein fehlender Zähler.**
#: ``arbeitszahl`` faltete ``None`` und ``0.0`` in ``float(waerme_kwh or 0.0)``
#: zusammen und nannte beides „kein Wärmemengenzähler zugeordnet". Für einen
#: Septembertag ohne Heizbetrieb ist das eine **Falschaussage**: Der Zähler ist
#: zugeordnet und meldet korrekt Null. Der Melder hat daraufhin nach einem
#: Zuordnungsfehler gesucht, den es nicht gab.
#:
#: ⭐ **Der Wortlaut ist von der Kühlseite übernommen, nicht neu erfunden.**
#: Dort steht seit W-5 „kein Kühlbetrieb in diesem Zeitraum" für exakt dieselbe
#: Lage. Zwei Sprachen für einen Sachverhalt auf einer Seite wären die Klasse,
#: gegen die N-327 den EINEN Wortlaut durchgesetzt hat.
#:
#: ⚠ **Warum kein Quotient statt eines Grundes.** 0 kWh Wärme ÷ 1 kWh Strom
#: ergibt 0 — wahr und trotzdem irreführend: Der Strom ist Standby und
#: Umwälzung, kein misslungenes Heizen. Eine 0 an der Stelle einer Arbeitszahl
#: liest sich als Bewertung des Geräts.
GRUND_KEIN_HEIZBETRIEB = "kein Heizbetrieb in diesem Zeitraum"
GRUND_KEINE_WARMWASSERBEREITUNG = "keine Warmwasserbereitung in diesem Zeitraum"

#: Für den Zeitraum liegt **überhaupt kein** Strom vor.
#:
#: ⚠ **Er stand bis zum 14.09.2026 als Literal in** ``arbeitszahl`` **und wurde
#: nur deshalb hier zur Konstante**: Die D-Sicht (Konzept §6) muss jeden Grund
#: **einer** Klasse zuordnen — Ausstattung oder Zeitraum —, und eine Zeichenkette
#: ohne Namen lässt sich nicht zuordnen, ohne sie ein zweites Mal zu tippen.
#: Der Wortlaut ist unverändert; das Handbuch zitiert ihn weiterhin wörtlich.
GRUND_KEIN_STROM = "kein Stromverbrauch erfasst"

#: Der ganze Strom ging in eine Funktion ohne bewertete Nutzenergie.
GRUND_NUR_KUEHLBETRIEB = "nur Kühlbetrieb in diesem Zeitraum"

#: Es liegt keine gemessene Wärme vor und der Aufrufer kennt keinen genaueren
#: Grund (**W-18**-Default).
GRUND_KEINE_WAERMEMESSUNG = "kein Wärmemengenzähler zugeordnet"

#: Die Wärme kam aus ``Strom × JAZ``; ein Quotient daraus gäbe genau den Faktor
#: zurück, mit dem gerechnet wurde (Konzept §3.5).
GRUND_WAERME_ABGELEITET = "Wärme ist gerechnet, nicht gemessen"

#: Grund für die Abgrenzungs-Sperre, wenn der Block Strom von Geräten trägt,
#: deren Wärme fehlt (SOLL §4.2 Fall 1). Kurz — er steht sichtbar auf der Kachel.
#:
#: ⭐ **Seit E1b (14.09.2026) sperrt er die ANLAGENWEITE Zahl nicht mehr** —
#: dort wird er zur unteren **Schranke** ({@link systemarbeitszahl}). Als Grund
#: **je Funktion** und als Auskunft im Hub bleibt er unverändert: R2 gilt je
#: Gerät und je Funktion weiter.
GRUND_GERAETE_OHNE_WAERME = "nicht alle Geräte melden Wärme"

#: **R2/W-7 — Fall H-C:** Der Strom eines fremden Verbrauchers (typisch ein
#: Heizstab) liegt auf dem WP-Zähler, seine Wärme läuft nicht über den
#: Wärmemengenzähler. ⇒ **E ist zu groß**, die Arbeitszahl systematisch zu
#: niedrig. Von außen unsichtbar — es ist eine Anwender-Angabe
#: (`PARAM_WAERMEPUMPE["ABGRENZUNG"] = "fremdstrom"`).
#:
#: ⛔ **Der Grund nennt seit dem 13.09.2026 die KLASSE, nicht das Beispiel
#: (N-371).** Bis dahin lautete er „Heizstab-Strom auf dem WP-Zähler" — und
#: damit las jemand, dessen **Klimaanlage** auf demselben Zähler hängt, einen
#: Satz über ein Gerät, das er nicht besitzt. Es ist dieselbe Bauform, gegen
#: die {@link GRUND_FREMDWAERME} weiter unten seit N-349 gebaut ist und die
#: ``abgrenzung_verletzt`` ausdrücklich vermeidet (*„Ein Kennzeichen je Beispiel
#: hätte eine Fallsammlung daraus gemacht"*): die **Regel** war allgemein, ihr
#: **Anwendertext** blieb Fallsammlung. Der Heizstab steht weiter als Beispiel
#: darin — er ist der häufigste Fall, nur nicht der einzige.
#:
#: ⚠ Der Text ist ein **Zitat** an drei Orten: Handbuch §4 („Die Gründe,
#: wörtlich"), Jahresbericht-PDF und die Kachel-Untertitel im Hub. Wer ihn
#: ändert, zieht ``docs/HANDBUCH_WAERME_KLIMA.md`` mit —
#: ``test_handbuch_waerme_klima_zitiert_die_gruende_woertlich`` meldet es.
GRUND_FREMDSTROM = "Ein weiterer Verbraucher auf dem WP-Zähler (z. B. Heizstab)"

#: **R2/F12 — bivalent:** Ein zweiter Wärmeerzeuger speist denselben Kreis, sein
#: Aufwand liegt nicht auf dem WP-Zähler. ⇒ **Q ist zu groß**, die Arbeitszahl
#: zu hoch.
#:
#: ⛔ **Der zweite Erzeuger ist nicht zwingend ein Kessel (N-349, 29.08.2026).**
#: Ein **elektrischer Heizstab**, dessen Wärme durch denselben
#: Wärmemengenzähler läuft, während sein Strom getrennt gezählt wird, ist
#: derselbe Fall — und bei Daikin und Nibe der Regelfall. Bis zum 29.08. nannten
#: alle vier Anwendertexte nur „Gas- oder Ölkessel"; das Wort *Heizstab* stand
#: baumweit **ausschließlich** bei ``GRUND_FREMDSTROM``, also auf der
#: Gegenseite, die die Lage sogar ausdrücklich ausschließt. Wer sich nicht
#: wiedererkennt, lässt „Kein Fremdanteil" stehen — und bekommt eine
#: systematisch **zu hohe** Arbeitszahl ohne Hinweis, weil
#: {@link JAZ_HEIZSTAB_SCHWELLE} nur nach unten feuert.
#:
#: ⚠ **Das war kein Rechenfehler, sondern eine Fallsammlung im Anwendertext** —
#: und damit dieselbe Bauform, gegen die ``abgrenzung_verletzt`` weiter unten
#: ausdrücklich gebaut ist (*„Ein Kennzeichen je Beispiel hätte eine
#: Fallsammlung daraus gemacht"*). Die **Regel** war verallgemeinert, ihre
#: **Beschreibung** nicht. Gemeldet hat es rapahl (T89667 #249) — nicht als
#: Fehlerbericht, sondern als Widerspruch gegen einen Rat, der genau in diese
#: Lage führte.
#:
#: ⭐ **Dieselbe Verletzung wie `GRUND_FREMDSTROM`, nur mit umgekehrtem
#: Vorzeichen** — und der Prüfstein dafür, dass R2 die richtige Abstraktionshöhe
#: hat: Der Fall hat **keinen Melder** und stand in **keiner** der vier Lagen des
#: SOLL §4.2. Sichtbar wurde er erst, als die Fallsammlung zu einer Regel
#: verallgemeinert wurde. Eine Aufzählung hätte ihn nie hervorgebracht.
GRUND_FREMDWAERME = "zweiter Erzeuger am Wärmezähler"

#: **R2/Zeitraum — SOLL §4.2 Fall 3:** Q und E stammen aus verschieden langen
#: Messzeiträumen (etwa: Wärme aus dem Monatsabschluss, Strom aus einem
#: Connector-Delta, das erst mitten im Monat zu messen begann). Der Quotient
#: wäre einer aus zwei Wirklichkeiten.
GRUND_ZEITRAUM = "Zähler messen verschiedene Zeiträume"

#: **N-441 — die Block-Ebene bekommt die zweite Richtung.** Wärme von einem
#: Gerät, Strom von einem anderen: beide Seiten tragen Geräte, aber nicht
#: dieselben.
#:
#: ⛔ **Warum {@link GRUND_GERAETE_OHNE_WAERME} das nicht abdeckt.** Jener Satz
#: ist **gerichtet** — „im Nenner der Strom von allen, im Zähler die Wärme von
#: weniger" (Handbuch §4). Er beschreibt die echte Teilmenge ``w ⊊ s`` und
#: stimmt dort. In der Gegenrichtung (ein Gerät meldet Wärme, sein Strom fehlt)
#: kippt die Zahl nach **oben**, und ein Rat, „einen Wärmemengenzähler
#: zuzuordnen", ginge ins Leere. Gemessen am Anlassfall (Wärme 2400 von A,
#: Heizstrom 800 von B): **3,0 ohne jeden Grund**, an die Community als
#: belastbar gemeldet.
#:
#: ⚠ Wortgleich zu seinem Funktions-Zwilling
#: {@link GRUND_FUNKTION_NICHT_DECKUNGSGLEICH}, nur ohne „dieser Funktion" —
#: hier geht es um die **Gesamt**zahl des Blocks. Und wie dort nennt er die
#: Ursache, nicht den Ausweg: einen allgemeingültigen gibt es nicht.
GRUND_GERAETE_VERSCHIEDEN = "Wärme und Strom stammen von verschiedenen Geräten"

#: **N-441 — dieselbe Störung über die ZEIT statt über die Geräte**, auf der
#: Block-Ebene. Das Block-Analogon zu
#: {@link GRUND_FUNKTION_VERSCHIEDENE_MONATE}.
#:
#: Ein Monat trägt Wärme **ohne** Strom, ein anderer trägt Strom: Die
#: Jahressumme nimmt beide mit und ergäbe eine zu hohe Zahl (gemessen **6,0**
#: statt 3,0 in *Cockpit → Jahr* **und** im Komponenten-Hub). Bis hierher sah
#: die Block-Regel nur den einzelnen Monat und faltete ihn mit ``any(...)`` —
#: eine Lage, die erst über mehrere Monate entsteht, konnte sie strukturell
#: nicht sehen.
#:
#: ⚠ **„Wärme", nicht „Nutzenergie"** — anders als beim Funktions-Zwilling.
#: Die Gesamtzahl des Blocks trägt **keine** Kältemenge im Zähler
#: (``arbeitszahl`` zieht den Kühlstrom aus dem Nenner ab, W-14/E4); ihr Zähler
#: ist Wärme, und der Satz darf das sagen.
GRUND_GERAETE_VERSCHIEDENE_MONATE = (
    "Wärme und Strom stammen aus verschiedenen Monaten"
)

#: **R2/Bauart — SOLL §5:** Der Block trägt Geräte **verschiedener Bauart**
#: (Luft-Wasser-Wärmepumpe und Luft-Luft-Split-Klimaanlage). Ihre Mengen dürfen
#: nebeneinander stehen, eine **gemeinsame Kennzahl** nicht: Sie haben
#: verschiedene Funktionen, verschiedene Nutzenergie und verschiedene
#: Vergleichsmaßstäbe. So steht es wörtlich im Konzept — *„Mengen dürfen
#: nebeneinander stehen, eine gemeinsame JAZ nicht."*
#:
#: ⭐ **Die Frage stammt vom Melder selbst** (dietmar1968, T89667 #201):
#: *„Ist es nicht sinnvoller, die Luft-Wasser-Wärmepumpe von der
#: Luft-Luft-Klimaanlage komplett zu trennen?"* — für die Kennzahl ist die
#: Antwort zwingend ja, und bis zum 28.08.2026 tat eedc genau das nicht.
#:
#: ⚠ **Warum das mehr ist als ein Sonderfall von `GRUND_GERAETE_OHNE_WAERME`.**
#: Eine Split-Klimaanlage hat bauartbedingt keinen Wärmemengenzähler
#: (`ist_luft_luft_waermepumpe` — das Formular sagt es dem Anwender zu). Ihr
#: Strom landete damit im Nenner, ohne dass ihre Nutzenergie je in den Zähler
#: kommen kann: **die Arbeitszahl konnte nur zu klein sein, dauerhaft und ohne
#: Aussicht auf Besserung.** Der allgemeinere Grund hätte zwar auch gesperrt,
#: aber zu einer Zuordnung geraten, die es beim Anwender nicht geben kann —
#: dieselbe Klasse wie der Daten-Checker-Hinweis, der dietmar1968 zu einem
#: unmöglichen Sensor schickte (Forum #89667/87).
GRUND_BAUARTEN_GEMISCHT = "Wärmepumpe und Klimaanlage in einer Zahl"

#: Die Anwender-Angabe → ihr Grund. **Der Layer übersetzt, nicht die Route** —
#: sonst stünde derselbe Text an vier Aufrufstellen.
GRUND_JE_ABGRENZUNG: dict[str, str] = {
    "fremdstrom": GRUND_FREMDSTROM,
    "fremdwaerme": GRUND_FREMDWAERME,
}


#: Herkunft der Wärme, wie der Komponenten-Hub sie nennt (SOLL §3.3: „zusätzlich
#: die Herkunft jeder Zahl — gemessen · abgeleitet · gepflegt").
HERKUNFT_GEMESSEN = "gemessen"


def waerme_herkunft(waerme_abgeleitet: bool, faktor: Optional[float]) -> str:
    """„gemessen" — oder „geschätzt: Strom × JAZ 3,5".

    **B3 (05.09.2026, SOLL §6 Präzisierung):** Eine aus ``Strom × gepflegte JAZ``
    abgeleitete Wärme ist zulässig, *erscheint aber als geschätzt*. Bis B3 stand
    sie im Hub als nackte Zahl neben gemessenen — nur die gesperrte Arbeitszahl
    verriet die Herkunft. Der Text entsteht hier, damit Hub, Cockpit und PDF
    dieselben Worte tragen (die W-3-Klasse: eine Aussage, ein Ort).
    """
    if not waerme_abgeleitet:
        return HERKUNFT_GEMESSEN
    if faktor is not None:
        return f"geschätzt: Strom × JAZ {faktor:.1f}".replace(".", ",")
    return "geschätzt: Strom × gepflegte JAZ"


#: Vorbehalt an Ersparnis und CO₂ bei abgeleiteter Wärme.
VORBEHALT_ABGELEITET = "Wärme geschätzt — Ersparnis und CO₂ folgen aus der Schätzung"
#: Vorbehalt an Ersparnis und CO₂ im bivalenten Fall (F12): der zweite Erzeuger
#: liefert Wärme durch denselben Zähler, seine Kosten sieht eedc nicht.
VORBEHALT_FREMDWAERME = (
    "zweiter Erzeuger am Wärmezähler — Ersparnis und CO₂ enthalten dessen Wärme"
)


def ersparnis_vorbehalt(
    *,
    waerme_abgeleitet: bool,
    abgrenzung: Optional[str],
) -> Optional[str]:
    """Der Satz, der neben Ersparnis und CO₂ steht — oder ``None``.

    **Warum ein Vorbehalt und keine Sperre** (Entscheid Gernot 05.09.2026, B3):
    Unterdrückt wird nur, was nie gemessen wurde. Die Ersparnis aus geschätzter
    Wärme ist eine zulässige Schätzung (§6) — sie muss es nur sagen. Im
    bivalenten Fall (``abgrenzung == "fremdwaerme"``, F12) zählt die Wärme des
    Gaskessels als vermiedene Gaskosten mit; eedc kennt seinen Anteil nicht und
    rechnet ihn nicht heraus — es sagt, dass er drin ist.

    Beide Fälle zugleich: beide Sätze, durch „ · " getrennt.
    """
    teile: list[str] = []
    if waerme_abgeleitet:
        teile.append(VORBEHALT_ABGELEITET)
    if abgrenzung == "fremdwaerme":
        teile.append(VORBEHALT_FREMDWAERME)
    return " · ".join(teile) if teile else None


def abgrenzungs_grund(
    *,
    abgrenzung_stoerung: Optional[str] = None,
    bauarten_gemischt: bool = False,
    geraete_ohne_waerme: bool = False,
    zeitraum_versetzt: bool = False,
    geraete_verschieden: bool = False,
    perioden_versetzt: bool = False,
) -> Optional[str]:
    """Der Grund, warum Q und E **nicht dieselbe Abgrenzung** tragen — oder ``None``.

    **Die eine Stelle, an der R2 aus den drei erkennbaren Lagen einen Grund
    macht.** Ohne sie stünde die Reihenfolge an vier Aufrufstellen nebeneinander
    und würde beim nächsten Fall zum fünften Mal getippt — genau die Bauform, die
    Befund W-3 erzeugt hat (dieselbe Frage an drei Stellen, eine davon im
    Client).

    ⭐ **Die Reihenfolge ist eine Entscheidung, keine Willkür** (Entscheid
    Gernot, 26.08.2026): **Die Anwender-Angabe schlägt die Selbsterkennung.**
    Wer eingetragen hat, dass sein Heizstab auf dem WP-Zähler liegt, bekommt
    genau diesen Satz zu lesen — nicht den allgemeineren „nicht alle Geräte
    melden Wärme", der auf dieselbe Anlage ebenfalls zutreffen kann. Der
    konkretere Grund ist die bessere Auskunft (SOLL §3.3/**S3**).

    Args:
        abgrenzung_stoerung: `WpFakten.abgrenzung_stoerung` — die Anwender-Angabe.
        bauarten_gemischt: Der Block trägt Luft-Wasser **und** Luft-Luft
            (SOLL §5). ⭐ **Steht bewusst VOR `geraete_ohne_waerme`**, obwohl
            beide zutreffen: Die Klimaanlage ist genau eines der Geräte, die
            keine Wärme melden — aber sie kann es bauartbedingt **nie**. Der
            allgemeinere Satz riete zu einer Zuordnung, die es beim Anwender
            nicht geben kann; der konkretere ist die bessere Auskunft (S3),
            und es ist dieselbe Reihenfolge-Entscheidung wie eine Zeile höher.
        geraete_ohne_waerme: `WpFakten.waerme_deckt_nicht_alle_geraete` — die
            Lage, die eedc aus den **Daten** erkennt (ein Gerät könnte einen
            Zähler haben und hat ihn nicht).
        zeitraum_versetzt: Q und E stammen aus verschieden langen Messzeiträumen
            (SOLL §4.2 Fall 3). Wird nur dort gesetzt, wo die Herkunft je Größe
            überhaupt bekannt ist — das ist die Vier-Quellen-Auflösung in
            `api/routes/aktueller_monat.py`. Hub und Tagesansicht lesen jeweils
            **eine** Quelle; dort gibt es den Fall nicht, und `False` ist deshalb
            keine Lücke, sondern die Wahrheit.
        geraete_verschieden: `WpFakten.geraete_verschieden` — mindestens ein
            Gerät steuert Wärme bei, ohne dass sein Strom im Nenner steht
            (N-441). Die **Gegenrichtung** zu ``geraete_ohne_waerme``; beide
            Lagen sind disjunkt und decken zusammen genau „beide Seiten tragen
            Geräte, aber nicht dieselben" ab.
        perioden_versetzt: Ein Monat trägt Wärme ohne Strom, ein anderer trägt
            Strom (N-441). Nur der Aufrufer, der über **mehrere** Monate faltet
            (Jahr, Hub), kann die Lage sehen; für einen einzelnen Monat ist
            ``False`` die Wahrheit und keine Lücke.

    ⭐ **Die beiden neuen Glieder hängen ans ENDE — auch hinter
    ``zeitraum_versetzt``, und das ist gemessen:** Im Monat können
    ``geraete_verschieden`` und ``zeitraum_versetzt`` **gemeinsam** wahr sein
    (`api/routes/aktueller_monat.py`, Vier-Quellen-Auflösung). Stünde das neue
    Glied davor, wechselte dort ein heute gezeigter Grund samt Hub-Link, ohne
    dass sich an der Anlage etwas geändert hätte. Hinten angehängt ändert sich
    **kein** bestehender Text. Untereinander gewinnt *Geräte* vor *Monate* —
    dieselbe Entscheidung wie auf der Funktions-Ebene (N-438): Verschiedene
    Geräte decken sich auch dann nicht, wenn jeder Monat vollständig wäre.
    """
    if abgrenzung_stoerung:
        grund = GRUND_JE_ABGRENZUNG.get(abgrenzung_stoerung)
        if grund:
            return grund
    if bauarten_gemischt:
        return GRUND_BAUARTEN_GEMISCHT
    if geraete_ohne_waerme:
        return GRUND_GERAETE_OHNE_WAERME
    if zeitraum_versetzt:
        return GRUND_ZEITRAUM
    if geraete_verschieden:
        return GRUND_GERAETE_VERSCHIEDEN
    if perioden_versetzt:
        return GRUND_GERAETE_VERSCHIEDENE_MONATE
    return None


#: Die drei Funktionen, für die es eine Arbeitszahl gibt. Lüften und
#: Entfeuchten stehen bewusst NICHT hier — sie erzeugen keine Nutzenergie, die
#: sich messen ließe (SOLL §2.3/E4).
ARBEITSZAHL_FUNKTIONEN = ("heizen", "warmwasser", "kuehlen")

#: Zähler und Nenner **einer Funktion** stammen von verschieden vielen Geräten.
#:
#: ⭐ **Die Lage, die es bis zum 10.09.2026 gar nicht gab** — und die deshalb
#: eine **falsche Zahl** zeigte statt einer fehlenden. Belegt an der Bauform von
#: 8ear: eine Wärmepumpe mit getrennter Strommessung neben einer
#: **Brauchwasser-Wärmepumpe**. Beide sind Luft-Wasser-Geräte
#: (``bauarten_gemischt`` False), beide melden Wärme
#: (``waerme_deckt_nicht_alle_geraete`` False) — keine der bisherigen Sperren
#: greift. Die Warmwasser-Wärme kommt aber von **beiden**, der getrennt
#: gemessene Warmwasser-Strom nur von **einem**: 1900 ÷ 400 = **4,75**, und
#: niemand sagte, dass die Zahl zwei Geräte im Zähler und eines im Nenner hat.
#:
#: ⚠ **Der Text nennt die Ursache, nicht den Ausweg** — anders als
#: {@link GRUND_KEINE_KAELTEMENGE}, der einen Zähler vorschlägt. Hier gibt es
#: keinen allgemeingültigen Handgriff: Je nach Anlage ist die getrennte
#: Strommessung des zweiten Geräts der Weg, oder es gibt schlicht keinen.
#:
#: ⚠ **„Nutzenergie", nicht „Wärme" (N-441, 12.09.2026).** Der Satz erscheint
#: auch an der **Kühl**-Kennzahl (``ARBEITSZAHL_FUNKTIONEN`` trägt ``kuehlen``),
#: und deren Zähler ist eine **Kälte**menge — seit Bauschnitt 6b eine eigene
#: Rolle, die nicht wieder „Wärme" heißen darf. Genau dieselbe Korrektur hat
#: N-438 einen Tag zuvor an {@link GRUND_FUNKTION_VERSCHIEDENE_MONATE}
#: vorgenommen; hier war sie noch offen.
GRUND_FUNKTION_NICHT_DECKUNGSGLEICH = (
    "Nutzenergie und Strom dieser Funktion stammen von verschiedenen Geräten"
)

#: **N-438** — dieselbe Sperre, aber über die **Zeit** statt über die Geräte.
#:
#: Ein Monat trägt Nutzenergie **ohne** den Strom derselben Funktion, ein anderer
#: trägt den Strom: Die Jahressumme nimmt beide mit und ergäbe eine zu hohe Zahl
#: (gemessen 3,75 statt 3,0, s. `test_r2_je_funktion`). Die Sperre ist damit
#: richtig — ihr **Grund** durfte aber nicht von „verschiedenen Geräten" sprechen,
#: wo es nur **eines** gibt. Der Unterschied liegt im Zeitraum (SOLL §3.3/**S3**:
#: nicht „—", sondern der Grund — und zwar der zutreffende).
#:
#: ⚠ **„Nutzenergie", nicht „Wärme".** Der Satz erscheint auch an der
#: Kühl-Kennzahl (`ARBEITSZAHL_FUNKTIONEN` trägt `kuehlen`, der Grund geht in
#: `arbeitszahl_kuehlen`), und deren Zähler ist eine **Kälte**menge — seit
#: Bauschnitt 6b eine eigene Rolle, die nicht wieder „Wärme" heißen darf.
GRUND_FUNKTION_VERSCHIEDENE_MONATE = (
    "Nutzenergie und Strom dieser Funktion stammen aus verschiedenen Monaten"
)


#: Die Gründe, bei denen der **Komponenten-Hub** die Zahl trotzdem zeigt.
#:
#: ⭐ **Gemessen, nicht geraten** (10.09.2026): Die beiden Hub-Aufrufer
#: (`investitionen/dashboard_waermepumpe.py`) reichen an ``arbeitszahl_je_funktion`` nur die
#: **Anwender-Angabe** und das **Abgeleitet**-Flag durch. Alles, was aus dem
#: Zusammenspiel MEHRERER Geräte entsteht, kennt der Hub deshalb gar nicht — er
#: rechnet je Gerät, und dort gibt es die Mischung nicht.
#:
#: ⛔ **Ein Link auf eine Sicht, die dasselbe sagt, ist schlechter als keiner** —
#: er schickt den Anwender auf einen vergeblichen Weg. Deshalb steht hier eine
#: **Positivliste** und keine „alles außer"-Regel: Ein neuer Grund erscheint
#: dann ohne Link, statt einen falschen zu erben.
#:
#: ⚠ Nicht enthalten und aus gutem Grund: ``GRUND_FREMDSTROM`` und
#: ``GRUND_FREMDWAERME`` (die Angabe hängt am Gerät, der Hub sperrt genauso),
#: die Abgeleitet-Sperre (dieselbe Regel je Gerät) und alle Datenlage-Gründe
#: („kein Wärmemengenzähler", „kein Heizbetrieb") — dort fehlt dem Hub dasselbe.
#:
#: ⭐ **``GRUND_GERAETE_VERSCHIEDEN`` gehört hinein (N-441, Entscheid Gernot
#: 12.09.2026), und zwar aus einer Messung:** Der Hub sagt in dieser Lage
#: **nicht dasselbe** wie das Cockpit — er nennt je Gerät, welche Seite fehlt
#: („kein Stromverbrauch erfasst" am wärmemeldenden Gerät, „kein
#: Wärmemengenzähler zugeordnet" am strommeldenden). Das ist die Diagnose, die
#: die anlagenweite Zahl nicht geben kann; der 10.09.-Grundsatz („ein Link auf
#: eine Sicht, die dasselbe sagt, ist schlechter als keiner") greift hier
#: gerade nicht.
#:
#: ⛔ **``GRUND_GERAETE_VERSCHIEDENE_MONATE`` gehört NICHT hinein** — der Hub
#: sperrt seine Gesamtzahl seit N-441 mit **demselben** Grund (S1). Ein Link
#: dorthin führte auf denselben Satz. Wie sein Funktions-Zwilling
#: ``GRUND_FUNKTION_VERSCHIEDENE_MONATE``, der ebenfalls nicht hier steht.
GRUENDE_HUB_HILFT: frozenset[str] = frozenset({
    GRUND_BAUARTEN_GEMISCHT,
    GRUND_GERAETE_OHNE_WAERME,
    GRUND_ZEITRAUM,
    GRUND_FUNKTION_NICHT_DECKUNGSGLEICH,
    GRUND_GERAETE_VERSCHIEDEN,
})


def hub_hilft(*gruende: Optional[str], ist_schranke: bool = False) -> bool:
    """Würde der Komponenten-Hub mindestens einen dieser Gründe beantworten?

    Der Aufrufer wirft alle Gründe seines Wärme/Klima-Blocks hinein (Gesamtzahl,
    je Funktion, Kühlen); ``True`` heißt: **mindestens eine** der gesperrten
    Zahlen steht dort je Gerät. Der Link ist ein Element des Blocks, keine Zeile
    je Kennzahl — deshalb eine Frage und nicht vier.

    ⚠ **Die Entscheidung gehört hierher, nicht in den Client.** Dort müsste er
    Grund-**Texte** vergleichen; dieselbe Aussage stünde dann an zwei Orten und
    liefe beim nächsten Wortlaut auseinander (ADR-001/S1 — die W-3-Klasse).

    Args:
        ist_schranke: **E1b (14.09.2026).** Die anlagenweite Zahl ist eine
            untere Schranke. ⭐ **Auch dann hilft der Hub, und gemessen mehr
            als vorher:** Die Schranke sagt *„mindestens 2,43"*, der Hub sagt
            *„diese Wärmepumpe: 3,0"*. Ohne dieses Argument verschwände der Weg
            genau in der Lage, für die er gebaut wurde — denn die Gründe, die
            ihn bisher auslösten (``GRUND_BAUARTEN_GEMISCHT``,
            ``GRUND_GERAETE_OHNE_WAERME``), sind jetzt **die** Schranke und
            stehen nicht mehr als Grund da.
    """
    return ist_schranke or any(g in GRUENDE_HUB_HILFT for g in gruende if g)


def abgrenzung_je_funktion(
    *,
    abgrenzung_stoerung: Optional[str] = None,
    bauarten_gemischt: bool = False,
    geraete_ohne_waerme: bool = False,
    zeitraum_versetzt: bool = False,
    deckung_je_funktion: Optional[dict[str, Optional[bool]]] = None,
    perioden_je_funktion: Optional[dict[str, bool]] = None,
) -> dict[str, Optional[str]]:
    """Je Funktion ihr Abgrenzungs-Grund — oder ``None`` (**SOLL §3.2b**).

    Gegenstück zu {@link abgrenzungs_grund}, der die **anlagenweite** Zahl
    beantwortet. Beide lesen dieselben Lagen; sie stehen deshalb nebeneinander
    und nicht an fünf Aufrufstellen.

    ⭐ **Die Trennlinie ist die Abgrenzung, nicht die Bauart** (Entscheid
    Gernot, 10.09.2026). Zwei Sorten Lage, und sie verhalten sich verschieden:

    * **Anwender-Angabe und Zeitraum-Versatz treffen alles.** Heizstab am
      Zähler, bivalenter Zweiterzeuger, versetzte Messzeiträume. ⚠ **Der
      ehrliche Grund ist nicht „das trifft physisch immer beide"** — ein
      Legionellen-Heizstab trifft nur das Warmwasser, ein Gaskessel am Heizkreis
      nur die Heizung. Der Grund ist, dass die Angabe **keine Funktion trägt**
      (``ABGRENZUNG_WERTE`` kennt nur ``fremdstrom``/``fremdwaerme``). Wir wissen
      nicht, welche Funktion betroffen ist, und dürfen keine freigeben. Wer der
      Angabe einmal eine Funktion gibt, darf diese Zeile ändern.
    * **Gemischte Bauarten und Geräte ohne Wärme treffen nur die Funktionen, die
      wirklich vermischt sind.**

    Args:
        deckung_je_funktion: je Funktion, ob sich der Geräte-Kreis von Zähler
            und Nenner **deckt** (``WpFakten.deckung_je_funktion``): ``True``
            deckt sich · ``False`` deckt sich nicht · ``None`` die Frage stellt
            sich nicht (Funktion nicht vorhanden, oder Wärme fehlt ganz — dafür
            hat ``arbeitszahl`` die besseren Sätze).

            Das **Argument als Ganzes** ``None`` heißt „unbekannt" und sperrt
            wie bisher alles — der Aufruf ist damit **bitgleich zum Stand vor
            der Präzisierung**. So rufen die Hub-Pfade auf: dort wird je Gerät
            gerechnet, die Frage ist gegenstandslos.

            ⛔ **Gezählt wird beidseitig, und das ist nicht verhandelbar.** Eine
            einseitige Regel („jedes Gerät mit Strom liefert auch Wärme") fängt
            nur den Nenner; der Zähler kippt in die **teurere** Richtung, weil
            dort eine zu hohe Kennzahl erscheint statt gar keiner.

            ⚠ **Die Faltung über mehrere Perioden gehört dem Aufrufer**, und
            sie ist nicht die Summe der Zahlen: Ein Monat, der Wärme ohne den
            Strom derselben Funktion trägt, verzerrt die **Jahres**summe, ohne
            dass die Gerätezahl des Jahres es zeigt (gemessen: 3,75 statt 3,0).
            Deshalb reicht das Jahr eine bereits gefällte Entscheidung herein.
    """
    global_grund = abgrenzungs_grund(
        abgrenzung_stoerung=abgrenzung_stoerung,
        bauarten_gemischt=bauarten_gemischt,
        geraete_ohne_waerme=geraete_ohne_waerme,
        zeitraum_versetzt=zeitraum_versetzt,
    )
    trifft_alles = bool(
        (abgrenzung_stoerung and GRUND_JE_ABGRENZUNG.get(abgrenzung_stoerung))
        or zeitraum_versetzt
        or deckung_je_funktion is None
    )

    ergebnis: dict[str, Optional[str]] = {}
    for f in ARBEITSZAHL_FUNKTIONEN:
        if global_grund and trifft_alles:
            ergebnis[f] = _ohne_waerme_wort(f, global_grund)
            continue
        if (deckung_je_funktion or {}).get(f) is False:
            # Der konkretere Grund gewinnt (S3) — er beschreibt genau DIESE
            # Funktion, während `global_grund` den ganzen Block beschreibt.
            #
            # N-438: **Zwei Lagen ergeben dieselbe verletzte Deckung** — andere
            # Geräte oder andere Monate. Welche vorliegt, weiß nur der Aufrufer,
            # der über die Perioden faltet (das Jahr); er sagt es hier. Ohne
            # seine Angabe bleibt es beim Geräte-Satz — bitgleich zu vorher.
            ergebnis[f] = _ohne_waerme_wort(f, global_grund) or (
                GRUND_FUNKTION_VERSCHIEDENE_MONATE
                if (perioden_je_funktion or {}).get(f)
                else GRUND_FUNKTION_NICHT_DECKUNGSGLEICH
            )
        else:
            ergebnis[f] = None
    return ergebnis


def _ohne_waerme_wort(funktion: str, grund: Optional[str]) -> Optional[str]:
    """Der Block-Satz „nicht alle Geräte melden Wärme" an der **Kühl**-Zeile.

    ⛔ **Er darf dort nicht stehen (N-441, Fall P).** Der Zähler der Kühlzahl
    ist eine **Kälte**menge; ein Satz über fehlende *Wärme*-Melder ist unter ihr
    eine Falschaussage — gemessen an einer Anlage mit drei Geräten (A vollständig,
    B nur Kälte, C nur Strom): ``wp_jaz_kuehlen_grund`` = „nicht alle Geräte
    melden Wärme".

    ⭐ **Dieselbe Klasse, die N-438 einen Tag zuvor für den Monate-Satz geheilt
    hat** — dort durch den Wortlaut der Konstante, hier durch einen Tausch: Für
    ``kuehlen`` tritt der **Funktions**-Satz an die Stelle des Block-Satzes. Er
    sagt dasselbe (verschiedene Geräte) in der Sprache dieser Funktion.

    ⚠ **Nur dieser eine Grund wird getauscht.** Heizstab-Angabe, gemischte
    Bauarten und Zeitraum-Versatz beschreiben den Block und nennen keine
    Nutzenergie-Art; sie bleiben unverändert an allen drei Zeilen stehen.
    """
    if funktion == "kuehlen" and grund == GRUND_GERAETE_OHNE_WAERME:
        return GRUND_FUNKTION_NICHT_DECKUNGSGLEICH
    return grund


def deckung_aus_geraeten(
    geraete_e: AbstractSet[int], geraete_q: AbstractSet[int],
) -> Optional[bool]:
    """Deckt sich der Geräte-Kreis von Zähler und Nenner einer Funktion? (**R2**)

    Die Regel hinter ``WpFakten.deckung_je_funktion`` — herausgezogen, damit der
    **Tag** sie ebenfalls ruft statt sie nachzubauen (Bauschnitt 6, Kälte je
    Tag). ``True`` = ja · ``False`` = nein · ``None`` = die Frage stellt sich
    nicht:

    * ``q`` leer — keine Nutzenergie. Entweder gab es die Funktion nicht, oder
      der Zähler fehlt; für beides hat die Kennzahl den genaueren Satz (S3).
    * ``e`` leer, ``q`` nicht — Nutzenergie ohne den Strom derselben Funktion
      ⇒ ``False``.
    * sonst — **dieselben Geräte** (``e == q``) ⇒ ``True``.

    ⛔ **Identität, nicht Anzahl (N-441, 12.09.2026).** Bis dahin nahm die Regel
    zwei ``int`` und verglich ``geraete_e == geraete_q``. Der Anlassfall fiel
    damit durch: Gerät A meldet 2400 kWh Wärme, Gerät B 800 kWh Heizstrom —
    ``(1, 1)``, also „deckt sich", und im Cockpit stand **3,0 ohne jeden
    Grund**, an der Community-Grenze als *belastbar* markiert. Ein Quotient aus
    der Wärme des einen und dem Strom des anderen Geräts ist keine Arbeitszahl;
    dass beide Seiten gleich **viele** Geräte haben, sagt darüber nichts.

    ⚠ **Gezählt wird der BEITRAG, nicht die Stammdaten** — der Aufrufer sammelt
    die Geräte, deren Menge an dieser Seite des Quotienten > 0 ist.
    """
    if not geraete_q:
        return None
    if not geraete_e:
        return False
    return set(geraete_e) == set(geraete_q)


def arbeitszahl(
    waerme_kwh: Optional[float],
    strom_kwh: Optional[float],
    *,
    waerme_abgeleitet_kwh: float = 0.0,
    strom_funktionsfremd_kwh: float = 0.0,
    abgrenzung_verletzt: Optional[str] = None,
    waerme_fehlt_grund: Optional[str] = None,
    kein_betrieb_grund: Optional[str] = None,
) -> Arbeitszahl:
    """Q ÷ E — oder der Grund, warum es diese Zahl nicht gibt (**R2**).

    Args:
        waerme_kwh: abgegebene Nutzenergie (thermisch) im Zeitraum.
        strom_kwh: elektrische Energie im selben Zeitraum, am selben Gerät.
        waerme_abgeleitet_kwh: der Anteil von ``waerme_kwh``, der aus
            ``Strom × JAZ`` gerechnet statt gemessen wurde.
        strom_funktionsfremd_kwh: der Anteil von ``strom_kwh``, der in eine
            Funktion **ohne bewertete Nutzenergie** ging — heute der
            Kühlbetrieb (**W-14**). Er wird **abgezogen**, nicht gesperrt.

            ⭐ **Das ist keine neue Entscheidung, sondern die dritte Anwendung
            einer bereits getroffenen** (#263 K-2, Entscheid **E-B**):
            `berechne_wp_ersparnis` und `berechne_co2_bilanz` rechnen den
            Kühlstrom seit v4.0.5 heraus, mit gemessener Begründung — an einer
            realen Anlage standen 26,4 kWh Heizen gegen 158,4 kWh Kühlen und
            ergaben **−45,04 €** Ersparnis und **−52 kg** CO₂. Die Arbeitszahl
            war die einzige der drei Größen, die den Kategorienfehler behielt:
            Kühlstrom im Nenner, Kältemenge nicht im Zähler. Eine Anlage, die
            kühlt, stand damit systematisch schlechter da als eine, die es
            nicht tut — im Community-Benchmark ebenso wie in eedc selbst
            (SOLL §4.2 Fall 4: *„eine JAZ gesamt über ein Gerät, dessen
            Kühlbetrieb nicht erfasst ist, ist keine Gesamtzahl"*).

            ⚠ **Warum hier abgezogen und bei `waerme_abgeleitet_kwh` gesperrt
            wird — das ist kein Widerspruch, sondern derselbe Grundsatz.** Dort
            enthält der **Zähler** einen Anteil, der aus dem Nenner gerechnet
            wurde; ihn abzuziehen ergäbe gemessene Wärme durch Gesamtstrom, also
            **falsch statt unbekannt**. Hier enthält der **Nenner** einen Anteil,
            der zu einer anderen Funktion gehört und **separat bekannt** ist —
            ihn abzuziehen stellt die Abgrenzung von Q und E überhaupt erst her.
            Beide Male gewinnt dieselbe Regel: Q und E müssen dasselbe meinen.

            ⭐ **Seit E4 (26.08.) sind es drei Funktionen, nicht eine:** Kühlen,
            **Lüften und Entfeuchten** — alle drei ohne bewertete Nutzenergie.
            Die Aufrufer lesen sie als *eine* Größe
            (`WpFakten.modus_strom_funktionsfremd_kwh`), statt drei Summanden
            aufzuzählen; die Aufzählung war die Bauform, an der W-14 entstand.

            ⛔ **Nicht abgezogen wird die Restmenge** (`modus_nicht_aufgeteilt_kwh`
            — Standby, Unbestimmt, und was mangels Zähler dort steckt). Sie ist
            keine gemessene Funktion, sondern das, was übrig bleibt; der
            Bereitschaftsverbrauch einer Heizung gehört legitim in ihre
            Arbeitszahl. ⚠ **Der Unterschied ist die Messung, nicht die
            Betriebsart:** Gemessenes Lüften wird abgezogen, ungemessenes bleibt
            als Teil der Restmenge im Nenner — denn dort ist es von Standby
            nicht unterscheidbar.
        waerme_fehlt_grund: **kurzer** Grund, warum ``waerme_kwh`` fehlt, wenn
            der Aufrufer ihn genauer kennt als diese Funktion. Nur im Fall
            ``q <= 0`` ausgewertet; ``None`` lässt den bisherigen Wortlaut
            stehen (**W-18**).

            ⭐ **Warum das ein Parameter ist und keine Fallunterscheidung hier
            drin.** Ob ein Wärmemengenzähler *fehlt*, ob er *zugeordnet, aber
            für diesen Tag leer* ist oder ob er *zurückgesprungen* ist, weiß
            allein der Erhebungspfad (``snapshot/aggregator``). Diese Funktion
            sieht nur eine Zahl, die nicht da ist — sie kann den Unterschied
            nicht kennen und darf ihn deshalb nicht behaupten. Genau das hat sie
            bis zum 26.08.2026 getan. Kurzformen: ``core/tageswert_grund.py``.
        abgrenzung_verletzt: kurzer Grund, wenn Q und E **nicht dieselbe
            Abgrenzung** tragen — anderes Gerät, andere Funktion, anderer
            Zeitraum. ``None`` heißt „keine bekannte Abweichung".

            ⭐ **Bewusst EIN Eingang für alle Abweichungen und keine Liste von
            Flags.** R2 ist *eine* Regel; §4.2 zählt nur Beispiele auf. Ein
            Parameter je Beispiel hätte die Fallsammlung in den Code geholt —
            genau die Bauform, die den bivalenten Fall jahrelang unsichtbar
            gelassen hat. Wer eine weitere Abweichung erkennt, reicht ihren
            Grund hier herein; die Regel selbst bleibt unverändert.

    ⚠ **Der abgeleitete Anteil wird NICHT abgezogen**, sondern sperrt die ganze
    Zahl. Zöge man ihn ab, teilte man gemessene Wärme durch den **Gesamt**strom
    und bekäme eine zu kleine Arbeitszahl — **falsch statt unbekannt**. Die
    Begründung steht ausführlich bei ``WpFakten.jaz_belastbar``, das dieselbe
    Regel für die Monats-Fakten trägt und unverändert bleibt.
    """
    e_gesamt = float(strom_kwh or 0.0)
    q = float(waerme_kwh or 0.0)
    # Der funktionsfremde Anteil wird nie negativ und nie größer als der
    # Gesamtstrom — dieselbe Zusicherung wie in `berechne_wp_ersparnis`, für
    # Aufrufer, die ihre Zahlen aus einer anderen Quelle ziehen.
    e = e_gesamt - min(max(strom_funktionsfremd_kwh, 0.0), max(e_gesamt, 0.0))
    if e_gesamt <= 0:
        # ⭐ **F-5 (14.09.2026): gemessene 0 ist kein fehlender Zähler — auch im
        # NENNER nicht.** Bis hierher hat W-18/ef696c1c genau diese
        # Unterscheidung für den **Zähler** gebaut (``q == 0`` ⇒ „kein
        # Heizbetrieb in diesem Zeitraum"), für den Nenner nicht. Wer seinen
        # Heizstrom getrennt misst, las im Juni „kein Stromverbrauch erfasst"
        # unter einer Anlage, die ihren Heizstrom sehr wohl erfasst — sie hat
        # nur nicht geheizt. Spiegelbildlich zu ``GRUND_KEIN_KUEHLBETRIEB``,
        # den ``arbeitszahl_kuehlen`` bei ``e <= 0`` **unbedingt** nennt.
        #
        # ⚠ **Dieselben zwei Riegel wie beim Zähler**: ein gemessener Wert
        # (``strom_kwh is not None``, exakt ``0``) UND ein Aufrufer, der
        # „gemessen 0" von „nie erfasst" unterscheiden kann (er reicht dafür
        # ``kein_betrieb_grund`` herein). Summen-Pfade tun das nicht — ``sum()``
        # liefert 0, ob gemessen oder nie erfasst.
        if (kein_betrieb_grund and strom_kwh is not None
                and float(strom_kwh) == 0.0):
            # ⭐ **Gegenfall (Bauplan §8a, Nachtrag aus der Nachmessung E4d):** Strom gemessen 0, die Wärme aber NICHT
            # erfasst (kein Wert oder ein Grund, warum sie fehlt) ⇒ Stufe 5 mit dem Wärme-Grund. Der Strom ist erfasst
            # — Stufe 1 träfe ihn zu Unrecht; „kein Betrieb" wüsste ohne Wärmemessung niemand.
            # ⭐ **Ausnahme (Fachentscheid Master zu E4f, H-3, 07.10.2026): die Wärme ist gemessen, nur nicht je Funktion**
            # (``GRUND_WAERME_NICHT_JE_FUNKTION``, ein gemeinsamer Wärmemengenzähler). Ist der Funktions-Strom bekannt
            # und 0, ist „kein Heizbetrieb" / „keine Warmwasserbereitung" (Klasse Zeitraum, stilles „—") die Aussage —
            # ein Zeitraum ohne Betrieb hat keinen Handgriff, den der Anwender tun könnte; der Ausstattungs-Satz wäre
            # dort falsch. Konzept Wärme/Klima §4.3: die Datenlage geht der Abgrenzung vor (Stufe 2/3 vor 5/6). Fehlt
            # die Wärme ganz (kein Zähler, keine Zählerstände), bleibt Stufe 5 mit dem Wärme-Grund (§8a-Nachtrag).
            if waerme_fehlt_grund == GRUND_WAERME_NICHT_JE_FUNKTION:
                return Arbeitszahl(None, kein_betrieb_grund)
            if waerme_kwh is None or waerme_fehlt_grund:
                return Arbeitszahl(None, waerme_fehlt_grund or GRUND_KEINE_WAERMEMESSUNG)
            return Arbeitszahl(None, kein_betrieb_grund)
        return Arbeitszahl(None, GRUND_KEIN_STROM)
    if e <= 0:
        # Der ganze Strom ging ins Kühlen: es gibt Verbrauch, aber keinen, der
        # zu einer Wärmemenge gehört. „Kein Stromverbrauch" wäre hier die
        # falsche Auskunft — der Zähler lief, nur nicht fürs Heizen.
        return Arbeitszahl(None, GRUND_NUR_KUEHLBETRIEB)
    if q <= 0:
        # W-18: Die Sperre stimmt, ihre Begründung war geraten. „Kein
        # Wärmemengenzähler zugeordnet" ist nur EINER von drei Gründen, aus
        # denen keine Wärme vorliegt — und ausgerechnet der falsche für
        # dietmar1968, der beide Zähler zugeordnet hatte (T89667 #210). Wer den
        # wahren Grund kennt, reicht ihn herein; wer ihn nicht kennt, bekommt
        # unverändert den bisherigen Satz. **Der Default ist bitgleich zu
        # vorher** — kein Aufrufer ändert sein Verhalten, ohne es zu wollen.
        # ⭐ **Die zweite Hälfte desselben Fehlers** (dietmar1968, T89667 #322,
        # 10.09.2026): W-18 hat den Fall „Wert fehlt, Grund bekannt" geheilt —
        # den Fall „Wert ist **gemessen** 0" nicht. `float(waerme_kwh or 0.0)`
        # faltet `None` und `0.0` zusammen, und ein gemessener Wert bekommt
        # ohnehin nie einen `waerme_fehlt_grund` (`snapshot/aggregator.py`
        # vergibt Gründe nur für Felder OHNE Summe). Ein Septembertag ohne
        # Heizbetrieb hieß deshalb „kein Wärmemengenzähler zugeordnet", obwohl
        # der Zähler zugeordnet ist und korrekt Null meldet.
        # ⚠ **`q == 0`, nicht `q <= 0`** — eine negative Wärme ist ein
        # Zählerrücksprung und kein ruhiges Gerät; für ihn gibt es
        # `GRUND_ZAEHLER_RUECKSPRUNG` über `waerme_fehlt_grund`.
        # ⚠ **`waerme_kwh is not None` ist Gürtel UND Hosenträger, gemessen am
        # 10.09.:** Ein Sprengsatz, der genau diese Teilbedingung entfernt,
        # bleibt still — den Fall „kein Zähler" trägt bereits
        # `not waerme_fehlt_grund` (ein unerfasstes Feld bekommt immer einen
        # Grund). Sie steht hier für Aufrufer, die künftig
        # `null_ist_gemessen=True` setzen, ohne dieselbe Grund-Erhebung zu
        # haben. **Wer sie für tragend hält, irrt** — der diskriminierende
        # Riegel ist der Grund, nicht der Wert.
        if q == 0 and waerme_kwh is not None and not waerme_fehlt_grund:
            if kein_betrieb_grund:
                return Arbeitszahl(None, kein_betrieb_grund)
        return Arbeitszahl(
            None, waerme_fehlt_grund or GRUND_KEINE_WAERMEMESSUNG,
        )
    if waerme_abgeleitet_kwh > 0:
        return Arbeitszahl(None, GRUND_WAERME_ABGELEITET)
    if abgrenzung_verletzt:
        return Arbeitszahl(None, abgrenzung_verletzt)
    wert = q / e
    return Arbeitszahl(
        wert,
        hinweis=HEIZSTAB_HINWEIS if wert < JAZ_HEIZSTAB_SCHWELLE else None,
        # `e`, nicht `e_gesamt` — die Herleitung zeigt den Nenner, mit dem
        # gerechnet wurde, sonst ginge die Division sichtbar nicht auf.
        zaehler_kwh=q,
        nenner_kwh=e,
    )


@dataclass(frozen=True)
class Systemarbeitszahl:
    """Die **anlagenweite** Arbeitszahl der Wärmeerzeugung — **E1b**.

    Sie ist etwas anderes als {@link Arbeitszahl}, und der Unterschied steht im
    Feld ``ist_schranke``: Diese Zahl darf einen Nenner tragen, der **mehr**
    Strom enthält, als im Zähler gemessene Wärme gegenübersteht. Das Ergebnis
    ist dann keine Arbeitszahl mehr, sondern eine **untere Schranke** — und als
    solche wird sie gezeigt („≥ 3,25").
    """

    wert: Optional[float]
    #: ``True`` ⇒ der wahre Wert ist **mindestens** ``wert``. Die Anzeige setzt
    #: dann „≥" davor; der Client rechnet nichts nach (ADR-002/P12, der Client
    #: liest ein Flag).
    ist_schranke: bool = False
    #: Der EINE Satz, der die Schranke erklärt — er nennt das Gerät, dessen
    #: Strom ohne Wärmemessung im Nenner steht.
    schranke_hinweis: Optional[str] = None
    #: ⛔ **Dasselbe Feld wie an {@link Arbeitszahl}, und mit Absicht dieselbe
    #: Bedeutung:** der Heizstab-Satz unter {@link JAZ_HEIZSTAB_SCHWELLE}. Er
    #: gehört NICHT mit der Schranke zusammen — eine Anlage, die viel direkt
    #: elektrisch heizt, bekommt ihn auch ohne Schranke, und eine Schranke von
    #: 3,25 braucht ihn nicht. Beide in **ein** Feld zu falten hieße, zwei
    #: verschiedene Aussagen unter einem Namen zu führen; die Route liefert
    #: sie deshalb als ``wp_jaz_hinweis`` und ``wp_jaz_schranke_hinweis``
    #: getrennt aus.
    hinweis: Optional[str] = None
    #: Warum es die Zahl nicht gibt (wie bei {@link Arbeitszahl}).
    grund: Optional[str] = None
    zaehler_kwh: Optional[float] = None
    nenner_kwh: Optional[float] = None

    @property
    def belastbar(self) -> bool:
        return self.wert is not None


#: Der Satz unter einer Schranke. Er nennt die Geräte, deren Strom im Nenner
#: steht, ohne dass ihre Wärme in den Zähler kommt — **Ursache, kein Vorwurf**
#: ([[feedback_eedc_ist_nicht_die_strom_polizei]]).
SCHRANKE_HINWEIS_MUSTER = "{geraete}: Strom ohne Wärmemessung enthalten"


def schranke_hinweis(geraete: Sequence[str]) -> Optional[str]:
    """„Klimaanlage: Strom ohne Wärmemessung enthalten" — oder ``None``.

    Mehrere Geräte stehen mit „ · " nebeneinander, wie überall sonst in dieser
    Fläche (``ersparnis_vorbehalt``, ``GeraeteHinweis``). Ohne Namen — der
    Aufrufer kennt sie nicht immer — bleibt der allgemeine Satz übrig, denn die
    Aussage gilt auch dann: irgendein Strom im Nenner hat keine Wärmemessung.
    """
    namen = [n for n in geraete if n]
    if not namen:
        return "Strom ohne Wärmemessung enthalten"
    return SCHRANKE_HINWEIS_MUSTER.format(geraete=" · ".join(namen))


def systemarbeitszahl(
    waerme_gemessen_kwh: Optional[float],
    strom_kwh: Optional[float],
    *,
    kuehlstrom_kwh: float = 0.0,
    strom_ohne_waerme_kwh: float = 0.0,
    geraete_ohne_waerme: Sequence[str] = (),
    waerme_abgeleitet_kwh: float = 0.0,
    abgrenzung_verletzt: Optional[str] = None,
    waerme_fehlt_grund: Optional[str] = None,
    strom_fehlt_grund: Optional[str] = None,
    kein_betrieb_grund: Optional[str] = None,
) -> Systemarbeitszahl:
    """Σ gemessene Wärme ÷ (Σ Strom − Kühlstrom) — die **Systemarbeitszahl** (E1b).

    ⭐ **Warum es diese Zahl gibt** (Entscheid Gernot, 14.09.2026, nach dem
    Vergleich mit dietmar1968s eigenem Dashboard): Sein Jahr zeigt
    *AZ Heizung 3,94 × 1188 kWh + AZ Warmwasser 2,84 × 843 kWh = 7075 kWh*
    Wärme, Gesamtstrom **2193** kWh, davon **17** kWh Klima-Kühlen —
    ``7075 ÷ (2193 − 17) = 3,25``. eedc sagte an derselben Stelle „—" mit dem
    Grund *„Wärmepumpe und Klimaanlage in einer Zahl"*, weil seine
    Split-Klimaanlage Heizstrom ohne Wärmemessung beisteuert.

    **Beide hatten recht, und genau deshalb braucht es zwei Größen.** Als
    *Arbeitszahl eines Geräts* wäre 3,25 falsch — sie mischt Zähler und Nenner
    verschiedener Geräte (E1/R2, unverändert gültig). Als **untere Schranke der
    Anlage** ist sie **wahr**: Mehr Strom im Nenner als gemessene Wärme im
    Zähler kann den Quotienten nur **kleiner** machen. ADR-002/**P4** verbietet
    eine *falsche* Zahl, nicht eine *wahre Schranke* — und ein Strich mit
    Grund-Text ist keine bessere Auskunft als „mindestens 3,25".

    ⛔ **Sie ersetzt {@link arbeitszahl} nicht.** Der Komponenten-Hub, der
    HA-Export-Sensor und jede Kennzahl **je Gerät** rufen weiterhin dort an; dort
    gilt R2 ohne Ausnahme. Diese Funktion beantwortet die **andere** Frage:
    *„Wie effizient erzeugt diese Anlage insgesamt Wärme?"*

    Args:
        waerme_gemessen_kwh: Σ der **gemessenen** Wärme aller Wärmeerzeuger.
            Eine abgeleitete Menge gehört nicht hinein — sie käme aus dem
            Nenner und gäbe ihren eigenen Faktor zurück (deshalb der eigene
            Eingang ``waerme_abgeleitet_kwh``, der wie in ``arbeitszahl``
            **sperrt** statt abzuziehen).
        strom_kwh: Σ Strom aller Wärmeerzeuger.
        kuehlstrom_kwh: der Anteil, der in eine Funktion **ohne bewertete
            Nutzenergie** ging (Kühlen · Lüften · Entfeuchten). **E7/Option A**,
            dieselbe Größe und dieselbe Begründung wie
            ``arbeitszahl(strom_funktionsfremd_kwh=…)`` — und dieselbe, die
            dietmar1968 in seiner eigenen Rechnung abzieht.
        strom_ohne_waerme_kwh: der Teil des Nenners, dem **keine gemessene
            Wärme** gegenübersteht (Klimaanlage ohne Wärmemengenzähler,
            Heizstab auf eigenem Zähler). ``> 0`` ⇒ ``ist_schranke``.
            ⚠ Die **Menge** ändert die Zahl nicht — sie steckt ohnehin im
            Nenner. Sie entscheidet allein, **ob** die Zahl eine Schranke ist.
        geraete_ohne_waerme: deren Namen, für den einen Hinweis-Satz.
        abgrenzung_verletzt: die Gründe, die **weiterhin sperren**. ⛔ *Nicht*
            darunter: ``GRUND_BAUARTEN_GEMISCHT`` und
            ``GRUND_GERAETE_OHNE_WAERME`` — genau sie werden hier zur Schranke.
            Der Aufrufer reicht sie nicht mehr herein (siehe
            {@link GRUENDE_ZUR_SCHRANKE}).

    ⚠ **Die Gegenrichtung bleibt eine Sperre, und das ist der Kern.** Steht im
    **Zähler** Wärme, deren Strom fehlt (``GRUND_GERAETE_VERSCHIEDEN``,
    ``GRUND_FREMDWAERME``, ``GRUND_GERAETE_VERSCHIEDENE_MONATE``), kippt die
    Zahl nach **oben** — eine untere Schranke wäre dort eine Falschaussage.
    Ebenso ``GRUND_ZEITRAUM``: Bei versetzten Messzeiträumen ist die Richtung
    **unbekannt**, und eine Schranke ohne bekannte Richtung ist keine.

    Grenzfälle, ausgeschrieben:

    * ``Q = 0`` ⇒ **Grund statt Zahl** (``waerme_fehlt_grund`` oder
      ``GRUND_KEINE_WAERMEMESSUNG``). Eine Schranke „≥ 0" ist wahr und sagt
      nichts; sie sähe aus wie eine Bewertung.
    * ``Nenner ≤ 0`` ⇒ ``GRUND_KEIN_STROM`` bzw. — wenn Strom floss, aber
      vollständig ins Kühlen — ``GRUND_NUR_KUEHLBETRIEB``. Beide Wortlaute sind
      die von ``arbeitszahl``; zwei Sprachen für einen Sachverhalt wären die
      N-327-Klasse.
      ⭐ **Es sei denn, der Aufrufer weiß es besser** (``strom_fehlt_grund``,
      **R-5**/N-492, 15.09.2026): *„kein Stromverbrauch erfasst"* ist eine
      Aussage über das **Gerät**, und sie ist falsch, wenn die Kachel daneben
      eine Strommenge zeigt und nur der **Randstand** dieses Tages fehlt.
      Dieselbe Bauform und derselbe Grund wie ``waerme_fehlt_grund``: Der
      Erhebungspfad weiß, welcher der drei W-18-Zustände vorliegt, der Layer
      kann es nicht wissen. Gemessen am Lab-Screenshot vom 15.09.2026: Kachel
      *„Strom verbraucht 2 kWh"*, daneben *„Arbeitszahl — kein Stromverbrauch
      erfasst"*.
    * **Nur ein Gerät**, dessen Wärme gemessen ist ⇒ ``strom_ohne_waerme_kwh``
      ist 0, ``ist_schranke`` bleibt ``False`` — die gewohnte Arbeitszahl, ohne
      „≥". Die Schranke ist ein Zusatz für gemischte Anlagen, keine neue
      Darstellung für alle.
    """
    e_gesamt = float(strom_kwh or 0.0)
    q = float(waerme_gemessen_kwh or 0.0)
    # Derselbe Klemmbereich wie in `arbeitszahl` — für Aufrufer, die ihre Zahlen
    # aus einer anderen Quelle ziehen.
    e = e_gesamt - min(max(kuehlstrom_kwh, 0.0), max(e_gesamt, 0.0))
    if e_gesamt <= 0:
        # ⭐ **HA-Bauform E4d (Bauplan §8a, Rest N-585): eine gemessene 0 ist erfasst.** Stufe 1 („kein Stromverbrauch
        # erfasst") gilt nur, wo der Strom FEHLT (``None``). Sind Strom UND Wärme gemessen 0, lief das Gerät in diesem
        # Zeitraum nicht — dann gilt Stufe 3 mit dem vorhandenen Grund des Aufrufers (``kein_betrieb_grund``, Klasse
        # Zeitraum: „—" ohne Text, {@link kein_betrieb_grund_der_achsen}). Dieselben zwei Riegel wie bei
        # ``arbeitszahl``: exakt 0, nicht ``None``, UND ein Aufrufer, der „gemessen 0" von „nie erfasst" unterscheiden
        # kann (er reicht dann den Grund herein). ⚠ Strom 0 bei Wärme > 0 bleibt bei Stufe 1 (Entscheid Master H-2,
        # Kandidat Daten-Checker „Wärme ohne Strom").
        # ⭐ **Gegenfall (§8a, Nachtrag aus der Nachmessung E4d):** Strom gemessen 0 (nicht ``None``) und Wärme NICHT
        # erfasst (``None``) ⇒ Stufe 5 „kein Wärmemengenzähler zugeordnet" bzw. der Grund des Aufrufers — der Strom ist
        # erfasst, es fehlt die Wärme. Ohne Riegel: jeder Aufrufer führt eine 0 nur, wo gemessen wurde (Cockpit → Monat:
        # Quellen-Kaskade; Tag: ``or None``; Übersicht: ``None`` ohne Marke ``strom_gemessen``/``waerme_gemessen``).
        if strom_kwh is not None and float(strom_kwh) == 0.0 and waerme_gemessen_kwh is None:
            return Systemarbeitszahl(None, grund=waerme_fehlt_grund or GRUND_KEINE_WAERMEMESSUNG)
        if (kein_betrieb_grund and strom_kwh is not None and float(strom_kwh) == 0.0
                and waerme_gemessen_kwh is not None and float(waerme_gemessen_kwh) == 0.0):
            return Systemarbeitszahl(None, grund=kein_betrieb_grund)
        return Systemarbeitszahl(None, grund=strom_fehlt_grund or GRUND_KEIN_STROM)
    if e <= 0:
        return Systemarbeitszahl(None, grund=GRUND_NUR_KUEHLBETRIEB)
    if q <= 0:
        return Systemarbeitszahl(
            None, grund=waerme_fehlt_grund or GRUND_KEINE_WAERMEMESSUNG,
        )
    if waerme_abgeleitet_kwh > 0:
        return Systemarbeitszahl(None, grund=GRUND_WAERME_ABGELEITET)
    if abgrenzung_verletzt:
        return Systemarbeitszahl(None, grund=abgrenzung_verletzt)
    ist_schranke = strom_ohne_waerme_kwh > 0
    wert = q / e
    return Systemarbeitszahl(
        wert,
        ist_schranke=ist_schranke,
        schranke_hinweis=(
            schranke_hinweis(geraete_ohne_waerme) if ist_schranke else None
        ),
        # Der Heizstab-Satz gilt hier wie bei `arbeitszahl` — dieselbe Schwelle,
        # dieselbe Begründung. Ihn hier wegzulassen hieße, eine Anlage mit viel
        # Direktheizung in der einen Sicht zu erklären und in der anderen nicht.
        hinweis=HEIZSTAB_HINWEIS if wert < JAZ_HEIZSTAB_SCHWELLE else None,
        zaehler_kwh=q,
        nenner_kwh=e,
    )


#: Grund, wenn der Strom nicht je Funktion vorliegt — die häufigste Lage.
#: **Kurz und mit Ausweg**, wie jeder Sperrgrund (S3): Er sagt nicht nur, dass
#: die Zahl fehlt, sondern woran es liegt.
GRUND_STROM_NICHT_JE_FUNKTION = "Strom nicht getrennt je Funktion gemessen"


def kein_betrieb_grund_der_achsen(achsen) -> str:
    """Der Grund „kein Betrieb im Zeitraum" für eine GESAMT-Zahl aus Strom 0 und Wärme 0 (HA-Bauform E4d, Bauplan §8a).

    **Kein neuer Grund-Text** (§8a): die zwei vorhandenen Zeitraum-Gründe der Kette. Hat die Ausstattung eine
    Heiz-Achse, ist es „kein Heizbetrieb in diesem Zeitraum"; eine Einheit nur mit Warmwasser-Achse (Brauchwasser-WP,
    §5.1a) sagt „keine Warmwasserbereitung in diesem Zeitraum" — eine Heiz-Aussage über ein Gerät ohne Heizkreis wäre
    eine Aussage über eine Achse, die es nicht gibt (WK-15c).
    """
    return GRUND_KEIN_HEIZBETRIEB if HEIZEN in (achsen or ()) else GRUND_KEINE_WARMWASSERBEREITUNG

#: Das Gegenstück auf der **Wärme**seite (N-391, 14.09.2026) — derselbe Satzbau,
#: weil es derselbe Sachverhalt in der anderen Größe ist: Der Quotient je
#: Funktion braucht **beide** Seiten je Funktion.
#:
#: ⛔ **Warum er nötig wurde.** Wer Heizung und Warmwasser über EINEN
#: Wärmemengenzähler misst, hat seine Zahl mangels Feld unter *Heizwärme*
#: eingetragen; mit getrennter Strommessung rechnete eedc daraus
#: `Gesamtwärme ÷ Heizstrom` — gemessen **5,0** statt 3,0, ohne Grund. Seit es
#: das Feld *Wärme gesamt* gibt, sagt die Datenlage selbst, dass die Wärme nicht
#: je Funktion vorliegt, und die Kennzahl bekommt diesen Grund statt einer Zahl.
#:
#: ⚠ **Er ersetzt genau dort den Default „kein Wärmemengenzähler zugeordnet",
#: wo dieser falsch ist:** Der Zähler IST zugeordnet — er misst nur beide
#: Funktionen. Dieselbe Klasse wie der am 26.08. geheilte Fall an
#: {@link GRUND_KEIN_HEIZBETRIEB} („Der Melder hat nach einem Zuordnungsfehler
#: gesucht, den es nicht gab"), nur in der Gegenrichtung.
GRUND_WAERME_NICHT_JE_FUNKTION = "Wärme nicht je Funktion gemessen"


@dataclass(frozen=True)
class ArbeitszahlJeFunktion:
    """Heizen und Warmwasser getrennt — **W-4**, SOLL §4.1.

    ⚠ **Warum das keine „genauere JAZ" ist, sondern zwei andere Zahlen.** Die
    Gesamt-Arbeitszahl teilt *alle* Wärme durch *allen* Strom. Diese beiden
    teilen je Funktion — und beantworten damit eine Frage, die die Gesamtzahl
    nicht beantworten kann: *warum* eine Anlage schlecht dasteht. Warmwasser
    liegt bauartbedingt niedriger als Heizen (höhere Zieltemperatur); eine
    Anlage mit viel Warmwasseranteil hat deshalb eine niedrigere Gesamtzahl,
    **ohne schlechter zu sein**.

    ⭐ **Diese Kennzahlen waren im Handbuch schon versprochen**
    (`HANDBUCH_BEDIENUNG` §Wärme/Klima: *„Zusätzlich: JAZ-Heizen /
    JAZ-Warmwasser getrennt"*) — und gab es im Code nie. `cop_heizung` /
    `scop_heizung` sind **Anwender-Vorgaben** für die Ableitung, keine
    gemessenen Werte. Eine Doku-Zusage ohne Deckung ist dieselbe Klasse wie ein
    Feld, das angeboten und nirgends ausgewertet wird.
    """

    heizen: Arbeitszahl
    warmwasser: Arbeitszahl


#: **Die Achse gibt es an diesem Gerät nicht** — weder Zahl noch Grund (WK-16h/R-1).
#:
#: ⛔ **Nicht dasselbe wie „kein Wert"**, und genau deshalb eine eigene
#: Konstante: Ein ``Arbeitszahl(None, <grund>)`` sagt *„die Zahl fehlt, und das
#: ist der Mangel"*; diese hier sagt *„danach ist nicht zu fragen"*. Die Anzeige
#: macht daraus eine **leere** Zelle statt eines Strichs mit Tooltip — ein
#: „gilt nicht" ist kein Mangel, und ein Strich, den niemand beheben kann, ist
#: die Strich-Flut, gegen die die D-Sicht gebaut ist.
ARBEITSZAHL_GILT_NICHT = Arbeitszahl(None, None)


def als_arbeitszahl(sys: "Systemarbeitszahl") -> Optional[Arbeitszahl]:
    """Die anlagenweite Zahl als {@link Arbeitszahl} — **oder gar nicht**.

    Für die Ein-Achsen-Regel in {@link arbeitszahl_je_funktion}: Trägt eine
    Anlage anlagenweit nur **eine** Wärme-Achse, ist ihre Gesamtzahl die Zahl
    dieser Funktion. Was dabei nicht mitgehen darf, ist das ``≥``.

    ⛔ **Eine Schranke wird NICHT zur Funktions-Arbeitszahl** (``None``). Sie
    ist eine *untere Grenze*, und die Funktions-Zeilen haben keine Bauform
    dafür — eine Schranke ohne ihr Zeichen wäre eine Zahl, die mehr behauptet,
    als sie weiß (ADR-002/**P4**). In dieser Lage bleibt es beim gewohnten Weg
    und damit beim Grund, den die Funktion selbst findet.
    """
    if sys.ist_schranke:
        return None
    return Arbeitszahl(
        sys.wert, sys.grund, sys.hinweis, sys.zaehler_kwh, sys.nenner_kwh,
    )


def arbeitszahl_je_funktion(
    *,
    heizung_kwh: Optional[float],
    strom_heizen_kwh: Optional[float],
    warmwasser_kwh: Optional[float],
    strom_warmwasser_kwh: Optional[float],
    hat_split: bool,
    waerme_ist_gesamt: bool = False,
    waerme_abgeleitet_kwh: float = 0.0,
    abgrenzung_verletzt: Optional[str] = None,
    waerme_fehlt_grund_heizen: Optional[str] = None,
    waerme_fehlt_grund_warmwasser: Optional[str] = None,
    null_ist_gemessen: bool = False,
    null_ist_gemessen_heizen: Optional[bool] = None,
    null_ist_gemessen_warmwasser: Optional[bool] = None,
    abgrenzung_je_funktion_grund: Optional[dict[str, Optional[str]]] = None,
    achsen: Optional[AbstractSet[str]] = None,
    gesamt: Optional[Arbeitszahl] = None,
) -> ArbeitszahlJeFunktion:
    """Je Funktion eine eigene Arbeitszahl — oder je Funktion ihr Grund.

    ⭐ **Rechnet nicht daneben, sondern ruft ``arbeitszahl`` zweimal.** Damit
    gelten **alle** R2-Sperren unverändert und automatisch auch hier: abgeleitete
    Wärme, Fremdanteil auf dem Zähler, Zeitraum-Versatz, fehlender Zähler. Eine
    zweite Rechenstelle wäre die F-56-Klasse — *eine Regel, die an zwei Stellen
    nachgebaut wird, driftet* —, und sie ist in dieser Datei bereits einmal
    teuer geworden (W-3: die JAZ stand an drei Orten).

    ⚠ **Kein ``strom_funktionsfremd_kwh``-Abzug, und das ist kein Vergessen —
    es ist SOLL-§9-E7.** Der Nenner einer Funktions-Arbeitszahl ist der getrennt
    **gemessene** Strom dieser Funktion (F5). Ein aus dem Betriebsmodus
    abgeleiteter Anteil ist eine **Verteilung** und darf ihn weder stellen noch
    kürzen: *eine Verteilung erbt jede Unschärfe ihres Schlüssels, eine Messung
    nicht.* Zöge man ihn hier ab, stünde im Nenner **Messung − Verteilung**, und
    das ist keine Messung mehr.

    ⛔ **Hier stand bis zum 12.09.2026: „``strom_heizen_kwh`` ist bereits nur
    der Heizbetrieb; Kühlen, Lüften und Entfeuchten sind darin gar nicht
    enthalten. Ihn hier abzuziehen zöge dieselbe Menge zweimal ab."** Der erste
    Satz ist der **Feld-Vertrag** (Registry ``field_definitions.py``, Handbuch
    Fall B) und keine Messung — ob ein Zähler *Strom Heizen* den Verdichter im
    Kühlbetrieb mitmisst, weiß eedc nicht. Der zweite Satz war schlicht falsch:
    In diesem Pfad wird **nichts** abgezogen, ein Abzug wäre der erste. Die
    Regel hält trotzdem — nur trägt sie jetzt ihren tragenden Grund.

    Args:
        hat_split: liegt der Strom **getrennt je Funktion** vor
            ⛔ **Dasselbe Wort, andere Frage als in** {@link
            backend.core.berechnungen.betriebsart_gemessen.funktionsfremd_abzug_kwh}:
            Dort heißt ``hat_split`` seit N-462 *ist der Nenner die feine
            Summe?*; hier bleibt es das **Kennzeichen**
            ``getrennte_strommessung``, denn ohne feine Zähler gibt es E je
            Funktion gar nicht — egal, welche Menge die Gesamt-Arbeitszahl als
            Nenner nimmt.
            (`getrennte_strommessung`)? Ohne ihn gibt es E je Funktion nicht —
            dann tragen **beide** Zahlen den Grund
            {@link GRUND_STROM_NICHT_JE_FUNKTION}. ⚠ Die Wärme allein genügt
            nicht: Q ohne E ist kein Quotient, und `strom_heizen_kwh` bedeutet
            **ohne** das Kennzeichen etwas anderes (K3) — dort ist es kein
            Summand einer zweiteiligen Achse.
        waerme_ist_gesamt: Trägt die Zeile eine **gemessene Gesamtwärme**
            (Feld ``waerme_kwh``, EIN gemeinsamer Wärmemengenzähler über
            Heizung und Warmwasser)? Dann bekommt **jede Funktion ohne eigenen
            Wärmewert** den Grund {@link GRUND_WAERME_NICHT_JE_FUNKTION} statt
            des Defaults „kein Wärmemengenzähler zugeordnet" — der ist hier
            falsch, der Zähler ist zugeordnet (N-391).

            ⛔ **Er macht keine eigene Sperre auf, sondern setzt den
            `waerme_fehlt_grund` der betroffenen Funktion.** Damit wirkt er
            genau dort, wo ``arbeitszahl`` ohnehin sperrt (``q <= 0``) — und
            **nur** dort. Wer neben dem Gesamtzähler auch die Aufteilung pflegt,
            behält seine beiden Zahlen: sie sind gemessen, ihr Zähler und ihr
            Nenner tragen dieselbe Funktion, R2 ist erfüllt. Eine Sperre „sobald
            ein Gesamtwert dasteht" nähme ihm eine **richtige** Zahl — dieselbe
            Klasse wie die verworfene Sperre „Warmwasser fehlt" (die hätte Lage D
            getroffen: Wärmemengenzähler nur auf dem Heizkreis, Heiz-Arbeitszahl
            richtig).

            ⚠ **Er gewinnt gegen ``waerme_fehlt_grund_*``**, wo beide gesetzt
            sind: Dass für diese Funktion kein Wert vorliegt, hat dann eine
            **bekannte** Ursache — der gemeinsame Zähler —, und die ist die
            genauere Auskunft als „kein Zähler zugeordnet" (S3).
        waerme_abgeleitet_kwh: sperrt **beide** Zahlen. Eine aus dem Strom
            gerechnete Wärme ergibt je Funktion genauso den Faktor zurück, mit
            dem sie gerechnet wurde, wie in der Summe (Konzept §3.5).
        abgrenzung_verletzt: gilt für **beide** — ein Heizstab auf dem Zähler
            oder ein versetzter Zeitraum trifft nicht nur eine der Funktionen.
        waerme_fehlt_grund_heizen: **W-18 je Funktion.** Kurzer Grund, warum
            ``heizung_kwh`` fehlt. ``None`` lässt den Default-Wortlaut von
            ``arbeitszahl`` stehen — der Aufruf ist damit **bitgleich zu vorher**.
        waerme_fehlt_grund_warmwasser: dasselbe für ``warmwasser_kwh``.

            ⭐ **Warum ZWEI Eingänge und nicht einer wie bei ``arbeitszahl``.**
            Die beiden Funktionen haben verschiedene Zähler und deshalb
            verschiedene Gründe; ``_tageswert_grund_kombiniert`` sagt es
            wörtlich: *„Wer den Wärmemengenzähler für die Heizung zugeordnet hat
            und den fürs Warmwasser nicht, soll nicht lesen ‚kein Zähler
            zugeordnet'."* Ein gemeinsamer Eingang träfe zwangsläufig eine der
            beiden Zeilen falsch — genau der Fehler, den W-18 abschaffen wollte,
            nur eine Ebene tiefer.

            ⛔ **Anders als ``abgrenzung_verletzt``, das bewusst für beide gilt.**
            Ein Heizstab auf dem Zähler trifft die Abgrenzung der ganzen Anlage;
            ein fehlender Tageswert trifft genau eine Größe. Die Asymmetrie ist
            Absicht, kein Versehen.

            ⭐ **Seit 10.09.2026 präzisiert (SOLL §3.2b):** „für beide" gilt
            weiterhin für die Anwender-Angabe und den Zeitraum-Versatz, aber
            **nicht** mehr für gemischte Bauarten und Geräte ohne Wärme — dafür
            gibt es ``abgrenzung_je_funktion_grund``.
        abgrenzung_je_funktion_grund: je Funktion ihr Grund — aus
            {@link abgrenzung_je_funktion}. ``None`` legt ``abgrenzung_verletzt``
            wie bisher auf **beide** und ist damit **bitgleich zum Stand vor der
            Präzisierung**; so rufen die Hub-Pfade weiterhin auf, wo je Gerät
            gerechnet wird und die Frage gegenstandslos ist.

            ⭐ **Was das sichtbar macht** (Fixture A5, dietmar1968): Eine
            Wärmepumpe mit getrennter Strommessung neben einer Split-Klimaanlage
            zeigte drei Striche, während der Komponenten-Hub für dasselbe Gerät
            längst 3,0 und 2,5 auswies. Die Klimaanlage trägt ihren Strom in
            ``stromverbrauch_kwh`` — das gehört zu keiner Funktion und steht in
            keinem der beiden Quotienten.
        achsen: **Welche Wärme-Achsen gibt es hier überhaupt?** (WK-16h/**R-1**,
            Namen aus ``field_definitions.WP_ACHSE_*``). ``None`` heißt „beide"
            und ist damit **bitgleich zum Stand vor WK-16h**.

            ⭐ **Die Registry antwortet, nicht diese Funktion** (ADR-001: der
            Layer bleibt registry-frei; ADR-002/**P13**: die Bauart entscheidet
            keine Größe). Je Gerät kommt die Menge aus
            ``field_definitions.wp_waerme_achsen``, anlagenweit aus der
            Vereinigung über die **beitragenden** Geräte
            (``waerme_klima_block.achsen_der_anlage``).

            Eine Achse, die nicht in ``achsen`` steht, bekommt
            {@link ARBEITSZAHL_GILT_NICHT} — **weder Zahl noch Grund**. Das ist
            WK-15c eine Fläche weiter: *eine Achse, die am Gerät nicht gilt,
            trägt in keiner Rechnung und keinem Hinweis eine Zahl.*
        gesamt: Die **Gesamt**-Arbeitszahl derselben Einheit (Gerät bzw. Anlage),
            für die **Ein-Achsen-Regel**. ``None`` schaltet sie ab und ist
            bitgleich zum Stand vor WK-16h.

            ⭐ **Hat eine Einheit genau EINE Wärme-Achse, ist die
            Funktions-Arbeitszahl dieser Achse die Gesamt-Arbeitszahl.** Strom
            und Wärme sind dann per Bauart dieser Funktion zugeordnet; ein
            getrennter Zähler könnte nichts anderes messen. Gemessen an der r28
            (15.09.2026): Die Brauchwasser-WP *Stiebel WWK 300* hatte eine
            Gesamtzahl von **3,31** und daneben *„Strom nicht getrennt je
            Funktion gemessen"* an der Warmwasser-Zeile — für ein Gerät, dessen
            gesamter Strom Warmwasser-Strom **ist** (N-499).

            ⛔ **Der Grund an der Kategorie, nicht am Beispiel:** Ein Gerät ohne
            zweite Funktion **hat** keine Aufteilung, die fehlen könnte. Deshalb
            gilt derselbe Satz für die **Split-Klimaanlage** (nur Heizen) — und
            dort löst er zugleich die Grund-Rangfolge (**R-2**): Ihre Gesamtzahl
            sagt *„kein Wärmemengenzähler zugeordnet"*, und das ist der
            zutreffende Grund; *„Strom nicht getrennt"* nannte die falsche Seite.

            ⚠ **Sie ersetzt nur einen Grund, nie eine Zahl.** Wo die feinen
            Zähler eine Funktions-Arbeitszahl hergeben, bleibt sie stehen: Sie
            ist eine Messung *dieser* Funktion, und ein Gesamtzähler, der mehr
            misst (Standby, Steuerung), wäre dafür der gröbere Nenner.
    """
    _achsen = WAERME_ACHSEN if achsen is None else frozenset(achsen)

    def _je_achse(achse: str, eigene: Arbeitszahl) -> Arbeitszahl:
        """Die Achsen-Regel an EINER Stelle (**R-1**), für beide Funktionen.

        Drei Lagen, in dieser Reihenfolge: die Achse gilt nicht ⇒ nichts · sie
        ist die **einzige** und die eigene Rechnung hat keine Zahl ⇒ die
        Gesamtzahl · sonst die eigene Rechnung. ``gesamt`` ersetzt damit nur
        einen **Grund**, nie eine **Zahl**.
        """
        if achse not in _achsen:
            return ARBEITSZAHL_GILT_NICHT
        if gesamt is None or _achsen != {achse} or eigene.wert is not None:
            return eigene
        return gesamt

    if not hat_split:
        gesperrt = Arbeitszahl(None, GRUND_STROM_NICHT_JE_FUNKTION)
        return ArbeitszahlJeFunktion(
            heizen=_je_achse(HEIZEN, gesperrt),
            warmwasser=_je_achse(WARMWASSER, gesperrt),
        )

    def _je(
        q: Optional[float],
        e: Optional[float],
        waerme_fehlt_grund: Optional[str],
        kein_betrieb_grund: Optional[str],
        abgrenzung_dieser_funktion: Optional[str],
    ) -> Arbeitszahl:
        return arbeitszahl(
            q, e,
            waerme_abgeleitet_kwh=waerme_abgeleitet_kwh,
            abgrenzung_verletzt=abgrenzung_dieser_funktion,
            waerme_fehlt_grund=waerme_fehlt_grund,
            # ⭐ **Welcher Wortlaut, weiß diese Funktion; OB überhaupt, weiß
            # nur der Aufrufer** (`null_ist_gemessen`). Die Trennung ist an einer
            # roten Probe gelernt: `test_b4_cockpit_matrix` meldete „Monat gegen
            # Jahr, zwei Aussagen", als der Grund hier unbedingt gesetzt war.
            # ⛔ **Der Jahres-Pfad darf ihn NICHT bekommen** — er bildet
            # `sum(f.wp.heizung_kwh …)` (`waermepumpe_jahreskennzahlen.py:118`),
            # und `sum()` liefert 0, ob gemessen oder nie erfasst. Dort hieße
            # „kein Heizbetrieb" bei einer Anlage OHNE Wärmemengenzähler eine
            # **neue** Falschaussage — derselbe Fehler wie der geheilte, nur in
            # der Gegenrichtung.
            kein_betrieb_grund=kein_betrieb_grund,
        )

    def _abgrenzung(funktion: str) -> Optional[str]:
        if abgrenzung_je_funktion_grund is None:
            return abgrenzung_verletzt
        return abgrenzung_je_funktion_grund.get(funktion)

    # N-391: die Gesamtwärme erklärt, warum es für eine Funktion keinen eigenen
    # Wert gibt. `arbeitszahl` wertet den Grund nur bei fehlendem Zähler aus —
    # wer die Aufteilung daneben pflegt, behält seine Zahlen.
    _gesamt_grund = GRUND_WAERME_NICHT_JE_FUNKTION if waerme_ist_gesamt else None
    # **N-479: die Marke darf je Funktion verschieden sein.** Der TAG liest die
    # Zeile selbst und setzt ``null_ist_gemessen=True`` pauschal — für ihn ist
    # jede fehlende Größe schon vorher als Grund benannt. Monat und Jahr
    # summieren dagegen über Geräte und Zeilen; dort kann die Heizwärme gemessen
    # sein und die Warmwasser-Wärme nicht. Ohne diese Trennung müssten sie sich
    # für **eine** der beiden Aussagen entscheiden und lägen bei der anderen
    # falsch. Fehlt die feine Angabe, gilt die pauschale — der Tagespfad bleibt
    # damit unverändert.
    _ng_heizen = (
        null_ist_gemessen if null_ist_gemessen_heizen is None
        else null_ist_gemessen_heizen
    )
    _ng_warmwasser = (
        null_ist_gemessen if null_ist_gemessen_warmwasser is None
        else null_ist_gemessen_warmwasser
    )
    _roh = ArbeitszahlJeFunktion(
        heizen=_je(
            heizung_kwh, strom_heizen_kwh,
            _gesamt_grund or waerme_fehlt_grund_heizen,
            GRUND_KEIN_HEIZBETRIEB if _ng_heizen else None,
            _abgrenzung("heizen"),
        ),
        warmwasser=_je(
            warmwasser_kwh, strom_warmwasser_kwh,
            _gesamt_grund or waerme_fehlt_grund_warmwasser,
            GRUND_KEINE_WARMWASSERBEREITUNG if _ng_warmwasser else None,
            _abgrenzung("warmwasser"),
        ),
    )
    # **R-1 auch mit getrennten Zählern.** Ein Kennzeichen macht keine Achse:
    # Wer `getrennte_strommessung` an einer Brauchwasser-WP setzt, bekommt für
    # die Heiz-Achse trotzdem nichts — sonst stünde dort wieder ein Grund für
    # eine Funktion, die es am Gerät nicht gibt. Und wo die feinen Zähler eine
    # Zahl hergeben, bleibt sie: `_je_achse` ersetzt nur einen **Grund**.
    return ArbeitszahlJeFunktion(
        heizen=_je_achse(HEIZEN, _roh.heizen),
        warmwasser=_je_achse(WARMWASSER, _roh.warmwasser),
    )


#: Grund, wenn die Kältemenge fehlt — der Normalfall, denn Kältemengenzähler
#: sind selten. **Er nennt den Ausweg**, statt nur das Fehlen zu melden.
GRUND_KEINE_KAELTEMENGE = "kein Kältemengenzähler zugeordnet"

#: Der Kältemengenzähler ist zugeordnet und meldet **null**, während Kühlstrom
#: floss — nur die Tagessicht kann das von „kein Zähler" unterscheiden
#: (Konzept Wärme/Klima §8, Bauschnitt 6, Entscheid Gernot 11.09.2026).
#:
#: ⛔ **Warum NICHT ``GRUND_KEIN_KUEHLBETRIEB``**, obwohl die Heizseite es so
#: macht (ef696c1c: gemessene Wärme 0 ⇒ „kein Heizbetrieb"). Dort trägt die
#: Begründung — Heizstrom ohne Heizwärme ist Standby und Umwälzung. Beim Kühlen
#: nicht: Der Kühlstrom ist in eedc über den **eingestellten Modus** bestimmt,
#: und ein pausiertes Gerät im Kühlmodus **kühlt** nach eedcs eigener Regel
#: weiter (Handbuch Wärme/Klima, „Leerlauf behält deinen Modus"). Der Grund
#: „kein Kühlbetrieb" heißt im Handbuch wörtlich *„der Kühlstrom ist null"* —
#: neben einer sichtbaren Kühlstrom-Menge wäre er eine Falschaussage.
#:
#: ⚠ Nur mit ``null_ist_gemessen`` — Monat und Jahr summieren vorher (``sum()``
#: ⇒ immer eine Zahl) und dürfen den Wortlaut nicht führen.
GRUND_KEINE_KAELTE_ABGEGEBEN = "keine Kälte abgegeben in diesem Zeitraum"

#: „Es wurde nicht gekühlt" — und das **schlägt** den Grund darüber.
#:
#: ⚑ Die Reihenfolge ist die Aussagekraft, nicht die Bequemlichkeit: Wer an
#: diesem Tag gar nicht gekühlt hat, soll das lesen und nicht einen Hinweis auf
#: eine Aggregationslücke, die ihn nichts angeht. Erst **wenn** Kühlstrom
#: geflossen ist, fehlt wirklich nur der Zähler des Quotienten.
#:
#: ⚠ Der Text stand bis 2026-08-29 als Literal in ``arbeitszahl_kuehlen`` und
#: wurde hier herausgezogen, damit der Tagespfad ihn **benutzt** statt ihn
#: danebenzuschreiben (ADR-001/S1 — eine Regel, zwei Formulierungen, eine Drift).
GRUND_KEIN_KUEHLBETRIEB = "kein Kühlbetrieb in diesem Zeitraum"


def arbeitszahl_kuehlen(
    kaelte_kwh: Optional[float],
    strom_kuehlen_kwh: Optional[float],
    *,
    abgrenzung_verletzt: Optional[str] = None,
    kaelte_fehlt_grund: Optional[str] = None,
    null_ist_gemessen: bool = False,
) -> Arbeitszahl:
    """Kältemenge ÷ Kühlstrom — **W-5**, SOLL §4.1.

    ⛔ **Diese Zahl heißt NICHT „SEER", und das ist eine Entscheidung**
    (Empfehlung 26.08., von Gernot angenommen). SEER ist eine **genormte**
    Größe: saisonal gewichtet, unter definierten Prüfstandsbedingungen ermittelt.
    Was hier entsteht, ist der schlichte Quotient zweier Zähler über einen
    Zeitraum. Ihn „SEER" zu nennen behauptete eine Vergleichbarkeit mit
    Datenblatt-Werten, die er nicht hat — dieselbe Klasse wie ein Feldname, der
    etwas anderes trägt als er verspricht (**#120**, die Warnung steht wörtlich
    an ``BETRIEBSART_NUTZENERGIE_FELD``).

    **Sie heißt „Arbeitszahl Kühlen"** — parallel zu „Arbeitszahl Heizen" aus
    W-4, und ehrlich über das, was sie ist: eine gemessene Verhältniszahl.

    ⚠ **Nur aus zwei gemessenen Größen.** Die Kältemenge lässt sich nicht
    ableiten — es gibt keinen „Kälte-Wirkungsgrad", aus dem man sie rechnen
    könnte, ohne genau den Faktor zurückzubekommen, mit dem man gerechnet hat
    (dieselbe Begründung wie bei der abgeleiteten Heizwärme, Konzept §3.5).
    Fehlt sie, steht der Grund da, nicht eine Schätzung.

    ⚠ **Kein Heizstab-Hinweis.** ``HEIZSTAB_HINWEIS`` erklärt eine Arbeitszahl
    nahe 1 mit direkter Elektroheizung — im Kühlbetrieb gibt es dafür keine
    Entsprechung, und eine niedrige Kälte-Arbeitszahl hat andere Ursachen
    (hohe Außentemperatur, kleiner Temperaturhub). Einen Satz zu übernehmen,
    weil die Bauform passt, wäre eine Erklärung, die nichts erklärt.

    Args:
        kaelte_kwh: gemessene abgegebene **Kälte**menge
            (`betriebsart_nutzenergie_kuehlen_kwh`).
        strom_kuehlen_kwh: der Strom, der in den Kühlbetrieb ging.
        abgrenzung_verletzt: wie bei {@link arbeitszahl} — R2 gilt unverändert.
            Ein Fremdanteil auf dem Zähler macht auch diese Zahl unbrauchbar.
        kaelte_fehlt_grund: **W-18 für die Kälte** — der kurze Grund, warum
            ``kaelte_kwh`` fehlt, wenn ihn der Aufrufer kennt („für diesen Tag
            keine Zählerstände", „Zählerrücksprung"). ⚠ **Nie für „nicht
            zugeordnet"**: dafür ist ``GRUND_KEINE_KAELTEMENGE`` der richtige
            Satz, und die Kurzform der Tagesgründe spricht von einem
            *Wärme*mengenzähler. Default ``None`` ⇒ bitgleich zu vorher.
        null_ist_gemessen: ``True`` nur, wo „gemessen 0" von „nicht erfasst"
            unterscheidbar ist (Tag). Dann ergibt gemessene Kälte 0 bei
            Kühlstrom > 0 ``GRUND_KEINE_KAELTE_ABGEGEBEN``.
    """
    e = float(strom_kuehlen_kwh or 0.0)
    q = float(kaelte_kwh or 0.0)
    if e <= 0:
        return Arbeitszahl(None, GRUND_KEIN_KUEHLBETRIEB)
    if q <= 0:
        # Dieselbe Bauform wie in `arbeitszahl` (W-18 + ef696c1c): ein
        # bekannter Grund gewinnt; ein gemessener Nullwert ist kein fehlender
        # Zähler. `q == 0`, nicht `<= 0` — ein negativer Wert wäre ein
        # Rücksprung, und für den gibt es `kaelte_fehlt_grund`.
        if (null_ist_gemessen and q == 0 and kaelte_kwh is not None
                and not kaelte_fehlt_grund):
            return Arbeitszahl(None, GRUND_KEINE_KAELTE_ABGEGEBEN)
        return Arbeitszahl(None, kaelte_fehlt_grund or GRUND_KEINE_KAELTEMENGE)
    if abgrenzung_verletzt:
        return Arbeitszahl(None, abgrenzung_verletzt)
    # Die Herleitung wie bei `arbeitszahl` — diese Funktion rechnet bewusst
    # selbst (kein `strom_funktionsfremd_kwh`-Abzug, s. Docstring), muss die
    # benutzten Zahlen deshalb auch selbst mitgeben. Sie erbt sie nicht.
    return Arbeitszahl(q / e, zaehler_kwh=q, nenner_kwh=e)


# =============================================================================
# D-Sicht — welche Gründe in den Kasten gehören und welche nur ein „—" sind
# =============================================================================

#: Die Ausstattung gibt diese Größe **nicht her** — kein Kältemengenzähler,
#: keine getrennte Strommessung, ein gemeinsamer Wärmemengenzähler, eine
#: gemeldete Abgrenzungs-Störung. Solche Gründe erscheinen **einmal je Sicht**
#: im Kasten *„Was noch möglich wäre"*, mit dem Handgriff daneben — nicht als
#: Kachel mit „—" (Konzept Wärme/Klima §6, **D-Sicht**, Entscheid Gernot
#: 14.09.2026).
GRUND_KLASSE_AUSSTATTUNG = "ausstattung"

#: Die Ausstattung gibt die Größe her, **dieser Zeitraum** ist leer — die
#: Arbeitszahl Heizen im Juni, der Kühlbetrieb im Januar. Dafür steht ein „—"
#: **ohne Text**: Es gibt nichts zu tun, und ein Satz daneben legte nahe, dass
#: doch etwas fehlt.
GRUND_KLASSE_ZEITRAUM = "zeitraum"

#: Jeder Grund dieser Fläche → seine Klasse. **Genau einmal, an der Konstante**
#: (D-Sicht 2) — der Client vergleicht keine Grund-Texte, sonst stünde dieselbe
#: Aussage an zwei Orten und liefe beim nächsten Wortlaut auseinander (die
#: W-3-Klasse, dieselbe Begründung wie bei {@link GRUENDE_HUB_HILFT}).
#:
#: ⚠ **``GRUND_ZEITRAUM`` steht unter AUSSTATTUNG, und das ist kein Tippfehler.**
#: Der Name meint *„die beiden Zähler messen verschieden lange Zeiträume"* —
#: eine Erfassungslücke mit Handgriff (*Lücken im Monatsabschluss schließen*),
#: nicht ein leerer Zeitraum. Die Klasse fragt: *Gibt es etwas zu tun?* — nicht:
#: *Steht „Zeitraum" im Namen?*
#:
#: ⚠ **Ein Grund ohne Eintrag gilt als AUSSTATTUNG** ({@link grund_klasse}).
#: Das ist die vorsichtige Richtung: Ein neuer Grund landet dann im Kasten, wo
#: ihn jemand liest, statt als stummes „—" zu verschwinden.
GRUND_KLASSE: dict[str, str] = {
    # ── Zeitraum: die Ausstattung ist da, der Zeitraum ist leer ──────────────
    GRUND_KEIN_HEIZBETRIEB: GRUND_KLASSE_ZEITRAUM,
    GRUND_KEINE_WARMWASSERBEREITUNG: GRUND_KLASSE_ZEITRAUM,
    GRUND_KEIN_KUEHLBETRIEB: GRUND_KLASSE_ZEITRAUM,
    GRUND_KEINE_KAELTE_ABGEGEBEN: GRUND_KLASSE_ZEITRAUM,
    GRUND_NUR_KUEHLBETRIEB: GRUND_KLASSE_ZEITRAUM,
    # ── Ausstattung: es gibt einen Handgriff ────────────────────────────────
    GRUND_KEIN_STROM: GRUND_KLASSE_AUSSTATTUNG,
    GRUND_KEINE_WAERMEMESSUNG: GRUND_KLASSE_AUSSTATTUNG,
    GRUND_KEINE_KAELTEMENGE: GRUND_KLASSE_AUSSTATTUNG,
    GRUND_WAERME_ABGELEITET: GRUND_KLASSE_AUSSTATTUNG,
    GRUND_STROM_NICHT_JE_FUNKTION: GRUND_KLASSE_AUSSTATTUNG,
    GRUND_WAERME_NICHT_JE_FUNKTION: GRUND_KLASSE_AUSSTATTUNG,
    GRUND_FREMDSTROM: GRUND_KLASSE_AUSSTATTUNG,
    GRUND_FREMDWAERME: GRUND_KLASSE_AUSSTATTUNG,
    GRUND_ZEITRAUM: GRUND_KLASSE_AUSSTATTUNG,
    GRUND_BAUARTEN_GEMISCHT: GRUND_KLASSE_AUSSTATTUNG,
    GRUND_GERAETE_OHNE_WAERME: GRUND_KLASSE_AUSSTATTUNG,
    GRUND_GERAETE_VERSCHIEDEN: GRUND_KLASSE_AUSSTATTUNG,
    GRUND_GERAETE_VERSCHIEDENE_MONATE: GRUND_KLASSE_AUSSTATTUNG,
    GRUND_FUNKTION_NICHT_DECKUNGSGLEICH: GRUND_KLASSE_AUSSTATTUNG,
    GRUND_FUNKTION_VERSCHIEDENE_MONATE: GRUND_KLASSE_AUSSTATTUNG,
}

#: Der **Handgriff** je Ausstattungs-Grund — was der Anwender tun kann, damit
#: die Größe entsteht. Quelle ist die Spalte *„Was du tun kannst"* aus
#: ``docs/HANDBUCH_WAERME_KLIMA.md`` §4; er steht hier, damit Cockpit und
#: Handbuch denselben Rat geben (S1).
#:
#: ⛔ **Nicht jeder Ausstattungs-Grund hat einen.** *„Wärme und Strom stammen
#: aus verschiedenen Monaten"* hat keinen allgemeingültigen Weg — dort bleibt
#: die Zeile mit ihrem Grund und ohne Rat stehen. Einen zu erfinden wäre die
#: Klasse, die W-18 ausgelöst hat: ein Rat, der ins Leere führt.
HANDGRIFF_JE_GRUND: dict[str, str] = {
    GRUND_KEIN_STROM: "Stromzähler zuordnen oder den Monatswert pflegen",
    GRUND_KEINE_WAERMEMESSUNG: (
        "Wärmemengenzähler zuordnen — oder die gepflegte Arbeitszahl nutzen "
        "(die Wärme ist dann geschätzt)"
    ),
    GRUND_KEINE_KAELTEMENGE: "Kältemengenzähler zuordnen",
    GRUND_WAERME_ABGELEITET: (
        "Wärmemengenzähler zuordnen — dann ist die Wärme gemessen statt "
        "gerechnet"
    ),
    GRUND_STROM_NICHT_JE_FUNKTION: (
        "Getrennte Strommessung einschalten und beide Zähler zuordnen"
    ),
    GRUND_WAERME_NICHT_JE_FUNKTION: (
        "Einen zweiten Wärmemengenzähler setzen und Heizwärme und "
        "Warmwasser-Wärme getrennt pflegen"
    ),
    GRUND_FREMDSTROM: "Angabe „Fremdanteil auf den Zählern“ am Gerät prüfen",
    GRUND_FREMDWAERME: "Angabe „Fremdanteil auf den Zählern“ am Gerät prüfen",
    GRUND_ZEITRAUM: "Lücken im Monatsabschluss schließen",
    GRUND_BAUARTEN_GEMISCHT: "Jedes Gerät einzeln im Komponenten-Hub ansehen",
    GRUND_GERAETE_OHNE_WAERME: "Jedes Gerät einzeln im Komponenten-Hub ansehen",
    GRUND_GERAETE_VERSCHIEDEN: (
        "Im Komponenten-Hub steht je Gerät, welche Seite fehlt"
    ),
    GRUND_FUNKTION_NICHT_DECKUNGSGLEICH: (
        "Getrennte Strommessung am zweiten Gerät einschalten und zuordnen, "
        "wenn es sie gibt"
    ),
    GRUND_GERAETE_VERSCHIEDENE_MONATE: "Die fehlenden Monatswerte nachpflegen",
    GRUND_FUNKTION_VERSCHIEDENE_MONATE: "Die fehlenden Monatswerte nachpflegen",
}


#: ⭐ **Die beiden TAGES-Gründe gehören dazu, und zwar als AUSSTATTUNG** (über
#: den Default von {@link grund_klasse}). Sie sagen nicht *„dieser Tag war
#: leer"*, sondern *„für diesen Tag fehlt die Messung"* — und genau dafür gibt
#: es W-18: Ein stummes „—" war die Auskunft, gegen die der Melder sich
#: beschwert hat (dietmar1968, T89667 #210). Sie hier zu verschlucken hieße,
#: W-18 rückgängig zu machen; sie bekommen deshalb einen Handgriff.
HANDGRIFF_JE_GRUND.update({
    TAGESWERT_GRUND_KURZ[GRUND_KEINE_ZAEHLERSTAENDE]: (
        "Den Tag in der Reparatur-Werkbank nachrechnen "
        "(Einstellungen → Daten)"
    ),
    TAGESWERT_GRUND_KURZ[GRUND_ZAEHLER_RUECKSPRUNG]: (
        "Den Zähler im Daten-Checker prüfen (Einstellungen → Daten)"
    ),
})


def grund_klasse(grund: Optional[str]) -> Optional[str]:
    """Die Klasse eines Grundes — ``None`` ohne Grund.

    ⚠ **Ein unbekannter Grund gilt als Ausstattung.** Das ist die vorsichtige
    Richtung: Er landet im Kasten *„Was noch möglich wäre"*, wo ihn jemand
    liest, statt als stummes „—" zu verschwinden. Die Gegenrichtung wäre ein
    still verschluckter Hinweis — genau das, was die D-Sicht abschaffen soll.
    """
    if not grund:
        return None
    return GRUND_KLASSE.get(grund, GRUND_KLASSE_AUSSTATTUNG)


def ist_ausstattungs_grund(grund: Optional[str]) -> bool:
    """Gehört dieser Grund in den Kasten *„Was noch möglich wäre"*?"""
    return grund_klasse(grund) == GRUND_KLASSE_AUSSTATTUNG
