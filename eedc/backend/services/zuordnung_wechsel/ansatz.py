"""Ansetzen eines Wechsels «bleiben» zwischen zwei Home-Assistant-Sensoren — **ein** Dienst (Sensorwechsel U2 a2, Rechenweg
``opus-berichte/SENSORWECHSEL-U2-RECHENWEG-2026-11-19.md`` F2/F3, Bauplan Nr. 138, 139, 143, 144).

**Regel** (wie Home Assistant mit zwei Sensoren): der alte Sensor zählt bis zu seinem letzten Wert, der neue ab seinem ersten;
zwischen zwei Sensoren entsteht nie eine Differenz, keine Stunde fällt weg. Eine Wechsel-Zeile mit Grund «Fortsetzung» von einer
HA-Entität zu einer anderen trägt dafür ``ansatz`` (``models/zuordnung_wechsel.py``): ``offen`` (Route, Nachtrag — noch nicht
angesetzt, liest wie eine Naht ohne Rand-Stände), dann ``beide`` oder ``schnitt`` mit den Rand-Ständen.

**F2 — Art und Rand.** T1 = die erste Stundenzeile des neuen Sensors (``ha_statistik_rand.erste_zeile``). **Überlappung**, wenn
der alte nach T1 weiterzählte (``zaehler_naht.ueberlappt``: heutiger letzter Stand ≠ Stand in der Zeile ≤ T1).
* ohne Überlappung ``beide``: G = T1 (die Zeile G zählt beide Sensoren), ``stand_alt_ende`` = der letzte Stand des alten aus HAs
  letzter Stundenzeile (Bauplan Nr. 143 (1): auch für eine gelöschte Entität; das fehlende angebrochene 5-Minuten-Stück fehlt in
  HA genauso), ``stand_neu_null`` = 0 (Stand-Feld: ``state − sum`` der ersten Zeile).
* mit Überlappung ``schnitt``: G = die Stunde des verzeichneten Wechsels (``ab_ts − 1 h``; frühestens T1 + 1 h), beide
  Rand-Stände sind die Stände in der Zeile vor G (der Stand um G).
* ``ab_ts`` = G + 1 h (der erste Stand der neuen Quelle; «zählt ab» = G = ``kanal_quelle.gueltig_ab``).
* **Höhe der Reihe** (Bauplan Nr. 144, M3): die Rand-Stände stehen in der Höhe der gespeicherten Reihe — der gespeicherte Stand
  des alten am Rand, sonst HAs Wert, wenn die Höhe passt (die frühere Prüfung der Korrektur: der letzte
  gespeicherte Stand des alten gleich HAs Summe dort), sonst der letzte gespeicherte. Führt HA den alten nicht mehr (Nr. 143
  (2)): der letzte bei eedc gespeicherte Stand, nur einer aus HAs Statistik — nie ein Live- oder Zustands-Wert. Der Kanal führt
  seinen Versatz selbst aus HAs Zeilen (``zaehler_naht.kanal_ende_alt``).

**F3 — Schritte** (``setze_an``, idempotent; ``lage`` zählt dasselbe lesend — Vorschau = Lauf):
1. alte Quelle bis vor G vervollständigen: fehlende Kanalzeilen aus HA (nur im Spiegel-Abschnitt der alten Entität); fehlende
   Stände der Reihe nur auf passender Höhe (Schritt 3, Nachlauf).
2. Kanal: Zeilen des Schlüssels ab G löschen, Quellzeile bei G mit dem Versatz ``kanal_versatz_neu``, eine spätere Quellzeile
   derselben Entität entfällt; nach dem Commit mit ``neu_spiegeln`` ab G gefüllt; spätere Quellen anderer Entitäten rücken um
   die Änderung des Kanalwerts an ihrer Grenze mit (``zaehler_naht.verschiebung``).
3. Reihe: die Stände zwischen altem und neuem ``ab_ts`` verworfen (auch die Unterstunden-Stände) und im Hintergrund neu gelesen
   (``korrektur.fuelle_staende`` über den Lauf: ab ``ab_ts`` aus der neuen Quelle, davor nur fehlende Stände der alten).
4. ``ab_ts``, Rand-Stände und Art in die Wechsel-Zeile.
5. abhängige abgeleitete Kanäle ab G verwerfen und nach dem Füllen bis jetzt neu schreiben (auch ohne verworfene Zeile —
   Korrekturrunde Lab-K F1), gemerkte Tage verwerfen.

**Grenze (Lab-K F1):** die Lage liest und das Füllen schreibt bis zur selben Stunde — der letzten vollen vor ``jetzt``
(``kanal/korrektur.fuell_ende``, ein Ort). Bis dahin endete das Füllen am Soll-Ende der Leser (70 Minuten Verzug): im
Stundenlauf um :05 fehlte die Stunde des Wechsels bis zum nächsten Lauf, und im Dialog zwischen H:05 und H:10 löschte das
Ansetzen die schon geschriebene Zeile ``H − 1`` ohne sie wieder zu füllen.
6. abgeschlossene Tage ab dem Tag von G, die einen Schlüssel des Felds tragen, im Hintergrund neu bilden (``korrektur_lauf``,
   ohne Sperre: die Zeile trägt keinen Lauf).

**Auslöser:** nach dem Commit der Route (Feld-Route, Preset, «Grund nachtragen»), wenn HA die neue Statistik schon führt; sonst
nach jedem Stundenlauf für offene Zeilen (``offene_ansetzen``). ``kanal/schreiber._spiegel`` lässt einen Schlüssel mit offener
Zeile aus. HA nicht erreichbar, noch keine Zeile des neuen oder ein offener Lauf am Schlüssel ⇒ die Zeile bleibt ``offen``
(``Lage.wartet``) und liest so lange wie eine Naht ohne Rand-Werte. Trägt der Kanal an G keinen Spiegel der alten oder der
neuen Entität (``WARTET_KANAL``), verliert die Zeile ``offen`` und rechnet wie bisher (Korrekturrunde a-K: sonst bliebe sie für
immer offen, und der Stundenlauf spiegelte den Schlüssel nie wieder).

**Korrekturrunde a-K** (Nachmessung a1 + a2): Stand-Felder am Schlüssel erkannt (N1); Grenze im Kanal und Ende des «heutigen»
Stands am nächsten verzeichneten Wechsel (N2, ``_nachbarn``); Mitrücken im Auftrag des Laufs, wiederholbar (N3,
``mitruecken``); zurück in derselben Stunde ohne eigenen Stand dazwischen ⇒ beide Zeilen heben sich auf (N4); Rand-Stand
epoch-genau aus der Zeile (N5, ``_ha_stand``). Nur Home Assistant → Home Assistant (MQTT und Felder ohne Spiegel lesen bei «bleiben» wie bisher, U3).
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Optional

from sqlalchemy import and_, delete, select

from backend.models.zuordnung_wechsel import (
    ANSATZ_BEIDE,
    ANSATZ_OFFEN,
    ANSATZ_OFFEN_SCHNITT,
    ANSATZ_SCHNITT,
    GRUND_FORTSETZUNG,
    ZuordnungWechsel,
)

logger = logging.getLogger(__name__)

_STUNDE = 3600
ANSATZ_WARTET = frozenset({ANSATZ_OFFEN, ANSATZ_OFFEN_SCHNITT})

#: Warum eine Zeile offen bleibt (Vorschau-Feld ``wartet``; die Sätze stehen in ``bleiben.SATZ_WARTET``).
WARTET_HA = "ha_nicht_erreichbar"
WARTET_ZEILE = "noch_keine_zeile"
WARTET_LAUF = "korrektur_lauf_offen"
WARTET_KANAL = "kanal_nicht_ansetzbar"


# ── Welche Zeilen ─────────────────────────────────────────────────────────────


def _eid(q) -> Optional[str]:
    return q.get("entity_id") if isinstance(q, dict) and q.get("art") == "ha" and q.get("entity_id") else None


def ist_ha_wechsel(row) -> bool:
    """Home Assistant → Home Assistant mit zwei verschiedenen Entitäten (nur dort setzt U2 an)."""
    alt, neu = _eid(row.vorher), _eid(row.nachher)
    return alt is not None and neu is not None and alt != neu


def wird_angesetzt(row) -> bool:
    """Eine gültige Fortsetzung zwischen zwei HA-Sensoren — sie bekommt beim Verzeichnen ``ansatz = offen``."""
    return row.grund == GRUND_FORTSETZUNG and row.aufgehoben_durch is None and ist_ha_wechsel(row)


def ist_offen(row) -> bool:
    return row.grund == GRUND_FORTSETZUNG and row.aufgehoben_durch is None and getattr(row, "ansatz", None) in ANSATZ_WARTET


def offene_schluessel(wechsel_je_key: dict) -> frozenset[str]:
    """Die Schlüssel mit einer offenen Zeile — der Stundenlauf spiegelt sie nicht (``kanal/schreiber._spiegel``, F3: sonst setzte
    der Spiegel die neue Quelle vor dem Dienst an)."""
    return frozenset(k for k, liste in (wechsel_je_key or {}).items() if any(ist_offen(w) for w in liste))


# ── Lage (lesend) ─────────────────────────────────────────────────────────────


@dataclass
class Lage:
    wechsel_id: int
    anlage_id: int
    sensor_key: str
    alt: str
    neu: str
    ab_alt: datetime
    wartet: Optional[str] = None
    art: Optional[str] = None
    t1: Optional[datetime] = None
    ueberlappung: bool = False
    g: Optional[datetime] = None
    stand_alt_ende: Optional[float] = None
    stand_neu_null: Optional[float] = None
    #: Rand alt aus HAs Statistik (``False``: HA führt den alten nicht mehr — Rückfall «gespeicherter Stand»).
    alt_von_ha: bool = True
    #: Höhe der Reihe gegen HA (``None`` = nicht prüfbar); passt sie nicht, füllt eedc keine Stände des alten.
    hoehe_passt: Optional[bool] = None
    kanal_id: Optional[int] = None
    kanal_versatz: Optional[float] = None
    #: Die Kanalzeilen des alten, die Schritt 1 aus HA ergänzt ``(start_ts, Zeile)``.
    kanal_ergaenzen: list = field(default_factory=list)
    #: Die Zeit, deren Stände Schritt 3 verwirft, und die, deren Stände der Nachlauf neu liest.
    staende_weg: Optional[tuple[datetime, datetime]] = None
    staende_neu: Optional[tuple[datetime, datetime]] = None
    tage: list[date] = field(default_factory=list)
    #: a-K N2: G des nächsten verzeichneten Wechsels des Schlüssels (``None`` = keiner) — dort endet, was dieser Wechsel
    #: im Kanal neu schreibt, und der «heutige» Stand des alten für die Überlappung.
    grenze_g: Optional[datetime] = None
    #: a-K N4: ein Wechsel zurück in derselben Stunde, bevor die Quelle dazwischen einen eigenen Stand hatte — die Zeile,
    #: mit der sich diese aufhebt.
    aufheben_mit: Optional[int] = None
    #: Lab-K F5: ab wann die bisherige Quelle gilt (der vorige verzeichnete Wechsel des Felds) — die früheste Stunde für
    #: «Der neue Sensor zählt ab» (``bleiben.bereich``); ``None`` = kein voriger Wechsel.
    vorige_grenze: Optional[datetime] = None
    #: Lab-K W3: ``beide`` — führt HA für den alten Sensor in der Stunde G eine Zeile (``None`` = nicht geprüft)?
    alt_in_g: Optional[bool] = None

    @property
    def ab_neu(self) -> Optional[datetime]:
        return None if self.g is None else self.g + timedelta(hours=1)


def _ts(t: datetime) -> int:
    return int(t.timestamp())


def _stunde(t: datetime) -> datetime:
    return t.replace(minute=0, second=0, microsecond=0)


async def _ha(abruf, *a):
    from backend.services.zuordnung_wechsel.korrektur import ha_abruf

    return await ha_abruf(asyncio.to_thread(abruf, *a))


async def _zeile_bis(svc, eid: str, ts: int) -> Optional[dict]:
    return await _ha(svc.get_stundenzeile_bis, eid, float(ts))


async def _letzter_stand(db, anlage_id: int, key: str, vor: datetime, *, genau: bool = False,
                         nur_ha: bool = False) -> Optional[tuple[datetime, float]]:
    """Der letzte gespeicherte Stand vor ``vor`` (``genau``: der Stand um ``vor`` selbst); ``nur_ha``: nur einer aus HAs
    Statistik (Bauplan Nr. 143 (2) — nie ein Live- oder Zustands-Wert)."""
    from backend.models.sensor_snapshot import SensorSnapshot
    from backend.services.snapshot.source import SnapshotSource

    bed = [SensorSnapshot.anlage_id == anlage_id, SensorSnapshot.sensor_key == key, SensorSnapshot.wert_kwh.is_not(None),
           SensorSnapshot.zeitpunkt == vor if genau else SensorSnapshot.zeitpunkt < vor]
    if nur_ha:
        bed.append(SensorSnapshot.quelle == SnapshotSource.HA_STATISTICS)
    z = (await db.execute(select(SensorSnapshot.zeitpunkt, SensorSnapshot.wert_kwh).where(and_(*bed))
                          .order_by(SensorSnapshot.zeitpunkt.desc()).limit(1))).one_or_none()
    return None if z is None else (z[0], float(z[1]))


async def _art_und_g(la: Lage, row, svc, bis_ts: int, stand: bool) -> Optional[dict]:
    """F2: T1, Überlappung, Art und G. Returns die erste Zeile des neuen (``None`` = HA führt ihn noch nicht). Der «heutige»
    Stand des alten endet am nächsten verzeichneten Wechsel des Schlüssels (``la.grenze_g``, a-K N2): zählt der alte erst
    danach wieder, ist das keine Überlappung mit dem neuen."""
    from backend.core.berechnungen.zaehler_naht import ueberlappt
    from backend.services.ha_statistik_rand import erste_zeile

    erste = await _ha(erste_zeile, svc, la.neu, float(bis_ts))
    if erste is None:
        return None
    t1 = int(round(erste["start_ts"]))
    la.t1 = datetime.fromtimestamp(t1)
    spalte = "state" if stand else "sum"
    ende = bis_ts if la.grenze_g is None else min(bis_ts, _ts(la.grenze_g) - _STUNDE)
    heute, bei_t1 = await _zeile_bis(svc, la.alt, ende), await _zeile_bis(svc, la.alt, t1)
    la.alt_von_ha = heute is not None
    la.ueberlappung = ueberlappt(None if heute is None else heute.get(spalte), None if bei_t1 is None else bei_t1.get(spalte))
    if row.ansatz == ANSATZ_OFFEN_SCHNITT or la.ueberlappung:
        la.art = ANSATZ_SCHNITT
        la.g = max(row.ab_ts - timedelta(hours=1), la.t1 + timedelta(hours=1))      # zulässig: T1 < G
        if la.vorige_grenze is not None:     # U3-K (LK-B3): nie vor dem vorigen Wechsel, auch nicht die Vorgabe
            la.g = max(la.g, _stunde(la.vorige_grenze))
    else:
        la.art, la.g = ANSATZ_BEIDE, la.t1
        # Lab-K W3: führt HA für den alten in der Stunde G eine Zeile? (Sonst zählt die Stunde nur den neuen.)
        la.alt_in_g = bei_t1 is not None and int(round(bei_t1["start_ts"])) == t1
    return erste


async def _ha_stand(svc, eid: str, zeile: Optional[dict], key: str) -> Optional[float]:
    """Der Wert, den der Schreiber der Reihe aus dieser HA-Zeile speichern würde (``get_value_at`` um ihr Ende) — **genau
    diese Zeile**: das Ende als Zeitpunkt mit Zone (``get_value_at`` rechnet ihn über ``timestamp()`` epoch-genau), nicht über
    die Wand-Uhr, die in der doppelten Herbststunde die erste der beiden Zeilen träfe (Korrekturrunde a-K, N5)."""
    from datetime import timezone

    from backend.services.snapshot.keys import ist_stand_sensor_key

    if zeile is None:
        return None
    ende = datetime.fromtimestamp(int(round(zeile["start_ts"])) + _STUNDE, tz=timezone.utc)
    return await _ha(svc.get_value_at, eid, ende, 10, False, ist_stand_sensor_key(key))


async def _rand_reihe(db, la: Lage, row, svc, erste: dict, stand: bool) -> None:
    """Die Rand-Stände in der Höhe der Reihe und die Zeiten, deren Stände verworfen und neu gelesen werden."""
    from backend.core.berechnungen.zaehler_naht import nullpunkt_neu
    from backend.core.berechnungen.zaehler_naht import stand_passt_zum_spiegel

    beide = la.art == ANSATZ_BEIDE
    s_alt = la.ab_neu if beide else la.g                                   # Zeit des Rand-Stands des alten
    ha_alt = await _ha_stand(svc, la.alt, await _zeile_bis(svc, la.alt, _ts(s_alt) - _STUNDE), la.sensor_key) \
        if la.alt_von_ha else None
    gespeichert = await _letzter_stand(db, row.anlage_id, la.sensor_key, s_alt, genau=True) if s_alt < la.ab_alt else None
    zl = await _letzter_stand(db, row.anlage_id, la.sensor_key, min(s_alt, la.ab_alt), nur_ha=not la.alt_von_ha)
    if zl is not None and la.alt_von_ha:
        ha_zl = await _ha(svc.get_value_at, la.alt, zl[0], 10, False, stand)
        la.hoehe_passt = None if ha_zl is None else stand_passt_zum_spiegel(zl[1], ha_zl, 0.0)
    passt = la.alt_von_ha and la.hoehe_passt is not False
    if gespeichert is not None:
        la.stand_alt_ende = gespeichert[1]
    elif passt and ha_alt is not None:
        la.stand_alt_ende = ha_alt
    else:
        la.stand_alt_ende = None if zl is None else zl[1]
    if beide:
        la.stand_neu_null = nullpunkt_neu(erste.get("state"), erste.get("sum")) if stand else 0.0
    else:
        la.stand_neu_null = await _ha_stand(svc, la.neu, await _zeile_bis(svc, la.neu, _ts(la.g) - _STUNDE), la.sensor_key)
    lo, hi = min(la.ab_neu, la.ab_alt), max(la.ab_neu, la.ab_alt)
    la.staende_weg = (lo, hi) if lo < hi else None
    von = zl[0] + timedelta(hours=1) if (passt and zl is not None) else la.ab_neu
    von = min(von, la.ab_neu)
    la.staende_neu = (von, hi) if von < hi else None


async def _kanal_basis(db, kanal, g: int) -> tuple[Optional[int], Optional[float], Any]:
    """Die letzte Kanalzeile vor G: ``(start_ts, Kanalwert mit Versatz, Quelle)``."""
    from backend.models.kanal import KanalQuelle
    from backend.services.kanal.korrektur import _referenz

    ref = await _referenz(db, kanal, g)
    if ref is None:
        return None, None, None
    q = (await db.execute(select(KanalQuelle).where(and_(KanalQuelle.kanal_id == kanal.id, KanalQuelle.gueltig_ab <= ref[0]))
                          .order_by(KanalQuelle.gueltig_ab.desc()).limit(1))).scalar_one_or_none()
    return ref[0], ref[1], q


async def _ergaenzen(db, la: Lage, kanal, svc, basis_ts: int, quelle) -> tuple[int, Optional[float]]:
    """Schritt 1 (lesend): die Kanalzeilen der alten Entität nach der letzten bis ``G − 1 h`` aus HA, nur in ihrem
    Spiegel-Abschnitt. Returns die neue Basis ``(start_ts, Kanalwert)`` — die letzte ergänzte Zeile."""
    from backend.models.kanal import FAMILIE_SPIEGEL
    from backend.services.kanal.nachfuellen import _zeilen_aus_ha

    g = _ts(la.g)
    if quelle is None or quelle.familie != FAMILIE_SPIEGEL or quelle.statistic_id != la.alt or basis_ts >= g - _STUNDE:
        return basis_ts, None
    gelesen = await _ha(svc.get_stundenzeilen_mehrere, {la.alt: float(basis_ts)}, float(g - _STUNDE))
    if la.alt not in gelesen:
        return basis_ts, None
    meta, roh = gelesen[la.alt]
    zeilen = _zeilen_aus_ha(kanal.id, kanal.art, meta, roh) or []
    spalte = "state" if kanal.art == "stand" else "sum"
    zeilen = [z for z in zeilen if z[spalte] is not None]
    if not zeilen:
        return basis_ts, None
    la.kanal_ergaenzen = zeilen
    return zeilen[-1]["start_ts"], float(zeilen[-1][spalte]) + float(quelle.offset)


async def _rand_kanal(db, la: Lage, svc, erste: dict) -> Optional[str]:
    """Der Versatz der Quellzeile des neuen bei G (Kanal aus HAs Zeilen). Returns ``WARTET_KANAL``, wenn der Kanal an G
    keinen Spiegel der alten oder der neuen Entität trägt (eine Mitschrift oder eine andere Quelle davor — U3)."""
    from backend.core.berechnungen.zaehler_naht import kanal_ende_alt, kanal_versatz_neu, nullpunkt_neu
    from backend.models.kanal import FAMILIE_SPIEGEL
    from backend.services.kanal.angaben import kanal_des_schluessels
    from backend.services.kanal.korrektur import _ha_wert

    kanal = await kanal_des_schluessels(db, la.anlage_id, la.sensor_key)
    if kanal is None:
        return None
    la.kanal_id = kanal.id
    g = _ts(la.g)
    basis_ts, kanalwert, quelle = await _kanal_basis(db, kanal, g)
    if basis_ts is None:
        kanalwert = 0.0                             # der Kanal beginnt erst mit dem neuen Sensor
    elif quelle is None or quelle.statistic_id not in (la.alt, la.neu) or quelle.familie != FAMILIE_SPIEGEL:
        return WARTET_KANAL
    if basis_ts is not None:
        neu_basis, neu_wert = await _ergaenzen(db, la, kanal, svc, basis_ts, quelle)
        if neu_wert is not None:
            basis_ts, kanalwert = neu_basis, neu_wert
    ziel = g if la.art == ANSATZ_BEIDE else g - _STUNDE
    ha_ziel = ha_basis = None
    if la.alt_von_ha and basis_ts is not None:
        z = await _zeile_bis(svc, la.alt, ziel)
        b = await _zeile_bis(svc, la.alt, basis_ts)
        if z is not None and b is not None:
            ha_ziel = await _ha_wert(svc, kanal, la.alt, int(round(z["start_ts"])))
            ha_basis = await _ha_wert(svc, kanal, la.alt, int(round(b["start_ts"])))
    ende = kanal_ende_alt(kanalwert, ha_ziel, ha_basis)
    if la.art == ANSATZ_BEIDE:
        null = nullpunkt_neu(erste.get("state"), erste.get("sum")) if kanal.art == "stand" else 0.0
    else:
        z = await _zeile_bis(svc, la.neu, g - _STUNDE)
        null = 0.0 if z is None else (await _ha_wert(svc, kanal, la.neu, int(round(z["start_ts"]))) or 0.0)
    la.kanal_versatz = kanal_versatz_neu(ende, null)
    return None


async def _tage(db, row, la: Lage, jetzt: datetime) -> list[date]:
    """Schritt 6: die abgeschlossenen Tage ab dem Tag von G, deren Tageszeile einen Schlüssel des Felds trägt."""
    from backend.models.anlage import Anlage
    from backend.services import verwerfen_vor_quellbeginn as vq
    from backend.services.zuordnung_wechsel.korrektur import Auftrag, tage_neu_bilden_liste

    anlage = (await db.execute(select(Anlage).where(Anlage.id == row.anlage_id))).scalar_one()
    ziele = await vq.bestand_ziele(db, anlage, la.sensor_key)
    a = Auftrag(anlage_id=row.anlage_id, sensor_key=la.sensor_key, falsch_seit=la.g, ab=_stunde(jetzt), vorher=row.vorher,
                nachher=row.nachher)
    return await tage_neu_bilden_liste(db, a, ziele)


async def _nachbarn(db, row, la: Lage) -> None:
    """a-K N2/N4: der nächste verzeichnete Wechsel des Schlüssels nach dieser Zeile (``la.grenze_g`` = sein G) und — am
    Wechsel zurück in derselben Stunde — die vorige Zeile, mit der sich diese aufhebt (``la.aufheben_mit``): sie ging von
    der neuen Quelle dieser Zeile zur alten, und die alte hat dazwischen keinen eigenen Stand geschrieben."""
    from backend.services.zuordnung_wechsel.abfrage import _gleich
    from backend.services.zuordnung_wechsel.nachtrag import ist_quellenwechsel
    from backend.services.zuordnung_wechsel.zeitpunkt import ab_ts_aus, lade_wechsel

    erklaert = getattr(row, "erklaert_ts", None)
    if erklaert is None:
        return
    alle = (await lade_wechsel(db, row.anlage_id)).get(row.sensor_key, ())
    la.vorige_grenze = _vorige_grenze(alle, row, erklaert)
    andere = [w for w in alle if w.id != row.id and ist_quellenwechsel(w)]
    spaeter = [w.ab_ts for w in andere if w.erklaert_ts > erklaert]
    if spaeter:
        la.grenze_g = min(spaeter) - timedelta(hours=1)
    frueher = sorted((w for w in andere if w.erklaert_ts < erklaert), key=lambda w: (w.erklaert_ts, w.id or 0))
    if row.id is None or not frueher:
        return
    p = frueher[-1]
    if (p.grund == GRUND_FORTSETZUNG and _gleich(p.vorher, row.nachher) and _gleich(p.nachher, row.vorher)
            and not await _hat_staende(db, row, p.ab_ts, ab_ts_aus(erklaert))):
        la.aufheben_mit = p.id


def _vorige_grenze(alle, row, erklaert: datetime) -> Optional[datetime]:
    """Lab-K F5: ab wann die bisherige Quelle gilt — der jüngste verzeichnete Wechsel des Felds vor dieser Zeile (nicht
    aufgehoben) ab seinem ``ab_ts`` (G + 1 h). Früher darf «Der neue Sensor zählt ab» nicht liegen, sonst überschriebe das
    Ansetzen die Zeit der Quelle davor."""
    frueher = sorted((w for w in alle if w.id != row.id and w.aufgehoben_durch is None
                      and w.erklaert_ts is not None and w.erklaert_ts < erklaert), key=lambda w: (w.erklaert_ts, w.id or 0))
    if not frueher:
        return None
    return frueher[-1].ab_ts


async def _hat_staende(db, row, von: datetime, bis: datetime) -> bool:
    from backend.models.sensor_snapshot import SensorSnapshot

    if von >= bis:
        return False
    return (await db.execute(select(SensorSnapshot.id).where(and_(
        SensorSnapshot.anlage_id == row.anlage_id, SensorSnapshot.sensor_key == row.sensor_key,
        SensorSnapshot.zeitpunkt >= von, SensorSnapshot.zeitpunkt < bis)).limit(1))).first() is not None


def _ab_alt(row) -> datetime:
    """Bis wann die Reihe die Stände der alten Quelle trägt: ``ab_ts`` — bei «Der neue Sensor zählt ab» (``offen_schnitt``,
    Lauf b: ``ab_ts`` = gewählte Stunde + 1 h, früher als der Wechsel) die erste volle Stunde des Wechsels; bis dorthin
    schrieb eedc die Stände aus dem alten Sensor, und Schritt 3 verwirft sie ab dem neuen ``ab_ts``."""
    from backend.services.zuordnung_wechsel.zeitpunkt import ab_ts_aus

    erklaert = getattr(row, "erklaert_ts", None)
    if row.ansatz != ANSATZ_OFFEN_SCHNITT or erklaert is None:
        return row.ab_ts
    return max(row.ab_ts, ab_ts_aus(erklaert))


async def lage(db, row, *, ha_svc, jetzt: Optional[datetime] = None) -> Lage:
    """Was ``setze_an`` an dieser Zeile täte (lesend; Vorschau = Lauf). ``ha_svc`` ``None`` ⇒ ``wartet = WARTET_HA``.
    HA-Abrufe sehen nur Zeilen bis zur letzten vollen Stunde vor ``jetzt``."""
    from backend.services.kanal.katalog import zaehler_art
    from backend.services.snapshot.keys import ist_stand_sensor_key
    from backend.services.zuordnung_wechsel import korrektur_lauf
    from backend.services.zuordnung_wechsel.korrektur import KorrekturNichtStartbar

    jetzt = jetzt or datetime.now()
    la = Lage(row.id, row.anlage_id, row.sensor_key, _eid(row.vorher), _eid(row.nachher), _ab_alt(row))
    if await korrektur_lauf.offener_lauf(db, row.anlage_id, row.sensor_key) is not None:
        la.wartet = WARTET_LAUF
        return la
    if ha_svc is None or not ha_svc.is_available:
        la.wartet = WARTET_HA
        return la
    from backend.services.kanal.korrektur import fuell_ende

    await _nachbarn(db, row, la)
    bis_ts = fuell_ende(_ts(jetzt))          # Lab-K F1: dieselbe Stunde, bis zu der ``_schreiben`` füllt
    # a-K N1: ein Stand-Feld (Gas, Wasser, Öl) am Schlüssel erkennen — ``zaehler_art`` kennt es ohne Kanal nicht.
    stand = ist_stand_sensor_key(row.sensor_key) or zaehler_art(row.sensor_key, None) == "stand"
    try:
        erste = await _art_und_g(la, row, ha_svc, bis_ts, stand)
        if erste is None:
            la.wartet = WARTET_ZEILE
            return la
        la.wartet = await _rand_kanal(db, la, ha_svc, erste)
        if la.wartet is None:
            await _rand_reihe(db, la, row, ha_svc, erste, stand)
            la.tage = await _tage(db, row, la, jetzt)
    except KorrekturNichtStartbar:
        la.wartet = WARTET_HA
    return la


def vorschau(la: Lage) -> dict[str, Any]:
    """Die Lage als Daten (Gerüst für Lauf b, keine Wortlaute)."""
    def iso(t):
        return None if t is None else t.isoformat()
    return {"wechsel_id": la.wechsel_id, "sensor_key": la.sensor_key, "wartet": la.wartet, "art": la.art,
            "erste_zeile_neu": iso(la.t1), "ueberlappung": la.ueberlappung, "zaehlt_ab": iso(la.g), "ab_ts": iso(la.ab_neu),
            "stand_alt_ende": la.stand_alt_ende, "stand_neu_null": la.stand_neu_null, "kanal_versatz": la.kanal_versatz,
            "alt_aus_home_assistant": la.alt_von_ha, "hoehe_passt": la.hoehe_passt,
            "staende_neu": None if la.staende_neu is None else [iso(t) for t in la.staende_neu],
            "tage_neu": [d.isoformat() for d in la.tage]}


# ── Ausführung ────────────────────────────────────────────────────────────────


async def _kanal_umschreiben(db, la: Lage) -> Optional[dict]:
    """Schritte 1 und 2 im Kanal (ohne Füllen). Returns das Mitrücken (F4) — ``{grenze, vorher, offsets}``: die Grenze der
    nächsten fremden Quelle, der Kanalwert davor und die Versätze der Quellen ab ihr vor dem Ansetzen (``None`` = keine
    Grenze). Es steht im Auftrag des Laufs, damit der Nachlauf es nachholt (a-K N3)."""
    from backend.models.kanal import FAMILIE_SPIEGEL, KanalQuelle
    from backend.services.kanal.korrektur import _referenz
    from backend.services.kanal.nachfuellen import _einfuegen
    from backend.services.kanal.verwerfen import loesche_zeilen_zwischen

    g = _ts(la.g)
    if la.kanal_ergaenzen:
        await _einfuegen(db, la.kanal_ergaenzen)
    quellen = list((await db.execute(select(KanalQuelle).where(KanalQuelle.kanal_id == la.kanal_id)
                                     .order_by(KanalQuelle.gueltig_ab))).scalars().all())
    # a-K N2: Grenze ist die nächste Quelle, die nicht die neue Entität dieses Wechsels ist (auch eine spätere Quelle der
    # alten: die Rückkehr eines späteren Wechsels), oder eine Quelle ab dem nächsten verzeichneten Wechsel.
    nxt = None if la.grenze_g is None else _ts(la.grenze_g)
    fremd = next((q for q in quellen if q.gueltig_ab > g and (q.statistic_id != la.neu or (nxt is not None and q.gueltig_ab >= nxt))),
                 None)
    x = None if fremd is None else fremd.gueltig_ab
    vorher = None
    if x is not None:
        k = await _kanal(db, la.kanal_id)
        ref = await _referenz(db, k, x)
        vorher = None if ref is None else ref[1]
    await loesche_zeilen_zwischen(db, la.kanal_id, g, x if x is not None else 2 ** 40)
    for q in quellen:
        if q.gueltig_ab >= g and (x is None or q.gueltig_ab < x) and q.statistic_id in (la.alt, la.neu):
            await db.delete(q)
    await db.flush()
    db.add(KanalQuelle(kanal_id=la.kanal_id, gueltig_ab=g, familie=FAMILIE_SPIEGEL, statistic_id=la.neu,
                       offset=float(la.kanal_versatz)))
    await db.flush()
    if x is None:
        return None
    return {"grenze": x, "vorher": vorher,
            "offsets": {str(q.gueltig_ab): float(q.offset) for q in quellen if q.gueltig_ab >= x}}


async def _kanal(db, kanal_id: int):
    from backend.models.kanal import Kanal

    return (await db.execute(select(Kanal).where(Kanal.id == kanal_id))).scalar_one()


async def _staende_verwerfen(db, row, la: Lage) -> int:
    """Schritt 3 (Verwerfen): alle Stände des Schlüssels zwischen altem und neuem ``ab_ts`` (auch die Unterstunden-Stände)."""
    from backend.models.sensor_snapshot import SensorSnapshot

    if la.staende_weg is None:
        return 0
    von, bis = la.staende_weg
    r = await db.execute(delete(SensorSnapshot).where(and_(
        SensorSnapshot.anlage_id == row.anlage_id, SensorSnapshot.sensor_key == la.sensor_key,
        SensorSnapshot.zeitpunkt >= von, SensorSnapshot.zeitpunkt < bis)))
    return int(r.rowcount or 0)


async def _schreiben(db, row, la: Lage, lauf: str, jetzt: datetime, svc) -> dict[str, Any]:
    """Schritte 1–6 in einer Transaktion (ohne Füllen): Kanal, Stände verwerfen, Wechsel-Zeile, abgeleitete Kanäle, Lauf."""
    from backend.services.kanal import merken
    from backend.services.kanal.abgeleitet import verwerfe_ab
    from backend.services.kanal.korrektur import KanalKorrektur, abhaengige_abgeleitete, fuell_ende, gehoert_zu
    from backend.services.zuordnung_wechsel import korrektur_lauf
    from backend.services.zuordnung_wechsel.korrektur import nachlauf_auftrag
    from backend.services.zuordnung_wechsel.zeitpunkt import vergiss

    mit = None
    if la.kanal_id is not None:
        mit = await _kanal_umschreiben(db, la)
    geloescht = await _staende_verwerfen(db, row, la)
    row.ansatz, row.ab_ts = la.art, la.ab_neu
    row.stand_alt_ende, row.stand_neu_null = la.stand_alt_ende, la.stand_neu_null
    if la.aufheben_mit is not None:          # a-K N4: zurück in derselben Stunde — beide Zeilen heben sich auf (keine Naht)
        vorige = (await db.execute(select(ZuordnungWechsel).where(ZuordnungWechsel.id == la.aufheben_mit))).scalar_one()
        vorige.aufgehoben_durch, row.aufgehoben_durch = row.id, vorige.id
    kk = KanalKorrektur(la.sensor_key, kanal_id=la.kanal_id, w0=_ts(la.g), h0=_ts(la.g) if la.kanal_id else None,
                        versatz=la.kanal_versatz)
    kk.abgeleitet_familien = await abhaengige_abgeleitete(db, row.anlage_id, la.sensor_key)
    kk.abgeleitet_verworfen = await verwerfe_ab(db, row.anlage_id, _ts(la.g),
                                                nur=lambda k: gehoert_zu(kk.abgeleitet_familien, k))
    bis_ts = fuell_ende(_ts(jetzt))
    staende = None if la.staende_neu is None else {"key": la.sensor_key, "von": la.staende_neu[0].isoformat(),
                                                   "bis": la.staende_neu[1].isoformat()}
    nach = nachlauf_auftrag(kk, svc, bis_ts, jetzt, staende=staende)
    if nach is not None:
        nach["abgeleitet_immer"] = True     # Lab-K F1: die abhängigen abgeleiteten Kanäle bis jetzt fortschreiben
        if mit is not None:
            nach["mitruecken"] = mit
    if la.tage or nach is not None:
        await korrektur_lauf.anlegen(db, lauf, row.anlage_id, la.sensor_key, la.tage, fuellen=nach,
                                     art=korrektur_lauf.ART_ANSETZEN)
    await db.flush()
    vergiss(db, row.anlage_id)
    merken.invalidiere(row.anlage_id, db=db)
    return {"lauf": lauf, "kk": kk, "bis_ts": bis_ts, "jetzt": jetzt, "nachlauf": nach, "mitruecken": mit,
            "staende_geloescht": geloescht}


async def mitruecken(sitzungen, kanal_id: Optional[int], m: Optional[dict]) -> float:
    """Spätere Quellen einer anderen Entität rücken um die Änderung des Kanalwerts an ihrer Grenze mit (F4). Setzt die
    Versätze aus ``m["offsets"]`` + Verschiebung (nicht dazu addiert) — wiederholbar: der Nachlauf des Laufs holt es nach,
    wenn das Füllen nach dem Commit scheitert oder der Prozess neu startet (a-K N3)."""
    from backend.core.berechnungen.zaehler_naht import verschiebung
    from backend.models.kanal import KanalQuelle
    from backend.services.kanal.korrektur import _referenz

    if not m or kanal_id is None:
        return 0.0
    x = int(m["grenze"])
    async with sitzungen() as db:
        ref = await _referenz(db, await _kanal(db, kanal_id), x)
        d = verschiebung(None if ref is None else ref[1], m.get("vorher"))
        for q in (await db.execute(select(KanalQuelle).where(and_(KanalQuelle.kanal_id == kanal_id,
                                                                  KanalQuelle.gueltig_ab >= x)))).scalars().all():
            alt = (m.get("offsets") or {}).get(str(q.gueltig_ab))
            if alt is not None:
                q.offset = float(alt) + d
    return d


async def _nach_dem_commit(sitzungen, anlage_id: int, la: Lage, erg: dict, svc, *, starten: bool) -> dict[str, Any]:
    """Kanal füllen (``neu_spiegeln`` ab G), spätere Quellen mitrücken, abgeleitete Kanäle neu schreiben; Stände und Tage
    macht der Hintergrund-Lauf. Scheitert das Füllen, holt es der Lauf nach (stündlich, nach dem Start)."""
    from backend.services.kanal.korrektur import fuelle_kanal, schreibe_abgeleitete_nach
    from backend.services.zuordnung_wechsel import korrektur_lauf

    kk, nach = erg["kk"], erg["nachlauf"]
    s = {"lauf": erg["lauf"] if (la.tage or nach is not None) else None, "kanal_neu_gespiegelt": 0, "abgeleitet_neu": 0}
    staende = nach is not None and isinstance(nach.get("staende"), dict)
    try:
        s["kanal_neu_gespiegelt"] = await fuelle_kanal(sitzungen, anlage_id, kk, ha_svc=svc, bis_ts=erg["bis_ts"])
        s["verschiebung"] = await mitruecken(sitzungen, la.kanal_id, erg["mitruecken"])
        # Lab-K F1: bis jetzt und auch ohne verworfene Zeile — der Stundenlauf hat den Schlüssel mit offener Zeile ausgelassen.
        s["abgeleitet_neu"] = await schreibe_abgeleitete_nach(sitzungen, anlage_id, kk, erg["jetzt"], immer=True)
    except Exception as e:  # noqa: BLE001 — der Lauf holt den Nachlauf nach (Zustand ``fuellen``)
        logger.warning("Ansetzen %s: Füllen nach dem Commit gescheitert, der Lauf holt es nach: %s: %s",
                       la.sensor_key, type(e).__name__, e)
        s["fuellen_offen"] = True
    else:
        if s["lauf"] is not None and nach is not None:
            await korrektur_lauf.nachlauf_erledigt(sitzungen, s["lauf"], s["kanal_neu_gespiegelt"], s["abgeleitet_neu"],
                                                   staende_offen=staende)
    if s["lauf"] is not None and starten:
        korrektur_lauf.starten(s["lauf"], sitzungen=sitzungen)
    return s


async def setze_an(sitzungen, wechsel_id: int, *, ha_svc=None, jetzt: Optional[datetime] = None,
                   starten: bool = True) -> dict[str, Any]:
    """Den Wechsel ansetzen (F3, idempotent: eine angesetzte Zeile bleibt, wie sie ist). Wirft nie — eine Zeile, die nicht
    angesetzt werden kann, bleibt offen. Returns ``{"angesetzt": bool, "lage": vorschau(...), …}``."""
    from backend.services.zuordnung_wechsel.korrektur import KorrekturNichtStartbar, ha_dienst

    jetzt = (jetzt or datetime.now()).replace(microsecond=0)
    try:
        svc = ha_dienst(ha_svc)
    except KorrekturNichtStartbar:
        svc = None
    try:
        async with sitzungen() as db:
            row = (await db.execute(select(ZuordnungWechsel).where(ZuordnungWechsel.id == wechsel_id))).scalar_one_or_none()
            if row is None or not ist_offen(row) or not ist_ha_wechsel(row):
                return {"angesetzt": False, "lage": None, "sensor_key": None if row is None else row.sensor_key}
            la = await lage(db, row, ha_svc=svc, jetzt=jetzt)
            if la.wartet == WARTET_KANAL:
                # a-K «Ungeprüft» (a): trägt der Kanal vor G keinen Spiegel der alten oder neuen Entität, kann eedc den
                # Wechsel nie wie Home Assistant ansetzen — die Zeile bliebe für immer offen und der Stundenlauf spiegelte den
                # Schlüssel nie wieder. Sie rechnet stattdessen wie bisher (Naht ohne Rand-Stände, wie MQTT bei «bleiben»).
                row.ansatz = None
                return {"angesetzt": False, "lage": vorschau(la), "sensor_key": la.sensor_key, "aufgegeben": True}
            if la.wartet is not None:
                return {"angesetzt": False, "lage": vorschau(la), "sensor_key": la.sensor_key}
            anlage_id = row.anlage_id
            erg = await _schreiben(db, row, la, uuid.uuid4().hex[:12], jetzt, svc)
        s = await _nach_dem_commit(sitzungen, anlage_id, la, erg, svc, starten=starten)
    except Exception as e:  # noqa: BLE001 — die Zeile bleibt offen, der nächste Stundenlauf versucht es wieder
        logger.warning("Ansetzen des Wechsels %s gescheitert: %s: %s", wechsel_id, type(e).__name__, e)
        return {"angesetzt": False, "lage": None, "fehler": f"{type(e).__name__}: {e}"}
    return {"angesetzt": True, "lage": vorschau(la), "staende_geloescht": erg["staende_geloescht"], **s}


async def offene_ansetzen(sitzungen=None, *, ha_svc=None, jetzt: Optional[datetime] = None,
                          starten: bool = True) -> list[dict[str, Any]]:
    """Vom Stundenlauf gerufen (``scheduler.sensor_snapshot_job``): jede offene Zeile ansetzen, deren neuer Sensor jetzt eine
    Zeile in HA hat. Wirft nie."""
    from backend.core.database import get_session

    sitzungen = sitzungen or get_session
    try:
        async with sitzungen() as db:
            ids = list((await db.execute(select(ZuordnungWechsel.id).where(and_(
                ZuordnungWechsel.grund == GRUND_FORTSETZUNG, ZuordnungWechsel.aufgehoben_durch.is_(None),
                ZuordnungWechsel.ansatz.in_(sorted(ANSATZ_WARTET)))).order_by(ZuordnungWechsel.id))).scalars().all())
    except Exception as e:  # noqa: BLE001 — der Stundenlauf darf davon nichts merken
        logger.warning("Offene Wechsel ansetzen: %s: %s", type(e).__name__, e)
        return []
    return [await setze_an(sitzungen, i, ha_svc=ha_svc, jetzt=jetzt, starten=starten) for i in ids]


__all__ = ["ANSATZ_WARTET", "Lage", "ist_ha_wechsel", "ist_offen", "lage", "mitruecken", "offene_ansetzen", "offene_schluessel",
           "setze_an", "vorschau", "wird_angesetzt"]
