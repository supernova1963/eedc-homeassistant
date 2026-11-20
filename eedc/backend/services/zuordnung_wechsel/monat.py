"""Monat aus Home Assistant je Geltungsabschnitt (Sensorwechsel U2 a1, Rechenweg F7, Bauplan Nr. 129/138/139).

**Regel.** Ein Monatswert aus Home Assistant ist die Summe der Zuwächse jeder Quelle in ihrer Geltungszeit — dieselbe
Zeilenregel wie bisher (``ha_statistics_service.get_sensor_fensterwert``, R4 und Anker wie ``get_sensor_monatswert``), nur je
Abschnitt. Ein Abschnitt endet an einem angesetzten Wechsel «bleiben» (``zuordnung_wechsel.ansatz`` ``beide``/``schnitt``,
``zeitpunkt.rand_versatz``): ``G = ab_ts − 1 h`` ist die erste Zeile, die die neue Quelle zählt.

* alte Quelle: ihre Zeilen vor ``G`` — bei ``beide`` (ohne Überlappung) einschließlich ``G`` (die Stunde des Wechsels zählt
  beide Sensoren);
* neue Quelle: ihre Zeilen ab ``G``; Anker ist die Zeile vor ``G`` — bei ``beide`` 0 (HAs Regel: die erste Zeile einer neuen
  Statistik zählt ab 0, nur hier am Wechsel, Bauplan Nr. 139).

Das Ergebnis steht unter der heutigen Entität, auch wenn der HA-Leser sie für den Monat nicht nennt (ein Monat nur mit dem
alten Sensor zeigt dessen Wert). ``start_wert``/``end_wert`` sind dann keine Zählerstände eines Sensors, sondern ein
durchlaufender Stand (wie beim Kanal-Ersatz). Ohne angesetzten Wechsel bleibt jede Antwort, wie der HA-Leser sie liefert —
Zeilen ohne ``ansatz`` lesen wie vor U2. **Wo:** vor dem Kanal-Ersatz der fünf Kalendermonats-Wege
(``kanal/bilanz_leser.monatswerte_mit_kanaelen``) und am laufenden Monat (``api/routes/aktueller_monat``).

**U3-K3 «Regel 2»** (``nullpunkt.py``, Bauplan Nr. 163): endet eine verworfene Zeit an der ersten Zeile ``G`` einer neuen
Statistik der heutigen Entität (die Lücken-Zeile trägt ``stand_neu_null``; U3-K4: oder «Falsch seit» liegt auf ``G``, dann
trägt die Korrektur-Zeile es), setzt die Hülle im Monat von ``G`` Anker 0 an ``G`` — die erste Zeile zählt ab HAs Nullpunkt
wie bei «beide» (``_nullpunkt_teile``). U3-K4 (K3-B5): führt ein späterer angesetzter Wechsel «bleiben» von dieser Entität
weiter, beginnt ihr Abschnitt an ``G`` mit Anker 0 (``_mit_nullpunkt``).

**Grenze (a1):** nur, wenn der jüngste angesetzte Wechsel des Schlüssels zur heutigen Entität führt; ein späterer Wechsel
ohne ``ansatz`` lässt den Schlüssel wie vor U2. Zwei Schlüssel mit derselben heutigen Entität sind nicht unterschieden.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Sequence

logger = logging.getLogger(__name__)

_STUNDE = 3600


def _unix(t: datetime) -> float:
    import time

    return time.mktime(t.timetuple())


def _angesetzte(wechsel: dict) -> dict[str, list]:
    """Je Schlüssel die angesetzten Wechsel «bleiben» (aufsteigend nach ``ab_ts``), deren jüngster zur heutigen Entität
    führt — sonst fehlt der Schlüssel."""
    from backend.services.zuordnung_wechsel.zeitpunkt import gleiche_quelle, quelle_aufgeloest, rand_versatz

    aus: dict[str, list] = {}
    for key, liste in (wechsel or {}).items():
        mit = sorted((w for w in liste if rand_versatz(w) is not None), key=lambda w: w.ab_ts)
        if not mit or not all(_ha(w.vorher) and _ha(w.nachher) for w in mit):       # nur Home Assistant → Home Assistant
            continue
        heute = quelle_aufgeloest(liste, datetime.max - timedelta(days=1))
        if gleiche_quelle(heute, mit[-1].nachher) and (heute or {}).get("art") == "ha":
            aus[key] = mit
    return aus


def _ha(q) -> bool:
    return isinstance(q, dict) and q.get("art") == "ha" and bool(q.get("entity_id"))


def abschnitte_des_fensters(zeilen: list, ts_start: float, ts_ende: float) -> list[tuple[str, float, float, bool]]:
    """Die Abschnitte ``(Entität, von, bis, anker_null)`` eines Fensters ``[ts_start, ts_ende)`` über die angesetzten
    Wechsel ``zeilen`` (aufsteigend) — leer, wenn das Fenster nach dem jüngsten ``G`` beginnt (dann gilt die heutige
    Entität wie bisher)."""
    from backend.models.zuordnung_wechsel import ANSATZ_BEIDE

    if not zeilen or ts_start > _unix(zeilen[-1].ab_ts) - _STUNDE:
        return []
    out: list[tuple[str, float, float, bool]] = []
    von, null = float("-inf"), False
    for w in zeilen:
        g = _unix(w.ab_ts) - _STUNDE
        beide = w.ansatz == ANSATZ_BEIDE
        out.append((w.vorher["entity_id"], von, g + (_STUNDE if beide else 0), null))
        von, null = g, beide
    out.append((zeilen[-1].nachher["entity_id"], von, float("inf"), null))
    fenster = []
    for eid, a, b, n in out:
        a2, b2 = max(a, ts_start), min(b, ts_ende)
        if a2 < b2:
            fenster.append((eid, a2, b2, n and a2 == a))     # Anker 0 nur, wenn der Abschnitt im Fenster an G beginnt
    return fenster


async def monatswerte_je_abschnitt(db, anlage_id: int, antworten: Sequence, monate: Sequence) -> list:
    """Die Hülle: je Antwort (``MonatswertResponse``) und Monat ``(jahr, monat)`` die Werte der Schlüssel mit angesetztem
    Wechsel je Geltungsabschnitt (``abschnitte_des_fensters``, ``get_fensterwerte``) unter der heutigen Entität. Ohne
    angesetzten Wechsel die Antworten selbst (bitgleich)."""
    from backend.services.zuordnung_wechsel.zeitpunkt import lade_wechsel

    from backend.services.zuordnung_wechsel.nullpunkt import abschnitte as nullpunkt_abschnitte

    antworten = list(antworten)
    wechsel = await lade_wechsel(db, anlage_id)
    je_key = _angesetzte(wechsel)
    null_alle = nullpunkt_abschnitte(wechsel)
    null = {k: v for k, v in null_alle.items() if k not in je_key and _heute_ist(wechsel[k], v[0])}
    if not je_key and not null:
        return antworten
    from backend.services.ha_statistics_service import _monatsgrenzen_ts, get_ha_statistics_service

    svc = get_ha_statistics_service()
    out = []
    for a, m in zip(antworten, monate):
        if a is None or m is None or None in m:
            out.append(a)
            continue
        ts_start, ts_ende = _monatsgrenzen_ts(*m)
        ersatz = {}
        for eid, teile in [(z[-1].nachher["entity_id"], _mit_nullpunkt(abschnitte_des_fensters(z, ts_start, ts_ende),
                                                                       null_alle.get(k))) for k, z in je_key.items()] \
                + [(eid, _nullpunkt_teile(eid, g, ts_start, ts_ende)) for eid, g in null.values()]:
            if teile:
                wert = await _summe(svc, eid, teile)
                if wert is not None:
                    ersatz[wert.sensor_id] = wert
        out.append(a if not ersatz else _ersetze(a, ersatz))
    return out


def _nullpunkt_teile(eid: str, g: datetime, ts_start: float, ts_ende: float) -> list[tuple[str, float, float, bool]]:
    """U3-K3 «Regel 2»: im Fenster, in dem die neue Statistik beginnt (``ts_start ≤ G < ts_ende``), ein Abschnitt ab ``G`` mit
    Anker 0 — davor führt HA für ``eid`` keine Zeile; sonst keiner (der HA-Leser liest wie bisher)."""
    g_ts = _unix(g)
    return [(eid, g_ts, ts_ende, True)] if ts_start <= g_ts < ts_ende else []


def _heute_ist(liste, eid: str) -> bool:
    from backend.services.zuordnung_wechsel.zeitpunkt import quelle_aufgeloest

    heute = quelle_aufgeloest(liste, datetime.max - timedelta(days=1))
    return isinstance(heute, dict) and heute.get("entity_id") == eid


def _mit_nullpunkt(teile: list[tuple[str, float, float, bool]], null) -> list[tuple[str, float, float, bool]]:
    """U3-K4 (K3-B5): beginnt die Statistik einer Quelle der angesetzten Wechsel in ihrem Abschnitt neu (``null`` =
    ``(Entität, G)`` aus ``nullpunkt.abschnitte``), beginnt ihr Abschnitt an ``G`` mit Anker 0 — davor führt HA für sie keine
    Zeile. Sonst ``teile`` unverändert."""
    if null is None:
        return teile
    eid, g = null
    g_ts = _unix(g)
    return [(e, g_ts, b, True) if e == eid and a <= g_ts < b else (e, a, b, n) for e, a, b, n in teile]


async def _summe(svc, eid: str, teile: list[tuple[str, float, float, bool]]):
    """Die Abschnitte über HA lesen und zu EINEM ``SensorMonatswert`` der heutigen Entität zusammenfassen
    (``core/berechnungen/zaehler_naht.monat_aus_abschnitten``); ``None``, wenn HA keinen Abschnitt führt."""
    from backend.core.berechnungen.zaehler_naht import monat_aus_abschnitten
    from backend.services.ha_statistics_service import SensorMonatswert

    try:
        werte = await asyncio.to_thread(svc.get_fensterwerte, teile)
    except Exception as e:  # noqa: BLE001 — wie der HA-Leser: ohne HA bleibt die Antwort, wie sie ist
        logger.warning("Monat je Abschnitt: HA nicht lesbar: %s: %s", type(e).__name__, e)
        return None
    da = [w for w in werte if w is not None]
    if not da:
        return None
    start, ende, differenz, verworfen, intervalle = monat_aus_abschnitten(
        [(w.start_wert, w.differenz, w.verworfen_kwh, w.intervalle) for w in da])
    return SensorMonatswert(sensor_id=eid, start_wert=start, end_wert=ende, differenz=differenz, einheit=da[0].einheit,
                            verworfen_kwh=verworfen, intervalle=intervalle)


def _ersetze(antwort, ersatz: dict):
    """Die Sensoren der Antwort: vorhandene durch den Wert je Abschnitt ersetzt, fehlende angehängt."""
    alt = list(antwort.sensoren)
    neu = [ersatz.get(w.sensor_id, w) for w in alt] + [w for sid, w in ersatz.items() if sid not in {x.sensor_id for x in alt}]
    return antwort.model_copy(update={"sensoren": neu})


async def sensorwerte_des_monats(anlage, antwort, jahr: int, monat: int):
    """Eine Antwort des laufenden Monats (``api/routes/aktueller_monat``: ``get_monatswerte`` der Anlage) durch die Hülle —
    mit der Sitzung, an der die Anlage hängt; ohne Sitzung (Proben mit einer Attrappe) oder ohne Wechsel unverändert."""
    from sqlalchemy.ext.asyncio import async_object_session

    try:
        db = async_object_session(anlage)
    except Exception:  # noqa: BLE001 — keine ORM-Instanz (Attrappe): keine verzeichneten Wechsel
        db = None
    if db is None or antwort is None:
        return antwort
    (aus,) = await monatswerte_je_abschnitt(db, anlage.id, [antwort], [(jahr, monat)])
    return aus


async def alle_monatswerte(db, anlage_id: int, svc, sensor_ids: list, ab_datum=None) -> list:
    """«Alle Monatswerte» und Import-Vorschau (U2 a2, Messfrage M8a): die Monate der heutigen Entitäten **und** der alten
    Sensoren ihrer angesetzten Wechsel — ein Monat, in dem nur der alte Werte hat, steht in der Liste (die Hülle vor
    ``kanal/bilanz_leser.monatswerte_mit_kanaelen`` setzt seinen Wert unter die heutige Entität). Ohne angesetzten Wechsel
    wörtlich ``svc.get_alle_monatswerte``. Ein hinzugenommener Monat ohne Wert nach der Hülle fällt heraus."""
    from backend.services.zuordnung_wechsel.zeitpunkt import lade_wechsel

    alte = sorted({w.vorher["entity_id"] for zeilen in _angesetzte(await lade_wechsel(db, anlage_id)).values()
                   if zeilen[-1].nachher["entity_id"] in sensor_ids for w in zeilen} - set(sensor_ids))
    antworten = await asyncio.to_thread(_monate_lesen, svc, list(sensor_ids), alte, ab_datum)
    if not alte:
        return antworten
    # Ein Monat nur des alten Sensors trägt hier noch keinen Wert der heutigen Entität: die Hülle setzt ihn (dieselbe, die
    # ``monatswerte_mit_kanaelen`` danach noch einmal anwendet — sie ist idempotent); ein Monat ohne jeden Wert fällt heraus.
    antworten = await monatswerte_je_abschnitt(db, anlage_id, antworten, [(a.jahr, a.monat) for a in antworten])
    return [a for a in antworten if a.sensoren]


def _monate_lesen(svc, sensor_ids: list, alte: list, ab_datum) -> list:
    """Der Recorder-Teil von ``alle_monatswerte`` (synchron, im Thread): ohne alte Sensoren wörtlich
    ``get_alle_monatswerte``; sonst die Monate beider und je Monat die Werte der heutigen Entitäten."""
    from datetime import date

    if not alte:
        return svc.get_alle_monatswerte(sensor_ids, ab_datum)
    out = []
    for m in svc.get_verfuegbare_monate(sensor_ids + alte).monate:
        if ab_datum is None or date(m.jahr, m.monat, 1) >= ab_datum:
            out.append(svc.get_monatswerte(sensor_ids, m.jahr, m.monat))
    return out


async def live_zeilen(db, anlage_id: int) -> dict[str, list]:
    """Live heute/gestern (U2 Lauf b, F8): je heutiger Entität die angesetzten Wechsel «bleiben» ihres Schlüssels — dieselben
    Zeilen wie die Hülle des Monats (``_angesetzte``), für ``abschnitte_des_fensters`` über das Tagesfenster."""
    from backend.services.zuordnung_wechsel.zeitpunkt import lade_wechsel

    return {zeilen[-1].nachher["entity_id"]: zeilen for zeilen in _angesetzte(await lade_wechsel(db, anlage_id)).values()}


def unix(t: datetime) -> float:
    """Örtliche Wand-Uhr ⇒ Epoch, wie die Abschnitte des Fensters rechnen."""
    return _unix(t)


__all__ = ["abschnitte_des_fensters", "alle_monatswerte", "live_zeilen", "monatswerte_je_abschnitt", "sensorwerte_des_monats",
           "unix"]
