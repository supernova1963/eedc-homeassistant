"""Zählerstand springt — die Erkennung hinter dem Daten-Checker-Befund ``ha_zaehlerstand_springt`` (Sensorwechsel mit Grund,
U2 Lauf c, Rechenweg F12; Messfrage M4).

**Warum es das gibt.** Wird an einem Zähler das Gerät getauscht und Home Assistant führt **dieselbe Entität** weiter, bucht HA
den Tausch als Menge (Leitlinie Gernot 19.11.2026, Bauplan Nr. 132 (b)): springt der Stand nach oben (der neue Zähler zeigt
mehr als der alte), zählt die Stunde den Sprung; beginnt der neue Zähler nicht bei 0, hält HA das für einen neuen Zyklus und
zählt den ganzen neuen Stand. eedc übernimmt HAs Werte wie das Energie-Dashboard und berichtigt nichts (Grundregel
«Quellentreue»); der Befund nennt die Stunde und den Weg in Home Assistant.

**Das Maß** je Zeilenpaar (r0, r1) **innerhalb eines Quell-Abschnitts** (dieselbe Statistik, keine Wechselstelle):

    mass = z / (größter Tageszuwachs im Bezugsfenster × Tage seit dem letzten Zuwachs, mindestens 1)

* ``z`` = der Zuwachs, den eedc für die Stunde zählt (Mengen-Zähler: Δ ``sum``; Stand-Zähler: Δ ``state``).
* Tageszuwachs = Σ der positiven ``z`` je lokalem Kalendertag; Bezugsfenster = die ``BEZUG_TAGE`` Tage vor dem Tag der Stunde
  (derselbe Abschnitt). Hat das Fenster weniger als ``BEZUG_MIN_TAGE`` Tage mit Zuwachs, ist der Zähler **jung**: kein Maß,
  kein Befund (ein neuer Zähler kennt sein eigenes Maß noch nicht).
* Tage seit dem letzten Zuwachs = Abstand zur letzten Zeile davor mit ``z > 0`` in Tagen. Eine Nachholstunde nach einer Lücke
  und ein großer Verbrauch nach langer Ruhe (Wallbox nach Wochen, Wärmepumpe im ersten kalten Monat) teilen sich so durch
  ihre Ruhezeit und bleiben bei höchstens etwa 1.

**Die zwei Arme:**

* **Neubeginn nicht bei 0** (``NEUBEGINN``): der Stand fällt unter ``NEUBEGINN_ANTEIL`` des vorigen (der vorige mindestens
  ``MIN_STAND``) und das Maß überschreitet ``SCHWELLE_NEUBEGINN``. Ein Fall gewöhnlichen Verbrauchs hat diese Form nicht: ein
  Zähler, der täglich oder monatlich bei 0 neu beginnt, zählt in der Stunde des Neubeginns nur den Verbrauch dieser Stunde.
  An einem Stand-Zähler ist ``z`` hier negativ — dieser Arm trifft ihn nie (einen gefallenen Stand nennt dort
  ``zaehlerstand_reihe_bruch``).
* **Sprung nach oben** (``SPRUNG``): Δ ``sum`` = Δ ``state`` (bis ``GLEICH_ABS`` + ``GLEICH_ANTEIL`` · |Δ ``sum``|) und das Maß
  überschreitet ``SCHWELLE_SPRUNG``. Diese Form hat auch jeder gewöhnliche Verbrauch — hier trennt allein das Maß, deshalb die
  höhere Schwelle.

**Dritter Arm «Rückgang»** (``RUECKGANG``, Sensorwechsel U3 Lauf b, Rechenweg G4; nur mit ``rueckgang=True``, den der
Erzeuger für MQTT ``mqtt_standsprung.py`` setzt): der Zuwachs der Stunde liegt unter −``RUECKGANG_SCHWELLE``. Das geschieht im
Kanal «Eigene Summe» nur, wenn ein Stand um weniger als 10 % fällt (HAs Regel zählt einen tieferen Fall als Neubeginn) — etwa
ein neuer Zähler, der etwas unter dem alten beginnt. Gewöhnlicher Betrieb hat diese Form nicht; der Arm braucht kein Maß und
gilt auch an einem jungen Zähler. Im HA-Spiegel nennt einen fallenden Zähler ``ha_zaehler_rueckgang`` (dort bleibt der Arm aus).

**Sensorwechsel U3-K (Nachmessung B2, Bauplan Nr. 158): wann der Arm «Sprung» melden darf.** Ein gewöhnlicher Verbrauch
hat dieselbe Form wie ein Sprung; das Maß allein trennt sie nur, wenn der Bezug den gewöhnlichen Betrieb kennt. Eine junge
Statistik oder ein neuer Abschnitt in einer ruhigen Jahreszeit kennt oft nur Standby (Wallbox vor dem ersten Auto, Klima im
Winter, Wärmepumpe im Sommer, PV unter Schnee) — dort erreichte die erste gewöhnliche Stunde Maße bis 92. Ein Fehlalarm, dessen
Handgriff richtige Quellwerte ändern lässt, wiegt schwerer als ein nicht gemeldeter mittlerer Sprung (Grundregel
«Quellentreue»). Der Arm meldet deshalb nur, wenn das Maß ``SCHWELLE_SPRUNG`` überschreitet **und**

* (a) der Bezug **reif** ist (``reif``): der Abschnitt reicht ``BEZUG_TAGE`` zurück, das Fenster hat mindestens ``BEZUG_MIN_TAGE``
  Tage mit Zuwachs, und sein größter Tag zählt mindestens ``REIF_MIN_TAG`` — oder
* (b) die Menge der Stunde über dem liegt, was eine Anlage in einer Stunde leisten kann (``grenze``; nur kWh-Felder, der
  Erzeuger gibt ``grenze_unmoeglich(schwelle_pv_einspeisung_stunde_kwh(kWp))`` = max(``MENGE_UNMOEGLICH_MIN``, 1,5 × kWp)).
  Trägt eine Zeile nach einer Zählerlücke ``n`` Stunden, gilt ``n`` × die Grenze (``grenze_der_zeile``, wie die Spanne in
  ``schwelle_pv_einspeisung_stunde_kwh``; gemessen: Produktiv-Kopie, PV 05.11.2025 18:00 nach 129 Stunden ohne Zeile 134,3 kWh —
  mit der Grenze je Zeile ein Fund am Stichtag 31.10.2025, mit der Spanne keiner).
  (b) gilt auch an einem jungen Zähler — seit U3-K3 (Nachmessung K2-B5) auch ohne Tag mit Zuwachs im Bezug (ein neuer
  Abschnitt nach einem eingetragenen Tausch: die zweite Stunde eines kurzen Fremdstands blieb sonst ungenannt); dort ohne Maß
  (``mass`` = 0). Stand-Zähler in anderen Einheiten (m³, l, km) haben kein (b).

Der Arm «Neubeginn» bleibt, wie er war (Bezug mit ``BEZUG_MIN_TAGE`` Tagen, Maß über ``SCHWELLE_NEUBEGINN``).

**Vierter Arm «Zwischenstand»** (``ZWISCHENSTAND``, U3-K B4; nur mit ``zwischenstand=True``, den der MQTT-Erzeuger setzt): ein
Gerät meldet innerhalb einer Stunde kurz 0 oder ein anderes Gerät sendet kurz seinen Stand — am Stundenende steht der alte
Zähler wieder, HAs Summenregel hat dazwischen aber einen Neubeginn gezählt. Die Zeile zeigt dann Δ ``sum`` − Δ ``state``
≥ ``ZWISCHEN_ANTEIL`` × Stand davor bei einem Stand, der nicht gefallen ist (der Stand davor mindestens ``MIN_STAND``). Kein
Maß, auch an einem jungen Zähler; ein Tageszähler fällt in der Stunde seines Neubeginns und trifft den Arm nie.

**Schwellen aus M4** (Messung 19.11.2026, ``~/.claude/plans/golden-master/sensorwechsel-saat/u2c/m4_verteilung.py``): über die
Produktiv-Kopie (12 Spiegel-Abschnitte, 137 450 Paare, 31.10.2024–15.11.2026) liegt das größte Maß bei 1,32 (Arm B, ein
Ladevorgang), Arm A bei keinem Paar über 0; im Saat-Satz (26 Abschnitte) bei 0,79. Mit einem Bezugsfenster von 30 Tagen statt
eines Jahres hätte ein Frühlingstag mit Netzbezug 13,3 kWh in einer Stunde nach einem Monat mit höchstens 0,4 kWh am Tag das
Maß 32 erreicht, mit 3 statt 14 Bezugstagen der erste Sonnentag eines jungen Einspeisezählers 44 — beides gewöhnlicher Betrieb.
Die Lab-Sprünge liegen bei +2 001 auf Zählern mit 6,9 bis 160 kWh am Tag zwischen 12,5 und 292 (Rechenweg F12) und beim
Lab-Neubeginn bei 300 (Rate 2,04 kWh je Stunde) bei ≈ 6. **U3-K (M4 erweitert, Stichtag-Probe):** dieselbe Produktiv-Kopie, als
hätte die Statistik an einem von 362 Stichtagen (alle zwei Tagen, 01.11.2024–24.10.2026) erst begonnen: mit der Regel vor U3-K 10
Fund-Stunden aus gewöhnlichem Betrieb bei 19 Stichtagen (Einspeisung im Winter bis 7,99 kWh, Netzbezug 13,31 kWh; Maß bis 51,5),
mit (a)/(b) **0**; die größte Stundenmenge der Kopie liegt weit unter ``MENGE_UNMOEGLICH_MIN`` (Anlage 12,3 kWp ⇒ Grenze 100).

Die Funktionen sind rein (keine Datenbank, keine Uhr; der Kalendertag ist der lokale der Prozesszone = HA, wie
``ha_sprung``). Welche Stunden ausgenommen sind (das Muster «kurz 0 und zurück», ``ha_zaehlersprung``), sagt der Aufrufer.
Der Kern kennt keine Familie: der Erzeuger ``services/daten_checker/datenquelle/standsprung.py`` gibt ihm die Zeilen eines
Spiegel-Abschnitts; eine MQTT-Mitschrift ließe sich ebenso prüfen.
"""

