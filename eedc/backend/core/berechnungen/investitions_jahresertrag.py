"""Was bringt DIESE Investition im Jahr? — die eine Antwort (§9.2 Geldseite).

## Der Anlass

`einsparung_prognose_jahr` („Ertrag/Jahr") wurde bis zum 06.09.2026 an **drei**
Stellen unabhängig summiert, und zwar mit **verschiedenen** Filtern:

===========================================  ==========================================
`investitionen/crud.py` (ROI-Dashboard)      je Investition
`aussichten.py` (`ertrag_jahr_ges`)          Σ, **mit** ``ist_aktiv_an(heute)``
`ha_export.py` (`jahres_ertraege_ges`)       Σ, **ohne** Aktiv-Filter
===========================================  ==========================================

Drei Stellen, drei Filter, eine Größe — die Bauform, die in diesem Projekt schon
P7, P9 und P10 erzwungen hat. Die §9.2-Geldseite hätte sie ein viertes Mal
verdreifacht: Die Regel „ein Gerät der Kategorie *Abgabe an Dritte* rechnet aus
seinen **gemessenen Monatserlösen**, nicht aus einem Schätzfeld" wäre dreimal
einzubauen gewesen.

## Was hier entschieden wird — und was nicht

Diese Funktion beantwortet **eine** Frage: *Welchen Jahres-Ertrag trägt diese
Investition in den Zähler der Kapitalrechnung?* Sie entscheidet **nicht**, ob
das Gerät aktiv ist (Laufzeit-Filter bleibt beim Aufrufer — die drei sind sich
darin bis heute uneinig, und das ist eine eigene Frage) und sie rechnet
**nichts nach**: Der Erlös ist ein gepflegter Betrag (§9 Weg 2).

## Der Vorrang: gemessen vor geschätzt

Ein Gerät der Kategorie ``abgabe`` hat **beide** Felder — das Monatsfeld „Erlös
(€)" und, weil es Typ *Sonstiges* ist, auch „Ertrag/Jahr". Wer beide pflegt,
bekommt **nicht** die Summe: Der gemessene Monatswert gewinnt, der Schätzwert
schweigt. Dieselbe Bauform wie ADR-002/**P7** (Einzelwerte vor Aggregat).

⚠ **Eine gepflegte 0 ist eine Aussage**, kein fehlender Wert: Wer unentgeltlich
an den Nachbarn abgibt, hat „bringt nichts" gesagt, und seine Zeile ist damit
**bewertet**. Deshalb liest diese Funktion ``hat_einspeise_erloes`` und nicht
den Betrag — der Betrag kann die beiden Fälle nicht trennen
(``imd_monatsaggregat._f`` macht aus ``None`` dieselbe ``0.0``).

## Warum beide Fälle ein ``ErsparnisPosten`` sind

``jahres_ersparnis_euro`` trennt zwei Eingänge: ``posten`` werden **annualisiert**,
``jahres_ertraege_euro`` ausdrücklich **nicht** („ein Jahresbetrag an der
Investition ist per Form wiederkehrend und darf weder verdünnt noch
hochgerechnet werden"). Diese Funktion liefert trotzdem in **beiden** Fällen
einen Posten — der geschätzte mit ``monate=12``.

Das ist rechnerisch exakt dasselbe (``x / 12 * 12 == x``) und hat einen Grund:
Der **Vorrang** *gemessen vor geschätzt* muss an **einer** Stelle entschieden
werden. Gäbe der Helfer den Jahresbetrag als zweiten Rückgabewert zurück,
müsste jeder der drei Aufrufer selbst entscheiden, welchen er nimmt — und
genau diese Entscheidung dreimal zu treffen ist der Fehler, gegen den es diese
Datei gibt.

## Warum ``ErsparnisPosten`` und nicht eine Jahreszahl

Ein Erlös, der in **drei** von zwölf Monaten gepflegt ist, ist keine
Jahresgröße. ``ErsparnisPosten`` trägt seine **eigene Monatszahl** (F-20) und
``jahres_ersparnis_euro`` rechnet daraus hoch — genau wie bei der Wärmepumpen-
und der E-Auto-Ersparnis. Wer stattdessen durch 12 teilt, meldet einem
Anwender, der seit drei Monaten pflegt, ein Viertel seines Ertrags.
"""

from __future__ import annotations

from typing import Iterable, Optional

from backend.core.berechnungen.kapitalrechnung import ErsparnisPosten
from backend.core.field_definitions import (
    SONSTIGES_ABGABE_LABEL,
    ist_abgabe_kategorie,
)

#: Bezeichnung des gemessenen Postens — sie erscheint in Erklärzeilen und
#: HA-Sensor-Attributen. Konzept §9.2: derselbe Begriff wie die Energiezeile,
#: deshalb **abgeleitet** statt zweitgeschrieben (`SONSTIGES_ABGABE_LABEL` ist
#: die eine Quelle des Namens; sonst driften Geld- und Energiezeile getrennt).
BEZEICHNUNG_ABGABE: str = f"Erlös aus {SONSTIGES_ABGABE_LABEL}"

#: Bezeichnung des geschätzten Postens (§8/1, unverändert für Wallbox und das
#: übrige *Sonstiges*).
BEZEICHNUNG_ERTRAGSFELD: str = "Ertrag/Jahr"


def jahresertrag_posten(inv, fakten: Iterable) -> Optional[ErsparnisPosten]:
    """Der Jahres-Ertrags-Posten dieser Investition, oder ``None``.

    ``None`` heißt **„nicht bewertet"** — nie „0 €". Eine 0 an dieser Stelle
    wäre die Fake-0, gegen die N-87 und N-258 angetreten sind: Sie sieht aus
    wie ein Ergebnis und ist eine fehlende Eingabe.

    Args:
        inv: die Investition. Gebraucht werden ``parameter`` (Kategorie),
            ``id`` und ``einsparung_prognose_jahr``.
        fakten: die Monats-Fakten des Zeitraums (ADR-002/P10). Der Aufrufer
            hat sie ohnehin geladen; diese Funktion liest **nur** daraus und
            fasst ``InvestitionMonatsdaten`` nicht selbst an.

    Returns:
        ``ErsparnisPosten`` mit eigener Monatszahl, oder ``None``.
    """
    kategorie = (getattr(inv, "parameter", None) or {}).get("kategorie")

    if ist_abgabe_kategorie(kategorie):
        summe = 0.0
        monate = 0
        for f in fakten:
            g = f.sonstiges.je_geraet.get(inv.id)
            if g is None or not g.hat_einspeise_erloes:
                continue
            summe += g.einspeise_erloes_euro
            monate += 1
        if monate > 0:
            return ErsparnisPosten(BEZEICHNUNG_ABGABE, summe, monate)
        # Kein gepflegter Monat ⇒ **kein** stiller Rückfall auf das Schätzfeld
        # ohne Kennzeichnung: der Rückfall ist erlaubt (unten), aber er heißt
        # dann auch „Ertrag/Jahr" und nicht „Erlös aus Abgabe an Dritte".

    if getattr(inv, "einsparung_prognose_jahr", None) is not None:
        # `is not None`: eine gepflegte 0 heißt „bringt nichts" und ist eine
        # bewertete Zeile (CLAUDE.md, 0-Werte).
        return ErsparnisPosten(
            BEZEICHNUNG_ERTRAGSFELD, float(inv.einsparung_prognose_jahr), 12
        )

    return None
