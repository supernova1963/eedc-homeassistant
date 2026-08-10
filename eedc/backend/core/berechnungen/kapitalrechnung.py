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
Ersatzteil, Wartung.

⚠ **Nur die AUSGABEN, nicht das Netto** (Entscheid Gernot, 09.08., nach der
Messung). Sonstige **Erträge** bleiben im Zähler, wo sie schon immer waren.
Grund ist keine Meinung, sondern das Verhalten der Formel: ein wiederkehrender
Ertrag ``E`` im Nenner ergibt ``(K − E·n) ÷ Z`` — eine Zahl, die jedes Jahr
schrumpft, bei ``n = K/E`` durch null geht und danach negativ wird. Sie ist
keine Amortisationsdauer mehr. Im Zähler ergibt derselbe Ertrag ``K ÷ (Z + E)``
und konvergiert. Bei Ausgaben tritt das Problem **nicht** auf — dort trägt die
Vollkostenrechnung in beiden Fällen (s. u.).

⏳ **ZWISCHENSTAND — die Ertragsseite ist nicht der Endzustand.** Sie wandert mit
**Bauschritt 7** aus ``docs/KONZEPT-WIRTSCHAFTLICHKEITSRECHNUNG.md`` §8 ebenfalls
in den Nenner; dann ist die Vollkostenrechnung vollständig. Der Grund für den
heutigen Zustand ist **nicht fachlich, sondern zeitlich**: solange es keinen Ort
für *wiederkehrende* Erträge gibt (Ertragsfeld an der Investition, §8/1), müssen
sie im Monatsabschluss stehen — und dort dürfen sie nicht als Kapital gewertet
werden, sonst bricht der Fall aus §9. ⚠ **Schritt 7 hat zwei harte
Vorbedingungen** (§9.1): der Umstiegsweg muss existieren, und die Betroffenen
müssen es **vorher** wissen — er ändert die Wirkung bestehender Daten.

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
  ein Aufwand des Zeitraums, und das ist richtig so (``monats_fakten.py``,
  ``aktueller_monat.py``, ``cockpit/*``, Jahresbericht-PDF, CSV-Export).
- Die **Kapitalrechnung** nimmt sie in den **Nenner**. „Wie lange dauert es, bis
  sich das rechnet?" — dort ist dieselbe Reparatur zusätzlich eingesetztes
  Kapital, kein Abzug vom laufenden Ertrag.

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
) -> float:
    """Nenner für ROI und Amortisationsdauer.

    Args:
        relevante_kosten_euro: Mehrkosten gegenüber der Alternative
            (``relevante_kosten_aus_investitionen``).
        sonstige_ausgaben_euro: **Kumulierte** sonstige AUSGABEN des
            betrachteten Zeitraums, als **positiver** Betrag
            (``berechne_sonstige_summen(...)["ausgaben_euro"]``). Sonstige
            Erträge gehören ausdrücklich **nicht** hierher — sie bleiben im
            Zähler, siehe Modul-Docstring.

    ⚠ **Kumuliert, nicht annualisiert.** Eine Reparatur von 3.000 € erhöht den
    Kapitaleinsatz um 3.000 € — nicht um 3.000 € pro Jahr und auch nicht um
    ihren Jahresdurchschnitt. Genau diese Annualisierung war F-19.

    ⚠ **Und nur echte ``sonstige_positionen``-Ausgaben.** Laufende Größen, die
    der Code selbst berechnet — allen voran die dienstlichen Ladekosten —
    gehören nicht in den Kapitaleinsatz: sie sind Aufwand des Zeitraums, kein
    eingesetztes Kapital.
    """
    return (relevante_kosten_euro or 0.0) + (sonstige_ausgaben_euro or 0.0)


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
) -> float:
    """Annualisiert **jeden Posten mit seiner eigenen Monatszahl** und zieht die
    laufenden Betriebskosten ab.

    ⚠ Ein gemeinsamer Divisor über alle Posten ist genau F-20. Wer hier einen
    Anlagen-Zeitraum einsetzt, verdünnt jede Komponente, die kürzer läuft als
    die Anlage — während ihre Kosten im Nenner voll stehen.

    Die Betriebskosten sind bereits eine Jahresgröße
    (``Investition.betriebskosten_jahr``) und werden deshalb **nicht**
    annualisiert.
    """
    summe = 0.0
    for p in posten:
        if p.monate > 0 and p.summe_euro:
            summe += p.summe_euro / p.monate * 12
    return summe - (betriebskosten_jahr_euro or 0.0)


def erklaerung_jahres_ersparnis(
    posten: Iterable[ErsparnisPosten],
    *,
    betriebskosten_jahr_euro: float = 0.0,
) -> str:
    """Rechenweg als Text — **inklusive** des Betriebskosten-Abzugs.

    Bis 2026-08-09 schrieb der HA-Export ``(10179.06 ÷ 31) × 12`` und lieferte
    daneben einen um exakt die Betriebskosten kleineren Wert (N-212). Wer
    nachrechnete, fand 500 € Differenz und keine Erklärung. Ein Rechenweg, der
    einen Summanden verschweigt, ist keiner.
    """
    teile = [
        f"({p.summe_euro:.2f} ÷ {p.monate}) × 12 [{p.bezeichnung}]"
        for p in posten
        if p.monate > 0 and p.summe_euro
    ]
    text = " + ".join(teile) if teile else "0.00"
    if betriebskosten_jahr_euro:
        text += f" − {betriebskosten_jahr_euro:.2f} (Betriebskosten/Jahr)"
    return text
