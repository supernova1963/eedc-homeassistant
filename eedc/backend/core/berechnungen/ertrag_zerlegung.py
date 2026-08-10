"""Den kumulierten Netto-Ertrag einer Anlage auf ihre Investitionen zerlegen.

Bauschritt 5 des Wirtschaftlichkeits-Konzepts (§8): neben der
**Amortisationsdauer je Zeile** (Modell) soll der **Fortschritt je Zeile**
stehen (Messung, §4). Der Nenner liegt längst vor — jede ROI-Zeile trägt ihren
``kapitaleinsatz``. Was fehlte, war der **Zähler je Komponente**.

**Warum Zerlegung und nicht Parallelrechnung.** Die naheliegende Bauform wäre,
je Komponente eine eigene kumulierte Ersparnis zu rechnen. Genau daraus
entsteht Drift: dieselbe Größe hätte zwei Rechenwege, und der zweite läuft
irgendwann anders als der anlagenweite Zähler — die Klasse, die dieses Projekt
schon mehrfach gemessen hat (N-137, N-220). Hier wird deshalb **nichts neu
gerechnet**, sondern die bereits gebildete Summe **verteilt**:

    Σ je_investition + nicht_zurechenbar == gesamt

Diese Identität gilt **per Konstruktion**, nicht per Test: ``nicht_zurechenbar``
ist die Differenz, nicht eine zweite Summe. Ein Prüfer kann sie deshalb nicht
„retten" — er kann nur noch feststellen, ob der Rest größer ist als er sein
sollte, und genau das ist die interessante Frage.

⚠ **Der Rest ist kein Mülleimer.** Er trägt, was zu keiner Investition gehören
*kann* — Beträge, deren Bezugsgröße im Zeitraum 0 ist (ein Einspeise-Erlös ohne
eine einzige gemessene Erzeugung), und laufende Größen ohne Komponentenbezug
wie die dienstlichen Ladekosten. Wächst er über das hinaus, ist das ein Befund
und keine Rundung; deshalb wird er ausgewiesen statt still auf die Zeilen
geschmiert.

⚑ **Zwei frühere Rest-Quellen sind seit 2026-08-10 keine mehr:** die
anlagenweiten Monatspositionen (§8/4) stehen mit **Bauschritt 7** im Nenner und
nicht mehr im Zähler, und der gepflegte Erzeuger-Erlös (§9 Weg 2) wird direkt
seiner Zeile zugeordnet — seine Investition ist bekannt.

Reine Funktionen, kein I/O, kein ORM (ADR-001). Wer die Größen beschafft, ist
Sache des Aufrufers — heute ``api/routes/aussichten.py``, wo alle Summanden des
anlagenweiten Zählers ohnehin entstehen.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ErtragsZerlegung:
    """Das Ergebnis: je Investition ein Betrag, plus der nicht zurechenbare Rest."""

    #: ``investition_id -> kumulierter Netto-Ertrag in €``. Negative Werte sind
    #: zulässig und bedeutsam: eine Komponente, deren Betriebskosten ihre
    #: Erträge übersteigen, soll das sagen dürfen.
    je_investition: dict[int, float] = field(default_factory=dict)
    #: ``gesamt − Σ je_investition`` — per Konstruktion, nie unabhängig gebildet.
    nicht_zurechenbar_euro: float = 0.0
    #: Der anlagenweite Zähler, aus dem zerlegt wurde.
    gesamt_euro: float = 0.0


def verteile_nach_gewichten(
    betrag_euro: float, gewichte: dict[int, float]
) -> dict[int, float]:
    """Verteilt ``betrag_euro`` proportional zu ``gewichte``.

    Der Anwendungsfall ist die **Erzeugungsseite**: Einspeise-Erlös und
    Eigenverbrauchs-Ersparnis sind Anlagengrößen — sie entstehen am
    Hauszähler, nicht am einzelnen Erzeuger. Zugerechnet werden sie deshalb
    nach **gemessener Erzeugung** (Entscheid Maintainer, 2026-08-10), nicht
    nach Nennleistung: die kWp sagt, was ein Modul könnte, die kWh sagt, was
    es beigetragen hat.

    Sonderfälle bewusst ohne Ersatzwert:

    * **Summe der Gewichte ≤ 0** ⇒ leeres Ergebnis. Es gibt dann keinen
      Schlüssel, und ein erfundener (Gleichverteilung) würde eine Messung
      behaupten, die nicht existiert — der Betrag bleibt im Rest und ist
      dort sichtbar.
    * **Einzelne Gewichte ≤ 0** fallen heraus, statt einen negativen Anteil
      zu bekommen.
    """
    positiv = {k: g for k, g in gewichte.items() if g and g > 0}
    summe = sum(positiv.values())
    if summe <= 0:
        return {}
    return {k: betrag_euro * g / summe for k, g in positiv.items()}


def zerlege_kumulierten_ertrag(
    *,
    gesamt_euro: float,
    erzeugungs_erloes_euro: float,
    erzeugungs_gewichte: dict[int, float],
    direkt_je_investition: dict[int, float] | None = None,
    abzug_je_investition: dict[int, float] | None = None,
) -> ErtragsZerlegung:
    """Zerlegt den anlagenweiten Zähler auf die Investitionen.

    Args:
        gesamt_euro: der anlagenweite kumulierte Netto-Ertrag — dieselbe Zahl,
            die in den Amortisations-Fortschritt der ganzen Anlage geht.
        erzeugungs_erloes_euro: der am Zähler entstehende Teil (Einspeise-Erlös
            + Eigenverbrauchs-Ersparnis, abzüglich der USt auf den
            Eigenverbrauch). Wird nach ``erzeugungs_gewichte`` verteilt.
        erzeugungs_gewichte: ``investition_id -> gemessene Erzeugung in kWh``
            über den Zeitraum. Schlüssel ist die **Zeilen-ID** der ROI-Sicht:
            beim PV-System der Wechselrichter, sonst die Investition selbst.
        direkt_je_investition: Beträge, die bereits komponentenscharf vorliegen
            und **nicht** verteilt werden — WP-Alternativkosten-Ersparnis,
            E-Auto-Ersparnis, BKW-Ersparnis, gepflegte Monatspositionen.
        abzug_je_investition: was einer Komponente zulasten geht, vor allem die
            Betriebskosten über **ihre** Laufzeit. Positiv übergeben, negativ
            verrechnet.

    Returns:
        ``ErtragsZerlegung`` — mit dem Rest als Differenz, nie als zweiter Summe.
    """
    je_inv: dict[int, float] = {}

    for inv_id, betrag in verteile_nach_gewichten(
        erzeugungs_erloes_euro, erzeugungs_gewichte
    ).items():
        je_inv[inv_id] = je_inv.get(inv_id, 0.0) + betrag

    for quelle, vorzeichen in ((direkt_je_investition, 1.0), (abzug_je_investition, -1.0)):
        for inv_id, betrag in (quelle or {}).items():
            if not betrag:
                continue
            je_inv[inv_id] = je_inv.get(inv_id, 0.0) + vorzeichen * betrag

    gerundet = {k: round(v, 2) for k, v in je_inv.items()}
    return ErtragsZerlegung(
        je_investition=gerundet,
        nicht_zurechenbar_euro=round(gesamt_euro - sum(gerundet.values()), 2),
        gesamt_euro=round(gesamt_euro, 2),
    )


def anteil_je_zeile(
    zerlegung: ErtragsZerlegung, kapitaleinsatz_je_zeile: dict[int, float]
) -> dict[int, float]:
    """Fortschritt in Prozent je Zeile — ``ertrag ÷ kapitaleinsatz × 100``.

    Zeilen ohne Kapitaleinsatz (> 0) kommen **nicht** vor: dort gibt es nichts
    zu amortisieren, und 0 % wäre eine Aussage über eine Größe, die es nicht
    gibt (dieselbe Grenze wie ``berechne_amortisations_fortschritt``). Nicht
    gedeckelt — eine Komponente, die sich doppelt bezahlt gemacht hat, darf das
    sagen.
    """
    return {
        inv_id: round(zerlegung.je_investition.get(inv_id, 0.0) / kosten * 100, 1)
        for inv_id, kosten in kapitaleinsatz_je_zeile.items()
        if kosten and kosten > 0
    }
