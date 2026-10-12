"""Betriebskosten eines Zeitraums — die Laufzeit-Regel N-228 an EINEM Ort (ADR-001).

**Regel (N-228, Wirtschaftlichkeits-Konzept §8/5):** eine Komponente trägt ihre gepflegten Betriebskosten
(``Investition.betriebskosten_jahr``) nur über ihre **aktiven Monate** — anteilig mit ``Jahresbetrag × aktive
Monate ÷ 12``. Ein Monat ist aktiv, wenn ``Investition.ist_aktiv_im_monat`` ihn zulässt (Anschaffung bis
Stilllegung). Eine Komponente, die im Zeitraum keinen aktiven Monat hat, trägt nichts.

**Ungerundet.** Gerundet wird an der Darstellung, nicht hier: bis 12.10.2026 rundete Cockpit → Monat den
Monatsanteil auf Cent, und Cockpit → Jahr summierte die gerundeten Monate (100 €/Jahr ⇒ 12 × 8,33 = 99,96 €),
während Übersicht und Aussichten ungerundet 100,00 € rechneten (N-699).

Bis 12.10.2026 stand die Regel viermal im Baum, in zwei Formen (N-699): je Monat gerundet in
``aktueller_monat/finanzen.py::betriebskosten_des_monats`` und im T-Konto (``tkonto.py``), über den Zeitraum
inline in ``cockpit/uebersicht.py`` und ``aussichten/finanz_rueckblick.py`` — und der Jahresbericht-PDF rechnete
daneben eine fünfte, alte Form (``Σ Jahresbeträge × Monatszeilen ÷ 12`` über alle Komponenten, auch vor der
Anschaffung und nach der Stilllegung).
"""

from __future__ import annotations

from typing import Iterable


def betriebskosten_monatsanteil(betriebskosten_jahr_euro) -> float:
    """Der Anteil EINES aktiven Monats: ``Jahresbetrag ÷ 12`` (ungerundet).

    Für eine Stelle, die die Aktivität schon selbst geprüft hat (T-Konto-Zeile je Investition). Für einen Monat
    ist das dieselbe Zahl wie :func:`betriebskosten_je_investition` mit genau diesem Monat.
    """
    return (betriebskosten_jahr_euro or 0) / 12


def betriebskosten_je_investition(investitionen: Iterable, monate: Iterable[tuple[int, int]]) -> dict[int, float]:
    """Betriebskosten je Investition über die Monate ``monate`` nach der Laufzeit-Regel (ungerundet).

    Args:
        investitionen: ``Investition``-Objekte (mit ``id``, ``betriebskosten_jahr``, ``ist_aktiv_im_monat``).
        monate: die Monate des Zeitraums als ``(jahr, monat)``; Doppelte zählen einmal.

    Returns:
        ``{investition_id: Jahresbetrag × aktive Monate ÷ 12}`` — nur Investitionen mit gepflegten Betriebskosten
        und mindestens einem aktiven Monat, in der Reihenfolge von ``investitionen``.
    """
    menge = set(monate)
    je_inv: dict[int, float] = {}
    for inv in investitionen:
        bk = inv.betriebskosten_jahr or 0
        if not bk:
            continue
        aktive = sum(1 for (j, m) in menge if inv.ist_aktiv_im_monat(j, m))
        if aktive:
            je_inv[inv.id] = bk * aktive / 12
    return je_inv


def betriebskosten_im_zeitraum(investitionen: Iterable, monate: Iterable[tuple[int, int]]) -> float:
    """Σ :func:`betriebskosten_je_investition` — die Betriebskosten des Zeitraums (ungerundet, 0 ohne Betrag)."""
    return sum(betriebskosten_je_investition(investitionen, monate).values(), 0.0)
