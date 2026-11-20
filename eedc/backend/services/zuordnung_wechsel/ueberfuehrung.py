"""Überführung der Wechsel aus dem Aktivitäts-Protokoll (``herkunft = altbestand``) — Auftrag Sitzung 1, Teil D.

Seit dem 25.09.2026 trägt jeder Eintrag ``kategorie = sensor_mapping`` der Feld-Route ``details_json = {field_id, vorher,
nachher}`` (die ``quellen``-Einträge vor und nach der Änderung, ``api/routes/datenquellen.py::set_feld_quelle``) mit Zeit. Jeder
Eintrag, der **sicher** eine wirksame Änderung eines Zählerschlüssels mit eigenen Werten war, wird eine Zeile (``erklaert_ts`` =
Zeit des Eintrags, ``grund`` leer) — **alle** solchen Einträge, nicht nur die Felder des Hinweis-Vermerks, damit B-0 auch die
Vergangenheit schützt.

**Nicht jeder Eintrag ist eine wirksame Änderung** (Messblatt S0 M-H): das Protokoll-``vorher`` ist der ``quellen``-Eintrag, nicht
die wirksame Quelle — leer heißt «kein Eintrag», und dahinter kann eine klassische HA-Zuordnung stehen. Ein leeres ``vorher`` wird
deshalb am Kanal aufgelöst (``kanal_quelle``, die vor der Stunde des Eintrags galt: Familie ``spiegel`` = HA-Entität, ``mitschrift``
= MQTT) und sonst an der letzten Zeile der Reihe davor (``sensor_snapshots.quelle``). Was danach nicht sicher eine wirksame
Änderung war, wird **nicht** überführt; ``ueberfuehre`` zählt je Grund (Rückgabe, Log).

**Nachgefüllte Geschichte ist keine Vor-Quelle** (Korrekturrunde Lab-K, F2): das Nachfüllen von v4.3.1 legte die Geschichte
der heute zugeordneten Entität vor den ersten Eintrag des Kanals. Eine am Kanal aufgelöste Vor-Quelle gilt deshalb nur, wenn
der Kanal den Wechsel selbst zeigt (``_kanal_zeigt_wechsel``: die erste Quellzeile ab ``Stunde − 1 h`` ist der Spiegel der
neuen Entität) — **nur, wenn vor der Stunde keine Stände der Reihe liegen** (``_staende_davor``, Korrekturrunde U3-K,
Nachmessung Lab-K LK-B1: mit eigenen Ständen davor ist die Vor-Quelle echt, und Teil 1 verwarf echte Wechsel HA → MQTT, eine
entfernte Zuordnung oder die erste Zeile von «Fehlgriff, dann zurück») —, und «eigene Werte davor» zählen nicht, wenn vor der Stunde keine Stände der Reihe liegen und jede Kanal-Quelle
davor der Spiegel der neuen Entität ist (``_nur_geschichte_des_neuen``). ``Stunde − 1 h``: eine Änderung zwischen H:00 und
H:05 beginnt im Kanal schon mit der Zeile ``H − 1`` (der Stundenlauf um :05 schreibt sie aus der neuen Entität).

Idempotent zweifach: als Start-Migration läuft sie einmal je Installation (``core/database.py::_run_data_migrations``), und sie
legt keine zweite Zeile mit gleicher Anlage, gleichem Schlüssel und gleicher Zeit an.

**Alt-Vermerke** (``ueberfuehre_vermerke``, Sitzung 4, Bauplan B-7, Konzept S-10 c): der Vermerk ``historie_hinweis`` im
gespeicherten Mapping (bis Sitzung 3b vom Hinweis-Block «Zuordnung geändert» gelesen und quittiert; seither schreibt ihn
niemand) wird je Feld zu einer Zeile — aus dem **jüngsten** Protokoll-Eintrag des Felds (``vorher``, ``nachher``, Zeit, bewertet
wie oben) und nur, wenn die Abfrage nach dem Grund gefragt hätte (``abfrage.haette_gefragt``); sonst verfällt er. Eine Zeile
zum selben Eintrag (aus der Überführung oben) wird nicht doppelt angelegt; der Befund «Zuordnung geändert, Grund fehlt» nennt
sie. Danach trägt kein Mapping den Schlüssel mehr. Läuft **bei jedem Start** (ein importiertes Mapping kann den Schlüssel
wieder mitbringen) und tut ohne Vermerk nichts.
"""