from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional, Sequence

#: Arm A: Neubeginn des Zählers nicht bei 0 (der Stand fällt, HA zählt den neuen Stand).
NEUBEGINN = "neubeginn"
#: Arm B: der Stand springt nach oben (Δ sum = Δ state).
SPRUNG = "sprung"
#: Arm C (U3 b, G4): die Stunde zählt einen Rückgang (Zuwachs unter −``RUECKGANG_SCHWELLE``) — nur mit ``rueckgang=True``.
RUECKGANG = "rueckgang"
#: Rückgang-Arm: ein Zuwachs unter −diesem Wert (Rechenweg G4; M2 an MQTT-Bestand: kein Paar darunter).
RUECKGANG_SCHWELLE = 0.01

#: Schwelle des Maßes im Arm «Neubeginn» (M4: Produktiv und Saat 0 Paare über 0; Lab-Neubeginn bei 300 ≈ 6).
SCHWELLE_NEUBEGINN = 3.0
#: Schwelle des Maßes im Arm «Sprung» (M4: Produktiv höchstens 1,32, Saat 0,79; Lab +2 001 ab 12,5).
SCHWELLE_SPRUNG = 10.0
#: Bezugsfenster in Tagen vor dem Tag der Stunde — ein Jahr, damit der Winter den Sommer und der Sommer den Winter kennt.
BEZUG_TAGE = 365
#: So viele Tage mit Zuwachs braucht das Bezugsfenster; darunter ist der Zähler jung (kein Befund).
BEZUG_MIN_TAGE = 14
#: U3-K (B2 (a)): so viel muss der größte Tag im Bezug zählen, damit der Bezug reif ist (eine Reihe aus Standby kennt den Betrieb
#: noch nicht).
REIF_MIN_TAG = 1.0
#: U3-K (B2 (b)): eine Stundenmenge über dieser Menge (kWh) — oder über 1,5 × Anlagenleistung, wenn das mehr ist — kann keine
#: Anlage in einer Stunde verbrauchen oder erzeugen.
MENGE_UNMOEGLICH_MIN = 100.0
#: Arm D (U3-K, B4): innerhalb der Stunde hat der Stand kurz eine andere Höhe gezeigt und ist zurückgekehrt.
ZWISCHENSTAND = "zwischenstand"
#: Arm D: Δ sum − Δ state ab diesem Anteil des Stands davor.
ZWISCHEN_ANTEIL = 0.9
#: Neubeginn: der Stand fällt unter diesen Anteil des vorigen.
NEUBEGINN_ANTEIL = 0.9
#: Unter diesem vorigen Stand ist ein Fallen kein Neubeginn (wie ``ha_sprung.MIN_STAND_KWH``).
MIN_STAND = 1.0
#: Δ sum = Δ state bis auf diese Menge …
GLEICH_ABS = 0.01
#: … plus diesen Anteil von |Δ sum|.
GLEICH_ANTEIL = 0.01
_TAG_S = 86400


