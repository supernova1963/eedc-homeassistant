"""Die statische Wirtschaftlichkeitsrechnung — **Zähler und Nenner an einem Ort**.

``amortisation_jahre = kapitaleinsatz ÷ jahres_ersparnis``. Beide Hälften stehen
hier, weil sie nur gemeinsam stimmen: ein Zähler, der über eine andere Zeitspanne
gemittelt wird als der Nenner sie abbildet, liefert eine Zahl, die auf keine
Frage antwortet (F-20).

**Warum eine Zahl dort steht, wo sie steht — inklusive der verworfenen
Alternativen und der Messungen dahinter:**
``docs/KONZEPT-WIRTSCHAFTLICHKEITSRECHNUNG.md``. Wer hier etwas ändern will,
liest zuerst dort §7 („Verworfen") — mehrere naheliegende Umbauten sind
durchgerechnet und gescheitert.

## Der Nenner: Kapitaleinsatz

Was musste bezahlt werden, damit die Anlage das erwirtschaftet, was sie
erwirtschaftet? Das sind die **relevanten Kosten** (Mehrkosten gegenüber der
Alternative, SoT ``investitionskosten.relevante_kosten_aus_investitionen``)
**plus die sonstigen Ausgaben**, die seither angefallen sind — Reparatur,
Ersatzteil, Wartung —, **abzüglich der sonstigen Erträge** (THG-Quote,
Förderung, ein einmaliger Erlös).

**Beide Seiten des Monatsabschlusses stehen damit im Nenner** (Bauschritt 7 des
Konzepts §8, gebaut 2026-08-10) — die Vollkostenrechnung ist vollständig. Die
Regel dahinter ist die **Form der Zahl**, nicht ihre Richtung (§2): ein
Einzelbetrag im Monatsabschluss ist einmal geflossen und wirkt einmal — als
eingesetztes Kapital (Ausgabe) oder als Minderung desselben (Ertrag). Was
*wiederkehrend* gemeint ist, steht an der Investition (``betriebskosten_jahr``
bzw. ``einsparung_prognose_jahr``) und wirkt jährlich im Zähler.

⚠ **Warum die Ertragsseite ein Jahr später kam als die Ausgabenseite** (F-19 am
09.08., Schritt 7 am 10.08.): ein *wiederkehrender* Ertrag ``E`` im Nenner
ergäbe ``(K − E·n) ÷ Z`` — eine Zahl, die jedes Jahr schrumpft, bei ``n = K/E``
durch null geht und danach negativ wird; sie wäre keine Amortisationsdauer mehr.
Solange es **keinen Ort** für wiederkehrende Erträge gab, mussten sie im
Monatsabschluss stehen, und dort durften sie nicht als Kapital gewertet werden
(der Fall aus §9). Beide Vorbedingungen aus §9.1 sind erfüllt, bevor dieser
Schritt gefahren wurde: das Ertragsfeld an der Investition (§8/1) und das
€-Feld je Erzeuger (§8/9) existieren, und die Betroffenen wurden vorher
informiert (§11 — #310, Kommentar vom 10.08.).

⚠ **Der Nenner kann dadurch kleiner werden als die reinen Anschaffungskosten**
— das ist die Aussage: eine Förderung ist Geld, das nie eingesetzt wurde. Fällt
er auf ``≤ 0``, liefern ``berechne_roi`` und ``berechne_amortisations_fortschritt``
**keine** Zahl (statt einer negativen Dauer); das ist der Sonderfall
„vollständig gefördert", und geraten wird dort nicht.

Die Richtung ``typ: ertrag|ausgabe`` muss eedc dabei **nicht raten**: sie steht
im Datenmodell (``utils/sonstige_positionen``), der Anwender wählt sie beim
Erfassen, und sie liegt für jeden Bestandseintrag vor. Das ist der Unterschied
zum verworfenen ``art: aufwand|kapital`` — das wäre eine **neue** Kategorie
gewesen, die niemand gepflegt hätte.

**Der Fall, an dem es gemessen wurde:** rilmor-mhrs betreibt zwei
Wechselrichter mit eigenen Einspeisetarifen (#310). eedc kennt nur **einen**
Einspeisesatz je Anlage — es gibt keine Vergütung je Erzeuger, weder als Spalte
noch im ``parameter``-JSON, und ``Monatsdaten.einspeisung_kwh`` ist ein
Anlagen-Zählerwert. Er muss diese Erlöse deshalb monatlich von Hand als
sonstige **Erträge** pflegen; das Handbuch sieht genau das vor
(``HANDBUCH_EINSTELLUNGEN.md``, „Kosten und Erlöse je Monat"). Im Nenner hätten
sie seine Amortisation **verlängert** statt verkürzt.

**Die Trennlinie, ohne die die nächste Inventur hier eine Drift sieht:**

- Die **Zeitraum-Bilanz** behält die sonstigen Positionen auf der **Ertragsseite**.
  „Was hat der Monat März gekostet und eingebracht?" — dort ist eine Reparatur
  ein Aufwand des Zeitraums und eine Förderung ein Ertrag des Zeitraums, und das
  ist richtig so (``monats_fakten.py``, ``aktueller_monat.py``, ``cockpit/*``,
  Jahresbericht-PDF, CSV-Export, HA-Sensor ``netto_ertrag_euro``).
- Die **Kapitalrechnung** nimmt sie in den **Nenner**. „Wie lange dauert es, bis
  sich das rechnet?" — dort ist dieselbe Reparatur zusätzlich eingesetztes
  Kapital und dieselbe Förderung gespartes Kapital, kein Posten des laufenden
  Ertrags.

**Warum überhaupt (F-19, gemessen 2026-08-09):** vorher landeten sie im
**Zähler** und wurden über die Laufzeit **annualisiert**. Eine einmalige
Reparatur von 3.000 € an einer Wärmepumpe verlängerte die Amortisation damit
von 8,1 auf **42,6 Jahre** — und die Zahl driftete jedes Folgejahr weiter,
ohne dass etwas passierte. In der Jahressicht erschien das Gerät als nie
amortisiert.

**Warum ohne Unterscheidung „einmalig ⟷ laufend"** (Entscheid Gernot, 09.08.):
eedc rechnet ohne Zins und Cash-Flow, also ist die statische Amortisation der
Kanon — und Vollkosten sind in **beiden** Fällen brauchbar. Bei wiederkehrenden
Kosten liefert die kumulative Rechnung sogar exakt das bisherige Ergebnis
(``K + 180n = 1235n ⇒ n = 9,5``); der Unterschied als Momentaufnahme ist ein
Artefakt des Stichtags, nicht des Ansatzes. Dem stünden 32 Jahre Fehler im
einmaligen Fall gegenüber. Ein Feld ``art: aufwand|kapital`` wurde deshalb
verworfen — **Häufigkeit ist nicht Art**, und keine Anwender-Pflege ist besser
als eine, die niemand pflegt (die Klasse von ``einsparung_prognose_jahr``).

**Nicht zu verwechseln mit der USt-Bemessungsgrundlage.** Die bleibt bei den
reinen Mehrkosten (§ 3 Abs. 1b UStG) — eine Reparatur gehört dort nicht hinein.
Deshalb ist das hier eine **zweite** Größe neben ``relevante_kosten_…``, kein
Ersatz dafür.

## Der Zähler: Jahres-Ersparnis

**Jeder Posten wird mit SEINER eigenen Monatszahl annualisiert** — nicht mit der
der Anlage. Das ist F-20 (gemessen 2026-08-09): der HA-Export teilte die Summe
aus Anlagenbilanz **plus** Wärmepumpen- und E-Auto-Ersparnis durch
``len(monatsdaten)``, also durch die Monate der **Anlage**. An der vermessenen
Anlage waren das 31 Monate, während die Wärmepumpe 25 und der zweite Wagen erst
**12** Monate lief. Deren Ersparnis wurde damit auf 12/31 verdünnt — ihre Kosten
standen aber **voll** im Nenner. Ergebnis: 26,4 statt höchstens 23,3 Jahre, und
die Verzerrung wächst mit jeder nachgerüsteten Komponente.

⚠ **Der Fehler war nicht „andere Zahl als das ROI-Dashboard", sondern ein
Widerspruch in der Formel selbst.** Er steht deshalb unabhängig davon, welche
Definition man vorzieht — Modell oder Messung.

Die Monatszahl eines Postens ist die Zahl der Monate, **aus denen seine Summe
stammt**. Nicht die Zahl der Monate seit Anschaffung: pflegt jemand die Daten
erst ab dem dritten Monat, wäre auch das wieder eine Verdünnung.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


def kapitaleinsatz_euro(
    *,
    relevante_kosten_euro: float,
    sonstige_ausgaben_euro: float,
    sonstige_ertraege_euro: float = 0.0,
) -> float:
    """Nenner für ROI und Amortisationsdauer.

    Args:
        relevante_kosten_euro: Mehrkosten gegenüber der Alternative
            (``relevante_kosten_aus_investitionen``).
        sonstige_ausgaben_euro: **Kumulierte** sonstige AUSGABEN des
            betrachteten Zeitraums, als **positiver** Betrag
            (``berechne_sonstige_summen(...)["ausgaben_euro"]``).
        sonstige_ertraege_euro: **Kumulierte** sonstige ERTRÄGE desselben
            Zeitraums, ebenfalls als **positiver** Betrag
            (``…["ertraege_euro"]``) — sie **mindern** den Kapitaleinsatz
            (Bauschritt 7, Konzept §8/§3). Wer sie zusätzlich im Zähler stehen
            lässt, zählt sie zweimal.

    ⚠ **Kumuliert, nicht annualisiert — beide Seiten.** Eine Reparatur von
    3.000 € erhöht den Kapitaleinsatz um 3.000 €, eine Förderung von 500 €
    senkt ihn um 500 € — nicht pro Jahr und nicht im Jahresdurchschnitt. Genau
    diese Annualisierung war F-19 (Ausgaben) bzw. Bauschritt 3 (Erträge).

    ⚠ **Und nur echte ``sonstige_positionen``.** Laufende Größen, die der Code
    selbst berechnet — allen voran die dienstlichen Ladekosten —, gehören nicht
    in den Kapitaleinsatz: sie sind Aufwand des Zeitraums, kein eingesetztes
    Kapital. Dasselbe gilt auf der Ertragsseite für den Einspeise-Erlös und den
    gepflegten ``einsparung_prognose_jahr``: beide sind wiederkehrend und
    gehören in den Zähler.

    ⚠ **Nicht auf 0 geklemmt.** Übersteigen die Erträge das eingesetzte Kapital,
    steht hier ein negativer Betrag — und die beiden Aufrufer-Formeln liefern
    dann *keine* Zahl statt einer negativen Dauer (``berechne_roi``,
    ``berechne_amortisations_fortschritt``). Eine stille 0 wäre die falsche
    Antwort auf eine echte Datenlage.
    """
    return (
        (relevante_kosten_euro or 0.0)
        + (sonstige_ausgaben_euro or 0.0)
        - (sonstige_ertraege_euro or 0.0)
    )


@dataclass(frozen=True)
class ErsparnisPosten:
    """Ein Beitrag zur Jahres-Ersparnis mit **seiner eigenen** Zeitbasis.

    Args:
        bezeichnung: für die Erklärzeile der Oberfläche/HA-Sensoren.
        summe_euro: aufsummierte Ersparnis über ``monate``.
        monate: Zahl der Monate, aus denen ``summe_euro`` stammt. ``0`` ⇒ der
            Posten trägt nichts bei (statt durch null zu teilen).
    """

    bezeichnung: str
    summe_euro: float
    monate: int


def jahres_ersparnis_euro(
    posten: Iterable[ErsparnisPosten],
    *,
    betriebskosten_jahr_euro: float = 0.0,
    jahres_ertraege_euro: float = 0.0,
) -> float:
    """Annualisiert **jeden Posten mit seiner eigenen Monatszahl**, addiert die
    gepflegten Jahres-Erträge und zieht die laufenden Betriebskosten ab.

    ⚠ Ein gemeinsamer Divisor über alle Posten ist genau F-20. Wer hier einen
    Anlagen-Zeitraum einsetzt, verdünnt jede Komponente, die kürzer läuft als
    die Anlage — während ihre Kosten im Nenner voll stehen.

    Die Betriebskosten sind bereits eine Jahresgröße
    (``Investition.betriebskosten_jahr``) und werden deshalb **nicht**
    annualisiert. Für ``jahres_ertraege_euro``
    (``Investition.einsparung_prognose_jahr``, Konzept §8/1+2) gilt dasselbe in
    die andere Richtung: ein Jahresbetrag an der Investition ist per Form
    wiederkehrend und darf weder verdünnt noch hochgerechnet werden.
    """
    summe = 0.0
    for p in posten:
        if p.monate > 0 and p.summe_euro:
            summe += p.summe_euro / p.monate * 12
    return summe + (jahres_ertraege_euro or 0.0) - (betriebskosten_jahr_euro or 0.0)


def annahme_dauer_text(*, betriebskosten_jahr_euro: float = 0.0) -> str:
    """Die Annahme, unter der die Amortisations**dauer** gilt — als Satzteil.

    Konzept §5 (Bauschritt 6): eine Dauer kann ohne Annahme über die Zukunft
    nicht existieren, und die gewählte ist **Modell A** — „es geht nie wieder
    etwas kaputt". Das ist optimistisch, und §5 verlangt ausdrücklich, dass es
    **ausgeschrieben** wird statt verschwiegen: der Amortisations-*Fortschritt*
    daneben unterstellt nichts (§4), die Dauer schon.

    ⚠ **Der Satz richtet sich nach den Daten, nicht nach dem Modellnamen.**
    Sobald jemand ``Investition.betriebskosten_jahr`` pflegt, rechnet eedc
    **Modell C** — der Betrag steht als Abzug im Zähler
    (``jahres_ersparnis_euro``). „Ohne künftige Instandhaltung" wäre dann eine
    falsche Aussage über die eigene Rechnung. Beide Fälle sind derselbe Text-
    SoT, damit nicht die eine Sicht A und die andere C behauptet.

    Args:
        betriebskosten_jahr_euro: Summe der gepflegten Jahres-Betriebskosten,
            die in **dieser** Zahl abgezogen wurde. ``0`` ⇒ Modell A.

    ⚠ Wer eine Dauer anzeigt, ohne diesen Text abzuholen, hat Bauschritt 6 an
    seiner Stelle nicht gefahren — die vier Backend-Quellen (ROI-Dashboard
    gesamt und je Zeile, PDF-Finanzbericht, HA-Sensor) sind in
    ``test_konzept_wirtschaftlichkeit_konformitaet.py`` namentlich gedeckt.
    Das Client-Pendant für Dauern, die der Client selbst bildet, steht in
    ``frontend/src/lib/amortisationAnnahme.ts``.
    """
    if not betriebskosten_jahr_euro:
        return "ohne künftige Instandhaltung"
    betrag = f"{betriebskosten_jahr_euro:_.2f}".replace(".", ",").replace("_", ".")
    return f"inkl. {betrag} €/Jahr Betriebskosten, ohne weitere Instandhaltung"


def erklaerung_jahres_ersparnis(
    posten: Iterable[ErsparnisPosten],
    *,
    betriebskosten_jahr_euro: float = 0.0,
    jahres_ertraege_euro: float = 0.0,
) -> str:
    """Rechenweg als Text — **inklusive** des Betriebskosten-Abzugs.

    Bis 2026-08-09 schrieb der HA-Export ``(10179.06 ÷ 31) × 12`` und lieferte
    daneben einen um exakt die Betriebskosten kleineren Wert (N-212). Wer
    nachrechnete, fand 500 € Differenz und keine Erklärung. Ein Rechenweg, der
    einen Summanden verschweigt, ist keiner — deshalb steht der Jahres-Ertrag
    hier ebenso, sobald er gepflegt ist.
    """
    teile = [
        f"({p.summe_euro:.2f} ÷ {p.monate}) × 12 [{p.bezeichnung}]"
        for p in posten
        if p.monate > 0 and p.summe_euro
    ]
    text = " + ".join(teile) if teile else "0.00"
    if jahres_ertraege_euro:
        text += f" + {jahres_ertraege_euro:.2f} (Ertrag/Jahr an Investitionen)"
    if betriebskosten_jahr_euro:
        text += f" − {betriebskosten_jahr_euro:.2f} (Betriebskosten/Jahr)"
    return text
