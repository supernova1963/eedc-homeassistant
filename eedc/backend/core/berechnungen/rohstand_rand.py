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
Höhe wechselt. Gesucht werden in den Paaren aufeinanderfolgender Rohstände, deren späterer Stand in der Stunde des Zeitpunkts
liegt, die Schritte, die ein **Höhenwechsel** sind (``hoehenwechsel``): ein Rückgang (ein Zähler fällt nie) oder ein Schritt nach
oben, dessen **Leistung** über ``SPRUNG_FAKTOR`` × der größten Leistung der Rohstände der ``BEZUG`` davor **und** über der Grenze
«mehr, als eine Anlage in einer Stunde leisten kann» liegt (``grenze_kw``, Befund «Zählerstand springt» B2 (b): max(100,
1,5 × kWp) kWh je Stunde, als kW; ohne Grenze — andere Einheit — mindestens ``SPRUNG_MIN``). Gewöhnliche Ladungen nach Stillstand
sind damit keine Höhenwechsel (U3-K, B7: am HEAD galt nach 24 h Stillstand jeder Schritt über 1 kWh als Sprung).

**Die Leistung eines Schritts** (U3-K2, P-2, Bauplan Nr. 161) ist der Schritt ÷ die Zeit **seit der Stand zuletzt anders war**
(``seit_dem_letzten_anderen``: vom ersten Rohstand mit dem Wert vor dem Schritt bis zum Rohstand danach) — nicht ÷ die fünf
Minuten zwischen den zwei Rohständen. Schweigt ein Publisher, wiederholt der Scheduler seinen letzten Stand; kommt danach der wahre
Stand, ist der Schritt die Menge der ganzen stillen Zeit (Nachholmenge: 15 kWh nach 30 h Stille sind 0,5 kW, nicht 180 kW) und kein
Höhenwechsel. Ein gewöhnlicher Schritt (der Stand davor hat sich im Schritt davor geändert) behält die fünf Minuten. Die Zeit reicht
höchstens bis zum ersten gelesenen Rohstand (``BEZUG`` vor der Stunde) zurück. Ein echter Tausch nach einer Pause bleibt ein
Höhenwechsel, wenn sein Schritt über der Grenze dieser Zeit liegt (+2 000 kWh nach 2 h: 1 000 kW).
**Benannte Grenze:** ein kleiner Versatz nach oben — unter dem, was die Anlage seit dem letzten anderen Stand leisten kann (bei der
Grenze 100 in fünf Minuten etwa 8 kWh, nach einer Stunde Stillstand 100 kWh) — ist nach dieser Regel kein Höhenwechsel.

**Der Befund entscheidet mit** (U3-K2, P-3): nennt der Daten-Checker «Zählerstand springt (MQTT)» die Stunde
(``zaehlerstand_sprung.finde_standspruenge`` am Kanal), sieht aber die Leistung keinen Höhenwechsel (ein reifer Zähler mit
kleinem Tageszuwachs, ein Schritt unter der Grenze), ist der **größte Schritt nach oben** der Stunde der Höhenwechsel
(``sprung_der_stunde(…, benannt=True)``) — eine Entscheidung, zwei Verbraucher: kein Befund, dessen Knopf «Zähler getauscht»
ablehnt. Nennt kein Befund die Stunde, bleibt es bei der Leistung (Ladung nach Standby, Nachholmenge).

**Die Spanne der Stunde** (U3-K, B1): trägt die Stunde mehrere Höhenwechsel (ein Gerät meldet fünf Minuten 0 und dann wieder
seinen Stand; ein anderes Gerät sendet zehn Minuten seinen Stand; ein neues Gerät meldet erst 0, dann 300), sind die Rand-Stände
der **letzte Stand vor dem ersten** und der **erste Stand nach dem letzten** Höhenwechsel. Die Stände dazwischen gehören keinem
der zwei Zähler und zählen nicht. Ein einzelnes Paar am größten Schritt (U3 b) nahm in diesen Lagen einen fremden Stand als
Rand und schrieb eine negative Stunde (−5 016,708).

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
#: Ein Schritt nach oben ist ein Höhenwechsel, wenn seine Leistung größer ist als dieses Vielfache der größten Leistung davor …
SPRUNG_FAKTOR = 10.0
#: … und, ohne Grenze der Anlage (andere Einheit als kWh), größer als diese Menge — eine fast stehende Reihe macht sonst jeden
#: Verbrauch zum Sprung.
SPRUNG_MIN = 1.0
#: So weit vor dem Schritt liest ``sprung_der_stunde`` die Schritte für den Vergleich.
BEZUG = timedelta(hours=24)
_H = 3600.0

Roh = tuple[datetime, float]


def leistung(delta: float, sekunden: float) -> float:
    """Die Leistung eines Schritts (Menge je Stunde): ``delta`` ÷ ``sekunden``; ohne Zeit unendlich."""
    return delta / (sekunden / _H) if sekunden > 0 else float("inf")


