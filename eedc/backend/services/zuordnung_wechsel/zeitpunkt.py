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


def quelle_am(wechsel: Optional[list[Wechsel]], z: datetime) -> Antwort:
    """Die Quelle eines Schlüssels um ``z`` (reine Funktion; ``wechsel`` = die Zeilen DIESES Schlüssels, beliebig sortiert)."""
    if not wechsel:
        return HEUTE
    gueltig = [w for w in wechsel if w.aufgehoben_durch is None]
    for w in gueltig:
        if (w.grund == "korrektur" and w.falsch_seit_ts is not None and w.falsch_seit_ts <= z < w.ab_ts):
            return _quelle_oder_unbekannt(w.nachher)
    spaetere = [w for w in gueltig + _vor_falsch_seit(wechsel, gueltig, z) if w.ab_ts > z]
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
                   row.aufgehoben_durch, row.erklaert_ts, row.id)


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


def naehte_der_fortsetzung(wechsel: Optional[list[Wechsel]]) -> list[datetime]:
    """Die Nähte eines Schlüssels (Bauplan B-3): ``ab_ts`` jedes nicht aufgehobenen Wechsels mit Grund «Fortsetzung»,
    aufsteigend. Ein Wechsel ohne Grund ist keine Naht — die Leser lesen dort wie vor diesem Vorhaben (Sitzung 2)."""
    from backend.models.zuordnung_wechsel import GRUND_FORTSETZUNG

    return sorted(w.ab_ts for w in (wechsel or ()) if w.grund == GRUND_FORTSETZUNG and w.aufgehoben_durch is None)


async def fortsetzungs_naehte(db, anlage_id: int, sensor_key: str) -> list[datetime]:
    """``naehte_der_fortsetzung`` mit dem Laden der Zeilen (je Sitzung gemerkt, ``lade_wechsel``) — die eine Ladestelle
    der Reihen-Leser (Wächter «Reihen-Leser»)."""
    return naehte_der_fortsetzung((await lade_wechsel(db, anlage_id)).get(sensor_key))


async def quelle_zum_zeitpunkt(db, anlage_id: int, sensor_key: str, z: datetime) -> Antwort:
    """``quelle_am`` mit dem Laden der Zeilen (für einzelne Fragen wie das Heilen eines Randes)."""
    return quelle_am((await lade_wechsel(db, anlage_id)).get(sensor_key), z)