from __future__ import annotations

import logging
from collections import Counter
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm.attributes import flag_modified

from backend.models.zuordnung_wechsel import HERKUNFT_ALTBESTAND, ZuordnungWechsel
from backend.services.snapshot.keys import (
    QUELLE_HA_ENERGY,
    QUELLE_KEINE_ENERGY,
    _energy_field_id_to_sensor_key,
    _sensor_key_to_mqtt_key,
)
from backend.services.zuordnung_wechsel.quelle import ART_HA, ART_KEINE, ART_MQTT, hat_eigene_werte, standard_quelle
from backend.services.zuordnung_wechsel.zeitpunkt import ab_ts_aus, vergiss

logger = logging.getLogger(__name__)

#: Gründe, aus denen ein Protokoll-Eintrag NICHT überführt wird (Zählung im Bericht).
GRUND_KEIN_ZAEHLER = "kein_zaehlerschluessel"
GRUND_GERAET_FEHLT = "geraet_geloescht"
GRUND_UNVERAENDERT = "wirksam_unveraendert"
GRUND_UNSICHER = "vorher_unbekannt"
GRUND_OHNE_WERTE = "ohne_eigene_werte"
GRUND_SCHON_DA = "schon_ueberfuehrt"
GRUND_OHNE_PROTOKOLL = "ohne_protokoll"
GRUND_NICHT_GEFRAGT = "nicht_gefragt"
#: Schlüssel des Alt-Vermerks im Mapping (bis Sitzung 3b ``services/datenquellen_historie.HISTORIE_HINWEIS_KEY``).
HISTORIE_HINWEIS_KEY = "historie_hinweis"
UEBERFUEHRT = "ueberfuehrt"
#: Lab-K F2: eine Änderung zwischen H:00 und H:05 beginnt im Kanal schon mit der Zeile ``H − 1`` (Stundenlauf um :05).
VORLAUF_S = 3600


def _aus_eintrag(sensor_key: str, eintrag) -> Optional[dict]:
    """Ein ``quellen``-Eintrag des Protokolls als wirksame Quelle — ``None``, wenn er sie nicht festlegt (kein Eintrag)."""
    if not isinstance(eintrag, dict) or not eintrag.get("quelle"):
        return None
    quelle = eintrag["quelle"]
    if quelle in QUELLE_HA_ENERGY:
        return {"art": ART_HA, "entity_id": eintrag.get("entity_id")} if eintrag.get("entity_id") else None
    if quelle == QUELLE_KEINE_ENERGY:
        return {"art": ART_KEINE}
    if quelle == "mqtt_gateway":
        # Topic der damaligen Gateway-Zeile unbekannt (die Zeile kann sich seither geändert haben) — der Schlüssel fehlt.
        return {"art": ART_MQTT, "mqtt_key": _sensor_key_to_mqtt_key(sensor_key)}
    return standard_quelle(sensor_key)  # mqtt_inbound_standard (Stempel der Materialisierung)


async def _kanal_quellen(db, anlage_id: int, sensor_key: str) -> list[tuple[int, str, Optional[str]]]:
    """Die Quellzeilen des Kanals ``(gueltig_ab, familie, statistic_id)``, aufsteigend."""
    from backend.models.kanal import Kanal, KanalQuelle

    return [tuple(r) for r in (await db.execute(
        select(KanalQuelle.gueltig_ab, KanalQuelle.familie, KanalQuelle.statistic_id)
        .join(Kanal, Kanal.id == KanalQuelle.kanal_id)
        .where(Kanal.anlage_id == anlage_id, Kanal.key == sensor_key).order_by(KanalQuelle.gueltig_ab))).all()]


