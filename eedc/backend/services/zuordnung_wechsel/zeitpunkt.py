"""Zuordnung zum Zeitpunkt (Bauplan B-0) — welche Quelle galt für einen Zählerschlüssel um ``z``?

**Regel (Bauplan §2 B-0):** für einen Zeitstempel ``z`` gilt ``vorher`` des **frühesten** nicht aufgehobenen Wechsels mit
``ab_ts > z``, sonst die heutige Zuordnung. Ohne verzeichneten Wechsel gilt für jeden Zeitpunkt die heutige Quelle — **das
Verhalten von vor diesem Vorhaben** (Bedingung für «Golden Master 0»). Die Korrektur mit «Falsch seit» und ihre Lücken-Zeilen
sind seit Weg B, Sitzung B3a, entfernt; eine solche Zeile aus einer älteren Datenbank liest wie ein Wechsel ohne Grund.

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
    aufgehoben_durch: Optional[int] = None
    #: Sekunde der Erklärung (B-4: im MQTT-Kanal schließen die Stände davor die alte Periode).
    erklaert_ts: Optional[datetime] = None
    #: Zeilen-Nummer — die Reihenfolge zweier Wechsel mit gleichem ``ab_ts`` (Bauplan §13 Nr. 66).
    id: Optional[int] = None
    #: Rand-Werte eines Wechsels «bleiben» (U2 a1, F1; ``models/zuordnung_wechsel.py``). Ohne ``ansatz``: wie vor U2.
    ansatz: Optional[str] = None
    stand_alt_ende: Optional[float] = None
    stand_neu_null: Optional[float] = None
    #: Wann eedc die Zeile eingetragen hat (U3-K, B5; ``monatswert_ueberholt``). ``None`` an Bestandszeilen.
    eingetragen_ts: Optional[datetime] = None


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


def quelle_am(wechsel: Optional[list[Wechsel]], z: datetime) -> Antwort:
    """Die Quelle eines Schlüssels um ``z`` (reine Funktion; ``wechsel`` = die Zeilen DIESES Schlüssels, beliebig sortiert)."""
    if not wechsel:
        return HEUTE
    spaetere = [w for w in wechsel if w.aufgehoben_durch is None and w.ab_ts > z]
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
    return Wechsel(row.sensor_key, row.ab_ts, row.vorher, row.nachher, row.grund, row.aufgehoben_durch, row.erklaert_ts,
                   row.id, getattr(row, "ansatz", None), getattr(row, "stand_alt_ende", None),
                   getattr(row, "stand_neu_null", None), getattr(row, "eingetragen_ts", None))


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


def naehte_der_fortsetzung(wechsel: Optional[list[Wechsel]]) -> list:
    """Die Nähte eines Schlüssels (Bauplan B-3): ``ab_ts`` jedes nicht aufgehobenen Wechsels mit Grund «Fortsetzung»,
    aufsteigend. Ein Wechsel ohne Grund ist keine Naht — die Leser lesen dort wie vor diesem Vorhaben (Sitzung 2).

    **Naht mit Rand-Ständen** (U2 a1, Rechenweg F5): ein angesetzter Wechsel «bleiben» (``rand_versatz``) liefert seine
    Naht als ``zaehler_naht.Naht`` mit Versatz — sie teilt nicht, sie hebt. Ein Zeitpunkt, an dem zugleich eine teilende Naht
    liegt, bleibt beides (die teilende gewinnt beim Teilen)."""
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
    if not hebend:
        return sorted(teilend)
    return sorted([*teilend, *hebend], key=lambda n: (n, isinstance(n, Naht)))


def quelle_aufgeloest(wechsel: Optional[list[Wechsel]], z: datetime) -> Optional[dict]:
    """Die Quelle um ``z`` aus den Zeilen allein: ``quelle_am``; gilt dort die heutige Zuordnung (``HEUTE``, kein Wechsel
    nach ``z``), die neue Quelle (``nachher``) des jüngsten gültigen Wechsels bis ``z``. ``None`` = unbekannt (auch: gar kein
    Wechsel bis ``z``). Ohne Blick auf die heutige Zuordnung."""
    q = quelle_am(wechsel, z)
    if isinstance(q, dict):
        return q
    if q is not HEUTE:
        return None
    frueher = [w for w in wechsel or () if w.aufgehoben_durch is None and w.ab_ts <= z]
    if not frueher:
        return None
    n = max(frueher, key=lambda w: (w.ab_ts, w.id if w.id is not None else -1)).nachher
    return n if isinstance(n, dict) and n.get("art") else None


def gleiche_quelle(a: Optional[dict], b: Optional[dict]) -> bool:
    """Dieselbe Quelle (Home Assistant: dieselbe Entität; sonst die gleiche Beschreibung)."""
    if not a or not b or a.get("art") != b.get("art"):
        return False
    return a.get("entity_id") == b.get("entity_id") if a.get("art") == "ha" else a == b


async def fortsetzungs_naehte(db, anlage_id: int, sensor_key: str) -> list:
    """``naehte_der_fortsetzung`` mit dem Laden der Zeilen (je Sitzung gemerkt, ``lade_wechsel``) — die eine Ladestelle
    der Reihen-Leser (Wächter «Reihen-Leser»)."""
    return naehte_der_fortsetzung((await lade_wechsel(db, anlage_id)).get(sensor_key))


async def quelle_zum_zeitpunkt(db, anlage_id: int, sensor_key: str, z: datetime) -> Antwort:
    """``quelle_am`` mit dem Laden der Zeilen (für einzelne Fragen wie das Heilen eines Randes)."""
    return quelle_am((await lade_wechsel(db, anlage_id)).get(sensor_key), z)
