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
oben, dessen **Leistung** über ``SPRUNG_FAKTOR`` × der größten Leistung der gewöhnlichen Schritte der ``BEZUG`` davor **und** über der Grenze
«mehr, als eine Anlage in einer Stunde leisten kann» liegt (``grenze_kw``, Befund «Zählerstand springt» B2 (b): max(100,
1,5 × kWp) kWh je Stunde, als kW; ohne Grenze — andere Einheit — mindestens ``SPRUNG_MIN``). Gewöhnliche Ladungen nach Stillstand
sind damit keine Höhenwechsel (U3-K, B7: am HEAD galt nach 24 h Stillstand jeder Schritt über 1 kWh als Sprung). **Gewöhnlich**
heißt (U3-K3, K2-B1): ein Schritt, der selbst kein Höhenwechsel ist — die Rückkehr eines ersten kurzen Null- oder Fremdstands
hebt den Vergleich nicht, ein zweiter binnen 24 Stunden bleibt ein Höhenwechsel (``_hoehenwechsel_alle``, in Zeitfolge; mit und
ohne Grenze dieselbe Regel).

**Die Leistung eines Schritts** (U3-K2, P-2, Bauplan Nr. 161) ist der Schritt ÷ die Zeit **seit der Stand zuletzt anders war**
(``seit_dem_letzten_anderen``: vom ersten Rohstand mit dem Wert vor dem Schritt bis zum Rohstand danach) — nicht ÷ die fünf
Minuten zwischen den zwei Rohständen. Schweigt ein Publisher, wiederholt der Scheduler seinen letzten Stand; kommt danach der wahre
Stand, ist der Schritt die Menge der ganzen stillen Zeit (Nachholmenge: 15 kWh nach 30 h Stille sind 0,5 kW, nicht 180 kW) und kein
Höhenwechsel. Ein gewöhnlicher Schritt (der Stand davor hat sich im Schritt davor geändert) behält die fünf Minuten. Die Zeit reicht
höchstens bis zum ersten gelesenen Rohstand (``BEZUG`` vor der Stunde) zurück. Ein echter Tausch nach einer Pause bleibt ein
Höhenwechsel, wenn sein Schritt über der Grenze dieser Zeit liegt (+2 000 kWh nach 2 h: 1 000 kW).

**Die Erkennung zeigt, sie entscheidet nicht** (Bauplan Nr. 166, Entscheid Gernot 20.11.2026: «Bei MQTT entscheidet allein der
Benutzer, ob neu angefangen wird»). Zwei Regeln für die Rand-Stände:

1. **R1** — wechselt der Stand in der Stunde eindeutig die Höhe (Höhenwechsel nach Leistung, oben), liegt der Eintrag dort: die
   Spanne der Stunde (``sprung_der_stunde``, unten). Gilt für alle Wege (Dialog «Zähler getauscht», «bleiben», Stundenlauf).
2. **R2** (Dialog «Zähler getauscht», sonst): der letzte Rohstand vor der gewählten Zeit und der **nächste Rohstand danach mit
   anderem Wert** (``rohstand.naechster_anderer_um``, ohne Zeitgrenze) — ein still wiederholter Stand ist kein Stand des neuen
   Zählers; gibt es noch keinen, trägt der Dialog nicht ein (Bauplan Nr. 168). «Bleiben» nimmt sonst
   die zwei Stände um den Zeitpunkt (``rohstand.rand_um``).

**«Hebt sich ab»** (``abgehoben``; nur für den Hinweis des Dialogs, den Hinweis von «bleiben» und den Befund «Zählerstand
springt (MQTT)», nie als Sperre): ein Schritt nach oben trägt mindestens ``EINZELSCHRITT_ANTEIL`` des Zuwachses nach oben seiner
Stunde **und** seine Menge liegt über ``SPRUNG_FAKTOR`` × der größten Menge der gewöhnlichen Schritte nach oben der ``BEZUG``
davor (``hebt_sich_ab``; ohne Schritt davor: ja). Der gewöhnliche Stundenschritt eines selten sendenden Publishers, das +1 eines
ganzzahligen Zählers heben sich nicht ab; ob ein Schritt, der sich abhebt, ein Tausch ist oder gezählte Menge, erkennt eedc nicht.

**Die Spanne der Stunde** (U3-K, B1): trägt die Stunde mehrere Höhenwechsel (ein Gerät meldet fünf Minuten 0 und dann wieder
seinen Stand; ein anderes Gerät sendet zehn Minuten seinen Stand; ein neues Gerät meldet erst 0, dann 300), sind die Rand-Stände
der **letzte Stand vor dem ersten** und der **erste Stand nach dem letzten** Höhenwechsel. Die Stände dazwischen gehören keinem
der zwei Zähler und zählen nicht. Ein einzelnes Paar am größten Schritt (U3 b) nahm in diesen Lagen einen fremden Stand als
Rand und schrieb eine negative Stunde (−5 016,708).

