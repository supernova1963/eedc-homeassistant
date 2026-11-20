"""Rand-Stände aus den MQTT-Rohständen (Sensorwechsel mit Grund, U3 Lauf b, Rechenweg G5/G7, Regel «Rohstand ist die Quelle»).

**Regel.** Bei MQTT ist der Rohstand (``mqtt_energy_snapshots``, alle fünf Minuten der zuletzt gemeldete Stand) die Quelle; eedc
führt die Summe. An einem Eintrag «Zähler getauscht» bzw. an einem Wechsel «bleiben» zwischen zwei MQTT-Quellen endet eine
Periode mit dem **letzten Rohstand vor** dem Zeitpunkt (``stand_alt_ende``) und beginnt mit dem **ersten ab** ihm
(``stand_neu_null``) — beide wörtlich, epochengenau, nie interpoliert. Die Stunde, in der der Wechsel liegt (Naht-Stunde), zählt
dann genau die Menge, die in den Rohständen steht: den Teil des alten Zählers bis zu seinem letzten Stand und den Teil des neuen ab
seinem ersten (``menge_der_naht``); zwischen den Ständen der zwei Zähler entsteht keine Differenz. Die Reihe hebt ihre Stände ab
dem Wechsel um ``stand_alt_ende − stand_neu_null`` (``zaehler_naht.rand_versatz``), der Kanal verschiebt seine Quellzeile so, dass
die Naht-Stunde diese Menge trägt (``verschiebung_der_naht``) — Kanal und Reihe nennen für den Tag dieselbe Zahl.

**Wo der Zähler springt** (``sprung_der_stunde``): ein Eintrag «Zähler getauscht» sagt, dass der Stand an diesem Zeitpunkt die
Höhe wechselt. Gesucht wird im Paar aufeinanderfolgender Rohstände, dessen späterer Stand in der Stunde des Zeitpunkts liegt, der
Schritt mit dem größten Betrag, der ein **Höhenwechsel** ist (``hoehenwechsel``): ein Rückgang (ein Zähler fällt nie) oder ein
Sprung über ``SPRUNG_FAKTOR`` × den größten Schritt der Rohstände des Tages davor (mindestens ``SPRUNG_MIN``). Gibt es keinen,
ist zu dieser Zeit kein Sprung zu sehen — die Vorschau lehnt den Zeitpunkt ab, statt still nichts zu bewirken.

**Brücke über eine verworfene Zeit ohne Höhenwechsel** (G7 «verwerfen», ``bruecke``): dieselbe Quelle davor und danach, kein
Zählertausch dazwischen — dann ist ``Stand(danach) − Stand(davor)`` die Menge der Zeit (wie an jeder Zählerlücke, Grundsatz
«Zählerlücken wie HA»), und sie steht in der ersten Stunde danach.

Rein (ADR-001): Zeitpunkte und Stände rein, Zahlen raus. Das Laden steht in ``services/zuordnung_wechsel/rohstand.py``.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional, Sequence

#: Ein Rückgang zwischen zwei Rohständen ist ein Höhenwechsel ab diesem Betrag (wie der Arm «Rückgang» von G4).
RUECKGANG_MIN = 0.01
#: Ein Sprung ist ein Höhenwechsel, wenn er größer ist als dieses Vielfache des größten Schritts des Tages davor …
SPRUNG_FAKTOR = 10.0
#: … und größer als diese Menge (kWh) — eine fast stehende Reihe macht sonst jeden Verbrauch zum Sprung.
SPRUNG_MIN = 1.0
#: So weit vor dem Schritt liest ``sprung_der_stunde`` die Schritte für den Vergleich.
BEZUG = timedelta(hours=24)

Roh = tuple[datetime, float]


def hoehenwechsel(delta: float, groesster_schritt_davor: float) -> bool:
    """Ist ein Schritt zwischen zwei Rohständen ein Höhenwechsel (kein Verbrauch)? Ein Rückgang unter −``RUECKGANG_MIN`` immer;
    ein Sprung, wenn er ``SPRUNG_FAKTOR`` × den größten Schritt davor und ``SPRUNG_MIN`` übersteigt."""
    if delta < -RUECKGANG_MIN:
        return True
    return delta > max(SPRUNG_FAKTOR * max(groesster_schritt_davor, 0.0), SPRUNG_MIN)


def sprung_der_stunde(rohstaende: Sequence[Roh], stunde: datetime) -> Optional[tuple[Roh, Roh]]:
    """Das Paar ``(letzter Rohstand vor dem Höhenwechsel, erster ab ihm)``, dessen späterer Stand in ``[stunde, stunde + 1 h)``
    liegt und dessen Schritt ein Höhenwechsel ist — der mit dem größten Betrag; ``None``, wenn es keinen gibt.
    ``rohstaende`` aufsteigend, mindestens ab ``BEZUG`` vor der Stunde."""
    beste: Optional[tuple[Roh, Roh]] = None
    for i in range(1, len(rohstaende)):
        a, b = rohstaende[i - 1], rohstaende[i]
        if not stunde <= b[0] < stunde + timedelta(hours=1):
            continue
        davor = [y[1] - x[1] for x, y in zip(rohstaende[:i - 1], rohstaende[1:i]) if y[0] >= a[0] - BEZUG and y[1] > x[1]]
        if hoehenwechsel(b[1] - a[1], max(davor, default=0.0)) and (
                beste is None or abs(b[1] - a[1]) > abs(beste[1][1] - beste[0][1])):
            beste = (a, b)
    return beste


def menge_der_naht(stand_alt_ende: float, stand_davor: float, stand_naht: float, stand_neu_null: float) -> float:
    """Die Menge der Naht-Stunde aus den Rohständen: der alte Zähler vom Stand der Stunde davor (``stand_davor``) bis zu seinem
    letzten Stand (``stand_alt_ende``), der neue von seinem ersten (``stand_neu_null``) bis zum Stand am Ende der Stunde."""
    return (stand_alt_ende - stand_davor) + (stand_naht - stand_neu_null)


def verschiebung_der_naht(menge: float, wert_naht: float, wert_davor: float) -> float:
    """Wie weit eine Quellzeile ab der Naht-Stunde den Kanal verschiebt, damit die Stunde ``menge`` trägt: ``menge − (wert_naht −
    wert_davor)`` (Kanal-Rohwerte der Naht-Zeile und der Zeile davor)."""
    return menge - (wert_naht - wert_davor)


def bruecke(kanalwert_davor: float, stand_davor: float, stand_danach: float, wert_danach: float) -> float:
    """Der Versatz der ersten Quellzeile nach einer verworfenen Zeit ohne Höhenwechsel: die erste Zeile danach (Rohwert
    ``wert_danach``) trägt den Kanalwert davor plus die Menge der Zeit ``stand_danach − stand_davor``."""
    return kanalwert_davor + (stand_danach - stand_davor) - wert_danach


__all__ = ["BEZUG", "RUECKGANG_MIN", "SPRUNG_FAKTOR", "SPRUNG_MIN", "bruecke", "hoehenwechsel", "menge_der_naht",
           "sprung_der_stunde", "verschiebung_der_naht"]
