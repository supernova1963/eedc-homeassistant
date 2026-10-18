"""Nachfüllen Spiegel und Neu-Laden — HA-Bauform E2 (Auftrag Punkte 1 und 3, Bauplan §4).

**Nachfüllen (einmalig je Anlage).** Für jeden Kanal, den der Stundenlauf aus HA spiegelt
(Zähler: ``snapshot/writer._build_counter_map``; Mittelwerte: ``schreiber._mean_zuordnung``), holt es
die **ganze Historie der heutigen Entity** aus HAs Langzeitstatistik: ``sum``/``state`` bzw.
``mean``/``min``/``max`` wörtlich, Einheit wie der Stundenlauf (``schreiber._mengen_faktor``).

* **Rückwärts in Blöcken.** Gefüllt wird nur, was VOR der ersten Zeile des Kanals liegt (ab da schreibt
  der Stundenlauf fort). Je Block: die letzte HA-Zeile vor der bisher ersten Kanal-Zeile suchen
  (``get_stundenzeile_bis`` — springt über HA-Lücken), ``BLOCK_STUNDEN`` davor lesen, schreiben,
  committen. **Kein HA-Abruf in einer offenen Schreib-Transaktion:** gelesen wird zwischen zwei
  Sitzungen, geschrieben in einer kurzen eigenen (``sitzungen()`` je Block) — SQLite hält den
  Schreib-Lock nur für das Einfügen eines Blocks, der Stundenlauf wartet höchstens so lange.
* **Wiederaufnehmbar, idempotent.** Der Fortschritt ist die erste Zeile des Kanals selbst: ein
  abgebrochener Lauf setzt dort fort, ein zweiter Lauf findet vor ihr keine HA-Zeile mehr und schreibt
  nichts. Eingefügt wird ``ON CONFLICT DO NOTHING`` — eine Zeile einer anderen Familie bleibt stehen.
* **Nur die Vorgeschichte DERSELBEN Quelle.** Ist die erste Quelle des Kanals nicht der Spiegel der
  heutigen Entity (Sensortausch, MQTT davor), wird nichts gefüllt und das gezählt — die Historie einer
  anderen Entity gehört nicht in diese Reihe (für diese Zeit bleiben die bisherigen Zeilen die Quelle, §3b).
* **Quelle.** Die Zeilen sind wörtlich; ihr ``offset`` ist der der ersten Quelle (dieselbe Rohreihe),
  deren ``gueltig_ab`` wird auf die neue erste Stunde gesenkt.

**Neu-Laden** (``neu_spiegeln``, vom Konsistenzlauf gerufen): ersetzt ab einer Stunde die
**Spiegelzeilen** eines Kanals durch HAs heutige Zeilen — Bestand- und Mitschriftzeilen bleiben stehen.
Je Spiegel-Abschnitt (eine Quelle = eine Entity) blockweise vorwärts; der letzte Block eines Abschnitts
verschiebt in DERSELBEN Transaktion die ``offset`` aller späteren Quellen um die Änderung des Kanalwerts
am Abschnittsende — damit bleibt jedes Δ nach der Naht so, wie HA es nennt.

**Marke je Kanal** (``kanal_nachfuellung``: Kanal + Entity): ein Kanal mit Marke für seine heutige Entity
wird nie wieder bei HA angefragt; ein später zugeordneter Sensor (neuer Kanal) oder eine neue Entity (neue
``kanal_quelle``) hat keine Marke und wird beim nächsten Lauf gefüllt.

**Nachfüllen aus den Stundenständen** (HA-Bauform S3, E-S3-4, Entscheid Gernot S3-E1; seit S4 E-S4-3 «Nachbau 2»,
S4-R-N2; ``nachfuellen_eigene_summe``): für **jeden Zähler-Schlüssel** — auch mit HA-Entity (S3-R9 berichtigt, Bauplan S3
§10f: HA-konform heißt «wo HA liefert, HAs Werte») — werden die stündlichen Stände in ``sensor_snapshots`` zu Zeilen der
Familie Mitschrift, **nur vor der ersten Kanal-Zeile und vor dem Beginn der ersten Quelle** (der Spiegel läuft zuerst; keine
inneren Lücken, S3-R9 (1); verworfene Zeit bleibt leer). Je Herkunft: ``ha_statistics`` (HAs Summen von damals) **wörtlich**
— keine Reset-Regel, kein Deckel, Quelle mit der Kennung ``sensor_snapshots:<key>``; ``mqtt_inbound``/``mqtt_live`` über
dieselbe Rechenstelle wie der Stundenlauf (``schreiber._eigene_summe_zeilen``: HAs 90-%-Regel, Deckel als Schreibfilter),
Quelle mit der MQTT-Kennung. ``live_fallback``-Stände (aus der Leistung abgeleitet) und ``unknown``-Stände (Herkunft
unklassifiziert) werden nicht übernommen (gezählt). Lücken bleiben Lücken (die Menge steht in der Folgestunde, wie HA). Kein
HA nötig; Marke je Kanal. **An jeder Quellgrenze ohne gemeinsamen Anker** (Herkunft wechselt; erste Kanal-Zeile einer
anderen Quelle) trägt die erste Stunde der späteren Quelle keinen Zuwachs — wie ein Quellwechsel im Stundenlauf.
**Reihen jeder Taktung (S4-R-3e):** ein Stand um 00:00 wird die Zeile 23:00 und liegt seit R-3 (Kalendertag, E-S4-1) genau
auf der Tagesgrenze — der Tag ist exakt Stand(00:00 D+1) − Stand(00:00 D), die Stunden-Sicht zeigt ihn als eine Spanne
(Regel (c) der Lese-Schicht: der Zeitraum ist nicht feiner als die Spanne). Das Option-B-Kriterium (``_tagesstaende``,
E-S3-4) ist entfallen; die Aktivität nennt die Zahl der Reihen, die gröber als stündlich sind.
**Zuordnung der Stunde (bestätigt Master E-S3-4):** ein Stand zur vollen Stunde ``Z`` ist der Zählerstand am ENDE von
``[Z − 1 h, Z)`` und wird die Kanalzeile ``start_ts = Z − 3600`` — so trägt HAs Zeile den Stand am Ende ihrer Stunde
(Gleichheit Stand für Stand mit der Eigenen Summe aus den Rohständen: ``test_kanal_eigene_summe_gleichheit.py``).
**Grenze (H-5, benannt):** taucht HA-Statistik für Stände-Stunden später auf, ersetzt der Spiegel sie nicht.

**Auslöser:** ``nachfuellen_nach_dem_start`` (Hintergrund-Aufgabe nach dem Start, alle Zuordnungen) und
``nachfuellen_anstossen`` (vom Stundenlauf NACH seiner Sitzung, nur schon angelegte Kanäle ohne Marke) — beide für den
Spiegel UND die Eigene Summe (``nachfuellen_anlage``).
Fortschritt und Ergebnis als Aktivität in der Schreib-Sitzung (N-532): beim Spiegel, wenn ein Kanal offen war; bei der
Eigenen Summe EIN Eintrag, nur wenn Zeilen geschrieben wurden oder ein Kanal abbrach.

**Stand E2:** wird geschrieben und nachgefüllt, von keiner Sicht gelesen. Die Familie ``bestand`` bleibt **unbelegt** (Entscheid Gernot 06.10., Bauplan §3b): die bisherigen Stunden- und
Tageszeilen werden nicht in Kanäle umgewandelt; sie bleiben die Quelle für Zeiträume, die die Kanäle nicht voll decken.

Schwesterdateien: ``schreiber.py``, ``konsistenz.py``, ``lesen.py``.
"""

from __future__ import annotations

import asyncio
import logging
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import AsyncContextManager, Callable, Optional

from sqlalchemy import and_, delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.kanal import (
    ART_MEAN,
    ART_STAND,
    ART_SUM,
    FAMILIE_MITSCHRIFT,
    FAMILIE_SPIEGEL,
    Kanal,
    KanalNachfuellung,
    KanalQuelle,
    KanalStatistik,
)
from backend.services.kanal import merken