def _ist_spiegel_von(q, neu: Optional[dict]) -> bool:
    from backend.models.kanal import FAMILIE_SPIEGEL

    return (isinstance(neu, dict) and neu.get("art") == ART_HA and bool(neu.get("entity_id"))
            and q[1] == FAMILIE_SPIEGEL and q[2] == neu["entity_id"])


async def _vorher_aus_kanal(db, anlage_id: int, sensor_key: str, ts: datetime,
                            neu: Optional[dict] = None) -> Optional[dict]:
    """Die Quelle des Kanals **vor** dem Eintrag: größtes ``gueltig_ab`` vor der Stunde von ``ts`` (Bauplan §8 Nr. 21 — die
    neue Quelle trägt die Stunde des Wechsels selbst: Änderung 10:47 ⇒ ``gueltig_ab`` 10:00). Korrekturrunde Lab-K (F2,
    «ab Stunde − 1 h»): eine Quelle der neuen Entität ab ``Stunde − 1 h`` ist die neue selbst (Änderung zwischen H:00 und H:05
    — der Stundenlauf um :05 schreibt die Stunde davor schon aus ihr) und keine Vor-Quelle."""
    from backend.models.kanal import FAMILIE_MITSCHRIFT, FAMILIE_SPIEGEL

    stunde = int(ts.replace(minute=0, second=0, microsecond=0).timestamp())
    davor = [q for q in await _kanal_quellen(db, anlage_id, sensor_key) if q[0] < stunde]
    if davor and davor[-1][0] >= stunde - VORLAUF_S and _ist_spiegel_von(davor[-1], neu):
        davor = davor[:-1]
    if not davor:
        return None
    _gueltig_ab, familie, statistic_id = davor[-1]
    if familie == FAMILIE_SPIEGEL and statistic_id:
        return {"art": ART_HA, "entity_id": statistic_id}
    if familie == FAMILIE_MITSCHRIFT:
        return {"art": ART_MQTT, "mqtt_key": _sensor_key_to_mqtt_key(sensor_key)}
    return None


async def _vorher_aus_reihe(db, anlage_id: int, sensor_key: str, ts: datetime) -> Optional[dict]:
    """Die Art der letzten Zeile der Reihe vor ``ts`` (Entität unbekannt)."""
    from backend.models.sensor_snapshot import SensorSnapshot

    quelle = (await db.execute(
        select(SensorSnapshot.quelle)
        .where(SensorSnapshot.anlage_id == anlage_id, SensorSnapshot.sensor_key == sensor_key,
               SensorSnapshot.zeitpunkt < ts)
        .order_by(SensorSnapshot.zeitpunkt.desc()).limit(1)
    )).scalar_one_or_none()
    if quelle == "ha_statistics":
        return {"art": ART_HA}
    if quelle in ("mqtt_inbound", "mqtt_live"):
        return {"art": ART_MQTT, "mqtt_key": _sensor_key_to_mqtt_key(sensor_key)}
    return None


def _sicher_verschieden(alt: dict, neu: dict) -> Optional[bool]:
    """``True`` sicher verschieden, ``False`` sicher gleich, ``None`` nicht entscheidbar (Entität oder Topic fehlt)."""
    if alt.get("art") != neu.get("art"):
        return True
    if alt["art"] == ART_KEINE:
        return False
    if alt["art"] == ART_HA:
        if not alt.get("entity_id") or not neu.get("entity_id"):
            return None
        return alt["entity_id"] != neu["entity_id"]
    if "topic" not in alt or "topic" not in neu:
        return None
    return alt.get("topic") != neu.get("topic")