Rein (ADR-001): Zeitpunkte und Stände rein, Zahlen raus. Das Laden steht in ``services/zuordnung_wechsel/rohstand.py``.
"""

from __future__ import annotations

from collections import deque
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
#: Bauplan Nr. 163/166: ein Schritt nach oben hebt sich nur ab (``abgehoben``), wenn er mindestens diesen Anteil des Zuwachses
#: nach oben seiner Stunde trägt.
EINZELSCHRITT_ANTEIL = 0.9
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


def seit_dem_letzten_anderen(rohstaende: Sequence[Roh], i: int) -> float:
    """P-2: die Zeit (Sekunden) des Schritts ``(i − 1, i)`` — vom ersten Rohstand mit dem Wert von ``i − 1`` (seit der Stand
    zuletzt anders war; ohne Wiederholung ist das ``i − 1`` selbst) bis ``i``."""
    return (rohstaende[i][0] - rohstaende[_erster_gleicher(rohstaende, i)][0]).total_seconds()


def _erster_gleicher(rohstaende: Sequence[Roh], i: int) -> int:
    j = i - 1
    while j > 0 and rohstaende[j - 1][1] == rohstaende[i - 1][1]:
        j -= 1
    return j


def _hoehenwechsel_alle(rohstaende: Sequence[Roh], grenze_kw: Optional[float]) -> list[bool]:
    """Je Paar ``(i − 1, i)``, in Zeitfolge: ist der Schritt ein Höhenwechsel? Die Vergleichsleistung eines Schritts ist die
    größte Leistung der Schritte nach oben, die vor ihm enden und in die ``BEZUG`` davor fallen — **ohne die Schritte, die selbst
    Höhenwechsel sind** (U3-K3, K2-B1: die Rückkehr eines ersten kurzen Null- oder Fremdstands stünde sonst 24 Stunden im
    Vergleich, und der zweite binnen 24 Stunden wäre keiner mehr). Dieselbe Regel mit und ohne Grenze der Anlage."""
    out = [False] * len(rohstaende)
    gewoehnlich: deque[tuple[datetime, float]] = deque()      # (Ende, Leistung), Leistung fallend — das Maximum vorn
    for i in range(1, len(rohstaende)):
        a, b = rohstaende[i - 1], rohstaende[i]
        while gewoehnlich and gewoehnlich[0][0] < a[0] - BEZUG:
            gewoehnlich.popleft()
        out[i] = hoehenwechsel(b[1] - a[1], seit_dem_letzten_anderen(rohstaende, i),
                               gewoehnlich[0][1] if gewoehnlich else 0.0, grenze_kw)
        if not out[i] and b[1] > a[1] and b[0] > a[0]:
            lst = leistung(b[1] - a[1], (b[0] - a[0]).total_seconds())
            while gewoehnlich and gewoehnlich[-1][1] <= lst:
                gewoehnlich.pop()
            gewoehnlich.append((b[0], lst))
    return out


def _in_der_stunde(rohstaende: Sequence[Roh], stunde: datetime) -> range:
    """Die Indizes ``i`` der Paare ``(i − 1, i)``, deren späterer Stand in ``[stunde, stunde + 1 h)`` liegt."""
    ende = stunde + timedelta(hours=1)
    idx = [i for i in range(1, len(rohstaende)) if stunde <= rohstaende[i][0] < ende]
    return range(idx[0], idx[-1] + 1) if idx else range(0)


def hoehenwechsel_der_stunde(rohstaende: Sequence[Roh], stunde: datetime, grenze_kw: Optional[float]) -> list[int]:
    """Die Indizes ``i`` der Paare ``(i − 1, i)``, deren späterer Stand in ``[stunde, stunde + 1 h)`` liegt und deren Schritt ein
    Höhenwechsel ist — in Zeitfolge. Die Leistung des Schritts gilt über ``seit_dem_letzten_anderen`` (P-2), die
    Vergleichsleistung ohne frühere Höhenwechsel (U3-K3)."""
    alle = _hoehenwechsel_alle(rohstaende, grenze_kw)
    return [i for i in _in_der_stunde(rohstaende, stunde) if alle[i]]


def abgehoben(rohstaende: Sequence[Roh], g: int, grenze_kw: Optional[float] = None,
             alle: Optional[Sequence[bool]] = None) -> bool:
    """Hebt sich der Schritt ``(g − 1, g)`` ab (Bauplan Nr. 165/166)? Ein Schritt nach oben, der mindestens
    ``EINZELSCHRITT_ANTEIL`` des Zuwachses nach oben seiner Stunde trägt (die Stunde des Stands ``g``; ein einziger Schritt immer)
    und sich gegen die gewöhnlichen Schritte der ``BEZUG`` davor abhebt (``hebt_sich_ab``). ``alle``: die Höhenwechsel aller
    Paare (``_hoehenwechsel_alle``), wenn schon gerechnet."""
    schritt = rohstaende[g][1] - rohstaende[g - 1][1]
    if schritt <= 0:
        return False
    stunde = rohstaende[g][0].replace(minute=0, second=0, microsecond=0)
    zuwachs = sum(max(0.0, rohstaende[i][1] - rohstaende[i - 1][1]) for i in _in_der_stunde(rohstaende, stunde))
    if schritt < EINZELSCHRITT_ANTEIL * zuwachs:
        return False
    return hebt_sich_ab(rohstaende, g, alle if alle is not None else _hoehenwechsel_alle(rohstaende, grenze_kw))


def abgehobener_schritt_der_stunde(rohstaende: Sequence[Roh], stunde: datetime,
                                   grenze_kw: Optional[float] = None) -> Optional[int]:
    """Der Index ``g`` des Schritts der Stunde, der sich abhebt (``abgehoben``; nur der größte Schritt nach oben kann
    ``EINZELSCHRITT_ANTEIL`` tragen) — für den Befund «Zählerstand springt (MQTT)» und den Hinweis von «bleiben»; sonst
    ``None``."""
    idx = [i for i in _in_der_stunde(rohstaende, stunde) if rohstaende[i][1] > rohstaende[i - 1][1]]
    if not idx:
        return None
    g = max(idx, key=lambda i: (rohstaende[i][1] - rohstaende[i - 1][1], -i))
    return g if abgehoben(rohstaende, g, grenze_kw) else None


def hebt_sich_ab(rohstaende: Sequence[Roh], g: int, alle: Sequence[bool]) -> bool:
    """U3-K4 (K3-B3): hebt sich der Schritt ``(g − 1, g)`` ab? Seine **Menge** liegt über ``SPRUNG_FAKTOR`` × der größten Menge
    der gewöhnlichen Schritte nach oben (kein Höhenwechsel), die vor ihm enden und in die ``BEZUG`` davor fallen — Menge, nicht
    Leistung: ein Tausch nach drei Stunden Stille mit +15 kWh hat nur das Neunfache der gewöhnlichen Leistung, aber das
    Dreihundertfache des gewöhnlichen Schritts; der gewöhnliche Stundenschritt eines stündlich sendenden Publishers, das +1 eines
    ganzzahligen Zählers heben sich nicht ab. Ohne Schritt nach oben in der ``BEZUG`` davor (Stille): ja."""
    a = rohstaende[g - 1]
    groesster = max((rohstaende[j][1] - rohstaende[j - 1][1] for j in range(1, g)
                     if rohstaende[j][0] >= a[0] - BEZUG and not alle[j] and rohstaende[j][1] > rohstaende[j - 1][1]),
                    default=None)
    return groesster is None or rohstaende[g][1] - rohstaende[g - 1][1] > SPRUNG_FAKTOR * groesster


def sprung_der_stunde(rohstaende: Sequence[Roh], stunde: datetime,
                      grenze_kw: Optional[float] = None) -> Optional[tuple[Roh, Roh]]:
    """Die Spanne der Höhenwechsel in ``[stunde, stunde + 1 h)``: ``(letzter Rohstand vor dem ersten, erster Rohstand nach dem
    letzten)``; ``None``, wenn es keinen gibt. ``rohstaende`` aufsteigend, mindestens ab ``BEZUG`` vor der Stunde."""
    idx = hoehenwechsel_der_stunde(rohstaende, stunde, grenze_kw)
    if not idx:
        return None
    return rohstaende[idx[0] - 1], rohstaende[idx[-1]]


def menge_des_schritts(paar: tuple[Roh, Roh]) -> float:
    """Was ein eingetragener Tausch an ``paar`` nicht zählt: Stand danach − Stand davor."""
    return paar[1][1] - paar[0][1]


def menge_der_naht(stand_alt_ende: float, stand_davor: float, stand_naht: float, stand_neu_null: float) -> float:
    """Die Menge der Naht-Stunde aus den Rohständen: der alte Zähler vom Stand der Stunde davor (``stand_davor``) bis zu seinem
    letzten Stand (``stand_alt_ende``), der neue von seinem ersten (``stand_neu_null``) bis zum Stand am Ende der Stunde."""
    return (stand_alt_ende - stand_davor) + (stand_naht - stand_neu_null)


def verschiebung_der_naht(menge: float, wert_naht: float, wert_davor: float) -> float:
    """Wie weit eine Quellzeile ab der Naht-Stunde den Kanal verschiebt, damit die Stunde ``menge`` trägt: ``menge − (wert_naht −
    wert_davor)`` (Kanal-Rohwerte der Naht-Zeile und der Zeile davor)."""
    return menge - (wert_naht - wert_davor)


__all__ = ["BEZUG", "EINZELSCHRITT_ANTEIL", "RUECKGANG_MIN", "SPRUNG_FAKTOR", "SPRUNG_MIN", "abgehoben",
           "abgehobener_schritt_der_stunde", "hebt_sich_ab", "hoehenwechsel", "hoehenwechsel_der_stunde", "leistung",
           "menge_der_naht", "menge_des_schritts", "seit_dem_letzten_anderen", "sprung_der_stunde",
           "verschiebung_der_naht"]