logger = logging.getLogger(__name__)

Sitzungen = Callable[[], AsyncContextManager[AsyncSession]]

#: Stunden je Lese- und Schreibblock (31 Tage). Ein Block eines Zählers sind höchstens 744 Zeilen —
#: das Einfügen hält den Schreib-Lock für Millisekunden.
BLOCK_STUNDEN = 24 * 31
_STUNDE = 3600
_TOL = 1e-9
#: Takt einer Stundenstand-Reihe: eine Reihe, deren unterer Median der Abstände aufeinanderfolgender Stände über einer Stunde
#: liegt, ist «gröber als stündlich» (Tagesstände). Seit S4 (E-S4-3, S4-R-3e) wird sie nachgefüllt wie jede andere und nur in
#: der Aktivität gezählt; bis S3 (Option B) wurde sie übersprungen.
TAKT_MAX_S = 3600


def _unix(dt: datetime) -> int:
    return int(round(dt.timestamp()))


@dataclass
class _Ziel:
    key: str
    eid: str
    art: str
    einheit: str


@dataclass
class NachfuellErgebnis:
    anlage_id: int
    kanaele: int = 0
    gefuellt: int = 0
    zeilen: int = 0
    bloecke: int = 0
    uebersprungen: Counter = field(default_factory=Counter)
    fehler: int = 0
    markiert: int = 0
    #: Seit E-S3-4: das Ergebnis der Eigenen Summe derselben Anlage (``nachfuellen_anlage``), nicht in ``als_dict``.
    eigene_summe: Optional["NachfuellErgebnis"] = field(default=None, repr=False)

    def als_dict(self) -> dict:
        return {"kanaele": self.kanaele, "gefuellt": self.gefuellt, "zeilen": self.zeilen,
                "bloecke": self.bloecke, "markiert": self.markiert,
                "uebersprungen": dict(sorted(self.uebersprungen.items())), "fehler": self.fehler}


# ── Plan (eine kurze Lese-Sitzung) ──────────────────────────────────────────


async def _ziele(db: AsyncSession, anlage, jetzt: datetime) -> list[_Ziel]:
    """Dieselbe Auswahl wie der Stundenlauf: Zähler-Spiegel und Mittelwert-Spiegel."""
    from backend.services.kanal import schreiber as sch

    k = await sch._kontext(db, anlage, jetzt)
    ziele: list[_Ziel] = []
    for key, eid in sorted(k.counter_map.items()):
        art, einheit = sch._art_und_einheit(key, k.invs)
        if art in (ART_SUM, ART_STAND):
            ziele.append(_Ziel(key, eid, art, einheit))
    for key, eid in sorted(sch._mean_zuordnung(k).items()):
        ziele.append(_Ziel(key, eid, ART_MEAN, ""))
    return ziele


async def _erste(db: AsyncSession, anlage_id: int, key: str) -> tuple[Optional[Kanal], Optional[int], Optional[KanalQuelle]]:
    kanal = (await db.execute(
        select(Kanal).where(and_(Kanal.anlage_id == anlage_id, Kanal.key == key))
    )).scalar_one_or_none()
    if kanal is None:
        return None, None, None
    erste_ts = (await db.execute(
        select(func.min(KanalStatistik.start_ts)).where(KanalStatistik.kanal_id == kanal.id)
    )).scalar_one_or_none()
    erste_q = (await db.execute(
        select(KanalQuelle).where(KanalQuelle.kanal_id == kanal.id).order_by(KanalQuelle.gueltig_ab).limit(1)
    )).scalar_one_or_none()
    return kanal, erste_ts, erste_q


# ── Zeilen aus HA ───────────────────────────────────────────────────────────


def _zeilen_aus_ha(kanal_id: int, art: str, meta, roh: list[dict]) -> Optional[list[dict]]:
    """HA-Zeilen → Kanalzeilen, wörtlich (Einheit wie ``schreiber._spiegel`` bzw. ``_mean_spiegel``).
    ``None``: der Stundenlauf spiegelt diesen Sensor nicht (Menge ohne ``sum`` und ohne Energie-Einheit, #200)."""
    from backend.services.kanal.schreiber import _mal, _mengen_faktor

    if art == ART_MEAN:
        return [{"kanal_id": kanal_id, "start_ts": int(round(z["start_ts"])), "sum": None, "state": None,
                 "mean": float(z["mean"]), "min": None if z["min"] is None else float(z["min"]),
                 "max": None if z["max"] is None else float(z["max"]), "familie": FAMILIE_SPIEGEL}
                for z in roh if z["mean"] is not None]
    faktor = 1.0 if art == ART_STAND else _mengen_faktor(meta)   # ein Stand wird nie umgerechnet (F-58)
    if faktor is None:
        return None
    return [{"kanal_id": kanal_id, "start_ts": int(round(z["start_ts"])), "sum": _mal(z["sum"], faktor),
             "state": _mal(z["state"], faktor), "mean": None, "min": None, "max": None,
             "familie": FAMILIE_SPIEGEL} for z in roh]


async def _einfuegen(db: AsyncSession, zeilen: list[dict]) -> int:
    from backend.services.kanal.schreiber import _zeilen_einfuegen

    return await _zeilen_einfuegen(db, zeilen)


# ── Nachfüllen ──────────────────────────────────────────────────────────────


async def _fuelle_kanal(sitzungen: Sitzungen, anlage_id: int, ziel: _Ziel, ha_svc, ts_bis_jetzt: int,
                        erg: NachfuellErgebnis, block_stunden: int) -> tuple[Optional[int], Optional[str], int]:
    """Vorgeschichte EINES Kanals füllen. Returns ``(kanal_id, grund, neue_zeilen)`` — ``kanal_id`` ``None``,
    solange es den Kanal nicht gibt (HA hat keine Zeile); ``grund`` nennt, warum nichts zu füllen war."""
    from backend.services.kanal.schreiber import kanaele_holen

    async with sitzungen() as db:
        kanal, erste_ts, erste_q = await _erste(db, anlage_id, ziel.key)
    kanal_id = kanal.id if kanal is not None else None
    if erste_q is not None and (erste_q.familie != FAMILIE_SPIEGEL or erste_q.statistic_id != ziel.eid):
        return kanal_id, "vorgeschichte_andere_quelle", 0
    obergrenze = (erste_ts - 1) if erste_ts is not None else ts_bis_jetzt
    neu = 0
    while True:
        anker = await asyncio.to_thread(ha_svc.get_stundenzeile_bis, ziel.eid, obergrenze)
        if anker is None:
            # „Historie zu Ende" — oder HA ist still weg (WebSocket: die Leser liefern dann None statt zu
            # werfen). Nur das erste setzt eine Marke; das zweite ist ein Fehler, der nächste Lauf setzt fort.
            _ha_erreichbar(ha_svc)
            break
        a_ts = float(anker["start_ts"])
        gelesen = await asyncio.to_thread(
            ha_svc.get_stundenzeilen_mehrere, {ziel.eid: a_ts - block_stunden * _STUNDE}, a_ts)
        if ziel.eid not in gelesen:
            _ha_erreichbar(ha_svc)
            return kanal_id, "ha_kennt_sensor_nicht", neu
        meta, roh = gelesen[ziel.eid]
        if not roh:
            _ha_erreichbar(ha_svc)
            break
        async with sitzungen() as db:
            if kanal is None:
                if ziel.art == ART_MEAN:
                    kanal = Kanal(anlage_id=anlage_id, key=ziel.key, art=ART_MEAN, einheit=meta.unit or "")
                    db.add(kanal)
                    await db.flush()
                else:
                    kanal = (await kanaele_holen(db, anlage_id, {ziel.key: (ziel.art, ziel.einheit)}))[ziel.key]
                kanal_id = kanal.id
            elif ziel.art == ART_MEAN and kanal.einheit != (meta.unit or ""):
                return kanal_id, "einheit_abweichend", neu
            zeilen = _zeilen_aus_ha(kanal.id, ziel.art, meta, roh)
            if zeilen is None:
                return kanal_id, "ohne_summe", neu
            if not zeilen:
                obergrenze = int(round(roh[0]["start_ts"])) - 1
                continue
            neu += await _einfuegen(db, zeilen)
            erste_neu = min(z["start_ts"] for z in zeilen)
            q = (await db.execute(
                select(KanalQuelle).where(KanalQuelle.kanal_id == kanal.id)
                .order_by(KanalQuelle.gueltig_ab).limit(1)
            )).scalar_one_or_none()
            if q is None:
                db.add(KanalQuelle(kanal_id=kanal.id, gueltig_ab=erste_neu, familie=FAMILIE_SPIEGEL,
                                   statistic_id=ziel.eid, offset=0.0))
            elif q.gueltig_ab > erste_neu and q.familie == FAMILIE_SPIEGEL and q.statistic_id == ziel.eid:
                await db.execute(update(KanalQuelle).where(and_(
                    KanalQuelle.kanal_id == kanal.id, KanalQuelle.gueltig_ab == q.gueltig_ab,
                )).values(gueltig_ab=erste_neu))
        erg.bloecke += 1
        obergrenze = erste_neu - 1
    return kanal_id, None, neu