@dataclass(frozen=True)
class Standsprung:
    """Eine Stunde mit Sprung: ``start_ts`` = Beginn der Zeile, in der eedc (wie HA) die Menge ``menge`` zählt."""

    start_ts: int
    art: str
    menge: float
    stand_vorher: float
    stand_nachher: float
    mass: float


def _tag(ts: int) -> date:
    return datetime.fromtimestamp(ts).date()


def _zuwachs(z0: tuple, z1: tuple, spalte: int) -> Optional[float]:
    a, b = z0[spalte], z1[spalte]
    return None if a is None or b is None else b - a


def tageszuwachs(zeilen: Sequence[tuple], spalte: int = 2) -> dict[date, float]:
    """Σ der positiven Zuwächse je lokalem Kalendertag (Tag der jeweils späteren Zeile). ``spalte``: 2 = ``sum``, 1 = ``state``."""
    je_tag: dict[date, float] = {}
    for z0, z1 in zip(zeilen, zeilen[1:]):
        d = _zuwachs(z0, z1, spalte)
        if d is not None and d > 0:
            je_tag[_tag(z1[0])] = je_tag.get(_tag(z1[0]), 0.0) + d
    return je_tag


def bezug(je_tag: dict[date, float], tag: date) -> tuple[int, float]:
    """(Tage mit Zuwachs, größter Tageszuwachs) im Bezugsfenster ``[tag − BEZUG_TAGE, tag)``."""
    tage = sorted(je_tag)
    links = bisect_left(tage, date.fromordinal(tag.toordinal() - BEZUG_TAGE))
    rechts = bisect_left(tage, tag)
    fenster = tage[links:rechts]
    return len(fenster), max((je_tag[t] for t in fenster), default=0.0)


