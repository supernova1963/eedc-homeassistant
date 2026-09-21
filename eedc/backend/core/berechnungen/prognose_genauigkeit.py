"""Prognose-Genauigkeit — der relative Tagesfehler und sein Mittel (MAE/MBE).

**Warum das seit dem 21.09.2026 im Layer steht.** Die Rechnung lebte bis dahin
ausschließlich als lokale Closure in
``api/routes/prognosen.py::get_prognosen_genauigkeit`` — einer 170-Zeilen-Route,
die daneben Wettersymbole, Ausreißerzählung und drei Quellen aufbereitet. Die
Abweichungs-Ampel des HA-Exports (S3/P6) braucht dieselbe Zahl als **Schwelle**.
Sie dort nachzubauen hieße: die Auswertung *Prognose-Genauigkeit* und der Sensor
*Prognose-Abweichung auffällig* nennen denselben mittleren Fehler mit zwei
Formeln. Das ist die Klasse, gegen die ADR-001 geschrieben ist.

**Was hier NICHT steht:** das Laden der Tage. Welche Tage gelten, welche Quelle
gemeint ist und ob Ausreißer ausgeschlossen werden, entscheidet der Aufrufer —
der Layer rechnet.
"""

from __future__ import annotations

from typing import Optional, Sequence

#: Unterhalb dieser Tagesmenge sagt ein relativer Fehler nichts mehr aus: bei
#: 0,2 kWh IST wird aus 0,3 kWh Prognose ein Fehler von 150 %, ohne dass an der
#: Prognose etwas falsch wäre. Übernommen aus der Route (``ist_kwh > 0.5``,
#: dort seit der Einführung des Trackings) — hier benannt statt eingestreut.
IST_MINDESTMENGE_KWH: float = 0.5


def relativer_tagesfehler_prozent(
    prognose_kwh: Optional[float], ist_kwh: Optional[float]
) -> Optional[float]:
    """``(Prognose − IST) ÷ IST × 100`` — **vorzeichenbehaftet**.

    Positiv = zu viel vorhergesagt. ``None``, wenn der Tag keine brauchbare
    Grundlage hat: kein IST, ein IST unter :data:`IST_MINDESTMENGE_KWH`, oder
    keine Prognose > 0. **Kein 0** — ein Tag ohne Messung ist kein Tag mit
    perfekter Prognose (ADR-002/P4).

    ⚠ **Das Vorzeichen bleibt erhalten, und zwar bis zum Schluss.** Erst
    :func:`mae_prozent` nimmt den Betrag; :func:`mbe_prozent` braucht das
    Vorzeichen. Wer hier schon absolut rechnete, könnte den systematischen
    Versatz (rechnet eedc grundsätzlich zu hoch?) nicht mehr von der Streuung
    trennen — genau die Unterscheidung, für die #151 die beiden Zahlen
    nebeneinander gestellt hat.
    """
    if ist_kwh is None or ist_kwh <= IST_MINDESTMENGE_KWH:
        return None
    if not prognose_kwh or prognose_kwh <= 0:
        return None
    return (float(prognose_kwh) - float(ist_kwh)) / float(ist_kwh) * 100


def mae_prozent(fehler: Sequence[float]) -> Optional[float]:
    """Mittlerer **absoluter** relativer Fehler, auf eine Nachkommastelle.

    ``None`` bei leerer Reihe — eine 0 hieße „perfekt getroffen".
    """
    werte = list(fehler)
    return round(sum(abs(x) for x in werte) / len(werte), 1) if werte else None


def mbe_prozent(fehler: Sequence[float]) -> Optional[float]:
    """Mittlerer **vorzeichenbehafteter** Fehler (Bias), auf eine Nachkommastelle."""
    werte = list(fehler)
    return round(sum(werte) / len(werte), 1) if werte else None