async def _bewerte(db, eintrag, sensor_key: str) -> tuple[str, Optional[dict], Optional[dict]]:
    dj = eintrag.details_json
    neu = _aus_eintrag(sensor_key, dj.get("nachher")) or standard_quelle(sensor_key)
    alt = _aus_eintrag(sensor_key, dj.get("vorher"))
    aus_kanal = False
    if alt is None:  # kein `quellen`-Eintrag vorher: am Kanal bzw. an der Reihe auflösen
        alt = await _vorher_aus_kanal(db, eintrag.anlage_id, sensor_key, eintrag.timestamp, neu)
        aus_kanal = alt is not None
        alt = alt or await _vorher_aus_reihe(db, eintrag.anlage_id, sensor_key, eintrag.timestamp)
    if alt is None:
        return GRUND_UNSICHER, None, neu
    verschieden = _sicher_verschieden(alt, neu)
    if verschieden is None:
        return GRUND_UNSICHER, alt, neu
    if not verschieden:
        return GRUND_UNVERAENDERT, alt, neu
    stunde = eintrag.timestamp.replace(minute=0, second=0, microsecond=0)
    quellen = await _kanal_quellen(db, eintrag.anlage_id, sensor_key)
    if aus_kanal and not await _staende_davor(db, eintrag.anlage_id, sensor_key, stunde) \
            and not _kanal_zeigt_wechsel(quellen, stunde, neu):
        return GRUND_UNSICHER, None, neu
    if not await hat_eigene_werte(db, eintrag.anlage_id, sensor_key, vor=stunde) \
            or await _nur_geschichte_des_neuen(db, eintrag.anlage_id, sensor_key, quellen, stunde, neu):
        return GRUND_OHNE_WERTE, alt, neu
    return UEBERFUEHRT, alt, neu


async def _staende_davor(db, anlage_id: int, sensor_key: str, stunde: datetime) -> bool:
    """Liegen vor der Stunde Stände der Reihe (Korrekturrunde U3-K, Nachmessung Lab-K LK-B1)? Dann hatte das Feld vor dem
    Eintrag eigene Werte aus der am Kanal aufgelösten Quelle — Teil 1 (``_kanal_zeigt_wechsel``) gilt nur ohne sie: sonst
    verwarf er echte Wechsel im Altbestand (HA → MQTT, Zuordnung entfernt) oder ließ von «Fehlgriff, dann zurück» nur die
    zweite Zeile stehen (HA-Tag der Wallbox 9,0 statt 27,0)."""
    from backend.models.sensor_snapshot import SensorSnapshot

    return (await db.execute(select(SensorSnapshot.id).where(
        SensorSnapshot.anlage_id == anlage_id, SensorSnapshot.sensor_key == sensor_key,
        SensorSnapshot.zeitpunkt < stunde).limit(1))).scalar_one_or_none() is not None


def _kanal_zeigt_wechsel(quellen: list, stunde: datetime, neu: Optional[dict]) -> bool:
    """Korrekturrunde Lab-K F2 Teil 1: eine am Kanal aufgelöste Vor-Quelle (leeres ``vorher``) gilt nur, wenn der Kanal den
    Wechsel selbst zeigt — die erste Quellzeile ab ``Stunde − 1 h`` ist der Spiegel der Entität des ``nachher``. Sonst hat das
    Nachfüllen die Geschichte der heute zugeordneten Entität vor den Eintrag gelegt (Lab P9: aus der Erst-Zuordnung wurde der
    Wechsel «p9_neu → p9_alt»)."""
    ab = int(stunde.timestamp()) - VORLAUF_S
    danach = next((q for q in quellen if q[0] >= ab), None)
    return danach is not None and _ist_spiegel_von(danach, neu)