def _ha_erreichbar(ha_svc) -> None:
    """Wirft, wenn HA nicht (mehr) erreichbar ist — ein leeres Ergebnis heißt dann nichts."""
    if not ha_svc.is_available:
        raise RuntimeError("HA-Langzeitstatistik während des Nachfüllens nicht erreichbar")


async def _marken(db: AsyncSession, anlage_id: int) -> dict[str, tuple[int, Optional[str]]]:
    """``{kanal_key: (kanal_id, statistic_id der Marke | None)}`` aller Kanäle der Anlage — ein Statement."""
    rows = (await db.execute(
        select(Kanal.key, Kanal.id, KanalNachfuellung.statistic_id)
        .outerjoin(KanalNachfuellung, KanalNachfuellung.kanal_id == Kanal.id)
        .where(Kanal.anlage_id == anlage_id)
    )).all()
    return {key: (kid, sid) for key, kid, sid in rows}


async def nachfuellen_spiegel(
    sitzungen: Sitzungen, anlage_id: int, *, jetzt: datetime, ha_svc=None,
    block_stunden: int = BLOCK_STUNDEN, nur_vorhandene: bool = False, beim_beginn=None,
) -> NachfuellErgebnis:
    """Die Spiegel-Kanäle einer Anlage mit HAs ganzer Historie der heutigen Entity füllen — **je Kanal
    einmal** (Marke ``kanal_nachfuellung`` je Kanal und Entity).

    * Ein Kanal, dessen Marke auf seine heutige Entity zeigt, wird **nicht** bei HA angefragt
      (``schon_gefuellt``).
    * Ohne Marke (neuer Kanal, oder die Zuordnung zeigt jetzt auf eine andere Entity) wird gefüllt; die
      Marke entsteht danach — auch wenn es nichts zu füllen gab (``grund`` in ``ergebnis``), damit derselbe
      Kanal nicht stündlich neu fragt. Ein Fehler setzt keine Marke; der nächste Lauf setzt fort.
    * ``nur_vorhandene`` (Anstoß aus dem Stundenlauf): nur Kanäle, die es schon gibt — der Stundenlauf
      legt einen Kanal an, sobald HA für ihn liefert; ein Sensor ohne Langzeitstatistik kostet so keine
      Abfrage je Stunde. Der Startlauf prüft alle Zuordnungen.

    ``jetzt``: Uhr des Laufs; ohne Kanal-Zeile wird bis zur Stunde vor ``jetzt`` gefüllt (wie der
    Stundenlauf, der danach fortschreibt).
    """
    from backend.models.anlage import Anlage
    from backend.services.ha_statistics_service import get_ha_statistics_service

    ha_svc = ha_svc or get_ha_statistics_service()
    erg = NachfuellErgebnis(anlage_id)
    stunde = jetzt.replace(minute=0, second=0, microsecond=0)
    async with sitzungen() as db:
        anlage = (await db.execute(select(Anlage).where(Anlage.id == anlage_id))).scalar_one()
        ziele = await _ziele(db, anlage, stunde)
        marken = await _marken(db, anlage_id)
    offen = []
    for ziel in ziele:
        kid, sid = marken.get(ziel.key, (None, None))
        if sid == ziel.eid:
            erg.uebersprungen["schon_gefuellt"] += 1
        elif nur_vorhandene and kid is None:
            erg.uebersprungen["noch_kein_kanal"] += 1
        else:
            offen.append(ziel)
    erg.kanaele = len(offen)
    if not offen:
        return erg
    if not ha_svc.is_available:
        erg.uebersprungen["ha_nicht_erreichbar"] += 1
        return erg
    if beim_beginn is not None:
        await beim_beginn(erg)
    ts_bis_jetzt = _unix(stunde - timedelta(hours=1))
    for ziel in offen:
        try:
            kanal_id, grund, neu = await _fuelle_kanal(sitzungen, anlage_id, ziel, ha_svc, ts_bis_jetzt, erg,
                                                       block_stunden)
        except Exception as e:  # noqa: BLE001 — ein Kanal hält die übrigen nicht auf
            erg.fehler += 1
            logger.warning("Kanal-Nachfüllen %s (Anlage %s) abgebrochen: %s: %s",
                           ziel.key, anlage_id, type(e).__name__, e)
            continue
        if grund:
            erg.uebersprungen[grund] += 1
        if neu:
            erg.gefuellt += 1
            erg.zeilen += neu
        if kanal_id is None:
            continue                       # kein Kanal ⇒ keine Marke; der Stundenlauf legt ihn an, wenn HA liefert
        async with sitzungen() as db:
            await db.merge(KanalNachfuellung(
                kanal_id=kanal_id, statistic_id=ziel.eid, abgeschlossen_ts=_unix(jetzt),
                ergebnis={"zeilen": neu, **({"grund": grund} if grund else {})},
            ))
        erg.markiert += 1
    return erg


# ── Nachfüllen aus den Stundenständen (HA-Bauform S3 E-S3-4; S4 E-S4-3 «Nachbau 2») ───


#: Kennung (``statistic_id``) der Quelle, die HAs Stände von damals (``sensor_snapshots.quelle = ha_statistics``) wörtlich
#: trägt — Familie Mitschrift (Neu-Laden, Konsistenzlauf, Sprung-Prüfung und Sensor-Zuordnung nehmen nur Familie Spiegel als
#: HA-Entity und fragen HA nie nach ihr); das Präfix trennt sie von der MQTT-Kennung des Stundenlaufs.
STAENDE_HA_PRAEFIX = "sensor_snapshots:"
_HERKUNFT_HA = "ha"
_HERKUNFT_MQTT = "mqtt"


@dataclass
class _ZielES:
    """Ein Zähler mit Stundenständen: Kanal-Key, MQTT-Kennung (``statistic_id`` der Mitschrift-Quelle wie im
    Stundenlauf). ``spiegel``: der Spiegel führt den Zähler (``counter_map``) und hält die Marke des Kanals — der
    Stände-Teil steht dann in ``ergebnis["staende"]`` (der Kanal ist der Schlüssel der Marke; sonst Pingpong)."""

    key: str
    mqtt_key: str
    art: str
    einheit: str
    spiegel: bool = False

    def kennung(self, herkunft: str) -> str:
        return STAENDE_HA_PRAEFIX + self.key if herkunft == _HERKUNFT_HA else self.mqtt_key


@dataclass
class EigeneSummeErgebnis(NachfuellErgebnis):
    """Wie ``NachfuellErgebnis``, dazu: ausgeschlossene ``live_fallback``-/``unknown``-Stände, vom Deckel verworfene
    Stunden und die Zahl der gefüllten Reihen, die gröber als stündlich sind (Tagesstände, S4-R-3e)."""

    live_fallback: int = 0
    unknown: int = 0
    deckel_verworfen: int = 0
    tagesstand_reihen: int = 0

    def als_dict(self) -> dict:
        return {**super().als_dict(), "live_fallback": self.live_fallback, "unknown": self.unknown,
                "deckel_verworfen": self.deckel_verworfen, "tagesstand_reihen": self.tagesstand_reihen}