def mass(menge: float, groesster_tag: float, tage_ruhe: float) -> float:
    """Das Maß F12: Zuwachs der Stunde ÷ (größter Tageszuwachs × Tage seit dem letzten Zuwachs, mindestens 1)."""
    return menge / (groesster_tag * max(1.0, tage_ruhe))


def _gleich(z0: tuple, z1: tuple) -> bool:
    d_sum, d_state = _zuwachs(z0, z1, 2), _zuwachs(z0, z1, 1)
    return d_sum is not None and d_state is not None and abs(d_sum - d_state) <= GLEICH_ABS + GLEICH_ANTEIL * abs(d_sum)


def _neubeginn(z0: tuple, z1: tuple) -> bool:
    st0, st1 = z0[1], z1[1]
    return st0 is not None and st1 is not None and st0 >= MIN_STAND and st1 < NEUBEGINN_ANTEIL * st0


def grenze_unmoeglich(schwelle_anlage: Optional[float]) -> float:
    """B2 (b): die Stundenmenge, über der eine Anlage nicht liegen kann — ``MENGE_UNMOEGLICH_MIN`` oder die Schwelle der Anlage
    (``snapshot/plausibility.schwelle_pv_einspeisung_stunde_kwh``, 1,5 × kWp), was größer ist."""
    return max(MENGE_UNMOEGLICH_MIN, schwelle_anlage or 0.0)


def grenze_der_zeile(grenze: float, z0: tuple, z1: tuple) -> float:
    """Die Grenze B2 (b) für eine Zeile, die ``n`` Stunden trägt (Zählerlücke: HA führt die Menge der Lücke in der ersten Zeile
    danach) — ``grenze × n`` wie ``snapshot/plausibility.schwelle_pv_einspeisung_stunde_kwh(…, spanne=n)``."""
    return grenze * max(1.0, (z1[0] - z0[0]) / 3600.0)


def reif(n_tage: int, groesster_tag: float, erste: date, tag: date) -> bool:
    """B2 (a): der Bezug kennt den gewöhnlichen Betrieb — der Abschnitt reicht ``BEZUG_TAGE`` zurück, das Fenster hat
    ``BEZUG_MIN_TAGE`` Tage mit Zuwachs, und sein größter Tag zählt mindestens ``REIF_MIN_TAG``."""
    return (erste.toordinal() <= tag.toordinal() - BEZUG_TAGE and n_tage >= BEZUG_MIN_TAGE
            and groesster_tag >= REIF_MIN_TAG)


def _zwischenstand(z0: tuple, z1: tuple) -> bool:
    """Arm D: der Stand ist nicht gefallen, die Summe aber um mindestens ``ZWISCHEN_ANTEIL`` × Stand davor mehr gewachsen."""
    d_sum, d_state = _zuwachs(z0, z1, 2), _zuwachs(z0, z1, 1)
    return (d_sum is not None and d_state is not None and z0[1] >= MIN_STAND and d_state >= 0
            and d_sum - d_state >= ZWISCHEN_ANTEIL * z0[1])