async def _nur_geschichte_des_neuen(db, anlage_id: int, sensor_key: str, quellen: list, stunde: datetime,
                                    neu: Optional[dict]) -> bool:
    """Lab-K F2 Teil 2: die «eigenen Werte davor» sind nur die nachgefüllte Geschichte des neuen Sensors — vor der Stunde
    liegen keine Stände der Reihe, und jede Kanal-Quelle davor ist der Spiegel der Entität des ``nachher`` (Lab R: Fehlgriff
    10:10, berichtigt 10:20 vor dem nächsten Stundenlauf). Dann hatte das Feld beim Wechsel keine eigenen Werte."""
    davor = [q for q in quellen if q[0] < int(stunde.timestamp())]
    if not davor or not all(_ist_spiegel_von(q, neu) for q in davor):
        return False
    return not await _staende_davor(db, anlage_id, sensor_key, stunde)


async def _geraet_da(db, anlage_id: int, sensor_key: str) -> bool:
    from backend.models.investition import Investition

    if not sensor_key.startswith("inv:"):
        return True
    inv_id = sensor_key.split(":")[1]
    return inv_id.isdigit() and (await db.execute(select(Investition.id).where(
        Investition.id == int(inv_id), Investition.anlage_id == anlage_id))).scalar_one_or_none() is not None


async def ueberfuehre(db) -> Counter:
    """Überführt die Protokoll-Einträge (``flush``, kein Commit). Rückgabe: Zählung je Ergebnis (``ueberfuehrt`` oder Grund)."""
    from backend.models.activity_log import ActivityLog

    zaehlung: Counter = Counter()
    eintraege = (await db.execute(
        select(ActivityLog).where(ActivityLog.kategorie == "sensor_mapping", ActivityLog.anlage_id.isnot(None))
        .order_by(ActivityLog.timestamp, ActivityLog.id)
    )).scalars().all()
    for e in eintraege:
        dj = e.details_json if isinstance(e.details_json, dict) else {}
        field_id = dj.get("field_id")
        if not isinstance(field_id, str) or "vorher" not in dj or isinstance(dj.get("vorher"), bool) \
                or isinstance(dj.get("nachher"), bool):
            continue  # kein Quellen-Eintrag (Vorzeichen, Sammelzeile der Energie-Vorschläge)
        sensor_key = _energy_field_id_to_sensor_key(field_id)
        if sensor_key is None:
            ergebnis, alt, neu = GRUND_KEIN_ZAEHLER, None, None
        elif not await _geraet_da(db, e.anlage_id, sensor_key):
            ergebnis, alt, neu = GRUND_GERAET_FEHLT, None, None   # sonst erbte die nächste Investition dieser ID den Wechsel
        else:
            ergebnis, alt, neu = await _bewerte(db, e, sensor_key)
        if ergebnis == UEBERFUEHRT and (await db.execute(select(ZuordnungWechsel.id).where(
                ZuordnungWechsel.anlage_id == e.anlage_id, ZuordnungWechsel.sensor_key == sensor_key,
                ZuordnungWechsel.erklaert_ts == e.timestamp.replace(microsecond=0)))).first() is not None:
            ergebnis = GRUND_SCHON_DA
        zaehlung[ergebnis] += 1
        if ergebnis != UEBERFUEHRT:
            logger.debug("Überführung: Protokoll %s (%s, %s) nicht überführt: %s", e.id, field_id, e.timestamp, ergebnis)
            continue
        erklaert = e.timestamp.replace(microsecond=0)
        db.add(ZuordnungWechsel(
            anlage_id=e.anlage_id, sensor_key=sensor_key, erklaert_ts=erklaert, ab_ts=ab_ts_aus(erklaert),
            vorher=alt, nachher=neu, grund=None, herkunft=HERKUNFT_ALTBESTAND,
        ))
        await db.flush()
    vergiss(db)
    logger.info("Sensorwechsel: Überführung aus dem Protokoll — %s", dict(sorted(zaehlung.items())))
    return zaehlung