def _ziel(key: str, k, quellen_energy: dict) -> Optional[_ZielES]:
    """Jeder Zähler-Schlüssel mit gültiger MQTT-Kennung und Katalog-Art ``sum``/``stand`` — auch mit HA-Entity, auch ein
    stillgelegtes Gerät (S4-R-N2; S3-R9 berichtigt §10f: HA-konform heißt «wo HA liefert, HAs Werte», nicht «HA-Felder
    nie aus eigenen Ständen»). Aus bleibt nur ``quellen`` «keine» (der Anwender will dort keinen Wert)."""
    from backend.services.kanal import schreiber as sch
    from backend.services.snapshot.keys import QUELLE_KEINE_ENERGY, _mqtt_key_to_sensor_key, _sensor_key_to_mqtt_key

    mqtt_key = _sensor_key_to_mqtt_key(key)
    if not mqtt_key or _mqtt_key_to_sensor_key(mqtt_key) != key:
        return None
    zuord = quellen_energy.get(key)
    if zuord and zuord[0] == QUELLE_KEINE_ENERGY:
        return None
    art, einheit = sch._art_und_einheit(key, k.invs)
    return _ZielES(key, mqtt_key, art, einheit, key in k.counter_map) if art in (ART_SUM, ART_STAND) else None


async def _ziele_eigene_summe(db: AsyncSession, anlage, jetzt: datetime, *, nur_vorhandene: bool) -> list[_ZielES]:
    """Startlauf: jeder Schlüssel mit Stundenständen. Anstoß: nur Kanäle, die es schon gibt UND die Stände haben — der
    Stundenlauf legt den Kanal an, sobald HA oder MQTT liefert; ein Spiegel-Kanal ohne Stände bleibt dem Anstoß fern (keine
    Marke, keine Abfrage je Stunde)."""
    from backend.models.sensor_snapshot import SensorSnapshot
    from backend.services.kanal import schreiber as sch
    from backend.services.snapshot.keys import extract_quellen_energy

    k = await sch._kontext(db, anlage, jetzt)
    mit_staenden = select(SensorSnapshot.sensor_key).where(SensorSnapshot.anlage_id == anlage.id).distinct()
    if nur_vorhandene:
        keys = (await db.execute(select(Kanal.key).where(and_(
            Kanal.anlage_id == anlage.id, Kanal.key.in_(mit_staenden))))).scalars().all()
    else:
        keys = (await db.execute(mit_staenden)).scalars().all()
    quellen_energy = extract_quellen_energy(anlage)
    ziele = (_ziel(key, k, quellen_energy) for key in sorted(keys))
    return [z for z in ziele if z is not None]


async def _rohstaende(db: AsyncSession, anlage_id: int, key: str, bis_ts: int,
                      erg: "EigeneSummeErgebnis") -> list[tuple[datetime, float, str]]:
    """Die Stundenstände eines Schlüssels als ``(Beginn der Stunde, Stand, Herkunft)`` mit ``start_ts < bis_ts``.

    Ein Stand zur vollen Stunde ``Z`` ist der Zählerstand AM ENDE der Stunde ``[Z − 1 h, Z)`` (``snapshot_anlage``: HAs
    ``get_value_at(Z)`` bzw. der MQTT-Stand nächst ``Z``) — seine Kanalzeile hat ``start_ts = Z − 3600`` (in absoluter Zeit,
    damit die Umstellungsstunden stimmen). Herkunft: ``ha_statistics`` ⇒ ``ha`` (HAs Summe von damals), ``mqtt_inbound``/
    ``mqtt_live`` ⇒ ``mqtt`` (Rohstand). ``live_fallback``-Zeilen (aus der Leistung abgeleitet) und ``unknown``-Zeilen
    (Herkunft unklassifiziert) sind keine Stände: nicht übernommen, gezählt (``erg.live_fallback``, ``erg.unknown``).
    """
    from backend.models.sensor_snapshot import SensorSnapshot
    from backend.services.snapshot.source import SnapshotSource

    staende: list[tuple[datetime, float, str]] = []
    for zp, wert, quelle in (await db.execute(
        select(SensorSnapshot.zeitpunkt, SensorSnapshot.wert_kwh, SensorSnapshot.quelle).where(and_(
            SensorSnapshot.anlage_id == anlage_id, SensorSnapshot.sensor_key == key,
            func.strftime("%M:%S", SensorSnapshot.zeitpunkt) == "00:00",
        )).order_by(SensorSnapshot.zeitpunkt)
    )).all():
        start = _unix(zp) - _STUNDE
        if start >= bis_ts:
            continue
        if quelle in (SnapshotSource.LIVE_FALLBACK, SnapshotSource.UNKNOWN):
            erg.live_fallback += quelle == SnapshotSource.LIVE_FALLBACK
            erg.unknown += quelle == SnapshotSource.UNKNOWN
            continue
        herkunft = _HERKUNFT_HA if quelle == SnapshotSource.HA_STATISTICS else _HERKUNFT_MQTT
        staende.append((datetime.fromtimestamp(start), wert, herkunft))
    return staende


def _grober_als_stuendlich(staende: list[tuple[datetime, float, str]]) -> bool:
    """Nur für die Zählung (Aktivität): unterer Median der Abstände aufeinanderfolgender Stände über ``TAKT_MAX_S``
    (``median_low``: bei gerader Zahl der kleinere der beiden mittleren; ein einzelner Stand ist kein Takt)."""
    from statistics import median_low

    ts = [_unix(t) for t, *_ in staende]
    abstaende = [b - a for a, b in zip(ts, ts[1:])]
    return bool(abstaende) and median_low(abstaende) > TAKT_MAX_S


def _verworfen(zeilen: list[dict]) -> int:
    """Stunden, deren Zuwachs der Deckel verwarf: die Summe steht, obwohl HAs Regel aus dem Stand der Stunde einen
    Zuwachs nennt (je Stunde genau ein Stand — ``sensor_snapshots`` ist je Zeitpunkt eindeutig)."""
    from backend.core.berechnungen.ha_summe import PeriodenSumme, ha_summe_der_periode

    n = 0
    for vor, z in zip(zeilen, zeilen[1:]):
        if vor["sum"] is None or z["sum"] is None or abs(z["sum"] - vor["sum"]) > _TOL:
            continue
        ha = ha_summe_der_periode(PeriodenSumme(sum=vor["sum"], state=vor["state"]), [z["state"]])
        n += ha is not None and ha.sum - vor["sum"] > _TOL
    return n


@dataclass
class _StaendeAbschnitt:
    """Ein Lauf aufeinanderfolgender Stände derselben Herkunft — eine Mitschrift-Quelle im Kanal (``kennung``,
    ``offset``). ``an_quelle``: ``gueltig_ab`` der ersten Quelle des Kanals, an die der Abschnitt anschließt (dieselbe
    Kennung), sonst ``None`` (eigene, neue Quelle)."""

    herkunft: str
    staende: list
    kennung: str = ""
    zeilen: list = field(default_factory=list)
    offset: float = 0.0
    an_quelle: Optional[int] = None


def _laeufe(staende: list[tuple[datetime, float, str]], ziel: _ZielES) -> list[_StaendeAbschnitt]:
    out: list[_StaendeAbschnitt] = []
    for t, w, h in staende:
        if not out or out[-1].herkunft != h:
            out.append(_StaendeAbschnitt(h, [], ziel.kennung(h)))
        out[-1].staende.append((t, w))
    return out


def _wert(z, art: str) -> Optional[float]:
    """Der Rohwert einer Zeile, über den der Kanal sein Δ bildet: ``sum`` bzw. beim Stand ``state`` (``lesen.py``)."""
    v = z["state"] if art == ART_STAND else z["sum"]
    return None if v is None else float(v)