def hoehenwechsel(delta: float, sekunden: float, groesste_leistung_davor: float, grenze_kw: Optional[float]) -> bool:
    """Ist ein Schritt zwischen zwei Rohständen ein Höhenwechsel (kein Verbrauch)? Ein Rückgang unter −``RUECKGANG_MIN`` immer;
    ein Schritt nach oben, wenn seine Leistung ``SPRUNG_FAKTOR`` × die größte Leistung davor und die Grenze der Anlage
    (``grenze_kw``) übersteigt; ohne Grenze muss der Schritt dazu größer als ``SPRUNG_MIN`` sein."""
    if delta < -RUECKGANG_MIN:
        return True
    if delta <= 0:
        return False
    ueber_davor = leistung(delta, sekunden) > SPRUNG_FAKTOR * max(groesste_leistung_davor, 0.0)
    if grenze_kw is None:
        return ueber_davor and delta > SPRUNG_MIN
    return ueber_davor and leistung(delta, sekunden) > grenze_kw


def _groesste_leistung(rohstaende: Sequence[Roh], i: int) -> float:
    """Die größte Leistung der Schritte nach oben, die vor dem Paar ``(i − 1, i)`` enden und in die ``BEZUG`` davor fallen."""
    a = rohstaende[i - 1]
    return max((leistung(y[1] - x[1], (y[0] - x[0]).total_seconds())
                for x, y in zip(rohstaende[:i - 1], rohstaende[1:i])
                if y[0] >= a[0] - BEZUG and y[1] > x[1] and y[0] > x[0]), default=0.0)


def seit_dem_letzten_anderen(rohstaende: Sequence[Roh], i: int) -> float:
    """P-2: die Zeit (Sekunden) des Schritts ``(i − 1, i)`` — vom ersten Rohstand mit dem Wert von ``i − 1`` (seit der Stand
    zuletzt anders war; ohne Wiederholung ist das ``i − 1`` selbst) bis ``i``."""
    j = i - 1
    while j > 0 and rohstaende[j - 1][1] == rohstaende[i - 1][1]:
        j -= 1
    return (rohstaende[i][0] - rohstaende[j][0]).total_seconds()


def hoehenwechsel_der_stunde(rohstaende: Sequence[Roh], stunde: datetime, grenze_kw: Optional[float]) -> list[int]:
    """Die Indizes ``i`` der Paare ``(i − 1, i)``, deren späterer Stand in ``[stunde, stunde + 1 h)`` liegt und deren Schritt ein
    Höhenwechsel ist — in Zeitfolge. Die Leistung des Schritts gilt über ``seit_dem_letzten_anderen`` (P-2)."""
    out = []
    for i in range(1, len(rohstaende)):
        a, b = rohstaende[i - 1], rohstaende[i]
        if stunde <= b[0] < stunde + timedelta(hours=1) and hoehenwechsel(
                b[1] - a[1], seit_dem_letzten_anderen(rohstaende, i), _groesste_leistung(rohstaende, i), grenze_kw):
            out.append(i)
    return out


def groesster_schritt_der_stunde(rohstaende: Sequence[Roh], stunde: datetime) -> Optional[int]:
    """P-3: der Index ``i`` des größten Schritts nach oben ``(i − 1, i)`` mit späterem Stand in ``[stunde, stunde + 1 h)``
    (bei gleichen Schritten der erste); ``None``, wenn die Stunde keinen Schritt nach oben trägt."""
    beste: Optional[int] = None
    for i in range(1, len(rohstaende)):
        d = rohstaende[i][1] - rohstaende[i - 1][1]
        if stunde <= rohstaende[i][0] < stunde + timedelta(hours=1) and d > 0 and (
                beste is None or d > rohstaende[beste][1] - rohstaende[beste - 1][1]):
            beste = i
    return beste


def sprung_der_stunde(rohstaende: Sequence[Roh], stunde: datetime,
                      grenze_kw: Optional[float] = None, *, benannt: bool = False) -> Optional[tuple[Roh, Roh]]:
    """Die Spanne der Höhenwechsel in ``[stunde, stunde + 1 h)``: ``(letzter Rohstand vor dem ersten, erster Rohstand nach dem
    letzten)``; ``None``, wenn es keinen gibt. ``rohstaende`` aufsteigend, mindestens ab ``BEZUG`` vor der Stunde. ``benannt``
    (P-3): der Befund «Zählerstand springt (MQTT)» nennt die Stunde — ohne Höhenwechsel nach der Leistung ist dann der größte
    Schritt nach oben der Stunde der Höhenwechsel."""
    idx = hoehenwechsel_der_stunde(rohstaende, stunde, grenze_kw)
    if not idx and benannt:
        g = groesster_schritt_der_stunde(rohstaende, stunde)
        idx = [] if g is None else [g]
    if not idx:
        return None
    return rohstaende[idx[0] - 1], rohstaende[idx[-1]]


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


__all__ = ["BEZUG", "RUECKGANG_MIN", "SPRUNG_FAKTOR", "SPRUNG_MIN", "bruecke", "groesster_schritt_der_stunde", "hoehenwechsel",
           "hoehenwechsel_der_stunde", "leistung", "menge_der_naht", "seit_dem_letzten_anderen", "sprung_der_stunde",
           "verschiebung_der_naht"]