async def _juengster_eintrag(db, anlage_id: int, field_id: str):
    """Der jüngste Protokoll-Eintrag der Feld-Route für ``field_id`` (mit ``vorher``/``nachher``), sonst ``None``."""
    from backend.models.activity_log import ActivityLog

    eintraege = (await db.execute(
        select(ActivityLog).where(ActivityLog.kategorie == "sensor_mapping", ActivityLog.anlage_id == anlage_id)
        .order_by(ActivityLog.timestamp.desc(), ActivityLog.id.desc())
    )).scalars().all()
    for e in eintraege:
        dj = e.details_json if isinstance(e.details_json, dict) else {}
        if dj.get("field_id") == field_id and "vorher" in dj and not isinstance(dj.get("vorher"), bool) \
                and not isinstance(dj.get("nachher"), bool):
            return e
    return None


async def _vermerk_feld(db, anlage_id: int, field_id) -> str:
    """Ein Feld des Vermerks: Zeile anlegen (``UEBERFUEHRT``) oder der Grund, warum es verfällt."""
    from backend.services.zuordnung_wechsel.abfrage import haette_gefragt

    sensor_key = _energy_field_id_to_sensor_key(field_id) if isinstance(field_id, str) else None
    if sensor_key is None:
        return GRUND_KEIN_ZAEHLER
    if not await _geraet_da(db, anlage_id, sensor_key):
        return GRUND_GERAET_FEHLT
    e = await _juengster_eintrag(db, anlage_id, field_id)
    if e is None:
        return GRUND_OHNE_PROTOKOLL
    ergebnis, alt, neu = await _bewerte(db, e, sensor_key)
    if ergebnis != UEBERFUEHRT:
        return ergebnis
    erklaert = e.timestamp.replace(microsecond=0)
    row = ZuordnungWechsel(anlage_id=anlage_id, sensor_key=sensor_key, erklaert_ts=erklaert, ab_ts=ab_ts_aus(erklaert),
                           vorher=alt, nachher=neu, grund=None, herkunft=HERKUNFT_ALTBESTAND)
    if not await haette_gefragt(db, anlage_id, row):
        return GRUND_NICHT_GEFRAGT
    if (await db.execute(select(ZuordnungWechsel.id).where(
            ZuordnungWechsel.anlage_id == anlage_id, ZuordnungWechsel.sensor_key == sensor_key,
            ZuordnungWechsel.erklaert_ts == erklaert))).first() is not None:
        return GRUND_SCHON_DA
    db.add(row)
    await db.flush()
    return UEBERFUEHRT


async def ueberfuehre_vermerke(db) -> Counter:
    """Die Alt-Vermerke ``historie_hinweis`` überführen und entfernen (``flush``, kein Commit). Rückgabe: Zählung je
    Ergebnis (``ueberfuehrt`` oder der Grund, aus dem der Vermerk eines Felds verfällt)."""
    from backend.models.anlage import Anlage

    zaehlung: Counter = Counter()
    vergiss(db)
    for anlage in (await db.execute(select(Anlage).order_by(Anlage.id))).scalars().all():
        mapping = anlage.sensor_mapping
        if not isinstance(mapping, dict) or HISTORIE_HINWEIS_KEY not in mapping:
            continue
        vermerk = mapping.get(HISTORIE_HINWEIS_KEY)
        felder = vermerk.get("felder") if isinstance(vermerk, dict) else None
        for f in felder if isinstance(felder, list) else ():
            ergebnis = await _vermerk_feld(db, anlage.id, f.get("id") if isinstance(f, dict) else None)
            zaehlung[ergebnis] += 1
            vergiss(db, anlage.id)
        neu = dict(mapping)
        neu.pop(HISTORIE_HINWEIS_KEY, None)
        anlage.sensor_mapping = neu
        flag_modified(anlage, "sensor_mapping")
        zaehlung["vermerke_entfernt"] += 1
    await db.flush()
    vergiss(db)
    if zaehlung:
        logger.info("Sensorwechsel: Alt-Vermerke überführt — %s", dict(sorted(zaehlung.items())))
    return zaehlung


async def ueberfuehre_altbestand(session) -> None:
    """Start-Migration (``_apply_once``): Commit macht der Aufrufer."""
    await ueberfuehre(session)