def _woertlich(kanal: Kanal, staende) -> list[dict]:
    """HAs Stände von damals wörtlich (``quelle = ha_statistics``: HAs Summe bzw. beim Stand HAs ``state``): keine
    Reset-Regel, kein Deckel — wie eine Spiegel-Zeile, nur ohne HAs ``state`` neben der Summe."""
    from backend.services.kanal.schreiber import _zeile

    if kanal.art == ART_STAND:
        return [_zeile(kanal.id, _unix(t), FAMILIE_MITSCHRIFT, state=float(w)) for t, w in staende]
    return [_zeile(kanal.id, _unix(t), FAMILIE_MITSCHRIFT, sum=float(w)) for t, w in staende]


async def _eigene_summe(db: AsyncSession, k, kanal: Kanal, ziel: _ZielES, staende) -> list[dict]:
    """Rohstände (MQTT) nach HAs Regel über DIESELBE Rechenstelle wie der Stundenlauf (``schreiber._eigene_summe_zeilen``:
    90-%-Regel, Deckel als Schreibfilter), ab dem ersten Stand als Nullpunkt. Die Quelle verwaltet das Nachfüllen."""
    from backend.services.kanal import schreiber as sch

    eigen = KanalQuelle(familie=FAMILIE_MITSCHRIFT, statistic_id=ziel.mqtt_key)   # nur Kennung, nicht gespeichert
    return await sch._eigene_summe_zeilen(db, k, sch._KanalStand(kanal, None, eigen), ziel.key, ziel.mqtt_key, staende)


async def _naht_gleiche_quelle(db, k, kanal: Kanal, ziel: _ZielES, ab: _StaendeAbschnitt, anker,
                               erg: "EigeneSummeErgebnis") -> Optional[str]:
    """Der letzte Abschnitt schließt an die erste Kanal-Zeile DERSELBEN Quelle an: er übernimmt ihren ``offset``.
    Wörtlich (HA): die Naht-Stunde trägt die Differenz der Summen. MQTT: die Rechnung läuft über den Stand der ersten
    Zeile weiter, und alle Summen werden so verschoben, dass die Naht-Stunde den Zuwachs nach HAs Regel trägt — die Zeilen
    ab dem Anker bleiben unberührt (Bericht E-S3-4). ``None`` oder der Grund, warum nicht."""
    if ab.herkunft == _HERKUNFT_HA or kanal.art != ART_SUM:
        ab.zeilen = _woertlich(kanal, ab.staende) if ab.herkunft == _HERKUNFT_HA else await _eigene_summe(
            db, k, kanal, ziel, ab.staende)
        return None
    if anker.sum is None or anker.state is None:
        return "anker_ohne_stand"
    zeilen = await _eigene_summe(db, k, kanal, ziel, [*ab.staende, (datetime.fromtimestamp(anker.start_ts),
                                                                    float(anker.state))])
    erg.deckel_verworfen += _verworfen(zeilen)
    naht = zeilen.pop() if zeilen and zeilen[-1]["start_ts"] == anker.start_ts else None
    verschiebung = float(anker.sum) - (naht["sum"] if naht is not None else zeilen[-1]["sum"]) if zeilen else 0.0
    for z in zeilen:
        z["sum"] += verschiebung
    ab.zeilen = zeilen
    return None


def _offsets_rueckwaerts(abschnitte: list[_StaendeAbschnitt], art: str, ende_wert: Optional[float]) -> None:
    """Die ``offset`` der Abschnitte von hinten: der letzte endet bei ``ende_wert`` (Kanalwert der ersten Kanal-Zeile
    einer ANDEREN Quelle) bzw. beginnt ohne Anker bei 0; jeder frühere endet beim Kanalwert der ersten Zeile seines
    Nachfolgers. An jeder Quellgrenze trägt die erste Stunde der späteren Quelle damit keinen Zuwachs — wie ein
    Quellwechsel im Stundenlauf, dessen neue Quelle am Kanalwert der alten ansetzt (zwei Summen-Systeme haben keinen
    gemeinsamen Anker; HA beginnt eine neue Statistik ebenso ohne Zuwachs). Ein Abschnitt, der an seine Quelle anschließt
    (``an_quelle``), behält deren ``offset``."""
    nach: Optional[float] = ende_wert
    for ab in reversed(abschnitte):
        letzter, erster = _wert(ab.zeilen[-1], art), _wert(ab.zeilen[0], art)
        if ab.an_quelle is None:
            ab.offset = (nach - letzter) if (nach is not None and letzter is not None) else 0.0
        nach = None if erster is None else erster + ab.offset


async def _plan_eigene_summe(sitzungen: Sitzungen, anlage_id: int, ziel: _ZielES, jetzt: datetime,
                             erg: EigeneSummeErgebnis) -> tuple[Optional[int], Optional[str], list[_StaendeAbschnitt]]:
    """Eine Sitzung: erste Kanal-Zeile und Quelle, Stände davor, Rechnung je Abschnitt; legt einen fehlenden Kanal an.

    **Wo:** nur vor der ersten Kanal-Zeile UND vor dem Beginn der ersten Quelle (``gueltig_ab``) — die Stunden davor hat
    keine Quelle. Die Spiegel-Zeilen eines HA-Felds beginnen damit, wo HAs Statistik beginnt (der Spiegel läuft zuerst);
    innere Lücken bleiben Lücken (S3-R9 (1)); eine Zeit, die der Anwender verworfen hat (die Quelle steht, ihre Zeilen
    nicht: Werkbank, ``verworfen_ts``), bleibt leer (Grund ``vorgeschichte_andere_quelle``)."""
    from backend.models.anlage import Anlage
    from backend.services.kanal import schreiber as sch

    async with sitzungen() as db:
        kanal, erste_ts, erste_q = await _erste(db, anlage_id, ziel.key)
        kanal_id = kanal.id if kanal is not None else None
        bis_ts = erste_ts if erste_ts is not None else _unix(jetzt.replace(minute=0, second=0, microsecond=0))
        grenze = min(bis_ts, erste_q.gueltig_ab) if erste_q is not None else bis_ts
        alle = await _rohstaende(db, anlage_id, ziel.key, bis_ts, erg)
        staende = [s for s in alle if _unix(s[0]) < grenze]
        if not staende:
            return kanal_id, "vorgeschichte_andere_quelle" if alle else "keine_staende", []
        anlage = (await db.execute(select(Anlage).where(Anlage.id == anlage_id))).scalar_one()
        if kanal is None:
            kanal = (await sch.kanaele_holen(db, anlage_id, {ziel.key: (ziel.art, ziel.einheit)}))[ziel.key]
        k = await sch._kontext(db, anlage, jetzt)
        anker = None if erste_ts is None else (await db.execute(select(KanalStatistik).where(and_(
            KanalStatistik.kanal_id == kanal.id, KanalStatistik.start_ts == erste_ts)))).scalar_one()
        abschnitte = _laeufe(staende, ziel)
        letzter = abschnitte[-1]
        gleich = (anker is not None and erste_q is not None and erste_q.familie == FAMILIE_MITSCHRIFT
                  and erste_q.statistic_id == letzter.kennung)
        for ab in abschnitte[:-1] if gleich else abschnitte:
            ab.zeilen = _woertlich(kanal, ab.staende) if ab.herkunft == _HERKUNFT_HA else await _eigene_summe(
                db, k, kanal, ziel, ab.staende)
            erg.deckel_verworfen += _verworfen(ab.zeilen) if ab.herkunft == _HERKUNFT_MQTT else 0
        if gleich:
            grund = await _naht_gleiche_quelle(db, k, kanal, ziel, letzter, anker, erg)
            if grund:
                return kanal.id, grund, []
            letzter.an_quelle, letzter.offset = erste_q.gueltig_ab, float(erste_q.offset)
        abschnitte = [ab for ab in abschnitte if ab.zeilen]
        ende = None
        if anker is not None and not gleich:
            roh = _wert({"sum": anker.sum, "state": anker.state}, kanal.art)
            ende = None if roh is None else roh + float(erste_q.offset if erste_q is not None else 0.0)
        if abschnitte:
            _offsets_rueckwaerts(abschnitte, kanal.art, ende)
            erg.tagesstand_reihen += _grober_als_stuendlich(staende)
        return kanal.id, None, abschnitte


