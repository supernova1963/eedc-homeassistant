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

from dataclasses import dataclass
from typing import Optional

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


#: Grund für die Abgrenzungs-Sperre, wenn der Block Strom von Geräten trägt,
#: deren Wärme fehlt (SOLL §4.2 Fall 1). Kurz — er steht sichtbar auf der Kachel.
GRUND_GERAETE_OHNE_WAERME = "nicht alle Geräte melden Wärme"

#: **R2/W-7 — Fall H-C:** Der Strom eines fremden Erzeugers (typisch ein
#: Heizstab) liegt auf dem WP-Zähler, seine Wärme läuft nicht über den
#: Wärmemengenzähler. ⇒ **E ist zu groß**, die Arbeitszahl systematisch zu
#: niedrig. Von außen unsichtbar — es ist eine Anwender-Angabe
#: (`PARAM_WAERMEPUMPE["ABGRENZUNG"] = "fremdstrom"`).
GRUND_FREMDSTROM = "Heizstab-Strom auf dem WP-Zähler"

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
    return None


def arbeitszahl(
    waerme_kwh: Optional[float],
    strom_kwh: Optional[float],
    *,
    waerme_abgeleitet_kwh: float = 0.0,
    strom_funktionsfremd_kwh: float = 0.0,
    abgrenzung_verletzt: Optional[str] = None,
    waerme_fehlt_grund: Optional[str] = None,
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
        return Arbeitszahl(None, "kein Stromverbrauch erfasst")
    if e <= 0:
        # Der ganze Strom ging ins Kühlen: es gibt Verbrauch, aber keinen, der
        # zu einer Wärmemenge gehört. „Kein Stromverbrauch" wäre hier die
        # falsche Auskunft — der Zähler lief, nur nicht fürs Heizen.
        return Arbeitszahl(None, "nur Kühlbetrieb in diesem Zeitraum")
    if q <= 0:
        # W-18: Die Sperre stimmt, ihre Begründung war geraten. „Kein
        # Wärmemengenzähler zugeordnet" ist nur EINER von drei Gründen, aus
        # denen keine Wärme vorliegt — und ausgerechnet der falsche für
        # dietmar1968, der beide Zähler zugeordnet hatte (T89667 #210). Wer den
        # wahren Grund kennt, reicht ihn herein; wer ihn nicht kennt, bekommt
        # unverändert den bisherigen Satz. **Der Default ist bitgleich zu
        # vorher** — kein Aufrufer ändert sein Verhalten, ohne es zu wollen.
        return Arbeitszahl(
            None, waerme_fehlt_grund or "kein Wärmemengenzähler zugeordnet",
        )
    if waerme_abgeleitet_kwh > 0:
        return Arbeitszahl(None, "Wärme ist gerechnet, nicht gemessen")
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


#: Grund, wenn der Strom nicht je Funktion vorliegt — die häufigste Lage.
#: **Kurz und mit Ausweg**, wie jeder Sperrgrund (S3): Er sagt nicht nur, dass
#: die Zahl fehlt, sondern woran es liegt.
GRUND_STROM_NICHT_JE_FUNKTION = "Strom nicht getrennt je Funktion gemessen"


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


def arbeitszahl_je_funktion(
    *,
    heizung_kwh: Optional[float],
    strom_heizen_kwh: Optional[float],
    warmwasser_kwh: Optional[float],
    strom_warmwasser_kwh: Optional[float],
    hat_split: bool,
    waerme_abgeleitet_kwh: float = 0.0,
    abgrenzung_verletzt: Optional[str] = None,
) -> ArbeitszahlJeFunktion:
    """Je Funktion eine eigene Arbeitszahl — oder je Funktion ihr Grund.

    ⭐ **Rechnet nicht daneben, sondern ruft ``arbeitszahl`` zweimal.** Damit
    gelten **alle** R2-Sperren unverändert und automatisch auch hier: abgeleitete
    Wärme, Fremdanteil auf dem Zähler, Zeitraum-Versatz, fehlender Zähler. Eine
    zweite Rechenstelle wäre die F-56-Klasse — *eine Regel, die an zwei Stellen
    nachgebaut wird, driftet* —, und sie ist in dieser Datei bereits einmal
    teuer geworden (W-3: die JAZ stand an drei Orten).

    ⚠ **Kein ``strom_funktionsfremd_kwh``-Abzug, und das ist kein Vergessen.**
    ``strom_heizen_kwh`` ist bereits nur der Heizbetrieb; Kühlen, Lüften und
    Entfeuchten sind darin gar nicht enthalten. Ihn hier abzuziehen zöge
    dieselbe Menge zweimal ab.

    Args:
        hat_split: liegt der Strom **getrennt je Funktion** vor
            (`getrennte_strommessung`)? Ohne ihn gibt es E je Funktion nicht —
            dann tragen **beide** Zahlen den Grund
            {@link GRUND_STROM_NICHT_JE_FUNKTION}. ⚠ Die Wärme allein genügt
            nicht: Q ohne E ist kein Quotient, und `strom_heizen_kwh` bedeutet
            **ohne** das Kennzeichen etwas anderes (K3) — dort ist es kein
            Summand einer zweiteiligen Achse.
        waerme_abgeleitet_kwh: sperrt **beide** Zahlen. Eine aus dem Strom
            gerechnete Wärme ergibt je Funktion genauso den Faktor zurück, mit
            dem sie gerechnet wurde, wie in der Summe (Konzept §3.5).
        abgrenzung_verletzt: gilt für **beide** — ein Heizstab auf dem Zähler
            oder ein versetzter Zeitraum trifft nicht nur eine der Funktionen.
    """
    if not hat_split:
        gesperrt = Arbeitszahl(None, GRUND_STROM_NICHT_JE_FUNKTION)
        return ArbeitszahlJeFunktion(heizen=gesperrt, warmwasser=gesperrt)

    def _je(q: Optional[float], e: Optional[float]) -> Arbeitszahl:
        return arbeitszahl(
            q, e,
            waerme_abgeleitet_kwh=waerme_abgeleitet_kwh,
            abgrenzung_verletzt=abgrenzung_verletzt,
        )

    return ArbeitszahlJeFunktion(
        heizen=_je(heizung_kwh, strom_heizen_kwh),
        warmwasser=_je(warmwasser_kwh, strom_warmwasser_kwh),
    )


#: Grund, wenn die Kältemenge fehlt — der Normalfall, denn Kältemengenzähler
#: sind selten. **Er nennt den Ausweg**, statt nur das Fehlen zu melden.
GRUND_KEINE_KAELTEMENGE = "kein Kältemengenzähler zugeordnet"

#: Grund für die **Tagessicht** — und ausdrücklich ein anderer als der darüber
#: (N-348, 2026-08-29).
#:
#: ⛔ **Warum `GRUND_KEINE_KAELTEMENGE` hier eine Falschaussage wäre.** Die
#: Kältemenge ist ein stündlicher Zähler (`betriebsart_nutzenergie_kuehlen_kwh`
#: steht in ``KUMULATIVE_ZAEHLER_FELDER``) — sie *könnte* je Tag entstehen. Was
#: fehlt, ist der Aggregationspfad: ``snapshot/aggregator.py::
#: get_betriebsart_strom_tageswerte`` filtert über ``ist_betriebsart_strom_feld``
#: und holt deshalb nur den **Nenner** (Kühlstrom), nie den Zähler. Wer einen
#: Kältemengenzähler zugeordnet hat, bekäme also „kein Kältemengenzähler
#: zugeordnet" zu lesen — ein Satz, der ihn an der falschen Stelle suchen lässt.
#:
#: ⚑ **Der Weg, falls die Tages-Kühlzahl je gewünscht wird**, damit ihn niemand
#: neu suchen muss: die ``AUSGABE``-Tabelle in ``get_tagesdetail_kwh``
#: (`aggregator.py:880`) um ``("waermepumpe", "betriebsart_nutzenergie_kuehlen_kwh")``
#: erweitern. ⚠ **Vorher zu messen, sonst entsteht eine falsche Zahl statt einer
#: fehlenden:** ob dieser Pfad den Innengerät-Suffix auflöst
#: (``betriebsart_nutzenergie_kuehlen_kwh-3``). ``get_betriebsart_strom_tageswerte``
#: reicht ihn bewusst ungelöst weiter; eine Multisplit-Anlage würde sonst zu
#: wenig Kälte zählen und eine **zu hohe** Arbeitszahl ausweisen.
GRUND_KUEHLZAHL_NUR_MONAT = "Kältemenge wird nicht je Tag gezählt — Kühl-Arbeitszahl im Monat"

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
    """
    e = float(strom_kuehlen_kwh or 0.0)
    q = float(kaelte_kwh or 0.0)
    if e <= 0:
        return Arbeitszahl(None, GRUND_KEIN_KUEHLBETRIEB)
    if q <= 0:
        return Arbeitszahl(None, GRUND_KEINE_KAELTEMENGE)
    if abgrenzung_verletzt:
        return Arbeitszahl(None, abgrenzung_verletzt)
    # Die Herleitung wie bei `arbeitszahl` — diese Funktion rechnet bewusst
    # selbst (kein `strom_funktionsfremd_kwh`-Abzug, s. Docstring), muss die
    # benutzten Zahlen deshalb auch selbst mitgeben. Sie erbt sie nicht.
    return Arbeitszahl(q / e, zaehler_kwh=q, nenner_kwh=e)
