"""Zuordnung zum Zeitpunkt (Bauplan B-0) — welche Quelle galt für einen Zählerschlüssel um ``z``?

**Regel (Bauplan §2 B-0):** für einen Zeitstempel ``z`` gilt ``vorher`` des **frühesten** Wechsels mit ``ab_ts > z``, sonst die
heutige Zuordnung; bei einer Korrektur gilt in ``[falsch_seit_ts, ab_ts)`` deren ``nachher``, und **vor** ``falsch_seit_ts``
zählen die Zeilen, die sie aufgehoben hat, weiter (dort gilt, was ohne die Korrektur galt — «Zu §13» Nr. 84). Ohne verzeichneten Wechsel gilt für
jeden Zeitpunkt die heutige Quelle — **das Verhalten von vor diesem Vorhaben** (Bedingung für «Golden Master 0»).

Drei Antworten: ``HEUTE`` (die heutige Zuordnung gilt — der Aufrufer verfährt wie bisher), ``UNBEKANNT`` (eine Quelle galt,
aber eedc weiß nicht welche ⇒ kein Schreiben, kein Löschen, kein Heilen), oder die Quelle selbst als Beschreibung
(``{"art": "ha", "entity_id": …}`` · ``{"art": "mqtt", "mqtt_key": …, …}`` · ``{"art": "keine"}``, Form in ``quelle.py``).

Das Laden merkt sich die Zeilen **je Sitzung** (``AsyncSession.info``) — ein Schreiblauf über viele Stunden oder ein Leser,
der viele Ränder heilt, fragt die Tabelle einmal je Anlage; ``verzeichnen.py`` trägt neue Zeilen in dieselbe Merkliste ein.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Optional, Union

from sqlalchemy import select
from sqlalchemy.exc import OperationalError

logger = logging.getLogger(__name__)


class _Marke:
    def __init__(self, name: str) -> None:
        self._name = name

    def __repr__(self) -> str:  # pragma: no cover — nur Anzeige
        return self._name


#: Die heutige Zuordnung gilt (kein verzeichneter Wechsel nach ``z``).
HEUTE = _Marke("HEUTE")
#: Eine Quelle galt, eedc weiß aber nicht welche (``vorher`` leer) ⇒ nichts schreiben, nichts löschen.
UNBEKANNT = _Marke("UNBEKANNT")

Antwort = Union[_Marke, dict]

_INFO = "zuordnung_wechsel"


@dataclass(frozen=True)
class Wechsel:
    """Eine verzeichnete Zeile, wie die Lesestelle sie braucht (unveränderlich, ohne Sitzung)."""
    sensor_key: str
    ab_ts: datetime
    vorher: Optional[dict]
    nachher: Optional[dict]
    grund: Optional[str] = None
    falsch_seit_ts: Optional[datetime] = None
    aufgehoben_durch: Optional[int] = None
    #: Sekunde der Erklärung (B-4: im MQTT-Kanal schließen die Stände davor die alte Periode).
    erklaert_ts: Optional[datetime] = None
    #: Zeilen-Nummer — die Reihenfolge zweier Wechsel mit gleichem ``ab_ts`` (Bauplan §13 Nr. 66).
    id: Optional[int] = None
    #: Kennung des Korrektur-Laufs (``korrektur_lauf``) — solange er das Füllen schuldet, gilt das Intervall als Lücke
    #: (Bauplan «Zu §14» Nr. 106, ``gesperrte_stuecke``).
    lauf: Optional[str] = None
    #: Rand-Werte eines Wechsels «bleiben» (U2 a1, F1; ``models/zuordnung_wechsel.py``). Ohne ``ansatz``: wie vor U2.
    ansatz: Optional[str] = None
    stand_alt_ende: Optional[float] = None
    stand_neu_null: Optional[float] = None


def rand_versatz(w) -> Optional[float]:
    """Der Versatz der Reihe an einem angesetzten Wechsel «bleiben» (``stand_alt_ende − stand_neu_null``, Rechenweg F5):
    nur für eine gültige Fortsetzung mit ``ansatz`` ``beide``/``schnitt`` und beiden Rand-Ständen — sonst ``None`` (die Naht
    teilt wie vor U2; ``offen``/``offen_schnitt`` lesen so). Für ORM-Zeilen und ``Wechsel``."""
    from backend.core.berechnungen.zaehler_naht import rand_versatz as _rechne
    from backend.models.zuordnung_wechsel import ANSATZ_MIT_RAND, GRUND_FORTSETZUNG

    if w.grund != GRUND_FORTSETZUNG or w.aufgehoben_durch is not None or getattr(w, "ansatz", None) not in ANSATZ_MIT_RAND:
        return None
    return _rechne(w.stand_alt_ende, w.stand_neu_null)


def ab_ts_aus(erklaert_ts: datetime) -> datetime:
    """Erste volle Stunde ab ``erklaert_ts``: 10:47:42 → 11:00, 11:00:00 → 11:00 (der Stundenlauf schreibt 11:00 um 11:05
    schon mit der neuen Quelle)."""
    voll = erklaert_ts.replace(minute=0, second=0, microsecond=0)
    return voll if voll == erklaert_ts else voll + timedelta(hours=1)


def _quelle_oder_unbekannt(beschreibung: Any) -> Antwort:
    return beschreibung if isinstance(beschreibung, dict) and beschreibung.get("art") else UNBEKANNT


def _vor_falsch_seit(wechsel: list[Wechsel], gueltig: list[Wechsel], z: datetime) -> list[Wechsel]:
    """Bauplan «Zu §13» Nr. 84: **vor «falsch seit» gilt die Quelle, die ohne die Korrektur dort galt** — eine Zeile, die
    eine Korrektur aufgehoben hat (``aufgehoben_durch`` = deren Nummer), zählt für Zeiten vor deren ``falsch_seit_ts`` weiter
    (A → X → A mit Korrektur am zweiten Wechsel: vor dem ersten Wechsel A, nicht das ``vorher`` X der Korrektur-Zeile)."""
    korrektur = {w.id: w for w in gueltig if w.grund == "korrektur" and w.id is not None and w.falsch_seit_ts is not None}
    if not korrektur:
        return []
    return [w for w in wechsel if w.aufgehoben_durch in korrektur and z < korrektur[w.aufgehoben_durch].falsch_seit_ts]


def _juengste_korrektur_am(gueltig: list[Wechsel], z: datetime) -> Optional[Wechsel]:
    """Die Korrektur-Zeile, deren Intervall ``[falsch_seit_ts, ab_ts)`` ``z`` enthält — in einer Überlappung **die jüngste**
    (höchste Zeilen-Nummer; Bauplan «Zu §14» Nr. 97, Nr. 91 d: eine spätere Korrektur, die eine frühere umschließt, gilt)."""
    treffer = [w for w in gueltig
               if w.grund == "korrektur" and w.falsch_seit_ts is not None and w.falsch_seit_ts <= z < w.ab_ts]
    return max(treffer, key=lambda w: w.id if w.id is not None else -1) if treffer else None


def quelle_am(wechsel: Optional[list[Wechsel]], z: datetime) -> Antwort:
    """Die Quelle eines Schlüssels um ``z`` (reine Funktion; ``wechsel`` = die Zeilen DIESES Schlüssels, beliebig sortiert).
    Eine Lücken-Zeile gilt nur in ihrem Intervall (dort: unbekannt); als Wechsel zählt sie nicht (``ist_luecken_zeile``)."""
    if not wechsel:
        return HEUTE
    gueltig = [w for w in wechsel if w.aufgehoben_durch is None]
    korrektur = _juengste_korrektur_am(gueltig, z)
    if korrektur is not None:
        return _quelle_oder_unbekannt(korrektur.nachher)
    spaetere = [w for w in gueltig + _vor_falsch_seit(wechsel, gueltig, z) if w.ab_ts > z and not ist_luecken_zeile(w)]
    if not spaetere:
        return HEUTE
    return _quelle_oder_unbekannt(min(spaetere, key=lambda w: w.ab_ts).vorher)


def zuordnung_am(wechsel_je_key: Optional[dict[str, list[Wechsel]]], z: datetime) -> dict[str, Antwort]:
    """Alle Schlüssel, für die um ``z`` **nicht** die heutige Zuordnung gilt (``HEUTE`` fehlt im Ergebnis)."""
    aus: dict[str, Antwort] = {}
    for key, liste in (wechsel_je_key or {}).items():
        antwort = quelle_am(liste, z)
        if antwort is not HEUTE:
            aus[key] = antwort
    return aus


def _als_wechsel(row) -> Wechsel:
    return Wechsel(row.sensor_key, row.ab_ts, row.vorher, row.nachher, row.grund, row.falsch_seit_ts,
                   row.aufgehoben_durch, row.erklaert_ts, row.id, getattr(row, "lauf", None), getattr(row, "ansatz", None),
                   getattr(row, "stand_alt_ende", None), getattr(row, "stand_neu_null", None))


async def lade_wechsel(db, anlage_id: int) -> dict[str, list[Wechsel]]:
    """Die verzeichneten Wechsel einer Anlage je Schlüssel — einmal je Sitzung gelesen (``db.info``)."""
    from backend.models.zuordnung_wechsel import ZuordnungWechsel

    if not isinstance(getattr(db, "info", None), dict):
        # Keine Sitzung (Proben mit einer gestellten Datenbank-Attrappe, seit Sitzung 2 auch über die Reihen-Leser): ohne
        # Sitzung gibt es keine verzeichneten Wechsel.
        return {}
    merk = db.info.setdefault(_INFO, {})
    if anlage_id in merk:
        return merk[anlage_id]
    try:
        rows = (await db.execute(
            select(ZuordnungWechsel).where(ZuordnungWechsel.anlage_id == anlage_id).order_by(ZuordnungWechsel.id)
        )).scalars().all()
    except OperationalError as e:  # Tabelle fehlt (Teil-Schema einer Probe) — ohne Tabelle gibt es keinen Wechsel
        if "no such table" not in str(e):
            raise
        logger.debug("zuordnung_wechsel fehlt in dieser Datenbank: %s", e)
        rows = []
    je_key: dict[str, list[Wechsel]] = {}
    for row in rows:
        je_key.setdefault(row.sensor_key, []).append(_als_wechsel(row))
    merk[anlage_id] = je_key
    return je_key


def merke_neu(db, row) -> None:
    """Eine eben verzeichnete Zeile in die Merkliste der Sitzung (sonst sähe derselbe Lauf sie erst nach Neustart)."""
    merk = db.info.get(_INFO)
    if merk is not None and row.anlage_id in merk:
        merk[row.anlage_id].setdefault(row.sensor_key, []).append(_als_wechsel(row))


def vergiss(db, anlage_id: Optional[int] = None) -> None:
    """Merkliste der Sitzung verwerfen (nach dem Räumen eines Geräts oder einer Überführung)."""
    merk = db.info.get(_INFO)
    if merk is None:
        return
    if anlage_id is None:
        merk.clear()
    else:
        merk.pop(anlage_id, None)


def ist_luecken_zeile(w) -> bool:
    """**Lücken-Zeilen sind keine Quellenwechsel** (Bauplan «Zu §14» Nr. 105, F7 — das eine Prädikat): die zweite
    Korrektur-Zeile, die der Korrektur-Dienst für einen ungefüllten Teil schreibt (``korrektur._luecken_zeile``: Grund
    «Korrektur», ``nachher`` leer). Sie sagt nur «hier gilt keine Quelle»; wer nach Wechseln fragt (letzte Quelle mit Werten,
    spätere Wechsel, «Grund nachtragen», die Quelle nach einem Wechsel), überspringt sie. Für ORM-Zeilen und ``Wechsel``."""
    from backend.models.zuordnung_wechsel import GRUND_KORREKTUR

    n = w.nachher
    return w.grund == GRUND_KORREKTUR and not (isinstance(n, dict) and n.get("art"))


def ist_luecke(w: Wechsel) -> bool:
    """Eine **Lücke** (Bauplan «Zu §14» Nr. 95 (1), Nr. 97): eine nicht aufgehobene Korrektur-Zeile, deren ``nachher`` keine
    Home-Assistant-Entität nennt (MQTT, «Keine», unbekannt) — ihr Intervall ``[falsch_seit_ts, ab_ts)`` ist verworfen und wird
    nie gefüllt (eine MQTT-Quelle hat keine Geschichte, ohne Quelle gibt es nichts zu lesen). Der Korrektur-Dienst schreibt
    für einen Teil, den Home Assistant nicht füllen kann, eine solche Zeile mit ``nachher`` leer (``korrektur._luecken_zeile``).
    Aus der Zeile abgeleitet, ohne eigene Spalte — gilt damit auch für schon eingetragene Korrekturen."""
    from backend.models.zuordnung_wechsel import GRUND_KORREKTUR

    if w.grund != GRUND_KORREKTUR or w.aufgehoben_durch is not None or w.falsch_seit_ts is None:
        return False
    n = w.nachher
    return not (isinstance(n, dict) and n.get("art") == "ha" and n.get("entity_id"))


def gesperrte_stuecke(wechsel: Optional[list[Wechsel]], offene_laeufe: frozenset[str] = frozenset(),
                      ausgenommen: frozenset = frozenset()) -> list[tuple[datetime, datetime]]:
    """Die Stücke ``[falsch_seit_ts, ab_ts)``, über die kein Leser eine Differenz bildet, aufsteigend: jede Lücke
    (``ist_luecke``) außer denen in ``ausgenommen`` (**ohne Höhenwechsel**, ``ohne_hoehenwechsel`` — Sensorwechsel U1, Bauplan
    Nr. 127/133 (4): dort rechnen die Leser wie über jede Zählerlücke) und — Bauplan «Zu §14» Nr. 106 — jede Korrektur, deren
    Lauf das Füllen noch schuldet (``offene_laeufe``: Kennungen der Läufe mit offenem Nachlauf,
    ``korrektur_lauf.offener_lauf``); mit dem Füllen endet diese Sperre."""
    from backend.models.zuordnung_wechsel import GRUND_KORREKTUR

    aus = set()
    for w in wechsel or ():
        if (ist_luecke(w) and (w.falsch_seit_ts, w.ab_ts) not in ausgenommen) or (
                offene_laeufe and w.lauf in offene_laeufe and w.grund == GRUND_KORREKTUR
                and w.aufgehoben_durch is None and w.falsch_seit_ts is not None):
            aus.add((w.falsch_seit_ts, w.ab_ts))
    return sorted(aus)


def verworfene_stuecke(wechsel: Optional[list[Wechsel]], offene_laeufe: frozenset[str] = frozenset()
                       ) -> list[tuple[datetime, datetime]]:
    """Alle verworfenen, nicht gefüllten Stücke (auch die ohne Höhenwechsel) — für den **Grund** eines Tages ohne Stände
    (``snapshot/aggregator._grund_ohne_staende``), nicht für die Rechnung."""
    return gesperrte_stuecke(wechsel, offene_laeufe)


def naehte_der_fortsetzung(wechsel: Optional[list[Wechsel]], offene_laeufe: frozenset[str] = frozenset(),
                           ausgenommen: frozenset = frozenset()) -> list[datetime]:
    """Die Nähte eines Schlüssels (Bauplan B-3): ``ab_ts`` jedes nicht aufgehobenen Wechsels mit Grund «Fortsetzung»,
    aufsteigend. Ein Wechsel ohne Grund ist keine Naht — die Leser lesen dort wie vor diesem Vorhaben (Sitzung 2).

    **Lücke nur bei Höhenwechsel** (Bauplan «Zu §14» Nr. 95 (1), Nr. 97, geändert durch Nr. 119/127 und das Zielbild Nr. 133
    (4)): dazu beide Ränder jedes gesperrten Stücks (``gesperrte_stuecke``: jede Lücke mit Höhenwechsel, und eine Korrektur,
    deren Füllen aussteht) — kein Leser bildet eine Differenz zweier Stände über ein verworfenes, nicht gefülltes Stück, wenn
    davor und danach verschiedene Zählerhöhen gelten. Ohne Höhenwechsel (``ausgenommen``) ist ein Rand keine Naht: die Menge
    der Zeit steht am ersten Stand danach, wie an jeder Zählerlücke.

    **Naht mit Rand-Ständen** (U2 a1, Rechenweg F5): ein angesetzter Wechsel «bleiben» (``rand_versatz``) liefert seine
    Naht als ``zaehler_naht.Naht`` mit Versatz — sie teilt nicht, sie hebt. Ein Zeitpunkt, an dem zugleich eine teilende Naht
    liegt, bleibt beides (die teilende gewinnt beim Teilen). **Wechselstelle «Falsch seit»** (Pflichtpunkt P-1): erklärt eine
    Korrektur für ihre Zeit eine andere Home-Assistant-Entität als richtig als die, die davor galt, ist ``falsch_seit_ts`` eine
    Naht ohne Rand-Stände (``_falsch_seit_zwischen_zwei_sensoren``) — keine Differenz zweier Sensoren."""
    from backend.core.berechnungen.zaehler_naht import Naht
    from backend.models.zuordnung_wechsel import GRUND_FORTSETZUNG

    teilend: set[datetime] = set()
    hebend: list[Naht] = []
    for w in wechsel or ():
        if w.grund != GRUND_FORTSETZUNG or w.aufgehoben_durch is not None:
            continue
        v = rand_versatz(w)
        if v is None:
            teilend.add(w.ab_ts)
        else:
            hebend.append(Naht(w.ab_ts, v))
    for s, r in gesperrte_stuecke(wechsel, offene_laeufe, ausgenommen):
        teilend |= {s, r}
    teilend |= _falsch_seit_zwischen_zwei_sensoren(wechsel)
    if not hebend:
        return sorted(teilend)
    return sorted([*teilend, *hebend], key=lambda n: (n, isinstance(n, Naht)))


def _falsch_seit_zwischen_zwei_sensoren(wechsel: Optional[list[Wechsel]]) -> set[datetime]:
    """Pflichtpunkt P-1 (Nachmessung U1 «F7»): ``falsch_seit_ts`` jeder gültigen Korrektur-Zeile (keine Lücken-Zeile), die eine
    Home-Assistant-Entität als richtig erklärt, wenn davor eine **andere** Home-Assistant-Entität galt (``quelle_aufgeloest``
    eine Sekunde vor «Falsch seit»). Nur Home Assistant → Home Assistant; andere Kombinationen lesen wie vor U2."""
    from backend.models.zuordnung_wechsel import GRUND_KORREKTUR

    aus: set[datetime] = set()
    for w in wechsel or ():
        if (w.grund != GRUND_KORREKTUR or w.aufgehoben_durch is not None or w.falsch_seit_ts is None
                or ist_luecken_zeile(w) or (w.nachher or {}).get("art") != "ha"):
            continue
        davor = quelle_aufgeloest(wechsel, w.falsch_seit_ts - timedelta(seconds=1))
        if davor is not None and davor.get("art") == "ha" and not gleiche_quelle(davor, w.nachher):
            aus.add(w.falsch_seit_ts)
    return aus


# ── Lücke ohne Höhenwechsel (Sensorwechsel U1, Bauplan Nr. 127 Option A, Zielbild Nr. 133 (4)) ─────────────────────────


def quelle_aufgeloest(wechsel: Optional[list[Wechsel]], z: datetime) -> Optional[dict]:
    """Die Quelle um ``z`` aus den Zeilen allein: ``quelle_am``; gilt dort die heutige Zuordnung (``HEUTE``, kein Wechsel
    nach ``z``), die neue Quelle (``nachher``) des jüngsten gültigen Wechsels bis ``z`` — Lücken-Zeilen zählen nicht. ``None``
    = unbekannt (auch: gar kein Wechsel bis ``z``). Ohne Blick auf die heutige Zuordnung, damit Vorschau und Leser dieselbe
    Antwort geben, auch bevor die Zuordnung der Vorschau geschrieben ist."""
    q = quelle_am(wechsel, z)
    if isinstance(q, dict):
        return q
    if q is not HEUTE:
        return None
    frueher = [w for w in wechsel or () if w.aufgehoben_durch is None and w.ab_ts <= z and not ist_luecken_zeile(w)]
    if not frueher:
        return None
    n = max(frueher, key=lambda w: (w.ab_ts, w.id if w.id is not None else -1)).nachher
    return n if isinstance(n, dict) and n.get("art") else None


def gleiche_quelle(a: Optional[dict], b: Optional[dict]) -> bool:
    """Dieselbe Quelle (Home Assistant: dieselbe Entität; sonst die gleiche Beschreibung)."""
    if not a or not b or a.get("art") != b.get("art"):
        return False
    return a.get("entity_id") == b.get("entity_id") if a.get("art") == "ha" else a == b


def _deckt(w: Wechsel, z: datetime) -> bool:
    return w.falsch_seit_ts is not None and w.falsch_seit_ts <= z < w.ab_ts


def erklaerte_quelle(wechsel: Optional[list[Wechsel]], z: datetime) -> Optional[dict]:
    """Die Quelle, die eine Korrektur für die leere Zeit um ``z`` als **richtig erklärt** hat (Korrekturrunde U1-K, Bauplan
    Nr. 141 (c) (i)): ``nachher`` der jüngsten Korrektur-Zeile (keine Lücken-Zeile) mit ``z`` in ihrem Intervall — auch einer,
    die eine spätere Korrektur aufgehoben hat, solange deren Intervall ``z`` nicht deckt (der Rest einer älteren Lücke behält
    die Quelle, die für ihn erklärt ist, Nr. 113). ``None`` = keine oder keine bekannte Quelle erklärt."""
    from backend.models.zuordnung_wechsel import GRUND_KORREKTUR

    zeilen = list(wechsel or ())
    je_id = {w.id: w for w in zeilen if w.id is not None}

    def gilt(w: Wechsel) -> bool:
        h = je_id.get(w.aufgehoben_durch)
        return w.aufgehoben_durch is None or (h is not None and not _deckt(h, z))

    treffer = [w for w in zeilen if w.grund == GRUND_KORREKTUR and not ist_luecken_zeile(w) and _deckt(w, z) and gilt(w)]
    if not treffer:
        return None
    n = max(treffer, key=lambda w: w.id if w.id is not None else -1).nachher
    return n if isinstance(n, dict) and n.get("art") else None


def _zaehlertausch_dazwischen(wechsel: Optional[list[Wechsel]], q: dict, vor: datetime, nach: datetime) -> bool:
    """Eine Fortsetzung mit ``vor < ab_ts ≤ nach``, an der die Quelle ``q`` beteiligt ist (Bauplan Nr. 141 (c) (ii)): jede
    gültige; dazu ein Zählertausch derselben Quelle (``q → q``) **auch, wenn eine Korrektur ihn aufgehoben hat** — der Zähler
    wurde getauscht, gleich was die Korrektur über die Quelle der Zeit sagt. Eine Fortsetzung nur einer anderen Quelle
    (``X → X``) zählt nicht."""
    from backend.models.zuordnung_wechsel import GRUND_FORTSETZUNG

    for w in wechsel or ():
        if w.grund != GRUND_FORTSETZUNG or not vor < w.ab_ts <= nach:
            continue
        vq, nq = gleiche_quelle(w.vorher, q), gleiche_quelle(w.nachher, q)
        if (vq and nq) or (w.aufgehoben_durch is None and (vq or nq)):
            return True
    return False


def ohne_hoehenwechsel(wechsel: Optional[list[Wechsel]], vor: Optional[datetime], nach: Optional[datetime],
                       luecke: tuple[datetime, datetime]) -> bool:
    """Liegt zwischen dem letzten Stand vor einer Lücke (``vor``) und dem ersten Stand danach (``nach``) **kein erklärter
    Höhenwechsel**? Ja, wenn dieselbe Quelle davor, **in** der leeren Zeit ``luecke`` und danach gilt — an beiden Ständen
    (``quelle_aufgeloest``) und als die für die Zeit erklärte richtige Quelle (``erklaerte_quelle``, an ihrem Beginn und an jeder
    Korrektur-Grenze darin) — und kein Zählertausch dieser Quelle dazwischen eingetragen ist (``_zaehlertausch_dazwischen``;
    Korrekturrunde U1-K, Bauplan Nr. 141 (c)). Dann ist ``Stand(nach) − Stand(vor)`` die Menge der Zeit, und sie steht am
    ersten Stand danach — wie an jeder Zählerlücke (Grundsatz «Zählerlücken wie HA», Regel Q1). Die Höhe selbst prüft eedc
    nicht. Ohne Stand davor oder danach gibt es keine Differenz: nein. **Merkmal «Höhe ungeprüft»** (Pflichtpunkt P-2, Halt H-1
    aus U1-K, Option A): trägt die Lücken-Zeile dieser Zeit ``ansatz = hoehe_ungeprueft`` (die Korrektur füllt erst nach ihr
    aus Home Assistant, und kein Rand-Stand war prüfbar), ist ihr Rand ein Höhenwechsel: nein."""
    from backend.models.zuordnung_wechsel import ANSATZ_HOEHE_UNGEPRUEFT, GRUND_KORREKTUR

    if vor is None or nach is None:
        return False
    if any(w.aufgehoben_durch is None and ist_luecken_zeile(w) and w.ansatz == ANSATZ_HOEHE_UNGEPRUEFT
           and (w.falsch_seit_ts, w.ab_ts) == tuple(luecke) for w in wechsel or ()):
        return False
    q = quelle_aufgeloest(wechsel, vor)
    if q is None or not gleiche_quelle(q, quelle_aufgeloest(wechsel, nach)):
        return False
    von, bis = luecke
    punkte = {von} | {t for w in wechsel or () if w.grund == GRUND_KORREKTUR
                      for t in (w.falsch_seit_ts, w.ab_ts) if t is not None and von < t < bis}
    if not all(gleiche_quelle(q, erklaerte_quelle(wechsel, t)) for t in punkte):
        return False
    return not _zaehlertausch_dazwischen(wechsel, q, vor, nach)


async def staende_um(db, anlage_id: int, sensor_key: str, von: datetime, bis: datetime
                     ) -> tuple[Optional[datetime], Optional[datetime]]:
    """Der Zeitpunkt des letzten gespeicherten Stands vor ``von`` und des ersten ab ``bis`` (mit Wert)."""
    from sqlalchemy import func

    from backend.models.sensor_snapshot import SensorSnapshot

    vor = (await db.execute(select(func.max(SensorSnapshot.zeitpunkt)).where(
        SensorSnapshot.anlage_id == anlage_id, SensorSnapshot.sensor_key == sensor_key, SensorSnapshot.zeitpunkt < von,
        SensorSnapshot.wert_kwh.is_not(None)))).scalar_one_or_none()
    nach = (await db.execute(select(func.min(SensorSnapshot.zeitpunkt)).where(
        SensorSnapshot.anlage_id == anlage_id, SensorSnapshot.sensor_key == sensor_key, SensorSnapshot.zeitpunkt >= bis,
        SensorSnapshot.wert_kwh.is_not(None)))).scalar_one_or_none()
    return vor, nach


async def _ohne_hoehenwechsel_je_luecke(db, anlage_id: int, sensor_key: str, wechsel: Optional[list[Wechsel]]
                                        ) -> frozenset:
    """Die Lücken des Schlüssels ohne Höhenwechsel (``ohne_hoehenwechsel`` an den gespeicherten Ständen um die Lücke) — ihre
    Ränder sind keine Nähte. Nur gefragt, wenn der Schlüssel eine Lücke hat (im Normalbetrieb keine Abfrage)."""
    aus = set()
    for w in wechsel or ():
        if ist_luecke(w) and isinstance(getattr(db, "info", None), dict):
            vor, nach = await staende_um(db, anlage_id, sensor_key, w.falsch_seit_ts, w.ab_ts)
            if ohne_hoehenwechsel(wechsel, vor, nach, (w.falsch_seit_ts, w.ab_ts)):
                aus.add((w.falsch_seit_ts, w.ab_ts))
    return frozenset(aus)


async def _offene_laeufe(db, anlage_id: int, wechsel: Optional[list[Wechsel]]) -> frozenset[str]:
    """Die Läufe dieser Anlage mit offenem Nachlauf (Füllen) — nur gefragt, wenn eine Korrektur-Zeile des Schlüssels einen
    Lauf trägt und selbst keine Lücke ist (im Normalbetrieb keine Abfrage). Nicht gemerkt: der Lauf füllt in einer
    anderen Sitzung, die Sperre endet mit dem Füllen."""
    from backend.models.zuordnung_wechsel import GRUND_KORREKTUR
    from backend.services.zuordnung_wechsel.korrektur_lauf import offene_fuell_laeufe

    if not any(w.grund == GRUND_KORREKTUR and w.lauf and w.aufgehoben_durch is None and not ist_luecke(w)
               for w in wechsel or ()):
        return frozenset()
    try:
        return await offene_fuell_laeufe(db, anlage_id)
    except OperationalError as e:  # Tabelle fehlt (Teil-Schema einer Probe) — ohne Zustand kein offener Lauf
        if "no such table" not in str(e):
            raise
        return frozenset()


async def luecken_des_schluessels(db, anlage_id: int, sensor_key: str) -> list[tuple[datetime, datetime]]:
    """``gesperrte_stuecke`` mit dem Laden (dieselbe Ladestelle wie ``fortsetzungs_naehte``) — für den Rand eines Tagesfensters,
    der nicht über ein gesperrtes Stück auf den letzten Stand davor rücken darf (``snapshot/aggregator``, Nr. 102). Lücken ohne
    Höhenwechsel sperren nicht (U1)."""
    if not isinstance(getattr(db, "info", None), dict):
        return []
    wechsel = (await lade_wechsel(db, anlage_id)).get(sensor_key)
    return gesperrte_stuecke(wechsel, await _offene_laeufe(db, anlage_id, wechsel),
                             await _ohne_hoehenwechsel_je_luecke(db, anlage_id, sensor_key, wechsel))


async def verworfen_ohne_fuellen(db, anlage_id: int, sensor_key: str) -> list[tuple[datetime, datetime]]:
    """``verworfene_stuecke`` mit dem Laden — alle verworfenen, nicht gefüllten Stücke des Schlüssels (für den Grund eines
    Tages ohne Stände; die Rechnung folgt ``luecken_des_schluessels``)."""
    if not isinstance(getattr(db, "info", None), dict):
        return []
    wechsel = (await lade_wechsel(db, anlage_id)).get(sensor_key)
    return verworfene_stuecke(wechsel, await _offene_laeufe(db, anlage_id, wechsel))


async def fortsetzungs_naehte(db, anlage_id: int, sensor_key: str) -> list[datetime]:
    """``naehte_der_fortsetzung`` mit dem Laden der Zeilen (je Sitzung gemerkt, ``lade_wechsel``) — die eine Ladestelle
    der Reihen-Leser (Wächter «Reihen-Leser»)."""
    wechsel = (await lade_wechsel(db, anlage_id)).get(sensor_key)
    if not wechsel or not isinstance(getattr(db, "info", None), dict):
        return naehte_der_fortsetzung(wechsel)
    return naehte_der_fortsetzung(wechsel, await _offene_laeufe(db, anlage_id, wechsel),
                                  await _ohne_hoehenwechsel_je_luecke(db, anlage_id, sensor_key, wechsel))


async def quelle_zum_zeitpunkt(db, anlage_id: int, sensor_key: str, z: datetime) -> Antwort:
    """``quelle_am`` mit dem Laden der Zeilen (für einzelne Fragen wie das Heilen eines Randes)."""
    return quelle_am((await lade_wechsel(db, anlage_id)).get(sensor_key), z)