async def _quellen_im_block(db: AsyncSession, kanal_id: int, abschnitte: list[_StaendeAbschnitt], beginn: list[int],
                            gueltig: dict[int, int]) -> None:
    """Je Abschnitt im Block seine Quelle: anlegen (erste Zeile des Abschnitts in diesem Block) oder ``gueltig_ab`` auf sie
    senken — so beginnt jede Quelle nach jedem Block an ihrer ersten geschriebenen Zeile (ein abgebrochener Lauf setzt an
    der dann ersten Zeile fort)."""
    for i, erste in enumerate(beginn):
        if erste is None:
            continue
        ab = abschnitte[i]
        if i not in gueltig:
            db.add(KanalQuelle(kanal_id=kanal_id, gueltig_ab=erste, familie=FAMILIE_MITSCHRIFT, statistic_id=ab.kennung,
                               offset=ab.offset))
        elif gueltig[i] > erste:
            await db.execute(update(KanalQuelle).where(and_(
                KanalQuelle.kanal_id == kanal_id, KanalQuelle.gueltig_ab == gueltig[i])).values(gueltig_ab=erste))
        gueltig[i] = min(erste, gueltig.get(i, erste))


async def _fuelle_eigene_summe(sitzungen: Sitzungen, anlage_id: int, ziel: _ZielES, jetzt: datetime,
                               erg: EigeneSummeErgebnis, block_stunden: int) -> tuple[Optional[int], Optional[str], int]:
    """Vorgeschichte EINES Kanals aus den Stundenständen. Rechnung in einer Sitzung, Schreiben blockweise rückwärts
    (jüngster Block zuerst) in je einer kurzen Sitzung, ``ON CONFLICT DO NOTHING``; jeder Block legt die Quellen seiner
    Abschnitte an bzw. senkt ihr ``gueltig_ab``. Abgebrochen ⇒ der nächste Lauf rechnet bis zur dann ersten Zeile neu
    (derselbe Abschnitt schließt an dieselbe Quelle an ⇒ dieselben Kanalwerte)."""
    kanal_id, grund, abschnitte = await _plan_eigene_summe(sitzungen, anlage_id, ziel, jetzt, erg)
    zeilen = [(i, z) for i, ab in enumerate(abschnitte) for z in ab.zeilen]
    gueltig = {i: ab.an_quelle for i, ab in enumerate(abschnitte) if ab.an_quelle is not None}
    neu = 0
    for ende in range(len(zeilen), 0, -block_stunden):
        block = zeilen[max(0, ende - block_stunden):ende]
        beginn: list = [None] * len(abschnitte)
        for i, z in reversed(block):
            beginn[i] = z["start_ts"]
        async with sitzungen() as db:
            neu += await _einfuegen(db, [z for _, z in block])
            await _quellen_im_block(db, kanal_id, abschnitte, beginn, gueltig)
        erg.bloecke += 1
    return kanal_id, grund, neu


async def _marken_staende(db: AsyncSession, anlage_id: int) -> dict[str, tuple[int, Optional[str], dict]]:
    """``{kanal_key: (kanal_id, statistic_id der Marke | None, ergebnis)}`` — wie ``_marken``, dazu das Ergebnis (der
    Stände-Teil eines Spiegel-Kanals steht in ``ergebnis["staende"]``)."""
    rows = (await db.execute(
        select(Kanal.key, Kanal.id, KanalNachfuellung.statistic_id, KanalNachfuellung.ergebnis)
        .outerjoin(KanalNachfuellung, KanalNachfuellung.kanal_id == Kanal.id)
        .where(Kanal.anlage_id == anlage_id)
    )).all()
    return {key: (kid, sid, erg or {}) for key, kid, sid, erg in rows}


def _schon_gefuellt(ziel: _ZielES, marke: tuple[Optional[int], Optional[str], dict]) -> bool:
    _kid, sid, ergebnis = marke
    return "staende" in ergebnis if ziel.spiegel else sid == ziel.mqtt_key


async def nachfuellen_eigene_summe(
    sitzungen: Sitzungen, anlage_id: int, *, jetzt: datetime, block_stunden: int = BLOCK_STUNDEN,
    nur_vorhandene: bool = False, beim_beginn=None,
) -> EigeneSummeErgebnis:
    """Die Kanäle einer Anlage aus den Stundenständen in ``sensor_snapshots`` füllen — **jeder Zähler-Schlüssel** (auch
    mit HA-Entity; ``_ziel``), **nur vor der ersten Zeile und vor der ersten Quelle** des Kanals (``_plan_eigene_summe``),
    **je Kanal einmal** (Marke ``kanal_nachfuellung``). HAs Stände (``ha_statistics``) wörtlich, MQTT-Rohstände nach HAs
    Regel; Reihen jeder Taktung (S4-R-3e: ein Stand um 00:00 wird die Zeile 23:00 = Grenze des Kalendertags). Kein HA
    nötig. Der Stundenlauf bleibt, wie er ist: er setzt ab der letzten Zeile fort und füllt keine Lücke aus
    ``sensor_snapshots`` (Entscheid Master E-S3-4). Taucht HA-Statistik für Stände-Stunden später auf, ersetzt der Spiegel
    sie nicht (H-5: das Spiegel-Nachfüllen füllt nur vor der ersten Zeile, Neu-Laden nur Spiegel-Abschnitte).

    ``jetzt``: Uhr des Laufs; ohne Kanal-Zeile wird bis zur Stunde vor ``jetzt`` gefüllt (wie der Stundenlauf).
    """
    from backend.models.anlage import Anlage

    erg = EigeneSummeErgebnis(anlage_id)
    async with sitzungen() as db:
        anlage = (await db.execute(select(Anlage).where(Anlage.id == anlage_id))).scalar_one()
        ziele = await _ziele_eigene_summe(db, anlage, jetzt, nur_vorhandene=nur_vorhandene)
        marken = await _marken_staende(db, anlage_id)
    offen = []
    for ziel in ziele:
        if _schon_gefuellt(ziel, marken.get(ziel.key, (None, None, {}))):
            erg.uebersprungen["schon_gefuellt"] += 1
        else:
            offen.append(ziel)
    erg.kanaele = len(offen)
    if offen and beim_beginn is not None:
        await beim_beginn(erg)
    for ziel in offen:
        await _eigene_summe_kanal_mit_marke(sitzungen, anlage_id, ziel, jetzt, erg, block_stunden)
    return erg


async def _marke_setzen(db: AsyncSession, kanal_id: int, ziel: _ZielES, jetzt: datetime, staende: dict) -> None:
    """Marke des Kanals: ohne Spiegel ``statistic_id`` = MQTT-Kennung (wie bisher); mit Spiegel der Stände-Teil in
    ``ergebnis["staende"]`` neben der Marke des Spiegels (deren Kennung bleibt; fehlt sie, trägt die Marke die Kennung der
    HA-Stände — der Spiegel setzt seine eigene, wenn er HA erreicht)."""
    from sqlalchemy.orm.attributes import flag_modified

    if not ziel.spiegel:
        await db.merge(KanalNachfuellung(kanal_id=kanal_id, statistic_id=ziel.mqtt_key, abgeschlossen_ts=_unix(jetzt),
                                         ergebnis=staende))
        return
    m = (await db.execute(select(KanalNachfuellung).where(KanalNachfuellung.kanal_id == kanal_id))).scalar_one_or_none()
    if m is None:
        db.add(KanalNachfuellung(kanal_id=kanal_id, statistic_id=ziel.kennung(_HERKUNFT_HA),
                                 abgeschlossen_ts=_unix(jetzt), ergebnis={"staende": staende}))
        return
    m.ergebnis = {**(m.ergebnis or {}), "staende": staende}
    flag_modified(m, "ergebnis")