def _arm(z0: tuple, z1: tuple, m: float, jung: bool, darf_springen: bool) -> Optional[str]:
    if _neubeginn(z0, z1):
        return NEUBEGINN if not jung and m > SCHWELLE_NEUBEGINN else None
    return SPRUNG if darf_springen and m > SCHWELLE_SPRUNG and _gleich(z0, z1) else None


def _ohne_mass(z0: tuple, z1: tuple, menge: float, rueckgang: bool, zwischenstand: bool) -> Optional[str]:
    """Die Arme ohne Maß (nur MQTT): «Rückgang» und «Zwischenstand»."""
    if rueckgang and menge < -RUECKGANG_SCHWELLE:
        return RUECKGANG
    if zwischenstand and _zwischenstand(z0, z1):
        return ZWISCHENSTAND
    return None


def finde_standspruenge(zeilen: Sequence[tuple], *, stand: bool = False,
                        ausgenommen: frozenset[int] | set[int] = frozenset(), rueckgang: bool = False,
                        grenze: Optional[float] = None, zwischenstand: bool = False) -> list[Standsprung]:
    """Reine Funktion: ``zeilen`` = ``(start_ts, state, sum)`` EINES Quell-Abschnitts, aufsteigend. ``stand``: der Zähler ist
    ein Stand (eedc zählt Δ ``state``), sonst eine Menge (Δ ``sum``). ``ausgenommen``: ``start_ts`` der Zeilen, die eine
    andere Prüfung schon nennt. ``rueckgang``/``zwischenstand``: dazu die Arme ohne Maß (U3 b, U3-K; nur MQTT). ``grenze``:
    B2 (b), die Stundenmenge, über der der Arm «Sprung» auch ohne reifen Bezug meldet (``None`` = kein (b)). Je Stunde mit
    Sprung ein ``Standsprung`` in Zeitfolge."""
    if not zeilen:
        return []
    spalte = 1 if stand else 2
    je_tag = tageszuwachs(zeilen, spalte)
    erste = _tag(zeilen[0][0])
    bezug_je_tag: dict[date, tuple[int, float]] = {}
    out: list[Standsprung] = []
    letzter_zuwachs: Optional[int] = None
    for z0, z1 in zip(zeilen, zeilen[1:]):
        menge = _zuwachs(z0, z1, spalte)
        if menge is None:
            continue
        ruhe = (z1[0] - letzter_zuwachs) / _TAG_S if letzter_zuwachs is not None else 1.0
        if menge > 0:
            letzter_zuwachs = z1[0]
        if z1[0] in ausgenommen:
            continue
        ohne = _ohne_mass(z0, z1, menge, rueckgang, zwischenstand)
        if ohne is not None:
            out.append(Standsprung(int(z1[0]), ohne, menge, z0[1], z1[1], 0.0))
            continue
        tag = _tag(z1[0])
        if tag not in bezug_je_tag:
            bezug_je_tag[tag] = bezug(je_tag, tag)
        n_tage, groesster = bezug_je_tag[tag]
        if menge <= 0:
            continue
        ueber = grenze is not None and menge > grenze_der_zeile(grenze, z0, z1)
        if n_tage < 1:
            # U3-K3 (K2-B5): ohne Tag mit Zuwachs im Bezug (ein neuer Abschnitt, etwa nach einem eingetragenen Tausch) kein Maß —
            # über der Grenze meldet der Arm «Sprung» trotzdem (B2 (b) braucht keinen Bezug); Maß 0 wie die Arme ohne Maß.
            if ueber and not _neubeginn(z0, z1) and _gleich(z0, z1):
                out.append(Standsprung(int(z1[0]), SPRUNG, menge, z0[1], z1[1], 0.0))
            continue
        m = mass(menge, groesster, ruhe)
        art = _arm(z0, z1, m, n_tage < BEZUG_MIN_TAGE, reif(n_tage, groesster, erste, tag) or ueber)
        if art is not None:
            out.append(Standsprung(int(z1[0]), art, menge, z0[1], z1[1], m))
    return out


__all__ = ["BEZUG_MIN_TAGE", "BEZUG_TAGE", "MENGE_UNMOEGLICH_MIN", "NEUBEGINN", "REIF_MIN_TAG", "RUECKGANG",
           "RUECKGANG_SCHWELLE", "SCHWELLE_NEUBEGINN", "SCHWELLE_SPRUNG", "SPRUNG", "Standsprung", "ZWISCHENSTAND",
           "ZWISCHEN_ANTEIL", "bezug", "finde_standspruenge", "grenze_der_zeile", "grenze_unmoeglich", "mass", "reif", "tageszuwachs"]
