"""Amortisations-Fortschritt — „wie weit bin ich?", aus gemessenen Erträgen.

Abzugrenzen von der **Amortisationsdauer** (`core/calculations.py::berechne_roi`,
gezeigt in *Auswertungen → ROI* als „X,X Jahre"). Beide beantworten die
Amortisationsfrage, aber verschieden — und genau deshalb dürfen sie nebeneinander
stehen, sofern sie **denselben Nenner** benutzen:

| | Amortisationsdauer | Amortisations-Fortschritt (hier) |
| --- | --- | --- |
| Zähler | *eine* Jahres-Einsparung, konstant hochgerechnet | die **tatsächlich erzielten** Netto-Erträge seit Inbetriebnahme |
| Aussage | „laut Rechnung in 9,2 Jahren" | „4.800 € von 12.000 € sind drin" |
| Charakter | Modell | Messung |

Der Nenner ist für beide `investitionskosten.relevante_kosten_aus_investitionen`
(Mehrkosten). Vor N-137 war er es nicht: der Fortschritt lief auf einer
Hybrid-Summe mit Festannahmen (siehe dort), die Dauer auf der gepflegten Spalte —
dieselbe Anlage bekam zwei Amortisationen, die sich nicht ineinander umrechnen
ließen.

Reine Funktion, kein I/O, kein ORM (ADR-001). Der Aufrufer bringt die drei
Zahlen mit; wie er zu den bisherigen Erträgen kommt, ist seine Sache — heute
tut das `api/routes/aussichten.py` über Monats-Fakten und Finanz-Zeilen.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class AmortisationsFortschritt:
    """Das Ergebnis. ``fortschritt_prozent`` ist **nicht** bei 100 gedeckelt —
    eine Anlage, die sich doppelt bezahlt gemacht hat, soll das sagen dürfen."""

    relevante_kosten_euro: float
    bisherige_ertraege_euro: float
    fortschritt_prozent: float
    erreicht: bool
    rest_betrag_euro: float
    #: None, wenn kein Rest offen ist ODER der Jahresertrag ≤ 0 — dann gibt es
    #: keine seriöse Restlaufzeit, und geraten wird hier nicht.
    rest_monate: Optional[int]
    prognose_jahr: Optional[int]


def berechne_amortisations_fortschritt(
    *,
    relevante_kosten_euro: float,
    bisherige_ertraege_euro: float,
    jahres_netto_ertrag_euro: float,
    aktuelles_jahr: int,
) -> AmortisationsFortschritt:
    """Wie viel der relevanten Kosten haben die bisherigen Erträge gedeckt?

    ``jahres_netto_ertrag_euro`` ist die Jahres-Prognose des Aufrufers und geht
    **nur** in die Restlaufzeit ein — der Fortschritt selbst ist reine Messung.

    Sonderfälle bewusst ohne Ersatzwert: sind die relevanten Kosten ≤ 0 (nichts
    erfasst, oder jede Anschaffung war günstiger als ihre Alternative), gibt es
    nichts zu amortisieren ⇒ Fortschritt 0, `erreicht=False`, keine Prognose.
    Ein negativer bisheriger Ertrag (Anlaufjahr mit Betriebskosten über den
    Erlösen) bleibt negativ stehen und wird nicht auf 0 geschönt.
    """
    kosten = relevante_kosten_euro or 0.0
    ertraege = bisherige_ertraege_euro or 0.0

    if kosten <= 0:
        return AmortisationsFortschritt(
            relevante_kosten_euro=0.0,
            bisherige_ertraege_euro=round(ertraege, 2),
            fortschritt_prozent=0.0,
            erreicht=False,
            rest_betrag_euro=0.0,
            rest_monate=None,
            prognose_jahr=None,
        )

    fortschritt = ertraege / kosten * 100
    erreicht = ertraege >= kosten
    rest = max(0.0, kosten - ertraege)

    rest_monate: Optional[int] = None
    prognose_jahr: Optional[int] = None
    if not erreicht and jahres_netto_ertrag_euro > 0:
        monate = rest / (jahres_netto_ertrag_euro / 12)
        rest_monate = int(monate)
        prognose_jahr = aktuelles_jahr + int(monate / 12)

    return AmortisationsFortschritt(
        relevante_kosten_euro=round(kosten, 2),
        bisherige_ertraege_euro=round(ertraege, 2),
        fortschritt_prozent=round(fortschritt, 1),
        erreicht=erreicht,
        rest_betrag_euro=round(rest, 2),
        rest_monate=rest_monate,
        prognose_jahr=prognose_jahr,
    )