async def _eigene_summe_kanal_mit_marke(sitzungen: Sitzungen, anlage_id: int, ziel: _ZielES, jetzt: datetime,
                                        erg: EigeneSummeErgebnis, block_stunden: int) -> None:
    """Einen Kanal füllen und markieren; ein Fehler setzt keine Marke (der nächste Lauf setzt fort)."""
    try:
        kanal_id, grund, neu = await _fuelle_eigene_summe(sitzungen, anlage_id, ziel, jetzt, erg, block_stunden)
    except Exception as e:  # noqa: BLE001 — ein Kanal hält die übrigen nicht auf
        erg.fehler += 1
        logger.warning("Kanal-Nachfüllen eigene Summe %s (Anlage %s) abgebrochen: %s: %s",
                       ziel.key, anlage_id, type(e).__name__, e)
        return
    if grund:
        erg.uebersprungen[grund] += 1
    if neu:
        erg.gefuellt += 1
        erg.zeilen += neu
    if kanal_id is None:
        return                             # kein Kanal (keine Stände) ⇒ keine Marke; der Stundenlauf legt ihn an
    async with sitzungen() as db:
        await _marke_setzen(db, kanal_id, ziel, jetzt, {"zeilen": neu, **({"grund": grund} if grund else {})})
    erg.markiert += 1


# ── Neu-Laden (Konsistenzlauf) ──────────────────────────────────────────────


@dataclass
class _Abschnitt:
    eid: str
    von: int          # erste Stunde der Quelle (gueltig_ab)
    bis: Optional[int]  # erste Stunde der nächsten Quelle (exklusiv) oder None


def abschnitte(quellen: list[KanalQuelle]) -> list[_Abschnitt]:
    """Spiegel-Abschnitte eines Kanals: je Spiegel-Quelle ``[gueltig_ab, nächstes gueltig_ab)``."""
    qs = sorted(quellen, key=lambda q: q.gueltig_ab)
    out = []
    for i, q in enumerate(qs):
        if q.familie == FAMILIE_SPIEGEL and q.statistic_id:
            out.append(_Abschnitt(q.statistic_id, q.gueltig_ab, qs[i + 1].gueltig_ab if i + 1 < len(qs) else None))
    return out


def _wertspalte(art: str) -> str:
    return "state" if art == ART_STAND else "sum"


async def _wert_am_ende(db: AsyncSession, kanal: Kanal, abschnitt: _Abschnitt) -> Optional[float]:
    spalte = getattr(KanalStatistik, _wertspalte(kanal.art))
    bed = [KanalStatistik.kanal_id == kanal.id, KanalStatistik.start_ts >= abschnitt.von, spalte.is_not(None)]
    if abschnitt.bis is not None:
        bed.append(KanalStatistik.start_ts < abschnitt.bis)
    v = (await db.execute(select(spalte).where(and_(*bed)).order_by(KanalStatistik.start_ts.desc()).limit(1))).scalar_one_or_none()
    return None if v is None else float(v)


async def neu_spiegeln(
    sitzungen: Sitzungen, kanal_id: int, ab_ts: int, *, ha_svc, block_stunden: int = BLOCK_STUNDEN,
) -> int:
    """Spiegelzeilen eines Kanals ab ``ab_ts`` durch HAs heutige Zeilen ersetzen. Nie Bestand oder Mitschrift.

    Obergrenze ist die letzte Spiegelzeile zum Zeitpunkt des Plans — was danach kommt, schreibt der
    Stundenlauf. Untergrenze des Löschens ist HAs erste Zeile des Abschnitts: was HA nicht mehr hält, bleibt.
    HA unterwegs unerreichbar ⇒ Fehler, der Block wird nicht angefasst. Returns: Zahl der neu eingefügten Zeilen.
    """
    async with sitzungen() as db:
        kanal = (await db.execute(select(Kanal).where(Kanal.id == kanal_id))).scalar_one()
        quellen = list((await db.execute(select(KanalQuelle).where(KanalQuelle.kanal_id == kanal_id))).scalars().all())
        oben = (await db.execute(select(func.max(KanalStatistik.start_ts)).where(and_(
            KanalStatistik.kanal_id == kanal_id, KanalStatistik.familie == FAMILIE_SPIEGEL,
        )))).scalar_one_or_none()
    if oben is None or kanal.art not in (ART_SUM, ART_STAND, ART_MEAN):
        return 0
    neu = 0
    for ab in abschnitte(quellen):
        a = max(ab_ts, ab.von)
        e = oben if ab.bis is None else min(oben, ab.bis - 1)
        if a > e:
            continue
        # Untergrenze des Löschens: HAs erste Zeile des ABSCHNITTS. Hält HA den Anfang nicht mehr (z. B. „alte
        # Statistik löschen" nach einem Einheitenwechsel), bleibt darunter stehen, was da ist (Nachmessung E2, 2b).
        kz = await asyncio.to_thread(ha_svc.get_stundenzeilen_kennzahlen, ab.eid, ab.von - 1, e)
        if kz is None:
            _ha_erreichbar(ha_svc)
            continue                       # HA kennt die Entity nicht mehr — nichts löschen
        if not kz["anzahl"] or kz["erste_ts"] is None:
            continue
        ha_erste = int(round(kz["erste_ts"]))
        cursor = a - 1                     # exklusiv
        while cursor < e:
            ende = min(e, cursor + block_stunden * _STUNDE)
            gelesen = await asyncio.to_thread(ha_svc.get_stundenzeilen_mehrere, {ab.eid: cursor}, ende)
            if ab.eid not in gelesen:
                _ha_erreichbar(ha_svc)     # still weg ⇒ Fehler; sonst: HA kennt die Entity nicht mehr
                break                      # — in beiden Fällen nichts löschen
            meta, roh = gelesen[ab.eid]
            letzter = ende >= e
            if not roh:
                # HA liefert für diesen Block nichts (Statistik dort gelöscht?): NICHT nachziehen — ein
                # Neu-Laden soll eine Korrektur übernehmen, keine Historie wegwerfen.
                cursor = ende
                continue
            unten = max(cursor, ha_erste - 1)
            async with sitzungen() as db:
                vorher = await _wert_am_ende(db, kanal, ab) if (letzter and kanal.art != ART_MEAN) else None
                zeilen = _zeilen_aus_ha(kanal.id, kanal.art, meta, roh) or []
                await db.execute(delete(KanalStatistik).where(and_(
                    KanalStatistik.kanal_id == kanal.id, KanalStatistik.familie == FAMILIE_SPIEGEL,
                    KanalStatistik.start_ts > unten, KanalStatistik.start_ts <= ende,
                )))
                # HA-Bauform S5 E-S5-1c (S5-R7c i): ab dem Tag des vorigen Stands, offen nach oben (auch der
                # Offset der späteren Quelle unten).
                for aid, von in (await merken.tag_des_vorstands(db, [kanal.id], unten + 1)).items():
                    merken.invalidiere(aid, von=von, db=db)
                neu += await _einfuegen(db, zeilen)
                if letzter and kanal.art != ART_MEAN and ab.bis is not None and vorher is not None:
                    nachher = await _wert_am_ende(db, kanal, ab)
                    if nachher is not None and abs(nachher - vorher) > _TOL:
                        await db.execute(update(KanalQuelle).where(and_(
                            KanalQuelle.kanal_id == kanal.id, KanalQuelle.gueltig_ab >= ab.bis,
                        )).values(offset=KanalQuelle.offset + (nachher - vorher)))
            cursor = ende
    return neu


# ── Auslöser: Startlauf und Anstoß aus dem Stundenlauf ─────────────────────


