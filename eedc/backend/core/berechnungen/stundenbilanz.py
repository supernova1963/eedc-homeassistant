"""Bilanzieller Stundenverbrauch aus Zähler-Deltas (ADR-001).

Single Source of Truth für die Formel

    verbrauch = PV + Netzbezug − Einspeisung − Batterie-Nettoladung

die bis 29.08.2026 **zweimal wortgleich** im Baum stand: einmal im Snapshot-
Pfad (`services/snapshot/aggregator.py`) und einmal im HA-LTS-Pfad
(`services/snapshot/lts_aggregator.py`). Das Ergebnis wird als
`TagesEnergieProfil.verbrauch_kw` gespeichert und trägt von dort aus die
Tages- und Monatsbilanz, die Grundlast (Nacht-Sockel) und den HA-Sensor
`eedc_grundlast_kw`.

Die Regel dahinter ist die von ``docs/KONZEPT-UNVOLLSTAENDIGE-WERTE.md``, in
derselben Lesart wie ``core/berechnungen/tagesbilanz.py`` eine Ebene höher:
**eine Summe darf 0 bleiben, eine Differenz nicht.** Der Verbrauch ist eine
Differenz mit vier Eingängen — fehlt einer, ist er nicht *0*, sondern
*unbekannt*.

N-346 (Melder OB73-gif, #395): Bis hierher zählte der Wächter nur drei der vier
Größen auf. Ein fehlender Batterie-Zähler wurde über ``(batt_netto or 0.0)``
still zur 0, und damit war der Stundenverbrauch nachts der **reine Netzbezug**.
Trägt der Speicher die Nacht, steht dort fast nichts — und die Zahl steigt über
den Monat, je weniger er trägt. Der Melder sah genau das: 0 W, dann 10 W, dann
270 W, dann 300 W, während die Live-Prognose daneben 340 W nannte.

⚠ **Zwei Arten von 0 bei der Batterie, und sie sehen gleich aus.** Ein Speicher
führt zwei getrennte Zähler (`ladung_kwh` → Kategorie ``ladung_batterie``,
`entladung_kwh` → ``entladung_batterie``). Eine Richtung allein ergibt keine
Netto-Ladung: Nachts entlädt der Speicher, ohne zu laden — wer dann nur den
Ladezähler kennt, rechnet die Entladung dauerhaft als 0 und bekommt eine
*plausible*, aber falsche Bilanz. Deshalb verlangt ``berechne_batterie_netto_kwh``
**beide** Richtungen, sobald überhaupt ein Speicher erwartet wird.
"""

from __future__ import annotations

from datetime import date
from typing import Iterable, Optional


def erwartet_batterie_beitrag(investitionen: Iterable, tag: date) -> bool:
    """True, wenn an diesem Tag ein aktiver Speicher in der Bilanz stehen muss.

    Maßstab ist ``Investition.ist_aktiv_an(tag)`` und **nicht** das ``aktiv``-Flag
    allein: Ein Speicher, der erst nächsten Monat angeschafft oder letztes Jahr
    stillgelegt wurde, darf für den betrachteten Tag keinen Zähler einfordern —
    sonst entsteht genau die Klasse, die N-64 und N-313 behoben haben (eine
    Investitions-Abfrage ohne Zeitfilter).

    `investitionen` ist bewusst eine beliebige Iterable von Investitions-Objekten
    (auch die `.values()` der `investitionen_by_id`-Map der Aufrufer); geprüft
    wird duck-typed über `typ` und `ist_aktiv_an`.
    """
    for inv in investitionen:
        typ = getattr(inv, "typ", None)
        # `typ` ist im Modell eine String-Spalte, in Fixtures gelegentlich das
        # Enum — beide Formen auf denselben Wert bringen, statt eine davon
        # stillschweigend nicht zu treffen.
        if getattr(typ, "value", typ) != "speicher":
            continue
        pruef = getattr(inv, "ist_aktiv_an", None)
        if pruef is None or pruef(tag):
            return True
    return False


def berechne_batterie_netto_kwh(
    *,
    ladung_kwh: Optional[float],
    entladung_kwh: Optional[float],
    erwartet: bool,
) -> Optional[float]:
    """Netto-Ladung der Stunde (positiv = Ladung) — ``None``, wenn unbekannt.

    Konvention wie bisher: ``Ladung − Entladung``.

    * ``erwartet=True`` (die Anlage führt an diesem Tag einen aktiven Speicher):
      **beide** Richtungen müssen vorliegen. Fehlt eine, ist die Netto-Ladung
      unbekannt — nicht 0. Das ist der Kern von N-346.
    * ``erwartet=False``: unverändertes Verhalten. Eine Anlage ohne Speicher hat
      keine Batterie-Kategorien, und ein bereits stillgelegter Speicher, dessen
      Zähler noch liefert, soll weiterhin abgezogen werden dürfen.
    """
    if erwartet:
        if ladung_kwh is None or entladung_kwh is None:
            return None
        return ladung_kwh - entladung_kwh
    if ladung_kwh is None and entladung_kwh is None:
        return None
    return (ladung_kwh or 0.0) - (entladung_kwh or 0.0)


def stunden_verbrauch_kwh(
    *,
    pv_kwh: Optional[float],
    netzbezug_kwh: Optional[float],
    einspeisung_kwh: Optional[float],
    batterie_netto_kwh: Optional[float],
    batterie_erwartet: bool,
) -> Optional[float]:
    """Bilanzieller Hausverbrauch einer Stunde — ``None``, wenn nicht bildbar.

    ``verbrauch = pv + netzbezug − einspeisung − batterie_netto``, auf 0 geklemmt
    (eine negative Bilanz ist ein Zähler-Artefakt, kein negativer Verbrauch).

    Nicht bildbar ist sie, wenn eine der vier Größen fehlt, die sie braucht:
    PV, Netzbezug und Einspeisung immer — die Batterie genau dann, wenn an
    diesem Tag ein aktiver Speicher geführt wird (``batterie_erwartet``).

    ⚠ Der Klemmschritt ``max(0.0, …)`` steht **nach** dem Wächter und nicht
    statt seiner: Er macht aus einer leicht negativen Bilanz eine 0, aber er
    kann eine fehlende Größe nicht ersetzen. Vor N-346 war er die letzte Stufe,
    an der die zu niedrige Zahl noch plausibel aussah.
    """
    if pv_kwh is None or einspeisung_kwh is None or netzbezug_kwh is None:
        return None
    if batterie_erwartet and batterie_netto_kwh is None:
        return None
    v = pv_kwh + netzbezug_kwh - einspeisung_kwh - (batterie_netto_kwh or 0.0)
    return max(0.0, v)