async def nachfuellen_anlage(
    sitzungen: Sitzungen, anlage_id: int, *, jetzt: datetime, ha_svc=None,
    block_stunden: int = BLOCK_STUNDEN, nur_vorhandene: bool = False,
) -> NachfuellErgebnis:
    """Spiegel aus HA (``_nachfuellen_anlage_spiegel``) und — seit E-S3-4 — die Eigene Summe aus den Stundenständen
    (``_nachfuellen_eigene_summe_protokolliert``, ohne HA). Rückgabe: das Ergebnis des Spiegels; das der Eigenen Summe
    steht in ``.eigene_summe`` (``None``, wenn ihr Lauf abbrach — geloggt, der Spiegel bleibt)."""
    erg = await _nachfuellen_anlage_spiegel(sitzungen, anlage_id, jetzt=jetzt, ha_svc=ha_svc,
                                            block_stunden=block_stunden, nur_vorhandene=nur_vorhandene)
    try:
        erg.eigene_summe = await _nachfuellen_eigene_summe_protokolliert(
            sitzungen, anlage_id, jetzt=jetzt, block_stunden=block_stunden, nur_vorhandene=nur_vorhandene)
    except Exception as e:  # noqa: BLE001 — der Spiegel-Teil ist geschrieben; der nächste Lauf setzt fort
        logger.warning("Kanal-Nachfüllen eigene Summe (Anlage %s) fehlgeschlagen: %s: %s",
                       anlage_id, type(e).__name__, e)
    return erg


async def _nachfuellen_eigene_summe_protokolliert(
    sitzungen: Sitzungen, anlage_id: int, *, jetzt: datetime, block_stunden: int, nur_vorhandene: bool,
) -> EigeneSummeErgebnis:
    """``nachfuellen_eigene_summe`` mit EINEM Protokolleintrag (N-532) — nur, wenn Zeilen geschrieben wurden oder ein Kanal
    abbrach (Nachmessung E-S3-4, M-1: Schlüssel ohne Kanal — nur ``live_fallback``-/``unknown``-Stände — bekommen keine Marke und
    werden bei jedem Start neu geprüft; ohne diese Bedingung schrieb jeder Start zwei leere Einträge). Sonst nur ``debug``."""
    from backend.services.activity_service import log_activity

    erg = await nachfuellen_eigene_summe(sitzungen, anlage_id, jetzt=jetzt, block_stunden=block_stunden,
                                         nur_vorhandene=nur_vorhandene)
    if not (erg.gefuellt or erg.fehler):
        logger.debug("Kanal-Nachfüllen eigene Summe (Anlage %s): nichts geschrieben — %s", anlage_id, erg.als_dict())
        return erg
    async with sitzungen() as db:
        await log_activity(
            kategorie="scheduler",
            aktion="Kanalstatistik: Nachfüllen aus den Zählerständen " + ("abgeschlossen" if erg.fehler == 0 else "unvollständig"),
            erfolg=erg.fehler == 0,
            details=(f"{erg.gefuellt} von {erg.kanaele} offenen Zählern gefüllt, {erg.zeilen} Stundenzeilen in "
                     f"{erg.bloecke} Blöcken; {erg.live_fallback} aus der Leistung abgeleitete"
                     + (f" und {erg.unknown} unklassifizierte" if erg.unknown else "") + " Stände nicht übernommen, "
                     f"{erg.deckel_verworfen} Stunden vom Plausibilitätsdeckel verworfen"
                     + (f"; {erg.tagesstand_reihen} Reihen mit Tagesständen" if erg.tagesstand_reihen else "")
                     + (f"; {erg.fehler} Kanäle abgebrochen (nächster Lauf setzt fort)" if erg.fehler else "")),
            details_json=erg.als_dict(), anlage_id=anlage_id, db=db,
        )
    return erg


async def _nachfuellen_anlage_spiegel(
    sitzungen: Sitzungen, anlage_id: int, *, jetzt: datetime, ha_svc=None,
    block_stunden: int = BLOCK_STUNDEN, nur_vorhandene: bool = False,
) -> NachfuellErgebnis:
    """``nachfuellen_spiegel`` mit Protokoll: „begonnen" und „abgeschlossen"/„unvollständig" — nur, wenn ein
    Kanal offen war (ein Lauf ohne offenen Kanal schreibt nichts, auch kein Protokoll). Jeder Eintrag in der
    Sitzung, die ihn schreibt (N-532)."""
    from backend.services.activity_service import log_activity

    async def _begonnen(e: NachfuellErgebnis) -> None:
        async with sitzungen() as db:
            await log_activity(kategorie="scheduler", aktion="Kanalstatistik: Nachfüllen aus HA begonnen",
                               details=f"{e.kanaele} Kanäle ohne Marke", anlage_id=anlage_id, db=db)

    erg = await nachfuellen_spiegel(sitzungen, anlage_id, jetzt=jetzt, ha_svc=ha_svc,
                                    block_stunden=block_stunden, nur_vorhandene=nur_vorhandene,
                                    beim_beginn=_begonnen)
    if not erg.kanaele or erg.uebersprungen.get("ha_nicht_erreichbar"):
        return erg
    async with sitzungen() as db:
        await log_activity(
            kategorie="scheduler",
            aktion="Kanalstatistik: Nachfüllen aus HA " + ("abgeschlossen" if erg.fehler == 0 else "unvollständig"),
            erfolg=erg.fehler == 0,
            details=(f"{erg.gefuellt} von {erg.kanaele} offenen Kanälen gefüllt, {erg.zeilen} Stundenzeilen in "
                     f"{erg.bloecke} Blöcken" + (f", {erg.fehler} Kanäle abgebrochen (nächster Lauf setzt fort)"
                                                  if erg.fehler else "")),
            details_json=erg.als_dict(), anlage_id=anlage_id, db=db,
        )
    return erg


async def nachfuellen_alle_anlagen(sitzungen: Sitzungen, *, jetzt: Optional[datetime] = None, ha_svc=None,
                                   nur_vorhandene: bool = False) -> list[NachfuellErgebnis]:
    from backend.models.anlage import Anlage

    async with sitzungen() as db:
        ids = list((await db.execute(select(Anlage.id).order_by(Anlage.id))).scalars().all())
    return [await nachfuellen_anlage(sitzungen, aid, jetzt=jetzt or datetime.now(), ha_svc=ha_svc,
                                     nur_vorhandene=nur_vorhandene) for aid in ids]


async def nachfuellen_nach_dem_start(*, warte_s: float = 120.0) -> None:
    """Hintergrund-Aufgabe nach dem Start (``main.py``): jeder Kanal ohne Marke für seine Entity.

    Blockiert weder den Start (eigene Aufgabe, erst nach ``warte_s``) noch den Stundenlauf (kurze
    Schreib-Transaktionen je Block, HA-Abrufe außerhalb). Ein Fehler bleibt hier und wird geloggt.
    """
    from backend.core.database import get_session

    try:
        await asyncio.sleep(warte_s)
        await nachfuellen_alle_anlagen(get_session)
    except Exception as e:  # noqa: BLE001 — eine Hintergrund-Aufgabe darf den Prozess nicht stören
        logger.warning("Kanal-Nachfüllen nach dem Start fehlgeschlagen: %s: %s", type(e).__name__, e)


#: Die laufende Anstoß-Aufgabe (höchstens eine — ein langer Lauf wird nicht verdoppelt).
_ANSTOSS: Optional[asyncio.Task] = None


def nachfuellen_anstossen(sitzungen: Optional[Sitzungen] = None, *, jetzt: Optional[datetime] = None,
                          ha_svc=None) -> Optional[asyncio.Task]:
    """Vom Stundenlauf NACH seiner Sitzung gerufen: Kanäle ohne Marke (neu angelegt oder neue Entity) im
    Hintergrund nachfüllen. Kanäle mit Marke kosten dabei keine HA-Abfrage, nur einen Blick in die Tabelle.

    Returns die Aufgabe (Proben warten darauf) oder ``None``, wenn noch eine läuft.
    """
    global _ANSTOSS
    if _ANSTOSS is not None and not _ANSTOSS.done():
        return None

    async def _lauf() -> None:
        from backend.core.database import get_session

        try:
            await nachfuellen_alle_anlagen(sitzungen or get_session, jetzt=jetzt, ha_svc=ha_svc,
                                           nur_vorhandene=True)
        except Exception as e:  # noqa: BLE001
            logger.warning("Kanal-Nachfüllen (Anstoß Stundenlauf) fehlgeschlagen: %s: %s", type(e).__name__, e)

    _ANSTOSS = asyncio.get_running_loop().create_task(_lauf())
    return _ANSTOSS
